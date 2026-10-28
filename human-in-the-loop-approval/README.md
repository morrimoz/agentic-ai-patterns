# Durable human approval

## Read the implementation

- [approval.py](approval.py): Versioned decisions, exact argument binding, bounded edits, expiry and transactional resume outbox.
- [../deterministic-workflow-with-subagents/graph.py](../deterministic-workflow-with-subagents/graph.py): LangGraph interrupt and separately checkpointed execution node.

## Mechanism

The workflow creates a durable pending proposal and interrupts before a write. A reviewer can approve, edit the amount or reject. Decision version prevents overwriting another review. The execution node rereads authority and source revisions. A resume value identifies the decision; it cannot itself grant permission.

## Run

From the repository root after installation:

```bash
uv run python human-in-the-loop-approval/demo.py
uv run pytest human-in-the-loop-approval/test_approval.py
```

## Observable result

The demo pauses, opens a new Service instance, edits 12000 cents to 10000, resumes execution and verifies one credit receipt. The application acceptance also resumes from a fresh Python interpreter.

## Tradeoffs

Reviewer authentication is outside this local demo. Production needs an authenticated identity adapter. Expired approval forbids a new effect; reconciliation of an already committed matching effect does not create a second write.

The integrated [invoice application](../application/README.md) uses these same implementations. [All patterns](../README.md).
