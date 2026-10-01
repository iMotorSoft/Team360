"""TELCHI_MRP_CONFIGURATION_AUDIT_V1.

Investigation-only, SELECT-only audit of the SAP Business One MRP model.
The runner discovers physical columns first and only then extracts fields that
exist in this company database.  It deliberately does not execute MRP, create
forecasts, or write SAP.  Physical outputs are Parquet in DATA_ROOT.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.paths import DATA_ROOT, INVESTIGATION_ROOT
from modules.telchi.investigation.validation.credit_control.readonly import ReadOnlyConnection

GATE = "TELCHI_MRP_CONFIGURATION_AUDIT_V1"
VERSION = "mrp_configuration_audit_v1"
SCHEMA = "TELCHI"
SQL_DIR = INVESTIGATION_ROOT / "sql" / "current" / "mrp_configuration"
DEFAULT_RUN_ROOT = DATA_ROOT / "business" / "mrp_configuration_audit_v1"
DEFAULT_REPORT = INVESTIGATION_ROOT / "docs" / "telchi_mrp_configuration_audit_v1_report.md"

CORE_TABLES = ("OITM", "OITW", "OITB", "OWHS", "OCRD", "OADM", "OITT", "ITT1", "OFCT", "FCT1")
INTERNAL_FORECAST_PREFIXES = ("PAL_", "FORECASTSLR_", "MULTIPLEFORECAST_", "CRSP_")

ITEM_FIELDS: dict[str, tuple[str, ...]] = {
    "ItemCode": ("ItemCode",), "ItemName": ("ItemName",), "ItemGroup": ("ItmsGrpCod",),
    "ActiveFlag": ("validFor",), "FrozenFlag": ("frozenFor",), "DeletedFlag": ("Deleted",),
    "InventoryItem": ("InvntItem",), "PurchaseItem": ("PrchseItem",), "SalesItem": ("SellItem",),
    "PlanningMethodRaw": ("PlaningSys",), "ProcurementMethodRaw": ("PrcrmntMtd",),
    "LeadTime": ("LeadTime",), "MinimumInventory": ("MinLevel",), "MaximumInventory": ("MaxLevel",),
    "SafetyStock": ("ReorderPnt",), "OrderMultiple": ("OrdrMulti",), "MinimumOrderQty": ("MinOrdrQty",),
    "OrderInterval": ("OrdrIntrvl",), "OrderCycle": ("OrdrIntrvl",), "ReorderQty": ("ReorderQty",),
    "PreferredVendor": ("CardCode",), "DefaultWarehouse": ("DfltWH",), "ProductionTime": ("MnufctTime",),
    "IssueMethod": ("IssueMthd",), "TreeType": ("TreeType",), "UProduce": ("U_PRODUCE",),
    "InventoryUOM": ("InvntryUom",), "SourceDate": ("UpdateDate",),
}
WAREHOUSE_FIELDS: dict[str, tuple[str, ...]] = {
    "ItemCode": ("ItemCode",), "Warehouse": ("WhsCode",), "OnHand": ("OnHand",),
    "IsCommited": ("IsCommited",), "OnOrder": ("OnOrder",), "MinimumInventory": ("MinStock",),
    "MaximumInventory": ("MaxStock",), "MinimumOrderQty": ("MinOrder",), "LockedFlag": ("Locked",),
    "FrozenFlag": ("Freezed",), "DefaultBin": ("DftBinAbs",),
}
GROUP_FIELDS: dict[str, tuple[str, ...]] = {
    "ItemGroup": ("ItmsGrpCod",), "ItemGroupName": ("ItmsGrpNam",),
    "PlanningMethodRaw": ("PlaningSys",), "ProcurementMethodRaw": ("PrcrmntMtd",),
    "LeadTime": ("LeadTime",), "MinimumInventory": ("MinOrdrQty",), "MaximumInventory": ("OrdrMulti",),
    "OrderInterval": ("OrdrIntrvl",), "OrderMultiple": ("OrdrMulti",),
}
WAREHOUSE_MASTER_FIELDS: dict[str, tuple[str, ...]] = {
    "Warehouse": ("WhsCode",), "WarehouseName": ("WhsName",), "PlanningIncludedFlag": ("Nettable",),
    "InactiveFlag": ("Inactive",), "DefaultWarehouseFlag": ("WhsCode",),
}
FORECAST_HEADER_FIELDS: dict[str, tuple[str, ...]] = {
    "ForecastId": ("AbsID",), "ForecastCode": ("Code",), "ForecastName": ("Name",),
    "StartDate": ("StartDate",), "EndDate": ("EndDate",), "FormView": ("FormView",),
}
FORECAST_LINE_FIELDS: dict[str, tuple[str, ...]] = {
    "ForecastId": ("AbsID",), "ForecastLineId": ("LineID",), "ItemCode": ("ItemCode",),
    "Period": ("Date",), "Quantity": ("Quantity",), "Warehouse": ("WhsCode",),
}
BOM_HEADER_FIELDS: dict[str, tuple[str, ...]] = {
    "ItemCode": ("Code",), "BOMTypeRaw": ("TreeType",), "BOMQuantity": ("Qauntity",),
    "BOMName": ("Name",), "BOMWarehouse": ("ToWH",), "CreateDate": ("CreateDate",),
    "UpdateDate": ("UpdateDate",),
}
BOM_LINE_FIELDS: dict[str, tuple[str, ...]] = {
    "ItemCode": ("Father",), "ComponentItemCode": ("Code",), "ComponentLine": ("ChildNum",),
    "Quantity": ("Quantity",), "Warehouse": ("Warehouse",), "IssueMethod": ("IssueMthd",),
}
GLOBAL_FIELDS: dict[str, tuple[str, ...]] = {
    "DefaultWarehouse": ("DfltWhs",), "DefaultReserveWarehouse": ("DftResWhs",),
    "AutoReserveWarehouse": ("AutoResWhs",), "ForecastConsumption": ("ConsumeFCT",),
    "PlanningDaysBack": ("DaysBack",), "PlanningDaysForward": ("DaysFwrd",),
    "InactivePlanning": ("InActPln",), "InventorySystem": ("InvntSystm",),
    "DefaultPlanningWarehouse": ("DfltWhs",), "CompanyCurrency": ("MainCurncy",),
}

COMPARISON_COLUMNS = [
    "ItemCode", "Warehouse", "SAP_PlanningMethod", "SAP_ProcurementMethod", "SAP_LeadTime",
    "SAP_MinStock", "SAP_MaxStock", "SAP_SafetyStock", "SAP_ReorderPoint", "SAP_MOQ", "SAP_Multiple",
    "SAP_OrderInterval", "SAP_PreferredVendor", "SAP_BOM", "SAP_Forecast", "REAL_LeadTime_Median",
    "REAL_LeadTime_P90", "REAL_Demand", "REAL_DemandVariability", "REAL_StockoutFrequency",
    "REAL_ReplenishmentQty", "REAL_ReplenishmentInterval", "REAL_BOMConsumption", "GapType",
    "GapMagnitude", "MRPImpact",
]


def clean(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def qident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def execute_rows(cur: Any, schema: str, table: str, fields: dict[str, tuple[str, ...]], available: dict[str, list[str]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Select the first physically present candidate for each logical field."""
    physical = {x.upper(): x for x in available.get(table, [])}
    selected: dict[str, str] = {}
    expressions: list[str] = []
    for logical, candidates in fields.items():
        source = next((physical[c.upper()] for c in candidates if c.upper() in physical), None)
        if source:
            selected[logical] = source
            expressions.append(f"{qident(source)} AS {qident(logical)}")
        else:
            expressions.append(f"NULL AS {qident(logical)}")
    cur.execute(f"SELECT {', '.join(expressions)} FROM {qident(schema)}.{qident(table)}")
    names = [x[0] for x in cur.description]
    return [{name: clean(value) for name, value in zip(names, row)} for row in cur.fetchall()], selected


def catalog(cur: Any, schema: str) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    sql = "\n".join(line for line in (SQL_DIR / "catalog_discovery_v1.sql").read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--")).strip().rstrip(";")
    cur.execute(sql, (schema, schema))
    candidates = sorted({(r[0], r[1]) for r in cur.fetchall()})
    available: dict[str, list[str]] = {}
    inventory: list[dict[str, Any]] = []
    for table, object_type in candidates:
        try:
            cur.execute('SELECT "COLUMN_NAME" FROM "SYS"."TABLE_COLUMNS" WHERE "SCHEMA_NAME"=? AND "TABLE_NAME"=? ORDER BY "POSITION"', (schema, table))
            cols = [r[0] for r in cur.fetchall()]
            if not cols:
                cur.execute(f"SELECT * FROM {qident(schema)}.{qident(table)} LIMIT 0")
                cols = [d[0] for d in cur.description]
            available[table] = cols
            cur.execute(f"SELECT COUNT(*) FROM {qident(schema)}.{qident(table)}")
            row_count = cur.fetchone()[0]
            status = "DISCOVERED"
        except Exception as exc:
            cols, row_count, status = [], None, f"UNRESOLVED: {exc}"
        inventory.append({"Schema": schema, "ObjectName": table, "ObjectType": object_type,
                          "RowCount": row_count, "ColumnCount": len(cols), "Columns": json.dumps(cols, ensure_ascii=False),
                          "MRPRelevance": relevance(table), "DiscoveryStatus": status})
    return available, inventory


def relevance(table: str) -> str:
    upper = table.upper()
    if table in CORE_TABLES:
        return "CORE_MRP_SOURCE"
    if "FORECAST" in upper or upper in {"OFCT", "FCT1"}:
        return "FORECAST_OR_SUPPORT"
    if "MRP" in upper or "PLAN" in upper:
        return "PLANNING_OR_SUPPORT"
    return "CANDIDATE_SUPPORT"


def scalar_table(cur: Any, schema: str, table: str, fields: dict[str, tuple[str, ...]], available: dict[str, list[str]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if table not in available:
        return [], {}
    return execute_rows(cur, schema, table, fields, available)


def active(row: dict[str, Any]) -> bool:
    valid = str(row.get("ActiveFlag") or "").upper()
    frozen = str(row.get("FrozenFlag") or "").upper()
    deleted = str(row.get("DeletedFlag") or "").upper()
    return valid in {"Y", "YES", "1", "TRUE"} and frozen not in {"Y", "YES", "1", "TRUE"} and deleted not in {"Y", "YES", "1", "TRUE"}


def has_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def positive(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def status(value: Any) -> str:
    if not has_value(value):
        return "MISSING"
    if isinstance(value, (int, float, Decimal)) and float(value) == 0:
        return "ZERO"
    return "CONFIGURED"


def planning_semantic(raw: Any) -> str:
    # SAP B1's standard codes are retained beside this executive label.
    code = str(raw or "").upper()
    return {"M": "MRP", "N": "NO_MRP"}.get(code, "UNKNOWN" if code else "MISSING")


def procurement_semantic(raw: Any) -> str:
    code = str(raw or "").upper()
    return {"M": "MAKE", "B": "BUY"}.get(code, "UNKNOWN" if code else "MISSING")


def activity(cur: Any, available: dict[str, list[str]]) -> dict[str, dict[str, int]]:
    """Small HANA aggregates for reproducible Tier A/B/C selection only."""
    result: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    specs = [("OINV", "INV1", "sales"), ("OPOR", "POR1", "purchases"), ("OWOR", "OWOR", "production")]
    for header, line, label in specs:
        if header not in available or line not in available:
            continue
        try:
            if header == line:
                sql = f'''SELECT "ItemCode", COUNT(*) FROM {qident(SCHEMA)}.{qident(header)}
                          WHERE "PostDate" >= ADD_MONTHS(CURRENT_DATE, -12) GROUP BY "ItemCode"'''
            else:
                date_col = "DocDate" if "DocDate" in available[header] else "PostDate"
                sql = f'''SELECT L."ItemCode", COUNT(*) FROM {qident(SCHEMA)}.{qident(line)} L
                          JOIN {qident(SCHEMA)}.{qident(header)} H ON H."DocEntry"=L."DocEntry"
                          WHERE H.{qident(date_col)} >= ADD_MONTHS(CURRENT_DATE, -12)
                            AND (H."CANCELED"='N' OR H."CANCELED" IS NULL)
                          GROUP BY L."ItemCode"'''
            cur.execute(sql)
            for item, count in cur.fetchall():
                result[str(item)][label] += int(count or 0)
        except Exception:
            # A source not exposed to the READ ONLY user degrades tiers, never the audit.
            continue
    if "OINM" in available:
        try:
            date_col = "DocDate" if "DocDate" in available["OINM"] else "CreateDate"
            cur.execute(f'''SELECT "ItemCode", COUNT(*) FROM {qident(SCHEMA)}."OINM"
                            WHERE {qident(date_col)} >= ADD_MONTHS(CURRENT_DATE, -12)
                            GROUP BY "ItemCode"''')
            for item, count in cur.fetchall():
                result[str(item)]["movements"] += int(count or 0)
        except Exception:
            pass
    return {k: dict(v) for k, v in result.items()}


def enrich_items(items: list[dict[str, Any]], activity_rows: dict[str, dict[str, int]], bom_by_item: dict[str, dict[str, Any]], forecast_items: set[str]) -> None:
    for row in items:
        code = str(row.get("ItemCode") or "")
        act = activity_rows.get(code, {})
        row.update({"RecentSalesCount": act.get("sales", 0), "RecentPurchaseCount": act.get("purchases", 0),
                    "RecentProductionCount": act.get("production", 0), "RecentMovementCount": act.get("movements", 0),
                    "BOMExists": code in bom_by_item, "ForecastExists": code in forecast_items,
                    "PlanningMethod": planning_semantic(row.get("PlanningMethodRaw")),
                    "ProcurementMethod": procurement_semantic(row.get("ProcurementMethodRaw")),
                    "ItemActive": active(row), "PlanningMethodStatus": status(row.get("PlanningMethodRaw")),
                    "ProcurementMethodStatus": status(row.get("ProcurementMethodRaw")), "LeadTimeStatus": status(row.get("LeadTime")),
                    "MinimumInventoryStatus": status(row.get("MinimumInventory")), "MaximumInventoryStatus": status(row.get("MaximumInventory")),
                    "OrderMultipleStatus": status(row.get("OrderMultiple")), "MinimumOrderQtyStatus": status(row.get("MinimumOrderQty")),
                    "PreferredVendorStatus": status(row.get("PreferredVendor"))})
        row["Tier"] = tier(row)


def merge_by_item(items: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("ItemCode")): row for row in items if row.get("ItemCode") is not None}


def make_bom(headers: list[dict[str, Any]], lines: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    counts = Counter(str(x.get("ItemCode")) for x in lines if x.get("ItemCode") is not None)
    by_item: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for row in headers:
        code = str(row.get("ItemCode") or "")
        if not code:
            continue
        item = {**row, "ComponentCount": counts.get(code, 0), "BOMExists": True,
                "BOMType": row.get("BOMTypeRaw") or "UNKNOWN"}
        by_item[code] = item
        out.append(item)
    return out, by_item


def make_forecast(headers: list[dict[str, Any]], lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = {str(x.get("ForecastId")): x for x in headers if x.get("ForecastId") is not None}
    out = []
    for line in lines:
        header = names.get(str(line.get("ForecastId")), {})
        out.append({**header, **line, "ActiveStatus": "NOT_EXPOSED" if header else "UNKNOWN"})
    return out


def warehouse_pairs(items: list[dict[str, Any]], whs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    item_by = merge_by_item(items)
    out: list[dict[str, Any]] = []
    for row in whs:
        item = item_by.get(str(row.get("ItemCode") or ""), {})
        out.append({**row, "ItemName": item.get("ItemName"), "ItemActive": item.get("ItemActive", False),
                    "PlanningMethod": item.get("PlanningMethod", "MISSING"), "PlanningMethodRaw": item.get("PlanningMethodRaw"),
                    "ProcurementMethod": item.get("ProcurementMethod", "MISSING"), "ProcurementMethodRaw": item.get("ProcurementMethodRaw"),
                    "LeadTime": item.get("LeadTime"), "PreferredVendor": item.get("PreferredVendor"),
                    "DefaultWarehouse": item.get("DefaultWarehouse"), "OrderMultiple": item.get("OrderMultiple"),
                    "OrderInterval": item.get("OrderInterval"), "SafetyStockProxy": item.get("SafetyStock"),
                    "BOMExists": item.get("BOMExists", False), "ForecastExists": item.get("ForecastExists", False)})
    return out


def tier(row: dict[str, Any]) -> str:
    score = sum(int(row.get(k, 0) or 0) for k in ("RecentSalesCount", "RecentPurchaseCount", "RecentProductionCount", "RecentMovementCount"))
    if score > 100 or row.get("RecentProductionCount", 0) > 0:
        return "A"
    if score > 0:
        return "B"
    return "C"


def anomaly_rows(items: list[dict[str, Any]], pairs: list[dict[str, Any]], bom: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        code = item.get("ItemCode")
        if not item.get("ItemActive"):
            continue
        def add(kind: str, field: str, evidence: str, impact: str, severity: int = 1) -> None:
            rows.append({"ItemCode": code, "Warehouse": None, "AnomalyType": kind, "Field": field,
                         "Classification": "MISSING" if "MISSING" in kind else "INCONSISTENT" if "INCONSISTENT" in kind else "ZERO",
                         "Evidence": evidence, "PotentialMRPImpact": impact, "Severity": severity,
                         "Tier": tier(item)})
        if item.get("PlanningMethodStatus") == "MISSING": add("PLANNING_METHOD_MISSING", "PlaningSys", "active item without physical planning code", "item may be outside MRP", 5)
        if item.get("ProcurementMethodStatus") == "MISSING": add("PROCUREMENT_METHOD_MISSING", "PrcrmntMtd", "active item without physical procurement code", "make/buy decision unavailable", 5)
        if item.get("LeadTimeStatus") in {"MISSING", "ZERO"}: add("LEAD_TIME_" + item["LeadTimeStatus"], "LeadTime", repr(item.get("LeadTime")), "time-phased supply may be immediate or unresolved", 4)
        if item.get("PlanningMethod") == "MAKE" or item.get("ProcurementMethod") == "MAKE":
            if code not in bom: add("PRODUCTION_WITHOUT_BOM", "OITT/ITT1", "make semantic but no current BOM", "MRP cannot explode components", 5)
        if code in bom and item.get("ProcurementMethod") == "BUY": add("BOM_PROCUREMENT_INCONSISTENT", "PrcrmntMtd/OITT", "BOM exists with BUY semantic", "MRP may buy finished item instead of exploding BOM", 4)
        if item.get("ProcurementMethod") == "BUY" and not has_value(item.get("PreferredVendor")): add("PURCHASE_WITHOUT_VENDOR", "CardCode", "BUY semantic without preferred vendor", "source selection unavailable", 3)
        for field in ("MinimumInventory", "MaximumInventory", "OrderMultiple", "MinimumOrderQty"):
            if status(item.get(field)) == "ZERO": add("" + field.upper() + "_ZERO", field, repr(item.get(field)), "policy parameter is explicitly zero", 2)
    for row in pairs:
        if row.get("ItemActive") and status(row.get("MinimumInventory")) in {"MISSING", "ZERO"} and positive(row.get("OnHand")):
            rows.append({"ItemCode": row.get("ItemCode"), "Warehouse": row.get("Warehouse"), "AnomalyType": "WAREHOUSE_STOCK_WITHOUT_MINIMUM",
                         "Field": "OITW.MinStock", "Classification": status(row.get("MinimumInventory")), "Evidence": f"OnHand={row.get('OnHand')}",
                         "PotentialMRPImpact": "warehouse stock exists without positive local minimum", "Severity": 2, "Tier": "UNKNOWN"})
    rows.sort(key=lambda x: (-int(x.get("Severity", 0)), str(x.get("ItemCode")), str(x.get("Warehouse"))) )
    return rows


def representative_cases(items: list[dict[str, Any]], pairs: list[dict[str, Any]], bom: dict[str, dict[str, Any]], forecasts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_item_wh: dict[str, dict[str, Any]] = {}
    for row in pairs:
        by_item_wh.setdefault(str(row.get("ItemCode")), row)
    selected: list[dict[str, Any]] = []
    groups = [
        ("BOM_MAKE", lambda x: x.get("BOMExists") and x.get("ProcurementMethod") == "MAKE"),
        ("BUY", lambda x: x.get("ProcurementMethod") == "BUY"),
        ("NONZERO_LEAD_TIME", lambda x: positive(x.get("LeadTime"))),
        ("FORECAST", lambda x: x.get("ForecastExists")),
        ("HIGH_ACTIVITY", lambda x: sum(int(x.get(k, 0) or 0) for k in ("RecentSalesCount", "RecentPurchaseCount", "RecentProductionCount")) > 100),
    ]
    seen: set[tuple[str, str | None]] = set()
    for basis, predicate in groups:
        for item in sorted(items, key=lambda x: str(x.get("ItemCode"))):
            if not item.get("ItemActive") or not predicate(item):
                continue
            pair = by_item_wh.get(str(item.get("ItemCode")))
            key = (str(item.get("ItemCode")), pair.get("Warehouse") if pair else None)
            if key in seen:
                continue
            seen.add(key)
            selected.append({"ItemCode": item.get("ItemCode"), "ItemName": item.get("ItemName"), "Warehouse": pair.get("Warehouse") if pair else None,
                             "PlanningMethod": item.get("PlanningMethod"), "PlanningMethodRaw": item.get("PlanningMethodRaw"),
                             "ProcurementMethod": item.get("ProcurementMethod"), "ProcurementMethodRaw": item.get("ProcurementMethodRaw"),
                             "LeadTime": item.get("LeadTime"), "Min": pair.get("MinimumInventory") if pair else item.get("MinimumInventory"),
                             "Max": pair.get("MaximumInventory") if pair else item.get("MaximumInventory"), "MOQ": item.get("MinimumOrderQty"),
                             "Multiple": item.get("OrderMultiple"), "PreferredVendor": item.get("PreferredVendor"),
                             "BOM": item.get("BOMExists"), "Forecast": item.get("ForecastExists"), "SelectionBasis": basis,
                             "Observation": "configuration-only case; no operational correctness claim"})
            if len([x for x in selected if x["SelectionBasis"] == basis]) >= 4:
                break
    return selected[:20]


def comparison_matrix(pairs: list[dict[str, Any]], bom: dict[str, dict[str, Any]], forecast_pairs: set[tuple[str, str]]) -> list[dict[str, Any]]:
    out = []
    for row in pairs:
        item = str(row.get("ItemCode") or "")
        wh = str(row.get("Warehouse") or "")
        out.append({"ItemCode": row.get("ItemCode"), "Warehouse": row.get("Warehouse"), "SAP_PlanningMethod": row.get("PlanningMethodRaw"),
                    "SAP_ProcurementMethod": row.get("ProcurementMethodRaw"), "SAP_LeadTime": row.get("LeadTime"), "SAP_MinStock": row.get("MinimumInventory"),
                    "SAP_MaxStock": row.get("MaximumInventory"), "SAP_SafetyStock": None, "SAP_ReorderPoint": row.get("SafetyStockProxy"), "SAP_MOQ": row.get("MinimumOrderQty"),
                    "SAP_Multiple": row.get("OrderMultiple"), "SAP_OrderInterval": row.get("OrderInterval"), "SAP_PreferredVendor": row.get("PreferredVendor"), "SAP_BOM": item in bom,
                    "SAP_Forecast": (item, wh) in forecast_pairs, **{x: None for x in COMPARISON_COLUMNS if x.startswith("REAL_") or x in {"GapType", "GapMagnitude", "MRPImpact"}}})
    return out


def add_metadata(rows: list[dict[str, Any]], generated_at: str, tables: list[str]) -> list[dict[str, Any]]:
    encoded = ",".join(tables)
    return [{"generated_at": generated_at, "source_system": "SAP_BUSINESS_ONE_HANA", "source_tables": encoded,
             "query_version": VERSION, "read_only": True, **row} for row in rows]


def write_parquet(name: str, rows: list[dict[str, Any]], run_root: Path, generated_at: str, tables: list[str], columns: list[str] | None = None) -> dict[str, Any]:
    import duckdb
    import pandas as pd
    path = run_root / f"{name}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    enriched = add_metadata(rows, generated_at, tables)
    if not enriched:
        fields = ["generated_at", "source_system", "source_tables", "query_version", "read_only"] + (columns or [])
        frame = pd.DataFrame(columns=fields)
    else:
        frame = pd.DataFrame(enriched)
    db = duckdb.connect()
    try:
        db.register("audit_frame", frame)
        db.execute(f"COPY audit_frame TO '{str(path).replace("'", "''")}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        db.close()
    return {"dataset": name, "path": str(path), "row_count": len(rows), "source_tables": tables,
            "query_version": VERSION, "read_only": True}


def report_markdown(result: dict[str, Any]) -> str:
    c = result["coverage"]
    def pct(x: dict[str, Any]) -> str:
        return f"{x['configured']:,} / {x['universe']:,} ({x['coverage_pct']:.1f}%)"
    lines = ["# TELCHI — MRP CONFIGURATION AUDIT V1", "", f"## A. Gate", f"**{result['gate']}**", f"- MRP CONFIGURATION MATURITY: **{result['maturity']}** (clasificador reproducible sobre cobertura y consistencia aparente)", "", "## B. SAP safety", "`SAP_WRITE_COUNT=0` · SELECT-only · no MRP executed", "", "## C. Universo analizado"]
    for k, v in result["universe"].items(): lines.append(f"- {k}: **{v:,}**" if isinstance(v, int) else f"- {k}: **{v}**")
    lines += ["", "## D. Cobertura MRP", "", "| Parámetro | Configurados | Universo | % |", "|---|---:|---:|---:|"]
    for key, val in c["item"] .items():
        lines.append(f"| {key} | {val['configured']:,} | {val['universe']:,} | {val['coverage_pct']:.1f}% |")
    lines += ["", "## E. Principales anomalías"]
    for i, row in enumerate(result["anomaly_summary"][:20], 1):
        lines.append(f"{i}. **{row['AnomalyType']}** — {row['Count']:,} casos; ejemplo `{row['ExampleItem']}`{('/' + str(row['ExampleWarehouse'])) if row.get('ExampleWarehouse') else ''} → {row['PotentialMRPImpact']}")
    lines += ["", "## F. Forecast", f"- definitions: **{result['forecast']['definitions']:,}**", f"- rows: **{result['forecast']['rows']:,}**", f"- SKUs: **{result['forecast']['skus']:,}**", f"- warehouses: **{result['forecast']['warehouses']:,}**", f"- coverage active items: **{result['forecast']['active_item_coverage_pct']:.1f}%**", "- ActiveStatus: `NOT_EXPOSED` en OFCT/FCT1; no se infiere activo/inactivo por fecha.", "", "## G. BOM / Procurement", f"- productos con BOM: **{result['bom']['items_with_bom']:,}**", f"- BOM + MAKE: **{result['bom']['bom_make']:,}**", f"- BOM + no MAKE: **{result['bom']['bom_non_make']:,}**", f"- MAKE sin BOM: **{result['bom']['make_without_bom']:,}**", f"- inconsistencias explícitas BOM/procurement: **{result['bom']['inconsistencies']:,}**", "", "## H. Lead time SAP", f"- configurados: **{c['item']['LeadTime']['configured']:,}**", f"- cero: **{result['lead_time']['zero']:,}**", f"- ausentes: **{result['lead_time']['missing']:,}**", f"- distribución: `{json.dumps(result['lead_time']['distribution'], ensure_ascii=False)}`", "", "## I. Stock policy SAP"]
    for key in ("MinimumInventoryWarehouse", "MaximumInventoryWarehouse", "MinimumOrderQtyWarehouse", "OrderMultiple", "OrderInterval", "PlanningIncludedWarehouse"):
        if key in c["warehouse"]: lines.append(f"- {key}: {pct(c['warehouse'][key])}")
    lines += ["", "## J. Casos representativos", "", "| ItemCode | ItemName | Warehouse | Planning | Procurement | LeadTime | Min | Max | MOQ | Multiple | Vendor | BOM | Forecast | Base |", "|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|"]
    for x in result["representative_cases"][:15]: lines.append(f"| {x.get('ItemCode')} | {x.get('ItemName','')} | {x.get('Warehouse','')} | {x.get('PlanningMethod')} | {x.get('ProcurementMethod')} | {x.get('LeadTime')} | {x.get('Min')} | {x.get('Max')} | {x.get('MOQ')} | {x.get('Multiple')} | {x.get('PreferredVendor')} | {x.get('BOM')} | {x.get('Forecast')} | {x.get('SelectionBasis')} |")
    lines += ["", "## K. Preparación siguiente gate", "**READY** para cruzar configuración SAP con lead time real; la matriz contiene `REAL_*` nulos por diseño.", "", "## L. Próximo gate recomendado", "`TELCHI_MRP_LEAD_TIME_GAP_V1`", "", "## Limitaciones", "- `SafetyStock` no se observó como campo estándar físico en OITM/OITW; se preserva `ReorderPnt` como proxy etiquetado, no como safety stock confirmado.", "- La cobertura warehouse se calcula sobre las filas físicas OITW; no se infiere una fila para cada combinación matemática artículo×almacén.", "- Los casos y tiers son selección reproducible de configuración y actividad agregada de 12 meses; no declaran calidad operativa ni repiten el diagnóstico real.", "- Forecast se reporta solo cuando OFCT/FCT1 tienen filas y joins identificables.", "", "## Artefactos", f"- Parquet root: `{result['run_root']}`", f"- Manifest: `{result['manifest_path']}`", f"- Runner: `{Path(__file__)}`", "- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`."]
    return "\n".join(lines) + "\n"


def coverage(values: list[Any], universe: int) -> dict[str, Any]:
    configured = sum(1 for value in values if has_value(value))
    return {"configured": configured, "universe": universe, "coverage_pct": round(100 * configured / universe, 2) if universe else 0.0}


def parameter_quality(parameter: str, values: list[Any], source_table: str, source_field: str, level: str) -> dict[str, Any]:
    present = [value for value in values if has_value(value)]
    counts = Counter(str(value) for value in present)
    mode_value, mode_count = counts.most_common(1)[0] if counts else (None, 0)
    zero_count = sum(1 for value in present if isinstance(value, (int, float, Decimal)) and float(value) == 0)
    if not present:
        quality = "NOT_APPLICABLE" if parameter == "SafetyStock" else "MISSING"
    elif mode_count / len(present) >= 0.90:
        quality = "DEFAULT_LIKE"
    elif zero_count == len(present):
        quality = "ZERO"
    else:
        quality = "CONFIGURED"
    return {"Parameter": parameter, "Level": level, "SourceTable": source_table, "SourceField": source_field,
            "Quality": quality, "Universe": len(values), "Configured": len(present), "ZeroCount": zero_count,
            "ModeValue": mode_value, "ModeSharePct": round(100 * mode_count / len(present), 2) if present else 0.0}


def run(run_root: Path = DEFAULT_RUN_ROOT, report_path: Path = DEFAULT_REPORT) -> dict[str, Any]:
    generated_at = datetime.now().astimezone().isoformat()
    conn, raw_cur = connect()
    cur = ReadOnlyConnection(conn).cursor()
    try:
        cur.execute('SELECT CURRENT_TIMESTAMP, CURRENT_USER, CURRENT_SCHEMA FROM DUMMY')
        preflight_row = cur.fetchone()
        available, catalog_rows = catalog(cur, SCHEMA)
        items, item_fields = scalar_table(cur, SCHEMA, "OITM", ITEM_FIELDS, available)
        pairs_raw, wh_fields = scalar_table(cur, SCHEMA, "OITW", WAREHOUSE_FIELDS, available)
        warehouses, _ = scalar_table(cur, SCHEMA, "OWHS", WAREHOUSE_MASTER_FIELDS, available)
        groups, _ = scalar_table(cur, SCHEMA, "OITB", GROUP_FIELDS, available)
        vendors, _ = scalar_table(cur, SCHEMA, "OCRD", {"PreferredVendor": ("CardCode",), "VendorName": ("CardName",), "CardType": ("CardType",)}, available)
        vendors = [x for x in vendors if str(x.get("CardType") or "").upper() == "S"]
        global_rows, global_fields = scalar_table(cur, SCHEMA, "OADM", GLOBAL_FIELDS, available)
        bom_headers, _ = scalar_table(cur, SCHEMA, "OITT", BOM_HEADER_FIELDS, available)
        bom_lines, _ = scalar_table(cur, SCHEMA, "ITT1", BOM_LINE_FIELDS, available)
        fc_headers, _ = scalar_table(cur, SCHEMA, "OFCT", FORECAST_HEADER_FIELDS, available)
        fc_lines, _ = scalar_table(cur, SCHEMA, "FCT1", FORECAST_LINE_FIELDS, available)
        activity_rows = activity(cur, available)
        bom_rows, bom_by_item = make_bom(bom_headers, bom_lines)
        forecasts = make_forecast(fc_headers, fc_lines)
        forecast_items = {str(x.get("ItemCode")) for x in forecasts if x.get("ItemCode")}
        forecast_pairs = {(str(x.get("ItemCode")), str(x.get("Warehouse"))) for x in forecasts if x.get("ItemCode") and x.get("Warehouse")}
        enrich_items(items, activity_rows, bom_by_item, forecast_items)
        pairs = warehouse_pairs(items, pairs_raw)
        warehouse_by_code = {str(x.get("Warehouse")): x for x in warehouses}
        for pair in pairs:
            master = warehouse_by_code.get(str(pair.get("Warehouse")), {})
            pair.update({"WarehouseName": master.get("WarehouseName"), "PlanningIncludedFlag": master.get("PlanningIncludedFlag"), "WarehouseInactiveFlag": master.get("InactiveFlag")})
        anomalies = anomaly_rows(items, pairs, bom_by_item)
        cases = representative_cases(items, pairs, bom_by_item, forecasts)
        matrix = comparison_matrix(pairs, bom_by_item, forecast_pairs)
        field_catalog_rows: list[dict[str, Any]] = []
        for table, mapping in (("OITM", ITEM_FIELDS), ("OITW", WAREHOUSE_FIELDS), ("OITB", GROUP_FIELDS), ("OWHS", WAREHOUSE_MASTER_FIELDS), ("OITT", BOM_HEADER_FIELDS), ("ITT1", BOM_LINE_FIELDS), ("OFCT", FORECAST_HEADER_FIELDS), ("FCT1", FORECAST_LINE_FIELDS), ("OADM", GLOBAL_FIELDS)):
            physical = {x.upper(): x for x in available.get(table, [])}
            for logical, candidates in mapping.items():
                source = next((physical[x.upper()] for x in candidates if x.upper() in physical), None)
                field_catalog_rows.append({"LogicalField": logical, "Level": "ITEM" if table == "OITM" else "ITEM_WAREHOUSE" if table == "OITW" else "GLOBAL" if table == "OADM" else "SOURCE_DETAIL", "SourceTable": table, "SourceField": source, "Available": bool(source), "FieldStatus": "CONFIRMED" if source else "NOT_FOUND", "Notes": "ReorderPnt is a reorder-point proxy; not confirmed safety stock." if logical == "SafetyStock" else ""})
        quality_rows = [parameter_quality("PlanningMethod", [x.get("PlanningMethodRaw") for x in items], "OITM", "PlaningSys", "ITEM"),
                        parameter_quality("ProcurementMethod", [x.get("ProcurementMethodRaw") for x in items], "OITM", "PrcrmntMtd", "ITEM"),
                        parameter_quality("LeadTime", [x.get("LeadTime") for x in items], "OITM", "LeadTime", "ITEM"),
                        parameter_quality("MinimumInventory", [x.get("MinimumInventory") for x in items], "OITM", "MinLevel", "ITEM"),
                        parameter_quality("MaximumInventory", [x.get("MaximumInventory") for x in items], "OITM", "MaxLevel", "ITEM"),
                        parameter_quality("OrderMultiple", [x.get("OrderMultiple") for x in items], "OITM", "OrdrMulti", "ITEM"),
                        parameter_quality("MinimumOrderQty", [x.get("MinimumOrderQty") for x in items], "OITM", "MinOrdrQty", "ITEM"),
                        parameter_quality("PreferredVendor", [x.get("PreferredVendor") for x in items], "OITM", "CardCode", "ITEM"),
                        parameter_quality("SafetyStock", [None for _ in items], "SAP_STANDARD", "NOT_OBSERVED", "ITEM")]

        active_items = [x for x in items if x.get("ItemActive")]
        item_universe = len(items)
        pair_universe = len(pairs)
        item_coverage = {
            "Planning Method": coverage([x.get("PlanningMethodRaw") for x in items], item_universe),
            "Procurement Method": coverage([x.get("ProcurementMethodRaw") for x in items], item_universe),
            "LeadTime": coverage([x.get("LeadTime") for x in items], item_universe),
            "SafetyStock": coverage([None for _ in items], item_universe),
            "ReorderPointProxy": coverage([x.get("SafetyStock") for x in items], item_universe),
            "MinimumInventory": coverage([x.get("MinimumInventory") for x in items], item_universe),
            "MaximumInventory": coverage([x.get("MaximumInventory") for x in items], item_universe),
            "OrderMultiple": coverage([x.get("OrderMultiple") for x in items], item_universe),
            "MinimumOrderQty": coverage([x.get("MinimumOrderQty") for x in items], item_universe),
            "PreferredVendor": coverage([x.get("PreferredVendor") for x in items], item_universe),
            "BOM": coverage([x.get("BOMExists") and "Y" or None for x in items], item_universe),
            "Forecast": coverage([x.get("ForecastExists") and "Y" or None for x in items], item_universe),
        }
        warehouse_coverage = {
            "MinimumInventoryWarehouse": coverage([x.get("MinimumInventory") for x in pairs], pair_universe),
            "MaximumInventoryWarehouse": coverage([x.get("MaximumInventory") for x in pairs], pair_universe),
            "MinimumOrderQtyWarehouse": coverage([x.get("MinimumOrderQty") for x in pairs], pair_universe),
        }
        warehouse_coverage.update({"OrderMultiple": item_coverage["OrderMultiple"], "OrderInterval": coverage([x.get("OrderInterval") for x in items], item_universe),
                                   "PlanningIncludedWarehouse": coverage([x.get("PlanningIncludedFlag") for x in pairs], pair_universe)})
        forecast_active = {str(x.get("ItemCode")) for x in forecasts if x.get("ItemCode")} & {str(x.get("ItemCode")) for x in active_items}
        inconsistent = sum(1 for x in anomalies if "INCONSISTENT" in str(x.get("Classification")))
        anomaly_summary = []
        for anomaly_type, group in __import__("itertools").groupby(sorted(anomalies, key=lambda x: str(x.get("AnomalyType"))), key=lambda x: x.get("AnomalyType")):
            group_rows = list(group)
            first = group_rows[0]
            anomaly_summary.append({"AnomalyType": anomaly_type, "Count": len(group_rows), "ExampleItem": first.get("ItemCode"), "ExampleWarehouse": first.get("Warehouse"), "PotentialMRPImpact": first.get("PotentialMRPImpact")})
        anomaly_summary.sort(key=lambda x: (-x["Count"], str(x["AnomalyType"])))
        lead_values = [x.get("LeadTime") for x in items]
        lead_dist = Counter("MISSING" if not has_value(x) else "ZERO" if not positive(x) else "POSITIVE" for x in lead_values)
        universe = {"items": item_universe, "active_items": len(active_items), "mrp_items": sum(1 for x in items if x.get("PlanningMethod") == "MRP"), "make_items": sum(1 for x in items if x.get("ProcurementMethod") == "MAKE"), "warehouses": len({x.get("Warehouse") for x in pairs if x.get("Warehouse")}), "item_warehouse": pair_universe, "BOM": len(bom_rows), "forecasts": len(fc_headers)}
        tiers = Counter(tier(x) for x in items)
        maturity = "MEDIUM"
        # Keep the rule explicit: confirmed safety stock absence, <75% lead time,
        # or MAKE items without BOM is enough for LOW.
        if item_coverage["SafetyStock"]["configured"] == 0 or item_coverage["LeadTime"]["coverage_pct"] < 75 or sum(1 for x in items if x.get("ProcurementMethod") == "MAKE" and not x.get("BOMExists")) > 0:
            maturity = "LOW"
        datasets: list[dict[str, Any]] = []
        write = lambda name, rows, tables, columns=None: datasets.append(write_parquet(name, rows, run_root, generated_at, tables, columns))
        write("mrp_schema_discovery", catalog_rows, ["SYS.TABLES", "SYS.VIEWS", "SYS.TABLE_COLUMNS"])
        write("mrp_field_catalog", field_catalog_rows, ["SYS.TABLE_COLUMNS", "OITM", "OITW", "OITB", "OWHS", "OITT", "ITT1", "OFCT", "FCT1", "OADM"])
        write("mrp_parameter_quality", quality_rows, ["OITM", "OITW", "OADM"])
        write("mrp_item_configuration", items, ["OITM", "OITB", "OCRD", "OITT", "OFCT", "FCT1", "OINV", "INV1", "OPOR", "POR1", "OWOR", "OINM"])
        write("mrp_item_warehouse_configuration", pairs, ["OITM", "OITW", "OWHS"])
        write("mrp_group_defaults", groups, ["OITB"])
        write("mrp_vendor_reference", vendors, ["OCRD"])
        write("mrp_global_configuration", global_rows, ["OADM"])
        write("mrp_bom_inventory", bom_rows + [{**x, "RecordType": "COMPONENT", **{k: v for k, v in line.items() if k not in x}} for line in bom_lines for x in []], ["OITT", "ITT1"])
        write("mrp_bom_lines", bom_lines, ["ITT1"])
        write("mrp_forecast", forecasts, ["OFCT", "FCT1"], list(FORECAST_HEADER_FIELDS) + list(FORECAST_LINE_FIELDS))
        write("mrp_coverage", [{"Level": "ITEM", "Parameter": k, **v} for k, v in item_coverage.items()] + [{"Level": "ITEM_WAREHOUSE", "Parameter": k, **v} for k, v in warehouse_coverage.items()], ["OITM", "OITW", "OITT", "OFCT", "FCT1"])
        write("mrp_anomalies", anomalies, ["OITM", "OITW", "OITT", "ITT1"])
        write("mrp_representative_cases", cases, ["OITM", "OITW", "OITT", "ITT1", "OFCT", "FCT1"])
        write("mrp_future_comparison_matrix", matrix, ["OITM", "OITW", "OITT", "ITT1", "OFCT", "FCT1"], COMPARISON_COLUMNS)
        manifest = {"gate": GATE, "generated_at": generated_at, "source_system": "SAP_BUSINESS_ONE_HANA", "source_schema": SCHEMA,
                    "read_only": True, "SAP_WRITE_COUNT": 0, "query_version": VERSION, "run_root": str(run_root), "datasets": datasets,
                    "field_lineage": {"OITM": item_fields, "OITW": wh_fields, "OADM": global_fields, "OITB": GROUP_FIELDS, "OWHS": WAREHOUSE_MASTER_FIELDS, "OITT": BOM_HEADER_FIELDS, "ITT1": BOM_LINE_FIELDS, "OFCT": FORECAST_HEADER_FIELDS, "FCT1": FORECAST_LINE_FIELDS}, "preflight": {"server_timestamp": clean(preflight_row[0]), "current_user": preflight_row[1], "current_schema": preflight_row[2]},
                    "raw_value_distributions": {"planning_method": dict(Counter(str(x.get("PlanningMethodRaw")) for x in items)), "procurement_method": dict(Counter(str(x.get("ProcurementMethodRaw")) for x in items)), "BOM_type": dict(Counter(str(x.get("BOMTypeRaw")) for x in bom_rows))},
                    "tier_counts": dict(tiers), "maturity": maturity, "anomaly_summary": anomaly_summary}
        manifest_path = run_root / "manifest.json"
        run_root.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        result = {"gate": GATE + "_PASS", "sap_write_count": 0, "run_root": str(run_root), "manifest_path": str(manifest_path), "universe": universe,
                  "coverage": {"item": item_coverage, "warehouse": warehouse_coverage}, "forecast": {"definitions": len(fc_headers), "rows": len(forecasts), "skus": len(forecast_items), "warehouses": len({x.get("Warehouse") for x in forecasts if x.get("Warehouse")}), "active_item_coverage_pct": round(100 * len(forecast_active) / len(active_items), 2) if active_items else 0.0},
                  "bom": {"items_with_bom": len(bom_rows), "lines": len(bom_lines), "inconsistencies": inconsistent, "bom_make": sum(1 for x in items if x.get("BOMExists") and x.get("ProcurementMethod") == "MAKE"), "bom_non_make": sum(1 for x in items if x.get("BOMExists") and x.get("ProcurementMethod") != "MAKE"), "make_without_bom": sum(1 for x in items if x.get("ProcurementMethod") == "MAKE" and not x.get("BOMExists"))}, "lead_time": {"configured": lead_dist.get("POSITIVE", 0) + lead_dist.get("ZERO", 0), "zero": lead_dist.get("ZERO", 0), "missing": lead_dist.get("MISSING", 0), "distribution": dict(lead_dist)},
                  "anomalies": anomalies, "anomaly_summary": anomaly_summary, "representative_cases": cases, "tiers": dict(tiers), "maturity": maturity, "datasets": datasets, "field_lineage": manifest["field_lineage"], "raw_value_distributions": manifest["raw_value_distributions"]}
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_markdown({**result, "manifest_path": str(manifest_path)}), encoding="utf-8")
        manifest["report_path"] = str(report_path)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return result
    finally:
        cur.close()
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    try:
        result = run(args.output_root, args.report)
    except Exception as exc:
        print(f"{GATE}_DEGRADED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in result.items() if k not in {"anomalies", "representative_cases", "datasets"}}, ensure_ascii=False, indent=2, default=str))
    print(f"SAP_WRITE_COUNT={result['sap_write_count']}")
    print(result["gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
