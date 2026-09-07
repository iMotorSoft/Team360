"""Atomic finding representation (§80, §23). Prepares, does not over-build."""

FINDING_STATUS = frozenset({"DISCOVERED", "AUDITED", "SAP_EVIDENCED", "EXECUTIVE_READY"})

# Unexplained-difference semantics (§23)
TOTAL_DIFFERENCE = "TOTAL_DIFFERENCE"
EXPLAINED_DIFFERENCE = "EXPLAINED_DIFFERENCE"
UNEXPLAINED_DIFFERENCE = "UNEXPLAINED_DIFFERENCE"


def build_finding(finding_type, severity, business_amount, evidence_refs, explanation,
                  status="DISCOVERED"):
    """Return a plain dict finding (no engine)."""
    if status not in FINDING_STATUS:
        raise ValueError(f"unknown status {status}")
    return {
        "finding_id": None,
        "finding_type": finding_type,
        "status": status,
        "severity": severity,
        "business_amount": business_amount,
        "evidence_refs": list(evidence_refs),
        "explanation": explanation,
    }