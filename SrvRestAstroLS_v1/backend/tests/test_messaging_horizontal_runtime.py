"""Horizontal runtime contracts with doubles; not PG18 or WhatsApp E2E."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from modules.messaging.handlers import (
    ChannelContext, HandlerRegistration, MessageDispatcher, MessageResult, SenderIdentity,
)
from modules.messaging.identity import PhoneIdentityRepository, InvalidPhoneBinding
from modules.messaging.repository import ChannelBinding, MessagingRepository
from modules.messaging.service import MessagingService
from modules.messaging.domain.delivery import MessagingSendError
from modules.messaging.providers.evolution.mapper import normalize_events
from test_messaging_handlers import HandlerDouble, IdentityDouble, message, run_async


@asynccontextmanager
async def transaction_double(pool):
    yield object()


class Store:
    def __init__(self):
        self.claims = {}
        self.intents = {}
        self.results = {}
        self.crash_intent = False
        self.crash_finish = False
        self.counter = 0

    async def claim(self, conn, binding, event, timings):
        key = (binding.storage_instance, event.external_message_id)
        if key in self.claims:
            return None
        self.counter += 1
        self.claims[key] = {'id': str(self.counter), 'thread_id': binding.storage_instance + event.sender}
        return self.claims[key]

    async def complete_dispatch(self, conn, binding, claimed, result):
        self.results[claimed['id']] = result

    async def intent(self, conn, binding, claimed, event, text, timings):
        if self.crash_intent:
            raise RuntimeError('interrupted result commit')
        self.intents.setdefault(claimed['id'], {'id': claimed['id'], 'state': 'intent', 'contact_identity': event.sender,
                                                'payload_jsonb': {'text': text, 'timings': timings}})
        return claimed['id']

    async def recoverable_intent(self, conn, binding, event):
        claimed = self.claims.get((binding.storage_instance, event.external_message_id))
        return self.intents.get(claimed['id']) if claimed else None

    async def begin_send(self, conn, binding, outbound_id, retry=False):
        row = self.intents[outbound_id]
        if row['state'] == 'intent' or (retry and row['state'] == 'failed'):
            row['state'] = 'sending'
            return True
        return False

    async def lock_receipt(self, *args):
        pass

    async def finish(self, conn, outbound_id, receipt=None, error=None, timings=None):
        if self.crash_finish:
            raise RuntimeError('interrupted receipt commit')
        self.intents[outbound_id]['state'] = ('accepted' if receipt else
                                              'uncertain' if error.uncertain else 'failed')


class Sender:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def send_text(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(external_message_id='provider-receipt')


def setup(monkeypatch, *, module='telchi', identity=True, public=frozenset(), store=None):
    monkeypatch.setattr('modules.messaging.service.transaction', transaction_double)
    binding = ChannelBinding('workspace', module, 'provider', 'instance', 'dev', module, 'tenant', 'receiver')
    channel = ChannelContext(module, 'evolution', 'instance', 'receiver', 'tenant', 'workspace', module)
    handler = HandlerDouble()
    resolver = IdentityDouble(SenderIdentity('user', 'tenant', 'workspace', 'dev', frozenset({'test.access'}))
                              if identity else None)
    dispatcher = MessageDispatcher(channels=(channel,), identities=resolver, handlers={
        module: HandlerRegistration(handler, public, required_permissions=frozenset({'test.access'})),
    })
    sender, store = Sender(), store or Store()
    service = MessagingService(pool=object(), repository=store, binding=binding,
                               sender=sender, authorized_sender='unused', dispatcher=dispatcher,
                               telchi_capability=object(), tenant='telchi')
    return service, handler, resolver, sender, store, message(channel)


@pytest.mark.parametrize('module', ['telchi', 'flow'])
@run_async
async def test_runtime_horizontal_dispatch_and_dedup(monkeypatch, module):
    service, handler, resolver, sender, store, event = setup(monkeypatch, module=module)
    assert await service.process(event, t0_ms=0, t1_ms=1) == 'accepted'
    assert await service.process(event, t0_ms=0, t1_ms=1) == 'duplicate'
    assert len(handler.contexts) == len(sender.calls) == len(store.intents) == 1
    assert handler.contexts[0].sender_identity.permissions == frozenset({'test.access'})
    assert handler.contexts[0].conversation_id.startswith(service.binding.storage_instance)


@pytest.mark.parametrize('module,public,invocations', [
    ('telchi', frozenset(), 0), ('flow', frozenset({'general_information'}), 1),
])
@run_async
async def test_runtime_public_policy(monkeypatch, module, public, invocations):
    service, handler, resolver, sender, store, event = setup(monkeypatch, module=module, identity=False, public=public)
    assert await service.process(event, t0_ms=0, t1_ms=1) == 'accepted'
    assert len(handler.contexts) == invocations
    if not invocations:
        assert next(iter(store.results.values())).classification == 'DENIED'


@pytest.mark.parametrize('failure', ['permissions', 'pg', 'tenant', 'workspace', 'environment'])
@run_async
async def test_runtime_fail_closed(monkeypatch, failure):
    service, handler, resolver, sender, store, event = setup(monkeypatch)
    if failure == 'pg':
        resolver.fail = True
    elif failure == 'permissions':
        resolver.identity = replace(resolver.identity, permissions=frozenset())
    else:
        resolver.identity = replace(resolver.identity, **{failure if failure == 'environment' else failure + '_id': 'other'})
    await service.process(event, t0_ms=0, t1_ms=1)
    assert not handler.contexts
    assert next(iter(store.results.values())).classification in {'DENIED', 'ERROR'}


@run_async
async def test_interruption_after_claim_never_reexecutes(monkeypatch):
    store = Store()
    store.crash_intent = True
    service, handler, resolver, sender, store, event = setup(monkeypatch, store=store)
    with pytest.raises(RuntimeError):
        await service.process(event, t0_ms=0, t1_ms=1)
    store.crash_intent = False
    assert await service.process(event, t0_ms=0, t1_ms=1) == 'execution_uncertain'
    assert len(handler.contexts) == 1
    assert not sender.calls


@run_async
async def test_durable_intent_resumes_without_handler(monkeypatch):
    service, handler, resolver, sender, store, event = setup(monkeypatch)
    original = service._send_horizontal

    async def interrupt(*args, **kwargs):
        raise RuntimeError('process interrupted before sending')

    service._send_horizontal = interrupt
    with pytest.raises(RuntimeError):
        await service.process(event, t0_ms=0, t1_ms=1)
    service._send_horizontal = original
    results = await asyncio.gather(*(service.process(event, t0_ms=0, t1_ms=1) for _ in range(2)))
    assert sorted(results) == ['accepted', 'duplicate']
    assert len(handler.contexts) == len(sender.calls) == 1


@pytest.mark.parametrize('uncertain', [True, False])
@run_async
async def test_controlled_retry_only_known_failure(monkeypatch, uncertain):
    service, handler, resolver, sender, store, event = setup(monkeypatch)
    sender.error = MessagingSendError('provider_error', uncertain=uncertain)
    assert await service.process(event, t0_ms=0, t1_ms=1) == 'send_failed'
    assert await service.process(event, t0_ms=0, t1_ms=1) == 'duplicate'
    sender.error = None
    assert await service.recover_delivery(event, retry=True) == ('duplicate' if uncertain else 'accepted')
    assert len(handler.contexts) == 1
    assert len(sender.calls) == (1 if uncertain else 2)


@run_async
async def test_acceptance_commit_failure_not_retried(monkeypatch):
    service, handler, resolver, sender, store, event = setup(monkeypatch)
    store.crash_finish = True
    with pytest.raises(RuntimeError):
        await service.process(event, t0_ms=0, t1_ms=1)
    store.crash_finish = False
    assert await service.recover_delivery(event, retry=True) == 'duplicate'
    assert len(sender.calls) == len(handler.contexts) == 1


@pytest.mark.parametrize('module', ['telchi', 'flow'])
@run_async
async def test_dev_cannot_reach_prod_or_unknown_channel(module):
    channel = ChannelContext(module, 'evolution', 'instance', 'receiver', 'tenant', 'workspace', module, 'pro')
    handler, resolver = HandlerDouble(), IdentityDouble()
    dispatcher = MessageDispatcher(channels=(channel,), handlers={module: HandlerRegistration(handler)}, identities=resolver)
    for channel_id in (module, 'unknown'):
        result = await dispatcher.dispatch(message(channel), channel_id=channel_id,
                                           conversation_id='thread', correlation_id='inbound')
        assert result.classification == 'DENIED'
    assert not resolver.calls and not handler.contexts


@run_async
async def test_payload_environment_cannot_override_runtime(monkeypatch):
    service, handler, resolver, sender, store, event = setup(monkeypatch)
    event = replace(event, metadata={**event.metadata, 'environment': 'pro', 'module': 'flow'})
    assert await service.process(event, t0_ms=0, t1_ms=1) == 'accepted'
    assert handler.contexts[0].channel.environment == 'dev'
    assert handler.contexts[0].channel.module == 'telchi'


@pytest.mark.parametrize('change', ['instance', 'receiver', 'provider'])
@run_async
async def test_untrusted_transport_rejected_before_claim(monkeypatch, change):
    service, handler, resolver, sender, store, event = setup(monkeypatch)
    event = replace(event, **({'metadata': {'provider_instance': 'other'}} if change == 'instance' else
                              {'recipients': ('wrong-group',)} if change == 'receiver' else {'provider': 'other'}))
    assert await service.process(event, t0_ms=0, t1_ms=1) == 'ignored'
    assert not store.claims and not resolver.calls and not sender.calls


def test_groups_and_lid_require_separate_verified_normalization():
    for jid in ('group@g.us', '123456789@lid'):
        payload = {'event': 'messages.upsert', 'instance': 'instance', 'environment': 'pro',
                   'data': {'key': {'id': 'm', 'remoteJid': jid, 'fromMe': False},
                            'message': {'conversation': 'hola'}}}
        assert not normalize_events(payload, instance='instance', recipient='receiver', received_at=datetime.now(timezone.utc))


def test_horizontal_settings_no_allowlist_and_no_legacy_sql(monkeypatch):
    from modules.messaging.settings import MessagingDevSettings
    for name, value in {
        'TEAM360_ENV': 'development', 'TEAM360_MESSAGING_DEV_ENABLED': '1',
        'TEAM360_MESSAGING_WORKSPACE_SLUG': 'test-workspace', 'TEAM360_MESSAGING_CHANNEL_ALIAS': 'test-channel',
        'TEAM360_MESSAGING_WEBHOOK_TOKEN': 'fixture-token-not-a-real-secret-000000',
        'TEAM360_MESSAGING_DISPATCH_MODE': 'horizontal_v1',
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER', raising=False)
    monkeypatch.delenv('TEAM360_MESSAGING_DEV_SQL_TENANT', raising=False)
    assert MessagingDevSettings.from_env().authorized_sender == ''
    monkeypatch.setenv('TEAM360_MESSAGING_DEV_SQL_TENANT', 'telchi')
    with pytest.raises(ValueError, match='incompatible'):
        MessagingDevSettings.from_env()


def test_persistent_environment_and_channel_keys_disjoint():
    binding = ChannelBinding('workspace', 'telchi', 'provider', 'same-instance', 'dev')
    assert binding.storage_instance != replace(binding, environment='pro').storage_instance
    assert binding.storage_instance != replace(binding, channel_id='flow').storage_instance
    assert binding.storage_instance != replace(binding, tenant_id='other').storage_instance
    assert binding.storage_instance != replace(binding, workspace_id='other').storage_instance
    assert binding.storage_instance != replace(binding, module='other').storage_instance
    assert ChannelBinding('w', 'c', 'p', 'legacy').storage_instance == 'legacy'


class RowsConnection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    async def execute(self, sql, params):
        self.queries.append((sql, params))
        return self

    async def fetchall(self):
        return self.rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None


def phone_row():
    return dict(user_id='user', workspace_id='workspace', tenant_id='tenant', environment='dev',
                verification_status='verified', verified_at_utc=datetime.now(timezone.utc),
                verification_ref='operator-proof-reference', user_status='active', user_workspace_id='workspace')


@pytest.mark.parametrize('case', ['verified', 'unknown', 'revoked', 'ambiguous', 'inactive', 'workspace', 'tenant', 'environment', 'proof'])
@run_async
async def test_phone_repository_uses_existing_permissions(monkeypatch, case):
    row = phone_row()
    if case == 'revoked': row['verification_status'] = 'revoked'
    if case == 'inactive': row['user_status'] = 'inactive'
    if case == 'workspace': row['user_workspace_id'] = 'other'
    if case == 'tenant': row['tenant_id'] = 'other'
    if case == 'environment': row['environment'] = 'pro'
    if case == 'proof': row['verification_ref'] = None
    rows = [] if case == 'unknown' else [row, row] if case == 'ambiguous' else [row]
    conn = RowsConnection(rows)
    calls = []

    async def permissions(self, conn, workspace, user):
        calls.append((workspace, user))
        return ['test.access']

    monkeypatch.setattr('modules.messaging.identity.PermissionConsoleRepository.list_effective_permissions', permissions)
    channel = ChannelContext('c', 'evolution', 'instance', 'receiver', 'tenant', 'workspace', 'telchi')
    if case not in {'verified', 'unknown'}:
        with pytest.raises(InvalidPhoneBinding):
            await PhoneIdentityRepository().resolve(conn, channel, '123456789')
        assert not calls
    else:
        result = await PhoneIdentityRepository().resolve(conn, channel, '123456789')
        assert (result is None) == (case == 'unknown')
        if result: assert result.permissions == frozenset({'test.access'})
    assert conn.queries[0][1] == ('dev', 'evolution', '123456789', 'tenant', 'workspace')


@run_async
async def test_duplicate_cannot_redirect_persisted_response(monkeypatch):
    service, handler, resolver, sender, store, event = setup(monkeypatch)
    await service.process(event, t0_ms=0, t1_ms=1)
    assert await service.recover_delivery(replace(event, sender='other'), retry=True) == 'ignored'
    assert len(sender.calls) == 1


@run_async
async def test_production_handler_registration_rejected_before_identity():
    channel = ChannelContext('c', 'evolution', 'i', 'r', 't', 'w', 'telchi')
    handler, resolver = HandlerDouble(), IdentityDouble(fail=True)
    dispatcher = MessageDispatcher(channels=(channel,), identities=resolver,
        handlers={'telchi': HandlerRegistration(handler, environment='pro')})
    result = await dispatcher.dispatch(message(channel), channel_id='c', conversation_id='t', correlation_id='e')
    assert result.classification == 'DENIED'
    assert not resolver.calls


@pytest.mark.parametrize('metadata', [
    {'dispatcher': 'horizontal_v1', 'environment': 'pro', 'module': 'telchi', 'tenant_id': 't', 'receiver_context': 'r'},
    {'dispatcher': 'horizontal_v1', 'environment': 'dev'},
    {'dispatcher': 'unknown'},
])
@run_async
async def test_binding_incomplete_or_wrong_environment_fails_closed(metadata):
    conn = RowsConnection([dict(workspace_id='w', channel_id='c', provider_id='p', metadata_jsonb=metadata)])
    with pytest.raises(ValueError):
        await MessagingRepository().binding(conn, workspace_slug='w', channel_alias='c', provider='evolution', instance='i')


@pytest.mark.parametrize('mode,channel_horizontal,registered,works', [
    ('horizontal_v1', True, True, True), ('horizontal_v1', True, False, False),
    ('horizontal_v1', False, True, False), ('legacy', True, True, False),
])
@run_async
async def test_webhook_builds_horizontal_service_without_sql_import(monkeypatch, mode, channel_horizontal, registered, works):
    from modules.messaging.webhooks import evolution_whatsapp as webhook
    binding = ChannelBinding('w', 'c', 'p', 'i', **(
        dict(environment='dev', module='telchi', tenant_id='t', receiver_context='r') if channel_horizontal else {}))

    async def lookup(*args, **kwargs):
        return binding

    monkeypatch.setattr(MessagingRepository, 'binding', lookup)
    monkeypatch.setattr(webhook, 'transaction', transaction_double)
    monkeypatch.setattr(webhook, 'get_pool', lambda: object())
    settings = SimpleNamespace(workspace_slug='w', channel_alias='c', dispatch_mode=mode,
                               authorized_sender='', telchi_tenant=None)
    registration = HandlerRegistration(HandlerDouble(), required_permissions=frozenset({'approved.permission'}))
    handlers = {'telchi': registration} if registered else {}
    if works:
        service = await webhook.build_service(settings, SimpleNamespace(instance='i'), handlers=handlers)
        assert service.dispatcher and service.telchi_capability is None
    else:
        with pytest.raises(ValueError):
            await webhook.build_service(settings, SimpleNamespace(instance='i'), handlers=handlers)


@run_async
async def test_phone_database_error_propagates_not_anonymous():
    class Unavailable:
        async def execute(self, *args):
            raise RuntimeError('database unavailable')

    channel = ChannelContext('c', 'evolution', 'i', 'r', 't', 'w', 'telchi')
    with pytest.raises(RuntimeError):
        await PhoneIdentityRepository().resolve(Unavailable(), channel, '123456789')


@run_async
async def test_repository_sql_uses_scoped_transport_key():
    repository = MessagingRepository()
    from uuid import uuid4
    workspace, channel, outbound = (str(uuid4()) for _ in range(3))
    binding = ChannelBinding(workspace, channel, 'p', 'instance', 'dev')
    conn = RowsConnection([{'id': outbound}])
    assert await repository.begin_send(conn, binding, outbound)
    assert conn.queries[-1][1][1:] == (outbound, workspace, channel, binding.storage_instance, False)
    assert conn.queries[-1][1][0].obj['outbound_intent_id'] == outbound
    await repository.recoverable_intent(conn, binding, SimpleNamespace(external_message_id='inbound'))
    assert conn.queries[-1][1] == (channel, binding.storage_instance, 'inbound')
