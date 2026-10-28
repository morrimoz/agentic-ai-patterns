# Agents as tools

## Read the implementation

- [agent.py](agent.py): Tool schema exposure, Pydantic argument validation, observe/act loop and shared execution budgets.
- [../deterministic-workflow-with-subagents/specialists.py](../deterministic-workflow-with-subagents/specialists.py): A coordinator calling ledger and policy agents as typed tools.

## Mechanism

The coordinator receives specialist tools with descriptions and JSON schemas. Each specialist has its own objective, context and observations. Both nested and parent calls consume one shared budget. Unregistered tools, invalid arguments and oversize observations are refused before further execution.

## Run

From the repository root after installation:

```bash
uv run python agents-as-tools/demo.py
uv run pytest agents-as-tools/test_agents.py
```

## Observable result

The coordinator delegates ledger and policy reads. The ledger specialist reads invoice, payments and existing credits through MCP and computes a verified overpayment.

## Tradeoffs

Nested agents add latency and may duplicate work if assignments overlap. The bounded runtime demonstrates orchestration mechanics; the fixture does not establish real-model tool-selection quality. HTTP inference uses the same contracts.

The integrated [invoice application](../application/README.md) uses these same implementations. [All patterns](../README.md).
