from datetime import date

from modules.telchi.investigation.validation.cash_deposit_control.cash_deposit_control_v1 import (
    classify_document_row,
    fifo_match,
    lag_bucket,
    transfer_semantics,
)


def test_lag_buckets_are_exhaustive():
    assert lag_bucket(0) == "SAME_DAY"
    assert lag_bucket(1) == "D+1"
    assert lag_bucket(3) == "D+3"
    assert lag_bucket(7) == "D+4_7"
    assert lag_bucket(15) == "D+8_15"
    assert lag_bucket(30) == "D+16_30"
    assert lag_bucket(31) == "GT_30"
    assert lag_bucket(None) == "UNKNOWN"


def test_document_priority_excludes_canceled_and_keeps_deposit_internal():
    assert classify_document_row({"DOC_CANCELED": "Y"}, 2) == "CANCELED_EXCLUDED"
    assert classify_document_row({"DOC_CANCELED": "N", "ORCT_LINK": 1}, 1) == "ORCT_CASH_IN"
    assert classify_document_row({"DOC_CANCELED": "N", "ODPS_LINK": 1, "ALLOC_ACCOUNT": "1110101", "ACCOUNT": "1110101"}, 2) == "CASH_DEPOSIT"


def test_fifo_pool_preserves_accounts_and_reports_lag():
    result = fifo_match(
        {
            "collections": {
                "status": "PASS",
                "rows": [
                    {"ACCOUNT": "1110201", "CURRENCY": "BS", "DATE": date(2026, 9, 1), "COUNT": 2, "AMOUNT": 100},
                    {"ACCOUNT": "1110202", "CURRENCY": "BS", "DATE": date(2026, 9, 2), "COUNT": 1, "AMOUNT": 50},
                ],
            },
            "deposits": {
                "status": "PASS",
                "rows": [{"ACCOUNT": "1110101", "CURRENCY": "BS", "DATE": date(2026, 9, 3), "COUNT": 1, "AMOUNT": 120}],
            },
        }
    )
    assert result["summary"]["matched_amount"] == 120
    assert result["summary"]["unmatched_amount"] == 0
    assert result["matches"][0]["source_account"] == "1110201"
    assert result["matches"][0]["deposit_alloc_account"] == "1110101"
    assert result["matches"][0]["lag_bucket"] == "D+2"


def test_currency_transfer_semantics_never_hides_unresolved_amount():
    assert transfer_semantics(0, {"BS": 0}) == "EXACT_LC_MATCH"
    assert transfer_semantics(0, {"BS": -10, "##": 10}) == "SEMANTIC_CURRENCY_MISMATCH"
    assert transfer_semantics(-10, {"BS": -10}) == "UNRESOLVED"
