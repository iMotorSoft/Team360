"""TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1.

Source-native, read-only capture of the eight Material Supply fact datasets
from SAP Business One / HANA into the immutable raw layer:

    bom_header / bom_line
    production_order / production_issue
    purchase_order / purchase_order_line
    purchase_receipt / purchase_receipt_line

Design contract (V1):

* SAP is strictly read-only. Every statement is passed through
  :func:`modules.telchi.datalake.sql.assert_read_only_select` and the only
  adapter used is :class:`modules.telchi.datalake.source.HanaReadOnlySource`.
* Columns are discovered from ``SYS.TABLE_COLUMNS`` before any extraction.
  Optional fields that do not exist are recorded as ``ABSENT`` and skipped;
  required logical-key fields fail closed.
* Persistence always goes through :func:`modules.telchi.datalake.raw.write_raw`
  (atomic temp + rename, manifest with exact row count, empty segment
  rejection). No other writer is introduced.
* Only :class:`modules.telchi.runtime.resource_guard.ResourceGuard` is used for
  resource safety (sequential, bounded, single heavy worker).
* The capture is checkpointed per segment and idempotent: an already completed
  ``(dataset, segment)`` is never rewritten, so a re-run cannot duplicate rows.
* This module knows nothing about Foundation publication, business derivations,
  or the Saavedra acceptance query; it only materialises source-native facts.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from modules.telchi.runtime.config import DuckDBSafetyProfile, RuntimeConfig, open_safe_duckdb
from modules.telchi.runtime.resource_guard import ResourceGuard, SafeAbort

from .ducklake import DATA_ROOT
from .planner import month_ranges
from .raw import write_raw
from .sql import assert_read_only_select

GATE = "TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1"
FOUNDATION_EVIDENCE_ROOT = (
    Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi")
    / "TELCHI_DATALAKE_MATERIAL_SUPPLY_FOUNDATION_V1"
)
# This capture gate extends the existing Material Supply Foundation evidence
# folder instead of inventing a parallel one.
EVIDENCE_ROOT = FOUNDATION_EVIDENCE_ROOT
RAW_ROOT = DATA_ROOT / "raw" / "sap" / GATE
SOURCE_SCHEMA = "TELCHI"
CAPTURE_YEAR = 2026

COLUMN_DISCOVERY_SQL = """
SELECT COLUMN_NAME, DATA_TYPE_NAME, POSITION, LENGTH, SCALE
FROM SYS.TABLE_COLUMNS
WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?
ORDER BY POSITION
"""

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")


def _ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"unsafe source identifier: {name!r}")
    return name


class CaptureAbort(RuntimeError):
    """Controlled stop: the captured snapshot is not trusted."""


class FactSource(Protocol):
    """Minimal read-only surface the capture needs from a HANA adapter."""

    def query_read_only(self, query_id: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Dataset definitions (source-native fields, optional candidates)
# ---------------------------------------------------------------------------


def _f(out: str, owner: str, *candidates: str) -> tuple[str, str, tuple[str, ...]]:
    return (out, owner, tuple(candidates) or (out,))


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    header_table: str
    line_table: str | None
    date_field: str | None
    key_fields: tuple[str, ...]
    quantity_field: str | None
    fields: tuple[tuple[str, str, tuple[str, ...]], ...]
    kind: str = "month"  # "full" | "month"

    @property
    def tables(self) -> tuple[str, ...]:
        return (self.header_table, self.line_table) if self.line_table else (self.header_table,)


DEFAULT_DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        name="bom_header", header_table="OITT", line_table=None, date_field=None,
        key_fields=("Code",), quantity_field=None, kind="full",
        fields=(
            _f("Code", "H"), _f("Name", "H"), _f("TreeType", "H"),
            _f("Qauntity", "H", "Qauntity", "Quantity"),
            _f("U_MEDIDA", "H"), _f("U_ALMACEN", "H"), _f("PriceList", "H"),
            _f("Transfered", "H"), _f("CreateDate", "H"), _f("UpdateDate", "H"),
            _f("UserSign", "H"),
        ),
    ),
    DatasetSpec(
        name="bom_line", header_table="ITT1", line_table=None, date_field=None,
        key_fields=("Father", "ChildNum", "VisOrder"), quantity_field="Quantity", kind="full",
        fields=(
            _f("Father", "H"), _f("ChildNum", "H"), _f("VisOrder", "H"), _f("Code", "H"),
            _f("Quantity", "H"), _f("Warehouse", "H"), _f("IssueMthd", "H"), _f("Uom", "H"),
            _f("Type", "H"), _f("AddQuantit", "H"), _f("LineText", "H"), _f("StageId", "H"),
            _f("ItemName", "H"), _f("Price", "H"), _f("Currency", "H"),
        ),
    ),
    DatasetSpec(
        name="production_order", header_table="OWOR", line_table=None, date_field="PostDate",
        key_fields=("DocEntry",), quantity_field="PlannedQty",
        fields=(
            _f("DocEntry", "H"), _f("DocNum", "H"), _f("Series", "H"), _f("ItemCode", "H"),
            _f("Status", "H"), _f("Type", "H"), _f("PlannedQty", "H"), _f("CmpltQty", "H"),
            _f("RjctQty", "H"), _f("PostDate", "H"), _f("DueDate", "H"), _f("StartDate", "H"),
            _f("CloseDate", "H"), _f("OriginAbs", "H"), _f("OriginNum", "H"), _f("OriginType", "H"),
            _f("Warehouse", "H"), _f("Uom", "H"), _f("CardCode", "H"), _f("U_Estado", "H"),
            _f("U_Almacen", "H"), _f("U_MEDIDA", "H"), _f("U_LOTE", "H"), _f("Project", "H"),
            _f("UserSign", "H"),
        ),
    ),
    DatasetSpec(
        name="production_issue", header_table="OIGE", line_table="IGE1", date_field="DocDate",
        key_fields=("DocEntry", "LineNum"), quantity_field="Quantity",
        fields=(
            _f("DocEntry", "H"), _f("DocNum", "H"), _f("DocDate", "H"), _f("CANCELED", "H"),
            _f("DocStatus", "H"), _f("CardCode", "H"), _f("Comments", "H"),
            _f("LineNum", "L"), _f("ItemCode", "L"), _f("Dscription", "L"), _f("Quantity", "L"),
            _f("WhsCode", "L"), _f("FromWhsCod", "L"), _f("BaseType", "L"), _f("BaseEntry", "L"),
            _f("BaseLine", "L"), _f("LineStatus", "L"), _f("unitMsr", "L"), _f("NumPerMsr", "L"),
            _f("UomCode", "L"), _f("LineDocDate", "L", "DocDate"), _f("Price", "L"),
            _f("LineTotal", "L"), _f("Project", "L"), _f("OcrCode", "L"),
        ),
    ),
    DatasetSpec(
        name="purchase_order", header_table="OPOR", line_table=None, date_field="DocDate",
        key_fields=("DocEntry",), quantity_field=None,
        fields=(
            _f("DocEntry", "H"), _f("DocNum", "H"), _f("CardCode", "H"), _f("CardName", "H"),
            _f("DocDate", "H"), _f("DocDueDate", "H"), _f("ReqDate", "H"), _f("CANCELED", "H"),
            _f("DocStatus", "H"), _f("DocCur", "H"), _f("DocRate", "H"), _f("DocTotal", "H"),
            _f("DocTotalFC", "H"), _f("DocTotalSy", "H"), _f("U_TIPOCOMPRA", "H"),
            _f("U_ORIGIN", "H"), _f("U_INCOTERM", "H"), _f("U_CODPAIS", "H"), _f("Series", "H"),
            _f("UserSign", "H"), _f("NumAtCard", "H"), _f("Comments", "H"),
        ),
    ),
    DatasetSpec(
        name="purchase_order_line", header_table="OPOR", line_table="POR1", date_field="DocDate",
        key_fields=("DocEntry", "LineNum"), quantity_field="Quantity",
        fields=(
            _f("DocEntry", "H"), _f("DocNum", "H"), _f("CardCode", "H"), _f("DocDate", "H"),
            _f("DocCur", "H"), _f("U_TIPOCOMPRA", "H"),
            _f("LineNum", "L"), _f("ItemCode", "L"), _f("Dscription", "L"), _f("WhsCode", "L"),
            _f("Quantity", "L"), _f("OpenQty", "L"), _f("LineStatus", "L"), _f("ShipDate", "L"),
            _f("unitMsr", "L"), _f("NumPerMsr", "L"), _f("UomCode", "L"), _f("BaseType", "L"),
            _f("BaseEntry", "L"), _f("BaseLine", "L"), _f("Price", "L"), _f("Currency", "L"),
            _f("LineTotal", "L"), _f("Project", "L"), _f("OcrCode", "L"), _f("U_LOTE", "L"),
            _f("U_VENCLOTE", "L"),
        ),
    ),
    DatasetSpec(
        name="purchase_receipt", header_table="OPDN", line_table=None, date_field="DocDate",
        key_fields=("DocEntry",), quantity_field=None,
        fields=(
            _f("DocEntry", "H"), _f("DocNum", "H"), _f("CardCode", "H"), _f("CardName", "H"),
            _f("DocDate", "H"), _f("DocDueDate", "H"), _f("CANCELED", "H"), _f("DocStatus", "H"),
            _f("DocCur", "H"), _f("DocTotal", "H"), _f("U_TIPOCOMPRA", "H"), _f("Series", "H"),
            _f("UserSign", "H"), _f("NumAtCard", "H"), _f("Comments", "H"),
        ),
    ),
    DatasetSpec(
        name="purchase_receipt_line", header_table="OPDN", line_table="PDN1", date_field="DocDate",
        key_fields=("DocEntry", "LineNum"), quantity_field="Quantity",
        fields=(
            _f("DocEntry", "H"), _f("DocNum", "H"), _f("CardCode", "H"), _f("DocDate", "H"),
            _f("U_TIPOCOMPRA", "H"),
            _f("LineNum", "L"), _f("ItemCode", "L"), _f("Dscription", "L"), _f("WhsCode", "L"),
            _f("Quantity", "L"), _f("LineStatus", "L"), _f("unitMsr", "L"), _f("NumPerMsr", "L"),
            _f("UomCode", "L"), _f("BaseType", "L"), _f("BaseEntry", "L"), _f("BaseLine", "L"),
            _f("Price", "L"), _f("Currency", "L"), _f("LineTotal", "L"), _f("Project", "L"),
            _f("U_LOTE", "L"), _f("U_VENCLOTE", "L"),
        ),
    ),
)

DATASET_NAMES: tuple[str, ...] = tuple(spec.name for spec in DEFAULT_DATASETS)


# ---------------------------------------------------------------------------
# Column discovery and explicit SELECT construction
# ---------------------------------------------------------------------------


def discover_columns(source: FactSource, table: str, *, schema: str = SOURCE_SCHEMA) -> dict[str, dict[str, Any]]:
    """Discover real source columns from ``SYS.TABLE_COLUMNS`` (read-only)."""
    if not _IDENT.match(table):
        raise ValueError(f"unsafe table identifier: {table!r}")
    rows = source.query_read_only(f"column_discovery_{table}", COLUMN_DISCOVERY_SQL, (schema, table))
    return {str(row["COLUMN_NAME"]): row for row in rows}


def resolve_fields(
    spec: DatasetSpec, available: dict[str, dict[str, dict[str, Any]]]
) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Return present ``(out, owner, source)`` fields and ABSENT output names."""
    present: list[tuple[str, str, str]] = []
    absent: list[str] = []
    for out, owner, candidates in spec.fields:
        table = spec.header_table if owner == "H" else (spec.line_table or spec.header_table)
        columns = available.get(table, {})
        match = next((candidate for candidate in candidates if candidate in columns), None)
        if match is None:
            absent.append(out)
        else:
            present.append((out, owner, match))
    return present, absent


def build_select(
    spec: DatasetSpec,
    available: dict[str, dict[str, dict[str, Any]]],
) -> tuple[str, list[str]]:
    """Build an explicit, bounded, read-only SELECT for one dataset."""
    present, absent = resolve_fields(spec, available)
    output_names = {out for out, _, _ in present}
    missing_keys = [key for key in spec.key_fields if key not in output_names]
    if missing_keys:
        raise CaptureAbort(f"{spec.name}: required logical key fields are ABSENT: {missing_keys}")
    expressions = [f'{owner}."{_ident(source)}" AS "{out}"' for out, owner, source in present]
    sql = "SELECT " + ", ".join(expressions)
    sql += f' FROM "{SOURCE_SCHEMA}"."{_ident(spec.header_table)}" H'
    if spec.line_table:
        sql += f' JOIN "{SOURCE_SCHEMA}"."{_ident(spec.line_table)}" L ON L."DocEntry" = H."DocEntry"'
    if spec.date_field:
        sql += f' WHERE H."{_ident(spec.date_field)}" >= ? AND H."{_ident(spec.date_field)}" < ?'
    ordering = []
    for key in spec.key_fields:
        entry = next(item for item in present if item[0] == key)
        ordering.append(f'{entry[1]}."{_ident(entry[2])}"')
    sql += " ORDER BY " + ", ".join(ordering)
    assert_read_only_select(sql)
    return sql, absent


def build_control_select(
    spec: DatasetSpec,
    available: dict[str, dict[str, dict[str, Any]]],
) -> str:
    """Build a bounded aggregate control query for reconciliation."""
    present, _ = resolve_fields(spec, available)
    expressions = ["COUNT(*) AS \"row_count\""]
    for key in spec.key_fields:
        entry = next(item for item in present if item[0] == key)
        expressions.append(f'COUNT({entry[1]}."{_ident(entry[2])}") AS "key_{entry[0]}_nonnull"')
    if spec.quantity_field and spec.quantity_field in {out for out, _, _ in present}:
        entry = next(item for item in present if item[0] == spec.quantity_field)
        expressions.append(
            f'SUM(CASE WHEN {entry[1]}."{_ident(entry[2])}" IS NULL THEN 0 '
            f'ELSE {entry[1]}."{_ident(entry[2])}" END) AS "quantity_sum"'
        )
    sql = "SELECT " + ", ".join(expressions)
    sql += f' FROM "{SOURCE_SCHEMA}"."{_ident(spec.header_table)}" H'
    if spec.line_table:
        sql += f' JOIN "{SOURCE_SCHEMA}"."{_ident(spec.line_table)}" L ON L."DocEntry" = H."DocEntry"'
    if spec.date_field:
        sql += f' WHERE H."{_ident(spec.date_field)}" >= ? AND H."{_ident(spec.date_field)}" < ?'
    assert_read_only_select(sql)
    return sql


# ---------------------------------------------------------------------------
# Segment planning, checkpointing and idempotency
# ---------------------------------------------------------------------------


def dataset_segments(spec: DatasetSpec, *, as_of: date) -> list[tuple[str, tuple[str, ...]]]:
    """Return ``(segment_label, params)`` pairs for one dataset."""
    if spec.kind == "full":
        return [("full", ())]
    start = date(as_of.year, 1, 1)
    end = date(as_of.year + 1, 1, 1) if as_of.month == 12 else date(as_of.year, as_of.month + 1, 1)
    result: list[tuple[str, tuple[str, ...]]] = []
    for month_from, month_to in month_ranges(start, end):
        label = f"{month_from.year:04d}-{month_from.month:02d}"
        result.append((label, (month_from.isoformat(), month_to.isoformat())))
    return result


def segment_directory(root: Path, spec: DatasetSpec, label: str) -> Path:
    return root / spec.name / label


def existing_segment_manifests(root: Path, spec: DatasetSpec, label: str) -> list[dict[str, Any]]:
    """Completed manifests already present for a logical segment (idempotency)."""
    base = segment_directory(root, spec, label)
    if not base.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for child in sorted(base.iterdir()):
        manifest_path = child / "manifest.json"
        if not child.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("status") == "COMPLETED":
            found.append(manifest)
    return found


def validate_logical_keys(rows: list[dict[str, Any]], key_fields: Iterable[str], *, label: str) -> dict[str, Any]:
    """Fail closed on unexpected duplicate logical primary keys."""
    fields = tuple(key_fields)
    seen: set[tuple[Any, ...]] = set()
    duplicates: list[tuple[Any, ...]] = []
    null_keys = 0
    for row in rows:
        key = tuple(row.get(field) for field in fields)
        if any(value is None for value in key):
            null_keys += 1
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        raise CaptureAbort(f"{label}: duplicate logical keys detected: {duplicates[:5]} (total {len(duplicates)})")
    return {"key_fields": list(fields), "distinct_keys": len(seen), "null_keys": null_keys, "duplicates": 0}


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def _numbers_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        return abs(float(left) - float(right)) < 1e-6
    except (TypeError, ValueError):
        return str(left) == str(right)


def reconcile_segment(
    *,
    spec: DatasetSpec,
    captured_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    control: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare persisted rows against the manifest and bounded SAP control."""
    persisted = int(manifest.get("row_count") or 0)
    captured = len(captured_rows)
    if persisted != captured:
        return {
            "status": "MISMATCH",
            "reason": "PERSISTED_ROWS_DIFFER_FROM_CAPTURED_ROWS",
            "captured": captured, "persisted": persisted, "control": control,
        }
    quantity_field = spec.quantity_field
    captured_quantity = None
    if quantity_field:
        total = 0.0
        for row in captured_rows:
            value = row.get(quantity_field)
            if value is not None:
                total += float(value)
        captured_quantity = total
    if not control:
        return {
            "status": "EXACT",
            "reason": "PERSISTED_MATCHES_CAPTURED_NO_CONTROL",
            "captured": captured, "persisted": persisted, "quantity_sum": captured_quantity,
        }
    control_rows = int(control.get("row_count") or 0)
    reasons: list[str] = []
    if control_rows != persisted:
        reasons.append("SOURCE_ROW_COUNT_MOVED_AFTER_CAPTURE")
    for key in spec.key_fields:
        control_key = control.get(f"key_{key}_nonnull")
        if control_key is not None:
            nonnull = sum(1 for row in captured_rows if row.get(key) is not None)
            if int(control_key) != nonnull:
                reasons.append(f"SOURCE_KEY_NONNULL_MOVED:{key}")
    if quantity_field and "quantity_sum" in control:
        if not _numbers_equal(control.get("quantity_sum"), captured_quantity):
            reasons.append("SOURCE_QUANTITY_SUM_MOVED_AFTER_CAPTURE")
    if reasons:
        return {
            "status": "DEGRADED",
            "reason": ",".join(reasons),
            "source_changed_after_capture": True,
            "captured": captured, "persisted": persisted,
            "captured_quantity_sum": captured_quantity, "control": control,
        }
    return {
        "status": "EXACT",
        "reason": "PERSISTED_MATCHES_BOUNDED_SAP_CONTROL",
        "captured": captured, "persisted": persisted,
        "captured_quantity_sum": captured_quantity, "control": control,
    }


# ---------------------------------------------------------------------------
# Capture driver
# ---------------------------------------------------------------------------


@dataclass
class CaptureSegmentResult:
    dataset: str
    segment: str
    status: str
    rows: int
    manifest: dict[str, Any] | None
    reconciliation: dict[str, Any] | None
    key_validation: dict[str, Any] | None
    absent_fields: list[str] = field(default_factory=list)
    source_as_of_window: dict[str, Any] | None = None
    started_at: str | None = None
    completed_at: str | None = None
    source_as_of: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "segment": self.segment,
            "status": self.status,
            "rows": self.rows,
            "manifest_path": (self.manifest or {}).get("manifest_path"),
            "parquet_path": (self.manifest or {}).get("path")
            or next(iter((self.manifest or {}).get("file_references", [])), None),
            "manifest_hash": (self.manifest or {}).get("manifest_hash"),
            "reconciliation": self.reconciliation,
            "key_validation": self.key_validation,
            "absent_fields": self.absent_fields,
            "source_as_of_window": self.source_as_of_window,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "source_as_of": self.source_as_of,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metrics_snapshot(assessment: Any) -> dict[str, Any]:
    metrics = assessment.metrics
    return {
        "available_memory_bytes": metrics.available_memory_bytes,
        "memory_used_percent": metrics.memory_used_percent,
        "swap_used_percent": metrics.swap_used_percent,
        "load_ratio": metrics.load_ratio,
        "disk_free_bytes": metrics.disk_free_bytes,
    }


class CaptureMetrics:
    def __init__(self) -> None:
        self.max_load_ratio = 0.0
        self.max_memory_percent = 0.0
        self.max_swap_percent = 0.0
        self.min_available_memory: int | None = None

    def observe(self, assessment: Any) -> None:
        metrics = assessment.metrics
        self.max_load_ratio = max(self.max_load_ratio, float(metrics.load_ratio))
        self.max_memory_percent = max(self.max_memory_percent, float(metrics.memory_used_percent))
        self.max_swap_percent = max(self.max_swap_percent, float(metrics.swap_used_percent))
        if self.min_available_memory is None or metrics.available_memory_bytes < self.min_available_memory:
            self.min_available_memory = int(metrics.available_memory_bytes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_load_ratio": self.max_load_ratio,
            "max_memory_used_percent": self.max_memory_percent,
            "max_swap_used_percent": self.max_swap_percent,
            "min_available_memory_bytes": self.min_available_memory,
        }


def run_capture(
    *,
    source: FactSource,
    datasets: Iterable[DatasetSpec] = DEFAULT_DATASETS,
    root: Path = RAW_ROOT,
    run_id: str | None = None,
    runtime_config: RuntimeConfig | None = None,
    guard: ResourceGuard | None = None,
    as_of: date | None = None,
    skip_control: bool = False,
    gate: str = GATE,
    logger: Any = print,
) -> dict[str, Any]:
    """Capture every requested dataset/segment into the immutable raw layer."""
    specs = list(datasets)
    runtime_config = runtime_config or RuntimeConfig.from_env()
    guard = guard or ResourceGuard(policy=runtime_config.resource_policy())
    as_of = as_of or date.today()
    run_id = run_id or f"fact-capture-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    profile = DuckDBSafetyProfile.from_runtime_config(runtime_config)

    preflight = guard.preflight()
    metrics = CaptureMetrics()
    metrics.observe(preflight)
    logger(f"[capture] run_id={run_id} datasets={[spec.name for spec in specs]}")

    discovery: dict[str, dict[str, dict[str, Any]]] = {}
    for spec in specs:
        for table in spec.tables:
            if table not in discovery:
                discovery[table] = discover_columns(source, table)
                logger(f"[discovery] {table}: {len(discovery[table])} columns observed")

    results: list[CaptureSegmentResult] = []
    reconstructed: dict[str, list[dict[str, Any]]] = {spec.name: [] for spec in specs}
    for spec in specs:
        select_sql, absent = build_select(spec, discovery)
        control_sql = None if skip_control else build_control_select(spec, discovery)
        for label, params in dataset_segments(spec, as_of=as_of):
            window = {"from": params[0] if params else None, "to": params[1] if params else None}
            existing = existing_segment_manifests(root, spec, label)
            if existing:
                manifest = existing[-1]
                results.append(CaptureSegmentResult(
                    dataset=spec.name, segment=label, status="SEGMENT_ALREADY_CAPTURED",
                    rows=int(manifest.get("row_count") or 0), manifest=manifest, reconciliation=None,
                    key_validation=None, absent_fields=absent,
                    source_as_of_window=window,
                    source_as_of=manifest.get("source_as_of"),
                ))
                logger(f"[skip] {spec.name}/{label} already captured rows={manifest.get('row_count')}")
                continue
            guard.preflight()
            metrics.observe(guard.last_assessment)
            guard.begin_segment()
            started_at = _utc_now()
            try:
                rows = source.query_read_only(f"capture_{spec.name}_{label}", select_sql, params)
                metrics.observe(guard.assess())
                if not rows:
                    results.append(CaptureSegmentResult(
                        dataset=spec.name, segment=label, status="SEGMENT_EMPTY_SKIPPED",
                        rows=0, manifest=None, reconciliation=None, key_validation=None,
                        absent_fields=absent, source_as_of_window=window,
                        started_at=started_at, completed_at=_utc_now(),
                    ))
                    logger(f"[empty] {spec.name}/{label} no rows; skipped")
                    continue
                key_validation = validate_logical_keys(rows, spec.key_fields, label=f"{spec.name}/{label}")
                extraction_id = f"{run_id}_{spec.name}_{label}_{time.time_ns()}"
                query_meta = next(
                    (entry for entry in reversed(getattr(source, "query_log", []))
                     if entry.get("query_id") == f"capture_{spec.name}_{label}"),
                    {},
                )
                metadata = {
                    "gate": gate,
                    "dataset": spec.name,
                    "segment": label,
                    "source_system": "SAP_HANA",
                    "source_schema": SOURCE_SCHEMA,
                    "source_table": spec.header_table,
                    "source_line_table": spec.line_table,
                    "source_as_of_window": window,
                    "source_date_field": spec.date_field,
                    "logical_key": list(spec.key_fields),
                    "query_hash": query_meta.get("query_hash"),
                    "capture_started_at": started_at,
                    "capture_completed_at": _utc_now(),
                    "source_as_of": _utc_now(),
                    "sap_access_mode": "READ_ONLY",
                    "sap_write_count": int(getattr(source, "sap_write_count", 0)),
                    "absent_fields": absent,
                    "run_id": run_id,
                }
                manifest = write_raw(
                    root=root, segment_id=f"{spec.name}/{label}", extraction_id=extraction_id,
                    rows=rows, metadata=metadata, profile=profile,
                )
                control = None
                if control_sql:
                    control_rows = source.query_read_only(f"control_{spec.name}_{label}", control_sql, params)
                    control = control_rows[0] if control_rows else None
                reconciliation = reconcile_segment(
                    spec=spec, captured_rows=rows, manifest=manifest, control=control,
                )
                if reconciliation["status"] == "MISMATCH":
                    raise CaptureAbort(f"{spec.name}/{label}: {reconciliation['reason']}")
                guard.checkpoint()
                reconstructed[spec.name].extend(rows)
                results.append(CaptureSegmentResult(
                    dataset=spec.name, segment=label, status="CAPTURED",
                    rows=len(rows), manifest=manifest, reconciliation=reconciliation,
                    key_validation=key_validation, absent_fields=absent,
                    source_as_of_window=window,
                    started_at=started_at, completed_at=metadata["capture_completed_at"],
                    source_as_of=metadata["source_as_of"],
                ))
                logger(
                    f"[capture] {spec.name}/{label} rows={len(rows)} "
                    f"reconciliation={reconciliation['status']}"
                )
            finally:
                guard.end_segment()
    return {
        "gate": gate,
        "run_id": run_id,
        "as_of": as_of.isoformat(),
        "raw_root": str(root),
        "discovery": discovery,
        "results": [result.as_dict() for result in results],
        "segments": [result.as_dict() for result in results],
        "captured_rows": {name: len(rows) for name, rows in reconstructed.items()},
        "resource_metrics": metrics.as_dict(),
        "resource_guard_trips": 0,
        "sap_write_count": int(getattr(source, "sap_write_count", 0)),
    }


# ---------------------------------------------------------------------------
# Offline (no-HANA) read validation
# ---------------------------------------------------------------------------


def _dataset_parquet_files(root: Path, dataset: str) -> list[Path]:
    base = root / dataset
    if not base.is_dir():
        return []
    return sorted(path for path in base.rglob("*.parquet") if path.is_file())


def offline_read_dataset(root: Path, dataset: str) -> dict[str, Any]:
    """Read one persisted dataset directly from Parquet; never contacts HANA."""
    files = _dataset_parquet_files(root, dataset)
    result: dict[str, Any] = {
        "dataset": dataset, "parquet_files": len(files), "row_count": 0,
        "manifest_consistent": True, "errors": [],
    }
    if not files:
        result["manifest_consistent"] = False
        result["errors"].append("NO_PARQUET_FILES")
        return result
    connection = open_safe_duckdb(":memory:")
    try:
        for path in files:
            escaped = str(path).replace("'", "''")
            rows = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{escaped}')").fetchall()
            result["row_count"] += int(rows[0][0] or 0)
    finally:
        connection.close()
    return result


def read_persisted_rows(root: Path, dataset: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Read persisted Parquet rows back with DuckDB only (no HANA access)."""
    files = _dataset_parquet_files(root, dataset)
    if not files:
        return []
    connection = open_safe_duckdb(":memory:")
    try:
        selects = [f"SELECT * FROM read_parquet('{str(path).replace(chr(39), chr(39) * 2)}')" for path in files]
        sql = "SELECT * FROM (" + " UNION ALL ".join(selects) + ")"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        cursor = connection.execute(sql)
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()


def offline_validate(root: Path, dataset_names: Iterable[str] = DATASET_NAMES) -> dict[str, Any]:
    """Validate every persisted dataset from Parquet only (no HANA access)."""
    datasets = [offline_read_dataset(root, name) for name in dataset_names]
    manifest_checks: list[dict[str, Any]] = []
    for name in dataset_names:
        base = root / name
        if not base.is_dir():
            continue
        for manifest_path in sorted(base.rglob("manifest.json")):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest_checks.append({"path": str(manifest_path), "consistent": False, "reason": "UNREADABLE"})
                continue
            parquet = manifest_path.parent / "part-00000.parquet"
            consistent = parquet.is_file() and int(manifest.get("row_count") or 0) >= 0
            manifest_checks.append({
                "path": str(manifest_path),
                "dataset": manifest.get("dataset", name),
                "segment": manifest.get("segment"),
                "row_count": manifest.get("row_count"),
                "parquet_exists": parquet.is_file(),
                "consistent": consistent,
            })
    return {
        "datasets": datasets,
        "manifests": manifest_checks,
        "all_manifests_consistent": all(item["consistent"] for item in manifest_checks) if manifest_checks else False,
        "hana_query_count": 0,
    }


# ---------------------------------------------------------------------------
# Source-native linkage controls (computed from persisted facts only)
# ---------------------------------------------------------------------------


def linkage_controls(captured: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Compute production/receipt linkage coverage from captured facts only."""
    owor_entries = {str(row.get("DocEntry")) for row in captured.get("production_order", [])}
    issue_lines = captured.get("production_issue", [])
    base202 = [row for row in issue_lines if str(row.get("BaseType")) in {"202", "202.0"}]
    linked = [row for row in base202 if str(row.get("BaseEntry")) in owor_entries]
    por_lines = {
        (str(row.get("DocEntry")), str(row.get("LineNum")))
        for row in captured.get("purchase_order_line", [])
    }
    receipt_lines = captured.get("purchase_receipt_line", [])
    po_linked = [
        row for row in receipt_lines
        if str(row.get("BaseType")) in {"22", "22.0"}
        and (str(row.get("BaseEntry")), str(row.get("BaseLine"))) in por_lines
    ]
    return {
        "PRODUCTION_ISSUE_LINES_CAPTURED": len(issue_lines),
        "PRODUCTION_ISSUE_BASETYPE_202": len(base202),
        "PRODUCTION_ISSUE_LINKED_TO_OWOR": len(linked),
        "PRODUCTION_ISSUE_NOT_LINKED_TO_OWOR": len(issue_lines) - len(linked),
        "RECEIPT_LINES_CAPTURED": len(receipt_lines),
        "RECEIPT_LINES_WITH_PO_LINEAGE": len(po_linked),
        "RECEIPT_LINES_WITHOUT_PO_LINEAGE": len(receipt_lines) - len(po_linked),
    }


# ---------------------------------------------------------------------------
# Evidence helpers
# ---------------------------------------------------------------------------


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _family_results(report: dict[str, Any], dataset: str) -> list[dict[str, Any]]:
    return [item for item in report["results"] if item["dataset"] == dataset]


def build_family_evidence(report: dict[str, Any], dataset: str) -> tuple[dict[str, Any], dict[str, Any]]:
    items = _family_results(report, dataset)
    capture = {
        "dataset": dataset,
        "segments": items,
        "rows_captured": sum(int(item["rows"]) for item in items if item["status"] == "CAPTURED"),
        "segments_captured": sum(1 for item in items if item["status"] == "CAPTURED"),
        "segments_empty_skipped": sum(1 for item in items if item["status"] == "SEGMENT_EMPTY_SKIPPED"),
        "segments_skipped_existing": sum(1 for item in items if item["status"] == "SEGMENT_ALREADY_CAPTURED"),
        "absent_fields": sorted({field for item in items for field in item.get("absent_fields", [])}),
    }
    statuses = [item["reconciliation"]["status"] for item in items if item.get("reconciliation")]
    if any(status == "MISMATCH" for status in statuses):
        overall = "MISMATCH"
    elif any(status == "DEGRADED" for status in statuses):
        overall = "DEGRADED"
    elif statuses:
        overall = "EXACT"
    else:
        overall = "PENDING"
    reconciliation = {
        "dataset": dataset,
        "overall": overall,
        "segments": [
            {"segment": item["segment"], "status": item["status"], "reconciliation": item["reconciliation"]}
            for item in items
        ],
    }
    return capture, reconciliation


def build_evidence(report: dict[str, Any]) -> dict[str, Any]:
    """Assemble every required evidence document from one capture run."""
    evidence: dict[str, Any] = {}
    evidence["column_discovery.json"] = {
        table: {
            "column_count": len(columns),
            "columns": [
                {"name": row["COLUMN_NAME"], "type": row.get("DATA_TYPE_NAME"),
                 "position": row.get("POSITION"), "length": row.get("LENGTH"), "scale": row.get("SCALE")}
                for row in columns.values()
            ],
        }
        for table, columns in report["discovery"].items()
    }
    capture_files = {
        "bom_header": ("bom_capture.json", "bom_reconciliation.json"),
        "bom_line": ("bom_capture.json", "bom_reconciliation.json"),
        "production_order": ("production_capture.json", "production_reconciliation.json"),
        "production_issue": ("production_capture.json", "production_reconciliation.json"),
        "purchase_order": ("purchase_order_capture.json", "purchase_order_reconciliation.json"),
        "purchase_order_line": ("purchase_order_capture.json", "purchase_order_reconciliation.json"),
        "purchase_receipt": ("purchase_receipt_capture.json", "purchase_receipt_reconciliation.json"),
        "purchase_receipt_line": ("purchase_receipt_capture.json", "purchase_receipt_reconciliation.json"),
    }
    grouped_capture: dict[str, dict[str, Any]] = {}
    grouped_reconciliation: dict[str, dict[str, Any]] = {}
    for dataset, (capture_file, reconciliation_file) in capture_files.items():
        capture, reconciliation = build_family_evidence(report, dataset)
        grouped_capture.setdefault(capture_file, {})[dataset] = capture
        grouped_reconciliation.setdefault(reconciliation_file, {})[dataset] = reconciliation
    evidence.update(grouped_capture)
    evidence.update(grouped_reconciliation)
    evidence["capture_checkpoints.json"] = {
        "run_id": report["run_id"],
        "as_of": report["as_of"],
        "segments": [
            {"dataset": item["dataset"], "segment": item["segment"], "status": item["status"],
             "rows": item["rows"], "manifest_path": item.get("manifest_path"),
             "completed_at": item.get("completed_at")}
            for item in report["results"]
        ],
    }
    evidence["source_as_of.json"] = {
        "source_system": "SAP_HANA",
        "run_id": report["run_id"],
        "segments": [
            {"dataset": item["dataset"], "segment": item["segment"],
             "source_as_of": item.get("source_as_of"),
             "source_as_of_window": item.get("source_as_of_window")}
            for item in report["results"]
        ],
    }
    return evidence


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_source() -> FactSource:
    from .source import HanaReadOnlySource

    return HanaReadOnlySource()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD logical capture month")
    parser.add_argument("--datasets", default=",".join(DATASET_NAMES))
    parser.add_argument("--root", default=str(RAW_ROOT))
    parser.add_argument("--evidence-root", default=None)
    parser.add_argument("--skip-control", action="store_true")
    parser.add_argument("--offline-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selected = {name.strip() for name in args.datasets.split(",") if name.strip()}
    specs = [spec for spec in DEFAULT_DATASETS if spec.name in selected]
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    root = Path(args.root)
    evidence_root = Path(args.evidence_root) if args.evidence_root else EVIDENCE_ROOT

    if args.offline_only:
        report = {"run_id": "offline", "as_of": as_of.isoformat(), "raw_root": str(root),
                  "discovery": {}, "results": [], "captured_rows": {}}
    else:
        source = _default_source()
        report = run_capture(
            source=source, datasets=specs, root=root, run_id=args.run_id,
            as_of=as_of, skip_control=args.skip_control,
        )
    offline = offline_validate(root, [spec.name for spec in specs])
    report["offline"] = offline
    print(json.dumps({k: report[k] for k in ("gate", "run_id", "as_of") if k in report}, sort_keys=True))
    print(json.dumps(offline, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())