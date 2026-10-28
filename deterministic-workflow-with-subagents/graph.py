"""Durable fixed workflow with bounded autonomous investigation inside one node."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from patterns.database import digest
from patterns.evaluation import Judge, evaluate_proposal
from patterns.routing import Orchestrator, Plan
from .specialists import investigate


class State(TypedDict, total=False):
    tenant: str
    case_id: str
    invoice_id: str
    request: str
    status: str
    steps: list[str]
    context: dict
    plan: dict
    plan_results: dict
    executed: list[str]
    facts: dict
    policy: dict
    evidence_ids: list[str]
    draft_attempts: int
    proposal: dict
    failures: list[str]
    approval: dict
    ledger_fingerprint: str
    policy_generation: str
    report: dict
    specialist_tool_calls: int
    effect: dict
    resume: dict


def build_graph(service, checkpointer):
    def event(state, kind, body=None):
        service.db.event(state["tenant"], state["case_id"], kind, body)

    def assemble(state):
        context = service.context.assemble(state["tenant"], state["case_id"], state["request"])
        return {"context": context, "steps": ["assemble"], "draft_attempts": 0}

    def plan(state):
        planner = Orchestrator(service.model, lambda kind, body: event(state, kind, body))
        planned = planner.plan(state["request"], state["invoice_id"])
        event(state, "workflow.planned", planned.model_dump())
        return {"plan": planned.model_dump(), "steps": state["steps"] + ["plan"]}

    def research(state):
        result = investigate(
            service, state["tenant"], state["case_id"], state["invoice_id"], plan=state["plan"]
        )
        facts = result["ledger"]["answer"]
        # Agent arithmetic is checked against server reads before any proposal can pass.
        actual = service.erp.facts(state["tenant"], state["invoice_id"])
        if any(
            facts.get(key) != actual[key]
            for key in ["invoice_id", "invoice_cents", "paid_cents", "credited_cents", "overpayment_cents"]
        ):
            raise ValueError("Specialist facts disagree with the accounting ledger")
        policy = result["policy"]["answer"]
        hits = service.knowledge.search(
            state["tenant"], "duplicate payment credit operator approval overpayment", 3
        )
        valid_ids = {hit["id"] for hit in hits if hit["document_id"] == "credit-policy"}
        if not policy.get("allowed") or not valid_ids.intersection(policy.get("citations", [])):
            raise ValueError("No current authoritative credit policy evidence")
        facts = {**actual, "policy_limit_cents": actual["overpayment_cents"]}
        policy_generation = service.knowledge.document(state["tenant"], "credit-policy")["generation"]
        evidence = facts_evidence = result["ledger"]["answer"]["evidence"]
        for identity in evidence:
            service.db.evidence(state["tenant"], identity)
        evidence = evidence + list(valid_ids)
        facts["required_evidence"] = evidence
        ledger_receipt = service.db.receipt(state["tenant"], "ledger.verified", facts)
        service.docs.complete_item(state["tenant"], state["case_id"], "read_ledger", ledger_receipt)
        policy_receipt = service.db.receipt(
            state["tenant"], "policy.verified", {"citations": list(valid_ids)}
        )
        service.docs.complete_item(state["tenant"], state["case_id"], "review_policy", policy_receipt)
        event(
            state,
            "workflow.investigated",
            {"facts": facts, "tool_calls": result["tool_calls"], "ledger_evidence": facts_evidence},
        )
        return {
            "plan_results": result["plan_results"],
            "facts": facts,
            "policy": policy,
            "evidence_ids": evidence,
            "executed": ["ledger", "policy"],
            "ledger_fingerprint": digest(actual),
            "policy_generation": policy_generation,
            "specialist_tool_calls": result["tool_calls"],
            "steps": state["steps"] + ["investigate"],
        }

    def draft(state):
        attempt = state.get("draft_attempts", 0) + 1

        def compose(dependencies):
            return service.model.complete(
                "draft",
                {
                    "facts": state["facts"],
                    "evidence_ids": state["evidence_ids"],
                    "policy": state["policy"],
                    "attempt": attempt,
                    "previous_failures": state.get("failures", []),
                    "dependency_outputs": dependencies,
                },
            )

        planner = Orchestrator(service.model, lambda kind, body: event(state, kind, body))
        planned = Plan.model_validate(state["plan"])
        execution = planner.execute(planned, {"draft": compose}, prior_results=state["plan_results"])
        draft_id = next(step.id for step in planned.steps if step.capability == "draft")
        proposal = execution["results"][draft_id]
        event(state, "model.called", {"task": "draft", "attempt": attempt})
        return {
            "proposal": proposal,
            "draft_attempts": attempt,
            "steps": state["steps"] + ["draft"],
            "executed": ["ledger", "policy", "draft"],
        }

    def evaluate(state):
        verdict = evaluate_proposal(state["proposal"], state["facts"], state["evidence_ids"])
        judge = Judge.model_validate(
            service.model.complete(
                "judge",
                {
                    "proposal": state["proposal"],
                    "facts": state["facts"],
                    "failures": verdict.failures,
                    "evidence_ids": state["evidence_ids"],
                },
            )
        )
        event(state, "model.called", {"task": "judge", "attempt": state["draft_attempts"]})
        failures = verdict.failures + judge.missing_evidence if not judge.accepted else verdict.failures
        accepted = verdict.accepted and judge.accepted
        status = "validated" if accepted else "retry" if state["draft_attempts"] < 2 else "blocked"
        event(
            state,
            "evaluation.completed",
            {"accepted": accepted, "failures": failures, "attempt": state["draft_attempts"]},
        )
        return {"status": status, "failures": failures, "steps": state["steps"] + ["evaluate"]}

    def upgrade(state):
        # Reread authoritative sources rather than just asking the same model to try harder.
        actual = service.erp.facts(state["tenant"], state["invoice_id"])
        if digest(actual) != state["ledger_fingerprint"]:
            raise ValueError("Ledger changed during investigation")
        hits = service.knowledge.search(
            state["tenant"], "duplicate payment credit operator approval overpayment", 5
        )
        event(state, "evaluation.context_upgraded", {"documents": [hit["id"] for hit in hits]})
        return {"policy": {**state["policy"], "additional_context": hits}}

    def approval(state):
        if state["proposal"]["action"] == "no_action":
            return {"status": "no_action", "steps": state["steps"] + ["approval"]}
        record = service.approvals.propose(
            state["tenant"],
            state["case_id"],
            "create_credit",
            state["proposal"]["arguments"],
            ceiling=state["facts"]["overpayment_cents"],
            now=service.clock(),
        )
        service.update_case(
            state["tenant"],
            state["case_id"],
            {
                **state,
                "status": "awaiting_approval",
                "approval": record,
                "steps": state["steps"] + ["approval"],
            },
        )
        signal = interrupt(
            {
                "approval_id": record["id"],
                "version": record["version"],
                "tool": record["tool"],
                "arguments": record["arguments"],
                "choices": ["approve", "edit", "reject"],
            }
        )
        if not isinstance(signal, dict) or signal.get("approval_id") != record["id"]:
            raise PermissionError("Invalid approval resume identity")
        resolved = service.approvals.get(state["tenant"], record["id"])
        if resolved["status"] == "rejected":
            return {"approval": resolved, "status": "rejected", "steps": state["steps"] + ["approval"]}
        service.approvals.authorize(
            state["tenant"], record["id"], "create_credit", resolved["arguments"], service.clock()
        )
        return {"approval": resolved, "status": "approved", "steps": state["steps"] + ["approval"]}

    def execute(state):
        service.assert_ownership()
        approved = service.approvals.get(state["tenant"], state["approval"]["id"])
        operation = "credit-" + state["case_id"]
        args = approved["arguments"]
        existing = service.erp.credits(state["tenant"], state["invoice_id"])
        prior = next((credit for credit in existing if credit["operation_id"] == operation), None)
        if prior is not None:
            if approved["status"] != "approved" or any(
                prior[key] != args[key] for key in ["invoice_id", "amount_cents", "reason"]
            ):
                raise PermissionError("Existing provider effect does not match the saved decision")
            result = prior
            event(state, "effect.reconciled", {"receipt_id": prior["id"], "operation_id": operation})
        else:
            service.approvals.authorize(
                state["tenant"], approved["id"], "create_credit", args, service.clock()
            )
            actual = service.erp.facts(state["tenant"], state["invoice_id"])
            generation = service.knowledge.document(state["tenant"], "credit-policy")["generation"]
            if digest(actual) != state["ledger_fingerprint"] or generation != state["policy_generation"]:
                event(state, "effect.blocked", {"reason": "source_changed_after_approval"})
                return {
                    "status": "blocked",
                    "report": {
                        "verified": False,
                        "reason": "Ledger or policy changed after proposal; investigate again",
                    },
                }
            result = service.erp.credit(state["tenant"], args, operation)
        event(
            state,
            "tool.executed",
            {"tool": "create_credit", "operation_id": operation, "receipt_id": result["id"]},
        )
        if service.fault == "after_effect":
            service.fault = None
            raise RuntimeError("Injected response loss after accounting commit")
        receipt = service.db.receipt(state["tenant"], "credit.created", result)
        service.docs.complete_item(state["tenant"], state["case_id"], "execute_action", receipt)
        return {"effect": result, "status": "executed"}

    def finalize(state):
        service.assert_ownership()
        if state["status"] == "rejected":
            report = {
                "verified": True,
                "outcome": "rejected",
                "amount_cents": 0,
                "citations": state["evidence_ids"],
            }
            status = "rejected"
        elif state["status"] == "no_action":
            actual = service.erp.facts(state["tenant"], state["invoice_id"])
            if actual["overpayment_cents"] != 0:
                return {"status": "blocked", "report": {"verified": False, "reason": "Ledger changed"}}
            report = {
                "verified": True,
                "outcome": "no_action",
                "amount_cents": 0,
                "citations": state["evidence_ids"],
            }
            status = "completed"
        else:
            records = service.erp.credits(state["tenant"], state["invoice_id"])
            effect = state["effect"]
            if effect not in records:
                raise ValueError("External credit receipt could not be verified")
            if effect["amount_cents"] != state["approval"]["arguments"]["amount_cents"]:
                raise ValueError("Verified effect differs from approved amount")
            report = {
                "verified": True,
                "outcome": "credit_created",
                "amount_cents": effect["amount_cents"],
                "receipt": effect,
                "citations": state["evidence_ids"],
            }
            status = "completed"
            event(
                state, "effect.verified", {"receipt_id": effect["id"], "amount_cents": effect["amount_cents"]}
            )
        result = service.db.receipt(state["tenant"], "case.result", report)
        service.docs.complete_item(state["tenant"], state["case_id"], "verify_result", result)
        if state["status"] in {"no_action", "rejected"}:
            service.docs.skip_item(
                state["tenant"],
                state["case_id"],
                "execute_action",
                result,
                "No external write was authorized or needed",
            )
        return {"status": status, "report": report}

    def store(state):
        if state["status"] == "blocked":
            return {}
        service.context.save(
            state["tenant"], state["case_id"], state["case_id"], state["request"], str(state["report"])
        )
        service.knowledge.ingest(
            state["tenant"], "case-log-" + state["case_id"], str(state["report"]), kind="operating_log"
        )
        return {}

    builder = StateGraph(State)
    for name, node in [
        ("assemble", assemble),
        ("plan", plan),
        ("investigate", research),
        ("draft", draft),
        ("evaluate", evaluate),
        ("upgrade_context", upgrade),
        ("approval", approval),
        ("execute", execute),
        ("finalize", finalize),
        ("store", store),
    ]:
        builder.add_node(name, node)
    for left, right in [
        (START, "assemble"),
        ("assemble", "plan"),
        ("plan", "investigate"),
        ("investigate", "draft"),
        ("draft", "evaluate"),
        ("upgrade_context", "draft"),
    ]:
        builder.add_edge(left, right)
    builder.add_conditional_edges(
        "evaluate",
        lambda s: (
            "approval" if s["status"] == "validated" else "upgrade_context" if s["status"] == "retry" else END
        ),
        ["approval", "upgrade_context", END],
    )
    builder.add_conditional_edges(
        "approval", lambda s: "execute" if s["status"] == "approved" else "finalize", ["execute", "finalize"]
    )
    builder.add_conditional_edges(
        "execute", lambda s: END if s["status"] == "blocked" else "finalize", [END, "finalize"]
    )
    builder.add_edge("finalize", "store")
    builder.add_edge("store", END)
    return builder.compile(checkpointer=checkpointer)
