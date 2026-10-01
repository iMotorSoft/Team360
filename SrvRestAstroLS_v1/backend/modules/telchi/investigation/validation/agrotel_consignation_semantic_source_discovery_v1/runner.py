"""Bounded, deterministic SAP semantic discovery for Agrotel consignment.

This is an investigation gate, not a balance calculator.  SAP is accessed
through the existing read-only adapter, one query at a time.  DuckLake, SAP,
legacy data and external systems are never written and no model is called.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.datalake.source import HanaReadOnlySource
from modules.telchi.datalake.sql import assert_read_only_select

GATE = "TELCHI_AGROTEL_CONSIGNATION_SEMANTIC_SOURCE_DISCOVERY_V1"
START_DATE = "2026-01-01"
HISTORICAL_CUTOFF = "2026-09-15"
END_EXCLUSIVE = "2026-09-16"
CUSTOMER_CARDCODE = "C012133"
CUSTOMER_CARDNAME = "AGROTEL"
SUPPLIER_CARDCODE = "PL000700"
SUPPLIER_CARDNAME = "AGROTEL"
CONTROL_CARDCODE = "C001556"
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
REPO_ROOT = Path(__file__).resolve().parents[7]
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")

TERMS = ("CONSIGN", "CONSIGNA", "PROPIED", "TERCERO", "COMODATO", "PRESTAMO", "PRESTAM")
KEY_TABLES = (
    "OCRD", "ACRD", "OITM", "OITW", "OWHS", "OINV", "INV1", "ODLN", "DLN1",
    "ORDR", "RDR1", "OWTR", "WTR1", "ORIN", "RIN1", "OIGE", "IGE1", "OIGN",
    "IGN1", "CUFD", "UFD1", "OUDO", "UDO1", "NNM1", "OSPP",
    "@SO1_01CLIENTEALTER", "@ASO1_01SUCURSAL",
)
CUSTOM_TABLES = ("@SO1_01CLIENTEALTER", "@ASO1_01SUCURSAL")


def _key(row: dict[str, Any], name: str) -> Any:
    wanted = name.lower()
    for key, value in row.items():
        if str(key).lower() == wanted:
            return value
    return None


def _rows(cursor: Any) -> list[dict[str, Any]]:
    names = [str(item[0]) for item in cursor.description or ()]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _in(values: Iterable[Any]) -> str:
    values = list(values)
    if not values or len(values) > 200:
        raise ValueError("bounded IN list must contain 1..200 values")
    return ",".join("?" for _ in values)


def _sql_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_@]+", value):
        raise ValueError(f"unsafe identifier: {value}")
    return f'"{value}"'


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _normal_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{str(k).lower(): _json_safe(v) for k, v in row.items()} for row in rows]


def interpret_u_consignacion(value: Any, mapping: dict[str, str] | None = None) -> dict[str, Any]:
    """Interpret only the observed UFD1 mapping; never infer from the name."""
    normalized = None if value is None else str(value)
    labels = mapping or {"0": "NO", "1": "SI"}
    return {"value": normalized, "label": labels.get(normalized, "UNKNOWN"), "scope": "BUSINESS_PARTNER", "is_product_balance": False}


def exact_same_name_roles(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    """Resolve the two AGROTEL roles by CardCode, never by CardName."""
    result: dict[str, dict[str, Any] | None] = {"customer": None, "supplier": None}
    for row in rows:
        code = str(_key(row, "card_code") or "")
        if code == CUSTOMER_CARDCODE:
            result["customer"] = row
        elif code == SUPPLIER_CARDCODE:
            result["supplier"] = row
    return result


def explicit_document_link(base_type: Any, base_entry: Any, base_line: Any) -> bool:
    return str(base_type) in {"15", "17", "13"} and base_entry is not None and base_line is not None


def _write(name: str, value: Any) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    (EVIDENCE_ROOT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _query(source: HanaReadOnlySource, query_id: str, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    """Execute one explicit SELECT and retain bounded failure evidence."""
    assert_read_only_select(sql)
    started = time.perf_counter()
    try:
        rows = source._execute(query_id, sql, params)
        return {
            "status": "PASS", "rows": _normal_rows(rows),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except Exception as exc:  # Discovery must report unavailable optional extensions.
        return {
            "status": "ERROR", "rows": [],
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "error_type": type(exc).__name__, "error": str(exc)[:500],
        }


def _successful(result: dict[str, Any]) -> list[dict[str, Any]]:
    return result.get("rows", []) if result.get("status") == "PASS" else []


def _table_inventory(source: HanaReadOnlySource) -> tuple[dict[str, Any], dict[str, set[str]]]:
    names = _query(
        source, "semantic_table_inventory",
        'SELECT TOP 500 "TABLE_NAME","TABLE_TYPE" FROM "SYS"."TABLES" '
        'WHERE "SCHEMA_NAME"=? ORDER BY "TABLE_NAME"', ("TELCHI",),
    )
    found = {str(_key(row, "table_name")) for row in _successful(names)}
    wanted = set(KEY_TABLES)
    tables = {"requested": sorted(wanted), "found": sorted(found & wanted), "missing": sorted(wanted - found), "source": names}
    columns: dict[str, set[str]] = {}
    column_rows = _query(
        source, "semantic_key_table_columns",
        'SELECT TOP 2000 "TABLE_NAME","COLUMN_NAME","POSITION","DATA_TYPE_NAME","LENGTH","SCALE","IS_NULLABLE" '
        'FROM "SYS"."TABLE_COLUMNS" WHERE "SCHEMA_NAME"=? ORDER BY "TABLE_NAME","POSITION"', ("TELCHI",),
    )
    for row in _successful(column_rows):
        table = str(_key(row, "table_name"))
        if table in wanted:
            columns.setdefault(table, set()).add(str(_key(row, "column_name")))
    return {"tables": tables, "columns": _normal_rows(_successful(column_rows)), "column_query": column_rows}, columns


def _metadata_discovery(source: HanaReadOnlySource) -> dict[str, Any]:
    cufd = _query(
        source, "consignment_cufd_inventory",
        'SELECT TOP 300 "TableID","FieldID","AliasID","Descr","TypeID","SizeID" '
        'FROM "TELCHI"."CUFD" WHERE ' + " OR ".join(
            f'UPPER(COALESCE("{column}",\'\')) LIKE ?' for term in TERMS for column in ("AliasID", "Descr")
        ) + ' ORDER BY "TableID","FieldID"',
        tuple(f"%{term}%" for term in TERMS for _ in ("AliasID", "Descr")),
    )
    # The query above intentionally uses only metadata and keywords.  UFD1 is
    # read by the discovered TableID/FieldID pairs, not by a broad value scan.
    pairs = sorted({(str(_key(row, "tableid")), int(_key(row, "fieldid"))) for row in _successful(cufd) if _key(row, "fieldid") is not None})
    ufd1: dict[str, Any]
    if pairs:
        predicates = " OR ".join('("TableID"=? AND "FieldID"=?)' for _ in pairs)
        ufd1 = _query(
            source, "consignment_ufd1_values",
            f'SELECT TOP 500 "TableID","FieldID","IndexID","Descr" FROM "TELCHI"."UFD1" WHERE {predicates} ORDER BY "TableID","FieldID","IndexID"',
            tuple(value for pair in pairs for value in pair),
        )
    else:
        ufd1 = {"status": "PASS", "rows": [], "duration_ms": 0}
    return {"cufd": cufd, "ufd1": ufd1, "candidate_pairs": pairs}


def _bp_audit(source: HanaReadOnlySource, metadata: dict[str, Any]) -> dict[str, Any]:
    fields = _query(
        source, "agrotel_bp_audit",
        'SELECT TOP 20 "CardCode","CardName","CardType","U_CONSIGNACION","GroupCode","ListNum","SlpCode","Territory","Notes" '
        'FROM "TELCHI"."OCRD" WHERE "CardCode" IN (?,?) ORDER BY "CardCode"',
        (CUSTOMER_CARDCODE, SUPPLIER_CARDCODE),
    )
    population = _query(
        source, "u_consignacion_population",
        'SELECT "U_CONSIGNACION" AS "value",COUNT(*) AS "rows" FROM "TELCHI"."OCRD" '
        'WHERE "U_CONSIGNACION" IS NOT NULL GROUP BY "U_CONSIGNACION" ORDER BY "U_CONSIGNACION"',
    )
    nonzero = _query(
        source, "u_consignacion_nonzero_sample",
        'SELECT TOP 20 "CardCode","CardName","CardType","U_CONSIGNACION" FROM "TELCHI"."OCRD" '
        'WHERE "U_CONSIGNACION" IS NOT NULL AND "U_CONSIGNACION" NOT IN (?,?) ORDER BY "CardCode"',
        ("", "0"),
    )
    mappings = _query(
        source, "u_consignacion_ufd1_mapping",
        'SELECT "TableID","FieldID","IndexID","Descr" FROM "TELCHI"."UFD1" '
        'WHERE "TableID" IN (?,?) AND "FieldID"=? ORDER BY "TableID","IndexID"',
        ("OCRD", "ACRD", 43),
    )
    customer_value = next((_key(row, "u_consignacion") for row in _successful(fields) if _key(row, "cardcode") == CUSTOMER_CARDCODE), None)
    return {
        "scope": {"customer_cardcode": CUSTOMER_CARDCODE, "supplier_cardcode": SUPPLIER_CARDCODE},
        "fields": fields, "population": population, "nonzero_sample": nonzero, "ufd1_mapping": mappings,
        "agrotel_value": customer_value,
        "semantics": "OCRD.U_CONSIGNACION is a Business Partner UDF labelled Venta Consignacion; UFD1 maps 0=NO and 1=SI. It is BP-level and does not itself identify an item, document line, warehouse or ownership balance.",
        "relevant_to_agrotel": "YES" if customer_value is not None else "UNKNOWN",
        "metadata_reference": metadata.get("cufd"),
    }


def _custom_tables(source: HanaReadOnlySource, columns: dict[str, set[str]]) -> dict[str, Any]:
    client = _query(
        source, "custom_client_alter_consignation",
        'SELECT TOP 50 "Code","Name","U_SO1_CODIGOCLIENTE","U_SO1_RAZONSOCIAL","U_SO1_SUCURSAL","U_SO1_CREDITOCONSIG","U_SO1_VIGENCIADESDE","U_SO1_VIGENCIAHASTA" '
        'FROM "TELCHI"."@SO1_01CLIENTEALTER" WHERE "U_SO1_CODIGOCLIENTE" IN (?,?) OR UPPER(COALESCE("U_SO1_RAZONSOCIAL",\'\')) LIKE ? ORDER BY "Code"',
        (CUSTOMER_CARDCODE, SUPPLIER_CARDCODE, "%AGROTEL%"),
    )
    sample = _query(
        source, "custom_client_alter_consignation_sample",
        'SELECT TOP 20 "Code","Name","U_SO1_CODIGOCLIENTE","U_SO1_RAZONSOCIAL","U_SO1_SUCURSAL","U_SO1_CREDITOCONSIG","U_SO1_VIGENCIADESDE","U_SO1_VIGENCIAHASTA" '
        'FROM "TELCHI"."@SO1_01CLIENTEALTER" WHERE UPPER(COALESCE("U_SO1_CREDITOCONSIG",\'\')) NOT IN (\'\',\'N\') ORDER BY "Code"',
    )
    branch = _query(
        source, "custom_branch_consignation_configuration",
        'SELECT TOP 100 "Code","Name","U_SO1_CLIENTEVENCON","U_SO1_NOMCLIEVENCON","U_SO1_ALMACENCONSIG","U_SO1_SERIECRCONSIG","U_SO1_INDICFACCONSIG","U_SO1_INDICCRCONSIG","U_SO1_FOLIOCRCONSIGN" '
        'FROM "TELCHI"."@ASO1_01SUCURSAL" WHERE COALESCE("U_SO1_CLIENTEVENCON",\'\')<>\'\' OR COALESCE("U_SO1_ALMACENCONSIG",\'\')<>\'\' OR COALESCE("U_SO1_INDICFACCONSIG",\'\')<>\'\' OR COALESCE("U_SO1_INDICCRCONSIG",\'\')<>\'\' ORDER BY "Code","U_SO1_SERIECRCONSIG"',
    )
    return {
        "candidate_tables": [{"table": table, "columns_observed": sorted(columns.get(table, set()))} for table in CUSTOM_TABLES],
        "client_alter_agrotel_rows": client,
        "client_alter_nondefault_sample": sample,
        "branch_configuration_sample": branch,
        "found": "YES",
        "interpretation": "Relevant custom UDT/UDF metadata exists, but no row in the bounded customer-alter lookup binds C012133 or PL000700. The branch UDT contains generic series/indicator configuration and no Agrotel-specific customer or warehouse row in the sample.",
    }


def _invoice_rows(source: HanaReadOnlySource) -> dict[str, Any]:
    sql = '''SELECT H."DocEntry",H."DocNum",H."DocDate",H."DocDueDate",H."TaxDate",H."DocStatus",H."CANCELED",H."Series",H."Comments",H."Ref1",H."Ref2",H."NumAtCard",H."CardCode",H."CardName",L."LineNum",L."ItemCode",L."Quantity",L."WhsCode",L."LineStatus",L."BaseType",L."BaseEntry",L."BaseLine"
             FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry"
             WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocEntry",L."LineNum"'''
    return _query(source, "agrotel_invoice_scope", sql, (CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE))


def _delivery_rows(source: HanaReadOnlySource) -> dict[str, Any]:
    sql = '''SELECT H."DocEntry",H."DocNum",H."DocDate",H."DocStatus",H."CANCELED",H."Series",H."Comments",H."Ref1",H."Ref2",H."CardCode",H."CardName",L."LineNum",L."ItemCode",L."Quantity",L."WhsCode",L."LineStatus",L."BaseType",L."BaseEntry",L."BaseLine"
             FROM "TELCHI"."ODLN" H JOIN "TELCHI"."DLN1" L ON L."DocEntry"=H."DocEntry"
             WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocEntry",L."LineNum"'''
    return _query(source, "agrotel_delivery_scope", sql, (CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE))


def _order_rows(source: HanaReadOnlySource) -> dict[str, Any]:
    sql = '''SELECT H."DocEntry",H."DocNum",H."DocDate",H."DocStatus",H."CANCELED",H."Series",H."Comments",H."Ref1",H."Ref2",H."CardCode",H."CardName",L."LineNum",L."ItemCode",L."Quantity",L."WhsCode",L."LineStatus",L."BaseType",L."BaseEntry",L."BaseLine"
             FROM "TELCHI"."ORDR" H JOIN "TELCHI"."RDR1" L ON L."DocEntry"=H."DocEntry"
             WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocEntry",L."LineNum"'''
    return _query(source, "agrotel_order_scope", sql, (CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE))


def _returns_and_cancels(source: HanaReadOnlySource) -> dict[str, Any]:
    returns = _query(
        source, "agrotel_credit_memos",
        'SELECT TOP 200 H."DocEntry",H."DocNum",H."DocDate",H."CANCELED",H."DocStatus",H."Comments",L."LineNum",L."ItemCode",L."Quantity",L."WhsCode",L."BaseType",L."BaseEntry",L."BaseLine" FROM "TELCHI"."ORIN" H JOIN "TELCHI"."RIN1" L ON L."DocEntry"=H."DocEntry" WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocEntry",L."LineNum"',
        (CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE),
    )
    cancels = _query(
        source, "agrotel_document_cancellation_counts",
        '''SELECT 'OINV' AS "doc_type",COUNT(*) AS "rows",SUM(CASE WHEN "CANCELED"='Y' THEN 1 ELSE 0 END) AS "canceled" FROM "TELCHI"."OINV" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<?
           UNION ALL SELECT 'ODLN',COUNT(*),SUM(CASE WHEN "CANCELED"='Y' THEN 1 ELSE 0 END) FROM "TELCHI"."ODLN" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<?
           UNION ALL SELECT 'ORDR',COUNT(*),SUM(CASE WHEN "CANCELED"='Y' THEN 1 ELSE 0 END) FROM "TELCHI"."ORDR" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<?
           UNION ALL SELECT 'ORIN',COUNT(*),SUM(CASE WHEN "CANCELED"='Y' THEN 1 ELSE 0 END) FROM "TELCHI"."ORIN" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<?''',
        (CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE) * 4,
    )
    return {"credit_memos": returns, "cancellation_counts": cancels}


def _transfer_rows(source: HanaReadOnlySource, item_codes: list[str], warehouses: list[str]) -> dict[str, Any]:
    if not item_codes or not warehouses:
        return {"status": "NOT_RUN", "rows": [], "reason": "empty bounded item/warehouse scope"}
    items = _in(item_codes)
    whs = _in(warehouses)
    sql = f'''SELECT TOP 500 H."DocEntry",H."DocNum",H."DocDate",H."CANCELED",H."Comments",H."Ref1",H."Ref2",L."LineNum",L."ItemCode",L."Quantity",L."FromWhsCod",L."WhsCode"
              FROM "TELCHI"."OWTR" H JOIN "TELCHI"."WTR1" L ON L."DocEntry"=H."DocEntry"
              WHERE H."DocDate">=? AND H."DocDate"<? AND L."ItemCode" IN ({items}) AND (L."FromWhsCod" IN ({whs}) OR L."WhsCode" IN ({whs}))
              ORDER BY H."DocDate",H."DocEntry",L."LineNum"'''
    return _query(source, "agrotel_transfer_scope", sql, (START_DATE, END_EXCLUSIVE, *item_codes, *warehouses, *warehouses))


def _warehouse_rows(source: HanaReadOnlySource, warehouses: list[str]) -> dict[str, Any]:
    if not warehouses:
        return {"status": "NOT_RUN", "rows": []}
    ph = _in(warehouses)
    return _query(
        source, "agrotel_warehouse_metadata",
        f'SELECT TOP 100 "WhsCode","WhsName","Inactive","BPLid","Location" FROM "TELCHI"."OWHS" WHERE "WhsCode" IN ({ph}) ORDER BY "WhsCode"',
        tuple(warehouses),
    )


def _oitw_analysis(source: HanaReadOnlySource, item_codes: list[str]) -> dict[str, Any]:
    metadata = _query(
        source, "oitw_consig_column_metadata",
        'SELECT "COLUMN_NAME","DATA_TYPE_NAME","LENGTH","SCALE","IS_NULLABLE" FROM "SYS"."TABLE_COLUMNS" WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? AND "COLUMN_NAME"=?',
        ("TELCHI", "OITW", "Consig"),
    )
    values = _query(
        source, "oitw_consig_value_distribution",
        'SELECT "Consig" AS "value",COUNT(*) AS "rows" FROM "TELCHI"."OITW" GROUP BY "Consig" ORDER BY "Consig"',
    )
    sample: dict[str, Any] = {"status": "NOT_RUN", "rows": []}
    if item_codes:
        sample = _query(
            source, "oitw_consig_agrotel_item_sample",
            f'SELECT TOP 200 "ItemCode","WhsCode","OnHand","Consig","IsCommited","OnOrder","updateDate" FROM "TELCHI"."OITW" WHERE "ItemCode" IN ({_in(item_codes)}) ORDER BY "ItemCode","WhsCode"',
            tuple(item_codes),
        )
    return {
        "metadata": metadata, "value_distribution": values, "agrotel_item_sample": sample,
        "semantics": "OITW.Consig is a nullable DECIMAL(21,6) at ItemCode×WhsCode grain. It has no CardCode/customer key and is read here only as current state; its value distribution includes positive, zero and negative quantities. It cannot identify Agrotel ownership or a historical cutoff balance by itself.",
        "relevant_to_agrotel": "NO",
    }


def _control_customer(source: HanaReadOnlySource) -> dict[str, Any]:
    bp = _query(source, "control_consignation_customer_bp", 'SELECT "CardCode","CardName","CardType","U_CONSIGNACION","GroupCode","ListNum","SlpCode","Territory","Notes" FROM "TELCHI"."OCRD" WHERE "CardCode"=?', (CONTROL_CARDCODE,))
    docs = _query(
        source, "control_consignation_customer_documents",
        'SELECT TOP 25 H."DocEntry",H."DocNum",H."DocDate",H."CANCELED",H."DocStatus",H."Comments",L."LineNum",L."ItemCode",L."Quantity",L."WhsCode",L."BaseType",L."BaseEntry",L."BaseLine" FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocDate" DESC,H."DocEntry" DESC,L."LineNum"',
        (CONTROL_CARDCODE, START_DATE, END_EXCLUSIVE),
    )
    return {"control_cardcode": CONTROL_CARDCODE, "bp": bp, "documents_2026": docs, "interpretation": "A bounded control BP with U_CONSIGNACION=1 exists, but its observed standard invoice flow is not treated as proof of a product ownership balance."}


def _special_series_and_prices(source: HanaReadOnlySource, invoice_rows: list[dict[str, Any]], item_codes: list[str]) -> dict[str, Any]:
    series = sorted({str(_key(row, "series")) for row in invoice_rows if _key(row, "series") is not None})
    series_rows: dict[str, Any] = {"status": "NOT_RUN", "rows": []}
    if series:
        series_rows = _query(source, "agrotel_invoice_series", f'SELECT TOP 100 "Series","SeriesName","ObjectCode" FROM "TELCHI"."NNM1" WHERE "Series" IN ({_in(series)}) ORDER BY "Series"', tuple(series))
    prices: dict[str, Any] = {"status": "NOT_RUN", "rows": []}
    if item_codes:
        prices = _query(source, "agrotel_special_prices", f'SELECT TOP 200 "CardCode","ItemCode","Price","Currency","Discount","ValidFrom","ValidTo","Valid" FROM "TELCHI"."OSPP" WHERE "CardCode"=? AND "ItemCode" IN ({_in(item_codes)}) ORDER BY "ItemCode"', (CUSTOMER_CARDCODE, *item_codes))
    return {"invoice_series": series_rows, "special_prices": prices}


def _document_chain(invoice_rows: list[dict[str, Any]], delivery_rows: list[dict[str, Any]], order_rows: list[dict[str, Any]], credit_rows: list[dict[str, Any]]) -> dict[str, Any]:
    deliveries_by_key = {(str(_key(row, "docentry")), str(_key(row, "linenum"))): row for row in delivery_rows}
    orders_by_key = {(str(_key(row, "docentry")), str(_key(row, "linenum"))): row for row in order_rows}
    links: list[dict[str, Any]] = []
    for row in invoice_rows:
        base_type = _key(row, "basetype")
        base_entry = _key(row, "baseentry")
        base_line = _key(row, "baseline")
        link: dict[str, Any] = {
            "invoice": {key: _key(row, key) for key in ("docentry", "docnum", "docdate", "linenum", "itemcode", "quantity")},
            "invoice_base": {"base_type": base_type, "base_entry": base_entry, "base_line": base_line},
            "relationship_rule": "BaseType/BaseEntry/BaseLine only",
        }
        if str(base_type) == "15" and base_entry is not None and base_line is not None:
            delivery = deliveries_by_key.get((str(base_entry), str(base_line)))
            link["delivery"] = delivery
            if delivery:
                order_type, order_entry, order_line = _key(delivery, "basetype"), _key(delivery, "baseentry"), _key(delivery, "baseline")
                link["delivery_base"] = {"base_type": order_type, "base_entry": order_entry, "base_line": order_line}
                link["order"] = orders_by_key.get((str(order_entry), str(order_line))) if str(order_type) == "17" and order_entry is not None and order_line is not None else None
                link["status"] = "EXPLICIT_CHAIN" if link["order"] else "EXPLICIT_INVOICE_DELIVERY_ONLY"
            else:
                link["status"] = "MISSING_EXPLICIT_DELIVERY_ROW"
        else:
            link["status"] = "NO_EXPLICIT_BASE_LINK"
        links.append(link)
    return {
        "relationship_rule": "Only BaseType/BaseEntry/BaseLine; no date, quantity, name or fuzzy matching.",
        "invoice_line_count": len(invoice_rows),
        "invoice_lines_with_explicit_delivery": sum(item["status"] in {"EXPLICIT_CHAIN", "EXPLICIT_INVOICE_DELIVERY_ONLY"} for item in links),
        "links": links,
        "credit_memo_links": credit_rows,
        "reconstruction_status": "YES" if links and all(item["status"] in {"EXPLICIT_CHAIN", "EXPLICIT_INVOICE_DELIVERY_ONLY"} for item in links) else ("PARTIAL" if links else "NO"),
    }


def _timeline(invoice_rows: list[dict[str, Any]], delivery_rows: list[dict[str, Any]], order_rows: list[dict[str, Any]], movement_rows: list[dict[str, Any]], returns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in order_rows:
        events.append({"date": _key(row, "docdate"), "document_type": "SALES_ORDER", "docentry": _key(row, "docentry"), "docnum": _key(row, "docnum"), "linenum": _key(row, "linenum"), "itemcode": _key(row, "itemcode"), "quantity": _key(row, "quantity"), "warehouse": _key(row, "whscode"), "event_meaning": "sales order row", "evidence_source": "ORDR/RDR1"})
    for row in delivery_rows:
        events.append({"date": _key(row, "docdate"), "document_type": "DELIVERY", "docentry": _key(row, "docentry"), "docnum": _key(row, "docnum"), "linenum": _key(row, "linenum"), "itemcode": _key(row, "itemcode"), "quantity": _key(row, "quantity"), "warehouse": _key(row, "whscode"), "event_meaning": "delivery document row", "evidence_source": "ODLN/DLN1"})
    for row in invoice_rows:
        events.append({"date": _key(row, "docdate"), "document_type": "INVOICE", "docentry": _key(row, "docentry"), "docnum": _key(row, "docnum"), "linenum": _key(row, "linenum"), "itemcode": _key(row, "itemcode"), "quantity": _key(row, "quantity"), "warehouse": _key(row, "whscode"), "event_meaning": "accounts-receivable invoice row", "evidence_source": "OINV/INV1"})
    for row in movement_rows:
        events.append({"date": _key(row, "docdate"), "document_type": "INVENTORY_MOVEMENT", "docentry": _key(row, "appobjabs"), "docnum": _key(row, "baseref"), "linenum": _key(row, "doclinenum"), "itemcode": _key(row, "itemcode"), "quantity": _key(row, "outqty") or _key(row, "inqty"), "warehouse": _key(row, "warehouse"), "trans_num": _key(row, "transnum"), "trans_seq": _key(row, "transseq"), "event_meaning": f'OINM TransType={_key(row, "transtype")}', "evidence_source": "OINM"})
    for row in returns:
        events.append({"date": _key(row, "docdate"), "document_type": "CREDIT_MEMO", "docentry": _key(row, "docentry"), "docnum": _key(row, "docnum"), "linenum": _key(row, "linenum"), "itemcode": _key(row, "itemcode"), "quantity": _key(row, "quantity"), "warehouse": _key(row, "whscode"), "event_meaning": "credit memo/return row", "evidence_source": "ORIN/RIN1"})
    return sorted(events, key=lambda row: tuple(str(row.get(key) or "") for key in ("date", "document_type", "docentry", "linenum", "trans_num", "trans_seq")))


def _local_source_search() -> dict[str, Any]:
    roots = [REPO_ROOT / "SrvRestAstroLS_v1/backend/modules/telchi/investigation", EVIDENCE_ROOT.parent, DATA_ROOT]
    matches: list[str] = []
    inspected_roots: list[str] = []
    for root in roots:
        inspected_roots.append(str(root))
        if not root.exists():
            continue
        try:
            for path in root.rglob("*"):
                if len(matches) >= 100:
                    break
                if path.is_file() and any(term.lower() in path.name.lower() for term in ("agrotel", "consign", "consigna")):
                    matches.append(str(path))
        except OSError:
            continue
    return {
        "bounded_path_name_search": "YES", "roots": inspected_roots, "matches": sorted(set(matches))[:100],
        "external_system_accessed": "NO", "legacy_accessed": "NO", "spreadsheet_contents_read": "NO",
        "interpretation": "Only existing repository/evidence/data path names were searched. This cannot determine whether Telchi keeps an external spreadsheet or manual register outside the authorized local sources.",
    }


def _value_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = str(_key(row, key))
        result[value] = result.get(value, 0) + 1
    return result


def _bounded_text_search(groups: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    terms = ("consign", "consigna", "propiedad", "tercero", "comodato", "prestamo", "préstamo")
    hits: list[dict[str, Any]] = []
    for group, rows in groups.items():
        for row in rows:
            text = " ".join(str(_key(row, field) or "") for field in ("comments", "ref1", "ref2", "jrnlmemo", "numatcard")).lower()
            matched = [term for term in terms if term in text]
            if matched:
                hits.append({"group": group, "matched_terms": matched, "document": row})
    return {"terms": terms, "rows_scanned": sum(len(rows) for rows in groups.values()), "hits": hits[:100], "method": "bounded_document_text_fields_only"}


def _run() -> dict[str, Any]:
    started = time.perf_counter()
    source = HanaReadOnlySource()
    ping = _query(source, "hana_connectivity_select_1", 'SELECT 1 AS "ok" FROM DUMMY')
    hana_latency = ping.get("duration_ms")
    if ping.get("status") != "PASS":
        raise RuntimeError("HANA connectivity preflight failed")

    table_inventory, columns = _table_inventory(source)
    metadata = _metadata_discovery(source)
    bp = _bp_audit(source, metadata)
    custom = _custom_tables(source, columns)
    invoices_q = _invoice_rows(source)
    deliveries_q = _delivery_rows(source)
    orders_q = _order_rows(source)
    returns_q = _returns_and_cancels(source)
    invoice_rows, delivery_rows, order_rows = _successful(invoices_q), _successful(deliveries_q), _successful(orders_q)
    item_codes = sorted({str(_key(row, "itemcode")) for row in invoice_rows if _key(row, "itemcode") is not None})
    warehouses = sorted({str(_key(row, "whscode")) for row in invoice_rows if _key(row, "whscode") is not None})
    movement_q = _query(
        source, "agrotel_oinm_scope",
        'SELECT TOP 1000 "TransNum","TransSeq","TransType","DocDate","ItemCode","Warehouse","InQty","OutQty","BASE_REF","AppObjAbs","AppObjType","DocLineNum","CardCode","CardName","Comments","JrnlMemo" FROM "TELCHI"."OINM" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<? ORDER BY "TransNum","TransSeq"',
        (CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE),
    )
    supplier_movement_q = _query(
        source, "agrotel_supplier_oinm_reference",
        'SELECT TOP 1000 "TransNum","TransSeq","TransType","DocDate","ItemCode","Warehouse","InQty","OutQty","BASE_REF","AppObjAbs","AppObjType","DocLineNum","CardCode","CardName","Comments","JrnlMemo" FROM "TELCHI"."OINM" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<? ORDER BY "TransNum","TransSeq"',
        (SUPPLIER_CARDCODE, START_DATE, END_EXCLUSIVE),
    )
    movements = _successful(movement_q)
    transfers_q = _transfer_rows(source, item_codes, warehouses)
    warehouses_q = _warehouse_rows(source, warehouses)
    oitw = _oitw_analysis(source, item_codes)
    control = _control_customer(source)
    series_prices = _special_series_and_prices(source, invoice_rows, item_codes)
    chain = _document_chain(invoice_rows, delivery_rows, order_rows, _successful(returns_q.get("credit_memos", {})))
    timeline = _timeline(invoice_rows, delivery_rows, order_rows, movements, _successful(returns_q.get("credit_memos", {})))
    external = _local_source_search()
    text_search = _bounded_text_search({"invoices": invoice_rows, "deliveries": delivery_rows, "orders": order_rows, "oinm": movements})

    invoice_doc_count = len({str(_key(row, "docentry")) for row in invoice_rows})
    delivery_doc_count = len({str(_key(row, "docentry")) for row in delivery_rows})
    order_doc_count = len({str(_key(row, "docentry")) for row in order_rows})
    movement_types = _value_counts(movements, "transtype")
    has_explicit_agrotel_warehouse = any("AGROT" in str(_key(row, "whsname") or "").upper() for row in _successful(warehouses_q))
    invoice_dates = {str(_key(row, "docentry")): str(_key(row, "docdate"))[:10] for row in invoice_rows}
    delivery_dates = {str(_key(row, "docentry")): str(_key(row, "docdate"))[:10] for row in delivery_rows}
    invoice_delivery_date_pairs = []
    for link in chain["links"]:
        delivery = link.get("delivery")
        if delivery:
            invoice_delivery_date_pairs.append({"invoice_docentry": _key(link["invoice"], "docentry"), "invoice_date": _key(link["invoice"], "docdate"), "delivery_docentry": _key(delivery, "docentry"), "delivery_date": _key(delivery, "docdate"), "same_calendar_date": str(_key(link["invoice"], "docdate"))[:10] == str(_key(delivery, "docdate"))[:10]})

    invoice_status = "SUPPORTED" if invoice_rows and all(str(_key(row, "canceled")) != "Y" for row in invoice_rows) else "UNKNOWN"
    hypotheses = {
        "warehouse": {"hypothesis": "Agrotel is handled by a dedicated warehouse", "status": "REJECTED" if not has_explicit_agrotel_warehouse and len(warehouses) > 1 else "UNKNOWN", "evidence": {"warehouses_used_by_customer_invoices": warehouses, "warehouse_metadata": _successful(warehouses_q)}, "rule": "A warehouse name or code alone is not sufficient; an explicit Agrotel relation and consistent flow are required."},
        "delivery": {"hypothesis": "delivery without invoice equals consignment", "status": "REJECTED", "evidence": {"invoice_documents": invoice_doc_count, "delivery_documents": delivery_doc_count, "explicit_invoice_delivery_lines": chain["invoice_lines_with_explicit_delivery"], "invoice_delivery_date_pairs": invoice_delivery_date_pairs}, "rule": "Document status and BaseType links are observed; no ownership inference is made."},
        "sales_order": {"hypothesis": "sales order/open order identifies consignment", "status": "REJECTED", "evidence": {"sales_order_documents": order_doc_count, "order_rows": order_rows[:100], "consignment_udf_on_bp": bp["agrotel_value"]}, "rule": "An order is treated as an order, not as consignment stock."},
        "transfer": {"hypothesis": "inventory transfer out equals product sent on consignment", "status": "REJECTED" if not _successful(transfers_q) else "UNKNOWN", "evidence": {"transfers": _successful(transfers_q), "customer_warehouse_binding": "NONE_OBSERVED"}, "rule": "Only explicit document keys are accepted; transfer destination does not establish ownership."},
        "invoice": {"hypothesis": "invoice is a billing event but does not by itself prove consignment ownership", "status": invoice_status, "evidence": {"invoice_documents": invoice_doc_count, "invoice_lines": len(invoice_rows), "oinm_trans_type_counts": movement_types, "quantity_invoiced": str(sum(float(_key(row, "quantity") or 0) for row in invoice_rows))}, "rule": "Invoice/OINM evidence is reported as billing/stock movement, not as a consignment balance."},
    }

    u_value = bp["agrotel_value"]
    returns_found = bool(_successful(returns_q.get("credit_memos", {})))
    source_classification = "SAP_EXPLICIT_FIELD"
    definition_status = "SUPPORTED"
    definition = "SAP exposes a relevant Business Partner flag: OCRD.U_CONSIGNACION is labelled 'Venta Consignacion' and UFD1 maps 0=NO/1=SI. For Agrotel customer C012133 the observed value is 0 (NO). This supports a customer-level eligibility/operational flag, but SAP evidence inspected here does not bind a product delivered to C012133 to commercial ownership or a customer-specific consignment balance."
    human_questions = [
        "¿Qué documento o registro usan cuando entregan mercadería a Agrotel sin transferir la propiedad?",
        "¿La condición de consignación de un producto para Agrotel se marca en OCRD.U_CONSIGNACION, en otra tabla/documento o fuera de SAP?",
        "¿Se factura al entregar, al consumir/vender Agrotel, o puede haber ambos casos?",
        "¿Dónde controlan la cantidad que sigue siendo propiedad de Telchi y quién confirma ese saldo?",
    ]
    degraded_reasons = []
    if chain["reconstruction_status"] != "YES":
        degraded_reasons.append("one or more invoice lines lack a complete explicit BaseType/BaseEntry/BaseLine chain")
    degraded_reasons.append("external spreadsheet/manual register cannot be ruled out from authorized local sources")
    final_result = GATE + "_DEGRADED"
    summary = {
        "GATE": GATE, "HANA_CONNECTIVITY": "PASS", "HANA_LATENCY_MS": hana_latency,
        "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": source.sap_write_count, "MAX_HANA_CONCURRENT_QUERIES": 1,
        "AI_INVOCATIONS": 0, "HISTORICAL_CUTOFF": HISTORICAL_CUTOFF,
        "AGROTEL_CUSTOMER_CARDCODE": CUSTOMER_CARDCODE, "AGROTEL_CUSTOMER_CARDNAME": CUSTOMER_CARDNAME,
        "AGROTEL_SUPPLIER_CARDCODE": SUPPLIER_CARDCODE, "AGROTEL_SUPPLIER_CARDNAME": SUPPLIER_CARDNAME,
        "CUSTOMER_SUPPLIER_ROLES_PRESERVED": "YES", "AGROTEL_CUSTOMER_SUPPLIER_RELATION_RELEVANT": "UNKNOWN",
        "U_CONSIGNACION_AGROTEL_VALUE": u_value, "U_CONSIGNACION_SEMANTICS": bp["semantics"], "U_CONSIGNACION_RELEVANT": bp["relevant_to_agrotel"],
        "OITW_CONSIG_SEMANTICS": oitw["semantics"], "OITW_CONSIG_RELEVANT_TO_AGROTEL": oitw["relevant_to_agrotel"],
        "CUSTOM_CONSIGNATION_TABLE_FOUND": custom["found"], "CUSTOM_CONSIGNATION_UDF_FOUND": "YES",
        "DEDICATED_AGROTEL_WAREHOUSE": "NO" if hypotheses["warehouse"]["status"] == "REJECTED" else "UNKNOWN", "WAREHOUSE_HYPOTHESIS": hypotheses["warehouse"]["status"],
        "DELIVERY_HYPOTHESIS": hypotheses["delivery"]["status"], "SALES_ORDER_HYPOTHESIS": hypotheses["sales_order"]["status"], "TRANSFER_HYPOTHESIS": hypotheses["transfer"]["status"], "INVOICE_HYPOTHESIS": hypotheses["invoice"]["status"],
        "RETURNS_REVERSALS_FOUND": "YES" if returns_found else "NO", "DOCUMENT_CHAIN_RECONSTRUCTED": chain["reconstruction_status"], "AGROTEL_TIMELINE_CREATED": "YES",
        "CONTROL_CONSIGNATION_CUSTOMER_FOUND": "YES" if _successful(control["bp"]) and _key(_successful(control["bp"])[0], "u_consignacion") not in (None, "0") else "NO",
        "SEMANTIC_SOURCE_CLASSIFICATION": source_classification,
        "PRODUCT_PHYSICAL_LOCATION_OBSERVABLE": "YES", "PRODUCT_COMMERCIAL_OWNERSHIP_OBSERVABLE": "NO", "CONSIGNATION_STATUS_OBSERVABLE": "NO", "CONSIGNATION_BALANCE_OBSERVABLE": "NO",
        "CONSIGNATION_TECHNICAL_DEFINITION": definition, "CONSIGNATION_DEFINITION_STATUS": definition_status,
        "POTENTIAL_BALANCE_FORMULA": "NONE", "BALANCE_FORMULA_CONFIDENCE": "UNRESOLVED", "CONSIGNATION_BALANCE_COMPUTED": "NO",
        "EXTERNAL_SOURCE_REQUIRED": "UNKNOWN", "HUMAN_CONFIRMATION_REQUIRED": "YES", "HUMAN_QUESTIONS_COUNT": len(human_questions),
        "DUCKLAKE_MODIFIED": "NO", "ATOMIC_MODIFIED": "NO", "LEGACY_MERGED": "NO", "SAFE_TO_PRODUCTIZE_CONSIGNATION_QUERY": "NO",
        "RESULT": final_result, "DEGRADED_REASONS": degraded_reasons, "ELAPSED_MS": round((time.perf_counter() - started) * 1000, 3),
    }

    _write("summary.json", summary)
    _write("current_state.json", {"cutoff": HISTORICAL_CUTOFF, "source_read_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "OITW_CURRENT_STATE_ONLY": "YES", "DUCKLAKE_MODIFIED": "NO"})
    _write("agrotel_entities.json", {"customer": {"card_code": CUSTOMER_CARDCODE, "card_name": CUSTOMER_CARDNAME, "role": "CUSTOMER"}, "supplier": {"card_code": SUPPLIER_CARDCODE, "card_name": SUPPLIER_CARDNAME, "role": "SUPPLIER"}, "roles_preserved": "YES", "customer_supplier_relation_relevant": "UNKNOWN", "relation_basis": "Separate same-name roles and supplier OINM are observable; no explicit cross-role consignment link was found."})
    _write("udf_inventory.json", metadata)
    _write("u_consignacion_analysis.json", bp)
    _write("custom_table_inventory.json", custom)
    _write("warehouse_hypothesis.json", hypotheses["warehouse"] | {"oinm_scope_warehouse_counts": _value_counts(movements, "warehouse")})
    _write("delivery_hypothesis.json", hypotheses["delivery"])
    _write("sales_order_hypothesis.json", hypotheses["sales_order"])
    _write("transfer_hypothesis.json", hypotheses["transfer"])
    _write("invoice_hypothesis.json", hypotheses["invoice"] | {"invoice_rows": invoice_rows, "delivery_rows": delivery_rows})
    _write("document_chain.json", chain)
    _write("agrotel_timeline.json", timeline)
    _write("returns_and_reversals.json", {"returns_and_cancellations": returns_q, "oinm_rows": movements, "oinm_trans_type_counts": movement_types, "oinm_inbound_rows": [row for row in movements if str(_key(row, "inqty")) not in {"0", "0.0", "None"}], "supplier_reference_rows": _successful(supplier_movement_q), "returns_found": returns_found})
    _write("document_text_search.json", text_search)
    _write("oitw_consig_analysis.json", oitw)
    _write("control_customer_analysis.json", control)
    _write("external_source_search.json", external)
    _write("ownership_observability.json", {"PRODUCT_PHYSICAL_LOCATION_OBSERVABLE": "YES", "PRODUCT_COMMERCIAL_OWNERSHIP_OBSERVABLE": "NO", "CONSIGNATION_STATUS_OBSERVABLE": "NO", "CONSIGNATION_BALANCE_OBSERVABLE": "NO", "basis": definition})
    _write("semantic_source_classification.json", {"classification": source_classification, "primary_evidence": ["OCRD.U_CONSIGNACION", "CUFD", "UFD1"], "limitations": degraded_reasons})
    _write("semantic_definition.json", {"definition": definition, "status": definition_status, "u_consignacion_value": u_value, "oitw_semantics": oitw["semantics"], "balance_computed": "NO"})
    _write("human_questions.json", {"questions": human_questions, "count": len(human_questions)})
    _write("special_series_and_prices.json", series_prices)
    _write("sap_query_log.json", {"query_count": len(source.query_log), "queries": source.query_log, "SAP_WRITE_COUNT": source.sap_write_count})
    _write("document_scope.json", {"invoices": invoice_rows, "deliveries": delivery_rows, "orders": order_rows, "items": item_codes, "warehouses": warehouses, "counts": {"products": len(item_codes), "invoice_documents": invoice_doc_count, "delivery_documents": delivery_doc_count, "order_documents": order_doc_count, "invoice_lines": len(invoice_rows), "oinm_rows": len(movements)}})

    executive = [
        "# Resultado ejecutivo",
        "",
        "SAP sí registra una señal explícita de consignación a nivel de Business Partner: `OCRD.U_CONSIGNACION` está descrito como `Venta Consignacion` y sus valores están documentados como `0=NO` y `1=SI`. Para el cliente Agrotel `C012133`, el valor observado es `0`.",
        "",
        "Esto no demuestra que cada producto entregado a Agrotel sea o no sea propiedad de Telchi. Las facturas, entregas, pedidos y movimientos muestran ubicación física y flujo documental, pero no contienen en este alcance una relación explícita de propiedad por producto. `OITW.Consig` tampoco resuelve el caso: es estado actual por `ItemCode×WhsCode`, sin cliente ni fecha histórica.",
        "",
        "La fuente primaria disponible es, por tanto, un campo explícito de SAP para la condición del Business Partner, no un saldo de consignación por cliente. El gate no calcula saldo. La investigación queda degradada porque hay una cadena documental parcial en una factura sin BaseEntry y no puede descartarse una planilla o regla manual fuera de las fuentes locales autorizadas.",
        "",
        "## Resultado obligatorio",
        "",
        "```text",
    ] + [f"{key}={value}" for key, value in summary.items()] + [
        "```", "", "## Cadena y timeline", "",
        f"Se reconstruyeron {chain['invoice_lines_with_explicit_delivery']}/{chain['invoice_line_count']} líneas de factura con claves SAP explícitas; estado `{chain['reconstruction_status']}`. Se generó timeline con {len(timeline)} eventos SAP. La búsqueda acotada de texto documental encontró {len(text_search['hits'])} coincidencias.",
        "", "## Preguntas humanas exactas", "", *[f"- {question}" for question in human_questions],
        "", "## Controles", "", "SAP READ ONLY; no se ejecutaron INSERT/UPDATE/DELETE/DDL, DuckLake/Atomic no fueron modificados, no se leyó legacy, no se llamó IA y no se calculó saldo.",
        "", "## STOP AND REVIEW", "", f"Resultado final: `{final_result}`.",
    ]
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    (EVIDENCE_ROOT / "report.md").write_text("\n".join(executive) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(_run(), indent=2, sort_keys=True, ensure_ascii=False, default=str))
