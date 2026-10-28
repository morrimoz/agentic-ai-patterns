"""Runnable scenario using the implementation beside this file."""

from patterns.providers import emit

from patterns.mcp_bridge import Compiler, Gateway, create_erp_app, seed_erp


def demo():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as path:
        database = Path(path) / "erp.db"
        seed_erp(database)
        compiler = Compiler(create_erp_app(database).openapi())
        with Gateway(database, "north") as gateway:
            return {
                "transport": "mcp-stdio",
                "discovered": gateway.tools(),
                "invoice": gateway.call("get_invoice", {"invoice_id": "INV-1042"}),
                "credit_schema": compiler.by_name["create_credit"].schema,
            }


if __name__ == "__main__":
    emit(demo())
