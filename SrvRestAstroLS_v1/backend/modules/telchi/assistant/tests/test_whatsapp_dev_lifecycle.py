"""Offline lifecycle checks. No live dependencies, messages, or webhook changes."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant import whatsapp_dev_lifecycle as control


@pytest.fixture(autouse=True)
def no_external_services(monkeypatch, tmp_path):
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    monkeypatch.setattr(os, 'environ', os.environ.copy())
    def forbidden(*args, **kwargs):
        raise AssertionError('external dependency called by offline test')
    monkeypatch.setattr(dev, 'client_for', forbidden)
    monkeypatch.setattr(dev, 'check_database', forbidden)
    monkeypatch.setattr(dev, 'container_probe', forbidden)


@pytest.fixture
def args(tmp_path):
    return SimpleNamespace(approval=tmp_path / 'approval.json', output=tmp_path / 'session',
                           duration=60, host='192.0.2.1', port=18181, container='fixture')


@pytest.fixture
def session(args):
    control.directory(control.root())
    result = control.Session(args)
    result.publish()
    return result


def test_atomic_private_record_has_no_secret(session):
    session.publish('READY', listener=dict(host='192.0.2.1', port=18181,
                                          nonce_sha256='fixture-digest'))
    record = control.read_json(session.path)
    assert record['session_id'] and record['state'] == 'READY'
    assert record['launcher'] == control.identity(os.getpid())
    assert record['updated_at'] >= record['created_at']
    assert session.path.stat().st_mode & 0o077 == 0
    assert session.path.parent.stat().st_mode & 0o077 == 0
    assert not list(session.path.parent.glob('.state-*'))
    assert 'token' not in json.dumps(record) and 'phone' not in json.dumps(record)
    assert control.read_json(session.path.parent / (record['session_id'] + '.json')) == record


def test_atomic_failure_preserves_previous_record(session, monkeypatch):
    before = session.path.read_bytes()
    monkeypatch.setattr(control.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('fixture')))
    with pytest.raises(OSError):
        session.publish('READY')
    assert session.path.read_bytes() == before
    assert not list(session.path.parent.glob('.state-*'))


def test_lock_excludes_duplicate_start(args):
    with control.owned_session(args) as owner:
        owner.publish()
        with pytest.raises(BlockingIOError):
            with control.owned_session(args):
                pytest.fail('second owner accepted')
    assert control.read_json(control.root() / 'current.json')['state'] == 'STOPPED'


def test_unknown_prior_session_never_overwritten(session, args):
    before = session.path.read_bytes()
    with pytest.raises(RuntimeError, match='previous_session'):
        with control.owned_session(args):
            pytest.fail('ambiguous session accepted')
    assert session.path.read_bytes() == before


def test_preflight_failure_does_not_leave_claimed_session(args, monkeypatch):
    monkeypatch.setattr(dev, 'preflight', lambda *a: (_ for _ in ()).throw(ValueError('gates_expired')))
    with pytest.raises(ValueError, match='gates_expired'):
        dev.start(args)
    record = control.read_json(control.root() / 'current.json')
    assert record['state'] == 'STOPPED' and record['webhook_untouched']
    assert not record['webhook_attempted']
    # Lock released, without any subprocess or webhook call.
    monkeypatch.setattr(control, 'matches', lambda value: False)
    with control.owned_session(args):
        pass


def test_status_without_session_is_read_only():
    assert control.status()['state'] == 'STOPPED'
    assert not control.root().exists()
    assert control.stop()['state'] == 'STOPPED'
    assert not control.root().exists()


def dependencies(monkeypatch, webhook='SESSION', pg=True, healthy=True):
    monkeypatch.setattr(control, 'inspect_webhook', lambda record: (webhook, 'READY'))
    monkeypatch.setattr(control, 'listener_owned', lambda record: healthy)
    monkeypatch.setattr(dev, 'read_approval', lambda path: {})
    monkeypatch.setattr(dev, 'gate_evidence', lambda approval: None)
    monkeypatch.setattr(dev, 'configuration', lambda: (SimpleNamespace(evolution=None), None))
    async def database(*args):
        if not pg:
            raise RuntimeError('fixture unavailable')
    monkeypatch.setattr(dev, 'check_database', database)


def test_ready_status_checks_separate_dependencies_without_writes(session, monkeypatch):
    session.publish('READY', backend=control.identity(os.getpid()))
    dependencies(monkeypatch)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in control.root().iterdir()}
    report = control.status()
    assert report['state'] == 'READY'
    assert report['backend'] == 'OWNED' and report['webhook'] == 'SESSION'
    assert report['postgresql'] == report['evolution'] == 'READY'
    assert report['approval'] == report['gates'] == 'VALID'
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in control.root().iterdir()}


@pytest.mark.parametrize('webhook,pg,healthy,state', [
    ('FOREIGN', True, True, 'REVIEW_REQUIRED'),
    ('INTERNAL', True, True, 'REVIEW_REQUIRED'),
    ('SESSION', False, True, 'DEGRADED'),
    ('SESSION', True, False, 'DEGRADED'),
])
def test_status_failure_classification(session, monkeypatch, webhook, pg, healthy, state):
    session.publish('READY', backend=control.identity(os.getpid()))
    dependencies(monkeypatch, webhook, pg, healthy)
    assert control.status()['state'] == state


@pytest.mark.parametrize('field', ['launcher', 'backend'])
def test_reused_pid_is_review_and_never_signalled(session, monkeypatch, field):
    original = control.identity(os.getpid())
    changed = dict(original, start_ticks='wrong-start')
    session.publish('READY', launcher=original, backend=original, **{})
    session.publish(**{field: changed})
    dependencies(monkeypatch)
    monkeypatch.setattr(control, 'signal_owned', lambda *a: pytest.fail('foreign PID signalled'))
    assert control.status()['state'] == 'REVIEW_REQUIRED'
    assert control.stop()['state'] == 'REVIEW_REQUIRED'


def test_missing_process_is_review(session, monkeypatch):
    session.publish('READY', launcher=dict(control.identity(os.getpid()), pid=999999999))
    dependencies(monkeypatch)
    assert control.status()['state'] == 'REVIEW_REQUIRED'
    assert control.stop()['state'] == 'REVIEW_REQUIRED'


def test_uncertain_restore_never_reports_stopped(session, monkeypatch):
    session.publish('REVIEW_REQUIRED', webhook_restored=False, backend_stopped=True)
    dependencies(monkeypatch, webhook='FOREIGN')
    assert control.status()['state'] == 'REVIEW_REQUIRED'
    assert control.stop()['state'] == 'REVIEW_REQUIRED'


def test_duplicate_stop_never_signals(session, monkeypatch):
    session.publish('STOPPED', launcher=None, backend=None,
                    webhook_restored=True, backend_stopped=True)
    dependencies(monkeypatch, webhook='INTERNAL')
    monkeypatch.setattr(control, 'signal_owned', lambda *a: pytest.fail('duplicate signal'))
    assert control.stop()['state'] == control.stop()['state'] == 'STOPPED'


def test_stop_requests_only_launcher_then_checks_closure(session, monkeypatch):
    original = session.value['launcher']
    session.publish('READY')
    dependencies(monkeypatch, webhook='INTERNAL')
    signals = []
    def terminate(owner):
        signals.append(owner)
        session.publish('STOPPED', launcher=None, backend=None,
                        webhook_restored=True, backend_stopped=True)
    monkeypatch.setattr(control, 'signal_owned', terminate)
    real_matches = control.matches
    monkeypatch.setattr(control, 'matches', lambda owner: False if signals and owner == original else real_matches(owner))
    assert control.stop(timeout=.01)['state'] == 'STOPPED'
    assert signals == [original]


def test_stop_timeout_does_not_escalate_or_claim_success(session, monkeypatch):
    session.publish('READY')
    dependencies(monkeypatch)
    signals = []
    monkeypatch.setattr(control, 'signal_owned', signals.append)
    assert control.stop(timeout=0)['state'] == 'REVIEW_REQUIRED'
    assert signals == [session.value['launcher']]


def test_stopping_duplicate_waits_without_second_signal(session, monkeypatch):
    session.publish('STOPPING')
    dependencies(monkeypatch)
    monkeypatch.setattr(control, 'signal_owned', lambda *a: pytest.fail('second signal'))
    assert control.stop(timeout=0)['state'] == 'REVIEW_REQUIRED'


def test_verified_pidfd_signal_targets_only_own_temporary_process():
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        owner = control.wait_backend_identity(child,
            [sys.executable, '-c', 'import time; time.sleep(30)'])
        control.signal_owned(owner)
        assert child.wait(timeout=5) == -signal.SIGTERM
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)


def test_pidfd_recheck_refuses_changed_identity(monkeypatch):
    owner = dict(control.identity(os.getpid()), start_ticks='reused')
    monkeypatch.setattr(control.signal, 'pidfd_send_signal', lambda *a: pytest.fail('unsafe signal'))
    with pytest.raises(RuntimeError, match='identity_changed'):
        control.signal_owned(owner)


@pytest.mark.parametrize('mode', [0o644, 0o666])
def test_public_config_refused(tmp_path, mode):
    path = tmp_path / 'config.json'
    path.write_text('{"env": {}}')
    path.chmod(mode)
    with pytest.raises(ValueError, match='private_file'):
        control.load_config(path)


def test_symlink_config_refused(tmp_path):
    original = tmp_path / 'original'
    dev.save_private(original, {'env': {}})
    link = tmp_path / 'link'
    link.symlink_to(original)
    with pytest.raises(ValueError, match='symlink'):
        control.load_config(link)


def test_private_json_is_data_not_shell(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    sentinel = tmp_path / 'must-not-exist'
    dev.save_private(path, {'env': {'TEAM360_EVOLUTION_API_KEY': '$(touch ' + str(sentinel) + ')'}})
    monkeypatch.delenv('TEAM360_EVOLUTION_API_KEY', raising=False)
    control.load_config(path)
    assert not sentinel.exists()
    path.unlink()
    dev.save_private(path, {'env': {'PYTHONPATH': '/untrusted'}})
    with pytest.raises(ValueError, match='environment_entry'):
        control.load_config(path)


def test_invalid_gates_degrade_without_rewriting_state(session, monkeypatch):
    session.publish('READY', backend=control.identity(os.getpid()))
    dependencies(monkeypatch)
    def invalid(*args):
        raise ValueError('gate_source_mismatch')
    monkeypatch.setattr(dev, 'gate_evidence', invalid)
    before = session.path.read_bytes()
    report = control.status()
    assert report['state'] == 'DEGRADED' and report['gates'] == 'INVALID_OR_EXPIRED'
    assert report['postgresql'] == 'READY'
    assert session.path.read_bytes() == before


def test_invalid_approval_is_not_reported_as_postgresql_down(session, monkeypatch):
    session.publish('READY', backend=control.identity(os.getpid()))
    dependencies(monkeypatch)
    def invalid(*args):
        raise ValueError('pilot_access_revoked')
    monkeypatch.setattr(dev, 'read_approval', invalid)
    report = control.status()
    assert report['state'] == 'DEGRADED'
    assert report['approval'] == 'INVALID_OR_REVOKED'
    assert report['postgresql'] == report['gates'] == 'NOT_CHECKED'


def test_listener_nonce_hash_not_status_200_alone(session, monkeypatch):
    import hashlib
    session.publish('READY', backend=control.identity(os.getpid()), listener=dict(
        host='127.0.0.1', port=18181, nonce_sha256=hashlib.sha256(b'ours').hexdigest()))
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['trust_env'] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            return SimpleNamespace(status_code=200, headers={'x-team360-session': 'foreign'})
    monkeypatch.setattr(dev.httpx, 'Client', Client)
    assert not control.listener_owned(session.value)


def test_foreign_listener_blocks_start_without_process_discovery(args, monkeypatch):
    monkeypatch.setattr(dev, 'preflight', lambda *a: ({}, None, None, None))
    monkeypatch.setattr(dev, 'gate_evidence', lambda *a: None)
    args.host = '127.0.0.2'
    with socket.socket() as foreign:
        foreign.bind((args.host, 0))
        foreign.listen()
        args.port = foreign.getsockname()[1]
        monkeypatch.setattr(dev.subprocess, 'Popen', lambda *a, **k: pytest.fail('backend started'))
        with pytest.raises(OSError):
            dev.start(args)
        assert foreign.getsockname()[1] == args.port
        assert foreign.fileno() >= 0


def test_detached_start_uses_only_existing_launcher(monkeypatch):
    launches = []
    class Child:
        pid = 999999999
        def poll(self):
            return 1
    def popen(argv, **kwargs):
        launches.append((argv, kwargs))
        return Child()
    monkeypatch.setattr(control.subprocess, 'Popen', popen)
    report = control.launch(dict(host='192.0.2.1'))
    assert report['state'] == 'REVIEW_REQUIRED'
    assert len(launches) == 1
    argv, options = launches[0]
    assert argv[:4] == [sys.executable, '-m', dev.MODULE, 'start']
    assert options['start_new_session'] and options['stdin'] == subprocess.DEVNULL
    assert 'podman' not in argv and 'cloudflared' not in argv
    assert all(p.stat().st_mode & 0o077 == 0 for p in control.root().iterdir())


def test_direct_commands_remain_available():
    import inspect
    source = inspect.getsource(dev.main)
    for command in ['preflight', 'start', 'fingerprint', 'inspect', 'restore', '_serve']:
        assert repr(command) in source
    assert 'whatsapp_dev_lifecycle' not in inspect.getsource(dev.source_digest)
    # The digest still includes ALL assistant Python, including launcher + this helper.
    assert "'telchi/assistant'" in inspect.getsource(dev.source_digest)
