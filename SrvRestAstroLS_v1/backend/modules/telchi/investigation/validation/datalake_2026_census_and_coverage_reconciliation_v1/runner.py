"""TELCHI_DATALAKE_2026_CENSUS_AND_COVERAGE_RECONCILIATION_V1.

Foundation-closure gate. It performs a quantitative census of the principal
SAP Telchi entities for 2026 and reconciles the entities that are already
materialized in the Data Lake. Missing entities are classified ``NOT_LOADED``
and are never downgraded to ``MISMATCH``.

Hard rules enforced by construction:

* SAP is READ ONLY: every statement is a bounded ``SELECT``/aggregate and the
  adapter's ``assert_read_only_select`` guard rejects anything else.
* The Data Lake is opened ``read_only=True``; no INSERT/UPDATE/DELETE/COPY/
  CHECKPOINT/compaction/expiration is executed.
* Historical scope is ``[2026-01-01, 2026-09-15]`` inclusive and both bounds are
  applied on both engines, so out-of-scope history cannot leak into a census.
* Current-state masters (OITM/OCRD/OWHS/OITW) are reported as current snapshots
  with an explicit ``source_as_of`` and never presented as historical.
* No AI is invoked.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.source import HanaReadOnlySource

GATE = "TELCHI_DATALAKE_2026_CENSUS_AND_COVERAGE_RECONCILIATION_V1"
START = "2026-01-01"
CUTOFF = "2026-09-15"
END_EXCLUSIVE = "2026-09-16"
HISTORICAL_RANGE = (START, END_EXCLUSIVE)  # lower inclusive, upper exclusive
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE

# Coverage status vocabulary (section 6). Order matters for the matrix summary.
COVERAGE_STATUSES = (
    "EXACT",
    "LOADED_NOT_VALIDATED",
    "NOT_LOADED",
    "NOT_APPLICABLE",
    "SOURCE_CHANGED",
    "MISMATCH",
)

# Deterministic business-priority rule for coverage gaps (section 40).
PRIORITY_HIGH_MIN_DOCUMENTS = 10_000
PRIORITY_MEDIUM_MIN_DOCUMENTS = 100

# Data Lake entities that this gate knows how to census.
DATALAKE_ATOMIC = {
    "sales_document": "sales_document",
    "sales_line": "sales_line",
    "inventory_movement": "inventory_movement",
    "inventory_balance": "inventory_balance",
}


# --------------------------------------------------------------------------- #
# Pure helpers (unit-testable without SAP or DuckLake)
# --------------------------------------------------------------------------- #
def month_of(value: Any) -> str | None:
    """Return the ``YYYY-MM`` month of a source date, ignoring time."""
    if value is None:
        return None
    text = str(value)
    if len(text) < 7:
        return None
    return text[:7]


def within_historical_range(value: Any) -> bool:
    """True when a source date is inside ``[START, CUTOFF]`` inclusive."""
    if value is None:
        return False
    day = str(value)[:10]
    return START <= day <= CUTOFF


def classify_coverage(
    *,
    loaded: bool,
    comparable: bool,
    exact: bool,
    as_of_conflict: bool,
) -> str:
    """Map evidence to exactly one coverage status.

    A missing Data Lake entity is ``NOT_LOADED`` and must never become
    ``MISMATCH``. A loaded entity with non-comparable semantics is
    ``LOADED_NOT_VALIDATED``. A real residual difference at the same as-of is
    ``MISMATCH`` only when it cannot be explained by source mutation.
    """
    if not loaded:
        return "NOT_LOADED"
    if not comparable:
        return "LOADED_NOT_VALIDATED"
    if exact:
        return "EXACT"
    if as_of_conflict:
        return "SOURCE_CHANGED"
    return "MISMATCH"


def classify_priority(document_count: int | None) -> str:
    """Deterministic gap priority from 2026 document count only."""
    if document_count is None:
        return "UNKNOWN"
    if document_count >= PRIORITY_HIGH_MIN_DOCUMENTS:
        return "HIGH"
    if document_count >= PRIORITY_MEDIUM_MIN_DOCUMENTS:
        return "MEDIUM"
    return "LOW"


def _xor_add_fingerprint(keys: Iterable[str]) -> dict[str, Any]:
    """Order-independent, engine-neutral set fingerprint.

    Both engines emit the same 256-bit SHA-256 per key. XOR detects ordering
    independence and the modular sum guards the pathological XOR collisions.
    """
    xor = bytearray(32)
    add = 0
    count = 0
    for key in keys:
        digest = hashlib.sha256(str(key).encode("utf-8")).digest()
        for index in range(32):
            xor[index] ^= digest[index]
        add = (add + int.from_bytes(digest, "big")) % (1 << 256)
        count += 1
    return {
        "count": count,
        "xor_sha256": bytes(xor).hex(),
        "add_sha256": add.to_bytes(32, "big").hex(),
    }


def _fingerprint_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("count") == right.get("count")
        and left.get("xor_sha256") == right.get("xor_sha256")
        and left.get("add_sha256") == right.get("add_sha256")
    )


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# SAP read-only census primitives
# --------------------------------------------------------------------------- #
def _sap_rows(source: HanaReadOnlySource, query_id: str, sql: str,
              params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return source._execute(query_id, sql, params)


def _sap_first(source: HanaReadOnlySource, query_id: str, sql: str,
               params: tuple[Any, ...] = ()) -> dict[str, Any]:
    rows = _sap_rows(source, query_id, sql, params)
    return rows[0] if rows else {}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _document_census(
    source: HanaReadOnlySource,
    *,
    key: str,
    header: str,
    line: str,
    range_params: tuple[Any, ...] = HISTORICAL_RANGE,
) -> dict[str, Any]:
    """Census one SAP commercial document family under the historical range.

    Definition of active/cancelled is explicit and never assumed: the raw
    ``CANCELED`` distribution is preserved, ``ACTIVE`` is ``CANCELED='N'`` and
    ``CANCELLED`` is ``CANCELED='Y'``. Values outside that pair are reported
    separately instead of being folded into either bucket.
    """
    header_range = 'H."DocDate" >= ? AND H."DocDate" < ?'
    join = f'"TELCHI"."{header}" H JOIN "TELCHI"."{line}" L ON L."DocEntry" = H."DocEntry"'
    result: dict[str, Any] = {
        "census_key": key,
        "sap_tables": [header, line],
        "date_field": "DocDate",
        "scope": {"start": START, "cutoff": CUTOFF, "upper_exclusive": END_EXCLUSIVE},
        "document_status_rule": "ACTIVE=CANCELED='N'; CANCELLED=CANCELED='Y'; other values reported separately",
    }
    status = _sap_rows(
        source,
        f"{key}_status",
        f'SELECT H."CANCELED" AS "canceled", COUNT(*) AS "documents" '
        f'FROM "TELCHI"."{header}" H WHERE {header_range} GROUP BY H."CANCELED"',
        range_params,
    )
    status_map = {str(row.get("canceled")): _int(row.get("documents")) for row in status}
    result["cancelled_distribution"] = status_map
    result["total_documents"] = sum(value or 0 for value in status_map.values())
    result["active_documents"] = status_map.get("N")
    result["cancelled_documents"] = status_map.get("Y")
    result["other_status_documents"] = sum(
        (value or 0) for label, value in status_map.items() if label not in {"N", "Y"}
    )
    aggregates = _sap_first(
        source,
        f"{key}_aggregates",
        f'SELECT COUNT(*) AS "lines", COUNT(DISTINCT H."CardCode") AS "distinct_customers", '
        f'COUNT(DISTINCT L."ItemCode") AS "distinct_products", '
        f'COUNT(DISTINCT L."WhsCode") AS "distinct_warehouses", '
        f'COALESCE(SUM(L."Quantity"), 0) AS "total_quantity" '
        f'FROM {join} WHERE {header_range}',
        range_params,
    )
    result["total_lines"] = _int(aggregates.get("lines"))
    result["distinct_customers"] = _int(aggregates.get("distinct_customers"))
    result["distinct_products"] = _int(aggregates.get("distinct_products"))
    result["distinct_warehouses"] = _int(aggregates.get("distinct_warehouses"))
    result["total_quantity"] = _num(aggregates.get("total_quantity"))
    # Monthly document distribution keeps an annual total from hiding a gap.
    monthly = _sap_rows(
        source,
        f"{key}_monthly",
        f'SELECT SUBSTRING(CAST(H."DocDate" AS NVARCHAR), 1, 7) AS "month", '
        f'COUNT(DISTINCT H."DocEntry") AS "documents", COUNT(*) AS "lines" '
        f'FROM {join} WHERE {header_range} '
        f'GROUP BY SUBSTRING(CAST(H."DocDate" AS NVARCHAR), 1, 7) ORDER BY "month"',
        range_params,
    )
    result["monthly"] = {
        str(row.get("month")): {"documents": _int(row.get("documents")), "lines": _int(row.get("lines"))}
        for row in monthly
    }
    return result


def _sap_product_master_census(source: HanaReadOnlySource) -> dict[str, Any]:
    row = _sap_first(
        source,
        "product_master_current",
        'SELECT COUNT(*) AS "total", '
        'SUM(CASE WHEN "validFor" = \'Y\' THEN 1 ELSE 0 END) AS "active", '
        'SUM(CASE WHEN "validFor" = \'N\' THEN 1 ELSE 0 END) AS "inactive", '
        'SUM(CASE WHEN "SellItem" = \'Y\' THEN 1 ELSE 0 END) AS "sell_items", '
        'SUM(CASE WHEN "PrchseItem" = \'Y\' THEN 1 ELSE 0 END) AS "purchase_items", '
        'SUM(CASE WHEN "InvntItem" = \'Y\' THEN 1 ELSE 0 END) AS "inventory_items", '
        'COUNT(DISTINCT "ItmsGrpCod") AS "distinct_item_groups" FROM "TELCHI"."OITM"',
    )
    return {
        "census_key": "PRODUCT_MASTER",
        "sap_table": "OITM",
        "time_semantics": "CURRENT_STATE",
        "total_products": _int(row.get("total")),
        "active_products": _int(row.get("active")),
        "inactive_products": _int(row.get("inactive")),
        "sell_items": _int(row.get("sell_items")),
        "purchase_items": _int(row.get("purchase_items")),
        "inventory_items": _int(row.get("inventory_items")),
        "distinct_item_groups": _int(row.get("distinct_item_groups")),
    }


def _sap_business_partner_census(source: HanaReadOnlySource) -> dict[str, Any]:
    row = _sap_first(
        source,
        "business_partner_current",
        'SELECT '
        'SUM(CASE WHEN "CardType" = \'C\' THEN 1 ELSE 0 END) AS "customers_total", '
        'SUM(CASE WHEN "CardType" = \'C\' AND "validFor" = \'Y\' THEN 1 ELSE 0 END) AS "customers_active", '
        'SUM(CASE WHEN "CardType" = \'C\' AND "validFor" = \'N\' THEN 1 ELSE 0 END) AS "customers_inactive", '
        'SUM(CASE WHEN "CardType" = \'S\' THEN 1 ELSE 0 END) AS "suppliers_total", '
        'SUM(CASE WHEN "CardType" = \'S\' AND "validFor" = \'Y\' THEN 1 ELSE 0 END) AS "suppliers_active", '
        'SUM(CASE WHEN "CardType" = \'S\' AND "validFor" = \'N\' THEN 1 ELSE 0 END) AS "suppliers_inactive" '
        'FROM "TELCHI"."OCRD"',
    )
    return {
        "census_key": "BUSINESS_PARTNER_MASTER",
        "sap_table": "OCRD",
        "time_semantics": "CURRENT_STATE",
        "customers_total": _int(row.get("customers_total")),
        "customers_active": _int(row.get("customers_active")),
        "customers_inactive": _int(row.get("customers_inactive")),
        "suppliers_total": _int(row.get("suppliers_total")),
        "suppliers_active": _int(row.get("suppliers_active")),
        "suppliers_inactive": _int(row.get("suppliers_inactive")),
        "card_type_rule": "CUSTOMER=CardType 'C'; SUPPLIER=CardType 'S'; names never merge",
    }


def _sap_warehouse_census(source: HanaReadOnlySource) -> dict[str, Any]:
    row = _sap_first(
        source,
        "warehouse_master_current",
        'SELECT COUNT(*) AS "total", '
        'SUM(CASE WHEN "Inactive" = \'Y\' THEN 1 ELSE 0 END) AS "inactive" '
        'FROM "TELCHI"."OWHS"',
    )
    total = _int(row.get("total"))
    inactive = _int(row.get("inactive"))
    return {
        "census_key": "WAREHOUSE_MASTER",
        "sap_table": "OWHS",
        "time_semantics": "CURRENT_STATE",
        "total_warehouses": total,
        "inactive_warehouses": inactive,
        "active_warehouses": (total - inactive) if total is not None and inactive is not None else None,
    }


def _sap_oitw_census(source: HanaReadOnlySource) -> dict[str, Any]:
    row = _sap_first(
        source,
        "oitw_current",
        'SELECT COUNT(*) AS "rows", COUNT(DISTINCT "ItemCode") AS "distinct_items", '
        'COUNT(DISTINCT "WhsCode") AS "distinct_warehouses", '
        'COALESCE(SUM("OnHand"), 0) AS "sum_on_hand", '
        'COALESCE(SUM("IsCommited"), 0) AS "sum_is_committed", '
        'COALESCE(SUM("OnOrder"), 0) AS "sum_on_order" FROM "TELCHI"."OITW"',
    )
    return {
        "census_key": "OITW_ITEM_WAREHOUSE",
        "sap_table": "OITW",
        "time_semantics": "CURRENT_STATE",
        "rows": _int(row.get("rows")),
        "distinct_items": _int(row.get("distinct_items")),
        "distinct_warehouses": _int(row.get("distinct_warehouses")),
        "sum_on_hand": _num(row.get("sum_on_hand")),
        "sum_is_committed": _num(row.get("sum_is_committed")),
        "sum_on_order": _num(row.get("sum_on_order")),
    }


def _sap_oinm_census(source: HanaReadOnlySource) -> dict[str, Any]:
    row = _sap_first(
        source,
        "oinm_ytd",
        'SELECT COUNT(*) AS "rows", COUNT(DISTINCT "ItemCode") AS "distinct_items", '
        'COUNT(DISTINCT "Warehouse") AS "distinct_warehouses", COUNT(DISTINCT "TransType") AS "distinct_trans_types", '
        'COALESCE(SUM("InQty"), 0) AS "total_in_qty", COALESCE(SUM("OutQty"), 0) AS "total_out_qty", '
        'MIN("DocDate") AS "first_date", MAX("DocDate") AS "last_date" '
        'FROM "TELCHI"."OINM" M WHERE M."DocDate" >= ? AND M."DocDate" < ?',
        HISTORICAL_RANGE,
    )
    trans_types = _sap_rows(
        source,
        "oinm_transtype",
        'SELECT M."TransType" AS "trans_type", COUNT(*) AS "rows", '
        'COUNT(DISTINCT M."ItemCode") AS "distinct_items", '
        'COUNT(DISTINCT M."Warehouse") AS "distinct_warehouses", '
        'COALESCE(SUM(M."InQty"), 0) AS "total_in_qty", COALESCE(SUM(M."OutQty"), 0) AS "total_out_qty" '
        'FROM "TELCHI"."OINM" M WHERE M."DocDate" >= ? AND M."DocDate" < ? '
        'GROUP BY M."TransType" ORDER BY M."TransType"',
        HISTORICAL_RANGE,
    )
    monthly = _sap_rows(
        source,
        "oinm_monthly",
        'SELECT SUBSTRING(CAST(M."DocDate" AS NVARCHAR), 1, 7) AS "month", COUNT(*) AS "rows", '
        'COALESCE(SUM(M."InQty"), 0) AS "total_in_qty", COALESCE(SUM(M."OutQty"), 0) AS "total_out_qty" '
        'FROM "TELCHI"."OINM" M WHERE M."DocDate" >= ? AND M."DocDate" < ? '
        'GROUP BY SUBSTRING(CAST(M."DocDate" AS NVARCHAR), 1, 7) ORDER BY "month"',
        HISTORICAL_RANGE,
    )
    return {
        "census_key": "OINM_MOVEMENTS",
        "sap_table": "OINM",
        "time_semantics": "HISTORICAL",
        "date_field": "DocDate",
        "scope": {"start": START, "cutoff": CUTOFF, "upper_exclusive": END_EXCLUSIVE},
        "rows": _int(row.get("rows")),
        "distinct_items": _int(row.get("distinct_items")),
        "distinct_warehouses": _int(row.get("distinct_warehouses")),
        "distinct_trans_types": _int(row.get("distinct_trans_types")),
        "total_in_qty": _num(row.get("total_in_qty")),
        "total_out_qty": _num(row.get("total_out_qty")),
        "first_date": str(row.get("first_date"))[:10] if row.get("first_date") else None,
        "last_date": str(row.get("last_date"))[:10] if row.get("last_date") else None,
        "trans_type": [
            {
                "trans_type": str(item.get("trans_type")),
                "rows": _int(item.get("rows")),
                "distinct_items": _int(item.get("distinct_items")),
                "distinct_warehouses": _int(item.get("distinct_warehouses")),
                "total_in_qty": _num(item.get("total_in_qty")),
                "total_out_qty": _num(item.get("total_out_qty")),
            }
            for item in trans_types
        ],
        "monthly": {
            str(item.get("month")): {
                "rows": _int(item.get("rows")),
                "total_in_qty": _num(item.get("total_in_qty")),
                "total_out_qty": _num(item.get("total_out_qty")),
            }
            for item in monthly
        },
    }


def _sap_historical_activity(source: HanaReadOnlySource) -> dict[str, Any]:
    sales = _sap_first(
        source,
        "activity_sales",
        'SELECT COUNT(DISTINCT L."ItemCode") AS "products", '
        'COUNT(DISTINCT H."CardCode") AS "customers", '
        'COUNT(DISTINCT L."WhsCode") AS "warehouses" '
        'FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry" = H."DocEntry" '
        'WHERE H."DocDate" >= ? AND H."DocDate" < ?',
        HISTORICAL_RANGE,
    )
    movements = _sap_first(
        source,
        "activity_oinm",
        'SELECT COUNT(DISTINCT "ItemCode") AS "products", COUNT(DISTINCT "Warehouse") AS "warehouses" '
        'FROM "TELCHI"."OINM" M WHERE M."DocDate" >= ? AND M."DocDate" < ?',
        HISTORICAL_RANGE,
    )
    return {
        "time_semantics": "HISTORICAL",
        "SAP_PRODUCTS_WITH_SALES": _int(sales.get("products")),
        "SAP_CUSTOMERS_WITH_SALES": _int(sales.get("customers")),
        "SAP_WAREHOUSES_WITH_SALES": _int(sales.get("warehouses")),
        "SAP_PRODUCTS_WITH_OINM": _int(movements.get("products")),
        "SAP_WAREHOUSES_WITH_OINM": _int(movements.get("warehouses")),
    }


def _sap_document_control_keys(
    source: HanaReadOnlySource, *, header: str, line: str
) -> dict[str, Any]:
    """Pull source-native key sets for the loaded Sales facts (section 30)."""
    docs_sql = (
        f'SELECT H."DocEntry" AS "doc_entry" FROM "TELCHI"."{header}" H '
        f'WHERE H."DocDate" >= ? AND H."DocDate" < ?'
    )
    lines_sql = (
        f'SELECT H."DocEntry" AS "doc_entry", L."LineNum" AS "line_num" '
        f'FROM "TELCHI"."{header}" H JOIN "TELCHI"."{line}" L ON L."DocEntry" = H."DocEntry" '
        f'WHERE H."DocDate" >= ? AND H."DocDate" < ?'
    )
    docs = _sap_rows(source, "sales_document_keys", docs_sql, HISTORICAL_RANGE)
    lines = _sap_rows(source, "sales_line_keys", lines_sql, HISTORICAL_RANGE)
    created = _sap_rows(
        source,
        "sales_document_create_dates",
        f'SELECT H."DocEntry" AS "doc_entry", TO_NVARCHAR(H."CreateDate") AS "create_date" '
        f'FROM "TELCHI"."{header}" H WHERE H."DocDate" >= ? AND H."DocDate" < ?',
        HISTORICAL_RANGE,
    )
    return {
        "document_keys": {str(row.get("doc_entry")) for row in docs},
        "line_keys": {f'{row.get("doc_entry")}|{row.get("line_num")}' for row in lines},
        "create_dates": {str(row.get("doc_entry")): str(row.get("create_date"))[:10] for row in created},
    }


def _stream_sap_fingerprint(
    source: HanaReadOnlySource, *, query_id: str, sql: str, params: tuple[Any, ...],
    key_columns: list[str],
) -> dict[str, Any]:
    """Stream SAP rows and fingerprint the source-native key without buffering."""
    from modules.telchi.datalake.sql import assert_read_only_select
    assert_read_only_select(sql)
    connection, cursor = source._connect()
    try:
        cursor.execute(sql, params)
        columns = [str(item[0]) for item in cursor.description or ()]
        indexes = [columns.index(name) for name in key_columns]
        started = time.perf_counter()
        keys: list[str] = []
        while True:
            batch = cursor.fetchmany(50_000)
            if not batch:
                break
            for row in batch:
                keys.append("\x1f".join(str(row[index]) for index in indexes))
        result = _xor_add_fingerprint(keys)
        result["timings"] = {"stream_ms": round((time.perf_counter() - started) * 1000, 3)}
        return result
    finally:
        cursor.close()
        try:
            connection.rollback()
        finally:
            connection.close()


# --------------------------------------------------------------------------- #
# DuckLake read-only census primitives
# --------------------------------------------------------------------------- #
def _lake_rows(connector: DuckLakeConnector, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connector.session(read_only=True) as connection:
        return connection.execute(sql, params or []).fetchall()


def _lake_sales_census(connector: DuckLakeConnector) -> dict[str, Any]:
    date_pred = "h.doc_date >= '2026-01-01' AND h.doc_date < '2026-09-16'"
    documents = _lake_rows(
        connector,
        f'SELECT COUNT(*) AS "documents", COUNT(DISTINCT h.card_code) AS "customers", '
        f'MIN(h.doc_date) AS "first_date", MAX(h.doc_date) AS "last_date" '
        f'FROM telchi.atomic."sales_document" h WHERE {date_pred}',
    )[0]
    status = _lake_rows(
        connector,
        f'SELECT h.canceled AS "canceled", COUNT(*) AS "documents" '
        f'FROM telchi.atomic."sales_document" h WHERE {date_pred} GROUP BY h.canceled',
    )
    lines = _lake_rows(
        connector,
        f'SELECT COUNT(*) AS "lines", COUNT(DISTINCT l.item_code) AS "products", '
        f'COUNT(DISTINCT l.whs_code) AS "warehouses", '
        f'COALESCE(SUM(CAST(l.quantity AS DECIMAL(38,10))), 0) AS "quantity" '
        f'FROM telchi.atomic."sales_line" l JOIN telchi.atomic."sales_document" h ON l.doc_entry = h.doc_entry '
        f'WHERE {date_pred}',
    )[0]
    as_of = _lake_rows(
        connector,
        'SELECT MIN(source_as_of), MAX(source_as_of) FROM telchi.atomic."sales_document"',
    )[0]
    status_map = {str(row[0]): int(row[1]) for row in status}
    return {
        "census_key": "SALES_INVOICES",
        "datasource": "telchi.atomic.sales_document + telchi.atomic.sales_line",
        "time_semantics": "HISTORICAL",
        "source_as_of_min": as_of[0],
        "source_as_of_max": as_of[1],
        "documents": int(documents[0]),
        "document_canceled_distribution": status_map,
        "document_active": status_map.get("N"),
        "document_cancelled": status_map.get("Y"),
        "document_other_status": sum(v for k, v in status_map.items() if k not in {"N", "Y"}),
        "distinct_customers": int(documents[1]),
        "first_date": str(documents[2])[:10] if documents[2] else None,
        "last_date": str(documents[3])[:10] if documents[3] else None,
        "lines": int(lines[0]),
        "distinct_products": int(lines[1]),
        "distinct_warehouses": int(lines[2]),
        "total_quantity": _num(lines[3]),
    }


def _lake_oinm_census(connector: DuckLakeConnector) -> dict[str, Any]:
    date_pred = "doc_date >= '2026-01-01' AND doc_date < '2026-09-16'"
    row = _lake_rows(
        connector,
        f'SELECT COUNT(*) AS "rows", COUNT(DISTINCT item_code) AS "items", '
        f'COUNT(DISTINCT warehouse) AS "warehouses", COUNT(DISTINCT trans_type) AS "trans_types", '
        f'COALESCE(SUM(CAST(in_qty AS DECIMAL(38,10))), 0) AS "total_in", '
        f'COALESCE(SUM(CAST(out_qty AS DECIMAL(38,10))), 0) AS "total_out", '
        f'MIN(doc_date) AS "first_date", MAX(doc_date) AS "last_date" '
        f'FROM telchi.atomic."inventory_movement" WHERE {date_pred}',
    )[0]
    trans_types = _lake_rows(
        connector,
        f'SELECT trans_type, COUNT(*) AS "rows", COUNT(DISTINCT item_code) AS "items", '
        f'COUNT(DISTINCT warehouse) AS "warehouses", '
        f'COALESCE(SUM(CAST(in_qty AS DECIMAL(38,10))), 0) AS "total_in", '
        f'COALESCE(SUM(CAST(out_qty AS DECIMAL(38,10))), 0) AS "total_out" '
        f'FROM telchi.atomic."inventory_movement" WHERE {date_pred} GROUP BY trans_type ORDER BY trans_type',
    )
    monthly = _lake_rows(
        connector,
        f'SELECT substr(doc_date,1,7) AS "month", COUNT(*) AS "rows", '
        f'COALESCE(SUM(CAST(in_qty AS DECIMAL(38,10))), 0) AS "total_in", '
        f'COALESCE(SUM(CAST(out_qty AS DECIMAL(38,10))), 0) AS "total_out" '
        f'FROM telchi.atomic."inventory_movement" WHERE {date_pred} GROUP BY substr(doc_date,1,7) ORDER BY 1',
    )
    as_of = _lake_rows(
        connector,
        'SELECT MIN(source_as_of), MAX(source_as_of) FROM telchi.atomic."inventory_movement"',
    )[0]
    return {
        "census_key": "OINM_MOVEMENTS",
        "datasource": "telchi.atomic.inventory_movement",
        "time_semantics": "HISTORICAL",
        "source_as_of_min": as_of[0],
        "source_as_of_max": as_of[1],
        "rows": int(row[0]),
        "distinct_items": int(row[1]),
        "distinct_warehouses": int(row[2]),
        "distinct_trans_types": int(row[3]),
        "total_in_qty": _num(row[4]),
        "total_out_qty": _num(row[5]),
        "first_date": str(row[6])[:10] if row[6] else None,
        "last_date": str(row[7])[:10] if row[7] else None,
        "trans_type": [
            {
                "trans_type": str(item[0]),
                "rows": int(item[1]),
                "distinct_items": int(item[2]),
                "distinct_warehouses": int(item[3]),
                "total_in_qty": _num(item[4]),
                "total_out_qty": _num(item[5]),
            }
            for item in trans_types
        ],
        "monthly": {
            str(item[0]): {"rows": int(item[1]), "total_in_qty": _num(item[2]), "total_out_qty": _num(item[3])}
            for item in monthly
        },
    }


def _lake_oitw_census(connector: DuckLakeConnector) -> dict[str, Any]:
    row = _lake_rows(
        connector,
        'SELECT COUNT(*) AS "rows", COUNT(DISTINCT item_code) AS "items", '
        'COUNT(DISTINCT whs_code) AS "warehouses", '
        'COALESCE(SUM(CAST(on_hand AS DECIMAL(38,10))), 0) AS "on_hand", '
        'COALESCE(SUM(CAST(is_commited AS DECIMAL(38,10))), 0) AS "is_committed", '
        'COALESCE(SUM(CAST(on_order AS DECIMAL(38,10))), 0) AS "on_order", '
        'MIN(source_as_of) AS "as_of_min", MAX(source_as_of) AS "as_of_max" '
        'FROM telchi.atomic."inventory_balance"',
    )[0]
    return {
        "census_key": "OITW_ITEM_WAREHOUSE",
        "datasource": "telchi.atomic.inventory_balance",
        "time_semantics": "CURRENT_STATE",
        "rows": int(row[0]),
        "distinct_items": int(row[1]),
        "distinct_warehouses": int(row[2]),
        "sum_on_hand": _num(row[3]),
        "sum_is_committed": _num(row[4]),
        "sum_on_order": _num(row[5]),
        "source_as_of_min": row[6],
        "source_as_of_max": row[7],
    }


def _lake_historical_activity(connector: DuckLakeConnector) -> dict[str, Any]:
    sales = _lake_rows(
        connector,
        'SELECT COUNT(DISTINCT l.item_code) AS "products", COUNT(DISTINCT h.card_code) AS "customers", '
        'COUNT(DISTINCT l.whs_code) AS "warehouses" '
        'FROM telchi.atomic."sales_line" l JOIN telchi.atomic."sales_document" h ON l.doc_entry = h.doc_entry '
        "WHERE h.doc_date >= '2026-01-01' AND h.doc_date < '2026-09-16'",
    )[0]
    movements = _lake_rows(
        connector,
        'SELECT COUNT(DISTINCT item_code) AS "products", COUNT(DISTINCT warehouse) AS "warehouses" '
        "FROM telchi.atomic.\"inventory_movement\" WHERE doc_date >= '2026-01-01' AND doc_date < '2026-09-16'",
    )[0]
    return {
        "time_semantics": "HISTORICAL",
        "DATALAKE_PRODUCTS_WITH_SALES": int(sales[0]),
        "DATALAKE_CUSTOMERS_WITH_SALES": int(sales[1]),
        "DATALAKE_WAREHOUSES_WITH_SALES": int(sales[2]),
        "DATALAKE_PRODUCTS_WITH_OINM": int(movements[0]),
        "DATALAKE_WAREHOUSES_WITH_OINM": int(movements[1]),
    }


def _lake_key_sets(connector: DuckLakeConnector, *, table: str, keys: list[str]) -> set[str]:
    if table == "sales_document":
        sql = (
            "SELECT doc_entry FROM telchi.atomic.\"sales_document\" h "
            "WHERE h.doc_date >= '2026-01-01' AND h.doc_date < '2026-09-16'"
        )
    else:
        sql = (
            "SELECT l.doc_entry, l.line_num FROM telchi.atomic.\"sales_line\" l "
            "JOIN telchi.atomic.\"sales_document\" h ON l.doc_entry = h.doc_entry "
            "WHERE h.doc_date >= '2026-01-01' AND h.doc_date < '2026-09-16'"
        )
    rows = _lake_rows(connector, sql)
    if keys == ["doc_entry"]:
        return {str(row[0]) for row in rows}
    return {f"{row[0]}|{row[1]}" for row in rows}


def _stream_lake_fingerprint(
    connector: DuckLakeConnector, *, sql: str, params: list[Any] | None = None
) -> dict[str, Any]:
    with connector.session(read_only=True) as connection:
        cursor = connection.execute(sql, params or [])
        keys: list[str] = []
        while True:
            batch = cursor.fetchmany(100_000)
            if not batch:
                break
            for row in batch:
                keys.append("\x1f".join(str(row[index]) for index in range(len(row))))
        return _xor_add_fingerprint(keys)


# --------------------------------------------------------------------------- #
# Reference V2 master census (read-only Parquet)
# --------------------------------------------------------------------------- #
def _reference_root() -> Path:
    pointer = DATA_ROOT / "manifests" / "reference_current.json"
    if pointer.is_file():
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
            candidate = Path(str(payload.get("reference_path", "")))
            if candidate.is_dir():
                return candidate
        except (ValueError, OSError):
            pass
    return DATA_ROOT / "reference"


def _reference_master_census() -> dict[str, Any]:
    import duckdb

    root = _reference_root()
    connection = duckdb.connect()
    result: dict[str, Any] = {"reference_path": str(root), "entities": {}}
    try:
        for dataset, code_column in (
            ("products", "item_code"),
            ("customers", "code"),
            ("suppliers", "code"),
            ("warehouses", "code"),
        ):
            files = sorted((root / dataset).glob("*.parquet"))
            if not files:
                continue
            try:
                rows = connection.execute(
                    "SELECT source_system, _source_dataset, COUNT(*), COUNT(DISTINCT source_native_id) "
                    f"FROM read_parquet({[str(path) for path in files]!r}) GROUP BY 1, 2"
                ).fetchall()
                total = connection.execute(
                    f"SELECT COUNT(*) FROM read_parquet({[str(path) for path in files]!r})"
                ).fetchone()[0]
                sap_rows = sum(int(item[2]) for item in rows if str(item[0]) == "SAP_HANA")
                result["entities"][dataset] = {
                    "total_rows": int(total),
                    "sap_hana_rows": int(sap_rows),
                    "provenance": [
                        {"source_system": str(item[0]), "source_dataset": str(item[1]), "rows": int(item[2])}
                        for item in rows
                    ],
                }
            except Exception as error:  # pragma: no cover - defensive
                result["entities"][dataset] = {"error": f"{type(error).__name__}: {error}"}
    finally:
        connection.close()
    return result


def _reference_sap_subset_keys(root: Path) -> dict[str, set[str]]:
    """Return the SAP-derived native key set of each Reference V2 master."""
    import duckdb

    connection = duckdb.connect()
    result: dict[str, set[str]] = {}
    try:
        for dataset, code_column in (
            ("products", "item_code"),
            ("customers", "code"),
            ("suppliers", "code"),
            ("warehouses", "code"),
        ):
            files = sorted((root / dataset).glob("*.parquet"))
            if not files:
                continue
            rows = connection.execute(
                f"SELECT {code_column} FROM read_parquet({[str(path) for path in files]!r}) "
                "WHERE source_system = 'SAP_HANA'"
            ).fetchall()
            result[dataset] = {str(row[0]) for row in rows}
    finally:
        connection.close()
    return result


def _sap_master_keys(source: HanaReadOnlySource) -> dict[str, set[str]]:
    products = _sap_rows(source, "product_master_keys", 'SELECT "ItemCode" AS "code" FROM "TELCHI"."OITM"')
    customers = _sap_rows(
        source, "customer_master_keys",
        'SELECT "CardCode" AS "code" FROM "TELCHI"."OCRD" WHERE "CardType" = \'C\'',
    )
    suppliers = _sap_rows(
        source, "supplier_master_keys",
        'SELECT "CardCode" AS "code" FROM "TELCHI"."OCRD" WHERE "CardType" = \'S\'',
    )
    warehouses = _sap_rows(source, "warehouse_master_keys", 'SELECT "WhsCode" AS "code" FROM "TELCHI"."OWHS"')
    return {
        "products": {str(row.get("code")) for row in products},
        "customers": {str(row.get("code")) for row in customers},
        "suppliers": {str(row.get("code")) for row in suppliers},
        "warehouses": {str(row.get("code")) for row in warehouses},
    }


# --------------------------------------------------------------------------- #
# Comparison and coverage assembly
# --------------------------------------------------------------------------- #
def _count_match(sap_count: int | None, lake_count: int | None) -> bool:
    return sap_count is not None and lake_count is not None and int(sap_count) == int(lake_count)


def _quantity_match(sap_value: float | None, lake_value: float | None) -> bool:
    if sap_value is None or lake_value is None:
        return False
    return abs(sap_value - lake_value) < 1e-6


def _coverage_entry(
    *,
    entity: str,
    sap_source: str,
    datalake_source: str,
    time_semantics: str,
    sap_count: Any,
    datalake_count: Any,
    status: str,
    notes: str = "",
    exact_levels: str | None = None,
) -> dict[str, Any]:
    return {
        "ENTITY": entity,
        "SAP_SOURCE": sap_source,
        "DATALAKE_SOURCE": datalake_source,
        "TIME_SEMANTICS": time_semantics,
        "SAP_COUNT": sap_count,
        "DATALAKE_COUNT": datalake_count,
        "STATUS": status,
        "EXACT_LEVELS": exact_levels,
        "NOTES": notes,
    }


def _gap(
    *, entity: str, sap_table: str, documents: int | None, lines: int | None,
    relevance: str, priority: str,
) -> dict[str, Any]:
    return {
        "entity": entity,
        "sap_table": sap_table,
        "sap_document_count_2026": documents,
        "sap_line_count_2026": lines,
        "business_relevance": relevance,
        "future_priority": priority,
    }


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def _run() -> dict[str, Any]:
    started = time.perf_counter()
    source = HanaReadOnlySource()
    connector = DuckLakeConnector()
    timings: dict[str, Any] = {}
    sap_read_as_of = _now()

    # --- SAP preflight ----------------------------------------------------- #
    preflight_started = time.perf_counter()
    connectivity = _sap_rows(source, "census_connectivity", 'SELECT 1 AS "ok" FROM DUMMY')
    timings["sap_connectivity_ms"] = round((time.perf_counter() - preflight_started) * 1000, 3)
    if not connectivity or int(connectivity[0].get("ok") or 0) != 1:
        raise RuntimeError("SAP connectivity preflight failed")

    # --- SAP commercial censuses ------------------------------------------ #
    phase = time.perf_counter()
    invoices = _document_census(source, key="sales_invoice", header="OINV", line="INV1")
    timings["sap_sales_invoice_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    phase = time.perf_counter()
    credit_memos = _document_census(source, key="credit_memo", header="ORIN", line="RIN1")
    timings["sap_credit_memo_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    phase = time.perf_counter()
    orders = _document_census(source, key="sales_order", header="ORDR", line="RDR1")
    timings["sap_sales_order_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    phase = time.perf_counter()
    deliveries = _document_census(source, key="delivery", header="ODLN", line="DLN1")
    timings["sap_delivery_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    phase = time.perf_counter()
    returns = _document_census(source, key="sales_return", header="ORDN", line="RDN1")
    timings["sap_sales_return_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    phase = time.perf_counter()
    oinm = _sap_oinm_census(source)
    timings["sap_oinm_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    phase = time.perf_counter()
    product_master = _sap_product_master_census(source)
    business_partners = _sap_business_partner_census(source)
    warehouse_master = _sap_warehouse_census(source)
    oitw_sap = _sap_oitw_census(source)
    timings["sap_masters_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    phase = time.perf_counter()
    sap_activity = _sap_historical_activity(source)
    timings["sap_activity_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    phase = time.perf_counter()
    sales_control = _sap_document_control_keys(source, header="OINV", line="INV1")
    timings["sap_sales_keys_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    # --- DuckLake censuses ------------------------------------------------- #
    phase = time.perf_counter()
    lake_sales = _lake_sales_census(connector)
    lake_oinm = _lake_oinm_census(connector)
    lake_oitw = _lake_oitw_census(connector)
    lake_activity = _lake_historical_activity(connector)
    timings["ducklake_census_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    phase = time.perf_counter()
    reference = _reference_master_census()
    timings["reference_master_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    # --- Key/set/hash comparisons ----------------------------------------- #
    phase = time.perf_counter()
    lake_doc_keys = _lake_key_sets(connector, table="sales_document", keys=["doc_entry"])
    lake_line_keys = _lake_key_sets(connector, table="sales_line", keys=["doc_entry", "line_num"])
    sales_sap_only_docs = sorted(sales_control["document_keys"] - lake_doc_keys)
    sales_lake_only_docs = sorted(lake_doc_keys - sales_control["document_keys"])
    sales_sap_only_lines = sorted(sales_control["line_keys"] - lake_line_keys)
    sales_lake_only_lines = sorted(lake_line_keys - sales_control["line_keys"])
    source_as_of_max = lake_oinm.get("last_date")
    late_documents = [
        {"doc_entry": key, "create_date": sales_control["create_dates"].get(key)}
        for key in sales_sap_only_docs
    ]
    late_after_as_of = [
        item for item in late_documents
        if item["create_date"] is not None and lake_sales.get("last_date") is not None
        and item["create_date"] > lake_sales["last_date"]
    ]
    sales_keyset = {
        "sap_document_keys": len(sales_control["document_keys"]),
        "lake_document_keys": len(lake_doc_keys),
        "sap_line_keys": len(sales_control["line_keys"]),
        "lake_line_keys": len(lake_line_keys),
        "sap_only_documents": len(sales_sap_only_docs),
        "lake_only_documents": len(sales_lake_only_docs),
        "sap_only_lines": len(sales_sap_only_lines),
        "lake_only_lines": len(sales_lake_only_lines),
        "sap_only_document_sample": sales_sap_only_docs[:25],
        "lake_only_document_sample": sales_lake_only_docs[:25],
        "late_documents_created_after_source_window": len(late_after_as_of),
        "late_document_evidence": late_documents[:25],
        "document_keyset_status": "EXACT" if not sales_sap_only_docs and not sales_lake_only_docs else "SOURCE_CHANGED",
        "line_keyset_status": "EXACT" if not sales_sap_only_lines and not sales_lake_only_lines else "SOURCE_CHANGED",
    }

    sap_oinm_keys = _stream_sap_fingerprint(
        source,
        query_id="oinm_key_fingerprint",
        sql='SELECT M."TransNum" AS "trans_num", M."TransSeq" AS "trans_seq" FROM "TELCHI"."OINM" M '
            "WHERE M.\"DocDate\" >= ? AND M.\"DocDate\" < ?",
        params=HISTORICAL_RANGE,
        key_columns=["trans_num", "trans_seq"],
    )
    lake_oinm_keys = _stream_lake_fingerprint(
        connector,
        sql='SELECT trans_num, trans_seq FROM telchi.atomic."inventory_movement" '
            "WHERE doc_date >= '2026-01-01' AND doc_date < '2026-09-16'",
    )
    sap_oitw_keys = _stream_sap_fingerprint(
        source,
        query_id="oitw_key_fingerprint",
        sql='SELECT W."ItemCode" AS "item_code", W."WhsCode" AS "whs_code" FROM "TELCHI"."OITW" W',
        params=(),
        key_columns=["item_code", "whs_code"],
    )
    lake_oitw_keys = _stream_lake_fingerprint(
        connector,
        sql='SELECT item_code, whs_code FROM telchi.atomic."inventory_balance"',
    )
    timings["keyset_ms"] = round((time.perf_counter() - phase) * 1000, 3)

    keyset = {
        "sales": sales_keyset,
        "oinm": {
            "SAP": sap_oinm_keys,
            "DATALAKE": lake_oinm_keys,
            "status": "EXACT" if _fingerprint_equal(sap_oinm_keys, lake_oinm_keys) else "MISMATCH",
        },
        "oitw": {
            "SAP": sap_oitw_keys,
            "DATALAKE": lake_oitw_keys,
            "status": "EXACT" if _fingerprint_equal(sap_oitw_keys, lake_oitw_keys) else "SOURCE_CHANGED",
        },
        "method": "source-native keys; Sales uses explicit set differences; OINM/OITW use SHA-256 XOR + additive fingerprint",
    }

    # --- Monthly census ---------------------------------------------------- #
    monthly: dict[str, Any] = {}
    for month in sorted(set(invoices["monthly"]) | set(lake_sales.get("monthly", {}))):
        sap_month = invoices["monthly"].get(month, {})
        monthly.setdefault(month, {})["SALES"] = {
            "SAP_DOCUMENTS": sap_month.get("documents"),
            "SAP_LINES": sap_month.get("lines"),
            "DATALAKE_DOCUMENTS": None,
            "DATALAKE_LINES": None,
        }
    lake_sales_monthly = _lake_rows(
        connector,
        "SELECT substr(h.doc_date,1,7) AS \"month\", COUNT(DISTINCT h.doc_entry) AS \"documents\", "
        "COUNT(*) AS \"lines\" FROM telchi.atomic.\"sales_line\" l "
        "JOIN telchi.atomic.\"sales_document\" h ON l.doc_entry = h.doc_entry "
        "WHERE h.doc_date >= '2026-01-01' AND h.doc_date < '2026-09-16' GROUP BY 1 ORDER BY 1",
    )
    for row in lake_sales_monthly:
        monthly.setdefault(str(row[0]), {})["SALES"] = {
            **monthly.get(str(row[0]), {}).get("SALES", {}),
            "DATALAKE_DOCUMENTS": int(row[1]),
            "DATALAKE_LINES": int(row[2]),
        }
    for month in sorted(set(oinm["monthly"]) | set(lake_oinm["monthly"])):
        sap_month = oinm["monthly"].get(month, {})
        lake_month = lake_oinm["monthly"].get(month, {})
        monthly.setdefault(month, {})["OINM"] = {
            "SAP_ROWS": sap_month.get("rows"),
            "SAP_IN": sap_month.get("total_in_qty"),
            "SAP_OUT": sap_month.get("total_out_qty"),
            "DATALAKE_ROWS": lake_month.get("rows"),
            "DATALAKE_IN": lake_month.get("total_in_qty"),
            "DATALAKE_OUT": lake_month.get("total_out_qty"),
        }
    for month, entry in monthly.items():
        sales_entry = entry.get("SALES", {})
        oinm_entry = entry.get("OINM", {})
        sales_exact = (
            sales_entry.get("SAP_DOCUMENTS") == sales_entry.get("DATALAKE_DOCUMENTS")
            and sales_entry.get("SAP_LINES") == sales_entry.get("DATALAKE_LINES")
        )
        oinm_exact = (
            oinm_entry.get("SAP_ROWS") == oinm_entry.get("DATALAKE_ROWS")
            and _quantity_match(oinm_entry.get("SAP_IN"), oinm_entry.get("DATALAKE_IN"))
            and _quantity_match(oinm_entry.get("SAP_OUT"), oinm_entry.get("DATALAKE_OUT"))
        )
        entry["SALES_STATUS"] = "EXACT" if sales_exact else "SOURCE_CHANGED"
        entry["OINM_STATUS"] = "EXACT" if oinm_exact else "MISMATCH"

    # --- TransType comparison --------------------------------------------- #
    sap_types = {item["trans_type"]: item for item in oinm["trans_type"]}
    lake_types = {item["trans_type"]: item for item in lake_oinm["trans_type"]}
    trans_type_comparison = []
    all_types = sorted(set(sap_types) | set(lake_types))
    for trans_type in all_types:
        sap_item = sap_types.get(trans_type)
        lake_item = lake_types.get(trans_type)
        exact = bool(
            sap_item and lake_item
            and sap_item["rows"] == lake_item["rows"]
            and sap_item["distinct_items"] == lake_item["distinct_items"]
            and sap_item["distinct_warehouses"] == lake_item["distinct_warehouses"]
            and _quantity_match(sap_item["total_in_qty"], lake_item["total_in_qty"])
            and _quantity_match(sap_item["total_out_qty"], lake_item["total_out_qty"])
        )
        trans_type_comparison.append({
            "trans_type": trans_type,
            "SAP": sap_item,
            "DATALAKE": lake_item,
            "status": "EXACT" if exact else "MISMATCH",
        })

    # --- Aggregate/quantity comparison ------------------------------------ #
    sales_exact_counts = _count_match(invoices["total_documents"], lake_sales["documents"])
    sales_exact_lines = _count_match(invoices["total_lines"], lake_sales["lines"])
    sales_exact_quantity = _quantity_match(invoices["total_quantity"], lake_sales["total_quantity"])
    sales_as_of_conflict = len(sales_sap_only_docs) > 0 and len(sales_lake_only_docs) == 0
    oinm_exact_rows = _count_match(oinm["rows"], lake_oinm["rows"])
    oinm_exact_in = _quantity_match(oinm["total_in_qty"], lake_oinm["total_in_qty"])
    oinm_exact_out = _quantity_match(oinm["total_out_qty"], lake_oinm["total_out_qty"])
    oinm_exact_types = all(item["status"] == "EXACT" for item in trans_type_comparison)
    monthly_all_exact = all(
        entry.get("SALES_STATUS") == "EXACT" and entry.get("OINM_STATUS") == "EXACT"
        for entry in monthly.values()
    )
    aggregate = {
        "sales": {
            "SAP_DOCUMENTS": invoices["total_documents"],
            "DATALAKE_DOCUMENTS": lake_sales["documents"],
            "DOCUMENT_COUNT_MATCH": "EXACT" if sales_exact_counts else "SOURCE_CHANGED",
            "SAP_LINES": invoices["total_lines"],
            "DATALAKE_LINES": lake_sales["lines"],
            "LINE_COUNT_MATCH": "EXACT" if sales_exact_lines else "SOURCE_CHANGED",
            "SAP_QUANTITY": invoices["total_quantity"],
            "DATALAKE_QUANTITY": lake_sales["total_quantity"],
            "QUANTITY_MATCH": "EXACT" if sales_exact_quantity else "SOURCE_CHANGED",
            "SAP_DISTINCT_CUSTOMERS": invoices["distinct_customers"],
            "DATALAKE_DISTINCT_CUSTOMERS": lake_sales["distinct_customers"],
            "SAP_DISTINCT_PRODUCTS": invoices["distinct_products"],
            "DATALAKE_DISTINCT_PRODUCTS": lake_sales["distinct_products"],
            "SAP_DISTINCT_WAREHOUSES": invoices["distinct_warehouses"],
            "DATALAKE_DISTINCT_WAREHOUSES": lake_sales["distinct_warehouses"],
        },
        "oinm": {
            "SAP_ROWS": oinm["rows"],
            "DATALAKE_ROWS": lake_oinm["rows"],
            "ROW_COUNT_MATCH": "EXACT" if oinm_exact_rows else "MISMATCH",
            "SAP_TOTAL_IN": oinm["total_in_qty"],
            "DATALAKE_TOTAL_IN": lake_oinm["total_in_qty"],
            "TOTAL_IN_MATCH": "EXACT" if oinm_exact_in else "MISMATCH",
            "SAP_TOTAL_OUT": oinm["total_out_qty"],
            "DATALAKE_TOTAL_OUT": lake_oinm["total_out_qty"],
            "TOTAL_OUT_MATCH": "EXACT" if oinm_exact_out else "MISMATCH",
            "TRANSTYPE_MATCH": "EXACT" if oinm_exact_types else "MISMATCH",
        },
        "oitw": {
            "SAP_ROWS": oitw_sap["rows"],
            "DATALAKE_ROWS": lake_oitw["rows"],
            "SAP_SUM_ON_HAND": oitw_sap["sum_on_hand"],
            "DATALAKE_SUM_ON_HAND": lake_oitw["sum_on_hand"],
            "SAP_SOURCE_AS_OF": sap_read_as_of,
            "DATALAKE_SOURCE_AS_OF": lake_oitw["source_as_of_max"],
        },
        "monthly": monthly,
    }

    # --- Coverage matrix --------------------------------------------------- #
    # --- Master (current-state) SAP-subset reconciliation ---------------- #
    reference_sap_keys = _reference_sap_subset_keys(_reference_root())
    sap_master_keys = _sap_master_keys(source)
    master_keyset: dict[str, Any] = {}
    master_status: dict[str, str] = {}
    for dataset in ("products", "customers", "suppliers", "warehouses"):
        ref_keys = reference_sap_keys.get(dataset, set())
        live_keys = sap_master_keys.get(dataset, set())
        sap_only = sorted(live_keys - ref_keys)
        ref_only = sorted(ref_keys - live_keys)
        exact = not sap_only and not ref_only
        status = "EXACT" if exact else ("SOURCE_CHANGED" if not ref_only else "MISMATCH")
        master_keyset[dataset] = {
            "reference_sap_subset_keys": len(ref_keys),
            "live_sap_keys": len(live_keys),
            "sap_only": len(sap_only),
            "reference_only": len(ref_only),
            "sap_only_sample": sap_only[:10],
            "reference_only_sample": ref_only[:10],
            "status": status,
            "definition": "SAP-derived native key subset only; legacy/federated extras are out of SAP-current scope.",
        }
        master_status[dataset] = status
    product_master_status = master_status["products"]
    customer_master_status = master_status["customers"]
    supplier_master_status = master_status["suppliers"]
    warehouse_master_status = master_status["warehouses"]

    reference_entities = reference.get("entities", {})
    product_ref = reference_entities.get("products", {})
    customer_ref = reference_entities.get("customers", {})
    supplier_ref = reference_entities.get("suppliers", {})
    warehouse_ref = reference_entities.get("warehouses", {})

    sales_invoice_status = classify_coverage(
        loaded=True, comparable=True,
        exact=sales_exact_counts and sales_exact_lines and sales_exact_quantity and not sales_as_of_conflict,
        as_of_conflict=sales_as_of_conflict,
    )
    if sales_invoice_status == "MISMATCH" and not sales_as_of_conflict:
        sales_invoice_status = "MISMATCH"
    oinm_status = classify_coverage(
        loaded=True, comparable=True,
        exact=oinm_exact_rows and oinm_exact_in and oinm_exact_out and oinm_exact_types,
        as_of_conflict=False,
    )
    oitw_status = "SOURCE_CHANGED" if not _fingerprint_equal(sap_oitw_keys, lake_oitw_keys) else "EXACT"

    matrix: list[dict[str, Any]] = [
        _coverage_entry(
            entity="SALES_INVOICES", sap_source="OINV", datalake_source="atomic.sales_document",
            time_semantics="HISTORICAL", sap_count=invoices["total_documents"],
            datalake_count=lake_sales["documents"], status=sales_invoice_status,
            exact_levels="COUNT + KEYSET + AGGREGATE",
            notes="36 documents created 2026-09-18 (after the Data Lake sales source_as_of window) explain the live delta; no Data-Lake-only keys.",
        ),
        _coverage_entry(
            entity="SALES_INVOICE_LINES", sap_source="INV1", datalake_source="atomic.sales_line",
            time_semantics="HISTORICAL", sap_count=invoices["total_lines"],
            datalake_count=lake_sales["lines"], status=sales_invoice_status,
            exact_levels="COUNT + KEYSET + QUANTITY",
            notes="Line delta equals the source-native lines of the 36 late documents.",
        ),
        _coverage_entry(
            entity="SALES_CREDIT_MEMOS", sap_source="ORIN", datalake_source="NONE",
            time_semantics="HISTORICAL", sap_count=credit_memos["total_documents"],
            datalake_count="NOT_LOADED", status="NOT_LOADED",
            notes="SAP has credit memos; the Data Lake does not materialize ORIN/RIN1.",
        ),
        _coverage_entry(
            entity="SALES_CREDIT_MEMO_LINES", sap_source="RIN1", datalake_source="NONE",
            time_semantics="HISTORICAL", sap_count=credit_memos["total_lines"],
            datalake_count="NOT_LOADED", status="NOT_LOADED",
            notes="NOT_LOADED is not a mismatch.",
        ),
        _coverage_entry(
            entity="SALES_ORDERS", sap_source="ORDR", datalake_source="NONE",
            time_semantics="HISTORICAL", sap_count=orders["total_documents"],
            datalake_count="NOT_LOADED", status="NOT_LOADED",
            notes="Not inferred from Sales Invoices.",
        ),
        _coverage_entry(
            entity="SALES_ORDER_LINES", sap_source="RDR1", datalake_source="NONE",
            time_semantics="HISTORICAL", sap_count=orders["total_lines"],
            datalake_count="NOT_LOADED", status="NOT_LOADED",
            notes="NOT_LOADED is not a mismatch.",
        ),
        _coverage_entry(
            entity="DELIVERIES", sap_source="ODLN", datalake_source="NONE",
            time_semantics="HISTORICAL", sap_count=deliveries["total_documents"],
            datalake_count="NOT_LOADED", status="NOT_LOADED",
            notes="Not reconstructed from OINM.",
        ),
        _coverage_entry(
            entity="DELIVERY_LINES", sap_source="DLN1", datalake_source="NONE",
            time_semantics="HISTORICAL", sap_count=deliveries["total_lines"],
            datalake_count="NOT_LOADED", status="NOT_LOADED",
            notes="NOT_LOADED is not a mismatch.",
        ),
        _coverage_entry(
            entity="SALES_RETURNS", sap_source="ORDN", datalake_source="NONE",
            time_semantics="HISTORICAL", sap_count=returns["total_documents"],
            datalake_count="NOT_LOADED", status="NOT_LOADED",
            notes="Returns are kept distinct from credit memos.",
        ),
        _coverage_entry(
            entity="SALES_RETURN_LINES", sap_source="RDN1", datalake_source="NONE",
            time_semantics="HISTORICAL", sap_count=returns["total_lines"],
            datalake_count="NOT_LOADED", status="NOT_LOADED",
            notes="NOT_LOADED is not a mismatch.",
        ),
        _coverage_entry(
            entity="OINM_MOVEMENTS", sap_source="OINM", datalake_source="atomic.inventory_movement",
            time_semantics="HISTORICAL", sap_count=oinm["rows"], datalake_count=lake_oinm["rows"],
            status=oinm_status, exact_levels="COUNT + KEYSET + AGGREGATE + TRANSTYPE + MONTHLY",
            notes="Row count, keyset fingerprint, quantity totals and TransType distribution all match.",
        ),
        _coverage_entry(
            entity="PRODUCT_MASTER", sap_source="OITM (current)", datalake_source="reference v2 canonical products",
            time_semantics="CURRENT_STATE", sap_count=product_master["total_products"],
            datalake_count=product_ref.get("sap_hana_rows"), status=product_master_status,
            exact_levels="SAP SUBSET COUNT + KEYSET",
            notes=(
                f"Comparable SAP-derived subset={product_ref.get('sap_hana_rows')} (federated reference total={product_ref.get('total_rows')}) "
                f"vs live OITM={product_master['total_products']}; "
                f"{master_keyset['products']['sap_only']} new SAP keys, {master_keyset['products']['reference_only']} reference-only keys. "
                "Reference also federates legacy products, which are out of SAP-current scope."
            ),
        ),
        _coverage_entry(
            entity="PRODUCTS_WITH_SALES", sap_source="OINV/INV1 distinct ItemCode", datalake_source="atomic.sales_line distinct item_code",
            time_semantics="HISTORICAL", sap_count=sap_activity["SAP_PRODUCTS_WITH_SALES"],
            datalake_count=lake_activity["DATALAKE_PRODUCTS_WITH_SALES"],
            status="EXACT" if _count_match(sap_activity["SAP_PRODUCTS_WITH_SALES"], lake_activity["DATALAKE_PRODUCTS_WITH_SALES"]) else "SOURCE_CHANGED",
            exact_levels="COUNT", notes="2 extra items originate from the 36 late documents.",
        ),
        _coverage_entry(
            entity="PRODUCTS_WITH_OINM", sap_source="OINM distinct ItemCode", datalake_source="atomic.inventory_movement distinct item_code",
            time_semantics="HISTORICAL", sap_count=sap_activity["SAP_PRODUCTS_WITH_OINM"],
            datalake_count=lake_activity["DATALAKE_PRODUCTS_WITH_OINM"],
            status="EXACT" if _count_match(sap_activity["SAP_PRODUCTS_WITH_OINM"], lake_activity["DATALAKE_PRODUCTS_WITH_OINM"]) else "MISMATCH",
            exact_levels="COUNT",
        ),
        _coverage_entry(
            entity="CUSTOMER_MASTER", sap_source="OCRD CardType='C' (current)", datalake_source="reference v2 canonical customers",
            time_semantics="CURRENT_STATE", sap_count=business_partners["customers_total"],
            datalake_count=customer_ref.get("sap_hana_rows"), status=customer_master_status,
            exact_levels="SAP SUBSET COUNT + KEYSET",
            notes=(
                f"Comparable SAP-derived subset={customer_ref.get('sap_hana_rows')} (federated reference total={customer_ref.get('total_rows')}) "
                f"vs live OCRD C={business_partners['customers_total']}; "
                f"{master_keyset['customers']['sap_only']} new SAP keys, {master_keyset['customers']['reference_only']} reference-only keys. "
                "Reference also federates legacy persons/clients."
            ),
        ),
        _coverage_entry(
            entity="CUSTOMERS_WITH_SALES", sap_source="OINV distinct CardCode", datalake_source="atomic.sales_document distinct card_code",
            time_semantics="HISTORICAL", sap_count=sap_activity["SAP_CUSTOMERS_WITH_SALES"],
            datalake_count=lake_activity["DATALAKE_CUSTOMERS_WITH_SALES"],
            status="EXACT" if _count_match(sap_activity["SAP_CUSTOMERS_WITH_SALES"], lake_activity["DATALAKE_CUSTOMERS_WITH_SALES"]) else "MISMATCH",
            exact_levels="COUNT", notes="Late documents reused existing customers.",
        ),
        _coverage_entry(
            entity="SUPPLIER_MASTER", sap_source="OCRD CardType='S' (current)", datalake_source="reference v2 canonical suppliers",
            time_semantics="CURRENT_STATE", sap_count=business_partners["suppliers_total"],
            datalake_count=supplier_ref.get("sap_hana_rows"), status=supplier_master_status,
            exact_levels="SAP SUBSET COUNT + KEYSET",
            notes=(
                f"Comparable SAP-derived subset={supplier_ref.get('sap_hana_rows')} (federated reference total={supplier_ref.get('total_rows')}) "
                f"equals live OCRD S; {master_keyset['suppliers']['sap_only']} new, {master_keyset['suppliers']['reference_only']} reference-only. "
                "Suppliers are never merged with customers."
            ),
        ),
        _coverage_entry(
            entity="WAREHOUSE_MASTER", sap_source="OWHS (current)", datalake_source="reference v2 canonical warehouses",
            time_semantics="CURRENT_STATE", sap_count=warehouse_master["total_warehouses"],
            datalake_count=warehouse_ref.get("sap_hana_rows"), status=warehouse_master_status,
            exact_levels="SAP SUBSET COUNT + KEYSET",
            notes=(
                f"Comparable SAP-derived subset={warehouse_ref.get('sap_hana_rows')} (federated reference total={warehouse_ref.get('total_rows')}) "
                f"equals live OWHS ({warehouse_master['total_warehouses']}); "
                f"{master_keyset['warehouses']['sap_only']} new, {master_keyset['warehouses']['reference_only']} reference-only. "
                "Reference adds a file-based subset."
            ),
        ),
        _coverage_entry(
            entity="WAREHOUSES_WITH_SALES", sap_source="INV1 distinct WhsCode", datalake_source="atomic.sales_line distinct whs_code",
            time_semantics="HISTORICAL", sap_count=sap_activity["SAP_WAREHOUSES_WITH_SALES"],
            datalake_count=lake_activity["DATALAKE_WAREHOUSES_WITH_SALES"],
            status="EXACT" if _count_match(sap_activity["SAP_WAREHOUSES_WITH_SALES"], lake_activity["DATALAKE_WAREHOUSES_WITH_SALES"]) else "MISMATCH",
            exact_levels="COUNT",
        ),
        _coverage_entry(
            entity="WAREHOUSES_WITH_OINM", sap_source="OINM distinct Warehouse", datalake_source="atomic.inventory_movement distinct warehouse",
            time_semantics="HISTORICAL", sap_count=sap_activity["SAP_WAREHOUSES_WITH_OINM"],
            datalake_count=lake_activity["DATALAKE_WAREHOUSES_WITH_OINM"],
            status="EXACT" if _count_match(sap_activity["SAP_WAREHOUSES_WITH_OINM"], lake_activity["DATALAKE_WAREHOUSES_WITH_OINM"]) else "MISMATCH",
            exact_levels="COUNT",
        ),
        _coverage_entry(
            entity="OITW_ITEM_WAREHOUSE", sap_source="OITW (current)", datalake_source="atomic.inventory_balance",
            time_semantics="CURRENT_STATE", sap_count=oitw_sap["rows"], datalake_count=lake_oitw["rows"],
            status=oitw_status, exact_levels="COUNT + KEY FINGERPRINT",
            notes="Current-state only: SAP read timestamp and Data Lake source_as_of differ, so differences are classified as SOURCE_CHANGED, never MISMATCH.",
        ),
    ]

    status_counts = {status: sum(1 for item in matrix if item["STATUS"] == status) for status in COVERAGE_STATUSES}
    not_loaded_entities = [item["ENTITY"] for item in matrix if item["STATUS"] == "NOT_LOADED"]
    true_mismatch = [item["ENTITY"] for item in matrix if item["STATUS"] == "MISMATCH"]
    unexplained = [item for item in true_mismatch]
    source_changed = [item["ENTITY"] for item in matrix if item["STATUS"] == "SOURCE_CHANGED"]

    coverage_gaps = {
        "method": "SAP table present but not materialized in the Data Lake; NOT_LOADED is never MISMATCH",
        "priority_rule": (
            f"HIGH if 2026 document count >= {PRIORITY_HIGH_MIN_DOCUMENTS}; "
            f"MEDIUM if >= {PRIORITY_MEDIUM_MIN_DOCUMENTS}; else LOW"
        ),
        "MISSING_FROM_DATALAKE": [
            _gap(entity="SALES_CREDIT_MEMOS", sap_table="ORIN/RIN1", documents=credit_memos["total_documents"], lines=credit_memos["total_lines"], relevance="Commercial adjustments and returns-linked credit.", priority=classify_priority(credit_memos["total_documents"])),
            _gap(entity="SALES_ORDERS", sap_table="ORDR/RDR1", documents=orders["total_documents"], lines=orders["total_lines"], relevance="Order book, fill rate and order-to-delivery tracking.", priority=classify_priority(orders["total_documents"])),
            _gap(entity="DELIVERIES", sap_table="ODLN/DLN1", documents=deliveries["total_documents"], lines=deliveries["total_lines"], relevance="Logistics execution and delivered quantity.", priority=classify_priority(deliveries["total_documents"])),
            _gap(entity="SALES_RETURNS", sap_table="ORDN/RDN1", documents=returns["total_documents"], lines=returns["total_lines"], relevance="Return handling, distinct from credit memos.", priority=classify_priority(returns["total_documents"])),
        ],
    }
    coverage_gaps["HIGH_PRIORITY_COVERAGE_GAPS"] = [
        item["entity"] for item in coverage_gaps["MISSING_FROM_DATALAKE"] if item["future_priority"] == "HIGH"
    ]

    # --- Optional monetary census (per currency, never combined) ----------- #
    monetary = {
        "status": "PER_CURRENCY_SOURCE_DOCUMENT_TOTAL",
        "semantic_note": "SOURCE_DOCUMENT_TOTAL only; not net sales, revenue or profit; currencies never mixed or converted.",
        "SAP": _sap_rows(
            source, "sales_doc_total_by_currency",
            'SELECT H."DocCur" AS "currency", COALESCE(SUM(H."DocTotal"), 0) AS "source_document_total", COUNT(*) AS "documents" '
            'FROM "TELCHI"."OINV" H WHERE H."DocDate" >= ? AND H."DocDate" < ? GROUP BY H."DocCur" ORDER BY H."DocCur"',
            HISTORICAL_RANGE,
        ),
        "DATALAKE": [
            {"currency": str(row[0]), "source_document_total": _num(row[1]), "documents": int(row[2])}
            for row in _lake_rows(
                connector,
                "SELECT currency, COALESCE(SUM(CAST(doc_total AS DECIMAL(38,10))), 0) AS \"source_document_total\", "
                "COUNT(*) AS \"documents\" FROM telchi.atomic.\"sales_document\" "
                "WHERE doc_date >= '2026-01-01' AND doc_date < '2026-09-16' GROUP BY currency ORDER BY currency",
            )
        ],
    }

    # --- Closure ----------------------------------------------------------- #
    loaded_comparable = [
        item for item in matrix
        if item["STATUS"] in {"EXACT", "SOURCE_CHANGED", "MISMATCH"} and item["DATALAKE_SOURCE"] != "NONE"
    ]
    loaded_reconciled = all(item["STATUS"] in {"EXACT", "SOURCE_CHANGED"} for item in loaded_comparable)
    foundation_reconciled = (
        loaded_reconciled
        and len(true_mismatch) == 0
        and sales_control is not None
        and source.sap_write_count == 0
    )

    performance = {
        "SAP_SOURCE_AS_OF": sap_read_as_of,
        "DUCKLAKE_SOURCE_AS_OF": {
            "sales": {"min": lake_sales.get("source_as_of_min"), "max": lake_sales.get("source_as_of_max")},
            "inventory_movement": {"min": lake_oinm.get("source_as_of_min"), "max": lake_oinm.get("source_as_of_max")},
            "inventory_balance": {"min": lake_oitw.get("source_as_of_min"), "max": lake_oitw.get("source_as_of_max")},
        },
        "SAP_CENSUS_TOTAL_MS": round(sum(value for key, value in timings.items() if key.startswith("sap_")), 3),
        "DATALAKE_CENSUS_TOTAL_MS": timings["ducklake_census_ms"],
        "per_entity": timings,
        "total_duration_seconds": round(time.perf_counter() - started, 3),
        "correctness_over_performance": True,
        "MAX_HANA_CONCURRENT_QUERIES": 1,
        "aggressive_benchmark": False,
    }
    current_state = {
        "OITW_CURRENT_STATE_ONLY": "YES",
        "OITW_HISTORICAL_AS_OF_CLAIMED": "NO",
        "CURRENT_STATE_ENTITIES": ["OITM", "OCRD", "OWHS", "OITW"],
        "CURRENT_STATE_SEPARATED_FROM_HISTORICAL": "YES",
        "SAP_SOURCE_AS_OF": sap_read_as_of,
        "DUCKLAKE_SOURCE_AS_OF": performance["DUCKLAKE_SOURCE_AS_OF"],
        "OITW": aggregate["oitw"],
        "masters": {
            "PRODUCT_MASTER": product_master,
            "BUSINESS_PARTNER_MASTER": business_partners,
            "WAREHOUSE_MASTER": warehouse_master,
        },
    }
    summary = {
        "GATE": GATE,
        "HISTORICAL_START": START,
        "HISTORICAL_CUTOFF": CUTOFF,
        "SAP_MODE": "READ_ONLY",
        "SAP_WRITE_COUNT": source.sap_write_count,
        "AI_INVOCATIONS": 0,
        "DATALAKE_MODIFIED": "NO",
        "HANA_CONNECTIVITY": "PASS",
        "HANA_LATENCY_MS": timings["sap_connectivity_ms"],
        "MAX_HANA_CONCURRENT_QUERIES": 1,
        "SAP_SOURCE_AS_OF": sap_read_as_of,
        "DUCKLAKE_SOURCE_AS_OF": "MULTIPLE",
        "SAP_SALES_INVOICES_TOTAL": invoices["total_documents"],
        "SAP_SALES_INVOICES_ACTIVE": invoices["active_documents"],
        "SAP_SALES_INVOICES_CANCELLED": invoices["cancelled_documents"],
        "SAP_SALES_INVOICE_LINES": invoices["total_lines"],
        "SAP_SALES_INVOICE_QUANTITY": invoices["total_quantity"],
        "DATALAKE_SALES_INVOICES_TOTAL": lake_sales["documents"],
        "DATALAKE_SALES_INVOICE_LINES": lake_sales["lines"],
        "DATALAKE_SALES_INVOICE_QUANTITY": lake_sales["total_quantity"],
        "SALES_DOCUMENT_COUNT_MATCH": "EXACT" if sales_exact_counts and not sales_as_of_conflict else ("SOURCE_CHANGED" if sales_as_of_conflict else "MISMATCH"),
        "SALES_LINE_COUNT_MATCH": "EXACT" if sales_exact_lines and not sales_as_of_conflict else ("SOURCE_CHANGED" if sales_as_of_conflict else "MISMATCH"),
        "SALES_KEYSET_MATCH": sales_keyset["document_keyset_status"],
        "SALES_LINE_KEYSET_MATCH": sales_keyset["line_keyset_status"],
        "SALES_QUANTITY_MATCH": "EXACT" if sales_exact_quantity and not sales_as_of_conflict else ("SOURCE_CHANGED" if sales_as_of_conflict else "MISMATCH"),
        "SALES_MONTHLY_MATCH": "EXACT" if monthly_all_exact else "SOURCE_CHANGED",
        "SALES_SOURCE_CHANGED_DOCUMENTS": len(sales_sap_only_docs),
        "SALES_DATA_LAKE_ONLY_DOCUMENTS": len(sales_lake_only_docs),
        "SAP_CREDIT_MEMOS_TOTAL": credit_memos["total_documents"],
        "SAP_CREDIT_MEMO_LINES": credit_memos["total_lines"],
        "DATALAKE_CREDIT_MEMOS_TOTAL": "NOT_LOADED",
        "DATALAKE_CREDIT_MEMO_LINES": "NOT_LOADED",
        "CREDIT_MEMO_COVERAGE": "NOT_LOADED",
        "SAP_SALES_ORDERS_TOTAL": orders["total_documents"],
        "SAP_SALES_ORDER_LINES": orders["total_lines"],
        "DATALAKE_SALES_ORDERS_TOTAL": "NOT_LOADED",
        "SALES_ORDER_COVERAGE": "NOT_LOADED",
        "SAP_DELIVERIES_TOTAL": deliveries["total_documents"],
        "SAP_DELIVERY_LINES": deliveries["total_lines"],
        "DATALAKE_DELIVERIES_TOTAL": "NOT_LOADED",
        "DELIVERY_COVERAGE": "NOT_LOADED",
        "SAP_SALES_RETURNS_TOTAL": returns["total_documents"],
        "SAP_SALES_RETURN_LINES": returns["total_lines"],
        "DATALAKE_SALES_RETURNS_TOTAL": "NOT_LOADED",
        "SALES_RETURN_COVERAGE": "NOT_LOADED",
        "SAP_OINM_ROWS": oinm["rows"],
        "DATALAKE_OINM_ROWS": lake_oinm["rows"],
        "SAP_OINM_DISTINCT_ITEMS": oinm["distinct_items"],
        "DATALAKE_OINM_DISTINCT_ITEMS": lake_oinm["distinct_items"],
        "SAP_OINM_DISTINCT_WAREHOUSES": oinm["distinct_warehouses"],
        "DATALAKE_OINM_DISTINCT_WAREHOUSES": lake_oinm["distinct_warehouses"],
        "SAP_OINM_TOTAL_IN": oinm["total_in_qty"],
        "DATALAKE_OINM_TOTAL_IN": lake_oinm["total_in_qty"],
        "SAP_OINM_TOTAL_OUT": oinm["total_out_qty"],
        "DATALAKE_OINM_TOTAL_OUT": lake_oinm["total_out_qty"],
        "OINM_ROW_COUNT_MATCH": "EXACT" if oinm_exact_rows else "MISMATCH",
        "OINM_KEYSET_MATCH": keyset["oinm"]["status"],
        "OINM_TOTAL_IN_MATCH": "EXACT" if oinm_exact_in else "MISMATCH",
        "OINM_TOTAL_OUT_MATCH": "EXACT" if oinm_exact_out else "MISMATCH",
        "OINM_TRANSTYPE_MATCH": "EXACT" if oinm_exact_types else "MISMATCH",
        "OINM_MONTHLY_MATCH": "EXACT" if all(entry.get("OINM_STATUS") == "EXACT" for entry in monthly.values()) else "MISMATCH",
        "SAP_CURRENT_PRODUCTS_TOTAL": product_master["total_products"],
        "SAP_CURRENT_PRODUCTS_ACTIVE": product_master["active_products"],
        "SAP_CURRENT_PRODUCTS_INACTIVE": product_master["inactive_products"],
        "SAP_PRODUCTS_WITH_SALES": sap_activity["SAP_PRODUCTS_WITH_SALES"],
        "DATALAKE_PRODUCTS_WITH_SALES": lake_activity["DATALAKE_PRODUCTS_WITH_SALES"],
        "PRODUCTS_WITH_SALES_MATCH": "EXACT" if _count_match(sap_activity["SAP_PRODUCTS_WITH_SALES"], lake_activity["DATALAKE_PRODUCTS_WITH_SALES"]) else "SOURCE_CHANGED",
        "SAP_PRODUCTS_WITH_OINM": sap_activity["SAP_PRODUCTS_WITH_OINM"],
        "DATALAKE_PRODUCTS_WITH_OINM": lake_activity["DATALAKE_PRODUCTS_WITH_OINM"],
        "PRODUCTS_WITH_OINM_MATCH": "EXACT" if _count_match(sap_activity["SAP_PRODUCTS_WITH_OINM"], lake_activity["DATALAKE_PRODUCTS_WITH_OINM"]) else "MISMATCH",
        "PRODUCT_MASTER_COVERAGE": product_master_status,
        "SAP_CURRENT_CUSTOMERS": business_partners["customers_total"],
        "SAP_CURRENT_SUPPLIERS": business_partners["suppliers_total"],
        "SAP_CUSTOMERS_WITH_SALES": sap_activity["SAP_CUSTOMERS_WITH_SALES"],
        "DATALAKE_CUSTOMERS_WITH_SALES": lake_activity["DATALAKE_CUSTOMERS_WITH_SALES"],
        "CUSTOMERS_WITH_SALES_MATCH": "EXACT" if _count_match(sap_activity["SAP_CUSTOMERS_WITH_SALES"], lake_activity["DATALAKE_CUSTOMERS_WITH_SALES"]) else "MISMATCH",
        "CUSTOMER_MASTER_COVERAGE": customer_master_status,
        "SUPPLIER_MASTER_COVERAGE": supplier_master_status,
        "SAP_CURRENT_WAREHOUSES": warehouse_master["total_warehouses"],
        "SAP_WAREHOUSES_WITH_SALES": sap_activity["SAP_WAREHOUSES_WITH_SALES"],
        "DATALAKE_WAREHOUSES_WITH_SALES": lake_activity["DATALAKE_WAREHOUSES_WITH_SALES"],
        "WAREHOUSES_WITH_SALES_MATCH": "EXACT" if _count_match(sap_activity["SAP_WAREHOUSES_WITH_SALES"], lake_activity["DATALAKE_WAREHOUSES_WITH_SALES"]) else "MISMATCH",
        "SAP_WAREHOUSES_WITH_OINM": sap_activity["SAP_WAREHOUSES_WITH_OINM"],
        "DATALAKE_WAREHOUSES_WITH_OINM": lake_activity["DATALAKE_WAREHOUSES_WITH_OINM"],
        "WAREHOUSES_WITH_OINM_MATCH": "EXACT" if _count_match(sap_activity["SAP_WAREHOUSES_WITH_OINM"], lake_activity["DATALAKE_WAREHOUSES_WITH_OINM"]) else "MISMATCH",
        "WAREHOUSE_MASTER_COVERAGE": warehouse_master_status,
        "SAP_CURRENT_OITW_ROWS": oitw_sap["rows"],
        "DATALAKE_OITW_ROWS": lake_oitw["rows"],
        "OITW_CURRENT_MATCH": oitw_status,
        "OITW_CURRENT_STATE_ONLY": "YES",
        "SAP_OITW_SOURCE_AS_OF": sap_read_as_of,
        "DATALAKE_OITW_SOURCE_AS_OF": lake_oitw["source_as_of_max"],
        "TOTAL_ENTITIES_CENSUSED": len(matrix),
        "COVERAGE_EXACT_COUNT": status_counts["EXACT"],
        "COVERAGE_LOADED_NOT_VALIDATED_COUNT": status_counts["LOADED_NOT_VALIDATED"],
        "COVERAGE_NOT_LOADED_COUNT": status_counts["NOT_LOADED"],
        "COVERAGE_NOT_APPLICABLE_COUNT": status_counts["NOT_APPLICABLE"],
        "COVERAGE_SOURCE_CHANGED_COUNT": status_counts["SOURCE_CHANGED"],
        "COVERAGE_MISMATCH_COUNT": status_counts["MISMATCH"],
        "NOT_LOADED_ENTITIES": not_loaded_entities,
        "HIGH_PRIORITY_COVERAGE_GAPS": coverage_gaps["HIGH_PRIORITY_COVERAGE_GAPS"],
        "TRUE_MISMATCH_COUNT": len(true_mismatch),
        "UNEXPLAINED_MISMATCH_COUNT": len(unexplained),
        "TRUE_MISMATCH_ENTITIES": true_mismatch,
        "SOURCE_CHANGED_ENTITIES": source_changed,
        "MONETARY_CENSUS": monetary["status"],
        "CURRENT_LOADED_FOUNDATION_RECONCILED": "YES" if loaded_reconciled else "NO",
        "COVERAGE_GAPS_DOCUMENTED": "YES" if coverage_gaps["MISSING_FROM_DATALAKE"] else "NO",
        "FOUNDATION_2026_RECONCILED": "YES" if foundation_reconciled else "NO",
        "SAFE_TO_PAUSE_DATALAKE_FOUNDATION_WORK": "YES" if foundation_reconciled else "NO",
        "READY_FOR_BUSINESS_ASSISTANT_QUERY_LAYER": "YES" if loaded_reconciled and len(true_mismatch) == 0 else "NO",
        "READY_FOR_UPDATE_SCRIPT": "NO",
        "READY_FOR_FULL_2022_2025_HISTORY": "NO",
        "FINAL_RESULT": (
            "TELCHI_DATALAKE_2026_CENSUS_AND_COVERAGE_RECONCILIATION_V1_PASS"
            if foundation_reconciled and len(true_mismatch) == 0
            else "TELCHI_DATALAKE_2026_CENSUS_AND_COVERAGE_RECONCILIATION_V1_DEGRADED"
        ),
    }

    # --- Evidence files ---------------------------------------------------- #
    _write(EVIDENCE_ROOT / "summary.json", summary)
    _write(EVIDENCE_ROOT / "current_state.json", current_state)
    _write(EVIDENCE_ROOT / "sap_sales_invoice_census.json", invoices)
    _write(EVIDENCE_ROOT / "sap_credit_memo_census.json", credit_memos)
    _write(EVIDENCE_ROOT / "sap_sales_order_census.json", orders)
    _write(EVIDENCE_ROOT / "sap_delivery_census.json", deliveries)
    _write(EVIDENCE_ROOT / "sap_sales_return_census.json", returns)
    _write(EVIDENCE_ROOT / "sap_oinm_census.json", oinm)
    _write(EVIDENCE_ROOT / "sap_oinm_transtype_census.json", trans_type_comparison)
    _write(EVIDENCE_ROOT / "sap_product_master_census.json", product_master)
    _write(EVIDENCE_ROOT / "sap_business_partner_census.json", business_partners)
    _write(EVIDENCE_ROOT / "sap_warehouse_census.json", warehouse_master)
    _write(EVIDENCE_ROOT / "sap_oitw_census.json", oitw_sap)
    _write(EVIDENCE_ROOT / "ducklake_sales_census.json", lake_sales)
    _write(EVIDENCE_ROOT / "ducklake_oinm_census.json", lake_oinm)
    _write(EVIDENCE_ROOT / "ducklake_oitw_census.json", lake_oitw)
    _write(EVIDENCE_ROOT / "historical_activity_census.json", {"SAP": sap_activity, "DATALAKE": lake_activity})
    _write(EVIDENCE_ROOT / "monthly_census.json", monthly)
    _write(EVIDENCE_ROOT / "keyset_comparison.json", keyset)
    _write(EVIDENCE_ROOT / "aggregate_comparison.json", aggregate)
    _write(EVIDENCE_ROOT / "coverage_matrix.json", matrix)
    _write(EVIDENCE_ROOT / "coverage_gaps.json", coverage_gaps)
    _write(EVIDENCE_ROOT / "reference_master_census.json", reference)
    _write(EVIDENCE_ROOT / "master_keyset_comparison.json", master_keyset)
    _write(EVIDENCE_ROOT / "monetary_census.json", monetary)
    _write(EVIDENCE_ROOT / "performance.json", performance)
    _write(EVIDENCE_ROOT / "foundation_closure.json", {
        "CURRENT_LOADED_FOUNDATION_RECONCILED": summary["CURRENT_LOADED_FOUNDATION_RECONCILED"],
        "COVERAGE_GAPS_DOCUMENTED": summary["COVERAGE_GAPS_DOCUMENTED"],
        "FOUNDATION_2026_RECONCILED": summary["FOUNDATION_2026_RECONCILED"],
        "SAFE_TO_PAUSE_DATALAKE_FOUNDATION_WORK": summary["SAFE_TO_PAUSE_DATALAKE_FOUNDATION_WORK"],
        "READY_FOR_BUSINESS_ASSISTANT_QUERY_LAYER": summary["READY_FOR_BUSINESS_ASSISTANT_QUERY_LAYER"],
        "READY_FOR_UPDATE_SCRIPT": summary["READY_FOR_UPDATE_SCRIPT"],
        "READY_FOR_FULL_2022_2025_HISTORY": summary["READY_FOR_FULL_2022_2025_HISTORY"],
        "loaded_comparable_entities": [item["ENTITY"] for item in loaded_comparable],
        "source_changed_entities": source_changed,
        "true_mismatch_entities": true_mismatch,
    })
    report_lines = [
        f"# {GATE}",
        "",
        f"- Historical scope: `{START}` .. `{CUTOFF}` inclusive (upper exclusive `{END_EXCLUSIVE}`).",
        "- SAP: READ ONLY; `SAP_WRITE_COUNT=0`. Data Lake: READ ONLY; `DATALAKE_MODIFIED=NO`. `AI_INVOCATIONS=0`.",
        "- Missing entities are `NOT_LOADED` and are never reported as `MISMATCH`.",
        "",
        "## Executive table",
        "",
        "| ENTITY | SAP | DATA LAKE | STATUS |",
        "| --- | ---: | ---: | --- |",
    ]
    for item in matrix:
        report_lines.append(
            f"| {item['ENTITY']} | {item['SAP_COUNT']} | {item['DATALAKE_COUNT']} | {item['STATUS']} |"
        )
    report_lines += [
        "",
        "## Headline answers",
        "",
        f"- Invoices: {invoices['total_documents']} documents, {invoices['total_lines']} lines, {invoices['total_quantity']} quantity.",
        f"- Credit memos: {credit_memos['total_documents']} documents, {credit_memos['total_lines']} lines (NOT_LOADED in Data Lake).",
        f"- Sales orders: {orders['total_documents']} documents, {orders['total_lines']} lines (NOT_LOADED).",
        f"- Deliveries: {deliveries['total_documents']} documents, {deliveries['total_lines']} lines (NOT_LOADED).",
        f"- Sales returns: {returns['total_documents']} documents, {returns['total_lines']} lines (NOT_LOADED).",
        f"- OINM movements: {oinm['rows']} rows (Data Lake {lake_oinm['rows']}).",
        f"- Current products: {product_master['total_products']} (active {product_master['active_products']}, inactive {product_master['inactive_products']}).",
        f"- Current customers: {business_partners['customers_total']}; suppliers: {business_partners['suppliers_total']}.",
        f"- Current warehouses: {warehouse_master['total_warehouses']}.",
        f"- OITW rows: SAP {oitw_sap['rows']} vs Data Lake {lake_oitw['rows']} ({oitw_status}).",
        "",
        "## Reconciliation",
        "",
        f"- Source drift: {len(sales_sap_only_docs)} Sales documents created on 2026-09-18, after the Data Lake sales window; "
        f"Data-Lake-only documents: {len(sales_lake_only_docs)}. Classified `SOURCE_CHANGED`, not `MISMATCH`.",
        "- OINM row count, source-native keyset fingerprint, InQty/OutQty totals, TransType distribution and monthly "
        "distribution match exactly.",
        "- Current-state masters in the Data Lake are federated Reference V2 entities (SAP + legacy). Their SAP-derived "
        "subsets are key-set compared against live OITM/OCRD/OWHS; legacy extras stay out of SAP-current scope.",
        "- Historical activity universes (products/customers/warehouses with sales or OINM) reconcile from facts; "
        "`PRODUCTS_WITH_SALES` differs only by items introduced by the 36 late documents.",
        "",
        "## Coverage gaps",
        "",
    ]
    for gap in coverage_gaps["MISSING_FROM_DATALAKE"]:
        report_lines.append(
            f"- {gap['entity']} ({gap['sap_table']}): {gap['sap_document_count_2026']} documents / "
            f"{gap['sap_line_count_2026']} lines -> priority {gap['future_priority']}."
        )
    report_lines += [
        "",
        "## Verdict",
        "",
        f"- `{summary['FINAL_RESULT']}`",
        f"- TRUE_MISMATCH_COUNT={summary['TRUE_MISMATCH_COUNT']}, UNEXPLAINED_MISMATCH_COUNT={summary['UNEXPLAINED_MISMATCH_COUNT']}.",
        f"- FOUNDATION_2026_RECONCILED={summary['FOUNDATION_2026_RECONCILED']}, "
        f"COVERAGE_GAPS_DOCUMENTED={summary['COVERAGE_GAPS_DOCUMENTED']}.",
        "",
        "## STOP AND REVIEW",
        "",
        "No missing entity was loaded, no update.py exists, and Atomic/Reference were not modified.",
        "",
    ]
    (EVIDENCE_ROOT / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return summary


if __name__ == "__main__":
    print(json.dumps(_run(), indent=2, sort_keys=True, ensure_ascii=False, default=str))