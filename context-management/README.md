# Context management

## Read the implementation

- [context.py](context.py): Idempotent turn persistence, reviewed memory drafts and bounded context assembly.
- [../deterministic-workflow-with-subagents/graph.py](../deterministic-workflow-with-subagents/graph.py): Start-of-turn assembly and end-of-turn store nodes.

## Mechanism

Assembly selects only the current workspace and thread, keeps the current request intact, then includes reviewed memories and whole earlier turns within a character budget. Turn IDs make repeated storage idempotent. A memory draft references a saved source turn and remains unavailable until confirmed.

## Run

From the repository root after installation:

```bash
uv run python context-management/demo.py
uv run pytest context-management/test_context.py
```

## Observable result

The demo saves and confirms a preference, reassembles it in the same workspace and shows an empty memory set in another workspace.

## Tradeoffs

Character budgets are easy to audit but do not exactly predict model tokens. Whole-turn eviction can lose useful history. This explicit memory workflow does not infer personal facts or automatically promote agent prose.

The integrated [invoice application](../application/README.md) uses these same implementations. [All patterns](../README.md).
