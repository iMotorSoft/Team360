"""Supervised DEV-only Foundation binding. No provider or channel integration.

The operator authorization is the explicit local pilot assignment, NOT Console
RBAC, FULL_ACCESS or an authorization suitable for a shared service. The sealed
projection limits this pilot to the four reference SKUs in August 2026.
"""
from contextlib import contextmanager
import os
import time

from .contracts import (AuthorizedExecutionContext, Budget, CandidateRelation, Catalog,
                        Column, Decision, ExploratoryQueryResult, LogicalTable, SecurityDecision)
from .direct_readonly import DirectReadonlyExecutor, connection_config
from .executor import ResearchBudget
from .validator import authorize

PUBLICATION = "foundation_afd08d9eca6a725be53cdc3f9d5709c9"
SNAPSHOT = "1408"
PERMISSION = "telchi.exploratory.foundation.supervised_dev.read.v1"
SKUS = ("L02822", "L02823", "L03658", "L03649")
START, END = "2026-08-01", "2026-09-01"


def _table(name, columns, grain, limitations):
    return LogicalTable(name, tuple(Column(n, t, True) for n, t in columns),
                        PERMISSION, grain, 1000000, limitations)


CATALOG = Catalog(
    "telchi_foundation_supervised_dev_v1", "TELCHI", "foundation_supervised_dev",
    PUBLICATION, SNAPSHOT,
    (_table("sales_document", (
        ("doc_entry", "VARCHAR"), ("doc_num", "VARCHAR"), ("doc_date", "VARCHAR"),
        ("currency", "VARCHAR"), ("slp_code", "VARCHAR"), ("series", "VARCHAR"),
        ("sales_channel_code", "VARCHAR"), ("sales_channel_semantic_status", "VARCHAR"),
        ("raw_extraction_id", "VARCHAR"), ("source_as_of", "VARCHAR")), ("doc_entry",),
        ("SAP_B1_HANA/OINV, active August 2026 invoices only; header grain, no header money exposed.",
         "Only documents containing one of the four reference SKUs; classification is current, not historical.")),
     _table("sales_line", (
        ("doc_entry", "VARCHAR"), ("line_num", "VARCHAR"), ("item_code", "VARCHAR"),
        ("currency", "VARCHAR"), ("line_total", "DECIMAL(38,6)"),
        ("raw_extraction_id", "VARCHAR"), ("source_as_of", "VARCHAR")), ("doc_entry", "line_num"),
        ("Commercial line amount before credit memos and global header adjustments, not collections or net billing.",
         "Four explicit reference SKUs, not an accredited universal brand definition.",
         "Currency and lineage must be verified, not assumed from successful SQL.",
         "Conservative join-pair budget may reject joins; no automatic budget elevation."))),
    (CandidateRelation("sales_document", "doc_entry", "sales_line", "doc_entry"),),
    synthetic_only=False)


def local_context(investigation_id):
    """Trusted CLI composition only, under the owner's explicit DEV assignment."""
    return AuthorizedExecutionContext(
        identity=f"supervised-local-uid:{os.getuid()}", organization=CATALOG.organization,
        workspace=CATALOG.workspace, environment="dev", permissions=frozenset({PERMISSION}),
        catalog=CATALOG, sources=tuple(t.name for t in CATALOG.tables), publication=PUBLICATION,
        snapshot=SNAPSHOT, effective_budget=Budget(), investigation_id=investigation_id)


def host_read_preflight():
    """Small Linux observation; sustained I/O wait blocks real reads, not fixtures."""
    from pathlib import Path
    def ticks():
        return [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    waits = []
    first = ticks()
    for _ in range(3):
        time.sleep(0.25)
        last = ticks()
        delta = [b-a for a, b in zip(first, last)]
        waits.append(delta[4] / max(sum(delta), 1))
        first = last
    wait = sum(waits) / len(waits)
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0]) * 1024
    sustained_io_pressure = sum(w >= .25 for w in waits) >= 2
    return dict(safe=not sustained_io_pressure and available >= 1024**3,
                io_wait_fraction=wait, io_wait_samples=waits, available_bytes=available,
                load_average=os.getloadavg(), cpu_count=os.cpu_count())


class FoundationReadonlyExecutor(DirectReadonlyExecutor):
    """Same AST, budget, fetch, interrupt and execution lock as the direct pilot.

    Canonical reader owns physical namespaces and snapshot resolution. Only
    explicit temporary views in the private in-memory main DB are writable;
    the attached Foundation catalog MUST report read-only. External access is
    needed by the trusted DuckLake reader, not available in admitted model SQL.
    This is not an OS sandbox. No files are exported or Foundation objects written.
    """
    catalog = CATALOG

    def __init__(self, context, *, reader=None):
        authorize(context)
        if context.catalog != self.catalog:
            raise ValueError('foundation_context_required')
        self.context, self.reader = context, reader
        self.budget = ResearchBudget(context.effective_budget)
        self._execution_seconds, self._closed = 0.0, False
        self.last_preflight = None

    def close(self):
        self._closed = True

    def execute(self, proposal, context, *, cancel=None):
        # Denied SQL/context is rejected before any host wait, connection or metadata I/O.
        from .validator import context_digest, validate
        decision, query = validate(proposal, context)
        if query is None or context_digest(context) != context_digest(self.context) or self._closed:
            return super().execute(proposal, context, cancel=cancel)
        self.last_preflight = host_read_preflight()
        if not self.last_preflight['safe']:
            return SecurityDecision(Decision.RESOURCE_BLOCKED, 'host_io_or_memory_pressure'), ExploratoryQueryResult(
                query_id=query.query_id, source=CATALOG.dataset, publication=PUBLICATION, snapshot=SNAPSHOT,
                limitations=('BLOCKED_HOST',), status='NOT_EXECUTED')
        return super().execute(proposal, context, cancel=cancel)

    @contextmanager
    def _open_connection(self, limits):
        from ..datalake.foundation_reader import FoundationReader
        if self.reader is None:
            self.reader = FoundationReader()
        reader = self.reader
        # Attachment establishment is not OS-preemptible. No model SQL is run here.
        with reader.connector.session(read_only=True) as db:
            for name, value in connection_config(limits).items():
                if name == 'enable_external_access':
                    continue  # Trusted DuckLake metadata/file access requires it.
                db.execute(f"SET {name}='{value}'")
            yield db

    def _prepare_connection(self, db, context):
        from ..datalake.foundation_reader import FoundationReader
        reader = self.reader or FoundationReader()
        if db.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() != (True,):
            raise ValueError('foundation_not_readonly')
        access = reader.resolve_on(db)
        if (access.foundation_publication_id, str(access.ducklake_snapshot_id)) != (PUBLICATION, SNAPSHOT):
            raise ValueError('foundation_binding_changed')
        docs, lines = access.sales('sales_document'), access.sales('sales_line')
        # All SQL here is trusted composition. No paths, identifiers, filters or
        # expressions are selected by Luna. Views retain NULL/invalid amounts.
        codes = ','.join("'" + sku + "'" for sku in SKUS)
        window = f"d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND d.canceled='N' AND d.doc_date>='{START}' AND d.doc_date<'{END}'"
        line_scope = f"l.source_system='SAP_B1_HANA' AND l.source_table='INV1' AND l.item_code IN ({codes})"
        doc_projection = ','.join(f'CAST(d.{c.name} AS {c.sql_type}) AS {c.name}' for c in CATALOG.tables[0].columns)
        line_projection = ','.join(f'TRY_CAST(l.{c.name} AS {c.sql_type}) AS {c.name}' for c in CATALOG.tables[1].columns)
        db.execute(f"CREATE TEMP VIEW sales_document AS SELECT {doc_projection} FROM {docs} d WHERE {window} AND EXISTS (SELECT 1 FROM {lines} l WHERE {line_scope} AND l.doc_entry=d.doc_entry)")
        db.execute(f"CREATE TEMP VIEW sales_line AS SELECT {line_projection} FROM {lines} l WHERE {line_scope} AND EXISTS (SELECT 1 FROM {docs} d WHERE {window} AND d.doc_entry=l.doc_entry)")
        # Resolve all unqualified logical tables in the private main schema, never
        # a physical Atomic namespace or a caller-selected search path.
        db.execute("SET schema='main'")
