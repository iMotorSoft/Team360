"""Pure contract tests; no human accounts/tokens or live database are created."""
import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from modules.business_semantics.authenticated_gate import load_manifest
from modules.business_semantics import runtime_connection as runtime
from modules.telchi.assistant.handler import TelchiHandler


def test_manifest_requires_four_distinct_subjects_and_other_workspace(tmp_path):
    workspace = str(uuid.uuid4())
    identities = [dict(slot=slot, email=slot+'@example.invalid', workspace='dev',
                       user_id=str(uuid.uuid4()), workspace_id=workspace if slot != 'tenant-b' else str(uuid.uuid4()))
                  for slot in ('user-a', 'user-b', 'tenant-b', 'admin')]
    path = tmp_path/'manifest.json'
    path.write_text(json.dumps({'identities': identities}))
    assert len(load_manifest(path)) == 4
    identities[-1]['user_id'] = identities[0]['user_id']
    path.write_text(json.dumps({'identities': identities}))
    with pytest.raises(ValueError, match='distinct'):
        load_manifest(path)


def test_restricted_connection_pin_role_guard_and_cleanup(monkeypatch):
    events = []
    @asynccontextmanager
    async def transaction():
        events.append('begin')
        try:
            yield
        finally:
            events.append('end')
    conn = SimpleNamespace(transaction=transaction)
    @asynccontextmanager
    async def connected():
        try:
            yield conn
        finally:
            events.append('close')
    connect = AsyncMock(return_value=connected())
    guard = AsyncMock()
    monkeypatch.setenv('TEAM360_ENV', 'dev')
    monkeypatch.setattr(runtime, 'read_config', lambda _: {'runtime_dsn': 'synthetic', 'target': {'pin': 'synthetic'}})
    monkeypatch.setattr(runtime.psycopg.AsyncConnection, 'connect', connect)
    monkeypatch.setattr(runtime, 'checked_target', guard)
    factory = runtime.RestrictedSemanticsConnection('synthetic')
    handler = TelchiHandler(store=None, authorization=None, semantics_connection=factory)
    async def exercise():
        async with handler._semantics_turn({'conn': 'global-connection-must-not-be-used'}) as actual:
            assert actual is conn
    asyncio.run(exercise())
    guard.assert_awaited_once_with(conn, {'pin': 'synthetic'}, runtime=True)
    assert events == ['begin', 'end', 'close']
    monkeypatch.setenv('TEAM360_ENV', 'production')
    with pytest.raises(PermissionError):
        asyncio.run(exercise())
    assert connect.await_count == 1


@pytest.mark.parametrize('mode,slot', [(m, s) for m in ('full', 'diagnostic-three')
                                     for s in ('user-a', 'user-b', 'tenant-b', 'admin')
                                     if m == 'full' or s != 'user-b'])
def test_authenticated_gate_contracts_with_explicit_doubles(monkeypatch, tmp_path, mode, slot):
    from modules.business_semantics import authenticated_gate as gate
    from modules.console.auth import ConsoleAuthError
    import psycopg
    identities = [dict(slot=s, user_id=s, workspace_id='other' if s == 'tenant-b' else 'telchi')
                  for s in ('user-a', 'user-b', 'tenant-b', 'admin')]
    if mode == 'diagnostic-three':
        identities = [i for i in identities if i['slot'] != 'user-b']
    identity = next(i for i in identities if i['slot'] == slot)
    transactions = []
    @asynccontextmanager
    async def transaction(**kwargs):
        transactions.append(kwargs)
        yield
    conn = SimpleNamespace(transaction=transaction)
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setattr(gate.psycopg.AsyncConnection, 'connect', AsyncMock(return_value=connection()))
    monkeypatch.setattr(gate, 'checked_target', AsyncMock())
    monkeypatch.setattr(gate, 'issuer_settings', lambda cfg: None)
    class Login:
        def __init__(self, settings): pass
        async def verify_session(self, conn, token, workspace_id):
            if workspace_id != identity['workspace_id']:
                raise ConsoleAuthError('wrong workspace')
            return SimpleNamespace(user_id=identity['user_id'])
    monkeypatch.setattr(gate, 'ConsoleLoginService', Login)
    class Repository:
        async def scope(self, conn, workspace):
            return dict(organization_id=workspace, organization_code=workspace)
        async def authorize(self, *args): pass
        async def catalog(self, *args):
            return [dict(concept_id='synthetic-concept', version=1, semantic_code='synthetic.code')]
    monkeypatch.setattr(gate, 'BusinessConceptRepository', Repository)
    class Resolver:
        async def resolve(self, conn, **kwargs):
            if kwargs['workspace_id'] != identity['workspace_id']:
                raise PermissionError('foreign')
            return dict(status='resolved')
    monkeypatch.setattr(gate, 'BusinessConceptResolver', Resolver)
    actions = []
    class Admin:
        async def execute(self, conn, **kwargs):
            if kwargs['workspace_id'] != identity['workspace_id'] or slot != 'admin':
                raise PermissionError('not admin')
            if kwargs['payload'].get('alias', '').startswith('Forbidden'):
                raise psycopg.errors.RaiseException('immutable')
            actions.append(kwargs['action'])
            return dict(concept_id='synthetic-concept', version=1)
    monkeypatch.setattr(gate, 'BusinessConceptAdministration', Admin)
    path = tmp_path/'synthetic-token-stub'
    path.write_text('not-a-valid-token; login-service-is-a-double')
    monkeypatch.setattr(gate, 'private_path', lambda path, **kwargs: path)
    result = asyncio.run(gate.validate({'runtime_dsn': 'synthetic', 'target': {}}, identity, path, identities))
    assert result['status'] == 'PASS' and result['rollback_only']
    assert transactions[0] == {'force_rollback': True}
    assert result['checks']['foreign_session_rejected']
    if slot == 'admin':
        assert actions.index('alias') < actions.index('publish')
        assert result['checks']['published_alias_mutation_denied']
    else:
        assert not actions


@pytest.mark.parametrize('mode', ['full', 'diagnostic-three'])
@pytest.mark.parametrize('failure', [False, True, 'inactive', 'wrong_tenant', 'reader_is_admin', 'admin_is_reader'])
def test_ceremony_consumes_each_login_immediately_and_cleans_tokens(monkeypatch, tmp_path, mode, failure):
    from modules.business_semantics import authenticated_gate as gate
    identities = [dict(slot=s, email=s+'@example.invalid', workspace='other' if s == 'tenant-b' else 'telchi',
                       user_id=s, workspace_id='other' if s == 'tenant-b' else 'telchi')
                  for s in ('user-a', 'user-b', 'tenant-b', 'admin')]
    if mode == 'diagnostic-three':
        identities = [i for i in identities if i['slot'] != 'user-b']
    config = tmp_path/'synthetic-config'
    output = tmp_path/'result.json'
    monkeypatch.setattr(gate, 'read_config', lambda _: {'runtime_dsn': 'synthetic', 'target': {}})
    monkeypatch.setattr(gate, 'private_path', lambda path, **kwargs: path)
    monkeypatch.setattr(gate, 'load_manifest', lambda _, selected_mode: identities)
    monkeypatch.setattr(gate, 'service_actor', AsyncMock(return_value=failure != 'inactive'))
    monkeypatch.setattr(gate, 'checked_target', AsyncMock())
    @asynccontextmanager
    async def connection():
        yield object()
    monkeypatch.setattr(gate.psycopg.AsyncConnection, 'connect', AsyncMock(return_value=connection()))
    class Repository:
        async def scope(self, conn, workspace):
            return dict(organization_id=workspace, organization_code='unexpected' if failure == 'wrong_tenant' else workspace)
        async def authorize(self, conn, org, workspace, actor, admin=False):
            if admin and (failure == 'admin_is_reader' or (actor != 'admin' and failure != 'reader_is_admin')):
                raise PermissionError('reader')
    monkeypatch.setattr(gate, 'BusinessConceptRepository', Repository)
    timeline = []
    def command(argv, **kwargs):
        assert 'set-password' not in argv  # No implicit activation.
        if 'login' in argv:
            email = argv[argv.index('--email')+1]
            slot = email.split('@')[0]
            timeline.append(('login', slot))
            from pathlib import Path
            Path(argv[argv.index('--token-output')+1]).write_text('explicit synthetic token stub')
            return SimpleNamespace(returncode=0)
        assert 'list' in argv
        slot = timeline[-1][1]
        return SimpleNamespace(returncode=0 if slot == 'admin' else 1)
    monkeypatch.setattr(gate.subprocess, 'run', command)
    async def validate(cfg, identity, token, identities):
        timeline.append(('validate', identity['slot']))
        assert token.exists()
        if failure is True:
            raise PermissionError('synthetic authorization failure')
        return dict(slot=identity['slot'], checks={}, subject_hash=identity['slot'],
                    catalog_fingerprint='foreign' if identity['slot'] == 'tenant-b' else 'same')
    monkeypatch.setattr(gate, 'validate', validate)
    monkeypatch.setattr(gate.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(gate.sys, 'argv', ['gate', '--auth-config', str(config), '--manifest', str(tmp_path/'manifest'), '--output', str(output), '--mode', mode])
    monkeypatch.setenv('TEAM360_ENV', 'dev')
    if failure or mode == 'diagnostic-three':
        with pytest.raises(SystemExit) as exc:
            gate.main()
        assert exc.value.code == (1 if failure else 2)
    else:
        gate.main()
    exercised = [] if isinstance(failure, str) else identities[:1] if failure else identities
    assert timeline == [(action, i['slot']) for i in exercised for action in ('login', 'validate')]
    report = json.loads(output.read_text())
    assert report['status'] == ('FAIL' if failure else 'PASS' if mode == 'full' else 'PARTIAL')
    assert bool(report['missing_coverage']) == (mode == 'diagnostic-three')
    assert not list(tmp_path.glob('*.paseto'))


def test_semantics_connection_failure_does_not_fallback_to_global_or_luna():
    from modules.telchi.assistant.tests.test_assistant import setup, event, context
    handler, store, interpreter, calls = setup([])
    @asynccontextmanager
    async def denied():
        raise PermissionError('restricted role rejected')
        yield  # pragma: no cover
    handler.semantics_connection = denied
    handler.concept_resolver = SimpleNamespace(repository=None)
    result = asyncio.run(handler.handle(event(), context()))
    assert result.classification == 'ERROR'
    assert not calls and not interpreter.calls


def test_guard_failure_never_yields_runtime_connection(monkeypatch):
    @asynccontextmanager
    async def tx():
        yield
    conn = SimpleNamespace(transaction=tx)
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setenv('TEAM360_ENV', 'dev')
    monkeypatch.setattr(runtime, 'read_config', lambda _: {'runtime_dsn': 'synthetic', 'target': {}})
    monkeypatch.setattr(runtime.psycopg.AsyncConnection, 'connect', AsyncMock(return_value=connection()))
    monkeypatch.setattr(runtime, 'checked_target', AsyncMock(side_effect=PermissionError('privileged')))
    async def exercise():
        async with runtime.RestrictedSemanticsConnection('synthetic')():
            pytest.fail('guard must reject before yielding')
    with pytest.raises(PermissionError):
        asyncio.run(exercise())
