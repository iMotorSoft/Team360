"""Direct terminal contracts with tiny isolated real DuckDB fixtures, no services."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
import threading

import duckdb
import pytest

from . import adaptive_research as runner
from .ask import Session, SYSTEM, terminal
from .ask_sources import CATALOG, AskExecutor, context_for_run
from .ask_verifier import AskRegistry
from .claim_evidence import EvidenceRegistry
from .contracts import Column, Decision, ExploratoryQueryResult
from .foundation_dev import proposal
from .test_claim_evidence import claim_for
from .test_foundation import reader
from .validator import validate


@pytest.fixture
def executor_factory(reader, tmp_path, monkeypatch):
    with reader.connector.session(read_only=True) as db:
        path = db.execute("SELECT path FROM duckdb_databases() WHERE database_name='telchi'").fetchone()[0]
    with duckdb.connect(path) as db:
        db.execute("ALTER TABLE docs ADD COLUMN user_sign VARCHAR DEFAULT '1'")
        db.execute("ALTER TABLE lines ADD COLUMN whs_code VARCHAR DEFAULT 'W'")
        for dataset, sql in (
            ('products', "SELECT 'SAP_HANA' AS source_system,'OTHER_SKU' AS item_code,'Vitamin C' AS sap_item_name,NULL::VARCHAR AS product_name,NULL::VARCHAR AS canonical_name,'unit' AS inventory_uom_id"),
            ('salespersons', "SELECT 'SAP_HANA' AS source_system,'7' AS source_native_id,'Test' AS name,'X' AS salesperson_category_code,'Example' AS salesperson_category_name")):
            target = tmp_path / (dataset+'.parquet')
            db.execute(f"COPY ({sql}) TO '{target}' (FORMAT PARQUET)")
    reader.access.reference = lambda name: tmp_path / (name+'.parquet')
    monkeypatch.setattr('modules.telchi.exploratory_sql.foundation_dev.host_read_preflight', lambda: {'safe': True})
    class FixtureExecutor(AskExecutor):
        def __init__(self, context, *, authorized):
            super().__init__(context, authorized=authorized)
            self.reader = reader
    return FixtureExecutor


def observe(factory, sql, source='sales_operation'):
    ctx = context_for_run()
    p = proposal(sql, source)
    _, query = validate(p, ctx)
    with factory(ctx, authorized=True) as executor:
        decision, result = executor.execute(p, ctx)
    assert result.status == 'COMPLETED', (decision, result)
    return ctx, query, result


def test_open_projection_not_calenta_or_august(executor_factory):
    ctx, q, r = observe(executor_factory, 'SELECT sum(line_total) AS money FROM sales_operation')
    assert r.rows == ((Decimal('1111.340000'),),)  # Includes July and OTHER_SKU, excludes other tenant.
    assert ctx.catalog == CATALOG


def test_document_calendar_day_includes_timestamp_month_end(executor_factory):
    ctx = context_for_run()
    with executor_factory(ctx, authorized=True) as executor:
        with executor.reader.connector.session(read_only=True) as db:
            path = db.execute("SELECT path FROM duckdb_databases() WHERE database_name='telchi'").fetchone()[0]
        with duckdb.connect(path) as db:
            db.execute("UPDATE docs SET doc_date='2026-08-31T00:00:00' WHERE doc_entry='2'")
    for upper in ("doc_date<='2026-08-31'", "doc_date<'2026-09-01'"):
        _, _, result = observe(executor_factory, "SELECT sum(line_total) AS money FROM sales_operation WHERE doc_date>='2026-08-01' AND "+upper)
        assert result.rows == ((Decimal('1111.340000'),),)


def test_model_cancellation_closes_own_task(monkeypatch):
    from .ask import CancellableLuna
    from .research import LunaSQL
    cancel = threading.Event()
    closed = []
    async def slow(*_, **__):
        try:
            await asyncio.sleep(30)
        finally:
            closed.append(True)
    monkeypatch.setattr(LunaSQL, 'next', slow)
    async def exercise():
        loop = asyncio.get_running_loop()
        loop.call_later(.02, cancel.set)
        with pytest.raises(RuntimeError, match='cancelled_by_user'):
            await CancellableLuna(cancel).next({})
    asyncio.run(exercise())
    assert closed == [True]


def test_independent_arithmetic_binding_and_wrong_value(executor_factory):
    ctx, q, r = observe(executor_factory, "SELECT sum(line_total) AS amount FROM sales_operation WHERE item_code='OTHER_SKU'")
    registry = AskRegistry(ctx, executor_factory=executor_factory)
    try:
        m = registry.register(q, r, r.rows)
        assert registry.verify(claim_for(m, value='999'))['match'], registry.audit
        assert not registry.verify(claim_for(m, value='1998'))['match']
        assert registry.audit[0]['result']['rows']  # Raw controls retained, not sent to Luna.
    finally:
        registry.close()


@pytest.mark.parametrize('sql', [
    'WITH x AS (SELECT sum(line_total) AS money FROM sales_operation) SELECT money AS amount FROM x',
    'SELECT sum(x.line_total) AS money FROM (SELECT line_total AS line_total FROM sales_operation) x',
    'SELECT sum(line_total+line_total) AS money FROM sales_operation',
    'SELECT count(DISTINCT item_code) AS products FROM sales_operation',
])
def test_unsupported_semantics_never_verified(executor_factory, sql):
    ctx, q, r = observe(executor_factory, sql)
    registry = AskRegistry(ctx, executor_factory=executor_factory)
    try:
        m = registry.register(q, r, r.rows)
        check = registry.verify(claim_for(m, value=str(r.rows[0][0])))
        assert not check['match'] and check['state'] == 'UNVERIFIED'
    finally:
        registry.close()


def test_reference_more_than_model_in_limit_is_bound_as_data(executor_factory):
    ctx, q, result = observe(executor_factory, 'SELECT sum(line_total) AS money FROM sales_operation')
    registry = AskRegistry(ctx, executor_factory=executor_factory)
    try:
        keys = {'1', '2'} | {str(i) for i in range(100, 170)}
        registry.controls.reference_item_codes = {'L02822', 'OTHER_SKU'}
        rows = registry._raw_reference('sales_document', keys, 'test-reference')
        assert {r['doc_entry'] for r in rows} == {'1', '2'}
        assert registry.audit[-1]['reference_scope_digest']
        assert ' IN (' not in registry.audit[-1]['proposal']['sql']
    finally:
        registry.close()


@pytest.mark.parametrize('mutation,reason', [
    ('provenance', 'raw_header_line_currency_or_provenance_mismatch'),
    ('duplicate', 'raw_documentary_duplicate_or_null_key'),
])
def test_independent_reference_never_accredits_broken_lineage(executor_factory, mutation, reason):
    ctx, q, result = observe(executor_factory, 'SELECT sum(line_total) AS money FROM sales_operation')
    registry = AskRegistry(ctx, executor_factory=executor_factory)
    original = registry._raw_reference
    def changed(source, keys, result_id):
        rows = original(source, keys, result_id)
        if source == 'sales_line':
            if mutation == 'provenance':
                rows[0]['raw_extraction_id'] = 'different'
            else:
                raise ValueError(reason)
        return rows
    registry._raw_reference = changed
    try:
        m = registry.register(q, result, result.rows)
        assert not registry.verify(claim_for(m, value='1111.34'))['match']
        assert registry.audit[-1]['reason'] == reason
    finally:
        registry.close()


def test_filtered_groups_derived_classification(executor_factory):
    ctx, q, r = observe(executor_factory, "SELECT COALESCE(sales_channel_code,'UNKNOWN') AS channel,sum(line_total) AS money FROM sales_operation WHERE doc_date>='2026-08-01' GROUP BY COALESCE(sales_channel_code,'UNKNOWN')")
    registry = AskRegistry(ctx, executor_factory=executor_factory)
    try:
        m = registry.register(q, r, r.rows)
        assert registry.verify(claim_for(m, 1, value='1011.34'))['match'], registry.audit
        assert not registry.verify(claim_for(m, 1, value='1011.34', classification='official'))['match']
    finally:
        registry.close()


def test_source_discovery_and_cancellation(executor_factory):
    _, _, result = observe(executor_factory, "SELECT item_code AS code,item_name AS name FROM product WHERE contains(lower(item_name),'vitamin')", 'product')
    assert result.rows == (('OTHER_SKU', 'Vitamin C'),)
    ctx = context_for_run()
    cancel = threading.Event()
    cancel.set()
    with executor_factory(ctx, authorized=True) as executor:
        d, result = executor.execute(proposal('SELECT count(*) AS n FROM sales_operation', 'sales_operation'), ctx, cancel=cancel)
        assert result.status == 'NOT_EXECUTED' and d.decision == Decision.RESOURCE_BLOCKED


@pytest.mark.parametrize('change', [dict(environment='production'), dict(identity='untrusted'),
    dict(snapshot='latest'), dict(organization='OTHER'), dict(permissions=frozenset())])
def test_security_authority_stays_server_owned(change):
    ctx = replace(context_for_run(), **change)
    decision, q = validate(proposal('SELECT count(*) AS n FROM sales_operation', 'sales_operation'), ctx)
    assert decision.decision == Decision.DENY and q is None


def test_clarification_and_conversation_continuity(monkeypatch, executor_factory):
    class Probe:
        calls = []
        async def next(self, *_args, **_kwargs):
            return {'ready': True}
    monkeypatch.setattr(runner, 'LunaSQL', lambda **_: Probe())
    monkeypatch.setattr('modules.telchi.exploratory_sql.ask.host_read_preflight', lambda: {'safe': True})
    payloads = []
    class Model:
        calls = []
        async def next(self, payload, **_):
            payloads.append(payload)
            return dict(action='clarify', question='¿Qué período y qué productos querés incluir?')
    session = Session(progress=lambda _: None)
    for question in ('¿Cuánto vendimos?', 'Agosto 2026, vitamina C sola, no combinaciones.'):
        report = asyncio.run(session.ask(question, lambda _: None, luna=Model(), executor_factory=executor_factory,
            registry_factory=lambda ctx: AskRegistry(ctx, executor_factory=executor_factory)))
        assert report['status'] == 'NEEDS_CLARIFICATION'
    assert payloads[1]['conversation'][0]['content'] == '¿Cuánto vendimos?'
    assert 'período' in payloads[1]['conversation'][1]['content']
    assert payloads[1]['question'].startswith('Agosto')
    assert 'Only four reference SKUs' not in SYSTEM
    assert '\x1b' not in terminal('\x1b[31munsafe')
