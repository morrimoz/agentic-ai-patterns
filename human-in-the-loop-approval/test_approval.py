import pytest
from patterns.database import Database
from patterns.approval import ApprovalStore


def test_durable_approval_edit_reject_and_argument_binding(tmp_path):
    db = Database(tmp_path / "app.db")
    store = ApprovalStore(db)
    args = {"invoice_id": "INV-7", "amount_cents": 12000, "reason": "duplicate payment"}
    decision = store.propose("north", "case-7", "create_credit", args, ceiling=12000, now=0)
    with pytest.raises(PermissionError):
        store.authorize("north", decision["id"], "create_credit", args, now=1)
    reopened = ApprovalStore(Database(tmp_path / "app.db"))
    changed = reopened.decide(
        "north",
        decision["id"],
        "edit",
        "reviewer",
        expected_version=0,
        edited_args={**args, "amount_cents": 10000},
        now=1,
    )
    assert changed["arguments"]["amount_cents"] == 10000
    reopened.authorize("north", decision["id"], "create_credit", changed["arguments"], now=2)
    with pytest.raises(PermissionError):
        reopened.authorize("north", decision["id"], "create_credit", args, now=2)
    with pytest.raises(KeyError):
        reopened.get("south", decision["id"])


@pytest.mark.parametrize("amount", [0, -1, 12001, True])
def test_invalid_edits_do_not_consume_pending_approval(tmp_path, amount):
    store = ApprovalStore(Database(tmp_path / "app.db"))
    d = store.propose(
        "north",
        "case",
        "create_credit",
        {"invoice_id": "INV-7", "amount_cents": 12000, "reason": "duplicate"},
        ceiling=12000,
        now=0,
    )
    with pytest.raises(ValueError):
        store.decide(
            "north",
            d["id"],
            "edit",
            "reviewer",
            expected_version=0,
            edited_args={**d["arguments"], "amount_cents": amount},
            now=1,
        )
    assert store.get("north", d["id"])["status"] == "pending"


def test_expiry_version_and_rejection(tmp_path):
    store = ApprovalStore(Database(tmp_path / "app.db"))
    d = store.propose(
        "north",
        "case",
        "create_credit",
        {"invoice_id": "INV-7", "amount_cents": 10, "reason": "duplicate"},
        ceiling=10,
        now=0,
        ttl=5,
    )
    with pytest.raises(PermissionError):
        store.decide("north", d["id"], "approve", "reviewer", expected_version=0, now=6)
    other = store.propose("north", "other", "create_credit", d["arguments"], ceiling=10, now=0)
    store.decide("north", other["id"], "reject", "reviewer", expected_version=0, now=1)
    with pytest.raises(ValueError):
        store.decide("north", other["id"], "approve", "reviewer", expected_version=0, now=2)
