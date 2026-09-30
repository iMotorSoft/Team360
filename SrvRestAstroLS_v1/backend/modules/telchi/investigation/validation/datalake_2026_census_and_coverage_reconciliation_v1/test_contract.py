"""Focal contract tests for the 2026 census and coverage reconciliation gate.

These tests are pure: they never open SAP or DuckLake and never mutate data.
They lock the safety/closure contracts that make the live runner trustworthy.
"""
from modules.telchi.datalake.sql import assert_read_only_select

from modules.telchi.investigation.validation.datalake_2026_census_and_coverage_reconciliation_v1.runner import (
    COVERAGE_STATUSES,
    END_EXCLUSIVE,
    GATE,
    START,
    CUTOFF,
    _count_match,
    _quantity_match,
    _xor_add_fingerprint,
    classify_coverage,
    classify_priority,
    month_of,
    within_historical_range,
)


def test_gate_and_cutoff_are_fixed():
    assert GATE == "TELCHI_DATALAKE_2026_CENSUS_AND_COVERAGE_RECONCILIATION_V1"
    assert START == "2026-01-01"
    assert CUTOFF == "2026-09-15"
    assert END_EXCLUSIVE == "2026-09-16"


def test_coverage_vocabulary_is_exact():
    assert set(COVERAGE_STATUSES) == {
        "EXACT", "LOADED_NOT_VALIDATED", "NOT_LOADED",
        "NOT_APPLICABLE", "SOURCE_CHANGED", "MISMATCH",
    }


def test_not_loaded_is_never_mismatch():
    assert classify_coverage(loaded=False, comparable=True, exact=False, as_of_conflict=False) == "NOT_LOADED"
    assert classify_coverage(loaded=False, comparable=False, exact=False, as_of_conflict=True) == "NOT_LOADED"


def test_loaded_non_comparable_is_not_validated():
    assert classify_coverage(loaded=True, comparable=False, exact=False, as_of_conflict=False) == "LOADED_NOT_VALIDATED"


def test_source_changed_is_preferred_over_mismatch_when_as_of_conflicts():
    assert classify_coverage(loaded=True, comparable=True, exact=False, as_of_conflict=True) == "SOURCE_CHANGED"
    assert classify_coverage(loaded=True, comparable=True, exact=False, as_of_conflict=False) == "MISMATCH"


def test_exact_requires_loaded_comparable_and_equal():
    assert classify_coverage(loaded=True, comparable=True, exact=True, as_of_conflict=True) == "EXACT"


def test_priority_rule_is_deterministic():
    assert classify_priority(26_742) == "HIGH"
    assert classify_priority(10_000) == "HIGH"
    assert classify_priority(2_137) == "MEDIUM"
    assert classify_priority(100) == "MEDIUM"
    assert classify_priority(87) == "LOW"
    assert classify_priority(None) == "UNKNOWN"


def test_historical_range_enforces_both_bounds():
    assert within_historical_range("2026-01-01")
    assert within_historical_range("2026-09-15T23:59:59")
    assert not within_historical_range("2025-12-31")
    assert not within_historical_range("2026-09-16")
    assert not within_historical_range(None)


def test_month_of_ignores_time_component():
    assert month_of("2026-09-15T10:00:00") == "2026-09"
    assert month_of("2026-01-01") == "2026-01"
    assert month_of(None) is None


def test_count_and_quantity_match_helpers():
    assert _count_match(320_333, 320_333)
    assert not _count_match(320_369, 320_333)
    assert _quantity_match(1.5, 1.5)
    assert not _quantity_match(1.5, 1.51)
    assert not _quantity_match(None, 1.5)


def test_fingerprint_is_order_independent_and_change_sensitive():
    left = _xor_add_fingerprint(["a", "b", "c"])
    right = _xor_add_fingerprint(["c", "a", "b"])
    assert left == right
    assert left["count"] == 3
    changed = _xor_add_fingerprint(["a", "b", "d"])
    assert changed["xor_sha256"] != left["xor_sha256"]
    assert changed["add_sha256"] != left["add_sha256"]


def test_read_only_guard_rejects_sap_writes_and_select_star():
    for statement in (
        "INSERT INTO T VALUES (1)",
        "UPDATE T SET x=1",
        "DELETE FROM T",
        "MERGE INTO T USING S ON 1=1",
        "COPY T TO '/tmp/x.parquet'",
        "SELECT * FROM T",
    ):
        try:
            assert_read_only_select(statement)
        except ValueError:
            continue
        raise AssertionError(f"guard accepted forbidden statement: {statement}")
    assert assert_read_only_select('SELECT COUNT(*) FROM "TELCHI"."OINV"')