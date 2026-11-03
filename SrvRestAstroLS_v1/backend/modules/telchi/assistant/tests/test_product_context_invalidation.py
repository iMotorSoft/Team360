"""Replay the audited non-empty product → category transition, without services."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from .test_assistant import event, latest
from .test_category_line_amount import grant, options, result
from .test_sales_business_contract import setup

AUDIT = json.loads((Path(__file__).parent / 'fixtures/product_context_invalidation_audited.json').read_text())


@pytest.fixture(autouse=True)
def historical_product_binding(monkeypatch):
    # Exact offline replay of an old publication, not a CURRENT product probe.
    from modules.telchi.datalake import product_sales_query
    context = AUDIT['previous_state']['product_context']
    historical = context['source']['publication_id']
    if historical != product_sales_query.PUBLICATION:
        with pytest.raises(ValueError, match='invalid_product_result'):
            product_sales_query.validate_result('products.search', context['parameters'], context)
    monkeypatch.setattr(product_sales_query, 'PUBLICATION', historical)


def before():
    return deepcopy(AUDIT['previous_state'])


def test_audited_transition_removes_only_obsolete_context():
    catalog = SalesCapabilities()
    # The old committed state proves the catalog correctly rejects residual context.
    assert catalog.availability(AUDIT['obsolete_state']).category == 'CATEGORY_CAPABILITY_UNAVAILABLE'
    prior = before()
    processed = engine.process(prior, AUDIT['proposal'], {}, 'category')
    assert processed['committed']
    expected = dict(deepcopy(AUDIT['obsolete_state']), product_context=None)
    assert processed['state_after'] == expected
    assert prior == AUDIT['previous_state']  # atomic, no caller mutation
    assert catalog.availability(expected).allowed
    assert catalog.required_permission(expected) == 'telchi.sales.category_line_amount.read.v1'
    assert expected['entity_mention'] == {'text': 'RAW_MATERIAL', 'type': None}
    assert expected['period'] == {'start': '2026-09-01', 'end_exclusive': '2026-10-01'}
    assert expected['requested_metrics'] == ['sales.net_amount']


@pytest.mark.parametrize('clear', ['unset', 'set_null'])
@pytest.mark.parametrize('selection', ['existing', 'set', 'unset', 'set_empty'])
def test_clear_text_uses_final_selection_not_delta_order(clear, selection):
    prior = before()
    code = prior['product_context']['rows'][0]['item_code']
    prior['selected_item_codes'] = [code]
    sets, unsets = {}, []
    if clear == 'unset':
        unsets.append('/product_search_text')
    else:
        sets['/product_search_text'] = None
    if selection == 'set':
        sets['/selected_item_codes'] = [code]
    elif selection == 'unset':
        unsets.insert(0, '/selected_item_codes')
    elif selection == 'set_empty':
        sets['/selected_item_codes'] = []
    after = engine.patch(prior, dict(set=sets, unset=unsets))
    retained = selection in {'existing', 'set'}
    assert after['product_context'] == (prior['product_context'] if retained else None)
    assert after['selected_item_codes'] == ([code] if retained else [])
    assert after['product_search_text'] is None


def test_period_refinement_preserves_selected_product_and_context():
    prior = before()
    prior['selected_item_codes'] = [prior['product_context']['rows'][0]['item_code']]
    after = engine.patch(prior, dict(set={'/period': {'start': '2026-08-01', 'end_exclusive': '2026-09-01'}}, unset=[]))
    assert after['product_context'] == prior['product_context']
    assert after['selected_item_codes'] == prior['selected_item_codes']
    assert SalesCapabilities().availability(after).allowed


def test_explicit_search_and_switching_products_keep_existing_contract():
    prior = before()
    first, second = [r['item_code'] for r in prior['product_context']['rows'][:2]]
    prior['selected_item_codes'] = [first]
    switched = engine.patch(prior, dict(set={'/selected_item_codes': [second]}, unset=[]))
    assert switched['product_context'] == prior['product_context']
    assert switched['selected_item_codes'] == [second]
    searched = engine.patch(prior, dict(set={'/product_search_text': 'otro producto'}, unset=[]))
    assert searched['product_context'] is None and searched['selected_item_codes'] == []
    assert searched['product_search_text'] == 'otro producto'
    # No implicit cleanup without an explicit text removal/change.
    kept = engine.patch(prior, dict(set={'/selected_item_codes': []}, unset=[]))
    assert kept['product_context'] == prior['product_context']


@pytest.mark.parametrize('mutation', ['invented_selection', 'conflict', 'missing_period', 'foreign_context'])
def test_invalid_or_incomplete_delta_cannot_execute(mutation):
    prior, raw = before(), deepcopy(AUDIT['proposal'])
    if mutation == 'invented_selection':
        raw['state_delta']['unset'].remove('/selected_item_codes')
        raw['state_delta']['set']['/selected_item_codes'] = ['not-from-search']
    elif mutation == 'conflict':
        raw['state_delta']['set']['product_search_text'] = None
    elif mutation == 'missing_period':
        del raw['state_delta']['set']['/period']
        raw['state_delta']['unset'].append('/period')
    else:
        raw['state_delta']['set']['/product_context'] = None
    processed = engine.process(prior, raw, {}, 'bad')
    assert not processed['committed'] and processed['state_after'] == prior


def test_category_with_retained_selection_still_fails_closed():
    prior, raw = before(), deepcopy(AUDIT['proposal'])
    prior['selected_item_codes'] = [prior['product_context']['rows'][0]['item_code']]
    raw['state_delta']['unset'].remove('/selected_item_codes')
    processed = engine.process(prior, raw, {}, 'incompatible')
    assert processed['committed']
    assert processed['state_after']['product_context'] == prior['product_context']
    assert not SalesCapabilities().availability(processed['state_after']).allowed


@pytest.mark.parametrize('authorized', [True, False])
def test_nonempty_handler_transition_never_searches_or_substitutes_global(authorized):
    async def exercise():
        handler, store, global_calls, context = setup([deepcopy(AUDIT['proposal'])])
        owner = (context.channel.environment, context.channel.tenant_id, context.channel.workspace_id,
                 context.channel.channel_id, context.sender_identity.user_id)
        store.states[owner + (context.conversation_id,)] = before()
        calls = []
        async def category_query(opts, **kwargs):
            calls.append(opts)
            return result(opts)
        async def forbidden(*args, **kwargs):
            raise AssertionError('search/global substitute must never execute')
        handler.capabilities = SalesCapabilities(category_query=category_query, product_query=forbidden, sales_query=forbidden)
        if authorized:
            context = grant(context)
        response = await handler.handle(event('Cuánto vendimos de materia prima en septiembre?'), context)
        assert response.classification == ('DIRECT_AVAILABLE' if authorized else 'DENIED')
        assert calls == ([options()] if authorized else [])
        assert not global_calls
        audit = latest(store)
        assert audit['previous_state'] == AUDIT['previous_state']
        assert audit['confirmed_state']['product_context'] is None
        assert audit['capability_calls'] == int(authorized)
    asyncio.run(exercise())
