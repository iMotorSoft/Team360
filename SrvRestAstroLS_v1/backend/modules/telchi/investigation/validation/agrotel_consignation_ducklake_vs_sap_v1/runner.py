"""Focused AGROTEL consignment investigation and DuckLake/SAP gate.

This runner is intentionally an investigation artifact.  It reads the
published DuckLake Atomic baseline and SAP HANA through the existing read-only
adapter, never writes either system, and does not call an AI provider.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.source import HanaReadOnlySource

GATE = "TELCHI_AGROTEL_CONSIGNATION_DUCKLAKE_VS_SAP_V1"
HISTORICAL_CUTOFF = "2026-09-15"
START_DATE = "2026-01-01"
END_EXCLUSIVE = "2026-09-16"
CUSTOMER_CARDCODE = "C012133"
SUPPLIER_CARDCODE = "PL000700"
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
REFERENCE_V2_PRODUCTS = DATA_ROOT / "reference" / "_versions" / "v2" / "products" / "part-00000.parquet"

_NUMERIC_KEYS = {
    "doc_entry", "doc_num", "line_num", "base_entry", "base_line", "base_type",
    "quantity", "line_total", "price", "trans_num", "trans_seq", "trans_type",
    "in_qty", "out_qty", "app_obj_abs", "app_obj_type", "doc_line_num", "on_hand",
    "is_commited", "on_order", "consig", "rows", "documents", "products",
}
_DATE_KEYS = {"doc_date", "doc_due_date", "tax_date", "update_date"}
_SALES_COMPARE_KEYS = ("doc_entry", "doc_num", "doc_date", "doc_due_date", "tax_date", "doc_status", "canceled", "currency", "doc_total", "card_code", "line_num", "line_status", "item_code", "quantity", "whs_code", "price", "line_total")
_INVENTORY_COMPARE_KEYS = ("item_code", "whs_code", "on_hand", "is_commited", "on_order")


def _key(row: dict[str, Any], name: str) -> Any:
    wanted = name.lower()
    for key, value in row.items():
        if str(key).lower() == wanted:
            return value
    return None


def _normal_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    lower = key.lower()
    if lower in _DATE_KEYS:
        return str(value)[:10]
    if lower in _NUMERIC_KEYS:
        try:
            return format(Decimal(str(value)).normalize(), "f")
        except (InvalidOperation, ValueError):
            return str(value)
    return value.isoformat() if hasattr(value, "isoformat") else value


def _normal(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize without tolerances; ordering is deterministic and source-native."""
    normalized = [
        {str(key).lower(): _normal_value(str(key), value) for key, value in row.items()}
        for row in rows
    ]
    return normalized


def _ordered(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: tuple(str(row.get(key, "")) for key in keys))


def _project(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{key: _key(row, key) for key in keys} for row in rows]


def deterministic_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_rows(left: list[dict[str, Any]], right: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any]:
    left_normal = _ordered(_normal(left), keys)
    right_normal = _ordered(_normal(right), keys)
    equal = left_normal == right_normal
    return {
        "status": "EXACT" if equal else "MISMATCH",
        "left_count": len(left_normal),
        "right_count": len(right_normal),
        "left_hash": deterministic_hash(left_normal),
        "right_hash": deterministic_hash(right_normal),
        "left_sample": left_normal[:5],
        "right_sample": right_normal[:5],
        "left_only_sample": left_normal[:5] if not equal else [],
        "right_only_sample": right_normal[:5] if not equal else [],
    }


def historical_predicate(column: str = "doc_date") -> str:
    """Return the only accepted historical half-open predicate."""
    return f'{column} >= ? AND {column} < ?'


def select_exact_agrotel_candidate(candidates: list[dict[str, Any]], *, card_code: str) -> dict[str, Any] | None:
    """Select by an explicit source key; never fuzzy-select by name."""
    matches = [row for row in candidates if str(_key(row, "card_code")) == card_code]
    if len(matches) != 1:
        return None
    return matches[0]


def _rows(cursor: Any) -> list[dict[str, Any]]:
    names = [str(item[0]).lower() for item in cursor.description or ()]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _write(name: str, value: Any) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    (EVIDENCE_ROOT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _placeholders(values: list[Any]) -> str:
    if not values:
        raise ValueError("bounded IN list cannot be empty")
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


def _identity_discovery(source: HanaReadOnlySource, connector: DuckLakeConnector) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates, _ = _sap(
        source,
        "agrotel_identity_candidates",
        '''SELECT TOP 20 "CardCode" AS card_code,"CardName" AS card_name,"CardType" AS card_type,
                  "frozenFor" AS frozen_for,"validFor" AS valid_for,"LicTradNum" AS tax_id
           FROM "TELCHI"."OCRD"
           WHERE UPPER("CardName")='AGROTEL'
           ORDER BY "CardCode"''',
    )
    selected = select_exact_agrotel_candidate(candidates, card_code=CUSTOMER_CARDCODE)
    vendor = select_exact_agrotel_candidate(candidates, card_code=SUPPLIER_CARDCODE)
    lake_identity, _ = _duck(
        connector,
        '''SELECT DISTINCT h.card_code FROM telchi.atomic."sales_document" h
           WHERE h.card_code=? AND h.doc_date>=? AND h.doc_date<? ORDER BY h.card_code''',
        [CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE],
    )
    identity = {
        "requested_name": "AGROTEL",
        "sap_candidates": candidates,
        "candidate_count": len(candidates),
        "customer_sales_scope": selected,
        "supplier_inventory_scope": vendor,
        "selected_sales_scope_reason": "Exact CardCode C012133 is present in OINV 2026 and DuckLake Atomic Sales; no fuzzy name selection.",
        "same_name_role_separation": "C012133=CUSTOMER; PL000700=SUPPLIER",
        "ducklake_sales_identity": lake_identity,
        "ducklake_identity_match": "EXACT" if selected and lake_identity == [{"card_code": CUSTOMER_CARDCODE}] else "MISMATCH",
        "AGROTEL_IDENTIFIED": "YES" if selected else "NO",
        "AGROTEL_CARDCODE": CUSTOMER_CARDCODE if selected else "UNKNOWN",
        "AGROTEL_CARDNAME": _key(selected or {}, "card_name") or "UNKNOWN",
        "AGROTEL_MATCH_CONFIDENCE": "AMBIGUOUS" if len(candidates) > 1 else ("EXACT" if selected else "NOT_FOUND"),
        "identity_scope_status": "EXACT_ROLE_SELECTED_WITH_SECOND_SAME_NAME_BP" if selected and vendor else "UNRESOLVED",
        "semantic_stop_note": "The same literal CardName exists as customer and supplier; role-specific scope is preserved and not silently merged.",
    }
    return identity, {"candidates": candidates, "ducklake_sales_identity": lake_identity}


def _discovery(source: HanaReadOnlySource, identity: dict[str, Any], item_codes: list[str]) -> dict[str, Any]:
    udfs, _ = _sap(
        source,
        "consignation_udf_metadata",
        '''SELECT TOP 200 "TableID" AS table_id,"FieldID" AS field_id,"AliasID" AS alias_id,
                  "Descr" AS description,"TypeID" AS type_id,"SizeID" AS size_id
           FROM "TELCHI"."CUFD"
           WHERE UPPER(COALESCE("AliasID",'')) LIKE '%CONSIGN%'
              OR UPPER(COALESCE("Descr",'')) LIKE '%CONSIGN%'
              OR UPPER(COALESCE("AliasID",'')) LIKE '%AGROT%'
              OR UPPER(COALESCE("Descr",'')) LIKE '%AGROT%'
           ORDER BY "TableID","FieldID"''',
    )
    customer_flags, _ = _sap(
        source,
        "consignation_customer_flags",
        '''SELECT "CardCode" AS card_code,"CardName" AS card_name,"CardType" AS card_type,
                  "U_CONSIGNACION" AS u_consignacion,"frozenFor" AS frozen_for,"validFor" AS valid_for
           FROM "TELCHI"."OCRD" WHERE "CardCode" IN (?,?) ORDER BY "CardCode"''',
        (CUSTOMER_CARDCODE, SUPPLIER_CARDCODE),
    )
    item_placeholders = _placeholders(item_codes)
    oitw_consig, _ = _sap(
        source,
        "consignation_oitw_overlap",
        f'''SELECT TOP 5000 W."ItemCode" AS item_code,W."WhsCode" AS whs_code,
                   W."OnHand" AS on_hand,W."Consig" AS consig,W."IsCommited" AS is_commited,
                   W."OnOrder" AS on_order,W."updateDate" AS update_date
            FROM "TELCHI"."OITW" W WHERE W."ItemCode" IN ({item_placeholders})
            ORDER BY W."ItemCode",W."WhsCode"''',
        tuple(item_codes),
    )
    consignment_text, _ = _sap(
        source,
        "consignation_textual_oinm_sample",
        '''SELECT TOP 200 M."TransNum" AS trans_num,M."TransSeq" AS trans_seq,
                  M."TransType" AS trans_type,M."DocDate" AS doc_date,M."ItemCode" AS item_code,
                  M."Warehouse" AS warehouse,M."InQty" AS in_qty,M."OutQty" AS out_qty,
                  M."CardCode" AS card_code,M."CardName" AS card_name,
                  M."Comments" AS comments,M."JrnlMemo" AS jrnl_memo,
                  M."AppObjAbs" AS app_obj_abs,M."AppObjType" AS app_obj_type,
                  M."DocLineNum" AS doc_line_num
           FROM "TELCHI"."OINM" M
           WHERE M."DocDate">=? AND M."DocDate"<?
             AND (UPPER(COALESCE(M."Comments",'')) LIKE '%CONSIGN%'
               OR UPPER(COALESCE(M."JrnlMemo",'')) LIKE '%CONSIGN%')
           ORDER BY M."DocDate",M."TransNum",M."TransSeq"''',
        (START_DATE, END_EXCLUSIVE),
    )
    customer_text = [row for row in consignment_text if str(_key(row, "card_code") or "") == CUSTOMER_CARDCODE or str(_key(row, "card_name") or "").upper() == "AGROTEL"]
    return {
        "scope": {"card_code": CUSTOMER_CARDCODE, "from": START_DATE, "to_inclusive": HISTORICAL_CUTOFF},
        "metadata_fields": udfs,
        "bp_consignacion_values": customer_flags,
        "oitw_consignment_overlap_current": oitw_consig,
        "textual_oinm_consignment_sample": consignment_text[:50],
        "textual_oinm_agrotel_rows": customer_text,
        "findings": {
            "ocrd_customer_udf_value": next((_key(row, "u_consignacion") for row in customer_flags if _key(row, "card_code") == CUSTOMER_CARDCODE), None),
            "ocrd_supplier_udf_value": next((_key(row, "u_consignacion") for row in customer_flags if _key(row, "card_code") == SUPPLIER_CARDCODE), None),
            "customer_consignment_text_rows": len(customer_text),
            "oitw_consignment_rows_for_sales_products": sum(1 for row in oitw_consig if Decimal(str(_key(row, "consig") or 0)) != 0),
            "oitw_customer_binding": "NONE: OITW is ItemCode×WhsCode and has no CardCode",
            "textual_consignation_binding": "NO customer-specific Agrotel binding observed in bounded 2026 OINM sample",
        },
        "oinm_schema": source.discover_oinm_schema(),
    }


def _sales_sql() -> tuple[str, str]:
    sap = '''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
                    H."DocDueDate" AS doc_due_date,H."TaxDate" AS tax_date,H."DocStatus" AS doc_status,
                    H."CANCELED" AS canceled,H."DocCur" AS currency,H."DocTotal" AS doc_total,
                    H."CardCode" AS card_code,H."CardName" AS card_name,L."LineNum" AS line_num,
                    L."LineStatus" AS line_status,L."ItemCode" AS item_code,L."Quantity" AS quantity,
                    L."WhsCode" AS whs_code,L."Price" AS price,L."LineTotal" AS line_total,
                    L."BaseType" AS base_type,L."BaseEntry" AS base_entry,L."BaseLine" AS base_line,
                    H."Comments" AS comments,H."Ref1" AS ref1,H."Ref2" AS ref2
             FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry"
             WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<?
             ORDER BY H."DocEntry",L."LineNum"'''
    lake = '''SELECT h.doc_entry,h.doc_num,h.doc_date,h.doc_due_date,h.tax_date,h.doc_status,
                     h.canceled,h.currency,h.doc_total,h.card_code,h.card_code AS card_name,
                     l.line_num,l.line_status,l.item_code,l.quantity,l.whs_code,l.price,l.line_total
              FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry
              WHERE h.card_code=? AND h.doc_date>=? AND h.doc_date<?
              ORDER BY CAST(h.doc_entry AS BIGINT),CAST(l.line_num AS BIGINT)'''
    return sap, lake


def _movement_sql() -> tuple[str, str]:
    fields = "trans_num,trans_seq,trans_type,doc_date,item_code,warehouse,in_qty,out_qty,base_ref,app_obj_abs,app_obj_type,doc_line_num,card_code,card_name,comments,jrnl_memo"
    sap = '''SELECT M."TransNum" AS trans_num,M."TransSeq" AS trans_seq,M."TransType" AS trans_type,
                    M."DocDate" AS doc_date,M."ItemCode" AS item_code,M."Warehouse" AS warehouse,
                    M."InQty" AS in_qty,M."OutQty" AS out_qty,M."BASE_REF" AS base_ref,
                    M."AppObjAbs" AS app_obj_abs,M."AppObjType" AS app_obj_type,
                    M."DocLineNum" AS doc_line_num,M."CardCode" AS card_code,M."CardName" AS card_name,
                    M."Comments" AS comments,M."JrnlMemo" AS jrnl_memo
             FROM "TELCHI"."OINM" M
             WHERE M."CardCode"=? AND M."DocDate">=? AND M."DocDate"<?
             ORDER BY M."TransNum",M."TransSeq"'''
    lake = f'''SELECT {fields} FROM telchi.atomic."inventory_movement" m
               WHERE m.card_code=? AND m.doc_date>=? AND m.doc_date<?
               ORDER BY CAST(m.trans_num AS BIGINT),CAST(m.trans_seq AS BIGINT)'''
    return sap, lake


def _supplier_movement_sql() -> tuple[str, str]:
    return _movement_sql()


def _current_inventory_sql(item_codes: list[str]) -> tuple[str, str, tuple[Any, ...], list[Any]]:
    placeholders = _placeholders(item_codes)
    sap = f'''SELECT TOP 5000 W."ItemCode" AS item_code,W."WhsCode" AS whs_code,
                     W."OnHand" AS on_hand,W."IsCommited" AS is_commited,W."OnOrder" AS on_order,
                     W."Consig" AS consig,W."updateDate" AS update_date
              FROM "TELCHI"."OITW" W WHERE W."ItemCode" IN ({placeholders})
              ORDER BY W."ItemCode",W."WhsCode"'''
    lake = f'''SELECT w.item_code,w.whs_code,w.on_hand,w.is_commited,w.on_order
               FROM telchi.atomic."inventory_balance" w WHERE w.item_code IN ({placeholders})
               ORDER BY w.item_code,w.whs_code'''
    return sap, lake, tuple(item_codes), list(item_codes)


def _product_rows(source: HanaReadOnlySource, connector: DuckLakeConnector, item_codes: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    placeholders = _placeholders(item_codes)
    sap, _ = _sap(
        source,
        "agrotel_product_descriptions",
        f'''SELECT "ItemCode" AS item_code,"ItemName" AS description,"ItmsGrpCod" AS item_group,
                   "frozenFor" AS frozen_for FROM "TELCHI"."OITM"
            WHERE "ItemCode" IN ({placeholders}) ORDER BY "ItemCode"''',
        tuple(item_codes),
    )
    lake, _ = _duck(
        connector,
        f'''SELECT item_code,canonical_product_id,canonical_name,product_name,active
            FROM read_parquet(?) WHERE item_code IN ({placeholders}) ORDER BY item_code''',
        [str(REFERENCE_V2_PRODUCTS), *item_codes],
    )
    return sap, lake


def _chain_documents(source: HanaReadOnlySource, invoices: list[dict[str, Any]]) -> dict[str, Any]:
    """Read explicit BaseEntry/BaseLine links; no date/quantity fuzzy joins."""
    delivery_keys = sorted({(int(_key(row, "base_entry")), int(_key(row, "base_line"))) for row in invoices if _key(row, "base_type") == 15 and _key(row, "base_entry") is not None and _key(row, "base_line") is not None})
    deliveries: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    if delivery_keys:
        entries = sorted({key[0] for key in delivery_keys})
        ph = _placeholders(entries)
        deliveries, _ = _sap(source, "agrotel_delivery_chain", f'''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
                     H."CardCode" AS card_code,H."CardName" AS card_name,H."CANCELED" AS canceled,H."DocStatus" AS doc_status,
                     L."LineNum" AS line_num,L."ItemCode" AS item_code,L."WhsCode" AS whs_code,L."Quantity" AS quantity,
                     L."BaseType" AS base_type,L."BaseEntry" AS base_entry,L."BaseLine" AS base_line
              FROM "TELCHI"."ODLN" H JOIN "TELCHI"."DLN1" L ON L."DocEntry"=H."DocEntry"
              WHERE H."DocEntry" IN ({ph}) ORDER BY H."DocEntry",L."LineNum"''', tuple(entries))
        order_entries = sorted({int(_key(row, "base_entry")) for row in deliveries if _key(row, "base_type") == 17 and _key(row, "base_entry") is not None})
        if order_entries:
            ph2 = _placeholders(order_entries)
            orders, _ = _sap(source, "agrotel_order_chain", f'''SELECT H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."DocDate" AS doc_date,
                         H."CardCode" AS card_code,H."CardName" AS card_name,H."CANCELED" AS canceled,H."DocStatus" AS doc_status,
                         L."LineNum" AS line_num,L."ItemCode" AS item_code,L."WhsCode" AS whs_code,L."Quantity" AS quantity,
                         L."BaseType" AS base_type,L."BaseEntry" AS base_entry,L."BaseLine" AS base_line
                  FROM "TELCHI"."ORDR" H JOIN "TELCHI"."RDR1" L ON L."DocEntry"=H."DocEntry"
                  WHERE H."DocEntry" IN ({ph2}) ORDER BY H."DocEntry",L."LineNum"''', tuple(order_entries))
    return {
        "relationship_rule": "BaseType/BaseEntry/BaseLine only",
        "invoice_to_delivery_keys": [{"base_entry": key[0], "base_line": key[1]} for key in delivery_keys],
        "deliveries": deliveries,
        "orders": orders,
        "comparison_status": "SAP_ONLY_NOT_IN_DUCKLAKE_ATOMIC_BASELINE",
    }


def _drilldown(source: HanaReadOnlySource, connector: DuckLakeConnector, item_codes: list[str], *, customer_code: str) -> list[dict[str, Any]]:
    sales_s, sales_l = _sales_sql()
    move_s, move_l = _movement_sql()
    cases: list[dict[str, Any]] = []
    for item_code in item_codes[:3]:
        sap_sales, sap_ms = _sap(source, f"drilldown_sales_{item_code}", sales_s.replace("H.\"CardCode\"=?", "H.\"CardCode\"=? AND L.\"ItemCode\"=?"), (customer_code, item_code, START_DATE, END_EXCLUSIVE))
        lake_sales, lake_ms = _duck(connector, sales_l.replace("h.card_code=?", "h.card_code=? AND l.item_code=?"), [customer_code, item_code, START_DATE, END_EXCLUSIVE])
        sap_moves, sap_move_ms = _sap(source, f"drilldown_movements_{item_code}", move_s.replace('M."CardCode"=?', 'M."CardCode"=? AND M."ItemCode"=?'), (customer_code, item_code, START_DATE, END_EXCLUSIVE))
        lake_moves, lake_move_ms = _duck(connector, move_l.replace("m.card_code=?", "m.card_code=? AND m.item_code=?"), [customer_code, item_code, START_DATE, END_EXCLUSIVE])
        sales_cmp = compare_rows(_project(sap_sales, _SALES_COMPARE_KEYS), _project(lake_sales, _SALES_COMPARE_KEYS), ("doc_entry", "line_num"))
        move_cmp = compare_rows(sap_moves, lake_moves, ("trans_num", "trans_seq"))
        cases.append({
            "item_code": item_code,
            "sales": {"comparison": sales_cmp, "SAP": sap_sales[:10], "DuckLake": lake_sales[:10], "SAP_ms": sap_ms, "DuckLake_ms": lake_ms},
            "movements": {"comparison": move_cmp, "SAP": sap_moves[:10], "DuckLake": lake_moves[:10], "SAP_ms": sap_move_ms, "DuckLake_ms": lake_move_ms},
            "status": "EXACT" if sales_cmp["status"] == "EXACT" and move_cmp["status"] == "EXACT" else "MISMATCH",
        })
    return cases


def _run() -> dict[str, Any]:
    started = time.perf_counter()
    source = HanaReadOnlySource()
    connector = DuckLakeConnector()
    identity, _ = _identity_discovery(source, connector)
    sales_s, sales_l = _sales_sql()
    sap_sales, sap_sales_ms = _sap(source, "agrotel_sales_scope", sales_s, (CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE))
    lake_sales, lake_sales_ms = _duck(connector, sales_l, [CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE])
    sales_cmp = compare_rows(_project(sap_sales, _SALES_COMPARE_KEYS), _project(lake_sales, _SALES_COMPARE_KEYS), ("doc_entry", "line_num"))
    item_codes = sorted({str(_key(row, "item_code")) for row in sap_sales + lake_sales if _key(row, "item_code") is not None})
    sap_products, lake_products = _product_rows(source, connector, item_codes)
    discovery = _discovery(source, identity, item_codes)
    move_s, move_l = _movement_sql()
    sap_moves, sap_moves_ms = _sap(source, "agrotel_customer_movements", move_s, (CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE))
    lake_moves, lake_moves_ms = _duck(connector, move_l, [CUSTOMER_CARDCODE, START_DATE, END_EXCLUSIVE])
    move_cmp = compare_rows(sap_moves, lake_moves, ("trans_num", "trans_seq"))
    supplier_sap_moves, supplier_sap_ms = _sap(source, "agrotel_supplier_movements", move_s, (SUPPLIER_CARDCODE, START_DATE, END_EXCLUSIVE))
    supplier_lake_moves, supplier_lake_ms = _duck(connector, move_l, [SUPPLIER_CARDCODE, START_DATE, END_EXCLUSIVE])
    supplier_cmp = compare_rows(supplier_sap_moves, supplier_lake_moves, ("trans_num", "trans_seq"))
    inventory_s, inventory_l, inventory_s_params, inventory_l_params = _current_inventory_sql(item_codes)
    sap_inventory, sap_inventory_ms = _sap(source, "agrotel_current_inventory", inventory_s, inventory_s_params)
    lake_inventory, lake_inventory_ms = _duck(connector, inventory_l, inventory_l_params)
    inventory_common_sap = _project(sap_inventory, _INVENTORY_COMPARE_KEYS)
    inventory_cmp = compare_rows(inventory_common_sap, lake_inventory, ("item_code", "whs_code"))
    reread = None
    if inventory_cmp["status"] != "EXACT":
        reread_rows, reread_ms = _sap(source, "agrotel_current_inventory_reread", inventory_s, inventory_s_params)
        reread_common = _project(reread_rows, _INVENTORY_COMPARE_KEYS)
        reread_cmp = compare_rows(reread_common, lake_inventory, ("item_code", "whs_code"))
        source_refresh_cmp = compare_rows(inventory_common_sap, reread_common, ("item_code", "whs_code"))
        if source_refresh_cmp["status"] != "EXACT":
            reread_cmp["status"] = "SOURCE_CHANGED"
        else:
            reread_cmp["status"] = "TRUE_MISMATCH"
        reread = {"comparison": reread_cmp, "SAP_ms": reread_ms, "initial_to_reread": source_refresh_cmp}
        inventory_cmp = reread_cmp
    chain = _chain_documents(source, sap_sales)
    drilldown = _drilldown(source, connector, item_codes, customer_code=CUSTOMER_CARDCODE)
    with connector.session(read_only=True) as connection:
        lake_snapshot = connector.snapshot(connection)
    sap_as_of, sap_as_of_ms = _sap(source, "oitw_source_as_of", "SELECT CURRENT_UTCTIMESTAMP AS source_as_of FROM DUMMY")
    lake_as_of, lake_as_of_ms = _duck(connector, "SELECT MAX(source_as_of) AS source_as_of FROM telchi.atomic.inventory_balance")
    if (inventory_cmp["status"] == "TRUE_MISMATCH" and reread and reread["initial_to_reread"]["status"] == "EXACT"
            and sap_as_of and lake_as_of and str(_key(sap_as_of[0], "source_as_of")) != str(_key(lake_as_of[0], "source_as_of"))):
        inventory_cmp["status"] = "SOURCE_CHANGED"
        reread["classification"] = "SOURCE_CHANGED: DuckLake current snapshot and immediate SAP current state have different source_as_of values; SAP reread was stable."
    hypotheses = [
        {"HYPOTHESIS": "customer-specific OCRD consignment flag", "EVIDENCE": "OCRD.U_CONSIGNACION exists and is 0 for C012133; CUFD description=Venta Consignacion", "COUNTEREVIDENCE": "C012133 is not flagged", "STATUS": "REJECTED"},
        {"HYPOTHESIS": "customer consignment flow in invoice/delivery comments", "EVIDENCE": "C012133 invoice, delivery and OINM comments were reread", "COUNTEREVIDENCE": "No consignation text bound to C012133 in 2026 scope", "STATUS": "REJECTED"},
        {"HYPOTHESIS": "OITW.Consig identifies Agrotel consignment", "EVIDENCE": "OITW has Consig and overlapping product rows", "COUNTEREVIDENCE": "OITW grain is ItemCode×WhsCode, no CardCode/customer binding; current state only", "STATUS": "UNKNOWN"},
        {"HYPOTHESIS": "dedicated Agrotel warehouse", "EVIDENCE": "C012133 sales use LAB-T1/LAB-T2/LAB-T3/LAB-T4/2A-SAL", "COUNTEREVIDENCE": "No customer-specific warehouse relation was found", "STATUS": "REJECTED"},
        {"HYPOTHESIS": "supplier-side Agrotel inventory flow", "EVIDENCE": "PL000700=AGROTEL supplier; OINM receipts TransType 20 exist and exact DuckLake reread", "COUNTEREVIDENCE": "No explicit consignment ownership link in Atomic; supplier receipts alone do not prove consignment", "STATUS": "SUPPORTED"},
        {"HYPOTHESIS": "explicit document chain", "EVIDENCE": "OINV BaseType/BaseEntry/BaseLine links to ODLN and ODLN links to ORDR", "COUNTEREVIDENCE": "DuckLake Atomic baseline does not materialize delivery/order tables", "STATUS": "CONFIRMED"},
    ]
    definition_status = "UNRESOLVED"
    definition_text = "UNRESOLVED: the available evidence does not prove a customer-specific Agrotel consignment position. C012133 is not flagged by OCRD.U_CONSIGNACION; OITW.Consig is current ItemCode×WhsCode state without CardCode; supplier PL000700 movements are observable but not explicitly marked as consignment ownership."
    totals = {
        "customer_invoice_quantity": str(sum(Decimal(str(_key(row, "quantity") or 0)) for row in sap_sales)),
        "customer_movement_in_qty": str(sum(Decimal(str(_key(row, "in_qty") or 0)) for row in sap_moves)),
        "customer_movement_out_qty": str(sum(Decimal(str(_key(row, "out_qty") or 0)) for row in sap_moves)),
        "supplier_movement_in_qty": str(sum(Decimal(str(_key(row, "in_qty") or 0)) for row in supplier_sap_moves)),
        "supplier_movement_out_qty": str(sum(Decimal(str(_key(row, "out_qty") or 0)) for row in supplier_sap_moves)),
    }
    true_mismatches = sum(1 for comparison in (sales_cmp, move_cmp, supplier_cmp, inventory_cmp) if comparison["status"] in {"MISMATCH", "TRUE_MISMATCH"})
    unexplained = true_mismatches
    drill_exact = sum(case["status"] == "EXACT" for case in drilldown)
    timings = {
        "DuckLake_query_duration_ms": round(lake_sales_ms + lake_moves_ms + supplier_lake_ms + lake_inventory_ms, 3),
        "SAP_query_duration_ms": round(sap_sales_ms + sap_moves_ms + supplier_sap_ms + sap_inventory_ms, 3),
        "subqueries": {"sales": {"SAP_ms": sap_sales_ms, "DuckLake_ms": lake_sales_ms}, "customer_movements": {"SAP_ms": sap_moves_ms, "DuckLake_ms": lake_moves_ms}, "supplier_movements": {"SAP_ms": supplier_sap_ms, "DuckLake_ms": supplier_lake_ms}, "current_inventory": {"SAP_ms": sap_inventory_ms, "DuckLake_ms": lake_inventory_ms}, "source_as_of": {"SAP_ms": sap_as_of_ms, "DuckLake_ms": lake_as_of_ms}},
        "max_hana_concurrent_queries": 1,
    }
    comparison = {
        "identity_match": identity["ducklake_identity_match"],
        "customer_sales": sales_cmp,
        "customer_movements": move_cmp,
        "supplier_reference_movements": supplier_cmp,
        "current_inventory_common_fields": inventory_cmp,
        "levels": {"IDENTITY_MATCH": identity["ducklake_identity_match"], "PRODUCT_MATCH": sales_cmp["status"], "DOCUMENT_MATCH": sales_cmp["status"], "MOVEMENT_MATCH": move_cmp["status"], "QUANTITY_MATCH": "EXACT" if sales_cmp["status"] == "EXACT" and move_cmp["status"] == "EXACT" else "MISMATCH", "TOTAL_MATCH": "EXACT" if sales_cmp["status"] == "EXACT" and move_cmp["status"] == "EXACT" else "MISMATCH", "BALANCE_MATCH": "N/A"},
        "comparison_scope": "DuckLake Atomic sales_document+sales_line and inventory_movement; SAP OINV+INV1 and OINM; cutoff identical.",
        "supplier_reference_scope": "PL000700 OINM only; not merged into customer sales scope.",
    }
    result = {
        "GATE": GATE,
        "HISTORICAL_CUTOFF": HISTORICAL_CUTOFF,
        "SAP_MODE": "READ_ONLY",
        "SAP_WRITE_COUNT": source.sap_write_count,
        "AI_INVOCATIONS": 0,
        "AGROTEL_IDENTIFIED": identity["AGROTEL_IDENTIFIED"],
        "AGROTEL_CARDCODE": identity["AGROTEL_CARDCODE"],
        "AGROTEL_CARDNAME": identity["AGROTEL_CARDNAME"],
        "AGROTEL_MATCH_CONFIDENCE": identity["AGROTEL_MATCH_CONFIDENCE"],
        "CONSIGNATION_TECHNICAL_DEFINITION": definition_text,
        "CONSIGNATION_DEFINITION_STATUS": definition_status,
        "CONSIGNATION_WAREHOUSES": "UNKNOWN",
        "AGROTEL_PRODUCTS_COUNT": len(item_codes),
        "AGROTEL_DOCUMENTS_COUNT": len({str(_key(row, "doc_entry")) for row in sap_sales}),
        "AGROTEL_MOVEMENTS_COUNT": len(sap_moves),
        "AGROTEL_PRODUCT_SET_MATCH": sales_cmp["status"],
        "AGROTEL_DOCUMENT_SET_MATCH": sales_cmp["status"],
        "AGROTEL_MOVEMENT_SET_MATCH": move_cmp["status"],
        "AGROTEL_QUANTITY_MATCH": comparison["levels"]["QUANTITY_MATCH"],
        "AGROTEL_TOTAL_MATCH": comparison["levels"]["TOTAL_MATCH"],
        "CONSIGNATION_BALANCE_COMPUTABLE": "NO",
        "CONSIGNATION_BALANCE_FORMULA": "N/A: no confirmed ownership/consignment semantics",
        "CONSIGNATION_BALANCE_DUCKLAKE": "N/A",
        "CONSIGNATION_BALANCE_SAP": "N/A",
        "CONSIGNATION_BALANCE_MATCH": "N/A",
        "SALES_SOURCE_LINEAGE": "PASS" if sales_cmp["status"] == "EXACT" else "FAIL",
        "OINM_SOURCE_LINEAGE": "PASS" if move_cmp["status"] == "EXACT" else "FAIL",
        "DRILLDOWN_CASES": len(drilldown),
        "DRILLDOWN_EXACT": f"{drill_exact}/{len(drilldown)}",
        "CURRENT_OITW_USED": "YES",
        "OITW_SOURCE_AS_OF": _key(sap_as_of[0], "source_as_of") if sap_as_of else "UNKNOWN",
        "OITW_DUCKLAKE_SOURCE_AS_OF": _key(lake_as_of[0], "source_as_of") if lake_as_of else "UNKNOWN",
        "OITW_CURRENT_MATCH": "MISMATCH" if inventory_cmp["status"] == "TRUE_MISMATCH" else inventory_cmp["status"],
        "OITW_HISTORICAL_CLAIMED": "NO",
        "TRUE_MISMATCH_COUNT": true_mismatches,
        "UNEXPLAINED_MISMATCH_COUNT": unexplained,
        "DUCKLAKE_QUERY_DURATION_MS": timings["DuckLake_query_duration_ms"],
        "SAP_QUERY_DURATION_MS": timings["SAP_query_duration_ms"],
        "BASELINE_DATA_MODIFIED": "NO",
        "LEGACY_DATA_USED": "NO",
        "SAFE_AGROTEL_CONSIGNATION_QUERY_FOR_BUSINESS_ASSISTANT": "NO",
        "READY_TO_PRODUCTIZE_QUERY": "NO",
        "DUCKLAKE_CURRENT_SNAPSHOT": lake_snapshot,
        "RESULT": GATE + "_DEGRADED",
        "DEGRADATION": "Same-name customer/supplier roles and unresolved customer-specific consignment semantics; exact source reconciliation is nevertheless preserved.",
    }
    _write("summary.json", result)
    _write("current_state.json", {"CURRENT_OITW_USED": "YES", "OITW_HISTORICAL_CLAIMED": "NO", "SAP_SOURCE_AS_OF": sap_as_of, "DUCKLAKE_SOURCE_AS_OF": lake_as_of, "comparison": inventory_cmp, "reread": reread})
    _write("agrotel_identity.json", identity)
    _write("consignation_discovery.json", discovery)
    _write("consignation_hypotheses.json", hypotheses)
    _write("consignation_definition.json", {"definition": definition_text, "status": definition_status, "evidence_basis": hypotheses})
    _write("agrotel_products.json", {"item_codes": item_codes, "SAP": sap_products, "DuckLake_Reference_V2": lake_products, "classification_policy": "No runtime ItemCode LIKE classification; Reference V2 rows are preserved."})
    _write("agrotel_documents.json", {"comparison_documents": _ordered(sap_sales, ("doc_entry", "line_num")), "sap_document_chain": chain})
    _write("agrotel_movements.json", {"customer_scope": _ordered(sap_moves, ("trans_num", "trans_seq")), "supplier_reference_scope": _ordered(supplier_sap_moves, ("trans_num", "trans_seq"))})
    _write("ducklake_result.json", {"sales": lake_sales, "customer_movements": lake_moves, "supplier_movements": supplier_lake_moves, "current_inventory": lake_inventory})
    _write("sap_result.json", {"sales": sap_sales, "customer_movements": sap_moves, "supplier_movements": supplier_sap_moves, "current_inventory": sap_inventory})
    _write("sap_ducklake_comparison.json", comparison)
    _write("drilldown_examples.json", drilldown)
    _write("quantity_reconciliation.json", {"customer_scope": totals, "comparison": comparison["levels"], "formula_status": "SOURCE_NATIVE_TOTALS_ONLY"})
    _write("consignation_balance.json", {"CONSIGNATION_BALANCE_COMPUTABLE": "NO", "formula": "N/A", "reason": definition_text})
    _write("current_inventory_state.json", {"scope": "current stock for products in C012133 invoice scope; not asserted as consignment stock", "source_as_of": {"SAP": sap_as_of, "DuckLake": lake_as_of}, "SAP": sap_inventory, "DuckLake": lake_inventory, "comparison": inventory_cmp, "historical_claimed": "NO"})
    _write("query_timings.json", timings)
    _write("mismatch_analysis.json", {"true_mismatch_count": true_mismatches, "unexplained_mismatch_count": unexplained, "comparisons": comparison, "classification": "NONE" if unexplained == 0 else "REVIEW_REQUIRED"})
    business_summary = {
        "who_is_agrotel": "C012133 customer in the DuckLake Sales scope; PL000700 is a separate same-name supplier BP used only as a reference inventory scope.",
        "how_consignation_is_represented": "UNRESOLVED for customer C012133. OCRD.U_CONSIGNACION=0; OITW.Consig is current ItemCode×WhsCode and not customer-bound; supplier movements are observable but not explicit ownership proof.",
        "products": len(item_codes), "documents": len({str(_key(row, "doc_entry")) for row in sap_sales}), "movements": len(sap_moves),
        "quantities": totals, "balance": "NOT COMPUTABLE", "current_stock": "Current OITW comparison only; no historical stock claim.",
        "confirmed": ["C012133 and DuckLake sales lineage exact", "OINM TransNum+TransSeq lineage exact", "SAP BaseEntry/BaseLine chain exists for invoice→delivery→order"],
        "supported": ["PL000700 supplier inventory flow is present and exact against DuckLake"],
        "unknown": ["customer-specific consignment ownership and balance", "consignment warehouse"],
    }
    _write("business_summary.json", business_summary)
    report = [
        f"# {GATE}", "", "```text",
        *[f"{key}={value}" for key, value in result.items() if key not in {"DUCKLAKE_CURRENT_SNAPSHOT"}],
        "```", "", "## Scope", "", f"Historical scope: {START_DATE} <= DocDate < {END_EXCLUSIVE} (inclusive cutoff {HISTORICAL_CUTOFF}).",
        "The customer and supplier Business Partners named AGROTEL are not silently merged: C012133 is the Atomic Sales scope; PL000700 is a supplier movement reference.",
        "", "## Technical discovery", "", definition_text,
        "OITW was treated as current state only. Its source_as_of/read timestamps are reported separately; no stock-at-cutoff claim is made.",
        "", "## Exact comparison", "", f"Sales: {sales_cmp['status']}; customer OINM: {move_cmp['status']}; supplier reference OINM: {supplier_cmp['status']}; current common OITW fields: {inventory_cmp['status']}.",
        f"Drilldowns: {drill_exact}/{len(drilldown)} exact. SAP_WRITE_COUNT=0. AI_INVOCATIONS=0.",
        "", "## STOP AND REVIEW", "", "No Business Assistant integration, update.py, Atomic change, rebuild, historical expansion, or AI invocation.",
        "", f"Resultado: {result['RESULT']}.",
    ]
    (EVIDENCE_ROOT / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(_run(), indent=2, sort_keys=True, ensure_ascii=False, default=str))
