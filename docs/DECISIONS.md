# Architecture decisions

## Fixed graph, autonomous investigation

The workflow fixes the stages that matter: prepare context, plan, gather evidence, draft, evaluate, approve, execute, verify and store. Inside investigation, each specialist can select tools until it finishes or exhausts a shared call/time budget. Tool schemas and observations are visible to the model; the orchestrator binds completed dependency outputs to the next task.

The supported task family is invoice investigation. The router validates a plan across ledger, policy and draft capabilities. This is not an open-ended general assistant. Capability selection and natural-language quality with a real model remain separate evaluation work.

## Exact authority boundaries

The specialist MCP session exposes read operations only. The workspace is injected by the server process, not chosen in a tool argument. Write schemas can be compiled and inspected, but the workflow's trusted execution node owns accounting writes after approval. A model cannot grant itself permission by returning an approved flag.

Approval records bind tool name, arguments, reviewer, expiry, ceiling and version. An amount edit cannot change the invoice or reason. The graph checks current policy generation and ledger revision immediately before a new effect. These checks are conservative: any source change requires a new investigation.

Workspace headers are only a demonstration of an identity adapter. Production code must derive identity from authenticated credentials and protect worker endpoints. This repo provides no multi-user authentication service.

## At-least-once execution

Case creation and its initial outbox entry commit together. Decision and resume signal also commit together. Polling excludes already-projected signals so old records cannot starve later batches.

Jobs use transactional claims, bounded attempts, exponential backoff, lease renewal and attempt fencing. Different phases for one case cannot execute concurrently while a lease is active. The shared work document holds revisioned notes and evidence-backed item states. Notes do not authorize actions or prove task completion.

SQLite serializes local writers. It is suitable for inspecting the transaction boundaries in this example, not for claiming distributed database scalability. Use one `Service` per worker; the HTTP route creates an execution instance per tick.

The accounting service independently enforces idempotency and the current overpayment cap in its own transaction. A response loss after commit causes the graph node to run again. Recovery first looks for the exact operation receipt, then verifies it against the saved decision. There is no claim that the checkpoint database makes external calls exactly once. A real provider without idempotency or a receipt lookup needs an explicit unknown-outcome/reconciliation path.

## Retrieval and context

Document content is chunked with source line ranges and stable generation-derived IDs. Re-ingesting a changed document replaces old chunks and its full-text index in a transaction. Metadata drafts bind their generation; approval fails if the document changed meanwhile.

Retrieval filters by workspace before ranking. Hybrid retrieval fuses full-text and vector ranks using reciprocal rank fusion. The offline embedding provider is a hashed lexical representation, so dense-versus-hybrid results establish fixture behavior only. A real embedding provider can use the same interface.

The context store deduplicates turn IDs, selects whole previous turns within a character budget and includes only confirmed memories. Memory facts are drafted, linked to an existing source turn and reviewed before becoming persistent context. This is not automatic unrestricted memory extraction. An operating event records a verified outcome and remains distinct from user memory.

## Evaluation and correction

The model judge can reject a proposal or request better context. Deterministic checks independently validate the schema, invoice identity, integer monetary amount, verified ceiling and required citations. A model cannot override a failed guard.

One correction is allowed. The retry rereads the ledger, retrieves a larger policy context and includes the observed failures and dependency results. If the proposal remains unsupported it is blocked, not written. This is a bounded action evaluator, not a proof of arbitrary answer entailment.

## Packaging

The requested hyphenated folders contain the actual Python packages. Explicit `package-dir` mappings expose them as `patterns.workflow`, `patterns.agents` and similar imports. `demo.py` remains a small entry point; the implementation is beside it, not hidden in a second shared copy. The integrated service uses these same package interfaces.

## References

[LangGraph durable checkpoints](https://reference.langchain.com/python/langgraph.checkpoint.sqlite/SqliteSaver), [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [SQLite transactions](https://www.sqlite.org/lang_transaction.html).
