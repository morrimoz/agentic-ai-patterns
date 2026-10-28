"""Independent specialist contexts and a coordinator that can call agents as typed tools."""

from pydantic import BaseModel, ConfigDict, Field

from patterns.agents import Agent, Budget, Tool
from patterns.mcp_bridge import Gateway


class InvoiceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: str = Field(pattern=r"^INV-[0-9]+$")


class PolicyQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=3, max_length=500)
    k: int = Field(default=3, ge=1, le=5)


def investigate(service, tenant, case_id, invoice_id, coordinator=False, plan=None):
    budget = Budget(max_calls=24, max_seconds=60)

    def observe(kind, body):
        service.db.event(tenant, case_id, kind, body)

    with Gateway(service.erp.path, tenant) as gateway:

        def read(name, args):
            result = gateway.call(name, args.model_dump())
            evidence = service.db.receipt(
                tenant, "erp." + name, {"invoice_id": invoice_id, "response": result}
            )
            return {"data": result, "evidence": evidence}

        ledger_tools = [
            Tool(name, description, InvoiceQuery, lambda args, name=name: read(name, args))
            for name, description in [
                ("get_invoice", "Read current invoice amount and revision"),
                ("list_payments", "Read all booked payments"),
                ("list_credits", "Read existing credit receipts"),
            ]
        ]

        def policy(args):
            hits = service.knowledge.search(tenant, args.query, args.k)
            return {"data": hits}

        ledger = Agent(service.model, ledger_tools, budget, observe)
        policy_agent = Agent(
            service.model,
            [Tool("search_policy", "Find policy text with original line citations", PolicyQuery, policy)],
            budget,
            observe,
        )

        def run_ledger(args):
            if args.invoice_id != invoice_id:
                raise PermissionError("Specialist cannot change assigned invoice scope")
            return ledger.run(
                "Reconcile the invoice from current ledger records",
                {"assignment": "ledger", "invoice_id": invoice_id},
            )

        def run_policy(args):
            if args.invoice_id != invoice_id:
                raise PermissionError("Specialist cannot change assigned invoice scope")
            return policy_agent.run(
                "Retrieve duplicate payment credit rules", {"assignment": "policy", "invoice_id": invoice_id}
            )

        if coordinator:
            parent = Agent(
                service.model,
                [
                    Tool("ledger_specialist", "Investigate the invoice ledger", InvoiceQuery, run_ledger),
                    Tool("policy_specialist", "Research credit approval rules", InvoiceQuery, run_policy),
                ],
                budget,
                observe,
            )
            return parent.run(
                "Investigate possible duplicate payment",
                {"assignment": "coordinator", "invoice_id": invoice_id},
            )
        query = InvoiceQuery(invoice_id=invoice_id)
        from patterns.routing import Orchestrator, Plan

        planner = Orchestrator(service.model, observe)
        selected = Plan.model_validate(plan) if plan else planner.plan("Investigate invoice", invoice_id)
        execution = planner.execute(
            selected, {"ledger": lambda deps: run_ledger(query), "policy": lambda deps: run_policy(query)}
        )
        ledger_id = next(step.id for step in selected.steps if step.capability == "ledger")
        policy_id = next(step.id for step in selected.steps if step.capability == "policy")
        ledger_result = execution["results"][ledger_id]
        policy_result = execution["results"][policy_id]
    return {
        "plan_results": execution["results"],
        "ledger": ledger_result,
        "policy": policy_result,
        "model_calls": budget.calls,
        "tool_calls": budget.tool_calls,
    }
