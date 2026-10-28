"""SQLite persistence shared by the examples; the mock ERP owns a separate database."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (tenant TEXT, id TEXT, kind TEXT, body TEXT, PRIMARY KEY(tenant,id));
CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT, case_id TEXT, kind TEXT, body TEXT, at REAL);
CREATE INDEX IF NOT EXISTS event_scope ON events(tenant,case_id,seq);
CREATE TABLE IF NOT EXISTS cases (tenant TEXT, id TEXT, request_id TEXT, request_hash TEXT, invoice_id TEXT, state TEXT, PRIMARY KEY(tenant,id), UNIQUE(tenant,request_id));
CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, tenant TEXT, case_id TEXT, tool TEXT, arguments TEXT, ceiling INTEGER, status TEXT, version INTEGER, expires REAL, actor TEXT, receipt TEXT);
CREATE TABLE IF NOT EXISTS signals (tenant TEXT, id TEXT, payload TEXT, due REAL, PRIMARY KEY(tenant,id));
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, tenant TEXT, signal_id TEXT, payload TEXT, state TEXT, owner TEXT, attempt INTEGER, lease_until REAL, ready REAL, result TEXT, error TEXT, UNIQUE(tenant,signal_id));
CREATE TABLE IF NOT EXISTS workdocs (tenant TEXT, id TEXT, revision INTEGER, body TEXT, PRIMARY KEY(tenant,id));
CREATE TABLE IF NOT EXISTS documents (tenant TEXT, id TEXT, generation TEXT, content TEXT, kind TEXT, metadata TEXT, PRIMARY KEY(tenant,id));
CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, tenant TEXT, document_id TEXT, generation TEXT, kind TEXT, text TEXT, line_start INTEGER, line_end INTEGER, vector TEXT);
CREATE INDEX IF NOT EXISTS chunk_scope ON chunks(tenant,document_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(id UNINDEXED, tenant UNINDEXED, text);
CREATE TABLE IF NOT EXISTS metadata_drafts (id TEXT PRIMARY KEY, tenant TEXT, document_id TEXT, generation TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS turns (tenant TEXT, thread TEXT, id TEXT, request TEXT, answer TEXT, seq INTEGER, PRIMARY KEY(tenant,thread,id));
CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, tenant TEXT, fact TEXT, source_turn TEXT, status TEXT);
"""


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=20) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def receipt(self, tenant, kind, body):
        identity = "E-" + digest([tenant, kind, body])[:24]
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO receipts VALUES (?,?,?,?)", (tenant, identity, kind, encoded(body))
            )
        return identity

    def evidence(self, tenant, identity):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM receipts WHERE tenant=? AND id=?", (tenant, identity)).fetchone()
        if row is None:
            raise KeyError("Evidence not found in this workspace")
        return {**dict(row), "body": json.loads(row["body"])}

    def event(self, tenant, case_id, kind, body=None):
        with self.transaction() as db:
            db.execute(
                "INSERT INTO events (tenant,case_id,kind,body,at) VALUES (?,?,?,?,?)",
                (tenant, case_id, kind, encoded(body or {}), time.time()),
            )

    def events(self, tenant, case_id):
        with self.transaction() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE tenant=? AND case_id=? ORDER BY seq", (tenant, case_id)
            ).fetchall()
        return [{**dict(row), "body": json.loads(row["body"])} for row in rows]
