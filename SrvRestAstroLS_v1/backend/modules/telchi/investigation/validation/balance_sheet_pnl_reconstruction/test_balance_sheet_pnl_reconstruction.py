"""Focused offline tests for the Balance Sheet / P&L reconstruction V1.

These tests do not touch HANA.  They exercise the classification contract and
validate the frozen JSON artifact produced by the read-only runner.
"""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.investigation.validation.balance_sheet_pnl_reconstruction.balance_sheet_pnl_reconstruction_v1 import (
    A,
    C,
    E,
    F,
    L,
    O,
    R,
    T,
    X,
    build_financials,
    classify_account,
    coverage,
    pnl_view,
    statement_view,
)

ARTIFACT = Path(__file__).resolve().parent / "balance_sheet_pnl_reconstruction_v1.json"


def _account(code: str, name: str, group: str) -> dict:
    return {"ACCTCODE": code, "ACCTNAME": name, "GROUPMASK": group}


def test_asset_subfamilies_are_differentiated():
    assert classify_account(_account("1110101", "Caja General Tesoreria MN", "1"))["bs_subgroup"] == "CASH"
    assert classify_account(_account("1111001", "BMSC Cta.Cte. 4010608078 MN", "1"))["bs_subgroup"] == "BANK"
    assert classify_account(_account("1120101", "Cuentas por cobrar clientes MN", "1"))["bs_subgroup"] == "ACCOUNTS_RECEIVABLE"
    assert classify_account(_account("1121501", "Crédito Fiscal IVA", "1"))["bs_subgroup"] == "TAX_RECEIVABLES"
    assert classify_account(_account("1121301", "Anticipo proveedores MN", "1"))["bs_subgroup"] == "ADVANCES"
    assert classify_account(_account("1130301", "Almacén Medicamentos 2A", "1"))["bs_subgroup"] == "INVENTORY"
    assert classify_account(_account("1240101", "Seguros pagados por anticipado", "1"))["bs_subgroup"] == "PREPAIDS"


def test_fixed_assets_and_depreciation_split():
    assert classify_account(_account("1210101", "Terrenos", "1"))["bs_subgroup"] == "FIXED_ASSETS"
    assert classify_account(_account("1210103", "Depreciación acumulada edificios", "1"))["bs_subgroup"] == "ACCUMULATED_DEPRECIATION"


def test_liability_subfamilies_are_differentiated():
    assert classify_account(_account("2110101", "Cuentas por pagar MN", "2"))["bs_subgroup"] == "ACCOUNTS_PAYABLE"
    assert classify_account(_account("2110301", "Anticipos de clientes M/N", "2"))["bs_subgroup"] == "CUSTOMER_ADVANCES"
    assert classify_account(_account("2120101", "Sueldos por pagar", "2"))["bs_subgroup"] == "PAYROLL_LIABILITIES"
    assert classify_account(_account("2140103", "IUE por pagar", "2"))["bs_subgroup"] == "TAX_LIABILITIES"
    assert classify_account(_account("2210101", "Préstamos bancarios", "2"))["bs_subgroup"] == "LONG_TERM_DEBT"


def test_equity_subfamilies():
    assert classify_account(_account("3110101", "Capital social", "3"))["bs_subgroup"] == "CAPITAL"
    assert classify_account(_account("3110401", "Reserva legal", "3"))["bs_subgroup"] == "RESERVES"
    assert classify_account(_account("3110501", "Resultados acumulados", "3"))["bs_subgroup"] == "RETAINED_EARNINGS"
    assert classify_account(_account("3110502", "Resultados del periodo", "3"))["bs_subgroup"] == "CURRENT_YEAR_RESULT"


def test_pl_classification_keeps_statements_separate():
    assert classify_account(_account("4110101", "Ventas producto terminado", "4"))["statement"] == R
    assert classify_account(_account("5110101", "Costos de ventas", "5"))["statement"] == C
    assert classify_account(_account("6110101", "Sueldos y salarios", "6"))["statement"] == X
    assert classify_account(_account("6020103", "Comisión tarjetas debito/credito", "6"))["statement"] == F
    assert classify_account(_account("6210105", "Comision tarjetas debito/credito", "6"))["statement"] == X
    assert classify_account(_account("6510101", "Diferencia de cambio", "6"))["statement"] == F
    assert classify_account(_account("6310103", "IUE", "6"))["statement"] == T
    assert classify_account(_account("6710101", "Gastos especiales", "6"))["statement"] == O


def test_balance_equation_on_synthetic_trial_balance():
    accounts = [
        _account("1110101", "Caja", "1"),
        _account("2110101", "CxP", "2"),
        _account("3110101", "Capital", "3"),
        _account("4110101", "Ventas", "4"),
    ]
    balances = {
        "1110101": {"BAL_ASOF": 100, "LINES": 1},
        "2110101": {"BAL_ASOF": -40, "LINES": 1},
        "3110101": {"BAL_ASOF": -50, "LINES": 1},
        "4110101": {"BAL_ASOF": -10, "LINES": 1},
    }
    build = build_financials(accounts, balances, [])
    view = statement_view(build, balances, "BAL_ASOF")
    assert view["total_assets"] == 100
    assert view["total_liabilities"] == 40
    assert view["balance_gap"] == 0.0


def test_pnl_view_uses_presentation_signs():
    accounts = [_account("4110101", "Ventas", "4"), _account("5110101", "Costo", "5"), _account("6110101", "Sueldo", "6")]
    balances = {
        "4110101": {"FLOW_2026YTD": -100, "BAL_ASOF": -100, "LINES": 1},
        "5110101": {"FLOW_2026YTD": 60, "BAL_ASOF": 60, "LINES": 1},
        "6110101": {"FLOW_2026YTD": 25, "BAL_ASOF": 25, "LINES": 1},
    }
    build = build_financials(accounts, balances, [])
    view = pnl_view(build, balances, "FLOW_2026YTD")
    assert view["revenue"] == 100
    assert view["cost_of_sales"] == 60
    assert view["gross_profit"] == 40
    assert view["net_income"] == 15


def test_artifact_balance_equation_and_coverage():
    assert ARTIFACT.exists(), "run the reconstruction runner first"
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    bs = data["balance_sheet"]["as_of"]
    assert abs(bs["balance_gap"]) <= 0.01
    assert abs(data["balance_sheet"]["system_currency_as_of"]["balance_gap"]) <= 0.01
    cov = data["account_classification"]["coverage"]
    assert cov["bs_classified_amount_pct"] == 100.0
    assert cov["pnl_classified_amount_pct"] == 100.0
    assert cov["unresolved_count"] == 0
    assert data["profit_and_loss"]["ytd_2026"]["net_income"] > 0


def test_artifact_invariants_and_gate_checks_all_pass():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS"
    assert data["sap_write_count"] == 0
    assert all(check["pass"] for check in data["invariants"].values())
    assert all(data["gate_checks"].values())


def test_artifact_has_all_real_cases():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    labels = {case["case"] for case in data["cases"]}
    assert {"A_SALE_REVENUE_AR_IVA", "B_COGS_INVENTORY", "C_PURCHASE_AP", "J_CLOSING_EQUITY"} <= labels
    assert all(case["trans_id"] for case in data["cases"])
    closing = next(c for c in data["cases"] if c["case"] == "J_CLOSING_EQUITY")
    assert closing["detail"]["header"]["TRANSTYPE"] == "-3"
