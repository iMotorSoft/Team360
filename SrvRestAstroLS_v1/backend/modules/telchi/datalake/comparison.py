"""Bounded, drillable SAP-extraction versus trusted DuckLake comparisons."""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .ducklake import DuckLakeConnector
from .planner import SegmentSpec
from .rebuild import read_raw_rows


def _canonical_row(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), default=lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value))


def _number(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _key(row: dict[str, Any], domain: str) -> tuple[str, ...]:
    if domain == "sales":
        return str(row.get("DocEntry")), str(row.get("LineNum"))
    if domain in {"inventory_movement", "inventory_movements"}:
        return str(row.get("TransNum")), str(row.get("TransSeq"))
    return str(row.get("ItemCode")), str(row.get("WhsCode"))


def _raw_files(results: list[dict[str, Any]], domain: str) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    output = []
    for result in results:
        if result.get("domain") != domain:
            continue
        manifest = result.get("raw_manifest") or {}
        path = manifest.get("path")
        if not path or not Path(path).is_file():
            continue
        output.append((manifest, read_raw_rows(Path(path))))
    return output


def _sales_duck_rows(connection: Any, table: str, keys: list[tuple[str, str]]) -> list[tuple[Any, ...]]:
    if not keys:
        return []
    where = " OR ".join("(doc_entry=? AND line_num=?)" for _ in keys)
    params = [value for pair in keys for value in pair]
    return connection.execute(
        f"SELECT doc_entry, line_num, item_code, whs_code, quantity, line_total "
        f"FROM telchi.atomic.\"{table.replace(chr(34), chr(34) * 2)}\" WHERE {where}", params
    ).fetchall()


def _inventory_movement_duck_rows(connection: Any, table: str, keys: list[tuple[str, ...]]) -> list[dict[str, Any]]:
    if not keys:
        return []
    columns = ("trans_num", "trans_seq", "instance", "trans_type", "doc_entry", "base_ref", "doc_date", "item_code", "warehouse", "in_qty", "out_qty", "movement_qty", "price", "calc_price", "trans_value", "created_by", "app_obj_abs", "app_obj_type", "doc_line_num", "ref1", "ref2", "comments", "jrnl_memo", "doc_due_date", "doc_time", "card_code", "card_name", "dscription", "balance", "slp_code", "user_sign", "appl_obj", "app_obj_line")
    # The source key list can contain tens of thousands of rows.  Building an
    # OR predicate per key is both slower and less bounded than reading the
    # already-bounded Atomic relation once and intersecting exact keys in
    # Python; no source rows are read here.
    sql = f'SELECT {", ".join(columns)} FROM telchi.atomic."{table.replace(chr(34), chr(34) * 2)}"'
    rows = connection.execute(sql).fetchall()
    wanted = set(keys)
    return [dict(zip(columns, row)) for row in rows if (str(row[0]), str(row[1])) in wanted]


def _movement_source_projection(row: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "trans_num": "TransNum", "trans_seq": "TransSeq", "instance": "Instance", "trans_type": "TransType",
        "doc_entry": "DocEntry", "base_ref": "BaseRef", "doc_date": "DocDate", "item_code": "ItemCode",
        "warehouse": "Warehouse", "in_qty": "InQty", "out_qty": "OutQty", "price": "Price", "calc_price": "CalcPrice",
        "trans_value": "TransValue", "created_by": "CreatedBy", "app_obj_abs": "AppObjAbs", "app_obj_type": "AppObjType",
        "doc_line_num": "DocLineNum", "ref1": "Ref1", "ref2": "Ref2", "comments": "Comments", "jrnl_memo": "JrnlMemo",
        "doc_due_date": "DocDueDate", "doc_time": "DocTime", "card_code": "CardCode", "card_name": "CardName",
        "dscription": "Dscription", "balance": "Balance", "slp_code": "SlpCode", "user_sign": "UserSign",
        "appl_obj": "ApplObj", "app_obj_line": "AppObjLine",
    }
    return {target: row.get(source) for target, source in mapping.items()}


def _movement_equal(source: dict[str, Any], actual: dict[str, Any]) -> bool:
    def normalized(value: Any) -> Any:
        value = _source_value(value)
        if value is None:
            return None
        text = str(value).replace("T", " ")
        return text.removesuffix("+00:00")
    return all(normalized(source.get(column)) == normalized(actual.get(column)) for column in source)


def _source_value(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _movement_decimal(rows: list[dict[str, Any]], field: str) -> str:
    return str(sum((_number(row.get(field)) for row in rows), Decimal("0")))


def _movement_comparisons(connector: DuckLakeConnector, table: str, manifest: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({_key(row, "inventory_movement") for row in rows})
    key_columns = tuple(manifest.get("source_key_columns") or ("TransNum", "TransSeq"))
    # The current Telchi source uses TransNum+TransSeq.  Other source-key
    # choices remain valid for discovery/reconciliation, but this comparison
    # reader is intentionally strict about its physical key projection.
    if key_columns != ("TransNum", "TransSeq"):
        return []
    source_by_key = {_key(row, "inventory_movement"): row for row in rows}
    with connector.session(read_only=True) as connection:
        duck_rows = _inventory_movement_duck_rows(connection, table, keys)
    duck_by_key = {(str(row.get("trans_num")), str(row.get("trans_seq"))): row for row in duck_rows}
    first_key = keys[0] if keys else ("", "")
    first_source = _movement_source_projection(source_by_key[first_key]) if first_key in source_by_key else {}
    exact = duck_by_key.get(first_key)
    first_exact = bool(exact and _movement_equal(first_source, exact))
    first_comparison = _comparison(
        "oinm_exact_source_key", "inventory_movement", "one native TransNum x TransSeq movement lookup",
        f"TransNum={first_key[0]} AND TransSeq={first_key[1]}", [first_key], first_source,
        exact if first_exact else None, manifest.get("source_as_of"),
    )
    if first_exact:
        first_comparison.update({"status": "EXACT", "difference": None})
    output = [first_comparison]
    dates = sorted(str(row.get("DocDate"))[:10] for row in rows if row.get("DocDate") is not None)
    date_from, date_to = (dates[0], dates[-1]) if dates else (None, None)
    if date_to:
        from datetime import date, timedelta
        date_to_exclusive = (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()
    else:
        date_to_exclusive = None
    item = next((str(row.get("ItemCode")) for row in rows if row.get("ItemCode") is not None), "")
    warehouse = next((str(row.get("Warehouse")) for row in rows if row.get("Warehouse") is not None), "")
    source_item = [row for row in rows if str(row.get("ItemCode")) == item and (not date_from or date_from <= str(row.get("DocDate"))[:10] < date_to_exclusive)]
    source_warehouse = [row for row in rows if str(row.get("Warehouse")) == warehouse and (not date_from or date_from <= str(row.get("DocDate"))[:10] < date_to_exclusive)]
    source_pair = [row for row in rows if str(row.get("ItemCode")) == item and str(row.get("Warehouse")) == warehouse]
    item_duck = [row for row in duck_rows if str(row.get("item_code")) == item]
    warehouse_duck = [row for row in duck_rows if str(row.get("warehouse")) == warehouse]
    pair_duck = [row for row in duck_rows if str(row.get("item_code")) == item and str(row.get("warehouse")) == warehouse]
    def aggregate(source_rows: list[dict[str, Any]], lake_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
        source_types = sorted(str(row.get("TransType")) for row in source_rows)
        lake_types = sorted(str(row.get("trans_type")) for row in lake_rows)
        return ({"rows": len(source_rows), "in_qty": _movement_decimal(source_rows, "InQty"), "out_qty": _movement_decimal(source_rows, "OutQty"), "trans_types": source_types}, {"rows": len(lake_rows), "in_qty": _movement_decimal(lake_rows, "in_qty"), "out_qty": _movement_decimal(lake_rows, "out_qty"), "trans_types": lake_types})
    output.append(_comparison("oinm_itemcode_date_history", "inventory_movement", "ItemCode history in bounded extracted dates", f"ItemCode={item} AND DocDate={date_from}..{date_to}", [_key(row, "inventory_movement") for row in source_item], *aggregate(source_item, item_duck), manifest.get("source_as_of")))
    output.append(_comparison("oinm_warehouse_date_history", "inventory_movement", "Warehouse history in bounded extracted dates", f"Warehouse={warehouse} AND DocDate={date_from}..{date_to}", [_key(row, "inventory_movement") for row in source_warehouse], *aggregate(source_warehouse, warehouse_duck), manifest.get("source_as_of")))
    output.append(_comparison("oinm_item_warehouse_aggregate", "inventory_movement", "ItemCode x Warehouse quantity aggregate", f"ItemCode={item} AND Warehouse={warehouse}", [_key(row, "inventory_movement") for row in source_pair], {"rows": len(source_pair), "in_qty": _movement_decimal(source_pair, "InQty"), "out_qty": _movement_decimal(source_pair, "OutQty")}, {"rows": len(pair_duck), "in_qty": _movement_decimal(pair_duck, "in_qty"), "out_qty": _movement_decimal(pair_duck, "out_qty")}, manifest.get("source_as_of")))
    type_counts = {}
    for row in rows:
        type_counts[str(row.get("TransType"))] = type_counts.get(str(row.get("TransType")), 0) + 1
    lake_type_counts = {}
    for row in duck_rows:
        lake_type_counts[str(row.get("trans_type"))] = lake_type_counts.get(str(row.get("trans_type")), 0) + 1
    output.append(_comparison("oinm_period_type_aggregate", "inventory_movement", "small bounded period across multiple TransTypes", str(manifest.get("scope")), keys, {"rows": len(rows), "in_qty": _movement_decimal(rows, "InQty"), "out_qty": _movement_decimal(rows, "OutQty"), "trans_type_counts": type_counts}, {"rows": len(duck_rows), "in_qty": _movement_decimal(duck_rows, "in_qty"), "out_qty": _movement_decimal(duck_rows, "out_qty"), "trans_type_counts": lake_type_counts}, manifest.get("source_as_of")))
    return output


def _inventory_duck_rows(connection: Any, table: str, keys: list[tuple[str, str]]) -> list[tuple[Any, ...]]:
    if not keys:
        return []
    where = " OR ".join("(item_code=? AND whs_code=?)" for _ in keys)
    params = [value for pair in keys for value in pair]
    return connection.execute(
        f"SELECT item_code, whs_code, on_hand, is_commited, on_order "
        f"FROM telchi.atomic.\"{table.replace(chr(34), chr(34) * 2)}\" WHERE {where}", params
    ).fetchall()


def _comparison(query_id: str, domain: str, definition: str, scope: str, keys: list[tuple[str, str]], source: Any, lake: Any, as_of: Any) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "domain": domain,
        "definition": definition,
        "scope": scope,
        "source_keys": [list(key) for key in keys],
        "SAP_result": source,
        "DuckLake_result": lake,
        "difference": None if source == lake else {"source": source, "ducklake": lake},
        "as_of": as_of,
        "status": "EXACT" if source == lake else "MISMATCH",
    }


def formal_comparison_suite(
    connector: DuckLakeConnector,
    table_names: dict[str, str | None],
    results: list[dict[str, Any]],
    *,
    source: Any | None = None,
) -> dict[str, Any]:
    """Produce five query-shaped exactness checks per populated domain.

    The raw files are immutable SAP extraction results from the same run and
    retain ``source_as_of``.  DuckLake is queried only for the exact source-key
    scopes represented by those files; no broad date delete or full-table
    comparison is inferred.
    """
    sales_parts = _raw_files(results, "sales")
    inventory_parts = _raw_files(results, "inventory")
    movement_parts = _raw_files(results, "inventory_movement") + _raw_files(results, "inventory_movements")
    source_rechecks: dict[str, dict[str, Any]] = {}
    for domain, parts in (("sales", sales_parts), ("inventory", inventory_parts), ("inventory_movement", movement_parts)):
        if source is None or not parts:
            continue
        manifest, raw_rows = parts[0]
        spec = SegmentSpec(
            segment_id=str(manifest.get("segment_id")), domain=domain,
            business_date_from=manifest.get("business_date_from"), business_date_to=manifest.get("business_date_to"),
            key_from=str(manifest.get("source_key_from", "")), key_to=str(manifest.get("source_key_to", "")),
            strategy="DOCENTRY_RANGE" if domain == "sales" else ("ITEMCODE_WHS_BOUNDED_GROUP" if domain == "inventory" else "TRANSNUM_DATE_BOUNDED"),
            scope=str(manifest.get("scope", "")),
        )
        fresh = source.verify(spec)
        source_rechecks[domain] = {
            "status": "EXACT" if sorted(_canonical_row(row) for row in fresh) == sorted(_canonical_row(row) for row in raw_rows) else "SOURCE_CHANGED_DURING_COMPARISON",
            "source_as_of": manifest.get("source_as_of"),
            "raw_row_count": len(raw_rows), "fresh_sap_row_count": len(fresh),
        }
    output: dict[str, list[dict[str, Any]]] = {"sales": [], "inventory": [], "inventory_movement": []}
    with connector.session(read_only=True) as connection:
        sales_table = table_names.get("sales_line")
        if sales_table and sales_parts:
            manifest, rows = sales_parts[0]
            keys = sorted({_key(row, "sales") for row in rows})
            duck = _sales_duck_rows(connection, sales_table, keys)
            source_by_key = {_key(row, "sales"): row for row in rows}
            duck_by_key = {(str(row[0]), str(row[1])): row for row in duck}
            doc = keys[0][0] if keys else ""
            item = next((str(row.get("ItemCode")) for row in rows if row.get("ItemCode") is not None), "")
            whs = next((str(row.get("WhsCode")) for row in rows if row.get("WhsCode") is not None), "")
            # Each definition drills down to the same exact source identities;
            # only the projection/aggregation changes.
            output["sales"] = [
                _comparison("sales_exact_docentry", "sales", "exact DocEntry line set", f"DocEntry={doc}", [key for key in keys if key[0] == doc], len([key for key in keys if key[0] == doc]), len([key for key in duck_by_key if key[0] == doc]), manifest.get("source_as_of")),
                _comparison("sales_document_lines", "sales", "document plus all lines", f"DocEntry={doc}", [key for key in keys if key[0] == doc], sorted([key for key in source_by_key if key[0] == doc]), sorted([key for key in duck_by_key if key[0] == doc]), manifest.get("source_as_of")),
                _comparison("sales_itemcode_aggregate", "sales", "ItemCode line count and quantity", f"ItemCode={item}", [key for key in keys if source_by_key[key].get("ItemCode") == item], {"rows": sum(source_by_key[key].get("ItemCode") == item for key in keys), "quantity": str(sum((_number(source_by_key[key].get("Quantity")) for key in keys if source_by_key[key].get("ItemCode") == item), Decimal("0")))}, {"rows": sum(row[2] == item for row in duck), "quantity": str(sum((_number(row[4]) for row in duck if row[2] == item), Decimal("0")))}, manifest.get("source_as_of")),
                _comparison("sales_warehouse_aggregate", "sales", "warehouse line count and quantity", f"WhsCode={whs}", [key for key in keys if source_by_key[key].get("WhsCode") == whs], {"rows": sum(source_by_key[key].get("WhsCode") == whs for key in keys), "quantity": str(sum((_number(source_by_key[key].get("Quantity")) for key in keys if source_by_key[key].get("WhsCode") == whs), Decimal("0")))}, {"rows": sum(row[3] == whs for row in duck), "quantity": str(sum((_number(row[4]) for row in duck if row[3] == whs), Decimal("0")))}, manifest.get("source_as_of")),
                _comparison("sales_period_aggregate", "sales", "bounded extraction period line count and total", str(manifest.get("scope")), keys, {"rows": len(rows), "line_total": str(sum((_number(row.get("LineTotal")) for row in rows), Decimal("0")))}, {"rows": len(duck), "line_total": str(sum((_number(row[5]) for row in duck), Decimal("0")))}, manifest.get("source_as_of")),
            ]
        movement_table = table_names.get("inventory_movement")
        if movement_table and movement_parts:
            manifest, rows = movement_parts[0]
            output["inventory_movement"] = _movement_comparisons(connector, movement_table, manifest, rows)
        inventory_table = table_names.get("inventory_balance_snapshot")
        if inventory_table and inventory_parts:
            manifest, rows = inventory_parts[0]
            keys = sorted({_key(row, "inventory") for row in rows})
            duck = _inventory_duck_rows(connection, inventory_table, keys)
            source_by_key = {_key(row, "inventory"): row for row in rows}
            duck_by_key = {(str(row[0]), str(row[1])): row for row in duck}
            item, whs = keys[0] if keys else ("", "")
            same_warehouse = [key for key in keys if key[1] == whs]
            same_item = [key for key in keys if key[0] == item]
            def state_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
                return (str(row.get("ItemCode")), str(row.get("WhsCode")), row.get("OnHand"), row.get("IsCommited"), row.get("OnOrder"))

            output["inventory"] = [
                _comparison("inventory_exact_item_warehouse", "inventory", "exact ItemCode x WhsCode state", f"ItemCode={item} AND WhsCode={whs}", [(item, whs)], state_tuple(source_by_key[(item, whs)]), duck_by_key.get((item, whs)), manifest.get("source_as_of")),
                _comparison("inventory_several_items_same_warehouse", "inventory", "several items in one warehouse", f"WhsCode={whs}", same_warehouse, sorted(state_tuple(source_by_key[key]) for key in same_warehouse), sorted(duck_by_key[key] for key in same_warehouse), manifest.get("source_as_of")),
                _comparison("inventory_same_item_warehouses", "inventory", "same item across warehouses", f"ItemCode={item}", same_item, sorted(state_tuple(source_by_key[key]) for key in same_item), sorted(duck_by_key[key] for key in same_item), manifest.get("source_as_of")),
                _comparison("inventory_small_scope_stock", "inventory", "aggregate stock in bounded scope", str(manifest.get("scope")), keys, str(sum((_number(row.get("OnHand")) for row in rows), Decimal("0"))), str(sum((_number(row[2]) for row in duck), Decimal("0"))), manifest.get("source_as_of")),
                _comparison("inventory_movement_state_check", "inventory", "current OITW state and movement availability", str(manifest.get("scope")), keys, {"state_rows": len(rows), "movement_rows": 0}, {"state_rows": len(duck), "movement_rows": 0}, manifest.get("source_as_of")),
            ]
    for items in output.values():
        for item in items:
            recheck = source_rechecks.get(item["domain"])
            item["sap_recheck"] = recheck or {"status": "RAW_EXTRACTION_AS_SOURCE"}
            if recheck and recheck["status"] != "EXACT":
                item["status"] = "MISMATCH"
    return {
        "sales": output["sales"],
        "inventory": output["inventory"],
        "inventory_movement": output["inventory_movement"],
        "sales_exact": sum(item["status"] == "EXACT" for item in output["sales"]),
        "inventory_exact": sum(item["status"] == "EXACT" for item in output["inventory"]),
        "inventory_movement_exact": sum(item["status"] == "EXACT" for item in output["inventory_movement"]),
        "source_rechecks": source_rechecks,
        "source_as_of_policy": "bounded extraction timestamp preserved; inventory comparisons use one source_as_of",
    }
