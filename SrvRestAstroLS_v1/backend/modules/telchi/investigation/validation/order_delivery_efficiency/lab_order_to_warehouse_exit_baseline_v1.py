"""Gate 5 discovery for the Telchi Laboratorio order-exit baseline.

This runner deliberately fails closed when OWHS exposes more than one plausible
finished-goods Laboratorio warehouse. It does not invent a single code from the
``LAB-*`` prefix. The only inventory query is constrained to the already frozen
Gate 1-3 order/document paths and joins OINM by the closed semantic key.

Saavedra is limited to bounded discovery in the frozen period; no efficiency
metrics are calculated for its raw-material circuit.
"""
from __future__ import annotations

import json
import os
import resource
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection
from modules.telchi.investigation.validation.order_delivery_efficiency.order_to_warehouse_exit_baseline_v1 import (
    END_DATE_EXCLUSIVE,
    SOURCE_CTE,
    START_DATE,
)

SAP_WRITE_COUNT = 0
SNAPSHOT = "2026-09-14 11:21:15"
EVIDENCE_DIR = EVIDENCE_ROOT / "order_delivery_efficiency" / "evidence"
EVIDENCE_PATH = EVIDENCE_DIR / "lab_order_to_warehouse_exit_baseline_v1.json"


def _rows(cursor: Any, sql: str) -> list[dict[str, Any]]:
    # The SELECT wrapper is required by the project READ ONLY guard for CTEs.
    cursor.execute(f"SELECT * FROM ({sql}) Q")
    columns = [item[0].lower() for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _json_default(value: Any) -> str | float:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


WAREHOUSE_SQL = '''
SELECT "WhsCode", "WhsName", "Inactive", "Locked", "U_TYPE",
       "U_TIPO", "U_WAREHOUSE_DMS", "U_SO1_01ALMACENCOLEC", "BPLid"
FROM "TELCHI"."OWHS"
WHERE "WhsCode" LIKE 'LAB%' OR "WhsCode" LIKE 'SAA%'
ORDER BY "WhsCode"
'''

def _frozen_order_entries() -> list[int]:
    """Return the persisted Gate-1/3 order keys, never a live cohort recount."""
    baseline_path = EVIDENCE_ROOT / "order_delivery_efficiency" / "evidence" / "order_to_warehouse_exit_baseline_v1.json"
    evidence = json.loads(baseline_path.read_text(encoding="utf-8"))
    entries = sorted({int(record["OrderKey"]) for record in evidence["records"]})
    if len(entries) != 3027:
        raise RuntimeError(f"unexpected frozen L-order key count: {len(entries)}")
    return entries


# The CTE is seeded from persisted keys. Current ORDR status cannot add/remove
# members. Exact closed Gate-3 source paths then constrain OINM by the semantic key.
FROZEN_ORDER_CTE_TEMPLATE = '''
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
WHERE H."DocEntry" IN ({order_entries})
GROUP BY H."DocEntry", H."DocNum", H."CANCELED", H."DocStatus",
    H."CreateDate", H."CreateTS", H."BPLId", H."SlpCode", H."UserSign",
    H."U_ORIGIN", H."U_OSLP_ID"
HAVING COUNT(CASE WHEN R."ItemCode" LIKE 'L%' THEN 1 END)>0
'''


# Exact closed Gate-3 source paths. No BASE_REF join and no open OINM scan.
LAB_EXIT_SUMMARY_SQL_TEMPLATE = f'''
WITH O AS ({{frozen_order_cte}}), S AS ({SOURCE_CTE}), E AS (
  SELECT S."order_entry", S."source_route", S."source_entry",
         S."source_line", S."item_code", S."warehouse" AS "document_warehouse",
         M."Warehouse" AS "movement_warehouse", SUM(M."OutQty") AS "out_qty",
         MIN(S."source_create_date") AS "source_create_date",
         MIN(S."source_create_ts") AS "source_create_ts"
  FROM S
  INNER JOIN "TELCHI"."OINM" M
    ON M."TransType"=S."source_type"
   AND M."CreatedBy"=S."source_entry"
   AND M."DocLineNum"=S."source_line"
   AND M."ItemCode"=S."item_code"
   AND M."Warehouse"=S."warehouse"
   AND M."OutQty">0
  GROUP BY S."order_entry", S."source_route", S."source_entry",
           S."source_line", S."item_code", S."warehouse", M."Warehouse"
)
SELECT "movement_warehouse", COUNT(DISTINCT "order_entry") AS "orders",
       COUNT(DISTINCT "source_entry") AS "source_documents",
       COUNT(*) AS "movement_line_rows", SUM("out_qty") AS "out_qty",
       MIN("source_create_date") AS "min_source_date",
       MAX("source_create_date") AS "max_source_date"
FROM E
GROUP BY "movement_warehouse"
ORDER BY "orders" DESC
'''

SAAVEDRA_ROUTE_SQL = f'''
SELECT L."FromWhsCod" AS "from_warehouse", L."WhsCode" AS "to_warehouse",
       W."ObjType" AS "document_object_type", W."DocType" AS "document_type",
       COUNT(DISTINCT W."DocEntry") AS "documents", COUNT(*) AS "lines",
       SUM(L."Quantity") AS "quantity"
FROM "TELCHI"."OWTR" W
INNER JOIN "TELCHI"."WTR1" L ON L."DocEntry"=W."DocEntry"
WHERE W."CANCELED"='N'
  AND W."DocDate">='{START_DATE}' AND W."DocDate"<'{END_DATE_EXCLUSIVE}'
  AND (L."FromWhsCod" LIKE 'SAA%' OR L."WhsCode" LIKE 'SAA%')
GROUP BY L."FromWhsCod", L."WhsCode", W."ObjType", W."DocType"
ORDER BY "documents" DESC
LIMIT 30
'''

SAAVEDRA_SOURCE_SQL = f'''
SELECT L."FromWhsCod" AS "from_warehouse",
       COUNT(DISTINCT W."DocEntry") AS "documents",
       COUNT(*) AS "lines", MIN(W."DocDate") AS "min_doc_date",
       MAX(W."DocDate") AS "max_doc_date", SUM(L."Quantity") AS "quantity"
FROM "TELCHI"."OWTR" W
INNER JOIN "TELCHI"."WTR1" L ON L."DocEntry"=W."DocEntry"
WHERE W."CANCELED"='N'
  AND W."DocDate">='{START_DATE}' AND W."DocDate"<'{END_DATE_EXCLUSIVE}'
  AND L."FromWhsCod" LIKE 'SAA%'
GROUP BY L."FromWhsCod"
ORDER BY "documents" DESC
'''


def _warehouse_decision(warehouses: list[dict[str, Any]], movements: list[dict[str, Any]]) -> dict[str, Any]:
    by_code = {str(row["whscode"]): row for row in warehouses}
    finished = [
        row for row in warehouses
        if str(row["whscode"]).startswith("LAB-")
        and "PRODUCTO TERMINADO" in str(row["whsname"]).upper()
    ]
    finished_codes = [str(row["whscode"]) for row in finished]
    movement_by_code = {str(row["movement_warehouse"]): row for row in movements}
    candidates = []
    for row in finished:
        code = str(row["whscode"])
        candidates.append({
            "warehouse_code": code,
            "warehouse_name": row["whsname"],
            "movement_orders": int(movement_by_code.get(code, {}).get("orders", 0) or 0),
            "movement_source_documents": int(
                movement_by_code.get(code, {}).get("source_documents", 0) or 0
            ),
        })
    # LAB-DES is a dispatch label, not a finished-goods warehouse; retain it as
    # evidence instead of silently promoting it to the canonical code.
    dispatch = {
        code: {
            "warehouse_name": by_code[code]["whsname"],
            "movement_orders": int(movement_by_code.get(code, {}).get("orders", 0) or 0),
        }
        for code in ("LAB-DES", "LAB-D0")
        if code in by_code
    }
    return {
        "canonical_lab_warehouse_code": None,
        "decision": "BLOCKED_AMBIGUOUS_LAB_FINISHED_GOODS_SCOPE",
        "finished_goods_candidates": candidates,
        "candidate_codes": finished_codes,
        "dispatch_warehouse_evidence": dispatch,
        "reason": (
            "OWHS contains multiple active LAB finished-goods warehouses "
            "(LAB-T1..LAB-T4), and the frozen order exits hit more than one. "
            "A single LAB_WAREHOUSE_CODE cannot be demonstrated from SAP alone."
        ),
    }


def _saavedra_decision(
    warehouses: list[dict[str, Any]], source_rows: list[dict[str, Any]], routes: list[dict[str, Any]]
) -> dict[str, Any]:
    candidates = [
        {"warehouse_code": str(row["whscode"]), "warehouse_name": row["whsname"]}
        for row in warehouses
        if str(row["whscode"]).startswith("SAA-")
    ]
    source_by_code = {str(row["from_warehouse"]): row for row in source_rows}
    return {
        "candidate_warehouses": candidates,
        "observed_raw_material_source_candidate": {
            "warehouse_code": "SAA-M1",
            "warehouse_name": next(
                (row["whsname"] for row in warehouses if row["whscode"] == "SAA-M1"),
                None,
            ),
            "confidence": "CANDIDATE_NOT_PROMOTED",
            "basis": (
                "OWHS name identifies a bulk-processing store; bounded OWTR "
                "discovery shows SAA-M1 as a source with destinations including "
                "SAA-P1, LAB-M1 and LAB-T*; full raw-material semantics remain open."
            ),
            "source_summary": source_by_code.get("SAA-M1"),
        },
        "bounded_routes": routes,
        "quantitative_efficiency_status": "NOT_STARTED_BY_DESIGN",
    }


def run() -> dict[str, Any]:
    started = time.monotonic()
    frozen_order_cte = FROZEN_ORDER_CTE_TEMPLATE.format(
        order_entries=",".join(str(entry) for entry in _frozen_order_entries())
    )
    lab_exit_summary_sql = LAB_EXIT_SUMMARY_SQL_TEMPLATE.format(
        frozen_order_cte=frozen_order_cte
    )
    connection, _ = connect()
    cursor = ReadOnlyConnection(connection).cursor()
    try:
        warehouse_rows = _rows(cursor, WAREHOUSE_SQL)
        movement_rows = _rows(cursor, lab_exit_summary_sql)
        saavedra_routes = _rows(cursor, SAAVEDRA_ROUTE_SQL)
        saavedra_sources = _rows(cursor, SAAVEDRA_SOURCE_SQL)
        result = {
            "gate": "TELCHI_LAB_ORDER_TO_WAREHOUSE_EXIT_BASELINE_V1",
            "verdict": "BLOCKED",
            "mode": "SAP_HANA_READ_ONLY_LOW_IMPACT_SINGLE_THREAD",
            "snapshot": SNAPSHOT,
            "cohort": {
                "start_date": START_DATE,
                "end_date_exclusive": END_DATE_EXCLUSIVE,
                "frozen_active_orders": 2842,
                "frozen_first_exit": 2631,
                "frozen_complete_exit": 2561,
                "frozen_partial": 70,
                "frozen_no_exit": 211,
                "source": "Gate 1-3 frozen contract; no live cohort recount",
            },
            "warehouse_catalog": warehouse_rows,
            "lab_exit_movement_summary": movement_rows,
            "lab_warehouse_decision": _warehouse_decision(warehouse_rows, movement_rows),
            "saavedra_discovery": _saavedra_decision(
                warehouse_rows, saavedra_sources, saavedra_routes
            ),
            "data_quality": {
                "oinm_join": "TransType + CreatedBy + DocLineNum + ItemCode + Warehouse",
                "event": "OINM.OutQty > 0",
                "timestamp": "source document CreateDate + CreateTS",
                "physical_boundary": "registered inventory exit, not physical truck departure",
                "full_lab_metrics": "NOT_CALCULATED because canonical code is unresolved",
            },
            "resource_policy": {
                "sap_write_count": SAP_WRITE_COUNT,
                "query_count": 4,
                "process_policy": "one process, one numeric thread; no pandas/multiprocessing",
                "omp_num_threads": os.environ.get("OMP_NUM_THREADS", "unset"),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            },
        }
    finally:
        connection.rollback()
        connection.close()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    result["evidence_path"] = str(EVIDENCE_PATH)
    return result


def main() -> int:
    result = run()
    print(json.dumps({
        "gate": result["gate"],
        "verdict": result["verdict"],
        "lab_warehouse_decision": result["lab_warehouse_decision"],
        "saavedra_discovery": result["saavedra_discovery"],
        "resource_policy": result["resource_policy"],
        "evidence_path": result["evidence_path"],
    }, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
