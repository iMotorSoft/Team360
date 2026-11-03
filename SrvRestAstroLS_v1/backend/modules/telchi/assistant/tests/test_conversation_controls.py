"""No external calls: explicit controls use the existing authenticated handler."""
from dataclasses import replace
from copy import deepcopy

from .test_assistant import run, setup, context, event, proposal, plan, latest
from modules.telchi.assistant.conversation_controls import OPTIONS, with_options
from modules.telchi.assistant.state_engine import EMPTY


@run
async def test_continue_keeps_state_without_interpretation_or_execution():
    handler, store, luna, calls = setup([
        proposal({'/metric': 'sales.source_top_items', '/period': plan()['period']}, intent='NEW_QUERY')])
    result = await handler.handle(event('consulta'), context())
    assert result.text.endswith(OPTIONS)
    before = deepcopy(latest(store)['confirmed_state'])
    result = await handler.handle(event('Continuar'), replace(context(), correlation_id='turn-2'))
    assert result.classification == 'NEEDS_CLARIFICATION'
    assert result.text.endswith(OPTIONS)
    assert latest(store)['confirmed_state'] == before
    assert latest(store)['parent_turn_id'] == 'turn-1'
    assert len(luna.calls) == 1 and len(calls) == 1


@run
async def test_new_query_resets_filters_and_keeps_auditable_turns():
    handler, store, luna, calls = setup([
        proposal({'/metric': 'sales.source_top_items', '/period': plan()['period']}, intent='NEW_QUERY')])
    await handler.handle(event('consulta'), context())
    old_context = latest(store)['analysis_context_id']
    await handler.handle(event('Nueva consulta'), replace(context(), correlation_id='turn-2'))
    assert latest(store)['confirmed_state'] == EMPTY
    assert latest(store)['analysis_context_id'] != old_context
    assert latest(store)['parent_turn_id'] is None
    assert len(store.audits) == 2
    assert len(luna.calls) == 1 and len(calls) == 1
    # Replayed control returns its persisted response, not another reset.
    saved = deepcopy(latest(store))
    await handler.handle(event('Nueva consulta'), replace(context(), correlation_id='turn-2'))
    assert latest(store) == saved


@run
async def test_first_question_uses_context_created_by_new_query_control():
    handler, _, _, _ = setup([
        proposal({'/metric':'sales.source_top_items','/period':plan()['period']},intent='NEW_QUERY')])
    c = context()
    turn = dict(owner=['dev','telchi','workspace','channel','user'],state=deepcopy(EMPTY),
                history={},analysis_context_id='context-created-by-control')
    result, audit = await handler._process(event('otra pregunta'),c,turn)
    assert result.classification == 'DIRECT_AVAILABLE'
    assert audit['analysis_context_id'] == 'context-created-by-control'


@run
async def test_supplier_followup_never_substitutes_purchase_total():
    handler, store, luna, calls = setup([])
    c = context()
    owner = [c.channel.environment,c.channel.tenant_id,c.channel.workspace_id,c.channel.channel_id,c.sender_identity.user_id]
    key = tuple(owner) + (c.conversation_id,)
    state = deepcopy(EMPTY)
    state.update(metric='purchasing.invoiced_amount',period={'start':'2026-10-01','end_exclusive':'2026-11-01'})
    store.states[key] = state
    response = await handler.handle(event('¿Y cuáles fueron los cinco principales proveedores?'),c)
    assert response.classification == 'DIRECT_UNAVAILABLE'
    assert response.text.endswith(OPTIONS)
    assert '2026-10-01' in response.text and 'ranking por proveedor' in response.text
    assert not calls and not luna.calls
    assert latest(store)['confirmed_state'] == state


def test_options_fit_without_losing_menu_and_are_not_duplicated():
    text = 'Resultado: Bs 4.026.474,58\n' + ('detalle\n' * 1000) + 'Cobertura limitada'
    result = with_options(text)
    assert len(result) <= 4096 and result.endswith(OPTIONS)
    assert '4.026.474,58' in result and 'Cobertura limitada' in result
    assert with_options(result) == result
