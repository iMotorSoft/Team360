"""TELCHI Gate 2/3: guarded sample for daily stock and observed demand.

The default execution is intentionally a *resource smoke test*: one branch,
up to ten L products with real activity, and at most 90 days.  It never
materializes the warehouse universe or the complete OINM table in Python.
HANA does the filtering and aggregation; the selected batch is checkpointed
outside Git before the next stage runs.

This runner is investigation-only and read-only.  It does not infer lost sales,
write SAP, or recommend a replenishment policy.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import resource
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.branch_replenishment.branch_replenishment_gate_v1 import (
    branch_for,
    jsonable,
    role,
    rows,
)
from modules.telchi.investigation.validation.branch_replenishment.stock_demand_domain import (
    availability_state,
    build_stockout_episodes,
    classify_censoring,
    days_of_supply,
    insufficient_history,
    movement_category,
    net_movement,
    reconcile_latest,
    reconstruct_inverse,
    replenishment_intervals,
    summarize_values,
    trailing_mean,
    validate_continuity,
)

GATE = "TELCHI_BRANCH_REPLENISHMENT_DAILY_STOCK_DEMAND_V1"
RESOURCE_SMOKE_GATE = "TELCHI_DAILY_STOCK_RESOURCE_SMOKE_TEST_V1_PASS"
DEFAULT_OUT = EVIDENCE_ROOT / "branch_replenishment_daily_stock_demand" / "v1"
TOLERANCE = 1e-6
MAX_WORKERS = 1
MIN_MEM_AVAILABLE_BYTES = 2 * 1024**3
DEFAULT_BRANCH = "2A"
DEFAULT_ITEM_LIMIT = 8
DEFAULT_DAYS = 90


class ResourceGuardAbort(RuntimeError):
    """Raised when continuing would violate the local resource safety gate."""


def _date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, raw = line.partition(":")
            parts = raw.strip().split()
            if parts and parts[0].isdigit():
                values[key] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    except OSError:
        pass
    return values


def _cpu_counters() -> tuple[int, int] | None:
    try:
        fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
        values = [int(x) for x in fields]
        return sum(values), values[4]
    except (OSError, IndexError, ValueError):
        return None


def _iowait_percent() -> float | None:
    counters = _cpu_counters()
    if counters is None:
        return None
    total, iowait = counters
    return (100.0 * iowait / total) if total else None


def _iowait_window_percent(interval: float = 0.1) -> float | None:
    before = _cpu_counters()
    if before is None:
        return None
    time.sleep(interval)
    after = _cpu_counters()
    if after is None:
        return None
    total_delta, iowait_delta = after[0] - before[0], after[1] - before[1]
    return (100.0 * iowait_delta / total_delta) if total_delta > 0 else 0.0


def resource_snapshot() -> dict[str, Any]:
    """Return cheap local metrics; never loads a dataset."""
    mem = _read_meminfo()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss_mb = float(usage.ru_maxrss) / 1024.0  # Linux reports KiB.
    load1 = None
    try:
        load1 = float(os.getloadavg()[0])
    except OSError:
        pass
    return {
        "mem_available_mb": round(mem.get("MemAvailable", 0) / 1024**2, 2),
        "swap_free_mb": round(mem.get("SwapFree", 0) / 1024**2, 2),
        "rss_mb": round(rss_mb, 2),
        "load1": load1,
        "iowait_percent_since_boot": _iowait_percent(),
        "iowait_percent_window": _iowait_window_percent(),
    }


def adaptive_batch_size(requested: int, snapshot: dict[str, Any] | None = None) -> int:
    """Reduce the sample automatically when available memory is tight."""
    if not 1 <= requested <= 10:
        raise ValueError("sample item limit must be between 1 and 10")
    snap = assert_resource_safe(snapshot)
    available = float(snap["mem_available_mb"])
    if available < 3 * 1024:
        return min(requested, 1)
    if available < 4 * 1024:
        return min(requested, 3)
    if available < 6 * 1024:
        return min(requested, 5)
    return min(requested, 10)


def assert_resource_safe(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = snapshot or resource_snapshot()
    if snapshot.get("mem_available_mb", 0) * 1024**2 < MIN_MEM_AVAILABLE_BYTES:
        raise ResourceGuardAbort(
            f"MemAvailable below 2 GiB: {snapshot.get('mem_available_mb')} MiB"
        )
    return snapshot


class ResourceGuard:
    """Single-worker guard with append-only per-partition metrics."""

    def __init__(self, output: Path):
        self.output = output
        self.output.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.initial_rss_mb = resource_snapshot()["rss_mb"]
        self.min_mem_available_mb: float | None = None
        self.peak_rss_mb = 0.0
        self.max_batch_rows = 0
        self.abort_count = 0
        self.high_iowait_windows = 0
        self.max_iowait_percent = 0.0

    def check(self, partition: str, rows_read: int, rows_written: int, batch_size: int) -> dict[str, Any]:
        started = time.monotonic()
        try:
            snap = assert_resource_safe()
            if snap["rss_mb"] - self.initial_rss_mb > 1024:
                raise ResourceGuardAbort("process RSS increased by more than 1 GiB")
            if snap.get("iowait_percent_window") is not None:
                self.max_iowait_percent = max(self.max_iowait_percent, float(snap["iowait_percent_window"]))
            if snap.get("iowait_percent_window") is not None and snap["iowait_percent_window"] > 50:
                self.high_iowait_windows += 1
            else:
                self.high_iowait_windows = 0
            if self.high_iowait_windows >= 2:
                raise ResourceGuardAbort("sustained high iowait detected")
        except ResourceGuardAbort:
            self.abort_count += 1
            raise
        self.min_mem_available_mb = (
            snap["mem_available_mb"]
            if self.min_mem_available_mb is None
            else min(self.min_mem_available_mb, snap["mem_available_mb"])
        )
        self.peak_rss_mb = max(self.peak_rss_mb, snap["rss_mb"])
        self.max_batch_rows = max(self.max_batch_rows, rows_read, rows_written)
        metric = {
            "rows_read": rows_read,
            "rows_written": rows_written,
            "elapsed_seconds": round(time.monotonic() - started, 4),
            "peak_rss_mb": self.peak_rss_mb,
            "mem_available_min_mb": self.min_mem_available_mb,
            "batch_size": batch_size,
            "partition": partition,
            "result": "PASS",
            "snapshot": snap,
        }
        with (self.output / "resource_metrics.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(metric, ensure_ascii=False) + "\n")
        return metric

    def summary(self) -> dict[str, Any]:
        snap = resource_snapshot()
        return {
            "status": "PASS",
            "RESOURCE_GUARD": "ENABLED",
            "MAX_WORKERS": MAX_WORKERS,
            "peak_rss_mb": max(self.peak_rss_mb, snap["rss_mb"]),
            "min_mem_available_mb": self.min_mem_available_mb,
            "max_batch_rows": self.max_batch_rows,
            "resource_abort_count": self.abort_count,
            "high_iowait_windows": self.high_iowait_windows,
            "max_iowait_percent": self.max_iowait_percent,
            "final_snapshot": snap,
        }


def _dump_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(jsonable(value), ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> int:
    count = 0
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for value in values:
            fh.write(json.dumps(jsonable(value), ensure_ascii=False) + "\n")
            count += 1
    return count


def _write_warehouse_jsonl(
    path: Path,
    warehouse_stock: dict[tuple[str, str], dict[date, float]],
    branch_sales: dict[str, str],
) -> int:
    def stream() -> Iterable[dict[str, Any]]:
        for (item, warehouse), series in sorted(warehouse_stock.items()):
            for day, stock in sorted(series.items()):
                yield {
                    "ItemCode": item,
                    "Warehouse": warehouse,
                    "Date": day,
                    "StockEndOfDay": stock,
                    "Branch": branch_sales.get(warehouse),
                    "warehouse_role": "BRANCH_SALES",
                }

    return _write_jsonl(path, stream())


def _in_clause(values: list[str]) -> str:
    if not values:
        raise ValueError("empty SQL filter is not allowed")
    return ",".join("?" for _ in values)


def sample_warehouse_context(
    cur: Any, requested_branch: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Load the tiny warehouse master only; do not aggregate OINM here."""
    master = rows(cur, '''SELECT "WhsCode" AS code,"WhsName" AS name,"U_TYPE" AS u_type,
        "U_WAREHOUSE_DMS" AS dms,"BPLid" AS bplid FROM "TELCHI"."OWHS"
        ORDER BY "WhsCode"''')
    info: dict[str, dict[str, Any]] = {}
    branch_sales: dict[str, str] = {}
    wanted = requested_branch.upper()
    for raw in master:
        code = str(raw["code"])
        op_role, evidence = role(code, raw.get("name"), raw.get("u_type"), raw.get("dms"))
        branch_id, branch_name, confidence = branch_for(code)
        record = {
            **raw,
            "code": code,
            "role": op_role,
            "role_evidence": evidence,
            "branch_id": branch_id,
            "branch_name": branch_name,
            "branch_confidence": confidence,
        }
        info[code] = record
        if op_role == "BRANCH_SALES" and branch_id == wanted:
            branch_sales[code] = branch_id
    if not branch_sales:
        raise ValueError(f"no BRANCH_SALES warehouse found for branch {requested_branch!r}")
    return info, branch_sales


def latest_date_for_branch(cur: Any, warehouses: list[str]) -> date:
    ph = _in_clause(warehouses)
    result = rows(cur, f'''SELECT MAX("DocDate") AS last_date FROM "TELCHI"."OINM"
        WHERE "ItemCode" LIKE 'L%' AND "Warehouse" IN ({ph})
          AND (COALESCE("InQty",0)<>0 OR COALESCE("OutQty",0)<>0)''', tuple(warehouses))
    if not result or result[0].get("last_date") is None:
        raise RuntimeError("selected branch has no L-product OINM movement")
    return _date(result[0]["last_date"])


def select_sample_items(
    cur: Any, warehouses: list[str], start: date, end: date, limit: int,
) -> list[str]:
    if not 1 <= limit <= 10:
        raise ValueError("sample item limit must be between 1 and 10")
    ph = _in_clause(warehouses)
    result = rows(cur, f'''SELECT "ItemCode" AS item_code,
          SUM(ABS(COALESCE("InQty",0))+ABS(COALESCE("OutQty",0))) AS activity,
          COUNT(*) AS source_rows
        FROM "TELCHI"."OINM"
        WHERE "ItemCode" LIKE 'L%' AND "Warehouse" IN ({ph})
          AND "DocDate" BETWEEN ? AND ?
          AND (COALESCE("InQty",0)<>0 OR COALESCE("OutQty",0)<>0)
        GROUP BY "ItemCode" ORDER BY activity DESC LIMIT {int(limit)}''',
        tuple(warehouses) + (start, end))
    return [str(r["item_code"]) for r in result]


def extract_current(cur: Any, item_codes: list[str], warehouses: list[str]) -> dict[tuple[str, str], float]:
    items, whs = _in_clause(item_codes), _in_clause(warehouses)
    result = rows(cur, f'''SELECT "ItemCode" AS item_code,"WhsCode" AS warehouse,"OnHand" AS on_hand
        FROM "TELCHI"."OITW" WHERE "ItemCode" IN ({items}) AND "WhsCode" IN ({whs})''',
        tuple(item_codes) + tuple(warehouses))
    return {(str(r["item_code"]), str(r["warehouse"])): float(r["on_hand"] or 0) for r in result}


def extract_movements(
    cur: Any, item_codes: list[str], warehouses: list[str], start: date, end: date,
) -> list[dict[str, Any]]:
    items, whs = _in_clause(item_codes), _in_clause(warehouses)
    return rows(cur, f'''SELECT "ItemCode" AS item_code,"Warehouse" AS warehouse,
          "DocDate" AS doc_date,"TransType" AS trans_type,
          SUM(COALESCE("InQty",0)) AS in_qty,SUM(COALESCE("OutQty",0)) AS out_qty,
          SUM(COALESCE("TransValue",0)) AS trans_value,COUNT(*) AS source_rows
        FROM "TELCHI"."OINM"
        WHERE "ItemCode" IN ({items}) AND "Warehouse" IN ({whs})
          AND "DocDate" BETWEEN ? AND ?
          AND (COALESCE("InQty",0)<>0 OR COALESCE("OutQty",0)<>0)
        GROUP BY "ItemCode","Warehouse","DocDate","TransType"
        ORDER BY "ItemCode","Warehouse","DocDate","TransType"''',
        tuple(item_codes) + tuple(warehouses) + (start, end))


def extract_atomic_audit(
    cur: Any, item_codes: list[str], warehouses: list[str], start: date, end: date,
) -> dict[str, Any]:
    items, whs = _in_clause(item_codes), _in_clause(warehouses)
    params = tuple(item_codes) + tuple(warehouses) + (start, end)
    summary = rows(cur, f'''SELECT COUNT(*) AS rows_count,COUNT(DISTINCT "TransNum") AS transnums,
        MIN("DocDate") AS first_date,MAX("DocDate") AS last_date,
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
    canceled_rows = rows(cur, '''SELECT 'OINV' AS table_name,COUNT(*) AS canceled FROM "TELCHI"."OINV" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'ORIN',COUNT(*) FROM "TELCHI"."ORIN" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'ODLN',COUNT(*) FROM "TELCHI"."ODLN" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'OWTR',COUNT(*) FROM "TELCHI"."OWTR" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'OIGN',COUNT(*) FROM "TELCHI"."OIGN" WHERE "CANCELED"='Y'
        UNION ALL SELECT 'OIGE',COUNT(*) FROM "TELCHI"."OIGE" WHERE "CANCELED"='Y' ''')
    return {
        "oinm": summary,
        "by_transtype": by_type,
        "canceled_headers": {str(r["table_name"]): int(r["canceled"] or 0) for r in canceled_rows},
        "grain": "TransNum atomic; grouped projection is selected ItemCode×Warehouse×DocDate×TransType",
        "scope": {"items": item_codes, "warehouses": warehouses, "start": start, "end": end},
    }


def extract_transfer_events(
    cur: Any, branch_sales: dict[str, str], info: dict[str, dict[str, Any]],
    item_codes: list[str], start: date, end: date,
) -> list[dict[str, Any]]:
    items, destinations = _in_clause(item_codes), _in_clause(list(branch_sales))
    raw = rows(cur, f'''SELECT O."DocEntry" AS doc_entry,O."DocNum" AS doc_num,O."DocDate" AS doc_date,
          W."LineNum" AS line_num,W."ItemCode" AS item_code,W."FromWhsCod" AS origin,
          W."WhsCode" AS destination,W."Quantity" AS quantity
        FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
        WHERE O."CANCELED"='N' AND W."ItemCode" IN ({items})
          AND W."WhsCode" IN ({destinations}) AND O."DocDate" BETWEEN ? AND ?
          AND W."Quantity"<>0
        ORDER BY W."ItemCode",W."WhsCode",O."DocDate",O."DocEntry",W."LineNum"''',
        tuple(item_codes) + tuple(branch_sales) + (start, end))
    out = []
    for r in raw:
        quantity = float(r["quantity"] or 0)
        destination = str(r["destination"])
        if quantity <= 0:
            continue
        origin = str(r["origin"])
        source_role = info.get(origin, {}).get("role", "UNKNOWN")
        source_branch = info.get(origin, {}).get("branch_id")
        source_type = {
            "CENTRAL": "TRANSFER_FROM_CENTRAL", "TRANSIT": "TRANSFER_FROM_TRANSIT",
            "FINISHED_GOODS": "TRANSFER_FROM_FINISHED_GOODS", "BRANCH_SALES": "TRANSFER_FROM_BRANCH",
            "PRODUCTION": "PRODUCTION_DIRECT",
        }.get(source_role, "TRANSFER_FROM_OTHER")
        out.append({
            "ItemCode": str(r["item_code"]), "Branch": branch_sales[destination], "Warehouse": destination,
            "Date": _date(r["doc_date"]), "DocEntry": r["doc_entry"], "DocNum": r["doc_num"],
            "LineNum": r["line_num"], "OriginWarehouse": origin, "OriginBranch": source_branch,
            "SourceRole": source_role, "SourceType": source_type, "ReplenishmentQty": quantity,
        })
    return out


def build_warehouse_stock(
    current: dict[tuple[str, str], float], movement_rows: list[dict[str, Any]], start: date, end: date,
) -> tuple[dict[tuple[str, str], dict[date, float]], dict[str, Any]]:
    daily: dict[tuple[str, str], dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for row in movement_rows:
        key = (str(row["item_code"]), str(row["warehouse"]))
        daily[key][_date(row["doc_date"])] += net_movement(row)
    keys = set(current) | set(daily)
    reconstructed: dict[tuple[str, str], dict[date, float]] = {}
    continuity = {"series": 0, "days": 0, "gaps": 0, "movement_violations": 0}
    for key in keys:
        series = reconstruct_inverse(float(current.get(key, 0.0)), daily.get(key, {}), start, end)
        reconstructed[key] = series
        check = validate_continuity(series, daily.get(key, {}), TOLERANCE)
        continuity["series"] += 1
        continuity["days"] += check["days"]
        continuity["gaps"] += check["gaps"]
        continuity["movement_violations"] += len(check["movement_violations"])
    return reconstructed, continuity


def build_branch_daily(
    branch_sales: dict[str, str], warehouse_stock: dict[tuple[str, str], dict[date, float]],
    movement_rows: list[dict[str, Any]], transfers: list[dict[str, Any]], start: date, end: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    wh_by_branch: dict[str, list[str]] = defaultdict(list)
    for warehouse, branch in branch_sales.items():
        wh_by_branch[branch].append(warehouse)
    movement_daily: dict[tuple[str, str, date], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in movement_rows:
        warehouse = str(row["warehouse"])
        branch = branch_sales.get(warehouse)
        if not branch:
            continue
        day = _date(row["doc_date"])
        category = movement_category(row["trans_type"])
        key = (str(row["item_code"]), branch, day)
        qty_in, qty_out = float(row["in_qty"] or 0), float(row["out_qty"] or 0)
        movement_daily[key]["net_movement"] += qty_in - qty_out
        movement_daily[key]["in_qty"] += qty_in
        movement_daily[key]["out_qty"] += qty_out
        movement_daily[key][category + "_IN"] += qty_in
        movement_daily[key][category + "_OUT"] += qty_out
    transfer_daily: dict[tuple[str, str, date], float] = defaultdict(float)
    for event in transfers:
        transfer_daily[(event["ItemCode"], event["Branch"], event["Date"])] += event["ReplenishmentQty"]
    keys = {(item, branch) for item, branch, _ in movement_daily}
    keys.update((item, branch_sales[warehouse]) for item, warehouse in warehouse_stock if warehouse in branch_sales)
    stock_rows: list[dict[str, Any]] = []
    demand_rows: list[dict[str, Any]] = []
    all_days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    for item, branch in sorted(keys):
        warehouses = wh_by_branch[branch]
        for day in all_days:
            stock = sum(warehouse_stock.get((item, wh), {}).get(day, 0.0) for wh in warehouses)
            facts = movement_daily.get((item, branch, day), {})
            gross, returns = facts.get("SALES_OUT", 0.0), facts.get("RETURNS_IN", 0.0)
            stockout = "CONFIRMED_STOCKOUT" if stock <= TOLERANCE else "NO_STOCKOUT"
            row = {
                "ItemCode": item, "Branch": branch, "Date": day, "StockEndOfDay": stock,
                "AVAILABLE_BRANCH_STOCK": stock, "IN_TRANSIT_STOCK": 0.0,
                "availability_state": availability_state(stock), "stockout_classification": stockout,
                "BRANCH_STOCK_CONFIDENCE": "EXACT",
                "GROSS_SALES_QTY": gross, "RETURNS_QTY": returns, "NET_SALES_QTY": gross - returns,
                "TRANSFER_IN_QTY": transfer_daily.get((item, branch, day), 0.0),
                "NET_MOVEMENT_QTY": facts.get("net_movement", 0.0),
                "OTHER_IN_QTY": facts.get("OTHER_IN", 0.0), "OTHER_OUT_QTY": facts.get("OTHER_OUT", 0.0),
            }
            row["censoring_classification"] = classify_censoring(
                stock, row["NET_SALES_QTY"], False, False, row["TRANSFER_IN_QTY"] > 0
            )
            stock_rows.append(row)
            demand_rows.append({**row, "OBSERVED_DEMAND": row["NET_SALES_QTY"]})
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in stock_rows:
        grouped[(row["ItemCode"], row["Branch"])].append(row)
    demand_by_key = {(r["ItemCode"], r["Branch"], r["Date"]): r for r in demand_rows}
    for group in grouped.values():
        group.sort(key=lambda x: x["Date"])
        for index, row in enumerate(group):
            pre, post = group[max(0, index - 30):index], group[index + 1:index + 31]
            classification = classify_censoring(
                row["StockEndOfDay"], row["NET_SALES_QTY"],
                any(x["NET_SALES_QTY"] > 0 for x in pre),
                any(x["NET_SALES_QTY"] > 0 for x in post),
                any(x["TRANSFER_IN_QTY"] > 0 for x in post),
            )
            row["censoring_classification"] = classification
            demand_by_key[(row["ItemCode"], row["Branch"], row["Date"])] ["censoring_classification"] = classification
    return stock_rows, demand_rows


def replenishment_output(
    transfers: list[dict[str, Any]], stock_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key = {(r["ItemCode"], r["Branch"], r["Date"]): r for r in stock_rows}
    by_item_branch: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    events = []
    for event in transfers:
        key = (event["ItemCode"], event["Branch"])
        previous_events = by_item_branch[key]
        before = by_key.get((event["ItemCode"], event["Branch"], event["Date"] - timedelta(days=1)))
        current = by_key.get((event["ItemCode"], event["Branch"], event["Date"]))
        event_row = {
            **event,
            "StockBeforeReplenishment": before.get("StockEndOfDay") if before else None,
            "StockAfterReplenishment": current.get("StockEndOfDay") if current else None,
            "Sales7dBefore": sum(float(by_key.get((event["ItemCode"], event["Branch"], event["Date"] - timedelta(days=i)), {}).get("NET_SALES_QTY", 0) or 0) for i in range(1, 8)),
            "Sales30dBefore": sum(float(by_key.get((event["ItemCode"], event["Branch"], event["Date"] - timedelta(days=i)), {}).get("NET_SALES_QTY", 0) or 0) for i in range(1, 31)),
            "DaysSincePreviousReplenishment": (event["Date"] - previous_events[-1]["Date"]).days if previous_events else None,
            "REPLENISHMENT_EVENT": event["SourceType"] != "TRANSFER_FROM_OTHER",
            "confidence": "HEURISTIC" if event["SourceType"] == "TRANSFER_FROM_OTHER" else "VALIDATED_SOURCE_ROLE",
        }
        events.append(event_row)
        by_item_branch[key].append(event_row)
    return events, {
        "size": summarize_values(e["ReplenishmentQty"] for e in events),
        "intervals_by_item_branch": {str(key): replenishment_intervals(value) for key, value in by_item_branch.items()},
    }


def build_gate(
    cur: Any, output: Path, branch_id: str = DEFAULT_BRANCH,
    item_limit: int = DEFAULT_ITEM_LIMIT, days: int = DEFAULT_DAYS,
) -> dict[str, Any]:
    if days < 60 or days > 90:
        raise ValueError("resource smoke window must be between 60 and 90 days")
    guard = ResourceGuard(output)
    initial_snapshot = assert_resource_safe()
    effective_item_limit = adaptive_batch_size(item_limit, initial_snapshot)
    guard.check("resource_check", 0, 0, effective_item_limit)
    info, branch_sales = sample_warehouse_context(cur, branch_id)
    warehouses = sorted(branch_sales)
    latest = latest_date_for_branch(cur, warehouses)
    start = latest - timedelta(days=days - 1)
    item_codes = select_sample_items(cur, warehouses, start, latest, effective_item_limit)
    if not item_codes:
        raise RuntimeError("sample query returned no L products")
    guard.check("sample_discovery", len(item_codes), 0, effective_item_limit)

    current = extract_current(cur, item_codes, warehouses)
    movements = extract_movements(cur, item_codes, warehouses, start, latest)
    guard.check("branch_date_item_batch", len(movements), len(current), effective_item_limit)
    checkpoint = output / "checkpoint_branch_date_item.json"
    _dump_json(checkpoint, {"branch": branch_id, "warehouses": warehouses, "items": item_codes, "start": start, "end": latest, "movement_rows": len(movements), "current_rows": len(current)})

    transfers = extract_transfer_events(cur, branch_sales, info, item_codes, start, latest)
    atomic = extract_atomic_audit(cur, item_codes, warehouses, start, latest)
    guard.check("transfer_and_atomic_audit", len(transfers) + int(atomic["oinm"]["rows_count"] or 0), 0, effective_item_limit)
    branch_current = {key: value for key, value in current.items() if key[1] in branch_sales}
    branch_movements = [r for r in movements if str(r["warehouse"]) in branch_sales]
    warehouse_stock, continuity = build_warehouse_stock(branch_current, branch_movements, start, latest)
    reconciliation = reconcile_latest(warehouse_stock, branch_current, TOLERANCE)
    stock_rows, demand_rows = build_branch_daily(branch_sales, warehouse_stock, branch_movements, transfers, start, latest)
    episodes = build_stockout_episodes(stock_rows)
    replenishments, replenishment_summary = replenishment_output(transfers, stock_rows)
    guard.check("reconstruction_and_outputs", len(stock_rows), len(replenishments), effective_item_limit)

    categories: dict[str, dict[str, float]] = defaultdict(lambda: {"rows": 0, "in_qty": 0.0, "out_qty": 0.0})
    for row in movements:
        category = movement_category(row["trans_type"])
        categories[category]["rows"] += int(row["source_rows"] or 0)
        categories[category]["in_qty"] += float(row["in_qty"] or 0)
        categories[category]["out_qty"] += float(row["out_qty"] or 0)
    status_counts: dict[str, int] = defaultdict(int)
    censor_counts: dict[str, int] = defaultdict(int)
    for row in stock_rows:
        status_counts[row["availability_state"]] += 1
        censor_counts[row["censoring_classification"]] += 1

    warehouse_rows = _write_warehouse_jsonl(output / "daily_item_warehouse_stock.jsonl.gz", warehouse_stock, branch_sales)
    branch_rows = _write_jsonl(output / "daily_item_branch_stock.jsonl.gz", stock_rows)
    demand_count = _write_jsonl(output / "daily_branch_demand.jsonl.gz", demand_rows)
    replenishment_count = _write_jsonl(output / "replenishment_events.jsonl.gz", replenishments)
    _dump_json(output / "stockout_episodes.json", episodes)
    _dump_json(output / "reconciliation.json", reconciliation)
    resource_result = guard.summary()
    result = {
        "gate": GATE,
        "context": {"ENTITY": "TELCHI", "DOMAIN": "REPOSICIÓN / STOCK_E_INVENTARIOS", "STAGE": "INVESTIGATION", "SOURCES": ["SAP_HANA", "DATA_LAKE"], "READ_ONLY": True, "SAP_WRITE_COUNT": 0, "product_filter": "ItemCode LIKE 'L%'"},
        "verdict": "DEGRADED",
        "smoke_gate": RESOURCE_SMOKE_GATE,
        "sample_only": True,
        "degraded_causes": [
            "SAMPLE_ONLY_NO_UNIVERSE_EXPANSION",
            "CANCELLATION_DOCUMENT_LINKAGE_REQUIRES_PER_TRANSTYPE_RECONCILIATION",
            "LOW_STOCK_THRESHOLD_PENDING_POLICY",
            "IN_TRANSIT_ALLOCATION_UNRESOLVED_FOR_UNASSIGNED_TRANSIT_WAREHOUSES",
            "LOST_SALES_NOT_IMPUTED",
        ],
        "resource_safety": resource_result,
        "batch": {"branch": branch_id, "warehouses": warehouses, "items": item_codes, "date_start": start, "date_end": latest, "days": days, "requested_batch_size": item_limit, "batch_size": effective_item_limit, "MAX_WORKERS": MAX_WORKERS},
        "reliability": {"FIRST_RELIABLE_DATE": start, "LAST_RELIABLE_DATE": latest, "model": "inverse_current_on_hand_anchor", "no_zero_opening_assumption": True, "stock_reconciliation_scope": "selected BRANCH_SALES sample"},
        "coverage": {"l_products": len(item_codes), "branches": 1, "branch_sales_warehouses": len(branch_sales), "movement_source_rows": sum(int(r["source_rows"] or 0) for r in movements), "movement_projection_rows": len(movements), "daily_item_warehouse_stock_rows": warehouse_rows, "daily_branch_stock_rows": branch_rows, "daily_demand_rows": demand_count, "replenishment_rows": replenishment_count, "date_start": start, "date_end": latest},
        "reconciliation": reconciliation,
        "continuity": continuity,
        "movement_categories": dict(categories),
        "availability_state_counts": dict(status_counts),
        "censoring_counts": dict(censor_counts),
        "stockout": {"episodes": len(episodes), "duration": summarize_values(e["DurationDays"] for e in episodes), "classification": {"CONFIRMED_STOCKOUT_DAYS": sum(1 for r in stock_rows if r["stockout_classification"] == "CONFIRMED_STOCKOUT"), "POSSIBLE_CENSORED_DEMAND_EPISODES": sum(1 for e in episodes if e["DemandClassification"] == "POSSIBLE_CENSORED_DEMAND"), "UNPROVEN_CENSORED_DEMAND_EPISODES": sum(1 for e in episodes if e["DemandClassification"] == "UNPROVEN_CENSORED_DEMAND")}},
        "replenishment": {"events": len(replenishments), **replenishment_summary},
        "atomic_audit": atomic,
        "data_quality": {"sample_guard": "PASS", "low_stock": "PENDING_POLICY_THRESHOLD", "lost_sales": "NOT_IMPUTED", "in_transit": "SEPARATE_FROM_AVAILABLE_BRANCH_STOCK"},
        "artifacts": ["checkpoint_branch_date_item.json", "resource_metrics.jsonl", "daily_item_warehouse_stock.jsonl.gz", "daily_item_branch_stock.jsonl.gz", "daily_branch_demand.jsonl.gz", "replenishment_events.jsonl.gz", "stockout_episodes.json", "reconciliation.json", "gate_result.json"],
        "next_gate": "GATE 4 — BASELINE CUANTITATIVO + LEAD TIME OPERATIVO",
    }
    _dump_json(output / "gate_result.json", result)
    return result


def _abort_result(output: Path, error: str) -> dict[str, Any]:
    result = {
        "gate": GATE,
        "verdict": "DEGRADED",
        "result": "RESOURCE_GUARD_ABORT",
        "RESOURCE_GUARD": "ENABLED",
        "MAX_WORKERS": MAX_WORKERS,
        "error": error,
        "resource_safety": {"status": "RESOURCE_GUARD_ABORT", "abort_count": 1, "snapshot": resource_snapshot()},
    }
    _dump_json(output / "gate_result.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded Telchi branch stock/demand smoke test")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--items", type=int, default=DEFAULT_ITEM_LIMIT)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    conn = cur = None
    try:
        assert_resource_safe()
        conn, cur = connect()
        result = build_gate(cur, args.output, args.branch, args.items, args.days)
    except ResourceGuardAbort as exc:
        result = _abort_result(args.output, str(exc))
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
    print(json.dumps(jsonable({"gate": result["gate"], "verdict": result["verdict"], "result": result.get("result", "DEGRADED"), "resource_safety": result.get("resource_safety"), "coverage": result.get("coverage"), "reconciliation": result.get("reconciliation"), "output": str(args.output)}), ensure_ascii=False, indent=2))
    return 3 if result.get("result") == "RESOURCE_GUARD_ABORT" else 0


if __name__ == "__main__":
    sys.exit(main())
