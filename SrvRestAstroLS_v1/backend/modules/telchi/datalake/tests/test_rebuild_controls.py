from __future__ import annotations

from pathlib import Path

import pytest

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.rebuild import (
    ScopeKeySet,
    classify_tiny_files,
    purge_raw_scope,
    require_destructive_confirmation,
)


def test_sales_scope_uses_exact_source_keys() -> None:
    keys = ScopeKeySet("sales", (("100", "0"), ("100", "1")))
    assert keys.identity
    assert len(keys.keys) == 2


def test_scope_rejects_empty_or_duplicate_keys() -> None:
    with pytest.raises(ValueError):
        ScopeKeySet("sales", ())
    with pytest.raises(ValueError):
        ScopeKeySet("inventory", (("I1", "W1"), ("I1", "W1")))


def test_confirmation_requires_plan_and_explicit_flag() -> None:
    from modules.telchi.datalake.rebuild import DestructivePlan

    plan = DestructivePlan("ATOMIC_REBUILD", "inventory", "I1 x W1", ScopeKeySet("inventory", (("I1", "W1"),)), 3, ("inventory_balance",), {"inventory_balance": 1})
    with pytest.raises(PermissionError):
        require_destructive_confirmation(plan, confirm_destructive=False, plan_was_shown=True)
    with pytest.raises(PermissionError):
        require_destructive_confirmation(plan, confirm_destructive=True, plan_was_shown=False)
    require_destructive_confirmation(plan, confirm_destructive=True, plan_was_shown=True)


def test_tiny_file_classification_does_not_use_count_alone() -> None:
    assert classify_tiny_files([100_000, 120_000, 140_000])["status"] == "NO_TINY_FILE_PROBLEM"
    assert classify_tiny_files([305, 446, 3_774])["status"] == "SEVERE_TINY_FILE_PROBLEM"


def test_managed_filesystem_delete_is_rejected() -> None:
    connector = object.__new__(DuckLakeConnector)
    connector.data_path = Path("/tmp/telchi-ducklake-data")
    with pytest.raises(PermissionError):
        connector.reject_managed_filesystem_delete(connector.data_path / "atomic" / "x.parquet")


def test_raw_purge_requires_confirmation_before_unlink(tmp_path: Path) -> None:
    # The real gate root check is intentionally stricter than a generic temp
    # path; this verifies that an unapproved root cannot be purged at all.
    with pytest.raises(PermissionError):
        purge_raw_scope(tmp_path, domain="sales", segment_id="segment-1", confirm_destructive=False)
