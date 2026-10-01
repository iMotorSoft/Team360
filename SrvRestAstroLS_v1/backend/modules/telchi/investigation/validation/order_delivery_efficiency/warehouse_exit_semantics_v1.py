"""Gate 3: semantics of the registered warehouse exit for frozen Telchi orders.

The Gate 1 order cohort and Gate 2 document snapshot are immutable inputs. All
SAP/HANA statements are SELECT-only, sequential, bounded to that cohort, and
return aggregates or at most 20 traceable cases.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection

EVIDENCE_DIR = EVIDENCE_ROOT / "order_delivery_efficiency" / "evidence"
START_DATE = "2026-08-15"
END_DATE_EXCLUSIVE = "2026-09-15"
MAX_ORDER_DOCENTRY = 215152
GATE2_SNAPSHOT_DATE = "2026-09-14"
GATE2_SNAPSHOT_TIME = 112115
SAMPLE_LIMIT = 15
SAP_WRITE_COUNT = 0
GATE2_ACTIVE_ORDERS = 2842
GATE2_FULL_MOVEMENT = 2448
GATE2_PARTIAL_MOVEMENT = 70
GATE2_OVER_EXIT = 6
GATE2_WITHOUT_POSTERIOR = 207


def _rows(cursor: Any, sql: str) -> list[dict[str, Any]]:
    cursor.execute(sql)
    columns = [column[0].lower() for column in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _json_default(value: Any) -> str | float:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def classify_quantity(ordered: Any, exited: Any) -> str:
    """Compare SAP inventory quantities exactly; no hidden tolerance."""
    ordered_qty = Decimal(str(ordered or 0))
    exited_qty = Decimal(str(exited or 0))
    if exited_qty == 0:
        return "NO_MOVEMENT"
    if exited_qty < ordered_qty:
        return "PARTIAL"
    if exited_qty > ordered_qty:
        return "OVER"
    return "EXACT"


def evidence_class(has_out_movement: bool, has_source_create_timestamp: bool) -> str:
    """Classify evidence for a registered inventory exit, never truck departure."""
    if has_out_movement and has_source_create_timestamp:
        return "WAREHOUSE_EXIT_CONFIRMED"
    if has_out_movement:
        return "WAREHOUSE_EXIT_OPERATIONAL"
    return "NOT_AVAILABLE"


def _frozen(alias: str) -> str:
    return (
        f'({alias}."CreateDate"<\'{GATE2_SNAPSHOT_DATE}\' OR '
        f'({alias}."CreateDate"=\'{GATE2_SNAPSHOT_DATE}\' '
        f'AND {alias}."CreateTS"<={GATE2_SNAPSHOT_TIME}))'
    )


ORDER_COHORT_SQL = f'''
SELECT H."DocEntry" AS "order_entry", H."DocNum" AS "order_number",
    H."DocStatus" AS "order_status", SUM(R."InvQty") AS "ordered_inv_qty"
FROM "TELCHI"."ORDR" H
INNER JOIN "TELCHI"."RDR1" R
    ON R."DocEntry"=H."DocEntry" AND R."ItemCode" LIKE 'L%'
WHERE H."DocDate">='{START_DATE}' AND H."DocDate"<'{END_DATE_EXCLUSIVE}'
  AND H."DocEntry"<={MAX_ORDER_DOCENTRY} AND H."CANCELED"='N'
GROUP BY H."DocEntry", H."DocNum", H."DocStatus"
'''


def _source_lines_sql() -> str:
    """Return the three proven stock-generating paths at source-line grain."""
    return f'''
WITH O AS ({ORDER_COHORT_SQL})
SELECT I."BaseEntry" AS "order_entry", 'DIRECT_INVOICE' AS "route",
    13 AS "source_type", H."DocEntry" AS "source_entry", H."DocNum" AS "source_number",
    I."LineNum" AS "source_line", I."ItemCode" AS "item_code",
    I."WhsCode" AS "warehouse", I."InvQty" AS "document_inv_qty",
    H."DocDate" AS "source_doc_date", H."DocTime" AS "source_doc_time",
    H."CreateDate" AS "source_create_date", H."CreateTS" AS "source_create_ts"
FROM O
INNER JOIN "TELCHI"."INV1" I
    ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."OINV" H
    ON H."DocEntry"=I."DocEntry" AND H."CANCELED"='N' AND H."isIns"='N'
WHERE {_frozen('H')}
UNION ALL
SELECT D."BaseEntry", 'ORDER_DELIVERY', 15, H."DocEntry", H."DocNum",
    D."LineNum", D."ItemCode", D."WhsCode", D."InvQty",
    H."DocDate", H."DocTime", H."CreateDate", H."CreateTS"
FROM O
INNER JOIN "TELCHI"."DLN1" D
    ON D."BaseType"='17' AND D."BaseEntry"=O."order_entry" AND D."ItemCode" LIKE 'L%'
INNER JOIN "TELCHI"."ODLN" H
    ON H."DocEntry"=D."DocEntry" AND H."CANCELED"='N'
WHERE {_frozen('H')}
UNION ALL
SELECT I."BaseEntry", 'RESERVE_INVOICE_DELIVERY', 15, D."DocEntry", D."DocNum",
    L."LineNum", L."ItemCode", L."WhsCode", L."InvQty",
    D."DocDate", D."DocTime", D."CreateDate", D."CreateTS"
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


def _coverage_sql() -> str:
    return f'''
SELECT Q."exit_class", Q."order_status", COUNT(*) AS "orders",
    SUM(Q."ordered_inv_qty") AS "ordered_inv_qty",
    SUM(Q."out_qty") AS "out_qty", SUM(Q."remaining_qty") AS "remaining_qty"
FROM (
  WITH C AS ({ORDER_COHORT_SQL}), S AS ({_source_lines_sql()}),
  A AS (
    SELECT S."order_entry", SUM(S."document_inv_qty") AS "document_inv_qty",
      SUM(COALESCE(M."OutQty",0)) AS "out_qty",
      SUM(CASE WHEN M."OutQty">0 AND M."Warehouse"<>S."warehouse" THEN 1 ELSE 0 END)
        AS "warehouse_mismatch_lines",
      SUM(CASE WHEN M."OutQty">0 AND M."OutQty"<>S."document_inv_qty" THEN 1 ELSE 0 END)
        AS "quantity_mismatch_lines"
    FROM S
    LEFT JOIN "TELCHI"."OINM" M
      ON M."TransType"=S."source_type" AND M."CreatedBy"=S."source_entry"
     AND M."DocLineNum"=S."source_line" AND M."ItemCode"=S."item_code"
     AND M."OutQty">0
    GROUP BY S."order_entry"
  )
  SELECT C."order_entry", C."order_status", C."ordered_inv_qty",
    COALESCE(A."out_qty",0) AS "out_qty",
    C."ordered_inv_qty"-COALESCE(A."out_qty",0) AS "remaining_qty",
    CASE WHEN COALESCE(A."out_qty",0)=0 THEN 'NO_MOVEMENT'
      WHEN A."out_qty"<C."ordered_inv_qty" THEN 'PARTIAL'
      WHEN A."out_qty">C."ordered_inv_qty" THEN 'OVER' ELSE 'EXACT' END AS "exit_class"
  FROM C LEFT JOIN A ON A."order_entry"=C."order_entry"
) Q
GROUP BY Q."exit_class", Q."order_status"
ORDER BY "orders" DESC
'''


def _route_summary_sql() -> str:
    return f'''
SELECT S."route", COUNT(DISTINCT S."order_entry") AS "orders",
  COUNT(DISTINCT S."source_entry") AS "source_documents", COUNT(*) AS "document_lines",
  SUM(CASE WHEN M."OutQty">0 THEN 1 ELSE 0 END) AS "out_movement_lines",
  SUM(CASE WHEN M."OutQty">0 AND M."Warehouse"=S."warehouse" THEN 0 ELSE 1 END)
    AS "missing_or_warehouse_mismatch_lines",
  SUM(CASE WHEN M."OutQty">0 AND M."OutQty"=S."document_inv_qty" THEN 0 ELSE 1 END)
    AS "missing_or_quantity_mismatch_lines",
  SUM(CASE WHEN M."OutQty">0 AND M."InQty"=0 THEN 0 ELSE 1 END)
    AS "invalid_out_lines"
FROM ({_source_lines_sql()}) S
LEFT JOIN "TELCHI"."OINM" M
  ON M."TransType"=S."source_type" AND M."CreatedBy"=S."source_entry"
 AND M."DocLineNum"=S."source_line" AND M."ItemCode"=S."item_code" AND M."OutQty">0
GROUP BY S."route" ORDER BY "orders" DESC
'''


def _timestamp_summary_sql() -> str:
    return f'''
SELECT S."route", COUNT(DISTINCT S."source_entry") AS "documents", COUNT(*) AS "movement_lines",
  SUM(CASE WHEN M."BASE_REF"=TO_NVARCHAR(S."source_number") THEN 0 ELSE 1 END)
    AS "base_ref_mismatch_lines",
  SUM(CASE WHEN M."DocDate"=S."source_doc_date" THEN 0 ELSE 1 END)
    AS "movement_docdate_mismatch_lines",
  SUM(CASE WHEN M."DocTime"=S."source_doc_time" THEN 0 ELSE 1 END)
    AS "movement_doctime_mismatch_lines",
  COUNT(DISTINCT CASE WHEN S."source_doc_date"<>S."source_create_date"
    THEN S."source_entry" END) AS "posting_vs_create_date_mismatch_documents",
  COUNT(DISTINCT CASE WHEN M."DocTime"<>FLOOR(S."source_create_ts"/100)
    THEN S."source_entry" END) AS "movement_time_vs_create_minute_mismatch_documents",
  SUM(CASE WHEN M."AppObjAbs"=-1 THEN 1 ELSE 0 END) AS "app_obj_abs_minus_one_lines",
  MIN(DAYS_BETWEEN(S."source_doc_date",S."source_create_date")) AS "min_posting_create_days",
  MAX(DAYS_BETWEEN(S."source_doc_date",S."source_create_date")) AS "max_posting_create_days"
FROM ({_source_lines_sql()}) S
INNER JOIN "TELCHI"."OINM" M
  ON M."TransType"=S."source_type" AND M."CreatedBy"=S."source_entry"
 AND M."DocLineNum"=S."source_line" AND M."ItemCode"=S."item_code" AND M."OutQty">0
GROUP BY S."route" ORDER BY "documents" DESC
'''


def _sample_sql(route: str, limit: int = SAMPLE_LIMIT) -> str:
    return f'''
SELECT S."order_entry", S."route", S."source_type", S."source_entry", S."source_number",
  COUNT(*) AS "l_lines", COUNT(DISTINCT S."item_code") AS "l_items",
  SUM(S."document_inv_qty") AS "document_inv_qty", SUM(M."OutQty") AS "out_qty",
  SUM(CASE WHEN M."Warehouse"=S."warehouse" THEN 0 ELSE 1 END) AS "warehouse_mismatch_lines",
  MIN(M."TransNum") AS "first_transnum", MIN(M."DocDate") AS "movement_doc_date",
  MIN(M."DocTime") AS "movement_doc_time", MIN(S."source_create_date") AS "source_create_date",
  MIN(S."source_create_ts") AS "source_create_ts"
FROM ({_source_lines_sql()}) S
INNER JOIN "TELCHI"."OINM" M
  ON M."TransType"=S."source_type" AND M."CreatedBy"=S."source_entry"
 AND M."DocLineNum"=S."source_line" AND M."ItemCode"=S."item_code" AND M."OutQty">0
WHERE S."route"='{route}'
GROUP BY S."order_entry", S."route", S."source_type", S."source_entry", S."source_number"
ORDER BY S."order_entry" LIMIT {limit}
'''


def _reserve_invoice_gap_sql() -> str:
    return f'''
SELECT Q."target_type", Q."exit_class", COUNT(*) AS "orders",
  SUM(Q."warehouse_mismatch_lines") AS "warehouse_mismatch_lines"
FROM (
 WITH O AS ({ORDER_COHORT_SQL}), RI AS (
  SELECT I."BaseEntry" AS "order_entry", V."DocEntry" AS "invoice_entry",
    MAX(I."TargetType") AS "target_type", SUM(I."InvQty") AS "invoice_inv_qty"
  FROM O INNER JOIN "TELCHI"."INV1" I
    ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
  INNER JOIN "TELCHI"."OINV" V
    ON V."DocEntry"=I."DocEntry" AND V."CANCELED"='N' AND V."isIns"='Y'
  WHERE {_frozen('V')} GROUP BY I."BaseEntry", V."DocEntry"
 ), X AS (
  SELECT RI."order_entry", SUM(M."OutQty") AS "out_qty",
    SUM(CASE WHEN M."Warehouse"=L."WhsCode" THEN 0 ELSE 1 END) AS "warehouse_mismatch_lines"
  FROM RI INNER JOIN "TELCHI"."DLN1" L
    ON L."BaseType"='13' AND L."BaseEntry"=RI."invoice_entry" AND L."ItemCode" LIKE 'L%'
  INNER JOIN "TELCHI"."ODLN" D ON D."DocEntry"=L."DocEntry" AND D."CANCELED"='N'
  INNER JOIN "TELCHI"."OINM" M
    ON M."TransType"=15 AND M."CreatedBy"=D."DocEntry"
   AND M."DocLineNum"=L."LineNum" AND M."ItemCode"=L."ItemCode" AND M."OutQty">0
  WHERE {_frozen('D')} GROUP BY RI."order_entry"
 )
 SELECT RI."order_entry", RI."target_type", COALESCE(X."warehouse_mismatch_lines",0)
   AS "warehouse_mismatch_lines",
  CASE WHEN COALESCE(X."out_qty",0)=0 THEN 'NO_MOVEMENT'
    WHEN X."out_qty"<RI."invoice_inv_qty" THEN 'PARTIAL'
    WHEN X."out_qty">RI."invoice_inv_qty" THEN 'OVER' ELSE 'EXACT' END AS "exit_class"
 FROM RI LEFT JOIN X ON X."order_entry"=RI."order_entry"
) Q GROUP BY Q."target_type", Q."exit_class" ORDER BY "orders" DESC
'''


def _partial_summary_sql() -> str:
    return f'''
SELECT Q."order_status", COUNT(*) AS "orders", SUM(Q."ordered_inv_qty") AS "ordered_inv_qty",
  SUM(Q."out_qty") AS "out_qty", SUM(Q."ordered_inv_qty"-Q."out_qty") AS "remaining_qty"
FROM (
 WITH C AS ({ORDER_COHORT_SQL}), S AS ({_source_lines_sql()}), A AS (
  SELECT S."order_entry", SUM(M."OutQty") AS "out_qty"
  FROM S INNER JOIN "TELCHI"."OINM" M
    ON M."TransType"=S."source_type" AND M."CreatedBy"=S."source_entry"
   AND M."DocLineNum"=S."source_line" AND M."ItemCode"=S."item_code" AND M."OutQty">0
  GROUP BY S."order_entry")
 SELECT C."order_entry", C."order_number", C."order_status", C."ordered_inv_qty",
   A."out_qty" FROM C INNER JOIN A ON A."order_entry"=C."order_entry"
 WHERE A."out_qty">0 AND A."out_qty"<C."ordered_inv_qty"
) Q GROUP BY Q."order_status" ORDER BY "orders" DESC
'''


def _over_exit_sql() -> str:
    # Reproduces Gate 2's BASE_REF-only excess and proves the foreign-document fanout.
    return f'''
SELECT Q.* FROM (
 WITH O AS ({ORDER_COHORT_SQL}), X AS (
  SELECT I."BaseEntry" AS "order_entry", SUM(M."OutQty") AS "gate2_out_qty",
    SUM(CASE WHEN M."CreatedBy"=H."DocEntry" THEN M."OutQty" ELSE 0 END) AS "exact_out_qty",
    SUM(CASE WHEN M."CreatedBy"<>H."DocEntry" THEN M."OutQty" ELSE 0 END) AS "foreign_out_qty"
  FROM O INNER JOIN "TELCHI"."INV1" I
    ON I."BaseType"='17' AND I."BaseEntry"=O."order_entry" AND I."ItemCode" LIKE 'L%'
  INNER JOIN "TELCHI"."OINV" H ON H."DocEntry"=I."DocEntry" AND H."CANCELED"='N'
  INNER JOIN "TELCHI"."OINM" M
    ON M."TransType"=13 AND M."BASE_REF"=TO_NVARCHAR(H."DocNum")
   AND M."DocLineNum"=I."LineNum" AND M."ItemCode"=I."ItemCode"
  WHERE {_frozen('H')} GROUP BY I."BaseEntry"
  UNION ALL
  SELECT D."BaseEntry", SUM(M."OutQty"),
    SUM(CASE WHEN M."CreatedBy"=H."DocEntry" THEN M."OutQty" ELSE 0 END),
    SUM(CASE WHEN M."CreatedBy"<>H."DocEntry" THEN M."OutQty" ELSE 0 END)
  FROM O INNER JOIN "TELCHI"."DLN1" D
    ON D."BaseType"='17' AND D."BaseEntry"=O."order_entry" AND D."ItemCode" LIKE 'L%'
  INNER JOIN "TELCHI"."ODLN" H ON H."DocEntry"=D."DocEntry" AND H."CANCELED"='N'
  INNER JOIN "TELCHI"."OINM" M
    ON M."TransType"=15 AND M."BASE_REF"=TO_NVARCHAR(H."DocNum")
   AND M."DocLineNum"=D."LineNum" AND M."ItemCode"=D."ItemCode"
  WHERE {_frozen('H')} GROUP BY D."BaseEntry"
 ), A AS (
  SELECT "order_entry", SUM("gate2_out_qty") AS "gate2_out_qty",
    SUM("exact_out_qty") AS "exact_out_qty", SUM("foreign_out_qty") AS "foreign_out_qty"
  FROM X GROUP BY "order_entry")
 SELECT O."order_entry", O."ordered_inv_qty", A."gate2_out_qty",
   A."exact_out_qty", A."foreign_out_qty"
 FROM O INNER JOIN A ON A."order_entry"=O."order_entry"
 WHERE A."gate2_out_qty">O."ordered_inv_qty"
) Q ORDER BY Q."order_entry"
'''


def _reversal_sql() -> str:
    return f'''
SELECT S."order_entry", S."source_entry", S."source_type",
  M."TransType" AS "reversal_type", M."CreatedBy" AS "reversal_document_entry",
  M."AppObjAbs" AS "reversed_source_entry", COUNT(*) AS "lines",
  SUM(M."InQty") AS "reversed_in_qty", MIN(M."DocDate") AS "reversal_doc_date",
  MIN(M."DocTime") AS "reversal_doc_time"
FROM ({_source_lines_sql()}) S
INNER JOIN "TELCHI"."OINM" M
  ON M."AppObjAbs"=S."source_entry" AND M."ItemCode"=S."item_code"
 AND M."Warehouse"=S."warehouse" AND M."InQty">0
GROUP BY S."order_entry", S."source_entry", S."source_type", M."TransType",
  M."CreatedBy", M."AppObjAbs"
ORDER BY S."order_entry"
'''


def run() -> dict[str, Any]:
    connection, _ = connect()
    cursor = ReadOnlyConnection(connection).cursor()
    try:
        evidence: dict[str, Any] = {
            "gate": "TELCHI_WAREHOUSE_EXIT_SEMANTICS_V1",
            "mode": "SAP_HANA_READ_ONLY_LOW_IMPACT_SINGLE_THREAD",
            "cohort": {
                "start_date": START_DATE,
                "end_date_exclusive": END_DATE_EXCLUSIVE,
                "max_order_docentry": MAX_ORDER_DOCENTRY,
                "gate2_snapshot_date": GATE2_SNAPSHOT_DATE,
                "gate2_snapshot_time": GATE2_SNAPSHOT_TIME,
            },
            "sap_write_count": SAP_WRITE_COUNT,
        }
        evidence["preflight"] = _rows(
            cursor,
            'SELECT CURRENT_TIMESTAMP AS "server_timestamp", CURRENT_USER AS "current_user", '
            'CURRENT_SCHEMA AS "current_schema" FROM DUMMY',
        )[0]
        evidence["route_summary"] = _rows(cursor, _route_summary_sql())
        evidence["coverage"] = _rows(cursor, _coverage_sql())
        evidence["timestamp_semantics"] = _rows(cursor, _timestamp_summary_sql())
        evidence["samples"] = {
            "direct_invoice": _rows(cursor, _sample_sql("DIRECT_INVOICE")),
            "order_delivery": _rows(cursor, _sample_sql("ORDER_DELIVERY")),
            "reserve_invoice_delivery": _rows(cursor, _sample_sql("RESERVE_INVOICE_DELIVERY")),
        }
        evidence["reserve_invoice_gap"] = _rows(cursor, _reserve_invoice_gap_sql())
        evidence["partial_summary"] = _rows(cursor, _partial_summary_sql())
        evidence["over_exit_all_six"] = _rows(cursor, _over_exit_sql())
        evidence["reversals"] = _rows(cursor, _reversal_sql())

        reserve_resolved = sum(
            int(row["orders"])
            for row in evidence["reserve_invoice_gap"]
            if row["exit_class"] == "EXACT"
        )
        corrected_complete = GATE2_FULL_MOVEMENT + GATE2_OVER_EXIT + reserve_resolved
        first_exit = corrected_complete + GATE2_PARTIAL_MOVEMENT
        evidence["gate2_reconciled_coverage"] = {
            "active_orders": GATE2_ACTIVE_ORDERS,
            "first_exit_confirmed": first_exit,
            "complete_exit_confirmed": corrected_complete,
            "partial_exit": GATE2_PARTIAL_MOVEMENT,
            "not_available": GATE2_ACTIVE_ORDERS - first_exit,
            "without_posterior_document": GATE2_WITHOUT_POSTERIOR,
            "reserve_invoice_without_exit_at_snapshot": (
                GATE2_ACTIVE_ORDERS - first_exit - GATE2_WITHOUT_POSTERIOR
            ),
            "first_exit_coverage_pct": round(first_exit * 100 / GATE2_ACTIVE_ORDERS, 2),
            "complete_exit_coverage_pct": round(
                corrected_complete * 100 / GATE2_ACTIVE_ORDERS, 2
            ),
            "reconciliation_formula": "2448 Gate2 full + 6 corrected fanout + 107 reserve-delivery exits",
        }
        evidence["live_state_warning"] = {
            "purpose": "detect mutable SAP header status; not a Gate 1/2 recount",
            "current_rows_in_coverage_query": sum(
                int(row["orders"]) for row in evidence["coverage"]
            ),
            "frozen_gate2_active_orders": GATE2_ACTIVE_ORDERS,
            "canonical_coverage_source": "gate2_reconciled_coverage",
        }
        evidence["semantic_decision"] = {
            "event": "OINM OutQty > 0 linked by TransType + CreatedBy + DocLineNum + ItemCode",
            "timestamp": "source document CreateDate + CreateTS",
            "timestamp_precision": "second",
            "classification": "WAREHOUSE_EXIT_CONFIRMED for registered inventory exit",
            "physical_boundary": "does not prove physical truck departure",
            "oinm_docdate": "source posting/document date; can be backdated",
            "oinm_doctime": "movement registration minute; usually source DocTime, not second precision",
            "first_exit": "minimum source CreateDate/CreateTS over valid OutQty movements",
            "complete_exit": "first source CreateDate/CreateTS where cumulative valid OutQty reaches ordered InvQty",
            "reversal_rule": "InQty compensation is separate; never add it as another exit",
        }
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        output = EVIDENCE_DIR / "warehouse_exit_semantics_v1.json"
        output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        evidence["evidence_path"] = str(output)
        return evidence
    finally:
        connection.rollback()
        connection.close()


def main() -> int:
    evidence = run()
    print(json.dumps({
        "gate": evidence["gate"],
        "cohort": evidence["cohort"],
        "route_summary": evidence["route_summary"],
        "gate2_reconciled_coverage": evidence["gate2_reconciled_coverage"],
        "live_state_warning": evidence["live_state_warning"],
        "timestamp_semantics": evidence["timestamp_semantics"],
        "reserve_invoice_gap": evidence["reserve_invoice_gap"],
        "partial_summary": evidence["partial_summary"],
        "over_exit_all_six": evidence["over_exit_all_six"],
        "reversals": evidence["reversals"],
        "sap_write_count": evidence["sap_write_count"],
        "evidence_path": evidence["evidence_path"],
    }, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
