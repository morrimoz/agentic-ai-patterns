# Event-driven jobs and shared work

## Read the implementation

- [runner.py](runner.py): Transactional outbox polling, job leases, attempt fencing, heartbeat, backoff and case-phase serialization.
- [work_document.py](work_document.py): Revisioned agent notes and evidence-backed progress.
- [../application/service.py](../application/service.py): Graph recovery and queue integration.

## Mechanism

A committed DB signal is projected into a unique job. Workers claim with a lease and attempt identity. Concurrent jobs for the same case serialize. Stale owners cannot complete a job. A shared work document records each evidence-backed milestone; an agent note does not prove completion.

## Run

From the repository root after installation:

```bash
uv run python event-driven-job-runner/demo.py
uv run pytest event-driven-job-runner/test_jobs.py
```

## Observable result

The demo injects response loss after the accounting commit. A new worker resumes the durable graph and reconciles the existing receipt. The ledger contains one effect after recovery.

## Tradeoffs

Polling adds latency and SQLite coordinates one local database. The accounting provider separately enforces idempotency. A database checkpoint alone cannot guarantee exactly-once external effects.

The integrated [invoice application](../application/README.md) uses these same implementations. [All patterns](../README.md).
