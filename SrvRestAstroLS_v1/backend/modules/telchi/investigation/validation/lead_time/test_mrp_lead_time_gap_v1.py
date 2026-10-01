"""Pure tests for TELCHI_MRP_LEAD_TIME_GAP_V1 classification helpers."""
from __future__ import annotations

from modules.telchi.investigation.validation.lead_time.mrp_lead_time_gap_v1 import (
    classify,
    confidence,
    nearest_rank,
    stats,
)


def test_nearest_rank_percentiles_are_deterministic() -> None:
    values = [0, 2, 4, 10, 20]
    assert nearest_rank(values, 0.25) == 2
    assert nearest_rank(values, 0.50) == 4
    assert nearest_rank(values, 0.90) == 20
    assert nearest_rank(values, 0.95) == 20


def test_stats_include_complete_diagnostic_percentiles_and_iqr() -> None:
    result = stats([0, 2, 4, 10, 20])
    assert result["n"] == 5
    assert result["median"] == 4
    assert result["p90"] == 20
    assert result["p95"] == 20
    assert result["iqr"] == 8


def test_missing_and_zero_parameter_are_not_silently_equated() -> None:
    assert classify(None, {"n": 5, "median": 4, "p90": 10})[:2] == ("SAP_LEADTIME_MISSING", "SAP_NOT_POPULATED")
    assert classify(0, {"n": 5, "median": 4, "p90": 10})[:2] == ("SAP_LEADTIME_ZERO", "UNKNOWN")


def test_insufficient_history_excludes_gap_inference() -> None:
    assert classify(2, {"n": 2, "median": 4, "p90": 10})[:2] == ("INSUFFICIENT_HISTORY", "UNKNOWN")


def test_gap_bands_use_median_and_p90_without_exact_equality_bug() -> None:
    observed = {"n": 10, "median": 4, "p90": 10}
    assert classify(3, observed)[:2] == ("SAP_LT_BELOW_MEDIAN", "SAP_MISCONFIGURED")
    assert classify(4, observed)[:2] == ("SAP_LT_BETWEEN_MEDIAN_AND_P90", "NO_GAP_CONFIRMED")
    assert classify(9, observed)[:2] == ("SAP_LT_BETWEEN_MEDIAN_AND_P90", "NO_GAP_CONFIRMED")
    assert classify(10, observed)[:2] == ("SAP_LT_AT_OR_ABOVE_P90", "NO_GAP_CONFIRMED")
    assert classify(20, observed)[:2] == ("SAP_LT_AT_OR_ABOVE_P90", "SAP_MISCONFIGURED")


def test_confidence_thresholds_match_gate_policy() -> None:
    assert confidence(3) == "LOW_CONFIDENCE"
    assert confidence(5) == "MEDIUM_CONFIDENCE"
    assert confidence(10) == "HIGH_CONFIDENCE"
