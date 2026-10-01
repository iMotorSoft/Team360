from modules.telchi.investigation.validation.ap_payables_payment_reconciliation.ap_payables_payment_reconciliation_v1 import (
    TOLERANCE,
    bucket_days,
    payment_method,
    settlement_classification,
)


def test_payment_method_classifies_single_and_mixed_tender():
    assert payment_method(100, 0, 0, 0) == "CASH"
    assert payment_method(0, 0, 100, 0) == "BANK_TRANSFER"
    assert payment_method(50, 0, 50, 0) == "MIXED"
    assert payment_method(0, 0, 0, 0) == "OTHER"


def test_payment_timing_buckets_are_exhaustive():
    assert bucket_days(-1) == "BEFORE_INVOICE"
    assert bucket_days(0) == "0_DAYS"
    assert bucket_days(7) == "1_7"
    assert bucket_days(15) == "8_15"
    assert bucket_days(30) == "16_30"
    assert bucket_days(60) == "31_60"
    assert bucket_days(91) == "OVER_90"
    assert bucket_days(None) == "UNKNOWN"


def test_settlement_classification_payment_only_and_open():
    assert settlement_classification({
        "GROSS_AP": 100, "CASH_SETTLED": 100, "CREDIT_NOTE_SETTLED": 0,
        "ADVANCE_SETTLED": 0, "JOURNAL_SETTLED": 0, "OTHER_SETTLED": 0,
        "OPEN_BALANCE": 0, "CANCELED": "N",
    }) == "PAYMENT_ONLY"
    assert settlement_classification({
        "GROSS_AP": 100, "CASH_SETTLED": 0, "CREDIT_NOTE_SETTLED": 0,
        "ADVANCE_SETTLED": 0, "JOURNAL_SETTLED": 0, "OTHER_SETTLED": 0,
        "OPEN_BALANCE": 100, "CANCELED": "N",
    }) == "OPEN"


def test_settlement_classification_does_not_call_non_cash_retention():
    result = settlement_classification({
        "GROSS_AP": 100, "CASH_SETTLED": 95, "CREDIT_NOTE_SETTLED": 0,
        "ADVANCE_SETTLED": 0, "JOURNAL_SETTLED": 0, "OTHER_SETTLED": 0,
        "OPEN_BALANCE": 5, "CANCELED": "N",
    })
    assert result == "OTHER"
    assert TOLERANCE == 0.01


def test_canceled_document_is_separate_from_settlement():
    assert settlement_classification({
        "GROSS_AP": 100, "CASH_SETTLED": 100, "CREDIT_NOTE_SETTLED": 0,
        "ADVANCE_SETTLED": 0, "JOURNAL_SETTLED": 0, "OTHER_SETTLED": 0,
        "OPEN_BALANCE": 0, "CANCELED": "Y",
    }) == "CANCELED_DOCUMENT"
