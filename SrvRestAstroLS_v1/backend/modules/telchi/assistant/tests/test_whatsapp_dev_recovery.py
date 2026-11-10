"""Administrative recovery preserves history and fences uncertain/replayable work."""
import json
import os
import socket
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant import whatsapp_dev_lifecycle as control
from modules.telchi.assistant import whatsapp_dev_recovery as recovery


@pytest.fixture(params=['STOPPING', 'READY'])
def orphan(monkeypatch, tmp_path, request):
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    control.directory(control.root())
    session = control.Session(SimpleNamespace(output=tmp_path / 'session', approval=tmp_path / 'approval'))
    control.directory(tmp_path / 'session')
    dev.save_private(session.value['backup'], {'instance': 'fixture', 'previous': {}, 'temporary': {}})
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        listener = dict(host='127.0.0.1', port=probe.getsockname()[1])
    absent = dict(control.identity(os.getpid()), pid=2**30)
    session.publish(request.param, launcher=absent, backend=absent,
                    listener=listener, webhook_attempted=True)
    counts = dict(durable_pending=0, resumable_outbound=0, session_uncertain_outbound=0,
                  session_running_inbound=0, older_uncertain_outbound=1, older_legacy_running=1)
    async def inventory(*a):
        return counts.copy()
    monkeypatch.setattr(recovery, 'inventory', inventory)
    monkeypatch.setattr(dev, 'configuration', lambda: (SimpleNamespace(evolution=SimpleNamespace(instance='fixture')), None))
    monkeypatch.setattr(dev, 'client_for', lambda *a: nullcontext(None))
    calls = []
    monkeypatch.setattr(dev, 'restore', lambda *a: calls.append('verified_restore'))
    return session, counts, calls


def test_reconciled_closure_preserves_bytes_and_allows_new_session(orphan):
    session, counts, calls = orphan
    before = session.path.read_bytes()
    result = recovery.reconcile(session.value['session_id'])
    assert result['recovery'] == 'RECONCILED'
    closed = control.read_json(session.path)
    assert closed['closure'] == 'ADMINISTRATIVE_RECOVERY'
    assert closed['backend_stopped'] and closed['webhook_restored']
    audit = control.root() / ('recovery-' + session.value['session_id'])
    assert (audit / 'current.json').read_bytes() == before
    evidence = json.loads((audit / 'verified.json').read_text())
    assert evidence['inventory'] == counts
    assert evidence['transition'] == dict(from_state=json.loads(before)['state'], to_state='STOPPED')
    assert evidence['processes_absent'] and evidence['listener_free']
    assert evidence['database_writes'] == evidence['messages_sent'] == 0
    assert calls == ['verified_restore']
    assert recovery.reconcile(session.value['session_id'])['recovery'] == 'ALREADY_RECONCILED'
    assert calls == ['verified_restore']
    with control.owned_session(SimpleNamespace(output=dev.PRIVATE_ROOT / 'new', approval=dev.PRIVATE_ROOT / 'approval')):
        pass


@pytest.mark.parametrize('field', ['durable_pending', 'resumable_outbound',
                                   'session_uncertain_outbound', 'session_running_inbound'])
def test_pending_work_blocks_without_writes(orphan, field):
    session, counts, calls = orphan
    counts[field] = 1
    before = session.path.read_bytes()
    with pytest.raises(RuntimeError, match='work_requires'):
        recovery.reconcile(session.value['session_id'])
    assert session.path.read_bytes() == before
    assert not calls


def test_wrong_session_does_not_touch_current(orphan):
    session, _, calls = orphan
    before = session.path.read_bytes()
    with pytest.raises(RuntimeError, match='session_changed'):
        recovery.reconcile('another-session')
    assert session.path.read_bytes() == before and not calls


@pytest.mark.parametrize('field', ['launcher', 'backend'])
@pytest.mark.parametrize('reused', [False, True])
def test_live_or_reused_pid_blocks(orphan, field, reused):
    session, _, calls = orphan
    value = control.identity(os.getpid())
    if reused:
        value = dict(value, start_ticks='different-start')
    session.publish(**{field: value})
    before = session.path.read_bytes()
    with pytest.raises(RuntimeError, match='process_present'):
        recovery.reconcile(session.value['session_id'])
    assert session.path.read_bytes() == before and not calls


@pytest.mark.parametrize('field', ['launcher', 'backend', 'listener'])
def test_ready_requires_original_process_and_listener_evidence(orphan, field):
    session, _, calls = orphan
    session.publish('READY', **{field: None})
    before = session.path.read_bytes()
    with pytest.raises(RuntimeError, match='ready_orphan_evidence_required'):
        recovery.reconcile(session.value['session_id'])
    assert session.path.read_bytes() == before and not calls


def test_occupied_listener_blocks_without_writes(orphan):
    session, _, calls = orphan
    with socket.socket() as listener:
        listener.bind((session.value['listener']['host'], session.value['listener']['port']))
        listener.listen(1)
        before = session.path.read_bytes()
        with pytest.raises(OSError):
            recovery.reconcile(session.value['session_id'])
        assert session.path.read_bytes() == before and not calls


def test_foreign_webhook_preserves_review_and_originals(orphan, monkeypatch):
    session, _, calls = orphan
    before = session.path.read_bytes()
    def foreign(*a):
        raise RuntimeError('webhook_changed_by_other_owner_manual_reconciliation_required')
    monkeypatch.setattr(dev, 'restore', foreign)
    with pytest.raises(RuntimeError, match='other_owner'):
        recovery.reconcile(session.value['session_id'])
    assert session.path.read_bytes() == before
    assert not calls


def test_active_lock_fences_recovery(orphan):
    session, _, calls = orphan
    fd = os.open(control.root() / 'owner.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        control.fcntl.flock(fd, control.fcntl.LOCK_EX | control.fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            recovery.reconcile(session.value['session_id'])
    finally:
        os.close(fd)
    assert not calls


def test_v1_stop_does_not_stop_shared_evolution(orphan, monkeypatch):
    session, _, _ = orphan
    session.publish('STOPPED', webhook_restored=True, backend_stopped=True)
    monkeypatch.setenv('TEAM360_TRANSPORT_V1_CONFIG', 'fixture')
    monkeypatch.setattr(control, 'evolution_running', lambda *a: pytest.fail('shared Evolution stopped'))
    monkeypatch.setattr(control, 'status', lambda: {'state': 'STOPPED'})
    assert control.stop()['state'] == 'STOPPED'


def test_v1_invalid_gates_never_prepares_or_reaccredits(orphan, monkeypatch):
    session, _, _ = orphan
    monkeypatch.setenv('TEAM360_TRANSPORT_V1_CONFIG', 'fixture')
    session.publish('STOPPED', webhook_restored=True, backend_stopped=True)
    monkeypatch.setattr(control, 'prepare_v1', lambda: pytest.fail('mutation before gates'))
    monkeypatch.setattr(control, 'reaccredit_v1', lambda *a: pytest.fail('implicit battery'))
    monkeypatch.setattr(dev, 'read_approval', lambda *a: {})
    monkeypatch.setattr(dev, 'gate_evidence', lambda *a: (_ for _ in ()).throw(ValueError('invalid_gates')))
    with pytest.raises(ValueError, match='invalid_gates'):
        dev.start(SimpleNamespace(output=dev.PRIVATE_ROOT / 'new', approval=dev.PRIVATE_ROOT / 'approval'))
