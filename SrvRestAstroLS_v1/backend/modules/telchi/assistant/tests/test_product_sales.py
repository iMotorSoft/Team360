"""Generic product search, trusted-ID context, partial metrics and execution fence."""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
from modules.telchi.datalake.product_sales_query import PERMISSIONS, parameters, normalize
from modules.telchi.datalake.sales_query import PUBLICATION
from .test_assistant import MemoryStore, Interpreter, context, event, proposal, latest


def search(text='Producto', *, truncated=False):
    return dict(capability='products.search.v1', parameters={'text': text, 'limit': 20},
        rows=[dict(item_code='X01', namespace='SAP_HANA', description='Producto 250 g',
                   match_rank=1, catalog_sales_uom_id=None, status='ACTIVE', sell_item='Y')],
        source=dict(publication_id=PUBLICATION, snapshot_id=1408), truncated=truncated,
        read_only=True, sap_accessed=False)


def request(text='Producto'):
    return proposal({'/schema_version': 2, '/requested_metrics': ['sales.by_products'],
        '/entity_mention': None, '/temporal_reference': None,
        '/metric': 'sales.by_products', '/product_search_text': text}, intent='NEW_QUERY')


@pytest.mark.parametrize('options', [{'text': ''}, {'text': 'x'*121}, {'text': 'x', 'limit': True},
    {'text': 'x', 'limit': 21}, {'text': 'x', 'sql': 'SELECT 1'}, {'text': '\nabc'}])
def test_search_bounds(options):
    with pytest.raises(ValueError):
        parameters('products.search', options)


def test_normalization_and_literal_sql_values():
    assert normalize('  PÓMADA   CalenTA ') == 'pomada calenta'
    assert parameters('products.search', {'text': "x%' OR 1=1 --"})[0] == "x%' or 1=1 --"


@pytest.mark.parametrize('options', [dict(item_codes=[], namespace='SAP_HANA'),
    dict(item_codes=['X']*21, namespace='SAP_HANA'), dict(item_codes=['X'], namespace='LEGACY_DS'),
    dict(item_codes=['X'], namespace='SAP_HANA', date_from='2026-05-01'),
    dict(item_codes=['X'], namespace='SAP_HANA', metric='net_amount')])
def test_sales_bounds(options):
    with pytest.raises(ValueError):
        parameters('sales.by_products', options)


def test_cannot_patch_trusted_context_or_invent_id():
    before = deepcopy(engine.EMPTY | engine.INTENT_V2 | engine.PRODUCT_FIELDS)
    for delta in ({'/product_context': search()}, {'/selected_item_codes': ['X01']}):
        p = request()
        p['state_delta']['set'].update(delta)
        assert engine.process(before, p, {}, 'turn')['committed'] is False
    state = dict(before, product_search_text='Producto', product_context=search())
    accepted = engine.patch(state, {'set': {'/selected_item_codes': ['X01']}, 'unset': []})
    assert accepted['selected_item_codes'] == ['X01']
    refined = engine.patch(state, {'set': {'/product_search_text': 'Producto 250 g',
        '/selected_item_codes': ['X01']}, 'unset': []})
    assert refined['product_context'] == state['product_context']
    with pytest.raises(ValueError):
        engine.patch(state, {'set': {'/selected_item_codes': ['MADE-UP']}, 'unset': []})


@pytest.mark.parametrize('authorized,committed', [(True, True), (False, True), (True, False)])
def test_real_handler_chain_and_security(authorized, committed):
    async def run():
        calls = []
        async def query(op, options, **kwargs):
            calls.append((op, options))
            if op == 'products.search': return search()
            return dict(capability=op+'.v1', parameters=options, rows=[dict(item_code='X01',
                description='Producto 250 g', source_system='SAP_B1_HANA', document_type='OINV',
                doc_date='2026-09-23T00:00:00', doc_entry='12', line_num='0', quantity='2')],
                source=dict(publication_id=PUBLICATION, snapshot_id=1408), truncated=False,
                read_only=True, sap_accessed=False)
        c = context()
        c = replace(c, channel=replace(c.channel, tenant_id='telchi'),
            sender_identity=replace(c.sender_identity, tenant_id='telchi',
                permissions=frozenset({'fixture.business.read'} | (set(PERMISSIONS.values()) if authorized else set()))))
        store = MemoryStore()
        handler = TelchiHandler(store=store, interpreter=Interpreter([request()]),
            authorization=BusinessAuthorization(BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)),
            capabilities=SalesCapabilities(product_query=query))
        if not committed:
            handler.engine = lambda *a: dict(committed=False, state_after=deepcopy(engine.EMPTY), output=request())
        r = await handler.handle(event('Últimas ventas de Producto'), c)
        assert len(calls) == (2 if authorized and committed else 0)
        if calls:
            assert calls[1][1]['item_codes'] == ['X01']
            assert 'text' not in calls[1][1]
            assert r.classification == 'DIRECT_AVAILABLE'
            assert 'No reparto DocTotal' in r.text
            assert latest(store)['confirmed_state']['selected_item_codes'] == ['X01']
    asyncio.run(run())


def test_product_context_can_never_unlock_a_global_total():
    state = dict(deepcopy(engine.EMPTY | engine.INTENT_V2 | engine.PRODUCT_FIELDS),
        metric='sales.net_amount', requested_metrics=['sales.net_amount'],
        product_search_text='Producto', product_context=search(), selected_item_codes=['X01'],
        period=dict(start='2026-05-01', end_exclusive='2026-06-01'))
    assert SalesCapabilities().availability(state).category == 'MAPPING_MISSING'
    state.update(metric='sales.latest_documents', requested_metrics=['sales.latest_documents'], period=None)
    assert SalesCapabilities().availability(state).category == 'MAPPING_MISSING'


def test_context_roundtrip_and_period_does_not_search_again():
    async def run():
        state = dict(deepcopy(engine.EMPTY | engine.INTENT_V2 | engine.PRODUCT_FIELDS),
            metric='sales.by_products', requested_metrics=['sales.by_products'],
            product_search_text='Producto', product_context=search(), selected_item_codes=['X01'],
            period=dict(start='2026-05-01', end_exclusive='2026-06-01'))
        import json
        state = json.loads(json.dumps(state))
        engine.validate(state)
        calls = []
        async def query(op, options, **kw):
            calls.append(op)
            return dict(capability=op+'.v1', parameters=options, rows=[], truncated=False,
                read_only=True, sap_accessed=False, source=dict(publication_id=PUBLICATION, snapshot_id=1408))
        await SalesCapabilities(product_query=query).execute(state)
        assert calls == ['sales.by_products']
    asyncio.run(run())


def test_explicit_code_target_is_resolved_through_catalog_before_sales():
    async def run():
        state = dict(deepcopy(engine.EMPTY | engine.INTENT_V2 | engine.PRODUCT_FIELDS),
            metric='sales.by_products', requested_metrics=['sales.by_products'],
            product_target='X01', period=dict(start='2026-05-01', end_exclusive='2026-06-01'))
        engine.validate(state)
        capabilities = SalesCapabilities()
        assert capabilities.availability(state).allowed
        calls = []
        async def query(op, options, **kw):
            calls.append((op, options))
            if op == 'products.search':
                return search(options['text'])
            return dict(capability=op+'.v1', parameters=options, rows=[dict(item_code='X01',
                description='Producto 250 g', source_system='SAP_B1_HANA', document_type='OINV',
                doc_date='2026-05-23T00:00:00', doc_entry='12', line_num='0', quantity='2')],
                product_summary=[dict(item_code='X01', line_count=1,
                    first_date='2026-05-23T00:00:00', last_date='2026-05-23T00:00:00')],
                source=dict(publication_id=PUBLICATION, snapshot_id=1408), truncated=False,
                grain='invoice_line', limitations='fixture',
                read_only=True, sap_accessed=False)
        capabilities.product_query = query
        result = await capabilities.execute(state)
        assert [op for op, _ in calls] == ['products.search', 'sales.by_products']
        assert calls[0][1]['text'] == 'X01'
        assert calls[1][1]['item_codes'] == ['X01']
        assert result['product_summary'][0]['item_code'] == 'X01'
    asyncio.run(run())
