"""Shared progress uses compare-and-swap notes and evidence-backed item completion."""

import json

from patterns.database import encoded


class WorkDocument:
    def __init__(self, db):
        self.db = db

    def create(self, tenant, identity, objective, items):
        body = {
            "objective": objective,
            "items": {item: {"state": "todo", "evidence": None} for item in items},
            "notes": [],
        }
        with self.db.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO workdocs VALUES (?,?,?,?)", (tenant, identity, 0, encoded(body))
            )
        return self.get(tenant, identity)

    def get(self, tenant, identity):
        with self.db.transaction() as db:
            row = db.execute("SELECT * FROM workdocs WHERE tenant=? AND id=?", (tenant, identity)).fetchone()
        if row is None:
            raise KeyError("Work document not found")
        return {**json.loads(row["body"]), "revision": row["revision"]}

    def note(self, tenant, identity, actor, text, expected_revision):
        if not actor or len(text) > 1000:
            raise ValueError("Bounded attributed note required")
        with self.db.transaction() as db:
            row = db.execute("SELECT * FROM workdocs WHERE tenant=? AND id=?", (tenant, identity)).fetchone()
            if row is None:
                raise KeyError(identity)
            if row["revision"] != expected_revision:
                raise ValueError("Work document revision conflict")
            body = json.loads(row["body"])
            body["notes"] = (body["notes"] + [{"actor": actor, "text": text}])[-20:]
            db.execute(
                "UPDATE workdocs SET body=?,revision=revision+1 WHERE tenant=? AND id=?",
                (encoded(body), tenant, identity),
            )
        return self.get(tenant, identity)

    def complete_item(self, tenant, identity, item, evidence_id):
        self.db.evidence(tenant, evidence_id)
        with self.db.transaction() as db:
            row = db.execute("SELECT * FROM workdocs WHERE tenant=? AND id=?", (tenant, identity)).fetchone()
            if row is None:
                raise KeyError(identity)
            body = json.loads(row["body"])
            if item not in body["items"]:
                raise KeyError(item)
            body["items"][item] = {"state": "done", "evidence": evidence_id}
            db.execute(
                "UPDATE workdocs SET body=?,revision=revision+1 WHERE tenant=? AND id=?",
                (encoded(body), tenant, identity),
            )
        return self.get(tenant, identity)

    def skip_item(self, tenant, identity, item, evidence_id, reason):
        self.db.evidence(tenant, evidence_id)
        with self.db.transaction() as db:
            row = db.execute("SELECT * FROM workdocs WHERE tenant=? AND id=?", (tenant, identity)).fetchone()
            if row is None:
                raise KeyError(identity)
            body = json.loads(row["body"])
            if item not in body["items"]:
                raise KeyError(item)
            body["items"][item] = {"state": "skipped", "evidence": evidence_id, "reason": reason}
            db.execute(
                "UPDATE workdocs SET body=?,revision=revision+1 WHERE tenant=? AND id=?",
                (encoded(body), tenant, identity),
            )
        return self.get(tenant, identity)
