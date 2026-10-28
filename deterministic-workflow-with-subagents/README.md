# Fixed workflow with autonomous sub-agents

## Read the implementation

- [graph.py](graph.py): The complete LangGraph, typed state, durable interrupt, effect reconciliation and store node.
- [specialists.py](specialists.py): Ledger and policy specialists with isolated tool sets and shared budgets.

## Mechanism

The outer workflow fixes business stages. Inside investigation, agents inspect tool schemas and observations to choose the next read. Ledger facts are independently reread and compared before a proposal is accepted.

## Run

From the repository root after installation:

```bash
uv run python deterministic-workflow-with-subagents/demo.py
uv run pytest deterministic-workflow-with-subagents/test_workflow.py
```

## Observable result

The demo investigates INV-1042 and pauses with a proposed 12000-cent credit and zero accounting effects. It returns the actual state, plan, evidence IDs and specialist call counts.

## Tradeoffs

Fixed stages simplify auditing but restrict task families. Model output is not deterministic. SQLite checkpoints persist the graph; a worker lease serializes case phases.

The integrated [invoice application](../application/README.md) uses these same implementations. [All patterns](../README.md).
