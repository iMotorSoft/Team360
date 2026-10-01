"""Focused offline tests for Financial Debt / Interest / Financial Result V1.

No HANA access.  They exercise the deterministic domain rules and validate the
frozen JSON artifact produced by the read-only runner.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from modules.telchi.investigation.validation.financial_debt_and_financial_result.financial_debt_and_financial_result_v1 import (
    FINANCING_TARGET,
    build_amortization,
    build_v1_treatment,
    classify_debt_type,
    classify_financing_doc,
    expected_installment_count,
    financial_result_decomposition,
    horizon_total,
    next_due_on_day,
    pareto,
    parse_loan_ref,
)

ARTIFACT = Path(__file__).resolve().parent / "financial_debt_and_financial_result_v1.json"
AS_OF = date(2026, 9, 10)


# ---------------------------------------------------------------------------
# document classification
# ---------------------------------------------------------------------------
def test_principal_provision_beats_interest_keyword():
    comment = ("Provision d/Prestamo N.-10010818132 Bco.Banco FIE K. 487.000.- M/N Int. 5.99% "
               "pagos en cuotas mensuales Capital e Intereses (Int.+K)")
    assert classify_financing_doc(comment) == "PRINCIPAL"


def test_interest_provision_is_accrued_interest():
    assert classify_financing_doc("Provision de Intereses Ptmo. N.- 10002618651, Bs.- 3.865,13") == "ACCRUED_INTEREST"
    assert classify_financing_doc("Provision d/Interes Ope. N.-10011872517, Bs.- 1.913,58") == "ACCRUED_INTEREST"


def test_bank_fee_is_not_debt():
    assert classify_financing_doc("F. - 1021442 - Bs.-250 BMSC, Comision Bancaria por mantenimiento") == "BANK_FEE"
    assert classify_financing_doc("F-4647657 /BANCO UNION SA/Comision ACH. P/Transf.") == "BANK_FEE"


def test_debt_type_detection():
    assert classify_debt_type("Provision d/Prestamo Bajo LC. N.-10011872517") == "CREDIT_LINE"
    assert classify_debt_type("Provision d/Prestamo N.-6014236751") == "BANK_LOAN"
    assert classify_debt_type("Tarjeta de Credito 5302 mantenimiento", "Banco MSC") == "CARD_FINANCING"


# ---------------------------------------------------------------------------
# loan reference parsing
# ---------------------------------------------------------------------------
def test_parse_loan_ref_handles_contract_and_op_numbers():
    assert parse_loan_ref("S.I -Provision d/Prestamo N.-7018-11907 Bco.Banco Fie") == "7018-11907"
    assert parse_loan_ref("Pago de Ptmo N°10011872517 Capital Bs.-27.777,78") == "10011872517"
    assert parse_loan_ref("Pago de Ptmo. 10010818132 Capital Bs 8,116.67") == "10010818132"
    assert parse_loan_ref("Pago de Ptmo. Nº.- 1045533847 Capital") == "1045533847"


def test_parse_loan_ref_ignores_payment_document_numbers():
    assert parse_loan_ref("Cancelar entrada para número de pago 261501404") is None


# ---------------------------------------------------------------------------
# amortization
# ---------------------------------------------------------------------------
def test_expected_installment_count_rounds_to_nearest():
    assert expected_installment_count(300.0, 100.0) == 3
    assert expected_installment_count(890.0, 222.5) == 4
    assert expected_installment_count(0.0, 100.0) == 0


def test_next_due_on_day_rolls_forward():
    assert next_due_on_day(date(2026, 9, 10), 10) == date(2026, 9, 10)
    assert next_due_on_day(date(2026, 9, 10), 20) == date(2026, 9, 20)
    assert next_due_on_day(date(2026, 9, 21), 20) == date(2026, 10, 20)


def test_build_amortization_applies_residual_to_last_installment():
    loan = {"open_lc": 300.0}
    rows = build_amortization(loan, AS_OF, monthly_capital=100.0, monthly_interest=5.0, payment_day=10)
    assert [row["due_date"] for row in rows] == ["2026-09-10", "2026-10-10", "2026-11-10"]
    assert [row["capital"] for row in rows] == [100.0, 100.0, 100.0]
    assert rows[-1]["remaining_after"] == 0.0
    assert sum(row["capital"] for row in rows) == 300.0


def test_build_amortization_never_exceeds_principal():
    loan = {"open_lc": 250.0}
    rows = build_amortization(loan, AS_OF, monthly_capital=100.0, monthly_interest=0.0, payment_day=10)
    assert sum(row["capital"] for row in rows) == 200.0  # round(2.5) -> 2 installments


def test_horizon_total_respects_window():
    schedule = [
        {"due_date": "2026-09-20", "capital": 100.0, "interest": 10.0, "total": 110.0},
        {"due_date": "2026-11-20", "capital": 100.0, "interest": 10.0, "total": 110.0},
    ]
    assert horizon_total(schedule, AS_OF, 30, "capital") == 100.0
    assert horizon_total(schedule, AS_OF, 30, "total") == 110.0
    assert horizon_total(schedule, AS_OF, 90, "capital") == 200.0


# ---------------------------------------------------------------------------
# financial result
# ---------------------------------------------------------------------------
def test_financial_result_decomposition_matches_bspnl_semantics():
    flows = {
        "6020101": 300_000.0,
        "6020303": -10_000.0,
        "6020102": 3_850.40,
        "6020103": 38_819.70,
        "6020104": 4_957.89,
        "6020105": 1_090_697.04,
        "6020301": 14.37,
        "4210105": -1_452.79,
        "4210111": -26_280.50,
    }
    detail = financial_result_decomposition(flows)
    assert detail["INTEREST_EXPENSE"] == -290_000.0
    assert detail["BANK_CHARGES"] == round(-(3_850.40 + 38_819.70 + 4_957.89 + 1_090_697.04), 2)
    assert detail["FX_LOSS"] == -14.37
    assert detail["FX_GAIN"] == 1_452.79
    assert detail["INTEREST_INCOME"] == 26_280.50
    assert detail["OTHER_FINANCIAL"] == 0.0


def test_pareto_orders_by_absolute_amount():
    result = pareto({"A": 100.0, "B": -300.0, "C": 50.0})
    assert [item["key"] for item in result["top"]] == ["B", "A", "C"]


# ---------------------------------------------------------------------------
# V1 treatment
# ---------------------------------------------------------------------------
def _doc(doc_entry, due, amount, nature="PRINCIPAL"):
    return {"doc_entry": doc_entry, "bp_name": "BANCO X", "due_date": due, "open_lc": amount, "nature": nature}


def test_v1_treatment_concentrates_placeholder_dated_loans():
    docs = [
        _doc(1, "2022-03-31", 1_000_000.0),   # >90d overdue -> day 30
        _doc(2, "2026-09-20", 80_000.0),      # not due -> day 10
        _doc(3, "2027-10-11", 300_000.0),     # far future -> outside 90d
        _doc(4, "2026-08-31", 2_000.0, nature="ACCRUED_INTEREST"),
    ]
    v1 = build_v1_treatment(docs, AS_OF)
    assert v1["overdue_beyond_90d_documents"] == 1
    assert v1["overdue_beyond_90d_amount"] == 1_000_000.0
    assert v1["v1_30d"] == 1_082_000.0
    assert v1["v1_90d"] == 1_082_000.0


# ---------------------------------------------------------------------------
# artifact coherence
# ---------------------------------------------------------------------------
def test_artifact_exists_and_passes():
    assert ARTIFACT.exists(), "run the financial-debt runner first"
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS"
    assert data["gate"] == "TELCHI_FINANCIAL_DEBT_AND_FINANCIAL_RESULT_TRACEABILITY_V1_PASS"
    assert data["sap_write_count"] == 0
    assert all(check["pass"] for check in data["invariants"].values())
    assert all(data["gate_checks"].values())


def test_artifact_financing_universe_reproduced():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    fu = data["financing_universe"]
    assert abs(fu["total"] - FINANCING_TARGET) <= 0.01
    assert abs(fu["by_nature"]["PRINCIPAL"] + fu["by_nature"]["ACCRUED_INTEREST"] + fu["by_nature"]["BANK_FEE"] - fu["total"]) <= 0.01
    assert fu["by_nature"]["PRINCIPAL"] > fu["by_nature"]["ACCRUED_INTEREST"]
    assert {e["card_code"] for e in fu["by_entity"]} >= {"PL000212", "PL000288"}


def test_artifact_debt_is_currency_separated():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert data["currency"]["debt"] == "BS"
    assert all(doc["currency"] == "BS" for doc in data["financing_universe"]["documents"])


def test_artifact_financial_result_reconciles_to_frozen_target():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    fr = data["financial_result"]
    total = round(sum(fr["decomposition_frozen"].values()), 2)
    assert total == fr["frozen_target"]
    assert fr["frozen_target"] == -1_414_305.12
    assert round(fr["live_total"] - fr["post_cutoff_bridge"], 2) == fr["frozen_target"]


def test_artifact_schedule_is_heuristic_and_not_invented():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    schedule = data["financial_debt_schedule"]
    assert schedule["total_scheduled_capital"] > 0
    for loan in schedule["loans"]:
        assert loan["evidence"] == "HEURISTIC"
        assert loan["monthly_capital"] > 0
        assert sum(i["capital"] for i in loan["installments"]) <= loan["open_lc"] + 0.01
    assert data["maturity"]["schedule"] == "HEURISTIC"
    assert "DEGRADED" in data["maturity"]["classification"]


def test_artifact_real_cases_present():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    labels = {case["case"] for case in data["real_cases"]}
    required = {
        "A_PRINCIPAL_DOCUMENT", "B_PRINCIPAL_PAYMENT", "C_INTEREST_PAYMENT", "D_BANK_FEE",
        "E_FX_DEBT", "F_ENTITY_MULTI_DOC", "G_OVERDUE_NOT_ECONOMIC", "H_NEW_FINANCING",
    }
    assert required <= labels
    assert all(case["amount"] is not None for case in data["real_cases"])


def test_artifact_forecast_impact_uses_economic_schedule():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    v1 = data["forecast_v1_impact"]
    service = data["debt_service"]
    assert v1["overdue_beyond_90d_documents"] >= 1
    assert v1["v1_90d"] > service["90d"]["debt_service"]
    assert service["30d"]["debt_service"] <= service["90d"]["debt_service"] <= service["365d"]["debt_service"]
