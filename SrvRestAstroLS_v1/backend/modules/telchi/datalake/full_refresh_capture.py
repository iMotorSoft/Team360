"""Bounded capture adapter for existing Telchi contracts; never a publisher.

One SQL statement/server cursor per segment (statement-consistent observation,
not a cross-domain transaction). Completed segments are reusable only after
hash verification. An interrupted cursor cannot be resumed as the same SAP
snapshot: its intent blocks automatic re-extraction. No shared Atomic writes.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import time

from . import sales_incremental as durable
from .raw import digest, file_hash, write_raw
from .source import HanaTransportLimits
from .sql import assert_read_only_select
from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb
from modules.telchi.runtime.resource_guard import ResourceGuard

CONTRACT = "full-data-lake-refresh-capture-v1"
CLOCK_SQL = 'SELECT CURRENT_UTCTIMESTAMP AS "utc", CURRENT_TIMESTAMP AS "source_local", CURRENT_DATE AS "source_date" FROM DUMMY'


@dataclass(frozen=True)
class DomainBudget:
    max_selects: int
    total_seconds: int
    max_rows_per_statement: int
    statement_seconds: int = 60
    operation_seconds: int = 1200
    batch_rows: int = 10000

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in asdict(self).values()):
            raise ValueError("finite positive budgets required")
        if self.batch_rows > 10000:
            raise ValueError("batch exceeds memory contract")

    def transport(self):
        return HanaTransportLimits(query_seconds=self.statement_seconds,
                                   operation_seconds=self.operation_seconds,
                                   max_rows=self.max_rows_per_statement,
                                   communication_ms=30000)


class CaptureSession:
    def __init__(self, root, source, budget, *, guard=None, profile=None):
        self.root, self.source, self.budget = Path(root), source, budget
        if source.limits != budget.transport():
            raise ValueError("transport and domain budget differ")
        self.root.mkdir(parents=True, exist_ok=True)
        budget_path = self.root / "domain-budget.json"
        if not budget_path.exists():
            durable.seal(budget_path, dict(budget=asdict(budget), started_at=durable.now()))
        previous = durable.read_json(budget_path)
        if previous['budget'] != asdict(budget):
            raise ValueError("DOMAIN_BUDGET_CONFLICT")
        self.started_at = datetime.fromisoformat(previous['started_at'])
        self.started = time.monotonic()
        self.audit_offset = len(list(self.root.glob('query-*.json')))
        self.selects = self.audit_offset
        self.guard = guard or ResourceGuard()
        self.profile = profile or DuckDBSafetyProfile(memory_limit="256MB", threads=2)

    def check(self):
        self.guard.checkpoint()
        if self.selects >= self.budget.max_selects:
            raise RuntimeError("DOMAIN_SELECT_BUDGET_EXHAUSTED")
        if (datetime.now(timezone.utc) - self.started_at).total_seconds() >= self.budget.total_seconds:
            raise TimeoutError("DOMAIN_WALL_BUDGET_EXHAUSTED")

    def query(self, query_id, sql, params=()):
        self.check()
        self.selects += 1
        try:
            return self.source.query_read_only(query_id, sql, params)
        finally:
            self.audit()

    def audit(self):
        # Each query gets an immutable audit receipt, including failed queries.
        for i, event in enumerate(self.source.query_log):
            path = self.root / f"query-{i + self.audit_offset:05d}.json"
            if not path.exists():
                durable.seal(path, event)

    def capture(self, dataset, sql, params=(), *, keys, sums=(), semantic_scope, nullable_keys=False, ordered_keys=True):
        if not dataset.replace("_", "").replace("-", "").isalnum():
            raise ValueError("invalid segment name")
        assert_read_only_select(sql)
        if not keys or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field) for field in (*keys, *sums)):
            raise ValueError("explicit safe logical keys required")
        directory = self.root / dataset
        directory.mkdir(exist_ok=True)
        with durable.locked(directory):
            plan = dict(contract=CONTRACT, sql=sql, params=list(params), keys=list(keys), sums=list(sums),
                        semantic_scope=semantic_scope, budget=asdict(self.budget), publication="NOT_PUBLISHED",
                        nullable_keys=nullable_keys, ordered_keys=ordered_keys)
            if (directory / "complete.json").exists():
                result = durable.read_json(directory / "complete.json")
                if result["plan_sha256"] != digest(plan):
                    raise ValueError("SEGMENT_PLAN_CONFLICT")
                verify_capture(directory)
                return result
            if (directory / "intent.json").exists():
                raise RuntimeError("INTERRUPTED_SNAPSHOT_REQUIRES_NEW_EXPLICIT_ATTEMPT")
            self.guard.preflight()
            clock_before = self.query(dataset + "_clock_before", CLOCK_SQL)[0]
            body = sql.rsplit(" ORDER BY ", 1)[0] if " ORDER BY " in sql else sql
            control_sql = 'SELECT COUNT(*) AS "rows"' + ''.join(
                f', SUM(Q."{f}") AS "sum_{f}"' for f in sums) + f" FROM ({body}) Q"
            before = self.query(dataset + "_control_before", control_sql, params)[0]
            intent = dict(plan=plan, plan_sha256=digest(plan), source_before=clock_before,
                          control_before=before, started_at=durable.now())
            durable.seal(directory / "intent.json", intent)
            started = time.monotonic()
            total, pages, last_key = 0, [], None
            totals = {f: Decimal(0) for f in sums}
            try:
                self.check()
                self.selects += 1
                with closing(self.source.stream_read_only(dataset, sql, params, batch_size=self.budget.batch_rows)) as stream:
                    for rows in stream:
                        self.guard.checkpoint()
                        if (datetime.now(timezone.utc) - self.started_at).total_seconds() >= self.budget.total_seconds:
                            raise TimeoutError("DOMAIN_WALL_BUDGET_EXHAUSTED")
                        for row in rows:
                            key = tuple(row[k] for k in keys)
                            if (not nullable_keys and any(k is None for k in key)) or (ordered_keys and last_key is not None and key <= last_key):
                                raise ValueError("NULL_DUPLICATE_OR_UNORDERED_KEY")
                            last_key = key
                            for f in sums:
                                totals[f] += Decimal(str(row[f] or 0))
                        manifest = write_raw(root=directory / "raw", segment_id=f"page-{len(pages):05d}",
                            extraction_id="capture", rows=rows, profile=self.profile,
                            metadata=dict(contract=CONTRACT, dataset=dataset, plan_sha256=digest(plan),
                                          source_as_of=clock_before["utc"], source_as_of_window=list(params),
                                          semantic_scope=semantic_scope, trusted_for_foundation=False))
                        # Strengthen existing raw writer durability before checkpoint commit.
                        for path in (Path(manifest["path"]), Path(manifest["manifest_path"])):
                            with path.open("rb") as fd:
                                os.fsync(fd.fileno())
                        durable.sync_dir(Path(manifest["manifest_path"]).parent)
                        page = dict(manifest_path=manifest["manifest_path"], manifest_hash=manifest["manifest_hash"],
                                    path=manifest["path"], sha256=manifest["file_hashes"][0], rows=len(rows),
                                    last_key=list(last_key), cumulative_rows=total + len(rows))
                        durable.seal(directory / f"checkpoint-{len(pages):05d}.json", page)
                        pages.append(page)
                        total += len(rows)
                self.audit()
                if pages:
                    db = open_safe_duckdb(profile=self.profile)
                    try:
                        group = ','.join('"' + k + '"' for k in keys)
                        duplicates = db.execute(f"SELECT COUNT(*) FROM (SELECT {group} FROM read_parquet(?, union_by_name=true) GROUP BY {group} HAVING COUNT(*) > 1)",
                                                [[p['path'] for p in pages]]).fetchone()[0]
                        if duplicates:
                            raise ValueError("DUPLICATE_LOGICAL_KEYS")
                    finally:
                        db.close()
                after = self.query(dataset + "_control_after", control_sql, params)[0]
                clock_after = self.query(dataset + "_clock_after", CLOCK_SQL)[0]
                durable.seal(directory / "controls.json", dict(before=before, after=after,
                    captured_rows=total, captured_sums={k:str(v) for k,v in totals.items()}))
                expected = dict(rows=total, **{"sum_" + k: str(v) for k, v in totals.items()})
                for control in (before, after):
                    if int(control["rows"]) != total or any(Decimal(str(control["sum_" + f] or 0)) != totals[f] for f in sums):
                        raise ValueError("SOURCE_CONTROL_CHANGED_OR_CAPTURE_MISMATCH")
                result = dict(status="CAPTURE_RECONCILED_NOT_PUBLISHED", plan_sha256=digest(plan),
                    source_before=clock_before, source_after=clock_after,
                    row_count=total, pages=pages, control=expected, elapsed_seconds=time.monotonic()-started,
                    captured_at=durable.now(), keys=list(keys), semantic_scope=semantic_scope,
                    observation="SINGLE_STATEMENT_CURSOR; other queries/captures not transactionally simultaneous",
                    late_change_watermark=None, published_watermark=None)
                durable.seal(directory / "complete.json", result)
                return result
            except BaseException as exc:
                self.audit()
                failure = directory / "failure.json"
                if not failure.exists():
                    durable.seal(failure, dict(error_type=type(exc).__name__, code=str(exc)[:180],
                        captured_rows=total, completed_pages=len(pages), failed_at=durable.now(),
                        trusted=False, automatic_retry=False))
                raise


def verify_capture(directory):
    """Offline recovery validates receipts, manifests and exact persisted bytes."""
    directory = Path(directory)
    result = durable.read_json(directory / "complete.json")
    intent = durable.read_json(directory / "intent.json")
    if result["plan_sha256"] != digest(intent["plan"]) or intent["plan_sha256"] != result["plan_sha256"]:
        raise ValueError("CAPTURE_PLAN_HASH_MISMATCH")
    total = 0
    for i, page in enumerate(result["pages"]):
        if durable.read_json(directory / f"checkpoint-{i:05d}.json") != page:
            raise ValueError("CAPTURE_CHECKPOINT_CONFLICT")
        manifest = durable.read_json(Path(page["manifest_path"]))
        unsigned = dict(manifest)
        unsigned.pop("manifest_hash", None)
        if digest(unsigned) != page["manifest_hash"] or manifest["manifest_hash"] != page["manifest_hash"]:
            raise ValueError("CAPTURE_MANIFEST_HASH_MISMATCH")
        if manifest["row_count"] != page["rows"] or file_hash(Path(page["path"])) != page["sha256"]:
            raise ValueError("CAPTURE_BYTES_CHANGED")
        total += page["rows"]
    if total != result["row_count"]:
        raise ValueError("CAPTURE_ROW_COUNT_MISMATCH")
    return result
