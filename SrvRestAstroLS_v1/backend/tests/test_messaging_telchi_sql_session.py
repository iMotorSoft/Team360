"""Probe cannot claim readiness/PASS when transport preflight fails."""
import asyncio
import json
from types import SimpleNamespace

import modules.messaging.telchi_sql_session as session


def test_transport_failure_sanitized_no_backend_or_private_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(session.MessagingDevSettings, 'from_env', lambda: SimpleNamespace(telchi_tenant='telchi'))
    monkeypatch.setattr(session.EvolutionConfig, 'from_env', lambda: SimpleNamespace(base_url='http://127.0.0.1:9', api_key='SECRET', instance='test'))
    class Client:
        def __init__(self, **kwargs): pass
        def request(self, *args, **kwargs):
            raise ConnectionError('SECRET phone=15550000001')
        def close(self): pass
    monkeypatch.setattr(session.httpx, 'Client', Client)
    def unexpected(*args, **kwargs):
        raise AssertionError('No backend may start before Evolution preflight')
    monkeypatch.setattr(session.subprocess, 'Popen', unexpected)
    output = tmp_path/'probe'
    code = asyncio.run(session.run(SimpleNamespace(host='127.0.0.1',port=18181,
        output=str(output),duration=1,count=1)))
    state = json.loads((output/'session.json').read_text())
    assert code==2 and state['status']=='BLOCKED' and state['layer']=='Evolution transport'
    assert state['own_processes_left_running']==0 and not state['runtime_active']
    assert 'SECRET' not in (output/'session.json').read_text()
    assert not (output/'evidence.json').exists()
