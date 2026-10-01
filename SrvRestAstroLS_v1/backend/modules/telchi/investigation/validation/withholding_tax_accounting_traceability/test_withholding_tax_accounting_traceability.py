from modules.telchi.investigation.validation.withholding_tax_accounting_traceability.withholding_tax_accounting_traceability_v1 import (
    classify_account,
    hierarchy,
    is_candidate,
    rollforward,
)


def test_configured_tax_account_is_not_called_withholding_from_name_alone():
    classification = classify_account(
        {"ACCTCODE": "2140108", "ACCTNAME": "Ret. IT por pagar", "GROUPMASK": 2},
        {"2140108"},
        {},
    )
    assert classification == ("WITHHOLDING_LIABILITY", "OWHT.Account + GroupMask=2", "CONFIGURED_ONLY")


def test_rc_iva_general_payable_is_not_vendor_wht():
    assert classify_account(
        {"ACCTCODE": "2140104", "ACCTNAME": "RC-IVA por Pagar", "GROUPMASK": 2},
        set(),
        {},
    )[0] == "TAX_LIABILITY"


def test_general_it_and_iue_accounts_remain_tax_liability():
    assert classify_account(
        {"ACCTCODE": "2140102", "ACCTNAME": "IT por pagar", "GROUPMASK": 2},
        set(),
        {},
    )[0] == "TAX_LIABILITY"
    assert classify_account(
        {"ACCTCODE": "2140103", "ACCTNAME": "IUE por pagar", "GROUPMASK": 2},
        set(),
        {},
    )[0] == "TAX_LIABILITY"


def test_judicial_retention_is_separate_from_vendor_wht():
    assert classify_account(
        {"ACCTCODE": "1240201", "ACCTNAME": "Retencion Judicial", "GROUPMASK": 1},
        set(),
        {},
    )[0] == "OTHER_FISCAL"


def test_inventory_retention_false_positive_is_not_fiscal_liability():
    assert classify_account(
        {"ACCTCODE": "1130205", "ACCTNAME": "Almacén Retención", "GROUPMASK": 1},
        set(),
        {},
    )[0] == "OTHER_FISCAL"


def test_hierarchy_path_is_stable_and_cycle_safe():
    accounts = [
        {"ACCTCODE": "2140000", "FATHERNUM": "2100000"},
        {"ACCTCODE": "2100000", "FATHERNUM": None},
        {"ACCTCODE": "2140108", "FATHERNUM": "2140000"},
    ]
    assert hierarchy(accounts)["2140108"] == "2100000 > 2140000 > 2140108"


def test_candidate_detection_uses_configured_account_or_fiscal_hierarchy():
    assert is_candidate({"ACCTCODE": "999", "ACCTNAME": "Cuenta puente", "GROUPMASK": 2}, {"999"}, "999")
    assert is_candidate({"ACCTCODE": "2140108", "ACCTNAME": "Cuenta", "GROUPMASK": 2}, set(), "2100000 > 2140000 > 2140108")
    assert not is_candidate({"ACCTCODE": "999", "ACCTNAME": "Ventas", "GROUPMASK": 4}, set(), "999")


def test_monthly_rollforward_matches_open_plus_credits_minus_debits():
    monthly = [
        {"ACCOUNT": "2140108", "YEAR": 2025, "MONTH": 1, "DEBIT": 0, "CREDIT": 100},
        {"ACCOUNT": "2140108", "YEAR": 2025, "MONTH": 2, "DEBIT": 25, "CREDIT": 0},
    ]
    result = rollforward(monthly, [{"ACCOUNT": "2140108", "CURRTOTAL": -75}])
    details = [r for r in result if "SUMMARY" not in r]
    summary = next(r["SUMMARY"] for r in result if "SUMMARY" in r)
    assert [r["CLOSING_BALANCE"] for r in details] == [-100, -75]
    assert summary["ROLLING_CLOSING_BALANCE"] == -75
    assert summary["OACT_RECONCILIATION_DELTA"] == 0
