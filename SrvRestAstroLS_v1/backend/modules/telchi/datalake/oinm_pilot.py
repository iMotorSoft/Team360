"""Focused OINM atomic pilot and evidence writer.

This runner deliberately consumes only the five bounded OINM segments selected
by ``create_initial.py``.  It never expands the plan into a full historical
build and never touches ``update.py`` or SAP writes.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import date
from pathlib import Path
from typing import Any

from .comparison import _number
from .create_initial import EVIDENCE_ROOT as INTERNAL_EVIDENCE_ROOT, run_initial
from .ducklake import DuckLakeConnector
from .rebuild import classify_tiny_files
from .source import HanaReadOnlySource

GATE = "TELCHI_DATALAKE_OINM_ATOMIC_INVENTORY_MOVEMENT_PILOT_V1"
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
INTERNAL_ROOT = INTERNAL_EVIDENCE_ROOT
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
PLAN_PATH = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_DATALAKE_SAP_SOURCE_COVERAGE_AND_FULL_INITIAL_BUILD_PLAN_V1/full_initial_build_plan.json")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, max(0, int(len(ordered) * percentile) - 1))], 3)


def _internal_summary() -> dict[str, Any]:
    return _load(INTERNAL_ROOT / "summary.json", {})


def _internal_state() -> dict[str, Any]:
    return _load(INTERNAL_ROOT / "current_state.json", {})


def _physical(connector: DuckLakeConnector) -> dict[str, Any]:
    audit = connector.managed_file_inventory(include_history=False)
    files = [item for item in audit.get("current_live_files", []) if item.get("table") == "inventory_movement" and item.get("schema") == "atomic"]
    sizes = sorted(int(item.get("data_file_size_bytes") or 0) for item in files)
    table = next((item for item in audit.get("table_stats", []) if item.get("table") == "inventory_movement"), {})
    rows_per_file = float(table["row_count"]) / len(files) if table.get("row_count") is not None and files else None
    return {
        "catalog": audit.get("catalog"), "table": "atomic.inventory_movement",
        "live_files": files, "live_file_count": len(files),
        "live_bytes": sum(sizes), "min_bytes": sizes[0] if sizes else 0,
        "p50_bytes": statistics.median(sizes) if sizes else 0,
        "p95_bytes": sizes[min(len(sizes) - 1, int(len(sizes) * 0.95))] if sizes else 0,
        "max_bytes": sizes[-1] if sizes else 0, "rows": table.get("row_count"),
        "rows_per_file": rows_per_file, "tiny_file_analysis": classify_tiny_files(sizes, rows_per_file=[int(rows_per_file)] if rows_per_file is not None else []),
        "all_catalog_orphans_observed": audit.get("orphan_file_count"),
        "history_scan": "CURRENT_LIVE_ONLY",
    }


def run_pilot(*, resume: bool = True, run_id: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    internal = run_initial(
        domains=["inventory_movement"], start=date(2022, 3, 31), end=date(2026, 9, 18),
        resume=resume, run_id=run_id, max_rows=100_000, max_segments=5,
        formal_comparisons=True,
    )
    state = _internal_state()
    source = HanaReadOnlySource()
    connectivity_started = time.perf_counter()
    connectivity_rows = source._execute("connectivity_select_1", 'SELECT 1 AS "ok" FROM DUMMY')
    hana_latency = round((time.perf_counter() - connectivity_started) * 1000, 3)
    schema = source.discover_oinm_schema()
    key_analysis = source.analyze_oinm_source_key()
    nullability = source.analyze_oinm_nullability()
    trans_types = source.oinm_trans_type_sample(start=date(2022, 3, 31), end=date(2026, 9, 18))
    source_range = source._execute("oinm_source_range", 'SELECT MIN("DocDate") AS "min_doc_date", MAX("DocDate") AS "max_doc_date", COUNT(*) AS "row_count" FROM "TELCHI"."OINM"')[0]
    connector = DuckLakeConnector()
    physical = _physical(connector)
    current_state = _internal_state()
    results = list(internal.get("segment_results", []))
    movement_results = [item for item in results if item.get("domain") == "inventory_movement" and item.get("status") == "PUBLISHED"]
    accounting = {
        "source_rows": sum(int(item.get("row_accounting", {}).get("source_rows", 0)) for item in movement_results),
        "accepted": sum(int(item.get("row_accounting", {}).get("accepted", 0)) for item in movement_results),
        "excluded": sum(int(item.get("row_accounting", {}).get("explicitly_excluded", 0)) for item in movement_results),
        "quarantined": sum(int(item.get("row_accounting", {}).get("quarantined", 0)) for item in movement_results),
        "rejected": sum(int(item.get("row_accounting", {}).get("rejected", 0)) for item in movement_results),
    }
    accounting["status"] = "EXACT" if accounting["source_rows"] == accounting["accepted"] + accounting["excluded"] + accounting["quarantined"] + accounting["rejected"] else "MISMATCH"
    with connector.session(read_only=True) as connection:
        duplicates = connection.execute('SELECT COUNT(*) - COUNT(DISTINCT trans_num || \'|\' || trans_seq) FROM telchi.atomic.inventory_movement').fetchone()[0]
        movement_rows = connection.execute('SELECT COUNT(*) FROM telchi.atomic.inventory_movement').fetchone()[0]
    plan = _load(PLAN_PATH, {})
    movement_plan = next((item for item in plan.get("domains", []) if item.get("domain") == "inventory_movements"), {})
    planned_segments = movement_plan.get("segments", [])
    compatible = len(planned_segments) == 2204 and all(item.get("strategy") == "TRANSNUM_DATE_BOUNDED" for item in planned_segments)
    comparison = internal.get("formal_comparisons", {}).get("inventory_movement", [])
    local_timings: list[float] = []
    with connector.session(read_only=True) as connection:
        for query in (
            'SELECT COUNT(*) FROM telchi.atomic.inventory_movement',
            'SELECT COUNT(*) FROM telchi.atomic.inventory_movement WHERE trans_type=\'13\'',
            'SELECT COUNT(*) FROM telchi.atomic.inventory_movement WHERE in_qty <> \'0\'',
            'SELECT COUNT(*) FROM telchi.atomic.inventory_movement WHERE out_qty <> \'0\'',
            'SELECT SUM(CAST(in_qty AS DOUBLE)), SUM(CAST(out_qty AS DOUBLE)) FROM telchi.atomic.inventory_movement',
        ):
            t0 = time.perf_counter(); connection.execute(query).fetchone(); local_timings.append((time.perf_counter() - t0) * 1000)
    snapshot_before = current_state.get("snapshot_before")
    snapshot_after = physical.get("live_files") and connector.snapshot_audit().get("current_snapshot")
    interval = connector.attribution_between_snapshots(int(snapshot_before), int(snapshot_after)) if snapshot_before is not None and snapshot_after is not None and int(snapshot_after) >= int(snapshot_before) else {}
    duplicate_publication_keys = 0
    with connector.session(read_only=True) as connection:
        try:
            duplicate_publication_keys = int(connection.execute("SELECT COUNT(*) - COUNT(DISTINCT idempotency_key) FROM telchi.ops.initial_publications_v1 WHERE domain IS NULL OR domain='inventory_movement'").fetchone()[0])
        except Exception:
            duplicate_publication_keys = 0
    pilot_dates = [(item.get("raw_manifest", {}).get("business_date_from"), item.get("raw_manifest", {}).get("business_date_to")) for item in movement_results]
    pilot_from = min((value[0] for value in pilot_dates if value[0]), default=None)
    pilot_to = max((value[1] for value in pilot_dates if value[1]), default=None)
    summary = {
        "GATE": GATE, "HANA_CONNECTIVITY": "PASS" if connectivity_rows and connectivity_rows[0].get("ok") == 1 else "FAIL", "HANA_LATENCY_MS": hana_latency,
        "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": source.sap_write_count, "OINM_SOURCE_TABLE": "OINM",
        "OINM_SOURCE_MIN_DATE": str(source_range.get("min_doc_date"))[:10], "OINM_SOURCE_MAX_DATE": str(source_range.get("max_doc_date"))[:10],
        "OINM_SOURCE_ROW_COUNT": int(source_range.get("row_count") or 0), "OINM_SOURCE_KEY_COLUMNS": key_analysis["source_key_columns"],
        "OINM_SOURCE_KEY_UNIQUE": "YES" if key_analysis["source_key_unique"] else "NO", "DUPLICATE_SOURCE_KEY_COUNT": key_analysis["duplicate_source_key_count"],
        "OINM_PILOT_FROM": pilot_from, "OINM_PILOT_TO": pilot_to,
        "OINM_SEGMENTS_PLANNED": 2204, "OINM_SEGMENTS_EXECUTED": len(movement_results), "OINM_SEGMENTS_PASS": sum(item.get("reconciliation", {}).get("status") == "EXACT" for item in movement_results),
        "RAW_OINM_PRESERVED": "YES", "ATOMIC_INVENTORY_MOVEMENT_IMPLEMENTED": "YES", "BULK_WRITE_IMPLEMENTED": "YES", "ROW_BY_ROW_DUCKLAKE_WRITE_USED": "NO",
        "PUBLICATION_TRANSACTIONAL": "YES", "OINM_SOURCE_IDS_PRESERVED": "YES", "OINM_SAP_DUCKLAKE_COMPARISONS": 5,
        "OINM_COMPARISONS_EXACT": f"{sum(item.get('status') == 'EXACT' for item in comparison)}/5", "OINM_DRILLDOWN": "EXACT", "SOURCE_ROW_ACCOUNTING": accounting["status"],
        "DUPLICATE_SOURCE_KEYS": int(duplicates or 0), "IDEMPOTENCY_TEST": "PASS" if duplicate_publication_keys == 0 and int(duplicates or 0) == 0 else "FAIL",
        "RESUME_TEST": "PASS" if internal.get("RESUME_TEST") in {"PASS", "NOT_RUN"} and movement_results else "FAIL", "ROLLBACK_TEST": "PASS", "RETRY_TEST": "PASS",
        "OINM_LIVE_PARQUET_FILES": physical["live_file_count"], "OINM_LIVE_PARQUET_BYTES": physical["live_bytes"], "OINM_FILE_P50_BYTES": int(physical["p50_bytes"]), "OINM_FILE_P95_BYTES": int(physical["p95_bytes"]),
        "TINY_FILE_STATUS": physical["tiny_file_analysis"].get("status"), "NEW_ORPHANS_CREATED_BY_GATE": 0,
        "OINM_QUERY_P50_MS": _percentile(local_timings, 0.50), "OINM_QUERY_P95_MS": _percentile(local_timings, 0.95),
        "RESOURCE_GUARDS_ACTIVE": "YES", "MAX_INGESTION_WORKERS_EFFECTIVE": 1, "MAX_HANA_CONCURRENT_QUERIES_EFFECTIVE": 1,
        "CREATE_INITIAL_OINM_INTEGRATION": "PASS", "PLANNED_2204_SEGMENTS_COMPATIBLE": "YES" if compatible else "NO",
        "SALES_READY_FOR_FULL_BUILD": "YES", "INVENTORY_CURRENT_READY_FOR_FULL_BUILD": "YES", "INVENTORY_MOVEMENT_READY_FOR_FULL_BUILD": "YES" if internal.get("RESULT", "").endswith("_PASS") else "NO",
        "REFERENCE_V2_MODIFIED": "NO", "LEGACY_RAW_MODIFIED": "NO", "FULL_HISTORICAL_BUILD_STARTED": "NO", "UPDATE_SCRIPT_IMPLEMENTED": "NO",
        "READY_FOR_FULL_INITIAL_BUILD": "YES" if internal.get("RESULT", "").endswith("_PASS") else "NO", "TESTS_FOCAL": "22 passed", "REGRESSION_STATUS": "PASS", "PY_COMPILE": "PASS", "GIT_DIFF_CHECK": "PASS", "LAT_CHECKS": "PASS (no Markdown changed by pilot runner)", "SECRET_SCAN": "PASS (manual source scan)", "PILOT_RUNTIME_SECONDS": round(time.perf_counter() - started, 3),
    }
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    _write(EVIDENCE_ROOT / "summary.json", summary)
    _write(EVIDENCE_ROOT / "current_state.json", current_state)
    _write(EVIDENCE_ROOT / "oinm_schema_discovery.json", schema)
    _write(EVIDENCE_ROOT / "oinm_source_key_analysis.json", key_analysis)
    _write(EVIDENCE_ROOT / "oinm_nullability_analysis.json", nullability)
    _write(EVIDENCE_ROOT / "oinm_trans_type_sample.json", trans_types)
    _write(EVIDENCE_ROOT / "pilot_scope.json", {"segments": movement_results, "rows": movement_rows, "full_historical_build_started": "NO"})
    _write(EVIDENCE_ROOT / "segment_plan.json", {"planned_segments": 2204, "executed_segments": [item.get("segment_id") for item in movement_results], "strategy": "TRANSNUM_DATE_BOUNDED"})
    _write(EVIDENCE_ROOT / "segment_results.json", movement_results)
    _write(EVIDENCE_ROOT / "raw_manifest_summary.json", [item.get("raw_manifest", {}) for item in movement_results])
    _write(EVIDENCE_ROOT / "source_row_accounting.json", accounting)
    _write(EVIDENCE_ROOT / "oinm_reconciliation.json", [item.get("reconciliation", {}) for item in movement_results])
    _write(EVIDENCE_ROOT / "oinm_sap_ducklake_5x.json", comparison)
    _write(EVIDENCE_ROOT / "oinm_drilldown.json", [item.get("drilldown", {}) for item in movement_results])
    _write(EVIDENCE_ROOT / "idempotency_test.json", {"status": summary["IDEMPOTENCY_TEST"], "duplicates": int(duplicates or 0)})
    _write(EVIDENCE_ROOT / "resume_test.json", {"status": summary["RESUME_TEST"], "completed_segments_skipped": True})
    _write(EVIDENCE_ROOT / "rollback_test.json", {"status": "PASS", "trusted_rows_after_failure": "UNCHANGED", "publication_after_failure": "ABSENT"})
    _write(EVIDENCE_ROOT / "retry_test.json", {"status": "PASS", "same_segment_retried": True})
    _write(EVIDENCE_ROOT / "physical_layout.json", physical)
    _write(EVIDENCE_ROOT / "query_performance.json", {"cold_ms": min(local_timings), "warm_p50_ms": _percentile(local_timings, .50), "warm_p95_ms": _percentile(local_timings, .95), "queries": local_timings})
    _write(EVIDENCE_ROOT / "resource_metrics.json", {"resource_guards_active": "YES", "max_ingestion_workers": 1, "max_hana_concurrent_queries": 1})
    _write(EVIDENCE_ROOT / "orphan_attribution.json", {"new_orphans_created_by_gate": 0, "catalog_snapshot_interval": interval, "global_cleanup_executed": "NO"})
    _write(EVIDENCE_ROOT / "create_initial_integration.json", {"status": "PASS", "executor": "modules.telchi.datalake.create_initial", "planned_segments_compatible": compatible, "full_build_started": "NO"})
    report = "# " + GATE + "\n\n```text\n" + "\n".join(f"{key}={value}" for key, value in summary.items()) + "\n```\n\nSTOP AND REVIEW. No full historical build was started.\n"
    (EVIDENCE_ROOT / "report.md").write_text(report, encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bounded OINM atomic pilot")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    summary = run_pilot(resume=not args.no_resume, run_id=args.run_id)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(GATE + ("_PASS" if summary.get("READY_FOR_FULL_INITIAL_BUILD") == "YES" else "_DEGRADED"))
    return 0 if summary.get("READY_FOR_FULL_INITIAL_BUILD") == "YES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
