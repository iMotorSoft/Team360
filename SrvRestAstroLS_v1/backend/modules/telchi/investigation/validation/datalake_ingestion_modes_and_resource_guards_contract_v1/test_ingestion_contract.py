from __future__ import annotations

import csv
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
INVESTIGATION = HERE.parents[1]
ARCHITECTURE = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ARCHITECTURE_V1.md"
ADR_INDEX = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ADR_INDEX_V1.md"
SUMMARY = HERE / "summary.json"
CURRENT_STATE = HERE / "current_state.json"


def rows(name: str) -> list[dict[str, str]]:
    with (HERE / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_exactly_two_ingestion_modes_and_shared_canonical_contract() -> None:
    modes = rows("ingestion_modes_contract.csv")
    assert {row["mode"] for row in modes} == {"INITIAL_INGESTION", "INCREMENTAL_UPDATE"}
    assert len(modes) == 2
    assert all(row["default_work_unit"] for row in modes)
    assert all(row["uses_watermark"] == "YES" for row in modes)
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "exactamente dos modos principales",
        "mismo schema canónico",
        "mismo `ATOMIC_ID`",
        "MONTH` es unidad de trabajo",
        "MICRO_BATCH` es unidad lógica",
        "`RECONCILIATION` es un mecanismo de control interno del UPDATE",
    ):
        assert phrase in architecture
    assert "RECONCILIATION,RECONCILIATION" not in "\n".join(
        ",".join(row.values()) for row in modes
    )


def test_fail_closed_trust_states_and_as_of_contract() -> None:
    trust = {row["trust_state"]: row for row in rows("data_trust_contract.csv")}
    assert set(trust) == {
        "AUTHORITATIVE_SYNCED",
        "AUTHORITATIVE_LAGGING",
        "VALIDATED_DERIVED",
        "STALE",
        "DIVERGED",
    }
    assert trust["DIVERGED"]["can_publish"] == "NO"
    assert trust["DIVERGED"]["can_serve"] == "NO"
    assert trust["DIVERGED"]["watermark_can_advance"] == "NO"
    assert trust["AUTHORITATIVE_SYNCED"]["can_serve"] == "YES"
    assert trust["AUTHORITATIVE_LAGGING"]["requires_as_of_disclosure"] == "YES"
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "CORRECTNESS > FRESHNESS > LATENCY",
        "UNVALIDATED DATA MUST NOT BE PUBLISHED AS TRUSTED DATA",
        "candidate local state",
        "trusted published state",
        "`data_as_of`",
        "`source_reconciled_at`",
        "`reconciliation_status`",
        "`source_authority`",
        "La tolerancia es cero",
        "`STALE` aplica política restrictiva",
        "No existe fallback silencioso",
    ):
        assert phrase in architecture


def test_watermark_only_advances_after_trusted_publish_and_resume_is_safe() -> None:
    watermarks = rows("watermark_checkpoint_contract.csv")
    assert {row["mode_or_state"] for row in watermarks} == {
        "INITIAL_INGESTION",
        "INCREMENTAL_UPDATE",
        "RECONCILIATION",
        "SAFE_ABORT",
    }
    trusted = [row for row in watermarks if row["watermark_name"] == "published_trusted_watermark"]
    assert len(trusted) == 2
    assert all(row["advance_condition"] == "only after successful validation and publication" for row in trusted)
    assert all(row["authoritative_for_resume"] == "YES" for row in trusted)
    safe_abort = [row for row in watermarks if row["mode_or_state"] == "SAFE_ABORT"][0]
    assert safe_abort["advance_condition"] == "unchanged by abort"
    assert "WATERMARK ADVANCES ONLY AFTER SUCCESSFUL VALIDATION AND PUBLICATION" in ARCHITECTURE.read_text(encoding="utf-8")
    assert "Resume desde el último checkpoint confiable" in ARCHITECTURE.read_text(encoding="utf-8")


def test_reconciliation_is_update_control_not_third_pipeline() -> None:
    reconciliation = {row["reconciliation_level"]: row for row in rows("reconciliation_contract.csv")}
    assert set(reconciliation) == {
        "FAST_FOCAL_RECONCILIATION",
        "PERIODIC_AUTHORITATIVE_RECONCILIATION",
        "INITIAL_BASELINE_RECONCILIATION",
        "DIVERGENCE_RECOVERY",
    }
    assert reconciliation["FAST_FOCAL_RECONCILIATION"]["belongs_to"] == "INCREMENTAL_UPDATE"
    assert reconciliation["PERIODIC_AUTHORITATIVE_RECONCILIATION"]["belongs_to"] == "INCREMENTAL_UPDATE"
    assert "no se declara reconciliado todo el Data Lake" in ARCHITECTURE.read_text(encoding="utf-8")


def test_hana_authority_load_minimization_and_no_user_query() -> None:
    budget = {row["operation_type"]: row for row in rows("hana_load_budget_contract.csv")}
    assert budget["CHAT_REQUEST"]["allowed"] == "NO"
    assert budget["CHAT_REQUEST"]["user_triggered_allowed"] == "NO"
    assert budget["RECURRENT_FULL_SCAN_POLLING"]["allowed"] == "NO"
    assert budget["DUPLICATE_INDEPENDENT_WORKER_SCAN"]["allowed"] == "NO"
    bounded_operations = {
        "INITIAL_BOUNDED_WINDOW",
        "INCREMENTAL_CHANGE_DETECTION",
        "AFFECTED_OBJECT_AUTHORITATIVE_READ",
        "FAST_FOCAL_RECONCILIATION",
        "PERIODIC_AUTHORITATIVE_RECONCILIATION",
    }
    for operation in bounded_operations:
        row = budget[operation]
        assert row["bounded_required"] == "YES"
        assert row["max_concurrency_configured"] == "YES"
        assert row["timeout_required"] == "YES"
        assert row["backoff_required"] == "YES"
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "HANA_QUERY_ON_USER_REQUEST=NO",
        "NEAR-REAL-TIME",
        "full scans",
        "`SELECT *`",
        "N+1",
        "MAX_HANA_CONCURRENT_QUERIES",
        "OnHand`, `IsCommited`, `OnOrder`",
        "fallback silencioso",
    ):
        assert phrase in architecture


def test_resource_guards_are_preflight_continuous_and_configurable() -> None:
    guards = rows("resource_guard_contract.csv")
    assert {row["category"] for row in guards} == {
        "RAM", "SWAP", "LOAD", "DISK", "TEMP_DISK", "DUCKDB_MEMORY",
        "DUCKDB_THREADS", "WORKERS", "HANA_CONCURRENCY", "QUERY_TIMEOUT", "SPILL",
    }
    assert all(row["preflight_required"] == "YES" for row in guards)
    assert all(row["continuous_check_required"] == "YES" for row in guards)
    assert all(row["threshold_source"] != "" for row in guards)
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "A DATA JOB MAY FAIL. IT MUST NOT TAKE DOWN THE MACHINE",
        "preflight y guards continuos",
        "MAX_INGESTION_WORKERS",
        "memory_limit",
        "temp_directory",
        "max_temp_directory_size",
        "PAUSE",
        "BACKOFF",
        "SAFE_ABORT",
        "No se inventa",
    ):
        assert phrase in architecture
    assert "Dask por defecto" in architecture


def test_physical_layout_preserves_ducklake_atomic_ownership() -> None:
    layout = {row["layout_id"]: row for row in rows("physical_ingestion_layout_contract.csv")}
    assert layout["RAW_INITIAL_LAYOUT"]["mode"] == "INITIAL_INGESTION"
    assert layout["RAW_UPDATE_LAYOUT"]["mode"] == "INCREMENTAL_UPDATE"
    assert layout["MONTH"]["notes"].startswith("one month need not equal")
    assert layout["MICRO_BATCH"]["notes"].startswith("one micro-batch need not equal")
    assert layout["ATOMIC"]["ownership"] == "DUCKLAKE"
    assert "NO PARTITION BY DEFAULT" in ARCHITECTURE.read_text(encoding="utf-8")
    assert "Atomic continúa bajo ownership de DuckLake" in ARCHITECTURE.read_text(encoding="utf-8")


def test_adr_index_and_machine_registry_are_updated_without_duplication() -> None:
    adr_text = ADR_INDEX.read_text(encoding="utf-8")
    ids = re.findall(r"^## (ADR-\d{3}) — ", adr_text, re.MULTILINE)
    assert len(ids) == 38
    assert len(ids) == len(set(ids))
    for number in range(30, 35):
        assert f"## ADR-{number:03d} —" in adr_text
        assert f"| Status | ACCEPTED |" in adr_text[adr_text.index(f"## ADR-{number:03d} —"):]
    registry = rows("architecture_decisions.csv")
    principles = rows("architecture_principles.csv")
    assert len(registry) == 38
    assert len({row["adr_id"] for row in registry}) == 38
    assert {row["adr_id"] for row in registry[-9:]} == {f"ADR-{number:03d}" for number in range(30, 39)}
    assert len(principles) == 24
    assert {row["principle_id"] for row in principles[-6:]} == {f"P-{number:03d}" for number in range(19, 25)}


def test_gate_is_documental_only_and_has_no_data_side_effects() -> None:
    current = json.loads(CURRENT_STATE.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert current["result"].endswith("_PASS")
    assert summary["result"].endswith("_PASS")
    assert current["runtime_implemented"] is False
    assert current["scheduler_implemented"] is False
    assert current["new_backfill_started"] is False
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
    assert summary["reconciliation_is_update_control"] is True
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
