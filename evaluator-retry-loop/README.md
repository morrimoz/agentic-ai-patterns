# Evidence-driven evaluation and retry

## Read the implementation

- [evaluator.py](evaluator.py): Typed proposals and judge output, integer amount bounds, invoice identity and required-source coverage.
- [../deterministic-workflow-with-subagents/graph.py](../deterministic-workflow-with-subagents/graph.py): Draft/evaluate/upgrade-context loop and two-attempt limit.

## Mechanism

The model judge reviews the proposal, while deterministic checks independently enforce arithmetic and evidence. Missing or fabricated citations trigger a reread of the ledger and wider retrieval context. The next draft receives failures and actual dependency outputs. A second failure blocks the action.

## Run

From the repository root after installation:

```bash
uv run python evaluator-retry-loop/demo.py
uv run pytest evaluator-retry-loop/test_evaluation.py
```

## Observable result

The demo intentionally fabricates the first draft citation. Evaluation rejects it, upgrades the context and accepts the corrected second draft. The always-fabricate acceptance case ends blocked with no credit.

## Tradeoffs

This evaluator verifies a narrow financial-action contract. It does not prove arbitrary natural-language entailment. The fixture judge tests control flow; precision and false-acceptance rates with a real judge remain separate work.

The integrated [invoice application](../application/README.md) uses these same implementations. [All patterns](../README.md).
