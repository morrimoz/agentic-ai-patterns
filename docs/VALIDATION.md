# Recorded validation

Date: 2026-10-28. Local macOS execution with synthetic records and offline model providers. LangGraph, SQLite, FastAPI and the MCP subprocess execute normally. No real business account or paid inference is involved.

## Run the same acceptance

```bash
uv sync --locked --extra dev
uv run python scripts/verify.py
```

The command runs the behavioral acceptance suite, all nine focused demos, an actual localhost HTTP lifecycle and the integrated response-loss walkthrough. It saves command output, exit codes, timings, provider mode and a source fingerprint to `evidence/verification.json`.

## Compatibility

| Python | Behavioral checks | Focused demos | HTTP lifecycle | Integrated recovery |
| --- | --- | --- | --- | --- |
| 3.11.10 | 41 passed | 9 passed | Passed | Passed |
| 3.14.10 | 41 passed | 9 passed | Passed | Passed |
| 3.15.2 | 41 passed | 9 passed | Passed | Passed |

Python 3.15 is the default. Linux CI is configured for the three release lines. GitHub Actions also passed the full offline verification on Linux across all three release lines. [Initial hosted run](https://github.com/morrimoz/agentic-ai-patterns/actions/runs/40765416390) includes downloadable evidence for each runtime. Python 3.15 exposes upstream LangSmith deprecation warnings, which do not fail acceptance.

The wheel was also installed in an isolated Python 3.15.2 environment. All nine demo scripts and the integrated walkthrough passed with a working directory outside the source checkout. This checks that the explicit package mappings are included in distribution.

## Expected and observed outcomes

| Scenario | Expected | Observed |
| --- | --- | --- |
| Duplicate payment | Propose the computed 12000-cent excess, without writing | Awaiting approval; zero credits |
| Fully reconciled invoice | Finish without a credit | Completed with verified no-action result |
| Reviewed edit and fresh process | Resume from durable state using edited amount | One 10000-cent credit, receipt verified |
| Rejection | No external write | Rejected, zero credits |
| Lost response after accounting commit | Recover without duplicating the external effect | One credit after recovery |
| Approval expires after a committed effect | Reconcile the completed effect without another write | Verified matching receipt |
| Ledger or policy changes after proposal | Refuse stale authorization | Blocked before a new effect |
| Fabricated first-draft evidence | Upgrade context and retry once | Corrected second draft reaches approval |
| Fabricated evidence on both drafts | Stop before approval or write | Blocked, zero credits |
| Concurrent worker connections | One investigator owns the job | One claim and one plan event |
| Different phase jobs for one case | Serialize active execution | Second phase waits for the active owner |
| Stale lease owner | Refuse late completion | Refused |
| More than one poller batch | Do not rescan only old signals forever | 100 jobs, then 5, then 0 |
| Wrong workspace | No record access or retrieval leakage | 404 / empty scoped results |
| Changed document | Remove stale chunks and reject old metadata draft | Replacement and refusal verified |
| Real MCP client/server | Initialize, discover typed tools and call mock HTTP API | Passed through stdio subprocess |

The HTTP smoke check makes real requests to a local Uvicorn server on port 8765. It submits an investigation, runs a worker, checks the pending proposal, refuses another workspace, applies an edited decision, verifies the external ledger receipt and confirms an idle replay. The endpoint results are saved to `evidence/http.json`.

## Retrieval evaluation

The golden set has 18 questions: 16 positive reference lookups and two unrelated negative queries. The harness reports dense-only and hybrid retrieval separately.

Observed hybrid results with fixture lexical embeddings:

- Recall@3: 1.0
- MRR: 0.96875
- Negative-query success: 1.0
- Cross-workspace hits: 0

These are regression scores for a small synthetic corpus. They do not establish real-model semantic retrieval quality. [Per-question cases and ablations](../rag-pipeline-with-evals/evals.py) remain inspectable.

## Evidence files

- `verification.json`: commands, output, runtime, source identity and overall result.
- `latest.json`: per-demo command, elapsed time and full structured output.
- `http.json`: expected/actual HTTP status and returned state for each lifecycle request.
- `integrated.json`: proposal, approval, receipt, shared work document and recovery event trail.

Generated receipts stay out of Git and are uploaded as CI artifacts. The source fingerprint covers implementations, tests, scripts, demos, CI, dependency lock and runtime configuration. Documentation edits do not change it.

Real-model quality/cost, production authentication, multi-host deployment and providers without idempotency still need separate acceptance work.
