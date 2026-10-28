"""A semantic judge can request context; arithmetic and citation guards remain authoritative."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: str
    amount_cents: int = Field(ge=0, strict=True)
    reason: str = Field(min_length=3, max_length=200)


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["create_credit", "no_action"]
    arguments: Arguments
    citations: list[str] = Field(min_length=1, max_length=12)
    summary: str = Field(default="", max_length=1000)


class Judge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    missing_evidence: list[str]
    retrieval_query: str = Field(max_length=500)


@dataclass
class Verdict:
    accepted: bool
    failures: list[str]


def evaluate_proposal(proposal, facts, evidence_ids):
    try:
        parsed = Proposal.model_validate(proposal)
    except ValueError:
        return Verdict(False, ["invalid_proposal_schema"])
    failures = []
    if not set(parsed.citations) <= set(evidence_ids):
        failures.append("unresolvable_citation")
    if not set(facts.get("required_evidence", [])) <= set(parsed.citations):
        failures.append("missing_required_source")
    if parsed.arguments.invoice_id != facts["invoice_id"]:
        failures.append("wrong_invoice")
    ceiling = min(facts["overpayment_cents"], facts["policy_limit_cents"])
    if parsed.action == "create_credit" and not 0 < parsed.arguments.amount_cents <= ceiling:
        failures.append("amount_exceeds_verified_bounds")
    if parsed.action == "no_action" and (
        parsed.arguments.amount_cents != 0 or facts["overpayment_cents"] > 0
    ):
        failures.append("unsupported_no_action")
    return Verdict(not failures, failures)
