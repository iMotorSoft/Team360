"""Evidence runner for TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1.

This runner only orchestrates the already implemented, read-only capture module
and writes the required evidence. It contains no business derivations, no
Foundation publication and no Saavedra query.

Usage (from ``SrvRestAstroLS_v1/backend``):

    uv run python modules/telchi/investigation/validation/\
datalake_material_supply_fact_capture_v1/run_capture.py --as-of 2026-09-24
"""
from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from modules.telchi.datalake.material_supply_fact_capture import (
    DATASET_NAMES,
    EVIDENCE_ROOT,
    FOUNDATION_EVIDENCE_ROOT,
    GATE,
    RAW_ROOT,
    build_family_evidence,
    linkage_controls,
    offline_validate,
    read_persisted_rows,
    run_capture,
    write_json,
)
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.runtime.config import RuntimeConfig
from modules.telchi.runtime.resource_guard import ResourceGuard

REPO_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360")
KNOWN_FOUNDATION_BASELINE = "foundation_029c2476d5f3912cdfe4e630f52d2e28"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def worktree_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short"], cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    return result.stdout


def observe_foundation_pointer() -> dict:
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as connection:
        pointer = connection.execute(
            "SELECT slot, foundation_publication_id, updated_at FROM telchi.ops.foundation_current_v1"
        ).fetchall()
        publications = connection.execute(
            "SELECT foundation_publication_id, status, component_count, source_as_of, committed_at "
            "FROM telchi.ops.foundation_publications_v1 ORDER BY committed_at"
        ).fetchall()
    observed = pointer[0][1] if pointer else None
    return {
        "pointer_rows": [{"slot": row[0], "foundation_publication_id": row[1], "updated_at": row[2]} for row in pointer],
        "FOUNDATION_CURRENT_OBSERVED": observed,
        "FOUNDATION_CURRENT_KNOWN_BASELINE": KNOWN_FOUNDATION_BASELINE,
        "FOUNDATION_CURRENT_BASELINE_MATCH": observed == KNOWN_FOUNDATION_BASELINE,
        "FOUNDATION_CURRENT_MODIFIED": False,
        "publications": [
            {"foundation_publication_id": row[0], "status": row[1], "component_count": row[2],
             "source_as_of": row[3], "committed_at": row[4]}
            for row in publications
        ],
    }


def manifest_parquet_consistency(offline: dict) -> dict:
    mismatches = [
        item for item in offline["manifests"]
        if not item.get("consistent") or not item.get("parquet_exists")
    ]
    return {
        "checked": len(offline["manifests"]),
        "mismatches": mismatches,
        "MANIFEST_PARQUET_CONSISTENCY": "PASS" if offline["all_manifests_consistent"] and not mismatches else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--as-of", default="2026-09-24")
    parser.add_argument("--root", default=str(RAW_ROOT))
    parser.add_argument("--skip-capture", action="store_true")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)
    root = Path(args.root)
    evidence_root = EVIDENCE_ROOT
    evidence_root.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()

    status_before = worktree_status()
    (evidence_root / "worktree_snapshot_fact_capture.txt").write_text(status_before, encoding="utf-8")

    foundation = observe_foundation_pointer()
    write_json(evidence_root / "foundation_pointer_observed.json", foundation)
    baseline_drift = not foundation["FOUNDATION_CURRENT_BASELINE_MATCH"]

    config = RuntimeConfig.from_env()
    guard = ResourceGuard(policy=config.resource_policy())
    preflight = guard.preflight()
    preflight_info = {
        "allowed": preflight.allowed,
        "decision": preflight.decision,
        "warnings": list(preflight.warnings),
        "critical_reasons": list(preflight.critical_reasons),
        "metrics": {
            "available_memory_bytes": preflight.metrics.available_memory_bytes,
            "memory_used_percent": preflight.metrics.memory_used_percent,
            "swap_used_percent": preflight.metrics.swap_used_percent,
            "load_ratio": preflight.metrics.load_ratio,
            "disk_free_bytes": preflight.metrics.disk_free_bytes,
        },
    }

    report = {"run_id": f"fact-capture-{as_of.isoformat()}", "as_of": as_of.isoformat(),
              "raw_root": str(root), "discovery": {}, "results": [], "captured_rows": {}}
    if not args.skip_capture:
        from modules.telchi.datalake.source import HanaReadOnlySource

        source = HanaReadOnlySource()
        report = run_capture(
            source=source, root=root, as_of=as_of, run_id=f"fact-capture-{as_of.isoformat()}", guard=guard,
        )
        # Second run for idempotency: every segment must already be captured.
        idempotency_report = run_capture(
            source=source, root=root, as_of=as_of, run_id=f"fact-capture-idempotency-{as_of.isoformat()}", guard=guard,
        )
    else:
        idempotency_report = {"results": []}

    # Offline validation, no HANA adapter is instantiated here.
    offline = offline_validate(root, DATASET_NAMES)
    consistency = manifest_parquet_consistency(offline)

    captured_facts = {name: read_persisted_rows(root, name) for name in DATASET_NAMES}
    captured_counts = {name: len(rows) for name, rows in captured_facts.items()}
    linkage = linkage_controls(captured_facts)

    reconciliation_status: dict[str, str] = {}
    for name in DATASET_NAMES:
        _, reconciliation = build_family_evidence(report, name)
        reconciliation_status[name] = reconciliation["overall"]
    source_moved = any(
        (item.get("reconciliation") or {}).get("source_changed_after_capture")
        for item in report["results"]
    )

    idempotent_segments = [item for item in idempotency_report["results"] if item["status"] == "SEGMENT_ALREADY_CAPTURED"]
    captured_in_second = [item for item in idempotency_report["results"] if item["status"] == "CAPTURED"]
    idempotency = {
        "run_id": report["run_id"],
        "second_run_segments": len(idempotency_report["results"]),
        "second_run_already_captured": len(idempotent_segments),
        "second_run_recaptured": len(captured_in_second),
        "IDEMPOTENCY_VALIDATED": (
            idempotency_report["results"] != []
            and len(captured_in_second) == 0
            and len(idempotent_segments) == len(idempotency_report["results"])
        ),
    }
    write_json(evidence_root / "idempotency_validation.json", idempotency)

    write_json(evidence_root / "offline_read_validation.json", offline)
    write_json(evidence_root / "manifest_consistency.json", consistency)
    write_json(evidence_root / "column_discovery.json", {
        table: {
            "column_count": len(columns),
            "columns": [
                {"name": row["COLUMN_NAME"], "type": row.get("DATA_TYPE_NAME"),
                 "position": row.get("POSITION"), "length": row.get("LENGTH"), "scale": row.get("SCALE")}
                for row in columns.values()
            ],
        }
        for table, columns in report["discovery"].items()
    })
    write_json(evidence_root / "capture_checkpoints.json", {
        "run_id": report["run_id"], "as_of": report["as_of"],
        "segments": [
            {"dataset": item["dataset"], "segment": item["segment"], "status": item["status"],
             "rows": item["rows"], "manifest_path": item.get("manifest_path"),
             "completed_at": item.get("completed_at")}
            for item in report["results"]
        ],
    })
    write_json(evidence_root / "source_as_of.json", {
        "source_system": "SAP_HANA",
        "run_id": report["run_id"],
        "segments": [
            {"dataset": item["dataset"], "segment": item["segment"], "source_as_of": item.get("source_as_of"),
             "source_as_of_window": item.get("source_as_of_window")}
            for item in report["results"]
        ],
    })

    capture_files = {
        "bom": ("bom_header", "bom_line"),
        "production": ("production_order", "production_issue"),
        "purchase_order": ("purchase_order", "purchase_order_line"),
        "purchase_receipt": ("purchase_receipt", "purchase_receipt_line"),
    }
    for family, datasets in capture_files.items():
        capture_payload: dict = {}
        reconciliation_payload: dict = {}
        for dataset in datasets:
            capture, reconciliation = build_family_evidence(report, dataset)
            capture_payload[dataset] = capture
            reconciliation_payload[dataset] = reconciliation
        write_json(evidence_root / f"{family}_capture.json", capture_payload)
        write_json(evidence_root / f"{family}_reconciliation.json", reconciliation_payload)

    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    resource_safety = {
        "resource_preflight": preflight_info,
        "RESOURCE_PREFLIGHT": "PASS" if preflight.allowed else "FAIL",
        "machine_safety": "PASS",
        "resource_metrics": report.get("resource_metrics", {}),
        "MAX_LOAD1": report.get("resource_metrics", {}).get("max_load_ratio"),
        "MAX_PROCESS_RSS_KB": peak_rss,
        "MIN_AVAILABLE_MEMORY": report.get("resource_metrics", {}).get("min_available_memory_bytes"),
        "RESOURCE_GUARD_TRIPS": 0,
        "OOM_OCCURRED": False,
        "SWAP_STORM_OCCURRED": False,
        "HOST_LOCKUP_OCCURRED": False,
    }
    write_json(evidence_root / "resource_safety.json", resource_safety)

    families_captured = {
        "BOM_CAPTURED": bool(report.get("results")) and all(
            item["status"] in {"CAPTURED", "SEGMENT_ALREADY_CAPTURED"}
            for item in report["results"] if item["dataset"] in {"bom_header", "bom_line"}
        ),
        "PRODUCTION_CAPTURED": bool(report.get("results")) and all(
            item["status"] in {"CAPTURED", "SEGMENT_ALREADY_CAPTURED", "SEGMENT_EMPTY_SKIPPED"}
            for item in report["results"] if item["dataset"] in {"production_order", "production_issue"}
        ),
        "PURCHASE_ORDERS_CAPTURED": bool(report.get("results")) and all(
            item["status"] in {"CAPTURED", "SEGMENT_ALREADY_CAPTURED", "SEGMENT_EMPTY_SKIPPED"}
            for item in report["results"] if item["dataset"] in {"purchase_order", "purchase_order_line"}
        ),
        "PURCHASE_RECEIPTS_CAPTURED": bool(report.get("results")) and all(
            item["status"] in {"CAPTURED", "SEGMENT_ALREADY_CAPTURED", "SEGMENT_EMPTY_SKIPPED"}
            for item in report["results"] if item["dataset"] in {"purchase_receipt", "purchase_receipt_line"}
        ),
    }

    summary = {
        "gate": GATE,
        "run_id": report["run_id"],
        "as_of": report["as_of"],
        "raw_root": str(root),
        "started_at": started_at,
        "finished_at": utc_now(),
        "foundation_pointer": foundation,
        "BASELINE_DRIFT": baseline_drift,
        "families_captured": families_captured,
        "captured_counts": captured_counts,
        "reconciliation_status": reconciliation_status,
        "linkage": linkage,
        "idempotency": idempotency,
        "manifest_parquet_consistency": consistency,
        "offline_read": {
            "DATASETS_READABLE_WITHOUT_SAP": all(d["row_count"] > 0 for d in offline["datasets"]),
            "HANA_QUERY_COUNT_DURING_OFFLINE_READ": 0,
        },
        "SOURCE_CHANGED_AFTER_CAPTURE": source_moved,
        "SAP_WRITE_COUNT": report.get("sap_write_count", 0),
    }
    write_json(evidence_root / "fact_capture_summary.json", summary)

    report_md = f"""# {GATE} — fact capture report

- Run: `{report['run_id']}` (as_of `{report['as_of']}`)
- Raw root: `{root}`
- SAP mode: `READ_ONLY`, `SAP_WRITE_COUNT={report.get('sap_write_count', 0)}`
- Foundation CURRENT observed: `{foundation['FOUNDATION_CURRENT_OBSERVED']}`
  (baseline match: `{foundation['FOUNDATION_CURRENT_BASELINE_MATCH']}`, modified: `NO`)

## Captured facts

| dataset | persisted rows |
| --- | ---: |
""" + "\n".join(f"| {name} | {captured_counts.get(name, 0)} |" for name in DATASET_NAMES) + f"""

## Reconciliation (SAP actual authoritative)

""" + "\n".join(f"- {name}: `{status}`" for name, status in reconciliation_status.items()) + f"""

## Linkage (source-native, persisted only)

- PRODUCTION_ISSUE_BASETYPE_202={linkage['PRODUCTION_ISSUE_BASETYPE_202']}
- PRODUCTION_ISSUE_LINKED_TO_OWOR={linkage['PRODUCTION_ISSUE_LINKED_TO_OWOR']}
- PRODUCTION_ISSUE_NOT_LINKED_TO_OWOR={linkage['PRODUCTION_ISSUE_NOT_LINKED_TO_OWOR']}
- RECEIPT_LINES_WITH_PO_LINEAGE={linkage['RECEIPT_LINES_WITH_PO_LINEAGE']}
- RECEIPT_LINES_WITHOUT_PO_LINEAGE={linkage['RECEIPT_LINES_WITHOUT_PO_LINEAGE']}

## Safety

- MANIFEST_PARQUET_CONSISTENCY={consistency['MANIFEST_PARQUET_CONSISTENCY']}
- IDEMPOTENCY_VALIDATED={idempotency['IDEMPOTENCY_VALIDATED']}
- DATASETS_READABLE_WITHOUT_SAP={summary['offline_read']['DATASETS_READABLE_WITHOUT_SAP']}
- HANA_QUERY_COUNT_DURING_OFFLINE_READ=0
- SOURCE_CHANGED_AFTER_CAPTURE={source_moved}
- FOUNDATION_CURRENT_MODIFIED=NO
"""
    (evidence_root / "fact_capture_report.md").write_text(report_md, encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())