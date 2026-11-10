"""CAPABILITY_MISSING is a routing signal, not a dead end.

Only a catalog gap reaches the single existing researcher. Known queries keep the
optimized capability path, and no extra model call chooses the path: the capability
plan already failed before the fallback is attempted.
"""
import asyncio
from copy import deepcopy

from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler

from .test_assistant import Interpreter, MemoryStore, context, event, latest, proposal

POLICY = BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)
PERIOD = {'start': '2026-10-01', 'end_exclusive': '2026-11-01'}
# sales.by_products without an explicit product reference is not in the catalog:
# availability() returns CAPABILITY_MISSING by design.
GAP = proposal({'/metric': 'sales.by_products', '/period': PERIOD}, intent='NEW_QUERY')
ANSWER = 'Investigación acreditada sobre Foundation: soda cáustica x25 kg, octubre 2026.'


def build(proposals, researcher):
    return TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                         interpreter=Interpreter(proposals), capabilities=SalesCapabilities(),
                         researcher=researcher)


def record(status='READY', text=ANSWER, **extra):
    calls = []

    async def researcher(question, conversation_id, ctx):
        calls.append((question, conversation_id, ctx.correlation_id))
        return dict(status=status, business_answer=text, publication='foundation_current',
                    snapshot='1408', question_coverage='COMPLETE',
                    model_calls=[{'model': 'luna'}], sql_executions=2, **extra)
    researcher.calls = calls
    return researcher


def test_catalog_gap_uses_the_same_in_process_researcher():
    async def run():
        researcher = record()
        handler = build([GAP], researcher)
        response = await handler.handle(event('Qué clientes compraron soda cáustica x25 kg'), context())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert response.text.startswith(ANSWER)
        assert researcher.calls and researcher.calls[0][1] == 'conversation'
        audit = latest(handler.store)
        assert audit['decision'] == 'RESEARCH' and audit['execution_status'] == 'executed'
        assert audit['research']['publication'] == 'foundation_current'
        assert audit['research']['sql_executions'] == 2
        assert audit['capability_calls'] == 0  # the catalog executed nothing

    asyncio.run(run())


def test_without_the_port_the_accredited_gap_answer_is_unchanged():
    async def run():
        handler = build([GAP], None)
        response = await handler.handle(event('Qué clientes compraron soda cáustica x25 kg'), context())
        assert response.classification == 'DIRECT_UNAVAILABLE'
        assert latest(handler.store)['decision'] == 'DIRECT_UNAVAILABLE'

    asyncio.run(run())


def test_a_refused_comparison_is_a_catalog_gap_and_reaches_the_researcher():
    async def run():
        researcher = record()
        handler = build([proposal({'/metric': 'sales.net_amount', '/period': PERIOD,
                                   '/comparison': {'start': '2026-09-01',
                                                   'end_exclusive': '2026-10-01'}},
                                  intent='NEW_QUERY')], researcher)
        response = await handler.handle(event('Diferencia de facturación entre septiembre y octubre'), context())
        # The accredited operation refuses the scope; that is not missing data.
        audit = latest(handler.store)
        assert audit['bmd']['category'] == 'RESEARCH_ANSWER'
        assert audit['research']['routing_category'] == 'COMPARISON_UNSUPPORTED'
        assert [call[0] for call in researcher.calls] == [
            'Diferencia de facturación entre septiembre y octubre']
        assert response.classification == 'DIRECT_AVAILABLE'
        assert audit['decision'] == 'RESEARCH'

    asyncio.run(run())


def test_without_the_port_a_refused_comparison_keeps_the_accredited_gap_answer():
    async def run():
        handler = build([proposal({'/metric': 'sales.net_amount', '/period': PERIOD,
                                   '/comparison': {'start': '2026-09-01',
                                                   'end_exclusive': '2026-10-01'}},
                                  intent='NEW_QUERY')], None)
        response = await handler.handle(event('Diferencia de facturación entre septiembre y octubre'), context())
        assert response.classification == 'DIRECT_UNAVAILABLE'
        assert latest(handler.store)['bmd']['category'] == 'COMPARISON_UNSUPPORTED'

    asyncio.run(run())


def test_fixed_capability_window_does_not_prove_a_foundation_coverage_gap():
    async def run():
        researcher = record()
        handler = build([proposal({'/metric': 'sales.source_top_items',
                                   '/period': {'start': '2021-01-01',
                                               'end_exclusive': '2021-02-01'}},
                                  intent='NEW_QUERY')], researcher)
        response = await handler.handle(event('Cantidades documentales por producto en enero de 2021'), context())
        # This category comes from the FIXED capability window, not a read of
        # Foundation coverage. Research must establish what sources can answer.
        assert response.classification == 'DIRECT_AVAILABLE'
        assert len(researcher.calls) == 1
        assert latest(handler.store)['research']['routing_category'] == 'COVERAGE_GAP'

    asyncio.run(run())


def test_blocked_or_failed_research_never_invents_an_answer():
    async def run():
        for status, text in (('BLOCKED', ''), ('READY', '')):
            researcher = record(status=status, text=text)
            handler = build([GAP], researcher)
            response = await handler.handle(event('Pregunta no acreditable'), context())
            assert researcher.calls
            assert response.classification == 'DIRECT_UNAVAILABLE'
            assert latest(handler.store)['decision'] == 'DIRECT_UNAVAILABLE'
            assert latest(handler.store)['research']['status'] == status

    asyncio.run(run())


def test_researcher_failure_keeps_the_gap_answer_and_is_audited():
    async def run():
        calls = []

        async def researcher(question, conversation_id, ctx):
            calls.append(question)
            raise RuntimeError('foundation_unavailable')
        handler = build([GAP], researcher)
        response = await handler.handle(event('Pregunta no acreditable'), context())
        assert calls
        assert response.classification == 'DIRECT_UNAVAILABLE'
        assert latest(handler.store)['research'] == {'status': 'ERROR',
                                                    'reason': 'researcher_unavailable'}

    asyncio.run(run())

AUDITED_QUESTION = ('¿Qué clientes compraron soda cáustica x25 kg en octubre de 2026, '
                    'pero no en septiembre?')
AUDITED = proposal({
    '/limit': 10,
    '/metric': 'sales.commercial_line_amount_by',
    '/period': {'start': '2026-10-01', 'end_exclusive': '2026-11-01'},
    '/group_by': 'card_code',
    '/comparison': {'start': '2026-09-01', 'end_exclusive': '2026-10-01'},
    '/entity_mention': None,
    '/schema_version': 2,
    '/requested_metrics': ['sales.commercial_line_amount_by'],
    '/temporal_reference': None,
    '/product_search_text': 'soda cáustica x25 kg',
    '/selected_item_codes': [],
}, unset=['/ranking_by', '/product_target', '/customer_target', '/period_mode',
          '/breakdown_by'], intent='REFINE')


def previous_commercial_state():
    from modules.telchi.assistant import state_engine as engine
    state = deepcopy(engine.EMPTY | engine.INTENT_V2 | engine.PRODUCT_FIELDS | engine.SCOPE_FIELDS)
    state.update(metric='sales.commercial_line_amount_by',
                 requested_metrics=['sales.commercial_line_amount_by'],
                 group_by='sap_product', ranking_by='amount', limit=3, period=dict(PERIOD),
                 focus={'product': 'L01772', 'product_label': 'SULFATO DE COBRE x 25kg.'})
    engine.validate(state)
    return state


def test_first_free_analysis_e2e_of_0811_reaches_the_researcher():
    """The audited turn never dead-ended on a false «no accredited product»."""
    async def run():
        researcher = record(status='READY', text='7 clientes compraron en octubre y no en septiembre.')
        handler = build([AUDITED], researcher)
        ctx = context()
        async with handler.store.turn(ctx) as turn:
            handler.store.states[turn['key']] = previous_commercial_state()
        response = await handler.handle(event(AUDITED_QUESTION), ctx)
        assert len(researcher.calls) == 1
        question = researcher.calls[0][0]
        assert question.startswith(AUDITED_QUESTION + '\nContexto previo confirmado')
        assert '"metric": "sales.commercial_line_amount_by"' in question
        assert '"group_by": "sap_product"' in question
        assert 'No encontré un producto acreditado' not in response.text
        assert response.classification == 'DIRECT_AVAILABLE'
        audit = latest(handler.store)
        assert audit['bmd']['category'] == 'RESEARCH_ANSWER'
        assert audit['research']['routing_category'] == 'COMPARISON_UNSUPPORTED'
        assert audit['decision'] == 'RESEARCH'
        assert audit['capability_calls'] == 0
        assert 'product_resolution' not in audit  # no catalog dead end

    asyncio.run(run())
