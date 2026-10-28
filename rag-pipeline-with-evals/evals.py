"""Report retrieval quality and negatives separately, with dense versus hybrid ablations."""

from patterns.database import Database
from .knowledge import KnowledgeBase
from .fixtures import GOLDEN, seed_knowledge


def run_evals(path):
    from pathlib import Path

    kb = KnowledgeBase(Database(Path(path) / "eval.db"))
    seed_knowledge(kb)
    ablations = {}
    for mode in ["dense", "hybrid"]:
        rows = []
        recalls = []
        ranks = []
        negatives = []
        leaks = 0
        for question, relevant in GOLDEN:
            hits = kb.search("north", question, k=3, mode=mode)
            ids = [hit["document_id"] for hit in hits]
            leaks += sum(hit["tenant"] != "north" for hit in hits)
            if relevant:
                recalls.append(int(relevant in ids))
                ranks.append(1 / (ids.index(relevant) + 1) if relevant in ids else 0)
            else:
                negatives.append(not hits)
            rows.append({"question": question, "expected": relevant, "retrieved": ids})
        ablations[mode] = {
            "recall_at_3": sum(recalls) / len(recalls),
            "mrr": sum(ranks) / len(ranks),
            "negative_pass_rate": sum(negatives) / len(negatives),
            "tenant_leaks": leaks,
            "results": rows,
        }
    return {
        "cases": len(GOLDEN),
        **{k: v for k, v in ablations["hybrid"].items() if k != "results"},
        "ablations": ablations,
        "scope": "Fixture lexical embeddings: regression evidence, not real-model semantic quality",
    }
