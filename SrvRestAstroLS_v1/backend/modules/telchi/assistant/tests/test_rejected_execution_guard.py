"""Negative execution-guard evidence for the V2 state contract.

Separate from the 32-turn HTTP battery: proves that a structurally invalid
proposal never commits, never executes, never re-runs a previous action and
returns a safe response. It reuses the module's existing controlled fixtures
(``MemoryStore`` + injected interpreter), never the live HTTP endpoint, so no
business message, permission or arbitrary client state is fabricated.
"""
from copy import deepcopy
from dataclasses import replace

from .test_assistant import context, event, latest, plan, proposal, run, setup


@run
async def test_rejected_proposal_guard_negative_case():
    # A real, executable plan must already exist so "no re-execution" is meaningful.
    valid = proposal({'/metric': plan()['metric'], '/period': plan()['period']})
    # Structurally invalid proposal: end_exclusive < start -> engine contract_error.
    invalid = proposal({'/period': {'start': '2026-09-30', 'end_exclusive': '2026-09-01'}})
    handler, store, llm, calls = setup([valid, invalid])

    first = await handler.handle(event('consulta valida'), context())
    assert first.classification == 'DIRECT_AVAILABLE' and len(calls) == 1

    state_before = deepcopy(latest(store)['confirmed_state'])
    calls_before = len(calls)

    negative = await handler.handle(
        event('turno con periodo invalido'), replace(context(), correlation_id='turn-negative'))
    audit = latest(store)

    # 1. Invalid structured interpretation is rejected (no guess, no repair).
    assert negative.classification == 'ERROR'
    # 2. It does not commit.
    assert audit['committed'] is False
    # 3. The previous confirmed state is preserved byte-for-byte.
    assert audit['previous_state'] == state_before == audit['confirmed_state']
    # 4/5. Zero capability and Foundation calls; the prior action is never re-run.
    assert len(calls) == calls_before == 1
    assert audit['execution_result'] is None and audit['execution_status'] == 'not_executed'
    # 6. Deterministic guard decision, not an LLM judgement.
    assert audit['decision'] == 'EXECUTION_FORBIDDEN'
    # 7. Safe, coherent response with no business data.
    assert negative.text == 'No pude interpretar la consulta. No se ejecutó ninguna consulta.'