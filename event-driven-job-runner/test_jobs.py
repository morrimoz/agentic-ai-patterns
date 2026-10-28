from concurrent.futures import ThreadPoolExecutor
import pytest
from patterns.database import Database
from patterns.jobs import JobQueue, WorkDocument


def test_transactional_claim_expiry_fencing_backoff_and_terminal_state(tmp_path):
    db = Database(tmp_path / "app.db")
    q = JobQueue(db, max_attempts=2)
    assert q.signal("north", "event-1", {"case_id": "case"}, now=0)
    assert not q.signal("north", "event-1", {"case_id": "case"}, now=0)
    with pytest.raises(ValueError):
        q.signal("north", "event-1", {"case_id": "different"}, now=0)
    assert q.poll(now=0) == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda i: JobQueue(Database(db.path)).claim(str(i), now=0, lease=5), range(4)))
    old = next(c for c in claims if c)
    assert sum(c is not None for c in claims) == 1
    new = q.claim("fresh", now=6, lease=5)
    assert new["attempt"] == 2
    assert not q.complete(old, {"ok": True}, now=7)
    assert q.fail(new, "temporary", now=7)
    assert q.claim("later", now=100) is None
    assert q.get(new["id"])["state"] == "failed"


def test_shared_work_doc_cas_and_completion_needs_real_evidence(tmp_path):
    db = Database(tmp_path / "app.db")
    docs = WorkDocument(db)
    doc = docs.create("north", "case", "Reconcile invoice", ["read_ledger", "review_policy"])
    doc = docs.note(
        "north", "case", actor="agent-a", text="Ledger read in progress", expected_revision=doc["revision"]
    )
    with pytest.raises(ValueError):
        docs.note("north", "case", actor="agent-b", text="stale", expected_revision=0)
    with pytest.raises(KeyError):
        docs.complete_item("north", "case", "read_ledger", "invented")
    evidence = db.receipt("north", "invoice.read", {"invoice_id": "INV-7"})
    docs.complete_item("north", "case", "read_ledger", evidence)
    assert docs.get("north", "case")["items"]["read_ledger"]["state"] == "done"
    with pytest.raises(KeyError):
        docs.get("south", "case")


def test_running_case_serializes_different_phase_jobs_and_heartbeat(tmp_path):
    db = Database(tmp_path / "app.db")
    q = JobQueue(db)
    q.signal("north", "investigate", {"case_id": "shared", "phase": "investigate"}, now=0)
    q.poll(now=0)
    original = q.claim("first", now=0, lease=5)
    q.signal("north", "resume", {"case_id": "shared", "phase": "resume"}, now=1)
    q.poll(now=1)
    assert q.claim("other", now=1) is None
    assert q.heartbeat(original, now=4, lease=10)
    assert q.claim("other", now=6) is None
    assert q.complete(original, {"paused": True}, now=7)
    assert q.claim("other", now=7)["payload"]["phase"] == "resume"


def test_poller_does_not_starve_new_signals_after_first_batch(tmp_path):
    q = JobQueue(Database(tmp_path / "app.db"))
    for index in range(105):
        q.signal("north", f"event-{index:03d}", {"case_id": f"case-{index}"}, now=0)
    assert q.poll(now=0) == 100
    assert q.poll(now=0) == 5
    assert q.poll(now=0) == 0
