"""Telchi registration through real Srv05 injection; external lifecycle inert."""
from unittest.mock import AsyncMock
import pytest
from litestar.testing import TestClient

from test_srv05_evolution_isolation import composition
from modules.telchi.assistant.composition import create_telchi_app
from modules.telchi.assistant.handler import BusinessPolicy, TelchiHandler


def test_telchi_handler_registered_using_existing_srv05_port(composition, monkeypatch):
    srv, _, events = composition
    monkeypatch.setenv('TEAM360_MESSAGING_DISPATCH_MODE', 'horizontal_v1')
    from modules.messaging.identity import PhoneIdentityRepository
    import modules.messaging.webhooks.evolution_whatsapp as webhook
    monkeypatch.setattr(PhoneIdentityRepository, 'validate_schema', AsyncMock())
    build = AsyncMock()
    monkeypatch.setattr(webhook, 'build_service', build)
    policy = BusinessPolicy('fixture-tenant', 'fixture-workspace', 'fixture.business.read', True, True)
    app = create_telchi_app(policy=policy)
    registration = app.state.messaging_handlers['telchi']
    from modules.db.pool import get_pool
    assert registration.handler.store.pool is get_pool  # lazy, after existing lifespan
    assert isinstance(registration.handler, TelchiHandler)
    assert registration.required_permissions == frozenset({'fixture.business.read'})
    assert not registration.public_capabilities and registration.environment == 'dev'
    with TestClient(app):
        build.assert_awaited_once_with(app.state.srv05_settings.messaging, app.state.srv05_settings.evolution,
                                      handlers=app.state.messaging_handlers,
                                      transport_runtime=app.state.transport_v1)
    assert events == ['open', 'binding', 'schema', 'v1_start', 'start', 'v1_stop', 'stop', 'close']


def test_durable_worker_lifecycle_uses_existing_srv05_runtime(composition, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    _, _, events = composition
    monkeypatch.setenv('TEAM360_MESSAGING_DISPATCH_MODE', 'horizontal_v1')
    monkeypatch.setenv('TEAM360_TELCHI_DURABLE', '1')
    from modules.messaging.identity import PhoneIdentityRepository
    import modules.messaging.webhooks.evolution_whatsapp as webhook
    import modules.messaging.durable as durable
    monkeypatch.setattr(PhoneIdentityRepository, 'validate_schema', AsyncMock())
    build = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(webhook, 'build_service', build)
    class Worker:
        def __init__(self, service): self.stopped = asyncio.Event()
        async def run(self):
            try: await self.stopped.wait()
            finally: events.append('worker_stop')
    monkeypatch.setattr(durable, 'DurableWorker', Worker)
    app = create_telchi_app(policy=BusinessPolicy('fixture-tenant','fixture-workspace','fixture.business.read',True,True))
    assert app.state.durable_messaging is True
    assert app.state.messaging_handlers['telchi'].handler.turn_timeout_seconds == 300
    with TestClient(app):
        assert not app.state.durable_worker_task.done()
        assert any(call.kwargs.get('durable') is True for call in build.await_args_list)
    assert app.state.durable_worker_task.done()
    assert events.index('worker_stop') < events.index('close')


def test_invalid_durable_setting_rejected(composition, monkeypatch):
    monkeypatch.setenv('TEAM360_TELCHI_DURABLE', 'yes')
    with pytest.raises(ValueError, match='Invalid durable'):
        create_telchi_app(policy=BusinessPolicy('fixture-tenant','fixture-workspace','fixture.business.read',True,True))


def test_semantics_requires_dedicated_connection_without_changing_store(composition, monkeypatch):
    monkeypatch.setenv('TEAM360_ENV', 'dev')
    monkeypatch.setenv('TEAM360_BUSINESS_SEMANTICS', '1')
    monkeypatch.delenv('TEAM360_SEMANTICS_AUTH_CONFIG', raising=False)
    policy = BusinessPolicy('fixture-tenant', 'fixture-workspace', 'fixture.business.read', True, True)
    with pytest.raises(ValueError, match='restricted_semantics_configuration_required'):
        create_telchi_app(policy=policy)
    from modules.business_semantics import runtime_connection
    sentinel = object()
    monkeypatch.setattr(runtime_connection, 'RestrictedSemanticsConnection', lambda path: sentinel)
    monkeypatch.setenv('TEAM360_SEMANTICS_AUTH_CONFIG', '/synthetic/private/config')
    app = create_telchi_app(policy=policy)
    handler = app.state.messaging_handlers['telchi'].handler
    from modules.db.pool import get_pool
    assert handler.store.pool is get_pool
    assert handler.semantics_connection is sentinel
    assert handler.concept_resolver is not None
