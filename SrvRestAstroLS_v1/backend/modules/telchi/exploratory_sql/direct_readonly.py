"""Explicit DEV pilot, NOT an OS sandbox or the historical F1 executor.

This class enables only the sealed synthetic fixture; foundation.py reuses its
execution loop for a separately scoped supervised DEV binding. The model never
chooses a path, connection, configuration, extension, permission or physical relation.
"""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import time

from .contracts import Column, Decision, ExploratoryQueryResult, SecurityDecision
from .executor import ResearchBudget
from .synthetic import CATALOG, ROWS
from .validator import authorize, canonical, context_digest, identifier, validate


LIMITATIONS = ("dev_pilot_not_multiuser_accreditation", "os_isolation_not_accredited",
               "process_memory_cpu_and_scan_bytes_not_enforced")
# One executing query per process; the runner also holds an interprocess lock.
_EXECUTION_LOCK = threading.Lock()


def connection_config(budget):
    return {"threads": str(budget.threads),
            "memory_limit": str(budget.process_memory_bytes // (1024 * 1024)) + "MB",
            "enable_external_access": "false", "autoload_known_extensions": "false",
            "autoinstall_known_extensions": "false", "max_temp_directory_size": "0B",
            "max_expression_depth": "64"}


class DirectReadonlyExecutor:
    """Revalidates each proposal; only regenerated SQL reaches a read-only DB.

    DuckDB memory_limit is an engine limit, NOT a process RSS limit. Deadline
    uses interrupt, not OS preemption. Fetching is bounded, not full fetchall.
    Construction writes ONLY our private synthetic DB, never Foundation.
    """
    def __init__(self, context):
        authorize(context)
        if context.catalog != CATALOG:
            raise ValueError("synthetic_context_required")
        self.context = context
        self.budget = ResearchBudget(context.effective_budget)
        self._execution_seconds = 0.0
        self._temp = tempfile.TemporaryDirectory(prefix="telchi-synthetic-readonly-")
        self._path = Path(self._temp.name) / "fixture.duckdb"
        self._closed = False
        try:
            import duckdb
            if len(canonical(ROWS).encode()) > context.effective_budget.source_bytes:
                raise ValueError("source_byte_budget")
            with duckdb.connect(str(self._path), config=connection_config(context.effective_budget)) as db:
                for table in CATALOG.tables:
                    columns = ", ".join(identifier(c.name) + " " + c.sql_type for c in table.columns)
                    db.execute(f"CREATE TABLE {identifier(table.name)} ({columns})")
                    if ROWS[table.name]:
                        marks = ",".join("?" for _ in table.columns)
                        db.executemany(f"INSERT INTO {identifier(table.name)} VALUES ({marks})", ROWS[table.name])
        except BaseException:
            self.close()
            raise

    def _open_connection(self, limits):
        import duckdb
        return duckdb.connect(str(self._path), read_only=True, config=connection_config(limits))

    def _prepare_connection(self, db, context):
        """Trusted composition hook; never receives model SQL."""

    def close(self):
        self._closed = True
        self._temp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def execute(self, proposal, context, *, cancel=None):
        decision, query = validate(proposal, context)
        result = ExploratoryQueryResult(
            query_id=query.query_id if query else "", declared_grain=proposal.expected_grain,
            publication=context.publication, snapshot=context.snapshot, limitations=LIMITATIONS)

        execution_started = None
        self.last_timing = {}
        def stop(kind, reason):
            return SecurityDecision(kind, reason, query.query_id if query else None), replace(
                result, limitations=LIMITATIONS + (reason,),
                elapsed_seconds=time.monotonic()-execution_started if execution_started is not None else 0.0)

        if query is None:
            return decision, result
        if self._closed or context_digest(context) != context_digest(self.context):
            return stop(Decision.DENY, "executor_context_mismatch")
        if cancel is not None and cancel.is_set():
            return stop(Decision.RESOURCE_BLOCKED, "cancelled_before_execution")
        if not _EXECUTION_LOCK.acquire(blocking=False):
            return stop(Decision.RESOURCE_BLOCKED, "dev_execution_busy")
        # Total SQL wall time excludes time the controller spends awaiting Luna.
        self.budget.started = time.monotonic() - self._execution_seconds
        if not self.budget.reserve():
            _EXECUTION_LOCK.release()
            return stop(Decision.RESOURCE_BLOCKED, "research_budget_exhausted")
        started = time.monotonic()
        execution_started = started
        sql_started = None
        finished, interrupted = threading.Event(), threading.Event()
        watcher = None
        try:
            remaining = self.budget.budget.total_seconds - (started - self.budget.started)
            deadline = started + min(query.limits.query_seconds, remaining)
            with self._open_connection(query.limits) as db:
                def supervise():
                    while not finished.wait(0.01):
                        if time.monotonic() >= deadline or (cancel is not None and cancel.is_set()):
                            interrupted.set()
                            db.interrupt()
                            # Continue interrupting until the executing thread acknowledges it.
                watcher = threading.Thread(target=supervise, name="telchi-readonly-deadline")
                watcher.start()
                try:
                    self._prepare_connection(db, context)
                    sql_started = time.monotonic()
                    cursor = db.execute(query.generated_sql, {p.name: p.value for p in query.parameters})
                    schema = tuple(Column(str(c[0]), str(c[1]), True) for c in cursor.description)
                    rows, used, truncated = [], len(canonical(schema).encode()), False
                    while True:
                        row = cursor.fetchone()
                        if row is None:
                            break
                        size = len(canonical(row).encode())
                        if len(rows) >= query.limits.result_rows or used + size > query.limits.result_bytes:
                            truncated = True
                            break
                        rows.append(row)
                        used += size
                    if interrupted.is_set() or time.monotonic() >= deadline:
                        return stop(Decision.RESOURCE_BLOCKED, "query_deadline_or_cancel")
                    return decision, replace(result, schema=schema, rows=tuple(rows),
                        returned_count=len(rows), total_count=None if truncated else len(rows),
                        truncated=truncated, elapsed_seconds=time.monotonic() - started,
                        source="synthetic" if context.catalog.synthetic_only else context.catalog.dataset,
                        evidence=(query.query_id, query.context_digest, "direct_readonly_dev"), status="COMPLETED")
                finally:
                    finished.set()
                    watcher.join()
        except Exception as exc:
            # Closed categories only: never relay exception text (SQL, paths,
            # values or credentials). Luna can reformulate a binder/type error
            # without learning anything beyond its authorized catalog.
            import duckdb
            category = ('sql_binding_error_check_catalog_types_and_grouping'
                        if isinstance(exc, duckdb.BinderException) else
                        'sql_conversion_error_check_operand_types'
                        if isinstance(exc, duckdb.ConversionException) else
                        'sql_arithmetic_error_check_zero_and_numeric_range'
                        if isinstance(exc, (duckdb.OutOfRangeException, duckdb.InvalidInputException)) else
                        'execution_rejected')
            return stop(Decision.RESOURCE_BLOCKED if interrupted.is_set() else Decision.INVALID_QUERY,
                        "query_deadline_or_cancel" if interrupted.is_set() else category)
        finally:
            finished.set()
            if watcher is not None:
                watcher.join()
            elapsed = time.monotonic() - started
            self.last_timing = dict(total_seconds=elapsed,
                setup_seconds=(sql_started or time.monotonic())-started,
                sql_seconds=time.monotonic()-sql_started if sql_started else 0.0)
            self._execution_seconds += elapsed
            self.budget.release()
            _EXECUTION_LOCK.release()


def foundation_gate():
    """No generic DuckDB escape hatch, implicit CURRENT or fabricated RBAC.

    This historical synthetic runner remains disconnected from real data.
    foundation.py adds a local supervised projection, not shared-service RBAC or
    enterprise egress attestation. Synthetic authority cannot be repurposed as
    Foundation authority. This static gate performs no data/metadata I/O.
    """
    return {"status": "BLOCKED", "reasons": [
        "enterprise_openai_destination_scope_not_accredited",
        "foundation_supervised_binding_real_validation_pending",
        "host_io_pressure_requires_new_preflight"],
        "foundation_opened": False, "business_data_sent_to_model": False}
