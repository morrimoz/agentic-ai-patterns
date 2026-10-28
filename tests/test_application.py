"""Acceptance across the real graph, MCP process, database and approval boundary."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from patterns.application.service import Service
from patterns.application.api import create_app


def prepared(tmp_path, **kwargs):
    service = Service(tmp_path, **kwargs)
    service.seed()
    return service


def test_real_input_drives_different_investigation_results(tmp_path):
    app = prepared(tmp_path)
    first = app.submit("north", "INV-1042", "Investigate duplicate payment", request_id="first")
    app.work("worker-a")
    pending = app.case("north", first["case_id"])
    assert pending["status"] == "awaiting_approval"
    assert pending["proposal"]["arguments"]["amount_cents"] == 12000
    assert app.erp.credits("north", "INV-1042") == []
    second = app.submit("north", "INV-1043", "Check whether this invoice needs a credit", request_id="second")
    app.work("worker-b")
    no_credit = app.case("north", second["case_id"])
    assert no_credit["status"] == "completed"
    assert no_credit["proposal"]["action"] == "no_action"
    assert no_credit["report"]["verified"]


def test_approval_survives_process_restart_and_executes_edited_amount_once(tmp_path):
    app = prepared(tmp_path)
    case = app.submit("north", "INV-1042", "Investigate duplicate payment", request_id="durable")
    app.work("first-process")
    pending = app.case("north", case["case_id"])
    decision = pending["approval"]
    script = """
from patterns.application.service import Service
import sys,json
s=Service(sys.argv[1])
c=s.case('north',sys.argv[2])
s.resolve('north',c['case_id'],action='edit',actor='reviewer',expected_version=c['approval']['version'],amount_cents=10000)
s.work('fresh-python-process')
print(json.dumps(s.case('north',c['case_id'])))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), case["case_id"]],
        text=True,
        capture_output=True,
        timeout=30,
        env=dict(os.environ, AI_PROVIDER="fake"),
    )
    assert result.returncode == 0, result.stderr
    final = json.loads(result.stdout)
    assert final["status"] == "completed"
    assert final["report"]["amount_cents"] == 10000
    assert final["report"]["verified"]
    assert len(app.erp.credits("north", "INV-1042")) == 1
    assert app.case("north", case["case_id"])["approval"]["id"] == decision["id"]
    assert app.work("idle") is None


def test_rejection_never_changes_external_ledger(tmp_path):
    app = prepared(tmp_path)
    case = app.submit("north", "INV-1042", "Investigate", request_id="reject")
    app.work("worker")
    pending = app.case("north", case["case_id"])
    app.resolve(
        "north",
        case["case_id"],
        action="reject",
        actor="reviewer",
        expected_version=pending["approval"]["version"],
    )
    app.work("worker")
    assert app.case("north", case["case_id"])["status"] == "rejected"
    assert app.erp.credits("north", "INV-1042") == []


def test_crash_after_external_effect_recovers_with_same_idempotency_key(tmp_path):
    app = prepared(tmp_path)
    case = app.submit("north", "INV-1042", "Investigate", request_id="crash")
    app.work("worker-a")
    pending = app.case("north", case["case_id"])
    app.resolve(
        "north",
        case["case_id"],
        action="approve",
        actor="reviewer",
        expected_version=pending["approval"]["version"],
    )
    app.work("worker-a", fault="after_effect")
    assert len(app.erp.credits("north", "INV-1042")) == 1
    restarted = Service(tmp_path)
    restarted.work("worker-b", now=app.clock() + 10)
    final = restarted.case("north", case["case_id"])
    assert final["status"] == "completed"
    assert final["report"]["verified"]
    assert len(app.erp.credits("north", "INV-1042")) == 1
    assert any(e["kind"] == "job.failed" for e in app.events("north", case["case_id"]))


def test_stale_approval_is_refused_after_external_ledger_changes(tmp_path):
    app = prepared(tmp_path)
    case = app.submit("north", "INV-1042", "Investigate", request_id="stale")
    app.work("worker")
    pending = app.case("north", case["case_id"])
    app.resolve(
        "north",
        case["case_id"],
        action="approve",
        actor="reviewer",
        expected_version=pending["approval"]["version"],
    )
    app.erp.credit(
        "north",
        {"invoice_id": "INV-1042", "amount_cents": 12000, "reason": "Other reviewed operation"},
        "other-operation",
    )
    app.work("worker")
    assert app.case("north", case["case_id"])["status"] == "blocked"
    assert len(app.erp.credits("north", "INV-1042")) == 1


def test_request_identity_and_tenant_boundaries(tmp_path):
    app = prepared(tmp_path)
    one = app.submit("north", "INV-1042", "Investigate", request_id="same")
    assert app.submit("north", "INV-1042", "Investigate", request_id="same")["case_id"] == one["case_id"]
    with pytest.raises(ValueError):
        app.submit("north", "INV-1043", "Changed", request_id="same")
    with pytest.raises(KeyError):
        app.case("south", one["case_id"])
    with pytest.raises(KeyError):
        app.submit("south", "INV-1042", "Investigate", request_id="wrong-scope")


def test_two_actual_worker_connections_execute_only_one_investigation(tmp_path):
    app = prepared(tmp_path)
    case = app.submit("north", "INV-1042", "Investigate", request_id="race")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda owner: Service(tmp_path).work(owner), ["a", "b"]))
    assert sum(result is not None for result in results) == 1
    assert app.case("north", case["case_id"])["status"] == "awaiting_approval"
    assert len([e for e in app.events("north", case["case_id"]) if e["kind"] == "workflow.planned"]) == 1


def test_model_evaluation_corrects_once_then_blocks_unverifiable_output(tmp_path):
    from patterns.providers import FixtureModel

    app = prepared(tmp_path, model=FixtureModel(fault="bad_first_draft"))
    case = app.submit("north", "INV-1042", "Investigate", request_id="correction")
    app.work("worker")
    pending = app.case("north", case["case_id"])
    assert pending["status"] == "awaiting_approval"
    assert pending["draft_attempts"] == 2
    assert any(e["kind"] == "evaluation.context_upgraded" for e in app.events("north", case["case_id"]))
    broken = Service(tmp_path / "broken", model=FixtureModel(fault="always_fabricate"))
    broken.seed()
    other = broken.submit("north", "INV-1042", "Investigate", request_id="bad")
    broken.work("worker")
    assert broken.case("north", other["case_id"])["status"] == "blocked"
    assert broken.erp.credits("north", "INV-1042") == []


def test_http_case_lifecycle_and_trace(tmp_path):
    service = prepared(tmp_path)
    client = TestClient(create_app(service))
    assert (
        client.post(
            "/cases", json={"invoice_id": "INV-1042", "request": "Investigate", "request_id": "api"}
        ).status_code
        == 401
    )
    headers = {"X-Workspace": "north", "X-Actor": "reviewer"}
    case = client.post(
        "/cases",
        headers=headers,
        json={"invoice_id": "INV-1042", "request": "Investigate", "request_id": "api"},
    ).json()
    assert client.post("/worker/tick").status_code == 200
    pending = client.get("/cases/" + case["case_id"], headers=headers).json()
    wrong = client.get("/cases/" + case["case_id"], headers={**headers, "X-Workspace": "south"})
    assert wrong.status_code == 404
    assert (
        client.post(
            "/cases/" + case["case_id"] + "/decision",
            headers=headers,
            json={
                "action": "edit",
                "amount_cents": 999999,
                "expected_version": pending["approval"]["version"],
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/cases/" + case["case_id"] + "/decision",
            headers=headers,
            json={"action": "approve", "expected_version": pending["approval"]["version"]},
        ).status_code
        == 200
    )
    client.post("/worker/tick")
    final = client.get("/cases/" + case["case_id"], headers=headers).json()
    assert final["status"] == "completed" and final["report"]["verified"]
    events = client.get("/cases/" + case["case_id"] + "/events", headers=headers).json()
    assert {"model.called", "tool.executed", "approval.decided", "effect.verified"} <= {
        e["kind"] for e in events
    }


def test_changed_policy_invalidates_approved_proposal(tmp_path):
    app = prepared(tmp_path)
    case = app.submit("north", "INV-1042", "Investigate", request_id="policy-drift")
    app.work("worker")
    pending = app.case("north", case["case_id"])
    app.resolve(
        "north",
        case["case_id"],
        action="approve",
        actor="reviewer",
        expected_version=pending["approval"]["version"],
    )
    app.knowledge.ingest(
        "north", "credit-policy", "# Credit policy\nAll credits now require a separate legal review."
    )
    app.work("worker")
    assert app.case("north", case["case_id"])["status"] == "blocked"
    assert app.erp.credits("north", "INV-1042") == []


def test_failure_after_approval_commit_recovery_enqueues_resume(tmp_path):
    app = prepared(tmp_path)
    case = app.submit("north", "INV-1042", "Investigate", request_id="decision-outbox")
    app.work("worker")
    pending = app.case("north", case["case_id"])
    # The decision store is the authoritative transaction boundary. Simulate loss of
    # the service response immediately after that transaction, before projection updates.
    app.approvals.decide(
        "north",
        pending["approval"]["id"],
        "approve",
        "reviewer",
        expected_version=0,
        now=app.clock(),
        resume_payload={"case_id": case["case_id"], "phase": "resume"},
    )
    Service(tmp_path).work("fresh-worker")
    assert app.case("north", case["case_id"])["status"] == "completed"
    assert len(app.erp.credits("north", "INV-1042")) == 1


def test_reconciliation_after_effect_does_not_need_a_fresh_write_approval(tmp_path):
    app = prepared(tmp_path)
    case = app.submit("north", "INV-1042", "Investigate", request_id="expired-after-effect")
    app.work("first")
    pending = app.case("north", case["case_id"])
    app.resolve("north", case["case_id"], action="approve", actor="operator", expected_version=0)
    app.work("first", fault="after_effect")
    with app.db.transaction() as db:
        db.execute("UPDATE approvals SET expires=0 WHERE id=?", (pending["approval"]["id"],))
    Service(tmp_path).work("reconciler", now=app.clock() + 10)
    final = app.case("north", case["case_id"])
    assert final["status"] == "completed" and final["report"]["verified"]
    assert len(app.erp.credits("north", "INV-1042")) == 1
