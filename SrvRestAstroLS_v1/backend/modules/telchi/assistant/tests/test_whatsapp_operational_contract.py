"""Offline regression: explicit environment and full restoration equality."""
import json
import os
from pathlib import Path
import subprocess

import pytest

from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant import whatsapp_dev_lifecycle as control


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    monkeypatch.setattr(os, 'environ', os.environ.copy())
    return tmp_path / 'control.json'


def test_shell_sanitizes_python_before_imports(tmp_path):
    script = Path(dev.__file__).resolve().parents[4] / 'scripts/telchi/telchiai-dev.sh'
    result = subprocess.run(['bash', str(script), 'status', '--config',
                             str(tmp_path / 'absent.json')],
        env=dict(os.environ, PYTHONHOME='/untrusted/missing', PYTHONPATH='/untrusted'),
        text=True, capture_output=True, timeout=10)
    assert result.returncode == 1
    assert json.loads(result.stdout)['state'] == 'REVIEW_REQUIRED'
    assert 'Fatal Python error' not in result.stderr


def test_explicit_postgres_and_terminal_independence(config):
    dev.save_private(config, {'env': {'AUTOMATION_DIAGNOSIS_REPOSITORY': 'postgres'}})
    outputs = []
    for profile in ('messaging-only', 'full'):
        os.environ.update(TEAM360_DEV_PROFILE=profile, TEAM360_BUSINESS_SEMANTICS='1',
                          TEAM360_TELCHI_ASSISTANT_DEV_HTTP='1', PGOPTIONS='foreign',
                          PYTHONPATH='/foreign', OPENAI_API_KEY='foreign',
                          TEAM360_MESSAGING_DEV_SQL_TENANT='foreign')
        control.load_config(config)
        outputs.append(dict(os.environ))
    assert outputs[0] == outputs[1]
    assert os.environ['AUTOMATION_DIAGNOSIS_REPOSITORY'] == 'postgres'
    assert set(os.environ) <= control.BASE_ENV | control.CONFIG_ENV


def test_missing_authorized_host_cannot_create_session(config):
    with pytest.raises(ValueError, match='explicit_authorized_launch_host'):
        control.launch({'env': {}})
    assert not control.root().exists()


@pytest.mark.parametrize('name,value', [
    ('AUTOMATION_DIAGNOSIS_REPOSITORY', 'memory'),
    ('TEAM360_UNKNOWN', '1'), ('PGOPTIONS', '-c role=foreign'),
    ('TEAM360_DEV_PROFILE', 'messaging-only'),
    ('TEAM360_BUSINESS_SEMANTICS', '1'),
    ('TEAM360_TELCHI_ASSISTANT_DEV_HTTP', '1'),
])
def test_rejection_is_atomic(config, name, value):
    dev.save_private(config, {'env': {name: value}})
    before = dict(os.environ)
    with pytest.raises(ValueError):
        control.load_config(config)
    assert dict(os.environ) == before


@pytest.mark.parametrize('field,value', [
    ('enabled', True), ('url', 'http://foreign.test'),
    ('events', ['MESSAGES_UPDATE']), ('headers', {'foreign': 'fixture'}),
    ('byEvents', True), ('base64', True),
])
def test_same_url_and_disabled_are_not_sufficient(monkeypatch, field, value):
    previous = dev.webhook_body({'enabled': False, 'url': 'http://same.test'})
    backup = {'previous': previous, 'temporary': dict(previous, enabled=True)}
    foreign = dict(previous, **{field: value})
    # enabled=True is the known temporary state; all other mismatches are foreign.
    calls = []
    def api(client, method, path, body=None):
        calls.append(method)
        return foreign
    monkeypatch.setattr(dev, 'api', api)
    with pytest.raises(RuntimeError):
        dev.restore(None, 'fixture', backup)
    assert calls == (['GET', 'POST', 'GET'] if field == 'enabled' else ['GET'])
