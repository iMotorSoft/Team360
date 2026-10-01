from modules.telchi.investigation.validation.external_payroll_to_sap_reconciliation.external_payroll_to_sap_reconciliation_v1 import (
    classify_journal,
    extract_period,
    timing_metrics,
)


def header(memo: str, transtype: str = "30"):
    return {
        "MEMO": memo,
        "REF1": "",
        "REF2": "",
        "REF3": "",
        "BASEREF": "",
        "TRANSTYPE": transtype,
        "AUTOSTORNO": "N",
        "REFDATE": "2026-03-31",
    }


def test_period_extraction_requires_explicit_month_and_year():
    assert extract_period("Prov. planilla correspondiente al mes Marzo 2026") == "2026-03"
    assert extract_period("Pago de sueldos Abril22") == "2022-04"
    assert extract_period("Pago de sueldos") is None


def test_classification_separates_accrual_payment_and_reversal():
    classes = {"6010101": "SALARY_EXPENSE", "2120101": "SALARIES_PAYABLE"}
    accrual_lines = [
        {"ACCOUNT": "6010101", "DEBIT": 100, "CREDIT": 0, "LINEMEMO": ""},
        {"ACCOUNT": "2120101", "DEBIT": 0, "CREDIT": 100, "LINEMEMO": ""},
    ]
    payment_lines = [
        {"ACCOUNT": "2120101", "DEBIT": 100, "CREDIT": 0, "LINEMEMO": ""},
        {"ACCOUNT": "1111001", "DEBIT": 0, "CREDIT": 100, "LINEMEMO": ""},
    ]
    assert classify_journal(header("Prov. de planilla de sueldos Marzo 2026"), accrual_lines, classes)[0] == "PAYROLL_ACCRUAL"
    assert classify_journal(header("Pago de sueldos Marzo 2026", "46"), payment_lines, classes)[0] == "PAYROLL_PAYMENT"
    reversal = header("Prov. de planilla Marzo 2026 (Anulación)")
    reversal["AUTOSTORNO"] = "Y"
    assert classify_journal(reversal, accrual_lines, classes)[0] == "PAYROLL_REVERSAL"


def test_timing_metrics_uses_only_matching_memo_periods():
    base = header("Prov. de planilla de sueldos Marzo 2026")
    base["REFDATE"] = "2026-03-31"
    payment = header("Pago de sueldos Marzo 2026", "46")
    payment["REFDATE"] = "2026-04-02"
    classes = {"6010101": "SALARY_EXPENSE", "2120101": "SALARIES_PAYABLE"}
    accrual_lines = [
        {"ACCOUNT": "6010101", "DEBIT": 100, "CREDIT": 0, "LINEMEMO": ""},
        {"ACCOUNT": "2120101", "DEBIT": 0, "CREDIT": 100, "LINEMEMO": ""},
    ]
    payment_lines = [
        {"ACCOUNT": "2120101", "DEBIT": 100, "CREDIT": 0, "LINEMEMO": ""},
        {"ACCOUNT": "1111001", "DEBIT": 0, "CREDIT": 100, "LINEMEMO": ""},
    ]
    a_kind, a_signal = classify_journal(base, accrual_lines, classes)
    p_kind, p_signal = classify_journal(payment, payment_lines, classes)
    journals = [
        {"classification": a_kind, "signal": a_signal, "REFDATE": base["REFDATE"]},
        {"classification": p_kind, "signal": p_signal, "REFDATE": payment["REFDATE"]},
    ]
    result = timing_metrics(journals)
    assert result["matched_periods"] == 1
    assert result["median_days"] == 2
