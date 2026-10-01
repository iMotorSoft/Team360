"""Gate 2: bounded order -> document -> inventory-movement chain discovery.

The fixed order cohort reproduces Gate 1 (2026-08-15..2026-09-14,
DocEntry <= 215152). SAP/HANA access is SELECT-only and sequential.
This gate proves relationships and cardinalities; it does not assign physical
warehouse-exit timestamp semantics, which belongs to Gate 3.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.credit_control.readonly import (
    ReadOnlyConnection,
)

EVIDENCE_DIR = EVIDENCE_ROOT / "order_delivery_efficiency" / "evidence"
START_DATE = "2026-08-15"
END_DATE_EXCLUSIVE = "2026-09-15"
MAX_ORDER_DOCENTRY = 215152
SAMPLE_PER_ROUTE = 4
SAP_WRITE_COUNT = 0
TOLERANCE = 0.000001

ORDER_COHORT_SQL = f'''
SELECT O."DocEntry", O."DocNum", O."DocDate", O."CreateDate", O."CreateTS",
    O."CANCELED", O."DocStatus", O."CardCode", O."SlpCode", O."UserSign",
    O."U_ORIGIN", O."U_DMS_STATE",
    COUNT(*) AS "all_line_count",
    SUM(CASE WHEN R."ItemCode" LIKE 'L%' THEN 1 ELSE 0 END) AS "l_line_count",
    COUNT(DISTINCT CASE WHEN R."ItemCode" LIKE 'L%' THEN R."ItemCode" END) AS "l_item_count",
    SUM(CASE WHEN R."ItemCode" LIKE 'L%' THEN R."Quantity" ELSE 0 END) AS "l_order_qty",
    MAX(CASE WHEN R."ItemCode" NOT LIKE 'L%' THEN 1 ELSE 0 END) AS "mixed_flag"
FROM "TELCHI"."ORDR" O
INNER JOIN "TELCHI"."RDR1" R ON R."DocEntry"=O."DocEntry"
WHERE O."DocDate">='{START_DATE}' AND O."DocDate"<'{END_DATE_EXCLUSIVE}'
  AND O."DocEntry"<={MAX_ORDER_DOCENTRY}
GROUP BY O."DocEntry", O."DocNum", O."DocDate", O."CreateDate", O."CreateTS",
    O."CANCELED", O."DocStatus", O."CardCode", O."SlpCode", O."UserSign",
    O."U_ORIGIN", O."U_DMS_STATE"
HAVING SUM(CASE WHEN R."ItemCode" LIKE 'L%' THEN 1 ELSE 0 END)>0
'''


def _rows(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, params)
    columns = [column[0].lower() for column in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _json_default(value: Any) -> str | float:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _number(value: Any) -> float:
    return float(value or 0)


def classify_route(row: dict[str, Any]) -> str:
    has_delivery = int(row["active_delivery_count"] or 0) > 0
    has_direct_invoice = int(row["active_direct_invoice_count"] or 0) > 0
    has_delivery_invoice = int(row["active_delivery_invoice_count"] or 0) > 0
    if has_delivery and has_direct_invoice and has_delivery_invoice:
        return "ORDER_TO_DELIVERY_AND_DIRECT_INVOICE"
    if has_delivery and has_delivery_invoice:
        return "ORDER_TO_DELIVERY_TO_INVOICE"
    if has_delivery and has_direct_invoice:
        return "ORDER_TO_DELIVERY_PLUS_DIRECT_INVOICE"
    if has_delivery:
        return "ORDER_TO_DELIVERY"
    if has_direct_invoice:
        return "ORDER_TO_INVOICE_DIRECT"
    return "ORDER_WITHOUT_ACTIVE_POSTERIOR_DOCUMENT"


def classify_quantity(order_qty: Any, exited_qty: Any) -> str:
    ordered = _number(order_qty)
    exited = _number(exited_qty)
    if exited <= TOLERANCE:
        return "NO_EXIT"
    if exited < ordered - TOLERANCE:
        return "PARTIAL_EXIT"
    if exited > ordered + TOLERANCE:
        return "OVER_EXIT"
    return "FULL_EXIT"


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    route_counts: Counter[str] = Counter()
    quantity_counts: Counter[str] = Counter()
    movement_counts: Counter[str] = Counter()
    route_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    totals = Counter()

    for row in rows:
        route = classify_route(row)
        route_counts[route] += 1
        if len(route_examples[route]) < SAMPLE_PER_ROUTE:
            route_examples[route].append({
                "order_entry": row["docentry"],
                "order_number": row["docnum"],
                "order_date": row["docdate"],
                "channel": row["u_origin"],
                "canceled": row["canceled"],
                "l_order_qty": row["l_order_qty"],
                "delivery_count": row["active_delivery_count"],
                "direct_invoice_count": row["active_direct_invoice_count"],
                "delivery_invoice_count": row["active_delivery_invoice_count"],
                "document_exit_qty": row["document_exit_qty"],
                "movement_out_qty": row["movement_out_qty"],
            })

        if row["canceled"] == "Y":
            totals["canceled_orders"] += 1
            continue
        totals["active_orders"] += 1
        document_class = classify_quantity(row["l_order_qty"], row["document_exit_qty"])
        movement_class = classify_quantity(row["l_order_qty"], row["movement_out_qty"])
        quantity_counts[document_class] += 1
        movement_counts[movement_class] += 1
        if int(row["active_delivery_count"] or 0) > 1:
            totals["orders_multiple_deliveries"] += 1
        if int(row["active_direct_invoice_count"] or 0) + int(
            row["active_delivery_invoice_count"] or 0
        ) > 1:
            totals["orders_multiple_invoices"] += 1
        if int(row["active_delivery_count"] or 0) == 0 and int(
            row["active_direct_invoice_count"] or 0
        ) == 0:
            totals["active_without_posterior"] += 1

    return {
        "orders": len(rows),
        "active_orders": totals["active_orders"],
        "canceled_orders": totals["canceled_orders"],
        "active_without_posterior": totals["active_without_posterior"],
        "orders_multiple_deliveries": totals["orders_multiple_deliveries"],
        "orders_multiple_invoices": totals["orders_multiple_invoices"],
        "routes": dict(route_counts),
        "document_quantity_classes_active": dict(quantity_counts),
        "movement_quantity_classes_active_provisional": dict(movement_counts),
        "route_examples": dict(route_examples),
    }


def run() -> dict[str, Any]:
    connection, _ = connect()
    readonly = ReadOnlyConnection(connection)
    cursor = readonly.cursor()
    try:
        evidence: dict[str, Any] = {
            "gate": "TELCHI_ORDER_DOCUMENT_CHAIN_V1",
            "mode": "SAP_HANA_READ_ONLY_LOW_IMPACT",
            "cohort": {
                "start_date": START_DATE,
                "end_date_exclusive": END_DATE_EXCLUSIVE,
                "max_order_docentry": MAX_ORDER_DOCENTRY,
                "purpose": "freeze Gate 1 order cohort",
            },
            "sap_write_count": SAP_WRITE_COUNT,
        }
        evidence["preflight"] = _rows(
            cursor,
            'SELECT CURRENT_TIMESTAMP AS "server_timestamp", CURRENT_USER AS "current_user", '
            'CURRENT_SCHEMA AS "current_schema" FROM DUMMY',
        )[0]

        # Relationship quality before the combined chain. Each check is line-grain.
        evidence["relationship_quality"] = {}
        evidence["relationship_quality"]["order_to_delivery"] = _rows(
            cursor,
            f'''SELECT * FROM (WITH O AS ({ORDER_COHORT_SQL})
                SELECT COUNT(*) AS "linked_lines",
                    SUM(CASE WHEN R."DocEntry" IS NOT NULL AND R."ItemCode"=D."ItemCode"
                             THEN 1 ELSE 0 END) AS "exact_line_item_matches",
                    COUNT(DISTINCT D."DocEntry") AS "delivery_documents",
                    COUNT(DISTINCT D."BaseEntry") AS "orders_referenced"
                FROM "TELCHI"."DLN1" D
                INNER JOIN O ON O."DocEntry"=D."BaseEntry"
                LEFT JOIN "TELCHI"."RDR1" R
                  ON R."DocEntry"=D."BaseEntry" AND R."LineNum"=D."BaseLine"
                WHERE D."BaseType"='17' AND D."ItemCode" LIKE 'L%') AS Q ''',
        )[0]
        evidence["relationship_quality"]["order_to_direct_invoice"] = _rows(
            cursor,
            f'''SELECT * FROM (WITH O AS ({ORDER_COHORT_SQL})
                SELECT COUNT(*) AS "linked_lines",
                    SUM(CASE WHEN R."DocEntry" IS NOT NULL AND R."ItemCode"=I."ItemCode"
                             THEN 1 ELSE 0 END) AS "exact_line_item_matches",
                    COUNT(DISTINCT I."DocEntry") AS "invoice_documents",
                    COUNT(DISTINCT I."BaseEntry") AS "orders_referenced"
                FROM "TELCHI"."INV1" I
                INNER JOIN O ON O."DocEntry"=I."BaseEntry"
                LEFT JOIN "TELCHI"."RDR1" R
                  ON R."DocEntry"=I."BaseEntry" AND R."LineNum"=I."BaseLine"
                WHERE I."BaseType"='17' AND I."ItemCode" LIKE 'L%') AS Q ''',
        )[0]
        evidence["relationship_quality"]["delivery_to_invoice"] = _rows(
            cursor,
            f'''SELECT * FROM (WITH O AS ({ORDER_COHORT_SQL})
                SELECT COUNT(*) AS "linked_lines",
                    SUM(CASE WHEN D."DocEntry" IS NOT NULL AND D."ItemCode"=I."ItemCode"
                             THEN 1 ELSE 0 END) AS "exact_line_item_matches",
                    COUNT(DISTINCT I."DocEntry") AS "invoice_documents",
                    COUNT(DISTINCT D."DocEntry") AS "deliveries_referenced"
                FROM "TELCHI"."DLN1" D
                INNER JOIN O ON O."DocEntry"=D."BaseEntry"
                INNER JOIN "TELCHI"."INV1" I
                  ON I."BaseType"='15' AND I."BaseEntry"=D."DocEntry"
                 AND I."BaseLine"=D."LineNum"
                WHERE D."BaseType"='17' AND D."ItemCode" LIKE 'L%') AS Q ''',
        )[0]

        per_order = _rows(
            cursor,
            f'''SELECT * FROM (WITH O AS ({ORDER_COHORT_SQL}),
            D AS (
              SELECT X."BaseEntry" AS "order_entry",
                COUNT(DISTINCT CASE WHEN H."CANCELED"='N' THEN H."DocEntry" END)
                    AS "active_delivery_count",
                COUNT(DISTINCT CASE WHEN H."CANCELED"<>'N' THEN H."DocEntry" END)
                    AS "canceled_delivery_count",
                SUM(CASE WHEN H."CANCELED"='N' THEN X."Quantity" ELSE 0 END)
                    AS "active_delivery_qty"
              FROM "TELCHI"."DLN1" X
              INNER JOIN O ON O."DocEntry"=X."BaseEntry"
              INNER JOIN "TELCHI"."ODLN" H ON H."DocEntry"=X."DocEntry"
              INNER JOIN "TELCHI"."RDR1" R
                ON R."DocEntry"=X."BaseEntry" AND R."LineNum"=X."BaseLine"
               AND R."ItemCode"=X."ItemCode"
              WHERE X."BaseType"='17' AND X."ItemCode" LIKE 'L%'
              GROUP BY X."BaseEntry"
            ),
            DI AS (
              SELECT X."BaseEntry" AS "order_entry",
                COUNT(DISTINCT CASE WHEN H."CANCELED"='N' THEN H."DocEntry" END)
                    AS "active_direct_invoice_count",
                COUNT(DISTINCT CASE WHEN H."CANCELED"<>'N' THEN H."DocEntry" END)
                    AS "canceled_direct_invoice_count",
                SUM(CASE WHEN H."CANCELED"='N' THEN X."Quantity" ELSE 0 END)
                    AS "active_direct_invoice_qty"
              FROM "TELCHI"."INV1" X
              INNER JOIN O ON O."DocEntry"=X."BaseEntry"
              INNER JOIN "TELCHI"."OINV" H ON H."DocEntry"=X."DocEntry"
              INNER JOIN "TELCHI"."RDR1" R
                ON R."DocEntry"=X."BaseEntry" AND R."LineNum"=X."BaseLine"
               AND R."ItemCode"=X."ItemCode"
              WHERE X."BaseType"='17' AND X."ItemCode" LIKE 'L%'
              GROUP BY X."BaseEntry"
            ),
            DVI AS (
              SELECT D0."BaseEntry" AS "order_entry",
                COUNT(DISTINCT CASE WHEN IH."CANCELED"='N' THEN I."DocEntry" END)
                    AS "active_delivery_invoice_count",
                COUNT(DISTINCT CASE WHEN IH."CANCELED"<>'N' THEN I."DocEntry" END)
                    AS "canceled_delivery_invoice_count"
              FROM "TELCHI"."DLN1" D0
              INNER JOIN O ON O."DocEntry"=D0."BaseEntry"
              INNER JOIN "TELCHI"."INV1" I
                ON I."BaseType"='15' AND I."BaseEntry"=D0."DocEntry"
               AND I."BaseLine"=D0."LineNum" AND I."ItemCode"=D0."ItemCode"
              INNER JOIN "TELCHI"."OINV" IH ON IH."DocEntry"=I."DocEntry"
              WHERE D0."BaseType"='17' AND D0."ItemCode" LIKE 'L%'
              GROUP BY D0."BaseEntry"
            ),
            DM AS (
              SELECT X."BaseEntry" AS "order_entry", SUM(M."OutQty") AS "delivery_out_qty",
                COUNT(DISTINCT M."TransNum") AS "delivery_movement_count"
              FROM "TELCHI"."DLN1" X
              INNER JOIN O ON O."DocEntry"=X."BaseEntry"
              INNER JOIN "TELCHI"."ODLN" H ON H."DocEntry"=X."DocEntry" AND H."CANCELED"='N'
              INNER JOIN "TELCHI"."RDR1" R
                ON R."DocEntry"=X."BaseEntry" AND R."LineNum"=X."BaseLine"
               AND R."ItemCode"=X."ItemCode"
              INNER JOIN "TELCHI"."OINM" M
                ON M."TransType"=15 AND M."BASE_REF"=TO_NVARCHAR(H."DocNum")
               AND M."DocLineNum"=X."LineNum" AND M."ItemCode"=X."ItemCode"
              WHERE X."BaseType"='17' AND X."ItemCode" LIKE 'L%'
              GROUP BY X."BaseEntry"
            ),
            IM AS (
              SELECT X."BaseEntry" AS "order_entry", SUM(M."OutQty") AS "invoice_out_qty",
                COUNT(DISTINCT M."TransNum") AS "invoice_movement_count"
              FROM "TELCHI"."INV1" X
              INNER JOIN O ON O."DocEntry"=X."BaseEntry"
              INNER JOIN "TELCHI"."OINV" H ON H."DocEntry"=X."DocEntry" AND H."CANCELED"='N'
              INNER JOIN "TELCHI"."RDR1" R
                ON R."DocEntry"=X."BaseEntry" AND R."LineNum"=X."BaseLine"
               AND R."ItemCode"=X."ItemCode"
              INNER JOIN "TELCHI"."OINM" M
                ON M."TransType"=13 AND M."BASE_REF"=TO_NVARCHAR(H."DocNum")
               AND M."DocLineNum"=X."LineNum" AND M."ItemCode"=X."ItemCode"
              WHERE X."BaseType"='17' AND X."ItemCode" LIKE 'L%'
              GROUP BY X."BaseEntry"
            )
            SELECT O.*,
              COALESCE(D."active_delivery_count",0) AS "active_delivery_count",
              COALESCE(D."canceled_delivery_count",0) AS "canceled_delivery_count",
              COALESCE(D."active_delivery_qty",0) AS "active_delivery_qty",
              COALESCE(DI."active_direct_invoice_count",0) AS "active_direct_invoice_count",
              COALESCE(DI."canceled_direct_invoice_count",0) AS "canceled_direct_invoice_count",
              COALESCE(DI."active_direct_invoice_qty",0) AS "active_direct_invoice_qty",
              COALESCE(DVI."active_delivery_invoice_count",0) AS "active_delivery_invoice_count",
              COALESCE(DVI."canceled_delivery_invoice_count",0) AS "canceled_delivery_invoice_count",
              COALESCE(DM."delivery_out_qty",0) AS "delivery_out_qty",
              COALESCE(DM."delivery_movement_count",0) AS "delivery_movement_count",
              COALESCE(IM."invoice_out_qty",0) AS "invoice_out_qty",
              COALESCE(IM."invoice_movement_count",0) AS "invoice_movement_count",
              COALESCE(D."active_delivery_qty",0)+COALESCE(DI."active_direct_invoice_qty",0)
                AS "document_exit_qty",
              COALESCE(DM."delivery_out_qty",0)+COALESCE(IM."invoice_out_qty",0)
                AS "movement_out_qty"
            FROM O
            LEFT JOIN D ON D."order_entry"=O."DocEntry"
            LEFT JOIN DI ON DI."order_entry"=O."DocEntry"
            LEFT JOIN DVI ON DVI."order_entry"=O."DocEntry"
            LEFT JOIN DM ON DM."order_entry"=O."DocEntry"
            LEFT JOIN IM ON IM."order_entry"=O."DocEntry"
            ORDER BY O."DocEntry") AS Q''',
        )

        evidence["summary"] = _aggregate(per_order)
        sample_ids = sorted({
            example["order_entry"]
            for examples in evidence["summary"]["route_examples"].values()
            for example in examples
        })
        placeholders = ",".join("?" for _ in sample_ids)
        evidence["sample_documents"] = {
            "deliveries": _rows(
                cursor,
                f'''SELECT D."BaseEntry" AS "order_entry", H."DocEntry" AS "document_entry",
                    H."DocNum" AS "document_number", H."CANCELED" AS "canceled",
                    D."LineNum" AS "document_line", D."BaseLine" AS "order_line",
                    D."ItemCode" AS "item_code", D."WhsCode" AS "warehouse",
                    D."Quantity" AS "quantity", M."TransNum" AS "movement_id",
                    M."OutQty" AS "movement_out_qty"
                    FROM "TELCHI"."DLN1" D
                    INNER JOIN "TELCHI"."ODLN" H ON H."DocEntry"=D."DocEntry"
                    LEFT JOIN "TELCHI"."OINM" M
                      ON M."TransType"=15 AND M."BASE_REF"=TO_NVARCHAR(H."DocNum")
                     AND M."DocLineNum"=D."LineNum" AND M."ItemCode"=D."ItemCode"
                    WHERE D."BaseType"='17' AND D."BaseEntry" IN ({placeholders})
                      AND D."ItemCode" LIKE 'L%'
                    ORDER BY D."BaseEntry", H."DocEntry", D."LineNum"''',
                tuple(sample_ids),
            ),
            "direct_invoices": _rows(
                cursor,
                f'''SELECT I."BaseEntry" AS "order_entry", H."DocEntry" AS "document_entry",
                    H."DocNum" AS "document_number", H."CANCELED" AS "canceled",
                    I."LineNum" AS "document_line", I."BaseLine" AS "order_line",
                    I."ItemCode" AS "item_code", I."WhsCode" AS "warehouse",
                    I."Quantity" AS "quantity", M."TransNum" AS "movement_id",
                    M."OutQty" AS "movement_out_qty"
                    FROM "TELCHI"."INV1" I
                    INNER JOIN "TELCHI"."OINV" H ON H."DocEntry"=I."DocEntry"
                    LEFT JOIN "TELCHI"."OINM" M
                      ON M."TransType"=13 AND M."BASE_REF"=TO_NVARCHAR(H."DocNum")
                     AND M."DocLineNum"=I."LineNum" AND M."ItemCode"=I."ItemCode"
                    WHERE I."BaseType"='17' AND I."BaseEntry" IN ({placeholders})
                      AND I."ItemCode" LIKE 'L%'
                    ORDER BY I."BaseEntry", H."DocEntry", I."LineNum"''',
                tuple(sample_ids),
            ),
            "delivery_invoices": _rows(
                cursor,
                f'''SELECT D."BaseEntry" AS "order_entry", D."DocEntry" AS "delivery_entry",
                    I."DocEntry" AS "invoice_entry", H."DocNum" AS "invoice_number",
                    H."CANCELED" AS "canceled", I."LineNum" AS "invoice_line",
                    D."LineNum" AS "delivery_line", D."BaseLine" AS "order_line",
                    I."ItemCode" AS "item_code", I."Quantity" AS "quantity"
                    FROM "TELCHI"."DLN1" D
                    INNER JOIN "TELCHI"."INV1" I
                      ON I."BaseType"='15' AND I."BaseEntry"=D."DocEntry"
                     AND I."BaseLine"=D."LineNum" AND I."ItemCode"=D."ItemCode"
                    INNER JOIN "TELCHI"."OINV" H ON H."DocEntry"=I."DocEntry"
                    WHERE D."BaseType"='17' AND D."BaseEntry" IN ({placeholders})
                      AND D."ItemCode" LIKE 'L%'
                    ORDER BY D."BaseEntry", D."DocEntry", I."DocEntry", I."LineNum"''',
                tuple(sample_ids),
            ),
        }
        evidence["semantics_boundary"] = {
            "proven_here": [
                "BaseType/BaseEntry/BaseLine plus ItemCode document relationships",
                "document and movement cardinalities for the frozen order cohort",
                "OINM TransType family plus BASE_REF=DocNum and line/item linkage",
            ],
            "not_proven_here": [
                "OINM timestamp meaning as physical warehouse exit",
                "whether ODLN or OINV movement is the authoritative exit event",
                "first and complete warehouse-exit datetime",
            ],
        }
        evidence["sap_write_count"] = SAP_WRITE_COUNT
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        output = EVIDENCE_DIR / "document_chain_v1.json"
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
        "relationship_quality": evidence["relationship_quality"],
        "summary": evidence["summary"],
        "sap_write_count": evidence["sap_write_count"],
        "evidence_path": evidence["evidence_path"],
    }, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
