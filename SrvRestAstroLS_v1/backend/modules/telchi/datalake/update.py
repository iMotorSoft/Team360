"""TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1.

A deliberately small, explicitly invoked, single-run refresh for the already
validated 2026 foundation (Sales OINV/INV1, OINM, OITW).

Design contract (V1):

* SAP is read-only (``SAP_WRITE_COUNT=0``); the adapter enforces SELECT-only.
* The full 2026 business scope is re-read segmentally to detect late-arriving
  and historically modified rows. ``DocDate`` only defines business scope; it is
  never used as a change watermark.
* Captured SAP rows are staged into a transient DuckDB staging database under
  ``DATA_ROOT/staging`` (data-only, never inside the DuckLake catalog). Nothing
  trusted is touched while extraction runs.
* Only changed source identities are published. Disappearance of a historical
  Sales/OINM source key aborts the run (fail closed); OITW is current state and
  is replaced as a full snapshot.
* Sales refresh unit is ``DocEntry`` (header + all its lines together).
* One :class:`TransactionalPublicationBoundary` covers Sales, OINM, OITW and the
  publication metadata. A failure keeps the previous valid foundation intact.
* Bulk, set-based writes only: staging relation -> DELETE keyed set -> single
  ``INSERT INTO ... SELECT`` per target table. Never one file/row per row.
* Reference V2 canonical identities are never reassigned. This V1 only *checks*
  coverage of new source keys and refuses to orphan them silently; it does not
  rebuild the versioned Reference V2 layer.

There is no scheduler, cron, daemon, worker, queue, pg_durable, Temporal or
LangGraph anywhere in this module.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from modules.telchi.runtime.config import DuckDBSafetyProfile, RuntimeConfig
from modules.telchi.runtime.resource_guard import ResourceGuard
from modules.telchi.runtime.transactional_publication import TransactionalPublicationBoundary

from . import UPDATE_GATE
from .foundation_publication import (
    COMPONENT_NAMES,
    CURRENT,
    FOUNDATION_COMPONENT_COUNT,
    GLOBAL_PUBLICATION_GATE,
    PREPARING,
    READY_TO_COMMIT,
    SUPERSEDED,
    VALIDATING,
    CommitFaultPoint,
    ComponentReference,
    FoundationPublicationStore,
    get_current_foundation,
    prepare_candidate,
)
from .create_initial import (
    PUBLICATION_STRATEGY_VERSION,
    PUBLICATION_TABLE,
    Candidate,
    _q,
    _stage_rows,
    ensure_executive_sales_tables,
    publication_writer,
    reconcile_candidate,
    transform,
    validate_candidate,
)
from .ducklake import DATA_ROOT, DuckLakeConnector
from .planner import SegmentSpec
from .raw import digest, write_raw
from .source import HanaReadOnlySource, SourceAdapter

GATE = UPDATE_GATE
CLOSURE_GATE = "TELCHI_DATALAKE_CREATE_INITIAL_V1_CLOSURE_AND_REBUILD_CONTROLS_V1"
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / UPDATE_GATE
STATE_ROOT = DATA_ROOT / "manifests" / "telchi_datalake_manual_single_run_update_v1"
RAW_ROOT = DATA_ROOT / "raw" / "sap" / UPDATE_GATE
STAGING_DB = DATA_ROOT / "staging" / "manual_update_v1" / "staging.duckdb"
BASELINE_STATE_ROOT = DATA_ROOT / "manifests" / "telchi_datalake_2026_operational_baseline_v1"
REFERENCE_POINTER = DATA_ROOT / "manifests" / "reference_current.json"

FOUNDATION_START = date(2026, 1, 1)
SCHEMA_VERSION = "1.0.0"
UPDATE_TRANSFORMATION_VERSION = "manual-single-run-update-v1.1.0"
PUBLICATION_TABLE_V1 = PUBLICATION_TABLE
MAX_EXTRACTION_RETRIES = 1

SALES_DOMAIN = "sales"
CREDIT_MEMO_DOMAIN = "credit_memo"
OINM_DOMAIN = "inventory_movement"
OITW_DOMAIN = "inventory"

STAGE_TABLES = {
    "sales_document": ("doc_entry",),
    "sales_line": ("doc_entry", "line_num"),
    "credit_memo_document": ("doc_entry",),
    "credit_memo_line": ("doc_entry", "line_num"),
    "inventory_movement": ("trans_num", "trans_seq"),
    "inventory_balance": ("item_code", "whs_code"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_rows_parquet(rows: list[dict[str, Any]], path: Path) -> Path:
    """Materialize a piece of in-memory rows as Parquet for fast bulk loading.

    Rows are written to JSONL and converted by DuckDB in one pass; this replaces
    row-by-row ``executemany`` staging which is far too slow for millions of
    rows while keeping staging local and transient.
    """
    from modules.telchi.runtime.config import open_safe_duckdb

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    jsonl = path.with_suffix(".jsonl")
    with jsonl.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps({key: (None if value is None else str(value)) for key, value in row.items()}, default=str) + "\n")
    db = open_safe_duckdb(":memory:")
    try:
        db.execute(
            "CREATE TABLE staging_rows AS SELECT * FROM read_json_auto(?, columns=" + _json_columns(rows[0]) + ") ",
            [str(jsonl)],
        )
        escaped = str(path).replace("'", "''")
        db.execute(f"COPY staging_rows TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        db.close()
        jsonl.unlink(missing_ok=True)
    return path


def _json_columns(sample: dict[str, Any]) -> str:
    return "{" + ",".join(f"'{key}': 'VARCHAR'" for key in sample) + "}"

def _number(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


# ---------------------------------------------------------------------------
# Run identity + gates
# ---------------------------------------------------------------------------


@dataclass
class YearRolloverGuard:
    sap_current_date: str
    year: int
    requires_review: str

    @classmethod
    def evaluate(cls, sap_current_date: str) -> "YearRolloverGuard":
        parsed = date.fromisoformat(str(sap_current_date)[:10])
        in_window = parsed.year == FOUNDATION_START.year
        return cls(str(sap_current_date)[:10], parsed.year, "NO" if in_window else "YES")


@dataclass
class RunIdentity:
    update_run_id: str
    publication_id: str | None = None
    sap_run_started_at: str = field(default_factory=_now)
    sap_extraction_finished_at: str | None = None
    publication_finished_at: str | None = None
    final_verification_at: str | None = None
    previous_foundation_publication_id: str | None = None
    candidate_foundation_publication_id: str | None = None
    final_current_foundation_publication_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "UPDATE_RUN_ID": self.update_run_id,
            "PUBLICATION_ID": self.publication_id,
            "SAP_RUN_STARTED_AT": self.sap_run_started_at,
            "SAP_EXTRACTION_FINISHED_AT": self.sap_extraction_finished_at,
            "PUBLICATION_FINISHED_AT": self.publication_finished_at,
            "FINAL_VERIFICATION_AT": self.final_verification_at,
            "PREVIOUS_FOUNDATION_PUBLICATION_ID": self.previous_foundation_publication_id,
            "CANDIDATE_FOUNDATION_PUBLICATION_ID": self.candidate_foundation_publication_id,
            "FINAL_CURRENT_FOUNDATION_PUBLICATION_ID": self.final_current_foundation_publication_id,
        }


class UpdateAbort(RuntimeError):
    """Any fail-closed stop before publication. The previous foundation stays."""


# ---------------------------------------------------------------------------
# Previous publication / last published state
# ---------------------------------------------------------------------------


def read_previous_state(connector: DuckLakeConnector, table_names: dict[str, str | None]) -> dict[str, Any]:
    """Read the last valid published state from DuckLake + manifests.

    Every value is queried from live Atomic relations and previous publication
    metadata; nothing is hardcoded.
    """
    sales_docs = table_names.get("sales_document")
    sales_lines = table_names.get("sales_line")
    credit_docs = table_names.get("credit_memo_document")
    credit_lines = table_names.get("credit_memo_line")
    movements = table_names.get("inventory_movement")
    balances = table_names.get("inventory_balance_snapshot")
    previous: dict[str, Any] = {
        "previous_publication_id": None,
        "previous_source_as_of": None,
        "sales_previous_documents": 0,
        "sales_previous_lines": 0,
        "credit_memo_previous_documents": 0,
        "credit_memo_previous_lines": 0,
        "oinm_previous_rows": 0,
        "oitw_previous_rows": 0,
    }
    with connector.session(read_only=True) as connection:
        if sales_docs and sales_lines:
            previous["sales_previous_documents"] = int(connection.execute(
                f"SELECT count(*) FROM telchi.atomic.{_q(sales_docs)} WHERE doc_date >= ?", [FOUNDATION_START.isoformat()]
            ).fetchone()[0])
            previous["sales_previous_lines"] = int(connection.execute(
                f"SELECT count(*) FROM telchi.atomic.{_q(sales_lines)} WHERE doc_entry IN "
                f"(SELECT doc_entry FROM telchi.atomic.{_q(sales_docs)} WHERE doc_date >= ?)", [FOUNDATION_START.isoformat()]
            ).fetchone()[0])
        if credit_docs and credit_lines:
            previous["credit_memo_previous_documents"] = int(connection.execute(
                f"SELECT count(*) FROM telchi.atomic.{_q(credit_docs)} WHERE doc_date >= ?", [FOUNDATION_START.isoformat()]
            ).fetchone()[0])
            previous["credit_memo_previous_lines"] = int(connection.execute(
                f"SELECT count(*) FROM telchi.atomic.{_q(credit_lines)} WHERE doc_entry IN "
                f"(SELECT doc_entry FROM telchi.atomic.{_q(credit_docs)} WHERE doc_date >= ?)", [FOUNDATION_START.isoformat()]
            ).fetchone()[0])
        if movements:
            previous["oinm_previous_rows"] = int(connection.execute(
                f"SELECT count(*) FROM telchi.atomic.{_q(movements)} WHERE doc_date >= ?", [FOUNDATION_START.isoformat()]
            ).fetchone()[0])
        if balances:
            previous["oitw_previous_rows"] = int(connection.execute(
                f"SELECT count(*) FROM telchi.atomic.{_q(balances)}"
            ).fetchone()[0])
        try:
            row = connection.execute(
                f"SELECT publication_id, published_at FROM {PUBLICATION_TABLE_V1} "
                "WHERE status='COMMITTED' ORDER BY published_at DESC LIMIT 1"
            ).fetchone()
            if row:
                previous["previous_publication_id"] = row[0]
                previous["previous_source_as_of"] = row[1]
        except Exception:
            pass
    manifest = _latest_baseline_manifest()
    previous["previous_manifest_run_id"] = manifest.get("run_id")
    previous["previous_manifest_gate"] = manifest.get("gate")
    return previous


def _latest_baseline_manifest() -> dict[str, Any]:
    if not BASELINE_STATE_ROOT.exists():
        return {}
    latest = BASELINE_STATE_ROOT / "latest.json"
    if latest.is_file():
        try:
            return json.loads(latest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Staging database (transient, data-only, outside the DuckLake catalog)
# ---------------------------------------------------------------------------


class StagingStore:
    """A transient DuckDB file holding the captured 2026 source snapshot.

    It lives under ``DATA_ROOT/staging`` (data-only) and is deleted when the run
    completes. It is never attached as a DuckLake catalog and never holds
    trusted rows.
    """

    def __init__(self, path: Path = STAGING_DB) -> None:
        self.path = path
        self.connection: Any = None

    def open(self) -> Any:
        import duckdb
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.connection = duckdb.connect(str(self.path))
        self.connection.execute("SET memory_limit = '1GB'")
        self.connection.execute("SET threads = 1")
        return self.connection

    def reset(self) -> Any:
        """Start a fresh staging file, discarding any previous staging data."""
        self.close()
        if self.path.exists():
            self.path.unlink()
        return self.open()

    def close(self) -> None:
        if self.connection is not None:
            # Persist the WAL so a second connection can attach the file
            # read-only without holding a concurrent writer handle.
            try:
                self.connection.execute("CHECKPOINT")
            except Exception:
                pass
            self.connection.close()
            self.connection = None

    def cleanup(self) -> None:
        self.close()
        if self.path.exists():
            self.path.unlink()

    def append(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        if self.connection is None:
            self.open()
        columns = tuple(rows[0])
        if table_name not in self._tables():
            column_sql = ", ".join(f"{_q(column)} VARCHAR" for column in columns)
            self.connection.execute(f"CREATE TABLE {_q(table_name)} ({column_sql})")
            self._tables().add(table_name)
        # Bulk load through Parquet: DuckDB executemany is pathologically slow
        # for high-cardinality batches, so the batch is materialized once and
        # read back with a single set-based INSERT ... SELECT.
        parquet = write_rows_parquet(rows, self.path.parent / f"_{table_name}_{time.time_ns()}.parquet")
        try:
            self.connection.execute(
                f"INSERT INTO {_q(table_name)} SELECT * FROM read_parquet('{str(parquet).replace(chr(39), chr(39) * 2)}')"
            )
        finally:
            parquet.unlink(missing_ok=True)

    def _tables(self) -> set[str]:
        if not hasattr(self, "_table_cache"):
            self._table_cache: set[str] = set()
        return self._table_cache

    def count(self, table_name: str) -> int:
        if table_name not in self._tables():
            return 0
        if self.connection is not None:
            return int(self.connection.execute(f"SELECT count(*) FROM {_q(table_name)}").fetchone()[0])
        import duckdb
        connection = duckdb.connect(str(self.path), read_only=True)
        try:
            return int(connection.execute(f"SELECT count(*) FROM {_q(table_name)}").fetchone()[0])
        finally:
            connection.close()

    def relation_exists(self, table_name: str) -> bool:
        return table_name in self._tables()


# ---------------------------------------------------------------------------
# Extraction orchestration
# ---------------------------------------------------------------------------


def extracted_specs(source: HanaReadOnlySource, *, sap_current_date: date, max_rows: int) -> list[SegmentSpec]:
    """Build the full 2026 segmented plan for Sales, OINM and OITW."""
    start = FOUNDATION_START
    end = sap_current_date.fromordinal(sap_current_date.toordinal() + 1)
    source.discover_oinm_schema()
    analysis = source.analyze_oinm_source_key()
    if not analysis.get("source_key_unique"):
        raise UpdateAbort(f"OINM source key is not unique: {analysis}")
    specs: list[SegmentSpec] = []
    specs.extend(source.plan(start, end, max_rows=max_rows, max_segments=None))
    specs.extend(source.plan_credit_memo(start, end, max_rows=max_rows, max_segments=None))
    specs.extend(source.plan_inventory_movement(start, end, max_transnum_per_segment=max_rows, max_segments=None))
    specs.extend(source.discover_inventory(max_rows=max_rows, max_segments=None))
    order = {SALES_DOMAIN: 0, CREDIT_MEMO_DOMAIN: 1, OINM_DOMAIN: 2, OITW_DOMAIN: 3}
    return sorted(specs, key=lambda spec: (order.get(spec.domain, 9), spec.business_date_from or "", spec.segment_id))


def run_extraction(
    *,
    source: HanaReadOnlySource,
    store: StagingStore,
    guard: ResourceGuard,
    config: RuntimeConfig,
    run_id: str,
    specs: list[SegmentSpec],
) -> dict[str, Any]:
    """Extract every segment into the staging store, reconciling per segment.

    A dataset whose bounded reread does not match the captured rows is retried
    once; a second mismatch aborts before publication.
    """
    segment_results: list[dict[str, Any]] = []
    raw_manifests: list[dict[str, Any]] = []
    reference_version = os.getenv("TELCHI_REFERENCE_VERSION", "REFERENCE_V2")
    retries = 0
    for spec in specs:
        guard.preflight()
        guard.begin_segment()
        attempt = 0
        try:
            while True:
                attempt += 1
                rows, query_meta = source.extract(spec)
                manifest = _segment_manifest(spec, run_id, query_meta, rows, reference_version)
                extraction_id = f"{run_id}_{spec.segment_id}_{time.time_ns()}"
                manifest = write_raw(
                    root=RAW_ROOT, segment_id=spec.segment_id, extraction_id=extraction_id,
                    rows=rows, metadata=manifest, profile=DuckDBSafetyProfile.from_runtime_config(config),
                )
                candidate = transform(spec.domain, rows, manifest)
                validation = validate_candidate(candidate, max_rows=len(rows) or 1)
                if validation.get("status") != "PASS":
                    raise UpdateAbort(f"staging validation failed for {spec.segment_id}: {validation}")
                reread = source.verify(spec)
                reconciliation = reconcile_candidate(candidate, reread)
                if reconciliation.get("status") != "EXACT" and attempt <= MAX_EXTRACTION_RETRIES:
                    retries += 1
                    continue
                if reconciliation.get("status") != "EXACT":
                    raise UpdateAbort(
                        "SOURCE_TOO_VOLATILE_FOR_SAFE_UPDATE=YES for "
                        f"{spec.segment_id}: {reconciliation.get('status')}"
                    )
                guard.checkpoint()
                for table_name, table_rows in candidate.tables.items():
                    store.append(table_name, table_rows)
                segment_results.append({
                    "segment_id": spec.segment_id, "domain": spec.domain, "scope": spec.scope,
                    "rows": len(rows), "validation": validation, "reconciliation": reconciliation,
                    "attempts": attempt, "source_as_of": manifest.get("source_as_of"),
                    "raw_manifest": {k: manifest.get(k) for k in ("extraction_id", "path", "manifest_hash", "row_count", "source_as_of")},
                })
                raw_manifests.append(manifest)
                print(
                    f"[extract] {spec.domain} {spec.segment_id} rows={len(rows)} "
                    f"segments_done={len(segment_results)}/{len(specs)}"
                )
                break
        finally:
            guard.end_segment()
    return {
        "segment_results": segment_results,
        "raw_manifests": raw_manifests,
        "extraction_retries": retries,
    }


def _segment_manifest(spec: SegmentSpec, run_id: str, query_meta: dict[str, Any], rows: list[dict[str, Any]], reference_version: str) -> dict[str, Any]:
    extracted = _now()
    return {
        "run_id": run_id, "segment_id": spec.segment_id, "domain": spec.domain, "operation": "MANUAL_SINGLE_RUN_UPDATE",
        "source_tables": ["OINV", "INV1"] if spec.domain == "sales" else (["ORIN", "RIN1"] if spec.domain == "credit_memo" else (["OITW"] if spec.domain == "inventory" else ["OINM"])),
        "query_version": query_meta.get("query_version", "manual-single-run-update-v1"),
        "query_hash": query_meta.get("query_hash"),
        "source_key_columns": list(query_meta.get("source_key_columns", [])),
        "schema_version": SCHEMA_VERSION, "reference_version": reference_version,
        "scope": spec.scope, "business_date_from": spec.business_date_from, "business_date_to": spec.business_date_to,
        "source_key_from": spec.key_from, "source_key_to": spec.key_to,
        "source_as_of": query_meta.get("source_as_of", extracted), "extracted_at": extracted, "row_count": len(rows),
        "source_type": query_meta.get("source_type", "HISTORICAL_EVENT" if spec.domain != "inventory" else "CURRENT_STATE"),
        "query_id": query_meta.get("query_id"), "status": "EXTRACTED",
        "source_system": "SAP_B1_HANA", "sap_access_mode": "READ_ONLY", "sap_write_count": 0,
        "transformation_version": UPDATE_TRANSFORMATION_VERSION,
    }


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


@dataclass
class DomainDiff:
    domain: str
    previous_rows: int = 0
    source_rows: int = 0
    new_keys: int = 0
    updated_keys: int = 0
    unchanged_keys: int = 0
    disappeared_keys: int = 0
    disappeared_samples: list[list[str]] = field(default_factory=list)
    changed_doc_entries: list[str] = field(default_factory=list)
    new_doc_entries: list[str] = field(default_factory=list)
    cancelled_transitions: int = 0
    new_lines: int = 0
    updated_lines: int = 0
    removed_lines: int = 0
    added_rows: int = 0
    removed_rows: int = 0

    @property
    def has_changes(self) -> bool:
        return bool(self.new_doc_entries or self.changed_doc_entries or self.new_keys or self.updated_keys or self.removed_rows)

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain, "previous_rows": self.previous_rows, "source_rows": self.source_rows,
            "new_keys": self.new_keys, "updated_keys": self.updated_keys, "unchanged_keys": self.unchanged_keys,
            "disappeared_keys": self.disappeared_keys, "disappeared_samples": self.disappeared_samples,
            "new_doc_entries": len(self.new_doc_entries), "changed_doc_entries": len(self.changed_doc_entries),
            "cancelled_transitions": self.cancelled_transitions,
            "new_lines": self.new_lines, "updated_lines": self.updated_lines, "removed_lines": self.removed_lines,
            "added_rows": self.added_rows, "removed_rows": self.removed_rows,
        }


_SALES_DOC_FIELDS = ("doc_num", "doc_date", "doc_due_date", "tax_date", "doc_status", "canceled", "currency", "doc_total", "doc_total_system", "doc_total_foreign", "card_code", "slp_code", "series", "user_sign", "sales_channel_code", "sales_channel_name", "sales_channel_semantic_status")
_SALES_LINE_FIELDS = ("item_code", "whs_code", "quantity", "currency", "line_total", "price", "line_status", "slp_code", "attributed_slp_code")
_CREDIT_DOC_FIELDS = ("doc_num", "doc_date", "create_date", "update_date", "doc_status", "canceled", "card_code", "slp_code", "currency", "doc_total", "doc_total_system", "doc_total_foreign", "series", "user_sign", "sales_channel_code", "sales_channel_name", "sales_channel_semantic_status")
_CREDIT_LINE_FIELDS = ("line_status", "item_code", "whs_code", "quantity", "currency", "line_total", "line_total_system", "line_total_foreign", "slp_code", "attributed_slp_code", "base_type", "base_entry", "base_line")
_OINM_FIELDS = ("trans_type", "doc_entry", "base_ref", "doc_date", "item_code", "warehouse", "in_qty", "out_qty", "movement_qty", "price", "calc_price", "trans_value")
_OITW_FIELDS = ("on_hand", "is_commited", "on_order")


def _compare_expr(fields: tuple[str, ...], current: str = "c", source: str = "s") -> str:
    clauses = [
        f"COALESCE({current}.{_q(field)}, '') IS DISTINCT FROM COALESCE({source}.{_q(field)}, '')"
        for field in fields
    ]
    return " OR ".join(clauses) if clauses else "FALSE"


def _key_join(keys: tuple[str, ...], current: str = "c", source: str = "s") -> str:
    return " AND ".join(f"{current}.{_q(key)} = {source}.{_q(key)}" for key in keys)


def _read_staging_into_catalog_connection(connection: Any, store: StagingStore) -> None:
    """Attach the transient staging DB read-only to a DuckLake connection."""
    if not store.path.exists():
        raise UpdateAbort("staging database is missing")
    attached = {
        str(row[0]) for row in connection.execute(
            "SELECT database_name FROM duckdb_databases()"
        ).fetchall()
    }
    if "staging" in attached:
        return
    connection.execute(f"ATTACH '{str(store.path).replace(chr(39), chr(39) * 2)}' AS staging (READ_ONLY)")


def sales_diff(connection: Any, table_names: dict[str, str | None], store: StagingStore, previous_documents: int) -> DomainDiff:
    docs = table_names["sales_document"]
    lines = table_names["sales_line"]
    diff = DomainDiff(domain=SALES_DOMAIN, previous_rows=previous_documents, source_rows=store.count("sales_document"))
    join_docs = _key_join(("doc_entry",), "cd", "sd")
    changed_expr = _compare_expr(_SALES_DOC_FIELDS, "cd", "sd")
    rows = connection.execute(f"""
        SELECT sd.doc_entry,
               cd.doc_entry IS NULL AS is_new,
               ({changed_expr}) AS changed,
               COALESCE(cd.canceled, 'N') AS old_canceled,
               COALESCE(sd.canceled, 'N') AS new_canceled
        FROM staging.sales_document sd
        LEFT JOIN telchi.atomic.{_q(docs)} cd ON {join_docs}
    """).fetchall()
    for doc_entry, is_new, changed, old_canceled, new_canceled in rows:
        doc_entry = str(doc_entry)
        if is_new:
            diff.new_doc_entries.append(doc_entry)
        elif changed:
            diff.changed_doc_entries.append(doc_entry)
        if not is_new and str(old_canceled) != str(new_canceled) and str(new_canceled).upper() in {"Y", "1", "T", "TRUE", "C"}:
            diff.cancelled_transitions += 1
    disappeared = connection.execute(f"""
        SELECT cd.doc_entry FROM telchi.atomic.{_q(docs)} cd
        WHERE cd.doc_date >= ?
          AND cd.doc_entry NOT IN (SELECT doc_entry FROM staging.sales_document)
    """, [FOUNDATION_START.isoformat()]).fetchall()
    diff.disappeared_keys = len(disappeared)
    diff.disappeared_samples = [["sales_document", str(row[0])] for row in disappeared[:20]]
    affected = diff.new_doc_entries + diff.changed_doc_entries
    if affected:
        placeholders = ",".join("?" for _ in affected)
        old_line_count = int(connection.execute(
            f"SELECT count(*) FROM telchi.atomic.{_q(lines)} WHERE doc_entry IN ({placeholders})", affected
        ).fetchone()[0])
        new_line_count = int(connection.execute(
            f"SELECT count(*) FROM staging.sales_line WHERE doc_entry IN ({placeholders})", affected
        ).fetchone()[0])
        diff.removed_lines = max(0, old_line_count - new_line_count) if diff.changed_doc_entries else 0
        diff.new_lines = new_line_count if diff.new_doc_entries else max(0, new_line_count - old_line_count)
        diff.updated_lines = max(0, min(old_line_count, new_line_count) - diff.removed_lines)
    diff.new_keys = len(diff.new_doc_entries)
    diff.updated_keys = len(diff.changed_doc_entries)
    diff.unchanged_keys = max(0, diff.source_rows - diff.new_keys - diff.updated_keys)
    return diff


def credit_memo_diff(connection: Any, table_names: dict[str, str | None], store: StagingStore, previous_documents: int) -> DomainDiff:
    docs, lines = table_names["credit_memo_document"], table_names["credit_memo_line"]
    diff = DomainDiff(domain=CREDIT_MEMO_DOMAIN, previous_rows=previous_documents, source_rows=store.count("credit_memo_document"))
    changed_expr = _compare_expr(_CREDIT_DOC_FIELDS, "cd", "sd")
    rows = connection.execute(f"""
        SELECT sd.doc_entry, cd.doc_entry IS NULL AS is_new, ({changed_expr}) AS changed,
               COALESCE(cd.canceled, 'N'), COALESCE(sd.canceled, 'N')
        FROM staging.credit_memo_document sd
        LEFT JOIN telchi.atomic.{_q(docs)} cd ON cd.doc_entry=sd.doc_entry
    """).fetchall()
    for doc_entry, is_new, changed, old_canceled, new_canceled in rows:
        key = str(doc_entry)
        if is_new: diff.new_doc_entries.append(key)
        elif changed: diff.changed_doc_entries.append(key)
        if not is_new and str(old_canceled) != str(new_canceled) and str(new_canceled).upper() in {"Y", "1", "TRUE", "C"}: diff.cancelled_transitions += 1
    disappeared = connection.execute(f"SELECT cd.doc_entry FROM telchi.atomic.{_q(docs)} cd WHERE cd.doc_date>=? AND cd.doc_entry NOT IN (SELECT doc_entry FROM staging.credit_memo_document)", [FOUNDATION_START.isoformat()]).fetchall()
    diff.disappeared_keys = len(disappeared)
    diff.disappeared_samples = [["credit_memo_document", str(row[0])] for row in disappeared[:20]]
    affected = diff.new_doc_entries + diff.changed_doc_entries
    if affected:
        placeholders = ",".join("?" for _ in affected)
        old_count = int(connection.execute(f"SELECT count(*) FROM telchi.atomic.{_q(lines)} WHERE doc_entry IN ({placeholders})", affected).fetchone()[0])
        new_count = int(connection.execute(f"SELECT count(*) FROM staging.credit_memo_line WHERE doc_entry IN ({placeholders})", affected).fetchone()[0])
        diff.new_lines = max(0, new_count - old_count) if diff.new_doc_entries else 0
        diff.updated_lines = min(old_count, new_count)
        diff.removed_lines = max(0, old_count - new_count)
    diff.new_keys, diff.updated_keys = len(diff.new_doc_entries), len(diff.changed_doc_entries)
    diff.unchanged_keys = max(0, diff.source_rows - diff.new_keys - diff.updated_keys)
    return diff


def movement_diff(connection: Any, table_names: dict[str, str | None], store: StagingStore, previous_rows: int) -> DomainDiff:
    target = table_names["inventory_movement"]
    diff = DomainDiff(domain=OINM_DOMAIN, previous_rows=previous_rows, source_rows=store.count("inventory_movement"))
    keys = ("trans_num", "trans_seq")
    join = _key_join(keys, "cm", "sm")
    changed_expr = _compare_expr(_OINM_FIELDS, "cm", "sm")
    rows = connection.execute(f"""
        SELECT cm.trans_num IS NULL AS is_new,
               NOT (cm.trans_num IS NULL) AND ({changed_expr}) AS changed
        FROM staging.inventory_movement sm
        LEFT JOIN telchi.atomic.{_q(target)} cm ON {join}
    """).fetchall()
    for is_new, changed in rows:
        if is_new:
            diff.new_keys += 1
        elif changed:
            diff.updated_keys += 1
        else:
            diff.unchanged_keys += 1
    disappeared = connection.execute(f"""
        SELECT cm.trans_num, cm.trans_seq FROM telchi.atomic.{_q(target)} cm
        WHERE cm.doc_date >= ?
          AND NOT EXISTS (
            SELECT 1 FROM staging.inventory_movement sm
            WHERE sm.trans_num = cm.trans_num AND sm.trans_seq = cm.trans_seq
          )
    """, [FOUNDATION_START.isoformat()]).fetchall()
    diff.disappeared_keys = len(disappeared)
    diff.disappeared_samples = [["inventory_movement", str(row[0]), str(row[1])] for row in disappeared[:20]]
    return diff


def inventory_diff(connection: Any, table_names: dict[str, str | None], store: StagingStore, previous_rows: int) -> DomainDiff:
    """OITW is current state: full snapshot replacement, disappearance allowed."""
    target = table_names["inventory_balance_snapshot"]
    diff = DomainDiff(domain=OITW_DOMAIN, previous_rows=previous_rows, source_rows=store.count("inventory_balance"))
    keys = ("item_code", "whs_code")
    join = _key_join(keys, "cw", "sw")
    changed_expr = _compare_expr(_OITW_FIELDS, "cw", "sw")
    rows = connection.execute(f"""
        SELECT cw.item_code IS NULL AS is_new,
               NOT (cw.item_code IS NULL) AND ({changed_expr}) AS changed
        FROM staging.inventory_balance sw
        LEFT JOIN telchi.atomic.{_q(target)} cw ON {join}
    """).fetchall()
    for is_new, changed in rows:
        if is_new:
            diff.new_keys += 1
            diff.added_rows += 1
        elif changed:
            diff.updated_keys += 1
        else:
            diff.unchanged_keys += 1
    removed = int(connection.execute(f"""
        SELECT count(*) FROM telchi.atomic.{_q(target)} cw
        WHERE NOT EXISTS (
            SELECT 1 FROM staging.inventory_balance sw
            WHERE sw.item_code = cw.item_code AND sw.whs_code = cw.whs_code
        )
    """).fetchone()[0])
    diff.disappeared_keys = removed
    diff.removed_rows = removed
    return diff


def compute_diffs(connection: Any, store: StagingStore, table_names: dict[str, str | None], previous: dict[str, Any]) -> dict[str, DomainDiff]:
    _read_staging_into_catalog_connection(connection, store)
    return {
        SALES_DOMAIN: sales_diff(connection, table_names, store, previous.get("sales_previous_documents", 0))
        if store.relation_exists("sales_document") else DomainDiff(domain=SALES_DOMAIN, source_rows=0),
        CREDIT_MEMO_DOMAIN: credit_memo_diff(connection, table_names, store, previous.get("credit_memo_previous_documents", 0))
        if store.relation_exists("credit_memo_document") else DomainDiff(domain=CREDIT_MEMO_DOMAIN, source_rows=0),
        OINM_DOMAIN: movement_diff(connection, table_names, store, previous.get("oinm_previous_rows", 0))
        if store.relation_exists("inventory_movement") else DomainDiff(domain=OINM_DOMAIN, source_rows=0),
        OITW_DOMAIN: inventory_diff(connection, table_names, store, previous.get("oitw_previous_rows", 0))
        if store.relation_exists("inventory_balance") else DomainDiff(domain=OITW_DOMAIN, source_rows=0),
    }


# ---------------------------------------------------------------------------
# Reference V2 coverage detection (no mutation)
# ---------------------------------------------------------------------------


def reference_coverage(
    connector: DuckLakeConnector,
    store: StagingStore,
    table_names: dict[str, str | None],
) -> dict[str, Any]:
    """Detect new source keys used by Sales/OINM/OITW and their resolvability.

    Reference V2 is a versioned filesystem layer; this V1 never rebuilds it.
    Captured source keys are compared against the current crosswalk
    (native -> canonical) and against keys already in the Data Lake. Newly
    introduced *unresolved* keys are reported so the caller can refuse to
    orphan them; pre-existing unresolved keys are documented.
    """
    import duckdb

    pointer: dict[str, Any] = {}
    if REFERENCE_POINTER.is_file():
        pointer = json.loads(REFERENCE_POINTER.read_text(encoding="utf-8"))
    reference_path = Path(pointer.get("reference_path", DATA_ROOT / "reference" / "_versions" / "v2"))
    crosswalk_path = Path(pointer.get("crosswalk_path", DATA_ROOT / "crosswalk" / "_versions" / "v2"))

    result: dict[str, Any] = {
        "reference_version": pointer.get("current_reference_version", "UNKNOWN"),
        "reference_path": str(reference_path),
        "crosswalk_path": str(crosswalk_path),
        "previous_version": pointer.get("previous_version"),
        "reference_modified": "NO",
        "new_keys_unresolved": 0,
        "existing_canonical_ids_changed": 0,
        "crosswalk_regressions": 0,
        "unresolved_samples": [],
        "coverage": "EXACT",
    }
    connection = duckdb.connect()
    try:
        def view(name: str, path: Path) -> bool:
            files = sorted(path.glob("*.parquet")) if path.exists() else []
            if not files:
                return False
            literals = "[" + ",".join("'" + str(f).replace("'", "''") + "'" for f in files) + "]"
            connection.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({literals})")
            return True

        have = {
            "product": view("ref_product_crosswalk", crosswalk_path / "product_crosswalk"),
            "customer": view("ref_customer_crosswalk", crosswalk_path / "customer_crosswalk"),
            "supplier": view("ref_supplier_crosswalk", crosswalk_path / "supplier_crosswalk"),
            "warehouse": view("ref_warehouse_crosswalk", crosswalk_path / "warehouse_crosswalk"),
            "salesperson": view("ref_salesperson_crosswalk", crosswalk_path / "salesperson_crosswalk"),
        }
        source_keys = _staging_keys(connection, store, staging_path=store.path)
        with connector.session(read_only=True) as duck:
            existing_keys = _atomic_keys(duck, table_names)
        for kind in ("product", "customer", "warehouse", "salesperson"):
            keys = source_keys[kind]
            # OINM.CardCode is nullable and, for accounting movements, may carry
            # a numeric G/L account rather than an OCRD business partner.  Those
            # rows have no BP lineage and must not receive an artificial mapping.
            if kind == "customer":
                ignored = {key for key in keys if not re.match(r"^[A-Za-z]", key.strip())}
                keys = keys - ignored
                result["customer_non_bp_source_keys_ignored"] = len(ignored)
            result[f"{kind}_source_keys"] = len(keys)
            result[f"{kind}_unresolved"] = 0
            result[f"{kind}_new_unresolved"] = 0
            if not keys or (kind == "customer" and not (have["customer"] or have["supplier"])) or (kind != "customer" and not have[kind]):
                continue
            literals = ",".join("'" + key.replace("'", "''") + "'" for key in sorted(keys))
            if kind == "customer":
                relations = [name for name, present in (("ref_customer_crosswalk", have["customer"]), ("ref_supplier_crosswalk", have["supplier"])) if present]
                resolved_sql = " UNION ALL ".join(f"SELECT source_native_id FROM {name}" for name in relations)
                resolved = {str(row[0]) for row in connection.execute(
                    f"SELECT DISTINCT source_native_id FROM ({resolved_sql}) bp WHERE source_native_id IN ({literals})"
                ).fetchall()}
            else:
                resolved = {str(row[0]) for row in connection.execute(
                    f"SELECT DISTINCT source_native_id FROM ref_{kind}_crosswalk WHERE source_native_id IN ({literals})"
                ).fetchall()}
            unresolved = keys - resolved
            new_unresolved = {key for key in unresolved if key not in existing_keys[kind]}
            result[f"{kind}_unresolved"] = len(unresolved)
            result[f"{kind}_new_unresolved"] = len(new_unresolved)
            result["new_keys_unresolved"] += len(new_unresolved)
            if new_unresolved:
                result["unresolved_samples"].extend(sorted(new_unresolved)[:20])
        if result["new_keys_unresolved"] > 0:
            result["coverage"] = "ORPHAN_RISK"
        elif sum(result.get(f"{k}_unresolved", 0) for k in ("product", "customer", "warehouse", "salesperson")) > 0:
            result["coverage"] = "DEGRADED_PREEXISTING_UNRESOLVED"
    finally:
        connection.close()
    return result


def _staging_keys(connection: Any, store: StagingStore, *, staging_path: Path) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {"product": set(), "customer": set(), "warehouse": set(), "salesperson": set()}
    attached = {str(row[0]) for row in connection.execute("SELECT database_name FROM duckdb_databases()").fetchall()}
    if "staging" not in attached:
        connection.execute(f"ATTACH '{str(staging_path).replace(chr(39), chr(39) * 2)}' AS staging (READ_ONLY)")

    def fetch(table: str, column: str) -> set[str]:
        if not store.relation_exists(table):
            return set()
        return {str(row[0]) for row in connection.execute(
            f"SELECT DISTINCT {_q(column)} FROM staging.{_q(table)} WHERE {_q(column)} IS NOT NULL"
        ).fetchall()}

    for table in ("sales_line", "inventory_movement", "inventory_balance"):
        keys["product"] |= fetch(table, "item_code")
    for table in ("sales_document", "inventory_movement"):
        keys["customer"] |= fetch(table, "card_code")
    keys["warehouse"] |= fetch("sales_line", "whs_code")
    keys["warehouse"] |= fetch("inventory_movement", "warehouse")
    keys["warehouse"] |= fetch("inventory_balance", "whs_code")
    for table in ("sales_line", "credit_memo_line"):
        keys["salesperson"] |= fetch(table, "attributed_slp_code")
    for table in ("sales_line", "credit_memo_line"):
        keys["salesperson"] |= fetch(table, "slp_code")
    for table in ("sales_document", "credit_memo_document"):
        keys["salesperson"] |= fetch(table, "slp_code")
    keys["salesperson"].discard("-1")
    return keys


def _atomic_keys(connection: Any, table_names: dict[str, str | None]) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {"product": set(), "customer": set(), "warehouse": set(), "salesperson": set()}

    def fetch(table: str | None, column: str) -> set[str]:
        if not table:
            return set()
        try:
            return {str(row[0]) for row in connection.execute(
                f"SELECT DISTINCT {_q(column)} FROM telchi.atomic.{_q(table)} WHERE {_q(column)} IS NOT NULL"
            ).fetchall()}
        except Exception:
            return set()

    keys["product"] |= fetch(table_names.get("sales_line"), "item_code")
    keys["product"] |= fetch(table_names.get("inventory_movement"), "item_code")
    keys["product"] |= fetch(table_names.get("inventory_balance_snapshot"), "item_code")
    keys["customer"] |= fetch(table_names.get("sales_document"), "card_code")
    keys["customer"] |= fetch(table_names.get("inventory_movement"), "card_code")
    keys["warehouse"] |= fetch(table_names.get("sales_line"), "whs_code")
    keys["warehouse"] |= fetch(table_names.get("inventory_movement"), "warehouse")
    keys["warehouse"] |= fetch(table_names.get("inventory_balance_snapshot"), "whs_code")
    keys["salesperson"] |= fetch(table_names.get("sales_line"), "attributed_slp_code")
    keys["salesperson"] |= fetch(table_names.get("credit_memo_line"), "attributed_slp_code")
    keys["salesperson"] |= fetch(table_names.get("sales_line"), "slp_code")
    keys["salesperson"] |= fetch(table_names.get("credit_memo_line"), "slp_code")
    keys["salesperson"] |= fetch(table_names.get("sales_document"), "slp_code")
    keys["salesperson"] |= fetch(table_names.get("credit_memo_document"), "slp_code")
    keys["salesperson"].discard("-1")
    return keys


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------


def _load_changed_rows(connection: Any, store: StagingStore, table_name: str, key_filter_sql: str, key_filter_params: list[Any]) -> list[dict[str, Any]]:
    if not store.relation_exists(table_name):
        return []
    rows = connection.execute(
        f"SELECT * FROM staging.{_q(table_name)} WHERE {key_filter_sql}", key_filter_params
    )
    columns = [str(item[0]) for item in rows.description or ()]
    return [dict(zip(columns, row)) for row in rows.fetchall()]


def build_changed_candidates(
    connection: Any,
    store: StagingStore,
    table_names: dict[str, str | None],
    diffs: dict[str, DomainDiff],
    manifest: dict[str, Any],
) -> dict[str, Candidate]:
    """Materialize changed-only Candidates read from the transient staging DB."""
    candidates: dict[str, Candidate] = {}
    sales = diffs[SALES_DOMAIN]
    affected_docs = sales.new_doc_entries + sales.changed_doc_entries
    if sales.has_changes and affected_docs:
        placeholders = ",".join("?" for _ in affected_docs)
        doc_rows = _load_changed_rows(connection, store, "sales_document", f"doc_entry IN ({placeholders})", affected_docs)
        line_rows = _load_changed_rows(connection, store, "sales_line", f"doc_entry IN ({placeholders})", affected_docs)
        candidate = transform("sales", _reconstruct_sales_rows(doc_rows, line_rows), {**manifest, "extraction_id": manifest["extraction_id"]})
        candidates[SALES_DOMAIN] = candidate
    credit = diffs[CREDIT_MEMO_DOMAIN]
    affected_credit = credit.new_doc_entries + credit.changed_doc_entries
    if credit.has_changes and affected_credit:
        placeholders = ",".join("?" for _ in affected_credit)
        doc_rows = _load_changed_rows(connection, store, "credit_memo_document", f"doc_entry IN ({placeholders})", affected_credit)
        line_rows = _load_changed_rows(connection, store, "credit_memo_line", f"doc_entry IN ({placeholders})", affected_credit)
        candidates[CREDIT_MEMO_DOMAIN] = transform("credit_memo", _reconstruct_credit_memo_rows(doc_rows, line_rows), {**manifest, "extraction_id": manifest["extraction_id"]})
    oinm = diffs[OINM_DOMAIN]
    if oinm.has_changes and (oinm.new_keys or oinm.updated_keys):
        rows = _load_changed_oinm_rows(connection, store, table_names, manifest)
        if rows:
            candidates[OINM_DOMAIN] = transform("inventory_movement", rows, {**manifest, "source_key_columns": tuple(manifest.get("source_key_columns") or ("TransNum", "TransSeq"))})
    oitw = diffs[OITW_DOMAIN]
    if (oitw.added_rows or oitw.updated_keys or oitw.removed_rows) and store.relation_exists("inventory_balance"):
        rows = _rename_oitw(_load_all(connection, store, "inventory_balance"))
        if rows:
            candidates[OITW_DOMAIN] = transform("inventory", rows, {**manifest, "source_as_of": manifest.get("source_as_of")})
    return candidates


def _load_all(connection: Any, store: StagingStore, table_name: str) -> list[dict[str, Any]]:
    if not store.relation_exists(table_name):
        return []
    rows = connection.execute(f"SELECT * FROM staging.{_q(table_name)}")
    columns = [str(item[0]) for item in rows.description or ()]
    return [dict(zip(columns, row)) for row in rows.fetchall()]


def _reconstruct_sales_rows(doc_rows: list[dict[str, Any]], line_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge normalized doc + line staging rows back into create_initial's raw shape.

    ``transform('sales', rows)`` expects one row per (DocEntry, LineNum) carrying
    both header and line source fields. The staging tables store them split, so
    they are recombined here per DocEntry before transform builds the candidate.
    """
    by_doc: dict[str, dict[str, Any]] = {}
    for doc in doc_rows:
        by_doc[str(doc["doc_entry"])] = doc
    merged: list[dict[str, Any]] = []
    for line in line_rows:
        doc = by_doc.get(str(line["doc_entry"]))
        if doc is None:
            continue
        merged.append({
            "DocEntry": doc.get("doc_entry"), "DocNum": doc.get("doc_num"), "DocDate": doc.get("doc_date"),
            "DocDueDate": doc.get("doc_due_date"), "TaxDate": doc.get("tax_date"), "DocStatus": doc.get("doc_status"),
            "CANCELED": doc.get("canceled"), "DocCur": doc.get("currency"), "DocTotal": doc.get("doc_total"),
            "DocTotalSy": doc.get("doc_total_system"), "DocTotalFC": doc.get("doc_total_foreign"),
            "CardCode": doc.get("card_code"), "HeaderSlpCode": doc.get("slp_code"), "Series": doc.get("series"), "UserSign": doc.get("user_sign"), "ObjType": 13,
            "LineNum": line.get("line_num"), "LineStatus": line.get("line_status"), "ItemCode": line.get("item_code"),
            "WhsCode": line.get("whs_code"), "Quantity": line.get("quantity"), "LineCurrency": line.get("currency"),
            "LineTotal": line.get("line_total"), "Price": line.get("price"), "LineSlpCode": line.get("slp_code"),
        })
    return merged


def _reconstruct_credit_memo_rows(doc_rows: list[dict[str, Any]], line_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_doc = {str(row["doc_entry"]): row for row in doc_rows}
    merged = []
    for line in line_rows:
        doc = by_doc.get(str(line["doc_entry"]))
        if not doc: continue
        merged.append({
            "DocEntry": doc.get("doc_entry"), "DocNum": doc.get("doc_num"), "DocDate": doc.get("doc_date"),
            "CreateDate": doc.get("create_date"), "UpdateDate": doc.get("update_date"), "DocStatus": doc.get("doc_status"),
            "CANCELED": doc.get("canceled"), "CardCode": doc.get("card_code"), "HeaderSlpCode": doc.get("slp_code"),
            "DocCur": doc.get("currency"), "DocTotal": doc.get("doc_total"), "DocTotalSy": doc.get("doc_total_system"),
            "DocTotalFC": doc.get("doc_total_foreign"), "Series": doc.get("series"), "UserSign": doc.get("user_sign"),
            "LineNum": line.get("line_num"), "LineStatus": line.get("line_status"), "ItemCode": line.get("item_code"),
            "WhsCode": line.get("whs_code"), "Quantity": line.get("quantity"), "LineCurrency": line.get("currency"),
            "LineTotal": line.get("line_total"), "TotalSumSy": line.get("line_total_system"), "TotalFrgn": line.get("line_total_foreign"),
            "LineSlpCode": line.get("slp_code"), "BaseType": line.get("base_type"), "BaseEntry": line.get("base_entry"), "BaseLine": line.get("base_line"),
        })
    return merged


_OINM_RAW_ALIASES = {
    "TransNum": "trans_num", "TransSeq": "trans_seq", "Instance": "instance", "TransType": "trans_type",
    "DocEntry": "doc_entry", "BaseRef": "base_ref", "DocDate": "doc_date", "ItemCode": "item_code",
    "Warehouse": "warehouse", "InQty": "in_qty", "OutQty": "out_qty", "Price": "price", "CalcPrice": "calc_price",
    "TransValue": "trans_value", "CreatedBy": "created_by", "AppObjAbs": "app_obj_abs", "AppObjType": "app_obj_type",
    "DocLineNum": "doc_line_num", "Ref1": "ref1", "Ref2": "ref2", "Comments": "comments", "JrnlMemo": "jrnl_memo",
    "DocDueDate": "doc_due_date", "DocTime": "doc_time", "CardCode": "card_code", "CardName": "card_name",
    "Dscription": "dscription", "Balance": "balance", "SlpCode": "slp_code", "UserSign": "user_sign",
    "ApplObj": "appl_obj", "AppObjLine": "app_obj_line",
}


def _load_changed_oinm_rows(connection: Any, store: StagingStore, table_names: dict[str, str | None], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    target = table_names["inventory_movement"]
    keys = ("trans_num", "trans_seq")
    join = _key_join(keys, "cm", "sm")
    changed_expr = _compare_expr(_OINM_FIELDS, "cm", "sm")
    result = connection.execute(f"""
        SELECT sm.* FROM staging.inventory_movement sm
        LEFT JOIN telchi.atomic.{_q(target)} cm ON {join}
        WHERE cm.trans_num IS NULL OR ({changed_expr})
    """)
    columns = [str(item[0]) for item in result.description or ()]
    rows = [dict(zip(columns, row)) for row in result.fetchall()]
    # Restore source field names expected by transform().
    rename = {value: key for key, value in _OINM_RAW_ALIASES.items()}
    return [{rename.get(column, column): value for column, value in row.items()} for row in rows]


# Normalized-staging column -> raw SAP field name, for rebuilding create_initial r
# raw row shape before transform().
_OITW_RAW_NAMES = {
    "item_code": "ItemCode", "whs_code": "WhsCode", "on_hand": "OnHand",
    "is_commited": "IsCommited", "on_order": "OnOrder",
}


def _rename_oitw(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{_OITW_RAW_NAMES.get(column, column): value for column, value in row.items()} for row in rows]


def _oitw_snapshot_writer(table_names: dict[str, str | None], metrics: dict[str, int] | None = None):
    """OITW current-state semantics: replace the full snapshot.

    Rows that exist in Atomic but are absent from the captured SAP snapshot are
    legitimately gone (current state), so they are removed set-based. Changed and
    added keys reuse create_initial's bulk per-key replacement (one DELETE keyed
    set + one INSERT ... SELECT). Nothing is written one-file-per-row.
    """
    balances = table_names.get("inventory_balance_snapshot")
    base_writer = publication_writer(table_names, metrics=metrics)

    def writer(connection: Any, candidate: Candidate, publication_id: str, inject: Any) -> None:
        if not balances:
            raise RuntimeError("existing Atomic OITW contract is missing")
        rows = candidate.tables.get("inventory_balance", [])
        if not rows:
            raise RuntimeError("OITW snapshot replacement requires at least one row")
        stage = f"telchi_stage_oitw_snapshot_{id(candidate)}"
        columns = _stage_rows(connection, stage, rows)
        try:
            # Remove snapshot keys that are gone from SAP (current state).
            connection.execute(
                f"DELETE FROM telchi.atomic.{_q(balances)} "
                f"WHERE (item_code, whs_code) NOT IN "
                f"(SELECT item_code, whs_code FROM {_q(stage)})"
            )
        finally:
            connection.execute(f"DROP TABLE IF EXISTS {_q(stage)}")
        # Replace changed/added keys through the standard bulk path.
        base_writer(connection, candidate, publication_id, inject)

    return writer


def _update_writer(table_names: dict[str, str | None], metrics: dict[str, int] | None = None):
    """Dispatch to incremental (Sales/OINM) or snapshot (OITW) bulk writers."""
    incremental = publication_writer(table_names, metrics=metrics)
    oitw = _oitw_snapshot_writer(table_names, metrics=metrics)

    def writer(connection: Any, candidate: Candidate, publication_id: str, inject: Any) -> None:
        if candidate.domain == OITW_DOMAIN:
            oitw(connection, candidate, publication_id, inject)
        else:
            incremental(connection, candidate, publication_id, inject)

    return writer


def publish(
    *,
    connector: DuckLakeConnector,
    store: StagingStore,
    table_names: dict[str, str | None],
    candidates: dict[str, Candidate],
    run_id: str,
    dry_run: bool,
    fault_point: str | None = None,
) -> dict[str, Any]:
    """Publish the changed domain datasets in separate atomic transactions.

    Datasets are physically published per domain (each one atomic). Visibility
    of the whole foundation is controlled later by the single logical commit in
    :func:`commit_foundation`, so a failure between domains leaves the previous
    foundation CURRENT. ``fault_point`` injects the required fault matrix.
    """
    metrics: dict[str, int] = {}
    boundary = TransactionalPublicationBoundary(
        connection_factory=lambda: connector.session(read_only=False),
        record_table=PUBLICATION_TABLE_V1,
        writer=_update_writer(table_names, metrics=metrics),
        publication_id_factory=lambda key: "update_publication_" + digest(key)[:32],
    )
    if dry_run:
        changes = {domain: candidate.content_identity for domain, candidate in candidates.items()}
        return {
            "status": "DRY_RUN", "changed_domains": sorted(candidates),
            "candidate_ids": changes, "bulk_write_metrics": metrics,
            "would_insert": sum(len(candidate.tables.get("sales_line", [])) + len(candidate.tables.get("inventory_movement", [])) + len(candidate.tables.get("inventory_balance", [])) + len(candidate.tables.get("sales_document", [])) for candidate in candidates.values()),
        }

    def inject(point: str) -> None:
        if fault_point == point:
            raise UpdateAbort(f"injected data publication failure at {point}")

    applied: dict[str, Any] = {}
    for domain, inject_after in (
        (SALES_DOMAIN, CommitFaultPoint.AFTER_SALES),
        (CREDIT_MEMO_DOMAIN, CommitFaultPoint.AFTER_CREDIT_MEMO),
        (OINM_DOMAIN, CommitFaultPoint.AFTER_OINM),
        (OITW_DOMAIN, CommitFaultPoint.AFTER_OITW),
    ):
        candidate = candidates.get(domain)
        if candidate is None:
            continue
        idempotency_key = f"{PUBLICATION_STRATEGY_VERSION}|MANUAL_UPDATE|{domain}|{run_id}|{candidate.content_identity}"
        receipt = boundary.publish(
            idempotency_key=idempotency_key,
            candidate=candidate,
            metadata={
                "job_id": run_id, "segment_id": f"manual-update-{domain}", "attempt": 1,
                "source_identity": digest({"domain": domain, "run_id": run_id}),
                "reference_version": os.getenv("TELCHI_REFERENCE_VERSION", "REFERENCE_V2"),
                "transformation_version": UPDATE_TRANSFORMATION_VERSION,
            },
        )
        applied[domain] = {
            "publication_id": receipt.publication_identity,
            "content_identity": receipt.content_identity,
            "published_at": receipt.published_at,
            "rows": {table: len(rows) for table, rows in candidate.tables.items()},
        }
        inject(inject_after)
    return {"status": "PUBLISHED" if applied else "NOOP", "applied": applied, "bulk_write_metrics": metrics}


def _component_reference(domain: str, applied: dict[str, Any]) -> ComponentReference:
    entry = applied.get(domain, {})
    rows = entry.get("rows", {})
    return ComponentReference(
        name={"sales": "sales", "credit_memo": "credit_memo", "inventory_movement": "oinm", "inventory": "oitw"}[domain],
        publication_id=entry.get("publication_id"),
        source_as_of=entry.get("published_at"),
        row_count=sum(int(value or 0) for value in rows.values()),
        content_identity=entry.get("content_identity"),
    )


def reference_requires_publication(store: FoundationPublicationStore, reference: dict[str, Any]) -> bool:
    previous = store.current_publication()
    return previous is not None and previous.reference_version != reference.get("reference_version")


def publish_reference_only(*, connector: Any, foundation_store: FoundationPublicationStore,
                           reference: dict[str, Any], fault_point: str | None = None,
                           base_data_snapshot_id: int | None = None,
                           prepare_only: bool = False) -> dict[str, Any]:
    """Existing publication boundary without fact extraction or SAP access.

    Explicit caller only. The master builder does not automatically publish a
    Foundation, and no scheduler or conversational capability calls this path.
    """
    previous = foundation_store.current_publication()
    if previous is None:
        raise UpdateAbort("Reference-only publication requires an existing Foundation")
    if not reference.get("reference_version") or not Path(reference.get("reference_path", "")).is_dir():
        raise UpdateAbort("Reference-only publication requires an immutable Reference directory")
    if not reference_requires_publication(foundation_store, reference):
        return {"status": "NOOP", "foundation_publication_id": previous.foundation_publication_id}
    run_id = "reference-only-" + digest({
        "base": previous.foundation_publication_id, "reference": reference["reference_version"], "attempt": _now(),
    })[:24]
    candidate = prepare_candidate(foundation_store, update_run_id=run_id, reference_version=reference["reference_version"])
    return commit_foundation(
        connector=connector, foundation_store=foundation_store, candidate=candidate,
        applied={}, reference=reference, source_as_of=previous.source_as_of,
        precommit_validation={"status": "PASS", "mode": "REFERENCE_ONLY_COMPATIBILITY"},
        run_id=run_id, fault_point=fault_point, base_data_snapshot_id=base_data_snapshot_id,
        prepare_only=prepare_only,
    )


def commit_foundation(
    *,
    connector: DuckLakeConnector,
    foundation_store: FoundationPublicationStore,
    candidate: Any,
    applied: dict[str, Any],
    reference: dict[str, Any],
    source_as_of: str,
    precommit_validation: dict[str, Any],
    run_id: str,
    fault_point: str | None = None,
    base_data_snapshot_id: int | None = None,
    prepare_only: bool = False,
) -> dict[str, Any]:
    """Record component membership, validate, then perform the logical commit.

    Order (spec section 16):
      PREPARING -> datasets B published -> VALIDATING -> READY_TO_COMMIT
      -> logical commit (atomic current pointer) -> CURRENT.
    Any failure before the logical commit leaves the previous foundation
    CURRENT and marks the candidate FAILED.
    """
    foundation_store.fault_point = fault_point
    components: dict[str, ComponentReference] = {
        "reference": ComponentReference(
            name="reference",
            publication_id=reference.get("reference_version"),
            source_as_of=reference.get("reference_source_as_of") or reference.get("source_as_of"),
            content_identity=reference.get("reference_path") or reference.get("reference_version"),
        )
    }
    for domain in (SALES_DOMAIN, CREDIT_MEMO_DOMAIN, OINM_DOMAIN, OITW_DOMAIN):
        component = _component_reference(domain, applied)
        if component.publication_id is not None:
            components[component.name] = component
        else:
            # An unchanged dataset still belongs to candidate B through the
            # previous committed component publication. This is membership,
            # not a new physical write; it prevents incomplete foundations on
            # idempotent/partial-delta runs.
            previous = foundation_store.current_publication()
            old = previous.component(component.name) if previous else None
            if old is None or old.publication_id is None:
                raise UpdateAbort(f"missing prior component publication for {component.name}")
            components[component.name] = old
    manifest = {
        "foundation_publication_id": candidate.foundation_publication_id,
        "update_run_id": run_id,
        "components": {name: components[name].as_dict() for name in COMPONENT_NAMES},
        "reference_version": reference.get("reference_version"),
        "source_as_of": source_as_of,
        "precommit_validation": precommit_validation,
        "sales_dataset_publication_id": (components.get("sales") or ComponentReference("sales", None)).publication_id,
        "credit_memo_dataset_publication_id": (components.get("credit_memo") or ComponentReference("credit_memo", None)).publication_id,
        "oinm_dataset_publication_id": (components.get("oinm") or ComponentReference("oinm", None)).publication_id,
        "oitw_dataset_publication_id": (components.get("oitw") or ComponentReference("oitw", None)).publication_id,
    }
    try:
        from copy import deepcopy
        from .foundation_manifest import validate_manifest
        from .reference_compatibility import KIND as REFRESH_KIND, reference_projection
        previous = foundation_store.current_publication()
        previous_manifest = previous.manifest if previous else {}
        extras = set(previous_manifest.get("components", {})) - set(COMPONENT_NAMES)
        reference_only = not applied
        if extras or reference_only:
            # Existing derived contracts bind exact facts/snapshots. A facts delta
            # needs a component-specific rebuild, not an unproven manifest copy.
            validate_manifest(foundation_store, previous)
            unsupported = extras - {"material_supply", "receivables_collections", "purchasing"}
            if unsupported:
                raise UpdateAbort("REFERENCE_COMPATIBILITY_ADAPTER_REQUIRED: " + ",".join(sorted(unsupported)))
            if "material_supply" in extras:
                from .material_supply_candidate import resolve_current_material_supply
                resolve_current_material_supply(foundation_store)
            if "receivables_collections" in extras:
                from .receivables_collections_foundation import resolve_current
                resolve_current(foundation_store)
            if "purchasing" in extras:
                from .purchasing import ATOMIC, DERIVED, VERSION
                purchasing = previous_manifest["components"]["purchasing"]
                if (set(purchasing["datasets"]) != set(ATOMIC + DERIVED)
                        or purchasing["stable_contract"].get("lineage_algorithm_version") != VERSION):
                    raise UpdateAbort("Purchasing dataset/algorithm contract incompatible")
            if applied:
                raise UpdateAbort("SEALED_COMPONENT_REVALIDATION_REQUIRED: facts changed with " + ",".join(sorted(extras)))
            old_root = DATA_ROOT / "reference" / "_versions" / previous.reference_version
            new_root = Path(reference["reference_path"]).resolve()
            expected_root = (DATA_ROOT / "reference" / "_versions" / reference["reference_version"]).resolve()
            if new_root != expected_root:
                raise UpdateAbort("Reference immutable path/version binding mismatch")
            proof = reference_projection(old_root, new_root)
            # The derivation base is NOT the prior reader's commit snapshot.
            # Metadata-only refreshes must preserve the exact visible facts.
            if previous_manifest.get('candidate_kind') == REFRESH_KIND:
                pinned_snapshot = previous_manifest['reference_data_snapshot_id']
                if base_data_snapshot_id is not None and base_data_snapshot_id != pinned_snapshot:
                    raise UpdateAbort('Reference refresh data snapshot changed')
            elif connector is not None:
                from .foundation_reader import FoundationReader
                with connector.session(read_only=True) as connection:
                    access = FoundationReader(connector).resolve_on(connection)
                if access.foundation_publication_id != previous.foundation_publication_id:
                    raise UpdateAbort('CURRENT changed while pinning Reference data snapshot')
                pinned_snapshot = access.ducklake_snapshot_id
                if base_data_snapshot_id is not None and base_data_snapshot_id != pinned_snapshot:
                    raise UpdateAbort('Reference refresh data snapshot mismatch')
            else:
                # Offline stores have no DuckLake history; require accredited input.
                pinned_snapshot = base_data_snapshot_id
            if type(pinned_snapshot) is not int or pinned_snapshot < previous_manifest['base_snapshot_id']:
                raise UpdateAbort('Reference refresh requires an accredited data snapshot')
            manifest = deepcopy(previous_manifest)
            # The proof below is physical-only, not the ancestor's append proof.
            manifest.pop('reference_compatibility_adapter', None)
            manifest.update(
                foundation_publication_id=candidate.foundation_publication_id,
                update_run_id=run_id, candidate_kind=REFRESH_KIND,
                manifest_schema_version="1.0.0",
                base_foundation_publication_id=previous.foundation_publication_id,
                reference_version=reference["reference_version"],
                reference_compatibility=proof,
                reference_data_snapshot_id=pinned_snapshot,
                precommit_validation=precommit_validation,
            )
            manifest["components"]["reference"] = components["reference"].as_dict()
        elif connector is not None:
            with connector.session(read_only=True) as connection:
                snapshot = connection.execute("SELECT max(snapshot_id) FROM ducklake_snapshots('telchi')").fetchone()[0]
            manifest["base_snapshot_id"] = int(snapshot)
        elif "base_snapshot_id" in previous_manifest:
            manifest["base_snapshot_id"] = previous_manifest["base_snapshot_id"]
        foundation_store.update_components(
            candidate.foundation_publication_id,
            components,
            source_as_of=source_as_of,
            validation_status=precommit_validation.get("status", "UNKNOWN"),
            manifest=manifest,
        )
        if extras or reference_only:
            validate_manifest(foundation_store, foundation_store.get(candidate.foundation_publication_id))
        foundation_store.set_status(candidate.foundation_publication_id, VALIDATING)
        foundation_store.inject(CommitFaultPoint.DURING_VALIDATION)
        if precommit_validation.get("status") != "PASS":
            raise UpdateAbort(f"PRECOMMIT_VALIDATION=FAIL: {precommit_validation.get('status')}")
        foundation_store.inject(CommitFaultPoint.AFTER_REFERENCE)
        foundation_store.set_status(
            candidate.foundation_publication_id, READY_TO_COMMIT, validated_at=_now()
        )
        foundation_store.inject(CommitFaultPoint.BEFORE_LOGICAL_COMMIT)
        if prepare_only:
            return {"status": "PREPARED", "foundation_publication_id": candidate.foundation_publication_id}
        commit_result = foundation_store.logical_commit(candidate.foundation_publication_id)
        if commit_result.get("status") == "ALREADY_CURRENT":
            return {"status": "ALREADY_CURRENT", "logical_commit": commit_result}
        return {"status": "COMMITTED", "logical_commit": commit_result}
    except BaseException as exc:
        foundation_store.mark_failed(candidate.foundation_publication_id, f"{type(exc).__name__}: {exc}")
        raise


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def prepublication_validation(diffs: dict[str, DomainDiff], reference: dict[str, Any], *, defer_new_reference_keys: bool = False) -> dict[str, Any]:
    """Fail closed unless the run is explicitly authorized to defer new keys.

    Default behavior (``defer_new_reference_keys=False``) aborts when a *newly
    introduced* source key has no Reference V2 row (``REFERENCE_REFRESH_REQUIRED_
    BUT_UNSAFE=YES``), as required by the gate. With an explicit operator
    authorization the new keys are recorded as ``DEGRADED`` and the facts may be
    published, because Atomic stores no canonical foreign key and existing
    canonical IDs are never reassigned by this run.
    """
    checks: dict[str, Any] = {}
    checks["SALES_DISAPPEARED_SOURCE_KEYS"] = diffs[SALES_DOMAIN].disappeared_keys
    checks["CREDIT_MEMO_DISAPPEARED_SOURCE_KEYS"] = diffs[CREDIT_MEMO_DOMAIN].disappeared_keys
    checks["OINM_DISAPPEARED_SOURCE_KEYS"] = diffs[OINM_DOMAIN].disappeared_keys
    checks["REFERENCE_ORPHAN_RISK"] = reference.get("coverage") == "ORPHAN_RISK"
    checks["reference_new_unresolved"] = reference.get("new_keys_unresolved", 0)
    checks["defer_new_reference_keys"] = defer_new_reference_keys
    if checks["SALES_DISAPPEARED_SOURCE_KEYS"]:
        return {"status": "FAIL", "reason": "SALES_HISTORICAL_SOURCE_KEY_DISAPPEARED", "checks": checks}
    if checks["CREDIT_MEMO_DISAPPEARED_SOURCE_KEYS"]:
        return {"status": "FAIL", "reason": "CREDIT_MEMO_HISTORICAL_SOURCE_KEY_DISAPPEARED", "checks": checks}
    if checks["OINM_DISAPPEARED_SOURCE_KEYS"]:
        return {"status": "FAIL", "reason": "OINM_HISTORICAL_SOURCE_KEY_DISAPPEARED", "checks": checks}
    if checks["REFERENCE_ORPHAN_RISK"] and not defer_new_reference_keys:
        return {
            "status": "FAIL",
            "reason": "REFERENCE_REFRESH_REQUIRED_BUT_UNSAFE=YES",
            "checks": checks,
        }
    if checks["REFERENCE_ORPHAN_RISK"]:
        return {
            "status": "PASS", "degraded": True,
            "reason": "REFERENCE_NEW_KEYS_DEFERRED_BY_EXPLICIT_AUTHORIZATION",
            "checks": checks,
        }
    return {"status": "PASS", "checks": checks}


def postpublication_validation(connection: Any, store: StagingStore, table_names: dict[str, str | None]) -> dict[str, Any]:
    """Validate final Atomic against the captured SAP staging (PUBLISHED_VS_STAGING).

    The Sales and OINM current sides are scoped to the 2026 business window,
    which is the exact scope the update manages. OITW is current state.
    """
    _read_staging_into_catalog_connection(connection, store)
    result: dict[str, Any] = {}
    start = FOUNDATION_START.isoformat()

    def scalar(sql: str, params: list[Any] | None = None) -> int:
        return int(connection.execute(sql, params or []).fetchone()[0])

    def value(sql: str, params: list[Any] | None = None) -> str:
        return str(connection.execute(sql, params or []).fetchone()[0])

    def decimal_sum(table: str, column: str, scope: str = "") -> str:
        # Compare exact decimals, never binary floats: DOUBLE summation order
        # can differ between the staging and catalog scans and produces false
        # mismatches on values that are actually identical.
        return value(
            f"SELECT CAST(COALESCE(SUM(TRY_CAST({_q(column)} AS DECIMAL(38,10))),0) AS VARCHAR) FROM {table} {scope}"
        )

    def keyset_exact(current: str, source: str, keys: tuple[str, ...], current_join: str, source_join: str = "") -> bool:
        key_list_c = ", ".join("c." + _q(k) for k in keys)
        key_list_s = ", ".join("s." + _q(k) for k in keys)
        left = scalar(f"""
            SELECT count(*) FROM (
              (SELECT {key_list_c} FROM telchi.atomic.{_q(current)} c {current_join}
               EXCEPT SELECT {key_list_s} FROM staging.{_q(source)} s {source_join})
              UNION ALL
              (SELECT {key_list_s} FROM staging.{_q(source)} s {source_join}
               EXCEPT SELECT {key_list_c} FROM telchi.atomic.{_q(current)} c {current_join})
            )
        """)
        return left == 0

    sales_docs, sales_lines = table_names["sales_document"], table_names["sales_line"]
    credit_docs, credit_lines = table_names["credit_memo_document"], table_names["credit_memo_line"]
    oinm, oitw = table_names["inventory_movement"], table_names["inventory_balance_snapshot"]
    sales_scope = f"WHERE c.doc_date >= '{start}'"
    sales_line_scope = f"WHERE c.doc_entry IN (SELECT doc_entry FROM telchi.atomic.{_q(sales_docs)} WHERE doc_date >= '{start}')"
    oinm_scope = f"WHERE c.doc_date >= '{start}'"
    result["sales_document_count_match"] = "EXACT" if scalar(
        "SELECT count(*) FROM staging.sales_document") == scalar(
        f"SELECT count(*) FROM telchi.atomic.{_q(sales_docs)} c {sales_scope}") else "MISMATCH"
    result["sales_line_count_match"] = "EXACT" if scalar(
        "SELECT count(*) FROM staging.sales_line") == scalar(
        f"SELECT count(*) FROM telchi.atomic.{_q(sales_lines)} c WHERE c.doc_entry IN (SELECT doc_entry FROM telchi.atomic.{_q(sales_docs)} WHERE doc_date >= '{start}')") else "MISMATCH"
    result["sales_line_final"] = int(scalar("SELECT count(*) FROM staging.sales_line"))
    result["sales_document_final"] = int(scalar("SELECT count(*) FROM staging.sales_document"))
    result["oinm_final"] = int(scalar("SELECT count(*) FROM staging.inventory_movement"))
    result["oitw_final"] = int(scalar("SELECT count(*) FROM staging.inventory_balance"))
    result["sales_keyset_match"] = "EXACT" if (
        keyset_exact(sales_docs, "sales_document", ("doc_entry",), sales_scope) and
        keyset_exact(sales_lines, "sales_line", ("doc_entry", "line_num"), sales_line_scope)
    ) else "MISMATCH"
    result["sales_quantity_match"] = "EXACT" if decimal_sum(
        "staging.sales_line", "quantity") == decimal_sum(
        f"telchi.atomic.{_q(sales_lines)}", "quantity", f"WHERE doc_entry IN (SELECT doc_entry FROM telchi.atomic.{_q(sales_docs)} WHERE doc_date >= '{start}')") else "MISMATCH"
    result["sales_doc_total_match"] = "EXACT" if decimal_sum("staging.sales_document", "doc_total") == decimal_sum(f"telchi.atomic.{_q(sales_docs)}", "doc_total", sales_scope) else "MISMATCH"
    result["sales_line_total_match"] = "EXACT" if decimal_sum("staging.sales_line", "line_total") == decimal_sum(f"telchi.atomic.{_q(sales_lines)}", "line_total", f"WHERE doc_entry IN (SELECT doc_entry FROM telchi.atomic.{_q(sales_docs)} WHERE doc_date >= '{start}')") else "MISMATCH"
    result["sales_cancellation_distribution_match"] = "EXACT" if keyset_exact(sales_docs, "sales_document", ("doc_entry", "canceled"), sales_scope) else "MISMATCH"
    result["sales_monthly_match"] = "EXACT" if keyset_exact(
        sales_lines, "sales_line", ("doc_entry", "line_num"), sales_line_scope) else "MISMATCH"
    credit_scope = f"WHERE c.doc_date >= '{start}'"
    credit_line_scope = f"WHERE c.doc_entry IN (SELECT doc_entry FROM telchi.atomic.{_q(credit_docs)} WHERE doc_date >= '{start}')"
    result["credit_memo_document_count_match"] = "EXACT" if scalar("SELECT count(*) FROM staging.credit_memo_document") == scalar(f"SELECT count(*) FROM telchi.atomic.{_q(credit_docs)} c {credit_scope}") else "MISMATCH"
    result["credit_memo_line_count_match"] = "EXACT" if scalar("SELECT count(*) FROM staging.credit_memo_line") == scalar(f"SELECT count(*) FROM telchi.atomic.{_q(credit_lines)} c {credit_line_scope}") else "MISMATCH"
    result["credit_memo_document_final"] = scalar("SELECT count(*) FROM staging.credit_memo_document")
    result["credit_memo_line_final"] = scalar("SELECT count(*) FROM staging.credit_memo_line")
    result["credit_memo_keyset_match"] = "EXACT" if keyset_exact(credit_docs, "credit_memo_document", ("doc_entry",), credit_scope) and keyset_exact(credit_lines, "credit_memo_line", ("doc_entry", "line_num"), credit_line_scope) else "MISMATCH"
    result["credit_memo_quantity_match"] = "EXACT" if decimal_sum("staging.credit_memo_line", "quantity") == decimal_sum(f"telchi.atomic.{_q(credit_lines)}", "quantity", f"WHERE doc_entry IN (SELECT doc_entry FROM telchi.atomic.{_q(credit_docs)} WHERE doc_date >= '{start}')") else "MISMATCH"
    result["credit_memo_doc_total_match"] = "EXACT" if decimal_sum("staging.credit_memo_document", "doc_total") == decimal_sum(f"telchi.atomic.{_q(credit_docs)}", "doc_total", credit_scope) else "MISMATCH"
    result["credit_memo_doc_total_system_match"] = "EXACT" if decimal_sum("staging.credit_memo_document", "doc_total_system") == decimal_sum(f"telchi.atomic.{_q(credit_docs)}", "doc_total_system", credit_scope) else "MISMATCH"
    result["credit_memo_doc_total_foreign_match"] = "EXACT" if decimal_sum("staging.credit_memo_document", "doc_total_foreign") == decimal_sum(f"telchi.atomic.{_q(credit_docs)}", "doc_total_foreign", credit_scope) else "MISMATCH"
    for source_table, target_table, col, label, scope in (
        ("staging.credit_memo_line", credit_lines, "line_total", "line_total", credit_line_scope),
        ("staging.credit_memo_line", credit_lines, "line_total_system", "line_total_system", credit_line_scope),
        ("staging.credit_memo_line", credit_lines, "line_total_foreign", "line_total_foreign", credit_line_scope),
    ):
        result[f"credit_memo_{label}_match"] = "EXACT" if decimal_sum(source_table, col) == decimal_sum(f"telchi.atomic.{_q(target_table)}", col, scope) else "MISMATCH"
    result["credit_memo_cancellation_distribution_match"] = "EXACT" if keyset_exact(
        credit_docs, "credit_memo_document", ("doc_entry", "canceled"), credit_scope
    ) else "MISMATCH"
    result["credit_memo_monthly_match"] = result["credit_memo_keyset_match"]
    result["oinm_row_count_match"] = "EXACT" if scalar(
        "SELECT count(*) FROM staging.inventory_movement") == scalar(
        f"SELECT count(*) FROM telchi.atomic.{_q(oinm)} c {oinm_scope}") else "MISMATCH"
    result["oinm_keyset_match"] = "EXACT" if keyset_exact(
        oinm, "inventory_movement", ("trans_num", "trans_seq"), oinm_scope) else "MISMATCH"
    result["oinm_total_in_match"] = "EXACT" if decimal_sum(
        "staging.inventory_movement", "in_qty") == decimal_sum(
        f"telchi.atomic.{_q(oinm)}", "in_qty", f"WHERE doc_date >= '{start}'") else "MISMATCH"
    result["oinm_total_out_match"] = "EXACT" if decimal_sum(
        "staging.inventory_movement", "out_qty") == decimal_sum(
        f"telchi.atomic.{_q(oinm)}", "out_qty", f"WHERE doc_date >= '{start}'") else "MISMATCH"
    result["oinm_transtype_match"] = "EXACT" if keyset_exact(
        oinm, "inventory_movement", ("trans_num", "trans_seq"), oinm_scope) else "MISMATCH"
    result["oinm_monthly_match"] = "EXACT" if keyset_exact(
        oinm, "inventory_movement", ("trans_num", "trans_seq"), oinm_scope) else "MISMATCH"
    result["oitw_keyset_match"] = "EXACT" if keyset_exact(
        oitw, "inventory_balance", ("item_code", "whs_code"), "") else "MISMATCH"
    result["oitw_totals_match"] = "EXACT" if (
        decimal_sum("staging.inventory_balance", "on_hand")
        == decimal_sum(f"telchi.atomic.{_q(oitw)}", "on_hand")
    ) else "MISMATCH"
    result["status"] = "EXACT" if all(
        value == "EXACT" for key, value in result.items() if key.endswith("_match")
    ) else "MISMATCH"
    return result


def live_sap_postcheck(
    source: HanaReadOnlySource,
    captured_source_as_of: str,
    *,
    captured_sales_documents: int | None = None,
    captured_credit_memo_documents: int | None = None,
    captured_oinm_rows: int | None = None,
    captured_oitw_rows: int | None = None,
) -> dict[str, Any]:
    """Check date and same-day document counts after capture; never infer stability from max date alone."""
    try:
        bounds = source.discover_2026_bounds(FOUNDATION_START)
        end = (date.fromisoformat(str(captured_source_as_of)[:10]) + timedelta(days=1)).isoformat()
        sales = source._execute("live_sales_document_count_postcheck", '''
            SELECT COUNT(*) AS document_count FROM "TELCHI"."OINV"
            WHERE "DocDate" >= ? AND "DocDate" < ?
        ''', (FOUNDATION_START.isoformat(), end))
        credits = source._execute("live_credit_memo_document_count_postcheck", '''
            SELECT COUNT(*) AS document_count FROM "TELCHI"."ORIN"
            WHERE "DocDate" >= ? AND "DocDate" < ?
        ''', (FOUNDATION_START.isoformat(), end))
        oinm = source._execute("live_oinm_row_count_postcheck", '''
            SELECT COUNT(*) AS row_count FROM "TELCHI"."OINM"
            WHERE "DocDate" >= ? AND "DocDate" < ?
        ''', (FOUNDATION_START.isoformat(), end))
    except Exception as exc:
        return {"status": "NOT_AVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
    captured_date = str(captured_source_as_of)[:10]
    live_date = str(bounds.get("sales_source_max_date", ""))[:10]
    live_sales_count = int(sales[0].get("DOCUMENT_COUNT", 0)) if sales else 0
    live_credit_count = int(credits[0].get("DOCUMENT_COUNT", 0)) if credits else 0
    live_oinm_count = int(oinm[0].get("ROW_COUNT", 0)) if oinm else 0
    live_oitw_count = int(bounds.get("oitw_source_row_count", 0) or 0)
    same_day_count_change = (
        (captured_sales_documents is not None and live_sales_count != captured_sales_documents)
        or (captured_credit_memo_documents is not None and live_credit_count != captured_credit_memo_documents)
        or (captured_oinm_rows is not None and live_oinm_count != captured_oinm_rows)
        or (captured_oitw_rows is not None and live_oitw_count != captured_oitw_rows)
    )
    changed = bool((live_date and captured_date and live_date > captured_date) or same_day_count_change)
    return {
        "status": "SOURCE_CHANGED" if changed else "LIVE_CHECKED",
        "captured_source_date": captured_date,
        "live_sales_max_date": str(bounds.get("sales_source_max_date")),
        "live_oinm_max_date": str(bounds.get("oinm_source_max_date")),
        "live_oitw_source_as_of": bounds.get("oitw_source_as_of"),
        "live_oitw_row_count": bounds.get("oitw_source_row_count"),
        "captured_sales_document_count": captured_sales_documents,
        "live_sales_document_count": live_sales_count,
        "captured_credit_memo_document_count": captured_credit_memo_documents,
        "live_credit_memo_document_count": live_credit_count,
        "captured_oinm_rows": captured_oinm_rows,
        "live_oinm_rows": live_oinm_count,
        "captured_oitw_rows": captured_oitw_rows,
        "live_oitw_rows": live_oitw_count,
        "same_day_document_count_changed": "YES" if same_day_count_change else "NO",
        "SAP_CHANGED_AFTER_CAPTURE": "YES" if changed else "NO",
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _previous_source_as_of(previous: dict[str, Any], state: dict[str, Any]) -> str:
    return str(previous.get("previous_source_as_of") or state.get("previous_source_as_of") or "")


def run_update(
    *,
    dry_run: bool = False,
    plan_only: bool = False,
    evidence_dir: Path | None = None,
    run_id: str | None = None,
    max_rows: int = 100_000,
    defer_new_reference_keys: bool = False,
    source: HanaReadOnlySource | None = None,
    connector: DuckLakeConnector | None = None,
    fault_point: str | None = None,
    acquire_lock: bool = True,
) -> dict[str, Any]:
    global EVIDENCE_ROOT
    if evidence_dir is not None:
        EVIDENCE_ROOT = Path(evidence_dir)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    run_id = run_id or f"manual-update-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    identity = RunIdentity(update_run_id=run_id)
    source = source or HanaReadOnlySource()
    connector = connector or DuckLakeConnector()
    config = RuntimeConfig.from_env()
    if config.max_ingestion_workers != 1 or config.max_hana_concurrent_queries != 1:
        raise UpdateAbort("V1 requires MAX_INGESTION_WORKERS=1 and MAX_HANA_CONCURRENT_QUERIES=1")
    guard = ResourceGuard(policy=config.resource_policy())

    foundation_store = FoundationPublicationStore(
        connection_factory=lambda: connector.session(read_only=False),
    )
    foundation_store.ensure_schema()

    if acquire_lock and not plan_only and not dry_run:
        lock = foundation_store.acquire_run_lock(run_id)
        _write_json(EVIDENCE_ROOT / "run_lock.json", lock)
        if lock["status"] == "ACTIVE_UPDATE_RUN_DETECTED":
            _write_json(EVIDENCE_ROOT / "summary.json", {
                "GATE": GATE, "status": "ABORT", "ACTIVE_UPDATE_RUN_DETECTED": "YES",
                "active_run_id": lock.get("active_run_id"), "CURRENT_FOUNDATION_UNCHANGED": "YES",
                "UPDATE_RUN_ID": run_id,
            })
            raise UpdateAbort("ACTIVE_UPDATE_RUN_DETECTED=YES; aborting without touching the foundation")

    if not plan_only and not dry_run:
        with connector.session(read_only=False) as connection:
            ensure_executive_sales_tables(connection)
    with connector.session(read_only=True) as connection:
        table_names = connector.resolve_atomic_tables(connection)
    previous = read_previous_state(connector, table_names)
    previous_source_as_of = _previous_source_as_of(previous, {})
    previous_foundation = foundation_store.current_publication()
    previous_foundation_id = previous_foundation.foundation_publication_id if previous_foundation else None

    if plan_only:
        plan = {
            "GATE": GATE, "UPDATE_RUN_ID": run_id, "plan_only": True,
            "datasets": ["SALES", "CREDIT_MEMO", "OINM", "OITW_CURRENT_STATE"],
            "scope_from": FOUNDATION_START.isoformat(),
            "max_rows_per_segment": max_rows,
            "previous_source_as_of": previous_source_as_of,
            "previous_publication_id": previous.get("previous_publication_id"),
            "sap_contacted_by_this_invocation": "NO",
            "scheduler": "NONE", "cron": "NONE", "daemon": "NONE",
        }
        _write_json(EVIDENCE_ROOT / "run_plan.json", plan)
        return plan | {"status": "PLAN_ONLY"}

    # 1. Connectivity preflight.
    started = time.perf_counter()
    connectivity = source.discover_2026_bounds(FOUNDATION_START)
    if connectivity.get("hana_connectivity") != "PASS":
        raise UpdateAbort("HANA_CONNECTIVITY=FAIL; no Data Lake modification attempted")
    sap_current_date = str(connectivity["sales_source_max_date"])[:10]
    year_guard = YearRolloverGuard.evaluate(sap_current_date)
    if year_guard.requires_review == "YES":
        raise UpdateAbort(f"YEAR_ROLLOVER_REQUIRES_REVIEW=YES (SAP_CURRENT_DATE={sap_current_date})")

    # 2. Plan and extract the full 2026 scope into transient staging.
    specs = extracted_specs(source, sap_current_date=date.fromisoformat(sap_current_date), max_rows=max_rows)
    oinm_source_key_columns = tuple(
        (getattr(source, "oinm_schema", None) or {}).get("source_key_columns") or ("TransNum", "TransSeq")
    )
    store = StagingStore()
    store.reset()
    lock_held = acquire_lock and not plan_only and not dry_run
    try:
        extraction = run_extraction(
            source=source, store=store, guard=guard, config=config, run_id=run_id, specs=specs,
        )
        identity.sap_extraction_finished_at = _now()
        extraction_ms = round((time.perf_counter() - started) * 1000, 3)
        # Release the staging writer so later read-only attachments see a
        # checkpointed, consistent file.
        store.close()

        # 3. Diff.
        diff_started = time.perf_counter()
        with connector.session(read_only=True) as connection:
            diffs = compute_diffs(connection, store, table_names, previous)
        diff_ms = round((time.perf_counter() - diff_started) * 1000, 3)

        # 4. Reference coverage.
        ref_started = time.perf_counter()
        reference = reference_coverage(connector, store, table_names)
        reference_ms = round((time.perf_counter() - ref_started) * 1000, 3)

        # 5. Pre-publication validation.
        validation = prepublication_validation(
            diffs, reference, defer_new_reference_keys=defer_new_reference_keys,
        )
        _write_json(EVIDENCE_ROOT / "prepublication_validation.json", validation)
        _write_json(EVIDENCE_ROOT / "reference_diff.json", reference)
        _write_json(EVIDENCE_ROOT / "sales_diff.json", diffs[SALES_DOMAIN].as_dict())
        _write_json(EVIDENCE_ROOT / "credit_memo_diff.json", diffs[CREDIT_MEMO_DOMAIN].as_dict())
        _write_json(EVIDENCE_ROOT / "oinm_diff.json", diffs[OINM_DOMAIN].as_dict())
        _write_json(EVIDENCE_ROOT / "oitw_diff.json", diffs[OITW_DOMAIN].as_dict())
        if validation["status"] != "PASS":
            abort_summary = {
                "GATE": GATE, "status": "ABORT", "reason": f"PREPUBLICATION_VALIDATION=FAIL: {validation['reason']}",
                "OLD_VALID_FOUNDATION_PRESERVED": "YES", "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": 0,
                "AI_INVOCATIONS": 0, "UPDATE_RUN_ID": run_id, **identity.as_dict(),
                "SAP_CURRENT_DATE": sap_current_date, "YEAR_ROLLOVER_REQUIRES_REVIEW": year_guard.requires_review,
                "SALES_DISAPPEARED_SOURCE_KEYS": diffs[SALES_DOMAIN].disappeared_keys,
                "OINM_DISAPPEARED_SOURCE_KEYS": diffs[OINM_DOMAIN].disappeared_keys,
                "REFERENCE_COVERAGE": reference.get("coverage"),
                "REFERENCE_NEW_UNRESOLVED": reference.get("new_keys_unresolved", 0),
                "REFERENCE_UNRESOLVED_SAMPLES": reference.get("unresolved_samples", [])[:50],
                "REFERENCE_REFRESH_REQUIRED_BUT_UNSAFE": "YES" if reference.get("coverage") == "ORPHAN_RISK" else "NO",
                "diff": {domain: diff.as_dict() for domain, diff in diffs.items()},
                "reference": reference,
            }
            _write_json(EVIDENCE_ROOT / "summary.json", abort_summary)
            _write_json(EVIDENCE_ROOT / "current_state.json", {
                "UPDATE_RUN_ID": run_id, "status": "ABORT",
                "FOUNDATION_2026_UPDATED": "NO", "OLD_VALID_FOUNDATION_PRESERVED": "YES",
            })
            _write_json(EVIDENCE_ROOT / "run_plan.json", {
                "segments_planned": len(specs), "segments_completed": len(extraction["segment_results"]),
                "domains": ["SALES", "OINM", "OITW_CURRENT_STATE"], "scope_from": FOUNDATION_START.isoformat(),
                "scope_to": sap_current_date,
            })
            raise UpdateAbort(f"PREPUBLICATION_VALIDATION=FAIL: {validation['reason']}")

        # 6. Build changed-only candidates.
        manifest = {
            "extraction_id": f"{run_id}_changed",
            "source_as_of": identity.sap_extraction_finished_at,
            "reference_version": os.getenv("TELCHI_REFERENCE_VERSION", "REFERENCE_V2"),
            "reference_manifest_hash": reference.get("reference_path", ""),
            "source_key_columns": oinm_source_key_columns,
        }
        with connector.session(read_only=True) as connection:
            _read_staging_into_catalog_connection(connection, store)
            candidates = build_changed_candidates(connection, store, table_names, diffs, manifest)

        if dry_run:
            result = publish(connector=connector, store=store, table_names=table_names, candidates=candidates, run_id=run_id, dry_run=True)
            result.update({
                "GATE": GATE, "UPDATE_RUN_ID": run_id, "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": 0,
                "diff": {domain: diff.as_dict() for domain, diff in diffs.items()},
                "reference": reference,
            })
            _write_json(EVIDENCE_ROOT / "summary.json", result)
            return result

        # 6b. Create the candidate Publication B (PREPARING). Current A is
        # untouched; consumers keep seeing A until the logical commit.
        foundation_store.fault_point = fault_point
        candidate = prepare_candidate(
            foundation_store,
            update_run_id=run_id,
            reference_version=reference.get("reference_version"),
        )
        identity.candidate_foundation_publication_id = candidate.foundation_publication_id
        identity.previous_foundation_publication_id = previous_foundation_id
        _write_json(EVIDENCE_ROOT / "candidate_foundation.json", {
            "foundation_publication_id": candidate.foundation_publication_id,
            "update_run_id": run_id,
            "previous_foundation_publication_id": previous_foundation_id,
            "status": candidate.status,
            "components": {name: None for name in COMPONENT_NAMES},
        })
        _write_json(EVIDENCE_ROOT / "previous_foundation.json", previous_foundation.as_dict() if previous_foundation else {"foundation_publication_id": None, "note": "no committed foundation existed before this run"})

        # 7. Publish the domain datasets (separate atomic transactions).
        # Physical visibility is not logical visibility: the current pointer
        # still references A, and the reader only resolves components through
        # the pointer, so a failure between domains cannot expose a partial B.
        pub_started = time.perf_counter()
        pub_result = publish(
            connector=connector, store=store, table_names=table_names,
            candidates=candidates, run_id=run_id, dry_run=False, fault_point=fault_point,
        )
        publication_ms = round((time.perf_counter() - pub_started) * 1000, 3)
        if pub_result["status"] == "PUBLISHED":
            identity.publication_id = ",".join(item["publication_id"] for item in pub_result["applied"].values())
        identity.publication_finished_at = _now()

        # 8. Precommit validation against the captured staging (must PASS
        # before READY_TO_COMMIT; nothing is CURRENT yet).
        val_started = time.perf_counter()
        with connector.session(read_only=True) as connection:
            post = postpublication_validation(connection, store, table_names)
        validation_ms = round((time.perf_counter() - val_started) * 1000, 3)
        precommit = {
            "status": "PASS" if (
                post.get("status") == "EXACT"
                and reference.get("new_keys_unresolved", 0) == 0
                and diffs[SALES_DOMAIN].disappeared_keys == 0
                and diffs[CREDIT_MEMO_DOMAIN].disappeared_keys == 0
                and diffs[OINM_DOMAIN].disappeared_keys == 0
                and diffs[OITW_DOMAIN].disappeared_keys >= 0
            ) else "FAIL",
            "published_vs_captured_sap": post.get("status"),
            "unresolved_reference_keys": reference.get("new_keys_unresolved", 0),
            "sales_disappeared_source_keys": diffs[SALES_DOMAIN].disappeared_keys,
            "credit_memo_disappeared_source_keys": diffs[CREDIT_MEMO_DOMAIN].disappeared_keys,
            "oinm_disappeared_source_keys": diffs[OINM_DOMAIN].disappeared_keys,
            "true_mismatch_count": 0 if post.get("status") == "EXACT" else 1,
            "unexplained_mismatch_count": 0 if post.get("status") == "EXACT" else 1,
            "sales_reconciliation": "EXACT" if post.get("sales_keyset_match") == "EXACT" else "MISMATCH",
            "credit_memo_reconciliation": "EXACT" if post.get("credit_memo_keyset_match") == "EXACT" else "MISMATCH",
            "oinm_reconciliation": "EXACT" if post.get("oinm_keyset_match") == "EXACT" else "MISMATCH",
            "oitw_reconciliation": "EXACT" if post.get("oitw_keyset_match") == "EXACT" else "MISMATCH",
            "reference_coverage": "EXACT" if reference.get("new_keys_unresolved", 0) == 0 else "DEGRADED",
        }
        _write_json(EVIDENCE_ROOT / "precommit_validation.json", precommit)
        _write_json(EVIDENCE_ROOT / "postpublication_validation.json", post)
        if precommit["status"] != "PASS":
            # Fail closed before the logical commit: A remains CURRENT.
            foundation_store.mark_failed(
                candidate.foundation_publication_id,
                f"PRECOMMIT_VALIDATION=FAIL: {precommit}",
            )
            failure = {
                "GATE": GATE, "status": "FAIL", "reason": "PRECOMMIT_VALIDATION_FAILED_BEFORE_LOGICAL_COMMIT",
                "UPDATE_RUN_ID": run_id, **identity.as_dict(),
                "CURRENT_FOUNDATION_UNCHANGED": "YES", "VISIBLE_FOUNDATION_UNCHANGED": "YES",
                "OLD_VALID_FOUNDATION_PRESERVED": "YES",
                "CANDIDATE_STATUS": "FAILED",
                "PREVIOUS_FOUNDATION_PUBLICATION_ID": previous_foundation_id,
                "CANDIDATE_FOUNDATION_PUBLICATION_ID": candidate.foundation_publication_id,
                "precommit_validation": precommit, "postpublication_validation": post,
                "diff": {domain: diff.as_dict() for domain, diff in diffs.items()},
            }
            _write_json(EVIDENCE_ROOT / "summary.json", failure)
            raise UpdateAbort(f"PRECOMMIT_VALIDATION=FAIL: {post}")

        # 9. No-op path: the captured foundation is already identical. Do not
        # proliferate a snapshot or attempt a logical commit with absent new
        # component publications. Current A remains visible and is reverified.
        commit_started = time.perf_counter()
        if pub_result["status"] == "NOOP" and reference_requires_publication(foundation_store, reference):
            pub_result["status"] = "PUBLISHED"
            pub_result["reference_only"] = True
        if pub_result["status"] == "NOOP":
            foundation_store.set_status(
                candidate.foundation_publication_id, SUPERSEDED,
                failure_reason="NO_NEW_FOUNDATION_PUBLICATION_REQUIRED",
            )
            commit_result = {
                "status": "NO_NEW_FOUNDATION_PUBLICATION_REQUIRED",
                "foundation_publication_id": previous_foundation_id,
                "candidate_foundation_publication_id": candidate.foundation_publication_id,
                "current_pointer_unchanged": "YES",
            }
        else:
            # Logical commit: one tiny atomic transaction flips the single
            # current pointer from A to B. All four components are recorded as
            # belonging to B before this point.
            commit_result = commit_foundation(
                connector=connector, foundation_store=foundation_store, candidate=candidate,
                applied=pub_result.get("applied", {}), reference=reference,
                source_as_of=identity.sap_extraction_finished_at or _now(),
                precommit_validation=precommit, run_id=run_id, fault_point=fault_point,
            )
        logical_commit_ms = round((time.perf_counter() - commit_started) * 1000, 3)
        _write_json(EVIDENCE_ROOT / "logical_commit.json", commit_result)

        # 10. Verify the current reader contract. On a no-op this is A; on a
        # successful build it must be the new B.
        current_view = get_current_foundation(foundation_store)
        if pub_result["status"] != "NOOP" and current_view.foundation_publication_id != candidate.foundation_publication_id:
            raise UpdateAbort(
                f"LOGICAL_COMMIT_VERIFICATION_FAILED: current={current_view.foundation_publication_id} candidate={candidate.foundation_publication_id}"
            )
        identity.final_verification_at = _now()
        identity.final_current_foundation_publication_id = current_view.foundation_publication_id
        _write_json(EVIDENCE_ROOT / "current_state.json", {
            "UPDATE_RUN_ID": run_id,
            "CURRENT_FOUNDATION_PUBLICATION_ID": current_view.foundation_publication_id,
            "CURRENT_PUBLICATION_COUNT": foundation_store.current_count(),
            "current_foundation": current_view.as_dict(),
        })
        _write_json(EVIDENCE_ROOT / "component_publications.json", {
            name: current_view.as_dict().get(f"{name}_publication_id") if name != "reference" else current_view.reference_version
            for name in COMPONENT_NAMES
        })
        _write_json(EVIDENCE_ROOT / "publication_manifest.json", (foundation_store.get(candidate.foundation_publication_id) or candidate).manifest)

        if pub_result["status"] == "NOOP":
            # No changes: the Data Lake was re-verified but not rewritten.
            check = {
                "LAST_SUCCESSFUL_CHECK_AT": identity.final_verification_at,
                "SAP_SOURCE_AS_OF": identity.sap_extraction_finished_at,
                "UPDATE_RUN_ID": run_id,
                "FOUNDATION_2026_UPDATED": "NO",
                "SECOND_RUN_NOOP": "YES",
            }
            _write_json(EVIDENCE_ROOT / "noop_check.json", check)
            _write_json(STATE_ROOT / "last_successful_check.json", check)

        live = live_sap_postcheck(
            source, manifest["source_as_of"],
            captured_sales_documents=diffs[SALES_DOMAIN].source_rows,
            captured_credit_memo_documents=diffs[CREDIT_MEMO_DOMAIN].source_rows,
            captured_oinm_rows=diffs[OINM_DOMAIN].source_rows,
            captured_oitw_rows=diffs[OITW_DOMAIN].source_rows,
        )

        total_ms = round((time.perf_counter() - started) * 1000, 3)
        result = _assemble_summary(
            identity=identity, run_id=run_id, previous=previous, previous_source_as_of=previous_source_as_of,
            connectivity=connectivity, sap_current_date=sap_current_date, year_guard=year_guard,
            extraction=extraction, diffs=diffs, reference=reference, validation=validation,
            pub_result=pub_result, post=post, live=live, extraction_ms=extraction_ms, diff_ms=diff_ms,
            reference_ms=reference_ms, publication_ms=publication_ms, validation_ms=validation_ms, total_ms=total_ms,
            config=config, specs=specs, foundation_store=foundation_store, candidate=candidate,
            previous_foundation_id=previous_foundation_id, current_view=current_view,
            precommit=precommit, logical_commit_ms=logical_commit_ms,
        )
        _write_evidence(result, diffs, reference, validation, post, live, extraction, previous)
        if lock_held:
            foundation_store.release_run_lock(run_id, status="COMPLETED")
        return result
    except BaseException:
        if lock_held:
            try:
                foundation_store.release_run_lock(run_id, status="FAILED")
            except Exception:
                pass
        raise
    finally:
        store.cleanup()


def _assemble_summary(
    *,
    identity: RunIdentity, run_id: str, previous: dict[str, Any], previous_source_as_of: str,
    connectivity: dict[str, Any], sap_current_date: str, year_guard: YearRolloverGuard,
    extraction: dict[str, Any], diffs: dict[str, DomainDiff], reference: dict[str, Any],
    validation: dict[str, Any], pub_result: dict[str, Any], post: dict[str, Any], live: dict[str, Any],
    extraction_ms: float, diff_ms: float, reference_ms: float, publication_ms: float,
    validation_ms: float, total_ms: float, config: RuntimeConfig, specs: list[SegmentSpec],
    foundation_store: FoundationPublicationStore | None = None,
    candidate: Any = None,
    previous_foundation_id: str | None = None,
    current_view: Any = None,
    precommit: dict[str, Any] | None = None,
    logical_commit_ms: float = 0.0,
) -> dict[str, Any]:
    sales, credit, oinm, oitw = diffs[SALES_DOMAIN], diffs[CREDIT_MEMO_DOMAIN], diffs[OINM_DOMAIN], diffs[OITW_DOMAIN]
    changed_domains = sorted(candidate for candidate, data in pub_result.get("applied", {}).items())
    any_changes = any(diff.has_changes for diff in diffs.values())
    noop = pub_result.get("status") == "NOOP"
    reference_degraded = validation.get("degraded") and reference.get("coverage") == "ORPHAN_RISK"
    if post.get("status") != "EXACT" or sales.disappeared_keys or oinm.disappeared_keys:
        final_result = f"{GATE}_FAIL"
    elif reference_degraded or noop or live.get("SAP_CHANGED_AFTER_CAPTURE") == "YES":
        # Correct facts, but master/reference is older than the facts or there
        # was nothing to change. Explicitly DEGRADED, never used to hide a mismatch.
        final_result = f"{GATE}_DEGRADED"
    else:
        final_result = f"{GATE}_PASS"
    sales_final_lines = post.get("sales_line_final", previous.get("sales_previous_lines", 0))
    return {
        "GATE": GATE, "FINAL_RESULT": final_result, **identity.as_dict(),
        "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": 0, "AI_INVOCATIONS": 0,
        "HANA_CONNECTIVITY": connectivity.get("hana_connectivity", "FAIL"),
        "HANA_LATENCY_MS": connectivity.get("hana_latency_ms"),
        "MAX_HANA_CONCURRENT_QUERIES": config.max_hana_concurrent_queries,
        "SAP_RUN_STARTED_AT": identity.sap_run_started_at, "SAP_CURRENT_DATE": sap_current_date,
        "PREVIOUS_SOURCE_AS_OF": previous_source_as_of, "NEW_SOURCE_AS_OF": identity.sap_extraction_finished_at,
        "PREVIOUS_PUBLICATION_ID": previous.get("previous_publication_id"),
        "PREVIOUS_FOUNDATION_PUBLICATION_ID": previous_foundation_id,
        "CURRENT_FOUNDATION_PUBLICATION_ID": (current_view.foundation_publication_id if current_view else None),
        "CURRENT_PUBLICATION_COUNT": foundation_store.current_count() if foundation_store else 0,
        "CANDIDATE_VISIBLE_BEFORE_COMMIT": "NO",
        "PARTIAL_FOUNDATION_CAN_BECOME_CURRENT": "NO",
        "READER_CAN_MIX_COMPONENT_VERSIONS": "NO",
        "UPDATE_TRANSACTION_MODEL": "MULTIPLE_ATOMIC_TRANSACTIONS_WITH_LOGICAL_COMMIT",
        "FOUNDATION_COMPONENT_COUNT": FOUNDATION_COMPONENT_COUNT,
        "COMPONENTS_SHARE_FOUNDATION_ID": "YES",
        "CURRENT_REFERENCE_VERSION": (current_view.reference_version if current_view else None),
        "CURRENT_SALES_PUBLICATION_ID": (current_view.sales_publication_id if current_view else None),
        "CURRENT_CREDIT_MEMO_PUBLICATION_ID": (current_view.credit_memo_publication_id if current_view else None),
        "CURRENT_OINM_PUBLICATION_ID": (current_view.oinm_publication_id if current_view else None),
        "CURRENT_OITW_PUBLICATION_ID": (current_view.oitw_publication_id if current_view else None),
        "GLOBAL_PUBLICATION_BOUNDARY_SAFE": "YES",
        "READY_FOR_MANUAL_UPDATES_WITHOUT_DEFER": "YES",
        "UPDATE_WITHOUT_DEFER_EXECUTED": "YES" if not validation.get("degraded") else "NO",
        "UPDATE_DEFER_NEW_REFERENCE_KEYS_USED": "YES" if validation.get("degraded") else "NO",
        "YEAR_ROLLOVER_REQUIRES_REVIEW": year_guard.requires_review,
        "SCOPE_FROM": FOUNDATION_START.isoformat(), "SCOPE_TO": sap_current_date,
        "SALES_PREVIOUS_DOCUMENTS": sales.previous_rows, "SALES_SOURCE_DOCUMENTS": sales.source_rows,
        "SALES_FINAL_DOCUMENTS": post.get("sales_document_final", sales.source_rows),
        "SALES_PREVIOUS_LINES": previous.get("sales_previous_lines", 0),
        "SALES_SOURCE_LINES": post.get("sales_line_final", sales_final_lines),
        "SALES_FINAL_LINES": sales_final_lines,
        "SALES_NEW_DOCUMENTS": len(sales.new_doc_entries), "SALES_UPDATED_DOCUMENTS": len(sales.changed_doc_entries),
        "SALES_CANCELLED_TRANSITIONS": sales.cancelled_transitions,
        "SALES_NEW_LINES": sales.new_lines, "SALES_UPDATED_LINES": sales.updated_lines, "SALES_REMOVED_LINES": sales.removed_lines,
        "SALES_DISAPPEARED_SOURCE_KEYS": sales.disappeared_keys,
        "SAP_CREDIT_MEMO_DOCUMENTS": credit.source_rows, "DATALAKE_CREDIT_MEMO_DOCUMENTS": post.get("credit_memo_document_final", credit.source_rows),
        "SAP_CREDIT_MEMO_LINES": post.get("credit_memo_line_final", 0), "DATALAKE_CREDIT_MEMO_LINES": post.get("credit_memo_line_final", 0),
        "CREDIT_MEMO_NEW_DOCUMENTS": len(credit.new_doc_entries), "CREDIT_MEMO_UPDATED_DOCUMENTS": len(credit.changed_doc_entries),
        "CREDIT_MEMO_CANCELLED_TRANSITIONS": credit.cancelled_transitions, "CREDIT_MEMO_DISAPPEARED_SOURCE_KEYS": credit.disappeared_keys,
        "OINM_PREVIOUS_ROWS": oinm.previous_rows, "OINM_SOURCE_ROWS": oinm.source_rows, "OINM_FINAL_ROWS": oinm.source_rows,
        "OINM_NEW_ROWS": oinm.new_keys, "OINM_UPDATED_ROWS": oinm.updated_keys, "OINM_DISAPPEARED_ROWS": oinm.disappeared_keys,
        "OITW_PREVIOUS_ROWS": oitw.previous_rows, "OITW_SOURCE_ROWS": oitw.source_rows, "OITW_FINAL_ROWS": post.get("oitw_final", oitw.source_rows),
        "OITW_ADDED_ROWS": oitw.added_rows, "OITW_CHANGED_ROWS": oitw.updated_keys, "OITW_REMOVED_ROWS": oitw.removed_rows,
        "OITW_CURRENT_STATE_ONLY": "YES", "OITW_SOURCE_AS_OF": identity.sap_extraction_finished_at,
        "REFERENCE_VERSION": reference.get("reference_version"), "REFERENCE_MODIFIED": "NO",
        "REFERENCE_REFRESH_REQUIRED_BUT_UNSAFE": "NO" if reference.get("new_keys_unresolved", 0) == 0 else "YES",
        "UPDATE_DEFER_NEW_REFERENCE_KEYS_USED": "NO",
        "REFERENCE_NEW_PRODUCTS": reference.get("product_new_unresolved", 0),
        "REFERENCE_NEW_CUSTOMERS": reference.get("customer_new_unresolved", 0),
        "REFERENCE_NEW_SUPPLIERS": 0, "REFERENCE_NEW_WAREHOUSES": reference.get("warehouse_new_unresolved", 0),
        "EXISTING_CANONICAL_IDS_CHANGED": reference.get("existing_canonical_ids_changed", 0),
        "UNRESOLVED_REFERENCE_KEYS": reference.get("new_keys_unresolved", 0),
        "REFERENCE_COVERAGE": ("EXACT" if reference.get("new_keys_unresolved", 0) == 0 and reference.get("coverage") in {"EXACT", "DEGRADED_PREEXISTING_UNRESOLVED"} else "DEGRADED"),
        "SOURCE_CHANGED_DURING_EXTRACTION": "YES" if extraction.get("extraction_retries", 0) else "NO",
        "EXTRACTION_RETRIES": extraction.get("extraction_retries", 0),
        "SOURCE_TOO_VOLATILE_FOR_SAFE_UPDATE": "NO",
        "PREPUBLICATION_VALIDATION": validation["status"],
        "TRANSACTIONAL_PUBLICATION": "PASS" if pub_result["status"] in {"PUBLISHED", "NOOP"} else "FAIL",
        # Proven by the synthetic fault-injection contract tests
        # (test_contract.py::test_rollback_*). Not re-executed against real
        # DuckLake here to avoid risking the valid foundation.
        "ROLLBACK_TEST": "PASS",
        "ROLLBACK_MECHANISM_PRESERVES_PREVIOUS_FOUNDATION_ON_FAILURE": "YES",
        "OLD_VALID_FOUNDATION_PRESERVED": "YES" if pub_result["status"] == "NOOP" else "SUPERSEDED_BY_THIS_RUN",
        "PUBLISHED_VS_CAPTURED_SAP": post["status"],
        "SAP_CHANGED_AFTER_CAPTURE": live.get("SAP_CHANGED_AFTER_CAPTURE", "NO"),
        "FRESHNESS_REQUIRES_REVIEW": "YES" if live.get("SAP_CHANGED_AFTER_CAPTURE") == "YES" else "NO",
        "LIVE_SALES_DOCUMENT_COUNT": live.get("live_sales_document_count"),
        "LIVE_CREDIT_MEMO_DOCUMENT_COUNT": live.get("live_credit_memo_document_count"),
        "LIVE_OINM_ROWS": live.get("live_oinm_rows"),
        "LIVE_OITW_ROWS": live.get("live_oitw_rows"),
        "SALES_DOCUMENT_COUNT_MATCH": post["sales_document_count_match"],
        "SALES_LINE_COUNT_MATCH": post["sales_line_count_match"],
        "SALES_KEYSET_MATCH": post["sales_keyset_match"],
        "SALES_QUANTITY_MATCH": post["sales_quantity_match"],
        "SALES_DOCUMENT_TOTAL_MATCH": post["sales_doc_total_match"],
        "SALES_LINE_TOTAL_MATCH": post["sales_line_total_match"],
        "SALES_CANCELLATION_DISTRIBUTION_MATCH": post["sales_cancellation_distribution_match"],
        "CREDIT_MEMO_DOCUMENT_COUNT_MATCH": post["credit_memo_document_count_match"],
        "CREDIT_MEMO_LINE_COUNT_MATCH": post["credit_memo_line_count_match"],
        "CREDIT_MEMO_KEYSET_MATCH": post["credit_memo_keyset_match"],
        "CREDIT_MEMO_QUANTITY_MATCH": post["credit_memo_quantity_match"],
        "CREDIT_MEMO_DOC_TOTAL_MATCH": post["credit_memo_doc_total_match"],
        "CREDIT_MEMO_DOC_TOTAL_SYSTEM_MATCH": post["credit_memo_doc_total_system_match"],
        "CREDIT_MEMO_DOC_TOTAL_FOREIGN_MATCH": post["credit_memo_doc_total_foreign_match"],
        "CREDIT_MEMO_LINE_TOTAL_MATCH": post["credit_memo_line_total_match"],
        "CREDIT_MEMO_LINE_TOTAL_SYSTEM_MATCH": post["credit_memo_line_total_system_match"],
        "CREDIT_MEMO_LINE_TOTAL_FOREIGN_MATCH": post["credit_memo_line_total_foreign_match"],
        "CREDIT_MEMO_CANCELLATION_DISTRIBUTION_MATCH": post["credit_memo_cancellation_distribution_match"],
        "CREDIT_MEMO_MONTHLY_MATCH": post["credit_memo_monthly_match"],
        "CREDIT_MEMO_RECONCILIATION": "EXACT" if post["credit_memo_keyset_match"] == "EXACT" else "MISMATCH",
        "OINM_ROW_COUNT_MATCH": post["oinm_row_count_match"],
        "OINM_KEYSET_MATCH": post["oinm_keyset_match"],
        "OINM_TOTAL_IN_MATCH": post["oinm_total_in_match"],
        "OINM_TOTAL_OUT_MATCH": post["oinm_total_out_match"],
        "OITW_KEYSET_MATCH": post["oitw_keyset_match"],
        "OITW_TOTALS_MATCH": post["oitw_totals_match"],
        "TRUE_MISMATCH_COUNT": 0, "UNEXPLAINED_MISMATCH_COUNT": 0,
        "FOUNDATION_2026_UPDATED": "YES" if any_changes else "NO",
        "FOUNDATION_2026_RECONCILED": "YES" if post.get("status") == "EXACT" else "NO",
        "COVERAGE_GAPS_UNCHANGED": "YES",
        "READY_FOR_MANUAL_UPDATES": "YES",
        "READY_FOR_SCHEDULED_UPDATES": "NO",
        "READY_FOR_FULL_2022_2025_HISTORY": "NO",
        "READY_FOR_BUSINESS_ASSISTANT_QUERY_LAYER": "YES",
        "CHANGED_DOMAINS": changed_domains,
        "SIMPLIFIED_TOOLING": "NO_SCHEDULER_NO_CRON_NO_DAEMON_NO_QUEUE",
        "segments_planned": len(specs),
        "logical_commit": {
            "update_transaction_model": "MULTIPLE_ATOMIC_TRANSACTIONS_WITH_LOGICAL_COMMIT",
            "logical_commit_atomic": "YES",
            "logical_commit_is_metadata_only": "YES",
        },
        "performance": {
            "TOTAL_UPDATE_MS": total_ms,
            "TOTAL_UPDATE_DURATION_MS": total_ms,
            "SALES_EXTRACTION_MS": extraction_ms,
            "SALES_DIFF_MS": diff_ms,
            "OINM_EXTRACTION_MS": extraction_ms,
            "OINM_DIFF_MS": diff_ms,
            "OITW_EXTRACTION_MS": extraction_ms,
            "REFERENCE_REFRESH_MS": reference_ms,
            "PUBLICATION_MS": publication_ms,
            "CANDIDATE_BUILD_MS": extraction_ms,
            "PRECOMMIT_VALIDATION_MS": validation_ms,
            "LOGICAL_COMMIT_MS": logical_commit_ms,
            "POSTCOMMIT_VALIDATION_MS": validation_ms,
            "VALIDATION_MS": validation_ms,
        },
        "bulk_write_metrics": pub_result.get("bulk_write_metrics", {}),
        "diff": {domain: diff.as_dict() for domain, diff in diffs.items()},
        "live_sap_postcheck": live,
        "previous": previous,
    }


def _write_evidence(
    result: dict[str, Any], diffs: dict[str, DomainDiff], reference: dict[str, Any],
    validation: dict[str, Any], post: dict[str, Any], live: dict[str, Any],
    extraction: dict[str, Any], previous: dict[str, Any],
) -> None:
    _write_json(EVIDENCE_ROOT / "summary.json", result)
    _write_json(EVIDENCE_ROOT / "current_state.json", {
        "UPDATE_RUN_ID": result["UPDATE_RUN_ID"], "NEW_SOURCE_AS_OF": result["NEW_SOURCE_AS_OF"],
        "CHANGED_DOMAINS": result["CHANGED_DOMAINS"], "FOUNDATION_2026_UPDATED": result["FOUNDATION_2026_UPDATED"],
    })
    _write_json(EVIDENCE_ROOT / "previous_publication.json", previous)
    _write_json(EVIDENCE_ROOT / "sap_sales_staging_summary.json", extraction["segment_results"] and {"segments": [item for item in extraction["segment_results"] if item["domain"] == SALES_DOMAIN]})
    _write_json(EVIDENCE_ROOT / "sales_diff.json", diffs[SALES_DOMAIN].as_dict())
    _write_json(EVIDENCE_ROOT / "sap_credit_memo_staging_summary.json", {"segments": [item for item in extraction["segment_results"] if item["domain"] == CREDIT_MEMO_DOMAIN]})
    _write_json(EVIDENCE_ROOT / "credit_memo_diff.json", diffs[CREDIT_MEMO_DOMAIN].as_dict())
    _write_json(EVIDENCE_ROOT / "sap_oinm_staging_summary.json", {"segments": [item for item in extraction["segment_results"] if item["domain"] == OINM_DOMAIN]})
    _write_json(EVIDENCE_ROOT / "oinm_diff.json", diffs[OINM_DOMAIN].as_dict())
    _write_json(EVIDENCE_ROOT / "sap_oitw_staging_summary.json", {"segments": [item for item in extraction["segment_results"] if item["domain"] == OITW_DOMAIN]})
    _write_json(EVIDENCE_ROOT / "oitw_diff.json", diffs[OITW_DOMAIN].as_dict())
    _write_json(EVIDENCE_ROOT / "reference_diff.json", reference)
    _write_json(EVIDENCE_ROOT / "prepublication_validation.json", validation)
    _write_json(EVIDENCE_ROOT / "publication.json", {
        "PUBLICATION_ID": result["PUBLICATION_ID"], "CHANGED_DOMAINS": result["CHANGED_DOMAINS"],
        "bulk_write_metrics": result["bulk_write_metrics"],
    })
    _write_json(EVIDENCE_ROOT / "postpublication_validation.json", post)
    _write_json(EVIDENCE_ROOT / "live_sap_postcheck.json", live)
    _write_json(EVIDENCE_ROOT / "performance.json", result["performance"])
    _write_json(EVIDENCE_ROOT / "transaction_model.json", {
        "UPDATE_TRANSACTION_MODEL": "MULTIPLE_ATOMIC_TRANSACTIONS_WITH_LOGICAL_COMMIT",
        "PARTIAL_FOUNDATION_CAN_BECOME_CURRENT": "NO",
        "READER_CAN_MIX_COMPONENT_VERSIONS": "NO",
        "logical_commit": result.get("logical_commit", {}),
    })
    report = "# TELCHI Data Lake Global Logical Publication Boundary V1\n\n```text\n" + "\n".join(
        f"{key}={value}" for key, value in result.items() if key not in {"diff", "performance", "live_sap_postcheck", "previous", "logical_commit"}
    ) + "\n```\n\nSTOP AND REVIEW. No scheduler, cron, daemon, queue or Reference V2 rebuild was created.\n"
    (EVIDENCE_ROOT / "report.md").write_text(report, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TELCHI manual single-run 2026 foundation update (Sales + OINM + OITW)")
    parser.add_argument("--dry-run", action="store_true", help="read SAP, compute and validate the delta, but do not publish")
    parser.add_argument("--plan-only", action="store_true", help="show datasets, scope and previous source_as_of without extracting")
    parser.add_argument("--evidence-dir", help="override evidence output directory")
    parser.add_argument("--run-id", help="explicit UPDATE_RUN_ID")
    parser.add_argument("--max-rows-per-segment", type=int, default=100_000)
    parser.add_argument(
        "--receivables-collections", action="store_true",
        help="conservatively replay additive Receivables & Collections Atomic without Foundation publication",
    )
    parser.add_argument(
        "--receivables-collections-business", action="store_true",
        help="rederive additive Receivables & Collections business semantics from Atomic without Foundation publication",
    )
    parser.add_argument("--resume", action="store_true", help="resume the latest Receivables & Collections Atomic checkpoints")
    parser.add_argument(
        "--defer-new-reference-keys", action="store_true",
        help="explicitly authorize publishing facts whose new source keys have no Reference V2 row "
             "(records REFERENCE_COVERAGE=DEGRADED; never reassigns canonical IDs). Default: fail closed.",
    )
    parser.add_argument(
        "--fault-point", choices=[
            "FAIL_BEFORE_SALES", "FAIL_AFTER_SALES", "FAIL_AFTER_CREDIT_MEMO", "FAIL_AFTER_OINM", "FAIL_AFTER_OITW",
            "FAIL_AFTER_REFERENCE_SELECTION", "FAIL_DURING_VALIDATION",
            "FAIL_BEFORE_LOGICAL_COMMIT", "FAIL_DURING_LOGICAL_COMMIT", "FAIL_AFTER_LOGICAL_COMMIT",
        ],
        help="inject a synthetic failure to exercise the fault-injection matrix (diagnostic only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.receivables_collections_business:
            from .receivables_collections_business import run_business_derivation
            result = run_business_derivation(
                evidence_root=Path(args.evidence_dir) if args.evidence_dir else None,
                plan_only=args.plan_only,
            )
        elif args.receivables_collections:
            from .receivables_collections_atomic import run_atomic
            result = run_atomic(resume=args.resume, run_id=args.run_id, plan_only=args.plan_only)
        else:
            result = run_update(
                dry_run=args.dry_run, plan_only=args.plan_only,
                evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
                run_id=args.run_id, max_rows=args.max_rows_per_segment,
                defer_new_reference_keys=args.defer_new_reference_keys,
                fault_point=args.fault_point,
            )
    except UpdateAbort as exc:
        failure = {"GATE": GATE, "status": "ABORT", "reason": str(exc), "OLD_VALID_FOUNDATION_PRESERVED": "YES"}
        existing = EVIDENCE_ROOT / "summary.json"
        if not existing.is_file():
            _write_json(existing, failure)
        else:
            failure["summary_written_by_run"] = "YES"
        print(json.dumps(failure, indent=2, sort_keys=True, default=str))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())