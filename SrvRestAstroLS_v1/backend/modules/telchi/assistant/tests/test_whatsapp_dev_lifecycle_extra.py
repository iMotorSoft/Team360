"""Additional offline regression checks for webhook readback and controller exits."""
import json
import os
from types import SimpleNamespace

import pytest

from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant import whatsapp_dev_lifecycle as control


@pytest.mark.parametrize('variant,expected', [
    ('previous', 'INTERNAL'), ('temporary', 'SESSION'), ('foreign', 'FOREIGN')])
def test_webhook_status_uses_only_gets_and_canonical_fields(tmp_path, monkeypatch, variant, expected):
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    backup = dict(instance='fixture',
        previous=dev.webhook_body(dict(enabled=False, url='http://internal.fixture/hook')),
        temporary=dev.webhook_body(dict(enabled=True, url='http://temporary.fixture/hook',
                                      headers={'x-team360-webhook-token': 'sensitive-fixture'})))
    path = tmp_path / 'backup.json'
    dev.save_private(path, backup)
    monkeypatch.setattr(dev, 'configuration', lambda: (
        SimpleNamespace(evolution=SimpleNamespace(instance='fixture')), None))
    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(dev, 'client_for', lambda *a: Client())
    calls = []
    def api(client, method, route, body=None):
        calls.append(method)
        assert method == 'GET' and body is None
        if 'connectionState' in route:
            return {'instance': {'state': 'open'}}
        return backup[variant] if variant != 'foreign' else dict(enabled=True, url='http://foreign.fixture')
    monkeypatch.setattr(dev, 'api', api)
    result = control.inspect_webhook({'backup': str(path)})
    assert result == (expected, 'READY') and calls == ['GET', 'GET']
    assert 'sensitive-fixture' not in json.dumps(result)


def test_start_does_not_report_success_on_gate_rejection(monkeypatch):
    monkeypatch.setattr(control.sys, 'argv', ['control', 'start'])
    monkeypatch.setattr(control, 'load_config', lambda *a: {})
    monkeypatch.setattr(control, 'launch', lambda *a: dict(state='STOPPED', reason='start_closed_before_ready'))
    assert control.main() == 1


def test_public_errors_do_not_reveal_credentials(monkeypatch, capsys):
    monkeypatch.setattr(control.sys, 'argv', ['control', 'status'])
    def failure(*args):
        raise ValueError('sensitive-credential-fixture')
    monkeypatch.setattr(control, 'load_config', failure)
    assert control.main() == 1
    assert 'sensitive-credential-fixture' not in capsys.readouterr().out


def test_backend_disappears_during_start_is_review(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    control.directory(control.root())
    owner = control.Session(SimpleNamespace(output=tmp_path / 'session', approval=tmp_path / 'approval'))
    owner.publish('STARTING', backend=dict(control.identity(os.getpid()), pid=999999999))
    monkeypatch.setattr(control, 'inspect_webhook', lambda *a: ('INTERNAL', 'READY'))
    monkeypatch.setattr(dev, 'read_approval', lambda *a: (_ for _ in ()).throw(ValueError('fixture')))
    assert control.status()['state'] == 'REVIEW_REQUIRED'


def test_lock_symlink_is_never_followed(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    control.directory(control.root())
    target = tmp_path / 'target'
    target.write_text('unchanged')
    (control.root() / 'owner.lock').symlink_to(target)
    with pytest.raises(OSError):
        with control.owned_session(SimpleNamespace(output=tmp_path / 'session', approval=tmp_path / 'approval')):
            pytest.fail('symlink accepted')
    assert target.read_text() == 'unchanged'


def test_insecure_state_directory_is_not_repaired(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    control.root().mkdir(mode=0o755)
    with pytest.raises(ValueError, match='private_directory'):
        with control.owned_session(SimpleNamespace(output=tmp_path / 'session', approval=tmp_path / 'approval')):
            pytest.fail('public directory accepted')
    assert control.root().stat().st_mode & 0o077
