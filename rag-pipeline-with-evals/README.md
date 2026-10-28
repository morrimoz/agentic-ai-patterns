# Versioned retrieval with evals

## Read the implementation

- [knowledge.py](knowledge.py): Ingestion, line-preserving chunking, replacement transactions, FTS5/vector retrieval and metadata review.
- [fixtures.py](fixtures.py): Synthetic reference documents and golden question set.
- [evals.py](evals.py): Dense versus hybrid ablations, recall, MRR, negative cases and leakage reporting.

## Mechanism

Documents have content generations. Chunks carry source line ranges and generation-derived IDs. Changed ingestion replaces stale chunks and FTS rows together. Queries filter workspace before ranking, then fuse vector and full-text ranks. Metadata review refuses stale-generation drafts.

## Run

From the repository root after installation:

```bash
uv run python rag-pipeline-with-evals/demo.py
uv run pytest rag-pipeline-with-evals/test_rag.py
```

## Observable result

The eval demo runs 18 questions, reports recall@3 and MRR separately from negative-case success, and compares dense-only with hybrid retrieval. Read the individual results rather than treating one blended score as quality.

## Tradeoffs

Default embeddings are lexical hashes. This demonstrates index and evaluation engineering, not production semantic quality. The index is local and needs an explicit rebuild when an embedding model changes.

The integrated [invoice application](../application/README.md) uses these same implementations. [All patterns](../README.md).
