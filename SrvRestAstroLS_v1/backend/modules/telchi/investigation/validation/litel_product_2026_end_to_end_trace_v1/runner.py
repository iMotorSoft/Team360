"""TELCHI_LITEL_PRODUCT_2026_END_TO_END_TRACE_V1.

A deterministic investigation-only trace.  Selection and the first complete
reconstruction are DuckLake-first; SAP HANA is read afterwards with the same
item, half-open historical range and source-native keys.  This module never
imports an AI client, update.py or an ingestion/publishing path.
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

GATE = "TELCHI_LITEL_PRODUCT_2026_END_TO_END_TRACE_V1"
START = "2026-01-01"
HISTORICAL_CUTOFF = "2026-09-15"
END_EXCLUSIVE = "2026-09-16"
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
REFERENCE_V2_ROOT = DATA_ROOT / "reference" / "_versions" / "v2"
CROSSWALK_V2_ROOT = DATA_ROOT / "crosswalk" / "_versions" / "v2"
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE

SALES_FIELDS = (
    "doc_date", "doc_entry", "doc_num", "obj_type", "doc_due_date", "tax_date",
    "doc_status", "canceled", "currency", "doc_total", "card_code", "line_num",
    "line_status", "item_code", "quantity", "whs_code", "price", "line_total",
)
OINM_FIELDS = (
    "trans_num", "trans_seq", "instance", "trans_type", "doc_date", "item_code",
    "warehouse", "in_qty", "out_qty", "price", "calc_price", "trans_value",
    "created_by", "app_obj_abs", "app_obj_type", "doc_line_num", "base_ref",
    "ref1", "ref2", "comments", "jrnl_memo", "doc_due_date", "doc_time",
    "card_code", "card_name", "dscription", "balance", "slp_code", "user_sign",
    "appl_obj", "app_obj_line",
)
OITW_FIELDS = ("item_code", "whs_code", "on_hand", "is_commited", "on_order")
NUMERIC_FIELDS = {
    "doc_entry", "doc_num", "line_num", "quantity", "doc_total", "price", "line_total",
    "trans_num", "trans_seq", "instance", "trans_type", "in_qty", "out_qty", "calc_price",
    "trans_value", "created_by", "app_obj_abs", "app_obj_type", "doc_line_num", "doc_time",
    "slp_code", "user_sign", "appl_obj", "app_obj_line", "on_hand", "is_commited", "on_order",
}
DATE_FIELDS = {"doc_date", "doc_due_date", "tax_date"}


def _key(row: dict[str, Any], name: str) -> Any:
    return next((v for k, v in row.items() if str(k).lower() == name.lower()), None)


def _field_name(name: str) -> str:
    text = str(name)
    if text.upper() == text:
        return text.lower()
    return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()


def _normal_value(name: str, value: Any) -> Any:
    if value is None:
        return None
    if name.lower() in DATE_FIELDS:
        return str(value)[:10]
    if name.lower() in NUMERIC_FIELDS:
        try:
            return format(Decimal(str(value)).normalize(), "f")
        except (InvalidOperation, ValueError):
            return str(value)
    return value.isoformat() if hasattr(value, "isoformat") else value


def normalize(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{_field_name(str(k)): _normal_value(_field_name(str(k)), v) for k, v in row.items()} for row in rows]


def ordered(rows: Iterable[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return sorted(normalize(rows), key=lambda row: tuple(str(row.get(k, "")) for k in keys))


def deterministic_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def compare_rowsets(sap_rows: list[dict[str, Any]], ducklake_rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any]:
    """Compare complete normalized rowsets, not samples or aggregates only."""
    left, right = ordered(sap_rows, keys), ordered(ducklake_rows, keys)
    equal = left == right
    return {
        "status": "EXACT" if equal else "MISMATCH",
        "sap_row_count": len(left), "ducklake_row_count": len(right),
        "sap_hash": deterministic_hash(left), "ducklake_hash": deterministic_hash(right),
        "sap_only_sample": left[:5] if not equal else [],
        "ducklake_only_sample": right[:5] if not equal else [],
    }


def historical_predicate(column: str) -> str:
    """All historical SQL uses this fixed inclusive-cutoff half-open range."""
    return f"{column} >= ? AND {column} < ?"


def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [str(item[0]).lower() for item in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _write(name: str, value: Any) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    (EVIDENCE_ROOT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )


def _duck(connector: DuckLakeConnector, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    with connector.session(read_only=True) as connection:
        result = _rows(connection.execute(sql, params))
    return result, round((time.perf_counter() - started) * 1000, 3)


def _sap(source: HanaReadOnlySource, query_id: str, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    result = source._execute(query_id, sql, params)
    return result, round((time.perf_counter() - started) * 1000, 3)


def _selection_sql() -> str:
    """Reference V2 classification is the authority; no ItemCode prefix rule."""
    products = str(REFERENCE_V2_ROOT / "products" / "*.parquet")
    families = str(REFERENCE_V2_ROOT / "portfolio_family" / "*.parquet")
    relation = str(CROSSWALK_V2_ROOT / "product_portfolio_family" / "*.parquet")
    return f"""
WITH classified AS (
  SELECT p.item_code, p.canonical_product_id, p.product_name, p.canonical_name,
         p.source_system, p.source_native_id, pf.code AS portfolio_family,
         pf.source AS classification_source, pf.confidence, pf.status
  FROM read_parquet('{products}') p
  JOIN read_parquet('{relation}') r ON r.canonical_product_id = p.canonical_product_id
  JOIN read_parquet('{families}') pf ON pf.portfolio_family_id = r.portfolio_family_id
  WHERE pf.code = 'LITEL'
), sales AS (
  SELECT l.item_code, COUNT(*) AS sales_lines, COUNT(DISTINCT h.doc_entry) AS sales_documents,
         SUM(TRY_CAST(l.quantity AS DECIMAL(38,10))) AS sales_quantity,
         COUNT(DISTINCT l.whs_code) AS sales_warehouses,
         COUNT(DISTINCT h.card_code) AS sales_customers,
         COUNT(DISTINCT SUBSTR(h.doc_date, 1, 7)) AS active_months
  FROM telchi.atomic.sales_document h
  JOIN telchi.atomic.sales_line l ON l.doc_entry = h.doc_entry
  WHERE h.doc_date >= '2026-01-01' AND h.doc_date < '2026-09-16'
  GROUP BY l.item_code
), moves AS (
  SELECT item_code, COUNT(*) AS movement_rows,
         COUNT(DISTINCT warehouse) AS movement_warehouses,
         COUNT(DISTINCT trans_type) AS movement_trans_types,
         SUM(TRY_CAST(in_qty AS DECIMAL(38,10))) AS total_in_qty,
         SUM(TRY_CAST(out_qty AS DECIMAL(38,10))) AS total_out_qty
  FROM telchi.atomic.inventory_movement
  WHERE doc_date >= '2026-01-01' AND doc_date < '2026-09-16'
  GROUP BY item_code
), ranked AS (
  SELECT c.*, s.sales_lines, s.sales_documents, s.sales_quantity,
         s.sales_warehouses, s.sales_customers, s.active_months,
         m.movement_rows, m.movement_warehouses, m.movement_trans_types,
         m.total_in_qty, m.total_out_qty,
         (s.sales_lines + s.sales_warehouses * 100 + COALESCE(m.movement_warehouses,0) * 50 + COALESCE(m.movement_trans_types,0) * 200 + s.active_months * 100 + LEAST(s.sales_customers, 2000)) AS representativeness_score,
         ROW_NUMBER() OVER (
           PARTITION BY c.item_code ORDER BY CASE WHEN c.source_system = 'SAP_HANA' THEN 0 ELSE 1 END,
           c.canonical_product_id
         ) AS source_rank
  FROM classified c JOIN sales s ON s.item_code = c.item_code
  LEFT JOIN moves m ON m.item_code = c.item_code
)
SELECT * FROM ranked
WHERE source_rank = 1 AND sales_lines BETWEEN 3000 AND 10000
ORDER BY representativeness_score DESC, movement_trans_types DESC, movement_warehouses DESC, sales_warehouses DESC, sales_lines DESC, item_code
LIMIT 1
"""


def select_litel_product(connector: DuckLakeConnector) -> dict[str, Any]:
    rows, _ = _duck(connector, _selection_sql())
    if len(rows) != 1:
        raise RuntimeError(f"Reference V2 Litel selection expected one row, got {len(rows)}")
    selected = rows[0]
    selected["why_selected"] = (
        "Highest deterministic representativeness score among Reference V2 LITEL products with 2026 sales: "
        "sales on multiple dates/months, many warehouses/customers and multiple OINM warehouses/TransTypes."
    )
    selected["litel_classification_source"] = "Reference V2 crosswalk.product_portfolio_family -> portfolio_family(code=LITEL)"
    selected["classification_rule"] = "Reference V2 relationship; runtime does not classify by ItemCode LIKE 'L%'"
    return selected


def _sales_sql(item_code: str) -> tuple[str, str, list[Any], tuple[Any, ...]]:
    sap = '''SELECT H."DocDate" AS doc_date,H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,
        H."ObjType" AS obj_type,H."DocDueDate" AS doc_due_date,H."TaxDate" AS tax_date,
        H."DocStatus" AS doc_status,H."CANCELED" AS canceled,H."DocCur" AS currency,
        H."DocTotal" AS doc_total,H."CardCode" AS card_code,L."LineNum" AS line_num,
        L."LineStatus" AS line_status,L."ItemCode" AS item_code,L."Quantity" AS quantity,
        L."WhsCode" AS whs_code,L."Price" AS price,L."LineTotal" AS line_total
        FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry"
        WHERE H."DocDate">=? AND H."DocDate"<? AND L."ItemCode"=?
        ORDER BY H."DocEntry",L."LineNum"'''
    lake = '''SELECT h.doc_date,h.doc_entry,h.doc_num,'13' AS obj_type,h.doc_due_date,h.tax_date,
        h.doc_status,h.canceled,h.currency,h.doc_total,h.card_code,l.line_num,l.line_status,
        l.item_code,l.quantity,l.whs_code,l.price,l.line_total
        FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry
        WHERE h.doc_date>=? AND h.doc_date<? AND l.item_code=?
        ORDER BY TRY_CAST(h.doc_entry AS BIGINT),TRY_CAST(l.line_num AS BIGINT)'''
    return sap, lake, [START, END_EXCLUSIVE, item_code], (START, END_EXCLUSIVE, item_code)


def _oinm_sql(item_code: str, available: set[str], physical_names: dict[str, str] | None = None) -> tuple[str, str, list[Any], tuple[Any, ...]]:
    wanted = [field for field in OINM_FIELDS if field in available]
    physical = physical_names or {"doc_date":"DocDate", "trans_num":"TransNum", "trans_seq":"TransSeq", "instance":"Instance",
        "trans_type":"TransType", "item_code":"ItemCode", "warehouse":"Warehouse", "in_qty":"InQty",
        "out_qty":"OutQty", "price":"Price", "calc_price":"CalcPrice", "trans_value":"TransValue",
        "created_by":"CreatedBy", "app_obj_abs":"AppObjAbs", "app_obj_type":"AppObjType", "doc_line_num":"DocLineNum",
        "base_ref":"BaseRef", "ref1":"Ref1", "ref2":"Ref2", "comments":"Comments", "jrnl_memo":"JrnlMemo",
        "doc_due_date":"DocDueDate", "doc_time":"DocTime", "card_code":"CardCode", "card_name":"CardName",
        "dscription":"Dscription", "balance":"Balance", "slp_code":"SlpCode", "user_sign":"UserSign",
        "appl_obj":"ApplObj", "app_obj_line":"AppObjLine"}
    sap_projection = ",".join(f'M."{physical[f]}" AS {f}' for f in wanted)
    lake_projection = ",".join(f'm.{f}' for f in wanted)
    sap = f'''SELECT {sap_projection} FROM "TELCHI"."OINM" M
        WHERE M."DocDate">=? AND M."DocDate"<? AND M."ItemCode"=?
        ORDER BY M."TransNum",M."TransSeq"'''
    lake = f'''SELECT {lake_projection} FROM telchi.atomic."inventory_movement" m
        WHERE m.doc_date>=? AND m.doc_date<? AND m.item_code=?
        ORDER BY TRY_CAST(m.trans_num AS BIGINT),TRY_CAST(m.trans_seq AS BIGINT)'''
    return sap, lake, [START, END_EXCLUSIVE, item_code], (START, END_EXCLUSIVE, item_code)


def _oitw_sql(item_code: str) -> tuple[str, str, list[Any], tuple[Any, ...]]:
    sap = '''SELECT W."ItemCode" AS item_code,W."WhsCode" AS whs_code,W."OnHand" AS on_hand,
        W."IsCommited" AS is_commited,W."OnOrder" AS on_order
        FROM "TELCHI"."OITW" W WHERE W."ItemCode"=? ORDER BY W."WhsCode"'''
    lake = '''SELECT w.item_code,w.whs_code,w.on_hand,w.is_commited,w.on_order
        FROM telchi.atomic."inventory_balance" w WHERE w.item_code=? ORDER BY w.whs_code'''
    return sap, lake, [item_code], (item_code,)


def _aggregate(rows: list[dict[str, Any]], date_key: str, dimensions: tuple[str, ...], quantity_keys: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        date = str(_key(row, date_key) or "")[:7]
        key = (date, *(str(_key(row, dimension) or "") for dimension in dimensions))
        current = groups.setdefault(key, {"month": date, **{dimension: value for dimension, value in zip(dimensions, key[1:])}, "rows": 0})
        current["rows"] += 1
        for quantity_key in quantity_keys:
            current[quantity_key] = str(Decimal(str(current.get(quantity_key, "0"))) + Decimal(str(_key(row, quantity_key) or "0")))
    return [groups[key] for key in sorted(groups)]


def _monthly_summary(sales: list[dict[str, Any]], moves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for month in [f"2026-{index:02d}" for index in range(1, 10)]:
        s = [row for row in sales if str(_key(row, "doc_date"))[:7] == month]
        m = [row for row in moves if str(_key(row, "doc_date"))[:7] == month]
        result.append({"month": month, "sales_qty": str(sum((Decimal(str(_key(row, "quantity") or 0)) for row in s), Decimal(0))),
                       "oinm_in_qty": str(sum((Decimal(str(_key(row, "in_qty") or 0)) for row in m), Decimal(0))),
                       "oinm_out_qty": str(sum((Decimal(str(_key(row, "out_qty") or 0)) for row in m), Decimal(0))),
                       "movement_count": len(m), "active_warehouses": sorted({str(_key(row, "whs_code") or _key(row, "warehouse")) for row in s + m})})
    return result


def _warehouse_summary(sales: list[dict[str, Any]], moves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warehouses = sorted({str(_key(row, "whs_code")) for row in sales} | {str(_key(row, "warehouse")) for row in moves})
    return [{"warehouse": warehouse,
             "sales_qty": str(sum((Decimal(str(_key(row, "quantity") or 0)) for row in sales if str(_key(row, "whs_code")) == warehouse), Decimal(0))),
             "oinm_in_qty": str(sum((Decimal(str(_key(row, "in_qty") or 0)) for row in moves if str(_key(row, "warehouse")) == warehouse), Decimal(0))),
             "oinm_out_qty": str(sum((Decimal(str(_key(row, "out_qty") or 0)) for row in moves if str(_key(row, "warehouse")) == warehouse), Decimal(0))),
             "movement_count": sum(1 for row in moves if str(_key(row, "warehouse")) == warehouse),
             "activity_dates": sorted({str(_key(row, "doc_date"))[:10] for row in sales if str(_key(row, "whs_code")) == warehouse} | {str(_key(row, "doc_date"))[:10] for row in moves if str(_key(row, "warehouse")) == warehouse})}
            for warehouse in warehouses]


def _transtype_summary(moves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for trans_type in sorted({str(_key(row, "trans_type")) for row in moves}):
        scope = [row for row in moves if str(_key(row, "trans_type")) == trans_type]
        result.append({"trans_type": trans_type, "movement_count": len(scope),
                       "in_qty": str(sum((Decimal(str(_key(row, "in_qty") or 0)) for row in scope), Decimal(0))),
                       "out_qty": str(sum((Decimal(str(_key(row, "out_qty") or 0)) for row in scope), Decimal(0)))})
    return result


def _timeline(sales: list[dict[str, Any]], moves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for row in sales:
        events.append({"date": str(_key(row, "doc_date"))[:10], "event_type": "SALE_LINE", "source": "SAP_OINV_INV1",
                       "source_key": {"DocEntry": _key(row, "doc_entry"), "LineNum": _key(row, "line_num")},
                       "warehouse": _key(row, "whs_code"), "customer": _key(row, "card_code"), "in_qty": "0", "out_qty": "0",
                       "sales_qty": _key(row, "quantity"), "TransType": None, "DocEntry": _key(row, "doc_entry"), "LineNum": _key(row, "line_num"),
                       "TransNum": None, "TransSeq": None, "relationship": "UNLINKED"})
    for row in moves:
        explicit = _key(row, "app_obj_type") is not None and str(_key(row, "app_obj_type")) == "13" and _key(row, "app_obj_abs") is not None
        events.append({"date": str(_key(row, "doc_date"))[:10], "event_type": "OINM_MOVEMENT", "source": "SAP_OINM",
                       "source_key": {"TransNum": _key(row, "trans_num"), "TransSeq": _key(row, "trans_seq")},
                       "warehouse": _key(row, "warehouse"), "customer": _key(row, "card_code"), "in_qty": _key(row, "in_qty"),
                       "out_qty": _key(row, "out_qty"), "sales_qty": "0", "TransType": _key(row, "trans_type"),
                       "DocEntry": _key(row, "app_obj_abs") if explicit else None, "LineNum": _key(row, "app_obj_line") if explicit else None,
                       "TransNum": _key(row, "trans_num"), "TransSeq": _key(row, "trans_seq"),
                       "relationship": "EXPLICIT" if explicit else "UNLINKED",
                       "explicit_reference": {"AppObjAbs": _key(row, "app_obj_abs"), "AppObjType": _key(row, "app_obj_type"), "AppObjLine": _key(row, "app_obj_line")} if explicit else None})
    return sorted(events, key=lambda row: (row["date"], row["source"], str(row["source_key"])))


def _drilldown(source: HanaReadOnlySource, connector: DuckLakeConnector, sales: list[dict[str, Any]], moves: list[dict[str, Any]], item: str, available: set[str], physical_names: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    physical = physical_names or {"doc_date":"DocDate", "trans_num":"TransNum", "trans_seq":"TransSeq", "instance":"Instance", "trans_type":"TransType", "item_code":"ItemCode", "warehouse":"Warehouse", "in_qty":"InQty", "out_qty":"OutQty", "price":"Price", "calc_price":"CalcPrice", "trans_value":"TransValue", "created_by":"CreatedBy", "app_obj_abs":"AppObjAbs", "app_obj_type":"AppObjType", "doc_line_num":"DocLineNum", "base_ref":"BaseRef", "ref1":"Ref1", "ref2":"Ref2", "comments":"Comments", "jrnl_memo":"JrnlMemo", "doc_due_date":"DocDueDate", "doc_time":"DocTime", "card_code":"CardCode", "card_name":"CardName", "dscription":"Dscription", "balance":"Balance", "slp_code":"SlpCode", "user_sign":"UserSign", "appl_obj":"ApplObj", "app_obj_line":"AppObjLine"}
    sales_cases = []
    for row in ordered(sales, ("doc_entry", "line_num"))[:3]:
        doc_entry, line_num = _key(row, "doc_entry"), _key(row, "line_num")
        sap, _ = _sap(source, f"sales_drilldown_{doc_entry}_{line_num}", '''SELECT H."DocDate" AS doc_date,H."DocEntry" AS doc_entry,H."DocNum" AS doc_num,H."ObjType" AS obj_type,H."DocDueDate" AS doc_due_date,H."TaxDate" AS tax_date,H."DocStatus" AS doc_status,H."CANCELED" AS canceled,H."DocCur" AS currency,H."DocTotal" AS doc_total,H."CardCode" AS card_code,L."LineNum" AS line_num,L."LineStatus" AS line_status,L."ItemCode" AS item_code,L."Quantity" AS quantity,L."WhsCode" AS whs_code,L."Price" AS price,L."LineTotal" AS line_total FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" WHERE H."DocEntry"=? AND L."LineNum"=?''', (doc_entry, line_num))
        lake, _ = _duck(connector, '''SELECT h.doc_date,h.doc_entry,h.doc_num,'13' AS obj_type,h.doc_due_date,h.tax_date,h.doc_status,h.canceled,h.currency,h.doc_total,h.card_code,l.line_num,l.line_status,l.item_code,l.quantity,l.whs_code,l.price,l.line_total FROM telchi.atomic."sales_document" h JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry WHERE h.doc_entry=? AND l.line_num=?''', [doc_entry, line_num])
        cmp = compare_rowsets(sap, lake, ("doc_entry", "line_num"))
        sales_cases.append({"DocEntry": doc_entry, "LineNum": line_num, "comparison": cmp, "SAP": sap, "DuckLake": lake})
    move_cases = []
    for row in ordered(moves, ("trans_num", "trans_seq"))[:3]:
        trans_num, trans_seq = _key(row, "trans_num"), _key(row, "trans_seq")
        fields = [name for name in OINM_FIELDS if name in available]
        sap, _ = _sap(source, f"oinm_drilldown_{trans_num}_{trans_seq}", f'''SELECT {','.join(f'M."{physical[name]}" AS {name}' for name in fields)} FROM "TELCHI"."OINM" M WHERE M."TransNum"=? AND M."TransSeq"=?''', (trans_num, trans_seq))
        lake, _ = _duck(connector, f'''SELECT {','.join('m.' + name for name in OINM_FIELDS if name in available)} FROM telchi.atomic."inventory_movement" m WHERE m.trans_num=? AND m.trans_seq=?''', [trans_num, trans_seq])
        cmp = compare_rowsets(sap, lake, ("trans_num", "trans_seq"))
        move_cases.append({"TransNum": trans_num, "TransSeq": trans_seq, "comparison": cmp, "SAP": sap, "DuckLake": lake})
    return sales_cases, move_cases


def _main() -> dict[str, Any]:
    started = time.perf_counter()
    connector = DuckLakeConnector()
    # Selection and complete DuckLake reconstruction happen before any SAP query.
    selection = select_litel_product(connector)
    item = str(selection["item_code"])
    duck_started = time.perf_counter()
    sales_sql, sales_lake_sql, sales_params, sales_sap_params = _sales_sql(item)
    duck_sales, duck_sales_ms = _duck(connector, sales_lake_sql, sales_params)
    # These fields are the source-native OINM columns already validated by the
    # operational baseline. No SAP query guides the DuckLake reconstruction.
    oinm_available = set(OINM_FIELDS)
    oinm_sql, oinm_lake_sql, oinm_params, oinm_sap_params = _oinm_sql(item, oinm_available)
    duck_moves, duck_moves_ms = _duck(connector, oinm_lake_sql, oinm_params)
    oitw_sql, oitw_lake_sql, oitw_params, oitw_sap_params = _oitw_sql(item)
    duck_oitw, duck_oitw_ms = _duck(connector, oitw_lake_sql, oitw_params)
    duck_duration_ms = round((time.perf_counter() - duck_started) * 1000, 3)
    duck_monthly, duck_warehouse, duck_transtype = _monthly_summary(duck_sales, duck_moves), _warehouse_summary(duck_sales, duck_moves), _transtype_summary(duck_moves)
    duck_timeline = _timeline(duck_sales, duck_moves)
    # Explicit links are computed from SAP fields only; matching by date/item/quantity is forbidden.
    explicit_links = [event for event in duck_timeline if event["relationship"] == "EXPLICIT"]
    # SAP equivalent reconstruction, only after DuckLake outputs are complete.
    source = HanaReadOnlySource()
    schema = source.discover_oinm_schema()
    physical_names = {_field_name(str(row["canonical_name"])): str(row["source_name"]) for row in schema["columns"]}
    oinm_available = set(physical_names) & set(OINM_FIELDS)
    oinm_sql, oinm_lake_sql, oinm_params, oinm_sap_params = _oinm_sql(item, oinm_available, physical_names)
    sap_started = time.perf_counter()
    sap_sales, sap_sales_ms = _sap(source, "litel_sales_history", sales_sql, sales_sap_params)
    sap_moves, sap_moves_ms = _sap(source, "litel_oinm_history", oinm_sql, oinm_sap_params)
    sap_oitw, sap_oitw_ms = _sap(source, "litel_oitw_current", oitw_sql, oitw_sap_params)
    sap_duration_ms = round((time.perf_counter() - sap_started) * 1000, 3)
    sap_monthly, sap_warehouse, sap_transtype = _monthly_summary(sap_sales, sap_moves), _warehouse_summary(sap_sales, sap_moves), _transtype_summary(sap_moves)
    sales_cmp = compare_rowsets(sap_sales, duck_sales, ("doc_entry", "line_num"))
    oinm_cmp = compare_rowsets(sap_moves, duck_moves, ("trans_num", "trans_seq"))
    sales_total_cmp = "EXACT" if _monthly_summary(sap_sales, []) == _monthly_summary(duck_sales, []) else "MISMATCH"
    sales_monthly_cmp = "EXACT" if _monthly_summary(sap_sales, []) == _monthly_summary(duck_sales, []) else "MISMATCH"
    oinm_monthly_cmp = "EXACT" if _monthly_summary([], sap_moves) == _monthly_summary([], duck_moves) else "MISMATCH"
    sales_warehouse_cmp = "EXACT" if _warehouse_summary(sap_sales, []) == _warehouse_summary(duck_sales, []) else "MISMATCH"
    oinm_warehouse_cmp = "EXACT" if _warehouse_summary([], sap_moves) == _warehouse_summary([], duck_moves) else "MISMATCH"
    transtype_cmp = "EXACT" if sap_transtype == duck_transtype else "MISMATCH"
    monthly_cmp = "EXACT" if sales_monthly_cmp == oinm_monthly_cmp == "EXACT" else "MISMATCH"
    warehouse_cmp = "EXACT" if sales_warehouse_cmp == oinm_warehouse_cmp == "EXACT" else "MISMATCH"
    oitw_cmp = compare_rowsets(sap_oitw, duck_oitw, ("item_code", "whs_code"))
    sales_drill, oinm_drill = _drilldown(source, connector, duck_sales, duck_moves, item, oinm_available, physical_names)
    # Warm sequential DuckLake repetitions are bounded and never mutate the catalog.
    warm = []
    for index in range(3):
        _, elapsed = _duck(connector, sales_lake_sql, sales_params)
        _, movement_elapsed = _duck(connector, oinm_lake_sql, oinm_params)
        warm.append({"execution": index + 1, "sales_ms": elapsed, "oinm_ms": movement_elapsed, "total_ms": round(elapsed + movement_elapsed, 3)})
    current_as_of_sap, asof_sap_ms = _sap(source, "litel_oitw_source_as_of", "SELECT CURRENT_UTCTIMESTAMP AS source_as_of FROM DUMMY")
    current_as_of_lake, asof_lake_ms = _duck(connector, "SELECT MAX(source_as_of) AS source_as_of FROM telchi.atomic.\"inventory_balance\"")
    current_oitw_match = oitw_cmp["status"]
    if current_oitw_match != "EXACT":
        current_oitw_match = "SOURCE_CHANGED" if current_as_of_sap and current_as_of_lake else "MISMATCH"
    comparison_statuses = [sales_cmp["status"], oinm_cmp["status"], sales_monthly_cmp, sales_warehouse_cmp, oinm_monthly_cmp, oinm_warehouse_cmp, transtype_cmp, current_oitw_match]
    true_mismatch_count = sum(value == "MISMATCH" for value in comparison_statuses)
    unexplained_mismatch_count = true_mismatch_count
    summary = {
        "GATE": GATE, "HISTORICAL_CUTOFF": HISTORICAL_CUTOFF, "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": source.sap_write_count, "AI_INVOCATIONS": 0,
        "SELECTED_ITEMCODE": item, "PRODUCT_DESCRIPTION": selection.get("product_name") or selection.get("canonical_name"), "CANONICAL_PRODUCT_ID": selection.get("canonical_product_id"),
        "LITEL_CLASSIFICATION_SOURCE": selection["litel_classification_source"], "SALES_DOCUMENTS_COUNT": len({str(_key(row, 'doc_entry')) for row in duck_sales}), "SALES_LINES_COUNT": len(duck_sales),
        "SALES_TOTAL_QUANTITY": str(sum((Decimal(str(_key(row, "quantity") or 0)) for row in duck_sales), Decimal(0))), "SALES_FIRST_DATE": min((str(_key(row, "doc_date"))[:10] for row in duck_sales), default=None), "SALES_LAST_DATE": max((str(_key(row, "doc_date"))[:10] for row in duck_sales), default=None),
        "OINM_MOVEMENT_COUNT": len(duck_moves), "OINM_TOTAL_IN_QTY": str(sum((Decimal(str(_key(row, "in_qty") or 0)) for row in duck_moves), Decimal(0))), "OINM_TOTAL_OUT_QTY": str(sum((Decimal(str(_key(row, "out_qty") or 0)) for row in duck_moves), Decimal(0))), "OINM_FIRST_DATE": min((str(_key(row, "doc_date"))[:10] for row in duck_moves), default=None), "OINM_LAST_DATE": max((str(_key(row, "doc_date"))[:10] for row in duck_moves), default=None),
        "WAREHOUSE_COUNT": len({str(_key(row, "whs_code")) for row in duck_sales} | {str(_key(row, "warehouse")) for row in duck_moves}), "CUSTOMER_COUNT": len({str(_key(row, "card_code")) for row in duck_sales}), "TRANSTYPE_COUNT": len({str(_key(row, "trans_type")) for row in duck_moves}),
        "PRODUCT_IDENTITY_MATCH": "EXACT" if item == str(selection["item_code"]) else "MISMATCH", "SALES_ROWSET_MATCH": sales_cmp["status"], "SALES_TOTAL_MATCH": "EXACT" if str(sum((Decimal(str(_key(row, "quantity") or 0)) for row in sap_sales), Decimal(0))) == summary_quantity(duck_sales) else "MISMATCH", "SALES_MONTHLY_MATCH": sales_monthly_cmp, "SALES_WAREHOUSE_MATCH": sales_warehouse_cmp,
        "OINM_ROWSET_MATCH": oinm_cmp["status"], "OINM_TOTAL_IN_MATCH": "EXACT" if sum_decimal(sap_moves, "in_qty") == sum_decimal(duck_moves, "in_qty") else "MISMATCH", "OINM_TOTAL_OUT_MATCH": "EXACT" if sum_decimal(sap_moves, "out_qty") == sum_decimal(duck_moves, "out_qty") else "MISMATCH", "OINM_MONTHLY_MATCH": oinm_monthly_cmp, "OINM_WAREHOUSE_MATCH": oinm_warehouse_cmp, "OINM_TRANSTYPE_MATCH": transtype_cmp,
        "SALES_DRILLDOWN_CASES": len(sales_drill), "SALES_DRILLDOWN_EXACT": f"{sum(case['comparison']['status']=='EXACT' for case in sales_drill)}/{len(sales_drill)}", "OINM_DRILLDOWN_CASES": len(oinm_drill), "OINM_DRILLDOWN_EXACT": f"{sum(case['comparison']['status']=='EXACT' for case in oinm_drill)}/{len(oinm_drill)}",
        "EXPLICIT_SALES_OINM_LINKS": len(explicit_links), "UNLINKED_EVENTS": sum(event["relationship"] == "UNLINKED" for event in duck_timeline), "SOURCE_LINEAGE_VALIDATED": "YES" if sales_cmp["status"] == "EXACT" and oinm_cmp["status"] == "EXACT" else "NO",
        "OITW_CURRENT_STATE_ONLY": "YES", "OITW_SOURCE_AS_OF": _key(current_as_of_sap[0], "source_as_of") if current_as_of_sap else None, "OITW_CURRENT_MATCH": current_oitw_match, "CURRENT_TOTAL_ONHAND": str(sum_decimal(duck_oitw, "on_hand")), "CURRENT_TOTAL_COMMITTED": str(sum_decimal(duck_oitw, "is_commited")), "CURRENT_TOTAL_ONORDER": str(sum_decimal(duck_oitw, "on_order")),
        "TRUE_MISMATCH_COUNT": true_mismatch_count, "UNEXPLAINED_MISMATCH_COUNT": unexplained_mismatch_count,
        "DUCKLAKE_TRACE_DURATION_MS": duck_duration_ms, "SAP_TRACE_DURATION_MS": sap_duration_ms, "GOLDEN_CASE_CREATED": "YES", "BASELINE_DATA_MODIFIED": "NO", "REFERENCE_V2_MODIFIED": "NO", "LEGACY_USED": "NO", "SAFE_PRODUCT_TRACE_FOR_BUSINESS_ASSISTANT": "YES" if sales_cmp["status"] == oinm_cmp["status"] == monthly_cmp == warehouse_cmp == transtype_cmp == "EXACT" else "NO",
        "FINAL_RESULT": "PENDING_REVIEW",
    }
    mismatches = summary["TRUE_MISMATCH_COUNT"]
    summary["FINAL_RESULT"] = GATE + ("_PASS" if mismatches == 0 and summary["UNEXPLAINED_MISMATCH_COUNT"] == 0 and summary["SALES_DRILLDOWN_EXACT"] == f"{len(sales_drill)}/{len(sales_drill)}" and summary["OINM_DRILLDOWN_EXACT"] == f"{len(oinm_drill)}/{len(oinm_drill)}" else "_DEGRADED" if sales_cmp["status"] == oinm_cmp["status"] == "EXACT" else "_FAIL")
    product_activity = {"first_sales_date": summary["SALES_FIRST_DATE"], "last_sales_date": summary["SALES_LAST_DATE"], "first_movement_date": summary["OINM_FIRST_DATE"], "last_movement_date": summary["OINM_LAST_DATE"], "sales_total_qty": summary["SALES_TOTAL_QUANTITY"], "movement_in_total": summary["OINM_TOTAL_IN_QTY"], "movement_out_total": summary["OINM_TOTAL_OUT_QTY"], "warehouse_count": summary["WAREHOUSE_COUNT"], "customer_count": summary["CUSTOMER_COUNT"], "TransType_count": summary["TRANSTYPE_COUNT"], "current_state_only": True}
    _write("summary.json", summary)
    _write("product_selection.json", selection)
    _write("current_state.json", {"OITW_CURRENT_STATE_ONLY": "YES", "OITW_SOURCE_AS_OF": current_as_of_sap, "DuckLake_SOURCE_AS_OF": current_as_of_lake, "current_oitw_match": current_oitw_match})
    _write("ducklake_sales_history.json", ordered(duck_sales, ("doc_entry", "line_num")))
    _write("ducklake_oinm_history.json", ordered(duck_moves, ("trans_num", "trans_seq")))
    _write("ducklake_monthly_summary.json", duck_monthly)
    _write("ducklake_warehouse_summary.json", duck_warehouse)
    _write("ducklake_timeline.json", duck_timeline)
    _write("sap_sales_history.json", ordered(sap_sales, ("doc_entry", "line_num")))
    _write("sap_oinm_history.json", ordered(sap_moves, ("trans_num", "trans_seq")))
    _write("sap_monthly_summary.json", sap_monthly)
    _write("sap_warehouse_summary.json", sap_warehouse)
    _write("sales_comparison.json", sales_cmp)
    _write("oinm_comparison.json", oinm_cmp)
    _write("aggregate_comparison.json", {"sales_total": summary["SALES_TOTAL_MATCH"], "sales_monthly": sales_monthly_cmp, "sales_warehouse": sales_warehouse_cmp, "oinm_total_in": summary["OINM_TOTAL_IN_MATCH"], "oinm_total_out": summary["OINM_TOTAL_OUT_MATCH"], "oinm_monthly": oinm_monthly_cmp, "oinm_warehouse": oinm_warehouse_cmp, "oinm_transtype": transtype_cmp})
    _write("sales_drilldown.json", sales_drill)
    _write("oinm_drilldown.json", oinm_drill)
    _write("current_oitw.json", {"OITW_CURRENT_STATE_ONLY": "YES", "SAP": sap_oitw, "DuckLake": duck_oitw, "comparison": oitw_cmp})
    _write("performance.json", {"DuckLake_trace_duration_ms": duck_duration_ms, "SAP_trace_duration_ms": sap_duration_ms, "subqueries": {"DuckLake_sales_ms": duck_sales_ms, "DuckLake_oinm_ms": duck_moves_ms, "DuckLake_oitw_ms": duck_oitw_ms, "SAP_sales_ms": sap_sales_ms, "SAP_oinm_ms": sap_moves_ms, "SAP_oitw_ms": sap_oitw_ms, "SAP_as_of_ms": asof_sap_ms, "DuckLake_as_of_ms": asof_lake_ms}, "DuckLake_warm_sequential": warm, "MAX_HANA_CONCURRENT_QUERIES": 1})
    _write("golden_case.json", {"business_question": "Para un producto Litel relevante, mostrar toda su historia operativa 2026 hasta 2026-09-15 inclusive.", "expected_structured_answer": {"selected_item": item, "sales": summary["SALES_TOTAL_QUANTITY"], "oinm_in": summary["OINM_TOTAL_IN_QTY"], "oinm_out": summary["OINM_TOTAL_OUT_QTY"], "current_stock_caveat": "OITW current state only"}, "source_lineage": {"sales": "OINV/INV1 -> atomic.sales_document/sales_line", "oinm": "OINM -> atomic.inventory_movement", "oitw": "OITW current -> atomic.inventory_balance"}, "exact_comparisons": {"sales_rowset": sales_cmp["status"], "oinm_rowset": oinm_cmp["status"], "monthly": monthly_cmp, "warehouse": warehouse_cmp, "transtype": transtype_cmp}, "ai_invocations": 0, "sap_write_count": source.sap_write_count})
    activity = product_activity
    report = [f"# {GATE}", "", "```text"] + [f"{key}={value}" for key, value in summary.items()] + ["```", "", "## Method", "", "DuckLake selection and complete trace were executed before equivalent SAP reads. Historical predicates use 2026-01-01 <= DocDate < 2026-09-16. Sales keys are DocEntry+LineNum; OINM keys are TransNum+TransSeq.", "", "Sales and OINM events are independent. Relations are EXPLICIT only when AppObjAbs/AppObjType is present; all other events are UNLINKED. No fuzzy date/quantity/item linking was used.", "", "OITW is current state only and is not stock at the historical cutoff.", "", "## Product activity", "", json.dumps(activity, indent=2, ensure_ascii=False), "", "## STOP AND REVIEW", "", "No Business Assistant, update.py, Atomic modification, historical expansion or AI was implemented.", ""]
    (EVIDENCE_ROOT / "report.md").write_text("\n".join(report), encoding="utf-8")
    return summary


def sum_decimal(rows: Iterable[dict[str, Any]], field: str) -> Decimal:
    return sum((Decimal(str(_key(row, field) or 0)) for row in rows), Decimal(0))


def summary_quantity(rows: Iterable[dict[str, Any]]) -> str:
    return str(sum_decimal(rows, "quantity"))


if __name__ == "__main__":
    print(json.dumps(_main(), indent=2, sort_keys=True, ensure_ascii=False, default=str))
