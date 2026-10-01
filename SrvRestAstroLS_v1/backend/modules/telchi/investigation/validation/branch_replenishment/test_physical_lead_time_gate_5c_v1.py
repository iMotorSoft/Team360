from datetime import date, datetime

from modules.telchi.investigation.validation.branch_replenishment.physical_lead_time_gate_5c_v1 import (
    _delta_days,
    _select_real_cases,
    confidence_for_episode,
    percentile,
    sap_timestamp,
    stats,
)


def test_sap_timestamp_preserves_invalid_and_parses_hhmmss():
    assert sap_timestamp(date(2026, 1, 2), 93015) == datetime(2026, 1, 2, 9, 30, 15)
    assert sap_timestamp(None, 93015) is None
    assert sap_timestamp(date(2026, 1, 2), 999999) is None


def test_sap_doc_timestamp_parses_hhmm_not_hhmmss():
    from modules.telchi.investigation.validation.branch_replenishment.physical_lead_time_gate_5c_v1 import sap_doc_timestamp
    assert sap_doc_timestamp(date(2026, 1, 2), 930) == datetime(2026, 1, 2, 9, 30)
    assert sap_doc_timestamp(date(2026, 1, 2), 1802) == datetime(2026, 1, 2, 18, 2)


def test_percentile_is_interpolated_and_empty_is_unknown():
    assert percentile([0, 10, 20, 30], .75) == 22.5
    assert percentile([], .5) is None


def test_stats_separates_distribution_shape():
    result = stats([0, 1, 2, 3, 4])
    assert result["count"] == 5
    assert result["median"] == 2
    assert result["p90"] == 3.6
    assert result["max"] == 4


def test_delta_days_is_not_a_physical_label():
    assert _delta_days(datetime(2026, 1, 1), datetime(2026, 1, 2, 12)) == 1.5
    assert _delta_days(None, datetime(2026, 1, 2)) is None


def test_confidence_requires_physical_hitos_for_exact_or_strong():
    base = {"AccountingAvailabilityTimestamp": datetime(2026, 1, 2), "FirstSaleAfterTimestamp": datetime(2026, 1, 4), "physical_dispatch_timestamp": None, "physical_receipt_timestamp": None, "stock_available_timestamp": None}
    assert confidence_for_episode(base) == "PROXY"
    base["FirstSaleAfterTimestamp"] = None
    assert confidence_for_episode(base) == "UNKNOWN"
    base["AccountingAvailabilityTimestamp"] = None
    assert confidence_for_episode(base) == "UNKNOWN"


def test_case_selector_returns_at_most_twenty_without_duplicate_documents():
    episodes = [
        {"ItemCode": f"L{i:05d}", "RequestEvidence": "NONE", "TransitWhs": None, "StockoutContext": "NO_STOCKOUT_CONTEXT", "TransferDocEntry": i, "TransferLine": 0}
        for i in range(25)
    ]
    selected = _select_real_cases(episodes)
    assert len(selected) == 20
    assert len({(row["TransferDocEntry"], row["TransferLine"]) for row in selected}) == 20
