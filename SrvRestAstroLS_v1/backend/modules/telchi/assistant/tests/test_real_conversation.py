"""Real-case contract regressions. Interpreter doubles are NOT Luna quality evidence."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import TelchiHandler
from .test_assistant import context, event, latest, plan, proposal, run, setup

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/whatsapp_20261011.json').read_text())
MAY = {'start': '2026-05-01', 'end_exclusive': '2026-06-01'}
BOTH = ['sales.net_amount', 'sales.source_top_items']


def v2(**kwargs):
    return deepcopy(engine.EMPTY) | deepcopy(engine.INTENT_V2) | kwargs


def known(**kwargs):
    state = v2(entity_mention={'text': 'calenta', 'type': None}, **kwargs)
    return {'/' + k: v for k, v in state.items() if k != 'pending'}


@run
async def test_exact_six_turns_with_handler_restart_and_no_monetary_execution():
    proposals = [
        proposal(known(), action='ASK', intent='NEW_QUERY', clarification={'slot': 'metric', 'question': '¿Importe, cantidades o ambas?'}),
        proposal(known(metric=BOTH[0], requested_metrics=BOTH), action='DIRECT_UNAVAILABLE', intent='ANSWER_CLARIFICATION'),
        proposal({'/metric': BOTH[0], '/requested_metrics': BOTH}, action='DIRECT_UNAVAILABLE'),
        proposal({'/period': None, '/temporal_reference': 'latest_available_month'}, action='DIRECT_UNAVAILABLE'),
        proposal({'/period': MAY, '/temporal_reference': None}),
        proposal({'/period': MAY}),
    ]
    handler, store, llm, calls = setup(proposals)
    for n, turn in enumerate(FIXTURE['turns']):
        if n == 3:
            handler = TelchiHandler(store=store, authorization=handler.authorization, interpreter=llm, capabilities=handler.capabilities)
        response = await handler.handle(event(turn['text']), replace(context(), correlation_id=f'real-{n}'))
        assert latest(store)['committed'] is True
        if n:
            assert response.classification == 'DIRECT_UNAVAILABLE'
            state = latest(store)['confirmed_state']
            assert state['requested_metrics'] == BOTH and state['metric'] == BOTH[0]
            assert state['entity_mention'] == {'text': 'calenta', 'type': None}
            assert 'importe' in response.text and 'cantidades' in response.text
        if n == 3:
            assert 'metadata' in response.text and state['period'] is None
        if n >= 4:
            assert state['period'] == MAY and state['temporal_reference'] is None
            assert 'No es un problema con la fecha' in response.text
        assert not calls
    assert llm.calls[-1]['state']['period'] == MAY


@run
async def test_missing_metric_does_not_provoke_useless_date_clarification():
    handler, store, llm, calls = setup([
        proposal(known(metric=BOTH[0], requested_metrics=BOTH), action='ASK', clarification={'slot': 'period', 'question': '¿Qué mes?'}),
    ])
    response = await handler.handle(event('primero la plata'), context())
    audit = latest(store)
    assert audit['committed'] and response.classification == 'DIRECT_UNAVAILABLE'
    assert audit['bmd']['category'] == 'MAPPING_MISSING' and not calls
    # Pending known intention is retained; ASK never overwrites active state.
    assert audit['confirmed_state']['metric'] is None
    assert audit['confirmed_state']['pending']['proposed']['requested_metrics'] == BOTH
    assert 'importe' in response.text and '¿Qué mes?' not in response.text


def test_followup_ask_keeps_known_pending_entity():
    first = engine.process(engine.EMPTY, proposal(known(), action='ASK', clarification={'slot': 'metric', 'question': '¿Qué métrica?'}), {}, 'a')
    followup = engine.process(first['state_after'], proposal({'/metric': 'sales.source_top_items', '/requested_metrics': ['sales.source_top_items']}, action='ASK', intent='ANSWER_CLARIFICATION', clarification={'slot': 'period', 'question': '¿Qué período?'}), {}, 'b')
    assert followup['committed']
    assert followup['state_after']['pending']['proposed']['entity_mention']['text'] == 'calenta'


@pytest.mark.parametrize('slot,kwargs', [('metric', dict(metric=BOTH[0], requested_metrics=BOTH)), ('period', dict(period=MAY)), ('period', dict(temporal_reference='latest_available_month'))])
def test_redundant_clarification_rejected_without_state_change(slot, kwargs):
    before = v2(**kwargs)
    result = engine.process(before, proposal(action='ASK', clarification={'slot': slot, 'question': '¿Otra vez?'}), {}, 'a')
    assert result['committed'] is False and result['state_after'] == before


def test_correct_supersedes_pending_and_executes_without_loop():
    # Pending period raised while the metric is unavailable (handler suppresses the
    # ASK to DIRECT_UNAVAILABLE but the durable pending remains). A CORRECT follow-up
    # must apply the correction and clear pending instead of failing unresolved_pending.
    first = engine.process(engine.EMPTY, proposal(
        known(metric=BOTH[0], requested_metrics=BOTH), action='ASK', intent='ANSWER_CLARIFICATION',
        clarification={'slot': 'period', 'question': '¿Qué período?'}), {}, 'a')
    assert first['committed'] and first['state_after']['pending'] is not None
    corrected = engine.process(first['state_after'], proposal(
        {'/metric': BOTH[1], '/requested_metrics': [BOTH[1]], '/period': plan()['period']},
        action='EXECUTE', intent='CORRECT'), {}, 'b')
    assert corrected['committed'] and corrected['state_after']['pending'] is None
    assert corrected['state_after']['metric'] == BOTH[1]
    # The correction is now a valid request; the retained entity still needs an
    # approved mapping, but the pending clarification no longer blocks it.
    assert SalesCapabilities().availability(corrected['state_after']).category == 'MAPPING_MISSING'


def test_priority_reorders_without_dropping_quantity():
    before = v2(metric=BOTH[1], requested_metrics=list(reversed(BOTH)))
    result = engine.process(before, proposal({'/metric': BOTH[0], '/requested_metrics': BOTH}, action='DIRECT_UNAVAILABLE'), {}, 'p')
    assert result['committed'] and result['state_after']['requested_metrics'] == BOTH


@pytest.mark.parametrize('sets', [
    {'/schema_version': 3}, {'/requested_metrics': ['sales.net_amount', 'sales.net_amount']},
    {'/requested_metrics': ['sales.net_amount']}, {'/entity_mention': {'text': 'Calenta', 'type': 'brand'}},
    {'/temporal_reference': 'latest_available_month', '/period': MAY},
])
@run
async def test_invalid_v2_cannot_execute_retained_supported_state(sets):
    handler, store, llm, calls = setup([proposal({'/metric': plan()['metric'], '/period': plan()['period']}), proposal(sets)])
    await handler.handle(event(), context())
    calls.clear()
    await handler.handle(event(), replace(context(), correlation_id='invalid'))
    assert not calls and latest(store)['committed'] is False
    assert latest(store)['previous_state'] == latest(store)['confirmed_state']


@pytest.mark.parametrize('period,category', [
    (MAY, 'PERIOD_PARAMETER_UNSUPPORTED'),
    ({'start': '2026-09-01', 'end_exclusive': '2026-10-01'}, 'COVERAGE_GAP'),
])
def test_window_is_not_month_parameterization(period, category):
    available = SalesCapabilities().availability(dict(plan(), period=period))
    assert not available.allowed and available.category == category


def test_latest_month_metadata_missing_not_user_ambiguity():
    state = v2(metric=BOTH[1], requested_metrics=[BOTH[1]], temporal_reference='latest_available_month')
    available = SalesCapabilities().availability(state)
    assert available.category == 'TEMPORAL_METADATA_MISSING'


def test_entity_not_resolved_by_intuition():
    state = v2(metric=BOTH[1], requested_metrics=[BOTH[1]], period=plan()['period'], entity_mention={'text': 'Calenta', 'type': None})
    assert SalesCapabilities().availability(state).category == 'MAPPING_MISSING'


@run
async def test_v2_repository_roundtrip_preserves_metrics_entity_and_period():
    from modules.telchi.assistant.repository import ConversationRepository
    from .test_repository import Connection
    c = context()
    repo = ConversationRepository()
    conn = Connection([{'metadata_jsonb': {}}, {'payload_jsonb': {'environment': 'dev'}}])
    turn = await repo.load(conn, c)
    state = v2(metric=BOTH[0], requested_metrics=BOTH, period=MAY, entity_mention={'text': 'Calenta', 'type': None})
    audit = dict(owner=turn['owner'], confirmed_state=state, response_prepared={'text': 'fixture', 'classification': 'DIRECT_UNAVAILABLE'})
    await repo.save(conn, c, turn, audit)
    saved = conn.calls[-2][1][0].obj['telchi_assistant_v1']
    # New repository + connection model restart; not in-process state reuse.
    reloaded = await ConversationRepository().load(Connection([{'metadata_jsonb': {'telchi_assistant_v1': saved}}, {'payload_jsonb': {'environment': 'dev'}}]), c)
    assert reloaded['state'] == state
    assert reloaded['history'][c.correlation_id] == state


def test_supported_exact_v2_contract_still_available():
    state = v2(metric=BOTH[1], requested_metrics=[BOTH[1]], period=plan()['period'])
    assert SalesCapabilities().availability(state).allowed
