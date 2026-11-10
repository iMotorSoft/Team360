"""Category meaning must not authorize text search, product lines or global totals."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json

import httpx
import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.business_categories import CATEGORIES, interpreter_context
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.luna import LunaInterpreter, MODEL
from .test_assistant import event, latest, proposal
from .test_sales_business_contract import setup

PERIOD = dict(start='2026-09-01', end_exclusive='2026-10-01')


def category(metric='sales.net_amount', code='RAW_MATERIAL', action='DIRECT_UNAVAILABLE'):
    return proposal({'/schema_version': 2, '/metric': metric,
        '/requested_metrics': [metric] if metric else [],
        '/entity_mention': dict(text=code, type=None), '/period': PERIOD},
        intent='NEW_QUERY', action=action)


@pytest.mark.parametrize('metric', ['sales.net_amount', 'sales.source_top_items', 'sales.by_products', 'products.search', None])
@pytest.mark.parametrize('code', list(CATEGORIES))
def test_category_blocks_every_incompatible_execution(metric, code):
    raw = category(metric, code, 'EXECUTE')
    if metric in {'sales.by_products', 'products.search'}:
        raw['state_delta']['set']['/product_search_text'] = 'materia prima'
    processed = engine.process(deepcopy(engine.EMPTY), raw, {}, 'category')
    assert processed['committed'] is (metric is not None)  # Engine already forbids EXECUTE without metric.
    catalog = SalesCapabilities()
    state = engine.patch(deepcopy(engine.EMPTY), raw['state_delta'])
    if metric == 'sales.net_amount' and code != 'UNKNOWN':
        assert catalog.availability(state).allowed
        assert catalog.required_permission(state) == 'telchi.sales.category_line_amount.read.v1'
    else:
        assert not catalog.availability(state).allowed
        with pytest.raises(ValueError, match='capability_not_available'):
            asyncio.run(catalog.execute(state))


def category_amount(options):
    """Accredited category aggregate fixture: same contract, no Foundation read."""
    from modules.telchi.datalake import category_line_amount_query as category
    return dict(capability=category.CAPABILITY, parameters=options, definition=category.DEFINITION,
        currency='BS', rows=[dict(key=None, amount='1520.00', product_count=1, line_count=2,
            document_count=1, first_date='2026-09-10', last_date='2026-09-10')],
        coverage=dict(first_date='2026-09-10', last_date='2026-09-10', complete=False),
        classification=dict(version=category.CLASSIFICATION_VERSION, sha256=category.CROSSWALK_SHA256,
            reference='fixture_reference', quality_lines={'VALIDATED': 2}),
        source=dict(publication_id=category.PUBLICATION, snapshot_id=category.SNAPSHOT,
            updated_at='2026-11-04T13:55:47.173006+00:00'),
        limitations=category.LIMITATIONS, read_only=True, sap_accessed=False)


def test_a_representable_category_request_is_executed_not_declared_unavailable():
    """An interpreter decision is not evidence of business unavailability.

    The committed scope is a complete category amount: the handler resolves it
    through the accredited operation instead of rendering an invented gap, and
    no internal identifier reaches the answer.
    """
    async def run():
        handler, store, calls, context = setup([category(action='DIRECT_UNAVAILABLE')])
        from modules.telchi.datalake.category_line_amount_query import PERMISSION
        grant = replace(context, sender_identity=replace(context.sender_identity,
            permissions=context.sender_identity.permissions | {PERMISSION}))
        executed = []

        async def query(options, **kwargs):
            executed.append(options)
            return category_amount(options)
        handler.capabilities = SalesCapabilities(sales_query=handler.capabilities.sales_query,
                                                 category_query=query)
        result = await handler.handle(event('cuanto vendimos de materia prima en septiembre'), grant)
        assert result.classification == 'DIRECT_AVAILABLE'
        audit = latest(store)
        assert audit['committed'] and audit['capability_calls'] == 1 and not calls
        assert audit['availability_inconsistency']['proposed_action'] == 'DIRECT_UNAVAILABLE'
        assert audit['decision'] == 'EXECUTE'
        assert audit['confirmed_state']['metric'] == 'sales.net_amount'
        assert audit['confirmed_state']['period'] == PERIOD
        assert '1.520,00' in result.text and 'septiembre de 2026' in result.text
        assert 'todavía no está disponible' not in result.text
        assert executed == [dict(category='RAW_MATERIAL', currency='BS',
                                 date_from=PERIOD['start'], date_to_exclusive=PERIOD['end_exclusive'])]
        assert not any(x in result.text for x in ('MAPPING_MISSING', 'RAW_MATERIAL', 'DocTotal', 'OINV', '306', '526'))
    asyncio.run(run())


def test_production_consumption_not_presented_as_sales():
    async def run():
        handler, store, calls, context = setup([category(metric=None)])
        result = await handler.handle(event('¿Cuánta materia prima consumimos en producción?'), context)
        assert result.classification == 'DIRECT_UNAVAILABLE' and not calls
        assert 'no la sustituyo por ventas' in result.text
        assert latest(store)['confirmed_state']['metric'] is None
    asyncio.run(run())


@pytest.mark.parametrize('metric,text', [('products.search', 'materia prima'), ('products.search', 'L01128'), ('sales.by_products', 'L01128')])
def test_explicit_text_code_and_individual_product_contracts_remain_available(metric, text):
    raw = proposal({'/schema_version': 2, '/metric': metric, '/requested_metrics': [metric],
                    '/product_search_text': text, '/entity_mention': None}, intent='NEW_QUERY')
    state = engine.process(deepcopy(engine.EMPTY), raw, {}, 'search')['state_after']
    assert SalesCapabilities().availability(state).allowed


def test_genuine_metric_ambiguity_asks_without_running_or_claiming_consumption():
    async def run():
        raw = category(metric=None, action='ASK')
        raw['clarification'] = dict(slot='metric', question='¿Querés el importe de ventas o las cantidades?')
        handler, store, calls, context = setup([raw])
        result = await handler.handle(event('Ventas de materia prima en septiembre de 2026'), context)
        assert result.classification == 'NEEDS_CLARIFICATION' and not calls
        assert 'importe' in result.text and 'cantidades' in result.text
        pending = latest(store)['confirmed_state']['pending']['proposed']
        assert pending['entity_mention']['text'] == 'RAW_MATERIAL' and pending['period'] == PERIOD
    asyncio.run(run())


def test_elliptical_category_followup_keeps_money_and_period():
    before = engine.process(deepcopy(engine.EMPTY), category(), {}, 'raw')['state_after']
    followup = proposal({'/entity_mention': dict(text='LAB_FINISHED_PRODUCT', type=None)},
                        intent='REFINE', action='DIRECT_UNAVAILABLE')
    result = engine.process(before, followup, {'raw': before}, 'finished')
    assert result['committed']
    assert result['state_after']['period'] == PERIOD
    assert result['state_after']['requested_metrics'] == ['sales.net_amount']
    assert result['state_after']['entity_mention']['text'] == 'LAB_FINISHED_PRODUCT'


def test_compact_semantic_data_reaches_adapter(monkeypatch):
    monkeypatch.setenv('OpenAI_Key_JAI_query', 'test-only')
    def respond(request):
        payload = json.loads(json.loads(request.content)['input'][1]['content'])
        assert payload['business_categories'] == interpreter_context()
        assert len(json.dumps(payload['business_categories'])) < 2000
        assert 'L01128' not in json.dumps(payload['business_categories'])
        return httpx.Response(200, json=dict(model=MODEL, status='completed', reasoning={'effort': 'medium'},
            output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(category()))])]))
    raw = asyncio.run(LunaInterpreter(transport=httpx.MockTransport(respond)).interpret(
        text='ventas por categoría', state=deepcopy(engine.EMPTY), history={}, turn_id='context'))
    assert raw == category()
