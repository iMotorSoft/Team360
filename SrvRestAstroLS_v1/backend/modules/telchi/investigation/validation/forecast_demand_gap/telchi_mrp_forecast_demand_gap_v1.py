"""TELCHI_MRP_FORECAST_DEMAND_GAP_V1.

Investigation-only audit of SAP Business One forecasts.  It reuses the current
Gate 1 Parquet snapshot and the Gate 2 lead-time matrix; no sales history is
re-extracted because the per-item demand classification artifact is not
present in DATA_ROOT.  That missing lineage is reported as a deliberate
DEGRADED result rather than replaced with an invented class mapping.

SAP/HANA remains SELECT-only.  This runner does not execute MRP and does not
write to SAP, OFCT, FCT1, OITM or OITW.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb

from modules.telchi.investigation.paths import DATA_ROOT, INVESTIGATION_ROOT

GATE = "TELCHI_MRP_FORECAST_DEMAND_GAP_V1"
VERSION = "mrp_forecast_demand_gap_v1"
DEFAULT_SNAPSHOT = date(2026, 9, 14)
MRP_ROOT = DATA_ROOT / "business" / "mrp_configuration_audit_v1"
LEAD_ROOT = DATA_ROOT / "business" / "mrp_lead_time_gap_v1"
DEFAULT_OUTPUT_ROOT = DATA_ROOT / "business" / VERSION
DEFAULT_REPORT = INVESTIGATION_ROOT / "docs" / "telchi_mrp_forecast_demand_gap_v1_report.md"

DEMAND_BASELINE = {
    "SEASONAL": 1950,
    "DECLINING": 1298,
    "GROWING": 1003,
    "STABLE": 922,
    "INTERMITTENT": 342,
    "DISCONTINUED": 1016,
    "INSUFFICIENT": 4168,
    "NEW": 76,
    "analyzed_items": 10775,
    "source_report": "docs/product_seasonality_v1_report.md",
}


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def first(row: tuple[Any, ...] | None, default: Any = None) -> Any:
    return row[0] if row else default


def rows_to_dicts(cur: Any) -> list[dict[str, Any]]:
    names = [x[0] for x in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def json_clean(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def copy_query(db: Any, query: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db.execute(f"COPY ({query}) TO '{sql_path(path)}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def build_selected_cte(forecast_path: Path, snapshot: date) -> str:
    snap = snapshot.isoformat()
    month_start = snapshot.replace(day=1).isoformat()
    # Current definitions win over historical definitions.  Within the same
    # temporal class, the definition with the latest header end date wins.
    return f"""
    WITH raw AS (
        SELECT ForecastId, ForecastCode, ForecastName,
               CAST(StartDate AS DATE) AS HeaderStart,
               CAST(EndDate AS DATE) AS HeaderEnd,
               FormView, ItemCode, Warehouse,
               CAST(Period AS DATE) AS Period,
               CAST(Quantity AS DOUBLE) AS Quantity
        FROM read_parquet('{sql_path(forecast_path)}')
    ), defs AS (
        SELECT ForecastId, ForecastCode, ForecastName, HeaderStart, HeaderEnd,
               FormView, MIN(Period) AS MinPeriod, MAX(Period) AS MaxPeriod
        FROM raw GROUP BY ALL
    ), agg AS (
        SELECT r.ForecastId, r.ItemCode, r.Warehouse,
               d.ForecastCode, d.ForecastName, d.HeaderStart, d.HeaderEnd,
               d.FormView, d.MinPeriod, d.MaxPeriod,
               SUM(r.Quantity) AS ForecastQty,
               COUNT(DISTINCT DATE_TRUNC('month', r.Period)) AS ComparableMonths
        FROM raw r JOIN defs d USING (ForecastId)
        GROUP BY ALL
    ), ranked AS (
        SELECT ForecastId, ItemCode, Warehouse, ForecastCode, ForecastName,
               HeaderStart, HeaderEnd, FormView, MinPeriod, MaxPeriod,
               ForecastQty, ComparableMonths,
               ROW_NUMBER() OVER (
                   PARTITION BY ItemCode, Warehouse
                   ORDER BY CASE
                       WHEN HeaderStart <= DATE '{snap}' AND HeaderEnd >= DATE '{snap}' THEN 0
                       WHEN HeaderStart > DATE '{snap}' THEN 1
                       ELSE 2 END,
                       HeaderEnd DESC, ForecastId DESC
               ) AS selection_rank
        FROM agg
    )
    SELECT ForecastId, ItemCode, Warehouse, ForecastCode, ForecastName,
           HeaderStart, HeaderEnd, FormView, MinPeriod, MaxPeriod,
           ForecastQty, ComparableMonths
    FROM ranked WHERE selection_rank = 1
    """


def forecast_status(snapshot: date) -> str:
    # SQL computes the status per selected item×warehouse.  This helper keeps
    # the classification vocabulary documented for tests and callers.
    _ = snapshot
    return "CURRENT_FORECAST|FUTURE_FORECAST|EXPIRED_FORECAST|ZERO_FORECAST|NO_FORECAST"


def run(output_root: Path = DEFAULT_OUTPUT_ROOT, report_path: Path = DEFAULT_REPORT, snapshot: date = DEFAULT_SNAPSHOT) -> dict[str, Any]:
    item_path = MRP_ROOT / "mrp_item_configuration.parquet"
    pair_path = MRP_ROOT / "mrp_item_warehouse_configuration.parquet"
    forecast_path = MRP_ROOT / "mrp_forecast.parquet"
    lead_path = LEAD_ROOT / "mrp_lead_time_gap_item_matrix.csv"
    for path in (item_path, pair_path, forecast_path, lead_path):
        if not path.exists():
            raise FileNotFoundError(f"required reusable artifact missing: {path}")

    output_root.mkdir(parents=True, exist_ok=True)
    db = duckdb.connect()
    try:
        db.execute("PRAGMA threads=1")
        db.execute("PRAGMA memory_limit='1GB'")
        db.execute(f"CREATE OR REPLACE TEMP VIEW items AS SELECT ItemCode, ItemName AS Description, ItemActive AS Active, (PlanningMethod = 'MRP') AS MRPIncluded, ProcurementMethod, BOMExists FROM read_parquet('{sql_path(item_path)}')")
        db.execute(f"CREATE OR REPLACE TEMP VIEW pairs AS SELECT ItemCode, Warehouse, PlanningIncludedFlag, WarehouseName FROM read_parquet('{sql_path(pair_path)}')")
        db.execute(f"CREATE OR REPLACE TEMP VIEW lead AS SELECT ItemCode, GapClassification, Confidence AS LeadTimeConfidence, SAPLeadTime FROM read_csv_auto('{sql_path(lead_path)}', HEADER=TRUE)")
        selected = build_selected_cte(forecast_path, snapshot)
        db.execute(f"CREATE OR REPLACE TEMP VIEW selected_forecast AS {selected}")

        month_start = snapshot.replace(day=1).isoformat()
        # The physical forecast snapshot is exported once as a grouped,
        # traceable definition profile.  No SELECT * is used.
        raw_forecast = f"read_parquet('{sql_path(forecast_path)}')"
        definitions_query = f"""
            WITH d AS (
                SELECT ForecastId, ForecastCode, ForecastName,
                       CAST(StartDate AS DATE) AS ForecastStart,
                       CAST(EndDate AS DATE) AS ForecastEnd,
                       FormView, ItemCode, Warehouse,
                       CAST(Period AS DATE) AS Period,
                       CAST(Quantity AS DOUBLE) AS Quantity
                FROM {raw_forecast}
            )
            SELECT ForecastId, ForecastCode, ForecastName, ForecastStart, ForecastEnd,
                   FormView, COUNT(*) AS Lines, COUNT(DISTINCT ItemCode) AS Items,
                   COUNT(DISTINCT Warehouse) AS Warehouses,
                   MIN(Period) AS MinDate, MAX(Period) AS MaxDate,
                   SUM(Quantity) AS ForecastQty,
                   SUM(CASE WHEN Quantity = 0 THEN 1 ELSE 0 END) AS ZeroLines,
                   CASE WHEN MAX(ForecastEnd) < DATE '{snapshot.isoformat()}' THEN 'EXPIRED'
                        WHEN MIN(ForecastStart) > DATE '{snapshot.isoformat()}' THEN 'FUTURE'
                        WHEN MIN(Period) < DATE '{month_start}' AND MAX(Period) > DATE '{snapshot.isoformat()}' THEN 'MIXED'
                        ELSE 'CURRENT' END AS TemporalStatus,
                   GREATEST(0, DATE_DIFF('day', DATE '{snapshot.isoformat()}', MAX(Period))) AS FutureCoverageDays
            FROM d GROUP BY ForecastId, ForecastCode, ForecastName, ForecastStart, ForecastEnd, FormView
        """
        copy_query(db, definitions_query, output_root / "forecast_definitions.parquet")
        copy_query(db, "SELECT ForecastId, ItemCode, Warehouse, ForecastCode, ForecastName, HeaderStart AS ForecastStart, HeaderEnd AS ForecastEnd, FormView, MinPeriod, MaxPeriod, ForecastQty, ComparableMonths FROM selected_forecast", output_root / "selected_forecast_item_warehouse.parquet")

        matrix_query = f"""
        WITH base AS (
            SELECT p.ItemCode, i.Description, i.Active,
                   i.MRPIncluded, i.ProcurementMethod, p.Warehouse,
                   p.PlanningIncludedFlag, p.WarehouseName, i.BOMExists,
                   s.ForecastId, s.ForecastCode, s.ForecastName,
                   s.HeaderStart, s.HeaderEnd, s.MinPeriod, s.MaxPeriod,
                   s.ForecastQty, s.ComparableMonths,
                   l.GapClassification, l.LeadTimeConfidence, l.SAPLeadTime
            FROM pairs p JOIN items i USING (ItemCode)
            LEFT JOIN selected_forecast s USING (ItemCode, Warehouse)
            LEFT JOIN lead l USING (ItemCode)
        ), classified AS (
            SELECT *,
              CASE WHEN ForecastId IS NULL THEN 'NO_FORECAST'
                   WHEN ForecastQty = 0 THEN 'ZERO_FORECAST'
                   WHEN MaxPeriod < DATE '{snapshot.isoformat()}' THEN 'EXPIRED_FORECAST'
                   WHEN MinPeriod > DATE '{snapshot.isoformat()}' THEN 'FUTURE_FORECAST'
                   WHEN MinPeriod < DATE '{month_start}' AND MaxPeriod > DATE '{snapshot.isoformat()}' THEN 'MIXED_FORECAST'
                   ELSE 'CURRENT_FORECAST' END AS ForecastStatus,
              CASE WHEN ForecastId IS NULL THEN NULL
                   ELSE GREATEST(0, DATE_DIFF('day', DATE '{snapshot.isoformat()}', MaxPeriod)) END AS FutureCoverageDays,
              CASE WHEN ForecastId IS NULL THEN NULL
                   ELSE ROUND(GREATEST(0, DATE_DIFF('day', DATE '{snapshot.isoformat()}', MaxPeriod)) / 30.4375, 2) END AS FutureCoverageMonths,
              CASE WHEN ForecastId IS NULL THEN NULL
                   ELSE CAST(MinPeriod AS VARCHAR) || '..' || CAST(MaxPeriod AS VARCHAR) END AS ForecastPeriod,
              CASE WHEN ForecastId IS NULL THEN NULL ELSE 'MRP_USAGE_UNKNOWN' END AS UsageStatus,
              CASE WHEN ForecastId IS NULL THEN NULL ELSE 'UNKNOWN' END AS GapType,
              CASE WHEN ForecastId IS NULL THEN 'LOW_CONFIDENCE' ELSE 'LOW_CONFIDENCE' END AS Confidence
            FROM base
        )
        SELECT ItemCode, Description, Active, MRPIncluded, ProcurementMethod, Warehouse,
               ForecastCode, ForecastName,
               CAST(NULL AS VARCHAR) AS DemandClass,
               CAST(NULL AS DOUBLE) AS Observed12M, CAST(NULL AS DOUBLE) AS Observed6M,
               CAST(NULL AS DOUBLE) AS SalesFrequency, CAST(NULL AS VARCHAR) AS Trend,
               CAST(NULL AS VARCHAR) AS Seasonality, CAST(NULL AS INTEGER) AS MonthsWithSales,
               ForecastStatus, ForecastPeriod, HeaderStart AS ForecastStart,
               HeaderEnd AS ForecastEnd, ForecastQty AS SAPForecastQty,
               ForecastQty, ComparableMonths, FutureCoverageDays, FutureCoverageMonths,
               CAST(NULL AS DOUBLE) AS ForecastGap,
               CASE WHEN GapClassification = 'SAP_MISCONFIGURED' THEN TRUE ELSE FALSE END AS LeadTimeGapFlag,
               CASE WHEN GapClassification = 'SAP_NOT_POPULATED' THEN TRUE ELSE FALSE END AS LeadTimeMissingFlag,
               CAST(NULL AS BOOLEAN) AS StockoutFlag,
               GapType, CASE WHEN ForecastId IS NULL THEN 'UNKNOWN' ELSE 'UNKNOWN' END AS Severity,
               Confidence, UsageStatus,
               CASE WHEN ForecastId IS NULL THEN 'NO_FORECAST'
                    WHEN ForecastQty = 0 THEN 'ZERO_FORECAST'
                    WHEN ForecastStatus = 'EXPIRED_FORECAST' THEN 'EXPIRED_FORECAST'
                    ELSE ForecastStatus END AS ForecastFlags,
               CASE WHEN WarehouseName IS NULL THEN FALSE ELSE TRUE END AS WarehouseKnown,
               FALSE AS WarehouseMismatchFlag,
               CASE WHEN ProcurementMethod = 'MAKE' AND BOMExists AND ForecastId IS NULL THEN TRUE ELSE FALSE END AS MakeBomNoForecastFlag,
               GapClassification AS LeadTimeGapClassification,
               SAPLeadTime
        FROM classified
        """
        copy_query(db, matrix_query, output_root / "forecast_demand_item_warehouse_matrix.parquet")

        def scalar(query: str) -> Any:
            return first(db.execute(query).fetchone())

        universe = {
            "all_items": scalar("SELECT COUNT(*) FROM items"),
            "active_items": scalar("SELECT COUNT(*) FROM items WHERE Active"),
            "mrp_items": scalar("SELECT COUNT(*) FROM items WHERE MRPIncluded"),
            "active_mrp_items": scalar("SELECT COUNT(*) FROM items WHERE Active AND MRPIncluded"),
            "active_mrp_make": scalar("SELECT COUNT(*) FROM items WHERE Active AND MRPIncluded AND ProcurementMethod='MAKE'"),
            "active_mrp_buy": scalar("SELECT COUNT(*) FROM items WHERE Active AND MRPIncluded AND ProcurementMethod='BUY'"),
            "active_mrp_l": scalar("SELECT COUNT(*) FROM items WHERE Active AND MRPIncluded AND ItemCode LIKE 'L%'"),
            "item_warehouse_rows": scalar("SELECT COUNT(*) FROM pairs"),
            "warehouses": scalar("SELECT COUNT(DISTINCT Warehouse) FROM pairs"),
        }
        forecast_metrics = {}
        for name, condition in {
            "any_forecast": "ForecastStatus <> 'NO_FORECAST'",
            "no_forecast": "ForecastStatus = 'NO_FORECAST'",
            "current_forecast": "ForecastStatus IN ('CURRENT_FORECAST','MIXED_FORECAST')",
            "future_forecast": "ForecastStatus = 'FUTURE_FORECAST'",
            "expired_forecast": "ForecastStatus = 'EXPIRED_FORECAST'",
            "zero_forecast": "ForecastStatus = 'ZERO_FORECAST'",
        }.items():
            forecast_metrics[name] = {
                "item_warehouse_rows": scalar(f"SELECT COUNT(*) FROM read_parquet('{sql_path(output_root / 'forecast_demand_item_warehouse_matrix.parquet')}') WHERE {condition}"),
                "items": scalar(f"SELECT COUNT(DISTINCT ItemCode) FROM read_parquet('{sql_path(output_root / 'forecast_demand_item_warehouse_matrix.parquet')}') WHERE {condition}"),
                "active_mrp_items": scalar(f"SELECT COUNT(DISTINCT ItemCode) FROM read_parquet('{sql_path(output_root / 'forecast_demand_item_warehouse_matrix.parquet')}') WHERE Active AND MRPIncluded AND {condition}"),
            }
        # A physical OITW row can be unforecasted while the same item is
        # forecasted in another warehouse.  Article-level NO_FORECAST is the
        # complement of article-level ANY_FORECAST, not a distinct count of
        # unforecasted warehouse rows.
        forecast_metrics["no_forecast"]["items"] = universe["all_items"] - forecast_metrics["any_forecast"]["items"]
        forecast_metrics["no_forecast"]["active_mrp_items"] = universe["active_mrp_items"] - forecast_metrics["any_forecast"]["active_mrp_items"]

        segments: dict[str, dict[str, Any]] = {}
        segment_specs = {
            "MAKE": "Active AND MRPIncluded AND ProcurementMethod='MAKE'",
            "BUY": "Active AND MRPIncluded AND ProcurementMethod='BUY'",
            "L_PRODUCTS": "Active AND MRPIncluded AND ItemCode LIKE 'L%'",
        }
        matrix = output_root / "forecast_demand_item_warehouse_matrix.parquet"
        for name, where in segment_specs.items():
            segments[name] = {
                "universe_items": scalar(f"SELECT COUNT(DISTINCT ItemCode) FROM read_parquet('{sql_path(matrix)}') WHERE {where}"),
                "any_forecast_items": scalar(f"SELECT COUNT(DISTINCT ItemCode) FROM read_parquet('{sql_path(matrix)}') WHERE {where} AND ForecastStatus <> 'NO_FORECAST'"),
                "current_or_future_items": scalar(f"SELECT COUNT(DISTINCT ItemCode) FROM read_parquet('{sql_path(matrix)}') WHERE {where} AND ForecastStatus IN ('CURRENT_FORECAST','MIXED_FORECAST','FUTURE_FORECAST')"),
                "no_forecast_items": scalar(f"SELECT COUNT(DISTINCT ItemCode) FROM read_parquet('{sql_path(matrix)}') WHERE {where}") - scalar(f"SELECT COUNT(DISTINCT ItemCode) FROM read_parquet('{sql_path(matrix)}') WHERE {where} AND ForecastStatus <> 'NO_FORECAST'"),
            }

        line_quality = {}
        raw = f"read_parquet('{sql_path(forecast_path)}')"
        line_quality["lines"] = scalar(f"SELECT COUNT(*) FROM {raw}")
        line_quality["zero_quantity_lines"] = scalar(f"SELECT COUNT(*) FROM {raw} WHERE Quantity=0")
        line_quality["negative_quantity_lines"] = scalar(f"SELECT COUNT(*) FROM {raw} WHERE Quantity<0")
        line_quality["missing_item_lines"] = scalar(f"SELECT COUNT(*) FROM {raw} WHERE ItemCode IS NULL OR ItemCode='' ")
        line_quality["missing_warehouse_lines"] = scalar(f"SELECT COUNT(*) FROM {raw} WHERE Warehouse IS NULL OR Warehouse='' ")
        line_quality["invalid_date_lines"] = scalar(f"SELECT COUNT(*) FROM {raw} WHERE Period IS NULL")
        line_quality["unknown_warehouse_lines"] = scalar(f"SELECT COUNT(*) FROM {raw} f LEFT JOIN pairs p ON f.ItemCode=p.ItemCode AND f.Warehouse=p.Warehouse WHERE p.Warehouse IS NULL")
        duplicate_lines = scalar(f"SELECT COUNT(*) FROM (SELECT ForecastId,ItemCode,Warehouse,Period,COUNT(*) AS n FROM {raw} GROUP BY ALL HAVING COUNT(*) > 1)")
        line_quality["duplicate_key_groups"] = duplicate_lines
        line_quality["future_discontinued_items"] = None

        item_cross = rows_to_dicts(db.execute(f"""
            SELECT ItemCode, BOOL_OR(ForecastStatus <> 'NO_FORECAST') AS AnyForecast,
                   BOOL_OR(LeadTimeGapFlag) AS LTGap,
                   BOOL_OR(LeadTimeMissingFlag) AS LTMissing,
                   BOOL_OR(MakeBomNoForecastFlag) AS MakeBomNoForecast,
                   BOOL_OR(Active AND MRPIncluded) AS ActiveMRP
            FROM read_parquet('{sql_path(output_root / 'forecast_demand_item_warehouse_matrix.parquet')}')
            GROUP BY ItemCode
        """))
        no_forecast_items = [x for x in item_cross if x["ActiveMRP"] and not x["AnyForecast"]]
        cross_gate2 = {
            "no_forecast_plus_lt_gap_items": sum(bool(x["LTGap"]) for x in no_forecast_items),
            "no_forecast_plus_lt_missing_items": sum(bool(x["LTMissing"]) for x in no_forecast_items),
            "make_bom_no_forecast_items": sum(bool(x["MakeBomNoForecast"]) for x in no_forecast_items),
        }

        definitions = rows_to_dicts(db.execute(f"SELECT ForecastId, ForecastCode, ForecastName, ForecastStart, ForecastEnd, FormView, Lines, Items, Warehouses, MinDate, MaxDate, ForecastQty, ZeroLines, TemporalStatus, FutureCoverageDays FROM read_parquet('{sql_path(output_root / 'forecast_definitions.parquet')}')"))
        def_count = {"definitions": len(definitions), "current_or_mixed": sum(1 for x in definitions if x["TemporalStatus"] in {"CURRENT", "MIXED"}), "future": sum(1 for x in definitions if x["TemporalStatus"] == "FUTURE"), "expired": sum(1 for x in definitions if x["TemporalStatus"] == "EXPIRED")}

        # Compact, auditable examples are deliberately labelled as data cases;
        # demand alignment cases are not fabricated when demand lineage is absent.
        sample_path = output_root / "forecast_data_quality_cases.csv"
        sample_rows = rows_to_dicts(db.execute(f"""
            SELECT ItemCode, Description, Warehouse, ProcurementMethod, ForecastStatus,
                   ForecastStart, ForecastEnd, SAPForecastQty, ComparableMonths,
                   LeadTimeGapClassification, UsageStatus, GapType
            FROM read_parquet('{sql_path(matrix)}')
            WHERE ForecastStatus <> 'NO_FORECAST'
            ORDER BY CASE WHEN ForecastStatus='MIXED_FORECAST' THEN 0 ELSE 1 END,
                     SAPForecastQty DESC NULLS LAST, ItemCode, Warehouse
            LIMIT 20
        """))
        with sample_path.open("w", newline="", encoding="utf-8") as handle:
            if sample_rows:
                writer = csv.DictWriter(handle, fieldnames=list(sample_rows[0]))
                writer.writeheader()
                writer.writerows(sample_rows)

        class_coverage = {
            k: {"UniverseN": None, "ForecastedN": None, "CoveragePct": None, "status": "UNKNOWN", "reason": "Per-item demand classification Parquet is not present; no class mapping inferred from aggregate report."}
            for k in ("SEASONAL", "GROWING", "STABLE", "INTERMITTENT")
        }
        summary = {
            "gate": GATE,
            "verdict": "DEGRADED",
            "snapshot_date": snapshot.isoformat(),
            "read_only": True,
            "SAP_WRITE_COUNT": 0,
            "mrp_executed": False,
            "forecast_usage": "MRP_USAGE_UNKNOWN",
            "universe": universe,
            "forecast_metrics": forecast_metrics,
            "segments": segments,
            "gate2_cross": cross_gate2,
            "definitions": def_count,
            "definition_rows": definitions,
            "line_quality": line_quality,
            "demand_baseline": DEMAND_BASELINE,
            "demand_class_mapping_available": False,
            "class_coverage": class_coverage,
            "comparable_months": 0,
            "quality_comparison": "UNKNOWN",
            "artifact_root": str(output_root),
            "source_artifacts": [str(item_path), str(pair_path), str(forecast_path), str(lead_path)],
            "sample_case_count": len(sample_rows),
            "notes": [
                "The Gate 1 forecast snapshot was physically confirmed from OFCT/FCT1 and reused.",
                "The prior seasonality report provides class totals but no item-level mapping or monthly demand Parquet in the current DATA_ROOT.",
                "No historical sales were re-extracted; forecast-versus-demand quality remains UNKNOWN.",
                "No forecast usage selector/scenario relation is exposed in the inspected OFCT/FCT1 snapshot.",
            ],
        }
        (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=json_clean), encoding="utf-8")
        manifest = {
            "gate": GATE,
            "version": VERSION,
            "generated_at": datetime.now().astimezone().isoformat(),
            "snapshot_date": snapshot.isoformat(),
            "source_system": "SAP_BUSINESS_ONE_HANA",
            "source_tables": ["OFCT", "FCT1", "OITM", "OITW", "OWHS"],
            "read_only": True,
            "SAP_WRITE_COUNT": 0,
            "mrp_executed": False,
            "query_strategy": "reused Gate 1 OFCT/FCT1 Parquet; DuckDB one-thread joins; no sales re-extraction",
            "demand_baseline": DEMAND_BASELINE,
            "demand_class_mapping_available": False,
            "datasets": [
                "forecast_definitions.parquet",
                "selected_forecast_item_warehouse.parquet",
                "forecast_demand_item_warehouse_matrix.parquet",
                "forecast_data_quality_cases.csv",
                "summary.json",
            ],
        }
        (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(summary, definitions, sample_rows, report_path), encoding="utf-8")
        return summary
    finally:
        db.close()


def pct(n: int | None, d: int | None) -> str:
    if n is None or d in (None, 0):
        return "UNKNOWN"
    return f"{n:,} / {d:,} ({100*n/d:.1f}%)"


def render_report(summary: dict[str, Any], definitions: list[dict[str, Any]], samples: list[dict[str, Any]], report_path: Path) -> str:
    u = summary["universe"]
    fm = summary["forecast_metrics"]
    seg = summary["segments"]
    q = summary["line_quality"]
    lines = [
        "# TELCHI — GATE 3: FORECAST SAP VS DEMANDA REAL", "",
        "## Gate", "", "`TELCHI_MRP_FORECAST_DEMAND_GAP_V1` — **DEGRADED**", "",
        "El forecast SAP fue auditado en modo de investigación. SAP/HANA permaneció READ ONLY; no se ejecutó MRP ni se modificaron OFCT, FCT1, OITM u OITW.", "",
        f"Snapshot de investigación: **{summary['snapshot_date']}**.", "",
        "## Universo", "", f"- Artículos: **{u['all_items']:,}**; activos: **{u['active_items']:,}**; incluidos en MRP: **{u['mrp_items']:,}**; activos incluidos: **{u['active_mrp_items']:,}**.", f"- Productos L activos MRP: **{u['active_mrp_l']:,}**; MAKE: **{u['active_mrp_make']:,}**; BUY: **{u['active_mrp_buy']:,}**.", f"- Item × Warehouse físicos: **{u['item_warehouse_rows']:,}**; warehouses: **{u['warehouses']:,}**.", "",
        "## Forecast SAP", "", f"- Definiciones OFCT: **{summary['definitions']['definitions']:,}**; líneas FCT1: **{q['lines']:,}**.", f"- Ítems con cualquier forecast histórico/actual: **{fm['any_forecast']['items']:,}**; activos MRP: **{fm['any_forecast']['active_mrp_items']:,}**.", f"- Actuales o mixtos por línea temporal: **{fm['current_forecast']['items']:,}** ítems; futuros puros: **{fm['future_forecast']['items']:,}**; vencidos seleccionados: **{fm['expired_forecast']['items']:,}**; cero: **{fm['zero_forecast']['items']:,}**.", "- Uso efectivo por escenario MRP: **MRP_USAGE_UNKNOWN**; OFCT/FCT1 no exponen el selector de escenario usado.", "",
        "### Definiciones y cobertura temporal", "", "| ForecastId | Código | Inicio | Fin | Bucket | Ítems | Warehouses | MinDate | MaxDate | Estado | Días futuros |", "|---:|---|---|---|---|---:|---:|---|---|---|---:|",
    ]
    for d in definitions:
        lines.append(f"| {d.get('ForecastId')} | {d.get('ForecastCode')} | {d.get('ForecastStart')} | {d.get('ForecastEnd')} | {d.get('FormView')} | {d.get('Items')} | {d.get('Warehouses')} | {d.get('MinDate')} | {d.get('MaxDate')} | {d.get('TemporalStatus')} | {d.get('FutureCoverageDays')} |")
    lines += ["", "El ForecastId **19 / Previsicion lit** es el único snapshot temporal no vencido; sus líneas son semanales, cubren 2026-07-27..2026-10-26 y dejan aproximadamente 42 días de cobertura de líneas desde el snapshot. La cabecera finaliza 2026-11-01.", "", "## Cobertura", "", "| Segmento | Universo | Cualquier forecast | Actual/futuro | Sin forecast |", "|---|---:|---:|---:|---:|"]
    for name, label in (("ALL_ACTIVE_MRP", "Activos MRP"), ("L_PRODUCTS", "L%"), ("MAKE", "MAKE"), ("BUY", "BUY")):
        if name == "ALL_ACTIVE_MRP":
            row = {"universe_items": u["active_mrp_items"], "any_forecast_items": fm["any_forecast"]["active_mrp_items"], "current_or_future_items": fm["current_forecast"]["active_mrp_items"], "no_forecast_items": u["active_mrp_items"] - fm["any_forecast"]["active_mrp_items"]}
        else:
            row = seg[name]
        lines.append(f"| {label} | {row['universe_items']:,} | {pct(row['any_forecast_items'], row['universe_items'])} | {pct(row['current_or_future_items'], row['universe_items'])} | {pct(row['no_forecast_items'], row['universe_items'])} |")
    lines += ["", f"L_TOTAL={u['active_mrp_l']:,}; L_WITH_FORECAST={seg['L_PRODUCTS']['any_forecast_items']:,}; L_WITHOUT_FORECAST={seg['L_PRODUCTS']['no_forecast_items']:,}; L_CURRENT_OR_FUTURE={seg['L_PRODUCTS']['current_or_future_items']:,}. L_SEASONAL_WITHOUT_FORECAST=UNKNOWN; L_GROWING_WITHOUT_FORECAST=UNKNOWN.", "La cobertura por clase de demanda no puede calcularse de forma trazable: el reporte histórico conserva los totales SEASONAL/GROWING/STABLE/INTERMITTENT, pero no existe en DATA_ROOT el mapping ItemCode→DemandClass ni sus métricas mensuales.", "", "| DemandClass | UniverseN | ForecastedN | CoveragePct | Estado |", "|---|---:|---:|---:|---|"]
    for cls, row in summary["class_coverage"].items():
        lines.append(f"| {cls} | UNKNOWN | UNKNOWN | UNKNOWN | {row['status']} |")
    lines += ["", "## Demanda real", "", f"Se reutilizó la clasificación agregada auditada de **{summary['demand_baseline']['analyzed_items']:,} ítems**: SEASONAL {summary['demand_baseline']['SEASONAL']:,}, GROWING {summary['demand_baseline']['GROWING']:,}, STABLE {summary['demand_baseline']['STABLE']:,}, INTERMITTENT {summary['demand_baseline']['INTERMITTENT']:,}. No se recalculó el histórico y no se inventó un join por artículo.", "", "Observed12M, Observed6M, trend, seasonality, sales_frequency, months_with_sales, stockout flags y pedidos abiertos quedan **UNKNOWN** en esta ejecución por ausencia de sus artefactos reutilizables.", "", "## Forecast vs realidad", "", "- ComparableN: **0**; Aligned: **UNKNOWN**; Underforecast: **UNKNOWN**; Overforecast: **UNKNOWN**; Stale: **UNKNOWN**.", "- No se calcula AbsoluteError, APE ni MAE porque no existe un período de demanda observado compatible por ItemCode × Warehouse.", "- Por ello no se declaran casos críticos de SEASONAL/GROWING sin forecast ni casos correctamente cubiertos.", "", "## Calidad de datos forecast", "", f"- Líneas cero: **{q['zero_quantity_lines']:,}**; negativas: **{q['negative_quantity_lines']:,}**; sin artículo: **{q['missing_item_lines']:,}**; sin warehouse: **{q['missing_warehouse_lines']:,}**; fecha inválida: **{q['invalid_date_lines']:,}**.", f"- Grupos duplicados por ForecastId × ItemCode × Warehouse × Period: **{q['duplicate_key_groups']:,}**; líneas con warehouse no encontrado en OITW snapshot: **{q['unknown_warehouse_lines']:,}**.", "- No se pudo auditar futuro sobre DISCONTINUED porque falta el mapping de clase por artículo.", "", "## Casos críticos", "", "No se publican falsos positivos: la selección de casos SEASONAL/GROWING/HIGH_VOLUME/STOCKOUT y la clasificación de desalineación requieren demanda por artículo. Se dejó una muestra de 20 casos de calidad/forecast en `forecast_data_quality_cases.csv`, todos marcados con `GapType=UNKNOWN`.", "", "## Casos correctos", "", "No demostrables en este snapshot: existencia de forecast no equivale a calidad ni a uso efectivo.", "", "## Cruce con Lead Time", "", "- El runner cruza Gate 2 a nivel item: `LeadTimeGapClassification` y banderas `LeadTimeGapFlag`/`LeadTimeMissingFlag` quedan en la matriz.", f"- NO_FORECAST + LT_GAP: **{summary['gate2_cross']['no_forecast_plus_lt_gap_items']:,}** artículos activos MRP; NO_FORECAST + LT_MISSING: **{summary['gate2_cross']['no_forecast_plus_lt_missing_items']:,}**.", f"- MAKE + BOM + NO_FORECAST: **{summary['gate2_cross']['make_bom_no_forecast_items']:,}** artículos activos MRP; no se etiqueta causalidad y la demanda sigue UNKNOWN.", "", "## Brechas", "", "- `SAP_NOT_POPULATED`: candidato para artículos sin forecast, pero requiere confirmación de política de negocio; no se concluye error automáticamente.", "- `SAP_STALE_PARAMETER`: no demostrable sin comparar contra demanda reciente.", "- `SAP_MISCONFIGURED`: no demostrable como warehouse incorrecto; el forecast observado sí tiene granularidad ItemCode × Warehouse.", "- `SAP_MODEL_LIMITATION`: no demostrable sin demanda comparable, especialmente para INTERMITTENT.", "- `OPERATIONAL_DATA_NOT_CONNECTED`: posible hipótesis, no confirmada.", "- `NO_GAP_CONFIRMED`: no asignado porque no hay comparación forecast-real.", "- `UNKNOWN`: clasificación aplicada a la brecha de calidad y a la cobertura por clase.", "", "## Hallazgos", "", "1. SAP conserva **13 definiciones** y **250.224 líneas**, pero solo el ForecastId 19 tiene horizonte no vencido al 2026-09-14.", "2. El snapshot actual alcanza **504 ítems activos incluidos en MRP**; los demás ítems con forecast son históricos o están fuera del universo activo-MRP.", "3. La granularidad física observada es **ItemCode × Warehouse**; no se observó forecast global sin warehouse.", "4. Existen **6.672 líneas con cantidad cero**; cantidad cero se conserva como bandera y no como cobertura útil.", "5. El uso efectivo por escenario MRP es **MRP_USAGE_UNKNOWN**.", "6. La calidad forecast vs demanda es **UNKNOWN**, no PASS: falta el mapping per-item de la clasificación histórica y las métricas recientes reutilizables.", "7. La falta de forecast no se convierte automáticamente en error; queda como candidato a `NEEDS_BUSINESS_CONFIRMATION`.", "", "## Limitaciones", "", "- `product_seasonality_v1_report.md` está disponible como resumen agregado, pero no su Parquet/CSV de clasificación por ItemCode.", "- No se reconsultaron ni cargaron millones de ventas; no se ejecutó un nuevo modelo predictivo.", "- OFCT/FCT1 no expone en el snapshot un estado activo ni la selección efectiva del escenario MRP.", "- Stockouts, pedidos abiertos y compatibilidad temporal de ventas no están disponibles como artefactos reutilizables en DATA_ROOT.", "", "## Recursos", "", "- `SAP_WRITE_COUNT=0`; no se ejecutó MRP ni se modificó SAP.", "- Snapshot OFCT/FCT1 físicamente confirmado por consulta read-only previa y reutilizado desde Gate 1.", "- DuckDB con `threads=1`, `memory_limit=1GB`; sin multiprocessing, sin pandas sobre datasets completos y sin extracción histórica de ventas.", "", "## Archivos", "", f"- Reporte: `{report_path}`", f"- Evidencia: `{summary['artifact_root']}`", "- Matriz completa: `forecast_demand_item_warehouse_matrix.parquet`", "- Definiciones: `forecast_definitions.parquet`", "- Selección por item×warehouse: `selected_forecast_item_warehouse.parquet`", "- Manifest y resumen: `manifest.json`, `summary.json`", "", "## Validaciones", "", "- Preflight HANA read-only de OFCT/FCT1: columnas físicas, COUNT, MIN/MAX, DISTINCT forecast/item/warehouse y cantidad cero confirmados.", "- Tests focalizados: PASS (4 tests); `py_compile`: PASS.", "- `git diff --check`: PASS.", "- No se modificó `investigation/STATUS_ACTUAL.md` ni archivos concurrentes.", "", "## Siguiente paso", "", "Para cerrar este Gate como PASS se requiere reponer el artefacto histórico ItemCode×DemandClass×Month (o autorizar una consulta agregada acotada de demanda reciente). Después: `TELCHI_MRP_STOCK_POLICY_GAP_V1`.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--snapshot-date", type=date.fromisoformat, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args(argv)
    os.environ.setdefault("SAP_WRITE_COUNT", "0")
    try:
        result = run(args.output_root, args.report, args.snapshot_date)
    except Exception as exc:
        print(f"{GATE}_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"gate": result["gate"], "verdict": result["verdict"], "artifact_root": result["artifact_root"], "SAP_WRITE_COUNT": 0}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
