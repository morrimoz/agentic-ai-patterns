# OpenAPI to MCP tools

## Read the implementation

- [compiler.py](compiler.py): Local reference resolution, JSON request bodies, path/query schemas and effect annotations.
- [server.py](server.py): MCP discovery and guarded tool execution.
- [gateway.py](gateway.py): Managed stdio subprocess lifecycle and MCP client.
- [erp.py](erp.py): Separate FastAPI accounting sandbox with transactions, provider idempotency and amount bounds.

## Mechanism

FastAPI generates an OpenAPI document. The compiler resolves local schema references and exposes exact MCP argument schemas. Server-injected workspace and idempotency headers are excluded from model arguments. The read-only specialist session cannot discover or execute write tools.

## Run

From the repository root after installation:

```bash
uv run python mcp-server-from-rest-api/demo.py
uv run pytest mcp-server-from-rest-api/test_mcp.py
```

## Observable result

The demo starts an actual MCP server subprocess, discovers ledger read tools and reads invoice INV-1042. It also displays the compiled credit request-body schema. Writes are executed by the trusted workflow boundary after review, not by the read-only agent session.

## Tradeoffs

The compiler handles GET/POST with path/query parameters and JSON bodies. It intentionally rejects external/cyclic schema references and unsupported methods. The REST API runs in process behind its HTTP interface; MCP transport is an actual subprocess. No real accounting provider is contacted.

The integrated [invoice application](../application/README.md) uses these same implementations. [All patterns](../README.md).
