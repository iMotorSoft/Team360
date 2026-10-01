"""TELCHI_AP_INVOICED_WITHOUT_WAREHOUSE_RECEIPT_V1 gate runner.

Usage (from SrvRestAstroLS_v1/backend):

    uv run python modules/telchi/investigation/validation/\
ap_invoiced_without_warehouse_receipt_v1/run_gate.py

Data Lake only. READ ONLY. SAP/HANA is out of scope for this run:
SAP_ACCESSED=NO, SAP_QUERY_COUNT=0, SAP_WRITE_COUNT=0.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.telchi.investigation.validation.ap_invoiced_without_warehouse_receipt_v1.ap_invoice_no_grpo import (  # noqa: E402
    CLASS_ORDER,
    GATE,
    SAP_ACCESSED,
    SAP_QUERY_COUNT,
    SAP_WRITE_COUNT,
    analyze,
)

EVIDENCE_ROOT = Path(__file__).resolve().parent / "evidence"

THRESHOLDS = {
    "expected_target_lines": 25,
    "expected_purchased_base": "683025",
    "max_duplicate_keys": 0,
    "max_item_code_null": 0,
    "max_invalid_po_lines": 0,
    "max_invalid_invoices": 0,
    "max_unclassified": 0,
    "max_linked_movement_key_collisions": 0,
    "max_linked_movement_item_mismatch": 0,
    "max_base_entries_not_matching_po": 0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate_gate(analysis: dict[str, Any]) -> tuple[str, list[str]]:
    controls = analysis["controls"]
    reasons: list[str] = []
    ok = True

    checks = [
        ("target lines", controls["target_lines"], THRESHOLDS["expected_target_lines"]),
        ("purchased base total", controls["purchased_base_total"],
         THRESHOLDS["expected_purchased_base"]),
        ("duplicate keys", controls["duplicate_keys"], THRESHOLDS["max_duplicate_keys"]),
        ("ItemCode null", controls["item_code_null"], THRESHOLDS["max_item_code_null"]),
        ("invalid PO lines", controls["invalid_po_lines"], THRESHOLDS["max_invalid_po_lines"]),
        ("invalid invoices", controls["invalid_invoices"], THRESHOLDS["max_invalid_invoices"]),
        ("unclassified lines", controls["unclassified"], THRESHOLDS["max_unclassified"]),
        ("linked movement collisions", controls["linked_movement_key_collisions"],
         THRESHOLDS["max_linked_movement_key_collisions"]),
        ("linked movement item mismatch", controls["linked_movement_item_mismatch"],
         THRESHOLDS["max_linked_movement_item_mismatch"]),
        ("invoice base not matching PO", controls["base_entries_match_po"],
         THRESHOLDS["max_base_entries_not_matching_po"]),
    ]
    for label, got, want in checks:
        if got == want:
            reasons.append(f"{label}={got} OK")
        else:
            ok = False
            reasons.append(f"{label}={got} (expected {want})")

    if controls["category_partition_ok"]:
        reasons.append("exactly one category per line")
    else:
        ok = False
        reasons.append("category partition does not add up to the target lines")

    reasons.append(
        f"receipts linked to targets={controls['receipts_linked_to_targets']}, "
        f"linked movements={controls['linked_movement_count']}, "
        f"reversals={controls['reversal_detected']}, "
        f"rejected candidates={controls['rejected_candidates_total']}"
    )

    if controls["target_lines"] == 0:
        return f"{GATE}_BLOCKED", reasons + ["empty target universe"]
    return (f"{GATE}_PASS" if ok else f"{GATE}_DEGRADED"), reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--json-out", default=None, help="override evidence json path")
    args = parser.parse_args()

    started = utc_now()
    analysis = analyze()

    summary: dict[str, Any] = {
        "gate": GATE,
        "started_at": started,
        "finished_at": utc_now(),
        "source": "DATA_LAKE_ONLY",
        "foundation_current": analysis["foundation_current"],
        "windows": analysis["windows"],
        "totals": analysis["totals"],
        "controls": analysis["controls"],
        "class_stats": analysis["class_stats"],
        "thresholds": THRESHOLDS,
        "sap": {"SAP_ACCESSED": SAP_ACCESSED, "SAP_QUERY_COUNT": SAP_QUERY_COUNT,
                "SAP_WRITE_COUNT": SAP_WRITE_COUNT},
    }

    gate, reasons = evaluate_gate(analysis)
    summary["gate_result"] = gate
    summary["gate_reasons"] = reasons

    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = started.replace(":", "").replace("-", "")[:15]
    json_path = Path(args.json_out) if args.json_out else EVIDENCE_ROOT / f"summary_{stamp}.json"
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    lines_path = json_path.with_name(f"ap_invoice_no_grpo_lines_{stamp}.jsonl")
    with lines_path.open("w", encoding="utf-8") as fh:
        for row in analysis["results"]:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    print(f"GATE={gate}")
    for reason in reasons:
        print(f"  - {reason}")
    for cls in CLASS_ORDER:
        s = analysis["class_stats"][cls]
        print(f"  {cls:34s} lines={s['lines']:3d} purchased_base={s['purchased_base']:>12s}")
    print(f"evidence: {json_path}")
    print(f"lines:    {lines_path}")
    return 0 if gate.endswith("_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
