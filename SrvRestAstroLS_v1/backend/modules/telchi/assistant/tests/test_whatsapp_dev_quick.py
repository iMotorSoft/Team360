"""Offline orchestration matrix: no real messages, Meta writes or service restarts."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from modules.telchi.assistant import whatsapp_dev_quick as quick


@pytest.fixture
def configured(monkeypatch, tmp_path):
    calls = []
    config = {'approval': tmp_path / 'approval'}
    monkeypatch.setattr(quick, 'operation_lock', nullcontext)
    monkeypatch.setattr(quick.dev, 'read_approval', lambda path: {})
    monkeypatch.setattr(quick.dev, 'gate_evidence', lambda approval: None)
    monkeypatch.setattr(quick.dev, 'configuration', lambda: (SimpleNamespace(evolution=None), None))
    async def database(*args):
        calls.append('database')
    monkeypatch.setattr(quick.dev, 'check_database', database)
    monkeypatch.setattr(quick, 'litellm_ready', lambda: True)
    monkeypatch.setattr(quick.control, 'status', lambda: {'state': 'STOPPED'})
    monkeypatch.setattr(quick, 'ensure_services', lambda: calls.append('ensure'))
    monkeypatch.setattr(quick.control, 'launch', lambda *args: calls.append('launch'))
    monkeypatch.setattr(quick.control, 'stop', lambda: calls.append('stop') or {'state': 'STOPPED'})
    def snapshot(*args):
        running = 'launch' in calls and 'stop' not in calls
        return dict(POSTGRES='READY', LITELLM='READY', EVOLUTION='READY', CLOUDFLARE='READY',
                    PUBLIC_URL='https://new-url.trycloudflare.com', META_CALLBACK='SYNCED',
                    SIX_GATES='PASS', WHATSAPP_RUNTIME='RUNNING' if running else 'STOPPED',
                    READY_FOR_DIALOGUE='YES' if running else 'NO',
                    BLOCKER='NONE' if running else 'RUNTIME_STOPPED')
    monkeypatch.setattr(quick, 'snapshot', snapshot)
    return config, calls, snapshot


def test_all_services_available_launch_once(configured):
    config, calls, _ = configured
    report = quick.operate('up', config, 'fixture.json', {})
    assert report['READY_FOR_DIALOGUE'] == 'YES'
    assert calls == ['database', 'ensure', 'launch']


def test_runtime_already_ready_no_duplicate(configured, monkeypatch):
    config, calls, snapshot = configured
    calls.append('launch')
    monkeypatch.setattr(quick.control, 'status', lambda: {'state': 'READY'})
    assert quick.operate('up', config, 'fixture.json', {})['READY_FOR_DIALOGUE'] == 'YES'
    assert calls.count('launch') == 1


@pytest.mark.parametrize('blocker', ['META_UPDATE_REQUIRES_EXPLICIT_AUTHORIZATION',
                                    'CLOUDFLARE_REVIEW_REQUIRED', 'EVOLUTION_NOT_READY'])
def test_preconditions_block_start_without_mutating_meta(configured, monkeypatch, blocker):
    config, calls, snapshot = configured
    def blocked(*args):
        report = snapshot(*args)
        report.update(BLOCKER=blocker, READY_FOR_DIALOGUE='NO', META_CALLBACK='UPDATE_REQUIRED')
        return report
    monkeypatch.setattr(quick, 'snapshot', blocked)
    assert quick.operate('up', config, 'fixture.json', {})['BLOCKER'] == blocker
    assert 'launch' not in calls


def test_new_url_prints_only_explicit_update_command(configured, capsys):
    _, _, snapshot = configured
    report = snapshot()
    report['META_CALLBACK'] = 'UPDATE_REQUIRED'
    quick.emit(report)
    assert 'AUTHORIZED_META_UPDATE_COMMAND=./meta-webhook-update.sh https://new-url.trycloudflare.com --apply' in capsys.readouterr().out


def test_degraded_gates_no_services_or_runtime(configured, monkeypatch):
    config, calls, _ = configured
    def invalid(*args):
        raise ValueError('gate_source_mismatch')
    monkeypatch.setattr(quick.dev, 'gate_evidence', invalid)
    with pytest.raises(RuntimeError, match='SIX_GATES_DEGRADED'):
        quick.operate('up', config, 'fixture.json', {})
    assert calls == []


def test_postgres_down_no_services_started(configured, monkeypatch):
    config, calls, _ = configured
    async def unavailable(*args):
        raise RuntimeError('fixture_db_unavailable')
    monkeypatch.setattr(quick.dev, 'check_database', unavailable)
    with pytest.raises(RuntimeError):
        quick.operate('up', config, 'fixture.json', {})
    assert calls == []


def test_litellm_down_never_restarted(configured, monkeypatch):
    config, calls, _ = configured
    monkeypatch.setattr(quick, 'litellm_ready', lambda: False)
    with pytest.raises(RuntimeError, match='LITELLM_UNAVAILABLE'):
        quick.operate('up', config, 'fixture.json', {})
    assert calls == ['database']


def test_historical_review_fences_infrastructure(configured, monkeypatch):
    config, calls, _ = configured
    monkeypatch.setattr(quick.control, 'status', lambda: {'state': 'REVIEW_REQUIRED'})
    with pytest.raises(RuntimeError, match='previous_session'):
        quick.operate('up', config, 'fixture.json', {})
    assert calls == ['database']


def test_down_only_requests_canonical_runtime_stop(configured):
    config, calls, _ = configured
    quick.operate('down', config, 'fixture.json', {})
    quick.operate('down', config, 'fixture.json', {})
    assert calls == ['stop', 'stop']


@pytest.mark.parametrize('state,expected', [('READY', []), ('STOPPED', ['cloudflare-start.sh']),
                                           ('DEGRADED', None), ('REVIEW_REQUIRED', None)])
def test_cloudflare_start_only_when_verified_absent(monkeypatch, state, expected):
    calls = []
    monkeypatch.setattr(quick.control, 'adopted_container', lambda: ('cid', {'State': {'Running': True}}))
    states = iter([state, 'READY'])
    monkeypatch.setattr(quick, 'cloud_state', lambda: next(states))
    monkeypatch.setattr(quick, 'script', lambda name: calls.append(name) or (0, ''))
    if expected is None:
        with pytest.raises(RuntimeError):
            quick.ensure_services()
        assert calls == []
    else:
        quick.ensure_services()
        assert calls == expected


def test_stopped_evolution_reuses_approved_script_then_readiness(monkeypatch):
    calls = []
    container = {'Id': 'cid', 'Image': 'sha256:installed', 'State': {'Running': False}}
    monkeypatch.setattr(quick.control, 'adopted_container', lambda: ('cid', container))
    monkeypatch.setattr(quick.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='cid\n'))
    monkeypatch.setattr(quick, 'script', lambda name, **kwargs: calls.append(name) or (0, ''))
    monkeypatch.setattr(quick, 'cloud_state', lambda: 'READY')
    monkeypatch.setattr(quick.dev, 'configuration', lambda: (SimpleNamespace(evolution=SimpleNamespace(instance='fixture')), None))
    monkeypatch.setattr(quick.dev, 'client_for', lambda cfg: nullcontext(None))
    monkeypatch.setattr(quick.dev, 'api', lambda *args: {'instance': {'state': 'open'}})
    quick.ensure_services()
    assert calls == ['start.sh']


def test_unverified_evolution_never_provisioned(monkeypatch):
    monkeypatch.setattr(quick.control, 'adopted_container', lambda: (_ for _ in ()).throw(ValueError('identity')))
    monkeypatch.setattr(quick, 'script', lambda *a: pytest.fail('provisioning attempted'))
    with pytest.raises(ValueError):
        quick.ensure_services()


@pytest.mark.parametrize('synchronized', [True, False])
def test_real_snapshot_contract_with_read_only_meta(monkeypatch, tmp_path, synchronized):
    monkeypatch.setattr(quick, 'LAB', tmp_path)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/cloudflared.url').write_text('https://new-url.trycloudflare.com\n')
    monkeypatch.setattr(quick.dev, 'read_approval', lambda *a: {})
    monkeypatch.setattr(quick.dev, 'gate_evidence', lambda *a: None)
    monkeypatch.setattr(quick.dev, 'configuration', lambda: (SimpleNamespace(evolution=SimpleNamespace(instance='fixture')), None))
    async def database(*a):
        pass
    monkeypatch.setattr(quick.dev, 'check_database', database)
    monkeypatch.setattr(quick, 'litellm_ready', lambda: True)
    monkeypatch.setattr(quick.control, 'adopted_container', lambda: ('cid', {'State': {'Running': True}}))
    monkeypatch.setattr(quick.dev, 'client_for', lambda *a: nullcontext(None))
    monkeypatch.setattr(quick.dev, 'api', lambda *a: {'instance': {'state': 'open'}})
    monkeypatch.setattr(quick, 'cloud_state', lambda: 'READY')
    monkeypatch.setattr(quick.control, 'status', lambda: {'state': 'READY'})
    calls = []
    class Updater:
        def __init__(self, *a):
            pass
        def inventory(self):
            calls.append('GET')
            origin = 'new-url' if synchronized else 'old-url'
            return {'callback_url': f'https://{origin}.trycloudflare.com/webhook/meta'}, {}
        def challenge(self, *a):
            calls.append('GET_CHALLENGE')
    monkeypatch.setattr(quick.meta, 'Updater', Updater)
    report = quick.snapshot({}, {})
    assert report['META_CALLBACK'] == ('SYNCED' if synchronized else 'UPDATE_REQUIRED')
    assert report['READY_FOR_DIALOGUE'] == ('YES' if synchronized else 'NO')
    assert report['SIX_GATES'] == 'PASS'
    assert calls == ['GET', 'GET_CHALLENGE', 'GET_CHALLENGE']
