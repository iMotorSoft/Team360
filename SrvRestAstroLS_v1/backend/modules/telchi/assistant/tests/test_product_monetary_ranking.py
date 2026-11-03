"""Persisted incident regression and fixed operation discriminant; no model substitutes."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities, format_result
from modules.telchi.assistant.handler import unavailable_response
from modules.telchi.assistant import business_categories, result_references
from modules.telchi.datalake.product_line_amount_ranking_query import METRIC, PERMISSION, PLAN, RankingError
from .test_sales_business_contract import setup
from .test_assistant import event, latest

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/product_monetary_ranking_incident.json').read_text())


def proposal(sets, action='EXECUTE'):
    return dict(intent='REFINE', action=action, state_delta={'set': sets, 'unset': []}, clarification=None)


def ranked():
    p = proposal({'/metric': METRIC, '/requested_metrics': [METRIC], '/limit': 5})
    out = engine.process(FIXTURE['previous_state'], p, {}, 'b')
    assert out['committed']
    return out['state_after']


def test_audited_proposal_not_silently_repaired_into_ranking():
    out = engine.process(FIXTURE['previous_state'], FIXTURE['proposal'], {}, 'replay')
    assert out['committed'] and out['state_after']['metric'] == 'sales.net_amount'
    assert not SalesCapabilities().availability(out['state_after']).allowed
    text = unavailable_response(out['state_after'], SalesCapabilities().availability(out['state_after']))
    assert 'Todavía no tengo disponible el importe' not in text


def test_explicit_operation_not_inferred_from_limit():
    state = ranked()
    caps = SalesCapabilities()
    assert caps.availability(state).allowed and caps.required_permission(state) == PERMISSION
    assert caps.required_permission(FIXTURE['previous_state']) != PERMISSION
    assert caps.availability(dict(state, limit=10)).allowed
    assert not caps.availability(dict(FIXTURE['previous_state'], limit=5)).allowed
    plan = business_categories.interpreter_context()['monetary_ranking']
    assert all(plan[k] == PLAN[k] for k in ('operation', 'group_by', 'measure', 'order_by'))


def test_b_c_d_preserve_only_pertinent_context():
    b = ranked()
    c = engine.process(b, proposal({'/limit': 10}), {}, 'c')['state_after']
    d = engine.process(c, proposal({'/entity_mention': {'text': 'RAW_MATERIAL', 'type': None}}), {}, 'd')['state_after']
    assert c == dict(b, limit=10)
    assert d == dict(c, entity_mention={'text': 'RAW_MATERIAL', 'type': None})
    assert SalesCapabilities().availability(d).allowed


@pytest.mark.parametrize('changes', [dict(entity_mention=None), dict(entity_mention={'text': 'UNKNOWN', 'type': None}),
    dict(branches=['x']), dict(sales_channel='SALON'), dict(product_search_text='legitimate product'),
    dict(requested_metrics=[METRIC, 'sales.source_top_items'])])
def test_incompatible_context_not_discarded(changes):
    state = dict(ranked(), **changes)
    assert not SalesCapabilities().availability(state).allowed


def test_new_independent_query_does_not_keep_ranking():
    p = proposal({'/metric': 'sales.coverage', '/requested_metrics': ['sales.coverage'], '/schema_version': 2})
    p['intent'] = 'NEW_QUERY'
    out = engine.process(ranked(), p, {}, 'new')
    assert out['committed'] and out['state_after']['entity_mention'] is None
    assert out['state_after']['period'] is None and 'limit' not in out['state_after']


def test_unavailable_formatter_names_requested_operation():
    state = ranked()
    text = unavailable_response(state, SalesCapabilities().availability(dict(state, branches=['x'])))
    assert 'ranking' in text and 'importe acumulado' in text
    assert 'importe de ventas calculado' not in text and 'Foundation' not in text
    no_period = dict(state, period=None)
    assert 'período concreto' in unavailable_response(no_period, SalesCapabilities().availability(no_period))


def test_unit_price_unavailable_does_not_turn_into_tax_explanation():
    async def run():
        p = proposal({'/schema_version': 2, '/metric': None, '/requested_metrics': [],
            '/entity_mention': {'text': 'RAW_MATERIAL', 'type': None}}, action='DIRECT_UNAVAILABLE')
        p['intent'] = 'EXPLAIN'  # Real Luna R2 output exposed this overly broad formatter branch.
        handler, store, calls, context = setup([p])
        response = await handler.handle(event('Quiero mayor precio unitario, no importe acumulado'), context)
        assert response.classification == 'DIRECT_UNAVAILABLE' and not calls
        assert latest(store)['capability_calls'] == 0 and 'total de cabecera' not in response.text
    asyncio.run(run())


def test_failed_reconciliation_audited_without_commercial_values():
    async def run():
        p = proposal({'/schema_version': 2, '/metric': METRIC, '/requested_metrics': [METRIC],
            '/period': FIXTURE['previous_state']['period'], '/entity_mention': {'text': 'LAB_FINISHED_PRODUCT', 'type': None}, '/limit': 5})
        handler, store, calls, context = setup([p])
        async def blocked(*args, **kwargs):
            raise RankingError('ranking_reconciliation_failed', {'difference': '123.45'})
        handler.capabilities = SalesCapabilities(ranking_query=blocked)
        context = replace(context, sender_identity=replace(context.sender_identity,
            permissions=context.sender_identity.permissions | {PERMISSION}))
        response = await handler.handle(event('ranking monetario'), context)
        assert response.classification == 'DIRECT_UNAVAILABLE' and '123.45' not in response.text
        assert latest(store)['capability_failure_evidence'] == {'difference': '123.45'}
        assert latest(store)['execution_result'] is None
    asyncio.run(run())


def ranking_fixture():
    from .test_category_line_amount import result as category_result, options
    from modules.telchi.datalake.product_line_amount_ranking_query import CAPABILITY, reconcile
    import hashlib
    full = [dict(item_code='SAP-A', description='Verified catalog name', amount='70.13', line_count=1, document_count=1)]
    r = category_result(options('LAB_FINISHED_PRODUCT'))
    total = r['rows'][0]
    r.update(capability=CAPABILITY, parameters=dict(r['parameters'], limit=5), plan=deepcopy(PLAN),
        category_total=total, rows=deepcopy(full), full_breakdown=full, reconciliation=reconcile(full, total))
    r['reconciliation']['breakdown_sha256'] = hashlib.sha256(json.dumps(full, sort_keys=True).encode()).hexdigest()
    return r


def test_specific_permission_executes_and_ordinal_uses_verified_product():
    async def run():
        from modules.telchi.datalake.product_line_amount_ranking_query import validate_result
        r = ranking_fixture()
        validate_result(r['parameters'], r)
        p = proposal({'/schema_version': 2, '/metric': METRIC, '/requested_metrics': [METRIC],
            '/period': FIXTURE['previous_state']['period'], '/entity_mention': {'text': 'LAB_FINISHED_PRODUCT', 'type': None}, '/limit': 5})
        handler, store, calls, context = setup([p])
        async def execute(*args, **kwargs):
            return deepcopy(r)
        handler.capabilities = SalesCapabilities(ranking_query=execute)
        context = replace(context, sender_identity=replace(context.sender_identity,
            permissions=context.sender_identity.permissions | {PERMISSION}))
        response = await handler.handle(event('ranking monetario'), context)
        assert response.classification == 'DIRECT_AVAILABLE' and 'Bs 70,13' in response.text
        a = latest(store)
        owner = a['owner']
        view = result_references.presentation(a, 'ranking', owner, 'thread')
        assert view and view['rows'][0]['item_code'] == 'SAP-A'
        ref = dict(intent='RESULT_REFERENCE', action='SELECT_RESULT', clarification=None,
                   result_reference=dict(result_id='ranking', ordinal=1, field='amount'))
        ordinal, text = result_references.resolve(ref, view, None, owner, 'thread')
        assert ordinal == 1 and 'SAP-A' in text and 'Bs 70,13' in text
        assert 'precios unitarios' not in response.text.split('No son')[0]
    asyncio.run(run())


@pytest.mark.parametrize('tamper', ['amount', 'order', 'limit', 'currency', 'total', 'plan', 'hash', 'snapshot'])
def test_result_contract_rejects_tampering(tamper):
    from modules.telchi.datalake.product_line_amount_ranking_query import validate_result
    r = ranking_fixture()
    opts = deepcopy(r['parameters'])
    if tamper == 'amount': r['rows'][0]['amount'] = '999'
    elif tamper == 'order': r['full_breakdown'].append(deepcopy(r['full_breakdown'][0]))
    elif tamper == 'limit': r['parameters']['limit'] = 1
    elif tamper == 'currency': r['currency'] = 'USD'
    elif tamper == 'total': r['category_total']['amount'] = '99'
    elif tamper == 'plan': r['plan']['group_by'] = 'category'
    elif tamper == 'hash': r['reconciliation']['breakdown_sha256'] = '0'*64
    elif tamper == 'snapshot': r['source']['snapshot_id'] = 999
    with pytest.raises(Exception):
        validate_result(opts, r)


def test_ranking_requires_own_permission_before_query():
    async def run():
        p = proposal({'/schema_version': 2, '/metric': METRIC, '/requested_metrics': [METRIC],
            '/period': FIXTURE['previous_state']['period'], '/entity_mention': {'text': 'LAB_FINISHED_PRODUCT', 'type': None}, '/limit': 5})
        handler, store, calls, context = setup([p])
        async def forbidden(*args, **kwargs):
            raise AssertionError('unauthorized query')
        handler.capabilities = SalesCapabilities(ranking_query=forbidden)
        response = await handler.handle(event('ranking monetario'), context)
        assert response.classification == 'DENIED' and latest(store)['capability_calls'] == 0
    asyncio.run(run())


def test_ordinal_without_result_does_not_execute():
    p = dict(intent='RESULT_REFERENCE', action='ASK', result_reference=None, clarification={'question': '¿Cuál?'})
    assert result_references.resolve(p, None, None, {}, 'thread')[0] is None
