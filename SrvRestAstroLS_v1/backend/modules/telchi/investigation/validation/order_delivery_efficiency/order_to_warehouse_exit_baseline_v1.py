"""Gate 4: quantitative baseline from SAP order creation to registered inventory exit.

This runner reuses the frozen Gate 1-3 contract and performs only two bounded,
SELECT-only HANA queries: one for order/source-exit rows and one for invoice
candidates. It never reconstructs the cohort from current cancellation status;
that status is retained only as a drift diagnostic. Statistics are calculated
locally from the compact order/document result, without pandas or parallelism.
"""
from __future__ import annotations

import json
import math
import os
import resource
import time
from collections import Counter, defaultdict
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection

START_DATE = "2026-08-15"
END_DATE_EXCLUSIVE = "2026-09-15"
SNAPSHOT_DATE = "2026-09-14"
SNAPSHOT_TIME = 112115
MAX_ORDER_DOCENTRY = 215152
SAP_WRITE_COUNT = 0
CANONICAL_ACTIVE = 2842
CANONICAL_FIRST_EXIT = 2631
CANONICAL_COMPLETE_EXIT = 2561
CANONICAL_PARTIAL = 70
CANONICAL_NO_EXIT = 211
CANONICAL_CANCELLED = 185

EVIDENCE_DIR = EVIDENCE_ROOT / "order_delivery_efficiency" / "evidence"
EVIDENCE_PATH = EVIDENCE_DIR / "order_to_warehouse_exit_baseline_v1.json"

BANDS = (
    ("<30m", 0, 30),
    ("30–60m", 30, 60),
    ("1–2h", 60, 120),
    ("2–4h", 120, 240),
    ("4–8h", 240, 480),
    ("8–12h", 480, 720),
    ("12–24h", 720, 1440),
    (">24h", 1440, math.inf),
)
HOUR_BANDS = (
    ("00–07", 0, 7),
    ("07–09", 7, 9),
    ("09–11", 9, 11),
    ("11–13", 11, 13),
    ("13–15", 13, 15),
    ("15–17", 15, 17),
    ("17–19", 17, 19),
    ("19–24", 19, 24),
)


def _frozen(alias: str) -> str:
    return (
        f'({alias}."CreateDate"<\'{SNAPSHOT_DATE}\' OR '
        f'({alias}."CreateDate"=\'{SNAPSHOT_DATE}\' '
        f'AND {alias}."CreateTS"<={SNAPSHOT_TIME}))'
    )


ORDER_CTE = f'''
SELECT H."DocEntry" AS "order_entry", H."DocNum" AS "order_number",
    H."CANCELED" AS "current_canceled", H."DocStatus" AS "order_status",
    H."CreateDate" AS "order_create_date", H."CreateTS" AS "order_create_ts",
    H."BPLId" AS "branch", H."SlpCode" AS "salesperson",
    H."UserSign" AS "user_sign", H."U_ORIGIN" AS "channel",
    H."U_OSLP_ID" AS "route_id",
    COUNT(CASE WHEN R."ItemCode" LIKE 'L%' THEN 1 END) AS "l_line_count",
    COUNT(DISTINCT CASE WHEN R."ItemCode" LIKE 'L%' THEN R."ItemCode" END)
        AS "l_item_count",
    SUM(CASE WHEN R."ItemCode" LIKE 'L%' THEN R."Quantity" ELSE 0 END)
        AS "l_quantity",
    SUM(CASE WHEN R."ItemCode" LIKE 'L%' THEN R."InvQty" ELSE 0 END)
        AS "l_ordered_inv_qty",
    MAX(CASE WHEN R."ItemCode" NOT LIKE 'L%' THEN 1 ELSE 0 END) AS "mixed_flag",
    CASE WHEN COUNT(DISTINCT CASE WHEN R."ItemCode" LIKE 'L%' THEN R."WhsCode" END)=1
         THEN MIN(CASE WHEN R."ItemCode" LIKE 'L%' THEN R."WhsCode" END)
         ELSE 'MULTIPLE' END AS "warehouse"
FROM "TELCHI"."ORDR" H
INNER JOIN "TELCHI"."RDR1" R ON R."DocEntry"=H."DocEntry"
WHERE H."DocDate">='{START_DATE}' AND H."DocDate"<'{END_DATE_EXCLUSIVE}'
  AND H."DocEntry"<={MAX_ORDER_DOCENTRY}
GROUP BY H."DocEntry", H."DocNum", H."CANCELED", H."DocStatus",
    H."CreateDate", H."CreateTS", H."BPLId", H."SlpCode", H."UserSign",
    H."U_ORIGIN", H."U_OSLP_ID"
HAVING COUNT(CASE WHEN R."ItemCode" LIKE 'L%' THEN 1 END)>0
'''

# The source CTE is line-grain until the exact OINM join. This prevents
# BASE_REF fanout and retains the Gate 3 canonical key.
SOURCE_CTE = f'''
SELECT O."order_entry", 'FACTURA_DIRECTA' AS "source_route", 13 AS "source_type",
    V."DocEntry" AS "source_entry", I."LineNum" AS "source_line",
    I."ItemCode" AS "item_code", I."WhsCode" AS "warehouse",
    V."CreateDate" AS "source_create_date", V."CreateTS" AS "source_create_ts"
FROM O
INNER JOIN "TELCHI"."INV1" I
    ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."OINV" V
    ON V."DocEntry"=I."DocEntry" AND V."CANCELED"='N' AND V."isIns"='N'
WHERE {_frozen('V')}
UNION ALL
SELECT O."order_entry", 'ENTREGA' AS "source_route", 15,
    D."DocEntry", L."LineNum", L."ItemCode", L."WhsCode",
    D."CreateDate", D."CreateTS"
FROM O
INNER JOIN "TELCHI"."DLN1" L
    ON L."BaseType"='17' AND L."BaseEntry"=O."order_entry" AND L."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."ODLN" D
    ON D."DocEntry"=L."DocEntry" AND D."CANCELED"='N'
WHERE {_frozen('D')}
UNION ALL
SELECT O."order_entry", 'FACTURA_RESERVA_ENTREGA' AS "source_route", 15,
    D."DocEntry", L."LineNum", L."ItemCode", L."WhsCode",
    D."CreateDate", D."CreateTS"
FROM O
INNER JOIN "TELCHI"."INV1" I
    ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."OINV" V
    ON V."DocEntry"=I."DocEntry" AND V."CANCELED"='N' AND V."isIns"='Y'
INNER JOIN "TELCHI"."DLN1" L
    ON L."BaseType"='13' AND L."BaseEntry"=V."DocEntry"
   AND L."BaseLine"=I."LineNum" AND L."ItemCode"=I."ItemCode"
INNER JOIN "TELCHI"."ODLN" D
    ON D."DocEntry"=L."DocEntry" AND D."CANCELED"='N'
WHERE {_frozen('V')} AND {_frozen('D')}
'''

DOC_REF_CTE = '''
SELECT O."order_entry", 'FACTURA_DIRECTA' AS "ref_route"
FROM O INNER JOIN "TELCHI"."INV1" I
  ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."OINV" V
  ON V."DocEntry"=I."DocEntry" AND V."CANCELED"='N' AND V."isIns"='N'
WHERE {frozen_v}
UNION ALL
SELECT O."order_entry", 'FACTURA_RESERVA_ENTREGA'
FROM O INNER JOIN "TELCHI"."INV1" I
  ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."OINV" V
  ON V."DocEntry"=I."DocEntry" AND V."CANCELED"='N' AND V."isIns"='Y'
WHERE {frozen_v}
UNION ALL
SELECT O."order_entry", 'ENTREGA'
FROM O INNER JOIN "TELCHI"."DLN1" L
  ON L."BaseType"='17' AND L."BaseEntry"=O."order_entry" AND L."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."ODLN" D
  ON D."DocEntry"=L."DocEntry" AND D."CANCELED"='N'
WHERE {frozen_d}
'''

DATA_SQL = f'''SELECT * FROM (
WITH O AS ({ORDER_CTE}), S AS ({SOURCE_CTE}),
DREF AS ({DOC_REF_CTE.format(frozen_v=_frozen('V'), frozen_d=_frozen('D'))}),
DR AS (
  SELECT "order_entry",
    MAX(CASE WHEN "ref_route"='FACTURA_DIRECTA' THEN 1 ELSE 0 END) AS "has_direct_invoice",
    MAX(CASE WHEN "ref_route"='FACTURA_RESERVA_ENTREGA' THEN 1 ELSE 0 END) AS "has_reserve_invoice",
    MAX(CASE WHEN "ref_route"='ENTREGA' THEN 1 ELSE 0 END) AS "has_order_delivery"
  FROM DREF GROUP BY "order_entry"
), E AS (
  SELECT S."order_entry", S."source_route", S."source_type", S."source_entry",
      S."source_create_date", S."source_create_ts",
      SUM(M."OutQty") AS "exited_qty", COUNT(DISTINCT S."source_line") AS "source_lines"
  FROM S
  INNER JOIN "TELCHI"."OINM" M
    ON M."TransType"=S."source_type" AND M."CreatedBy"=S."source_entry"
   AND M."DocLineNum"=S."source_line" AND M."ItemCode"=S."item_code"
   AND M."Warehouse"=S."warehouse" AND M."OutQty">0
  GROUP BY S."order_entry", S."source_route", S."source_type", S."source_entry",
      S."source_create_date", S."source_create_ts"
)
SELECT O.*, COALESCE(DR."has_direct_invoice",0) AS "has_direct_invoice",
    COALESCE(DR."has_reserve_invoice",0) AS "has_reserve_invoice",
    COALESCE(DR."has_order_delivery",0) AS "has_order_delivery",
    E."source_route", E."source_type", E."source_entry", E."source_create_date",
    E."source_create_ts", E."exited_qty", E."source_lines"
FROM O LEFT JOIN DR ON DR."order_entry"=O."order_entry"
LEFT JOIN E ON E."order_entry"=O."order_entry"
) Q ORDER BY Q."order_entry", Q."source_create_date", Q."source_create_ts", Q."source_entry"'''

INVOICE_SQL = f'''SELECT * FROM (
WITH O AS ({ORDER_CTE})
SELECT O."order_entry", 'FACTURA_DIRECTA' AS "invoice_route", V."DocEntry" AS "invoice_entry",
    V."CreateDate" AS "invoice_create_date", V."CreateTS" AS "invoice_create_ts"
FROM O INNER JOIN "TELCHI"."INV1" I
  ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."OINV" V
  ON V."DocEntry"=I."DocEntry" AND V."CANCELED"='N' AND V."isIns"='N'
WHERE {_frozen('V')}
GROUP BY O."order_entry", V."DocEntry", V."CreateDate", V."CreateTS"
UNION ALL
SELECT O."order_entry", 'FACTURA_RESERVA_ENTREGA', V."DocEntry", V."CreateDate", V."CreateTS"
FROM O INNER JOIN "TELCHI"."INV1" I
  ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."OINV" V
  ON V."DocEntry"=I."DocEntry" AND V."CANCELED"='N' AND V."isIns"='Y'
WHERE {_frozen('V')}
GROUP BY O."order_entry", V."DocEntry", V."CreateDate", V."CreateTS"
UNION ALL
SELECT O."order_entry", 'ENTREGA', IH."DocEntry", IH."CreateDate", IH."CreateTS"
FROM O INNER JOIN "TELCHI"."DLN1" D
  ON D."BaseType"='17' AND D."BaseEntry"=O."order_entry" AND D."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."INV1" I
  ON I."BaseType"='15' AND I."BaseEntry"=D."DocEntry"
 AND I."BaseLine"=D."LineNum" AND I."ItemCode"=D."ItemCode"
INNER JOIN "TELCHI"."OINV" IH
  ON IH."DocEntry"=I."DocEntry" AND IH."CANCELED"='N'
WHERE {_frozen('IH')}
GROUP BY O."order_entry", IH."DocEntry", IH."CreateDate", IH."CreateTS"
) Q ORDER BY Q."order_entry", Q."invoice_create_date", Q."invoice_create_ts", Q."invoice_entry"'''


def _rows(cursor: Any, sql: str) -> list[dict[str, Any]]:
    cursor.execute(sql)
    columns = [item[0].lower() for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _json_default(value: Any) -> str | float:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _timestamp(value_date: Any, value_ts: Any) -> datetime | None:
    if value_date is None or value_ts is None:
        return None
    if isinstance(value_date, datetime):
        day = value_date.date()
    elif isinstance(value_date, date):
        day = value_date
    else:
        day = date.fromisoformat(str(value_date)[:10])
    try:
        raw = int(value_ts)
        hh, rest = divmod(raw, 10000)
        mm, ss = divmod(rest, 100)
        return datetime.combine(day, dt_time(hh, mm, ss))
    except (TypeError, ValueError):
        return None


def _route(row: dict[str, Any]) -> str:
    if int(row.get("has_reserve_invoice") or 0):
        return "FACTURA_RESERVA_ENTREGA"
    if int(row.get("has_order_delivery") or 0):
        return "ENTREGA"
    if int(row.get("has_direct_invoice") or 0):
        return "FACTURA_DIRECTA"
    return "SIN_DOCUMENTO_POSTERIOR"


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires values")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {key: None for key in ("N", "mean", "median", "p25", "p75", "p90", "p95", "min", "max")}
    return {
        "N": len(values),
        "mean": round(mean(values), 3),
        "median": round(_quantile(values, 0.50), 3),
        "p25": round(_quantile(values, 0.25), 3),
        "p75": round(_quantile(values, 0.75), 3),
        "p90": round(_quantile(values, 0.90), 3),
        "p95": round(_quantile(values, 0.95), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def _duration(start: datetime | None, end: datetime | None) -> tuple[float | None, str]:
    if start is None or end is None:
        return None, "UNKNOWN"
    minutes = (end - start).total_seconds() / 60
    if minutes < 0:
        return minutes, "INVALID_TIMESTAMP"
    return minutes, "VALID"


def _band(minutes: float) -> str:
    for label, low, high in BANDS:
        if low <= minutes < high:
            return label
    return ">24h"


def _hour_band(hour: int) -> str:
    for label, low, high in HOUR_BANDS:
        if low <= hour < high:
            return label
    return "UNKNOWN"


def _calendar_class(start: datetime, end: datetime) -> str:
    delta_days = (end.date() - start.date()).days
    if delta_days == 0:
        return "SAME_DAY"
    if delta_days == 1:
        return "NEXT_CALENDAR_DAY"
    return "GREATER_THAN_1_CALENDAR_DAY"


def _record_from_rows(order_rows: list[dict[str, Any]], invoice_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    invoices: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in invoice_rows:
        invoices[int(row["order_entry"])].append(row)

    grouped: dict[int, dict[str, Any]] = {}
    for row in order_rows:
        entry = int(row["order_entry"])
        record = grouped.setdefault(entry, {
            "OrderKey": entry,
            "OrderNumber": int(row["order_number"]),
            "OrderDateTime": _timestamp(row["order_create_date"], row["order_create_ts"]),
            "SnapshotDateTime": datetime(2026, 9, 14, 11, 21, 15),
            "CurrentCancelledFlag": row["current_canceled"] == "Y",
            "OrderStatus": row["order_status"],
            "Channel": row["channel"] or "UNCLASSIFIED",
            "Branch": row["branch"],
            "Warehouse": row["warehouse"],
            "Salesperson": row["salesperson"],
            "RouteId": row["route_id"],
            "LLineCount": int(row["l_line_count"] or 0),
            "LItemCount": int(row["l_item_count"] or 0),
            "LQuantity": float(row["l_quantity"] or 0),
            "LOrderedInvQty": Decimal(str(row["l_ordered_inv_qty"] or 0)),
            "MixedOrderFlag": bool(row["mixed_flag"] or 0),
            "RouteType": _route(row),
            "FirstWarehouseExitDateTime": None,
            "CompleteWarehouseExitDateTime": None,
            "PartialExitFlag": False,
            "FirstExitEvidenceClass": "NOT_AVAILABLE",
            "CompleteExitFlag": False,
            "_exit_docs": [],
            "_invoice_candidates": invoices.get(entry, []),
        })
        if row["source_entry"] is not None:
            record["_exit_docs"].append({
                "source_route": row["source_route"],
                "source_entry": int(row["source_entry"]),
                "source_type": int(row["source_type"]),
                "source_datetime": _timestamp(row["source_create_date"], row["source_create_ts"]),
                "exited_qty": Decimal(str(row["exited_qty"] or 0)),
                "source_lines": int(row["source_lines"] or 0),
            })
    return list(grouped.values())


def _choose_invoice(record: dict[str, Any]) -> datetime | None:
    candidates = []
    for row in record["_invoice_candidates"]:
        stamp = _timestamp(row["invoice_create_date"], row["invoice_create_ts"])
        if stamp is not None:
            candidates.append(stamp)
    return min(candidates) if candidates else None


def _finalize_records(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    for record in records:
        docs = sorted(record["_exit_docs"], key=lambda x: (x["source_datetime"] or datetime.max, x["source_entry"]))
        first = next((doc["source_datetime"] for doc in docs if doc["source_datetime"] is not None), None)
        cumulative = Decimal("0")
        complete = None
        target = record["LOrderedInvQty"]
        for doc in docs:
            cumulative += doc["exited_qty"]
            if complete is None and doc["source_datetime"] is not None and cumulative >= target:
                complete = doc["source_datetime"]
        record["InvoiceDateTime"] = _choose_invoice(record)
        record["FirstWarehouseExitDateTime"] = first
        record["CompleteWarehouseExitDateTime"] = complete
        record["ExitedInvQty"] = sum((doc["exited_qty"] for doc in docs), Decimal("0"))
        record["RemainingInvQty"] = max(target - record["ExitedInvQty"], Decimal("0"))
        record["PartialExitFlag"] = first is not None and complete is None
        record["CompleteExitFlag"] = complete is not None
        record["FirstExitEvidenceClass"] = (
            "WAREHOUSE_EXIT_CONFIRMED" if first is not None else "NOT_AVAILABLE"
        )
        for key in ("_exit_docs", "_invoice_candidates"):
            record.pop(key, None)

    active = [record for record in records if not record["CurrentCancelledFlag"]]
    metric_values: dict[str, list[float]] = defaultdict(list)
    metric_quality: Counter[str] = Counter()
    calendar: dict[str, Counter[str]] = {
        "OrderToFirstWarehouseExit": Counter(),
        "OrderToCompleteWarehouseExit": Counter(),
    }
    bands: dict[str, Counter[str]] = {
        "OrderToFirstWarehouseExit": Counter(),
        "OrderToCompleteWarehouseExit": Counter(),
    }
    for record in active:
        for name, end_key in (
            ("OrderToInvoice", "InvoiceDateTime"),
            ("OrderToFirstWarehouseExit", "FirstWarehouseExitDateTime"),
            ("OrderToCompleteWarehouseExit", "CompleteWarehouseExitDateTime"),
        ):
            value, quality = _duration(record["OrderDateTime"], record[end_key])
            metric_quality[f"{name}:{quality}"] += 1
            if value is not None and value >= 0:
                metric_values[name].append(value)
                if name != "OrderToInvoice":
                    bands[name][_band(value)] += 1
                    if record["OrderDateTime"] and record[end_key]:
                        calendar[name][_calendar_class(record["OrderDateTime"], record[end_key])] += 1
        for name, end_key in (
            ("InvoiceToFirstWarehouseExit", "FirstWarehouseExitDateTime"),
            ("InvoiceToCompleteWarehouseExit", "CompleteWarehouseExitDateTime"),
        ):
            value, quality = _duration(record["InvoiceDateTime"], record[end_key])
            if quality == "INVALID_TIMESTAMP" and record["RouteType"] == "ENTREGA":
                quality = "SEMANTIC_EXCEPTION"
            metric_quality[f"{name}:{quality}"] += 1
            if value is not None and value >= 0:
                metric_values[name].append(value)

    stats = {name: _stats(values) for name, values in metric_values.items()}
    for name in ("OrderToInvoice", "OrderToFirstWarehouseExit", "OrderToCompleteWarehouseExit", "InvoiceToFirstWarehouseExit", "InvoiceToCompleteWarehouseExit"):
        stats.setdefault(name, _stats([]))

    def ratio(counter: Counter[str], key: str) -> dict[str, Any]:
        n = sum(counter.values())
        return {"N": counter[key], "pct": round(counter[key] * 100 / n, 2) if n else None}

    bands_out = {}
    for name, counter in bands.items():
        n = sum(counter.values())
        bands_out[name] = {
            label: {"N": counter[label], "pct": round(counter[label] * 100 / n, 2) if n else None}
            for label, _, _ in BANDS
        }
    calendar_out = {}
    for name, counter in calendar.items():
        n = sum(counter.values())
        calendar_out[name] = {
            key: {"N": counter[key], "pct": round(counter[key] * 100 / n, 2) if n else None}
            for key in ("SAME_DAY", "NEXT_CALENDAR_DAY", "GREATER_THAN_1_CALENDAR_DAY")
        }
        valid = sum(counter.values())
        le24 = sum(1 for record in active if record.get("OrderDateTime") and record.get("FirstWarehouseExitDateTime" if name.endswith("FirstWarehouseExit") else "CompleteWarehouseExitDateTime") and _duration(record["OrderDateTime"], record["FirstWarehouseExitDateTime" if name.endswith("FirstWarehouseExit") else "CompleteWarehouseExitDateTime"])[0] is not None and 0 <= _duration(record["OrderDateTime"], record["FirstWarehouseExitDateTime" if name.endswith("FirstWarehouseExit") else "CompleteWarehouseExitDateTime"])[0] <= 1440)
        calendar_out[name]["<=24h"] = {"N": le24, "pct": round(le24 * 100 / valid, 2) if valid else None}
        calendar_out[name][">24h"] = {"N": valid - le24, "pct": round((valid - le24) * 100 / valid, 2) if valid else None}

    entry_hour: dict[str, list[dict[str, Any]]] = {}
    for label, low, high in HOUR_BANDS:
        selected = [r for r in active if r["OrderDateTime"] and low <= r["OrderDateTime"].hour < high]
        first_values = [_duration(r["OrderDateTime"], r["FirstWarehouseExitDateTime"])[0] for r in selected]
        complete_values = [_duration(r["OrderDateTime"], r["CompleteWarehouseExitDateTime"])[0] for r in selected]
        first_values = [v for v in first_values if v is not None and v >= 0]
        complete_values = [v for v in complete_values if v is not None and v >= 0]
        same_day = sum(1 for r in selected if r["OrderDateTime"] and r["FirstWarehouseExitDateTime"] and r["OrderDateTime"].date() == r["FirstWarehouseExitDateTime"].date())
        le24 = sum(1 for v in first_values if v <= 1440)
        entry_hour[label] = {
            "N": len(selected),
            "first_median": round(_quantile(first_values, .5), 3) if first_values else None,
            "first_p90": round(_quantile(first_values, .9), 3) if first_values else None,
            "complete_median": round(_quantile(complete_values, .5), 3) if complete_values else None,
            "complete_p90": round(_quantile(complete_values, .9), 3) if complete_values else None,
            "same_day_N": same_day,
            "same_day_pct": round(same_day * 100 / len(first_values), 2) if first_values else None,
            "le24_N": le24,
            "le24_pct": round(le24 * 100 / len(first_values), 2) if first_values else None,
        }

    def exit_hour(key: str) -> dict[str, Any]:
        counts = Counter(_hour_band(r[key].hour) for r in active if r[key] is not None)
        n = sum(counts.values())
        return {label: {"N": counts[label], "pct": round(counts[label] * 100 / n, 2) if n else None} for label, _, _ in HOUR_BANDS}

    route_metrics: dict[str, dict[str, Any]] = {}
    for route in ("FACTURA_DIRECTA", "ENTREGA", "FACTURA_RESERVA_ENTREGA"):
        selected = [r for r in active if r["RouteType"] == route]
        first_values = [_duration(r["OrderDateTime"], r["FirstWarehouseExitDateTime"])[0] for r in selected]
        complete_values = [_duration(r["OrderDateTime"], r["CompleteWarehouseExitDateTime"])[0] for r in selected]
        first_values = [v for v in first_values if v is not None and v >= 0]
        complete_values = [v for v in complete_values if v is not None and v >= 0]
        route_metrics[route] = {
            "N": len(selected),
            "first": {"median": round(_quantile(first_values, .5), 3) if first_values else None, "p90": round(_quantile(first_values, .9), 3) if first_values else None, "N": len(first_values)},
            "complete": {"median": round(_quantile(complete_values, .5), 3) if complete_values else None, "p90": round(_quantile(complete_values, .9), 3) if complete_values else None, "N": len(complete_values)},
        }

    partials = [r for r in active if r["PartialExitFlag"]]
    no_exit = [r for r in active if r["FirstWarehouseExitDateTime"] is None]
    complete = [r for r in active if r["CompleteExitFlag"]]
    first = [r for r in active if r["FirstWarehouseExitDateTime"] is not None]
    snapshot = datetime(2026, 9, 14, 11, 21, 15)
    backlog_age_days = [
        (snapshot - r["OrderDateTime"]).total_seconds() / 86400
        for r in no_exit if r["OrderDateTime"] is not None
    ]
    partial_by_status = {}
    for status in ("C", "O"):
        selected = [r for r in partials if r["OrderStatus"] == status]
        partial_by_status[status] = {
            "N": len(selected),
            "ordered": float(sum((r["LOrderedInvQty"] for r in selected), Decimal("0"))),
            "exited": float(sum((r["ExitedInvQty"] for r in selected), Decimal("0"))),
            "remaining": float(sum((r["RemainingInvQty"] for r in selected), Decimal("0"))),
        }
    partial_qty = {
        "N": len(partials),
        "ordered": float(sum((r["LOrderedInvQty"] for r in partials), Decimal("0"))),
        "exited": float(sum((r["ExitedInvQty"] for r in partials), Decimal("0"))),
        "remaining": float(sum((r["RemainingInvQty"] for r in partials), Decimal("0"))),
        "by_order_status": partial_by_status,
    }

    coverage = {
        "active": len(active),
        "first_exit": len(first),
        "complete_exit": len(complete),
        "partial": len(partials),
        "no_exit": len(no_exit),
        "cancelled_current": sum(1 for r in records if r["CurrentCancelledFlag"]),
        "reconciliation": len(complete) + len(partials) + len(no_exit),
    }
    return {
        "records": records,
        "coverage": coverage,
        "stats_minutes": stats,
        "metric_quality": dict(metric_quality),
        "bands": bands_out,
        "calendar": calendar_out,
        "entry_hour": entry_hour,
        "first_exit_hour": exit_hour("FirstWarehouseExitDateTime"),
        "complete_exit_hour": exit_hour("CompleteWarehouseExitDateTime"),
        "routes": route_metrics,
        "partials": partial_qty,
        "backlog_age_at_snapshot_days": _stats(backlog_age_days),
        "backlog_route_observed": dict(Counter(r["RouteType"] for r in no_exit)),
    }, records


def _manual_cases(records: list[dict[str, Any]], metric_key: str) -> dict[str, list[dict[str, Any]]]:
    eligible = [r for r in records if not r["CurrentCancelledFlag"] and r[metric_key] is not None]
    eligible.sort(key=lambda r: r[metric_key])
    if not eligible:
        return {"fast": [], "median": [], "p90": [], "extreme": []}
    def pick(indices: list[int]) -> list[dict[str, Any]]:
        output = []
        for index in indices:
            r = eligible[max(0, min(index, len(eligible) - 1))]
            output.append({
                "OrderKey": r["OrderKey"], "OrderNumber": r["OrderNumber"],
                "OrderDateTime": r["OrderDateTime"], "FirstWarehouseExitDateTime": r["FirstWarehouseExitDateTime"],
                "CompleteWarehouseExitDateTime": r["CompleteWarehouseExitDateTime"],
                "minutes": r[metric_key], "RouteType": r["RouteType"],
            })
        return output
    n = len(eligible)
    return {"fast": pick(list(range(min(5, n)))), "median": pick([n // 2 - 2, n // 2 - 1, n // 2, n // 2 + 1, n // 2 + 2]), "p90": pick([int(n * .9) - 2, int(n * .9) - 1, int(n * .9), int(n * .9) + 1, int(n * .9) + 2]), "extreme": pick(list(range(max(0, n - 5), n)))}


def run() -> dict[str, Any]:
    started = time.monotonic()
    connection, _ = connect()
    cursor = ReadOnlyConnection(connection).cursor()
    try:
        preflight = _rows(cursor, 'SELECT CURRENT_TIMESTAMP AS "server_timestamp", CURRENT_USER AS "current_user", CURRENT_SCHEMA AS "current_schema" FROM DUMMY')[0]
        order_rows = _rows(cursor, DATA_SQL)
        invoice_rows = _rows(cursor, INVOICE_SQL)
    finally:
        connection.rollback()
        connection.close()
    built = _record_from_rows(order_rows, invoice_rows)
    # _finalize_records returns (analysis, records); keep the explicit shape for audit.
    analysis, records = _finalize_records(built)
    for record in records:
        for name, start_key, end_key in (
            ("OrderToInvoiceMinutes", "OrderDateTime", "InvoiceDateTime"),
            ("OrderToFirstWarehouseExitMinutes", "OrderDateTime", "FirstWarehouseExitDateTime"),
            ("OrderToCompleteWarehouseExitMinutes", "OrderDateTime", "CompleteWarehouseExitDateTime"),
            ("InvoiceToFirstWarehouseExitMinutes", "InvoiceDateTime", "FirstWarehouseExitDateTime"),
            ("InvoiceToCompleteWarehouseExitMinutes", "InvoiceDateTime", "CompleteWarehouseExitDateTime"),
        ):
            value, _ = _duration(record[start_key], record[end_key])
            record[name] = round(value, 6) if value is not None else None
    current_cancelled = analysis["coverage"]["cancelled_current"]
    expected = {
        "active": CANONICAL_ACTIVE, "first_exit": CANONICAL_FIRST_EXIT,
        "complete_exit": CANONICAL_COMPLETE_EXIT, "partial": CANONICAL_PARTIAL,
        "no_exit": CANONICAL_NO_EXIT, "cancelled": CANONICAL_CANCELLED,
    }
    observed = analysis["coverage"]
    reconciliation_ok = (
        observed["active"] == CANONICAL_ACTIVE and observed["first_exit"] == CANONICAL_FIRST_EXIT
        and observed["complete_exit"] == CANONICAL_COMPLETE_EXIT and observed["partial"] == CANONICAL_PARTIAL
        and observed["no_exit"] == CANONICAL_NO_EXIT and observed["reconciliation"] == CANONICAL_ACTIVE
    )
    data = {
        "gate": "TELCHI_ORDER_TO_WAREHOUSE_EXIT_BASELINE_V1",
        "verdict": "PASS" if reconciliation_ok else "DEGRADED",
        "mode": "SAP_HANA_READ_ONLY_LOW_IMPACT_SINGLE_THREAD",
        "snapshot": "2026-09-14 11:21:15",
        "cohort_contract": {
            "start_date": START_DATE, "end_date_exclusive": END_DATE_EXCLUSIVE,
            "max_order_docentry": MAX_ORDER_DOCENTRY, "active": CANONICAL_ACTIVE,
            "first_exit": CANONICAL_FIRST_EXIT, "complete_exit": CANONICAL_COMPLETE_EXIT,
            "partial": CANONICAL_PARTIAL, "no_exit": CANONICAL_NO_EXIT, "cancelled": CANONICAL_CANCELLED,
        },
        "preflight": preflight,
        "observed_coverage": observed,
        "coverage_contract_check": {"expected": expected, "observed": observed, "reconciliation_ok": reconciliation_ok},
        "stats_minutes": analysis["stats_minutes"],
        "metric_quality": analysis["metric_quality"],
        "bands": analysis["bands"], "calendar": analysis["calendar"],
        "entry_hour": analysis["entry_hour"],
        "first_exit_hour": analysis["first_exit_hour"],
        "complete_exit_hour": analysis["complete_exit_hour"],
        "routes": analysis["routes"], "partials": analysis["partials"],
        "backlog_age_at_snapshot_days": analysis["backlog_age_at_snapshot_days"],
        "backlog_route_observed": analysis["backlog_route_observed"],
        "manual_cases": _manual_cases(records, "OrderToFirstWarehouseExitMinutes"),
        "records": records,
        "resource_policy": {
            "sap_write_count": SAP_WRITE_COUNT, "query_count": 2,
            "process_policy": "one process, one numeric thread; no pandas/multiprocessing",
            "query_scope": "frozen order date/docentry cohort; exact OINM key; explicit columns",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS", "unset"),
        },
        "data_quality": {
            "timestamp_precision": "seconds",
            "negative_duration_policy": "retained as INVALID_TIMESTAMP; never corrected silently",
            "physical_boundary": "registered inventory exit, not truck departure or customer delivery",
        },
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    data["evidence_path"] = str(EVIDENCE_PATH)
    return data


def main() -> int:
    result = run()
    compact = {key: result[key] for key in ("gate", "verdict", "observed_coverage", "coverage_contract_check", "stats_minutes", "routes", "resource_policy", "evidence_path")}
    print(json.dumps(compact, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
