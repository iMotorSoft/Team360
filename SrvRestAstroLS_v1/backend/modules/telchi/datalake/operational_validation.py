"""Post-build validation for TELCHI_DATALAKE_2026_OPERATIONAL_BASELINE_V1.

All comparisons are bounded, sequential and read-only.  SAP and DuckLake use
separate explicit projections so equality is based on source-native facts, not
on a shared transformed result.
"""
from __future__ import annotations

import hashlib
import json
import resource
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import statistics
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .create_initial import BASELINE_EVIDENCE_ROOT, BASELINE_GATE
from .ducklake import DuckLakeConnector
from .source import HanaReadOnlySource

START = date(2026, 1, 1)
PLAN_PATH = BASELINE_EVIDENCE_ROOT / "build_plan_2026.json"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


_NUMERIC_FIELDS = {"doc_entry", "line_num", "quantity", "rows", "documents", "lines", "in_qty", "out_qty", "on_hand", "is_commited", "on_order", "trans_num", "trans_seq", "trans_type", "year", "month"}


def _normal_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in {"doc_date"}:
        return str(value)[:10]
    if key in _NUMERIC_FIELDS:
        try:
            number = Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            return format(number.normalize(), "f")
        except (InvalidOperation, ValueError):
            return str(value)
    return value


def _normalized(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{str(key).lower(): _normal_value(str(key).lower(), value) for key, value in row.items()} for row in rows]


def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [str(item[0]) for item in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _run(source: HanaReadOnlySource, connector: DuckLakeConnector, sap_sql: str, lake_sql: str, params: list[Any], query_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    sap = source._execute(query_id, sap_sql, tuple(params))
    sap_ms = round((time.perf_counter() - started) * 1000, 3)
    started = time.perf_counter()
    with connector.session(read_only=True) as connection:
        lake = _rows(connection.execute(lake_sql, params))
    lake_ms = round((time.perf_counter() - started) * 1000, 3)
    normalized_sap, normalized_lake = _normalized(sap), _normalized(lake)
    return {"query_id": query_id, "SAP_result": sap, "DuckLake_result": lake, "normalized_SAP_result": normalized_sap, "normalized_DuckLake_result": normalized_lake, "SAP_result_hash": _hash(normalized_sap), "DuckLake_result_hash": _hash(normalized_lake), "RESULT_MATCH": "EXACT" if normalized_sap == normalized_lake else "MISMATCH", "sap_ms": sap_ms, "ducklake_ms": lake_ms}


def _sample_values(source: HanaReadOnlySource, end: date) -> dict[str, Any]:
    finish = end.isoformat()
    sales = source._execute("final_sales_sample", 'SELECT TOP 1 H."DocEntry" AS "doc_entry", L."LineNum" AS "line_num", L."ItemCode" AS "item_code", L."WhsCode" AS "whs_code", H."CardCode" AS "card_code", H."DocDate" AS "doc_date" FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE H."DocDate">=? AND H."DocDate"<? ORDER BY H."DocDate", H."DocEntry", L."LineNum"', (START.isoformat(), finish))
    move = source._execute("final_oinm_sample", 'SELECT TOP 1 M."TransNum" AS "trans_num", M."TransSeq" AS "trans_seq", M."ItemCode" AS "item_code", M."Warehouse" AS "warehouse", M."TransType" AS "trans_type", M."DocDate" AS "doc_date" FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<? ORDER BY M."DocDate", M."TransNum", M."TransSeq"', (START.isoformat(), finish))
    stock = source._execute("final_oitw_sample", 'SELECT TOP 3 W."ItemCode" AS "item_code", W."WhsCode" AS "whs_code" FROM "TELCHI"."OITW" W ORDER BY W."ItemCode", W."WhsCode"')
    if not sales or not move or not stock:
        raise RuntimeError("final validation sample discovery returned no rows")
    return {"sales": sales[0], "move": move[0], "stock": stock}


def final_validation(*, source: HanaReadOnlySource | None = None, connector: DuckLakeConnector | None = None) -> dict[str, Any]:
    source = source or HanaReadOnlySource()
    connector = connector or DuckLakeConnector()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    sales_end = date.fromisoformat(plan["sales_source_max_date"]) + timedelta(days=1)
    move_end = date.fromisoformat(plan["oinm_source_max_date"]) + timedelta(days=1)
    sample = _sample_values(source, max(sales_end, move_end))
    s, m, w = sample["sales"], sample["move"], sample["stock"]
    item, whs, card = s["item_code"], s["whs_code"], s["card_code"]
    move_item, move_whs, trans_type = m["item_code"], m["warehouse"], m["trans_type"]
    stock_item, stock_whs = w[0]["item_code"], w[0]["whs_code"]
    s_from, s_to = START.isoformat(), sales_end.isoformat()
    m_from, m_to = START.isoformat(), move_end.isoformat()
    sales_base = '(H."DocDate">=? AND H."DocDate"<?)'
    line_projection = 'H."DocEntry" AS "doc_entry", L."LineNum" AS "line_num", L."ItemCode" AS "item_code", L."WhsCode" AS "whs_code", L."Quantity" AS "quantity"'
    sales = [
        ("sales_exact_document", f'SELECT {line_projection} FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE H."DocEntry"=? ORDER BY L."LineNum"', 'SELECT doc_entry,line_num,item_code,whs_code,quantity FROM telchi.atomic."sales_line" WHERE doc_entry=? ORDER BY line_num', [s["doc_entry"]]),
        ("sales_exact_lines", f'SELECT {line_projection} FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE H."DocEntry"=? AND L."LineNum"=?', 'SELECT doc_entry,line_num,item_code,whs_code,quantity FROM telchi.atomic."sales_line" WHERE doc_entry=? AND line_num=?', [s["doc_entry"], s["line_num"]]),
        ("sales_single_item", f'SELECT L."ItemCode" AS "item_code", COUNT(*) AS "rows", COALESCE(SUM(L."Quantity"),0) AS "quantity" FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE {sales_base} AND L."ItemCode"=? GROUP BY L."ItemCode"', 'SELECT item_code,COUNT(*) AS "rows",COALESCE(SUM(CAST(quantity AS DOUBLE)),0) AS quantity FROM telchi.atomic."sales_line" l JOIN telchi.atomic."sales_document" h ON h.doc_entry=l.doc_entry WHERE h.doc_date>=? AND h.doc_date<? AND l.item_code=? GROUP BY item_code', [s_from,s_to,item]),
        ("sales_warehouse", f'SELECT L."WhsCode" AS "whs_code", COUNT(*) AS "rows", COALESCE(SUM(L."Quantity"),0) AS "quantity" FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE {sales_base} AND L."WhsCode"=? GROUP BY L."WhsCode"', 'SELECT whs_code,COUNT(*) AS "rows",COALESCE(SUM(CAST(quantity AS DOUBLE)),0) AS quantity FROM telchi.atomic."sales_line" l JOIN telchi.atomic."sales_document" h ON h.doc_entry=l.doc_entry WHERE h.doc_date>=? AND h.doc_date<? AND l.whs_code=? GROUP BY whs_code', [s_from,s_to,whs]),
        ("sales_day_aggregate", f'SELECT H."DocDate" AS "doc_date", COUNT(DISTINCT H."DocEntry") AS "documents", COUNT(L."LineNum") AS "lines", COALESCE(SUM(L."Quantity"),0) AS "quantity" FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE {sales_base} AND H."DocDate"=? GROUP BY H."DocDate"', 'SELECT h.doc_date,COUNT(DISTINCT h.doc_entry) AS documents,COUNT(l.line_num) AS lines,COALESCE(SUM(CAST(l.quantity AS DOUBLE)),0) AS quantity FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry WHERE h.doc_date>=? AND h.doc_date<? AND h.doc_date=? GROUP BY h.doc_date', [s_from,s_to,str(s["doc_date"])]),
        ("sales_month_aggregate", f'SELECT YEAR(H."DocDate") AS "year", MONTH(H."DocDate") AS "month", COUNT(DISTINCT H."DocEntry") AS "documents", COALESCE(SUM(L."Quantity"),0) AS "quantity" FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE {sales_base} GROUP BY YEAR(H."DocDate"),MONTH(H."DocDate") ORDER BY 1,2', 'SELECT CAST(substr(h.doc_date,1,4) AS INTEGER) AS year,CAST(substr(h.doc_date,6,2) AS INTEGER) AS month,COUNT(DISTINCT h.doc_entry) AS documents,COALESCE(SUM(CAST(l.quantity AS DOUBLE)),0) AS quantity FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry WHERE h.doc_date>=? AND h.doc_date<? GROUP BY 1,2 ORDER BY 1,2', [s_from,s_to]),
        ("sales_multiple_months", f'SELECT YEAR(H."DocDate") AS "year", COUNT(DISTINCT H."DocEntry") AS "documents" FROM "TELCHI"."OINV" H WHERE {sales_base} GROUP BY YEAR(H."DocDate") ORDER BY 1', 'SELECT CAST(substr(doc_date,1,4) AS INTEGER) AS year,COUNT(DISTINCT doc_entry) AS documents FROM telchi.atomic."sales_document" WHERE doc_date>=? AND doc_date<? GROUP BY 1 ORDER BY 1', [s_from,s_to]),
        ("sales_customer_scope", f'SELECT H."CardCode" AS "card_code", COUNT(DISTINCT H."DocEntry") AS "documents", COALESCE(SUM(L."Quantity"),0) AS "quantity" FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE {sales_base} AND H."CardCode"=? GROUP BY H."CardCode"', 'SELECT h.card_code,COUNT(DISTINCT h.doc_entry) AS documents,COALESCE(SUM(CAST(l.quantity AS DOUBLE)),0) AS quantity FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry WHERE h.doc_date>=? AND h.doc_date<? AND h.card_code=? GROUP BY h.card_code', [s_from,s_to,card]),
        ("sales_customer_warehouse", f'SELECT H."CardCode" AS "card_code", L."WhsCode" AS "whs_code", COUNT(*) AS "lines", COALESCE(SUM(L."Quantity"),0) AS "quantity" FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE {sales_base} AND H."CardCode"=? AND L."WhsCode"=? GROUP BY H."CardCode",L."WhsCode"', 'SELECT h.card_code,l.whs_code,COUNT(*) AS lines,COALESCE(SUM(CAST(l.quantity AS DOUBLE)),0) AS quantity FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry WHERE h.doc_date>=? AND h.doc_date<? AND h.card_code=? AND l.whs_code=? GROUP BY h.card_code,l.whs_code', [s_from,s_to,card,whs]),
        ("sales_ytd_aggregate", f'SELECT COUNT(DISTINCT H."DocEntry") AS "documents", COUNT(L."LineNum") AS "lines", COALESCE(SUM(L."Quantity"),0) AS "quantity" FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE {sales_base}', 'SELECT COUNT(DISTINCT h.doc_entry) AS documents,COUNT(l.line_num) AS lines,COALESCE(SUM(CAST(l.quantity AS DOUBLE)),0) AS quantity FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry WHERE h.doc_date>=? AND h.doc_date<?', [s_from,s_to]),
    ]
    movement_projection = 'M."TransNum" AS "trans_num", M."TransSeq" AS "trans_seq", M."TransType" AS "trans_type", M."ItemCode" AS "item_code", M."Warehouse" AS "warehouse", M."InQty" AS "in_qty", M."OutQty" AS "out_qty"'
    movement = [
        ("oinm_exact_movement", f'SELECT {movement_projection} FROM "TELCHI"."OINM" M WHERE M."TransNum"=? AND M."TransSeq"=?', 'SELECT trans_num,trans_seq,trans_type,item_code,warehouse,in_qty AS in_qty,out_qty AS out_qty FROM telchi.atomic."inventory_movement" WHERE trans_num=? AND trans_seq=?', [m["trans_num"],m["trans_seq"]]),
        ("oinm_item_history", f'SELECT M."ItemCode" AS item_code,COUNT(*) AS rows,COALESCE(SUM(M."InQty"),0) AS in_qty,COALESCE(SUM(M."OutQty"),0) AS out_qty FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<? AND M."ItemCode"=? GROUP BY M."ItemCode"', 'SELECT item_code,COUNT(*) AS rows,COALESCE(SUM(CAST(in_qty AS DOUBLE)),0) AS in_qty,COALESCE(SUM(CAST(out_qty AS DOUBLE)),0) AS out_qty FROM telchi.atomic."inventory_movement" WHERE doc_date>=? AND doc_date<? AND item_code=? GROUP BY item_code', [m_from,m_to,move_item]),
        ("oinm_warehouse_history", f'SELECT M."Warehouse" AS warehouse,COUNT(*) AS rows FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<? AND M."Warehouse"=? GROUP BY M."Warehouse"', 'SELECT warehouse,COUNT(*) AS rows FROM telchi.atomic."inventory_movement" WHERE doc_date>=? AND doc_date<? AND warehouse=? GROUP BY warehouse', [m_from,m_to,move_whs]),
        ("oinm_item_warehouse", f'SELECT COUNT(*) AS rows,COALESCE(SUM(M."InQty"),0) AS in_qty,COALESCE(SUM(M."OutQty"),0) AS out_qty FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<? AND M."ItemCode"=? AND M."Warehouse"=?', 'SELECT COUNT(*) AS rows,COALESCE(SUM(CAST(in_qty AS DOUBLE)),0) AS in_qty,COALESCE(SUM(CAST(out_qty AS DOUBLE)),0) AS out_qty FROM telchi.atomic."inventory_movement" WHERE doc_date>=? AND doc_date<? AND item_code=? AND warehouse=?', [m_from,m_to,move_item,move_whs]),
        ("oinm_trans_type", f'SELECT M."TransType" AS trans_type,COUNT(*) AS rows FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<? AND M."TransType"=? GROUP BY M."TransType"', 'SELECT trans_type,COUNT(*) AS rows FROM telchi.atomic."inventory_movement" WHERE doc_date>=? AND doc_date<? AND trans_type=? GROUP BY trans_type', [m_from,m_to,trans_type]),
        ("oinm_day_aggregate", f'SELECT M."DocDate" AS doc_date,COUNT(*) AS rows,COALESCE(SUM(M."InQty"),0) AS in_qty,COALESCE(SUM(M."OutQty"),0) AS out_qty FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<? AND M."DocDate"=? GROUP BY M."DocDate"', 'SELECT doc_date,COUNT(*) AS rows,COALESCE(SUM(CAST(in_qty AS DOUBLE)),0) AS in_qty,COALESCE(SUM(CAST(out_qty AS DOUBLE)),0) AS out_qty FROM telchi.atomic."inventory_movement" WHERE doc_date>=? AND doc_date<? AND doc_date=? GROUP BY doc_date', [m_from,m_to,str(m["doc_date"])]),
        ("oinm_month_aggregate", f'SELECT YEAR(M."DocDate") AS year,MONTH(M."DocDate") AS month,COUNT(*) AS rows FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<? GROUP BY YEAR(M."DocDate"),MONTH(M."DocDate") ORDER BY 1,2', 'SELECT CAST(substr(doc_date,1,4) AS INTEGER) AS year,CAST(substr(doc_date,6,2) AS INTEGER) AS month,COUNT(*) AS rows FROM telchi.atomic."inventory_movement" WHERE doc_date>=? AND doc_date<? GROUP BY 1,2 ORDER BY 1,2', [m_from,m_to]),
        ("oinm_multiple_months", f'SELECT YEAR(M."DocDate") AS year,COUNT(*) AS rows FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<? GROUP BY YEAR(M."DocDate") ORDER BY 1', 'SELECT CAST(substr(doc_date,1,4) AS INTEGER) AS year,COUNT(*) AS rows FROM telchi.atomic."inventory_movement" WHERE doc_date>=? AND doc_date<? GROUP BY 1 ORDER BY 1', [m_from,m_to]),
        ("oinm_totals", f'SELECT COALESCE(SUM(M."InQty"),0) AS in_qty,COALESCE(SUM(M."OutQty"),0) AS out_qty FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<?', 'SELECT COALESCE(SUM(CAST(in_qty AS DOUBLE)),0) AS in_qty,COALESCE(SUM(CAST(out_qty AS DOUBLE)),0) AS out_qty FROM telchi.atomic."inventory_movement" WHERE doc_date>=? AND doc_date<?', [m_from,m_to]),
        ("oinm_source_drilldown", f'SELECT {movement_projection} FROM "TELCHI"."OINM" M WHERE M."TransNum"=? AND M."TransSeq"=?', 'SELECT trans_num,trans_seq,trans_type,item_code,warehouse,in_qty,out_qty FROM telchi.atomic."inventory_movement" WHERE trans_num=? AND trans_seq=?', [m["trans_num"],m["trans_seq"]]),
    ]
    stock2 = w[1] if len(w)>1 else w[0]
    inventory = [
        ("oitw_exact_item_warehouse", 'SELECT W."ItemCode" AS item_code,W."WhsCode" AS whs_code,W."OnHand" AS on_hand,W."IsCommited" AS is_commited,W."OnOrder" AS on_order FROM "TELCHI"."OITW" W WHERE W."ItemCode"=? AND W."WhsCode"=?', 'SELECT item_code,whs_code,on_hand,is_commited,on_order FROM telchi.atomic."inventory_balance" WHERE item_code=? AND whs_code=?', [stock_item,stock_whs]),
        ("oitw_same_item_warehouses", 'SELECT W."ItemCode" AS item_code,W."WhsCode" AS whs_code,W."OnHand" AS on_hand,W."IsCommited" AS is_commited,W."OnOrder" AS on_order FROM "TELCHI"."OITW" W WHERE W."ItemCode"=? ORDER BY W."WhsCode"', 'SELECT item_code,whs_code,on_hand,is_commited,on_order FROM telchi.atomic."inventory_balance" WHERE item_code=? ORDER BY whs_code', [stock_item]),
        ("oitw_warehouse_items", 'SELECT W."ItemCode" AS item_code,W."WhsCode" AS whs_code,W."OnHand" AS on_hand FROM "TELCHI"."OITW" W WHERE W."WhsCode"=? ORDER BY W."ItemCode" LIMIT 20', 'SELECT item_code,whs_code,on_hand FROM telchi.atomic."inventory_balance" WHERE whs_code=? ORDER BY item_code LIMIT 20', [stock_whs]),
        ("oitw_onhand", 'SELECT COALESCE(SUM(W."OnHand"),0) AS on_hand FROM "TELCHI"."OITW" W WHERE W."ItemCode"=?', 'SELECT COALESCE(SUM(CAST(on_hand AS DOUBLE)),0) AS on_hand FROM telchi.atomic."inventory_balance" WHERE item_code=?', [stock_item]),
        ("oitw_committed", 'SELECT COALESCE(SUM(W."IsCommited"),0) AS is_commited FROM "TELCHI"."OITW" W WHERE W."ItemCode"=?', 'SELECT COALESCE(SUM(CAST(is_commited AS DOUBLE)),0) AS is_commited FROM telchi.atomic."inventory_balance" WHERE item_code=?', [stock_item]),
        ("oitw_onorder", 'SELECT COALESCE(SUM(W."OnOrder"),0) AS on_order FROM "TELCHI"."OITW" W WHERE W."ItemCode"=?', 'SELECT COALESCE(SUM(CAST(on_order AS DOUBLE)),0) AS on_order FROM telchi.atomic."inventory_balance" WHERE item_code=?', [stock_item]),
        ("oitw_small_scope", 'SELECT COUNT(*) AS rows,COALESCE(SUM(W."OnHand"),0) AS on_hand,COALESCE(SUM(W."IsCommited"),0) AS is_commited,COALESCE(SUM(W."OnOrder"),0) AS on_order FROM "TELCHI"."OITW" W WHERE W."ItemCode" IN (?,?)', 'SELECT COUNT(*) AS rows,COALESCE(SUM(CAST(on_hand AS DOUBLE)),0) AS on_hand,COALESCE(SUM(CAST(is_commited AS DOUBLE)),0) AS is_commited,COALESCE(SUM(CAST(on_order AS DOUBLE)),0) AS on_order FROM telchi.atomic."inventory_balance" WHERE item_code IN (?,?)', [stock_item,stock2["item_code"]]),
        ("oitw_two_item_warehouses", 'SELECT "ItemCode" AS item_code,"WhsCode" AS whs_code,"OnHand" AS on_hand,"IsCommited" AS is_commited,"OnOrder" AS on_order FROM "TELCHI"."OITW" WHERE ("ItemCode"=? AND "WhsCode"=?) OR ("ItemCode"=? AND "WhsCode"=?) ORDER BY "ItemCode","WhsCode"', 'SELECT item_code,whs_code,on_hand,is_commited,on_order FROM telchi.atomic."inventory_balance" WHERE (item_code=? AND whs_code=?) OR (item_code=? AND whs_code=?) ORDER BY item_code,whs_code', [stock_item,stock_whs,stock2["item_code"],stock2["whs_code"]]),
        ("oitw_stock_warehouse", 'SELECT W."WhsCode" AS whs_code,COUNT(*) AS rows,COALESCE(SUM(W."OnHand"),0) AS on_hand FROM "TELCHI"."OITW" W WHERE W."WhsCode"=? GROUP BY W."WhsCode"', 'SELECT whs_code,COUNT(*) AS rows,COALESCE(SUM(CAST(on_hand AS DOUBLE)),0) AS on_hand FROM telchi.atomic."inventory_balance" WHERE whs_code=? GROUP BY whs_code', [stock_whs]),
        ("oitw_source_drilldown", 'SELECT W."ItemCode" AS item_code,W."WhsCode" AS whs_code,W."OnHand" AS on_hand,W."IsCommited" AS is_commited,W."OnOrder" AS on_order FROM "TELCHI"."OITW" W WHERE W."ItemCode"=? AND W."WhsCode"=?', 'SELECT item_code,whs_code,on_hand,is_commited,on_order FROM telchi.atomic."inventory_balance" WHERE item_code=? AND whs_code=?', [stock_item,stock_whs]),
    ]
    def run_group(definitions: list[tuple[str,str,str,list[Any]]]) -> list[dict[str, Any]]:
        out = []
        for query_id, sap_sql, lake_sql, params in definitions:
            out.append(_run(source, connector, sap_sql, lake_sql, params, query_id))
        return out
    sales_results, movement_results, inventory_results = run_group(sales), run_group(movement), run_group(inventory)
    _write(BASELINE_EVIDENCE_ROOT / "sales_final_10x.json", {"checks": sales_results, "exact": sum(x["RESULT_MATCH"] == "EXACT" for x in sales_results), "total": 10})
    _write(BASELINE_EVIDENCE_ROOT / "oinm_final_10x.json", {"checks": movement_results, "exact": sum(x["RESULT_MATCH"] == "EXACT" for x in movement_results), "total": 10})
    _write(BASELINE_EVIDENCE_ROOT / "oitw_final_10x.json", {"checks": inventory_results, "exact": sum(x["RESULT_MATCH"] == "EXACT" for x in inventory_results), "total": 10})
    return {"sales": sales_results, "oinm": movement_results, "oitw": inventory_results, "samples": sample}


def local_queries(*, connector: DuckLakeConnector | None = None) -> dict[str, Any]:
    connector = connector or DuckLakeConnector()
    definitions = [
        ("sales_product_period", 'SELECT l.item_code,SUM(CAST(l.quantity AS DOUBLE)) AS quantity FROM telchi.atomic."sales_line" l JOIN telchi.atomic."sales_document" h ON l.doc_entry=h.doc_entry WHERE substr(h.doc_date,1,4)=\'2026\' AND l.item_code IS NOT NULL GROUP BY l.item_code ORDER BY quantity DESC LIMIT 10'),
        ("sales_by_warehouse", 'SELECT l.whs_code,SUM(CAST(l.quantity AS DOUBLE)) AS quantity FROM telchi.atomic."sales_line" l JOIN telchi.atomic."sales_document" h ON l.doc_entry=h.doc_entry WHERE substr(h.doc_date,1,4)=\'2026\' GROUP BY l.whs_code ORDER BY quantity DESC'),
        ("top_products_quantity", 'SELECT l.item_code,SUM(CAST(l.quantity AS DOUBLE)) AS quantity FROM telchi.atomic."sales_line" l JOIN telchi.atomic."sales_document" h ON l.doc_entry=h.doc_entry WHERE substr(h.doc_date,1,4)=\'2026\' GROUP BY l.item_code ORDER BY quantity DESC LIMIT 10'),
        ("movement_product", 'SELECT item_code,SUM(CAST(in_qty AS DOUBLE)) AS in_qty,SUM(CAST(out_qty AS DOUBLE)) AS out_qty FROM telchi.atomic."inventory_movement" WHERE substr(doc_date,1,4)=\'2026\' GROUP BY item_code ORDER BY item_code LIMIT 10'),
        ("stock_product", 'SELECT item_code,SUM(CAST(on_hand AS DOUBLE)) AS on_hand FROM telchi.atomic."inventory_balance" GROUP BY item_code ORDER BY item_code LIMIT 10'),
        ("stock_warehouse", 'SELECT whs_code,SUM(CAST(on_hand AS DOUBLE)) AS on_hand FROM telchi.atomic."inventory_balance" GROUP BY whs_code ORDER BY whs_code'),
        ("sales_monthly_ytd", 'SELECT substr(h.doc_date,1,7) AS month,SUM(CAST(l.quantity AS DOUBLE)) AS quantity FROM telchi.atomic."sales_line" l JOIN telchi.atomic."sales_document" h ON l.doc_entry=h.doc_entry WHERE substr(h.doc_date,1,4)=\'2026\' GROUP BY 1 ORDER BY 1'),
        ("movement_monthly_ytd", 'SELECT substr(doc_date,1,7) AS month,SUM(CAST(in_qty AS DOUBLE)) AS in_qty,SUM(CAST(out_qty AS DOUBLE)) AS out_qty FROM telchi.atomic."inventory_movement" WHERE substr(doc_date,1,4)=\'2026\' GROUP BY 1 ORDER BY 1'),
        ("sales_customer_summary", 'SELECT h.card_code,COUNT(DISTINCT h.doc_entry) AS documents,SUM(CAST(l.quantity AS DOUBLE)) AS quantity FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry WHERE substr(h.doc_date,1,4)=\'2026\' GROUP BY h.card_code ORDER BY quantity DESC LIMIT 10'),
        ("movement_warehouse_summary", 'SELECT warehouse,COUNT(*) AS rows,SUM(CAST(in_qty AS DOUBLE)) AS in_qty,SUM(CAST(out_qty AS DOUBLE)) AS out_qty FROM telchi.atomic."inventory_movement" WHERE substr(doc_date,1,4)=\'2026\' GROUP BY warehouse ORDER BY rows DESC LIMIT 10'),
    ]
    rows: list[dict[str, Any]] = []
    timings: list[float] = []
    with connector.session(read_only=True) as connection:
        for query_id, sql in definitions:
            t0=time.perf_counter(); result=_rows(connection.execute(sql)); elapsed=(time.perf_counter()-t0)*1000; timings.append(elapsed); rows.append({"query_id":query_id,"result":result,"duration_ms":round(elapsed,3)})
    ordered=sorted(timings)
    result={"count":len(rows),"queries":rows,"cold_ms":timings[0] if timings else None,"warm_p50_ms":ordered[len(ordered)//2] if ordered else None,"warm_p95_ms":ordered[min(len(ordered)-1,int(len(ordered)*.95))] if ordered else None}
    _write(BASELINE_EVIDENCE_ROOT / "business_query_suite.json", result)
    _write(BASELINE_EVIDENCE_ROOT / "query_performance.json", result)
    return result


def benchmark(*, source: HanaReadOnlySource | None = None, connector: DuckLakeConnector | None = None) -> dict[str, Any]:
    source=source or HanaReadOnlySource(); connector=connector or DuckLakeConnector(); plan=json.loads(PLAN_PATH.read_text(encoding="utf-8")); end=(date.fromisoformat(plan["sales_source_max_date"])+timedelta(days=1)).isoformat(); params=[START.isoformat(),end]
    stock_sample = _sample_values(source, date.fromisoformat(plan["sales_source_max_date"]))["stock"][0]
    definitions=[
      ("sales_ytd", 'SELECT H."DocDate" AS doc_date,COUNT(*) AS lines,COALESCE(SUM(L."Quantity"),0) AS quantity FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE H."DocDate">=? AND H."DocDate"<? GROUP BY H."DocDate" ORDER BY H."DocDate"', 'SELECT h.doc_date,COUNT(*) AS lines,COALESCE(SUM(CAST(l.quantity AS DOUBLE)),0) AS quantity FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry WHERE h.doc_date>=? AND h.doc_date<? GROUP BY h.doc_date ORDER BY h.doc_date'),
      ("oinm_ytd", 'SELECT M."DocDate" AS doc_date,COUNT(*) AS rows,COALESCE(SUM(M."InQty"),0) AS in_qty,COALESCE(SUM(M."OutQty"),0) AS out_qty FROM "TELCHI"."OINM" M WHERE M."DocDate">=? AND M."DocDate"<? GROUP BY M."DocDate" ORDER BY M."DocDate"', 'SELECT doc_date,COUNT(*) AS rows,COALESCE(SUM(CAST(in_qty AS DOUBLE)),0) AS in_qty,COALESCE(SUM(CAST(out_qty AS DOUBLE)),0) AS out_qty FROM telchi.atomic."inventory_movement" WHERE doc_date>=? AND doc_date<? GROUP BY doc_date ORDER BY doc_date'),
      ("oitw_state", 'SELECT W."ItemCode" AS item_code,W."WhsCode" AS whs_code,W."OnHand" AS on_hand,W."IsCommited" AS is_commited,W."OnOrder" AS on_order FROM "TELCHI"."OITW" W WHERE W."ItemCode"=? AND W."WhsCode"=?', 'SELECT item_code,whs_code,on_hand,is_commited,on_order FROM telchi.atomic."inventory_balance" WHERE item_code=? AND whs_code=?'),
    ]
    output=[]
    for query_id,sap_sql,lake_sql in definitions:
        query_params = params if query_id != "oitw_state" else [stock_sample["item_code"], stock_sample["whs_code"]]
        one=_run(source,connector,sap_sql,lake_sql,query_params,query_id)
        sap_times=[]; lake_times=[]
        for _ in range(2):
            t=time.perf_counter(); source._execute(query_id+"_warm",sap_sql,tuple(query_params)); sap_times.append((time.perf_counter()-t)*1000)
        with connector.session(read_only=True) as connection:
            for _ in range(3):
                t=time.perf_counter(); connection.execute(lake_sql,query_params).fetchall(); lake_times.append((time.perf_counter()-t)*1000)
        output.append({**one,"definition":query_id,"scope":"2026 YTD" if query_id != "oitw_state" else "current OITW","SAP_timings_ms":sap_times,"DuckLake_timings_ms":lake_times,"status":"EXACT" if one["RESULT_MATCH"]=="EXACT" else "MISMATCH"})
    _write(BASELINE_EVIDENCE_ROOT / "sap_vs_ducklake_benchmark.json", {"queries":output,"exact":sum(x["status"]=="EXACT" for x in output),"total":3,"concurrency":"SEQUENTIAL"})
    return {"queries":output,"exact":sum(x["status"]=="EXACT" for x in output),"total":3}


def run_all() -> dict[str, Any]:
    source=HanaReadOnlySource(); connector=DuckLakeConnector(); started=time.perf_counter(); final=final_validation(source=source,connector=connector); local=local_queries(connector=connector); bench=benchmark(source=source,connector=connector); duration={"BUILD_STARTED_AT":None,"BUILD_FINISHED_AT":None,"TOTAL_VALIDATION_DURATION_SECONDS":round(time.perf_counter()-started,3),"peak_rss_kb":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}; _write(BASELINE_EVIDENCE_ROOT/"build_duration.json",duration); return {"final":final,"local":local,"benchmark":bench,"duration":duration}


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2, sort_keys=True, default=str))
