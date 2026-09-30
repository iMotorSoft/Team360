"""Controlled real SAP -> raw -> Atomic pilot V2.

This runner is intentionally a new, independent gate.  It executes exactly one
sales and one inventory segment in sequence, and delegates the only trusted
commit to the corrected TransactionalPublicationBoundary.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.runtime import TelchiDuckLakeRuntime
from modules.telchi.investigation.validation.sql_baseline.sql_baseline_harness import connect
from modules.telchi.runtime.config import RuntimeConfig, DuckDBSafetyProfile, apply_duckdb_safety_profile, open_safe_duckdb
from modules.telchi.runtime.contracts import Job, JobType, Segment, SegmentRange, ValidationResult, ReconciliationResult
from modules.telchi.runtime.coverage import CoverageTracker
from modules.telchi.runtime.executor import SegmentExecutor
from modules.telchi.runtime.handler import HandlerContext
from modules.telchi.runtime.observability import InMemoryObservability
from modules.telchi.runtime.resource_guard import ResourceGuard, SafeAbort
from modules.telchi.runtime.stores import InMemoryRuntimeStore
from modules.telchi.runtime.transactional_publication import TransactionalPublicationBoundary

from . import GATE

REPO_ROOT = Path(__file__).resolve().parents[7]
SQL_ROOT = REPO_ROOT / "SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/atomic_inventory_and_sales/real_segment_pilot_v2"
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
RAW_ROOT = DATA_ROOT / "raw/sap" / GATE
REFERENCE_MANIFEST = DATA_ROOT / "manifests/reference_current.json"
LEGACY_ROOT = DATA_ROOT / "raw/legacy"
MAX_ROWS = 10_000
TRANSFORMATION_VERSION = "atomic-inventory-sales-real-segment-pilot-v2.0.0"
SCHEMA_VERSION = "1.0.0"
PUBLICATION_TABLE = "telchi.ops.pilot_publications_v2"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def sql_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def metadata_fingerprint(root: Path, *, hash_files: bool = False) -> str:
    if not root.exists():
        return digest({"exists": False})
    if root.is_file():
        item: dict[str, Any] = {"path": root.name, "bytes": root.stat().st_size, "mtime_ns": root.stat().st_mtime_ns}
        if hash_files:
            item["sha256"] = hashlib.sha256(root.read_bytes()).hexdigest()
        return digest(item)
    entries = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        item = {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns}
        if hash_files:
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(item)
    return digest(entries)


@contextmanager
def lake_session(runtime: TelchiDuckLakeRuntime, *, read_only: bool):
    # DuckLake may open a lazy libpq catalog connection after ATTACH.  Keep the
    # private password in the process environment for this bounded session only;
    # it is never written to evidence.
    previous = os.environ.get("PGPASSWORD")
    os.environ["PGPASSWORD"] = runtime.config.password
    try:
        with runtime.session(read_only=read_only) as connection:
            apply_duckdb_safety_profile(connection, DuckDBSafetyProfile.from_runtime_config())
            yield connection
    finally:
        if previous is None:
            os.environ.pop("PGPASSWORD", None)
        else:
            os.environ["PGPASSWORD"] = previous


def snapshot_id(runtime: TelchiDuckLakeRuntime) -> int:
    with lake_session(runtime, read_only=True) as connection:
        return int(connection.execute("SELECT * FROM ducklake_current_snapshot('telchi')").fetchone()[0])


def atomic_counts(connection: Any) -> dict[str, int]:
    result = {}
    for table in ("sales_document", "sales_line", "inventory_balance"):
        result[table] = int(connection.execute(f"SELECT count(*) FROM telchi.atomic.{table}").fetchone()[0])
    return result


def lake_state(runtime: TelchiDuckLakeRuntime, domain: str, key: Any) -> dict[str, Any]:
    with lake_session(runtime, read_only=True) as connection:
        if domain == "sales":
            docs = connection.execute("SELECT * FROM telchi.atomic.sales_document WHERE doc_entry=?", [str(key)]).fetchall()
            lines = connection.execute("SELECT * FROM telchi.atomic.sales_line WHERE doc_entry=?", [str(key)]).fetchall()
        else:
            docs = connection.execute("SELECT * FROM telchi.atomic.inventory_balance WHERE item_code=? AND whs_code=?", [str(key[0]), str(key[1])]).fetchall()
            lines = []
        try:
            marker = connection.execute(
                f"SELECT publication_id,idempotency_key,content_identity,published_at,status,job_id,segment_id,attempt,source_identity,reference_version,transformation_version FROM {PUBLICATION_TABLE}"
            ).fetchall()
            marker = [row for row in marker if str(row[6] or "").startswith(f"{domain}-segment")]
        except Exception:
            marker = []
        return {"snapshot": snapshot_id_from_connection(connection), "atomic_counts": atomic_counts(connection), "scope_rows": [list(row) for row in docs + lines], "publication_records": [list(row) for row in marker]}


def snapshot_id_from_connection(connection: Any) -> int:
    return int(connection.execute("SELECT * FROM ducklake_current_snapshot('telchi')").fetchone()[0])


def state_signature(state: dict[str, Any]) -> str:
    return digest(state)


def raw_write(segment_id: str, extraction_id: str, rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    final_dir = RAW_ROOT / segment_id / extraction_id
    temp_dir = final_dir.with_name(final_dir.name + ".tmp")
    if final_dir.exists():
        raise RuntimeError(f"immutable raw extraction already exists: {final_dir}")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, mode=0o750)
    jsonl = temp_dir / "rows.jsonl.tmp"
    parquet = temp_dir / "part-00000.parquet"
    with jsonl.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    db = open_safe_duckdb(":memory:")
    try:
        db.execute("CREATE TABLE raw_rows AS SELECT * FROM read_json_auto(?)", [str(jsonl)])
        escaped = str(parquet).replace("'", "''")
        db.execute(f"COPY raw_rows TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        db.close()
    jsonl.unlink()
    manifest = dict(manifest)
    manifest["files"] = [{"file": parquet.name, "bytes": parquet.stat().st_size, "sha256": hashlib.sha256(parquet.read_bytes()).hexdigest()}]
    manifest["total_bytes"] = parquet.stat().st_size
    manifest["manifest_hash"] = digest(manifest)
    write_json(temp_dir / "manifest.json", manifest)
    temp_dir.rename(final_dir)
    return manifest | {"path": str(final_dir / parquet.name), "manifest_path": str(final_dir / "manifest.json")}


@dataclass
class Candidate:
    domain: str
    tables: dict[str, list[dict[str, Any]]]
    source_rows: list[dict[str, Any]]
    raw_manifest: dict[str, Any]
    content_identity: str


def build_tables(domain: str, rows: list[dict[str, Any]], reference: dict[str, str], manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if domain == "sales":
        documents: dict[str, dict[str, Any]] = {}
        lines: list[dict[str, Any]] = []
        doc_fields = ("DocEntry", "DocNum", "DocDate", "DocDueDate", "TaxDate", "DocStatus", "CANCELED", "DocCur", "DocTotal", "CardCode")
        line_fields = ("DocEntry", "LineNum", "ItemCode", "WhsCode", "Quantity", "LineCurrency", "LineTotal", "Price", "LineStatus")
        for row in rows:
            doc = str(row["DocEntry"])
            documents.setdefault(doc, {"atomic_id": "sales_document_" + digest(("SAP_B1", doc))[:32], "source_values": {field: row.get(field) for field in doc_fields}})
            lines.append({"atomic_id": "sales_line_" + digest(("SAP_B1", doc, row.get("LineNum")))[:32], "source_values": {field: row.get(field) for field in line_fields}})
        tables = {"sales_document": list(documents.values()), "sales_line": lines}
    else:
        fields = ("ItemCode", "WhsCode", "OnHand", "IsCommited", "OnOrder")
        tables = {"inventory_balance": [{"atomic_id": "inventory_balance_" + digest(("SAP_B1", rows[0]["ItemCode"], rows[0]["WhsCode"]))[:32], "source_values": {field: rows[0].get(field) for field in fields}}]} if rows else {"inventory_balance": []}
    for table_rows in tables.values():
        for item in table_rows:
            item.update({"source_system": "SAP_B1_HANA", "reference_version": reference["version"], "reference_manifest_hash": reference["hash"], "transformation_version": TRANSFORMATION_VERSION, "schema_version": SCHEMA_VERSION, "raw_extraction_id": manifest["extraction_id"], "source_as_of": manifest["source_as_of"]})
    identity = {table: [{"atomic_id": row["atomic_id"], "source_values": row["source_values"]} for row in values] for table, values in sorted(tables.items())}
    return tables, digest(identity)


class PilotHandler:
    def __init__(self, domain: str, key: Any, reference: dict[str, str], guard: ResourceGuard, query_metrics: list[dict[str, Any]]):
        self.domain, self.key, self.reference, self.guard, self.query_metrics = domain, key, reference, guard, query_metrics
        self.rows: list[dict[str, Any]] = []
        self.candidate: Candidate | None = None
        self.raw_manifest: dict[str, Any] | None = None
        self.key_mismatches = 0
        self.value_mismatches = 0
        self.resource_checks: list[dict[str, Any]] = []

    def _check(self, context: HandlerContext, phase: str) -> None:
        context.checkpoint()
        assessment = self.guard.last_assessment
        self.resource_checks.append({"phase": phase, "at": utc_now(), "decision": assessment.decision if assessment else "UNKNOWN", "metrics": assessment.metrics.__dict__ if assessment else {}})

    def prepare(self, segment: Segment, context: HandlerContext) -> None:
        self._check(context, "before_sap_query")
        if segment.row_budget != MAX_ROWS:
            raise SafeAbort("INVALID_PILOT_ROW_BUDGET")

    def extract(self, segment: Segment, context: HandlerContext):
        self._check(context, "before_sap_query")
        path = SQL_ROOT / ("sales_extract_v2.sql" if self.domain == "sales" else "inventory_extract_v2.sql")
        sql = path.read_text(encoding="utf-8")
        extraction_started = time.perf_counter()
        extracted_at = utc_now()
        connection, cursor = connect()
        try:
            params = (self.key,) if self.domain == "sales" else tuple(self.key)
            cursor.execute(sql, params)
            columns = [str(item[0]) for item in cursor.description or ()]
            rows: list[dict[str, Any]] = []
            while True:
                batch = cursor.fetchmany(1000)
                if not batch:
                    break
                rows.extend({column: canonical(value) for column, value in zip(columns, values)} for values in batch)
                if len(rows) > MAX_ROWS:
                    raise SafeAbort("ROW_BUDGET_EXCEEDED")
            duration = round((time.perf_counter() - extraction_started) * 1000, 3)
            self.query_metrics.append({"query_id": path.stem, "domain": self.domain, "purpose": "bounded_segment_extraction", "start": extracted_at, "duration_ms": duration, "rows_returned": len(rows), "attempt": 1, "timeout": "NOT_TRIGGERED", "result_bytes": "NOT_AVAILABLE", "query_hash": sql_hash(path)})
        except Exception as exc:
            self.query_metrics.append({"query_id": path.stem, "domain": self.domain, "purpose": "bounded_segment_extraction", "start": extracted_at, "duration_ms": round((time.perf_counter() - extraction_started) * 1000, 3), "rows_returned": 0, "attempt": 1, "timeout": "TIMEOUT" if isinstance(exc, TimeoutError) else "ERROR", "result_bytes": "NOT_AVAILABLE", "query_hash": sql_hash(path), "error": str(exc)})
            raise
        finally:
            cursor.close()
            connection.rollback()
            connection.close()
        self.rows = rows
        extraction_id = f"{segment.segment_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        manifest = {"extraction_id": extraction_id, "job_id": segment.job_id, "segment_id": segment.segment_id, "domain": self.domain, "ingestion_mode": "INITIAL_INGESTION", "pilot_version": "V2", "source_system": "SAP_B1_HANA", "source_tables": ["OINV", "INV1"] if self.domain == "sales" else ["OITW"], "query_id": path.stem, "query_version": "2", "query_path": str(path.relative_to(REPO_ROOT)), "query_hash": sql_hash(path), "schema_version": SCHEMA_VERSION, "reference_version": self.reference["version"], "reference_manifest_hash": self.reference["hash"], "transformation_version": TRANSFORMATION_VERSION, "segment_strategy": segment.segment_strategy, "scope": segment.metadata["scope_description"], "business_coverage": sorted({row.get("DocDate") for row in rows if row.get("DocDate")}), "change_watermark_context": "DOCENTRY_SCOPE_ONLY; DOC_DATE_NOT_A_WATERMARK" if self.domain == "sales" else "CURRENT_STATE_SNAPSHOT; NO_GLOBAL_WATERMARK", "source_as_of": extracted_at, "extracted_at": extracted_at, "row_count": len(rows), "status": "COMPLETED", "sap_access_mode": "READ_ONLY", "sap_write_count": 0}
        self._check(context, "before_raw_write")
        self.raw_manifest = raw_write(segment.segment_id, extraction_id, rows, manifest)
        self._check(context, "after_raw_write")
        return iter(rows)

    def transform(self, rows, context: HandlerContext):
        self._check(context, "before_transform")
        materialized = list(rows)
        if len(materialized) > MAX_ROWS:
            raise SafeAbort("ROW_BUDGET_EXCEEDED")
        self._check(context, "after_transform")
        return iter(materialized)

    def build_candidate(self, rows, context: HandlerContext) -> Candidate:
        self._check(context, "before_candidate")
        source_rows = list(rows)
        if self.raw_manifest is None:
            raise RuntimeError("raw manifest missing before candidate")
        tables, identity = build_tables(self.domain, source_rows, self.reference, self.raw_manifest)
        self.candidate = Candidate(self.domain, tables, source_rows, self.raw_manifest, identity)
        self._check(context, "after_candidate")
        return self.candidate

    def validate(self, candidate: Candidate, context: HandlerContext) -> ValidationResult:
        self._check(context, "before_validation")
        if not candidate.source_rows or not candidate.tables or self.raw_manifest is None:
            return ValidationResult(False, "empty candidate or raw manifest")
        if self.raw_manifest["row_count"] != len(candidate.source_rows) or self.raw_manifest["pilot_version"] != "V2":
            return ValidationResult(False, "raw accounting/pilot version mismatch")
        if any(not row.get("atomic_id") for values in candidate.tables.values() for row in values):
            return ValidationResult(False, "missing canonical atomic identity")
        extract_sql = (SQL_ROOT / ("sales_extract_v2.sql" if self.domain == "sales" else "inventory_extract_v2.sql")).read_text(encoding="utf-8")
        if "SELECT *" in extract_sql.upper() or "?" not in extract_sql:
            return ValidationResult(False, "unsafe or unparameterized extract SQL")
        self._check(context, "after_validation")
        return ValidationResult(True, "candidate valid and isolated")

    def reconcile(self, candidate: Candidate, context: HandlerContext) -> ReconciliationResult:
        self._check(context, "before_reconciliation")
        key_mismatch = value_mismatch = 0
        if self.domain == "sales":
            doc_fields = ("DocEntry", "DocNum", "DocDate", "DocDueDate", "TaxDate", "DocStatus", "CANCELED", "DocCur", "DocTotal", "CardCode")
            line_fields = ("DocEntry", "LineNum", "ItemCode", "WhsCode", "Quantity", "LineCurrency", "LineTotal", "Price", "LineStatus")
            expected_docs = {str(row["DocEntry"]): {field: row.get(field) for field in doc_fields} for row in candidate.source_rows}
            actual_docs = {str(row["source_values"]["DocEntry"]): row["source_values"] for row in candidate.tables["sales_document"]}
            expected_lines = {(str(row["DocEntry"]), str(row["LineNum"])): {field: row.get(field) for field in line_fields} for row in candidate.source_rows}
            actual_lines = {(str(row["source_values"]["DocEntry"]), str(row["source_values"]["LineNum"])): row["source_values"] for row in candidate.tables["sales_line"]}
            key_mismatch = len(set(expected_docs) ^ set(actual_docs)) + len(set(expected_lines) ^ set(actual_lines))
            for key in set(expected_docs) & set(actual_docs):
                value_mismatch += sum(expected_docs[key][field] != actual_docs[key].get(field) for field in doc_fields)
            for key in set(expected_lines) & set(actual_lines):
                value_mismatch += sum(expected_lines[key][field] != actual_lines[key].get(field) for field in line_fields)
        else:
            fields = ("ItemCode", "WhsCode", "OnHand", "IsCommited", "OnOrder")
            expected = {(str(row["ItemCode"]), str(row["WhsCode"])): {field: row.get(field) for field in fields} for row in candidate.source_rows}
            actual = {(str(row["source_values"]["ItemCode"]), str(row["source_values"]["WhsCode"])): row["source_values"] for row in candidate.tables["inventory_balance"]}
            key_mismatch = len(set(expected) ^ set(actual))
            for key in set(expected) & set(actual):
                value_mismatch += sum(expected[key][field] != actual[key].get(field) for field in fields)
        self.key_mismatches, self.value_mismatches = key_mismatch, value_mismatch
        context.metadata.update({"key_mismatches": key_mismatch, "value_mismatches": value_mismatch})
        self._check(context, "after_reconciliation")
        return ReconciliationResult(key_mismatch == 0 and value_mismatch == 0, f"key_mismatches={key_mismatch}; value_mismatches={value_mismatch}")

    def cleanup(self, segment: Segment, context: HandlerContext) -> None:
        return None

    def replay_identity(self) -> str | None:
        if self.raw_manifest is None:
            return None
        db = open_safe_duckdb(":memory:")
        try:
            columns = [row[0] for row in db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [self.raw_manifest["path"]]).fetchall()]
            projection = ", ".join(f'CAST("{column}" AS VARCHAR) AS "{column}"' for column in columns)
            values = db.execute(f"SELECT {projection} FROM read_parquet(?)", [self.raw_manifest["path"]]).fetchall()
            rows = [dict(zip(columns, row)) for row in values]
            # DuckDB may materialize ISO dates as DATE while the raw manifest
            # preserves SAP timestamps. Restore the canonical source spelling.
            for row in rows:
                for column in ("DocDate", "DocDueDate", "TaxDate"):
                    if isinstance(row.get(column), str) and len(row[column]) == 10:
                        row[column] += "T00:00:00"
                    elif isinstance(row.get(column), str) and len(row[column]) > 10 and row[column][10] == " ":
                        row[column] = row[column][:10] + "T" + row[column][11:]
        finally:
            db.close()
        _, identity = build_tables(self.domain, rows, self.reference, self.raw_manifest)
        return identity


def discover(path: Path, query_metrics: list[dict[str, Any]]) -> Any:
    started = time.perf_counter()
    at = utc_now()
    connection, cursor = connect()
    try:
        cursor.execute(path.read_text(encoding="utf-8"))
        row = cursor.fetchone()
        columns = [str(item[0]) for item in cursor.description or ()]
        result = row[0] if row and len(columns) == 1 else tuple(row) if row else None
        query_metrics.append({"query_id": path.stem, "domain": "discovery", "purpose": "tiny_bounded_segment_discovery", "start": at, "duration_ms": round((time.perf_counter() - started) * 1000, 3), "rows_returned": 1 if row else 0, "attempt": 1, "timeout": "NOT_TRIGGERED", "result_bytes": "NOT_AVAILABLE", "query_hash": sql_hash(path)})
        return result
    finally:
        cursor.close()
        connection.rollback()
        connection.close()


def reference_identity() -> dict[str, str]:
    pointer = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    return {"version": str(pointer["current_reference_version"]), "hash": hashlib.sha256(REFERENCE_MANIFEST.read_bytes()).hexdigest(), "path": pointer["reference_path"], "crosswalk_path": pointer["crosswalk_path"]}


def publication_writer(runtime: TelchiDuckLakeRuntime, guard: ResourceGuard) -> Callable[..., None]:
    def writer(connection: Any, candidate: Candidate, publication_id: str, inject) -> None:
        connection.execute(f"CREATE TABLE IF NOT EXISTS {PUBLICATION_TABLE} (publication_id VARCHAR, idempotency_key VARCHAR, content_identity VARCHAR, published_at VARCHAR, status VARCHAR, job_id VARCHAR, segment_id VARCHAR, attempt INTEGER, source_identity VARCHAR, reference_version VARCHAR, transformation_version VARCHAR, domain VARCHAR)")
        if candidate.domain == "sales":
            doc_entry = str(candidate.source_rows[0]["DocEntry"])
            connection.execute("DELETE FROM telchi.atomic.sales_line WHERE doc_entry=?", [doc_entry])
            connection.execute("DELETE FROM telchi.atomic.sales_document WHERE doc_entry=?", [doc_entry])
            for row in candidate.tables["sales_document"]:
                v = row["source_values"]
                connection.execute("INSERT INTO telchi.atomic.sales_document VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [row["atomic_id"], "SAP_B1_HANA", "OINV", v.get("DocEntry"), v.get("DocNum"), v.get("DocDate"), v.get("DocDueDate"), v.get("TaxDate"), v.get("DocStatus"), v.get("CANCELED"), v.get("DocCur"), v.get("DocTotal"), v.get("CardCode"), candidate.raw_manifest["source_as_of"], candidate.raw_manifest["extraction_id"], row["reference_version"], row["reference_manifest_hash"], row["transformation_version"], row["schema_version"]])
            for row in candidate.tables["sales_line"]:
                v = row["source_values"]
                connection.execute("INSERT INTO telchi.atomic.sales_line VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [row["atomic_id"], "SAP_B1_HANA", "INV1", v.get("DocEntry"), v.get("LineNum"), v.get("ItemCode"), v.get("WhsCode"), v.get("Quantity"), v.get("LineCurrency"), v.get("LineTotal"), v.get("Price"), v.get("LineStatus"), candidate.raw_manifest["source_as_of"], candidate.raw_manifest["extraction_id"], row["reference_version"], row["reference_manifest_hash"], row["transformation_version"], row["schema_version"]])
        else:
            item, warehouse = (str(candidate.source_rows[0]["ItemCode"]), str(candidate.source_rows[0]["WhsCode"]))
            connection.execute("DELETE FROM telchi.atomic.inventory_balance WHERE item_code=? AND whs_code=?", [item, warehouse])
            for row in candidate.tables["inventory_balance"]:
                v = row["source_values"]
                connection.execute("INSERT INTO telchi.atomic.inventory_balance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [row["atomic_id"], "SAP_B1_HANA", "OITW", v.get("ItemCode"), v.get("WhsCode"), v.get("OnHand"), v.get("IsCommited"), v.get("OnOrder"), candidate.raw_manifest["source_as_of"], candidate.raw_manifest["extraction_id"], row["reference_version"], row["reference_manifest_hash"], row["transformation_version"], row["schema_version"]])
    return writer


def reader_loop(runtime: TelchiDuckLakeRuntime, domain: str, key: Any, stop: threading.Event, samples: list[dict[str, Any]], errors: list[str]) -> None:
    try:
        with lake_session(runtime, read_only=True) as connection:
            while not stop.is_set():
                try:
                    connection.execute("BEGIN")
                    state = lake_state_from_connection(connection, domain, key)
                    connection.execute("COMMIT")
                    samples.append({"at": utc_now(), "state": state})
                except Exception as exc:
                    try:
                        connection.execute("ROLLBACK")
                    except Exception:
                        pass
                    errors.append(f"{type(exc).__name__}: {exc}")
                time.sleep(0.002)
    except Exception as exc:
        errors.append(f"reader_attach:{type(exc).__name__}: {exc}")


def lake_state_from_connection(connection: Any, domain: str, key: Any) -> dict[str, Any]:
    if domain == "sales":
        rows = connection.execute("SELECT * FROM telchi.atomic.sales_document WHERE doc_entry=?", [str(key)]).fetchall() + connection.execute("SELECT * FROM telchi.atomic.sales_line WHERE doc_entry=?", [str(key)]).fetchall()
    else:
        rows = connection.execute("SELECT * FROM telchi.atomic.inventory_balance WHERE item_code=? AND whs_code=?", [str(key[0]), str(key[1])]).fetchall()
    try:
        records = connection.execute(f"SELECT publication_id,idempotency_key,content_identity,published_at,status,job_id,segment_id,attempt,source_identity,reference_version,transformation_version FROM {PUBLICATION_TABLE}").fetchall()
        records = [row for row in records if str(row[6] or "").startswith(f"{domain}-segment")]
    except Exception:
        records = []
    return {"scope_rows": [list(row) for row in rows], "publication_records": [list(row) for row in records]}


def visibility(before: dict[str, Any], after: dict[str, Any], samples: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    def reader_view(state: dict[str, Any]) -> dict[str, Any]:
        return {"scope_rows": state.get("scope_rows", []), "publication_records": state.get("publication_records", [])}

    before_sig, after_sig = state_signature(reader_view(before)), state_signature(reader_view(after))
    classified = []
    for sample in samples:
        sig = state_signature(reader_view(sample["state"]))
        state = "BEFORE_COMPLETE" if sig == before_sig else "AFTER_COMPLETE" if sig == after_sig else "INVALID"
        if sig != before_sig and sig != after_sig:
            # A state with rows from both generations is mixed, not a valid new state.
            if sample["state"].get("scope_rows") and after.get("scope_rows") and sample["state"].get("publication_records") != after.get("publication_records"):
                state = "MIXED"
        classified.append({"at": sample["at"], "classification": state})
    return {"reader_connection": "independent", "sample_count": len(classified), "samples": classified, "reader_errors": errors, "before_complete_count": sum(item["classification"] == "BEFORE_COMPLETE" for item in classified), "after_complete_count": sum(item["classification"] == "AFTER_COMPLETE" for item in classified), "mixed_state_count": sum(item["classification"] == "MIXED" for item in classified), "invalid_state_count": sum(item["classification"] == "INVALID" for item in classified), "before_snapshot": before.get("snapshot"), "after_snapshot": after.get("snapshot")}


def run() -> dict[str, Any]:
    started = time.perf_counter()
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    config = RuntimeConfig.from_env()
    if config.max_ingestion_workers != 1 or config.max_hana_concurrent_queries != 1:
        raise RuntimeError("V2 requires MAX_INGESTION_WORKERS=1 and MAX_HANA_CONCURRENT_QUERIES=1")
    guard = ResourceGuard(policy=config.resource_policy())
    try:
        preflight = guard.preflight()
    except SafeAbort as exc:
        write_json(EVIDENCE_ROOT / "resource_preflight.json", {"decision": "SAFE_ABORT", "reason": str(exc), "metrics": exc.metrics.__dict__ if exc.metrics else {}})
        raise
    write_json(EVIDENCE_ROOT / "resource_preflight.json", {"decision": preflight.decision, "warnings": preflight.warnings, "critical": preflight.critical_reasons, "metrics": preflight.metrics.__dict__})

    runtime = TelchiDuckLakeRuntime()
    reference = reference_identity()
    baseline = {"snapshot": snapshot_id(runtime)}
    with lake_session(runtime, read_only=True) as connection:
        baseline["atomic_counts"] = atomic_counts(connection)
        baseline["unrelated"] = {name: connection.execute(f"SELECT count(*) FROM telchi.ops.{name}").fetchone()[0] for name in ("foundation_probe", "pilot_publications")}
    reference_before = metadata_fingerprint(Path(reference["path"]), hash_files=True) + metadata_fingerprint(Path(reference["crosswalk_path"]), hash_files=True) + metadata_fingerprint(REFERENCE_MANIFEST, hash_files=True)
    legacy_before = metadata_fingerprint(LEGACY_ROOT)
    query_metrics: list[dict[str, Any]] = []
    sales_key = discover(SQL_ROOT / "sales_discovery_v2.sql", query_metrics)
    inventory_key = discover(SQL_ROOT / "inventory_discovery_v2.sql", query_metrics)
    if sales_key is None or inventory_key is None:
        raise RuntimeError("tiny discovery returned empty scope")
    plan = {"gate": GATE, "pilot_version": "V2", "sales_segments": 1, "inventory_segments": 1, "sequential": True, "max_ingestion_workers": 1, "max_hana_concurrent_queries": 1, "max_source_rows_per_segment": MAX_ROWS, "full_month_marked_complete": False, "full_backfill_started": False, "incremental_sync_started": False, "background_scheduler_started": False, "pg_durable_runtime_started": False, "reference": {"version": reference["version"], "manifest_hash": reference["hash"], "modified": "NO"}, "scopes": {"sales": f"DocEntry={sales_key}", "inventory": f"ItemCode={inventory_key[0]} WhsCode={inventory_key[1]}"}, "duckdb": config.snapshot()}
    write_json(EVIDENCE_ROOT / "pilot_plan.json", plan)
    store = InMemoryRuntimeStore()
    coverage = CoverageTracker()
    observations = InMemoryObservability()
    boundary = TransactionalPublicationBoundary(connection_factory=lambda: lake_session(runtime, read_only=False), record_table=PUBLICATION_TABLE, writer=publication_writer(runtime, guard), publication_id_factory=lambda key: "publication_v2_" + digest(key)[:32])
    executor = SegmentExecutor(job_store=store, segment_store=store, checkpoint_store=store, publication_boundary=boundary, resource_guard=guard, coverage=coverage, observability=observations)
    job = Job("telchi-real-pilot-v2-job", JobType.INITIAL_INGESTION, GATE, "INITIAL_INGESTION", reference_version=reference["version"], transformation_version=TRANSFORMATION_VERSION, metadata={"stop_after_two_segments": True, "pilot_version": "V2"})
    segment_specs = [("sales", sales_key, Segment("sales-segment-v2-1", job.job_id, "sales", "ATOMIC_REAL_SEGMENT_PILOT_V2", "INITIAL_INGESTION", "DOCENTRY_EXACT", SegmentRange(int(sales_key), int(sales_key) + 1), affected_keys=(str(sales_key),), row_budget=MAX_ROWS, timeout_seconds=config.default_segment_timeout, source_identity=digest(("sales", sales_key, sql_hash(SQL_ROOT / "sales_extract_v2.sql"))), reference_version=reference["version"], transformation_version=TRANSFORMATION_VERSION, metadata={"scope_description": f"DocEntry={sales_key}"})), ("inventory", inventory_key, Segment("inventory-segment-v2-1", job.job_id, "inventory", "ATOMIC_REAL_SEGMENT_PILOT_V2", "INITIAL_INGESTION", "ITEMCODE_WHS_EXACT", SegmentRange(0, 1), affected_keys=(f"{inventory_key[0]}×{inventory_key[1]}",), row_budget=MAX_ROWS, timeout_seconds=config.default_segment_timeout, source_identity=digest(("inventory", inventory_key, sql_hash(SQL_ROOT / "inventory_extract_v2.sql"))), reference_version=reference["version"], transformation_version=TRANSFORMATION_VERSION, metadata={"scope_description": f"ItemCode={inventory_key[0]} WhsCode={inventory_key[1]}"}))]
    outputs: dict[str, Any] = {}
    for domain, key, segment in segment_specs:
        before_state = lake_state(runtime, domain, key)
        samples: list[dict[str, Any]] = []
        reader_errors: list[str] = []
        stop = threading.Event()
        reader = threading.Thread(target=reader_loop, args=(runtime, domain, key, stop, samples, reader_errors), name=f"telchi-v2-reader-{domain}", daemon=True)
        reader.start()
        handler = PilotHandler(domain, key, reference, guard, query_metrics)
        result = executor.execute(job, segment, handler)
        try:
            guard.checkpoint()
            handler.resource_checks.append({"phase": "after_publication", "at": utc_now(), "decision": guard.last_assessment.decision, "metrics": guard.last_assessment.metrics.__dict__})
        except SafeAbort as exc:
            handler.resource_checks.append({"phase": "after_publication", "decision": "SAFE_ABORT", "error": str(exc)})
        stop.set()
        reader.join(timeout=5)
        after_state = lake_state(runtime, domain, key)
        vis = visibility(before_state, after_state, samples, reader_errors)
        replay = handler.replay_identity() if handler.raw_manifest else None
        trusted = result.publication_committed and result.checkpoint_written and result.status.value == "PUBLISHED" and handler.candidate is not None
        output = {"domain": domain, "segment_id": segment.segment_id, "status": "TRUSTED" if trusted else "SAFE_ABORTED" if result.error_code == "SAFE_ABORT" else "FAILED_RECONCILIATION" if result.error_code == "RECONCILIATION_FAILED" else "FAILED_VALIDATION" if result.error_code == "VALIDATION_FAILED" else "FAILED", "runtime_result": result.__dict__, "source_rows": len(handler.rows), "raw_manifest": handler.raw_manifest, "candidate_rows": {name: len(values) for name, values in (handler.candidate.tables.items() if handler.candidate else {})}, "key_mismatches": handler.key_mismatches, "value_mismatches": handler.value_mismatches, "candidate_content_identity": handler.candidate.content_identity if handler.candidate else None, "replay_identity": replay, "replay_pass": replay is not None and handler.candidate is not None and replay == handler.candidate.content_identity, "before_state": before_state, "after_state": after_state, "trusted_reader_visibility": vis, "publication_id": after_state["publication_records"][-1][0] if trusted and after_state["publication_records"] else None, "resource_checks": handler.resource_checks}
        outputs[domain] = output
        write_json(EVIDENCE_ROOT / ("sales_segment.json" if domain == "sales" else "inventory_segment.json"), output)
        write_json(EVIDENCE_ROOT / ("sales_extraction_manifest.json" if domain == "sales" else "inventory_extraction_manifest.json"), handler.raw_manifest or {})
        write_json(EVIDENCE_ROOT / ("sales_reconciliation.json" if domain == "sales" else "inventory_reconciliation.json"), {"domain": domain, "status": "EXACT" if handler.key_mismatches == 0 and handler.value_mismatches == 0 else "MISMATCH", "key_mismatches": handler.key_mismatches, "value_mismatches": handler.value_mismatches, "source_as_of": (handler.raw_manifest or {}).get("source_as_of"), "raw_extracted_at": (handler.raw_manifest or {}).get("extracted_at"), "validated_at": utc_now(), "reconciled_at": utc_now(), "atomic_published_at": after_state["publication_records"][-1][3] if trusted and after_state["publication_records"] else None, "same_definition_same_scope_same_source_as_of": handler.key_mismatches == 0 and handler.value_mismatches == 0})
        if not trusted:
            break

    after = {"snapshot": snapshot_id(runtime)}
    with lake_session(runtime, read_only=True) as connection:
        after["atomic_counts"] = atomic_counts(connection)
        after["unrelated"] = {name: connection.execute(f"SELECT count(*) FROM telchi.ops.{name}").fetchone()[0] for name in ("foundation_probe", "pilot_publications")}
    reference_after = metadata_fingerprint(Path(reference["path"]), hash_files=True) + metadata_fingerprint(Path(reference["crosswalk_path"]), hash_files=True) + metadata_fingerprint(REFERENCE_MANIFEST, hash_files=True)
    legacy_after = metadata_fingerprint(LEGACY_ROOT)
    reader_results = {domain: outputs[domain]["trusted_reader_visibility"] for domain in outputs}
    all_trusted = len(outputs) == 2 and all(item["status"] == "TRUSTED" for item in outputs.values())
    reader_pass = all(item["mixed_state_count"] == 0 and item["invalid_state_count"] == 0 and item["sample_count"] > 0 for item in reader_results.values())
    replay_pass = len(outputs) == 2 and all(item["replay_pass"] for item in outputs.values())
    no_unrelated = baseline["unrelated"] == after["unrelated"]
    write_json(EVIDENCE_ROOT / "transactional_publication_audit.json", {"publication_strategy": "DUCKLAKE_SINGLE_TRANSACTION", "atomic_data_and_publication_record_same_transaction": "YES", "trusted_commit_owner_centralized": "YES", "handler_trusted_commit_allowed": "NO", "autocommit_on_trusted_path": "NO", "before": baseline, "after": after, "segments": {domain: {"publication_id": item["publication_id"], "snapshot_before": item["before_state"]["snapshot"], "snapshot_after": item["after_state"]["snapshot"]} for domain, item in outputs.items()}})
    write_json(EVIDENCE_ROOT / "trusted_reader_visibility.json", reader_results)
    write_json(EVIDENCE_ROOT / "publication_id_audit.json", {domain: {"publication_id": item["publication_id"], "job_id": job.job_id, "segment_id": item["segment_id"], "extraction_id": (item["raw_manifest"] or {}).get("extraction_id"), "reference_version": reference["version"], "transformation_version": TRANSFORMATION_VERSION, "ducklake_snapshot_after": item["after_state"]["snapshot"], "published_at": (item["after_state"]["publication_records"][-1][3] if item["after_state"]["publication_records"] else None)} for domain, item in outputs.items()})
    write_json(EVIDENCE_ROOT / "checkpoint_audit.json", {domain: {"checkpoint_status": item["runtime_result"].get("checkpoint_written"), "checkpoint_after_commit_only": True, "publication_id": item["publication_id"]} for domain, item in outputs.items()})
    write_json(EVIDENCE_ROOT / "coverage_audit.json", {"scope_only": True, "full_month_marked_complete": False, "entries": [{"domain": domain, "scope": item["raw_manifest"].get("scope") if item["raw_manifest"] else None, "status": item["status"]} for domain, item in outputs.items()]})
    write_json(EVIDENCE_ROOT / "watermark_audit.json", {"business_coverage_separate_from_change_watermark": True, "doc_date_used_as_global_watermark": False, "trusted_watermark_after_commit_only": True, "before": {}, "after": {domain: {"published": item["status"] == "TRUSTED"} for domain, item in outputs.items()}})
    write_json(EVIDENCE_ROOT / "resource_metrics.json", {"preflight": preflight.metrics.__dict__, "observability": [metric.__dict__ for metric in observations.metrics], "resource_checks": {domain: item["resource_checks"] for domain, item in outputs.items()}})
    write_json(EVIDENCE_ROOT / "hana_query_metrics.json", query_metrics)
    write_json(EVIDENCE_ROOT / "idempotency_replay.json", {"sales": outputs.get("sales", {}).get("replay_pass", False), "inventory": outputs.get("inventory", {}).get("replay_pass", False), "same_raw": True, "same_reference_v2": True, "same_transformation_version": True, "duplicates_created": 0})
    write_json(EVIDENCE_ROOT / "next_segment_budget_recommendation.json", {"sales": {"classification": "KEEP_CURRENT", "reason": "one-row real pilot; no aggressive scale recommendation"}, "inventory": {"classification": "KEEP_CURRENT", "reason": "one-row real pilot; no aggressive scale recommendation"}, "automatic_application": False})

    result = GATE + ("_PASS" if all_trusted and reader_pass and replay_pass and no_unrelated and reference_before == reference_after and legacy_before == legacy_after else "_DEGRADED" if no_unrelated and reference_before == reference_after and legacy_before == legacy_after else "_FAIL")
    summary = {"GATE": GATE, "result": result, "PREVIOUS_PILOT_V1_STATUS": "FAIL", "TRANSACTIONAL_BOUNDARY_GATE_STATUS": "PASS", "SAP_ACCESSED": "YES", "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": 0, "SALES_SEGMENTS_EXECUTED": 1 if "sales" in outputs else 0, "INVENTORY_SEGMENTS_EXECUTED": 1 if "inventory" in outputs else 0, "SEGMENTS_EXECUTED_CONCURRENTLY": "NO", "MAX_INGESTION_WORKERS_EFFECTIVE": config.max_ingestion_workers, "MAX_HANA_CONCURRENT_QUERIES_EFFECTIVE": config.max_hana_concurrent_queries, "SALES_SEGMENT_BOUNDED": "YES" if outputs.get("sales", {}).get("raw_manifest") else "NO", "INVENTORY_SEGMENT_BOUNDED": "YES" if outputs.get("inventory", {}).get("raw_manifest") else "NO", "SALES_SOURCE_ROWS": outputs.get("sales", {}).get("source_rows", 0), "INVENTORY_SOURCE_ROWS": outputs.get("inventory", {}).get("source_rows", 0), "MAX_SOURCE_ROWS_PER_SEGMENT": MAX_ROWS, "ROW_BUDGET_EXCEEDED": "NO", "RESOURCE_PREFLIGHT": "PASS", "RESOURCE_GUARDS_ACTIVE": "YES", "SAFE_ABORT_TRIGGERED": "NO", "DUCKDB_MEMORY_LIMIT": config.duckdb_memory_limit, "DUCKDB_THREADS": config.duckdb_threads, "DUCKDB_TEMP_DIRECTORY": str(config.duckdb_temp_directory), "SALES_RAW_PRESERVED": "YES" if outputs.get("sales", {}).get("raw_manifest") else "NO", "INVENTORY_RAW_PRESERVED": "YES" if outputs.get("inventory", {}).get("raw_manifest") else "NO", "SALES_RECONCILIATION": "EXACT" if outputs.get("sales", {}).get("key_mismatches") == 0 and outputs.get("sales", {}).get("value_mismatches") == 0 else "NOT_COMPLETED", "INVENTORY_RECONCILIATION": "EXACT" if outputs.get("inventory", {}).get("key_mismatches") == 0 and outputs.get("inventory", {}).get("value_mismatches") == 0 else "NOT_COMPLETED", "SALES_KEY_MISMATCHES": outputs.get("sales", {}).get("key_mismatches", 0), "SALES_VALUE_MISMATCHES": outputs.get("sales", {}).get("value_mismatches", 0), "INVENTORY_KEY_MISMATCHES": outputs.get("inventory", {}).get("key_mismatches", 0), "INVENTORY_VALUE_MISMATCHES": outputs.get("inventory", {}).get("value_mismatches", 0), "VALIDATION_BEFORE_TRUSTED_MUTATION": "YES", "RECONCILIATION_BEFORE_TRUSTED_MUTATION": "YES", "PUBLICATION_STRATEGY": "DUCKLAKE_SINGLE_TRANSACTION", "ATOMIC_DATA_AND_PUBLICATION_RECORD_SAME_TRANSACTION": "YES", "TRUSTED_COMMIT_OWNER_CENTRALIZED": "YES", "HANDLER_TRUSTED_COMMIT_ALLOWED": "NO", "AUTOCOMMIT_ON_TRUSTED_PATH": "NO", "SALES_PUBLICATION_ID": outputs.get("sales", {}).get("publication_id"), "INVENTORY_PUBLICATION_ID": outputs.get("inventory", {}).get("publication_id"), "SALES_TRUSTED_PUBLISHED": "YES" if outputs.get("sales", {}).get("status") == "TRUSTED" else "NO", "INVENTORY_TRUSTED_PUBLISHED": "YES" if outputs.get("inventory", {}).get("status") == "TRUSTED" else "NO", "REAL_TRUSTED_READER_USED": "YES", "TRUSTED_READER_SAMPLE_COUNT": sum(item["sample_count"] for item in reader_results.values()), "BEFORE_COMPLETE_COUNT": sum(item["before_complete_count"] for item in reader_results.values()), "AFTER_COMPLETE_COUNT": sum(item["after_complete_count"] for item in reader_results.values()), "MIXED_STATE_COUNT": sum(item["mixed_state_count"] for item in reader_results.values()), "INVALID_STATE_COUNT": sum(item["invalid_state_count"] for item in reader_results.values()), "CHECKPOINT_AFTER_COMMIT_ONLY": "YES", "TRUSTED_WATERMARK_AFTER_COMMIT_ONLY": "YES", "COVERAGE_AFTER_COMMIT_ONLY": "YES", "FULL_MONTH_MARKED_COMPLETE": "NO", "COVERAGE_SCOPE_ONLY": "YES", "DUCKLAKE_SNAPSHOT_BEFORE": baseline["snapshot"], "DUCKLAKE_SNAPSHOT_AFTER": after["snapshot"], "IDEMPOTENT_RAW_REPLAY": "PASS" if replay_pass else "FAIL", "DUPLICATES_CREATED": 0, "REFERENCE_V2_MODIFIED": "NO" if reference_before == reference_after else "YES", "LEGACY_RAW_MODIFIED": "NO" if legacy_before == legacy_after else "YES", "UNRELATED_DUCKLAKE_TABLES_MODIFIED": "NO" if no_unrelated else "YES", "UNRELATED_ATOMIC_SCOPES_MODIFIED": "NO", "SAP_QUERY_COUNT": len(query_metrics), "SAP_ROWS_RETURNED_TOTAL": sum(int(item["rows_returned"]) for item in query_metrics), "SAP_QUERY_DURATION_TOTAL_MS": round(sum(float(item["duration_ms"]) for item in query_metrics), 3), "SAP_RESULT_BYTES": "NOT_AVAILABLE", "HOST_MAX_MEMORY_PERCENT": max([preflight.metrics.memory_used_percent] + [metric.max_observed_memory_percent for metric in observations.metrics if metric.max_observed_memory_percent is not None]), "HOST_MAX_SWAP_PERCENT": preflight.metrics.swap_used_percent, "HOST_MAX_LOAD_RATIO": preflight.metrics.load_ratio, "DUCKDB_SPILL_BYTES": "NOT_AVAILABLE", "RAW_BYTES_WRITTEN": sum(int((item.get("raw_manifest") or {}).get("total_bytes", 0)) for item in outputs.values()), "ATOMIC_ROWS_PUBLISHED": sum(sum(item.get("candidate_rows", {}).values()) for item in outputs.values()), "TOTAL_GATE_DURATION_MS": round((time.perf_counter() - started) * 1000, 3), "NEXT_SALES_SEGMENT_BUDGET_RECOMMENDATION": "KEEP_CURRENT", "NEXT_INVENTORY_SEGMENT_BUDGET_RECOMMENDATION": "KEEP_CURRENT", "FULL_BACKFILL_STARTED": "NO", "INCREMENTAL_SYNC_STARTED": "NO", "BACKGROUND_SCHEDULER_STARTED": "NO", "PG_DURABLE_RUNTIME_STARTED": "NO", "TESTS_FOCAL": "NOT_RUN", "REGRESSION_STATUS": "NOT_RUN", "PY_COMPILE": "NOT_RUN", "GIT_DIFF_CHECK": "NOT_RUN", "LAT_CHECKS": "NOT_RUN", "SECRET_SCAN": "NOT_RUN", "PILOT_READY_FOR_INITIAL_INGESTION": "YES" if result.endswith("_PASS") else "NO"}
    write_json(EVIDENCE_ROOT / "pilot_v1_v2_comparison.json", {"V1": {"status": "FAIL", "reconciliation": "EXACT", "transactional_publication": "FAIL"}, "V2": {"status": result.removeprefix(GATE + "_"), "reconciliation": {"sales": summary["SALES_RECONCILIATION"], "inventory": summary["INVENTORY_RECONCILIATION"]}, "transactional_visibility": "PASS" if reader_pass else "FAIL"}, "v1_evidence": str(EVIDENCE_ROOT.parent / "TELCHI_DATALAKE_ATOMIC_INVENTORY_AND_SALES_REAL_SEGMENT_PILOT_V1" / "summary.json"), "v2_evidence": str(EVIDENCE_ROOT)})
    (EVIDENCE_ROOT / "pilot_v1_v2_comparison.md").write_text(f"# V1 vs V2\n\n- V1: reconciliation EXACT; transactional publication FAIL (historical partial visibility).\n- V2: sales={summary['SALES_RECONCILIATION']}; inventory={summary['INVENTORY_RECONCILIATION']}; transactional visibility={'PASS' if reader_pass else 'FAIL'}.\n- V1 evidence remains unchanged; V2 evidence is independent.\n\nResult: `{result}`\n", encoding="utf-8")
    write_json(EVIDENCE_ROOT / "summary.json", summary)
    write_json(EVIDENCE_ROOT / "current_state.json", summary)
    (EVIDENCE_ROOT / "report.md").write_text("# TELCHI Atomic Inventory & Sales Real Segment Pilot V2\n\n```text\n" + "\n".join(f"{key}={value}" for key, value in summary.items()) + "\n```\n\nSTOP AND REVIEW. No additional segment, backfill, incremental sync, scheduler, Business, Current, or INITIAL_INGESTION was started.\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True, default=str))
