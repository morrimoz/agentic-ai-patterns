"""Application boundary for submission, leased graph execution and durable decisions."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from threading import Event, Thread

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from patterns.approval import ApprovalStore
from patterns.context import ContextStore
from patterns.database import Database, digest, encoded
from patterns.jobs import JobQueue, WorkDocument
from patterns.mcp_bridge import ERPClient, seed_erp
from patterns.providers import get_model
from patterns.rag import KnowledgeBase
from patterns.rag.fixtures import seed_knowledge


class Service:
    def __init__(self, path, model=None):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.path / "application.db")
        self.erp = ERPClient(self.path / "accounting.db")
        self.model = model or get_model()
        self.knowledge = KnowledgeBase(self.db, model=self.model)
        self.context = ContextStore(self.db)
        self.approvals = ApprovalStore(self.db)
        self.queue = JobQueue(self.db)
        self.docs = WorkDocument(self.db)
        self.clock = time.time
        self.fault = None
        self.active_claim = None
        self.execution_now = None

    def seed(self):
        seed_erp(self.erp.path)
        seed_knowledge(self.knowledge)

    def submit(self, tenant, invoice_id, request, request_id):
        if not tenant or not request.strip() or len(request) > 4000 or not request_id:
            raise ValueError("Bounded request and request identity required")
        self.erp.invoice(tenant, invoice_id)
        payload = {"invoice_id": invoice_id, "request": request}
        identity = "C-" + digest([tenant, request_id])[:20]
        state = {
            "tenant": tenant,
            "case_id": identity,
            "invoice_id": invoice_id,
            "request": request,
            "status": "queued",
        }
        with self.db.transaction() as db:
            previous = db.execute(
                "SELECT * FROM cases WHERE tenant=? AND request_id=?", (tenant, request_id)
            ).fetchone()
            if previous:
                if previous["request_hash"] != digest(payload):
                    raise ValueError("Request identity reused with different content")
                return json.loads(previous["state"])
            db.execute(
                "INSERT INTO cases VALUES (?,?,?,?,?,?)",
                (tenant, identity, request_id, digest(payload), invoice_id, encoded(state)),
            )
            # Outbox insertion and case creation share a transaction: a crash cannot orphan accepted work.
            db.execute(
                "INSERT INTO signals VALUES (?,?,?,?)",
                (
                    tenant,
                    "investigate-" + identity,
                    encoded({"case_id": identity, "phase": "investigate"}),
                    self.clock(),
                ),
            )
        self.docs.create(
            tenant, identity, request, ["read_ledger", "review_policy", "execute_action", "verify_result"]
        )
        self.db.event(tenant, identity, "case.submitted", {"invoice_id": invoice_id})
        return state

    def update_case(self, tenant, case_id, state):
        body = {key: value for key, value in state.items() if not key.startswith("__")}
        with self.db.transaction() as db:
            if not db.execute(
                "UPDATE cases SET state=? WHERE tenant=? AND id=?", (encoded(body), tenant, case_id)
            ).rowcount:
                raise KeyError(case_id)

    def case(self, tenant, case_id):
        with self.db.transaction() as db:
            row = db.execute("SELECT state FROM cases WHERE tenant=? AND id=?", (tenant, case_id)).fetchone()
        if row is None:
            raise KeyError("Case not found in this workspace")
        state = json.loads(row["state"])
        if state.get("approval"):
            state["approval"] = self.approvals.get(tenant, state["approval"]["id"])
        return state

    def events(self, tenant, case_id):
        self.case(tenant, case_id)
        return self.db.events(tenant, case_id)

    @contextmanager
    def graph(self):
        from patterns.workflow import build_graph

        connection = sqlite3.connect(self.path / "checkpoints.db", check_same_thread=False, timeout=20)
        try:
            saver = SqliteSaver(connection)
            yield build_graph(self, saver)
        finally:
            connection.close()

    @staticmethod
    def config(tenant, case_id):
        return {"configurable": {"thread_id": tenant + ":" + case_id}, "recursion_limit": 30}

    def resolve(self, tenant, case_id, action, actor, expected_version, amount_cents=None):
        case = self.case(tenant, case_id)
        if case["status"] != "awaiting_approval":
            raise ValueError("Case is not waiting for a decision")
        approval = case["approval"]
        edited = None
        if action == "edit":
            edited = {**approval["arguments"], "amount_cents": amount_cents}
        record = self.approvals.decide(
            tenant,
            approval["id"],
            action,
            actor,
            expected_version,
            self.clock(),
            edited_args=edited,
            resume_payload={"case_id": case_id, "phase": "resume"},
        )
        self.db.event(
            tenant,
            case_id,
            "approval.decided",
            {"approval_id": record["id"], "actor": actor, "action": action, "version": record["version"]},
        )
        return record

    def assert_ownership(self):
        if self.active_claim is None:
            return
        current = self.execution_now()
        with self.db.transaction() as db:
            if not self.queue.owns(db, self.active_claim, current):
                raise PermissionError("Worker lost its lease")

    def work(self, owner, now=None, fault=None):
        now = self.clock() if now is None else now
        self.queue.poll(now)
        claim = self.queue.claim(owner, now, lease=120)
        if claim is None:
            return None
        tenant = claim["tenant"]
        case_id = claim["payload"]["case_id"]
        self.fault = fault
        started = time.monotonic()
        self.active_claim = claim
        self.execution_now = lambda: now + time.monotonic() - started
        stop = Event()

        def renew():
            while not stop.wait(10):
                if not self.queue.heartbeat(claim, self.execution_now(), lease=120):
                    return

        heartbeat = Thread(target=renew, daemon=True)
        heartbeat.start()
        self.db.event(
            tenant,
            case_id,
            "job.claimed",
            {"job_id": claim["id"], "attempt": claim["attempt"], "owner": owner},
        )
        try:
            case = self.case(tenant, case_id)
            self.docs.create(
                tenant,
                case_id,
                case["request"],
                ["read_ledger", "review_policy", "execute_action", "verify_result"],
            )
            # A bounded invocation runs within the lease; heartbeats guard the boundaries.
            if not self.queue.heartbeat(claim, now, lease=120):
                raise PermissionError("Job ownership lost")
            with self.graph() as graph:
                config = self.config(tenant, case_id)
                snapshot = graph.get_state(config)
                if (
                    claim["payload"]["phase"] == "resume"
                    and snapshot.tasks
                    and any(task.interrupts for task in snapshot.tasks)
                ):
                    input_value = Command(resume={"approval_id": case["approval"]["id"]})
                elif snapshot.values:
                    input_value = None
                else:
                    input_value = case
                result = graph.invoke(input_value, config)
            if "__interrupt__" in result:
                final = self.case(tenant, case_id)
            else:
                self.assert_ownership()
                self.update_case(tenant, case_id, result)
                final = self.case(tenant, case_id)
            elapsed = time.monotonic() - started
            if not self.queue.complete(claim, {"status": final["status"]}, now + elapsed):
                raise PermissionError("Job lease expired before completion")
            self.db.event(
                tenant, case_id, "job.completed", {"status": final["status"], "seconds": round(elapsed, 3)}
            )
            return final
        except Exception as exc:
            elapsed = time.monotonic() - started
            self.queue.fail(claim, type(exc).__name__ + ": " + str(exc), now + elapsed)
            self.db.event(
                tenant, case_id, "job.failed", {"error_type": type(exc).__name__, "message": str(exc)[:500]}
            )
            return {"case_id": case_id, "status": "retry_pending", "error": str(exc)}
        finally:
            stop.set()
            heartbeat.join(timeout=2)
            self.fault = None
            self.active_claim = None
            self.execution_now = None
