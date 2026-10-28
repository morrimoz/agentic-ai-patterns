"""Runnable scenario using the implementation beside this file."""

from patterns.providers import emit

from patterns.context import ContextStore


def demo():
    import tempfile
    from pathlib import Path
    from patterns.database import Database

    with tempfile.TemporaryDirectory() as path:
        store = ContextStore(Database(Path(path) / "context.db"))
        store.save("north", "review", "turn-1", "Prefer concise updates", "Saved as a draft preference")
        draft = store.draft_memory("north", {"fact": "Prefer concise updates", "source_turn": "turn-1"})
        store.confirm_memory("north", draft["id"])
        return {
            "same_scope": store.assemble("north", "review", "Investigate invoice INV-1042", budget=800),
            "other_workspace": store.assemble("south", "review", "Investigate invoice INV-1042", budget=800),
        }


if __name__ == "__main__":
    emit(demo())
