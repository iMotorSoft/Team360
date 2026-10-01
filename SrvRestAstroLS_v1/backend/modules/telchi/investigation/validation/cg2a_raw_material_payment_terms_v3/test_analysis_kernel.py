"""Focused regression tests for the CG2A payment-terms V3 closure."""
from datetime import date
import json
from pathlib import Path

from modules.telchi.investigation.validation.cg2a_raw_material_payment_terms_v3.analysis_kernel import (
    CONTADO_CONFIRMED,
    DELAYED_SETTLEMENT,
    IMMEDIATE_SETTLEMENT,
    cash_method_is_contado,
    commercial_classification,
    payment_method_grain_caveat,
    qr_from_method,
    same_day_settlement_is_contado_rule,
    settlement_behavior,
    transfer_method_can_be_contado,
    v1_v2_history_preserved,
)

EV = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V3")


def test_approved_contado_rule_requires_cash_term_and_same_due_date() -> None:
    day = date(2026, 1, 5)
    assert commercial_classification("COMMERCIAL_CASH_TERM", day, day) == CONTADO_CONFIRMED
    assert commercial_classification("COMMERCIAL_CASH_TERM", day, date(2026, 1, 6)) == "OTHER"
    assert commercial_classification("COMMERCIAL_CREDIT_TERM", day, day) == "CREDIT_CONFIRMED"


def test_commercial_contado_remains_contado_with_delayed_settlement() -> None:
    day = date(2026, 1, 5)
    assert commercial_classification("COMMERCIAL_CASH_TERM", day, day) == CONTADO_CONFIRMED
    assert settlement_behavior(day, date(2026, 1, 6), "FULLY_SETTLED") == DELAYED_SETTLEMENT


def test_cash_method_is_not_contado_rule() -> None:
    assert cash_method_is_contado() is False


def test_transfer_method_can_still_be_contado() -> None:
    assert transfer_method_can_be_contado() is True


def test_same_day_settlement_is_separate_from_contado() -> None:
    day = date(2026, 1, 5)
    assert same_day_settlement_is_contado_rule() is False
    assert settlement_behavior(day, day, "FULLY_SETTLED") == IMMEDIATE_SETTLEMENT
    assert commercial_classification("COMMERCIAL_CREDIT_TERM", day, day) == "CREDIT_CONFIRMED"


def test_payment_method_grain_caveat_is_mandatory() -> None:
    assert payment_method_grain_caveat() == "YES"


def test_qr_remains_unresolved() -> None:
    assert qr_from_method("TRANSFER") == "UNRESOLVED_SOURCE_EVIDENCE"
    assert qr_from_method("CASH") == "UNRESOLVED_SOURCE_EVIDENCE"


def test_v1_v2_history_is_preserved() -> None:
    assert v1_v2_history_preserved(
        "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V1_DEGRADED",
        "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2_DEGRADED",
    )


def test_persisted_rule_and_partitions() -> None:
    rule = json.loads((EV / "approved_contado_rule.json").read_text())
    commercial = json.loads((EV / "contado_classification.json").read_text())
    settlement = json.loads((EV / "settlement_behavior.json").read_text())
    assert rule["TELCHI_CONTADO_RULE_STATUS"] == "APPROVED"
    assert rule["CASH_METHOD_IS_CONTADO"] == "NO"
    assert rule["SAME_DAY_SETTLEMENT_IS_CONTADO_RULE"] == "NO"
    assert commercial["CONTADO_CONFIRMED_DOCS"] == 2136
    assert commercial["CONTADO_CONFIRMED_DOC_PCT"] == "100.00"
    assert commercial["CONTADO_RULE_PARTITION"] == "PASS"
    assert settlement["IMMEDIATE_SETTLEMENT_DOCS"] == 2134
    assert settlement["SAME_DAY_SETTLED_AMOUNT"] == "572573.310000"
    assert settlement["DELAYED_SETTLEMENT_DOCS"] == 2
    assert settlement["DELAYED_SETTLED_AMOUNT"] == "12772.250000"
    assert settlement["SETTLEMENT_BEHAVIOR_PARTITION"] == "PASS"


def test_v2_integrity_and_safety_controls_persisted() -> None:
    integrity = json.loads((EV / "v2_evidence_integrity.json").read_text())
    foundation = json.loads((EV / "foundation_precheck.json").read_text())
    assert integrity["V2_EVIDENCE_INTEGRITY"] == "PASS"
    assert foundation["FOUNDATION_CURRENT_BEFORE"] == "foundation_d222a203801cc84e9a14164d26aa67a0"
    assert foundation["SAP_ACCESSED"] == "NO"
    assert foundation["FOUNDATION_CANDIDATE_CREATED"] == "NO"
