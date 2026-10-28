"""Durable, versioned decisions bound to exact tool arguments and a bounded edit policy."""

from __future__ import annotations

import json
from uuid import uuid4

from patterns.database import digest, encoded


class ApprovalStore:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _decode(row):
        return {**dict(row), "arguments": json.loads(row["arguments"])}

    def propose(self, tenant, case_id, tool, arguments, ceiling, now, ttl=3600):
        identity = "A-" + digest([tenant, case_id, tool, arguments])[:24]
        self._validate(arguments, ceiling)
        with self.db.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    tenant,
                    case_id,
                    tool,
                    encoded(arguments),
                    ceiling,
                    "pending",
                    0,
                    now + ttl,
                    None,
                    None,
                ),
            )
        return self.get(tenant, identity)

    def get(self, tenant, identity):
        with self.db.transaction() as db:
            row = db.execute("SELECT * FROM approvals WHERE tenant=? AND id=?", (tenant, identity)).fetchone()
        if row is None:
            raise KeyError("Approval not found in this workspace")
        return self._decode(row)

    @staticmethod
    def _validate(args, ceiling):
        amount = args.get("amount_cents")
        if type(amount) is not int or not 0 < amount <= ceiling:
            raise ValueError("Edited amount must be a positive integer within the verified ceiling")
        if (
            set(args) != {"invoice_id", "amount_cents", "reason"}
            or not isinstance(args["reason"], str)
            or not args["reason"].strip()
        ):
            raise ValueError("Invalid credit arguments")

    def decide(
        self, tenant, identity, action, actor, expected_version, now, edited_args=None, resume_payload=None
    ):
        if action not in {"approve", "edit", "reject"} or not actor:
            raise ValueError("Explicit decision and reviewer identity required")
        with self.db.transaction() as db:
            row = db.execute("SELECT * FROM approvals WHERE tenant=? AND id=?", (tenant, identity)).fetchone()
            if row is None:
                raise KeyError("Approval not found")
            current = self._decode(row)
            if current["status"] != "pending" or current["version"] != expected_version:
                raise ValueError("Approval has already changed; reload before deciding")
            if current["expires"] <= now:
                raise PermissionError("Approval expired")
            args = current["arguments"]
            if action == "edit":
                if edited_args is None:
                    raise ValueError("Edit arguments required")
                if (
                    edited_args.get("invoice_id") != args["invoice_id"]
                    or edited_args.get("reason") != args["reason"]
                ):
                    raise ValueError("Only the amount is editable; changing scope requires a new proposal")
                self._validate(edited_args, current["ceiling"])
                args = edited_args
            status = "rejected" if action == "reject" else "approved"
            receipt = encoded(
                {
                    "decision_id": str(uuid4()),
                    "action": action,
                    "actor": actor,
                    "at": now,
                    "argument_hash": digest(args),
                }
            )
            db.execute(
                "UPDATE approvals SET arguments=?,status=?,version=version+1,actor=?,receipt=? WHERE id=?",
                (encoded(args), status, actor, receipt, identity),
            )
            if resume_payload is not None:
                db.execute(
                    "INSERT INTO signals VALUES (?,?,?,?)",
                    (
                        tenant,
                        "resume-" + current["case_id"] + "-" + str(current["version"] + 1),
                        encoded(resume_payload),
                        now,
                    ),
                )
        return self.get(tenant, identity)

    def authorize(self, tenant, identity, tool, args, now):
        current = self.get(tenant, identity)
        if (
            current["status"] != "approved"
            or current["expires"] <= now
            or current["tool"] != tool
            or current["arguments"] != args
        ):
            raise PermissionError("No current approval for these exact arguments")
        return current
