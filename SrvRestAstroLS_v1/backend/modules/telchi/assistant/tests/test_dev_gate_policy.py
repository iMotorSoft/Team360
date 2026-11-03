"""Admission contracts; real service evidence is preserved separately, never synthesized here."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from modules.telchi.assistant import whatsapp_dev as dev


@pytest.fixture
def manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    monkeypatch.setenv('TEAM360_ENV', 'dev')
    monkeypatch.setattr(dev, 'source_digest', lambda: 'current-source')
    approval = dict(environment='dev', workspace_id='workspace', user_id='pilot',
                    gates_file=str(tmp_path/'gates.json'))
    artifact = tmp_path/'real.json'
    dev.save_private(artifact, {'status': 'PASS', 'fixture_only': True,
                               'observations': {'fixture': {'status': 'PASS'}}})
    gate = dict(status='PASS', kind='real', observations=['fixture'], artifact=str(artifact),
                sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
    value = dict(schema_version=2, environment='dev', validity_policy=dev.DEV_GATE_POLICY,
                 issued_at=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat(),
                 workspace_id='workspace', user_id='pilot', instance='team360-meta-dev',
                 approval_sha256=dev.approval_digest(approval), source_sha256='current-source',
                 configuration_sha256=dev.configuration_digest(),
                 gates={name: dict(gate) for name in dev.GATES})
    def publish():
        path = Path(approval['gates_file'])
        path.unlink(missing_ok=True)
        dev.save_private(path, value)
    publish()
    return approval, value, publish


def test_dev_still_valid_after_thirty_days(manifest):
    assert dev.gate_evidence(manifest[0]) is None


@pytest.mark.parametrize('env', ['', 'production', 'prod', 'staging', 'unknown'])
def test_dev_manifest_never_accepted_outside_explicit_dev(manifest, monkeypatch, env):
    monkeypatch.setenv('TEAM360_ENV', env)
    with pytest.raises(ValueError, match='DEV_gate_policy'):
        dev.gate_evidence(manifest[0])


@pytest.mark.parametrize('change', ['source', 'config', 'contract', 'artifact', 'scope', 'missing', 'version', 'incomplete'])
def test_changes_and_corruption_reject(manifest, monkeypatch, change):
    approval, value, publish = manifest
    if change == 'source':
        monkeypatch.setattr(dev, 'source_digest', lambda: 'changed-code')
    elif change == 'contract':
        monkeypatch.setattr(dev, 'source_digest', lambda: 'changed-contract')
    elif change == 'config':
        monkeypatch.setenv('TEAM360_DB_SCHEMA', 'changed')
    elif change == 'artifact':
        Path(value['gates']['http_auth']['artifact']).write_text('corrupt')
    elif change == 'scope':
        value['user_id'] = 'different'
    elif change == 'missing':
        del value['gates']['http_auth']
    elif change == 'incomplete':
        value['gates']['http_auth']['observations'] = ['not_observed']
    else:
        value['schema_version'] = 3
    publish()
    with pytest.raises(ValueError):
        dev.gate_evidence(approval)


def test_valid_gates_do_not_override_live_rbac_or_pilot_revocation(manifest, monkeypatch):
    import asyncio
    from .test_pilot_access import policy, pilot_context
    from modules.telchi.assistant.handler import BusinessAuthorization
    from modules.console.repositories import PermissionConsoleRepository
    approval = manifest[0]
    revoked = False
    def check():
        dev.gate_evidence(approval)
        if revoked:
            raise PermissionError('revoked')
    grant = 'telchi.sales.latest_documents.read.v1'
    effective = {grant}
    async def live(*args):
        return effective
    monkeypatch.setattr(PermissionConsoleRepository, 'list_effective_permissions', live)
    async def run():
        nonlocal revoked
        auth = BusinessAuthorization(policy(check))
        context = pilot_context([grant])
        assert await auth.allowed(context, object(), required_permission=grant)
        effective.clear()
        assert dev.gate_evidence(approval) is None
        assert not await auth.allowed(context, object(), required_permission=grant)
        revoked = True
        assert not await auth.allowed(context)
    asyncio.run(run())


def test_legacy_production_expiration_unchanged(manifest, monkeypatch):
    approval, value, publish = manifest
    for key in ('schema_version', 'validity_policy', 'issued_at', 'environment'):
        del value[key]
    monkeypatch.setenv('TEAM360_ENV', 'production')
    value['expires_at'] = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    publish()
    assert dev.gate_evidence(approval) is not None
    value['expires_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    publish()
    with pytest.raises(ValueError, match='gates_expired'):
        dev.gate_evidence(approval)


def test_real_source_digest_covers_contracts_and_configuration(tmp_path, monkeypatch):
    backend = tmp_path/'backend'
    module = backend/'modules/telchi/assistant/whatsapp_dev.py'
    module.parent.mkdir(parents=True)
    for name in ('ls_iMotorSoft_Srv05.py', 'ls_iMotorSoft_Srv01.py',
                 'modules/srv05_settings.py', 'pyproject.toml', 'uv.lock'):
        target = backend/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('fixture')
    monkeypatch.setattr(dev, '__file__', str(module))
    before = dev.source_digest()
    contract = module.parent/'contract.json'
    contract.write_text('{}')
    assert dev.source_digest() != before
    before = dev.source_digest()
    contract.write_text('{"version": 2}')
    assert dev.source_digest() != before
    before = dev.source_digest()
    (backend/'modules/srv05_settings.py').write_text('changed')
    assert dev.source_digest() != before
