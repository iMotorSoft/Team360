"""Execution fence, crash recovery and contract safety at real boundaries."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from modules.messaging.handlers import MessageDispatcher
from modules.messaging.repository import ChannelBinding
from modules.messaging.service import MessagingService
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.handler import registration
from modules.telchi.assistant.luna import LunaInterpreter, LunaError, strict_json
from .test_assistant import setup, context, event, plan, proposal, TransportStore, run, latest


@pytest.mark.parametrize('commit', [False, None, 0, 'true'])
@run
async def test_commit_must_be_literal_true(commit):
    handler, store, llm, calls = setup([proposal()])
    handler.engine = lambda *args: dict(committed=commit, output=proposal(), state_after=plan())
    result = await handler.handle(event(), context())
    assert result.classification == 'ERROR' and not calls
    assert latest(store)['decision'] == 'EXECUTION_FORBIDDEN'


@pytest.mark.parametrize('delta', [
    {'set': {'/metric': 'sales.net_amount', 'metric': 'sales.source_top_items'}, 'unset': []},
    {'set': {'period': plan()['period']}, 'unset': ['/period']},
    {'set': {}, 'unset': ['/period', 'period']},
])
def test_atomic_path_conflicts_not_repaired(delta):
    p = proposal()
    p['state_delta'] = delta
    assert not engine.process(plan(), p, {}, 't')['committed']


def test_path_serialization_and_explanation_safety():
    p = proposal({'metric': 'sales.net_amount'})
    assert engine.process(plan(), p, {}, 't')['committed']
    assert not engine.process(plan(), proposal(intent='EXPLAIN'), {}, 't')['committed']


def test_pending_stale_binding_and_new_independent_request():
    spec = dict(slot='period', question='¿Qué año?')
    before = engine.process(plan(), proposal(action='ASK', clarification=spec), {}, 'a')['state_after']
    stale = dict(before, branches=['changed'])
    assert not engine.process(stale, proposal(intent='ANSWER_CLARIFICATION'), {}, 'b')['committed']
    out = engine.process(before, proposal(intent='NEW_QUERY'), {}, 'b')
    assert out['committed'] and out['state_after']['pending'] is None


@run
async def test_crash_after_state_commit_before_outbound_never_reexecutes(monkeypatch):
    @asynccontextmanager
    async def tx(pool): yield object()
    monkeypatch.setattr('modules.messaging.service.transaction', tx)
    handler, store, llm, calls = setup([proposal({'/metric': plan()['metric'], '/period': plan()['period']})])
    c = context()
    class Identities:
        async def resolve(self, *args): return c.sender_identity
    dispatcher = MessageDispatcher(channels=(c.channel,), identities=Identities(), handlers={'telchi': registration(handler)})
    transport = TransportStore()
    transport.interrupt_intent = True
    sends = []
    def send(**kwargs):
        sends.append(kwargs)
        return SimpleNamespace(external_message_id='receipt')
    binding = ChannelBinding('workspace', 'channel', 'provider', 'instance', 'dev', 'telchi', 'tenant', 'receiver')
    service = MessagingService(pool=object(), repository=transport, binding=binding,
        sender=SimpleNamespace(send_text=send), authorized_sender='', dispatcher=dispatcher)
    with pytest.raises(RuntimeError, match='interrupted outbound'):
        await service.process(event(), t0_ms=0, t1_ms=1)
    transport.interrupt_intent = False
    assert await service.process(event(), t0_ms=0, t1_ms=1) == 'execution_uncertain'
    assert len(calls) == len(llm.calls) == len(store.audits) == 1 and not sends
    assert latest(store)['execution_status'] == 'executed'


@run
async def test_state_commit_failure_does_not_return_prepared_success():
    handler, store, llm, calls = setup([proposal({'/metric': plan()['metric'], '/period': plan()['period']})])
    store.fail_save = True
    result = await handler.handle(event(), context())
    assert result.classification == 'ERROR' and not store.states and not store.audits
    assert len(calls) == 1  # read happened; not falsely persisted as executed


@pytest.mark.parametrize('status', [301, 401, 403, 429, 500])
@run
async def test_provider_failure_no_model_fallback(monkeypatch, status):
    monkeypatch.setenv('OpenAI_Key_JAI_query', 'fixture-key')
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={'Location': 'https://example.invalid/'})
    interpreter = LunaInterpreter(transport=httpx.MockTransport(respond))
    with pytest.raises(LunaError) as failure:
        await interpreter.interpret(text='consulta controlada', state=plan(), history={}, turn_id='t')
    assert interpreter.last_metadata is None
    # No fallback and no model swap: only the same request may be repeated,
    # and only once, and only for a transient failure.
    transient = status in {429, 500}
    assert len(calls) == (2 if transient else 1)
    assert failure.value.code in ('provider_rate_limited', 'provider_server_error',
                                   'provider_client_error')
    assert failure.value.status == status
    assert interpreter.last_failure['status'] == status
    assert interpreter.last_failure['attempts'] == len(calls)


@pytest.mark.parametrize('text', ['{"action":"ASK","action":"EXECUTE"}', '{"v":NaN}', '{"v":Infinity}'])
def test_strict_json(text):
    with pytest.raises(ValueError): strict_json(text)
