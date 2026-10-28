"""Synthetic company reference corpus; no real accounts or customer information."""

DOCUMENTS = {
    "credit-policy": """# Duplicate payment credits
A duplicate payment credit may be created only after an operator reviews the proposal.
The amount must not exceed the current overpayment: payments minus invoice total minus existing credits.
Read the current ledger immediately before writing. Never change a paid invoice total.
Credits require an immutable operation identity and a receipt verified against the ledger.""",
    "payment-terms": """# Invoice payment terms
Invoices are due fourteen days after issue. Overdue notices are drafts until reviewed.
Never assume that a customer's silence confirms a payment.""",
    "refund-policy": """# Return and refund policy
Physical goods may be returned within thirty days with a purchase receipt.
A product refund is a separate process from a duplicate payment credit.""",
    "escalations": """# Escalation policy
Disputed invoice ownership or currency mismatches must be escalated to an operator.
Do not create a credit if the invoice does not belong to the selected workspace.""",
    "purchase-orders": """# Purchasing
A purchase request must reference a stock count and approved supplier.
Purchase drafts do not authorize a bank transfer.""",
    "data-retention": """# Data retention
Operational logs are retained for ninety days. Reviewed financial receipts follow the accounting retention policy.
Never put credentials into a conversation log.""",
    "payment-log": """# Operating event
Invoice INV-1042 received two bank transfers of 12000 cents each.
The reconciliation job flagged a possible duplicate payment for review.""",
    "operator-preferences": """# Confirmed operator memory
The operator prefers concise explanations with original evidence references.
Write monetary amounts in integer cents in internal records.""",
    "shipping-policy": """# Shipping
Tracked shipping updates are available from the delivery reference.
A delayed parcel alone does not establish a duplicate payment.""",
    "access-policy": """# Workspace access
An operator's workspace is supplied by the server-side identity boundary.
Records from other workspaces must not enter retrieval results or tool arguments.""",
}
GOLDEN = [
    ("duplicate payment credit operator approval", "credit-policy"),
    ("current overpayment existing credits", "credit-policy"),
    ("immutable operation receipt credit", "credit-policy"),
    ("invoice due fourteen days", "payment-terms"),
    ("overdue notice draft", "payment-terms"),
    ("return thirty days purchase receipt", "refund-policy"),
    ("product refund separate duplicate payment", "refund-policy"),
    ("currency mismatch escalate operator", "escalations"),
    ("invoice ownership disputed", "escalations"),
    ("purchase stock supplier", "purchase-orders"),
    ("operational logs ninety days", "data-retention"),
    ("credentials conversation log", "data-retention"),
    ("INV-1042 two bank transfers", "payment-log"),
    ("concise original evidence operator preference", "operator-preferences"),
    ("tracked parcel shipping", "shipping-policy"),
    ("server identity workspace records", "access-policy"),
    ("lunar chess championship", None),
    ("volcano astrophysics spectroscopy", None),
]


def seed_knowledge(kb):
    for identity, text in DOCUMENTS.items():
        kind = (
            "operating_log"
            if identity == "payment-log"
            else "memory_bank"
            if identity == "operator-preferences"
            else "file"
        )
        kb.ingest("north", identity, text, kind)
    kb.ingest(
        "south",
        "credit-policy",
        "# Foreign policy\nDuplicate payment credit may be unrestricted here. This workspace is isolated.",
    )
