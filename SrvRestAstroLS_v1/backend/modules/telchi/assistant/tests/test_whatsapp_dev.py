"""Offline contracts only: no PostgreSQL, model, Podman or Evolution calls."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import inspect
import json
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant.whatsapp_dev_evidence import evaluate


@pytest.fixture
def settings():
    return SimpleNamespace(webhook_token='t'*32, authorized_sender='15550000001')


def payload(sender='15550000001'):
    return dict(event='messages.upsert', instance='test', data=dict(
        key=dict(id='fixture-id', remoteJid=sender+'@s.whatsapp.net', fromMe=False),
        message=dict(conversation='fixture question')))


async def request(settings, body, token=None, path=dev.WEBHOOK):
    called, responses = [], []
    async def app(scope, receive, send):
        called.append(await receive())
        await send(dict(type='http.response.start', status=200, headers=[]))
    boundary = dev.PilotBoundary(app, settings, SimpleNamespace(instance='test'), 'receiver')
    async def receive():
        return dict(type='http.request', body=body, more_body=False)
    async def send(value):
        responses.append(value)
    await boundary(dict(type='http', path=path, method='POST',
        headers=[(b'x-team360-webhook-token', (token if token is not None else settings.webhook_token).encode())]), receive, send)
    return responses[0]['status'], called


@pytest.mark.parametrize('token', ['', 'incorrect'])
def test_auth_before_json_decode(settings, token):
    assert asyncio.run(request(settings, b'not json', token))[0] == 401


def test_nonpilot_never_reaches_shared_pipeline(settings):
    status, calls = asyncio.run(request(settings, json.dumps(payload('15550000002')).encode()))
    assert status == 403 and not calls


def test_pilot_unmodified_real_pipeline(settings):
    raw = json.dumps(payload()).encode()
    status, calls = asyncio.run(request(settings, raw))
    assert status == 200 and calls[0]['body'] == raw


def test_mixed_batch_rejected(settings):
    batch = payload()
    batch['data'] = [batch['data'], payload('15550000002')['data']]
    status, calls = asyncio.run(request(settings, json.dumps(batch).encode()))
    assert status == 403 and not calls


@pytest.mark.parametrize('body,status', [(b'bad-json', 400), (b'x'*1_048_577, 413)])
def test_bad_body(settings, body, status):
    assert asyncio.run(request(settings, body))[0] == status


def test_other_surfaces_closed(settings):
    assert asyncio.run(request(settings, b'{}', path='/api/console'))[0] == 404


def test_status_and_connection_events_use_existing_webhook(settings):
    for value in [dict(event='connection.update', instance='test'),
                  dict(event='messages.update', instance='test', data=dict(keyId='fixture-id', status='READ'))]:
        assert asyncio.run(request(settings, json.dumps(value).encode()))[0] == 200


def test_webhook_roundtrip_and_unknown_fields():
    value = dict(enabled=False, url='http://previous.test/hook', headers={'secret': 'private'},
                 events=['MESSAGES_UPSERT'], webhookByEvents=True, webhookBase64=False, id='ignored')
    normalized = dev.webhook_body(value)
    assert dev.webhook_body(normalized) == normalized
    assert normalized['headers'] == value['headers'] and normalized['byEvents']
    with pytest.raises(ValueError):
        dev.webhook_body(dict(value, unknownSecuritySetting=True))


@pytest.mark.parametrize('current,expected_posts', [('previous', 0), ('temporary', 1)])
def test_restore_verified(monkeypatch, current, expected_posts):
    backup = dict(previous=dev.webhook_body(dict(url='http://old.test', enabled=False)),
                  temporary=dev.webhook_body(dict(url='http://new.test', enabled=True)))
    state, posts = [backup[current]], []
    def api(client, method, path, body=None):
        if method == 'POST':
            posts.append(body)
            state[0] = body['webhook']
        return state[0]
    monkeypatch.setattr(dev, 'api', api)
    dev.restore(None, 'test', backup)
    assert len(posts) == expected_posts and state[0] == backup['previous']


def test_restore_preserves_foreign_owner(monkeypatch):
    backup = dict(previous=dev.webhook_body(dict(url='http://old.test')),
                  temporary=dev.webhook_body(dict(url='http://new.test', enabled=True)))
    def api(client, method, path, body=None):
        assert method == 'GET'
        return dict(url='http://foreign.test', enabled=True)
    monkeypatch.setattr(dev, 'api', api)
    with pytest.raises(RuntimeError, match='other_owner'):
        dev.restore(None, 'test', backup)


def test_restore_requires_readback(monkeypatch):
    backup = dict(previous=dev.webhook_body(dict(url='http://old.test')),
                  temporary=dev.webhook_body(dict(url='http://new.test', enabled=True)))
    monkeypatch.setattr(dev, 'api', lambda *a, **kw: backup['temporary'])
    with pytest.raises(RuntimeError, match='not_verified'):
        dev.restore(None, 'test', backup)


@pytest.fixture
def approval(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    evidence = tmp_path/'business.json'
    dev.save_private(evidence, dict(owner_approval='fixture only'))
    value = dict(environment='dev', tenant_id='telchi', workspace_id='workspace', user_id='pilot',
        access='assistant', revoked=False, module_enabled=True, whole_workspace_scope_verified=True,
        sender_sha256=hashlib.sha256(b'15550000001').hexdigest(),
        approved_by='fixture owner', issued_at=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat(),
        business_evidence_file=str(evidence), business_evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
        gates_file=str(tmp_path/'gates.json'))
    return value, tmp_path/'approval.json'


def test_approval_has_no_implicit_enable_or_scope(approval):
    value, path = approval
    dev.save_private(path, value)
    assert dev.read_approval(path) == value
    for key in ('module_enabled', 'whole_workspace_scope_verified'):
        path.unlink()
        dev.save_private(path, dict(value, **{key: False}))
        with pytest.raises(PermissionError):
            dev.read_approval(path)


def test_approval_evidence_changed_blocks(approval):
    value, path = approval
    dev.save_private(path, dict(value, business_evidence_sha256='wrong'))
    with pytest.raises(PermissionError):
        dev.read_approval(path)


def test_public_private_file_rejected(approval):
    _, path = approval
    dev.save_private(path, {})
    path.chmod(0o644)
    with pytest.raises(ValueError):
        dev.private_file(path)


def test_doubles_never_satisfy_real_gates(approval, monkeypatch):
    value, _ = approval
    monkeypatch.setattr(dev, 'source_digest', lambda: 'fixture-source')
    gate = dict(status='PASS', kind='double')
    report = dict(workspace_id=value['workspace_id'], user_id=value['user_id'], instance='team360-meta-dev',
        approval_sha256=dev.approval_digest(value), source_sha256='fixture-source', expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
        gates={name: gate for name in dev.GATES})
    dev.save_private(Path(value['gates_file']), report)
    with pytest.raises(ValueError, match='real_gate'):
        dev.gate_evidence(value)


def test_preflight_does_not_activate_or_spawn(monkeypatch):
    approval = {'sender_sha256': hashlib.sha256(b'15550000001').hexdigest()}
    srv = SimpleNamespace(evolution=SimpleNamespace(instance='test'))
    settings = SimpleNamespace(authorized_sender='15550000001')
    monkeypatch.setattr(dev, 'read_approval', lambda _: approval)
    monkeypatch.setattr(dev, 'configuration', lambda: (srv, settings))
    async def check(*args):
        return 'binding'
    monkeypatch.setattr(dev, 'check_database', check)
    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(dev, 'client_for', lambda _: Client())
    calls = []
    def api(client, method, path, body=None):
        calls.append(method)
        assert method == 'GET'
        return {'instance': {'state': 'open'}} if 'connectionState' in path else dict(enabled=False, url='http://old.test')
    monkeypatch.setattr(dev, 'api', api)
    monkeypatch.setattr(dev, 'gate_evidence', lambda _: None)
    assert dev.preflight('private')[3] == 'binding'
    assert calls == ['GET', 'GET']


def test_node_probe_parses_without_network():
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable for syntax check')
    code = re.search(r'code = """(.*?)"""', inspect.getsource(dev.container_probe), re.S).group(1)
    result = subprocess.run([node, '--check'], input=code, text=True, capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('change_based', [False, True])
@pytest.mark.parametrize('failure', ['container', 'configuration_timeout', 'interrupt', 'restore_failure'])
def test_session_failure_cleans_only_owned_child(approval, monkeypatch, failure, change_based):
    value, path = approval
    settings = SimpleNamespace(webhook_token='t'*32)
    srv = SimpleNamespace(evolution=SimpleNamespace(instance='test'))
    monkeypatch.setattr(dev, 'preflight', lambda _: (value, srv, settings, None))
    monkeypatch.setattr(dev, 'gate_evidence', lambda _: None if change_based else
                        datetime.now(timezone.utc)+timedelta(hours=1))
    dev.save_private(path, value)
    previous = dev.webhook_body(dict(url='http://old.test', enabled=False))
    current = [previous]
    posts, children = [], []
    def api(client, method, route, body=None):
        if method == 'POST':
            if not posts:
                lifecycle = json.loads((path.parent/'whatsapp-dev-control/current.json').read_text())
                assert lifecycle['state'] == 'STARTING'
                assert lifecycle['webhook_attempted'] is True
            posts.append(body)
            if len(posts) == 2 and failure == 'restore_failure':
                raise RuntimeError('fixture restore failed')
            current[0] = body['webhook']
            if len(posts) == 1 and failure == 'configuration_timeout':
                raise RuntimeError('fixture ambiguous configuration timeout')
        return current[0]
    monkeypatch.setattr(dev, 'api', api)
    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, path):
            return SimpleNamespace(status_code=200, headers={'x-team360-session': 'n'*64})
    monkeypatch.setattr(dev, 'client_for', lambda _: Client())
    monkeypatch.setattr(dev.httpx, 'Client', Client)
    import secrets
    monkeypatch.setattr(secrets, 'token_hex', lambda _: 'n'*64)
    class Socket(Client):
        def bind(self, target):
            pass
    monkeypatch.setattr(dev.socket, 'socket', Socket)
    monkeypatch.setattr(dev.signal, 'signal', lambda *args: None)
    class Child:
        pid = dev.os.getpid()  # Identity double only; terminate below never signals.
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            self.stopped = True
        def wait(self, timeout):
            assert self.stopped
    def popen(argv, **kwargs):
        assert argv[:3] == [dev.sys.executable, '-m', dev.MODULE]
        assert kwargs['env']['TEAM360_TELCHI_WHATSAPP_NONCE'] == 'n'*64
        child = Child()
        children.append(child)
        return child
    monkeypatch.setattr(dev.subprocess, 'Popen', popen)
    from modules.telchi.assistant import whatsapp_dev_lifecycle as control
    monkeypatch.setattr(control, 'wait_backend_identity', lambda process, argv: control.identity(process.pid))
    def container(*args):
        if failure == 'container':
            raise RuntimeError('fixture container unreachable')
    monkeypatch.setattr(dev, 'container_probe', container)
    def sleep(seconds):
        lifecycle = json.loads((path.parent/'whatsapp-dev-control/current.json').read_text())
        assert lifecycle['state'] == 'READY'
        assert lifecycle['backend'] and lifecycle['listener']['nonce_sha256']
        backup = json.loads((Path(args.output)/'webhook-backup.json').read_text())
        assert current[0] == backup['temporary']
        raise KeyboardInterrupt
    monkeypatch.setattr(dev.time, 'sleep', sleep)
    args = SimpleNamespace(approval=path, output=str(path.parent/'session'),
        duration=60, host='192.0.2.1', port=18181, container='fixture')
    with pytest.raises((RuntimeError, KeyboardInterrupt)):
        dev.start(args)
    assert len(children) == 1 and children[0].stopped
    closure = json.loads((Path(args.output)/'closure.json').read_text())
    assert closure['backend_stopped']
    assert current[0] == previous if failure != 'restore_failure' else current[0]['enabled']
    assert len(posts) == (0 if failure == 'container' else 2)
    assert closure['webhook_restored'] == (failure != 'restore_failure')
    lifecycle = json.loads((path.parent/'whatsapp-dev-control/current.json').read_text())
    assert lifecycle['state'] == ('REVIEW_REQUIRED' if failure == 'restore_failure' else 'STOPPED')
    assert closure['status'] == ('REVIEW_REQUIRED' if failure == 'restore_failure' else 'CLOSED')
    assert closure['review_reasons'] == (['webhook_restoration_not_verified']
                                         if failure == 'restore_failure' else [])
    assert closure['runtime_incident'] in {'RuntimeError', 'KeyboardInterrupt'}
    assert lifecycle['backend_stopped'] and lifecycle['closed_at']
    assert (Path(args.output)/'webhook-backup.json').stat().st_mode & 0o077 == 0


def test_forced_cleanup_only_targets_owned_session_group(monkeypatch):
    signals = []
    class Child:
        pid = 123456
        waits = 0
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            pass
        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired('fixture', timeout)
            self.stopped = True
    child = Child()
    monkeypatch.setattr(dev.os, 'getpgid', lambda pid: pid)
    monkeypatch.setattr(dev.os, 'killpg', lambda pgid, sig: signals.append((pgid, sig)))
    assert dev.stop_owned(child)
    assert signals == [(child.pid, dev.signal.SIGKILL)]


def exchange():
    owner = ['dev', 'telchi', 'workspace', 'channel', 'pilot']
    audit = dict(owner=owner, execution_status='executed', capability_calls=1,
        required_permission='telchi.sales.source_quantity.read.v1', response_prepared={'text': 'fixture result'},
        execution_result=dict(capability='telchi.sales_top_items.source_quantity.20260101_20260915.v1',
            source=dict(publication_id='fixture-publication', snapshot_id=1, updated_at='fixture-date')))
    inbound = dict(id='inbound', thread_id='thread', direction='inbound', event_type='message',
        payload_jsonb=dict(metadata={'raw_event_reference': 'hash'}, telchi_assistant_v1=audit,
        dispatch_result=dict(classification='DIRECT_AVAILABLE', correlation_id='inbound', text='fixture result')))
    outbound = dict(id='outbound', thread_id='thread', direction='outbound', event_type='message',
        correlation_id='inbound', provider_message_id='receipt', transport_status='accepted',
        payload_jsonb={'text': 'fixture result'})
    return [inbound, outbound]


@pytest.mark.parametrize('capability,permission', [
    ('sales.invoice_lines.v1','telchi.sales.invoice_lines.read.v1'),
    ('sales.invoice_amount.v1','telchi.sales.invoice_amount.read.v1')])
def test_invoice_evidence_uses_specific_permission(capability,permission):
    rows=exchange()
    audit=rows[0]['payload_jsonb']['telchi_assistant_v1']
    audit['execution_result']['capability']=capability
    audit['required_permission']=permission
    result=evaluate(rows,SimpleNamespace(channel_id='channel'),dict(workspace_id='workspace',user_id='pilot'),'inbound')
    assert result['capability']==capability and result['E2E']=='NOT_DECLARED'
    audit['required_permission']='telchi.sales.latest_documents.read.v1'
    with pytest.raises(ValueError,match='capability_permission_contract_mismatch'):
        evaluate(rows,SimpleNamespace(channel_id='channel'),dict(workspace_id='workspace',user_id='pilot'),'inbound')


def test_acceptance_is_not_delivery_or_read():
    report = evaluate(exchange(), SimpleNamespace(channel_id='channel'),
        dict(workspace_id='workspace', user_id='pilot'), 'inbound')
    assert report['provider_accepted'] and not report['delivered_callback'] and not report['read_callback']
    assert report['E2E'] == 'NOT_DECLARED'
    assert 'fixture result' not in json.dumps(report) and 'receipt' not in json.dumps(report)


@pytest.mark.parametrize('mutation', ['duplicate_reply', 'http_adapter', 'wrong_owner', 'no_execution'])
def test_incomplete_evidence_rejected(mutation):
    rows = exchange()
    if mutation == 'duplicate_reply':
        rows.append(deepcopy(rows[1]))
    elif mutation == 'http_adapter':
        rows[0]['payload_jsonb']['dev_adapter'] = True
    elif mutation == 'wrong_owner':
        rows[0]['payload_jsonb']['telchi_assistant_v1']['owner'][1] = 'other-tenant'
    else:
        rows[0]['payload_jsonb']['telchi_assistant_v1']['capability_calls'] = 0
    with pytest.raises(ValueError):
        evaluate(rows, SimpleNamespace(channel_id='channel'),
            dict(workspace_id='workspace', user_id='pilot'), 'inbound')
