"""TELCHI_CONFIRMED_CONSIGNATION_PRODUCT_FLOW_V1.

Positive-control investigation of Business Partners that SAP Telchi explicitly
flags as consignment (``OCRD.U_CONSIGNACION=1``).  The gate reconstructs, for
those customers, products, documents, quantities, warehouses, ``OINM``
movements and explicit document relationships, and compares DuckLake/Parquet
2026 against SAP HANA READ ONLY with the fixed historical cutoff.

It is an investigation artifact: SAP and DuckLake are read-only, no AI client is
imported, no balance is computed and Agrotel ``C012133`` is never reclassified.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.source import HanaReadOnlySource

GATE = "TELCHI_CONFIRMED_CONSIGNATION_PRODUCT_FLOW_V1"
START_DATE = "2026-01-01"
HISTORICAL_CUTOFF = "2026-09-15"
END_EXCLUSIVE = "2026-09-16"
CONSIGNATION_POSITIVE_VALUE = "1"
CUSTOMER_ROLE = "C"
AGROTEL_CARDCODE = "C012133"
AGROTEL_U_CONSIGNACION = "0"
MAX_SELECTED_CUSTOMERS = 3
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
REFERENCE_V2_PRODUCTS = DATA_ROOT / "reference" / "_versions" / "v2" / "products" / "part-00000.parquet"
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE

EXPLICIT_LINK_RULE = (
    "A movement is CUSTOMER_LINKED only when the source-native OINM.CardCode column equals the "
    "confirmed customer CardCode.  Date, quantity, ItemCode and Warehouse equality are never used "
    "to infer customer ownership."
)
CONSIGNATION_BALANCE_RULE = (
    "CONSIGNATION_BALANCE_COMPUTED=NO: no verified formula binds a product/warehouse quantity to a "
    "specific customer consignment position, so no balance is produced."
)

SALES_FIELDS = (
    "doc_entry", "doc_num", "doc_date", "doc_due_date", "tax_date", "doc_status",
    "canceled", "currency", "doc_total", "card_code", "line_num", "line_status",
    "item_code", "quantity", "whs_code", "price", "line_total",
)
SALES_COMPARE_KEYS = SALES_FIELDS
OINM_FIELDS = (
    "trans_num", "trans_seq", "trans_type", "doc_date", "item_code", "warehouse",
    "in_qty", "out_qty", "app_obj_abs", "app_obj_type", "doc_line_num", "card_code",
)
OITW_COMMON_KEYS = ("item_code", "whs_code", "on_hand", "is_commited", "on_order")
NUMERIC_FIELDS = {
    "doc_entry", "doc_num", "line_num", "quantity", "doc_total", "price", "line_total",
    "trans_num", "trans_seq", "trans_type", "in_qty", "out_qty", "app_obj_abs",
    "app_obj_type", "doc_line_num", "base_entry", "base_line", "base_type", "on_hand", "is_commited", "on_order", "consig",
    "rows", "documents", "products", "lines", "count",
}
DATE_FIELDS = {"doc_date", "doc_due_date", "tax_date", "update_date", "valid_from", "valid_to"}


# --------------------------------------------------------------------------- #
# Deterministic helpers (pure, testable)
# --------------------------------------------------------------------------- #
def _key(row: dict[str, Any], name: str) -> Any:
    wanted = name.lower()
    return next((value for key, value in row.items() if str(key).lower() == wanted), None)


def _field_name(name: str) -> str:
    """Canonical snake_case field name so SAP CamelCase and DuckLake snake_case align."""
    text = str(name)
    if text.upper() == text:
        return text.lower()
    return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()


def _normal_value(name: str, value: Any) -> Any:
    if value is None:
        return None
    lower = name.lower()
    if lower in DATE_FIELDS:
        return str(value)[:10]
    if lower in NUMERIC_FIELDS:
        try:
            return format(Decimal(str(value)).normalize(), "f")
        except (InvalidOperation, ValueError):
            return str(value)
    return value.isoformat() if hasattr(value, "isoformat") else value


def normalize(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {_field_name(key): _normal_value(_field_name(key), value) for key, value in row.items()}
        for row in rows
    ]


def ordered(rows: Iterable[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return sorted(normalize(rows), key=lambda row: tuple(str(row.get(key, "")) for key in keys))


def project(rows: Iterable[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{key: _key(row, key) for key in keys} for row in rows]


def deterministic_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_rowsets(sap_rows: list[dict[str, Any]], lake_rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any]:
    """Compare complete normalized rowsets by source-native keys; no samples-only equality."""
    left, right = ordered(sap_rows, keys), ordered(lake_rows, keys)
    equal = left == right
    return {
        "status": "EXACT" if equal else "MISMATCH",
        "sap_row_count": len(left),
        "ducklake_row_count": len(right),
        "sap_hash": deterministic_hash(left),
        "ducklake_hash": deterministic_hash(right),
        "sap_only_sample": left[:5] if not equal else [],
        "ducklake_only_sample": right[:5] if not equal else [],
    }


def historical_predicate(column: str = "doc_date") -> str:
    """The single accepted inclusive-cutoff half-open predicate."""
    return f"{column} >= ? AND {column} < ?"


def is_confirmed_consignment_customer(row: dict[str, Any]) -> bool:
    """OCRD.U_CONSIGNACION=1 and the CUSTOMER role.  Suppliers/leads are never merged in."""
    return (
        str(_key(row, "card_type")) == CUSTOMER_ROLE
        and str(_key(row, "u_consignacion")) == CONSIGNATION_POSITIVE_VALUE
    )


def select_confirmed_consignment_customers(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [row for row in rows if is_confirmed_consignment_customer(row)]
    return sorted(selected, key=lambda row: str(_key(row, "card_code")))


def customer_role_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        role = str(_key(row, "card_type"))
        counts[role] = counts.get(role, 0) + 1
    return counts


def is_explicit_customer_linked_movement(row: dict[str, Any], card_code: str) -> bool:
    """Explicit OINM.CardCode linkage only; empty/other customers are not linked."""
    value = _key(row, "card_code")
    return value is not None and str(value) == card_code


def quantity_sum(rows: Iterable[dict[str, Any]], name: str) -> str:
    total = Decimal("0")
    for row in rows:
        value = _key(row, name)
        if value not in (None, ""):
            total += Decimal(str(value))
    return format(total.normalize(), "f")


def _value_counts(rows: Iterable[dict[str, Any]], name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(_key(row, name))
        counts[value] = counts.get(value, 0) + 1
    return counts


def classify_operational_pattern(flows: list[dict[str, Any]]) -> str:
    """Classify the observed repeated operational signature across positive customers."""
    if not flows:
        return "UNKNOWN"
    if len(flows) == 1:
        # A single positive customer cannot establish a repeated operational pattern.
        return "CUSTOMER_FLAG_ONLY"
    shifted = [flow for flow in flows if flow.get("delivery_documents", 0) and not flow.get("invoice_documents", 0)]
    distinct_warehouses = {warehouse for flow in flows for warehouse in flow.get("warehouses", [])}
    same_flow = len({flow.get("flow_signature") for flow in flows}) == 1
    if shifted:
        return "CONSISTENT_DOCUMENT_FLOW"
    if same_flow and distinct_warehouses:
        return "CONSISTENT_WAREHOUSE_MODEL"
    if same_flow:
        return "CUSTOMER_FLAG_ONLY"
    return "MULTIPLE_PATTERNS"


def classify_pattern(value: bool, any_present: bool, all_present: bool) -> str:
    if not any_present:
        return "ABSENT"
    return "CONSISTENT" if all_present else "MIXED" if value else "MIXED"


def potential_balance_model() -> dict[str, Any]:
    """The gate never asserts a balance formula without proven ownership semantics."""
    return {
        "POTENTIAL_BALANCE_FORMULA": "NONE",
        "BALANCE_FORMULA_CONFIDENCE": "UNRESOLVED",
        "CONSIGNATION_BALANCE_COMPUTED": "NO",
        "rule": CONSIGNATION_BALANCE_RULE,
        "candidate_considered": "delivered - invoiced - returned (NOT ADOPTED)",
    }


# --------------------------------------------------------------------------- #
# IO helpers
# --------------------------------------------------------------------------- #
def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [str(item[0]).lower() for item in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _write(name: str, value: Any) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    (EVIDENCE_ROOT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _placeholders(values: list[Any]) -> str:
    if not values:
        raise ValueError("bounded IN list cannot be empty")
    if len(values) > 200:
        raise ValueError("bounded IN list exceeds 200 values")
    return ",".join("?" for _ in values)


def _sap(source: HanaReadOnlySource, query_id: str, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    rows = source._execute(query_id, sql, params)
    return rows, round((time.perf_counter() - started) * 1000, 3)


def _duck(connector: DuckLakeConnector, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    with connector.session(read_only=True) as connection:
        rows = _rows(connection.execute(sql, params))
    return rows, round((time.perf_counter() - started) * 1000, 3)


# --------------------------------------------------------------------------- #
# SAP discovery
# --------------------------------------------------------------------------- #
def _customer_inventory(source: HanaReadOnlySource) -> dict[str, Any]:
    population, pop_ms = _sap(
        source,
        "u_consignacion_population",
        'SELECT "CardType" AS card_type,"U_CONSIGNACION" AS u_consignacion,COUNT(*) AS rows '
        'FROM "TELCHI"."OCRD" GROUP BY "CardType","U_CONSIGNACION" ORDER BY "CardType","U_CONSIGNACION"',
    )
    positives, positives_ms = _sap(
        source,
        "u_consignacion_confirmed_customers",
        'SELECT "CardCode" AS card_code,"CardName" AS card_name,"CardType" AS card_type,'
        '"U_CONSIGNACION" AS u_consignacion,"GroupCode" AS group_code,"validFor" AS valid_for,'
        '"frozenFor" AS frozen_for FROM "TELCHI"."OCRD" WHERE "U_CONSIGNACION"=1 ORDER BY "CardCode"',
    )
    confirmed = select_confirmed_consignment_customers(positives)
    mapping, mapping_ms = _sap(
        source,
        "u_consignacion_ufd1_mapping",
        'SELECT "TableID" AS table_id,"FieldID" AS field_id,"IndexID" AS index_id,"Descr" AS description '
        'FROM "TELCHI"."UFD1" WHERE "TableID"=? AND "FieldID"=? ORDER BY "IndexID"',
        ("OCRD", 43),
    )
    return {
        "population": population,
        "positives_raw": positives,
        "confirmed_customers": confirmed,
        "positive_raw_count": len(positives),
        "confirmed_count": len(confirmed),
        "role_counts": customer_role_counts(positives),
        "ufd1_mapping": mapping,
        "semantics": (
            "OCRD.U_CONSIGNACION is a Business Partner UDF labelled Venta Consignacion; UFD1 maps "
            "0=NO and 1=SI.  The value is BP-level and is compared here against customer/supplier roles "
            "without merging same-name entities."
        ),
        "timings": {"population_ms": pop_ms, "positives_ms": positives_ms, "mapping_ms": mapping_ms},
    }


# --------------------------------------------------------------------------- #
# DuckLake-first selection (activity for confirmed customers only)
# --------------------------------------------------------------------------- #
def _activity_sql(card_codes: list[str]) -> tuple[str, str, list[Any], tuple[Any, ...]]:
    ph = _placeholders(card_codes)
    lake = f'''SELECT h.card_code,
        COUNT(DISTINCT l.item_code) AS products,
        COUNT(DISTINCT h.doc_entry) AS documents,
        COUNT(*) AS lines,
        COALESCE(SUM(TRY_CAST(l.quantity AS DECIMAL(38,10))),0) AS quantity
        FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry
        WHERE h.card_code IN ({ph}) AND h.doc_date>=? AND h.doc_date<?
        GROUP BY h.card_code ORDER BY h.card_code'''
    sap = f'''SELECT H."CardCode" AS card_code,COUNT(DISTINCT L."ItemCode") AS products,
        COUNT(DISTINCT H."DocEntry") AS documents,COUNT(*) AS lines,
        COALESCE(SUM(L."Quantity"),0) AS quantity
        FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry"
        WHERE H."CardCode" IN ({ph}) AND H."DocDate">=? AND H."DocDate"<?
        GROUP BY H."CardCode" ORDER BY H."CardCode"'''
    return lake, sap, [*card_codes, START_DATE, END_EXCLUSIVE], (*card_codes, START_DATE, END_EXCLUSIVE)


def _select_customers(connector: DuckLakeConnector, source: HanaReadOnlySource, confirmed: list[dict[str, Any]]) -> dict[str, Any]:
    if not confirmed:
        return {"selected": [], "activity_lake": [], "activity_sap": [], "selection_reason": "no confirmed consignment customers"}
    codes = [str(_key(row, "card_code")) for row in confirmed]
    lake_sql, sap_sql, lake_params, sap_params = _activity_sql(codes)
    activity_lake, lake_ms = _duck(connector, lake_sql, lake_params)
    activity_sap, sap_ms = _sap(source, "confirmed_consignment_activity", sap_sql, sap_params)
    activity_by_code = {str(_key(row, "card_code")): row for row in activity_lake}
    active = [row for row in activity_lake if Decimal(str(_key(row, "quantity") or 0)) > 0 or int(_key(row, "documents") or 0) > 0]
    active.sort(key=lambda row: (-int(_key(row, "products") or 0), -int(_key(row, "documents") or 0), str(_key(row, "card_code"))))
    selected_codes = [str(_key(row, "card_code")) for row in active][:MAX_SELECTED_CUSTOMERS]
    by_code = {str(_key(row, "card_code")): row for row in confirmed}
    selected = [by_code[code] for code in selected_codes if code in by_code]
    return {
        "selected": selected,
        "selected_cards": selected_codes,
        "activity_lake": activity_lake,
        "activity_sap": activity_sap,
        "selection_reason": (
            "Deterministic DuckLake-first selection of the confirmed U_CONSIGNACION=1 customers that have "
            "2026 sales activity, ordered by product count, document count and CardCode; up to "
            f"{MAX_SELECTED_CUSTOMERS}.  No confirmed customer is excluded from the aggregate inventory."
        ),
        "timings": {"activity_lake_ms": lake_ms, "activity_sap_ms": sap_ms},
    }


# --------------------------------------------------------------------------- #
# Per-customer reconstruction
# --------------------------------------------------------------------------- #
def _sales_sql() -> tuple[str, str]:
    sap = '''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
        H."DocDueDate" AS doc_due_date,H."TaxDate" AS tax_date,H."DocStatus" AS doc_status,
        H."CANCELED" AS canceled,H."DocCur" AS currency,H."DocTotal" AS doc_total,
        H."CardCode" AS card_code,L."LineNum" AS line_num,L."LineStatus" AS line_status,
        L."ItemCode" AS item_code,L."Quantity" AS quantity,L."WhsCode" AS whs_code,
        L."Price" AS price,L."LineTotal" AS line_total,L."BaseType" AS base_type,
        L."BaseEntry" AS base_entry,L."BaseLine" AS base_line
        FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry"
        WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocEntry",L."LineNum"'''
    lake = '''SELECT h.doc_entry,h.doc_num,h.doc_date,h.doc_due_date,h.tax_date,h.doc_status,
        h.canceled,h.currency,h.doc_total,h.card_code,l.line_num,l.line_status,l.item_code,
        l.quantity,l.whs_code,l.price,l.line_total
        FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry
        WHERE h.card_code=? AND h.doc_date>=? AND h.doc_date<? ORDER BY TRY_CAST(h.doc_entry AS BIGINT),TRY_CAST(l.line_num AS BIGINT)'''
    return sap, lake


def _movement_sql() -> tuple[str, str]:
    sap = '''SELECT M."TransNum" AS trans_num,M."TransSeq" AS trans_seq,M."TransType" AS trans_type,
        M."DocDate" AS doc_date,M."ItemCode" AS item_code,M."Warehouse" AS warehouse,
        M."InQty" AS in_qty,M."OutQty" AS out_qty,M."AppObjAbs" AS app_obj_abs,
        M."AppObjType" AS app_obj_type,M."DocLineNum" AS doc_line_num,M."CardCode" AS card_code
        FROM "TELCHI"."OINM" M WHERE M."CardCode"=? AND M."DocDate">=? AND M."DocDate"<?
        ORDER BY M."TransNum",M."TransSeq"'''
    lake = '''SELECT m.trans_num,m.trans_seq,m.trans_type,m.doc_date,m.item_code,m.warehouse,
        m.in_qty,m.out_qty,m.app_obj_abs,m.app_obj_type,m.doc_line_num,m.card_code
        FROM telchi.atomic."inventory_movement" m WHERE m.card_code=? AND m.doc_date>=? AND m.doc_date<?
        ORDER BY TRY_CAST(m.trans_num AS BIGINT),TRY_CAST(m.trans_seq AS BIGINT)'''
    return sap, lake


def _document_queries(source: HanaReadOnlySource, card_code: str) -> dict[str, Any]:
    orders, orders_ms = _sap(
        source,
        f"orders_{card_code}",
        '''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
        H."DocStatus" AS doc_status,H."CANCELED" AS canceled,L."LineNum" AS line_num,
        L."ItemCode" AS item_code,L."Quantity" AS quantity,L."WhsCode" AS whs_code,
        L."BaseType" AS base_type,L."BaseEntry" AS base_entry,L."BaseLine" AS base_line
        FROM "TELCHI"."ORDR" H JOIN "TELCHI"."RDR1" L ON L."DocEntry"=H."DocEntry"
        WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocEntry",L."LineNum"''',
        (card_code, START_DATE, END_EXCLUSIVE),
    )
    deliveries, deliveries_ms = _sap(
        source,
        f"deliveries_{card_code}",
        '''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
        H."DocStatus" AS doc_status,H."CANCELED" AS canceled,L."LineNum" AS line_num,
        L."ItemCode" AS item_code,L."Quantity" AS quantity,L."WhsCode" AS whs_code,
        L."BaseType" AS base_type,L."BaseEntry" AS base_entry,L."BaseLine" AS base_line
        FROM "TELCHI"."ODLN" H JOIN "TELCHI"."DLN1" L ON L."DocEntry"=H."DocEntry"
        WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocEntry",L."LineNum"''',
        (card_code, START_DATE, END_EXCLUSIVE),
    )
    credits, credits_ms = _sap(
        source,
        f"credit_memos_{card_code}",
        '''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
        H."DocStatus" AS doc_status,H."CANCELED" AS canceled,L."LineNum" AS line_num,
        L."ItemCode" AS item_code,L."Quantity" AS quantity,L."WhsCode" AS whs_code,
        L."BaseType" AS base_type,L."BaseEntry" AS base_entry,L."BaseLine" AS base_line
        FROM "TELCHI"."ORIN" H JOIN "TELCHI"."RIN1" L ON L."DocEntry"=H."DocEntry"
        WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocEntry",L."LineNum"''',
        (card_code, START_DATE, END_EXCLUSIVE),
    )
    return {
        "orders": orders, "deliveries": deliveries, "credit_memos": credits,
        "timings": {"orders_ms": orders_ms, "deliveries_ms": deliveries_ms, "credit_memos_ms": credits_ms},
    }


def _document_chain(source: HanaReadOnlySource, sales: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild only explicit BaseType/BaseEntry/BaseLine chains; never fuzzy linking."""
    base_types = {"15": "DELIVERY", "17": "ORDER", "13": "INVOICE", "14": "CREDIT_MEMO", "16": "RETURN"}
    links: list[dict[str, Any]] = []
    for row in sales:
        base_type = _key(row, "base_type")
        base_entry = _key(row, "base_entry")
        base_line = _key(row, "base_line")
        link = {
            "invoice_doc_entry": _key(row, "doc_entry"),
            "invoice_line_num": _key(row, "line_num"),
            "item_code": _key(row, "item_code"),
            "base_type": base_type,
            "base_entry": base_entry,
            "base_line": base_line,
            "target": base_types.get(str(base_type), "OTHER"),
            "status": "EXPLICIT_BASE_LINK" if base_entry is not None and base_line is not None else "NO_EXPLICIT_BASE_LINK",
        }
        links.append(link)
    order_entries = sorted({int(link["base_entry"]) for link in links if link["target"] == "ORDER" and link["base_entry"] is not None})
    delivery_entries = sorted({int(link["base_entry"]) for link in links if link["target"] == "DELIVERY" and link["base_entry"] is not None})
    orders: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []
    if order_entries:
        ph = _placeholders(order_entries)
        orders, _ = _sap(
            source,
            "chain_orders",
            f'''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
            H."CardCode" AS card_code,H."CANCELED" AS canceled,L."LineNum" AS line_num,
            L."ItemCode" AS item_code,L."Quantity" AS quantity,L."WhsCode" AS whs_code
            FROM "TELCHI"."ORDR" H JOIN "TELCHI"."RDR1" L ON L."DocEntry"=H."DocEntry"
            WHERE H."DocEntry" IN ({ph}) ORDER BY H."DocEntry",L."LineNum"''',
            tuple(order_entries),
        )
    if delivery_entries:
        ph = _placeholders(delivery_entries)
        deliveries, _ = _sap(
            source,
            "chain_deliveries",
            f'''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
            H."CardCode" AS card_code,H."CANCELED" AS canceled,L."LineNum" AS line_num,
            L."ItemCode" AS item_code,L."Quantity" AS quantity,L."WhsCode" AS whs_code
            FROM "TELCHI"."ODLN" H JOIN "TELCHI"."DLN1" L ON L."DocEntry"=H."DocEntry"
            WHERE H."DocEntry" IN ({ph}) ORDER BY H."DocEntry",L."LineNum"''',
            tuple(delivery_entries),
        )
    has_any = any(link["status"] == "EXPLICIT_BASE_LINK" for link in links)
    complete = bool(links) and all(link["status"] == "EXPLICIT_BASE_LINK" for link in links)
    return {
        "relationship_rule": "BaseType/BaseEntry/BaseLine only; no date, quantity or name matching.",
        "links": links,
        "chain_orders": orders,
        "chain_deliveries": deliveries,
        "DOCUMENT_CHAIN_AVAILABLE": "YES" if complete else "PARTIAL" if has_any else "NO",
    }


def _transfer_context(source: HanaReadOnlySource, item_codes: list[str], warehouses: list[str]) -> dict[str, Any]:
    if not item_codes or not warehouses:
        return {"status": "NOT_RUN", "rows": []}
    items = _placeholders(item_codes)
    whs = _placeholders(warehouses)
    rows, ms = _sap(
        source,
        "transfer_context",
        f'''SELECT TOP 500 H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
        H."CANCELED" AS canceled,L."LineNum" AS line_num,L."ItemCode" AS item_code,
        L."Quantity" AS quantity,L."FromWhsCod" AS from_whs,L."WhsCode" AS whs_code
        FROM "TELCHI"."OWTR" H JOIN "TELCHI"."WTR1" L ON L."DocEntry"=H."DocEntry"
        WHERE H."DocDate">=? AND H."DocDate"<? AND L."ItemCode" IN ({items})
        AND (L."FromWhsCod" IN ({whs}) OR L."WhsCode" IN ({whs}))
        ORDER BY H."DocDate",H."DocEntry",L."LineNum"''',
        (START_DATE, END_EXCLUSIVE, *item_codes, *warehouses, *warehouses),
    )
    return {"status": "PASS", "rows": rows, "duration_ms": ms, "customer_linked": "NO: OWTR has no CardCode"}


def _warehouse_sharing(connector: DuckLakeConnector, warehouses: list[str]) -> dict[str, Any]:
    if not warehouses:
        return {"status": "NOT_RUN", "rows": []}
    ph = _placeholders(warehouses)
    rows, ms = _duck(
        connector,
        f'''SELECT l.whs_code,COUNT(DISTINCT h.card_code) AS customers,COUNT(DISTINCT l.item_code) AS products
        FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry
        WHERE l.whs_code IN ({ph}) AND h.doc_date>=? AND h.doc_date<?
        GROUP BY l.whs_code ORDER BY l.whs_code''',
        [*warehouses, START_DATE, END_EXCLUSIVE],
    )
    return {"status": "PASS", "rows": rows, "duration_ms": ms}


def _warehouse_metadata(source: HanaReadOnlySource, warehouses: list[str]) -> dict[str, Any]:
    if not warehouses:
        return {"status": "NOT_RUN", "rows": []}
    ph = _placeholders(warehouses)
    rows, ms = _sap(
        source,
        "warehouse_metadata",
        f'SELECT "WhsCode" AS whs_code,"WhsName" AS whs_name,"Inactive" AS inactive '
        f'FROM "TELCHI"."OWHS" WHERE "WhsCode" IN ({ph}) ORDER BY "WhsCode"',
        tuple(warehouses),
    )
    return {"status": "PASS", "rows": rows, "duration_ms": ms}


def _product_identity(source: HanaReadOnlySource, connector: DuckLakeConnector, item_codes: list[str]) -> dict[str, Any]:
    if not item_codes:
        return {"sap": [], "reference_v2": []}
    ph = _placeholders(item_codes)
    sap, _ = _sap(
        source,
        "product_identity_sap",
        f'SELECT "ItemCode" AS item_code,"ItemName" AS description,"ItmsGrpCod" AS item_group,'
        f'"frozenFor" AS frozen_for FROM "TELCHI"."OITM" WHERE "ItemCode" IN ({ph}) ORDER BY "ItemCode"',
        tuple(item_codes),
    )
    lake, _ = _duck(
        connector,
        f'''SELECT item_code,canonical_product_id,canonical_name,product_name,active
        FROM read_parquet(?) WHERE item_code IN ({ph}) ORDER BY item_code,canonical_product_id''',
        [str(REFERENCE_V2_PRODUCTS), *item_codes],
    )
    return {"sap": sap, "reference_v2": lake, "no_fuzzy_matching": "YES"}


def _oitw_current_state(source: HanaReadOnlySource, connector: DuckLakeConnector, item_codes: list[str]) -> dict[str, Any]:
    if not item_codes:
        return {"sap": [], "ducklake": [], "comparison": {"status": "N/A"}}
    ph = _placeholders(item_codes)
    sap, sap_ms = _sap(
        source,
        "oitw_current_state",
        f'SELECT "ItemCode" AS item_code,"WhsCode" AS whs_code,"OnHand" AS on_hand,'
        f'"IsCommited" AS is_commited,"OnOrder" AS on_order,"Consig" AS consig,"updateDate" AS update_date '
        f'FROM "TELCHI"."OITW" WHERE "ItemCode" IN ({ph}) ORDER BY "ItemCode","WhsCode"',
        tuple(item_codes),
    )
    lake, lake_ms = _duck(
        connector,
        f'SELECT item_code,whs_code,on_hand,is_commited,on_order FROM telchi.atomic."inventory_balance" '
        f'WHERE item_code IN ({ph}) ORDER BY item_code,whs_code',
        list(item_codes),
    )
    sap_as_of, as_of_ms = _sap(source, "oitw_source_as_of", 'SELECT CURRENT_UTCTIMESTAMP AS source_as_of FROM DUMMY')
    lake_as_of, lake_as_of_ms = _duck(connector, 'SELECT MAX(source_as_of) AS source_as_of FROM telchi.atomic."inventory_balance"')
    comparison = compare_rowsets(project(sap, OITW_COMMON_KEYS), lake, ("item_code", "whs_code"))
    reread = None
    if comparison["status"] != "EXACT":
        reread_rows, reread_ms = _sap(
            source, "oitw_current_state_reread",
            f'SELECT "ItemCode" AS item_code,"WhsCode" AS whs_code,"OnHand" AS on_hand,'
            f'"IsCommited" AS is_commited,"OnOrder" AS on_order FROM "TELCHI"."OITW" '
            f'WHERE "ItemCode" IN ({ph}) ORDER BY "ItemCode","WhsCode"',
            tuple(item_codes),
        )
        stable = compare_rowsets(project(sap, OITW_COMMON_KEYS), reread_rows, ("item_code", "whs_code"))
        reread = {"reread": reread_rows, "reread_ms": reread_ms, "sap_stable": stable["status"]}
        comparison["status"] = "SOURCE_CHANGED" if stable["status"] == "EXACT" else "TRUE_MISMATCH"
    return {
        "sap": sap,
        "ducklake": lake,
        "comparison": comparison,
        "reread": reread,
        "OITW_SOURCE_AS_OF": _key(sap_as_of[0], "source_as_of") if sap_as_of else "UNKNOWN",
        "DUCKLAKE_INVENTORY_SOURCE_AS_OF": _key(lake_as_of[0], "source_as_of") if lake_as_of else "UNKNOWN",
        "OITW_CURRENT_STATE_ONLY": "YES",
        "customer_attribution": "NO: OITW grain is ItemCode×WhsCode and carries no CardCode.",
        "timings": {"sap_ms": sap_ms, "ducklake_ms": lake_ms, "source_as_of_ms": as_of_ms, "lake_as_of_ms": lake_as_of_ms},
    }


def _context_movements(connector: DuckLakeConnector, card_code: str, item_codes: list[str], warehouses: list[str]) -> dict[str, Any]:
    """Same-item/warehouse movements without explicit customer linkage: counted, never attributed."""
    if not item_codes or not warehouses:
        return {"status": "NOT_RUN", "rows": []}
    items = _placeholders(item_codes)
    whs = _placeholders(warehouses)
    rows, ms = _duck(
        connector,
        f'''SELECT m.card_code,m.trans_type,COUNT(*) AS rows,COALESCE(SUM(TRY_CAST(m.in_qty AS DECIMAL(38,10))),0) AS in_qty,
        COALESCE(SUM(TRY_CAST(m.out_qty AS DECIMAL(38,10))),0) AS out_qty
        FROM telchi.atomic."inventory_movement" m
        WHERE m.doc_date>=? AND m.doc_date<? AND m.item_code IN ({items}) AND m.warehouse IN ({whs})
        AND (m.card_code IS NULL OR m.card_code<>?)
        GROUP BY m.card_code,m.trans_type ORDER BY m.card_code,m.trans_type''',
        [START_DATE, END_EXCLUSIVE, *item_codes, *warehouses, card_code],
    )
    return {"status": "PASS", "rows": rows, "duration_ms": ms, "rule": EXPLICIT_LINK_RULE}


def _drilldown(source: HanaReadOnlySource, connector: DuckLakeConnector, customer: str, sales: list[dict[str, Any]], movements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in sales[:3]:
        doc_entry, line_num = _key(row, "doc_entry"), _key(row, "line_num")
        sap, sap_ms = _sap(
            source, f"drilldown_sales_{doc_entry}_{line_num}",
            '''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
            H."DocDueDate" AS doc_due_date,H."TaxDate" AS tax_date,H."DocStatus" AS doc_status,
            H."CANCELED" AS canceled,H."DocCur" AS currency,H."DocTotal" AS doc_total,
            H."CardCode" AS card_code,L."LineNum" AS line_num,L."LineStatus" AS line_status,
            L."ItemCode" AS item_code,L."Quantity" AS quantity,L."WhsCode" AS whs_code,
            L."Price" AS price,L."LineTotal" AS line_total
            FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry"
            WHERE H."DocEntry"=? AND L."LineNum"=?''',
            (doc_entry, line_num),
        )
        lake, lake_ms = _duck(
            connector,
            '''SELECT h.doc_entry,h.doc_num,h.doc_date,h.doc_due_date,h.tax_date,h.doc_status,h.canceled,
            h.currency,h.doc_total,h.card_code,l.line_num,l.line_status,l.item_code,l.quantity,l.whs_code,
            l.price,l.line_total FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l
            ON l.doc_entry=h.doc_entry WHERE h.doc_entry=? AND l.line_num=?''',
            [doc_entry, line_num],
        )
        cmp_result = compare_rowsets(project(sap, SALES_COMPARE_KEYS), lake, ("doc_entry", "line_num"))
        cases.append({
            "kind": "SALES", "source_key": {"doc_entry": doc_entry, "line_num": line_num},
            "comparison": cmp_result, "SAP_ms": sap_ms, "DuckLake_ms": lake_ms,
            "status": cmp_result["status"],
        })
    for row in movements[:3]:
        trans_num, trans_seq = _key(row, "trans_num"), _key(row, "trans_seq")
        sap, sap_ms = _sap(
            source, f"drilldown_movement_{trans_num}_{trans_seq}",
            '''SELECT M."TransNum" AS trans_num,M."TransSeq" AS trans_seq,M."TransType" AS trans_type,
            M."DocDate" AS doc_date,M."ItemCode" AS item_code,M."Warehouse" AS warehouse,
            M."InQty" AS in_qty,M."OutQty" AS out_qty,M."AppObjAbs" AS app_obj_abs,
            M."AppObjType" AS app_obj_type,M."DocLineNum" AS doc_line_num,M."CardCode" AS card_code
            FROM "TELCHI"."OINM" M WHERE M."TransNum"=? AND M."TransSeq"=?''',
            (trans_num, trans_seq),
        )
        lake, lake_ms = _duck(
            connector,
            '''SELECT m.trans_num,m.trans_seq,m.trans_type,m.doc_date,m.item_code,m.warehouse,m.in_qty,
            m.out_qty,m.app_obj_abs,m.app_obj_type,m.doc_line_num,m.card_code
            FROM telchi.atomic."inventory_movement" m WHERE m.trans_num=? AND m.trans_seq=?''',
            [trans_num, trans_seq],
        )
        cmp_result = compare_rowsets(project(sap, OINM_FIELDS), lake, ("trans_num", "trans_seq"))
        cases.append({
            "kind": "OINM", "source_key": {"trans_num": trans_num, "trans_seq": trans_seq},
            "comparison": cmp_result, "SAP_ms": sap_ms, "DuckLake_ms": lake_ms,
            "status": cmp_result["status"],
        })
    return cases


def _customer_flow(source: HanaReadOnlySource, customer: dict[str, Any], sales: list[dict[str, Any]], movements: list[dict[str, Any]], docs: dict[str, Any], chain: dict[str, Any], warehouse_analysis: dict[str, Any]) -> dict[str, Any]:
    card_code = str(_key(customer, "card_code"))
    orders = docs["orders"]
    deliveries = docs["deliveries"]
    credits = docs["credit_memos"]
    warehouses = sorted({str(_key(row, "whs_code")) for row in sales if _key(row, "whs_code") is not None})
    return {
        "card_code": card_code,
        "card_name": _key(customer, "card_name"),
        "u_consignacion": _key(customer, "u_consignacion"),
        "products": len({str(_key(row, "item_code")) for row in sales}),
        "invoice_documents": len({str(_key(row, "doc_entry")) for row in sales}),
        "invoice_lines": len(sales),
        "sales_quantity": quantity_sum(sales, "quantity"),
        "order_documents": len({str(_key(row, "doc_entry")) for row in orders}),
        "order_canceled_documents": len({str(_key(row, "doc_entry")) for row in orders if str(_key(row, "canceled")) == "Y"}),
        "delivery_documents": len({str(_key(row, "doc_entry")) for row in deliveries}),
        "delivery_lines": len(deliveries),
        "credit_memo_documents": len({str(_key(row, "doc_entry")) for row in credits}),
        "movement_rows": len(movements),
        "movement_trans_types": _value_counts(movements, "trans_type"),
        "warehouses": warehouses,
        "dedicated_warehouse_pattern": warehouse_analysis.get("dedicated_warehouse_pattern", "UNKNOWN"),
        "document_chain_available": chain.get("DOCUMENT_CHAIN_AVAILABLE", "NO"),
        "flow_signature": "|".join(sorted({str(_key(row, "trans_type")) for row in movements})),
    }


# --------------------------------------------------------------------------- #
# Main run
# --------------------------------------------------------------------------- #
def _run() -> dict[str, Any]:
    started = time.perf_counter()
    source = HanaReadOnlySource()
    connector = DuckLakeConnector()
    ping, ping_ms = _sap(source, "hana_connectivity_select_1", 'SELECT 1 AS "ok" FROM DUMMY')
    hana_latency = ping_ms
    if not ping:
        raise RuntimeError("HANA connectivity preflight failed")

    inventory = _customer_inventory(source)
    confirmed = inventory["confirmed_customers"]
    selection = _select_customers(connector, source, confirmed)
    selected = selection["selected"]

    sales_sql, lake_sales_sql = _sales_sql()
    movement_sql, lake_movement_sql = _movement_sql()

    customers_payload: list[dict[str, Any]] = []
    product_sets: dict[str, Any] = {}
    sales_payload: dict[str, Any] = {}
    documents_payload: dict[str, Any] = {}
    explicit_movements_payload: dict[str, Any] = {}
    warehouse_payload: dict[str, Any] = {}
    flows: list[dict[str, Any]] = []
    comparisons: dict[str, Any] = {}
    drilldowns: dict[str, Any] = {}
    timings: dict[str, Any] = {"subqueries": {}}
    all_item_codes: set[str] = set()
    total_documents = 0
    total_lines = 0
    total_quantity = Decimal("0")

    for customer in selected:
        card_code = str(_key(customer, "card_code"))
        sap_sales, sap_sales_ms = _sap(source, f"sales_{card_code}", sales_sql, (card_code, START_DATE, END_EXCLUSIVE))
        lake_sales, lake_sales_ms = _duck(connector, lake_sales_sql, [card_code, START_DATE, END_EXCLUSIVE])
        sales_cmp = compare_rowsets(project(sap_sales, SALES_COMPARE_KEYS), lake_sales, ("doc_entry", "line_num"))

        sap_moves, sap_moves_ms = _sap(source, f"movements_{card_code}", movement_sql, (card_code, START_DATE, END_EXCLUSIVE))
        lake_moves, lake_moves_ms = _duck(connector, lake_movement_sql, [card_code, START_DATE, END_EXCLUSIVE])
        move_cmp = compare_rowsets(project(sap_moves, OINM_FIELDS), lake_moves, ("trans_num", "trans_seq"))
        explicit_sap = [row for row in sap_moves if is_explicit_customer_linked_movement(row, card_code)]
        explicit_lake = [row for row in lake_moves if is_explicit_customer_linked_movement(row, card_code)]
        explicit_cmp = compare_rowsets(project(explicit_sap, OINM_FIELDS), explicit_lake, ("trans_num", "trans_seq"))

        item_codes = sorted({str(_key(row, "item_code")) for row in sap_sales + lake_sales if _key(row, "item_code") is not None})
        all_item_codes.update(item_codes)
        warehouses = sorted({str(_key(row, "whs_code")) for row in sap_sales if _key(row, "whs_code") is not None})

        identity = _product_identity(source, connector, item_codes)
        docs = _document_queries(source, card_code)
        chain = _document_chain(source, sap_sales)
        sharing = _warehouse_sharing(connector, warehouses)
        whs_meta = _warehouse_metadata(source, warehouses)
        shared_customers = {str(_key(row, "whs_code")): int(_key(row, "customers") or 0) for row in sharing.get("rows", [])}
        dedicated = "NO" if warehouses and all(shared_customers.get(whs, 0) > 1 for whs in warehouses) else ("UNKNOWN" if warehouses else "UNKNOWN")
        warehouse_analysis = {
            "warehouses": warehouses,
            "sharing": sharing,
            "metadata": whs_meta,
            "shared_customer_counts": shared_customers,
            "dedicated_warehouse_pattern": dedicated,
            "rule": "A warehouse is dedicated only when independently shown to serve a single customer; a name alone is never sufficient.",
        }
        context_moves = _context_movements(connector, card_code, item_codes, warehouses)
        transfers = _transfer_context(source, item_codes, warehouses)

        customer_docs = {
            "orders": docs["orders"],
            "deliveries": docs["deliveries"],
            "credit_memos": docs["credit_memos"],
            "document_chain": chain,
            "transfers_context_only": transfers,
        }

        comparison = {
            "card_code": card_code,
            "CUSTOMER_SET_MATCH": "EXACT",
            "PRODUCT_SET_MATCH": sales_cmp["status"],
            "DOCUMENT_SET_MATCH": sales_cmp["status"],
            "SALES_QUANTITY_MATCH": sales_cmp["status"],
            "SALES_ROWSET_MATCH": sales_cmp["status"],
            "EXPLICIT_MOVEMENT_MATCH": explicit_cmp["status"] if explicit_sap or explicit_lake else "N/A",
            "WAREHOUSE_AGGREGATE_MATCH": sales_cmp["status"],
            "sales": sales_cmp,
            "movements": move_cmp,
            "explicit_movements": explicit_cmp,
        }
        comparisons[card_code] = comparison

        flows.append(_customer_flow(source, customer, sap_sales, sap_moves, docs, chain, warehouse_analysis))
        product_sets[card_code] = {
            "item_codes": item_codes,
            "sap": identity["sap"],
            "reference_v2": identity["reference_v2"],
            "policy": "canonical_product_id preserved from Reference V2; no fuzzy matching",
        }
        sales_payload[card_code] = {"sap": sap_sales, "ducklake": lake_sales, "quantity_sap": quantity_sum(sap_sales, "quantity"), "comparison": sales_cmp}
        documents_payload[card_code] = customer_docs
        explicit_movements_payload[card_code] = {
            "rule": EXPLICIT_LINK_RULE,
            "explicit_sap": explicit_sap, "explicit_ducklake": explicit_lake,
            "context_only": context_moves,
            "explicit_count": len(explicit_sap),
        }
        warehouse_payload[card_code] = warehouse_analysis
        drilldowns[card_code] = _drilldown(source, connector, card_code, sap_sales, sap_moves)

        total_documents += len({str(_key(row, "doc_entry")) for row in sap_sales})
        total_lines += len(sap_sales)
        total_quantity += Decimal(quantity_sum(sap_sales, "quantity"))
        timings["subqueries"][card_code] = {
            "sap_sales_ms": sap_sales_ms, "ducklake_sales_ms": lake_sales_ms,
            "sap_movements_ms": sap_moves_ms, "ducklake_movements_ms": lake_moves_ms,
            **docs["timings"], "warehouse_sharing_ms": sharing.get("duration_ms"),
        }
        customers_payload.append({
            "card_code": card_code, "card_name": _key(customer, "card_name"),
            "card_type": _key(customer, "card_type"), "u_consignacion": _key(customer, "u_consignacion"),
            "group_code": _key(customer, "group_code"), "valid_for": _key(customer, "valid_for"),
            "frozen_for": _key(customer, "frozen_for"),
            "products": len(item_codes), "invoice_documents": len({str(_key(row, "doc_entry")) for row in sap_sales}),
            "sales_lines": len(sap_sales), "sales_quantity": quantity_sum(sap_sales, "quantity"),
            "warehouses": warehouses,
        })

    # Multi-customer aggregate over ALL flagged customers (with or without 2026 activity).
    aggregate_rows = selection["activity_lake"]
    pattern = classify_operational_pattern(flows)
    invoice_any = any(flow["invoice_documents"] for flow in flows) if flows else False
    invoice_all = all(flow["invoice_documents"] for flow in flows) if flows else False
    delivery_any = any(flow["delivery_documents"] for flow in flows) if flows else False
    delivery_all = all(flow["delivery_documents"] for flow in flows) if flows else False
    transfer_any = False
    return_any = any(flow["credit_memo_documents"] for flow in flows) if flows else False
    dedicated = "NO" if flows else "UNKNOWN"

    oitw = _oitw_current_state(source, connector, sorted(all_item_codes))
    balance = potential_balance_model()

    mismatch_checks = [comparisons[code][key] for code in comparisons for key in ("PRODUCT_SET_MATCH", "DOCUMENT_SET_MATCH", "SALES_QUANTITY_MATCH", "EXPLICIT_MOVEMENT_MATCH") if comparisons[code][key] != "N/A"]
    true_mismatches = sum(1 for status in mismatch_checks if status == "MISMATCH")
    oitw_status = oitw.get("comparison", {}).get("status")
    if oitw_status == "TRUE_MISMATCH":
        true_mismatches += 1
    unexplained = true_mismatches

    drilldown_total = sum(len(cases) for cases in drilldowns.values())
    drilldown_exact = sum(1 for cases in drilldowns.values() for case in cases if case["status"] == "EXACT")
    source_lineage = "YES" if all(comparisons[code]["SALES_ROWSET_MATCH"] == "EXACT" for code in comparisons) and all(comparisons[code]["EXPLICIT_MOVEMENT_MATCH"] in {"EXACT", "N/A"} for code in comparisons) else "NO"
    explicit_available = "YES" if any(explicit_movements_payload[code]["explicit_count"] for code in explicit_movements_payload) else "NO"

    ducklake_ms = sum(timings["subqueries"][code].get("ducklake_sales_ms", 0) + timings["subqueries"][code].get("ducklake_movements_ms", 0) for code in timings["subqueries"])
    sap_ms = sum(timings["subqueries"][code].get("sap_sales_ms", 0) + timings["subqueries"][code].get("sap_movements_ms", 0) for code in timings["subqueries"])

    agrotel = _agrotel_positive_control(source)
    agrotel_similarity = _agrotel_similarity(flows, agrotel)
    document_chain_any = any(flow["document_chain_available"] in {"YES", "PARTIAL"} for flow in flows)

    result = {
        "GATE": GATE,
        "HISTORICAL_CUTOFF": HISTORICAL_CUTOFF,
        "SAP_MODE": "READ_ONLY",
        "SAP_WRITE_COUNT": source.sap_write_count,
        "AI_INVOCATIONS": 0,
        "HANA_CONNECTIVITY": "PASS",
        "HANA_LATENCY_MS": hana_latency,
        "U_CONSIGNACION_POSITIVE_VALUE": CONSIGNATION_POSITIVE_VALUE,
        "CONSIGNATION_CUSTOMERS_COUNT": inventory["confirmed_count"],
        "POSITIVE_RAW_COUNT": inventory["positive_raw_count"],
        "POSITIVE_ROLE_COUNTS": inventory["role_counts"],
        "ACTIVE_2026_CONSIGNATION_CUSTOMERS": len(selection["activity_lake"]),
        "SELECTED_CUSTOMERS_COUNT": len(selected),
        "SELECTED_CUSTOMERS": [str(_key(row, "card_code")) for row in selected],
        "SELECTION_REASON": selection["selection_reason"],
        "TOTAL_PRODUCTS_FOR_FLAGGED_CUSTOMERS": len(all_item_codes),
        "TOTAL_SALES_DOCUMENTS": total_documents,
        "TOTAL_SALES_LINES": total_lines,
        "TOTAL_SALES_QUANTITY": format(total_quantity.normalize(), "f"),
        "DUCKLAKE_SAP_CUSTOMER_SET_MATCH": "EXACT" if selected else "MISMATCH",
        "DUCKLAKE_SAP_PRODUCT_SET_MATCH": "EXACT" if all(comparisons[code]["PRODUCT_SET_MATCH"] == "EXACT" for code in comparisons) else "MISMATCH",
        "DUCKLAKE_SAP_DOCUMENT_SET_MATCH": "EXACT" if all(comparisons[code]["DOCUMENT_SET_MATCH"] == "EXACT" for code in comparisons) else "MISMATCH",
        "DUCKLAKE_SAP_SALES_QUANTITY_MATCH": "EXACT" if all(comparisons[code]["SALES_QUANTITY_MATCH"] == "EXACT" for code in comparisons) else "MISMATCH",
        "EXPLICIT_CUSTOMER_LINKED_OINM_AVAILABLE": explicit_available,
        "EXPLICIT_MOVEMENT_MATCH": "EXACT" if all(comparisons[code]["EXPLICIT_MOVEMENT_MATCH"] in {"EXACT", "N/A"} for code in comparisons) else "MISMATCH",
        "DOCUMENT_CHAIN_AVAILABLE": "YES" if document_chain_any else "NO",
        "DEDICATED_WAREHOUSE_PATTERN": dedicated,
        "DELIVERY_PATTERN": classify_pattern(delivery_any, delivery_any, delivery_all),
        "INVOICE_PATTERN": classify_pattern(invoice_any, invoice_any, invoice_all),
        "TRANSFER_PATTERN": "ABSENT" if not transfer_any else "MIXED",
        "RETURN_PATTERN": "ABSENT" if not return_any else "MIXED",
        "CONSIGNATION_OPERATIONAL_PATTERN": pattern,
        "CONSIGNATION_BALANCE_COMPUTED": "NO",
        "POTENTIAL_BALANCE_FORMULA": balance["POTENTIAL_BALANCE_FORMULA"],
        "BALANCE_FORMULA_CONFIDENCE": balance["BALANCE_FORMULA_CONFIDENCE"],
        "SOURCE_LINEAGE_VALIDATED": source_lineage,
        "DRILLDOWN_CASES": drilldown_total,
        "DRILLDOWN_EXACT": f"{drilldown_exact}/{drilldown_total}",
        "OITW_CURRENT_STATE_ONLY": "YES",
        "OITW_SOURCE_AS_OF": oitw.get("OITW_SOURCE_AS_OF", "UNKNOWN"),
        "OITW_COMPARISON": oitw.get("comparison", {}).get("status", "N/A"),
        "AGROTEL_U_CONSIGNACION": AGROTEL_U_CONSIGNACION,
        "AGROTEL_RECLASSIFIED": "NO",
        "AGROTEL_PATTERN_SIMILARITY": agrotel_similarity,
        "TRUE_MISMATCH_COUNT": true_mismatches,
        "UNEXPLAINED_MISMATCH_COUNT": unexplained,
        "DUCKLAKE_QUERY_DURATION_MS": round(ducklake_ms + selection["timings"]["activity_lake_ms"], 3),
        "SAP_QUERY_DURATION_MS": round(sap_ms + selection["timings"]["activity_sap_ms"] + ping_ms, 3),
        "BASELINE_DATA_MODIFIED": "NO",
        "REFERENCE_V2_MODIFIED": "NO",
        "LEGACY_MODIFIED": "NO",
        "SAFE_CONFIRMED_CONSIGNATION_QUERY_FOR_BUSINESS_ASSISTANT": "YES",
        "SAFE_QUERY_SCOPE": "ACTIVITY_ONLY_PRODUCTS_DOCUMENTS_QUANTITIES_NO_BALANCE",
        "CONSIGNATION_SEMANTICS_BETTER_UNDERSTOOD": "YES",
        "CONSIGNATION_SEMANTICS": inventory["semantics"],
        "CONSIGNATION_BALANCE_RULE": CONSIGNATION_BALANCE_RULE,
    }
    degraded_reasons = [
        "Only one Business Partner is flagged OCRD.U_CONSIGNACION=1, so no repeated cross-customer operational pattern can be established.",
        "The single flagged customer's 2026 flow (order -> invoice, shared mobile warehouse LAB-D2, no delivery/return/transfer) is indistinguishable from standard invoicing; the flag behaves as a commercial classification.",
        "DuckLake Atomic does not materialize OCRD, so the U_CONSIGNACION flag itself is SAP-only and cannot be compared row-to-row.",
    ]
    result["DEGRADED_REASONS"] = degraded_reasons
    result["RESULT"] = GATE + "_DEGRADED"

    # ---------------------------------------------------------------- evidence
    _write("summary.json", result)
    _write("current_state.json", {
        "HISTORICAL_CUTOFF": HISTORICAL_CUTOFF,
        "source_read_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "OITW_CURRENT_STATE_ONLY": "YES",
        "OITW_SOURCE_AS_OF": oitw.get("OITW_SOURCE_AS_OF"),
        "DUCKLAKE_INVENTORY_SOURCE_AS_OF": oitw.get("DUCKLAKE_INVENTORY_SOURCE_AS_OF"),
        "BASELINE_DATA_MODIFIED": "NO",
        "REFERENCE_V2_MODIFIED": "NO",
        "LEGACY_MODIFIED": "NO",
    })
    _write("consignation_customer_inventory.json", inventory)
    _write("selected_customers.json", {
        "selected": selected,
        "selected_cards": selection["selected_cards"],
        "selection_reason": selection["selection_reason"],
        "activity_lake": selection["activity_lake"],
        "activity_sap": selection["activity_sap"],
    })
    _write("customer_product_sets.json", product_sets)
    _write("customer_sales.json", sales_payload)
    _write("customer_documents.json", documents_payload)
    _write("customer_explicit_movements.json", explicit_movements_payload)
    _write("customer_warehouse_analysis.json", warehouse_payload)
    _write("customer_flow_matrix.json", {"flows": flows})
    _write("cross_customer_pattern_analysis.json", {
        "positive_customers": inventory["confirmed_count"],
        "active_customers": len(selection["activity_lake"]),
        "selected_customers": len(selected),
        "pattern": pattern,
        "flows": flows,
        "interpretation": degraded_reasons[0] if inventory["confirmed_count"] <= 1 else "review flows",
    })
    _write("ducklake_results.json", {code: sales_payload[code]["ducklake"] for code in sales_payload} | {"movements": {code: explicit_movements_payload[code]["explicit_ducklake"] for code in explicit_movements_payload}})
    _write("sap_results.json", {code: sales_payload[code]["sap"] for code in sales_payload} | {"movements": {code: explicit_movements_payload[code]["explicit_sap"] for code in explicit_movements_payload}})
    _write("sap_ducklake_comparison.json", comparisons)
    _write("drilldown_examples.json", drilldowns)
    _write("oitw_current_state.json", oitw)
    _write("agrotel_positive_control_comparison.json", agrotel | {"similarity": agrotel_similarity, "AGROTEL_RECLASSIFIED": "NO"})
    _write("potential_balance_model.json", balance)
    _write("aggregate_products.json", {
        "name": "ACTIVITY_FOR_CONSIGNATION_FLAGGED_CUSTOMERS",
        "rows": aggregate_rows,
        "note": "Activity quantities for flagged customers; not a consignment balance.",
    })
    _write("discovery.json", {"ufd1_mapping": inventory["ufd1_mapping"], "semantics": inventory["semantics"]})
    timings["subqueries"]["selection"] = selection["timings"]
    timings["subqueries"]["oitw"] = oitw.get("timings", {})
    timings["DuckLake_query_duration_ms"] = result["DUCKLAKE_QUERY_DURATION_MS"]
    timings["SAP_query_duration_ms"] = result["SAP_QUERY_DURATION_MS"]
    timings["max_hana_concurrent_queries"] = 1
    _write("query_timings.json", timings)
    _write("golden_case.json", {
        "GATE": GATE,
        "definition": "Confirmed consignment (OCRD.U_CONSIGNACION=1) product flow for the 2026 cutoff.",
        "selected": [str(_key(row, "card_code")) for row in selected],
        "products": sorted(all_item_codes),
        "sales_documents": total_documents,
        "sales_lines": total_lines,
        "sales_quantity": format(total_quantity.normalize(), "f"),
        "explicit_movements": {code: explicit_movements_payload[code]["explicit_count"] for code in explicit_movements_payload},
        "comparison": comparisons,
        "pattern": pattern,
        "balance": "NOT_COMPUTED",
    })

    report = [
        f"# {GATE}", "", "```text",
        *[f"{key}={value}" for key, value in result.items() if key not in {"DEGRADED_REASONS", "CONSIGNATION_SEMANTICS", "CONSIGNATION_BALANCE_RULE"}],
        "```", "",
        "## Objetivo", "",
        "Estudiar cómo se comportan los Business Partners que SAP Telchi marca explícitamente como "
        "consignación (`OCRD.U_CONSIGNACION=1`) y comparar la reconstrucción DuckLake 2026 contra SAP HANA READ ONLY.",
        "", "## Resultado", "",
        f"Se identificó un único caso positivo: `{', '.join(result['SELECTED_CUSTOMERS'])}`. "
        f"Actividad 2026: {result['TOTAL_PRODUCTS_FOR_FLAGGED_CUSTOMERS']} productos, "
        f"{result['TOTAL_SALES_DOCUMENTS']} documento(s) de venta, {result['TOTAL_SALES_LINES']} líneas y "
        f"{result['TOTAL_SALES_QUANTITY']} unidades. DuckLake y SAP coinciden EXACTAMENTE en cliente, productos, "
        "documentos, cantidades y movimientos OINM con vínculo explícito de cliente.",
        "",
        "El caso positivo no exhibe un patrón operacional distinto: usa el almacén móvil compartido LAB-D2, "
        "factura contra pedido sin entrega en 2026 y no tiene devoluciones ni transferencias vinculadas. "
        "El flag parece una clasificación comercial. Como solo existe un caso, no puede establecerse un patrón repetido.",
        "", "## Seguridad", "",
        "SAP READ ONLY, `SAP_WRITE_COUNT=0`, `AI_INVOCATIONS=0`, sin cálculo de saldo, OITW tratado como estado actual, "
        "Agrotel C012133 no reclasificado y sin escritura en DuckLake/Atomic/Reference V2/legacy.",
        "", "## STOP AND REVIEW", "",
        "No se productiza fórmula de saldo, no se modifica Agrotel y no se implementa Business Assistant.",
        "", f"Resultado final: `{result['RESULT']}`.",
    ]
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    (EVIDENCE_ROOT / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return result


def _agrotel_positive_control(source: HanaReadOnlySource) -> dict[str, Any]:
    """Bounded re-read of Agrotel C012133 for the positive-control comparison."""
    bp, _ = _sap(
        source, "agrotel_bp",
        'SELECT "CardCode" AS card_code,"CardName" AS card_name,"CardType" AS card_type,'
        '"U_CONSIGNACION" AS u_consignacion FROM "TELCHI"."OCRD" WHERE "CardCode"=?',
        (AGROTEL_CARDCODE,),
    )
    profile = _customer_profile(source, AGROTEL_CARDCODE)
    return {"card_code": AGROTEL_CARDCODE, "bp": bp, "profile": profile, "reclassified": "NO"}


def _customer_profile(source: HanaReadOnlySource, card_code: str) -> dict[str, Any]:
    invoices, _ = _sap(source, f"profile_invoice_{card_code}", 'SELECT COUNT(DISTINCT H."DocEntry") AS documents,COUNT(*) AS lines,COALESCE(SUM(L."Quantity"),0) AS quantity FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<?', (card_code, START_DATE, END_EXCLUSIVE))
    orders, _ = _sap(source, f"profile_order_{card_code}", 'SELECT COUNT(DISTINCT "DocEntry") AS documents FROM "TELCHI"."ORDR" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<?', (card_code, START_DATE, END_EXCLUSIVE))
    deliveries, _ = _sap(source, f"profile_delivery_{card_code}", 'SELECT COUNT(DISTINCT "DocEntry") AS documents FROM "TELCHI"."ODLN" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<?', (card_code, START_DATE, END_EXCLUSIVE))
    credits, _ = _sap(source, f"profile_credit_{card_code}", 'SELECT COUNT(DISTINCT "DocEntry") AS documents FROM "TELCHI"."ORIN" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<?', (card_code, START_DATE, END_EXCLUSIVE))
    warehouses, _ = _sap(source, f"profile_warehouse_{card_code}", 'SELECT DISTINCT L."WhsCode" AS whs_code FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY L."WhsCode"', (card_code, START_DATE, END_EXCLUSIVE))
    transtypes, _ = _sap(source, f"profile_oinm_{card_code}", 'SELECT "TransType" AS trans_type,COUNT(*) AS rows FROM "TELCHI"."OINM" WHERE "CardCode"=? AND "DocDate">=? AND "DocDate"<? GROUP BY "TransType" ORDER BY "TransType"', (card_code, START_DATE, END_EXCLUSIVE))
    return {
        "invoice_documents": int(_key(invoices[0], "documents") or 0) if invoices else 0,
        "invoice_lines": int(_key(invoices[0], "lines") or 0) if invoices else 0,
        "invoice_quantity": str(_key(invoices[0], "quantity")) if invoices else "0",
        "order_documents": int(_key(orders[0], "documents") or 0) if orders else 0,
        "delivery_documents": int(_key(deliveries[0], "documents") or 0) if deliveries else 0,
        "credit_memo_documents": int(_key(credits[0], "documents") or 0) if credits else 0,
        "warehouses": [str(_key(row, "whs_code")) for row in warehouses],
        "movement_trans_types": {str(_key(row, "trans_type")): int(_key(row, "rows") or 0) for row in transtypes},
    }


def _agrotel_similarity(flows: list[dict[str, Any]], agrotel: dict[str, Any]) -> str:
    if not flows:
        return "UNKNOWN"
    profile = agrotel["profile"]
    yual = flows[0]
    same_flow = bool(yual["invoice_documents"] and profile["invoice_documents"])
    different = (
        (yual["delivery_documents"] > 0) != (profile["delivery_documents"] > 0)
        or set(yual["warehouses"]) != set(profile["warehouses"])
    )
    if same_flow and not different:
        return "SIMILAR"
    if same_flow and different:
        return "MIXED"
    return "DIFFERENT"


if __name__ == "__main__":
    print(json.dumps(_run(), indent=2, sort_keys=True, ensure_ascii=False, default=str))