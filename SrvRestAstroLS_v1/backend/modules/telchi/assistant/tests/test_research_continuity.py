"""Executed research lists reuse the existing selection contract without SQL."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from contextlib import asynccontextmanager

from modules.telchi.assistant.result_references import research_presentation, interpreter_context
from .test_research_fallback import build
from .test_assistant import context as base_context, event, latest, MemoryStore


def context(turn_id='turn-1'):
    return replace(base_context(), correlation_id=turn_id)


class Store(MemoryStore):
    analysis_id = 'conversation'
    @asynccontextmanager
    async def turn(self, ctx):
        async with super().turn(ctx) as turn:
            turn['analysis_context_id'] = self.analysis_id
            yield turn
    async def save(self, ctx, turn, audit):
        await super().save(ctx, turn, audit)
        self.analysis_id = audit['analysis_context_id']


def saved():
    return dict(result_id='research-turn', receipt={'binding': {}}, full_result=dict(
        question='Lista anterior', claim_verifications=[dict(match=True,
            claim=dict(kind='executed_cell', result_id='executed'))],
        evidence_manifests=[dict(result_id='executed', query_id='query', publication='p',
            snapshot='1', columns=[{'alias': 'name'}, {'alias': 'amount', 'source_fields': ['sales_line.line_total']}],
            filter_expression='currency COMPARE_EQUAL "BS"')],
        results=[dict(query_id='query', status='COMPLETED', truncated=False,
            schema=[dict(name='name', sql_type='VARCHAR'), dict(name='amount', sql_type='DECIMAL(38,6)')],
            rows=[['Cliente A', '100.000000'], ['Cliente B', '9.250000']])]))


class Researcher:
    allowed = True
    checks = 0
    async def result_reference(self, ctx, turn):
        if self.allowed and turn.get('analysis_context_id', ctx.conversation_id) == ctx.conversation_id:
            return research_presentation(saved(), turn['owner'], ctx.conversation_id)
    async def revalidate(self, ctx, receipt):
        self.checks += 1
        return self.allowed
    async def __call__(self, *args, **kwargs):
        raise AssertionError('Research must not repeat')


def selection(ordinal=2):
    return dict(intent='RESULT_REFERENCE', action='SELECT_RESULT',
                result_reference=dict(result_id='research-turn', ordinal=ordinal, field=None), clarification=None)


def test_full_records_reach_interpreter_and_selection_survives_continue():
    async def run():
        researcher = Researcher()
        handler = build([selection()], researcher)
        await handler.handle(event('Continuar'), context('continue'))
        answer = await handler.handle(event('¿Cuál de esos clientes compró menos y cuánto?'), context('followup'))
        assert answer.classification == 'DIRECT_AVAILABLE'
        assert 'Cliente B' in answer.text and 'Bs 9,25' in answer.text
        assert latest(handler.store)['capability_calls'] == 0
        assert latest(handler.store)['research']['sql_executions'] == 0
        assert researcher.checks >= 2
        view = research_presentation(saved(), ['owner'], 'conversation')
        assert interpreter_context(view)['rows'] == view['rows']
    asyncio.run(run())


def test_new_query_detaches_previous_analysis():
    async def run():
        researcher = Researcher()
        handler = build([selection()], researcher)
        handler.store = Store()
        await handler.handle(event('Nueva consulta'), context('new'))
        answer = await handler.handle(event('El último'), context('followup'))
        assert answer.classification == 'NEEDS_CLARIFICATION'
        assert 'Cliente B' not in answer.text
    asyncio.run(run())


def test_revoked_records_are_not_disclosed():
    async def run():
        researcher = Researcher()
        researcher.allowed = False
        handler = build([selection()], researcher)
        answer = await handler.handle(event('El último'), context())
        assert answer.classification == 'NEEDS_CLARIFICATION'
        assert 'Cliente B' not in answer.text
    asyncio.run(run())


def test_revocation_during_interpretation_and_cached_replay():
    async def run():
        researcher = Researcher()
        handler = build([selection()], researcher)
        original = handler.interpreter.interpret
        async def revoke(**kwargs):
            proposal = await original(**kwargs)
            researcher.allowed = False
            return proposal
        handler.interpreter.interpret = revoke
        answer = await handler.handle(event('El de menor venta'), context())
        assert answer.classification == 'DENIED' and 'Cliente B' not in answer.text
        researcher.allowed = True
        handler = build([selection()], researcher)
        first = await handler.handle(event('El último'), context())
        assert first.classification == 'DIRECT_AVAILABLE'
        researcher.allowed = False
        replay = await handler.handle(event('El último'), context())
        assert replay.classification == 'DENIED' and 'Cliente B' not in replay.text
    asyncio.run(run())


def test_partial_or_ambiguous_lists_cannot_be_selected():
    for change in ('truncated', 'multiple', 'oversized'):
        value = deepcopy(saved())
        if change == 'truncated':
            value['full_result']['results'][0]['truncated'] = True
        elif change == 'multiple':
            value['full_result']['evidence_manifests'] *= 2
        else:
            value['full_result']['results'][0]['rows'] *= 2501
        assert research_presentation(value, ['owner'], 'conversation') is None
