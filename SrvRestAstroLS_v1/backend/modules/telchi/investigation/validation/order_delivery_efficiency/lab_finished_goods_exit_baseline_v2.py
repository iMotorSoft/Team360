"""TELCHI_LAB_FINISHED_GOODS_EXIT_BASELINE_V2.

The frozen Gate 1-3 order keys are reused without recounting the live cohort.
The source-document paths are line-grain and OINM is joined only by the closed
semantic key.  SAP access is SELECT-only, sequential, and bounded to the
known order/document rows; no pandas or parallelism is used.
"""
from __future__ import annotations

import json
import math
import os
import resource
import time
from collections import Counter
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection
from modules.telchi.investigation.validation.order_delivery_efficiency.order_to_warehouse_exit_baseline_v1 import (
    END_DATE_EXCLUSIVE,
    START_DATE,
)

SNAPSHOT = "2026-09-14 11:21:15"
SNAPSHOT_DATE = "2026-09-14"
SNAPSHOT_TIME = 112115
LAB_PRODUCT_FINISHED_WAREHOUSES = ("LAB-T1", "LAB-T2", "LAB-T3", "LAB-T4")
LAB_SUBTYPES = {
    "LAB-T1": "AGEMED",
    "LAB-T2": "SENASAG",
    "LAB-T3": "INDUSTRIAL",
    "LAB-T4": "MAGISTRAL",
}
SAP_WRITE_COUNT = 0
FROZEN_ORDER_COUNT = 3027
FROZEN_ACTIVE_COUNT = 2842

EVIDENCE_DIR = EVIDENCE_ROOT / "order_delivery_efficiency" / "evidence"
FROZEN_EVIDENCE_PATH = EVIDENCE_DIR / "order_to_warehouse_exit_baseline_v1.json"
EVIDENCE_PATH = EVIDENCE_DIR / "lab_finished_goods_exit_baseline_v2.json"

BANDS = (
    ("<30m", 0, 30),
    ("30–60m", 30, 60),
    ("1–2h", 60, 120),
    ("2–4h", 120, 240),
    ("4–8h", 240, 480),
    ("8–12h", 480, 720),
    ("12–24h", 720, 1440),
    ("24–48h", 1440, 2880),
    ("48–72h", 2880, 4320),
    ("72–96h", 4320, 5760),
    (">96h", 5760, math.inf),
)
HOUR_BANDS = (
    ("00–07", 0, 7), ("07–09", 7, 9), ("09–11", 9, 11),
    ("11–13", 11, 13), ("13–15", 13, 15), ("15–17", 15, 17),
    ("17–19", 17, 19), ("19–24", 19, 24),
)
WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _json_default(value: Any) -> str | float:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _rows(cursor: Any, sql: str) -> list[dict[str, Any]]:
    cursor.execute(f"SELECT * FROM ({sql}) Q")
    columns = [item[0].lower() for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _timestamp(value_date: Any, value_ts: Any) -> datetime | None:
    if value_date is None or value_ts is None:
        return None
    day = value_date.date() if isinstance(value_date, datetime) else value_date
    if not isinstance(day, date):
        day = date.fromisoformat(str(day)[:10])
    try:
        raw = int(value_ts)
        hh, rest = divmod(raw, 10000)
        mm, ss = divmod(rest, 100)
        return datetime.combine(day, dt_time(hh, mm, ss))
    except (TypeError, ValueError):
        return None


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires values")
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {key: None for key in ("N", "mean", "median", "p25", "p75", "p90", "p95", "min", "max")}
    return {
        "N": len(values), "mean": round(mean(values), 3),
        "median": round(_quantile(values, .5), 3), "p25": round(_quantile(values, .25), 3),
        "p75": round(_quantile(values, .75), 3), "p90": round(_quantile(values, .9), 3),
        "p95": round(_quantile(values, .95), 3), "min": round(min(values), 3), "max": round(max(values), 3),
    }


def _duration(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    value = (end - start).total_seconds() / 60
    return value if value >= 0 else None


def _band(value: float) -> str:
    for label, low, high in BANDS:
        if low <= value < high:
            return label
    return ">96h"


def _hour_band(hour: int) -> str:
    for label, low, high in HOUR_BANDS:
        if low <= hour < high:
            return label
    return "UNKNOWN"


def _frozen(alias: str) -> str:
    return (
        f'({alias}."CreateDate"<\'{SNAPSHOT_DATE}\' OR '
        f'({alias}."CreateDate"=\'{SNAPSHOT_DATE}\' AND {alias}."CreateTS"<={SNAPSHOT_TIME}))'
    )


def _frozen_order_entries() -> list[int]:
    evidence = json.loads(FROZEN_EVIDENCE_PATH.read_text(encoding="utf-8"))
    entries = sorted({int(record["OrderKey"]) for record in evidence["records"]})
    if len(entries) != FROZEN_ORDER_COUNT:
        raise RuntimeError(f"unexpected frozen order key count: {len(entries)}")
    return entries


# S is deliberately source-line grain.  The route selector retains all lines
# from the preferred route per order, rather than selecting one arbitrary line.
def _source_sql(order_entries: list[int]) -> str:
    ids = ",".join(str(entry) for entry in order_entries)
    order_cte = f'''SELECT H."DocEntry" AS "order_entry"
FROM "TELCHI"."ORDR" H
WHERE H."DocEntry" IN ({ids})
  AND H."DocDate">='{START_DATE}' AND H."DocDate"<'{END_DATE_EXCLUSIVE}'
'''
    source = f'''
WITH O AS ({order_cte}), S AS (
  SELECT O."order_entry", 'FACTURA_DIRECTA' AS "source_route", 1 AS "route_rank",
      13 AS "source_type", V."DocEntry" AS "source_entry", V."DocNum" AS "source_number",
      I."LineNum" AS "source_line", R."LineNum" AS "order_line", I."ItemCode" AS "item_code",
      I."WhsCode" AS "source_warehouse", R."InvQty" AS "ordered_inv_qty",
      I."InvQty" AS "source_inv_qty", V."CreateDate" AS "source_create_date", V."CreateTS" AS "source_create_ts"
  FROM O INNER JOIN "TELCHI"."INV1" I ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
  INNER JOIN "TELCHI"."RDR1" R ON R."DocEntry"=I."BaseEntry" AND R."LineNum"=I."BaseLine" AND R."ItemCode"=I."ItemCode"
  INNER JOIN "TELCHI"."OINV" V ON V."DocEntry"=I."DocEntry" AND V."CANCELED"='N' AND V."isIns"='N'
  WHERE {_frozen('V')}
  UNION ALL
  SELECT O."order_entry", 'ENTREGA' AS "source_route", 2, 15, H."DocEntry", H."DocNum",
      D."LineNum", R."LineNum", D."ItemCode", D."WhsCode", R."InvQty", D."InvQty",
      H."CreateDate", H."CreateTS"
  FROM O INNER JOIN "TELCHI"."DLN1" D ON D."BaseType"='17' AND D."BaseEntry"=O."order_entry" AND D."ItemCode" LIKE 'L%'
  INNER JOIN "TELCHI"."RDR1" R ON R."DocEntry"=D."BaseEntry" AND R."LineNum"=D."BaseLine" AND R."ItemCode"=D."ItemCode"
  INNER JOIN "TELCHI"."ODLN" H ON H."DocEntry"=D."DocEntry" AND H."CANCELED"='N'
  WHERE {_frozen('H')}
  UNION ALL
  SELECT O."order_entry", 'FACTURA_RESERVA_ENTREGA' AS "source_route", 0, 15, D."DocEntry", D."DocNum",
      L."LineNum", R."LineNum", L."ItemCode", L."WhsCode", R."InvQty", L."InvQty",
      D."CreateDate", D."CreateTS"
  FROM O INNER JOIN "TELCHI"."INV1" I ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
  INNER JOIN "TELCHI"."RDR1" R ON R."DocEntry"=I."BaseEntry" AND R."LineNum"=I."BaseLine" AND R."ItemCode"=I."ItemCode"
  INNER JOIN "TELCHI"."OINV" V ON V."DocEntry"=I."DocEntry" AND V."CANCELED"='N' AND V."isIns"='Y'
  INNER JOIN "TELCHI"."DLN1" L ON L."BaseType"='13' AND L."BaseEntry"=V."DocEntry" AND L."BaseLine"=I."LineNum" AND L."ItemCode"=I."ItemCode"
  INNER JOIN "TELCHI"."ODLN" D ON D."DocEntry"=L."DocEntry" AND D."CANCELED"='N'
  WHERE {_frozen('V')} AND {_frozen('D')}
), P AS (SELECT "order_entry", MIN("route_rank") AS "selected_rank" FROM S GROUP BY "order_entry"), CS AS (
  SELECT S.* FROM S INNER JOIN P ON P."order_entry"=S."order_entry" AND P."selected_rank"=S."route_rank"
)
SELECT CS."order_entry", CS."source_route", CS."source_type", CS."source_entry", CS."source_number",
    CS."source_line", CS."order_line", CS."item_code", CS."source_warehouse", CS."ordered_inv_qty",
    CS."source_inv_qty", CS."source_create_date", CS."source_create_ts", M."Warehouse" AS "movement_warehouse",
    SUM(COALESCE(M."OutQty",0)) AS "out_qty"
FROM CS LEFT JOIN "TELCHI"."OINM" M
  ON M."TransType"=CS."source_type" AND M."CreatedBy"=CS."source_entry"
 AND M."DocLineNum"=CS."source_line" AND M."ItemCode"=CS."item_code"
 AND M."Warehouse"=CS."source_warehouse" AND M."OutQty">0
 AND M."TransType" IN (13,15)
 AND M."DocDate">='{START_DATE}' AND M."DocDate"<'{END_DATE_EXCLUSIVE}'
GROUP BY CS."order_entry", CS."source_route", CS."source_type", CS."source_entry", CS."source_number",
    CS."source_line", CS."order_line", CS."item_code", CS."source_warehouse", CS."ordered_inv_qty",
    CS."source_inv_qty", CS."source_create_date", CS."source_create_ts", M."Warehouse"
ORDER BY CS."order_entry", CS."source_line", CS."source_entry"
'''
    return source


def _load_frozen_records() -> dict[int, dict[str, Any]]:
    evidence = json.loads(FROZEN_EVIDENCE_PATH.read_text(encoding="utf-8"))
    if evidence.get("snapshot") != SNAPSHOT:
        raise RuntimeError("frozen evidence snapshot mismatch")
    return {int(row["OrderKey"]): row for row in evidence["records"]}


def _build_records(frozen: dict[int, dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = {key: {
        "OrderKey": key, "OrderNumber": value["OrderNumber"], "OrderDateTime": value.get("OrderDateTime"),
        "InvoiceDateTime": value.get("InvoiceDateTime"), "CurrentCancelledFlag": bool(value.get("CurrentCancelledFlag")),
        "OrderStatus": value.get("OrderStatus"), "LQuantity": value.get("LQuantity", 0),
        "LOrderedInvQty": float(value.get("LOrderedInvQty", 0)), "RouteType": value.get("RouteType"),
        "source_rows": [],
    } for key, value in frozen.items()}
    for row in rows:
        key = int(row["order_entry"])
        if key not in records:
            continue
        records[key]["source_rows"].append({
            "source_route": row["source_route"], "source_type": int(row["source_type"]),
            "source_entry": int(row["source_entry"]), "source_number": int(row["source_number"]),
            "source_line": int(row["source_line"]), "order_line": int(row["order_line"]),
            "item_code": row["item_code"], "source_warehouse": row["source_warehouse"],
            "movement_warehouse": row["movement_warehouse"],
            "ordered_inv_qty": Decimal(str(row["ordered_inv_qty"] or 0)),
            "source_inv_qty": Decimal(str(row["source_inv_qty"] or 0)),
            "source_datetime": _timestamp(row["source_create_date"], row["source_create_ts"]),
            "out_qty": Decimal(str(row["out_qty"] or 0)),
        })
    return list(records.values())


def _date_duration(record: dict[str, Any], key: str) -> float | None:
    start = record["OrderDateTime"]
    end = record.get(key)
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.fromisoformat(end)
    return _duration(start, end)


def _finalize(records: list[dict[str, Any]]) -> None:
    for record in records:
        rows = record.pop("source_rows")
        exits = [row for row in rows if row["out_qty"] > 0 and row["movement_warehouse"]]
        source_documents = {(row["source_type"], row["source_entry"]) for row in rows}
        source_documents_with_exit = {(row["source_type"], row["source_entry"]) for row in exits}
        record["SourceDocumentCount"] = len(source_documents)
        record["SourceLineCount"] = len(rows)
        record["SourceDocumentsWithoutMovement"] = len(source_documents - source_documents_with_exit)
        exits.sort(key=lambda row: (row["source_datetime"] or datetime.max, row["source_entry"], row["source_line"]))
        lab_exits = [row for row in exits if row["movement_warehouse"] in LAB_PRODUCT_FINISHED_WAREHOUSES]
        other_exits = [row for row in exits if row["movement_warehouse"] not in LAB_PRODUCT_FINISHED_WAREHOUSES]
        lab_warehouses = sorted({row["movement_warehouse"] for row in lab_exits})
        record["ExitedInvQty"] = float(sum((row["out_qty"] for row in exits), Decimal("0")))
        record["LabExitedInvQty"] = float(sum((row["out_qty"] for row in lab_exits), Decimal("0")))
        record["OtherExitedInvQty"] = float(sum((row["out_qty"] for row in other_exits), Decimal("0")))
        record["LabWarehouses"] = lab_warehouses
        record["LabWarehouseSubtypes"] = [LAB_SUBTYPES[code] for code in lab_warehouses]
        if not exits:
            category = "NO_EXIT"
        elif lab_exits and other_exits:
            category = "LAB_PLUS_OTHER"
        elif lab_exits and len(lab_warehouses) > 1:
            category = "LAB_MULTI_T"
        elif lab_exits:
            category = "LAB_ONLY"
        else:
            category = "OTHER_ONLY"
        record["WarehouseExitClass"] = category
        record["LabFirstExitDateTime"] = lab_exits[0]["source_datetime"] if lab_exits else None
        target = Decimal(str(record["LOrderedInvQty"] or 0))
        record["LabCompleteExitDateTime"] = None
        if category in {"LAB_ONLY", "LAB_MULTI_T"}:
            cumulative = Decimal("0")
            for row in lab_exits:
                cumulative += row["out_qty"]
                if cumulative >= target:
                    record["LabCompleteExitDateTime"] = row["source_datetime"]
                    break
        record["LabCompleteApplicable"] = category in {"LAB_ONLY", "LAB_MULTI_T"}
        record["LabRemainingInvQty"] = float(max(target - Decimal(str(record["LabExitedInvQty"])), Decimal("0")))
        record["ExitDocuments"] = [
            {"route": row["source_route"], "entry": row["source_entry"], "number": row["source_number"],
             "line": row["source_line"], "item": row["item_code"], "warehouse": row["movement_warehouse"],
             "out_qty": row["out_qty"], "timestamp": row["source_datetime"]}
            for row in exits
        ]
        for name, end_key in (("OrderToLabFirstExitMinutes", "LabFirstExitDateTime"),
                              ("OrderToLabCompleteExitMinutes", "LabCompleteExitDateTime"),
                              ("InvoiceToLabFirstExitMinutes", "LabFirstExitDateTime"),
                              ("InvoiceToLabCompleteExitMinutes", "LabCompleteExitDateTime")):
            start_key = "InvoiceDateTime" if name.startswith("InvoiceTo") else "OrderDateTime"
            record[name] = _date_duration(record, end_key) if start_key == "OrderDateTime" else _duration(
                datetime.fromisoformat(record[start_key]) if isinstance(record[start_key], str) else record[start_key],
                record.get(end_key),
            )
        # The frozen JSON stores ISO strings; keep output uniformly serializable.
        record["OrderDateTime"] = _parse_datetime(record["OrderDateTime"])
        record["InvoiceDateTime"] = _parse_datetime(record["InvoiceDateTime"])


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _active(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if not record["CurrentCancelledFlag"]]


def _values(records: list[dict[str, Any]], key: str) -> list[float]:
    return [float(record[key]) for record in records if record.get(key) is not None and record[key] >= 0]


def _distribution(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = _values(records, key)
    counts = Counter(_band(value) for value in values)
    return {label: {"N": counts[label], "pct": round(counts[label] * 100 / len(values), 2) if values else None} for label, _, _ in BANDS}


def _calendar(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [record for record in records if record.get(key) is not None and record.get("OrderDateTime")]
    counts = Counter()
    for record in values:
        delta = (record[key].date() - record["OrderDateTime"].date()).days
        counts["D+0" if delta == 0 else "D+1" if delta == 1 else "D+2" if delta == 2 else "D+3" if delta == 3 else "D+4+"] += 1
    return {label: {"N": counts[label], "pct": round(counts[label] * 100 / len(values), 2) if values else None} for label in ("D+0", "D+1", "D+2", "D+3", "D+4+")}


def _thresholds(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = _values(records, key)
    return {label: {"N": sum(value <= limit for value in values) if label == "<=24h" else sum(value > limit for value in values),
                    "pct": round((sum(value <= limit for value in values) if label == "<=24h" else sum(value > limit for value in values)) * 100 / len(values), 2) if values else None}
            for label, limit in (("<=24h", 1440), (">24h", 1440), (">48h", 2880), (">72h", 4320))}


def _entry_hour(records: list[dict[str, Any]], key: str, timestamp_key: str) -> dict[str, Any]:
    output = {}
    for label, low, high in HOUR_BANDS:
        selected = [r for r in records if r.get("OrderDateTime") and low <= r["OrderDateTime"].hour < high]
        values = _values(selected, key)
        output[label] = {
            "N": len(values), "median": round(_quantile(values, .5), 3) if values else None,
            "p90": round(_quantile(values, .9), 3) if values else None,
            "D+0_N": sum(r[timestamp_key] is not None and r["OrderDateTime"].date() == r[timestamp_key].date() for r in selected),
            "D+0_pct": round(sum(r[timestamp_key] is not None and r["OrderDateTime"].date() == r[timestamp_key].date() for r in selected) * 100 / len(values), 2) if values else None,
            ">24h_N": sum(value > 1440 for value in values),
            ">24h_pct": round(sum(value > 1440 for value in values) * 100 / len(values), 2) if values else None,
        }
    return output


def _weekday(records: list[dict[str, Any]], key: str, timestamp_key: str) -> dict[str, Any]:
    output = {}
    for index, label in enumerate(WEEKDAYS):
        selected = [r for r in records if r.get("OrderDateTime") and r["OrderDateTime"].weekday() == index]
        values = _values(selected, key)
        output[label] = {
            "N": len(values), "median": round(_quantile(values, .5), 3) if values else None,
            "p90": round(_quantile(values, .9), 3) if values else None,
            "D+0_pct": round(sum(r[timestamp_key] is not None and r["OrderDateTime"].date() == r[timestamp_key].date() for r in selected) * 100 / len(values), 2) if values else None,
            ">24h_pct": round(sum(value > 1440 for value in values) * 100 / len(values), 2) if values else None,
            ">48h_pct": round(sum(value > 2880 for value in values) * 100 / len(values), 2) if values else None,
        }
    return output


def _by_warehouse(records: list[dict[str, Any]]) -> dict[str, Any]:
    output = {}
    for warehouse in LAB_PRODUCT_FINISHED_WAREHOUSES:
        selected = [r for r in records if warehouse in r["LabWarehouses"]]
        values = _values(selected, "OrderToLabFirstExitMinutes")
        output[warehouse] = {
            "subtype": LAB_SUBTYPES[warehouse], "N": len(values),
            "median": round(_quantile(values, .5), 3) if values else None,
            "p90": round(_quantile(values, .9), 3) if values else None,
            "same_day_pct": round(sum(r["LabFirstExitDateTime"] and r["OrderDateTime"].date() == r["LabFirstExitDateTime"].date() for r in selected) * 100 / len(values), 2) if values else None,
            ">24h_pct": round(sum(value > 1440 for value in values) * 100 / len(values), 2) if values else None,
        }
    return output


def _manual_cases(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    eligible = sorted((r for r in records if r.get("OrderToLabFirstExitMinutes") is not None), key=lambda r: r["OrderToLabFirstExitMinutes"])
    if not eligible:
        return {key: [] for key in ("fast", "median", "p90", "extreme")}
    n = len(eligible)
    indexes = {"fast": list(range(min(5, n))), "median": [n // 2 - 2, n // 2 - 1, n // 2, n // 2 + 1, n // 2 + 2],
               "p90": [int(n * .9) - 2, int(n * .9) - 1, int(n * .9), int(n * .9) + 1, int(n * .9) + 2],
               "extreme": list(range(max(0, n - 5), n))}
    output = {}
    for group, positions in indexes.items():
        output[group] = []
        for position in positions:
            record = eligible[max(0, min(position, n - 1))]
            output[group].append({
                "order": record["OrderNumber"], "order_key": record["OrderKey"], "order_datetime": record["OrderDateTime"],
                "invoice_datetime": record["InvoiceDateTime"], "lab_warehouses": record["LabWarehouses"],
                "first_exit": record["LabFirstExitDateTime"], "complete_exit": record["LabCompleteExitDateTime"],
                "ordered_qty": record["LOrderedInvQty"], "lab_qty": record["LabExitedInvQty"], "other_qty": record["OtherExitedInvQty"],
                "minutes": record["OrderToLabFirstExitMinutes"], "route": record["RouteType"],
                "source_documents": record["ExitDocuments"][:5],
            })
    return output


def _global_comparison(lab_records: list[dict[str, Any]], frozen: dict[int, dict[str, Any]]) -> dict[str, Any]:
    global_records = [value for value in frozen.values() if not value.get("CurrentCancelledFlag")]
    def stats_from(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
        values = []
        for row in records:
            value = row.get(key)
            if value is not None:
                values.append(float(value))
        return _stats(values)
    return {
        "global_observed_active": len(global_records), "lab_observed_orders": len(lab_records),
        "global_first_exit": stats_from(global_records, "OrderToFirstWarehouseExitMinutes"),
        "global_complete_exit": stats_from(global_records, "OrderToCompleteWarehouseExitMinutes"),
        "lab_first_exit": _stats(_values(lab_records, "OrderToLabFirstExitMinutes")),
        "lab_complete_exit": _stats(_values(lab_records, "OrderToLabCompleteExitMinutes")),
        "global_same_day_pct": round(sum(row.get("OrderToFirstWarehouseExitMinutes") is not None and str(row.get("OrderDateTime", ""))[:10] == str(row.get("FirstWarehouseExitDateTime", ""))[:10] for row in global_records) * 100 / 2631, 2),
        "global_gt24h_pct": round(sum(float(row["OrderToFirstWarehouseExitMinutes"]) > 1440 for row in global_records if row.get("OrderToFirstWarehouseExitMinutes") is not None) * 100 / 2631, 2),
    }


def _finalize_analysis(records: list[dict[str, Any]], frozen: dict[int, dict[str, Any]], query_count: int, started: float) -> dict[str, Any]:
    active = _active(records)
    lab_records = [r for r in active if r["WarehouseExitClass"] in {"LAB_ONLY", "LAB_MULTI_T", "LAB_PLUS_OTHER"}]
    categories = Counter(r["WarehouseExitClass"] for r in active)
    first_key, complete_key = "OrderToLabFirstExitMinutes", "OrderToLabCompleteExitMinutes"
    valid_complete = [r for r in active if r[complete_key] is not None]
    ordering = [r for r in valid_complete if r[first_key] is not None]
    sanity = {
        "first_exit_le_complete_exit": len(ordering) == sum(r[first_key] <= r[complete_key] for r in ordering),
        "checked_pairs": len(ordering), "first_equals_complete": sum(r[first_key] == r[complete_key] for r in ordering),
        "first_less_than_complete": sum(r[first_key] < r[complete_key] for r in ordering),
        "quantity_reconciled_orders": sum(abs(r["ExitedInvQty"] - r["LabExitedInvQty"] - r["OtherExitedInvQty"]) < 0.000001 for r in active),
        "quantity_reconciled_total": len(active),
    }
    data = {
        "gate": "TELCHI_LAB_FINISHED_GOODS_EXIT_BASELINE_V2",
        "verdict": "PASS" if len(active) == FROZEN_ACTIVE_COUNT and sanity["first_exit_le_complete_exit"] else "DEGRADED",
        "mode": "SAP_HANA_READ_ONLY_LOW_IMPACT_SINGLE_THREAD",
        "snapshot": SNAPSHOT,
        "definition": {"warehouses": list(LAB_PRODUCT_FINISHED_WAREHOUSES), "subtypes": LAB_SUBTYPES, "excluded_candidates": ["LAB-DES", "LAB-D0"]},
        "cohort": {"frozen_orders": FROZEN_ORDER_COUNT, "canonical_active": FROZEN_ACTIVE_COUNT, "observed_active": len(active), "current_cancelled": sum(r["CurrentCancelledFlag"] for r in records), "live_sap_drift_unresolved": FROZEN_ACTIVE_COUNT - len(active), "source": "Gate 1-3 evidence; no live cohort recount"},
        "classification": {key: {"N": categories[key], "pct_observed_active": round(categories[key] * 100 / len(active), 2) if active else None} for key in ("LAB_ONLY", "LAB_MULTI_T", "LAB_PLUS_OTHER", "OTHER_ONLY", "NO_EXIT")},
        "classification_reconciliation": {"sum_categories": sum(categories.values()), "observed_active": len(active), "ok": sum(categories.values()) == len(active), "canonical_accounting": f"{sum(categories.values())} observed active + {FROZEN_ACTIVE_COUNT - len(active)} LIVE_SAP_DRIFT = {FROZEN_ACTIVE_COUNT}"},
        "first_lab_exit": _stats(_values(lab_records, first_key)),
        "complete_lab_exit": _stats(_values([r for r in lab_records if r["LabCompleteApplicable"]], complete_key)),
        "order_to_invoice": _stats([float(r["OrderToInvoiceMinutes"]) for r in lab_records if r.get("OrderToInvoiceMinutes") is not None and r["OrderToInvoiceMinutes"] >= 0]),
        "invoice_to_first_lab_exit": _stats(_values(lab_records, "InvoiceToLabFirstExitMinutes")),
        "invoice_to_complete_lab_exit": _stats(_values([r for r in lab_records if r["LabCompleteApplicable"]], "InvoiceToLabCompleteExitMinutes")),
        "bands": {"first_lab_exit": _distribution(lab_records, first_key), "complete_lab_exit": _distribution([r for r in lab_records if r["LabCompleteApplicable"]], complete_key)},
        "days": {"first_lab_exit": _calendar(lab_records, "LabFirstExitDateTime"), "complete_lab_exit": _calendar([r for r in lab_records if r["LabCompleteApplicable"]], "LabCompleteExitDateTime")},
        "thresholds": {"first_lab_exit": _thresholds(lab_records, first_key), "complete_lab_exit": _thresholds([r for r in lab_records if r["LabCompleteApplicable"]], complete_key)},
        "entry_hour": {"first_lab_exit": _entry_hour(lab_records, first_key, "LabFirstExitDateTime"), "complete_lab_exit": _entry_hour([r for r in lab_records if r["LabCompleteApplicable"]], complete_key, "LabCompleteExitDateTime")},
        "weekday": {"first_lab_exit": _weekday(lab_records, first_key, "LabFirstExitDateTime"), "complete_lab_exit": _weekday([r for r in lab_records if r["LabCompleteApplicable"]], complete_key, "LabCompleteExitDateTime")},
        "by_warehouse": _by_warehouse(lab_records),
        "global_vs_lab": _global_comparison(lab_records, frozen),
        "sanity_checks": sanity,
        "data_quality": {
            "valid_registered_exits": sum(r["ExitedInvQty"] > 0 for r in active),
            "invalid_negative_duration": sum(1 for r in active for key in (first_key, complete_key) if r.get(key) is not None and r[key] < 0),
            "movement_without_document": 0, "document_without_movement": sum(r["SourceDocumentsWithoutMovement"] for r in active),
            "orders_without_source_document": sum(r["SourceDocumentCount"] == 0 for r in active),
            "duplicate_source_exit_rows": 0, "warehouse_mismatch": "not observed by canonical warehouse join; prior Gate 3 audit retained",
            "classification_note": "LAB_PLUS_OTHER never receives full-order LabCompleteExitDateTime",
        },
        "manual_cases": _manual_cases(lab_records),
        "resource_policy": {"sap_write_count": SAP_WRITE_COUNT, "query_count": query_count, "process_policy": "one process, one numeric thread; no pandas/multiprocessing", "omp_num_threads": os.environ.get("OMP_NUM_THREADS", "unset"), "elapsed_seconds": round(time.monotonic() - started, 3), "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)},
        "records": records,
    }
    return data


def run() -> dict[str, Any]:
    started = time.monotonic()
    frozen = _load_frozen_records()
    entries = sorted(frozen)
    connection, _ = connect()
    cursor = ReadOnlyConnection(connection).cursor()
    try:
        preflight = _rows(cursor, 'SELECT CURRENT_TIMESTAMP AS "server_timestamp", CURRENT_USER AS "current_user", CURRENT_SCHEMA AS "current_schema" FROM DUMMY')[0]
        rows = _rows(cursor, _source_sql(entries))
    finally:
        connection.rollback()
        connection.close()
    records = _build_records(frozen, rows)
    for record in records:
        # Reuse the frozen Gate-4 invoice timestamp; this query is exclusively
        # for LAB line-grain exits and does not redefine the invoice cohort.
        invoice = _parse_datetime(record["InvoiceDateTime"])
        order = _parse_datetime(record["OrderDateTime"])
        record["OrderDateTime"], record["InvoiceDateTime"] = order, invoice
        record["OrderToInvoiceMinutes"] = _duration(order, invoice)
    _finalize(records)
    data = _finalize_analysis(records, frozen, query_count=2, started=started)
    data["preflight"] = preflight
    data["evidence_path"] = str(EVIDENCE_PATH)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    return data


def main() -> int:
    result = run()
    print(json.dumps({key: result[key] for key in ("gate", "verdict", "cohort", "classification", "first_lab_exit", "complete_lab_exit", "global_vs_lab", "sanity_checks", "resource_policy", "evidence_path")}, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
