from datetime import date

from modules.telchi.investigation.validation.financial_position_cash_flow.financial_position_cash_flow_v1 import (
    TOLERANCE,
    add_flow,
    aggregate_cash_flow,
    classify_manual,
    classify_movement,
    due_bucket,
)


def test_due_bucket_is_forward_only_and_exhaustive():
    as_of = date(2026, 9, 9)
    assert due_bucket(date(2026, 9, 8), as_of) == "OVERDUE"
    assert due_bucket(as_of, as_of) == "0_7"
    assert due_bucket(date(2026, 9, 24), as_of) == "8_15"
    assert due_bucket(date(2026, 10, 9), as_of) == "16_30"
    assert due_bucket(date(2026, 11, 8), as_of) == "31_60"
    assert due_bucket(date(2026, 12, 8), as_of) == "61_90"
    assert due_bucket(date(2027, 1, 1), as_of) == ">90"
    assert due_bucket(None, as_of) == "UNRESOLVED"


def test_manual_classification_is_conservative():
    assert classify_manual("Comisión bancaria", "", -10) == "BANK_FEE"
    assert classify_manual("Interés banco", "", 10) == "INTEREST"
    assert classify_manual("Revaluación moneda", "", 10) == "FX"
    assert classify_manual("", "asiento de ajuste", -10) == "MANUAL_ADJUSTMENT"


def test_object_classification_keeps_deposit_internal():
    row = {"TRANSTYPE": "25", "NET": 100, "DOC_CANCELED": "N"}
    assert classify_movement(row, 2) == "INTERNAL_CASH_TO_BANK"
    row = {"TRANSTYPE": "24", "NET": 100, "DOC_CANCELED": "N"}
    assert classify_movement(row, 1) == "EXTERNAL_CUSTOMER_IN"
    row = {"TRANSTYPE": "46", "NET": -100, "DOC_CANCELED": "N", "CARDTYPE": "S"}
    assert classify_movement(row, 1, payment_has_ap=True) == "EXTERNAL_SUPPLIER_OUT"
    row = {"TRANSTYPE": "18", "NET": 100, "DOC_CANCELED": "N", "MEMO": "Provision de prestamo bancario"}
    assert classify_movement(row, 1) == "FINANCING_INFLOW"


def test_canceled_object_never_becomes_external_flow():
    row = {"TRANSTYPE": "24", "NET": 100, "DOC_CANCELED": "Y"}
    assert classify_movement(row, 1) == "CANCELED_EXCLUDED"


def test_add_flow_preserves_signed_other_effects():
    result = {}
    add_flow(result, "BANK_FEE", -25)
    add_flow(result, "FX", 10)
    add_flow(result, "UNRESOLVED", -5)
    assert result["external_out"] == 25
    assert result["accounting_effect"] == 5
    assert result["unresolved_amount"] == 5
    assert result["all_net"] == -20


def test_aggregate_cash_flow_reconciles_by_currency_without_conversion():
    movements = [
        {"ACCOUNT": "1110201", "CURRENCY": "BS", "NET": 100, "CLASSIFICATION": "EXTERNAL_CUSTOMER_IN", "PERIOD": "2026-09"},
        {"ACCOUNT": "1110201", "CURRENCY": "BS", "NET": -20, "CLASSIFICATION": "BANK_FEE", "PERIOD": "2026-09"},
        {"ACCOUNT": "1111001", "CURRENCY": "USD", "NET": 50, "CLASSIFICATION": "EXTERNAL_CUSTOMER_IN", "PERIOD": "2026-09"},
    ]
    positions = [
        {"account": "1110201", "currency": "BS", "classification": "CASH", "balance": 1000},
        {"account": "1111001", "currency": "USD", "classification": "BANK", "balance": 500},
    ]
    result = aggregate_cash_flow(movements, positions, date(2026, 9, 1))
    assert {x["currency"] for x in result["reconciliation"]} == {"BS", "USD"}
    assert all(abs(x["gap"]) <= TOLERANCE for x in result["reconciliation"])
    assert result["coverage"]["unresolved_amount"] == 0
    assert result["internal_transfer_net"] == 0
