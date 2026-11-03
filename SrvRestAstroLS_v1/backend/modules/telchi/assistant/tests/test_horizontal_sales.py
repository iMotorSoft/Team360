"""Horizontal sales uses the existing monetary family, never a global substitute."""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant.capabilities import SalesCapabilities, format_result
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
from modules.telchi.assistant import state_engine as engine
from modules.telchi.datalake.sales_query import SQL, parameters, validate_result
from .test_assistant import MemoryStore, Interpreter, context, event, proposal, latest
from .test_sales_monetary import result, OP, GRANT

OPTIONS = dict(date_from='2026-08-01', date_to_exclusive='2026-09-01', currency='BS', sales_channel='HORIZONTAL')
QUESTIONS = [
    '¿Cuál fue la venta por canal horizontal de agosto?',
    '¿Cuánto vendió DMS en agosto de 2026?',
    '¿Cuáles fueron las ventas horizontales de agosto?',
    '¿Cuánto vendimos por la calle en agosto?',
]


def channel_result(options):
    # Synthetic amounts; the live reference is independently recorded, not embedded here.
    return result(options) | dict(sales_channel='HORIZONTAL', channel_semantic_status='CONFIRMED',
        channel_basis='materialized DMS series', channel_limitations='Completeness not certified')


def state():
    return dict(deepcopy(engine.EMPTY | engine.INTENT_V2), requested_metrics=['sales.net_amount'], metric='sales.net_amount',
        period=dict(start='2026-08-01', end_exclusive='2026-09-01'), sales_channel='HORIZONTAL')


@pytest.mark.parametrize('question', QUESTIONS)
def test_handler_resolved_concept_no_generic_fallback(question):
    """Fixture interpreter tests downstream routing; real comprehension is a separate live gate."""
    async def run():
        calls = []
        async def query(op, options, **kwargs):
            calls.append((op, options))
            return channel_result(options)
        c = context()
        c = replace(c, sender_identity=replace(c.sender_identity,
            permissions=frozenset({'fixture.business.read', GRANT})))
        p = proposal({'/metric': 'sales.net_amount', '/period': state()['period'],
                      '/sales_channel': 'HORIZONTAL'}, intent='NEW_QUERY')
        store = MemoryStore()
        handler = TelchiHandler(store=store, authorization=BusinessAuthorization(
            BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)),
            interpreter=Interpreter([p]), capabilities=SalesCapabilities(sales_query=query))
        response = await handler.handle(event(question), c)
        assert calls == [(OP, OPTIONS)]
        assert response.classification == 'DIRECT_AVAILABLE'
        assert '90,01' in response.text and '10,00' in response.text
        assert 'horizontal / DMS' in response.text and 'agosto de 2026' in response.text
        assert 'No son cobros' in response.text and 'créditos entre canales' in response.text
        assert 'Decime qué información necesitás' not in response.text
        assert 'Todavía no puedo consultar' not in response.text
        assert latest(store)['capability_calls'] == 1
    asyncio.run(run())


@pytest.mark.parametrize('extra', [dict(branches=['Saavedra']), dict(sales_channel='SALON'),
    dict(entity_mention={'text':'cliente', 'type':None}, schema_version=2, requested_metrics=['sales.net_amount']),
    dict(comparison={'start':'2026-07-01','end_exclusive':'2026-08-01'})])
def test_no_scope_widening(extra):
    assert not SalesCapabilities().availability(state() | extra).allowed


@pytest.mark.parametrize('value', ['DMS', 'SALON', None, 'HORIZONTAL OR 1=1'])
def test_only_closed_canonical_channel(value):
    with pytest.raises(ValueError):
        parameters(OP, OPTIONS | dict(sales_channel=value))


@pytest.mark.parametrize('field,value', [('sales_channel',None), ('channel_semantic_status','SUPPORTED'),
    ('channel_basis',''), ('channel_limitations','')])
def test_global_or_unconfirmed_result_rejected(field, value):
    r = channel_result(OPTIONS)
    r[field] = value
    with pytest.raises(ValueError):
        validate_result(OP, OPTIONS, r)


def test_sql_filters_both_invoices_and_credits_without_join_fanout():
    import duckdb
    c = duckdb.connect()
    try:
        c.execute('SET threads=2')
        c.execute('CREATE TABLE invoices(source_system VARCHAR,canceled VARCHAR,currency VARCHAR,doc_date VARCHAR,doc_entry VARCHAR,doc_total VARCHAR,sales_channel_code VARCHAR)')
        c.execute('CREATE TABLE credits AS SELECT * FROM invoices WHERE false')
        for table in ('invoices','credits'):
            c.executemany(f'INSERT INTO {table} VALUES (?,?,?,?,?,?,?)', [
                ('SAP_B1_HANA','N','BS','2026-08-01','1','100','HORIZONTAL'),
                ('SAP_B1_HANA','N','BS','2026-08-02','2','9000','SALON'),
                ('SAP_B1_HANA','Y','BS','2026-08-01','3','7000','HORIZONTAL'),
                ('SAP_B1_HANA','N','USD','2026-08-01','4','8000','HORIZONTAL'),
                ('SAP_B1_HANA','N','BS','2026-09-01','5','6000','HORIZONTAL')])
        sql = SQL[OP].format(documents='invoices',credits='credits',channel_filter='AND sales_channel_code=?')
        cur = c.execute(sql, parameters(OP, OPTIONS))
        row = dict(zip([x[0] for x in cur.description],cur.fetchone()))
        assert row['invoice_count'] == row['credit_count'] == 1
        assert row['billed_amount'] == row['credit_amount'] == 100
        assert row['net_amount'] == 0
    finally:
        c.close()


@pytest.mark.parametrize('authorized', [True, False])
def test_horizontal_permission_and_dialogue_continuity(authorized):
    async def run():
        calls = []
        async def query(op, options, **kwargs):
            calls.append(options)
            return channel_result(options)
        c = context()
        c = replace(c, sender_identity=replace(c.sender_identity,
            permissions=frozenset({'fixture.business.read'} | ({GRANT} if authorized else set()))))
        store = MemoryStore()
        plans = [proposal({'/metric':'sales.net_amount','/period':state()['period'],
                           '/sales_channel':'HORIZONTAL'}, intent='NEW_QUERY'),
                 proposal({'/period':dict(start='2026-07-01',end_exclusive='2026-08-01')})]
        handler = TelchiHandler(store=store, authorization=BusinessAuthorization(
            BusinessPolicy('telchi','workspace','fixture.business.read',True,True)),
            interpreter=Interpreter(plans),capabilities=SalesCapabilities(sales_query=query))
        await handler.handle(event(QUESTIONS[0]),c)
        if authorized:
            follow = await handler.handle(event('¿Y en julio?'),replace(c,correlation_id='follow'))
            assert len(calls)==2 and all(o['sales_channel']=='HORIZONTAL' for o in calls)
            assert calls[-1]['date_from']=='2026-07-01'
            assert 'horizontal / DMS' in follow.text and 'julio de 2026' in follow.text
        else:
            assert not calls
            assert latest(store)['capability_calls']==0
    asyncio.run(run())


@pytest.mark.parametrize('status', [None, 'SUPPORTED', 'CONFIRMED'])
def test_worker_rejects_unconfirmed_channel_before_aggregation(monkeypatch, status):
    import duckdb
    from contextlib import contextmanager
    from types import SimpleNamespace
    from modules.telchi.datalake.sales_query import execute_query, PUBLICATION, SNAPSHOT
    from modules.telchi.datalake.messaging_sales_query import TelchiQueryError
    c = duckdb.connect()
    c.execute('SET threads=2')
    c.execute('CREATE TABLE invoices(source_system VARCHAR,canceled VARCHAR,currency VARCHAR,doc_date VARCHAR,doc_entry VARCHAR,doc_total VARCHAR,sales_channel_code VARCHAR,sales_channel_semantic_status VARCHAR)')
    c.execute('CREATE TABLE credits AS SELECT * FROM invoices WHERE false')
    c.execute('INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?)',
        ['SAP_B1_HANA','N','BS','2026-08-10','1','100','HORIZONTAL',status])
    class Connection:
        def execute(self, sql, args=None):
            if sql.startswith('SELECT readonly FROM'):
                return SimpleNamespace(fetchone=lambda:(True,))
            return c.execute(sql, args) if args is not None else c.execute(sql)
    class Connector:
        @contextmanager
        def session(self, *, read_only):
            assert read_only is True
            yield Connection()
    access = SimpleNamespace(foundation_publication_id=PUBLICATION,ducklake_snapshot_id=SNAPSHOT,
        foundation_data_as_of='2026-09-28T18:18:35.264000',sales=lambda _: 'invoices',credit_memo=lambda _: 'credits')
    monkeypatch.setattr('modules.telchi.datalake.foundation_reader.FoundationReader.resolve_on',lambda *args:access)
    # This fixture isolates channel semantics; canonical ancestry is exercised
    # with a real isolated catalog in test_sales_succession, not this SQL stub.
    monkeypatch.setattr('modules.telchi.datalake.sales_succession.admit', lambda *args, **kwargs: None)
    try:
        if status!='CONFIRMED':
            with pytest.raises(TelchiQueryError):
                execute_query(OP, OPTIONS, Connector())
        else:
            r=execute_query(OP, OPTIONS, Connector())
            assert validate_result(OP, OPTIONS, r)['rows'][0]['net_amount']=='100.000000'
    finally:
        c.close()


def test_empty_result_preserves_channel_without_certifying_zero():
    r = channel_result(OPTIONS)
    r['rows'][0] = {k: ('0' if k.endswith('amount') else 0) for k in r['rows'][0]}
    text = format_result(r)
    assert 'horizontal / DMS' in text and 'No puedo acreditar una facturación de cero' in text
