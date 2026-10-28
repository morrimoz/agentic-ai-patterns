from patterns.evaluation import evaluate_proposal


def test_numeric_and_citation_verification_is_independent_of_model_judgement():
    facts = {"invoice_id": "INV-7", "overpayment_cents": 12000, "policy_limit_cents": 12000}
    proposal = {
        "action": "create_credit",
        "arguments": {"invoice_id": "INV-7", "amount_cents": 12000, "reason": "duplicate"},
        "citations": ["ledger", "policy"],
    }
    assert evaluate_proposal(proposal, facts, {"ledger", "policy"}).accepted
    bad = {**proposal, "citations": ["invented"]}
    assert not evaluate_proposal(bad, facts, {"ledger", "policy"}).accepted
    bad = {**proposal, "arguments": {**proposal["arguments"], "amount_cents": 12001}}
    assert not evaluate_proposal(bad, facts, {"ledger", "policy"}).accepted


def test_valid_citation_cannot_hide_missing_required_source():
    facts = {
        "invoice_id": "INV-7",
        "overpayment_cents": 12000,
        "policy_limit_cents": 12000,
        "required_evidence": ["ledger", "policy"],
    }
    proposal = {
        "action": "create_credit",
        "arguments": {"invoice_id": "INV-7", "amount_cents": 12000, "reason": "duplicate"},
        "citations": ["ledger"],
    }
    assert not evaluate_proposal(proposal, facts, {"ledger", "policy"}).accepted
