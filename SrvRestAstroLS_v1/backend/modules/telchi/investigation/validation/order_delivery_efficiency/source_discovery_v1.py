"""Gate 1: low-impact source discovery for Telchi order/delivery efficiency.

All SAP/HANA access is guarded SELECT-only. Queries are sequential, date-filtered
where possible, and return aggregates or small samples. Evidence is written to the
external Telchi evidence root, never to the repository or Data Root.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import EVIDENCE_ROOT
from modules.telchi.investigation.validation.credit_control.readonly import (
    ReadOnlyConnection,
)

EVIDENCE_DIR = EVIDENCE_ROOT / "order_delivery_efficiency" / "evidence"
WINDOW_DAYS = 30
SAMPLE_LIMIT = 20
SAP_WRITE_COUNT = 0


def _rows(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, params)
    columns = [item[0].lower() for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _json_default(value: Any) -> str | float:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def run() -> dict[str, Any]:
    connection, _ = connect()
    readonly = ReadOnlyConnection(connection)
    cursor = readonly.cursor()
    try:
        evidence: dict[str, Any] = {
            "gate": "TELCHI_ORDER_DELIVERY_SOURCE_DISCOVERY_V1",
            "mode": "SAP_HANA_READ_ONLY_LOW_IMPACT",
            "window_days": WINDOW_DAYS,
            "sample_limit": SAMPLE_LIMIT,
            "sap_write_count": SAP_WRITE_COUNT,
        }

        evidence["preflight"] = _rows(
            cursor,
            'SELECT CURRENT_TIMESTAMP AS "server_timestamp", CURRENT_USER AS "current_user", '
            'CURRENT_SCHEMA AS "current_schema" FROM DUMMY',
        )[0]

        # Zero-row projection validates only the candidate columns needed by this gate.
        candidate_columns = {
            "ORDR": [
                "DocEntry", "DocNum", "DocDate", "DocTime", "CreateDate", "CreateTS",
                "UpdateDate", "UpdateTS", "CANCELED", "DocStatus", "CardCode", "SlpCode",
                "UserSign", "BPLId", "U_ORIGIN", "U_DMS_STATE", "U_OSLP_ID",
                "U_SO1_01RETAILONE", "U_SO1_01FOLIORETAIL1", "U_SO1_01SUCURSAL",
            ],
            "ODLN": [
                "DocEntry", "DocNum", "DocDate", "DocTime", "CreateDate", "CreateTS",
                "UpdateDate", "UpdateTS", "CANCELED", "DocStatus", "CardCode", "SlpCode",
                "UserSign", "BPLId", "U_ORIGIN", "U_DMS_STATE", "U_OSLP_ID",
                "U_SO1_01RETAILONE", "U_SO1_01FOLIORETAIL1", "U_SO1_01SUCURSAL",
            ],
            "OINV": [
                "DocEntry", "DocNum", "DocDate", "DocTime", "CreateDate", "CreateTS",
                "UpdateDate", "UpdateTS", "CANCELED", "DocStatus", "CardCode", "SlpCode",
                "UserSign", "BPLId", "U_ORIGIN", "U_DMS_STATE", "U_OSLP_ID",
                "U_SO1_01RETAILONE", "U_SO1_01FOLIORETAIL1", "U_SO1_01SUCURSAL",
            ],
            "@SO1_01VENTA": [
                "Code", "Name", "U_SO1_FECHA", "U_SO1_HORA", "U_SO1_HORACADENA",
                "U_SO1_PEDIDO", "U_SO1_FACTURA", "U_SO1_DOCUMENTOSBO", "U_SO1_CLIENTE",
                "U_SO1_SUCURSAL", "U_SO1_ESTACION", "U_SO1_USUARIO", "U_SO1_VENDEDOR",
                "U_SO1_TIPO", "U_SO1_STATUS", "U_SO1_SINCRONIZADO",
                "U_SO1_FECHAENTREGA", "U_SO1_HORAENTREGA", "U_SO1_HORAENTCADENA",
                "U_SO1_REPARTIDOR", "U_SO1_ZONA", "U_SO1_METODOENVIO",
                "U_SO1_MODALIDENTREGA", "U_SO1_ORIGENDOCUMENT",
            ],
        }
        evidence["candidate_columns"] = {}
        for table, columns in candidate_columns.items():
            projection = ",".join(f'"{column}"' for column in columns)
            cursor.execute(f'SELECT {projection} FROM "TELCHI"."{table}" LIMIT 0')
            evidence["candidate_columns"][table] = [item[0] for item in cursor.description]

        evidence["document_recency"] = {}
        for table in ("ORDR", "ODLN", "OINV"):
            evidence["document_recency"][table] = _rows(
                cursor,
                f'''SELECT MIN("DocDate") AS "window_min_date", MAX("DocDate") AS "max_date",
                    COUNT(*) AS "documents_30d",
                    SUM(CASE WHEN "CANCELED"='Y' THEN 1 ELSE 0 END) AS "canceled_30d"
                    FROM "TELCHI"."{table}"
                    WHERE "DocDate" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})''',
            )[0]

        evidence["l_order_universe_30d"] = _rows(
            cursor,
            f'''SELECT COUNT(*) AS "orders_with_l",
                SUM(CASE WHEN EXISTS (
                    SELECT 1 FROM "TELCHI"."RDR1" X
                    WHERE X."DocEntry"=O."DocEntry" AND X."ItemCode" NOT LIKE 'L%'
                ) THEN 1 ELSE 0 END) AS "mixed_orders",
                SUM(CASE WHEN O."CANCELED"='Y' THEN 1 ELSE 0 END) AS "canceled_orders"
                FROM "TELCHI"."ORDR" O
                WHERE O."DocDate" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                  AND EXISTS (
                    SELECT 1 FROM "TELCHI"."RDR1" L
                    WHERE L."DocEntry"=O."DocEntry" AND L."ItemCode" LIKE 'L%'
                  )''',
        )[0]

        evidence["l_order_channels_30d"] = _rows(
            cursor,
            f'''SELECT CASE
                    WHEN O."U_ORIGIN"='DMS' THEN 'DMS'
                    WHEN O."U_ORIGIN"='SAP' AND O."U_SO1_01RETAILONE"='Y' THEN 'RETAIL_ONE'
                    WHEN O."U_ORIGIN"='SAP' AND O."U_SO1_01RETAILONE"='N' THEN 'SAP_DIRECT'
                    ELSE 'UNCLASSIFIED'
                END AS "channel", COUNT(*) AS "orders"
                FROM "TELCHI"."ORDR" O
                WHERE O."DocDate" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                  AND EXISTS (
                    SELECT 1 FROM "TELCHI"."RDR1" L
                    WHERE L."DocEntry"=O."DocEntry" AND L."ItemCode" LIKE 'L%'
                  )
                GROUP BY CASE
                    WHEN O."U_ORIGIN"='DMS' THEN 'DMS'
                    WHEN O."U_ORIGIN"='SAP' AND O."U_SO1_01RETAILONE"='Y' THEN 'RETAIL_ONE'
                    WHEN O."U_ORIGIN"='SAP' AND O."U_SO1_01RETAILONE"='N' THEN 'SAP_DIRECT'
                    ELSE 'UNCLASSIFIED' END
                ORDER BY "orders" DESC''',
        )

        evidence["retail_one_candidate_coverage_30d"] = _rows(
            cursor,
            f'''SELECT COUNT(*) AS "retail_rows",
                SUM(CASE WHEN "U_SO1_PEDIDO" IS NOT NULL THEN 1 ELSE 0 END) AS "with_order_ref",
                SUM(CASE WHEN "U_SO1_FACTURA" IS NOT NULL THEN 1 ELSE 0 END) AS "with_invoice_ref",
                SUM(CASE WHEN "U_SO1_DOCUMENTOSBO" IS NOT NULL THEN 1 ELSE 0 END) AS "with_sap_document_ref",
                SUM(CASE WHEN "U_SO1_FECHAENTREGA" IS NOT NULL THEN 1 ELSE 0 END) AS "with_delivery_date",
                SUM(CASE WHEN "U_SO1_HORAENTREGA" IS NOT NULL THEN 1 ELSE 0 END) AS "with_delivery_time",
                SUM(CASE WHEN "U_SO1_REPARTIDOR" IS NOT NULL THEN 1 ELSE 0 END) AS "with_driver",
                SUM(CASE WHEN "U_SO1_ZONA" IS NOT NULL THEN 1 ELSE 0 END) AS "with_zone",
                SUM(CASE WHEN "U_SO1_METODOENVIO" IS NOT NULL THEN 1 ELSE 0 END) AS "with_shipping_method",
                SUM(CASE WHEN "U_SO1_MODALIDENTREGA" IS NOT NULL THEN 1 ELSE 0 END) AS "with_delivery_mode"
                FROM "TELCHI"."@SO1_01VENTA"
                WHERE "U_SO1_FECHA" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})''',
        )[0]

        evidence["retail_one_flag_distribution_30d"] = _rows(
            cursor,
            f'''SELECT "U_SO1_PEDIDO" AS "order_flag", "U_SO1_FACTURA" AS "invoice_flag",
                "U_SO1_SINCRONIZADO" AS "synchronized_flag", COUNT(*) AS "rows"
                FROM "TELCHI"."@SO1_01VENTA"
                WHERE "U_SO1_FECHA" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                GROUP BY "U_SO1_PEDIDO", "U_SO1_FACTURA", "U_SO1_SINCRONIZADO"
                ORDER BY "rows" DESC''',
        )

        evidence["retail_one_types_30d"] = _rows(
            cursor,
            f'''SELECT "U_SO1_TIPO" AS "type", "U_SO1_STATUS" AS "status",
                "U_SO1_ORIGENDOCUMENT" AS "document_origin", COUNT(*) AS "rows",
                SUM(CASE WHEN "U_SO1_FECHAENTREGA" IS NOT NULL
                              AND COALESCE("U_SO1_HORAENTREGA", 0) > 0 THEN 1 ELSE 0 END)
                    AS "with_complete_delivery_candidate"
                FROM "TELCHI"."@SO1_01VENTA"
                WHERE "U_SO1_FECHA" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                GROUP BY "U_SO1_TIPO", "U_SO1_STATUS", "U_SO1_ORIGENDOCUMENT"
                ORDER BY "rows" DESC LIMIT 30''',
        )

        evidence["retail_one_l_universe_30d"] = _rows(
            cursor,
            f'''SELECT COUNT(*) AS "transactions_with_l",
                SUM(CASE WHEN EXISTS (
                    SELECT 1 FROM "TELCHI"."@SO1_01VENTADETALLE" X
                    WHERE X."Code"=V."Code" AND X."U_SO1_NUMEROARTICULO" NOT LIKE 'L%'
                ) THEN 1 ELSE 0 END) AS "mixed_transactions",
                SUM(CASE WHEN V."U_SO1_PEDIDO"='Y' THEN 1 ELSE 0 END) AS "order_flag_y",
                SUM(CASE WHEN V."U_SO1_FACTURA"='Y' THEN 1 ELSE 0 END) AS "invoice_flag_y",
                SUM(CASE WHEN V."U_SO1_FECHAENTREGA" IS NOT NULL
                              AND COALESCE(V."U_SO1_HORAENTREGA", 0) > 0 THEN 1 ELSE 0 END)
                    AS "with_complete_delivery_candidate"
                FROM "TELCHI"."@SO1_01VENTA" V
                WHERE V."U_SO1_FECHA" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                  AND EXISTS (
                    SELECT 1 FROM "TELCHI"."@SO1_01VENTADETALLE" L
                    WHERE L."Code"=V."Code" AND L."U_SO1_NUMEROARTICULO" LIKE 'L%'
                  )''',
        )[0]

        evidence["retail_one_to_invoice_30d"] = _rows(
            cursor,
            f'''SELECT COUNT(*) AS "retail_l_transactions",
                SUM(CASE WHEN I."DocEntry" IS NOT NULL THEN 1 ELSE 0 END) AS "matched_invoices",
                COUNT(DISTINCT I."DocEntry") AS "distinct_invoices"
                FROM "TELCHI"."@SO1_01VENTA" V
                LEFT JOIN "TELCHI"."OINV" I ON I."U_SO1_01FOLIORETAIL1"=V."Name"
                WHERE V."U_SO1_FECHA" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                  AND EXISTS (
                    SELECT 1 FROM "TELCHI"."@SO1_01VENTADETALLE" L
                    WHERE L."Code"=V."Code" AND L."U_SO1_NUMEROARTICULO" LIKE 'L%'
                  )''',
        )[0]

        evidence["channel_users_30d"] = _rows(
            cursor,
            f'''SELECT CASE
                    WHEN O."U_ORIGIN"='DMS' THEN 'DMS'
                    WHEN O."U_ORIGIN"='SAP' AND O."U_SO1_01RETAILONE"='N' THEN 'SAP_DIRECT'
                    ELSE 'UNCLASSIFIED' END AS "channel",
                O."UserSign" AS "user_id", U."USER_CODE" AS "user_code", COUNT(*) AS "orders"
                FROM "TELCHI"."ORDR" O
                LEFT JOIN "TELCHI"."OUSR" U ON U."USERID"=O."UserSign"
                WHERE O."DocDate" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                  AND EXISTS (
                    SELECT 1 FROM "TELCHI"."RDR1" L
                    WHERE L."DocEntry"=O."DocEntry" AND L."ItemCode" LIKE 'L%'
                  )
                GROUP BY CASE
                    WHEN O."U_ORIGIN"='DMS' THEN 'DMS'
                    WHEN O."U_ORIGIN"='SAP' AND O."U_SO1_01RETAILONE"='N' THEN 'SAP_DIRECT'
                    ELSE 'UNCLASSIFIED' END, O."UserSign", U."USER_CODE"
                ORDER BY "orders" DESC''',
        )

        evidence["retail_one_samples"] = _rows(
            cursor,
            f'''SELECT "Code", "Name", "U_SO1_FECHA", "U_SO1_HORA", "U_SO1_HORACADENA",
                "U_SO1_PEDIDO", "U_SO1_FACTURA", "U_SO1_DOCUMENTOSBO", "U_SO1_CLIENTE",
                "U_SO1_SUCURSAL", "U_SO1_ESTACION", "U_SO1_TIPO", "U_SO1_STATUS",
                "U_SO1_SINCRONIZADO", "U_SO1_FECHAENTREGA", "U_SO1_HORAENTREGA",
                "U_SO1_HORAENTCADENA", "U_SO1_REPARTIDOR", "U_SO1_ZONA",
                "U_SO1_METODOENVIO", "U_SO1_MODALIDENTREGA", "U_SO1_ORIGENDOCUMENT"
                FROM "TELCHI"."@SO1_01VENTA"
                WHERE "U_SO1_FECHA" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                ORDER BY "U_SO1_FECHA" DESC, "U_SO1_HORA" DESC LIMIT {SAMPLE_LIMIT}''',
        )

        evidence["retail_one_delivery_candidate_samples"] = _rows(
            cursor,
            f'''SELECT "Code", "Name", "U_SO1_FECHA", "U_SO1_HORA", "U_SO1_TIPO",
                "U_SO1_STATUS", "U_SO1_FECHAENTREGA", "U_SO1_HORAENTREGA",
                "U_SO1_HORAENTCADENA", "U_SO1_REPARTIDOR", "U_SO1_ZONA",
                "U_SO1_METODOENVIO", "U_SO1_MODALIDENTREGA"
                FROM "TELCHI"."@SO1_01VENTA"
                WHERE "U_SO1_FECHA" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                  AND "U_SO1_FECHAENTREGA" IS NOT NULL
                  AND COALESCE("U_SO1_HORAENTREGA", 0) > 0
                ORDER BY "U_SO1_FECHA" DESC LIMIT {SAMPLE_LIMIT}''',
        )

        evidence["retail_one_invoice_link_samples"] = _rows(
            cursor,
            f'''SELECT V."Code" AS "retail_code", V."Name" AS "retail_folio",
                V."U_SO1_FECHA" AS "retail_date", V."U_SO1_HORA" AS "retail_time",
                I."DocEntry" AS "invoice_entry", I."DocNum" AS "invoice_number",
                I."CreateDate" AS "invoice_create_date", I."CreateTS" AS "invoice_create_ts",
                I."DocTime" AS "invoice_doc_time", I."UserSign" AS "invoice_user_id"
                FROM "TELCHI"."@SO1_01VENTA" V
                INNER JOIN "TELCHI"."OINV" I ON I."U_SO1_01FOLIORETAIL1"=V."Name"
                WHERE V."U_SO1_FECHA" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                  AND EXISTS (
                    SELECT 1 FROM "TELCHI"."@SO1_01VENTADETALLE" L
                    WHERE L."Code"=V."Code" AND L."U_SO1_NUMEROARTICULO" LIKE 'L%'
                  )
                ORDER BY V."U_SO1_FECHA" DESC, V."U_SO1_HORA" DESC LIMIT {SAMPLE_LIMIT}''',
        )

        evidence["l_order_samples"] = _rows(
            cursor,
            f'''SELECT O."DocEntry", O."DocNum", O."DocDate", O."DocTime", O."CreateDate",
                O."CreateTS", O."UpdateDate", O."UpdateTS", O."CANCELED", O."DocStatus",
                O."CardCode", O."SlpCode", O."UserSign", O."BPLId", O."U_ORIGIN",
                O."U_DMS_STATE", O."U_OSLP_ID", O."U_SO1_01RETAILONE",
                O."U_SO1_01FOLIORETAIL1", O."U_SO1_01SUCURSAL"
                FROM "TELCHI"."ORDR" O
                WHERE O."DocDate" >= ADD_DAYS(CURRENT_DATE, -{WINDOW_DAYS})
                  AND EXISTS (
                    SELECT 1 FROM "TELCHI"."RDR1" L
                    WHERE L."DocEntry"=O."DocEntry" AND L."ItemCode" LIKE 'L%'
                  )
                ORDER BY O."DocDate" DESC, O."DocEntry" DESC LIMIT {SAMPLE_LIMIT}''',
        )

        evidence["sap_write_count"] = SAP_WRITE_COUNT
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        output = EVIDENCE_DIR / "source_discovery_v1.json"
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
        "preflight": evidence["preflight"],
        "document_recency": evidence["document_recency"],
        "l_order_universe_30d": evidence["l_order_universe_30d"],
        "l_order_channels_30d": evidence["l_order_channels_30d"],
        "retail_one_candidate_coverage_30d": evidence["retail_one_candidate_coverage_30d"],
        "retail_one_l_universe_30d": evidence["retail_one_l_universe_30d"],
        "retail_one_to_invoice_30d": evidence["retail_one_to_invoice_30d"],
        "sap_write_count": evidence["sap_write_count"],
        "evidence_path": evidence["evidence_path"],
    }, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
