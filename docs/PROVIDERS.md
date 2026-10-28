# Model providers and reproducibility

Default mode makes no paid model or embedding requests. `FixtureModel` substitutes inference decisions for the supported invoice-investigation task family. It chooses its next tool from prior observations, calculates a draft from verified supplied facts and returns structured JSON. It is deliberately deterministic and is not evidence of general natural-language understanding.

Everything surrounding inference executes: JSON-schema validation, agent loops, MCP transport, REST handling, ledger queries, ingestion, full-text/vector ranking, checkpoints, approvals, outbox polling, job claims and receipt reconciliation.

## Optional compatible HTTP provider

```bash
export AI_PROVIDER=http
export AI_BASE_URL=http://127.0.0.1:8001/v1
export AI_MODEL=your-chat-model
export EMBEDDING_PROVIDER=http
export AI_EMBEDDING_MODEL=your-embedding-model
# Supply AI_API_KEY privately only if the endpoint requires it.
uv run agent-patterns walkthrough
```

The adapter calls `/chat/completions` with JSON-object output and `/embeddings`, each with a 30-second timeout. Credentials are read from the environment for HTTP headers and never included in model prompts. The adapter does not silently replace a failing provider with a fixture response.

Prompts and the typed contracts are in [providers.py](../patterns/providers.py), [agent.py](../agents-as-tools/agent.py), [planner.py](../router-and-orchestrator/planner.py) and [evaluator.py](../evaluator-retry-loop/evaluator.py). The real provider must satisfy those same contracts. Actual-model routing, tool choices, groundedness and cost have not been benchmarked here.

Use one embedding provider/model for ingestion and queries. Rebuild the local data directory when changing model configuration. The corpus rejects dimension changes; same-dimension model changes require an explicit rebuild. The default fixture uses hashed word vectors rather than claiming semantic embeddings.

`run_all.py` and pytest force offline providers. Run individual demos or the CLI to opt into HTTP inference. Fixture fault modes deliberately fabricate a first draft or every draft to exercise correction and blocking. They do not measure how frequently a real model makes those errors.

Environment files are not automatically loaded. Local databases, credentials and generated evidence are ignored by Git.
