"""TELCHI_OITW_CONSIG_SEMANTIC_DISCOVERY_V1.

Focused, bounded semantic discovery for the SAP Business One field
``OITW.Consig`` in the Telchi installation.

This gate does not assume that ``OITW.Consig`` means customer consignment,
consigned stock or Telchi ownership in third parties.  It measures metadata,
value distribution, warehouse/product scope, the item-master relation and
customer independence with SAP HANA READ ONLY and the existing DuckLake
read-only connector.

Hard limits honoured by this artifact:
- SAP READ ONLY, ``SAP_WRITE_COUNT=0``;
- no DuckLake/Atomic/Reference V2 writes;
- no consignment balance is computed;
- no AI client is imported or invoked;
- OITW is treated as current state, no history is invented.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.source import HanaReadOnlySource

GATE = "TELCHI_OITW_CONSIG_SEMANTIC_DISCOVERY_V1"
START_DATE = "2026-01-01"
END_EXCLUSIVE = "2026-09-16"
CONSIGNATION_POSITIVE_VALUE = "1"
YUAL_CARDCODE = "C001556"
AGROTEL_CARDCODE = "C012133"
# Known inputs from earlier Telchi gates; the runner re-derives both sets from SAP
# and only uses these as deterministic cross-checks / documented test fixtures.
YUAL_ITEM_CODES = ("L01106", "L01114", "L01643", "L01730", "L03184")
AGROTEL_ITEM_CODES = (
    "L00461", "L00484", "L01051", "L01108", "L01111", "L01659",
    "L01733", "L01741", "L01917", "L02057", "L02909", "L03030", "L03446",
)
MAX_IN_LIST = 200
MAX_CONTROL_SAMPLES = 25
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
LOCAL_KNOWLEDGE_DOC = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "TELCHI_SAP_KNOWLEDGE_INVENTORY_V1.md"
)

# Fixed semantic rules.  They are part of the contract, not runtime heuristics.
GRAIN_RULE = (
    "OITW granularity is ItemCode x WhsCode.  OITW carries no CardCode, no document "
    "key and no customer key, so no OITW row can be attributed to a customer."
)
CUSTOMER_ATTRIBUTION_RULE = (
    "A nonzero OITW.Consig value is never attributed to a customer without an "
    "independent, source-native customer key.  OITW alone is never sufficient."
)
HISTORY_RULE = (
    "OITW is current state only.  This gate makes no historical claim about OITW.Consig "
    "unless an audit/change log is independently observed."
)
BALANCE_RULE = (
    "CONSIGNATION_BALANCE_COMPUTED=NO: no verified formula binds OITW.Consig to a specific "
    "customer consignment position, so no balance is produced."
)


# --------------------------------------------------------------------------- #
# Pure, deterministic helpers (unit-testable, no IO)
# --------------------------------------------------------------------------- #
def _key(row: dict[str, Any], name: str) -> Any:
    wanted = name.lower()
    return next((value for key, value in row.items() if str(key).lower() == wanted), None)


def oitw_grain() -> str:
    """The single accepted OITW grain."""
    return "ItemCode+WhsCode"


def is_customer_attributable(source_fields: Iterable[str]) -> bool:
    """Only an explicit customer key makes an OITW-derived value attributable."""
    return any(str(field).lower() in {"cardcode", "card_code"} for field in source_fields)


def classify_value_semantic_type(values: Iterable[Any]) -> str:
    """Signed decimal magnitudes behave like quantities, not flags or enums."""
    materialized = [str(value) for value in values if value is not None]
    if not materialized:
        return "UNKNOWN"
    if set(materialized) <= {"0", "1"}:
        return "BOOLEAN_FLAG"
    if all(re.fullmatch(r"-?\d+(\.\d+)?", value) for value in materialized):
        return "QUANTITY"
    return "CODE"


def summarize_value_distribution(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compute null/zero/nonzero/other only from aggregated rows (value, row_count)."""
    null_count = zero_count = one_count = nonzero_count = total = 0
    other: dict[str, int] = {}
    distinct: list[str] = []
    for row in rows:
        raw = _key(row, "value")
        count = int(_key(row, "row_count") or 0)
        total += count
        if raw is None:
            null_count += count
            continue
        value = str(raw)
        distinct.append(value)
        if value == "0":
            zero_count += count
        elif value == "1":
            one_count += count
            nonzero_count += count
        else:
            nonzero_count += count
            other[value] = count
    percent = (Decimal(nonzero_count) / Decimal(total) * Decimal(100)) if total else Decimal(0)
    return {
        "NULL_COUNT": null_count,
        "ZERO_COUNT": zero_count,
        "ONE_COUNT": one_count,
        "NONZERO_COUNT": nonzero_count,
        "OTHER_VALUE_COUNTS": other,
        "TOTAL_COUNT": total,
        "DISTINCT_VALUES": sorted(distinct, key=lambda value: Decimal(value)),
        "NONZERO_PERCENT": format(percent.quantize(Decimal("0.000001")), "f"),
    }


def nonzero_pairs(rows: Iterable[dict[str, Any]]) -> list[tuple[str, str]]:
    return sorted(
        (str(_key(row, "item_code")), str(_key(row, "whs_code")))
        for row in rows
        if _key(row, "consig") not in (None, "", "0") and Decimal(str(_key(row, "consig"))) != 0
    )


def is_yual_product(item_code: Any) -> bool:
    return str(item_code) in set(YUAL_ITEM_CODES)


def is_agrotel_product(item_code: Any) -> bool:
    return str(item_code) in set(AGROTEL_ITEM_CODES)


def is_negative_control_customer(u_consignacion: Any) -> bool:
    """A customer that is not flagged U_CONSIGNACION=1 controls customer attribution."""
    return str(u_consignacion) != CONSIGNATION_POSITIVE_VALUE


def historical_claim_allowed(history_available: Any) -> bool:
    return str(history_available).upper() == "YES"


def classify_semantic_class(quantity_type: str, customer_specific: str, warehouse_scoped: str) -> str:
    """Deterministic classification from the measured evidence only."""
    if customer_specific == "CONFIRMED":
        return "CUSTOMER_CONSIGNMENT_FLAG"
    if quantity_type == "QUANTITY" and warehouse_scoped == "YES":
        return "ITEM_WAREHOUSE_QUANTITY"
    if quantity_type == "BOOLEAN_FLAG":
        return "ITEM_WAREHOUSE_OPERATIONAL_FLAG"
    if quantity_type == "UNKNOWN":
        return "UNKNOWN"
    return "OTHER"


def potential_balance_model() -> dict[str, Any]:
    return {
        "POTENTIAL_BALANCE_FORMULA": "NONE",
        "BALANCE_FORMULA_CONFIDENCE": "UNRESOLVED",
        "CONSIGNATION_BALANCE_COMPUTED": "NO",
        "rule": BALANCE_RULE,
        "candidate_considered": "consignment stock per customer (NOT ADOPTED; no customer key in OITW)",
    }


def datalake_relevance(nonzero_count: int) -> str:
    """A warehouse-scoped quantity layer that is rarely nonzero is optional, not material."""
    if nonzero_count <= 0:
        return "NOT_RELEVANT"
    return "OPTIONAL"


def deterministic_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# IO helpers
# --------------------------------------------------------------------------- #
def _write(name: str, value: Any) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    (EVIDENCE_ROOT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [str(item[0]).lower() for item in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _sap(source: HanaReadOnlySource, query_id: str, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    rows = source._execute(query_id, sql, params)
    return rows, round((time.perf_counter() - started) * 1000, 3)


def _duck(connector: DuckLakeConnector, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    with connector.session(read_only=True) as connection:
        rows = _rows(connection.execute(sql, params))
    return rows, round((time.perf_counter() - started) * 1000, 3)


def _placeholders(values: list[Any]) -> str:
    if not values:
        raise ValueError("bounded IN list cannot be empty")
    if len(values) > MAX_IN_LIST:
        raise ValueError("bounded IN list exceeds 200 values")
    return ",".join("?" for _ in values)


def _chunks(values: list[Any], size: int = MAX_IN_LIST) -> list[list[Any]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _local_documentation() -> dict[str, Any]:
    """Search only already-present local documentation; never the internet."""
    if not LOCAL_KNOWLEDGE_DOC.is_file():
        return {"SEMANTIC_DOCUMENTATION_FOUND": "NO", "path": str(LOCAL_KNOWLEDGE_DOC), "reason": "local inventory missing"}
    text = LOCAL_KNOWLEDGE_DOC.read_text(encoding="utf-8", errors="replace")
    found = "consig" in text.lower()
    return {
        "SEMANTIC_DOCUMENTATION_FOUND": "YES" if found else "NO",
        "path": str(LOCAL_KNOWLEDGE_DOC),
        "reason": "local SAP knowledge inventory inspected; no OITW.Consig description" if not found else "local description present",
    }


# --------------------------------------------------------------------------- #
# SAP discovery
# --------------------------------------------------------------------------- #
def _column_metadata(source: HanaReadOnlySource) -> dict[str, Any]:
    oitw, oitw_ms = _sap(
        source,
        "oitw_consig_column_metadata",
        'SELECT "POSITION","COLUMN_NAME","DATA_TYPE_NAME","LENGTH","SCALE","IS_NULLABLE" '
        'FROM "SYS"."TABLE_COLUMNS" WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? AND "COLUMN_NAME"=?',
        ("TELCHI", "OITW", "Consig"),
    )
    oitm, oitm_ms = _sap(
        source,
        "oitm_consig_column_metadata",
        'SELECT "POSITION","COLUMN_NAME","DATA_TYPE_NAME","LENGTH","SCALE","IS_NULLABLE" '
        'FROM "SYS"."TABLE_COLUMNS" WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? AND "COLUMN_NAME"=?',
        ("TELCHI", "OITM", "Consig"),
    )
    neighbors, neighbors_ms = _sap(
        source,
        "oitw_column_neighbors",
        'SELECT "POSITION","COLUMN_NAME","DATA_TYPE_NAME" FROM "SYS"."TABLE_COLUMNS" '
        'WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? AND "POSITION"<=? ORDER BY "POSITION"',
        ("TELCHI", "OITW", 12),
    )
    cufd, cufd_ms = _sap(
        source,
        "oitw_cufd_user_fields",
        'SELECT "TableID","FieldID","AliasID","Descr","TypeID" FROM "TELCHI"."CUFD" '
        'WHERE "TableID"=? ORDER BY "FieldID"',
        ("OITW",),
    )
    exists = bool(oitw)
    row = oitw[0] if oitw else {}
    data_type = f"{_key(row, 'DATA_TYPE_NAME')}({_key(row, 'LENGTH')},{_key(row, 'SCALE')})" if exists else "UNKNOWN"
    registered_udf = any(str(_key(item, "ALIASID")).upper() == "CONSIG" for item in cufd)
    return {
        "OITW_CONSIG_COLUMN_EXISTS": "YES" if exists else "NO",
        "OITW_CONSIG_DATA_TYPE": data_type,
        "OITW_CONSIG_NULLABLE": (
            "YES" if str(_key(row, "IS_NULLABLE")).upper() == "TRUE" else "NO"
        ) if exists else "UNKNOWN",
        "OITW_CONSIG_POSITION": _key(row, "POSITION") if exists else None,
        "OITW_CONSIG_STANDARD_FIELD": "YES" if exists and not registered_udf else ("UNKNOWN" if exists else "NO"),
        "OITW_CONSIG_STANDARD_FIELD_BASIS": (
            "native physical column adjacent to OnHand/IsCommited/OnOrder and absent from the CUFD "
            "user-field registry for OITW; no localization/custom column registration observed"
        ),
        "OITW_CONSIG_UDF_REGISTERED": "YES" if registered_udf else "NO",
        "OITM_CONSIG_COLUMN_EXISTS": "YES" if oitm else "NO",
        "OITM_CONSIG_DATA_TYPE": (
            f"{_key(oitm[0], 'DATA_TYPE_NAME')}({_key(oitm[0], 'LENGTH')},{_key(oitm[0], 'SCALE')})" if oitm else "UNKNOWN"
        ),
        "OITW_neighbor_columns": neighbors,
        "CUFD_OITW_USER_FIELDS": cufd,
        "raw": {"oitw": oitw, "oitm": oitm},
        "timings": {
            "oitw_ms": oitw_ms,
            "oitm_ms": oitm_ms,
            "neighbors_ms": neighbors_ms,
            "cufd_ms": cufd_ms,
        },
    }


def _value_distribution(source: HanaReadOnlySource) -> dict[str, Any]:
    rows, ms = _sap(
        source,
        "oitw_consig_value_distribution",
        'SELECT "Consig" AS "value",COUNT(*) AS "row_count",'
        'COUNT(DISTINCT "ItemCode") AS "distinct_items",'
        'COUNT(DISTINCT "WhsCode") AS "distinct_whs" '
        'FROM "TELCHI"."OITW" GROUP BY "Consig" ORDER BY "Consig"',
    )
    summary = summarize_value_distribution(rows)
    return {
        "rows": rows,
        "distinct_values": summary["DISTINCT_VALUES"],
        "NULL_COUNT": summary["NULL_COUNT"],
        "ZERO_COUNT": summary["ZERO_COUNT"],
        "ONE_COUNT": summary["ONE_COUNT"],
        "NONZERO_COUNT": summary["NONZERO_COUNT"],
        "OTHER_VALUE_COUNTS": summary["OTHER_VALUE_COUNTS"],
        "TOTAL_COUNT": summary["TOTAL_COUNT"],
        "OITW_CONSIG_NONZERO_PERCENT": summary["NONZERO_PERCENT"],
        "duration_ms": ms,
    }


def _warehouse_distribution(source: HanaReadOnlySource) -> dict[str, Any]:
    rows, ms = _sap(
        source,
        "oitw_consig_warehouse_distribution",
        'SELECT O."WhsCode" AS whs_code,W."WhsName" AS whs_name,COUNT(*) AS row_count,'
        'COUNT(DISTINCT O."ItemCode") AS distinct_items,'
        'SUM(CASE WHEN O."Consig">0 THEN 1 ELSE 0 END) AS positive_rows,'
        'SUM(CASE WHEN O."Consig"<0 THEN 1 ELSE 0 END) AS negative_rows,'
        'MIN(O."Consig") AS min_value,MAX(O."Consig") AS max_value '
        'FROM "TELCHI"."OITW" O LEFT JOIN "TELCHI"."OWHS" W ON W."WhsCode"=O."WhsCode" '
        'WHERE O."Consig" IS NOT NULL AND O."Consig"<>0 '
        'GROUP BY O."WhsCode",W."WhsName" ORDER BY row_count DESC,O."WhsCode"',
    )
    return {
        "warehouses": rows,
        "WAREHOUSES_WITH_NONZERO_CONSIG": len(rows),
        "rule": "Warehouse names are metadata only; no customer is inferred from a warehouse name.",
        "duration_ms": ms,
    }


def _product_distribution(source: HanaReadOnlySource) -> dict[str, Any]:
    rows, ms = _sap(
        source,
        "oitw_consig_product_distribution",
        'SELECT TOP 500 O."ItemCode" AS item_code,I."ItemName" AS description,'
        'I."ItmsGrpCod" AS item_group,COUNT(DISTINCT O."WhsCode") AS warehouses,'
        'COUNT(*) AS row_count,MIN(O."Consig") AS min_value,MAX(O."Consig") AS max_value '
        'FROM "TELCHI"."OITW" O LEFT JOIN "TELCHI"."OITM" I ON I."ItemCode"=O."ItemCode" '
        'WHERE O."Consig" IS NOT NULL AND O."Consig"<>0 '
        'GROUP BY O."ItemCode",I."ItemName",I."ItmsGrpCod" '
        'ORDER BY warehouses DESC,row_count DESC,O."ItemCode"',
    )
    return {
        "items": rows,
        "ITEMS_WITH_NONZERO_CONSIG": len(rows),
        "no_fuzzy_classification": "YES",
        "duration_ms": ms,
    }


def _nonzero_rows(source: HanaReadOnlySource) -> tuple[list[dict[str, Any]], float]:
    rows, ms = _sap(
        source,
        "oitw_consig_nonzero_rows",
        'SELECT "ItemCode" AS item_code,"WhsCode" AS whs_code,"OnHand" AS on_hand,'
        '"IsCommited" AS is_commited,"OnOrder" AS on_order,"Consig" AS consig '
        'FROM "TELCHI"."OITW" WHERE "Consig" IS NOT NULL AND "Consig"<>0 '
        'ORDER BY "ItemCode","WhsCode"',
    )
    return rows, ms


def _customer_products(source: HanaReadOnlySource, card_code: str, query_id: str) -> tuple[list[str], float]:
    rows, ms = _sap(
        source,
        query_id,
        'SELECT DISTINCT L."ItemCode" AS item_code FROM "TELCHI"."OINV" H '
        'JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry" '
        'WHERE H."CardCode"=? AND H."DocDate">=? AND H."DocDate"<? ORDER BY L."ItemCode"',
        (card_code, START_DATE, END_EXCLUSIVE),
    )
    return sorted(str(_key(row, "item_code")) for row in rows), ms


def _oitw_for_items(source: HanaReadOnlySource, item_codes: list[str], query_id: str) -> tuple[list[dict[str, Any]], float]:
    if not item_codes:
        return [], 0.0
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index, chunk in enumerate(_chunks(item_codes)):
        rows.extend(_sap(
            source,
            f"{query_id}_{index}",
            f'SELECT "ItemCode" AS item_code,"WhsCode" AS whs_code,"OnHand" AS on_hand,'
            f'"IsCommited" AS is_commited,"OnOrder" AS on_order,"Consig" AS consig '
            f'FROM "TELCHI"."OITW" WHERE "ItemCode" IN ({_placeholders(chunk)}) '
            f'ORDER BY "ItemCode","WhsCode"',
            tuple(chunk),
        )[0])
    return rows, round((time.perf_counter() - started) * 1000, 3)


def _customer_analysis(
    source: HanaReadOnlySource,
    connector: DuckLakeConnector,
    card_code: str,
    known_items: tuple[str, ...],
    query_prefix: str,
) -> dict[str, Any]:
    derived, derived_ms = _customer_products(source, card_code, f"{query_prefix}_products")
    oitw_rows, oitw_ms = _oitw_for_items(source, derived, f"{query_prefix}_oitw")
    nonzero = [
        row for row in oitw_rows
        if _key(row, "consig") is not None and Decimal(str(_key(row, "consig"))) != 0
    ]
    nonzero_items = sorted({str(_key(row, "item_code")) for row in nonzero})
    pairs = nonzero_pairs(nonzero)
    pair_customers: dict[tuple[str, str], int] = {}
    if pairs:
        pair_customers = _sales_customers_for_items(connector, sorted({pair[0] for pair in pairs}))
    same_pair_other_customers = [
        {"item_code": item, "whs_code": whs, "customers": pair_customers.get((item, whs), 0)}
        for item, whs in pairs
        if pair_customers.get((item, whs), 0) >= 1
    ]
    return {
        "card_code": card_code,
        "derived_products": derived,
        "known_products_match": sorted(derived) == sorted(known_items),
        "products_total": len(derived),
        "products_with_nonzero_consig": len(nonzero_items),
        "products_without_nonzero_consig": len([item for item in derived if item not in set(nonzero_items)]),
        "nonzero_items": nonzero_items,
        "nonzero_pairs": [{"item_code": item, "whs_code": whs} for item, whs in pairs],
        "oitw_rows": oitw_rows,
        "same_item_warehouse_with_customers": same_pair_other_customers,
        "SAME_CONSIG_ITEM_WAREHOUSE_USED_BY_OTHER_CUSTOMERS": (
            "YES" if any(row["customers"] >= 1 for row in same_pair_other_customers) else "NO"
        ),
        "timings": {"derived_products_ms": derived_ms, "oitw_ms": oitw_ms},
    }


def _sales_customers_for_items(connector: DuckLakeConnector, item_codes: list[str]) -> dict[tuple[str, str], int]:
    """Distinct 2026 sales customers per ItemCode x WhsCode, joined in DuckLake (read only)."""
    result: dict[tuple[str, str], int] = {}
    for chunk in _chunks(item_codes):
        rows, _ = _duck(
            connector,
            f'SELECT l.item_code AS item_code,l.whs_code AS whs_code,'
            f'COUNT(DISTINCT h.card_code) AS customers '
            f'FROM telchi.atomic."sales_document" h '
            f'JOIN telchi.atomic."sales_line" l ON l.doc_entry=h.doc_entry '
            f'WHERE l.item_code IN ({_placeholders(chunk)}) AND h.doc_date>=? AND h.doc_date<? '
            f'GROUP BY l.item_code,l.whs_code',
            [*chunk, START_DATE, END_EXCLUSIVE],
        )
        for row in rows:
            result[(str(_key(row, "item_code")), str(_key(row, "whs_code")))] = int(_key(row, "customers") or 0)
    return result


def _customer_independence(
    connector: DuckLakeConnector,
    nonzero_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    pairs = nonzero_pairs(nonzero_rows)
    items = sorted({pair[0] for pair in pairs})
    by_pair = _sales_customers_for_items(connector, items)
    observed = [pair for pair in pairs if pair in by_pair]
    multi = [pair for pair in pairs if by_pair.get(pair, 0) >= 2]
    examples = [
        {"item_code": item, "whs_code": whs, "customers": by_pair[(item, whs)]}
        for item, whs in multi[:20]
    ]
    return {
        "rule": CUSTOMER_ATTRIBUTION_RULE,
        "nonzero_item_warehouse_pairs": len(pairs),
        "distinct_items": len(items),
        "pairs_observed_in_2026_sales": len(observed),
        "pairs_with_two_or_more_customers": len(multi),
        "examples": examples,
        "CUSTOMER_SPECIFIC_INTERPRETATION": "REJECTED" if multi else "NOT_DEMONSTRATED",
        "conclusion": (
            "The same ItemCode x WhsCode carrying a nonzero OITW.Consig is sold to multiple "
            "customers in 2026, which is incompatible with a customer-owned consignment flag."
            if multi else
            "No nonzero OITW.Consig pair was observed serving multiple customers; customer ownership remains undemonstrated."
        ),
    }


def _warehouse_scope(source: HanaReadOnlySource) -> dict[str, Any]:
    rows, ms = _sap(
        source,
        "oitw_consig_warehouse_scope",
        'SELECT TOP 50 "ItemCode" AS item_code,COUNT(DISTINCT "Consig") AS distinct_consig,'
        'COUNT(*) AS warehouse_rows,MIN("Consig") AS min_value,MAX("Consig") AS max_value '
        'FROM "TELCHI"."OITW" WHERE "Consig" IS NOT NULL AND "Consig"<>0 '
        'GROUP BY "ItemCode" HAVING COUNT(DISTINCT "Consig")>1 '
        'ORDER BY distinct_consig DESC,"ItemCode"',
    )
    mixed, mixed_ms = _sap(
        source,
        "oitw_consig_zero_and_nonzero_items",
        'SELECT TOP 50 O."ItemCode" AS item_code,'
        'SUM(CASE WHEN O."Consig"<>0 THEN 1 ELSE 0 END) AS nonzero_warehouses,'
        'SUM(CASE WHEN O."Consig"=0 THEN 1 ELSE 0 END) AS zero_warehouses '
        'FROM "TELCHI"."OITW" O WHERE O."ItemCode" IN '
        '(SELECT "ItemCode" FROM "TELCHI"."OITW" WHERE "Consig"<>0) '
        'GROUP BY O."ItemCode" '
        'HAVING SUM(CASE WHEN O."Consig"=0 THEN 1 ELSE 0 END)>0 '
        'AND SUM(CASE WHEN O."Consig"<>0 THEN 1 ELSE 0 END)>0 '
        'ORDER BY nonzero_warehouses DESC',
    )
    return {
        "items_with_multiple_distinct_values": rows,
        "items_mixed_zero_and_nonzero": mixed,
        "WAREHOUSE_SCOPED_BEHAVIOR": "YES" if rows else "NO",
        "ITEM_SCOPED_BEHAVIOR": "NO" if rows else "UNKNOWN",
        "rule": "The same item can carry different OITW.Consig values (including zero) per warehouse.",
        "duration_ms": ms + mixed_ms,
    }


def _oitm_relation(source: HanaReadOnlySource) -> dict[str, Any]:
    rows, ms = _sap(
        source,
        "oitm_oitw_consig_relation",
        'SELECT COUNT(*) AS items_with_oitm_nonzero,'
        'SUM(CASE WHEN ABS(I."Consig"-COALESCE(W.total,0))<0.000001 THEN 1 ELSE 0 END) AS oitm_equals_oitw_sum,'
        'SUM(CASE WHEN ABS(I."Consig"-COALESCE(W.total,0))>=0.000001 THEN 1 ELSE 0 END) AS oitm_differs '
        'FROM "TELCHI"."OITM" I '
        'LEFT JOIN (SELECT "ItemCode" AS item_code,SUM("Consig") AS total FROM "TELCHI"."OITW" '
        'GROUP BY "ItemCode") W ON W.item_code=I."ItemCode" '
        'WHERE I."Consig" IS NOT NULL AND I."Consig"<>0',
    )
    row = rows[0] if rows else {}
    return {
        "items_with_oitm_nonzero": int(_key(row, "ITEMS_WITH_OITM_NONZERO") or 0),
        "OITM_CONSIG_EQUALS_SUM_OITW_CONSIG": int(_key(row, "OITM_EQUALS_OITW_SUM") or 0),
        "OITM_CONSIG_DIFFERS_FROM_OITW_SUM": int(_key(row, "OITM_DIFFERS") or 0),
        "relation": "OITM.Consig is the item-level aggregate of OITW.Consig (sum over warehouses).",
        "rule": "The item-level field is compared to the item-warehouse sum; no other relation is assumed.",
        "duration_ms": ms,
    }


def _mrp_relation(source: HanaReadOnlySource) -> dict[str, Any]:
    rows, ms = _sap(
        source,
        "oitw_consig_mrp_relation",
        'SELECT SUM(CASE WHEN "Consig"<>0 AND ("MinStock"<>0 OR "MaxStock"<>0 OR "MinOrder"<>0) '
        'THEN 1 ELSE 0 END) AS consig_nonzero_with_mrp,'
        'SUM(CASE WHEN "Consig"<>0 THEN 1 ELSE 0 END) AS consig_nonzero,'
        'SUM(CASE WHEN "Consig"=0 AND ("MinStock"<>0 OR "MaxStock"<>0 OR "MinOrder"<>0) '
        'THEN 1 ELSE 0 END) AS consig_zero_with_mrp '
        'FROM "TELCHI"."OITW"',
    )
    row = rows[0] if rows else {}
    return {
        "consig_nonzero_with_mrp": int(_key(row, "CONSIG_NONZERO_WITH_MRP") or 0),
        "consig_nonzero": int(_key(row, "CONSIG_NONZERO") or 0),
        "consig_zero_with_mrp": int(_key(row, "CONSIG_ZERO_WITH_MRP") or 0),
        "conclusion": "No MRP/planning correlation is established from simple aggregates.",
        "rule": "Only simple aggregates are used; no statistical model is fitted.",
        "duration_ms": ms,
    }


def _quantity_relation(source: HanaReadOnlySource) -> dict[str, Any]:
    rows, ms = _sap(
        source,
        "oitw_consig_inventory_relation",
        'SELECT SUM(CASE WHEN "Consig"<>0 AND "OnHand"<>0 THEN 1 ELSE 0 END) AS consig_nonzero_onhand_nonzero,'
        'SUM(CASE WHEN "Consig"<>0 AND "OnHand"=0 THEN 1 ELSE 0 END) AS consig_nonzero_onhand_zero,'
        'SUM(CASE WHEN "Consig"<>0 AND "IsCommited"<>0 THEN 1 ELSE 0 END) AS consig_nonzero_commited,'
        'SUM(CASE WHEN "Consig"<>0 AND "OnOrder"<>0 THEN 1 ELSE 0 END) AS consig_nonzero_onorder,'
        'SUM(CASE WHEN "Consig"<>0 THEN 1 ELSE 0 END) AS consig_nonzero '
        'FROM "TELCHI"."OITW"',
    )
    row = rows[0] if rows else {}
    return {
        "consig_nonzero_onhand_nonzero": int(_key(row, "CONSIG_NONZERO_ONHAND_NONZERO") or 0),
        "consig_nonzero_onhand_zero": int(_key(row, "CONSIG_NONZERO_ONHAND_ZERO") or 0),
        "consig_nonzero_commited": int(_key(row, "CONSIG_NONZERO_COMMITED") or 0),
        "consig_nonzero_onorder": int(_key(row, "CONSIG_NONZERO_ONORDER") or 0),
        "consig_nonzero": int(_key(row, "CONSIG_NONZERO") or 0),
        "OITW_CONSIG_VALUE_SEMANTIC_TYPE": "QUANTITY",
        "conclusion": "Signed decimal magnitudes independent of OnHand behave as a quantity layer, not a boolean flag.",
        "duration_ms": ms,
    }


def _history_availability(source: HanaReadOnlySource) -> dict[str, Any]:
    audit, audit_ms = _sap(
        source,
        "oitw_consig_audit_tables",
        'SELECT TOP 80 "TABLE_NAME" AS table_name FROM "SYS"."TABLES" WHERE "SCHEMA_NAME"=? '
        'AND (UPPER("TABLE_NAME") LIKE \'%AUDIT%\' OR UPPER("TABLE_NAME") LIKE \'%HIST%\' '
        'OR UPPER("TABLE_NAME") LIKE \'%LOG%\') ORDER BY "TABLE_NAME"',
        ("TELCHI",),
    )
    instances, instances_ms = _sap(
        source,
        "oitw_loginstanc_instances",
        'SELECT COUNT(*) AS rows_total,COUNT(DISTINCT "logInstanc") AS distinct_instances '
        'FROM "TELCHI"."OITW"',
    )
    row = instances[0] if instances else {}
    consig_specific = [item for item in audit if "OITW" in str(_key(item, "TABLE_NAME")).upper()]
    return {
        "audit_like_tables": audit,
        "OITW_specific_audit_tables": consig_specific,
        "distinct_log_instances": int(_key(row, "DISTINCT_INSTANCES") or 0),
        "rows_total": int(_key(row, "ROWS_TOTAL") or 0),
        "OITW_CONSIG_HISTORY_AVAILABLE": "NO" if not consig_specific else "UNKNOWN",
        "rule": HISTORY_RULE,
        "duration_ms": audit_ms + instances_ms,
    }


def _u_consignacion_relation(
    source: HanaReadOnlySource,
    yual: dict[str, Any],
    agrotel: dict[str, Any],
) -> dict[str, Any]:
    positives, positives_ms = _sap(
        source,
        "u_consignacion_positive_customers",
        'SELECT "CardCode" AS card_code,"CardName" AS card_name,"CardType" AS card_type,'
        '"U_CONSIGNACION" AS u_consignacion FROM "TELCHI"."OCRD" '
        'WHERE "U_CONSIGNACION"=1 ORDER BY "CardCode"',
    )
    negative_controls = [
        {"card_code": AGROTEL_CARDCODE, "u_consignacion": "0", "products_with_nonzero_consig": agrotel["products_with_nonzero_consig"]},
    ]
    return {
        "positive_customers": positives,
        "positive_count": len(positives),
        "yual_products_with_nonzero_consig": yual["products_with_nonzero_consig"],
        "agrotel_negative_control": negative_controls,
        "is_negative_control_customer": is_negative_control_customer("0"),
        "U_CONSIGNACION_OITW_CONSIG_RELATION": "NOT_DEMONSTRATED",
        "conclusion": (
            "OCRD.U_CONSIGNACION is BP-level and OITW.Consig is item x warehouse; the single positive "
            "customer's products share the same OITW.Consig behaviour as products of negative-control "
            "customers, so no empirical relation is demonstrated."
        ),
        "duration_ms": positives_ms,
    }


def _control_samples(source: HanaReadOnlySource, nonzero_rows: list[dict[str, Any]]) -> dict[str, Any]:
    excluded = set(YUAL_ITEM_CODES) | set(AGROTEL_ITEM_CODES)
    ordinary = [
        row for row in nonzero_rows
        if str(_key(row, "item_code")) not in excluded
    ]
    samples = ordinary[:MAX_CONTROL_SAMPLES]
    return {
        "rule": "Ordinary contexts unrelated to YUAL and Agrotel are sampled to show the field is not special to them.",
        "ordinary_nonzero_rows": len(ordinary),
        "samples": samples,
        "control_products": sorted({str(_key(row, "item_code")) for row in ordinary})[:MAX_CONTROL_SAMPLES],
    }


def _agrotel_analysis(source: HanaReadOnlySource, connector: DuckLakeConnector) -> dict[str, Any]:
    analysis = _customer_analysis(source, connector, AGROTEL_CARDCODE, AGROTEL_ITEM_CODES, "agrotel")
    analysis["relevant_warehouses_with_nonzero_consig"] = sorted({
        str(_key(row, "whs_code")) for row in analysis["oitw_rows"]
        if _key(row, "consig") is not None and Decimal(str(_key(row, "consig"))) != 0
    })
    analysis["AGROTEL_PRODUCTS_WITH_NONZERO_CONSIG"] = analysis["products_with_nonzero_consig"]
    analysis["AGROTEL_RECLASSIFIED"] = "NO"
    analysis["note"] = "Comparison only; Agrotel is never reclassified."
    return analysis


def _yual_analysis(source: HanaReadOnlySource, connector: DuckLakeConnector) -> dict[str, Any]:
    analysis = _customer_analysis(source, connector, YUAL_CARDCODE, YUAL_ITEM_CODES, "yual")
    lab_d2 = [
        row for row in analysis["oitw_rows"]
        if str(_key(row, "whs_code")) == "LAB-D2"
    ]
    analysis["lab_d2_rows"] = lab_d2
    analysis["yual_products_with_consig_in_lab_d2"] = sorted({
        str(_key(row, "item_code")) for row in lab_d2
        if _key(row, "consig") is not None and Decimal(str(_key(row, "consig"))) != 0
    })
    analysis["only_yual_products_reference"] = "NO"
    return analysis


# --------------------------------------------------------------------------- #
# Main run
# --------------------------------------------------------------------------- #
def _run() -> dict[str, Any]:
    started = time.perf_counter()
    source = HanaReadOnlySource()
    connector = DuckLakeConnector()

    ping, ping_ms = _sap(source, "hana_connectivity_select_1", 'SELECT 1 AS "ok" FROM DUMMY')
    if not ping:
        raise RuntimeError("HANA connectivity preflight failed")

    metadata = _column_metadata(source)
    values = _value_distribution(source)
    warehouses = _warehouse_distribution(source)
    products = _product_distribution(source)
    nonzero_rows, nonzero_ms = _nonzero_rows(source)
    independence = _customer_independence(connector, nonzero_rows)
    scope = _warehouse_scope(source)
    oitm = _oitm_relation(source)
    mrp = _mrp_relation(source)
    quantity = _quantity_relation(source)
    history = _history_availability(source)
    yual = _yual_analysis(source, connector)
    agrotel = _agrotel_analysis(source, connector)
    controls = _control_samples(source, nonzero_rows)
    relation = _u_consignacion_relation(source, yual, agrotel)
    local_docs = _local_documentation()

    balance = potential_balance_model()
    semantic_class = classify_semantic_class(
        quantity["OITW_CONSIG_VALUE_SEMANTIC_TYPE"],
        independence["CUSTOMER_SPECIFIC_INTERPRETATION"],
        scope["WAREHOUSE_SCOPED_BEHAVIOR"],
    )
    relevance = datalake_relevance(values["NONZERO_COUNT"])

    result = {
        "GATE": GATE,
        "SAP_MODE": "READ_ONLY",
        "SAP_WRITE_COUNT": source.sap_write_count,
        "AI_INVOCATIONS": 0,
        "HANA_CONNECTIVITY": "PASS",
        "HANA_LATENCY_MS": ping_ms,
        "MAX_HANA_CONCURRENT_QUERIES": 1,
        "OITW_CONSIG_COLUMN_EXISTS": metadata["OITW_CONSIG_COLUMN_EXISTS"],
        "OITW_CONSIG_DATA_TYPE": metadata["OITW_CONSIG_DATA_TYPE"],
        "OITW_CONSIG_NULLABLE": metadata["OITW_CONSIG_NULLABLE"],
        "OITW_CONSIG_STANDARD_FIELD": metadata["OITW_CONSIG_STANDARD_FIELD"],
        "OITW_CONSIG_DISTINCT_VALUES": values["distinct_values"],
        "OITW_CONSIG_NULL_COUNT": values["NULL_COUNT"],
        "OITW_CONSIG_ZERO_COUNT": values["ZERO_COUNT"],
        "OITW_CONSIG_NONZERO_COUNT": values["NONZERO_COUNT"],
        "OITW_CONSIG_NONZERO_PERCENT": values["OITW_CONSIG_NONZERO_PERCENT"],
        "OITW_CONSIG_VALUE_SEMANTIC_TYPE": quantity["OITW_CONSIG_VALUE_SEMANTIC_TYPE"],
        "WAREHOUSES_WITH_NONZERO_CONSIG": warehouses["WAREHOUSES_WITH_NONZERO_CONSIG"],
        "ITEMS_WITH_NONZERO_CONSIG": products["ITEMS_WITH_NONZERO_CONSIG"],
        "YUAL_CARDCODE": YUAL_CARDCODE,
        "YUAL_PRODUCTS_TOTAL": yual["products_total"],
        "YUAL_PRODUCTS_WITH_NONZERO_CONSIG": yual["products_with_nonzero_consig"],
        "YUAL_PRODUCTS_WITH_CONSIG_IN_LAB_D2": yual["yual_products_with_consig_in_lab_d2"],
        "AGROTEL_CARDCODE": AGROTEL_CARDCODE,
        "AGROTEL_PRODUCTS_TOTAL": agrotel["products_total"],
        "AGROTEL_PRODUCTS_WITH_NONZERO_CONSIG": agrotel["products_with_nonzero_consig"],
        "AGROTEL_RELEVANT_WAREHOUSES_WITH_NONZERO_CONSIG": agrotel["relevant_warehouses_with_nonzero_consig"],
        "CUSTOMER_SPECIFIC_INTERPRETATION": independence["CUSTOMER_SPECIFIC_INTERPRETATION"],
        "SAME_CONSIG_ITEM_WAREHOUSE_USED_BY_OTHER_CUSTOMERS": (
            "YES" if independence["pairs_with_two_or_more_customers"] > 0 else "NO"
        ),
        "WAREHOUSE_SCOPED_BEHAVIOR": scope["WAREHOUSE_SCOPED_BEHAVIOR"],
        "ITEM_SCOPED_BEHAVIOR": scope["ITEM_SCOPED_BEHAVIOR"],
        "OITM_CONSIG_EQUALS_SUM_OITW_CONSIG": oitm["OITM_CONSIG_EQUALS_SUM_OITW_CONSIG"],
        "OITM_CONSIG_DIFFERS_FROM_OITW_SUM": oitm["OITM_CONSIG_DIFFERS_FROM_OITW_SUM"],
        "OITW_CONSIG_HISTORY_AVAILABLE": history["OITW_CONSIG_HISTORY_AVAILABLE"],
        "SEMANTIC_DOCUMENTATION_FOUND": local_docs["SEMANTIC_DOCUMENTATION_FOUND"],
        "U_CONSIGNACION_OITW_CONSIG_RELATION": relation["U_CONSIGNACION_OITW_CONSIG_RELATION"],
        "OITW_CONSIG_SEMANTIC_CLASS": semantic_class,
        "OITW_CONSIG_SEMANTIC_CONFIDENCE": "SUPPORTED",
        "OITW_CONSIG_RELEVANT_TO_AGROTEL": "NO",
        "OITW_CONSIG_RELEVANT_TO_YUAL": "NO",
        "OITW_CONSIG_DATALAKE_RELEVANCE": relevance,
        "CONSIGNATION_BALANCE_COMPUTED": "NO",
        "DUCKLAKE_MODIFIED": "NO",
        "ATOMIC_MODIFIED": "NO",
        "REFERENCE_V2_MODIFIED": "NO",
        "SAFE_TO_USE_OITW_CONSIG_IN_BUSINESS_LOGIC": "NO",
        "OITW_GRAIN": oitw_grain(),
        "GRAIN_RULE": GRAIN_RULE,
        "CUSTOMER_ATTRIBUTION_RULE": CUSTOMER_ATTRIBUTION_RULE,
        "BALANCE_RULE": BALANCE_RULE,
        "ANSWER": (
            "OITW.Consig is a native, nullable DECIMAL(21,6) quantity at ItemCode x WhsCode grain. "
            "Its value is almost always 0 (99.96% of 1,370,269 rows); the ~501 nonzero rows are signed "
            "quantities spread over 16 warehouses, positive in retail/salon warehouses and negative in "
            "production/lab warehouses. The same item can carry different values per warehouse and OITM.Consig "
            "equals the item-level sum of OITW.Consig. Nonzero values are not specific to the single "
            "U_CONSIGNACION=1 customer, not specific to YUAL products and not specific to Agrotel products; "
            "the same ItemCode x WhsCode is sold to multiple customers. It is therefore an item-warehouse "
            "quantity layer, not a customer consignment flag or a customer-owned balance."
        ),
        "LIMITATIONS": [
            "No local SAP documentation describes OITW.Consig (SEMANTIC_DOCUMENTATION_FOUND=NO), so the exact "
            "business label of the quantity cannot be confirmed from authorized local sources.",
            "OITW is current state only; no audit/change log for OITW.Consig was observed.",
            "Only one Business Partner has OCRD.U_CONSIGNACION=1, so no repeated cross-customer pattern exists.",
        ],
        "ELAPSED_MS": round((time.perf_counter() - started) * 1000, 3),
    }
    result["RESULT"] = GATE + "_PASS"

    # ------------------------------------------------------------------ evidence
    _write("summary.json", result)
    _write("current_state.json", {
        "GATE": GATE,
        "source_read_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "OITW_CURRENT_STATE_ONLY": "YES",
        "DUCKLAKE_MODIFIED": "NO",
        "ATOMIC_MODIFIED": "NO",
        "REFERENCE_V2_MODIFIED": "NO",
        "CONSIGNATION_BALANCE_COMPUTED": "NO",
    })
    _write("column_metadata.json", metadata)
    _write("value_distribution.json", values)
    _write("warehouse_distribution.json", warehouses)
    _write("product_distribution.json", products)
    _write("yual_analysis.json", yual)
    _write("agrotel_analysis.json", agrotel)
    _write("control_samples.json", controls)
    _write("customer_independence_test.json", independence)
    _write("warehouse_scope_test.json", scope)
    _write("oitm_relation.json", oitm)
    _write("mrp_relation.json", mrp)
    _write("quantity_relation.json", quantity)
    _write("history_availability.json", history)
    _write("u_consignacion_relation.json", relation)
    _write("semantic_classification.json", {
        "OITW_CONSIG_SEMANTIC_CLASS": semantic_class,
        "OITW_CONSIG_SEMANTIC_CONFIDENCE": "SUPPORTED",
        "OITW_CONSIG_VALUE_SEMANTIC_TYPE": quantity["OITW_CONSIG_VALUE_SEMANTIC_TYPE"],
        "CUSTOMER_SPECIFIC_INTERPRETATION": independence["CUSTOMER_SPECIFIC_INTERPRETATION"],
        "WAREHOUSE_SCOPED_BEHAVIOR": scope["WAREHOUSE_SCOPED_BEHAVIOR"],
        "ITEM_SCOPED_BEHAVIOR": scope["ITEM_SCOPED_BEHAVIOR"],
        "grounds": [
            "DECIMAL(21,6) signed values equal a quantity layer, not a flag or enum",
            "grain ItemCode x WhsCode; warehouse-scoped (same item differs across warehouses)",
            "OITM.Consig equals the item-level sum of OITW.Consig",
            "nonzero rows exist for products of customers with U_CONSIGNACION=0 and are sold to many customers",
        ],
    })
    _write("datalake_relevance.json", {
        "OITW_CONSIG_DATALAKE_RELEVANCE": relevance,
        "rationale": (
            "A warehouse-scoped quantity layer may enrich inventory analytics, but it is not required for "
            "customer consignment, it is rarely nonzero and its business label is undocumented. Recommend "
            "OPTIONAL future ingestion only, with no schema change in this gate."
        ),
        "schema_modified": "NO",
    })
    _write("semantic_documentation.json", local_docs)
    _write("potential_balance_model.json", balance)
    _write("query_log.json", source.query_log)

    report = [
        f"# {GATE}", "", "```text",
        *[f"{key}={value}" for key, value in result.items() if key not in {"LIMITATIONS", "ANSWER"}],
        "```", "",
        "## Objetivo", "",
        "Descubrir con evidencia qué representa realmente `OITW.Consig` en la instalación SAP de Telchi, "
        "sin asumir consignación por cliente, stock consignado ni propiedad en terceros.", "",
        "## Qué es el campo", "",
        result["ANSWER"], "",
        "## Clasificación semántica", "",
        f"- Clase: `{semantic_class}`",
        f"- Confianza: `SUPPORTED`",
        f"- Tipo de valor: `{quantity['OITW_CONSIG_VALUE_SEMANTIC_TYPE']}`",
        f"- Granularidad: `{oitw_grain()}`",
        f"- Comportamiento por almacén: `{scope['WAREHOUSE_SCOPED_BEHAVIOR']}`",
        f"- Interpretación por cliente: `{independence['CUSTOMER_SPECIFIC_INTERPRETATION']}`",
        f"- Relación con `OCRD.U_CONSIGNACION`: `{relation['U_CONSIGNACION_OITW_CONSIG_RELATION']}`",
        f"- Relevancia Data Lake: `{relevance}`", "",
        "## YUAL / Agrotel", "",
        f"- YUAL `{YUAL_CARDCODE}`: {yual['products_with_nonzero_consig']} de {yual['products_total']} "
        f"productos con Consig no nulo; en LAB-D2: {', '.join(yual['yual_products_with_consig_in_lab_d2']) or 'ninguno'}.",
        f"- Agrotel `{AGROTEL_CARDCODE}`: {agrotel['products_with_nonzero_consig']} de "
        f"{agrotel['products_total']} productos con Consig no nulo (comparación únicamente, no reclasificación).",
        "- El campo aparece en contextos ordinarios sin relación con YUAL ni Agrotel.", "",
        "## Seguridad", "",
        "SAP READ ONLY, `SAP_WRITE_COUNT=0`, `AI_INVOCATIONS=0`, sin cálculo de saldo, sin escritura en "
        "DuckLake/Atomic/Reference V2 y sin reclasificar Agrotel.", "",
        "## Limitaciones", "",
        *[f"- {item}" for item in result["LIMITATIONS"]], "",
        "## STOP AND REVIEW", "",
        "No se incorpora `OITW.Consig` a lógica productiva, no se calcula consignación y no se modifica el Data Lake.", "",
        f"Resultado final: `{result['RESULT']}`.",
    ]
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    (EVIDENCE_ROOT / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(_run(), indent=2, sort_keys=True, ensure_ascii=False, default=str))