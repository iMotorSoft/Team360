"""Run TELCHI Gate 4 over the reconciled scale-up evidence.

The default input is the external Level E dataset (2A + CM, 365 days). HANA
is queried read-only only for event-category and accounting-lead-time audits.
No physical lead time is inferred when SAP timestamps are simultaneous.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.branch_replenishment.branch_replenishment_gate_v1 import (
    rows, role,
)
from modules.telchi.investigation.validation.branch_replenishment.current_policy_baseline_v1 import (
    build_current_policy_baseline,
)
from modules.telchi.investigation.validation.branch_replenishment.daily_stock_demand_v1 import (
    ResourceGuard, ResourceGuardAbort, _in_clause, _dump_json, resource_snapshot,
)
from modules.telchi.investigation.validation.branch_replenishment.stock_demand_domain import movement_category

DEFAULT_INPUT = EVIDENCE_ROOT / "branch_replenishment_daily_stock_demand" / "v2_scale_up" / "level_E"
DEFAULT_OUTPUT = EVIDENCE_ROOT / "branch_replenishment_current_policy_baseline" / "v1"
BRANCHES = ("2A", "CM")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_stock_index(path: Path) -> tuple[dict[tuple[str, str], dict[date, tuple[float, float, float]]], int]:
    """Load only fields required by Gate 4 into compact tuples.

    Keeping the 639k daily projections as JSON dictionaries breaches the
    existing +1 GiB RSS guard.  This representation is intentionally limited
    to stock, observed demand and net movement.
    """
    index: dict[tuple[str, str], dict[date, tuple[float, float, float]]] = defaultdict(dict)
    count = 0
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (str(row["ItemCode"]), str(row["Branch"]))
            day = date.fromisoformat(str(row["Date"])[:10])
            index[key][day] = (float(row.get("StockEndOfDay") or 0), float(row.get("NET_SALES_QTY") or row.get("OBSERVED_DEMAND") or 0), float(row.get("NET_MOVEMENT_QTY") or 0))
            count += 1
    return index, count


def _canonicalize_event_category(event: dict[str, Any]) -> dict[str, Any]:
    source = str(event.get("SourceType") or "")
    category = {
        "TRANSFER_FROM_CENTRAL": "CENTRAL_TRANSFER",
        "TRANSFER_FROM_BRANCH": "BRANCH_TRANSFER",
        "TRANSFER_FROM_TRANSIT": "TRANSIT_TRANSFER",
        "TRANSFER_FROM_FINISHED_GOODS": "OTHER_LOGISTIC_IN",
        "TRANSFER_FROM_OTHER": "OTHER_LOGISTIC_IN",
        "PRODUCTION_DIRECT": "PRODUCTION_IN",
        "PRODUCTION_IN": "PRODUCTION_IN",
        "PURCHASE_IN": "PURCHASE_IN",
        "OTHER_LOGISTIC_IN": "OTHER_LOGISTIC_IN",
    }.get(source, "OTHER_LOGISTIC_IN")
    return {**event, "EventCategory": category}


def _write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        count = 0
        for value in values:
            fh.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def _sap_timestamp(day: Any, raw_time: Any) -> datetime | None:
    if day is None:
        return None
    if isinstance(day, datetime):
        day = day.date()
    elif not isinstance(day, date):
        day = date.fromisoformat(str(day)[:10])
    try:
        value = int(raw_time or 0)
        text = f"{value:06d}"
        return datetime.combine(day, time(int(text[:2]), int(text[2:4]), int(text[4:6])))
    except (TypeError, ValueError):
        return None


def _stats(days: list[float]) -> dict[str, Any]:
    if not days:
        return {"count": 0, "mean": None, "median": None, "p90": None, "max": None}
    values = sorted(days)
    def percentile(p: float) -> float:
        pos = (len(values) - 1) * p
        lo, hi = int(pos), min(int(pos) + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (pos - lo)
    return {"count": len(values), "mean": sum(values) / len(values), "median": percentile(.5), "p90": percentile(.9), "max": values[-1]}


def accounting_lead_time(cur: Any, branches: dict[str, str], items: list[str], start: date, end: date) -> dict[str, Any]:
    """Match transfer lines to OINM on document, line, item and warehouse.

    OWTR and both OINM sides use the same DocDate/DocTime in this database;
    equality is intentionally reported as NOT_OBSERVABLE, not as a physical
    zero-day transit time.
    """
    destinations = list(branches)
    ph_items, ph_dest = _in_clause(items), _in_clause(destinations)
    query = f'''SELECT O."DocEntry" AS doc_entry,O."DocNum" AS doc_num,O."DocDate" AS source_date,
        O."DocTime" AS source_time,O."CreateDate" AS source_create_date,O."CreateTS" AS source_create_ts,
        W."LineNum" AS line_num,W."ItemCode" AS item_code,W."FromWhsCod" AS origin,W."WhsCode" AS destination,
        W."Quantity" AS quantity,M."TransNum" AS trans_num,M."Warehouse" AS movement_warehouse,
        M."DocDate" AS movement_date,M."DocTime" AS movement_time,M."DocLineNum" AS movement_line,
        M."BaseLine" AS movement_base_line,M."InQty" AS in_qty,M."OutQty" AS out_qty
      FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
      LEFT JOIN "TELCHI"."OINM" M ON M."TransType"=67
        AND M."BASE_REF"=CAST(O."DocNum" AS NVARCHAR(20)) AND M."ItemCode"=W."ItemCode"
        AND M."Warehouse" IN (W."FromWhsCod",W."WhsCode")
        AND (M."DocLineNum"=W."LineNum" OR M."BaseLine"=W."LineNum")
      WHERE O."CANCELED"='N' AND W."ItemCode" IN ({ph_items}) AND W."WhsCode" IN ({ph_dest})
        AND W."Quantity">0 AND O."DocDate" BETWEEN ? AND ?
      ORDER BY O."DocEntry",W."LineNum",M."TransNum"'''
    raw = rows(cur, query, tuple(items) + tuple(destinations) + (start, end))
    by_line: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in raw:
        key = (row["doc_entry"], row["line_num"])
        event = by_line.setdefault(key, {"doc_entry": row["doc_entry"], "doc_num": row["doc_num"], "line_num": row["line_num"], "item_code": row["item_code"], "origin": row["origin"], "destination": row["destination"], "quantity": float(row["quantity"] or 0), "source_timestamp": _sap_timestamp(row["source_date"], row["source_time"]), "source_create_date": row["source_create_date"], "source_create_ts": row["source_create_ts"], "movements": []})
        if row.get("trans_num") is not None and (row["movement_date"] is not None):
            movement = {"trans_num": row["trans_num"], "warehouse": row["movement_warehouse"], "timestamp": _sap_timestamp(row["movement_date"], row["movement_time"]), "in_qty": float(row["in_qty"] or 0), "out_qty": float(row["out_qty"] or 0), "line": row["movement_line"], "base_line": row["movement_base_line"]}
            if movement not in event["movements"]:
                event["movements"].append(movement)
    observations: list[dict[str, Any]] = []
    status_counts: dict[str, int] = defaultdict(int)
    for event in by_line.values():
        source = event["source_timestamp"]
        source_rows = [m for m in event["movements"] if m["warehouse"] == event["origin"]]
        destination_rows = [m for m in event["movements"] if m["warehouse"] == event["destination"]]
        # Require OINM evidence on both sides. OWTR.DocDate/DocTime is kept
        # as document metadata but is not substituted for origin accounting.
        source_ts = max((m["timestamp"] for m in source_rows if m["timestamp"]), default=None)
        destination_ts = min((m["timestamp"] for m in destination_rows if m["timestamp"]), default=None)
        if source_ts is None or destination_ts is None:
            status = "ACCOUNTING_LEAD_TIME_NOT_OBSERVABLE_MISSING_SIDE"
            days = None
        elif destination_ts == source_ts:
            status = "ACCOUNTING_LEAD_TIME_NOT_OBSERVABLE_SIMULTANEOUS"
            days = 0.0
        elif destination_ts > source_ts:
            status = "ACCOUNTING_LEAD_TIME_OBSERVABLE"
            days = (destination_ts - source_ts).total_seconds() / 86400
        else:
            status = "ACCOUNTING_LEAD_TIME_ANOMALY_DESTINATION_PRECEDES_ORIGIN"
            days = (destination_ts - source_ts).total_seconds() / 86400
        status_counts[status] += 1
        observations.append({**{k: event[k] for k in ("doc_entry", "doc_num", "line_num", "item_code", "origin", "destination", "quantity")}, "origin_timestamp": source_ts, "destination_timestamp": destination_ts, "accounting_lead_time_days": days, "status": status, "match_rows": len(event["movements"])})
    measured = [float(x["accounting_lead_time_days"]) for x in observations if x["status"] == "ACCOUNTING_LEAD_TIME_OBSERVABLE"]
    status = "ACCOUNTING_LEAD_TIME_NOT_OBSERVABLE" if not measured else "ACCOUNTING_LEAD_TIME_OBSERVABLE_WITH_NOT_OBSERVABLE_CASES"
    return {"status": status, "observations": observations, "status_counts": dict(status_counts), "measured_days": _stats(measured), "matching": {"transfer_lines": len(by_line), "with_destination_oinm": sum(x["destination_timestamp"] is not None for x in observations), "with_both_sides": sum(x["status"] != "ACCOUNTING_LEAD_TIME_NOT_OBSERVABLE_MISSING_SIDE" for x in observations)}}


def non_transfer_events(cur: Any, branches: dict[str, str], items: list[str], start: date, end: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ph_items, ph_whs = _in_clause(items), _in_clause(list(branches))
    raw = rows(cur, f'''SELECT "ItemCode" AS item_code,"Warehouse" AS warehouse,"DocDate" AS doc_date,
        "TransType" AS trans_type,SUM("InQty") AS in_qty,SUM("OutQty") AS out_qty,COUNT(*) AS source_rows
      FROM "TELCHI"."OINM" WHERE "ItemCode" IN ({ph_items}) AND "Warehouse" IN ({ph_whs})
        AND "DocDate" BETWEEN ? AND ? AND "TransType"<>67
        AND "InQty">0 GROUP BY "ItemCode","Warehouse","DocDate","TransType"''', tuple(items) + tuple(branches) + (start, end))
    events = []
    categories: dict[str, dict[str, float]] = defaultdict(lambda: {"rows": 0, "in_qty": 0.0, "out_qty": 0.0})
    for row in raw:
        category = movement_category(row["trans_type"])
        categories[category]["rows"] += int(row["source_rows"] or 0)
        categories[category]["in_qty"] += float(row["in_qty"] or 0)
        categories[category]["out_qty"] += float(row["out_qty"] or 0)
        # Returns and sales are audited as movements but are not a
        # replenishment source under this gate's physical-source definition.
        if category not in {"PRODUCTION_IN", "PURCHASE_IN", "OTHER"}:
            continue
        branch = branches[str(row["warehouse"])]
        source_type = {"PRODUCTION_IN": "PRODUCTION_IN", "PURCHASE_IN": "PURCHASE_IN"}.get(category, "OTHER_LOGISTIC_IN")
        events.append({"ItemCode": str(row["item_code"]), "Branch": branch, "Warehouse": str(row["warehouse"]), "Date": row["doc_date"], "SourceType": source_type, "SourceRole": category, "ReplenishmentQty": float(row["in_qty"] or 0), "source_rows": int(row["source_rows"] or 0), "INTRADAY_SEQUENCE": "UNKNOWN"})
    for category in ("CENTRAL_TRANSFER", "BRANCH_TRANSFER", "TRANSIT_TRANSFER", "PRODUCTION_IN", "PURCHASE_IN", "OTHER_LOGISTIC_IN", "INVENTORY_ADJUSTMENT"):
        categories.setdefault(category, {"rows": 0, "in_qty": 0.0, "out_qty": 0.0})
    return events, {"by_category": dict(categories), "inventory_adjustment_excluded_from_replenishment": True}


def cancellation_audit(cur: Any, start: date, end: date) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for table, line, trans_type in (("OINV", "INV1", 13), ("ORIN", "RIN1", 14)):
        result[table] = {"canceled_documents": rows(cur, f'''SELECT COUNT(*) AS n FROM "TELCHI"."{table}" WHERE "CANCELED"='Y' AND "DocDate" BETWEEN ? AND ?''', (start, end))[0]["n"]}
        result[table]["canceled_line_qty"] = rows(cur, f'''SELECT COALESCE(SUM(L."Quantity"),0) AS qty,COUNT(*) AS lines FROM "TELCHI"."{line}" L JOIN "TELCHI"."{table}" H ON H."DocEntry"=L."DocEntry" WHERE H."CANCELED"='Y' AND H."DocDate" BETWEEN ? AND ? AND L."ItemCode" LIKE 'L%' ''', (start, end))[0]
        result[table]["unresolved_cancelled_sales_impact"] = rows(cur, f'''SELECT COALESCE(SUM(L."Quantity"),0) AS qty,COUNT(*) AS lines FROM "TELCHI"."{line}" L JOIN "TELCHI"."{table}" H ON H."DocEntry"=L."DocEntry" WHERE H."CANCELED"='Y' AND H."DocDate" BETWEEN ? AND ? AND L."ItemCode" LIKE 'L%' AND NOT EXISTS (SELECT 1 FROM "TELCHI"."OINM" M WHERE M."TransType"=? AND M."BASE_REF"=CAST(H."DocNum" AS NVARCHAR(20)) AND M."ItemCode"=L."ItemCode" AND M."Warehouse"=L."WhsCode")''', (start, end, trans_type))[0]
    unresolved = sum(float(result[t]["unresolved_cancelled_sales_impact"]["qty"] or 0) for t in result)
    return {"period": {"start": start, "end": end}, "documents": result, "UNRESOLVED_CANCELLED_SALES_IMPACT": unresolved, "status": "DEGRADED_IF_NONZERO" if unresolved else "NO_UNRESOLVED_MATCH_IN_PERIOD"}


def in_transit_audit(cur: Any, items: list[str], branch_warehouses: list[str]) -> dict[str, Any]:
    transit_rows = rows(cur, '''SELECT W."WhsCode" AS warehouse,W."WhsName" AS name,W."U_TYPE" AS u_type,W."U_WAREHOUSE_DMS" AS dms FROM "TELCHI"."OWHS" W''')
    transit = [str(x["warehouse"]) for x in transit_rows if role(str(x["warehouse"]), str(x.get("name") or ""), x.get("u_type"), x.get("dms"))[0] == "TRANSIT"]
    if not transit:
        return {"IN_TRANSIT_STOCK": "UNRESOLVED", "transit_warehouses": [], "materiality": {"rows": 0, "qty": 0}}
    ph_items, ph_transit = _in_clause(items), _in_clause(transit)
    stock = rows(cur, f'''SELECT COUNT(*) AS rows,COUNT(DISTINCT "ItemCode") AS products,COALESCE(SUM("OnHand"),0) AS qty FROM "TELCHI"."OITW" WHERE "ItemCode" IN ({ph_items}) AND "WhsCode" IN ({ph_transit}) AND "OnHand"<>0''', tuple(items) + tuple(transit))[0]
    return {"IN_TRANSIT_STOCK": "UNRESOLVED", "transit_warehouses": transit, "materiality": {"rows": stock["rows"], "products": stock["products"], "qty": stock["qty"], "branch_warehouses": branch_warehouses}, "meaning": "stock in transit warehouses cannot be assigned to a physical branch"}


def run(input_dir: Path, output: Path, with_hana: bool = True) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    guard = ResourceGuard(output)
    guard.check("input_before", 0, 0, 1)
    stock, stock_row_count = _read_stock_index(input_dir / "daily_item_branch_stock.jsonl.gz")
    events = [_canonicalize_event_category(event) for event in _read_jsonl(input_dir / "replenishment_events.jsonl.gz")]
    transfer_event_count = len(events)
    episode_path = input_dir / "stockout_episodes.jsonl.gz"
    episodes = _read_jsonl(episode_path) if episode_path.exists() else _read_json(input_dir / "stockout_episodes.json")
    discovery = _read_json(input_dir / "level_discovery.json")
    start, end = date.fromisoformat(str(discovery["date_start"])[:10]), date.fromisoformat(str(discovery["date_end"])[:10])
    guard.check("input_loaded", stock_row_count + len(events) + len(episodes), 0, 1)
    hana: dict[str, Any] = {"status": "SKIPPED"}
    if with_hana:
        conn = cur = None
        try:
            conn, cur = connect()
            branch_warehouses: dict[str, str] = {}
            for branch in BRANCHES:
                _, found = _branch_context(cur, branch)
                branch_warehouses.update(found)
            items = sorted({str(key[0]) for key in stock})
            lead = accounting_lead_time(cur, branch_warehouses, items, start, end)
            extra, category_audit = non_transfer_events(cur, branch_warehouses, items, start, end)
            if extra:
                events.extend(_canonicalize_event_category(event) for event in extra)
            hana = {"accounting_lead_time": lead, "movement_categories": category_audit, "cancellation_audit": cancellation_audit(cur, start, end), "in_transit": in_transit_audit(cur, items, list(branch_warehouses)), "physical_lead_time": physical_timestamp_audit(cur, start, end)}
        finally:
            if cur is not None: cur.close()
            if conn is not None: conn.close()
    baseline = build_current_policy_baseline(stock, events, episodes)
    event_category_counts = Counter(str(event.get("EventCategory") or "UNKNOWN") for event in events)
    event_category_qty: dict[str, float] = defaultdict(float)
    for event in events:
        event_category_qty[str(event.get("EventCategory") or "UNKNOWN")] += float(event.get("ReplenishmentQty") or 0)
    hana["event_category_summary"] = {category: {"events": count, "qty": event_category_qty[category]} for category, count in sorted(event_category_counts.items())}
    guard.check("baseline_built", stock_row_count + len(events), len(baseline["item_branch"]), 1)
    resource = guard.summary()
    _write_jsonl(output / "replenishment_events_enriched.jsonl", baseline["events"])
    _write_jsonl(output / "item_branch_baseline.jsonl", baseline["item_branch"])
    _write_jsonl(output / "branch_baseline.jsonl", baseline["branch"])
    _dump_json(output / "rankings.json", baseline["rankings"])
    _dump_json(output / "real_cases.json", baseline["real_cases"])
    _dump_json(output / "classification.json", baseline["classification"])
    _dump_json(output / "lead_time_audit.json", hana)
    result = {"gate": "TELCHI_CURRENT_POLICY_BASELINE_V1", "verdict": "DEGRADED", "context": {"ENTITY": "TELCHI", "DOMAIN": "REPOSICIÓN / STOCK_E_INVENTARIOS", "STAGE": "INVESTIGATION", "SOURCES": ["SAP_HANA", "DATA_LAKE"], "READ_ONLY": True, "SAP_WRITE_COUNT": 0, "product_filter": "ItemCode LIKE 'L%'"}, "input": {"path": str(input_dir), "branches": list(BRANCHES), "date_start": start, "date_end": end, "stock_rows": stock_row_count, "transfer_event_rows": transfer_event_count, "episode_rows": len(episodes)}, "output_counts": {"enriched_events": len(baseline["events"]), "item_branch": len(baseline["item_branch"]), "branches": len(baseline["branch"])}, "branch_summary": baseline["branch"], "classification": baseline["classification"], "resource_safety": resource, "lead_time": hana, "limitations": ["INTRADAY_SEQUENCE_UNKNOWN", "PHYSICAL_LEAD_TIME_NOT_OBSERVABLE_UNLESS_DOCUMENTED_HITOS_EXIST", "IN_TRANSIT_STOCK_UNRESOLVED", "POSSIBLE_CENSORED_DEMAND_NOT_IMPUTED", "CURRENT_POLICY_IS_DESCRIPTIVE_NOT_OPTIMIZED"], "artifacts": ["replenishment_events_enriched.jsonl", "item_branch_baseline.jsonl", "branch_baseline.jsonl", "rankings.json", "real_cases.json", "classification.json", "lead_time_audit.json", "gate_result.json"]}
    _dump_json(output / "gate_result.json", result)
    return result


def _branch_context(cur: Any, branch: str) -> tuple[dict[str, Any], dict[str, str]]:
    from modules.telchi.investigation.validation.branch_replenishment.daily_stock_demand_v1 import sample_warehouse_context
    return sample_warehouse_context(cur, branch)


def physical_timestamp_audit(cur: Any, start: date, end: date) -> dict[str, Any]:
    fields = ("ReqDate", "StDlvDate", "StDlvTime", "EndDlvDate", "EndDlvTime", "U_FECHEST_EMBR", "U_FECHPRTO", "U_FECHALM", "U_FECHREAL_EMBR", "U_FECHREAL_PRTO")
    values: dict[str, int] = {}
    for field in fields:
        values[field] = int(rows(cur, f'''SELECT COUNT("{field}") AS n FROM "TELCHI"."OWTR" WHERE "CANCELED"='N' AND "DocDate" BETWEEN ? AND ?''', (start, end))[0]["n"] or 0)
    populated = [field for field, count in values.items() if count]
    return {"status": "PHYSICAL_LEAD_TIME_OBSERVABLE_CANDIDATE" if populated else "PHYSICAL_LEAD_TIME_NOT_OBSERVABLE", "candidate_fields": values, "populated_fields": populated, "semantic_warning": "presence is not proof that a field means request/preparation/dispatch/receipt; no duration is calculated without demonstrated semantics"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TELCHI Gate 4 current policy baseline")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-hana", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(args.input, args.output, not args.no_hana)
    except ResourceGuardAbort as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        _dump_json(args.output / "gate_result.json", {"gate": "TELCHI_CURRENT_POLICY_BASELINE_V1", "verdict": "DEGRADED", "result": "RESOURCE_GUARD_ABORT", "RESOURCE_GUARD": "ENABLED", "MAX_WORKERS": 1, "error": str(exc), "snapshot": resource_snapshot()})
        return 3
    print(json.dumps({"gate": result["gate"], "verdict": result["verdict"], "output_counts": result["output_counts"], "resource_safety": result["resource_safety"], "output": str(args.output)}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
