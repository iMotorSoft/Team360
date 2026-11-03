"""Second incident: search was abandoned in a previous persisted turn, unset=[]."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from .test_product_context_invalidation import AUDIT, historical_product_binding
from .test_assistant import event, latest
from .test_category_line_amount import grant, options, result
from .test_sales_business_contract import setup

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/persisted_product_context_recovery.json').read_text())


def before():
    return deepcopy(AUDIT[FIXTURE['previous_state_key']])


def proposal():
    return deepcopy(FIXTURE['proposal'])


def test_second_incident_unset_empty_and_idempotent():
    prior, raw = before(), proposal()
    assert prior['product_context']['capability'] == 'products.search.v1'
    assert prior['product_search_text'] is None and prior['selected_item_codes'] == []
    assert raw['state_delta']['unset'] == []
    assert not SalesCapabilities().availability(prior).allowed
    recovered = engine.process(prior, raw, {}, 'second')
    assert recovered['committed']
    expected = dict(before(), product_context=None)
    assert recovered['state_after'] == expected
    assert prior == before()
    assert SalesCapabilities().availability(expected).allowed
    assert engine.process(expected, raw, {}, 'repeat')['state_after'] == expected
    # No operation mentioning product slots (or even category) is required.
    assert engine.patch(prior, dict(set={}, unset=[])) == expected


@pytest.mark.parametrize('code', ['RAW_MATERIAL', 'LAB_FINISHED_PRODUCT', 'PACKAGING'])
def test_other_accredited_categories_recover(code):
    raw = proposal()
    raw['state_delta']['set']['/entity_mention']['text'] = code
    after = engine.process(before(), raw, {}, 'category')['state_after']
    assert after['product_context'] is None
    assert after['entity_mention']['text'] == code
    assert SalesCapabilities().availability(after).allowed


@pytest.mark.parametrize('case', ['selection', 'selected_period', 'active_search', 'noncategory', 'nonmonetary'])
def test_legitimate_or_unproven_context_is_not_erased(case):
    prior, delta = before(), dict(set={}, unset=[])
    if case in {'selection', 'selected_period'}:
        prior['selected_item_codes'] = [prior['product_context']['rows'][0]['item_code']]
    if case == 'selected_period':
        delta['set']['/period'] = dict(start='2026-08-01', end_exclusive='2026-09-01')
    elif case == 'active_search':
        prior['product_search_text'] = 'materia prima'
    elif case == 'noncategory':
        prior['entity_mention'] = dict(text='not-accredited', type=None)
    elif case == 'nonmonetary':
        prior['metric'], prior['requested_metrics'] = 'sales.by_products', ['sales.by_products']
    after = engine.patch(prior, delta)
    assert after['product_context'] == prior['product_context']
    assert after['selected_item_codes'] == prior['selected_item_codes']
    assert not SalesCapabilities().availability(after).allowed


def test_monetary_comparison_between_recovered_categories():
    from .test_category_line_amount import audit
    from modules.telchi.assistant.monetary_comparison import accredited, calculate
    owner = {'workspace': 'fixture'}
    results = []
    for code in ('RAW_MATERIAL', 'LAB_FINISHED_PRODUCT'):
        raw = proposal()
        raw['state_delta']['set']['/entity_mention']['text'] = code
        recovered = engine.process(before(), raw, {}, code)
        assert recovered['committed'] and recovered['state_after']['product_context'] is None
        record = audit(code)
        record['confirmed_state'] = recovered['state_after']
        results.append(accredited(record, code, owner))
    request = dict(intent='MONETARY_COMPARISON', action='CALCULATE', clarification=None,
        comparison=dict(target_id='LAB_FINISHED_PRODUCT', baseline_id='RAW_MATERIAL', mode='difference'))
    assert calculate(request, results, owner)[0]['difference'] == '100'
    request['comparison']['mode'] = 'percent'
    assert '100,00 %' in calculate(request, results, owner)[1]


def test_return_to_product_and_document_reference_preserved():
    prior = before()
    prior['reference'] = 'document-request'
    raw = proposal()
    after = engine.process(prior, raw, {'document-request': before()}, 'category')['state_after']
    assert after['reference'] == 'document-request'
    delta = dict(set={'/metric': 'products.search', '/requested_metrics': ['products.search'],
                      '/entity_mention': None, '/product_search_text': 'otro producto'}, unset=[])
    returned = engine.patch(after, delta)
    assert returned['product_search_text'] == 'otro producto'
    assert returned['reference'] == 'document-request'
    assert SalesCapabilities().availability(returned).allowed
    # An explicit selection from the retained trusted search still works.
    code = prior['product_context']['rows'][0]['item_code']
    selected = engine.patch(prior, dict(set={'/metric': 'sales.by_products',
        '/requested_metrics': ['sales.by_products'], '/entity_mention': None,
        '/selected_item_codes': [code]}, unset=[]))
    assert selected['product_context'] == prior['product_context']
    assert selected['selected_item_codes'] == [code]
    engine.validate(selected)


@pytest.mark.parametrize('case', ['missing_period', 'invented_selection', 'unknown_path', 'bad_context'])
def test_incomplete_or_incompatible_fails_closed(case):
    prior, raw = before(), proposal()
    sets = raw['state_delta']['set']
    if case == 'missing_period':
        sets['/period'] = None
    elif case == 'invented_selection':
        sets['/selected_item_codes'] = ['invented']
    elif case == 'unknown_path':
        sets['/product_context'] = None
    else:
        prior['product_context']['capability'] = 'untrusted'
    processed = engine.process(prior, raw, {}, 'invalid')
    assert not processed['committed']
    assert processed['state_after'] == prior


@pytest.mark.parametrize('authorized', [True, False])
def test_persisted_handler_recovery_and_denial(authorized):
    async def exercise():
        handler, store, global_calls, ctx = setup([proposal()])
        owner = (ctx.channel.environment, ctx.channel.tenant_id, ctx.channel.workspace_id,
                 ctx.channel.channel_id, ctx.sender_identity.user_id)
        store.states[owner + (ctx.conversation_id,)] = before()
        calls = []
        async def query(opts, **kwargs):
            calls.append(opts)
            return result(opts)
        async def forbidden(*args, **kwargs):
            raise AssertionError('No textual/global substitute')
        handler.capabilities = SalesCapabilities(category_query=query, product_query=forbidden, sales_query=forbidden)
        response = await handler.handle(event('Consulta monetaria por categoría'), grant(ctx) if authorized else ctx)
        assert response.classification == ('DIRECT_AVAILABLE' if authorized else 'DENIED')
        assert calls == ([options()] if authorized else []) and not global_calls
        audit = latest(store)
        assert audit['previous_state'] == before()
        assert audit['confirmed_state']['product_context'] is None
        assert audit['capability_calls'] == int(authorized)
    asyncio.run(exercise())
