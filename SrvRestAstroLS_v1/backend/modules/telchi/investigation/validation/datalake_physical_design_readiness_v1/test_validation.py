from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_exactly_eight_original_blocking_gaps_are_reviewed_once() -> None:
    review = rows("blocking_gaps_review.csv")
    assert len(review) == 8
    assert {row["gap_id"] for row in review} == {
        "GAP-001", "GAP-002", "GAP-003", "GAP-004",
        "GAP-010", "GAP-012", "GAP-017", "GAP-018",
    }
    allowed = {
        "RESOLVED", "RESOLVED_BY_TARGETED_VALIDATION",
        "DEFERRED_WITH_SAFE_CONTRACT", "STILL_BLOCKING",
    }
    assert all(row["final_status"] in allowed for row in review)


def test_every_deferred_gap_has_an_explicit_safe_contract() -> None:
    contracts = rows("gap_resolution_contracts.csv")
    deferred = [row for row in contracts if row["final_status"] == "DEFERRED_WITH_SAFE_CONTRACT"]
    assert len(deferred) == 6
    assert all(row["safe_contract"].strip() for row in deferred)
    assert all(row["impact_on_physical_design"].strip() for row in contracts)


def test_readiness_is_binary_and_all_areas_are_ready() -> None:
    matrix = rows("readiness_matrix.csv")
    assert len(matrix) == 8
    assert {row["status"] for row in matrix} <= {"READY", "BLOCKED"}
    assert all(row["status"] == "READY" for row in matrix)
    assert {row["area"] for row in matrix} == {
        "Canonical grain", "Identity", "Temporal model", "Snapshot policy",
        "Legacy ↔ SAP", "Lineage", "Security scope", "Atomic vs Business",
    }


def test_no_sap_validation_or_write_was_performed() -> None:
    validations = rows("sap_targeted_validations.csv")
    summary = json.loads((ROOT / "summary.json").read_text(encoding="utf-8"))
    assert validations == []
    assert summary["sap_accessed"] is False
    assert summary["sap_access_purpose"] == "NONE"
    assert summary["sap_targeted_validations"] == 0
    assert summary["sap_write_count"] == 0


def test_gate_is_ready_only_with_zero_still_blocking() -> None:
    summary = json.loads((ROOT / "summary.json").read_text(encoding="utf-8"))
    assert summary["blocking_gaps_initial"] == 8
    assert summary["resolved"] == 2
    assert summary["resolved_by_targeted_validation"] == 0
    assert summary["deferred_with_safe_contract"] == 6
    assert summary["still_blocking"] == 0
    assert summary["physical_design_ready"] is True
    assert summary["gate"] == "TELCHI_DATALAKE_PHYSICAL_DESIGN_READINESS_V1_PASS"


def test_no_physical_layout_or_parquet_was_created() -> None:
    summary = json.loads((ROOT / "summary.json").read_text(encoding="utf-8"))
    assert summary["production_parquets_created"] == 0
    assert summary["datalake_physical_layout_created"] == 0
    assert not list(ROOT.glob("*.parquet"))
    assert not list(ROOT.glob("*.parq"))
