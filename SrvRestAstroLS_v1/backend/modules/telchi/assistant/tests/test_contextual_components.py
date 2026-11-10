"""WhatsApp dispatcher -> handler -> actual repository serialization, no outbound.

Identity, SQL connection and Foundation execution are deterministic ports here;
Luna can additionally be exercised live without writing operational PostgreSQL.
"""
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from modules.messaging.handlers import MessageDispatcher
from modules.telchi.assistant import monetary_comparison as mc
from modules.telchi.assistant.handler import registration
from modules.telchi.datalake import sales_query
from .test_assistant import event, proposal, run
from .test_result_references import persistent_handler
from .test_conversational_quality import FIXTURE, OWNER

QUESTIONS = ['¿Cuánto facturamos en octubre de 2026?', 'continuar',
             '¿Qué porcentaje representan esas notas de crédito sobre lo facturado?',
             '¿Y qué porcentaje queda neto después de esas notas de crédito?']


def monetary_result():
    result = deepcopy(FIXTURE[1]['audit']['execution_result'])
    result['period'].update(date_from='2026-10-01', date_to_exclusive='2026-11-01')
    result['sql_parameters'] = sales_query.parameters(mc.MONETARY_OPERATION, result['period'])
    result['source']['updated_at'] = '2026-11-04T00:00:00'
    result['rows'][0].update(billed_amount='11982896.13', credit_amount='479145.78', net_amount='11503750.35')
    return result


def component(field='credit_amount', mode='ratio_percent', ident='turn-1'):
    return dict(intent='MONETARY_COMPARISON', action='CALCULATE', clarification=None,
        comparison=dict(target_id=ident, baseline_id=ident, target_field=field,
                        baseline_field='billed_amount', mode=mode))


def setup_dispatch(monkeypatch, proposals):
    monkeypatch.setattr(sales_query, 'PUBLICATION', monetary_result()['source']['publication_id'])
    handler, db, llm, calls, checks, c = persistent_handler(monkeypatch, proposals)
    original_execute = db.execute
    async def execute(sql, params=None):
        result = await original_execute(sql, params)
        if 'DESC LIMIT 20' in sql:
            result.rows = [dict(result_id=ident, audit=deepcopy(db.events[ident]['telchi_assistant_v1']))
                           for ident in reversed(params[4]) if ident in db.events]
        return result
    async def fetchall():
        return db.rows
    db.execute, db.fetchall = execute, fetchall
    async def query(state):
        calls.append(deepcopy(state))
        return monetary_result()
    handler.capabilities.execute = query
    async def allowed(ctx, conn=None, *, required_permission=None):
        checks.append(required_permission)
        return required_permission in (None, mc.MONETARY_PERMISSION)
    handler.authorization.allowed = allowed
    class Identities:
        async def resolve(self, channel, sender):
            return c.sender_identity
    dispatcher = MessageDispatcher(channels=(c.channel,), handlers={'telchi': registration(handler)}, identities=Identities())
    async def dispatch(text, n):
        return await dispatcher.dispatch(event(text, ident=f'm{n}'), channel_id=c.channel.channel_id,
            conversation_id=c.conversation_id, correlation_id=f'turn-{n}')
    return handler, db, llm, calls, checks, dispatch


def durable_runtime(monkeypatch, dispatch):
    """Real DurableWorker with isolated inbox/outbound SQL ports; zero network sends."""
    from modules.messaging.durable import DurableWorker
    from modules.messaging.repository import ChannelBinding
    rows, intents, sends = {}, {}, []
    @asynccontextmanager
    async def transaction(_):
        yield None
    monkeypatch.setattr('modules.messaging.durable.transaction', transaction)
    class Inbox:
        async def candidates(self, conn, binding):
            return [dict(id=k, thread_id='conversation') for k,v in rows.items()
                    if v['payload_jsonb']['durable_job']['state'] != 'OUTBOUND_ACCEPTED'][:1]
        async def lock(self, *args): return True
        async def load(self, conn, binding, ident): return rows[ident]
        async def state(self, conn, binding, ident, state, **kw):
            rows[ident]['payload_jsonb']['durable_job']['state'] = state
    class Repo:
        async def recoverable_intent(self, conn, binding, message):
            return intents.get(message.external_message_id)
        async def complete_dispatch(self, *args): pass
        async def intent(self, conn, binding, claimed, message, text, timings):
            ident = claimed['id']
            intents[ident] = dict(id=ident, status='pending', payload_jsonb=dict(text=text, initial_result='dispatch_intent'))
            return ident
        async def cancel_outbound(self, conn, binding, ident):
            intents[ident]['status'] = 'canceled'
    class Dispatcher:
        async def dispatch(self, message, **kwargs):
            return await dispatch(message.text_body, int(kwargs['correlation_id'].split('-')[-1]))
    async def send(ident, sender, text, timings):
        sends.append(dict(id=ident, text=text))
        intents[ident]['status'] = 'completed'
        return 'accepted'
    service = SimpleNamespace(pool=None, durable=True, repository=Repo(), dispatcher=Dispatcher(),
        binding=ChannelBinding('workspace','channel','provider','instance','dev','telchi','telchi','receiver'),
        _send_horizontal=send)
    worker = DurableWorker(service, repository=Inbox())
    async def enqueue(text, n):
        ident = f'turn-{n}'
        message = event(text, ident)
        rows[ident] = dict(id=ident, thread_id='conversation', provider_message_id=ident,
            occurred_at_utc=message.received_at, payload_jsonb=dict(provider='evolution',channel='whatsapp',
                sender=message.sender,recipients=['receiver'],text=text,metadata=message.metadata,
                timings={},durable_job={'state':'QUEUED'}))
        assert await worker.tick()
        assert not await worker.tick()  # no second intent or duplicate answer
        return sends[-1]
    return enqueue, sends


def initial():
    return proposal({'/metric': 'sales.net_amount', '/period': {'start':'2026-10-01',
                    'end_exclusive':'2026-11-01'}}, intent='NEW_QUERY')


@run
async def test_exact_whatsapp_dispatch_sequence_and_replay(monkeypatch):
    handler, db, llm, calls, checks, dispatch = setup_dispatch(monkeypatch,
        [initial(), component(), component('net_amount')])
    for n, text in enumerate(QUESTIONS, 1):
        response = await dispatch(text, n)
        assert response.classification == ('NEEDS_CLARIFICATION' if n == 2 else 'DIRECT_AVAILABLE'), response.text
        if n == 3:
            assert '4,00 %' in response.text
        if n == 4:
            assert '96,00 %' in response.text
    assert len(llm.calls) == 3 and len(calls) == 1
    ctx = llm.calls[1]['monetary_context']
    assert ctx['results'][0]['fields'] == ['billed_amount','credit_amount','net_amount']
    assert '11982896' not in str(llm.calls)
    assert llm.calls[2]['monetary_context']['previous']['target_field'] == 'credit_amount'
    for n in (3, 4):
        a = db.events[f'turn-{n}']['telchi_assistant_v1']
        assert a['decision'] == 'LOCAL_CALCULATION' and a['capability_calls'] == 0
        assert a['monetary_calculation']['formula'] == 'target / baseline * 100'
        assert a['confirmed_state'] == db.events['turn-1']['telchi_assistant_v1']['confirmed_state']
    replay = await dispatch(QUESTIONS[-1], 4)
    assert replay == response and len(llm.calls) == 3 and len(calls) == 1
    async def revoked(ctx, conn=None, *, required_permission=None):
        return required_permission is None
    handler.authorization.allowed = revoked
    assert (await dispatch(QUESTIONS[-1], 4)).classification == 'DENIED'
    assert (await dispatch(QUESTIONS[2], 5)).classification != 'DIRECT_AVAILABLE'
    assert len(calls) == 1


@run
async def test_exact_durable_worker_sequence(monkeypatch):
    handler, db, llm, calls, checks, dispatch = setup_dispatch(monkeypatch,
        [initial(), component(), component('net_amount')])
    enqueue, sends = durable_runtime(monkeypatch, dispatch)
    for n, text in enumerate(QUESTIONS, 1):
        await enqueue(text, n)
    assert len(sends) == 4 and len(llm.calls) == 3 and len(calls) == 1
    assert '4,00 %' in sends[2]['text'] and '96,00 %' in sends[3]['text']


@run
async def test_revocation_during_interpretation(monkeypatch):
    handler, db, llm, calls, checks, dispatch = setup_dispatch(monkeypatch, [initial()])
    await dispatch(QUESTIONS[0], 1)
    async def interpret(**kwargs):
        async def revoked(ctx, conn=None, *, required_permission=None):
            return required_permission is None
        handler.authorization.allowed = revoked
        return component()
    handler.interpreter.interpret = interpret
    assert (await dispatch(QUESTIONS[2], 2)).classification == 'DENIED'
    assert len(calls) == 1


@run
async def test_missing_context_and_truly_unavailable_analysis(monkeypatch):
    handler, db, llm, calls, checks, dispatch = setup_dispatch(monkeypatch,
        [component(), proposal(action='ANALYSIS_UNAVAILABLE', intent='EXPLAIN')])
    result = await dispatch(QUESTIONS[2], 1)
    assert result.classification == 'NEEDS_CLARIFICATION'
    result = await dispatch('Pronosticá la facturación del próximo año', 2)
    assert result.classification == 'ANALYSIS_UNAVAILABLE'
    assert not calls


@pytest.mark.parametrize('mutation', ['owner','zero','unknown','missing','different_result','nonfinite','extra','category'])
def test_component_fences(monkeypatch, mutation):
    monkeypatch.setattr(sales_query, 'PUBLICATION', monetary_result()['source']['publication_id'])
    audit = deepcopy(FIXTURE[1]['audit'])
    audit['confirmed_state']['period'] = {'start':'2026-10-01','end_exclusive':'2026-11-01'}
    audit['execution_result'] = monetary_result()
    r = mc.accredited(audit, 'turn-1', OWNER)
    assert r
    p = component()
    if mutation == 'owner': r['owner'] = []
    elif mutation == 'zero': r['components']['billed_amount'] = '0'
    elif mutation == 'unknown': p['comparison']['target_field'] = 'profit'
    elif mutation == 'missing': p['comparison']['target_id'] = p['comparison']['baseline_id'] = 'missing'
    elif mutation == 'different_result': p['comparison']['baseline_id'] = 'other'
    elif mutation == 'nonfinite': r['components']['credit_amount'] = 'NaN'
    elif mutation == 'extra': p['comparison']['amount'] = 5
    elif mutation == 'category': r['capability'] = 'sales.category_line_amount.v1'
    with pytest.raises((ValueError, KeyError)):
        mc.calculate(p, [r], OWNER)
