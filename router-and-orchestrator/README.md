# Router and orchestrator

## Read the implementation

- [planner.py](planner.py): Pydantic plans, capability validation, ordered dependencies and result binding.

## Mechanism

The model produces stable job IDs, capabilities and dependency IDs. Validation refuses unknown capabilities, duplicate IDs, missing prerequisites and a draft without ledger and policy dependencies. The orchestrator passes actual dependency results into each handler. The graph checkpoints evidence collection separately from drafting.

## Run

From the repository root after installation:

```bash
uv run python router-and-orchestrator/demo.py
uv run pytest router-and-orchestrator/test_routing.py
```

## Observable result

The executed capabilities are ledger, policy and draft. The final proposal amount comes from the current invoice and payments, rather than a fixture handler returning an arbitrary result.

## Tradeoffs

This router supports one explicit task family. Schema correctness cannot establish semantic intent. The fixture model returns a repeatable plan; real-model routing needs its own labelled evaluation.

The integrated [invoice application](../application/README.md) uses these same implementations. [All patterns](../README.md).
