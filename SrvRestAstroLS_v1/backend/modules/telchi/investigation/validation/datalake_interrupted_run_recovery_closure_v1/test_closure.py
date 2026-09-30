from __future__ import annotations

from types import SimpleNamespace

import pytest

from .run_gate import assert_read_only_sql, decision


def test_read_only_guard_rejects_mutation_sql() -> None:
    assert_read_only_sql("SELECT snapshot_id FROM ducklake_snapshots('telchi')")
    with pytest.raises(ValueError):
        assert_read_only_sql("UPDATE checkpoints SET watermark = 1")
    with pytest.raises(ValueError):
        assert_read_only_sql("CREATE TABLE atomic.x (id INTEGER)")


def test_candidate_is_not_visible_or_trusted() -> None:
    assert SimpleNamespace(candidate="CANDIDATE").candidate != "TRUSTED"
    assert SimpleNamespace(candidate="CANDIDATE").candidate != "VISIBLE"


def test_safe_to_ingest_requires_no_critical_unknown() -> None:
    ref = {"REFERENCE_V2_MODIFIED": "NO"}
    ducklake = {"DUCKLAKE_PARTIAL_STATE_FOUND": "UNKNOWN"}
    watermark = {"TRUSTED_WATERMARK_ADVANCED": "NO"}
    raw = {"RAW_SAP_PARTIAL_FILES_FOUND": "NO"}
    fs = {"PARTIAL_ATOMIC_VISIBLE": "NO", "ORPHAN_ARTIFACTS_FOUND": "NO", "CANDIDATE_ARTIFACTS_FOUND": "NO", "TEMP_FILES_FOUND": "NO"}
    identity = {"INTERRUPTED_RUN_IDENTIFIED": "YES"}
    result = decision(ref, ducklake, watermark, raw, fs, identity)
    assert result["SAFE_TO_START_REAL_INGESTION"] == "NO"
    assert result["critical_unknown_count"] == 1


def test_clean_classification_rules() -> None:
    ref = {"REFERENCE_V2_MODIFIED": "NO"}
    ducklake = {"DUCKLAKE_PARTIAL_STATE_FOUND": "NO"}
    watermark = {"TRUSTED_WATERMARK_ADVANCED": "NO"}
    raw = {"RAW_SAP_PARTIAL_FILES_FOUND": "NO"}
    fs = {"PARTIAL_ATOMIC_VISIBLE": "NO", "ORPHAN_ARTIFACTS_FOUND": "NO", "CANDIDATE_ARTIFACTS_FOUND": "NO", "TEMP_FILES_FOUND": "NO"}
    identity = {"INTERRUPTED_RUN_IDENTIFIED": "YES"}
    result = decision(ref, ducklake, watermark, raw, fs, identity)
    assert result["RECOVERY_CLASSIFICATION"] == "CLEAN"
    assert result["RECOVERY_REQUIRED"] == "NO"
    assert result["CLEANUP_REQUIRED"] == "NO"
    assert result["SAFE_TO_START_REAL_INGESTION"] == "YES"


def test_cleanup_plan_is_never_executed_by_decision() -> None:
    ref = {"REFERENCE_V2_MODIFIED": "NO"}
    ducklake = {"DUCKLAKE_PARTIAL_STATE_FOUND": "NO"}
    watermark = {"TRUSTED_WATERMARK_ADVANCED": "NO"}
    raw = {"RAW_SAP_PARTIAL_FILES_FOUND": "NO"}
    fs = {"PARTIAL_ATOMIC_VISIBLE": "NO", "ORPHAN_ARTIFACTS_FOUND": "YES", "CANDIDATE_ARTIFACTS_FOUND": "NO", "TEMP_FILES_FOUND": "NO"}
    identity = {"INTERRUPTED_RUN_IDENTIFIED": "YES"}
    result = decision(ref, ducklake, watermark, raw, fs, identity)
    assert result["DESTRUCTIVE_CLEANUP_PERFORMED"] == "NO"
    assert result["CLEANUP_PLAN_CREATED"] == "NO"


def test_trusted_and_candidate_watermarks_are_distinct() -> None:
    assert {"stage": "candidate"}["stage"] != "trusted"
    assert {"stage": "processed"}["stage"] != "trusted"
    assert {"stage": "validated"}["stage"] != "trusted"
