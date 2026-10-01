from __future__ import annotations

from datetime import datetime

from modules.telchi.investigation.validation.order_delivery_efficiency.order_to_warehouse_exit_baseline_v1 import (
    CANONICAL_ACTIVE,
    CANONICAL_COMPLETE_EXIT,
    CANONICAL_FIRST_EXIT,
    CANONICAL_NO_EXIT,
    CANONICAL_PARTIAL,
    _calendar_class,
    _duration,
    _quantile,
    _stats,
)


def test_gate4_contract_counts_are_frozen() -> None:
    assert (CANONICAL_ACTIVE, CANONICAL_FIRST_EXIT, CANONICAL_COMPLETE_EXIT) == (2842, 2631, 2561)
    assert CANONICAL_PARTIAL == 70
    assert CANONICAL_NO_EXIT == 211
    assert CANONICAL_COMPLETE_EXIT + CANONICAL_PARTIAL + CANONICAL_NO_EXIT == CANONICAL_ACTIVE


def test_elapsed_time_uses_seconds_and_keeps_negative_invalid() -> None:
    start = datetime(2026, 9, 1, 10, 0, 0)
    end = datetime(2026, 9, 1, 10, 0, 30)
    assert _duration(start, end) == (0.5, "VALID")
    assert _duration(end, start)[1] == "INVALID_TIMESTAMP"


def test_percentiles_are_deterministic() -> None:
    values = [0.0, 10.0, 20.0, 30.0]
    assert _quantile(values, 0.5) == 15.0
    assert _stats(values)["N"] == 4
    assert _stats(values)["median"] == 15.0


def test_calendar_day_is_descriptive_not_elapsed_time() -> None:
    start = datetime(2026, 9, 1, 23, 50)
    end = datetime(2026, 9, 2, 0, 20)
    assert _calendar_class(start, end) == "NEXT_CALENDAR_DAY"
    assert _duration(start, end) == (30.0, "VALID")
