"""Srv05 composition with inert baseline lifecycle; no operational writes."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from litestar.testing import TestClient
from test_srv05_evolution_isolation import composition, ENV
from test_messaging_horizontal_runtime import Store, Sender, transaction_double
from test_messaging_evolution import payload
from modules.messaging.repository import ChannelBinding
from modules.messaging.handlers import SenderIdentity
from modules.messaging.handlers import HandlerRegistration, MessageResult


class Handler:
    def __init__(self):
        self.contexts = []

    async def handle(self, message, context):
        self.contexts.append(context)
        return MessageResult('fixture', context.correlation_id, 'DIRECT_AVAILABLE')


def registry():
    return {name: HandlerRegistration(Handler(), required_permissions=frozenset({'task.view'}))
            for name in ('telchi', 'flow')}


def test_horizontal_registry_installed_and_validated_before_scheduler(composition, monkeypatch):
    srv, _, events = composition
    monkeypatch.setenv('TEAM360_MESSAGING_DISPATCH_MODE', 'horizontal_v1')
    from modules.messaging.identity import PhoneIdentityRepository
    import modules.messaging.webhooks.evolution_whatsapp as webhook
    schema = AsyncMock()
    build = AsyncMock()
    monkeypatch.setattr(PhoneIdentityRepository, 'validate_schema', schema)
    monkeypatch.setattr(webhook, 'build_service', build)
    registrations = registry()
    app = srv.create_app(messaging_handlers=registrations)
    registrations.clear()
    with TestClient(app):
        assert set(app.state.messaging_handlers) == {'telchi', 'flow'}
        with pytest.raises(TypeError):
            app.state.messaging_handlers['other'] = HandlerRegistration(Handler())
        build.assert_awaited_once_with(app.state.srv05_settings.messaging,
                                      app.state.srv05_settings.evolution,
                                      handlers=app.state.messaging_handlers,
                                      transport_runtime=app.state.transport_v1)
        schema.assert_awaited_once()
    assert events == ['open', 'binding', 'schema', 'v1_start', 'start', 'v1_stop', 'stop', 'close']


@pytest.mark.parametrize('registrations', [{'telchi': object()},
    {'telchi': HandlerRegistration(Handler(), environment='pro',
                                   required_permissions=frozenset({'task.view'}))}])
def test_invalid_horizontal_registry_aborts_before_baseline(composition, monkeypatch, registrations):
    srv, _, events = composition
    monkeypatch.setenv('TEAM360_MESSAGING_DISPATCH_MODE', 'horizontal_v1')
    monkeypatch.setattr(srv, 'create_legacy_app', lambda **kw: pytest.fail('baseline reached'))
    with pytest.raises(ValueError):
        srv.create_app(messaging_handlers=registrations)
    assert events == []


def test_horizontal_startup_failure_never_starts_scheduler_or_falls_back(composition, monkeypatch):
    srv, _, events = composition
    monkeypatch.setenv('TEAM360_MESSAGING_DISPATCH_MODE', 'horizontal_v1')
    from modules.messaging.identity import PhoneIdentityRepository
    import modules.messaging.webhooks.evolution_whatsapp as webhook
    monkeypatch.setattr(PhoneIdentityRepository, 'validate_schema', AsyncMock())
    monkeypatch.setattr(webhook, 'build_service', AsyncMock(side_effect=ValueError('mismatch')))
    with pytest.raises(ExceptionGroup):
        with TestClient(srv.create_app(messaging_handlers=registry())):
            pass
    assert 'start' not in events
    assert events[-2:] == ['stop', 'close']


@pytest.mark.parametrize('module,identity_case,invocations', [
    ('telchi', 'enabled', 1), ('telchi', 'unknown', 0), ('telchi', 'revoked', 0),
    ('telchi', 'tenant', 0), ('telchi', 'workspace', 0),
    ('flow', 'enabled', 1), ('flow', 'missing_entry_permission', 0),
])
def test_real_builder_webhook_dispatches_registry_without_legacy(
        composition, monkeypatch, module, identity_case, invocations):
    srv, _, events = composition
    monkeypatch.setenv('TEAM360_MESSAGING_DISPATCH_MODE', 'horizontal_v1')
    monkeypatch.setenv('META_TEAM360_PHONE_NUMBER_ID', 'receiver')
    from modules.messaging.repository import MessagingRepository
    from modules.messaging.identity import PhoneIdentityRepository, PostgresPhoneIdentityResolver
    from modules.messaging.handlers import InvalidIdentityBinding
    import modules.messaging.webhooks.evolution_whatsapp as webhook
    import modules.messaging.service as service_module
    binding = ChannelBinding('workspace', 'channel', 'provider', 'test-instance',
                             'dev', module, 'tenant', 'receiver')
    monkeypatch.setattr(MessagingRepository, 'binding', AsyncMock(return_value=binding))
    monkeypatch.setattr(PhoneIdentityRepository, 'validate_schema', AsyncMock())
    identity = SenderIdentity('user', 'other' if identity_case == 'tenant' else 'tenant',
        'other' if identity_case == 'workspace' else 'workspace',
        permissions=frozenset({'task.view'}) if module == 'flow' and identity_case == 'enabled'
        else frozenset())
    resolve = AsyncMock(return_value=None if identity_case == 'unknown' else identity)
    if identity_case == 'revoked':
        resolve.side_effect = InvalidIdentityBinding('revoked')
    monkeypatch.setattr(PostgresPhoneIdentityResolver, 'resolve', resolve)
    store, sender = Store(), Sender()
    store.binding = AsyncMock(return_value=binding)
    monkeypatch.setattr(webhook, 'MessagingRepository', lambda: store)
    monkeypatch.setattr(webhook, 'EvolutionProvider', lambda config: pytest.fail('Legacy fallback forbidden'))
    monkeypatch.setattr(webhook, 'transaction', transaction_double)
    monkeypatch.setattr(webhook, 'get_pool', lambda: object())
    monkeypatch.setattr(service_module, 'transaction', transaction_double)
    registrations = registry()
    # Telchi's existing contract admits authenticated identities without a base grant.
    registrations['telchi'] = HandlerRegistration(Handler())
    app = srv.create_app(messaging_handlers=registrations)
    app.state.transport_v1.provider = sender
    body = payload()
    body['instance'] = 'test-instance'
    with TestClient(app) as client:
        for expected in ('accepted', 'duplicate'):
            response = client.post('/webhooks/messaging/evolution/whatsapp', json=body,
                headers={'x-team360-webhook-token': ENV['TEAM360_MESSAGING_WEBHOOK_TOKEN']})
            assert response.status_code == 200
            assert response.json()['results'] == {expected: 1}
    assert len(registrations[module].handler.contexts) == invocations
    assert len(sender.calls) == 1
    if not invocations:
        assert next(iter(store.results.values())).classification == 'DENIED'
    assert not registrations[('flow' if module == 'telchi' else 'telchi')].handler.contexts
    if invocations:
        assert registrations[module].handler.contexts[0].channel.module == module
    assert events[-2:] == ['stop', 'close']


def test_empty_registry_is_importable_but_cannot_start_horizontal(composition, monkeypatch):
    srv, _, events = composition
    monkeypatch.setenv('TEAM360_MESSAGING_DISPATCH_MODE', 'horizontal_v1')
    from modules.messaging.identity import PhoneIdentityRepository
    from modules.messaging.repository import MessagingRepository
    import modules.messaging.webhooks.evolution_whatsapp as webhook
    monkeypatch.setenv('META_TEAM360_PHONE_NUMBER_ID', 'receiver')
    monkeypatch.setattr(MessagingRepository, 'binding', AsyncMock(return_value=
        ChannelBinding('workspace', 'channel', 'provider', 'test-instance',
                       'dev', 'telchi', 'tenant', 'receiver')))
    monkeypatch.setattr(PhoneIdentityRepository, 'validate_schema', AsyncMock())
    monkeypatch.setattr(webhook, 'transaction', transaction_double)
    monkeypatch.setattr(webhook, 'get_pool', lambda: object())
    with pytest.raises(ExceptionGroup):
        with TestClient(srv.create_app()):
            pass
    assert 'start' not in events


@pytest.mark.parametrize('mode,environment,receiver', [
    ('legacy', 'dev', 'receiver'), ('horizontal_v1', None, None),
    ('horizontal_v1', 'dev', 'wrong-receiver')])
def test_channel_runtime_mismatch_aborts_startup(composition, monkeypatch, mode, environment, receiver):
    srv, _, events = composition
    monkeypatch.setenv('TEAM360_MESSAGING_DISPATCH_MODE', mode)
    monkeypatch.setenv('META_TEAM360_PHONE_NUMBER_ID', 'receiver')
    from modules.messaging.repository import MessagingRepository
    monkeypatch.setattr(MessagingRepository, 'binding', AsyncMock(return_value=
        ChannelBinding('workspace', 'channel', 'provider', 'test-instance',
                       environment, 'telchi', 'tenant', receiver)))
    with pytest.raises(ExceptionGroup):
        with TestClient(srv.create_app(messaging_handlers=registry())):
            pass
    assert 'start' not in events
