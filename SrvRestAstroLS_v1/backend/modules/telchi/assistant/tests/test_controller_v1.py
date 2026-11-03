"""DEV controller integration, no real credentials, containers or messages."""
import asyncio
from types import SimpleNamespace

import pytest

from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant import whatsapp_dev_lifecycle as control


def test_v1_configuration_is_explicitly_allowlisted():
    assert {'TEAM360_TRANSPORT_V1_CONFIG', 'TEAM360_TRANSPORT_V1_RUNTIME_ROLE',
            'TEAM360_TELCHI_V1_SEND_AUTHORIZED', 'TEAM360_EVOLUTION_MANAGEMENT_API_KEY'} <= control.CONFIG_ENV
    assert 'PYTHONPATH' not in control.CONFIG_ENV


def test_management_credential_never_replaces_runtime_credential(monkeypatch):
    monkeypatch.setenv('TEAM360_TRANSPORT_V1_CONFIG', '/private/config.json')
    monkeypatch.setenv('TEAM360_EVOLUTION_MANAGEMENT_API_KEY', 'management-fixture')
    config = SimpleNamespace(base_url='http://127.0.0.1:18180', api_key='runtime-fixture')
    with dev.client_for(config) as client:
        assert client.headers['apikey'] == 'management-fixture'
    assert config.api_key == 'runtime-fixture'


def test_missing_management_key_fails_closed(monkeypatch):
    monkeypatch.setenv('TEAM360_TRANSPORT_V1_CONFIG', '/private/config.json')
    monkeypatch.delenv('TEAM360_EVOLUTION_MANAGEMENT_API_KEY', raising=False)
    with pytest.raises(KeyError):
        dev.client_for(SimpleNamespace(base_url='http://127.0.0.1', api_key='runtime-fixture'))


@pytest.mark.parametrize('healthy,expected', [(True, 200), (False, 503)])
def test_v1_health_requires_live_worker_and_callback(healthy, expected):
    boundary = dev.PilotBoundary(None, None, None, None, health_check=lambda: healthy)
    sent = []

    async def send(event):
        sent.append(event)

    asyncio.run(boundary({'type': 'http', 'path': '/health', 'method': 'GET'}, None, send))
    assert sent[0]['status'] == expected


def test_stopped_adopted_container_is_closed_not_foreign(monkeypatch):
    monkeypatch.setenv('TEAM360_TRANSPORT_V1_CONFIG', '/private/config.json')
    monkeypatch.setattr(control, 'adopted_container', lambda: ('verified-id', {'State': {'Running': False}}))
    assert control.inspect_webhook({}) == ('INACTIVE', 'STOPPED')
