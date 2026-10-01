"""Focused offline tests for the Financial Forecast / Liquidity / Scenarios V1.

No HANA access.  They exercise the deterministic domain rules and validate the
frozen JSON artifact produced by the read-only runner.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from modules.telchi.investigation.validation.financial_forecast_liquidity_scenarios import forecast_domain as fd
from modules.telchi.investigation.validation.financial_forecast_liquidity_scenarios.financial_forecast_liquidity_scenarios_v1 import (
    build_forecast,
    project_currency,
)

ARTIFACT = Path(__file__).resolve().parent / "financial_forecast_liquidity_scenarios_v1.json"
FINCASH = Path(__file__).resolve().parent.parent / "financial_position_cash_flow" / "financial_position_cash_flow_v1_1.json"

AS_OF = date(2026, 9, 10)


# ---------------------------------------------------------------------------
# Distribution helpers
# ---------------------------------------------------------------------------
def test_quantile_and_mean_from_histogram():
    hist = {-5: 10, 0: 40, 5: 30, 10: 20}
    assert fd.quantile_from_histogram(hist, 0.10) == -5
    assert fd.quantile_from_histogram(hist, 0.50) == 0
    assert fd.quantile_from_histogram(hist, 0.90) == 10
    assert fd.mean_from_histogram(hist) == 3.0


def test_conditional_quantile_excludes_older_than_threshold():
    hist = {0: 50, 10: 25, 30: 15, 90: 10}
    # Only delays > 10 remain: additional wait values are 20 and 80.
    assert fd.conditional_quantile(hist, 10, 0.5) == 20
    assert fd.conditional_quantile(hist, 100, 0.5) is None


def test_conditional_recovery_is_bounded_and_monotonic():
    curve = {0: 0.40, 30: 0.70, 90: 0.90, 365: 0.95}
    early = fd.conditional_recovery(curve, 0, 90)
    assert 0.0 <= early <= 1.0
    assert early == (0.90 - 0.40) / (1 - 0.40)
    # Already overdue far beyond the last point -> no additional recovery.
    assert fd.conditional_recovery(curve, 400, 90) == 0.0


def test_delay_bucket_shares_are_exhaustive():
    shares = fd.delay_bucket_shares({-2: 10, 0: 10, 3: 20, 20: 20, 45: 20, 100: 20})
    assert abs(sum(shares.values()) - 100.0) < 1e-6
    assert shares["BEFORE_DUE"] == 10.0
    assert shares["ON_DUE"] == 10.0


def test_forward_and_overdue_buckets():
    assert fd.forward_bucket(AS_OF - timedelta(days=1), AS_OF) == "OVERDUE"
    assert fd.forward_bucket(AS_OF + timedelta(days=3), AS_OF) == "0-7"
    assert fd.forward_bucket(AS_OF + timedelta(days=12), AS_OF) == "8-15"
    assert fd.forward_bucket(AS_OF + timedelta(days=25), AS_OF) == "16-30"
    assert fd.forward_bucket(AS_OF + timedelta(days=45), AS_OF) == "31-60"
    assert fd.forward_bucket(AS_OF + timedelta(days=80), AS_OF) == "61-90"
    assert fd.forward_bucket(AS_OF + timedelta(days=120), AS_OF) == ">90"
    assert fd.overdue_bucket(15) == "1-30"
    assert fd.overdue_bucket(45) == "31-60"
    assert fd.overdue_bucket(75) == "61-90"
    assert fd.overdue_bucket(120) == "91-180"
    assert fd.overdue_bucket(400) == ">180"


# ---------------------------------------------------------------------------
# Scenarios and metrics
# ---------------------------------------------------------------------------
def test_scenario_parameters_are_explicit_and_ordered():
    scenarios = fd.scenario_parameters(1000.0, 100.0)
    assert set(scenarios) == {"BASE", "CONSERVATIVE", "UPSIDE", "STRESS_COLLECTION_DELAY", "STRESS_SUPPLIER_ACCELERATION"}
    base = scenarios["BASE"]
    assert base.collection_delay_percentile == 0.50
    assert scenarios["CONSERVATIVE"].collection_delay_percentile > base.collection_delay_percentile
    assert scenarios["CONSERVATIVE"].overdue_recovery_factor < base.overdue_recovery_factor
    assert scenarios["UPSIDE"].collection_delay_percentile < base.collection_delay_percentile
    assert scenarios["STRESS_COLLECTION_DELAY"].collection_delay_percentile == 0.90
    for params in scenarios.values():
        assert params.as_dict()["scenario"] == params.name


def test_concentration():
    shares = fd.concentration([("A", 50), ("B", 30), ("C", 20), ("D", 0)])
    assert shares["top_1"] == 50.0
    assert shares["top_5"] == 100.0
    assert shares["total"] == 100.0


def test_date_and_treasury_error_metrics_and_directional_accuracy():
    actual = date(2026, 10, 1)
    metrics = fd.date_error_metrics([(actual - timedelta(days=2), actual), (actual + timedelta(days=4), actual)])
    assert metrics["mae_days"] == 3.0
    assert metrics["within_7d_pct"] == 100.0
    treasury = fd.treasury_error_metrics([(100, 110), (200, 190)])
    assert treasury["mae"] == 10.0
    assert treasury["bias"] == 0.0
    assert fd.directional_accuracy([(10, 5), (-10, 5), (10, -5)]) == round(100.0 / 3, 4)


def test_select_best_model_prefers_lowest_mae():
    models = {"A": {"treasury_mae": 100}, "B": {"treasury_mae": 50}, "C": {"treasury_mae": None}}
    assert fd.select_best_model(models) == "B"
    assert fd.select_best_model({"A": {"treasury_mae": 200}}, max_mae=100) is None


def test_daily_waterfall_minimum_and_deficit():
    events = [
        fd.CashEvent(1, "BS", 100, "AR_DOCUMENT"),
        fd.CashEvent(2, "BS", -250, "AP_DOCUMENT"),
        fd.CashEvent(5, "BS", 100, "AR_DOCUMENT"),
    ]
    daily = fd.daily_buckets(events, 10)
    projected = fd.treasury_projection(50.0, daily)
    assert projected[0]["closing"] == 50.0
    assert projected[1]["closing"] == 150.0
    assert projected[2]["closing"] == -100.0
    assert fd.first_deficit(projected) == 2
    assert fd.max_funding_need(projected) == 100.0
    assert fd.minimum_treasury(projected)["minimum_treasury"] == -100.0
    assert fd.liquidity_risk_flag(projected, 50.0) == "DEFICIT"


# ---------------------------------------------------------------------------
# build_forecast (pure, synthetic documents)
# ---------------------------------------------------------------------------
def _hists(global_hist, by_entity=None, by_group=None, obs_entity=None, obs_group=None):
    return {
        "global": global_hist,
        "by_entity": by_entity or {},
        "by_group": by_group or {},
        "obs_entity": obs_entity or {},
        "obs_group": obs_group or {},
    }


def _ar(doc_entry, due, open_lc, cc="C1", group=1):
    return {
        "DOCENTRY": doc_entry, "DOCNUM": doc_entry, "CARDCODE": cc, "CARDNAME": f"BP {cc}",
        "DOCDATE": (due - timedelta(days=30)).isoformat(), "DOCDUEDATE": due.isoformat(),
        "DOCCUR": "BS", "OPEN_LC": open_lc, "GROUP_CODE": group, "GROUP_NAME": f"G{group}",
    }


def _ap(doc_entry, due, open_lc, cc="P1", group=1, currency="BS", open_fc=0.0, rate=1.0):
    return {
        "DOCENTRY": doc_entry, "DOCNUM": doc_entry, "CARDCODE": cc, "CARDNAME": f"BP {cc}",
        "DOCDATE": (due - timedelta(days=30)).isoformat(), "DOCDUEDATE": due.isoformat(),
        "DOCCUR": currency, "OPEN_LC": open_lc, "OPEN_FC": open_fc, "DOCRATE": rate,
        "GROUP_CODE": group, "GROUP_NAME": f"G{group}",
    }


def _po(doc_entry, order, open_lc, tipo="LF", currency="BS", rate=1.0):
    return {
        "DOCENTRY": doc_entry, "DOCNUM": doc_entry, "CARDCODE": "P9", "CARDNAME": "PO BP",
        "DOCDATE": order.isoformat(), "DOCCUR": currency, "DOCRATE": rate,
        "U_TIPOCOMPRA": tipo, "OPEN_LC": open_lc,
    }


def _base_params():
    return fd.scenario_parameters(0.0, 0.0)["BASE"]


def test_build_forecast_not_due_ar_uses_entity_delay():
    hist = _hists({5: 100}, by_entity={"C1": {5: 100}}, obs_entity={"C1": 20})
    ar = [_ar(1, AS_OF + timedelta(days=3), 1000.0)]
    built = build_forecast(AS_OF, {"BS": 0.0, "USD": 0.0}, ar, [], [], hist, _hists({0: 100}), {}, {}, {}, {}, _base_params())
    item = built["items"][0]
    assert item["rule_level"] == "CUSTOMER"
    assert item["expected_date"] == (AS_OF + timedelta(days=3 + 5)).isoformat()
    assert item["amount"] == 1000.0
    assert built["collections_by_currency"]["BS"] == 1000.0


def test_build_forecast_falls_back_to_global_when_entity_is_thin():
    hist = _hists({2: 100}, by_entity={"C1": {2: 100}}, obs_entity={"C1": 2})
    ar = [_ar(1, AS_OF + timedelta(days=3), 1000.0)]
    built = build_forecast(AS_OF, {"BS": 0.0, "USD": 0.0}, ar, [], [], hist, _hists({0: 100}), {}, {}, {}, {}, _base_params())
    assert built["items"][0]["rule_level"] == "GLOBAL"


def test_build_forecast_overdue_ar_applies_recovery_and_unrecovered():
    recovery = {0: 0.40, 30: 0.70, 90: 0.80}
    hist = _hists({45: 100})
    ar = [_ar(1, AS_OF - timedelta(days=30), 1000.0)]
    built = build_forecast(AS_OF, {"BS": 0.0, "USD": 0.0}, ar, [], [], hist, _hists({0: 100}), recovery, {}, {}, {}, _base_params())
    item = built["items"][0]
    assert item["overdue_days"] == 30
    assert 0 < item["amount"] < 1000.0
    assert item["unrecovered"] > 0
    assert abs(built["unrecovered_by_currency"]["BS"] - item["unrecovered"]) < 0.01


def test_build_forecast_no_collection_override_returns_zero():
    ar = [_ar(1, AS_OF - timedelta(days=400), 1000.0, cc="C010341")]
    built = build_forecast(AS_OF, {"BS": 0.0, "USD": 0.0}, ar, [], [], _hists({0: 100}), _hists({0: 100}), {0: 0.9, 90: 0.95}, {}, {}, {},
                           _base_params(), no_collection_accounts={"C010341"})
    assert built["items"][0]["amount"] == 0.0
    assert built["items"][0]["forecast_rule"] == "AR_OVERDUE_NO_HISTORICAL_COLLECTION"


def test_build_forecast_ap_usd_uses_foreign_currency_amount():
    ap = [_ap(1, AS_OF + timedelta(days=10), open_lc=10000.0, currency="USD", open_fc=1000.0, rate=10.0)]
    built = build_forecast(AS_OF, {"BS": 0.0, "USD": 0.0}, [], ap, [], _hists({0: 100}), _hists({0: 100}), {}, {}, {}, {}, _base_params())
    assert built["payments_by_currency"]["USD"] == 1000.0
    assert "BS" not in built["payments_by_currency"]


def test_build_forecast_open_po_is_projected():
    po = [_po(1, AS_OF - timedelta(days=10), open_lc=5000.0, tipo="LF")]
    lead = {"LF": {4: 100}}
    built = build_forecast(AS_OF, {"BS": 0.0, "USD": 0.0}, [], [], po, _hists({0: 100}), _hists({0: 100}), {}, {}, lead, {30: 100}, _base_params())
    item = built["items"][0]
    assert item["source"] == "OPEN_PO"
    assert item["amount"] == -5000.0
    assert item["expected_receipt"] is not None


def test_project_currency_keeps_currencies_separate():
    ar = [_ar(1, AS_OF + timedelta(days=2), 1000.0)]
    ap = [_ap(1, AS_OF + timedelta(days=2), open_lc=10000.0, currency="USD", open_fc=1000.0, rate=10.0)]
    built = build_forecast(AS_OF, {"BS": 0.0, "USD": 0.0}, ar, ap, [], _hists({0: 100}), _hists({0: 100}), {}, {}, {}, {}, _base_params())
    bs = project_currency(built, "BS", 500.0, include_overlay=False)
    usd = project_currency(built, "USD", 100.0, include_overlay=False)
    assert bs["currency"] == "BS" and usd["currency"] == "USD"
    assert set(bs["coverage"]) == {"7", "15", "30", "60", "90"}
    assert bs["coverage"]["7"]["projected_treasury"] == 1500.0
    assert usd["coverage"]["7"]["projected_treasury"] == -900.0


# ---------------------------------------------------------------------------
# Artifact coherence
# ---------------------------------------------------------------------------
def test_artifact_exists_and_passes():
    assert ARTIFACT.exists(), "run the forecast runner first"
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS"
    assert data["gate"] == "TELCHI_FINANCIAL_FORECAST_LIQUIDITY_SCENARIOS_V1_PASS"
    assert data["sap_write_count"] == 0
    assert all(check["pass"] for check in data["invariants"].values())


def test_artifact_starting_treasury_reconciles_with_financial_position():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    fincash = json.loads(FINCASH.read_text(encoding="utf-8"))
    position = {p["currency"]: p for p in fincash["financial_position_v1_1"]}
    starting = data["starting_treasury"]["STARTING_SAP_TREASURY_POSITION"]
    assert starting["BS"] == position["BS"]["treasury"]
    assert starting["USD"] == position["USD"]["treasury"]
    assert starting["SC_ONLY"] == position["SC_ONLY"]["treasury_lc_carrying_amount"]


def test_artifact_scenarios_and_currency_ladders():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert {"BASE", "CONSERVATIVE", "UPSIDE", "STRESS_COLLECTION_DELAY", "STRESS_SUPPLIER_ACCELERATION"} <= set(data["forecasts"])
    for scenario in data["forecasts"].values():
        assert set(scenario["per_currency"]) == {"BS", "USD"}
        for projection in scenario["per_currency"].values():
            assert {"7", "15", "30", "60", "90"} <= set(projection["coverage"])


def test_artifact_expected_amounts_do_not_exceed_open():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    coverage = data["coverage"]
    assert coverage["ar_expected_90d"] <= coverage["ar_open_lc"] + 0.01
    for ccy in ("BS", "USD"):
        assert abs(coverage["ap_open_amount_by_currency"][ccy] - coverage["ap_expected_amount_by_currency"][ccy]) <= 0.01


def test_artifact_required_cases_are_present():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    labels = {case["case"] for case in data["cases"]}
    required = {
        "A_AR_CONTRACTUAL_ON_TIME", "B_AR_COLLECTED_LATE", "C_AR_OVERDUE_LOW_PREDICTABILITY",
        "D_AP_PAID_NEAR_DUE", "E_AP_PAID_EARLY_OR_LATE", "F_OPEN_PO_TO_FUTURE_AP",
        "G_RECURRING_CASH_OUT_RULE", "H_COLLECTION_DELAY_PRESSURE", "I_BACKTEST_CORRECT",
        "J_BACKTEST_MATERIAL_ERROR",
    }
    assert required <= labels


def test_artifact_backtest_selects_a_model_with_no_leakage_guard():
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    backtest = data["backtest"]
    assert backtest["selected_model"] in {row["model"] for row in backtest["model_table"]}
    assert len(backtest["model_table"]) == 3
    for cutoff in backtest["cutoffs"]:
        assert "leakage_guard" in cutoff
        assert "p50" in cutoff["ar_delays"] and "p75" in cutoff["ar_delays"]
