# Invoice investigation workbench

The application connects the nine pattern implementations. Every command uses durable local SQLite storage; the accounting sandbox owns a separate database. A pending approval can be resumed by another Python process.

## Inspect

- [service.py](service.py): submission transaction, outbox, worker claim, checkpoint recovery and decision boundary.
- [graph.py](../deterministic-workflow-with-subagents/graph.py): fixed nodes and conditional edges.
- [api.py](api.py): HTTP request/decision models and workspace handling.
- [cli.py](cli.py): CLI and response-loss walkthrough.
- [Acceptance cases](../tests/test_application.py): restart, concurrency, rejection, source changes and exact receipt verification.

## Interactive CLI

```bash
uv run agent-patterns --data .local-data seed
uv run agent-patterns --data .local-data submit --workspace north --invoice INV-1042 --request 'Investigate duplicate payment' --request-id investigation-1
uv run agent-patterns --data .local-data worker --owner investigator
```

Copy the `case_id` printed by submit. Read it before deciding:

```bash
uv run agent-patterns --data .local-data show CASE_ID
uv run agent-patterns --data .local-data decide CASE_ID --actor operator --action edit --amount-cents 10000 --version 0
uv run agent-patterns --data .local-data worker --owner executor
uv run agent-patterns --data .local-data show CASE_ID --events
```

Replace `CASE_ID` with the actual identifier. Use the current approval version from `show`; decisions use compare-and-swap rather than silently overwriting another review. The only editable field is the amount, bounded by the verified overpayment. `--action reject` performs no write.

For a fully paid invoice with no excess payment, submit `INV-1043` under a different request ID. It completes without a credit. A reused request ID with different content is refused.

Run a scheduled poll/worker loop with `worker --ticks 10 --interval 1`. A supervisor can restart the command; leases and durable job state coordinate multiple worker processes. Each process should construct its own `Service` instance.

## HTTP

```bash
uv run uvicorn patterns.api:app_factory --factory --host 127.0.0.1 --port 8000
```

Open [the local API docs](http://127.0.0.1:8000/docs). Supply `X-Workspace: north` on case routes and `X-Actor` on a decision. `POST /worker/tick` runs a single due job.

```bash
curl -s http://127.0.0.1:8000/cases \
  -H 'Content-Type: application/json' -H 'X-Workspace: north' \
  -d '{"invoice_id":"INV-1042","request":"Investigate duplicate payment","request_id":"http-1"}'
curl -s -X POST http://127.0.0.1:8000/worker/tick
```

The headers emulate a trusted identity adapter and can be forged locally. The worker endpoint is unauthenticated. Bind this demonstration to localhost only; neither is a production authentication design.

## Recovery boundaries

1. Accepted case and initial outbox signal commit together.
2. The poller projects signals into unique jobs. A claim carries an owner, lease and attempt number.
3. The worker serializes phases of one case and renews its lease. It checks ownership before an external effect.
4. The graph saves state to a SQLite checkpointer and pauses at a real LangGraph interrupt.
5. Reviewer decision and resume signal commit together. The execution node reads the saved decision, not an agent-supplied approval boolean.
6. A new write requires unexpired approval, exact approved arguments and unchanged ledger/policy revisions.
7. If the accounting operation exists after a lost response, recovery verifies the saved decision against that receipt. It reconciles the completed effect without requesting another write authorization.
8. The final node reads the credit back from the external ledger before marking the result verified. A separate store node saves the conversation and operating event.

[One-command walkthrough](cli.py) injects the response loss deliberately. The external accounting database is never rolled back with the application's checkpoint.
