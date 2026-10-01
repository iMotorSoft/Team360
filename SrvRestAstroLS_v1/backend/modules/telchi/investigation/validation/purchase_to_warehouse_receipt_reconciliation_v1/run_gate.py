"""TELCHI_PURCHASE_TO_WAREHOUSE_RECEIPT_RECONCILIATION_V1 gate runner.

Usage (from SrvRestAstroLS_v1/backend):

    uv run python modules/telchi/investigation/validation/\
purchase_to_warehouse_receipt_reconciliation_v1/run_gate.py

Data Lake only. READ ONLY. SAP/HANA is out of scope for this run:
SAP_ACCESSED=NO, SAP_QUERY_COUNT=0, SAP_WRITE_COUNT=0.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.telchi.investigation.validation.purchase_to_warehouse_receipt_reconciliation_v1.reconciliation import (  # noqa: E402
    CLASS_ORDER,
    GATE,
    SAP_ACCESSED,
    SAP_QUERY_COUNT,
    SAP_WRITE_COUNT,
    build_datasets,
    load_movements,
    run_reconciliation,
)

EVIDENCE_ROOT = Path(__file__).resolve().parent / "evidence"
REPORT_ROOT = Path(__file__).resolve().parents[2] / "docs"

THRESHOLDS = {
    "receipt_line_link_resolution_rate": 0.98,
    "movement_corroboration_rate_inventory_items": 0.95,
    "max_fanout_violations": 0,
    "max_item_mismatch_links": 0,
    "max_uom_incompatible_pairs": 0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate_gate(summary: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    ok = True
    controls = summary["controls"]
    universe = summary["universe"]

    valid_rl = universe["receipt_lines_valid"]
    linked = universe["receipt_lines_linked_to_po"]
    unresolved = universe["receipt_lines_unresolved_valid"]
    link_rate = (linked + universe.get("receipt_lines_linked_to_cancelled_po", 0)) / valid_rl if valid_rl else 0.0
    if link_rate < THRESHOLDS["receipt_line_link_resolution_rate"]:
        ok = False
        reasons.append(f"receipt line link resolution {link_rate:.4f} < {THRESHOLDS['receipt_line_link_resolution_rate']}")
    else:
        reasons.append(f"receipt line link resolution {link_rate:.4f} OK (unresolved={unresolved})")

    mv = controls["movement_controls"]
    corroborated = mv["matched"]
    inventory_receipt_lines = valid_rl  # includes import charges; compute below
    mv_rate = corroborated / inventory_receipt_lines if inventory_receipt_lines else 0.0
    if mv_rate < THRESHOLDS["movement_corroboration_rate_inventory_items"]:
        ok = False
        reasons.append(f"movement corroboration {mv_rate:.4f} < {THRESHOLDS['movement_corroboration_rate_inventory_items']}")
    else:
        reasons.append(f"movement corroboration {mv_rate:.4f} OK (qty_equal={mv['qty_equal']}, whs_equal={mv['whs_equal']})")

    if controls["fanout_violations_receipt_line_to_multi_po"] > THRESHOLDS["max_fanout_violations"]:
        ok = False
        reasons.append("fanout violations detected")
    else:
        reasons.append("join fanout = 0")

    if controls["item_mismatch_links"] > THRESHOLDS["max_item_mismatch_links"]:
        ok = False
        reasons.append("item mismatch on links")
    else:
        reasons.append("item match on links = 100%")

    if controls["uom_incompatible_pairs"] > THRESHOLDS["max_uom_incompatible_pairs"]:
        ok = False
        reasons.append("UoM incompatible pairs present")
    else:
        reasons.append("UoM incompatible pairs = 0")

    classified = summary["totals"]["main_universe_lines"]
    if classified <= 0:
        return f"{GATE}_BLOCKED", reasons + ["empty main universe"]

    if ok:
        return f"{GATE}_PASS", reasons
    return f"{GATE}_DEGRADED", reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--json-out", default=None, help="override evidence json path")
    args = parser.parse_args()

    started = utc_now()
    data = build_datasets()
    movements = load_movements()
    analysis = run_reconciliation(data, movements)

    link_paths = analysis["controls"]["link_paths"]
    universe = dict(analysis["universe"])
    universe["receipt_lines_linked_to_cancelled_po"] = link_paths.get("LINKED_TO_CANCELLED_PO", 0)

    summary: dict[str, Any] = {
        "gate": GATE,
        "started_at": started,
        "finished_at": utc_now(),
        "source": "DATA_LAKE_ONLY",
        "foundation_current": movements["foundation_current"],
        "oinm_window": movements["oinm_window"],
        "tt18_2026": movements["tt18"],
        "tt21_2026": {
            "movements": movements["tt21_total"][0],
            "qty_out_base": str(movements["tt21_total"][1]),
            "suppliers": movements["tt21_total"][2],
            "window": [str(movements["tt21_total"][3]), str(movements["tt21_total"][4])],
        },
        "universe": universe,
        "class_stats": analysis["class_stats"],
        "totals": analysis["totals"],
        "controls": analysis["controls"],
        "warehouse_rows": analysis["warehouse_rows"],
        "uom_rows": analysis["uom_rows"],
        "invoice_view": analysis["invoice_view"],
        "non_inventory_count": analysis["non_inventory_count"],
        "exceptions": analysis["exceptions"],
        "thresholds": THRESHOLDS,
        "sap": {"SAP_ACCESSED": SAP_ACCESSED, "SAP_QUERY_COUNT": SAP_QUERY_COUNT,
                "SAP_WRITE_COUNT": SAP_WRITE_COUNT},
    }

    gate, reasons = evaluate_gate(summary)
    summary["gate_result"] = gate
    summary["gate_reasons"] = reasons

    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = started.replace(":", "").replace("-", "")[:15]
    json_path = Path(args.json_out) if args.json_out else EVIDENCE_ROOT / f"summary_{stamp}.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines_path = json_path.with_name(f"po_line_reconciliation_{stamp}.jsonl")
    with lines_path.open("w", encoding="utf-8") as fh:
        for row in analysis["results"]:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    non_inv_path = json_path.with_name(f"non_inventory_lines_{stamp}.json")
    non_inv_path.write_text(
        json.dumps({"count": analysis["non_inventory_count"],
                    "sample": analysis["non_inventory_lines"]},
                   indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print(f"GATE={gate}")
    for reason in reasons:
        print(f"  - {reason}")
    print(f"main universe lines: {analysis['totals']['main_universe_lines']}")
    for cls in CLASS_ORDER:
        s = analysis["class_stats"][cls]
        print(f"  {cls:24s} lines={s['lines']:6d} purchased={s['purchased_base']:>18s} received={s['received_base']:>18s}")
    print(f"evidence: {json_path}")
    print(f"lines:    {lines_path}")
    return 0 if gate.endswith("_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())