import pytest
from patterns.context import ContextStore
from patterns.database import Database


def test_context_memory_store_idempotency_and_scope(tmp_path):
    store = ContextStore(Database(tmp_path / "context.db"))
    store.save("north", "thread", "turn-1", "Prefer concise updates", "Preference saved")
    store.save("north", "thread", "turn-1", "Prefer concise updates", "Preference saved")
    with pytest.raises(ValueError):
        store.save("north", "thread", "turn-1", "different", "reply")
    draft = store.draft_memory("north", {"fact": "Prefer concise updates", "source_turn": "turn-1"})
    assert not store.memories("north")
    store.confirm_memory("north", draft["id"])
    reopened = ContextStore(Database(tmp_path / "context.db"))
    pack = reopened.assemble("north", "thread", "What next?", budget=300)
    assert pack["used_chars"] <= 300 and pack["memories"]
    assert not reopened.assemble("south", "thread", "What next?", budget=300)["memories"]
    assert not reopened.assemble("north", "other", "What next?", budget=300)["turns"]
    with pytest.raises(ValueError):
        reopened.assemble("north", "thread", "x" * 301, budget=300)
