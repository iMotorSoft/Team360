"""Historical monetary contracts, parameter bounds, RBAC and no-commit fence."""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities, format_result
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
from modules.telchi.datalake.sales_query import (
    MONETARY_OPERATION as OP, MONETARY_PERMISSION as GRANT, PUBLICATION, parameters, validate_result,
)
from .test_assistant import MemoryStore, Interpreter, context, event, proposal, latest

OPTIONS = dict(date_from='2026-05-01', date_to_exclusive='2026-06-01', currency='BS')


def result(options):
    return dict(capability=OP+'.v1', period=options, currency='BS', grain='document_header',
        rows=[dict(invoice_count=2, unique_invoices=2, credit_count=1, unique_credits=1,
                   invoice_amount_count=2, credit_amount_count=1,
                   billed_amount='100.01', credit_amount='10.00', net_amount='90.01')],
        sql_parameters=parameters(OP, options), read_only=True, sap_accessed=False,
        source=dict(publication_id=PUBLICATION, snapshot_id=1408, updated_at='2026-09-28T18:18:35.264000'))


@pytest.mark.parametrize('change', [dict(currency='USD'), dict(currency='BS;DROP'),
    dict(date_from='2026-05-32'), dict(date_from='2026-06-01'), dict(date_to_exclusive='2028-06-01'),
    dict(date_from='20260501'), dict(entity_id='other'), dict(metric='cash'), dict(limit=10)])
def test_parameter_rejection(change):
    with pytest.raises((ValueError, TypeError)):
        parameters(OP, OPTIONS | change)


@pytest.mark.parametrize('change', ['net', 'count', 'duplicate', 'currency', 'period', 'publication', 'snapshot', 'sap', 'readonly', 'nan', 'updated_at'])
def test_result_rejection(change):
    r = result(OPTIONS)
    if change == 'net': r['rows'][0]['net_amount'] = '91.01'
    elif change == 'count': r['rows'][0]['invoice_count'] = True
    elif change == 'duplicate': r['rows'][0]['unique_invoices'] = 1
    elif change == 'currency': r['currency'] = 'USD'
    elif change == 'period': r['period'] = OPTIONS | dict(date_from='2026-04-01')
    elif change == 'publication': r['source']['publication_id'] = 'candidate'
    elif change == 'snapshot': r['source']['snapshot_id'] = 1409
    elif change == 'sap': r['sap_accessed'] = True
    elif change == 'readonly': r['read_only'] = False
    elif change == 'nan': r['rows'][0]['billed_amount'] = 'NaN'
    elif change == 'updated_at': r['source'].pop('updated_at')
    with pytest.raises(ValueError):
        validate_result(OP, OPTIONS, r)


@pytest.mark.parametrize('authorized,committed,tenant', [(True, True, 'telchi'), (False, True, 'telchi'),
                                                        (True, False, 'telchi'), (True, True, 'other')])
def test_handler_security_fences(authorized, committed, tenant):
    async def run():
        calls = []
        async def query(op, options, **kwargs):
            calls.append((op, options))
            return result(options)
        c = context()
        c = replace(c, channel=replace(c.channel, tenant_id=tenant),
            sender_identity=replace(c.sender_identity, tenant_id=tenant,
                permissions=frozenset({'fixture.business.read'} | ({GRANT} if authorized else set()))))
        store = MemoryStore()
        p = proposal({'/metric': 'sales.net_amount', '/period':
                      dict(start=OPTIONS['date_from'], end_exclusive=OPTIONS['date_to_exclusive'])}, intent='NEW_QUERY')
        handler = TelchiHandler(store=store, authorization=BusinessAuthorization(
            BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)),
            interpreter=Interpreter([p]), capabilities=SalesCapabilities(sales_query=query))
        if not committed:
            handler.engine = lambda *args: dict(committed=False, state_after=deepcopy(engine.EMPTY), output=p)
        response = await handler.handle(event('Ventas de mayo de 2026'), c)
        expected = authorized and committed and tenant == 'telchi'
        assert len(calls) == int(expected)
        if expected:
            assert response.classification == 'DIRECT_AVAILABLE'
            assert '90,01' in response.text and '100,01' in response.text
        if not committed and tenant == 'telchi':
            assert latest(store)['confirmed_state'] == engine.EMPTY
    asyncio.run(run())


@pytest.mark.parametrize('field,value,category', [('entity_mention', {'text': 'Calenta', 'type': None}, 'MAPPING_MISSING'),
                                                 ('branches', ['Sucursal'], 'MAPPING_MISSING'),
                                                 ('sales_channel', 'SALON', 'CHANNEL_NOT_ACCREDITED')])
def test_no_global_total_for_filtered_request(field, value, category):
    state = dict(deepcopy(engine.EMPTY | engine.INTENT_V2), metric='sales.net_amount',
        requested_metrics=['sales.net_amount'], period=dict(start='2026-05-01', end_exclusive='2026-06-01'))
    state[field] = value
    available = SalesCapabilities().availability(state)
    assert available.category == category
    assert not available.allowed


def test_both_keeps_money_and_quantity_limits_separate():
    r = result(OPTIONS)
    r['requested_metrics'] = ['sales.net_amount', 'sales.source_top_items']
    text = format_result(r)
    assert 'Conservo la solicitud de cantidades' in text
    assert 'conteo de documentos' in text


def test_comparison_does_not_ask_to_unlock_missing_operation():
    async def run():
        async def forbidden(*args, **kwargs):
            pytest.fail('unsupported comparison executed a query')
        p = proposal({'/metric': 'sales.net_amount', '/period':
            dict(start='2026-08-01', end_exclusive='2026-09-01')}, intent='COMPARE', action='ASK',
            clarification={'slot':'comparison','question':'¿Con qué período querés comparar agosto de 2026?'})
        store = MemoryStore()
        handler = TelchiHandler(store=store, authorization=BusinessAuthorization(
            BusinessPolicy('telchi','workspace','fixture.business.read',True,True)),
            interpreter=Interpreter([p]),capabilities=SalesCapabilities(sales_query=forbidden))
        response = await handler.handle(event('¿Cuál fue la diferencia?'),context())
        assert response.classification == 'DIRECT_UNAVAILABLE'
        assert 'diferencia de facturación' in response.text and '?' not in response.text
        assert latest(store)['capability_calls'] == 0
    asyncio.run(run())


def test_missing_rows_not_certified_zero_or_current():
    r = result(OPTIONS)
    r['rows'][0] = {key: ('0' if key.endswith('amount') else 0) for key in r['rows'][0]}
    text = format_result(r)
    assert 'No puedo acreditar una facturación de cero' in text
    assert '28 de septiembre de 2026' in text


def test_new_permission_is_distinct():
    from modules.telchi.datalake.sales_query import PERMISSIONS
    assert GRANT not in PERMISSIONS.values()
    assert SalesCapabilities().required_permission({'metric': 'sales.net_amount'}) == GRANT


@pytest.mark.parametrize('action', ['EXECUTE', 'ASK', 'DIRECT_UNAVAILABLE'])
def test_generic_ranking_uses_registered_window_not_luna_date(action):
    from modules.telchi.assistant.handler import fixed_ranking_request_contract
    p = proposal({'/metric': 'sales.source_top_items'}, intent='NEW_QUERY', action=action,
        clarification={'slot': 'period', 'question': '¿Qué mes?'} if action == 'ASK' else None)
    p['state_delta']['unset'] = ['/period']
    corrected = fixed_ranking_request_contract(p, '¿Cuáles son los productos más vendidos?')
    processed = engine.process(engine.EMPTY, corrected, {}, 'turn')
    assert processed['committed'] is True
    assert processed['state_after']['period'] == dict(start='2026-01-01', end_exclusive='2026-09-16')
    assert SalesCapabilities().availability(processed['state_after']).allowed
    # Explicit period questions are never rewritten.
    assert fixed_ranking_request_contract(p, '¿Cuáles son los productos más vendidos en mayo?') == p


@pytest.mark.parametrize('action', ['EXECUTE', 'DIRECT_UNAVAILABLE'])
def test_net_product_amount_never_executes_global_total(action):
    async def run():
        async def forbidden(*args, **kwargs):
            pytest.fail('product amount query reached Foundation')
        c = context()
        c = replace(c, channel=replace(c.channel, tenant_id='telchi'),
            sender_identity=replace(c.sender_identity, tenant_id='telchi',
                permissions=frozenset({'fixture.business.read', GRANT})))
        store = MemoryStore()
        p = proposal({'/metric': 'sales.net_amount', '/period':
                     dict(start='2026-05-01', end_exclusive='2026-06-01')}, intent='NEW_QUERY', action=action)
        handler = TelchiHandler(store=store, authorization=BusinessAuthorization(
            BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)),
            interpreter=Interpreter([p]), capabilities=SalesCapabilities(sales_query=forbidden))
        response = await handler.handle(event('Dame el importe neto por producto de mayo de 2026'), c)
        assert response.classification == 'DIRECT_UNAVAILABLE'
        assert latest(store)['capability_calls'] == 0
        assert latest(store)['bmd']['category'] == 'NET_PRODUCT_AMOUNT_UNRESOLVED'
    asyncio.run(run())
