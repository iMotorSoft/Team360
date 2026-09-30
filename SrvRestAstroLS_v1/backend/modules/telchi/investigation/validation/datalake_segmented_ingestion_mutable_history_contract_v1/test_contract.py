from __future__ import annotations

import csv
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
INVESTIGATION = HERE.parents[1]
ARCHITECTURE = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ARCHITECTURE_V1.md"
ADR_INDEX = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ADR_INDEX_V1.md"
PRIOR_GATE = INVESTIGATION / "validation" / "datalake_ingestion_modes_and_resource_guards_contract_v1"
CURRENT_STATE = HERE / "current_state.json"
SUMMARY = HERE / "summary.json"


def rows(name: str) -> list[dict[str, str]]:
    with (HERE / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_two_modes_and_all_heavy_work_is_segmented() -> None:
    modes = {row["mode"]: row for row in rows("../datalake_ingestion_modes_and_resource_guards_contract_v1/ingestion_modes_contract.csv")}
    assert set(modes) == {"INITIAL_INGESTION", "INCREMENTAL_UPDATE"}
    assert modes["INITIAL_INGESTION"]["execution_unit"] == "BOUNDED_SEGMENT"
    assert modes["INCREMENTAL_UPDATE"]["execution_unit"] == "BOUNDED_MICRO_BATCH"
    assert all(row["monolithic_allowed"] == "NO" for row in rows("segmented_execution_contract.csv"))
    execution = {row["execution_type"]: row for row in rows("segmented_execution_contract.csv")}
    for operation in ("RECONCILIATION", "REBUILD", "DIRTY_REPROCESSING", "BACKFILL"):
        assert execution[operation]["execution_unit"] == "BOUNDED_SEGMENT"
        assert execution[operation]["checkpoint_required"] == "YES"
        assert execution[operation]["resource_guards_required"] == "YES"
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "LONG_RUNNING_MONOLITHIC_LOADS_ALLOWED=NO",
        "INITIAL_INGESTION` usa `BOUNDED_SEGMENT",
        "INCREMENTAL_UPDATE` usa `BOUNDED_MICRO_BATCH",
        "COVERAGE_MAP_REQUIRED=YES",
        "S1` y `S2` pasan y `S3` falla",
        "SEGMENT_SIZE_CONFIGURABLE=YES",
        "SEGMENT_SIZE_ADAPTIVE=YES",
    ):
        assert phrase in architecture


def test_mutable_history_separates_times_and_watermarks() -> None:
    mutable = rows("mutable_history_contract.csv")
    assert len(mutable) == 1
    contract = mutable[0]
    assert contract["historical_mutability_allowed"] == "YES"
    assert contract["change_detection_required"] == "YES"
    assert contract["old_period_change_supported"] == "YES"
    assert contract["dirty_scope_supported"] == "YES"
    assert contract["full_period_reload_default"] == "NO"
    signals = {row["signal"]: row for row in rows("change_detection_contract.csv")}
    assert signals["DOC_DATE"]["watermark_policy"] == "BUSINESS_DATE_ONLY_WATERMARK=FORBIDDEN"
    assert signals["SOURCE_UPDATE_DATETIME"]["old_period_supported"] == "YES"
    assert signals["BOUNDED_LOOKBACK"]["old_period_supported"] == "YES"
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "HISTORICAL_COVERAGE_MAY_CHANGE_AFTER_INITIAL_INGESTION",
        "Business time",
        "Change time",
        "business_date != source_changed_at",
        "BUSINESS_DATE_ONLY_WATERMARK=FORBIDDEN",
        "COVERAGE` (períodos representados) y `CHANGE_WATERMARK",
        "CLOSED_FOREVER",
    ):
        assert phrase in architecture


def test_dirty_scope_is_focal_and_period_is_not_default_reload() -> None:
    dirty = {row["scope_type"]: row for row in rows("dirty_scope_contract.csv")}
    assert {"DOCUMENT", "DOCUMENT_LINES", "ITEM_WAREHOUSE", "TRANSACTION_RANGE", "CUSTOMER", "BUSINESS_DAY_RANGE", "MONTH"} == set(dirty)
    assert dirty["DOCUMENT"]["reprocess_scope"] == "document and authoritative lines"
    assert dirty["ITEM_WAREHOUSE"]["reprocess_scope"] == "affected ItemCode×Warehouse"
    assert dirty["MONTH"]["can_escalate_to_period"] == "NO"
    assert all(row["can_escalate_to_period"] == "YES" for name, row in dirty.items() if name != "MONTH")
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "DIRTY_SCOPE",
        "DIRTY_PERIOD",
        "HISTORICAL_CHANGE_DETECTED DOES NOT AUTOMATICALLY REQUIRE FULL_MONTH_RELOAD",
        "changed object/key → bounded authoritative reread",
        "período completo cuando la semántica de la fuente",
    ):
        assert phrase in architecture


def test_coverage_states_distinguish_scope_from_trust_and_fail_closed() -> None:
    coverage = {row["state"]: row for row in rows("coverage_state_contract.csv")}
    assert coverage["TRUSTED"]["trusted"] == "YES"
    assert coverage["TRUSTED"]["can_advance_coverage"] == "YES"
    for state in ("DIRTY", "RECONCILING", "DIVERGED"):
        assert coverage[state]["trusted"] == "NO"
        assert coverage[state]["requires_reconciliation"] == "YES"
        assert coverage[state]["can_advance_coverage"] == "NO"
    assert coverage["DIRTY"]["can_be_served"] == "LAST_TRUSTED_ONLY"
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "TRUSTED → DIRTY → RECONCILING → TRUSTED",
        "DIRTY` describe estado de cobertura/scope",
        "candidate data",
        "no publica candidate data",
        "WATERMARK_CAN_SKIP_DIRTY_GAP=NO",
    ):
        assert phrase in architecture


def test_reconciliation_hana_guards_and_physical_layout() -> None:
    segment = {row["execution_type"]: row for row in rows("segmented_execution_contract.csv")}
    assert segment["RECONCILIATION"]["execution_unit"] == "BOUNDED_SEGMENT"
    assert segment["REBUILD"]["execution_unit"] == "BOUNDED_SEGMENT"
    prior_reconciliation = rows("../datalake_ingestion_modes_and_resource_guards_contract_v1/reconciliation_contract.csv")
    assert all(row["segmented_required"] == "YES" for row in prior_reconciliation)
    prior_resources = rows("../datalake_ingestion_modes_and_resource_guards_contract_v1/resource_guard_contract.csv")
    assert all(row["per_segment_enforced"] == "YES" for row in prior_resources)
    prior_hana = {row["operation_type"]: row for row in rows("../datalake_ingestion_modes_and_resource_guards_contract_v1/hana_load_budget_contract.csv")}
    assert prior_hana["CHAT_REQUEST"]["allowed"] == "NO"
    assert prior_hana["RECURRENT_FULL_SCAN_POLLING"]["allowed"] == "NO"
    assert all(prior_hana[key]["segment_required"] == "YES" for key in ("INITIAL_BOUNDED_WINDOW", "INCREMENTAL_CHANGE_DETECTION", "FAST_FOCAL_RECONCILIATION", "PERIODIC_AUTHORITATIVE_RECONCILIATION"))
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "HANA_LOAD_MINIMIZATION=MANDATORY",
        "HANA_FULL_SCAN_POLLING_ALLOWED=NO",
        "HANA_QUERY_ON_USER_REQUEST=NO",
        "SEGMENT != PARQUET FILE",
        "Atomic continúa bajo `DUCKLAKE_MANAGED`",
        "## 34. Historical reconciliation",
    ):
        assert phrase in architecture


def test_adr_extension_and_principles_are_registered() -> None:
    adr_text = ADR_INDEX.read_text(encoding="utf-8")
    ids = re.findall(r"^## (ADR-\d{3}) — ", adr_text, re.MULTILINE)
    assert len(ids) == 38
    assert ids[-4:] == ["ADR-035", "ADR-036", "ADR-037", "ADR-038"]
    for number in range(35, 39):
        section_start = adr_text.index(f"## ADR-{number:03d} —")
        assert "| Status | ACCEPTED |" in adr_text[section_start:]
        assert "TELCHI_DATALAKE_SEGMENTED_INGESTION_MUTABLE_HISTORY_CONTRACT_V1_PASS" in adr_text[section_start:]
    principles = rows("../datalake_ingestion_modes_and_resource_guards_contract_v1/architecture_principles.csv")
    assert {row["principle_id"] for row in principles[-2:]} == {"P-023", "P-024"}
    assert {row["name"] for row in principles[-2:]} == {"SEGMENT BEFORE SCALE", "TRUST CAN BE REVALIDATED"}


def test_gate_is_documental_only_and_has_no_data_side_effects() -> None:
    current = json.loads(CURRENT_STATE.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert current["result"].endswith("_PASS")
    assert summary["result"].endswith("_PASS")
    assert current["runtime_implemented"] is False
    assert current["scheduler_implemented"] is False
    assert current["sap_accessed"] is False
    assert current["sap_write_count"] == 0
    assert current["postgres_modified"] is False
    assert current["ducklake_modified"] is False
    assert current["data_files_modified"] == 0
    assert current["raw_files_modified"] == 0
    assert current["reference_files_modified"] == 0
    assert current["atomic_data_files_modified"] == 0
    assert current["stop_and_review"] is True
    assert summary["mode_count"] == 2
    assert not list(HERE.glob("*.parquet"))
    assert not list(HERE.glob("*.parq"))


def test_no_obvious_secret_values_in_contract_artifacts() -> None:
    paths = list(HERE.glob("*.csv")) + [CURRENT_STATE, SUMMARY, ARCHITECTURE, ADR_INDEX]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for pattern in (
        r"(?i)(?:password|passwd|pwd|token|api[_-]?key)\s*[:=]\s*[^\s<]+",
        r"(?i)(?:postgres|postgresql|hana|sap)://[^\s/]+:[^\s@]+@",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    ):
        assert re.search(pattern, combined) is None, pattern
