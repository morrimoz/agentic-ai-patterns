import pytest
from patterns.mcp_bridge import Compiler, Gateway, ERPClient, seed_erp, create_erp_app


def test_openapi_body_refs_and_real_mcp_subprocess(tmp_path):
    path = tmp_path / "erp.db"
    seed_erp(path)
    compiler = Compiler(create_erp_app(path).openapi())
    credit = compiler.by_name["create_credit"]
    assert credit.schema["properties"]["body"]["properties"]["amount_cents"]["type"] == "integer"
    assert "body" in credit.schema["required"]
    with Gateway(path, "north") as gateway:
        assert len(gateway.tools()) >= 3
        assert gateway.call("get_invoice", {"invoice_id": "INV-1042"})["amount_cents"] == 12000
        with pytest.raises(ValueError):
            gateway.call(
                "create_credit", {"body": {"invoice_id": "INV-1042", "amount_cents": 1, "reason": "bad"}}
            )
        with pytest.raises(Exception):
            gateway.call("get_invoice", {"invoice_id": False})
    with Gateway(path, "south") as gateway:
        with pytest.raises(Exception):
            gateway.call("get_invoice", {"invoice_id": "INV-1042"})


def test_mock_erp_has_real_idempotency_payload_conflict_and_financial_bounds(tmp_path):
    path = tmp_path / "erp.db"
    seed_erp(path)
    client = ERPClient(path)
    args = {"invoice_id": "INV-1042", "amount_cents": 10000, "reason": "duplicate payment"}
    one = client.credit("north", args, "operation-a")
    assert client.credit("north", args, "operation-a") == one
    with pytest.raises(ValueError):
        client.credit("north", {**args, "amount_cents": 9000}, "operation-a")
    with pytest.raises(ValueError):
        client.credit("north", {**args, "amount_cents": 3000}, "operation-b")
    assert len(client.credits("north", "INV-1042")) == 1
