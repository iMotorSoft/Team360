"""Phase A runner for TELCHI_DATALAKE_MATERIAL_SUPPLY_DERIVATION_AND_CANDIDATE_V1.

Resolves the real purchasing lineage only. Reuses the frozen fact-capture
infrastructure; never recaptures the eight baseline datasets.

Usage (from ``SrvRestAstroLS_v1/backend``)::

    uv run python modules/telchi/investigation/validation/\
datalake_material_supply_derivation_v1/run_phase_a.py --as-of 2026-09-24
"""
from __future__ import annotations

import argparse
import json
import resource
import subprocess
import time
from datetime import date, datetime, timezone
from pathlib import Path

from modules.telchi.datalake.material_supply_fact_capture import (
    EVIDENCE_ROOT,
    FOUNDATION_EVIDENCE_ROOT,
    read_persisted_rows,
    write_json,
)
from modules.telchi.datalake.material_supply_purchasing_lineage import (
    AP_DATASET_NAMES,
    FACT_CAPTURE_ROOT,
    RAW_ROOT,
    ap_invoice_offline_validate,
    build_pdn_linkage_metrics,
    capture_ap_invoices,
    lineage_coverage,
    pdn1_basetype_distribution,
    persist_lineage_paths,
    resolve_receipt_lineage,
)
from modules.telchi.datalake.source import HanaReadOnlySource

REPO_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360")
EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / "TELCHI_DATALAKE_MATERIAL_SUPPLY_FOUNDATION_V1"
KNOWN_FOUNDATION = "foundation_029c2476d5f3912cdfe4e630f52d2e28"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def worktree_status() -> str:
    return subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Material Supply Phase A lineage")
    parser.add_argument("--as-of", default="2026-09-24")
    parser.add_argument("--skip-capture", action="store_true")
    parser.add_argument("--run-id", default="material-supply-lineage-2026-09-24")
    args = parser.parse_args(argv)
    as_of = date.fromisoformat(args.as_of)

    started = time.time()
    worktree_before = worktree_status()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    source = HanaReadOnlySource()
    if args.skip_capture:
        capture_report = {
            "gate": "TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1",
            "run_id": args.run_id, "as_of": as_of.isoformat(), "raw_root": str(RAW_ROOT),
            "results": [], "captured_rows": {}, "sap_write_count": source.sap_write_count,
        }
    else:
        capture_report = capture_ap_invoices(source, as_of=as_of, run_id=args.run_id, logger=print)
    offline = ap_invoice_offline_validate(RAW_ROOT)

    # Offline reconstruction from persisted raw (never SAP).
    receipt_lines = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_receipt_line")
    receipt_headers = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_receipt")
    ap_lines = read_persisted_rows(RAW_ROOT, "ap_invoice_line")
    po_lines = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_order_line")
    po_headers = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_order")

    distribution = pdn1_basetype_distribution(receipt_lines)
    linkage = build_pdn_linkage_metrics(receipt_lines, ap_lines, po_lines)
    records = resolve_receipt_lineage(receipt_lines, ap_lines, po_lines)
    coverage = lineage_coverage(records)
    lineage_manifest = persist_lineage_paths(records, run_id=args.run_id, as_of=utc_now())

    evidence = {
        "purchasing_lineage_discovery.json": {
            "gate": "TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1",
            "discovered_chain": ["PDN1.BaseType=18 -> OPCH/PCH1", "PCH1.BaseType=22 -> POR1"],
            "sap_object_types": {"18": "AP_INVOICE_OPCH", "20": "GOODS_RECEIPT_PO_OPDN",
                                 "22": "PURCHASE_ORDER_POR1", "-1": "FREE_TEXT_MANUAL"},
            "no_fuzzy_matching": True,
        },
        "pdn1_basetype_distribution.json": distribution,
        "purchase_lineage_paths.json": {
            "records": len(records),
            "defensible": coverage["DEFENSIBLE_PO_LINEAGE_LINES"],
            "persisted_manifest": lineage_manifest.get("manifest_path"),
            "sample": [r for r in records if r["lineage_path_type"] == "INDIRECT_PO_RECEIPT_VIA_AP_INVOICE"][:5],
        },
        "purchase_lineage_coverage.json": {
            **coverage, "linkage_metrics": linkage,
            "PDN1_BASETYPE_DISTRIBUTION": distribution["by_basetype"],
        },
        "ap_invoice_column_discovery.json": {
            table: {"column_count": len(columns)}
            for table, columns in capture_report.get("discovery", {}).items()
        },
        "ap_invoice_capture.json": {
            "raw_root": str(RAW_ROOT),
            "captured_rows": capture_report.get("captured_rows", {}),
            "datasets": AP_DATASET_NAMES,
            "offline": offline,
        },
    }
    for name, payload in evidence.items():
        write_json(EVIDENCE / name, payload)

    summary = {
        "gate": "TELCHI_DATALAKE_MATERIAL_SUPPLY_PURCHASING_LINEAGE_V1",
        "run_id": args.run_id,
        "as_of": as_of.isoformat(),
        "worktree_before": worktree_before,
        "sap_write_count": source.sap_write_count,
        "foundation_current_expected": KNOWN_FOUNDATION,
        "offline_read": offline,
        "pdn1_basetype_distribution": distribution["by_basetype"],
        "linkage_metrics": linkage,
        "lineage_coverage": coverage,
        "resource": {
            "elapsed_seconds": round(time.time() - started, 3),
            "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "rss_before_kb": rss_before,
        },
    }
    write_json(EVIDENCE / "phase_a_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())