"""TELCHI Gate 5C: physical lead-time / logistics process investigation.

This runner is deliberately conservative.  It separates request, accounting
transfer, OINM posting and physical availability; an OWTR/OINM timestamp is
never labelled as a physical dispatch or receipt without an external/explicit
hito.  HANA access is SELECT-only, MAX_WORKERS is one, and the main universe is
L items received by the 2A sales warehouses during the Gate 5C window.
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.branch_replenishment.branch_replenishment_gate_v1 import role
from modules.telchi.investigation.validation.branch_replenishment.daily_stock_demand_v1 import ResourceGuard

GATE = "TELCHI_PHYSICAL_LEAD_TIME_V1"
VERDICT = "TELCHI_PHYSICAL_LEAD_TIME_V1_NOT_OBSERVABLE"
WINDOW_START = date(2025, 9, 12)
WINDOW_END = date(2026, 9, 11)
BRANCH = "2A"
DESTINATIONS = ("2A-SAL", "2A-SMK")
TRANSIT_ROLES = {"TRANSIT"}
DEFAULT_OUTPUT = EVIDENCE_ROOT / "branch_replenishment_physical_lead_time" / "v1"
DEFAULT_BACKTEST_INPUT = EVIDENCE_ROOT / "branch_replenishment_daily_stock_demand" / "v2_scale_up" / "level_E"


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def rows(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    names = [d[0].lower() for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _in_clause(values: Iterable[str]) -> str:
    values = list(values)
    if not values:
        raise ValueError("empty IN clause")
    return ",".join("?" for _ in values)


def sap_timestamp(day: Any, raw_time: Any) -> datetime | None:
    """Parse SAP date + HHMMSS (CreateTS), preserving invalid values."""
    if day is None:
        return None
    if isinstance(day, datetime):
        day = day.date()
    elif not isinstance(day, date):
        try:
            day = date.fromisoformat(str(day)[:10])
        except ValueError:
            return None
    try:
        value = int(raw_time or 0)
        text = f"{value:06d}"
        return datetime.combine(day, time(int(text[:2]), int(text[2:4]), int(text[4:6])))
    except (TypeError, ValueError):
        return None


def sap_doc_timestamp(day: Any, raw_time: Any) -> datetime | None:
    """Parse SAP DocTime, whose operational format is HHMM (not HHMMSS)."""
    if day is None:
        return None
    if isinstance(day, datetime):
        day = day.date()
    elif not isinstance(day, date):
        try:
            day = date.fromisoformat(str(day)[:10])
        except ValueError:
            return None
    try:
        value = int(raw_time or 0)
        if value > 2359:
            text = f"{value:06d}"
            return datetime.combine(day, time(int(text[:2]), int(text[2:4]), int(text[4:6])))
        text = f"{value:04d}"
        return datetime.combine(day, time(int(text[:2]), int(text[2:4])))
    except (TypeError, ValueError):
        return None


def as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def stats(values: Iterable[float]) -> dict[str, Any]:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return {"count": 0, "mean": None, "median": None, "p25": None, "p75": None, "p90": None, "p95": None, "max": None}
    return {
        "count": len(numbers),
        "mean": statistics.fmean(numbers),
        "median": percentile(numbers, .50),
        "p25": percentile(numbers, .25),
        "p75": percentile(numbers, .75),
        "p90": percentile(numbers, .90),
        "p95": percentile(numbers, .95),
        "max": max(numbers),
    }


def _delta_days(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return (end - start).total_seconds() / 86400


def confidence_for_episode(episode: dict[str, Any]) -> str:
    """Physical confidence, not accounting completeness."""
    if episode.get("physical_dispatch_timestamp") and episode.get("physical_receipt_timestamp") and episode.get("stock_available_timestamp"):
        return "EXACT"
    if episode.get("physical_dispatch_timestamp") and episode.get("physical_receipt_timestamp"):
        return "STRONG"
    if episode.get("AccountingAvailabilityTimestamp") and episode.get("FirstSaleAfterTimestamp"):
        return "PROXY"
    # An accounting posting alone does not provide a defensible physical
    # interval: physical receipt may precede or follow the SAP posting.
    return "UNKNOWN"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _load_stockout_context(input_dir: Path | None) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if input_dir is None:
        return {}
    candidates = [input_dir / "stockout_episodes.jsonl.gz", input_dir / "stockout_episodes.json"]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        return {}
    episodes = _read_jsonl(path)
    result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for episode in episodes:
        key = (str(episode.get("ItemCode")), str(episode.get("Branch")))
        result[key].append(episode)
    return result


def _stockout_context(item: str, event_date: date, stockouts: dict[tuple[str, str], list[dict[str, Any]]]) -> str:
    episodes = stockouts.get((item, BRANCH), [])
    for episode in episodes:
        start = as_date(episode.get("StartDate"))
        end = as_date(episode.get("EndDate")) or start
        if start and end and start <= event_date <= end:
            return "DURING_STOCKOUT"
        if end and event_date > end:
            return "AFTER_STOCKOUT"
        if start and event_date < start:
            return "BEFORE_STOCKOUT"
    return "NO_STOCKOUT_CONTEXT"


def fetch_transfer_lines(cur: Any) -> list[dict[str, Any]]:
    destinations = _in_clause(DESTINATIONS)
    sql = f'''SELECT H."DocEntry" AS transfer_docentry,H."DocNum" AS transfer_docnum,
        H."DocDate" AS transfer_docdate,H."DocTime" AS transfer_doctime,
        H."CreateDate" AS transfer_createdate,H."CreateTS" AS transfer_createts,
        H."UpdateDate" AS transfer_updatedate,H."UpdateTS" AS transfer_updatets,
        H."TaxDate" AS transfer_taxdate,H."DocDueDate" AS transfer_duedate,
        H."CANCELED" AS transfer_canceled,H."Comments" AS transfer_comments,
        H."UserSign" AS transfer_usersign,UT."USER_CODE" AS transfer_usercode,
        UT."U_NAME" AS transfer_username,H."Series" AS transfer_series,
        L."LineNum" AS transfer_linenum,L."ItemCode" AS item_code,
        L."Quantity" AS quantity,L."FromWhsCod" AS source_whs,L."WhsCode" AS destination_whs,
        L."LineStatus" AS transfer_line_status,L."BaseType" AS base_type,
        L."BaseEntry" AS request_docentry,L."BaseLine" AS request_linenum,
        L."TrgetEntry" AS target_entry,L."ShipDate" AS line_shipdate,
        R."DocNum" AS request_docnum,R."DocDate" AS request_docdate,
        R."CreateDate" AS request_createdate,R."CreateTS" AS request_createts,
        R."ReqDate" AS request_reqdate,R."UserSign" AS request_usersign,
        UR."USER_CODE" AS request_usercode,UR."U_NAME" AS request_username,
        Q."Quantity" AS request_quantity,Q."LineStatus" AS request_line_status,
        Q."WhsCode" AS request_destination,Q."FromWhsCod" AS request_source
      FROM "TELCHI"."OWTR" H
      JOIN "TELCHI"."WTR1" L ON L."DocEntry"=H."DocEntry"
      LEFT JOIN "TELCHI"."OWTQ" R ON R."DocEntry"=L."BaseEntry"
        AND L."BaseType"='1250000001'
      LEFT JOIN "TELCHI"."WTQ1" Q ON Q."DocEntry"=R."DocEntry" AND Q."LineNum"=L."BaseLine"
      LEFT JOIN "TELCHI"."OUSR" UT ON UT."USERID"=H."UserSign"
      LEFT JOIN "TELCHI"."OUSR" UR ON UR."USERID"=R."UserSign"
      WHERE H."CANCELED"='N' AND L."ItemCode" LIKE 'L%'
        AND L."WhsCode" IN ({destinations}) AND L."Quantity">0
        AND H."DocDate" BETWEEN ? AND ?
      ORDER BY H."DocDate",H."DocEntry",L."LineNum"'''
    return rows(cur, sql, tuple(DESTINATIONS) + (WINDOW_START, WINDOW_END))


def fetch_oinm_for_transfers(cur: Any, transfers: list[dict[str, Any]]) -> dict[tuple[int, int], list[dict[str, Any]]]:
    """Fetch TT67 once and match by the atomic transfer line in Python.

    Matching preserves the validated BASE_REF + item + warehouse + line
    semantics and avoids a many-to-many SQL fan-out.
    """
    if not transfers:
        return {}
    docnums = sorted({str(row["transfer_docnum"]) for row in transfers})
    items = sorted({str(row["item_code"]) for row in transfers})
    ph_docs, ph_items = _in_clause(docnums), _in_clause(items)
    raw = rows(cur, f'''SELECT M."TransNum" AS trans_num,M."BASE_REF" AS base_ref,
        M."DocLineNum" AS doc_line_num,M."BaseLine" AS base_line,M."DocDate" AS movement_date,
        M."DocTime" AS movement_time,M."CreateDate" AS movement_createdate,
        M."ItemCode" AS item_code,M."Warehouse" AS warehouse,M."InQty" AS in_qty,
        M."OutQty" AS out_qty,M."UserSign" AS movement_usersign
      FROM "TELCHI"."OINM" M WHERE M."TransType"=67
        AND M."BASE_REF" IN ({ph_docs}) AND M."ItemCode" IN ({ph_items})''', tuple(docnums) + tuple(items))
    by_doc_item: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for movement in raw:
        by_doc_item[(str(movement["base_ref"]), str(movement["item_code"]))].append(movement)
    result: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for transfer in transfers:
        key = (int(transfer["transfer_docentry"]), int(transfer["transfer_linenum"]))
        for movement in by_doc_item.get((str(transfer["transfer_docnum"]), str(transfer["item_code"])), []):
            line = movement.get("doc_line_num")
            base_line = movement.get("base_line")
            if line is not None and int(line) != int(transfer["transfer_linenum"]) and base_line is not None and int(base_line) != int(transfer["transfer_linenum"]):
                continue
            result[key].append(movement)
    return result


def fetch_first_sales(cur: Any, transfers: list[dict[str, Any]]) -> dict[tuple[str, str], list[datetime]]:
    if not transfers:
        return {}
    items = sorted({str(row["item_code"]) for row in transfers})
    destinations = _in_clause(DESTINATIONS)
    ph_items = _in_clause(items)
    result: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    for row in rows(cur, f'''SELECT M."ItemCode" AS item_code,M."Warehouse" AS warehouse,
        M."DocDate" AS movement_date,M."DocTime" AS movement_time
      FROM "TELCHI"."OINM" M WHERE M."ItemCode" IN ({ph_items})
        AND M."Warehouse" IN ({destinations}) AND M."TransType" IN (13,15)
        AND M."OutQty">0 AND M."DocDate" BETWEEN ? AND ?
      ORDER BY M."DocDate",M."DocTime"''', tuple(items) + tuple(DESTINATIONS) + (WINDOW_START, WINDOW_END)):
        timestamp = sap_doc_timestamp(row["movement_date"], row["movement_time"])
        if timestamp:
            result[(str(row["item_code"]), str(row["warehouse"]))].append(timestamp)
    return result


def _movement_roles(cur: Any) -> list[dict[str, Any]]:
    return rows(cur, '''SELECT "WhsCode" AS warehouse,"WhsName" AS name,"U_TYPE" AS u_type,
        "U_WAREHOUSE_DMS" AS dms FROM "TELCHI"."OWHS" ORDER BY "WhsCode"''')


def transit_audit(cur: Any, transfer_rows: list[dict[str, Any]]) -> dict[str, Any]:
    warehouses = _movement_roles(cur)
    transit = [str(row["warehouse"]) for row in warehouses if role(str(row["warehouse"]), str(row.get("name") or ""), row.get("u_type"), row.get("dms"))[0] in TRANSIT_ROLES]
    if not transit:
        return {"warehouses": [], "current_stock": {"rows": 0, "items": 0, "qty": 0}, "exactly_assignable_qty": 0, "status": "NO_TRANSIT_WAREHOUSE"}
    ph_transit, ph_dest = _in_clause(transit), _in_clause(DESTINATIONS)
    stock_rows = rows(cur, f'''SELECT I."WhsCode" AS warehouse,I."ItemCode" AS item_code,
        I."OnHand" AS on_hand,W."WhsName" AS name FROM "TELCHI"."OITW" I
      JOIN "TELCHI"."OWHS" W ON W."WhsCode"=I."WhsCode"
      WHERE I."ItemCode" LIKE 'L%' AND I."OnHand"<>0 AND I."WhsCode" IN ({ph_transit})''', tuple(transit))
    total_stock = sum(float(row["on_hand"] or 0) for row in stock_rows)
    open_request_rows = rows(cur, f'''SELECT Q."FromWhsCod" AS source_whs,Q."WhsCode" AS destination_whs,
        Q."ItemCode" AS item_code,SUM(CASE WHEN Q."OpenQty">0 THEN Q."OpenQty" ELSE Q."Quantity" END) AS open_qty
      FROM "TELCHI"."OWTQ" H JOIN "TELCHI"."WTQ1" Q ON Q."DocEntry"=H."DocEntry"
      WHERE H."CANCELED"='N' AND Q."ItemCode" LIKE 'L%' AND Q."LineStatus"='O'
        AND Q."FromWhsCod" IN ({ph_transit}) AND Q."WhsCode" IN ({ph_dest})
      GROUP BY Q."FromWhsCod",Q."WhsCode",Q."ItemCode"''', tuple(transit) + tuple(DESTINATIONS))
    stock_by_item = defaultdict(float)
    for row in stock_rows:
        stock_by_item[(str(row["warehouse"]), str(row["item_code"]))] += float(row["on_hand"] or 0)
    potential = 0.0
    potential_rows = []
    for request in open_request_rows:
        key = (str(request["source_whs"]), str(request["item_code"]))
        candidate = min(max(stock_by_item.get(key, 0.0), 0.0), max(float(request["open_qty"] or 0), 0.0))
        potential += candidate
        if candidate:
            potential_rows.append({**request, "potential_match_qty": candidate, "allocation_status": "POTENTIAL_ONLY_NOT_ALLOCATION"})
    route_rows = rows(cur, f'''SELECT W."FromWhsCod" AS source_whs,W."WhsCode" AS destination_whs,
        COUNT(DISTINCT O."DocEntry") AS transfer_docs,COUNT(*) AS lines,SUM(ABS(W."Quantity")) AS qty
      FROM "TELCHI"."OWTR" O JOIN "TELCHI"."WTR1" W ON W."DocEntry"=O."DocEntry"
      WHERE O."CANCELED"='N' AND W."ItemCode" LIKE 'L%' AND W."FromWhsCod" IN ({ph_transit})
        AND W."WhsCode" IN ({ph_dest}) AND O."DocDate" BETWEEN ? AND ?
      GROUP BY W."FromWhsCod",W."WhsCode" ORDER BY qty DESC''', tuple(transit) + tuple(DESTINATIONS) + (WINDOW_START, WINDOW_END))
    return {
        "warehouses": transit,
        "current_stock": {"rows": len(stock_rows), "items": len({str(row['item_code']) for row in stock_rows}), "qty": total_stock, "by_warehouse": [dict(row) for row in stock_rows]},
        "open_requests_to_2a": {"rows": len(open_request_rows), "potential_match_qty": potential, "potential_rows": potential_rows},
        "exactly_assignable_qty": 0,
        "assignability": {"status": "NOT_ASSIGNABLE_FROM_CURRENT_SAP_STATE", "reason": "OITW is an aggregate stock position; an open request/item match is not a reservation or physical identity", "potential_upper_bound_qty": potential, "exact_percentage_of_current_qty": 0.0 if total_stock else None, "potential_percentage_of_current_qty": (100 * potential / total_stock) if total_stock else None},
        "routes_to_2a": route_rows,
        "duration": {"status": "UNKNOWN", "reason": "no physical departure/arrival timestamps and OITW has no stock age by shipment"},
    }


def document_inventory(cur: Any) -> dict[str, Any]:
    fields = {}
    for table in ("OWTR", "WTR1", "OINM", "OWTQ", "WTQ1", "ODLN", "DLN1"):
        cur.execute(f'SELECT * FROM "TELCHI"."{table}" LIMIT 0')
        fields[table] = [description[0] for description in cur.description]
    relevant = {}
    for table, names in fields.items():
        relevant[table] = [name for name in names if any(token in name.upper() for token in ("DATE", "TIME", "TS", "USER", "REQ", "DLV", "SHIP", "TRANS", "BASE", "TRGET", "REF", "COMMENT", "U_") )]
    return {"tables": {table: {"column_count": len(names), "relevant_columns": relevant[table]} for table, names in fields.items()}, "semantics": {"DocDate": "document/posting date; not physical receipt", "CreateDate_CreateTS": "SAP creation timestamp; not dispatch", "DocTime": "document time; not physical departure", "OINM_TT67": "accounting inventory transfer movement", "OWTQ_WTQ1": "request object when used; conversion linkage via BaseType/BaseEntry/BaseLine/TrgetEntry", "ODLN_DLN1": "delivery documents inspected for relation; not assumed to be transfer receipt"}}


def cancellation_audit(cur: Any) -> dict[str, Any]:
    return {
        "owtr_cancelled_in_window": rows(cur, 'SELECT COUNT(*) AS n FROM "TELCHI"."OWTR" WHERE "CANCELED"=\'Y\' AND "DocDate" BETWEEN ? AND ?', (WINDOW_START, WINDOW_END))[0]["n"],
        "owtq_cancelled_in_window": rows(cur, 'SELECT COUNT(*) AS n FROM "TELCHI"."OWTQ" WHERE "CANCELED"=\'Y\' AND "DocDate" BETWEEN ? AND ?', (WINDOW_START, WINDOW_END))[0]["n"],
        "active_negative_transfer_lines_in_window": rows(cur, '''SELECT COUNT(*) AS n FROM "TELCHI"."OWTR" H JOIN "TELCHI"."WTR1" L ON L."DocEntry"=H."DocEntry" WHERE H."CANCELED"='N' AND L."ItemCode" LIKE 'L%' AND L."WhsCode" IN ('2A-SAL','2A-SMK') AND L."Quantity"<0 AND H."DocDate" BETWEEN ? AND ?''', (WINDOW_START, WINDOW_END))[0]["n"],
        "delivery_lines_based_on_transfer": rows(cur, '''SELECT COUNT(*) AS n FROM "TELCHI"."ODLN" H JOIN "TELCHI"."DLN1" L ON L."DocEntry"=H."DocEntry" WHERE H."CANCELED"='N' AND L."ItemCode" LIKE 'L%' AND L."BaseType"='67' AND H."DocDate" BETWEEN ? AND ?''', (WINDOW_START, WINDOW_END))[0]["n"],
    }


def build_episodes(transfers: list[dict[str, Any]], movements: dict[tuple[int, int], list[dict[str, Any]]], first_sales: dict[tuple[str, str], list[datetime]], stockouts: dict[tuple[str, str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    episodes = []
    for row in transfers:
        key = (int(row["transfer_docentry"]), int(row["transfer_linenum"]))
        transfer_ts = sap_timestamp(row["transfer_createdate"], row["transfer_createts"])
        request_ts = sap_timestamp(row.get("request_createdate"), row.get("request_createts"))
        transfer_doc_ts = sap_doc_timestamp(row["transfer_docdate"], row["transfer_doctime"])
        line_movements = movements.get(key, [])
        source = [m for m in line_movements if str(m.get("warehouse")) == str(row["source_whs"]) and float(m.get("out_qty") or 0) > 0]
        destination = [m for m in line_movements if str(m.get("warehouse")) == str(row["destination_whs"]) and float(m.get("in_qty") or 0) > 0]
        source_ts = min((sap_doc_timestamp(m.get("movement_date"), m.get("movement_time")) for m in source), default=None)
        destination_ts = min((sap_doc_timestamp(m.get("movement_date"), m.get("movement_time")) for m in destination), default=None)
        sales_for_item = first_sales.get((str(row["item_code"]), str(row["destination_whs"])), [])
        first_sale = next((sale for sale in sales_for_item if transfer_ts is None or sale > transfer_ts), None)
        event_date = as_date(row["transfer_docdate"])
        episode = {
            "ItemCode": str(row["item_code"]), "Qty": float(row["quantity"] or 0), "SourceWhs": str(row["source_whs"]), "TransitWhs": str(row["source_whs"]) if str(row["source_whs"]) in {"SAP-R1", "SAL-TRS", "2A-DEV", "2A-TRAN", "LAB-A1", "LAB-TRAN", "01"} else None, "DestinationWhs": str(row["destination_whs"]),
            "RequestDoc": row.get("request_docnum"), "RequestDocEntry": row.get("request_docentry"), "TransferDoc": row.get("transfer_docnum"), "TransferDocEntry": row.get("transfer_docentry"), "TransferLine": row.get("transfer_linenum"),
            "RequestCreateTimestamp": request_ts, "TransferCreateTimestamp": transfer_ts, "PostingTimestamp": destination_ts,
            "SourceOINMTimestamp": source_ts, "OINMTimestamp": destination_ts, "AccountingAvailabilityTimestamp": destination_ts, "AccountingStockAvailableDate": destination_ts.date() if destination_ts else None, "FirstSaleAfterTimestamp": first_sale,
            "StockAvailableDate": None, "EarliestPossibleAvailability": None, "LatestPossibleAvailability": first_sale,
            "ArrivalEvidence": "OINM TT67 destination posting; physical arrival not proven" if destination_ts else "NONE",
            "RequestToTransferDocumentDelayDays": _delta_days(request_ts, transfer_ts), "TransferDocumentDelayDays": _delta_days(transfer_doc_ts, destination_ts), "TransferCreateToPostingDelayDays": _delta_days(transfer_ts, destination_ts),
            "StockoutContext": _stockout_context(str(row["item_code"]), event_date, stockouts) if event_date else "UNKNOWN",
            "RequestEvidence": "OWTQ/WTQ1 exact line relation" if row.get("request_docentry") is not None and row.get("request_linenum") is not None and row.get("request_quantity") is not None else "NONE",
            "DispatchEvidence": "NONE_PHYSICAL; OWTR_DOCUMENT_ONLY", "ReceiptEvidence": "OINM_TT67_ACCOUNTING_ONLY" if destination_ts else "NONE",
            "AvailabilityEvidence": "FIRST_SALE_AFTER_PROXY" if first_sale else ("OINM_DESTINATION_POSTING" if destination_ts else "NONE"),
            "physical_dispatch_timestamp": None, "physical_receipt_timestamp": None, "stock_available_timestamp": None,
            "OINMMatchRows": len(line_movements), "Confidence": None,
            "TransferUser": row.get("transfer_usercode") or row.get("transfer_usersign"), "RequestUser": row.get("request_usercode") or row.get("request_usersign"), "Comments": row.get("transfer_comments"),
        }
        episode["Confidence"] = confidence_for_episode(episode)
        episodes.append(episode)
    return episodes


def _select_real_cases(episodes: list[dict[str, Any]], count: int = 20) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    # Prefer request-linked, transit, different quantities/routes and stockout contexts.
    ranked = sorted(episodes, key=lambda x: (x["RequestEvidence"] == "NONE", x["TransitWhs"] is None, x["StockoutContext"] == "NO_STOCKOUT_CONTEXT", x["ItemCode"], x["TransferDocEntry"], x["TransferLine"]))
    for episode in ranked:
        if len(chosen) >= count:
            break
        if episode["ItemCode"] not in seen_items or len(chosen) >= count - 5:
            chosen.append(episode)
            seen_items.add(episode["ItemCode"])
    return chosen[:count]


def _coverage(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(episodes)
    def pct(predicate: Any) -> float:
        return 100 * sum(1 for x in episodes if predicate(x)) / n if n else 0.0
    return {
        "denominator": {"transfer_lines": n, "transfer_documents": len({x["TransferDocEntry"] for x in episodes})},
        "request": {"lines": sum(x["RequestEvidence"] != "NONE" for x in episodes), "pct_lines": pct(lambda x: x["RequestEvidence"] != "NONE"), "documents": len({x["TransferDocEntry"] for x in episodes if x["RequestEvidence"] != "NONE"}), "pct_documents": 100 * len({x["TransferDocEntry"] for x in episodes if x["RequestEvidence"] != "NONE"}) / len({x["TransferDocEntry"] for x in episodes}) if n else 0.0},
        "dispatch": {"document": n, "physical_timestamp": 0, "pct_physical_timestamp": 0.0},
        "transit_path": {"lines": sum(x["TransitWhs"] is not None for x in episodes), "pct_lines": pct(lambda x: x["TransitWhs"] is not None)},
        "receipt": {"accounting_oinm": sum(x["PostingTimestamp"] is not None for x in episodes), "physical_timestamp": 0, "pct_accounting_oinm": pct(lambda x: x["PostingTimestamp"] is not None)},
        "availability": {"accounting_posting": sum(x["AccountingAvailabilityTimestamp"] is not None for x in episodes), "first_sale_proxy": sum(x["FirstSaleAfterTimestamp"] is not None for x in episodes), "pct_first_sale_proxy": pct(lambda x: x["FirstSaleAfterTimestamp"] is not None)},
        "confidence": dict(Counter(x["Confidence"] for x in episodes)),
    }


def _distribution(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "REQUEST_TO_TRANSFER_DOCUMENT_DELAY": stats(x["RequestToTransferDocumentDelayDays"] for x in episodes if x["RequestToTransferDocumentDelayDays"] is not None),
        "TRANSFER_DOCUMENT_DELAY_ACCOUNTING": stats(x["TransferDocumentDelayDays"] for x in episodes if x["TransferDocumentDelayDays"] is not None),
        "TRANSFER_CREATE_TO_POSTING_DELAY": stats(x["TransferCreateToPostingDelayDays"] for x in episodes if x["TransferCreateToPostingDelayDays"] is not None),
        "ACCOUNTING_ANOMALIES": {"negative_or_pre_document": sum(1 for x in episodes if x["TransferDocumentDelayDays"] is not None and x["TransferDocumentDelayDays"] < 0), "nonzero_positive": sum(1 for x in episodes if x["TransferDocumentDelayDays"] is not None and x["TransferDocumentDelayDays"] > 0)},
        "PHYSICAL_LEAD_TIME": {"status": "NOT_OBSERVABLE", "sample": 0, "mean": None, "median": None, "p75": None, "p90": None, "p95": None, "max": None},
    }


def _group_stats(episodes: list[dict[str, Any]], key_fn: Any) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for episode in episodes:
        groups[str(key_fn(episode))].append(episode)
    return [{"group": key, "episodes": len(items), "request_to_transfer_document_delay": stats(x["RequestToTransferDocumentDelayDays"] for x in items if x["RequestToTransferDocumentDelayDays"] is not None), "accounting_transfer_to_posting": stats(x["TransferDocumentDelayDays"] for x in items if x["TransferDocumentDelayDays"] is not None)} for key, items in sorted(groups.items())]


def run(output: Path = DEFAULT_OUTPUT, backtest_input: Path | None = DEFAULT_BACKTEST_INPUT) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    guard = ResourceGuard(output)
    guard.check("before_hana", 0, 0, 1)
    conn, cur = connect()
    try:
        transfers = fetch_transfer_lines(cur)
        guard.check("transfer_lines", len(transfers), 0, 1)
        movements = fetch_oinm_for_transfers(cur, transfers)
        guard.check("oinm_transfer_movements", sum(len(value) for value in movements.values()), 0, 1)
        first_sales = fetch_first_sales(cur, transfers)
        guard.check("first_sale_proxy", sum(len(value) for value in first_sales.values()), 0, 1)
        stockouts = _load_stockout_context(backtest_input)
        episodes = build_episodes(transfers, movements, first_sales, stockouts)
        transit = transit_audit(cur, transfers)
        coverage = _coverage(episodes)
        resource_safety = guard.summary()
        result = {
            "gate": GATE, "verdict": VERDICT,
            "context": {"ENTITY": "TELCHI", "DOMAIN": "REPOSICIÓN / STOCK_E_INVENTARIOS", "STAGE": "INVESTIGATION", "SOURCES": ["SAP_HANA", "DATA_LAKE"], "READ_ONLY": True, "SAP_WRITE_COUNT": 0, "MAX_WORKERS": 1, "RESOURCE_GUARD": "ENABLED", "product_filter": "ItemCode LIKE 'L%'", "branch": BRANCH, "destination_warehouses": list(DESTINATIONS), "window_start": WINDOW_START, "window_end": WINDOW_END},
            "process_map": {"REQUEST": "OWTQ/WTQ1 when used", "TRANSFER": "OWTR/WTR1", "PREPARATION": "NOT_OBSERVED", "DISPATCH": "NOT_OBSERVED_PHYSICALLY", "TRANSIT": "warehouse role + OWTR route only; physical state not proven", "RECEIPT": "OINM TT67 destination posting", "AVAILABLE": "accounting destination posting; first sale after is upper-bound proxy"},
            "source_coverage": coverage,
            "resource_safety": resource_safety,
            "distributions": _distribution(episodes),
            "routes": {"by_source_destination": _group_stats(episodes, lambda x: f"{x['SourceWhs']} -> {x['DestinationWhs']}"), "by_day_of_week": _group_stats(episodes, lambda x: as_date(x["TransferCreateTimestamp"]).strftime("%A") if as_date(x["TransferCreateTimestamp"]) else "UNKNOWN"), "by_quantity_band": _group_stats(episodes, lambda x: "0-10" if x["Qty"] <= 10 else "11-100" if x["Qty"] <= 100 else "101+"), "by_stockout_context": _group_stats(episodes, lambda x: x["StockoutContext"])},
            "stockout_comparison": {"status": "ACCOUNTING_DELAY_ONLY", "urgent_or_during_stockout": _group_stats([x for x in episodes if x["StockoutContext"] in {"DURING_STOCKOUT", "AFTER_STOCKOUT"}], lambda x: x["StockoutContext"]), "anticipatory": _group_stats([x for x in episodes if x["StockoutContext"] == "BEFORE_STOCKOUT"], lambda x: x["StockoutContext"]), "physical_acceleration_inference": "NOT_ALLOWED"},
            "transit": transit,
            "cancellations_and_reverses": cancellation_audit(cur),
            "document_inventory": document_inventory(cur),
            "episodes": {"count": len(episodes), "real_cases_count": min(20, len(episodes)), "artifacts": ["episodes.jsonl", "real_cases.jsonl"]},
            "limitations": ["PHYSICAL_DISPATCH_TIMESTAMP_NOT_REGISTERED", "PHYSICAL_RECEIPT_TIMESTAMP_NOT_REGISTERED", "OWTR_AND_OINM_ARE_ACCOUNTING_EVENTS", "FIRST_SALE_IS_UPPER_BOUND_PROXY_NOT_AVAILABILITY_TIMESTAMP", "OITW_TRANSIT_STOCK_HAS_NO_SHIPMENT_IDENTITY_OR_STOCK_AGE", "REQUEST_TO_TRANSFER_DOCUMENT_IS_NOT_PHYSICAL_LEAD_TIME", "TRANSFER_TO_POSTING_IS_NOT_PHYSICAL_LEAD_TIME", "NO_GLOBAL_REPLENISHMENT_POLICY_CHANGE"],
            "minimum_operational_fix": ["dispatch_timestamp", "receipt_timestamp"],
            "backtest_impact": {"status": "DO_NOT_MODIFY_GATE_5C_BACKTEST_YET", "required_after_external_timestamp_capture": ["replace arbitrary LT 0/1/2/3/5/7 with route-aware observed distributions", "use median as typical, p75 as stressed and p90 as conservative", "keep physical/accounting/request delays separate"]},
            "real_case_selection": _select_real_cases(episodes),
        }
        (output / "gate_result.json").write_text(json.dumps(jsonable(result), ensure_ascii=False, indent=2), encoding="utf-8")
        with (output / "episodes.jsonl").open("w", encoding="utf-8") as handle:
            for episode in episodes:
                handle.write(json.dumps(jsonable(episode), ensure_ascii=False) + "\n")
        with (output / "real_cases.jsonl").open("w", encoding="utf-8") as handle:
            for episode in _select_real_cases(episodes):
                handle.write(json.dumps(jsonable(episode), ensure_ascii=False) + "\n")
        (output / "coverage.json").write_text(json.dumps(jsonable(coverage), ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "transit.json").write_text(json.dumps(jsonable(transit), ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        cur.close()
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TELCHI Gate 5C physical lead time investigation")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--backtest-input", type=Path, default=DEFAULT_BACKTEST_INPUT)
    args = parser.parse_args(argv)
    result = run(args.output, args.backtest_input)
    print(json.dumps({"gate": result["gate"], "verdict": result["verdict"], "transfer_lines": result["source_coverage"]["denominator"]["transfer_lines"], "real_cases": result["episodes"]["real_cases_count"], "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
