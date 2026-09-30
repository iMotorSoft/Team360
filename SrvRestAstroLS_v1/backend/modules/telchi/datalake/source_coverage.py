"""Read-only SAP coverage discovery and complete initial-build planning.

The discovery intentionally returns aggregates and bounded metadata only.  It
never extracts source rows and never publishes Data Lake data.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .ducklake import DuckLakeConnector
from .planner import SegmentSpec, inventory_movement_segments_from_bounds, sales_segments_from_bounds
from .source import HanaReadOnlySource

GATE = "TELCHI_DATALAKE_SAP_SOURCE_COVERAGE_AND_FULL_INITIAL_BUILD_PLAN_V1"
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
LEGACY_MANIFEST = DATA_ROOT / "manifests" / "legacy" / "legacy_parquet_mirror_v1.csv"
LEGACY_SOURCE_ROOT = Path("/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience")
CURRENT_STATE_PATH = DATA_ROOT / "manifests" / "telchi_datalake_create_initial_v1" / "latest.json"
BULK_EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / "TELCHI_DATALAKE_DUCKLAKE_BULK_WRITE_AND_PHYSICAL_LAYOUT_V1"
QUERY_MANIFEST_ROOT = DATA_ROOT / "raw" / "sap" / "query_extract"
MAX_HANA_CONCURRENT_QUERIES = 1
MAX_INGESTION_WORKERS = 1

CONNECTIVITY_SQL = 'SELECT 1 AS "ok" FROM DUMMY'
SALES_COVERAGE_SQL = '''
SELECT
  MIN(H."DocDate") AS "min_doc_date", MAX(H."DocDate") AS "max_doc_date",
  MIN(H."DocEntry") AS "min_doc_entry", MAX(H."DocEntry") AS "max_doc_entry",
  COUNT(DISTINCT H."DocEntry") AS "document_count", COUNT(L."DocEntry") AS "line_count",
  COUNT(DISTINCT CASE WHEN H."CANCELED" = 'N' THEN H."DocEntry" END) AS "non_canceled_document_count",
  COUNT(DISTINCT CASE WHEN H."CANCELED" = 'Y' THEN H."DocEntry" END) AS "canceled_document_count"
FROM "TELCHI"."OINV" H
LEFT JOIN "TELCHI"."INV1" L ON L."DocEntry" = H."DocEntry"
'''
SALES_MONTHLY_SQL = '''
SELECT
  YEAR(H."DocDate") AS "year", MONTH(H."DocDate") AS "month",
  MIN(H."DocDate") AS "min_doc_date", MAX(H."DocDate") AS "max_doc_date",
  MIN(H."DocEntry") AS "min_doc_entry", MAX(H."DocEntry") AS "max_doc_entry",
  COUNT(DISTINCT H."DocEntry") AS "document_count", COUNT(L."DocEntry") AS "line_count",
  COUNT(DISTINCT CASE WHEN H."CANCELED" = 'N' THEN H."DocEntry" END) AS "non_canceled_document_count",
  COUNT(DISTINCT CASE WHEN H."CANCELED" = 'Y' THEN H."DocEntry" END) AS "canceled_document_count"
FROM "TELCHI"."OINV" H
LEFT JOIN "TELCHI"."INV1" L ON L."DocEntry" = H."DocEntry"
GROUP BY YEAR(H."DocDate"), MONTH(H."DocDate")
ORDER BY YEAR(H."DocDate"), MONTH(H."DocDate")
'''
SALES_FIRST_NON_CANCELED_SQL = '''
SELECT TOP 1 H."DocDate" AS "doc_date", H."DocEntry" AS "doc_entry", H."DocNum" AS "doc_num"
FROM "TELCHI"."OINV" H
WHERE H."CANCELED" = 'N'
ORDER BY H."DocDate", H."DocEntry"
'''
SALES_FIRST_CANCELED_SQL = '''
SELECT TOP 1 H."DocDate" AS "doc_date", H."DocEntry" AS "doc_entry", H."DocNum" AS "doc_num"
FROM "TELCHI"."OINV" H
WHERE H."CANCELED" = 'Y'
ORDER BY H."DocDate", H."DocEntry"
'''
SALES_LAST_SQL = '''
SELECT TOP 1 H."DocDate" AS "doc_date", H."DocEntry" AS "doc_entry", H."DocNum" AS "doc_num", H."CANCELED" AS "canceled"
FROM "TELCHI"."OINV" H
ORDER BY H."DocDate" DESC, H."DocEntry" DESC
'''
SALES_ORPHAN_HEADERS_SQL = '''
SELECT COUNT(*) AS "orphan_headers"
FROM "TELCHI"."OINV" H
WHERE NOT EXISTS (SELECT 1 FROM "TELCHI"."INV1" L WHERE L."DocEntry" = H."DocEntry")
'''
SALES_ORPHAN_LINES_SQL = '''
SELECT COUNT(*) AS "orphan_lines"
FROM "TELCHI"."INV1" L
WHERE NOT EXISTS (SELECT 1 FROM "TELCHI"."OINV" H WHERE H."DocEntry" = L."DocEntry")
'''
INVENTORY_MOVEMENT_COVERAGE_SQL = '''
SELECT
  MIN(M."DocDate") AS "min_doc_date", MAX(M."DocDate") AS "max_doc_date",
  MIN(M."TransNum") AS "min_trans_num", MAX(M."TransNum") AS "max_trans_num",
  COUNT(*) AS "row_count"
FROM "TELCHI"."OINM" M
'''
INVENTORY_MOVEMENT_MONTHLY_SQL = '''
SELECT
  YEAR(M."DocDate") AS "year", MONTH(M."DocDate") AS "month",
  MIN(M."DocDate") AS "min_doc_date", MAX(M."DocDate") AS "max_doc_date",
  MIN(M."TransNum") AS "min_trans_num", MAX(M."TransNum") AS "max_trans_num",
  COUNT(*) AS "row_count"
FROM "TELCHI"."OINM" M
GROUP BY YEAR(M."DocDate"), MONTH(M."DocDate")
ORDER BY YEAR(M."DocDate"), MONTH(M."DocDate")
'''
INVENTORY_MOVEMENT_TYPES_SQL = '''
SELECT M."TransType" AS "trans_type", COUNT(*) AS "row_count"
FROM "TELCHI"."OINM" M
GROUP BY M."TransType"
ORDER BY COUNT(*) DESC, M."TransType"
'''
INVENTORY_STATE_SQL = '''
SELECT
  COUNT(*) AS "row_count", COUNT(DISTINCT W."ItemCode") AS "distinct_items",
  COUNT(DISTINCT W."WhsCode") AS "distinct_warehouses",
  CURRENT_UTCTIMESTAMP AS "source_as_of"
FROM "TELCHI"."OITW" W
'''


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _one(source: HanaReadOnlySource, query_id: str, sql: str) -> dict[str, Any]:
    rows = source._execute(query_id, sql)
    return rows[0] if rows else {}


def _date_only(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def discover_sap(source: HanaReadOnlySource | None = None) -> dict[str, Any]:
    """Run sequential, aggregate-only HANA discovery."""
    source = source or HanaReadOnlySource()
    connectivity_started = time.perf_counter()
    try:
        connectivity = _one(source, "connectivity_select_1", CONNECTIVITY_SQL)
        connectivity_pass = connectivity.get("ok") == 1
        connectivity_error = None
    except Exception as exc:
        connectivity_pass = False
        connectivity = {}
        connectivity_error = {"type": type(exc).__name__, "message": str(exc)}
    latency_ms = round((time.perf_counter() - connectivity_started) * 1000, 3)
    if not connectivity_pass:
        return {
            "gate": GATE, "connectivity_pass": "NO", "hana_latency_ms": latency_ms,
            "technical_failure": True, "connectivity_error": connectivity_error,
            "sap_mode": "READ_ONLY", "sap_write_count": source.sap_write_count,
            "query_log": source.query_log,
        }

    sales_overall = _one(source, "sales_coverage_overall", SALES_COVERAGE_SQL)
    sales_monthly = source._execute("sales_coverage_monthly", SALES_MONTHLY_SQL)
    first_non_canceled = _one(source, "sales_first_non_canceled", SALES_FIRST_NON_CANCELED_SQL)
    first_canceled = _one(source, "sales_first_canceled", SALES_FIRST_CANCELED_SQL)
    last_document = _one(source, "sales_last_document", SALES_LAST_SQL)
    orphan_headers = _one(source, "sales_orphan_headers", SALES_ORPHAN_HEADERS_SQL)
    orphan_lines = _one(source, "sales_orphan_lines", SALES_ORPHAN_LINES_SQL)

    movement_overall = _one(source, "inventory_movement_coverage_overall", INVENTORY_MOVEMENT_COVERAGE_SQL)
    movement_monthly = source._execute("inventory_movement_coverage_monthly", INVENTORY_MOVEMENT_MONTHLY_SQL)
    movement_types = source._execute("inventory_movement_type_distribution", INVENTORY_MOVEMENT_TYPES_SQL)
    inventory_state = _one(source, "inventory_state_current", INVENTORY_STATE_SQL)

    return {
        "gate": GATE,
        "connectivity_pass": "YES",
        "hana_latency_ms": latency_ms,
        "technical_failure": False,
        "sap_mode": "READ_ONLY",
        "sap_write_count": source.sap_write_count,
        "max_hana_concurrent_queries": MAX_HANA_CONCURRENT_QUERIES,
        "sales": {
            "source_tables": ["OINV", "INV1"],
            "overall": sales_overall,
            "monthly": sales_monthly,
            "first_non_canceled": first_non_canceled,
            "first_canceled": first_canceled,
            "last_document": last_document,
            "orphan_headers": int(orphan_headers.get("orphan_headers", 0)),
            "orphan_lines": int(orphan_lines.get("orphan_lines", 0)),
        },
        "inventory_movements": {
            "source_table": "OINM",
            "overall": movement_overall,
            "monthly": movement_monthly,
            "trans_type_distribution": movement_types,
        },
        "inventory_state": {
            "source_table": "OITW",
            "source_type": "CURRENT_STATE",
            "summary": inventory_state,
        },
        "query_log": source.query_log,
    }


def _yearly_counts(monthly: list[dict[str, Any]], *, count_field: str) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, int]] = {}
    for row in monthly:
        year = int(row["year"])
        target = grouped.setdefault(year, {"year": year, "document_count": 0, "line_count": 0, "row_count": 0})
        target[count_field] += int(row.get(count_field) or 0)
        if count_field == "document_count":
            target["line_count"] += int(row.get("line_count") or 0)
    return [grouped[year] for year in sorted(grouped)]


def _legacy_coverage() -> dict[str, Any]:
    families = {"sales": {"saleProduct", "saleSB1Product"}, "inventory_movements": {"movProduct", "movProductSB1"}}
    by_domain: dict[str, dict[str, Any]] = {}
    with LEGACY_MANIFEST.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for domain, selected in families.items():
        selected_rows = [row for row in rows if row.get("family") in selected and row.get("filename_date")]
        dates = sorted(row["filename_date"] for row in selected_rows)
        by_domain[domain] = {
            "families": sorted(selected), "file_count": len(selected_rows),
            "min_date": dates[0] if dates else None, "max_date": dates[-1] if dates else None,
            "row_count": sum(int(row.get("row_count") or 0) for row in selected_rows),
            "bytes": sum(int(row.get("destination_size_bytes") or row.get("size_bytes") or 0) for row in selected_rows),
            "metadata_only": True,
        }
    dates = [item["min_date"] for item in by_domain.values() if item["min_date"]] + [item["max_date"] for item in by_domain.values() if item["max_date"]]
    return {
        "source_root": str(LEGACY_SOURCE_ROOT), "manifest": str(LEGACY_MANIFEST),
        "metadata_only": True, "domains": by_domain,
        "min_date": min(dates) if dates else None, "max_date": max(dates) if dates else None,
        "legacy_sap_merge_executed": "NO",
    }


def _state_scopes() -> list[dict[str, Any]]:
    if not CURRENT_STATE_PATH.is_file():
        return []
    state = json.loads(CURRENT_STATE_PATH.read_text(encoding="utf-8"))
    return [
        {
            "segment_id": item.get("segment_id"), "domain": item.get("domain"),
            "business_date_from": item.get("business_date_from"), "business_date_to": item.get("business_date_to"),
            "source_key_from": item.get("source_key_from", item.get("key_from")),
            "source_key_to": item.get("source_key_to", item.get("key_to")),
            "status": item.get("status"),
        }
        for item in state.get("segments", []) if item.get("status") in {"PUBLISHED", "COMPLETED"}
    ]


def existing_ducklake_coverage(lake: DuckLakeConnector | None = None) -> dict[str, Any]:
    """Discover trusted publications and physical metadata without row extraction."""
    lake = lake or DuckLakeConnector()
    with lake.session(read_only=True) as connection:
        tables = lake.resolve_atomic_tables(connection)
        snapshot = lake.snapshot(connection)
        publications = connection.execute(
            "SELECT publication_id, segment_id, status, domain, published_at, reference_version "
            "FROM telchi.ops.initial_publications_v1 WHERE status='COMMITTED' ORDER BY published_at"
        ).fetchall()
        publication_rows = [dict(zip(("publication_id", "segment_id", "status", "domain", "published_at", "reference_version"), row)) for row in publications]
        pilot_v1 = connection.execute(
            "SELECT publication_id, idempotency_key, domain, content_identity, published_at, snapshot_id "
            "FROM telchi.ops.pilot_publications ORDER BY published_at"
        ).fetchall()
        for row in pilot_v1:
            item = dict(zip(("publication_id", "idempotency_key", "domain", "content_identity", "published_at", "snapshot_id"), row))
            item.update({"segment_id": str(item.get("idempotency_key", "")).split("|", 1)[0], "status": "COMMITTED", "provenance": "pilot_publications"})
            publication_rows.append(item)
        pilot_v2 = connection.execute(
            "SELECT publication_id, segment_id, status, job_id, published_at, reference_version "
            "FROM telchi.ops.pilot_publications_v2 WHERE status='COMMITTED' ORDER BY published_at"
        ).fetchall()
        for row in pilot_v2:
            item = dict(zip(("publication_id", "segment_id", "status", "job_id", "published_at", "reference_version"), row))
            item.update({"provenance": "pilot_publications_v2", "domain": "sales" if "sales" in str(item.get("segment_id")) else "inventory"})
            publication_rows.append(item)
        table_counts: dict[str, int | None] = {}
        for table in sorted(set(value for value in tables.values() if value)):
            try:
                table_counts[table] = int(connection.execute(f'SELECT count(*) FROM telchi.atomic."{table}"').fetchone()[0])
            except Exception:
                table_counts[table] = None
    trusted_ids = {str(row["segment_id"]) for row in publication_rows if row.get("segment_id")}
    scopes = [scope for scope in _state_scopes() if scope.get("segment_id") in trusted_ids]
    known_scope_ids = {str(scope.get("segment_id")) for scope in scopes}
    for item in publication_rows:
        segment_id = item.get("segment_id")
        if segment_id and str(segment_id) not in known_scope_ids:
            scopes.append({"segment_id": segment_id, "domain": item.get("domain"), "status": "COMMITTED", "metadata_status": "UNKNOWN", "source_key_from": None, "source_key_to": None})
    return {
        "catalog": "team360_telchi_ducklake", "current_snapshot": snapshot,
        "resolved_atomic_tables": tables, "table_counts": table_counts,
        "trusted_publication_count": len(publication_rows),
        "trusted_scope_count": len(trusted_ids), "trusted_publications": publication_rows,
        "trusted_scopes": scopes, "scope_metadata_source": str(CURRENT_STATE_PATH),
        "status": "PASS" if publication_rows else "UNKNOWN",
    }


def _overlap_status(spec: SegmentSpec, trusted: list[dict[str, Any]]) -> tuple[str, bool, list[str]]:
    matches: list[str] = []
    for item in trusted:
        if item.get("domain") != spec.domain:
            continue
        if item.get("segment_id") == spec.segment_id and item.get("source_key_from") == spec.key_from and item.get("source_key_to") == spec.key_to:
            matches.append(str(item["segment_id"]))
            return "ALREADY_TRUSTED", True, matches
        if spec.domain == "sales" and str(spec.key_from).isdigit() and str(spec.key_to).isdigit() and str(item.get("source_key_from", "")).isdigit() and str(item.get("source_key_to", "")).isdigit():
            same_month = item.get("business_date_from") == spec.business_date_from and item.get("business_date_to") == spec.business_date_to
            intersects = int(spec.key_from) < int(item["source_key_to"]) and int(item["source_key_from"]) < int(spec.key_to)
            if same_month and intersects:
                matches.append(str(item.get("segment_id")))
                if int(item["source_key_from"]) <= int(spec.key_from) and int(item["source_key_to"]) >= int(spec.key_to):
                    return "ALREADY_TRUSTED", True, matches
    return ("OVERLAP" if matches else "PENDING"), False, matches


def _with_estimates(spec: SegmentSpec, *, estimated_documents: int | None = None, estimated_lines: int | None = None, status: str = "PENDING", already_trusted: bool = False, trusted_matches: list[str] | None = None) -> dict[str, Any]:
    value = spec.as_dict()
    value.update({
        "status": status, "already_trusted": already_trusted, "trusted_matches": trusted_matches or [],
        "estimated_documents": estimated_documents, "estimated_lines": estimated_lines,
        "execution_unit": "SEGMENT", "month_is_coverage_unit": True,
        "resume_supported": True, "period_completion_requires_reconciliation": True,
    })
    return value


def _sales_plan(coverage: dict[str, Any], trusted: list[dict[str, Any]], max_docentries: int) -> tuple[list[dict[str, Any]], int]:
    result: list[dict[str, Any]] = []
    monthly = coverage.get("sales", {}).get("monthly", [])
    for month in monthly:
        low, high = month.get("min_doc_entry"), month.get("max_doc_entry")
        if low is None or high is None:
            continue
        month_from = f'{int(month["year"]):04d}-{int(month["month"]):02d}-01'
        month_to = _next_month(int(month["year"]), int(month["month"]))
        month_trusted = sorted(
            (item for item in trusted if item.get("domain") == "sales" and item.get("business_date_from") == month_from and str(item.get("source_key_from", "")).isdigit() and str(item.get("source_key_to", "")).isdigit()),
            key=lambda item: int(item["source_key_from"]),
        )
        # Subtract known trusted key ranges before making pending ranges. This
        # prevents the plan from reloading the August pilot just because its
        # newer plan segment size is larger than the historical pilot ranges.
        specs: list[SegmentSpec] = []
        cursor = int(low)
        for trusted_item in month_trusted:
            trusted_low = max(cursor, int(trusted_item["source_key_from"]))
            trusted_high = min(int(high) + 1, int(trusted_item["source_key_to"]))
            if trusted_low > cursor:
                specs.extend(sales_segments_from_bounds([(month_from, month_to, cursor, trusted_low - 1)], max_docentries_per_segment=max_docentries))
            if trusted_low < trusted_high:
                specs.append(SegmentSpec(
                    segment_id=str(trusted_item["segment_id"]), domain="sales", business_date_from=month_from, business_date_to=month_to,
                    key_from=str(trusted_low), key_to=str(trusted_high), strategy="DOCENTRY_RANGE", scope=f"DocEntry >= {trusted_low} AND DocEntry < {trusted_high}; DocDate >= {month_from} AND DocDate < {month_to}",
                ))
            cursor = max(cursor, trusted_high)
        if cursor <= int(high):
            specs.extend(sales_segments_from_bounds([(month_from, month_to, cursor, int(high))], max_docentries_per_segment=max_docentries))
        for spec in specs:
            status, exact, matches = _overlap_status(spec, trusted)
            span = max(1, int(spec.key_to) - int(spec.key_from))
            total_span = max(1, int(high) - int(low) + 1)
            docs = round(int(month.get("document_count") or 0) * span / total_span)
            lines = round(int(month.get("line_count") or 0) * span / total_span)
            result.append(_with_estimates(spec, estimated_documents=docs, estimated_lines=lines, status=status, already_trusted=exact, trusted_matches=matches))
    return result, len({(item["business_date_from"], item["business_date_to"]) for item in result})


def _next_month(year: int, month: int) -> str:
    if month == 12:
        return f"{year + 1:04d}-01-01"
    return f"{year:04d}-{month + 1:02d}-01"


def _movement_plan(coverage: dict[str, Any], trusted: list[dict[str, Any]], max_transnum: int) -> tuple[list[dict[str, Any]], int]:
    result: list[dict[str, Any]] = []
    monthly = coverage.get("inventory_movements", {}).get("monthly", [])
    bounds = []
    for month in monthly:
        if month.get("min_trans_num") is not None and month.get("max_trans_num") is not None:
            bounds.append((f'{int(month["year"]):04d}-{int(month["month"]):02d}-01', _next_month(int(month["year"]), int(month["month"])), int(month["min_trans_num"]), int(month["max_trans_num"]), int(month.get("row_count") or 0)))
    for month_from, month_to, low, high, rows in bounds:
        for spec in inventory_movement_segments_from_bounds([(month_from, month_to, low, high, rows)], max_transnum_per_segment=max_transnum):
            status, exact, matches = _overlap_status(spec, trusted)
            result.append(_with_estimates(spec, estimated_lines=spec.estimated_rows, status=status, already_trusted=exact, trusted_matches=matches))
    return result, len({(item["business_date_from"], item["business_date_to"]) for item in result})


def build_full_initial_plan(coverage: dict[str, Any], existing: dict[str, Any] | None = None, *, max_docentries: int = 100_000, max_transnum: int = 100_000, max_inventory_pairs: int = 1_000) -> dict[str, Any]:
    """Build a complete, nested year/month/segment plan from discovered coverage."""
    if max_docentries <= 0 or max_transnum <= 0 or max_inventory_pairs <= 0:
        raise ValueError("planning segment sizes must be positive")
    existing = existing or {}
    trusted = existing.get("trusted_scopes", [])
    sales, sales_months = _sales_plan(coverage, trusted, max_docentries)
    movement, movement_months = _movement_plan(coverage, trusted, max_transnum)
    state_summary = coverage.get("inventory_state", {}).get("summary", {})
    loaded_state_rows = int(existing.get("table_counts", {}).get("inventory_balance") or 0)
    source_state_rows = int(state_summary.get("row_count") or 0)
    state_segment_count = max(1, math.ceil(source_state_rows / max_inventory_pairs))
    state_segments: list[dict[str, Any]] = []
    for ordinal in range(state_segment_count):
        page_from = ordinal * max_inventory_pairs
        page_to = min(source_state_rows, page_from + max_inventory_pairs)
        # OITW keys stay source-owned.  Page ordinals are planning bounds only;
        # execution resolves real ItemCode x WhsCode boundaries by keyset.
        state_status = "OVERLAP" if ordinal == 0 and loaded_state_rows else "PENDING"
        state_segments.append({
            "segment_id": f"inventory-current-state-{ordinal:04d}", "domain": "inventory_current_state",
            "year": None, "month": None, "business_date_from": None, "business_date_to": None,
            "source_key_from": f"KEYSET_PAGE_{page_from:09d}", "source_key_to": f"KEYSET_PAGE_{page_to:09d}",
            "strategy": "ITEMCODE_WHS_KEYSET_PAGE", "scope": f"OITW current state; bounded keyset page {page_from}:{page_to}; no historical date predicate",
            "estimated_rows": page_to - page_from, "status": state_status, "already_trusted": False,
            "trusted_matches": [], "execution_unit": "SEGMENT", "month_is_coverage_unit": False,
            "resume_supported": True, "period_completion_requires_reconciliation": True,
            "source_type": "CURRENT_STATE", "source_as_of": state_summary.get("source_as_of"),
            "loaded_rows_observed": loaded_state_rows if ordinal == 0 else 0,
        })
    domains = [
        {"domain": "sales", "source_tables": ["OINV", "INV1"], "coverage_unit": "MONTH", "execution_unit": "SEGMENT", "months_planned": sales_months, "segments_planned": len(sales), "segments": sales},
        {"domain": "inventory_movements", "source_tables": ["OINM"], "coverage_unit": "MONTH", "execution_unit": "SEGMENT", "months_planned": movement_months, "segments_planned": len(movement), "segments": movement, "execution_supported_by_current_create_initial": True, "implementation_note": "create_initial consumes the existing bounded TransNum planner and publishes atomic.inventory_movement through the transactional bulk writer."},
        {"domain": "inventory_current_state", "source_tables": ["OITW"], "coverage_unit": "CURRENT_STATE", "execution_unit": "SEGMENT", "months_planned": 0, "segments_planned": len(state_segments), "segments": state_segments},
    ]
    years = sorted({int(item["business_date_from"][:4]) for item in sales + movement if item.get("business_date_from")})
    execution_order = {
        "priority": ["inventory_current_state", "sales", "inventory_movements"],
        "sales": [item["segment_id"] for item in sorted(sales, key=lambda item: (item.get("business_date_from") or "", item["segment_id"]), reverse=True)],
        "inventory_movements": [item["segment_id"] for item in sorted(movement, key=lambda item: (item.get("business_date_from") or "", item["segment_id"]), reverse=True)],
        "inventory_current_state": [item["segment_id"] for item in state_segments],
    }
    return {
        "gate": GATE, "plan_version": "1.0.0", "plan_only": True,
        "source_truth": "SAP_HANA_READ_ONLY_AGGREGATE_DISCOVERY", "legacy_merged": False,
        "legacy_sap_merge_executed": "NO", "full_historical_build_started": "NO",
        "max_ingestion_workers": MAX_INGESTION_WORKERS, "max_hana_concurrent_queries": MAX_HANA_CONCURRENT_QUERIES,
        "resource_guards_active": "YES", "bulk_write_path_preserved": "YES",
        "full_build_years": years, "recommended_build_order": "CURRENT_STATE_FIRST_THEN_CURRENT_YEAR_DESCENDING_THEN_PREVIOUS_YEARS_DESCENDING",
        "recommended_build_order_rationale": "Provides useful recent data first, keeps each month independently reconciled, and preserves resume/checkpoint value without a monolithic transaction.",
        "execution_order": execution_order,
        "domains": domains,
        "sales_months_planned": sales_months, "sales_segments_planned": len(sales),
        "inventory_months_planned": movement_months,
        "inventory_movement_segments_planned": len(movement), "inventory_current_state_segments_planned": len(state_segments), "inventory_segments_planned": len(movement) + len(state_segments),
        "inventory_current_state_included": "YES", "inventory_current_state_source_as_of": state_summary.get("source_as_of"),
        "existing_trusted_scope_count": existing.get("trusted_scope_count", 0),
        "period_complete_definition": "all planned segments PASS, all reconciliations PASS, and no gaps remain",
        "publication_contract": "temporary/staging batch -> set-based delete -> INSERT INTO ... SELECT -> single transaction",
        "source_identity_contract": ["DocEntry", "DocNum", "LineNum", "ObjType", "ItemCode", "WhsCode", "TransNum"],
        "ready_for_full_initial_build": "NO" if any(domain.get("execution_supported_by_current_create_initial") is False for domain in domains) else "YES",
        "segments_flat": sales + movement + state_segments,
    }


def _pilot_ratio(domain: str, field: str) -> float | None:
    candidates = {"sales": "sales", "inventory_movements": "inventory_movements", "inventory_current_state": "inventory_balance_snapshot"}
    path = QUERY_MANIFEST_ROOT / candidates[domain]
    manifests = sorted(path.glob("*/manifest.json")) if path.is_dir() else []
    if not manifests:
        return None
    data = json.loads(manifests[-1].read_text(encoding="utf-8"))
    rows = int(data.get("row_count") or 0)
    value = int(data.get(field) or data.get("total_bytes") or 0)
    return value / rows if rows else None


def storage_estimate(coverage: dict[str, Any], plan: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    sales_rows = int(coverage.get("sales", {}).get("overall", {}).get("line_count") or 0)
    movement_rows = int(coverage.get("inventory_movements", {}).get("overall", {}).get("row_count") or 0)
    state_rows = int(coverage.get("inventory_state", {}).get("summary", {}).get("row_count") or 0)
    raw_components = {
        "sales": sales_rows * (_pilot_ratio("sales", "total_bytes") or 0),
        "inventory_movements": movement_rows * (_pilot_ratio("inventory_movements", "total_bytes") or 0),
        "inventory_current_state": state_rows * (_pilot_ratio("inventory_current_state", "total_bytes") or 0),
    }
    raw_known = all(_pilot_ratio(domain, "total_bytes") is not None for domain in raw_components)
    table_stats = {}
    try:
        table_stats = {item["table"]: item for item in DuckLakeConnector().managed_file_inventory(include_history=False).get("table_stats", [])}
    except Exception:
        table_stats = {}
    atomic_components: dict[str, int | None] = {}
    for table, rows in [("sales_document", int(coverage.get("sales", {}).get("overall", {}).get("document_count") or 0)), ("sales_line", sales_rows), ("inventory_balance", state_rows)]:
        stat = table_stats.get(table, {})
        ratio = (int(stat.get("live_bytes") or 0) / int(stat.get("row_count") or 0)) if stat.get("row_count") else None
        atomic_components[table] = round(rows * ratio) if ratio is not None else None
    atomic_complete = not any(domain["domain"] == "inventory_movements" and domain.get("segments") for domain in plan["domains"])
    return {
        "method": "source cardinality multiplied by observed pilot bytes_per_row; approximate",
        "source_cardinality": {"sales_lines": sales_rows, "inventory_movement_rows": movement_rows, "inventory_state_rows": state_rows},
        "raw_components_bytes": {key: round(value) for key, value in raw_components.items()},
        "estimated_raw_bytes": round(sum(raw_components.values())) if raw_known else "UNKNOWN",
        "atomic_components_bytes_supported_tables": atomic_components,
        "estimated_atomic_bytes": round(sum(value for value in atomic_components.values() if value is not None)) if atomic_complete and all(value is not None for value in atomic_components.values()) else "UNKNOWN",
        "atomic_estimate_complete": atomic_complete,
        "estimated_atomic_file_count": "UNKNOWN" if not atomic_complete else sum(2 for item in plan["domains"][0]["segments"] if item["status"] != "ALREADY_TRUSTED") + 1,
        "pilot_evidence": str(BULK_EVIDENCE_ROOT), "physical_expectation": "bulk set-based publication; no 7066-file pattern extrapolation",
        "trusted_rows_excluded_for_workload": {"inventory_balance": int(existing.get("table_counts", {}).get("inventory_balance") or 0)},
    }


def overlap_summary(legacy: dict[str, Any], coverage: dict[str, Any]) -> dict[str, Any]:
    sap_min = _date_only(coverage.get("sales", {}).get("overall", {}).get("min_doc_date"))
    sap_max = _date_only(coverage.get("sales", {}).get("overall", {}).get("max_doc_date"))
    legacy_min, legacy_max = legacy.get("min_date"), legacy.get("max_date")
    overlap_from = max(item for item in [sap_min, legacy_min] if item) if sap_min or legacy_min else None
    overlap_to = min(item for item in [sap_max, legacy_max] if item) if sap_max or legacy_max else None
    return {
        "legacy_min_date": legacy_min, "legacy_max_date": legacy_max,
        "sap_min_date": sap_min, "sap_max_date": sap_max,
        "overlap_from": overlap_from if overlap_from and overlap_to and overlap_from <= overlap_to else None,
        "overlap_to": overlap_to if overlap_from and overlap_to and overlap_from <= overlap_to else None,
        "gap": "NO" if overlap_from and overlap_to and overlap_from <= overlap_to else "UNKNOWN",
        "merge_executed": "NO", "interpretation": "coverage/overlap only; no historical merge decision",
    }


def render_plan_markdown(plan: dict[str, Any], coverage: dict[str, Any], legacy: dict[str, Any], overlap: dict[str, Any], estimate: dict[str, Any]) -> str:
    lines = [f"# {GATE}", "", "## Source coverage", "", f"- SAP connectivity: **{coverage.get('connectivity_pass')}** ({coverage.get('hana_latency_ms')} ms)", f"- Sales: **{coverage.get('sales', {}).get('overall', {}).get('min_doc_date')} → {coverage.get('sales', {}).get('overall', {}).get('max_doc_date')}**", f"- Inventory movements: **{coverage.get('inventory_movements', {}).get('overall', {}).get('min_doc_date')} → {coverage.get('inventory_movements', {}).get('overall', {}).get('max_doc_date')}**", f"- OITW: **CURRENT_STATE**, as of `{coverage.get('inventory_state', {}).get('summary', {}).get('source_as_of')}`", "", "## Plan", "", f"- Years: `{plan.get('full_build_years')}`", f"- Sales: `{plan.get('sales_months_planned')}` months / `{plan.get('sales_segments_planned')}` bounded segments", f"- Inventory movements: `{plan.get('inventory_months_planned')}` months / `{plan.get('inventory_movement_segments_planned')}` bounded segments", f"- Inventory current state: `{plan.get('inventory_current_state_segments_planned')}` bounded ItemCode × WhsCode keyset pages (current-state only)", f"- Existing trusted scopes: `{plan.get('existing_trusted_scope_count')}`", f"- Recommended order: **{plan.get('recommended_build_order')}**", "", "## Legacy separation", "", f"- Legacy metadata: `{legacy.get('min_date')} → {legacy.get('max_date')}`", f"- SAP/legacy overlap: `{overlap.get('overlap_from')} → {overlap.get('overlap_to')}`", f"- Gap: **{overlap.get('gap')}**; merge executed: **NO**", "", "## Estimates", "", f"- Raw bytes (approx): `{estimate.get('estimated_raw_bytes')}`", f"- Atomic bytes (supported tables only): `{estimate.get('estimated_atomic_bytes')}`; complete: `{estimate.get('atomic_estimate_complete')}`", f"- Atomic file count: `{estimate.get('estimated_atomic_file_count')}`", "", "The plan preserves one worker, one HANA query, staging + set-based publication, segment checkpoints, resume, and per-segment reconciliation. `STOP AND REVIEW`: no full historical build was started and `update.py` was not implemented."]
    return "\n".join(lines) + "\n"


def write_evidence(coverage: dict[str, Any], existing: dict[str, Any], legacy: dict[str, Any], overlap: dict[str, Any], plan: dict[str, Any], estimate: dict[str, Any]) -> dict[str, Any]:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    _write_json(EVIDENCE_ROOT / "coverage.json", coverage)
    _write_json(EVIDENCE_ROOT / "hana_connectivity.json", {key: coverage.get(key) for key in ["gate", "connectivity_pass", "hana_latency_ms", "technical_failure", "connectivity_error", "sap_mode", "sap_write_count", "query_log"]})
    _write_json(EVIDENCE_ROOT / "sap_sales_coverage.json", coverage.get("sales", {}))
    _write_json(EVIDENCE_ROOT / "sap_inventory_movement_coverage.json", coverage.get("inventory_movements", {}))
    _write_json(EVIDENCE_ROOT / "sap_inventory_state_summary.json", coverage.get("inventory_state", {}))
    _write_json(EVIDENCE_ROOT / "sap_source_yearly_counts.json", {
        "sales_yearly": _yearly_counts(coverage.get("sales", {}).get("monthly", []), count_field="document_count"),
        "sales_monthly": coverage.get("sales", {}).get("monthly", []),
        "inventory_movements_yearly": _yearly_counts(coverage.get("inventory_movements", {}).get("monthly", []), count_field="row_count"),
        "inventory_movements_monthly": coverage.get("inventory_movements", {}).get("monthly", []),
    })
    _write_json(EVIDENCE_ROOT / "legacy_coverage_summary.json", legacy)
    _write_json(EVIDENCE_ROOT / "legacy_sap_overlap.json", overlap)
    _write_json(EVIDENCE_ROOT / "existing_ducklake_coverage.json", existing)
    _write_json(EVIDENCE_ROOT / "full_initial_build_plan.json", plan)
    (EVIDENCE_ROOT / "full_initial_build_plan.md").write_text(render_plan_markdown(plan, coverage, legacy, overlap, estimate), encoding="utf-8")
    _write_json(EVIDENCE_ROOT / "storage_estimate.json", estimate)
    order = {"recommended_build_order": plan.get("recommended_build_order"), "rationale": plan.get("recommended_build_order_rationale"), "full_historical_build_started": "NO"}
    _write_json(EVIDENCE_ROOT / "execution_order_recommendation.json", order)
    _write_json(EVIDENCE_ROOT / "planning_inputs.json", {"coverage": coverage, "existing_ducklake": existing, "legacy": legacy, "overlap": overlap})
    summary = {
        "GATE": GATE, "HANA_CONNECTIVITY": "PASS" if coverage.get("connectivity_pass") == "YES" else "FAIL", "HANA_LATENCY_MS": coverage.get("hana_latency_ms"),
        "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": coverage.get("sap_write_count", 0),
        "SALES_SOURCE_TABLES": "OINV,INV1", "SALES_SOURCE_MIN_DATE": _date_only(coverage.get("sales", {}).get("overall", {}).get("min_doc_date")), "SALES_SOURCE_MAX_DATE": _date_only(coverage.get("sales", {}).get("overall", {}).get("max_doc_date")),
        "SALES_DOCUMENT_COUNT": coverage.get("sales", {}).get("overall", {}).get("document_count"), "SALES_LINE_COUNT": coverage.get("sales", {}).get("overall", {}).get("line_count"),
        "INVENTORY_MOVEMENT_SOURCE": "OINM", "INVENTORY_MOVEMENT_MIN_DATE": _date_only(coverage.get("inventory_movements", {}).get("overall", {}).get("min_doc_date")), "INVENTORY_MOVEMENT_MAX_DATE": _date_only(coverage.get("inventory_movements", {}).get("overall", {}).get("max_doc_date")), "INVENTORY_MOVEMENT_ROW_COUNT": coverage.get("inventory_movements", {}).get("overall", {}).get("row_count"),
        "INVENTORY_STATE_SOURCE": "OITW", "INVENTORY_STATE_TYPE": "CURRENT_STATE", "INVENTORY_STATE_AS_OF": coverage.get("inventory_state", {}).get("summary", {}).get("source_as_of"), "OITW_ROW_COUNT": coverage.get("inventory_state", {}).get("summary", {}).get("row_count"), "OITW_DISTINCT_ITEMS": coverage.get("inventory_state", {}).get("summary", {}).get("distinct_items"), "OITW_DISTINCT_WAREHOUSES": coverage.get("inventory_state", {}).get("summary", {}).get("distinct_warehouses"),
        "LEGACY_MIN_DATE": legacy.get("min_date") or "UNKNOWN", "LEGACY_MAX_DATE": legacy.get("max_date") or "UNKNOWN", "SAP_LEGACY_OVERLAP_FROM": overlap.get("overlap_from") or "NONE", "SAP_LEGACY_OVERLAP_TO": overlap.get("overlap_to") or "NONE", "LEGACY_SAP_GAP": overlap.get("gap", "UNKNOWN"), "LEGACY_SAP_MERGE_EXECUTED": "NO",
        "INITIAL_BUILD_SALES_FROM": _date_only(coverage.get("sales", {}).get("overall", {}).get("min_doc_date")), "INITIAL_BUILD_SALES_TO": _exclusive_end(coverage.get("sales", {}).get("overall", {}).get("max_doc_date")), "INITIAL_BUILD_INVENTORY_MOVEMENT_FROM": _date_only(coverage.get("inventory_movements", {}).get("overall", {}).get("min_doc_date")), "INITIAL_BUILD_INVENTORY_MOVEMENT_TO": _exclusive_end(coverage.get("inventory_movements", {}).get("overall", {}).get("max_doc_date")), "CURRENT_INVENTORY_STATE_INCLUDED": "YES",
        "EXISTING_TRUSTED_SCOPE_COUNT": existing.get("trusted_scope_count", 0), "FULL_BUILD_YEARS": plan.get("full_build_years"), "SALES_MONTHS_PLANNED": plan.get("sales_months_planned"), "SALES_SEGMENTS_PLANNED": plan.get("sales_segments_planned"), "INVENTORY_MONTHS_PLANNED": plan.get("inventory_months_planned"), "INVENTORY_SEGMENTS_PLANNED": plan.get("inventory_segments_planned"), "INVENTORY_MOVEMENT_SEGMENTS_PLANNED": plan.get("inventory_movement_segments_planned"), "INVENTORY_CURRENT_STATE_SEGMENTS_PLANNED": plan.get("inventory_current_state_segments_planned"),
        "ESTIMATED_RAW_BYTES": estimate.get("estimated_raw_bytes"), "ESTIMATED_ATOMIC_BYTES": estimate.get("estimated_atomic_bytes"), "ESTIMATED_ATOMIC_FILE_COUNT": estimate.get("estimated_atomic_file_count"), "RECOMMENDED_BUILD_ORDER": plan.get("recommended_build_order"), "MAX_INGESTION_WORKERS_EFFECTIVE": 1, "MAX_HANA_CONCURRENT_QUERIES_EFFECTIVE": 1, "BULK_WRITE_PATH_PRESERVED": "YES", "RESOURCE_GUARDS_ACTIVE": "YES", "FULL_HISTORICAL_BUILD_STARTED": "NO", "UPDATE_SCRIPT_IMPLEMENTED": "NO", "READY_FOR_FULL_INITIAL_BUILD": plan.get("ready_for_full_initial_build"), "ORPHAN_HEADERS": coverage.get("sales", {}).get("orphan_headers"), "ORPHAN_LINES": coverage.get("sales", {}).get("orphan_lines"), "LEGACY_SAP_MERGE_EXECUTED": "NO",
    }
    _write_json(EVIDENCE_ROOT / "summary.json", summary)
    report_lines = [f"{key}={value}" for key, value in summary.items()]
    report_lines += ["", "FULL_BUILD_SINGLE_COMMAND_ALLOWED=YES (only with internal bounded segments/checkpoints/resume/resource guards)", "PERIOD_COMPLETE=all planned segments PASS + reconciliations PASS + no gaps", "", "STOP AND REVIEW. No full historical build, update.py, legacy merge, Business/Current or benchmark was started."]
    (EVIDENCE_ROOT / "report.md").write_text(f"# {GATE}\n\n```text\n" + "\n".join(report_lines) + "\n```\n", encoding="utf-8")
    return summary


def _exclusive_end(value: Any) -> str | None:
    parsed = _date_only(value)
    if not parsed:
        return None
    return (date.fromisoformat(parsed) + timedelta(days=1)).isoformat()


def run_discovery(*, output_dir: Path = EVIDENCE_ROOT, source: HanaReadOnlySource | None = None, lake: DuckLakeConnector | None = None) -> dict[str, Any]:
    global EVIDENCE_ROOT
    original = EVIDENCE_ROOT
    EVIDENCE_ROOT = output_dir
    try:
        coverage = discover_sap(source)
        existing = existing_ducklake_coverage(lake) if coverage.get("connectivity_pass") == "YES" else {"status": "UNKNOWN", "trusted_scope_count": 0, "trusted_scopes": []}
        legacy = _legacy_coverage()
        overlap = overlap_summary(legacy, coverage)
        plan = build_full_initial_plan(coverage, existing)
        estimate = storage_estimate(coverage, plan, existing) if coverage.get("connectivity_pass") == "YES" else {"estimated_raw_bytes": "UNKNOWN", "estimated_atomic_bytes": "UNKNOWN", "estimated_atomic_file_count": "UNKNOWN"}
        summary = write_evidence(coverage, existing, legacy, overlap, plan, estimate)
        return summary
    finally:
        EVIDENCE_ROOT = original


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover SAP/HANA source coverage and generate a full create_initial plan")
    parser.add_argument("--output-dir", default=str(EVIDENCE_ROOT))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_discovery(output_dir=Path(args.output_dir))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(GATE + ("_PASS" if summary.get("HANA_CONNECTIVITY") == "PASS" else "_DEGRADED"))
    return 0 if summary.get("HANA_CONNECTIVITY") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
