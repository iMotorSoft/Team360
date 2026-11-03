"""A–F isolation contracts. No live provider, mail or database access."""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from litestar.testing import TestClient
from test_srv05_compatibility import _check

PATH = '/webhooks/messaging/evolution/whatsapp'
ENV = {
    'TEAM360_ENV': 'development', 'TEAM360_SRV05_EVOLUTION_ENABLED': '1',
    'TEAM360_MESSAGING_DEV_ENABLED': '1',
    'TEAM360_EVOLUTION_BASE_URL': 'http://127.0.0.1:9',
    'TEAM360_EVOLUTION_INSTANCE': 'test-instance', 'TEAM360_EVOLUTION_API_KEY': 'synthetic-key',
    'TEAM360_MESSAGING_WORKSPACE_SLUG': 'test-workspace',
    'TEAM360_MESSAGING_CHANNEL_ALIAS': 'test-channel',
    'TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER': '15550000001',
    'TEAM360_MESSAGING_WEBHOOK_TOKEN': 'synthetic-webhook-token-0000000000000000',
    'AUTOMATION_DIAGNOSIS_REPOSITORY': 'postgres',
}


@pytest.mark.parametrize('present', [False, True])
def test_srv01_snapshot_and_no_evolution_import_with_or_without_env(present):
    _check('''
        import asyncio, json, socket, subprocess, sys
        from pathlib import Path
        from unittest.mock import patch
        def forbidden(*args, **kwargs): raise AssertionError('Import side effect')
        with patch.object(socket.socket, 'connect', forbidden), \\
             patch.object(subprocess, 'Popen', forbidden), \\
             patch.object(asyncio, 'create_task', forbidden):
            import ls_iMotorSoft_Srv01 as srv
            sys.path.insert(0, 'scripts')
            from srv05_composition_snapshot import snapshot
            baseline = json.loads(Path('tests/fixtures/srv01_legacy_composition.json').read_text())
            assert snapshot(srv.app) == baseline
            assert not any('evolution' in name for name in sys.modules)
            assert [h.__name__ for h in srv.app.on_startup] == ['_open_db_pool', '_start_flow_scheduler']
    ''', environment={**(ENV if present else {}), 'AUTOMATION_DIAGNOSIS_REPOSITORY': 'memory'})


def test_srv05_off_ignores_invalid_provider_env_and_does_not_import_evolution():
    _check('''
        import sys
        import ls_iMotorSoft_Srv01 as old
        import ls_iMotorSoft_Srv05 as new
        assert new.app is not old.app
        assert new.app.openapi_schema.to_schema() == old.app.openapi_schema.to_schema()
        assert not any('evolution' in name for name in sys.modules)
        assert new.app.on_startup == old.app.on_startup
    ''', environment={**ENV, 'TEAM360_SRV05_EVOLUTION_ENABLED': '0',
                      'TEAM360_EVOLUTION_BASE_URL': 'invalid',
                      'AUTOMATION_DIAGNOSIS_REPOSITORY': 'memory'})


def test_srv05_on_without_v1_aborts_without_network_workers_or_pool_open():
    _check('''
        import asyncio, socket, subprocess
        from unittest.mock import patch
        def forbidden(*args, **kwargs): raise AssertionError('Import side effect')
        with patch.object(socket.socket, 'connect', forbidden), \\
             patch.object(subprocess, 'Popen', forbidden), \\
             patch.object(asyncio, 'create_task', forbidden):
            try:
                import ls_iMotorSoft_Srv05
            except ValueError as error:
                assert 'V1 runtime configuration required' in str(error)
            else:
                raise AssertionError('Legacy-only configuration must fail closed')
            from modules.db.pool import get_pool
            assert get_pool().closed
            from modules.flow.scheduler import get_scheduler
            assert get_scheduler() is None
    ''', environment={**ENV, 'TEAM360_DB_URL': 'postgresql://localhost/synthetic'})


@pytest.mark.parametrize('key,value', [
    ('TEAM360_SRV05_EVOLUTION_ENABLED', 'typo'),
    ('TEAM360_ENV', 'production'), ('TEAM360_ENV', ''),
    ('TEAM360_EVOLUTION_API_KEY', ''), ('TEAM360_EVOLUTION_BASE_URL', 'invalid'),
    ('TEAM360_EVOLUTION_TIMEOUT_SECONDS', 'nan'),
    ('TEAM360_MESSAGING_WEBHOOK_TOKEN', 'short'),
    ('TEAM360_MESSAGING_CHANNEL_ALIAS', ''),
    ('TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER', 'bad'),
    ('TEAM360_SRV05_MESSAGING_PROVIDER', 'gupshup'),
    ('AUTOMATION_DIAGNOSIS_REPOSITORY', 'memory'),
])
def test_invalid_config_aborts_before_app_creation(monkeypatch, key, value):
    monkeypatch.setenv('TEAM360_SRV05_EVOLUTION_ENABLED', '0')
    import ls_iMotorSoft_Srv05 as srv
    def forbidden(**kwargs): raise AssertionError('Invalid extension reached base factory')
    monkeypatch.setattr(srv, 'create_legacy_app', forbidden)
    for k, v in ENV.items(): monkeypatch.setenv(k, v)
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError) as error:
        srv.create_app()
    assert 'synthetic-key' not in str(error.value)


@pytest.fixture
def composition(monkeypatch):
    # Import with OFF, then compose ON with explicit validated synthetic config.
    monkeypatch.setenv('TEAM360_SRV05_EVOLUTION_ENABLED', '0')
    import ls_iMotorSoft_Srv05 as srv
    import ls_iMotorSoft_Srv01 as old
    import modules.db.pool as pool
    import importlib
    transaction_module = importlib.import_module('modules.db.transaction')
    from modules.messaging.repository import MessagingRepository
    events = []
    async def opened(): events.append('open')
    async def closed(): events.append('close')
    async def started(): events.append('start')
    async def stopped(): events.append('stop')
    async def binding(*args, **kwargs):
        events.append('binding')
        assert kwargs == {'workspace_slug': 'test-workspace', 'channel_alias': 'test-channel',
                          'provider': 'evolution', 'instance': 'test-instance'}
        from modules.messaging.repository import ChannelBinding
        import os
        if os.getenv('TEAM360_MESSAGING_DISPATCH_MODE') == 'horizontal_v1':
            return ChannelBinding('workspace', 'channel', 'provider', 'test-instance',
                'dev', 'telchi', 'tenant', os.getenv('META_TEAM360_PHONE_NUMBER_ID', ''))
        return ChannelBinding('workspace', 'channel', 'provider', 'test-instance')
    async def schema(*args): events.append('schema')
    @asynccontextmanager
    async def tx(_): yield object()
    monkeypatch.setattr(old, '_open_db_pool', opened)
    monkeypatch.setattr(old, '_close_db_pool', closed)
    monkeypatch.setattr(old, '_start_flow_scheduler', started)
    monkeypatch.setattr(old, '_stop_flow_scheduler', stopped)
    monkeypatch.setattr(pool, 'get_pool', lambda: object())
    monkeypatch.setattr(transaction_module, 'transaction', tx)
    monkeypatch.setattr(MessagingRepository, 'binding', binding)
    monkeypatch.setattr(MessagingRepository, 'validate_transport_schema', schema)
    from modules.messaging.transport_runtime import TransportRuntime
    class FixtureRuntime:
        document = {'scope': {'environment': 'dev'}}
        admission_open = True
        running = False
        def __init__(self):
            from test_messaging_horizontal_runtime import Sender
            self.provider = Sender()
        def sender(self):
            return self.provider
        async def start(self, pool, binding):
            self.running = True
            events.append('v1_start')
        async def stop(self):
            if self.running:
                events.append('v1_stop')
                self.running = False
    monkeypatch.setattr(TransportRuntime, 'from_env', lambda config: FixtureRuntime())
    for k, v in ENV.items(): monkeypatch.setenv(k, v)
    return srv, old, events


def test_on_webhook_security_frozen_binding_and_lifecycle(composition, monkeypatch):
    srv, old, events = composition
    app = srv.create_app()
    from test_team360_full_gate import gate
    gate.check_schema(app.openapi_schema.to_schema(), gate.inventory(app))
    assert len(gate.inventory(app)) == 28
    assert {r['path'] for r in gate.inventory(app)} - {r['path'] for r in gate.inventory(old.create_app())} == {PATH}
    import modules.messaging.webhooks.evolution_whatsapp as webhook
    build = AsyncMock(side_effect=AssertionError('No DB or provider permitted'))
    monkeypatch.setattr(webhook, 'build_service', build)
    # Changing provider env after composition cannot redirect this app.
    monkeypatch.setenv('TEAM360_EVOLUTION_INSTANCE', 'another-instance')
    monkeypatch.setenv('TEAM360_MESSAGING_WEBHOOK_TOKEN', 'another-token')
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.post(PATH, content=b'bad').status_code == 401
        headers = {'x-team360-webhook-token': ENV['TEAM360_MESSAGING_WEBHOOK_TOKEN']}
        assert client.post(PATH, content=b'bad', headers=headers).status_code == 400
        assert client.post(PATH, json={}, headers=headers).json() == {'ok': True, 'results': {'ignored': 1}}
        monkeypatch.setenv('TEAM360_ENV', 'production')
        assert client.post(PATH, json={}, headers=headers).status_code == 503
    build.assert_not_called()
    assert events == ['open', 'binding', 'schema', 'v1_start', 'start', 'v1_stop', 'stop', 'close']
    assert len(app.on_shutdown) == 3  # V1 closes before baseline pool shutdown


@pytest.mark.parametrize('check', ['binding', 'validate_transport_schema'])
def test_missing_binding_aborts_and_closes_pool_before_scheduler(composition, monkeypatch, check):
    srv, _, events = composition
    from modules.messaging.repository import MessagingRepository
    monkeypatch.setattr(MessagingRepository, check, AsyncMock(side_effect=ValueError('private-secret')))
    with pytest.raises(ExceptionGroup) as error:
        with TestClient(srv.create_app()): pass
    def leaves(exc):
        if isinstance(exc, BaseExceptionGroup):
            return [leaf for child in exc.exceptions for leaf in leaves(child)]
        return [exc]
    assert any(isinstance(exc, RuntimeError) and str(exc) ==
               'Srv05 Evolution binding/schema unavailable' for exc in leaves(error.value))
    assert events == (['open', 'stop', 'close'] if check == 'binding' else
                      ['open', 'binding', 'stop', 'close'])  # no scheduler start


def test_srv05_webhook_routes_normalized_events_and_duplicates(composition, monkeypatch):
    srv, _, _ = composition
    import modules.messaging.webhooks.evolution_whatsapp as webhook
    import modules.messaging.service as service_module
    from modules.messaging.service import MessagingService
    from modules.messaging.repository import ChannelBinding
    from modules.messaging.domain.messages import OutboundMessageReceipt
    seen, sends = set(), []
    class Repository:
        async def claim(self, conn, binding, message, timings):
            if message.external_message_id in seen: return None
            seen.add(message.external_message_id)
            return {'id': 'inbound', 'thread_id': 'thread'}
        async def intent(self, *args): return 'outbound'
        async def begin_send(self, conn, binding, outbound_id, *, retry=False):
            assert outbound_id == 'outbound' and retry is False
            return True
        async def lock_receipt(self, *args): pass
        async def finish(self, *args, **kwargs): assert kwargs['receipt'].external_message_id == 'sent'
    class Sender:
        def send_text(self, **kwargs):
            sends.append(kwargs)
            return OutboundMessageReceipt('sent', ENV['TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER'])
    @asynccontextmanager
    async def tx(_): yield object()
    monkeypatch.setattr(service_module, 'transaction', tx)
    service = MessagingService(pool=object(), repository=Repository(),
        binding=ChannelBinding('workspace', 'channel', 'provider', 'test-instance'),
        sender=Sender(), authorized_sender=ENV['TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER'])
    monkeypatch.setattr(webhook, 'build_service', AsyncMock(return_value=service))
    from test_messaging_evolution import payload
    with TestClient(srv.create_app()) as client:
        headers = {'x-team360-webhook-token': ENV['TEAM360_MESSAGING_WEBHOOK_TOKEN']}
        assert client.post(PATH, json=payload(), headers=headers).json()['results'] == {'accepted': 1}
        assert client.post(PATH, json=payload(), headers=headers).json()['results'] == {'duplicate': 1}
    assert len(sends) == len(seen) == 1  # only fake port; never WhatsApp


def test_safe_simultaneous_apps_have_no_cross_activation_or_real_scheduler(composition):
    srv, old, events = composition
    # Both lifespans use inert scheduler/pool hooks; never two delivery tasks.
    with TestClient(old.create_app()) as legacy, TestClient(srv.create_app()) as modern:
        assert legacy.get('/health').status_code == modern.get('/health').status_code == 200
        assert legacy.post(PATH, json={}).status_code == 404
        assert modern.post(PATH, json={}).status_code == 401
        from modules.flow.scheduler import get_scheduler
        assert get_scheduler() is None
    assert events.count('open') == events.count('close') == 2
