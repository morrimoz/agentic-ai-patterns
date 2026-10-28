"""Typed capability plans and dependency-based result binding."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=60)
    capability: str
    depends_on: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[Step] = Field(min_length=1, max_length=8)


def validate_plan(plan):
    seen = {}
    for step in plan.steps:
        if step.capability not in {"ledger", "policy", "draft"}:
            raise ValueError("Capability is not registered")
        if step.id in seen or not set(step.depends_on) <= seen.keys():
            raise ValueError("Duplicate identity, missing dependency or cycle")
        if step.capability == "draft":
            dependencies = {seen[identity] for identity in step.depends_on}
            if dependencies != {"ledger", "policy"}:
                raise ValueError("Draft must depend on fresh ledger and policy evidence")
        seen[step.id] = step.capability
    if set(seen.values()) != {"ledger", "policy", "draft"} or len(seen) != 3:
        raise ValueError("Investigation needs one ledger, policy and draft step")
    return plan


class Orchestrator:
    def __init__(self, model, observe=None):
        self.model = model
        self.observe = observe or (lambda kind, body: None)

    def plan(self, request, invoice_id):
        raw = self.model.complete(
            "route",
            {
                "request": request,
                "invoice_id": invoice_id,
                "capabilities": {
                    "ledger": "Read current invoice, payments and credits",
                    "policy": "Retrieve approval policy",
                    "draft": "Draft from both evidence sets",
                },
            },
        )
        self.observe("model.called", {"task": "route"})
        return validate_plan(Plan.model_validate(raw))

    def execute(self, plan, handlers, prior_results=None):
        results = dict(prior_results or {})
        executed = []
        for step in validate_plan(plan).steps:
            if step.id in results or step.capability not in handlers:
                continue
            if not set(step.depends_on) <= results.keys():
                raise ValueError("Required dependency output is not available")
            dependencies = {identity: results[identity] for identity in step.depends_on}
            results[step.id] = handlers[step.capability](dependencies)
            executed.append(step.capability)
            self.observe("plan.step_completed", {"step_id": step.id, "capability": step.capability})
        return {"results": results, "executed": executed}
