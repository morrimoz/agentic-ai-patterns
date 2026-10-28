import pytest
from pydantic import BaseModel
from patterns.agents import Agent, Tool, Budget, BudgetExceeded


class Query(BaseModel):
    invoice_id: str


def test_model_sees_tool_schema_and_validates_arguments_before_execution():
    observed = []
    tool = Tool(
        "invoice",
        "Read invoice",
        Query,
        lambda args: observed.append(args.invoice_id) or {"id": args.invoice_id},
    )

    class Model:
        def complete(self, task, payload):
            assert payload["tools"][0]["inputSchema"]["properties"]["invoice_id"]["type"] == "string"
            if not payload["observations"]:
                return {"tool": "invoice", "arguments": {"invoice_id": "INV-7"}}
            return {"tool": None, "answer": {"invoice_id": "INV-7"}}

    result = Agent(Model(), [tool], Budget(3)).run("Read invoice", {"invoice_id": "INV-7"})
    assert result["answer"]["invoice_id"] == "INV-7" and observed == ["INV-7"]


def test_nested_agent_tool_uses_shared_budget_and_returns_structured_evidence():
    from patterns.agents.demo import demo

    result = demo()
    assert result["answer"]["overpayment_cents"] == 12000
    assert result["tool_calls"] >= 2
    assert result["model_calls"] >= 4


def test_budget_and_unknown_tools_fail_closed():
    class Loop:
        def complete(self, task, payload):
            return {"tool": "read", "arguments": {"invoice_id": "INV-7"}}

    tool = Tool("read", "Read invoice", Query, lambda args: {"id": args.invoice_id})
    with pytest.raises(BudgetExceeded):
        Agent(Loop(), [tool], Budget(2)).run("Read", {})

    class Unknown:
        def complete(self, task, payload):
            return {"tool": "delete_everything", "arguments": {}}

    with pytest.raises(ValueError):
        Agent(Unknown(), [tool], Budget(2)).run("Read", {})
