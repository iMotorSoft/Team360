"""Controlled integration at real module boundaries; never WhatsApp E2E."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from functools import wraps
from types import SimpleNamespace
import json

import httpx
import pytest

from modules.messaging.domain.messages import InboundMessage
from modules.messaging.handlers import ChannelContext, MessageContext, MessageDispatcher, SenderIdentity
from modules.messaging.repository import ChannelBinding
from modules.messaging.providers.evolution.mapper import normalize_events
from modules.messaging.service import MessagingService
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler, registration
from modules.telchi.assistant.luna import LunaInterpreter, LunaError, MODEL
from modules.telchi.datalake.messaging_sales_query import CAPABILITY


def run(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return wrapped


def proposal(sets=None, unset=None, action='EXECUTE', intent='REFINE', clarification=None):
    return dict(intent=intent, action=action, state_delta={'set': sets or {}, 'unset': unset or []}, clarification=clarification)


def plan():
    return dict(deepcopy(engine.EMPTY), metric='sales.source_top_items',
                period={'start': '2026-01-01', 'end_exclusive': '2026-09-16'})


def query_result():
    return dict(capability=CAPABILITY, read_only=True, sap_accessed=False,
                foundation_publication_id='fixture-publication', foundation_data_as_of='2026-09-16T01:00:00Z',
                ducklake_snapshot_id=5, period_from='2026-01-01', period_to_exclusive='2026-09-16',
                rows=[dict(item_code='fixture-item', quantity='12', line_total='999')])


class Interpreter:
    def __init__(self, proposals):
        self.proposals = iter(proposals)
        self.calls = []

    async def interpret(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return next(self.proposals)


class MemoryStore:
    """External PG double with atomic commits and per-conversation serialization."""
    def __init__(self):
        self.states, self.audits, self.history = {}, {}, {}
        self.lock = asyncio.Lock()
        self.fail_save = False

    @asynccontextmanager
    async def turn(self, context):
        async with self.lock:
            owner = [context.channel.environment, context.channel.tenant_id, context.channel.workspace_id,
                     context.channel.channel_id, context.sender_identity.user_id]
            key = tuple(owner) + (context.conversation_id,)
            yield dict(state=deepcopy(self.states.get(key, engine.EMPTY)), owner=owner, key=key,
                       history=deepcopy(self.history.get(key, {})), cached=self.audits.get((key, context.correlation_id)))

    async def save(self, context, turn, audit):
        if self.fail_save:
            raise RuntimeError('fixture commit failure')
        key = turn['key']
        self.audits[key, context.correlation_id] = deepcopy(audit)
        self.states[key] = deepcopy(audit['confirmed_state'])
        self.history.setdefault(key, {})[context.correlation_id] = deepcopy(audit['confirmed_state'])


def context():
    c = ChannelContext('channel', 'evolution', 'instance', 'receiver', 'telchi', 'workspace', 'telchi')
    i = SenderIdentity('user', 'telchi', 'workspace', permissions=frozenset({
        'fixture.business.read', 'telchi.sales.source_quantity.read.v1'}))
    return MessageContext(c, i, '123456789', 'conversation', 'turn-1', frozenset())


def event(text='hola', ident='m1'):
    return InboundMessage(provider='evolution', channel='whatsapp', external_message_id=ident,
                          sender='123456789', recipients=('receiver',), text_body=text,
                          external_thread_id=None, subject=None, received_at=datetime.now(timezone.utc), metadata={'provider_instance': 'instance'})


def setup(proposals):
    query_calls = []
    async def query(**kwargs):
        query_calls.append(kwargs)
        return query_result()
    auth = BusinessAuthorization(BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True))
    store, llm = MemoryStore(), Interpreter(proposals)
    handler = TelchiHandler(store=store, authorization=auth, interpreter=llm,
                           capabilities=SalesCapabilities(query=query))
    return handler, store, llm, query_calls


def latest(store):
    return list(store.audits.values())[-1]


@run
async def test_target_conversation_preserves_unavailable_requests():
    p = {'start': '2026-09-01', 'end_exclusive': '2026-10-01'}
    b = {'start': '2026-08-01', 'end_exclusive': '2026-09-01'}
    handler, store, llm, calls = setup([
        proposal({'/metric': 'sales.net_amount', '/period': p}, intent='NEW_QUERY'),
        proposal({'/branches': ['Saavedra']}), proposal({'/comparison': b}, intent='COMPARE'),
        proposal({'/sales_channel': 'HORIZONTAL'}),
    ])
    for n, text in enumerate(['¿Cuánto vendimos en septiembre?', '¿Y en Saavedra?', 'Comparalo con agosto.', 'Ahora solamente venta horizontal.']):
        result = await handler.handle(event(text), replace(context(), correlation_id=f'turn-{n}'))
        assert result.classification == ('DENIED' if n == 0 else 'DIRECT_UNAVAILABLE')
    state = latest(store)['confirmed_state']
    assert state['period'] == p and state['comparison'] == b
    assert state['branches'] == ['Saavedra'] and state['sales_channel'] == 'HORIZONTAL'
    assert not calls and latest(store)['execution_status'] == 'not_executed'
    assert llm.calls[-1]['state']['comparison'] == b


@run
async def test_ask_pending_answer_resume_and_single_execution():
    spec = {'slot': 'period', 'question': '¿Qué período querés consultar?'}
    handler, store, llm, calls = setup([
        proposal({'/metric': 'sales.source_top_items'}, action='ASK', intent='NEW_QUERY', clarification=spec),
        proposal({'/period': plan()['period']}, intent='ANSWER_CLARIFICATION'),
    ])
    result = await handler.handle(event(), context())
    assert result.classification == 'NEEDS_CLARIFICATION' and not calls
    assert latest(store)['confirmed_state']['metric'] is None
    assert latest(store)['confirmed_state']['pending']['proposed']['metric'] == 'sales.source_top_items'
    # A new handler instance resumes through the same external durable port.
    resumed = TelchiHandler(store=store, authorization=handler.authorization, interpreter=llm, capabilities=handler.capabilities)
    c = replace(context(), correlation_id='turn-2')
    result = await resumed.handle(event(), c)
    assert result.classification == 'DIRECT_AVAILABLE' and len(calls) == 1
    assert '999' not in result.text and 'no es facturación' in result.text
    assert latest(store)['confirmed_state']['pending'] is None
    assert latest(store)['execution_result']['source']['publication_id'] == 'fixture-publication'
    assert await resumed.handle(event(), c) == result
    assert len(calls) == 1 and len(llm.calls) == 2


@pytest.mark.parametrize('raw', [None, {}, proposal({'/unknown': 5}), proposal({'/period': {'start': '2026-09-30', 'end_exclusive': '2026-09-01'}}), proposal({'/metric': 'stock'}), proposal(action='ASK')])
@run
async def test_rejected_raw_execute_never_executes_previous_valid_plan(raw):
    handler, store, llm, calls = setup([proposal({'/metric': plan()['metric'], '/period': plan()['period']}), raw])
    await handler.handle(event(), context())
    calls.clear()
    result = await handler.handle(event(), replace(context(), correlation_id='turn-2'))
    assert result.classification == 'ERROR' and not calls
    audit = latest(store)
    assert audit['committed'] is False and audit['decision'] == 'EXECUTION_FORBIDDEN'
    assert audit['previous_state'] == audit['confirmed_state'] == plan()


@pytest.mark.parametrize('change', ['unknown', 'permission', 'tenant', 'workspace', 'environment', 'module', 'scope', 'enabled'])
@run
async def test_authorization_before_llm(change):
    handler, store, llm, calls = setup([proposal()])
    c = context()
    if change == 'unknown': c = replace(c, sender_identity=None)
    elif change == 'permission': c = replace(c, sender_identity=replace(c.sender_identity, permissions=frozenset()))
    elif change in {'tenant', 'workspace', 'environment'}:
        key = change if change == 'environment' else change + '_id'
        c = replace(c, sender_identity=replace(c.sender_identity, **{key: 'wrong'}))
    elif change == 'module': c = replace(c, channel=replace(c.channel, module='flow'))
    else:
        key = 'whole_workspace_scope_verified' if change == 'scope' else 'module_enabled'
        handler.authorization.policy = replace(handler.authorization.policy, **{key: False})
    assert (await handler.handle(event(), c)).classification == 'DENIED'
    assert not llm.calls and not calls and not store.audits


@pytest.mark.parametrize('sets,unset,expected', [
    ({'/branches': ['A']}, [], ['A']),  # override
    ({'/branches': ['Old', 'A']}, [], ['Old', 'A']),  # extend final set
    ({}, ['/branches'], []),  # remove
])
def test_override_extend_remove(sets, unset, expected):
    before = dict(plan(), branches=['Old'])
    after = engine.process(before, proposal(sets, unset), {}, 't')
    assert after['committed'] and after['state_after']['branches'] == expected
    assert after['state_after']['period'] == before['period']


def test_comparison_and_reference():
    old = dict(plan(), branches=['A'])
    before = dict(plan(), branches=['B'])
    out = engine.process(before, proposal({'/reference': 'first'}, intent='REFERENCE'), {'first': old}, 't')
    assert out['committed'] and out['state_after']['branches'] == ['A']
    assert not engine.process(before, proposal({'/reference': 'missing'}, intent='REFERENCE'), {}, 't')['committed']
    cmp = {'start': '2025-01-01', 'end_exclusive': '2025-09-16'}
    out = engine.process(before, proposal({'/comparison': cmp}), {}, 't')
    assert out['committed'] and out['state_after']['period'] == before['period']


@pytest.mark.parametrize('state,category', [
    (dict(plan(), branches=['Saavedra']), 'MAPPING_MISSING'),
    (dict(plan(), sales_channel='HORIZONTAL'), 'MAPPING_MISSING'),
    (dict(plan(), period={'start': '2026-10-01', 'end_exclusive': '2026-11-01'}), 'COVERAGE_GAP'),
    (dict(plan(), comparison=plan()['period']), 'CAPABILITY_MISSING'),
])
@run
async def test_catalog_blocks_only_unsupported_request(state, category):
    handler, store, llm, calls = setup([proposal({'/' + k: v for k, v in state.items() if k != 'pending'})])
    result = await handler.handle(event(), context())
    assert result.classification == 'DIRECT_UNAVAILABLE' and not calls
    assert latest(store)['bmd']['category'] == category


@pytest.mark.parametrize('field,value', [('read_only', False), ('sap_accessed', True), ('foundation_publication_id', None),
                                         ('foundation_data_as_of', None), ('period_from', 'wrong'), ('ducklake_snapshot_id', None), ('rows', None)])
@run
async def test_safe_foundation_errors(field, value):
    handler, store, llm, calls = setup([proposal({'/metric': plan()['metric'], '/period': plan()['period']})])
    async def broken(**kwargs):
        return dict(query_result(), **{field: value})
    handler.capabilities.query = broken
    result = await handler.handle(event(), context())
    assert result.classification == 'ERROR' and 'Foundation verificable' in result.text
    assert latest(store)['execution_status'] == 'failed' and latest(store)['confirmed_state'] == engine.EMPTY


@run
async def test_analysis_future_does_not_start_jobs():
    handler, store, llm, calls = setup([proposal(action='ANALYSIS_UNAVAILABLE')])
    result = await handler.handle(event(), context())
    assert result.classification == 'ANALYSIS_UNAVAILABLE' and 'todavía no está disponible' in result.text
    assert not calls and latest(store)['bmd']['category'] == 'ANALYSIS_REQUESTED'


@run
async def test_concurrent_retry_one_execution():
    handler, store, llm, calls = setup([proposal({'/metric': plan()['metric'], '/period': plan()['period']})])
    results = await asyncio.gather(handler.handle(event(), context()), handler.handle(event(), context()))
    assert results[0] == results[1] and len(calls) == len(llm.calls) == 1


@run
async def test_timeout_does_not_commit():
    handler, store, llm, calls = setup([])
    async def stuck(**kwargs):
        await asyncio.sleep(1)
    llm.interpret = stuck
    handler.turn_timeout_seconds = 0.01
    assert (await handler.handle(event(), context())).classification == 'ERROR'
    assert not store.audits and not calls


@run
async def test_luna_real_http_contract_with_transport_double(monkeypatch):
    monkeypatch.setenv('OpenAI_Key_JAI_query', 'fixture-key')
    def respond(request):
        body = json.loads(request.content)
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert body['model'] == MODEL and body['reasoning'] == {'effort': 'medium'} and body['store'] is False
        return httpx.Response(200, json={'model': MODEL, 'reasoning': {'effort': 'medium'}, 'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(proposal())}]}]})
    luna = LunaInterpreter(transport=httpx.MockTransport(respond))
    assert await luna.interpret(text='hola', state=plan(), history={}, turn_id='t') == proposal()
    monkeypatch.delenv('OpenAI_Key_JAI_query')
    with pytest.raises(LunaError, match='credential_unavailable'):
        await luna.interpret(text='hola', state=plan(), history={}, turn_id='t')


class TransportStore:
    """PG transport double only; MessagingService and dispatcher are real."""
    def __init__(self):
        self.claims, self.intents, self.results = {}, {}, {}
        self.interrupt_intent = False
    async def claim(self, conn, binding, event, timings):
        key = event.external_message_id
        if key in self.claims: return None
        self.claims[key] = {'id': key, 'thread_id': 'conversation'}
        return self.claims[key]
    async def complete_dispatch(self, conn, binding, claimed, result):
        self.results[claimed['id']] = result
    async def intent(self, conn, binding, claimed, event, text, timings):
        if self.interrupt_intent: raise RuntimeError('interrupted outbound commit')
        self.intents[claimed['id']] = dict(id=claimed['id'], contact_identity=event.sender,
            payload_jsonb={'text': text, 'timings': timings}, sent=False)
        return claimed['id']
    async def begin_send(self, conn, binding, outbound_id, retry=False):
        row = self.intents[outbound_id]
        if row['sent']: return False
        row['sent'] = True
        return True
    async def recoverable_intent(self, conn, binding, event):
        return self.intents.get(event.external_message_id)
    async def lock_receipt(self, *args): pass
    async def finish(self, *args, **kwargs): pass


@pytest.mark.parametrize('identity_case', ['authorized', 'unknown', 'permission', 'tenant', 'workspace', 'failure'])
@run
async def test_evolution_messaging_handler_outbound_and_duplicates(monkeypatch, identity_case):
    @asynccontextmanager
    async def tx(pool): yield object()
    monkeypatch.setattr('modules.messaging.service.transaction', tx)
    handler, store, llm, calls = setup([proposal({'/metric': plan()['metric'], '/period': plan()['period']})])
    c = context()
    class Identities:
        async def resolve(self, channel, phone):
            if identity_case == 'failure': raise RuntimeError('identity unavailable')
            if identity_case == 'unknown': return None
            if identity_case == 'permission': return replace(c.sender_identity, permissions=frozenset())
            if identity_case in {'tenant', 'workspace'}:
                return replace(c.sender_identity, **{identity_case + '_id': 'wrong'})
            return c.sender_identity
    dispatcher = MessageDispatcher(channels=(c.channel,), handlers={'telchi': registration(handler)}, identities=Identities())
    transport_store, sends = TransportStore(), []
    def send(**kwargs):
        sends.append(kwargs)
        return SimpleNamespace(external_message_id='receipt')
    binding = ChannelBinding('workspace', 'channel', 'provider', 'instance', 'dev', 'telchi', 'tenant', 'receiver')
    service = MessagingService(pool=object(), repository=transport_store, binding=binding,
        sender=SimpleNamespace(send_text=send), authorized_sender='', dispatcher=dispatcher)
    payload = {'event': 'messages.upsert', 'instance': 'instance', 'data': {
        'key': {'id': 'm1', 'remoteJid': '123456789@s.whatsapp.net', 'fromMe': False},
        'message': {'conversation': 'Top productos por cantidad del 1 enero al 15 septiembre 2026'}}}
    inbound = normalize_events(payload, instance='instance', recipient='receiver', received_at=datetime.now(timezone.utc))[0]
    assert await service.process(inbound, t0_ms=0, t1_ms=1) == 'accepted'
    assert await service.process(inbound, t0_ms=0, t1_ms=1) == 'duplicate'
    assert len(transport_store.intents) == len(sends) == 1
    if identity_case == 'authorized':
        assert len(calls) == len(llm.calls) == 1
        assert transport_store.results['m1'].classification == 'DIRECT_AVAILABLE'
    else:
        assert not calls and not llm.calls
        assert transport_store.results['m1'].classification in {'ERROR', 'DENIED'}


@run
async def test_permission_rechecked_with_existing_console_repository(monkeypatch):
    auth = BusinessAuthorization(BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True))
    calls = []
    async def denied(self, conn, workspace, user):
        calls.append((workspace, user))
        return []
    monkeypatch.setattr('modules.console.repositories.PermissionConsoleRepository.list_effective_permissions', denied)
    assert not await auth.allowed(context(), object())
    assert calls == [('workspace', 'user')]
