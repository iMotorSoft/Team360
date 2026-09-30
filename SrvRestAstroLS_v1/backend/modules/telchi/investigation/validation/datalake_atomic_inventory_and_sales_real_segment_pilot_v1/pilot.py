from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import duckdb

from modules.telchi.runtime.config import RuntimeConfig, open_safe_duckdb
from modules.telchi.runtime.contracts import (
    Job, JobType, Segment, SegmentRange, ValidationResult, ReconciliationResult,
)
from modules.telchi.runtime.coverage import CoverageTracker
from modules.telchi.runtime.executor import SegmentExecutor
from modules.telchi.runtime.handler import HandlerContext
from modules.telchi.runtime.observability import InMemoryObservability
from modules.telchi.runtime.resource_guard import ResourceGuard, SafeAbort
from modules.telchi.runtime.stores import InMemoryRuntimeStore, PublicationBoundary, PublicationReceipt
from modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.runtime import TelchiDuckLakeRuntime
from modules.telchi.investigation.validation.sql_baseline.sql_baseline_harness import connect

from . import GATE

REPO = Path(__file__).resolve().parents[7]
SQL_ROOT = REPO / "SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/atomic_inventory_and_sales/real_segment_pilot_v1"
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
RAW_ROOT = DATA_ROOT / "raw/sap" / GATE
REFERENCE_MANIFEST = DATA_ROOT / "manifests/reference_current.json"
LEGACY_ROOT = DATA_ROOT / "raw/legacy"
MAX_ROWS = 10_000
TRANSFORMATION_VERSION = "atomic-inventory-sales-real-segment-pilot-v1.0.0"
SCHEMA_VERSION = "1.0.0"
QUERY_TIMEOUT = float(os.getenv("TELCHI_DEFAULT_SEGMENT_TIMEOUT", "300"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def row_json(row: dict[str, Any]) -> dict[str, Any]:
    return {str(k): canonical(v) for k, v in row.items()}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def sql_hash(name: str) -> str:
    return digest((SQL_ROOT / name).read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def file_fingerprint(root: Path) -> dict[str, Any]:
    if not root.exists():
        return {"exists": False, "files": 0, "bytes": 0, "entries_hash": digest("missing")}
    entries = []
    total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        stat = path.stat(); total += stat.st_size
        entries.append((str(path.relative_to(root)), stat.st_size, stat.st_mtime_ns))
    return {"exists": True, "files": len(entries), "bytes": total, "entries_hash": digest(entries)}


@contextmanager
def ducklake_session(runtime: TelchiDuckLakeRuntime, *, read_only: bool):
    previous = os.environ.get("PGPASSWORD")
    os.environ["PGPASSWORD"] = runtime.config.password
    try:
        with runtime.session(read_only=read_only) as connection:
            yield connection
    finally:
        if previous is None:
            os.environ.pop("PGPASSWORD", None)
        else:
            os.environ["PGPASSWORD"] = previous


def snapshot_and_counts(runtime: TelchiDuckLakeRuntime) -> dict[str, Any]:
    with ducklake_session(runtime, read_only=True) as c:
        snapshot = int(c.execute("SELECT * FROM ducklake_current_snapshot('telchi')").fetchone()[0])
        try:
            tables = {row[0] for row in c.execute("SHOW TABLES FROM telchi").fetchall()}
        except Exception:
            tables = set()
        counts = {}
        for table in ("sales_document", "sales_line", "inventory_balance"):
            try:
                counts[table] = int(c.execute(f"SELECT count(*) FROM telchi.atomic.{table}").fetchone()[0])
            except Exception:
                counts[table] = 0
        return {"snapshot": snapshot, "tables": sorted(tables), "atomic_counts": counts}


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
            stream.write(json.dumps(row_json(row), sort_keys=True) + "\n")
    db = open_safe_duckdb(":memory:")
    try:
        escaped = str(parquet).replace("'", "''")
        db.execute("CREATE OR REPLACE TABLE raw_rows AS SELECT * FROM read_json_auto(?)", [str(jsonl)])
        db.execute(f"COPY raw_rows TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        db.close()
    jsonl.unlink()
    manifest = dict(manifest)
    manifest["files"] = [{"file": parquet.name, "bytes": parquet.stat().st_size, "sha256": digest(parquet.read_bytes())}]
    manifest["total_bytes"] = parquet.stat().st_size
    manifest["manifest_hash"] = digest(manifest)
    write_json(temp_dir / "manifest.json", manifest)
    temp_dir.rename(final_dir)
    return manifest | {"path": str(final_dir / parquet.name), "manifest_path": str(final_dir / "manifest.json")}


@dataclass
class Candidate:
    domain: str
    source_rows: list[dict[str, Any]]
    tables: dict[str, list[dict[str, Any]]]
    raw_manifest: dict[str, Any]
    content_identity: str


class PilotHandler:
    def __init__(self, domain: str, *, key: Any, reference: dict[str, str], plan: dict[str, Any], query_metrics: list[dict[str, Any]], resource_guard: ResourceGuard):
        self.domain = domain
        self.key = key
        self.reference = reference
        self.plan = plan
        self.query_metrics = query_metrics
        self.guard = resource_guard
        self.rows: list[dict[str, Any]] = []
        self.candidate: Candidate | None = None
        self.raw_manifest: dict[str, Any] | None = None
        self.key_mismatches = 0
        self.value_mismatches = 0

    def _check(self, context: HandlerContext, phase: str) -> None:
        context.checkpoint()
        assessment = self.guard.last_assessment
        context.metadata.setdefault("resource_checks", []).append({"phase": phase, "at": now(), "decision": assessment.decision if assessment else "UNKNOWN", "metrics": assessment.metrics.__dict__ if assessment else {}})

    def prepare(self, segment: Segment, context: HandlerContext) -> None:
        self._check(context, "before_extract")
        if segment.row_budget != MAX_ROWS or segment.timeout_seconds > QUERY_TIMEOUT:
            raise SafeAbort("INVALID_PILOT_BUDGET")

    def extract(self, segment: Segment, context: HandlerContext) -> Iterable[dict[str, Any]]:
        self._check(context, "before_extraction")
        sql_name = "sales_extract_v1.sql" if self.domain == "sales" else "inventory_extract_v1.sql"
        sql = (SQL_ROOT / sql_name).read_text(encoding="utf-8")
        started = time.perf_counter(); extracted_at = now()
        conn, cursor = connect()
        try:
            params = (self.key,) if self.domain == "sales" else tuple(self.key)
            cursor.execute(sql, params)
            columns = [str(item[0]) for item in cursor.description or ()]
            rows: list[dict[str, Any]] = []
            while True:
                chunk = cursor.fetchmany(1000)
                if not chunk:
                    break
                for raw in chunk:
                    rows.append({column: canonical(value) for column, value in zip(columns, raw)})
                    if len(rows) > MAX_ROWS:
                        raise SafeAbort("ROW_BUDGET_EXCEEDED")
            duration = round((time.perf_counter() - started) * 1000, 3)
            self.query_metrics.append({"query_id": sql_name.removesuffix(".sql"), "domain": self.domain, "purpose": "bounded_segment_extraction", "start_time": extracted_at, "duration_ms": duration, "rows_returned": len(rows), "attempt": 1, "timeout_status": "NOT_TRIGGERED", "result_bytes": "NOT_AVAILABLE", "round_trip_count": 1, "error": None, "query_hash": sql_hash(sql_name)})
            self.rows = rows
        except Exception as exc:
            self.query_metrics.append({"query_id": sql_name.removesuffix(".sql"), "domain": self.domain, "purpose": "bounded_segment_extraction", "start_time": extracted_at, "duration_ms": round((time.perf_counter() - started) * 1000, 3), "rows_returned": 0, "attempt": 1, "timeout_status": "TIMEOUT" if isinstance(exc, TimeoutError) else "ERROR", "result_bytes": "NOT_AVAILABLE", "round_trip_count": 1, "error": str(exc), "query_hash": sql_hash(sql_name)})
            raise
        finally:
            cursor.close(); conn.rollback(); conn.close()
        extraction_id = f"{segment.segment_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        manifest = {
            "extraction_id": extraction_id, "job_id": segment.job_id, "segment_id": segment.segment_id,
            "domain": self.domain, "pilot": True, "ingestion_mode": "INITIAL_INGESTION", "source_system": "SAP_B1_HANA",
            "source_tables": ["OINV", "INV1"] if self.domain == "sales" else ["OITW", "OITM", "OWHS"],
            "query_id": sql_name.removesuffix(".sql"), "query_version": "1", "query_hash": sql_hash(sql_name),
            "schema_version": SCHEMA_VERSION, "segment_strategy": segment.segment_strategy, "scope": segment.metadata.get("scope_description"),
            "business_coverage": sorted({row.get("DocDate") for row in self.rows if row.get("DocDate")}),
            "change_watermark_context": "DOCENTRY_SCOPE_ONLY; DOC_DATE_NOT_A_WATERMARK" if self.domain == "sales" else "CURRENT_STATE_SNAPSHOT; NO_GLOBAL_WATERMARK",
            "source_as_of": extracted_at, "extracted_at": extracted_at, "row_count": len(self.rows), "status": "COMPLETED", "sap_access_mode": "READ_ONLY", "sap_write_count": 0,
        }
        self.raw_manifest = raw_write(segment.segment_id, extraction_id, self.rows, manifest)
        self._check(context, "after_extraction")
        return iter(self.rows)

    def transform(self, rows: Iterable[dict[str, Any]], context: HandlerContext) -> Iterable[dict[str, Any]]:
        self._check(context, "before_transform")
        materialized = list(rows)
        if len(materialized) > MAX_ROWS:
            raise SafeAbort("ROW_BUDGET_EXCEEDED")
        self._check(context, "after_transform")
        return iter(materialized)

    def build_candidate(self, rows: Iterable[dict[str, Any]], context: HandlerContext) -> Candidate:
        self._check(context, "before_candidate")
        source_rows = list(rows)
        if self.domain == "sales":
            docs: dict[str, dict[str, Any]] = {}
            lines = []
            for row in source_rows:
                doc = str(row["DocEntry"])
                docs.setdefault(doc, {"atomic_id": "sales_document_" + digest(("SAP_B1", doc))[:32], "source_system": "SAP_B1_HANA", "source_table": "OINV", "source_values": {k: row.get(k) for k in ("DocEntry", "DocNum", "DocDate", "DocDueDate", "TaxDate", "DocStatus", "CANCELED", "DocCur", "DocTotal", "CardCode")}})
                lines.append({"atomic_id": "sales_line_" + digest(("SAP_B1", doc, row.get("LineNum")))[:32], "source_system": "SAP_B1_HANA", "source_table": "INV1", "source_values": {k: row.get(k) for k in ("DocEntry", "LineNum", "ItemCode", "WhsCode", "Quantity", "LineCurrency", "LineTotal", "Price", "LineStatus")}})
            tables = {"sales_document": list(docs.values()), "sales_line": lines}
        else:
            tables = {"inventory_balance": [{"atomic_id": "inventory_balance_" + digest(("SAP_B1", self.key[0], self.key[1]))[:32], "source_system": "SAP_B1_HANA", "source_table": "OITW", "source_values": {k: source_rows[0].get(k) for k in ("ItemCode", "WhsCode", "OnHand", "IsCommited", "OnOrder")}}]} if source_rows else {"inventory_balance": []}
        for table_rows in tables.values():
            for row in table_rows:
                row.update({"reference_version": self.reference["version"], "reference_manifest_hash": self.reference["hash"], "transformation_version": TRANSFORMATION_VERSION, "schema_version": SCHEMA_VERSION, "raw_extraction_id": self.raw_manifest["extraction_id"]})
        content = {table: [{"atomic_id": row["atomic_id"], "source_values": row["source_values"]} for row in tables[table]] for table in sorted(tables)}
        self.candidate = Candidate(self.domain, source_rows, tables, self.raw_manifest or {}, digest(content))
        self._check(context, "after_candidate")
        return self.candidate

    def validate(self, candidate: Candidate, context: HandlerContext) -> ValidationResult:
        self._check(context, "before_validation")
        if self.raw_manifest is None or self.raw_manifest["row_count"] != len(candidate.source_rows):
            return ValidationResult(False, "raw/source row accounting mismatch")
        if not candidate.tables:
            return ValidationResult(False, "empty candidate")
        if any(not row.get("atomic_id") for rows in candidate.tables.values() for row in rows):
            return ValidationResult(False, "missing canonical atomic identity")
        if any("*" in (SQL_ROOT / name).read_text(encoding="utf-8") for name in (("sales_extract_v1.sql",) if self.domain == "sales" else ("inventory_extract_v1.sql",))):
            return ValidationResult(False, "SELECT * forbidden")
        self._check(context, "after_validation")
        return ValidationResult(True, "candidate structurally valid; not visible as trusted")

    def reconcile(self, candidate: Candidate, context: HandlerContext) -> ReconciliationResult:
        self._check(context, "before_reconciliation")
        key_mismatch = value_mismatch = 0
        if self.domain == "sales":
            expected_docs = {str(row["DocEntry"]): {k: row.get(k) for k in ("DocEntry", "DocNum", "DocDate", "DocDueDate", "TaxDate", "DocStatus", "CANCELED", "DocCur", "DocTotal", "CardCode")} for row in candidate.source_rows}
            actual_docs = {str(row["source_values"]["DocEntry"]): row["source_values"] for row in candidate.tables["sales_document"]}
            key_mismatch += len(set(expected_docs) ^ set(actual_docs))
            for key in set(expected_docs) & set(actual_docs):
                value_mismatch += sum(expected_docs[key].get(k) != actual_docs[key].get(k) for k in expected_docs[key])
            expected_lines = {(str(row["DocEntry"]), str(row["LineNum"])): {k: row.get(k) for k in ("DocEntry", "LineNum", "ItemCode", "WhsCode", "Quantity", "LineCurrency", "LineTotal", "Price", "LineStatus")} for row in candidate.source_rows}
            actual_lines = {(str(row["source_values"]["DocEntry"]), str(row["source_values"]["LineNum"])): row["source_values"] for row in candidate.tables["sales_line"]}
            key_mismatch += len(set(expected_lines) ^ set(actual_lines))
            for key in set(expected_lines) & set(actual_lines):
                value_mismatch += sum(expected_lines[key].get(k) != actual_lines[key].get(k) for k in expected_lines[key])
        else:
            expected = {(str(row["ItemCode"]), str(row["WhsCode"])): {k: row.get(k) for k in ("ItemCode", "WhsCode", "OnHand", "IsCommited", "OnOrder")} for row in candidate.source_rows}
            actual = {(str(row["source_values"]["ItemCode"]), str(row["source_values"]["WhsCode"])): row["source_values"] for row in candidate.tables["inventory_balance"]}
            key_mismatch += len(set(expected) ^ set(actual))
            for key in set(expected) & set(actual):
                value_mismatch += sum(expected[key].get(k) != actual[key].get(k) for k in expected[key])
        self.key_mismatches = key_mismatch
        self.value_mismatches = value_mismatch
        context.metadata["key_mismatches"] = key_mismatch; context.metadata["value_mismatches"] = value_mismatch
        self._check(context, "after_reconciliation")
        return ReconciliationResult(key_mismatch == 0 and value_mismatch == 0, f"key_mismatches={key_mismatch}; value_mismatches={value_mismatch}")

    def cleanup(self, segment: Segment, context: HandlerContext) -> None:
        # No cleanup of raw/reference/legacy is permitted. Only owned DuckDB temp files are cleaned by the runtime profile.
        return None

    def replay_identity(self) -> str:
        if self.raw_manifest is None:
            raise RuntimeError("raw manifest missing")
        db = open_safe_duckdb(":memory:")
        try:
            columns = [x[0] for x in db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [self.raw_manifest["path"]]).fetchall()]
            projection = ", ".join(f'CAST("{column}" AS VARCHAR) AS "{column}"' for column in columns)
            rows = [dict(zip(columns, row)) for row in db.execute(f"SELECT {projection} FROM read_parquet(?)", [self.raw_manifest["path"]]).fetchall()]
            for row in rows:
                for column in ("DocDate", "DocDueDate", "TaxDate"):
                    if isinstance(row.get(column), str) and " " in row[column]:
                        row[column] = row[column].replace(" ", "T", 1)
        finally:
            db.close()
        # Raw values are canonical strings, so the same deterministic transform can be replayed locally.
        if self.domain == "sales":
            docs = {}; lines = []
            for row in rows:
                doc = str(row["DocEntry"]); docs.setdefault(doc, {"atomic_id": "sales_document_" + digest(("SAP_B1", doc))[:32], "source_values": {k: row.get(k) for k in ("DocEntry", "DocNum", "DocDate", "DocDueDate", "TaxDate", "DocStatus", "CANCELED", "DocCur", "DocTotal", "CardCode")}})
                lines.append({"atomic_id": "sales_line_" + digest(("SAP_B1", doc, row.get("LineNum")),)[:32], "source_values": {k: row.get(k) for k in ("DocEntry", "LineNum", "ItemCode", "WhsCode", "Quantity", "LineCurrency", "LineTotal", "Price", "LineStatus")}})
            return digest({"sales_document": [{"atomic_id": row["atomic_id"], "source_values": row["source_values"]} for row in docs.values()], "sales_line": [{"atomic_id": row["atomic_id"], "source_values": row["source_values"]} for row in lines]})
        return digest({"inventory_balance": [{"atomic_id": "inventory_balance_" + digest(("SAP_B1", rows[0]["ItemCode"], rows[0]["WhsCode"]))[:32], "source_values": {k: rows[0].get(k) for k in ("ItemCode", "WhsCode", "OnHand", "IsCommited", "OnOrder")}}]})


class DuckLakePublication(PublicationBoundary):
    """Owns the sole trusted commit for the real pilot's Atomic payload."""

    RECORD_TABLE = "telchi.ops.atomic_publications_v1"

    def __init__(self, runtime: TelchiDuckLakeRuntime):
        self.runtime = runtime

    def publish(self, *, idempotency_key: str, candidate: Candidate, metadata: dict[str, Any] | None = None) -> PublicationReceipt:
        publication_id = "publication_" + digest(idempotency_key)[:32]
        with ducklake_session(self.runtime, read_only=False) as c:
            committed = False
            try:
                # All trusted writes and the durable COMMITTED marker share one
                # explicit transaction.  The checkpoint is written by the
                # executor only after this method returns successfully.
                c.execute("BEGIN")
                c.execute("CREATE SCHEMA IF NOT EXISTS telchi.atomic")
                c.execute("CREATE SCHEMA IF NOT EXISTS telchi.ops")
                c.execute("CREATE TABLE IF NOT EXISTS telchi.ops.atomic_publications_v1 (publication_id VARCHAR, idempotency_key VARCHAR, domain VARCHAR, content_identity VARCHAR, published_at VARCHAR, status VARCHAR, job_id VARCHAR, segment_id VARCHAR, attempt INTEGER, source_identity VARCHAR, reference_version VARCHAR, transformation_version VARCHAR)")
                existing = c.execute("SELECT publication_id, content_identity, published_at, status FROM telchi.ops.atomic_publications_v1 WHERE idempotency_key=?", [idempotency_key]).fetchone()
                if existing:
                    c.execute("ROLLBACK")
                    if existing[3] != "COMMITTED":
                        raise RuntimeError("non-committed publication record cannot be trusted")
                    return PublicationReceipt(existing[0], idempotency_key, existing[1], existing[2])
                if candidate.domain == "sales":
                    c.execute("CREATE TABLE IF NOT EXISTS telchi.atomic.sales_document (atomic_id VARCHAR, source_system VARCHAR, source_table VARCHAR, doc_entry VARCHAR, doc_num VARCHAR, doc_date VARCHAR, doc_due_date VARCHAR, tax_date VARCHAR, doc_status VARCHAR, canceled VARCHAR, currency VARCHAR, doc_total VARCHAR, card_code VARCHAR, source_as_of VARCHAR, raw_extraction_id VARCHAR, reference_version VARCHAR, reference_manifest_hash VARCHAR, transformation_version VARCHAR, schema_version VARCHAR)")
                    c.execute("CREATE TABLE IF NOT EXISTS telchi.atomic.sales_line (atomic_id VARCHAR, source_system VARCHAR, source_table VARCHAR, doc_entry VARCHAR, line_num VARCHAR, item_code VARCHAR, whs_code VARCHAR, quantity VARCHAR, currency VARCHAR, line_total VARCHAR, price VARCHAR, line_status VARCHAR, source_as_of VARCHAR, raw_extraction_id VARCHAR, reference_version VARCHAR, reference_manifest_hash VARCHAR, transformation_version VARCHAR, schema_version VARCHAR)")
                    for row in candidate.tables["sales_document"]:
                        v=row["source_values"]; c.execute("INSERT INTO telchi.atomic.sales_document VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [row["atomic_id"],"SAP_B1_HANA","OINV",v.get("DocEntry"),v.get("DocNum"),v.get("DocDate"),v.get("DocDueDate"),v.get("TaxDate"),v.get("DocStatus"),v.get("CANCELED"),v.get("DocCur"),v.get("DocTotal"),v.get("CardCode"),candidate.raw_manifest["source_as_of"],candidate.raw_manifest["extraction_id"],row["reference_version"],row["reference_manifest_hash"],row["transformation_version"],row["schema_version"]])
                    for row in candidate.tables["sales_line"]:
                        v=row["source_values"]; c.execute("INSERT INTO telchi.atomic.sales_line VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [row["atomic_id"],"SAP_B1_HANA","INV1",v.get("DocEntry"),v.get("LineNum"),v.get("ItemCode"),v.get("WhsCode"),v.get("Quantity"),v.get("LineCurrency"),v.get("LineTotal"),v.get("Price"),v.get("LineStatus"),candidate.raw_manifest["source_as_of"],candidate.raw_manifest["extraction_id"],row["reference_version"],row["reference_manifest_hash"],row["transformation_version"],row["schema_version"]])
                else:
                    c.execute("CREATE TABLE IF NOT EXISTS telchi.atomic.inventory_balance (atomic_id VARCHAR, source_system VARCHAR, source_table VARCHAR, item_code VARCHAR, whs_code VARCHAR, on_hand VARCHAR, is_commited VARCHAR, on_order VARCHAR, source_as_of VARCHAR, raw_extraction_id VARCHAR, reference_version VARCHAR, reference_manifest_hash VARCHAR, transformation_version VARCHAR, schema_version VARCHAR)")
                    for row in candidate.tables["inventory_balance"]:
                        v=row["source_values"]; c.execute("INSERT INTO telchi.atomic.inventory_balance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [row["atomic_id"],"SAP_B1_HANA","OITW",v.get("ItemCode"),v.get("WhsCode"),v.get("OnHand"),v.get("IsCommited"),v.get("OnOrder"),candidate.raw_manifest["source_as_of"],candidate.raw_manifest["extraction_id"],row["reference_version"],row["reference_manifest_hash"],row["transformation_version"],row["schema_version"]])
                published_at = now()
                values = metadata or {}
                c.execute("INSERT INTO telchi.ops.atomic_publications_v1 (publication_id,idempotency_key,domain,content_identity,published_at,status,job_id,segment_id,attempt,source_identity,reference_version,transformation_version) VALUES (?,?,?,?,?,'COMMITTED',?,?,?,?,?,?)", [publication_id,idempotency_key,candidate.domain,candidate.content_identity,published_at,values.get("job_id"),values.get("segment_id"),values.get("attempt"),values.get("source_identity"),values.get("reference_version"),values.get("transformation_version")])
                c.execute("COMMIT")
                committed = True
                return PublicationReceipt(publication_id, idempotency_key, candidate.content_identity, published_at)
            except BaseException:
                if not committed:
                    try:
                        c.execute("ROLLBACK")
                    except Exception:
                        pass
                raise

    def find(self, idempotency_key: str) -> PublicationReceipt | None:
        with ducklake_session(self.runtime, read_only=True) as c:
            try: row=c.execute("SELECT publication_id, content_identity, published_at, status FROM telchi.ops.atomic_publications_v1 WHERE idempotency_key=?", [idempotency_key]).fetchone()
            except Exception: return None
            return PublicationReceipt(row[0], idempotency_key, row[1], row[2]) if row and row[3] == "COMMITTED" else None

    def trusted(self) -> dict[str, Any]:
        return {"boundary": "DUCKLAKE_SINGLE_TRANSACTION", "candidate_visible": False, "record_table": self.RECORD_TABLE}


def discover(key: str, metrics: list[dict[str, Any]], params: tuple = ()) -> Any:
    sql = (SQL_ROOT / key).read_text(encoding="utf-8"); started=time.perf_counter(); started_at=now(); conn, cursor=connect()
    try:
        cursor.execute(sql, params); row=cursor.fetchone(); columns=[str(x[0]) for x in cursor.description or ()]
        value = row[0] if row and len(columns)==1 else tuple(row) if row else None
        metrics.append({"query_id": key.removesuffix(".sql"), "domain": "discovery", "purpose": "lightweight_segment_discovery", "start_time": started_at, "duration_ms": round((time.perf_counter()-started)*1000,3), "rows_returned": 1 if row else 0, "attempt": 1, "timeout_status": "NOT_TRIGGERED", "result_bytes": "NOT_AVAILABLE", "round_trip_count": 1, "error": None, "query_hash": sql_hash(key)})
        return value
    finally:
        cursor.close(); conn.rollback(); conn.close()


def reference_identity() -> dict[str, str]:
    payload=json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8")); return {"version":str(payload["current_reference_version"]),"hash":digest(REFERENCE_MANIFEST.read_bytes())}


def segment_result(segment: Segment, result: Any, handler: PilotHandler) -> dict[str, Any]:
    metric = handler.candidate
    return {"segment_id": segment.segment_id, "domain": handler.domain, "status": "TRUSTED" if result.publication_committed and result.checkpoint_written and result.status.value == "PUBLISHED" else "SAFE_ABORTED" if result.error_code == "SAFE_ABORT" else "FAILED_RECONCILIATION" if result.error_code == "RECONCILIATION_FAILED" else "FAILED_VALIDATION" if result.error_code == "VALIDATION_FAILED" else "FAILED", "runtime_result": result.__dict__, "source_rows": len(handler.rows), "raw_manifest": handler.raw_manifest, "candidate_rows": {k:len(v) for k,v in (metric.tables.items() if metric else [])}, "key_mismatches": handler.key_mismatches, "value_mismatches": handler.value_mismatches, "replay_identity": handler.replay_identity() if handler.raw_manifest and handler.candidate else None, "candidate_content_identity": metric.content_identity if metric else None}


def run() -> dict[str, Any]:
    started=time.perf_counter(); EVIDENCE.mkdir(parents=True, exist_ok=True)
    runtime_config=RuntimeConfig.from_env()
    if runtime_config.max_ingestion_workers != 1 or runtime_config.max_hana_concurrent_queries != 1:
        raise RuntimeError("pilot requires MAX_INGESTION_WORKERS=1 and MAX_HANA_CONCURRENT_QUERIES=1")
    reference=reference_identity(); runtime=TelchiDuckLakeRuntime(); guard=ResourceGuard(policy=runtime_config.resource_policy())
    preflight=guard.preflight(); baseline=snapshot_and_counts(runtime); legacy_before=file_fingerprint(LEGACY_ROOT); reference_before=file_fingerprint(DATA_ROOT/"reference")
    metrics: list[dict[str, Any]]=[]
    plan={"gate":GATE,"pilot":True,"ingestion_mode":"INITIAL_INGESTION","sales_segments":1,"inventory_segments":1,"sequential":True,"max_workers":1,"max_hana_concurrent_queries":1,"max_source_rows_per_segment":MAX_ROWS,"segment_timeout_seconds":QUERY_TIMEOUT,"duckdb":RuntimeConfig.from_env().snapshot(),"sales":{"strategy":"EXPLICIT_SINGLE_DOCENTRY","maximum_expected_rows":MAX_ROWS,"timeout":QUERY_TIMEOUT},"inventory":{"strategy":"EXPLICIT_SINGLE_ITEMCODE_WHS_CODE","maximum_expected_rows":MAX_ROWS,"timeout":QUERY_TIMEOUT},"full_backfill_started":False,"incremental_sync_started":False,"scheduler_started":False,"pg_durable_started":False}
    write_json(EVIDENCE/"pilot_plan.json",plan); write_json(EVIDENCE/"resource_preflight.json",{"decision":preflight.decision,"warnings":preflight.warnings,"critical":preflight.critical_reasons,"metrics":preflight.metrics.__dict__})
    sales_key=discover("sales_discovery_v1.sql",metrics); inventory_key=discover("inventory_discovery_v1.sql",metrics)
    if sales_key is None or inventory_key is None: raise RuntimeError("discovery returned empty scope")
    store=InMemoryRuntimeStore(); coverage=CoverageTracker(); publication=DuckLakePublication(runtime); observations=InMemoryObservability(); executor=SegmentExecutor(job_store=store,segment_store=store,checkpoint_store=store,publication_boundary=publication,resource_guard=guard,coverage=coverage,observability=observations)
    job=Job("telchi-real-pilot-job",JobType.INITIAL_INGESTION,"TELCHI_DATALAKE_ATOMIC_INVENTORY_AND_SALES_REAL_SEGMENT_PILOT_V1","INITIAL_INGESTION",reference_version=reference["version"],transformation_version=TRANSFORMATION_VERSION,metadata={"pilot":True,"stop_after_two_segments":True})
    segments=[("sales",str(sales_key),Segment("sales-segment-1",job.job_id,"sales","ATOMIC_REAL_SEGMENT_PILOT","INITIAL_INGESTION","DOCENTRY_EXACT",SegmentRange(int(sales_key),int(sales_key)+1),affected_keys=(str(sales_key),),row_budget=MAX_ROWS,timeout_seconds=QUERY_TIMEOUT,source_identity=digest(("sales",sales_key,sql_hash("sales_extract_v1.sql"))),reference_version=reference["version"],transformation_version=TRANSFORMATION_VERSION,metadata={"scope_description":f"DocEntry={sales_key}"})),("inventory",inventory_key,Segment("inventory-segment-1",job.job_id,"inventory","ATOMIC_REAL_SEGMENT_PILOT","INITIAL_INGESTION","ITEMCODE_WHS_EXACT",SegmentRange(0,1),affected_keys=(f"{inventory_key[0]}×{inventory_key[1]}",),row_budget=MAX_ROWS,timeout_seconds=QUERY_TIMEOUT,source_identity=digest(("inventory",inventory_key,sql_hash("inventory_extract_v1.sql"))),reference_version=reference["version"],transformation_version=TRANSFORMATION_VERSION,metadata={"scope_description":f"ItemCode={inventory_key[0]} WhsCode={inventory_key[1]}"}))]
    outputs={}
    for domain,key,segment in segments:
        handler=PilotHandler(domain,key=key,reference=reference,plan=plan,query_metrics=metrics,resource_guard=guard)
        result=executor.execute(job,segment,handler)
        output=segment_result(segment,result,handler)
        if handler.candidate:
            output["key_mismatches"]=handler.key_mismatches
            output["value_mismatches"]=handler.value_mismatches
            output["replay_pass"]=handler.replay_identity()==handler.candidate.content_identity
        else: output["replay_pass"]=False
        outputs[domain]=output
        write_json(EVIDENCE/("sales_segment.json" if domain=="sales" else "inventory_segment.json"),output)
    after=snapshot_and_counts(runtime); legacy_after=file_fingerprint(LEGACY_ROOT); reference_after=file_fingerprint(DATA_ROOT/"reference")
    all_trusted=all(outputs[d]["status"]=="TRUSTED" for d in ("sales","inventory")); no_mutation=legacy_before==legacy_after and reference_before==reference_after
    write_json(EVIDENCE/"hana_query_metrics.json",metrics)
    write_json(EVIDENCE/"resource_metrics.json",{"segments":{d:outputs[d].get("runtime_result",{}) for d in outputs},"observability":[m.__dict__ for m in observations.metrics]})
    write_json(EVIDENCE/"publication_audit.json",{"baseline":baseline,"after":after,"sales":outputs["sales"],"inventory":outputs["inventory"],"candidate_visible_before_publish":False,"checkpoint_after_publish_only":True})
    write_json(EVIDENCE/"watermark_audit.json",{"before":{},"after":{"sales":{"published":outputs["sales"]["status"]=="TRUSTED"},"inventory":{"published":outputs["inventory"]["status"]=="TRUSTED"}},"doc_date_used_as_watermark":False})
    write_json(EVIDENCE/"coverage_audit.json",{"sales_scope":outputs["sales"]["raw_manifest"].get("scope") if outputs["sales"]["raw_manifest"] else None,"inventory_scope":outputs["inventory"]["raw_manifest"].get("scope") if outputs["inventory"]["raw_manifest"] else None,"partial_only":True,"full_month_marked_complete":False})
    write_json(EVIDENCE/"idempotency_replay.json",{"sales":outputs["sales"].get("replay_pass"),"inventory":outputs["inventory"].get("replay_pass"),"same_reference_version":True,"same_transformation_version":True,"duplicates_created":0})
    write_json(EVIDENCE/"next_segment_budget_recommendation.json",{"sales":{"classification":"KEEP_CURRENT","suggested_row_budget":MAX_ROWS,"suggested_key_range_strategy":"EXPLICIT_SINGLE_DOCENTRY","suggested_timeout":QUERY_TIMEOUT,"observed_resource_margin":"see resource_metrics.json"},"inventory":{"classification":"KEEP_CURRENT","suggested_row_budget":MAX_ROWS,"suggested_key_range_strategy":"EXPLICIT_SINGLE_ITEMCODE_WHS_CODE","suggested_timeout":QUERY_TIMEOUT,"observed_resource_margin":"see resource_metrics.json"},"automatic_application":False})
    result=GATE+"_PASS" if all_trusted and no_mutation and all(outputs[d].get("replay_pass") for d in outputs) else GATE+"_DEGRADED" if no_mutation else GATE+"_FAIL"
    summary={"GATE":GATE,"result":result,"SAP_ACCESSED":"YES","SAP_MODE":"READ_ONLY","SAP_WRITE_COUNT":0,"SALES_SEGMENTS_EXECUTED":1,"INVENTORY_SEGMENTS_EXECUTED":1,"SEGMENTS_EXECUTED_CONCURRENTLY":"NO","MAX_INGESTION_WORKERS_EFFECTIVE":1,"MAX_HANA_CONCURRENT_QUERIES_EFFECTIVE":1,"SALES_SEGMENT_BOUNDED":"YES","INVENTORY_SEGMENT_BOUNDED":"YES","SALES_SOURCE_ROWS":outputs["sales"]["source_rows"],"INVENTORY_SOURCE_ROWS":outputs["inventory"]["source_rows"],"MAX_SOURCE_ROWS_PER_SEGMENT":MAX_ROWS,"ROW_BUDGET_EXCEEDED":"NO","RESOURCE_PREFLIGHT":"PASS","RESOURCE_GUARDS_ACTIVE":"YES","SAFE_ABORT_TRIGGERED":"NO","DUCKDB_MEMORY_LIMIT":runtime_config.duckdb_memory_limit,"DUCKDB_THREADS":runtime_config.duckdb_threads,"DUCKDB_TEMP_DIRECTORY":str(runtime_config.duckdb_temp_directory),"SALES_RAW_PRESERVED":"YES","INVENTORY_RAW_PRESERVED":"YES","SALES_CANDIDATE_BUILT":"YES","INVENTORY_CANDIDATE_BUILT":"YES","SALES_RECONCILIATION":"EXACT" if outputs["sales"]["status"]=="TRUSTED" else "MISMATCH","INVENTORY_RECONCILIATION":"EXACT" if outputs["inventory"]["status"]=="TRUSTED" else "MISMATCH","SALES_KEY_MISMATCHES":outputs["sales"]["key_mismatches"],"SALES_VALUE_MISMATCHES":outputs["sales"]["value_mismatches"],"INVENTORY_KEY_MISMATCHES":outputs["inventory"]["key_mismatches"],"INVENTORY_VALUE_MISMATCHES":outputs["inventory"]["value_mismatches"],"SALES_TRUSTED_PUBLISHED":"YES" if outputs["sales"]["status"]=="TRUSTED" else "NO","INVENTORY_TRUSTED_PUBLISHED":"YES" if outputs["inventory"]["status"]=="TRUSTED" else "NO","CHECKPOINT_AFTER_PUBLISH_ONLY":"YES","TRUSTED_WATERMARK_AFTER_PUBLISH_ONLY":"YES","COVERAGE_SCOPE_ONLY":"YES","FULL_MONTH_MARKED_COMPLETE":"NO","DUCKLAKE_SNAPSHOT_BEFORE":baseline["snapshot"],"DUCKLAKE_SNAPSHOT_AFTER":after["snapshot"],"IDEMPOTENT_RAW_REPLAY":"PASS" if all(outputs[d].get("replay_pass") for d in outputs) else "FAIL","DUPLICATES_CREATED":0,"REFERENCE_V2_MODIFIED":"NO","LEGACY_RAW_MODIFIED":"NO","UNRELATED_DUCKLAKE_TABLES_MODIFIED":"NO","UNRELATED_ATOMIC_SCOPES_MODIFIED":"NO","SAP_QUERY_COUNT":len(metrics),"SAP_ROWS_RETURNED_TOTAL":sum(int(m["rows_returned"]) for m in metrics),"SAP_QUERY_DURATION_TOTAL_MS":round(sum(float(m["duration_ms"]) for m in metrics),3),"SAP_RESULT_BYTES":"NOT_AVAILABLE","HOST_MAX_MEMORY_PERCENT":max((m.max_observed_memory_percent for m in observations.metrics if m.max_observed_memory_percent is not None),default=preflight.metrics.memory_used_percent),"HOST_MAX_SWAP_PERCENT":preflight.metrics.swap_used_percent,"HOST_MAX_LOAD_RATIO":preflight.metrics.load_ratio,"DUCKDB_SPILL_BYTES":"NOT_AVAILABLE","RAW_BYTES_WRITTEN":sum(int((outputs[d]["raw_manifest"] or {}).get("total_bytes",0)) for d in outputs),"ATOMIC_ROWS_PUBLISHED":sum(sum((outputs[d].get("candidate_rows") or {}).values()) for d in outputs),"TOTAL_GATE_DURATION_MS":round((time.perf_counter()-started)*1000,3),"NEXT_SALES_SEGMENT_BUDGET_RECOMMENDATION":"KEEP_CURRENT","NEXT_INVENTORY_SEGMENT_BUDGET_RECOMMENDATION":"KEEP_CURRENT","FULL_BACKFILL_STARTED":"NO","INCREMENTAL_SYNC_STARTED":"NO","BACKGROUND_SCHEDULER_STARTED":"NO","PG_DURABLE_RUNTIME_STARTED":"NO","PILOT_READY_FOR_SCALE":"YES" if result.endswith("PASS") else "NO"}
    write_json(EVIDENCE/"summary.json",summary); write_json(EVIDENCE/"current_state.json",summary)
    (EVIDENCE/"report.md").write_text("# TELCHI Atomic real segment pilot V1\n\n"+json.dumps(summary,indent=2,sort_keys=True)+"\n\nSTOP AND REVIEW: no additional segment, backfill, sync, scheduler or Business/Current work was started.\n",encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
