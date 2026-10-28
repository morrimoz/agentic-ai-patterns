"""Versioned ingestion and tenant-filtered hybrid retrieval with source-line citations."""

from __future__ import annotations

from collections import defaultdict
import json
import math
import re

from pydantic import BaseModel, ConfigDict, Field

from patterns.database import digest, encoded
from patterns.providers import get_embeddings, get_model


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=500)


class KnowledgeBase:
    def __init__(self, db, embeddings=None, model=None):
        self.db, self.embeddings, self.model = db, embeddings or get_embeddings(), model or get_model()

    def _vector(self, text):
        vector = self.embeddings.embed(text)
        if not vector or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector):
            raise ValueError("Embedding contains invalid values")
        return vector

    @staticmethod
    def chunks(text, max_chars=700):
        lines = text.splitlines()
        start = 0
        current = []
        size = 0
        for index, line in enumerate(lines):
            if len(line) > max_chars:
                raise ValueError("Line too long for citation-preserving chunker")
            if current and size + len(line) + 1 > max_chars:
                yield start + 1, index, "\n".join(current)
                overlap = current[-1:] if len(current[-1]) < max_chars // 3 else []
                start = index - len(overlap)
                current = overlap
                size = sum(len(x) + 1 for x in overlap)
            if not current:
                start = index
            current.append(line)
            size += len(line) + 1
        if current and "\n".join(current).strip():
            yield start + 1, len(lines), "\n".join(current)

    def ingest(self, tenant, document_id, content, kind="file"):
        if kind not in {"file", "operating_log", "memory_bank"}:
            raise ValueError("Unknown source kind")
        generation = digest([content, kind, type(self.embeddings).__name__])[:20]
        with self.db.transaction() as db:
            existing = db.execute(
                "SELECT generation FROM documents WHERE tenant=? AND id=?", (tenant, document_id)
            ).fetchone()
        if existing and existing["generation"] == generation:
            return {"id": document_id, "generation": generation, "changed": False}
        rows = []
        for start, end, text in self.chunks(content):
            identity = "K-" + digest([tenant, document_id, generation, start, end])[:24]
            rows.append(
                (
                    identity,
                    tenant,
                    document_id,
                    generation,
                    kind,
                    text,
                    start,
                    end,
                    encoded(self._vector(text)),
                )
            )
        with self.db.transaction() as db:
            db.execute(
                "DELETE FROM chunks_fts WHERE id IN (SELECT id FROM chunks WHERE tenant=? AND document_id=?)",
                (tenant, document_id),
            )
            db.execute("DELETE FROM chunks WHERE tenant=? AND document_id=?", (tenant, document_id))
            db.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?,?) ON CONFLICT(tenant,id) DO UPDATE SET generation=excluded.generation,content=excluded.content,kind=excluded.kind,metadata=excluded.metadata",
                (tenant, document_id, generation, content, kind, "{}"),
            )
            db.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?)", rows)
            db.executemany(
                "INSERT INTO chunks_fts VALUES (?,?,?)", [(row[0], tenant, row[5]) for row in rows]
            )
        return {"id": document_id, "generation": generation, "chunks": len(rows), "changed": True}

    def document(self, tenant, document_id):
        with self.db.transaction() as db:
            row = db.execute(
                "SELECT * FROM documents WHERE tenant=? AND id=?", (tenant, document_id)
            ).fetchone()
        if row is None:
            raise KeyError(document_id)
        return {**dict(row), "metadata": json.loads(row["metadata"])}

    def search(self, tenant, query, k=3, mode="hybrid"):
        if not 1 <= k <= 20 or mode not in {"dense", "lexical", "hybrid"}:
            raise ValueError("Invalid retrieval options")
        vector = self._vector(query)
        tokens = re.findall(r"[a-z0-9]+", query.lower())[:20]
        expression = " OR ".join('"' + token + '"' for token in tokens)
        with self.db.transaction() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM chunks WHERE tenant=?", (tenant,))]
            lexical = []
            if expression:
                lexical = [
                    row["id"]
                    for row in db.execute(
                        "SELECT id FROM chunks_fts WHERE chunks_fts MATCH ? AND tenant=? ORDER BY bm25(chunks_fts) LIMIT 30",
                        (expression, tenant),
                    )
                ]
        by_id = {row["id"]: row for row in rows}
        dense = []
        similarities = {}
        for row in rows:
            stored = json.loads(row["vector"])
            if len(stored) != len(vector):
                raise ValueError("Embedding model changed: rebuild the index")
            score = sum(a * b for a, b in zip(vector, stored))
            similarities[row["id"]] = score
            if score >= 0.12:
                dense.append((row["id"], score))
        dense = [identity for identity, _ in sorted(dense, key=lambda pair: (-pair[1], pair[0]))[:30]]
        rankings = [dense] if mode == "dense" else [lexical] if mode == "lexical" else [dense, lexical]
        scores = defaultdict(float)
        for ranking in rankings:
            for rank, identity in enumerate(ranking, 1):
                scores[identity] += 1 / (60 + rank)
        hits = []
        for identity, score in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))[:k]:
            if identity not in by_id:
                continue
            row = by_id[identity]
            hits.append(
                {
                    key: row[key]
                    for key in [
                        "id",
                        "tenant",
                        "document_id",
                        "generation",
                        "kind",
                        "text",
                        "line_start",
                        "line_end",
                    ]
                }
            )
            hits[-1].update(score=score, dense_similarity=similarities[identity])
        return hits

    def draft_metadata(self, tenant, document_id):
        document = self.document(tenant, document_id)
        draft = Metadata.model_validate(
            self.model.complete("metadata", {"document_id": document_id, "content": document["content"]})
        ).model_dump()
        identity = "D-" + digest([tenant, document_id, document["generation"], draft])[:24]
        with self.db.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO metadata_drafts VALUES (?,?,?,?,?)",
                (identity, tenant, document_id, document["generation"], encoded(draft)),
            )
        return {"id": identity, **draft}

    def approve_metadata(self, tenant, identity):
        with self.db.transaction() as db:
            row = db.execute(
                "SELECT * FROM metadata_drafts WHERE tenant=? AND id=?", (tenant, identity)
            ).fetchone()
            if row is None:
                raise KeyError(identity)
            changed = db.execute(
                "UPDATE documents SET metadata=? WHERE tenant=? AND id=? AND generation=?",
                (row["body"], tenant, row["document_id"], row["generation"]),
            ).rowcount
            if not changed:
                raise ValueError("Document changed after metadata was drafted")
