from patterns.database import Database
from patterns.rag import KnowledgeBase, run_evals


def test_real_ingestion_generation_metadata_and_scoped_hybrid_retrieval(tmp_path):
    kb = KnowledgeBase(Database(tmp_path / "knowledge.db"))
    first = kb.ingest(
        "north",
        "policy",
        "# Credits\n\nDuplicate payments can be credited up to the overpayment.\n\nKeep the original invoice.",
        kind="file",
    )
    hits = kb.search("north", "duplicate payment credit", k=3)
    assert hits and hits[0]["document_id"] == "policy"
    assert hits[0]["line_start"] >= 1 and hits[0]["text"]
    assert kb.search("south", "duplicate payment credit") == []
    updated = kb.ingest("north", "policy", "# Credits\n\nCredits require review by an operator.", kind="file")
    assert updated["generation"] != first["generation"]
    assert all("up to the overpayment" not in h["text"] for h in kb.search("north", "credit", k=10))
    assert (
        kb.ingest("north", "policy", "# Credits\n\nCredits require review by an operator.", kind="file")[
            "generation"
        ]
        == updated["generation"]
    )
    draft = kb.draft_metadata("north", "policy")
    assert not kb.document("north", "policy")["metadata"]
    kb.approve_metadata("north", draft["id"])
    assert kb.document("north", "policy")["metadata"]["title"]


def test_eval_harness_measures_scopes_abstention_and_retrieval(tmp_path):
    report = run_evals(tmp_path)
    assert report["cases"] >= 16
    assert report["recall_at_3"] >= 0.85
    assert report["tenant_leaks"] == 0
    assert report["negative_pass_rate"] == 1
    assert "dense" in report["ablations"] and "hybrid" in report["ablations"]


def test_metadata_approval_refuses_stale_generation(tmp_path):
    import pytest

    kb = KnowledgeBase(Database(tmp_path / "knowledge.db"))
    kb.ingest("north", "policy", "# Policy\nDuplicate payment credits require review.")
    draft = kb.draft_metadata("north", "policy")
    kb.ingest("north", "policy", "# Policy\nAll credits are currently suspended.")
    with pytest.raises(ValueError):
        kb.approve_metadata("north", draft["id"])
