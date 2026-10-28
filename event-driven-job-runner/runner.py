"""Transactional polling, leased ownership and fencing for at-least-once work."""

from __future__ import annotations

import json
import time

from patterns.database import digest, encoded


class JobQueue:
    def __init__(self, db, max_attempts=3):
        self.db, self.max_attempts = db, max_attempts

    def signal(self, tenant, identity, payload, now):
        body = encoded(payload)
        with self.db.transaction() as db:
            row = db.execute(
                "SELECT payload FROM signals WHERE tenant=? AND id=?", (tenant, identity)
            ).fetchone()
            if row:
                if row["payload"] != body:
                    raise ValueError("Signal identity reused with changed payload")
                return False
            db.execute("INSERT INTO signals VALUES (?,?,?,?)", (tenant, identity, body, now))
        return True

    def poll(self, now):
        inserted = 0
        with self.db.transaction() as db:
            for row in db.execute(
                "SELECT * FROM signals AS signal WHERE due<=? AND NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.tenant=signal.tenant AND jobs.signal_id=signal.id) ORDER BY due,id LIMIT 100",
                (now,),
            ).fetchall():
                identity = "J-" + digest([row["tenant"], row["id"]])[:24]
                inserted += db.execute(
                    "INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        identity,
                        row["tenant"],
                        row["id"],
                        row["payload"],
                        "pending",
                        None,
                        0,
                        0,
                        row["due"],
                        None,
                        None,
                    ),
                ).rowcount
        return inserted

    def claim(self, owner, now, lease=30):
        if not owner or lease <= 0:
            raise ValueError("Owner and positive lease required")
        with self.db.transaction() as db:
            db.execute(
                "UPDATE jobs SET state='failed' WHERE state='running' AND lease_until<=? AND attempt>=?",
                (now, self.max_attempts),
            )
            row = db.execute(
                """SELECT * FROM jobs AS candidate WHERE attempt<? AND
                ((state='pending' AND ready<=?) OR (state='running' AND lease_until<=?))
                AND NOT EXISTS (SELECT 1 FROM jobs AS other WHERE other.id!=candidate.id AND other.tenant=candidate.tenant
                    AND json_extract(other.payload,'$.case_id')=json_extract(candidate.payload,'$.case_id')
                    AND other.state='running' AND other.lease_until>?)
                ORDER BY ready,id LIMIT 1""",
                (self.max_attempts, now, now, now),
            ).fetchone()
            if row is None:
                return None
            attempt = row["attempt"] + 1
            db.execute(
                "UPDATE jobs SET state='running',owner=?,attempt=?,lease_until=? WHERE id=?",
                (owner, attempt, now + lease, row["id"]),
            )
        return {
            **dict(row),
            "payload": json.loads(row["payload"]),
            "owner": owner,
            "attempt": attempt,
            "lease_until": now + lease,
            "state": "running",
        }

    @staticmethod
    def owns(db, claim, now):
        return (
            db.execute(
                "SELECT 1 FROM jobs WHERE id=? AND owner=? AND attempt=? AND state='running' AND lease_until>?",
                (claim["id"], claim["owner"], claim["attempt"], now),
            ).fetchone()
            is not None
        )

    def heartbeat(self, claim, now, lease=30):
        with self.db.transaction() as db:
            if not self.owns(db, claim, now):
                return False
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?", (now + lease, claim["id"]))
        return True

    def complete(self, claim, result, now):
        with self.db.transaction() as db:
            if not self.owns(db, claim, now):
                return False
            db.execute(
                "UPDATE jobs SET state='done',result=?,owner=NULL WHERE id=?", (encoded(result), claim["id"])
            )
        return True

    def fail(self, claim, error, now):
        with self.db.transaction() as db:
            if not self.owns(db, claim, now):
                return False
            state = "failed" if claim["attempt"] >= self.max_attempts else "pending"
            db.execute(
                "UPDATE jobs SET state=?,ready=?,owner=NULL,error=? WHERE id=?",
                (state, now + 2 ** claim["attempt"], str(error)[:500], claim["id"]),
            )
        return True

    def get(self, identity):
        with self.db.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        return {**dict(row), "payload": json.loads(row["payload"])}

    def scheduled_poll(self, interval=1, ticks=3):
        if interval <= 0 or ticks <= 0:
            raise ValueError("Positive scheduling parameters required")
        results = []
        for tick in range(ticks):
            results.append(self.poll(time.time()))
            if tick + 1 < ticks:
                time.sleep(interval)
        return results
