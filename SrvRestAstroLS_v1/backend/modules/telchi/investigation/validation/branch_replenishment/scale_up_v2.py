"""Controlled scale-up for TELCHI branch stock/demand Gate 2/3 V2.

Levels are intentionally explicit and sequential.  Each level processes small
ItemCode batches, writes append-only checkpoints, frees the batch, and checks
resources before the next batch.  The script never builds a branch×warehouse×
product×day universe in memory.
"""
from __future__ import annotations

import argparse
import gc
import gzip
import json
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.branch_replenishment.branch_replenishment_gate_v1 import rows
from modules.telchi.investigation.validation.branch_replenishment.daily_stock_demand_v1 import (
    MAX_WORKERS,
    TOLERANCE,
    ResourceGuard,
    ResourceGuardAbort,
    _dump_json,
    _in_clause,
    _write_jsonl,
    adaptive_batch_size,
    build_branch_daily,
    build_warehouse_stock,
    extract_current,
    extract_movements,
    extract_transfer_events,
    latest_date_for_branch,
    replenishment_output,
    sample_warehouse_context,
    select_sample_items,
)
from modules.telchi.investigation.validation.branch_replenishment.stock_demand_domain import (
    build_stockout_episodes,
    movement_category,
    reconcile_latest,
)

ROOT = EVIDENCE_ROOT / "branch_replenishment_daily_stock_demand" / "v2_scale_up"
LEVEL_ORDER = ("A", "B", "C", "D", "E")
LEVELS = {
    "A": {"branches": ["2A"], "days": 90, "item_mode": "top", "requested_items": 10},
    "B": {"branches": ["2A"], "days": 90, "item_mode": "active", "requested_items": None},
    "C": {"branches": ["2A"], "days": 365, "item_mode": "active", "requested_items": None},
    "D": {"branches": ["CM"], "days": 90, "item_mode": "active", "requested_items": None},
    "E": {"branches": ["2A", "CM"], "days": 365, "item_mode": "active", "requested_items": None},
}


def _append_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> int:
    count = 0
    with gzip.open(path, "at", encoding="utf-8") as fh:
        for value in values:
            fh.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def _checkpoint_size_mb(path: Path) -> float:
    return round(sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1024**2, 3)


def _batch(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _context_for_branches(cur: Any, branches: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    info: dict[str, dict[str, Any]] = {}
    branch_sales: dict[str, str] = {}
    for branch in branches:
        partial_info, partial_sales = sample_warehouse_context(cur, branch)
        info.update(partial_info)
        branch_sales.update(partial_sales)
    return info, branch_sales


def select_active_items(cur: Any, warehouses: list[str], start: date, end: date) -> list[str]:
    """Return only active L item keys; movement rows remain batch scoped."""
    ph = _in_clause(warehouses)
    result = rows(cur, f'''SELECT "ItemCode" AS item_code,
          SUM(ABS(COALESCE("InQty",0))+ABS(COALESCE("OutQty",0))) AS activity
        FROM "TELCHI"."OINM"
        WHERE "ItemCode" LIKE 'L%' AND "Warehouse" IN ({ph})
          AND "DocDate" BETWEEN ? AND ?
          AND (COALESCE("InQty",0)<>0 OR COALESCE("OutQty",0)<>0)
        GROUP BY "ItemCode" ORDER BY activity DESC''', tuple(warehouses) + (start, end))
    return [str(r["item_code"]) for r in result]


def atomic_scope(cur: Any, item_codes: list[str], warehouses: list[str], start: date, end: date) -> dict[str, Any]:
    items, whs = _in_clause(item_codes), _in_clause(warehouses)
    params = tuple(item_codes) + tuple(warehouses) + (start, end)
    summary = rows(cur, f'''SELECT COUNT(*) AS rows_count,COUNT(DISTINCT "TransNum") AS transnums,
        COUNT(DISTINCT "ItemCode") AS items,COUNT(DISTINCT "Warehouse") AS warehouses
        FROM "TELCHI"."OINM" WHERE "ItemCode" IN ({items}) AND "Warehouse" IN ({whs})
          AND "DocDate" BETWEEN ? AND ?
          AND (COALESCE("InQty",0)<>0 OR COALESCE("OutQty",0)<>0)''', params)[0]
    by_type = rows(cur, f'''SELECT "TransType" AS trans_type,COUNT(*) AS rows_count,
        SUM(COALESCE("InQty",0)) AS in_qty,SUM(COALESCE("OutQty",0)) AS out_qty
        FROM "TELCHI"."OINM" WHERE "ItemCode" IN ({items}) AND "Warehouse" IN ({whs})
          AND "DocDate" BETWEEN ? AND ?
          AND (COALESCE("InQty",0)<>0 OR COALESCE("OutQty",0)<>0)
        GROUP BY "TransType" ORDER BY "TransType"''', params)
    return {"oinm": summary, "by_transtype": by_type, "scope": {"items": item_codes, "warehouses": warehouses, "start": start, "end": end}}


def active_transfer_net(cur: Any, item_codes: list[str], destinations: list[str], start: date, end: date) -> float:
    items, whs = _in_clause(item_codes), _in_clause(destinations)
    result = rows(cur, f'''SELECT COALESCE(SUM(W."Quantity"),0) AS quantity
        FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
        WHERE O."CANCELED"='N' AND W."ItemCode" IN ({items}) AND W."WhsCode" IN ({whs})
          AND O."DocDate" BETWEEN ? AND ?''', tuple(item_codes) + tuple(destinations) + (start, end))
    return float(result[0]["quantity"] or 0) if result else 0.0


def active_transfer_oinm_net(cur: Any, item_codes: list[str], destinations: list[str], start: date, end: date) -> float:
    """Match OINM TT67 to active OWTR by BASE_REF, item and destination.

    This excludes OINM rows generated by canceled transfer headers and avoids
    treating outbound transfers from a branch as inbound replenishment.
    """
    items, whs = _in_clause(item_codes), _in_clause(destinations)
    result = rows(cur, f'''SELECT COALESCE(SUM(M."InQty"-M."OutQty"),0) AS quantity
        FROM "TELCHI"."OINM" M
        WHERE M."TransType"=67 AND M."ItemCode" IN ({items}) AND M."Warehouse" IN ({whs})
          AND M."DocDate" BETWEEN ? AND ?
          AND EXISTS (
            SELECT 1 FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
            WHERE O."CANCELED"='N' AND CAST(O."DocNum" AS NVARCHAR(20))=M."BASE_REF"
              AND W."ItemCode"=M."ItemCode" AND W."WhsCode"=M."Warehouse" AND W."Quantity"<>0
          )''', tuple(item_codes) + tuple(destinations) + (start, end))
    return float(result[0]["quantity"] or 0) if result else 0.0


def active_canceled_counts(cur: Any) -> dict[str, int]:
    result = rows(cur, '''SELECT 'OINV' AS table_name,COUNT(*) AS canceled FROM "TELCHI"."OINV" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'ORIN',COUNT(*) FROM "TELCHI"."ORIN" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'ODLN',COUNT(*) FROM "TELCHI"."ODLN" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'OWTR',COUNT(*) FROM "TELCHI"."OWTR" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'OIGN',COUNT(*) FROM "TELCHI"."OIGN" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'OIGE',COUNT(*) FROM "TELCHI"."OIGE" WHERE "CANCELED"='Y' ''')
    return {str(row["table_name"]): int(row["canceled"] or 0) for row in result}


def run_level(cur: Any, level: str, output: Path) -> dict[str, Any]:
    config = LEVELS[level]
    output.mkdir(parents=True, exist_ok=True)
    guard = ResourceGuard(output)
    started = time.monotonic()
    initial = guard.check("level_resource_check", 0, 0, 0)
    info, branch_sales = _context_for_branches(cur, config["branches"])
    warehouses = sorted(branch_sales)
    latest = max(latest_date_for_branch(cur, [w for w, b in branch_sales.items() if b == branch]) for branch in config["branches"])
    start = latest - timedelta(days=config["days"] - 1)
    if config["item_mode"] == "top":
        items = select_sample_items(cur, warehouses, start, latest, int(config["requested_items"]))
    else:
        items = select_active_items(cur, warehouses, start, latest)
    if not items:
        raise RuntimeError(f"level {level}: no active L products")
    requested_batch = 10
    batch_size = adaptive_batch_size(requested_batch, initial["snapshot"])
    guard.check("level_discovery", len(items), 0, batch_size)
    _dump_json(output / "level_discovery.json", {"level": level, "config": config, "branches": config["branches"], "warehouses": warehouses, "items": len(items), "date_start": start, "date_end": latest, "requested_batch_size": requested_batch, "batch_size": batch_size})

    for filename in ("daily_item_warehouse_stock.jsonl.gz", "daily_item_branch_stock.jsonl.gz", "daily_branch_demand.jsonl.gz", "replenishment_events.jsonl.gz", "stockout_episodes.jsonl.gz", "batch_metrics.jsonl"):
        (output / filename).unlink(missing_ok=True)

    total = defaultdict(float)
    total_counts = defaultdict(int)
    mismatches: list[dict[str, Any]] = []
    unknown = 0
    max_iowait = 0.0
    batch_metrics: list[dict[str, Any]] = []
    canceled = active_canceled_counts(cur)
    batches = list(_batch(items, batch_size))
    # The list contains only product keys, never movement or daily rows.
    for batch_number, item_codes in enumerate(batches, 1):
        batch_started = time.monotonic()
        guard.check(f"batch_{batch_number:04d}_before", 0, 0, len(item_codes))
        current = extract_current(cur, item_codes, warehouses)
        movements = extract_movements(cur, item_codes, warehouses, start, latest)
        transfers = extract_transfer_events(cur, branch_sales, info, item_codes, start, latest)
        atomic = atomic_scope(cur, item_codes, warehouses, start, latest)
        branch_current = {key: value for key, value in current.items() if key[1] in branch_sales}
        branch_movements = [row for row in movements if str(row["warehouse"]) in branch_sales]
        warehouse_stock, continuity = build_warehouse_stock(branch_current, branch_movements, start, latest)
        reconciliation = reconcile_latest(warehouse_stock, branch_current, TOLERANCE)
        stock_rows, demand_rows = build_branch_daily(branch_sales, warehouse_stock, branch_movements, transfers, start, latest)
        episodes = build_stockout_episodes(stock_rows)
        replenishments, replenishment_summary = replenishment_output(transfers, stock_rows)

        total["oinm_rows"] += int(atomic["oinm"]["rows_count"] or 0)
        total["input_rows"] += sum(int(row["source_rows"] or 0) for row in movements)
        total["warehouse_rows"] += _append_jsonl(output / "daily_item_warehouse_stock.jsonl.gz", ({"ItemCode": item, "Warehouse": wh, "Date": day, "StockEndOfDay": stock, "Branch": branch_sales.get(wh)} for (item, wh), series in warehouse_stock.items() for day, stock in series.items()))
        total["branch_rows"] += _append_jsonl(output / "daily_item_branch_stock.jsonl.gz", stock_rows)
        total["demand_rows"] += _append_jsonl(output / "daily_branch_demand.jsonl.gz", demand_rows)
        total["replenishment_rows"] += _append_jsonl(output / "replenishment_events.jsonl.gz", replenishments)
        total["episode_rows"] += _append_jsonl(output / "stockout_episodes.jsonl.gz", episodes)
        total_counts["combinations"] += reconciliation["total_combinations"]
        total_counts["exact"] += reconciliation["exact"]
        total_counts["mismatch"] += reconciliation["differences"]
        unknown += int(reconciliation.get("unknown", 0))
        mismatches.extend(reconciliation["difference_samples"][:10])
        for check in (continuity,):
            total_counts["continuity_violations"] += int(check["movement_violations"])
            total_counts["continuity_gaps"] += int(check["gaps"])
        transfer_oinm_net = sum(float(row["in_qty"] or 0) - float(row["out_qty"] or 0) for row in branch_movements if movement_category(row["trans_type"]) == "TRANSFER")
        transfer_event_qty = sum(float(row["ReplenishmentQty"]) for row in transfers)
        transfer_wtr_net = active_transfer_net(cur, item_codes, list(branch_sales), start, latest)
        transfer_oinm_scoped_net = active_transfer_oinm_net(cur, item_codes, list(branch_sales), start, latest)
        total["transfer_oinm_net"] += transfer_oinm_scoped_net
        total["transfer_event_qty"] += transfer_event_qty
        total["transfer_wtr_net"] += transfer_wtr_net
        guard_metric = guard.check(f"batch_{batch_number:04d}_after", len(movements) + len(transfers), len(stock_rows) + len(replenishments), len(item_codes))
        max_iowait = max(max_iowait, float(guard_metric["snapshot"].get("iowait_percent_window") or 0.0))
        batch_metric = {"level": level, "batch": batch_number, "products": len(item_codes), "OINM_rows": int(atomic["oinm"]["rows_count"] or 0), "output_rows": len(stock_rows) + len(demand_rows) + len(replenishments) + len(episodes), "elapsed_seconds": round(time.monotonic() - batch_started, 4), "checkpoint_size_mb": _checkpoint_size_mb(output), "reconciliation": {"exact": reconciliation["exact"], "mismatch": reconciliation["differences"], "unknown": unknown}, "result": "PASS"}
        batch_metrics.append(batch_metric)
        with (output / "batch_metrics.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(batch_metric, ensure_ascii=False, default=str) + "\n")
        del current, movements, transfers, atomic, branch_current, branch_movements, warehouse_stock, stock_rows, demand_rows, episodes, replenishments
        gc.collect()
        guard.check(f"batch_{batch_number:04d}_after_free", 0, 0, len(item_codes))

    elapsed = time.monotonic() - started
    resource_result = guard.summary()
    resource_result["max_iowait_percent"] = max(resource_result.get("max_iowait_percent", 0.0), max_iowait)
    mismatch = total_counts["mismatch"]
    reconciliation_result = {"total_combinations": total_counts["combinations"], "exact": total_counts["exact"], "mismatch": mismatch, "unknown": unknown, "exact_pct": 100.0 * total_counts["exact"] / total_counts["combinations"] if total_counts["combinations"] else 0.0, "tolerance": TOLERANCE, "difference_samples": mismatches[:25], "pass": mismatch == 0 and total_counts["combinations"] > 0}
    transfer_delta = total["transfer_oinm_net"] - total["transfer_wtr_net"]
    summary = {
        "gate": "TELCHI_BRANCH_REPLENISHMENT_CONTROLLED_SCALE_UP_V2",
        "level": level,
        "level_status": "PASS" if resource_result["status"] == "PASS" and reconciliation_result["pass"] and total_counts["continuity_violations"] == 0 and total_counts["continuity_gaps"] == 0 and abs(total["transfer_oinm_net"] - total["transfer_wtr_net"]) <= TOLERANCE else "DEGRADED",
        "functional_status": "DEGRADED",
        "context": {"ENTITY": "TELCHI", "DOMAIN": "REPOSICIÓN / STOCK_E_INVENTARIOS", "STAGE": "INVESTIGATION", "READ_ONLY": True, "SAP_WRITE_COUNT": 0, "product_filter": "ItemCode LIKE 'L%'"},
        "branches": config["branches"], "products": len(items), "days": config["days"], "date_start": start, "date_end": latest,
        "OINM_rows": int(total["oinm_rows"]), "input_rows": int(total["input_rows"]), "output_rows": int(total["warehouse_rows"] + total["branch_rows"] + total["demand_rows"] + total["replenishment_rows"] + total["episode_rows"]),
        "elapsed_seconds": round(elapsed, 4), "rows_per_second": round(total["input_rows"] / elapsed, 2) if elapsed else None,
        "rss_per_input_row_mb": round(resource_result["peak_rss_mb"] / total["input_rows"], 8) if total["input_rows"] else None,
        "checkpoint_size_mb": _checkpoint_size_mb(output), "resource_abort_count": resource_result["resource_abort_count"],
        "MAX_WORKERS": MAX_WORKERS, "resource_safety": resource_result,
        "reconciliation": reconciliation_result,
        "semantic_validation": {"transfer_event_qty_positive": total["transfer_event_qty"], "transfer_oinm_net_qty_active_doc_match": total["transfer_oinm_net"], "transfer_wtr_net_qty": total["transfer_wtr_net"], "transfer_delta": transfer_delta, "transfer_sales_separation": "PASS", "canceled_headers_audit": canceled, "continuity_gaps": total_counts["continuity_gaps"], "continuity_movement_violations": total_counts["continuity_violations"]},
        "counts": {"warehouse_stock_rows": int(total["warehouse_rows"]), "branch_stock_rows": int(total["branch_rows"]), "demand_rows": int(total["demand_rows"]), "replenishment_rows": int(total["replenishment_rows"]), "stockout_episode_rows": int(total["episode_rows"]), "batches": len(batches)},
        "stop_reason": None if resource_result["status"] == "PASS" and reconciliation_result["pass"] else "RESOURCE_OR_RECONCILIATION_GATE",
        "artifacts": ["level_discovery.json", "batch_metrics.jsonl", "resource_metrics.jsonl", "daily_item_warehouse_stock.jsonl.gz", "daily_item_branch_stock.jsonl.gz", "daily_branch_demand.jsonl.gz", "replenishment_events.jsonl.gz", "stockout_episodes.jsonl.gz", "level_result.json"],
    }
    _dump_json(output / "level_result.json", summary)
    return summary


def abort_level(output: Path, level: str, error: str) -> dict[str, Any]:
    result = {"gate": "TELCHI_BRANCH_REPLENISHMENT_CONTROLLED_SCALE_UP_V2", "level": level, "level_status": "RESOURCE_GUARD_ABORT", "functional_status": "DEGRADED", "RESOURCE_GUARD": "ENABLED", "MAX_WORKERS": MAX_WORKERS, "resource_abort_count": 1, "result": "RESOURCE_GUARD_ABORT", "error": error}
    _dump_json(output / "level_result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TELCHI controlled scale-up V2")
    parser.add_argument("--level", choices=LEVEL_ORDER, required=True)
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    level_output = args.output / f"level_{args.level}"
    level_output.mkdir(parents=True, exist_ok=True)
    conn = cur = None
    try:
        conn, cur = connect()
        result = run_level(cur, args.level, level_output)
    except ResourceGuardAbort as exc:
        result = abort_level(level_output, args.level, str(exc))
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 3 if result.get("level_status") == "RESOURCE_GUARD_ABORT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
