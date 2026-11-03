"""Ranking registry guard/idempotency tests; no DB mutations."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from modules.telchi.provisioning import ranking_repository as m
from modules.telchi.provisioning.repository import Conflict


def state():
    records = {t: [] for t in m.SECURITY_TABLES}
    records['core_module_full_access_grants'] = [dict(workspace_id=m.WORKSPACE,
        organization_id=m.ORGANIZATION, module='telchi', user_id=m.PILOT, revoked_at_utc=None)]
    records['core_permissions'] = [dict(id='p', permission_code=m.PERMISSION)]
    records['core_workspace_capabilities'] = [dict(permission_id='p', capability_code=m.CAPABILITY,
        workspace_id=m.WORKSPACE, module='telchi', enabled=True)]
    return dict(records=records, effective={m.PILOT: [m.PERMISSION], 'normal': []})


def repo(s):
    r = m.RankingRegistrationRepository()
    r.guard = AsyncMock()
    r.target = AsyncMock(return_value=m.TARGET)
    r.identities = AsyncMock(return_value=dict(workspace=dict(id=m.WORKSPACE, organization_id=m.ORGANIZATION),
        pilot=dict(id=m.PILOT), **{'global': {'id': 'owner'}}))
    r.security_state = AsyncMock(return_value=s)
    r.audit = AsyncMock()
    return r


def activate(r, **kwargs):
    return asyncio.run(r.activate(AsyncMock(), authorization=kwargs.get('authorization', m.AUTHORIZATION),
                                 backup_sha256=kwargs.get('backup_sha256', 'a'*64)))


@pytest.mark.parametrize('kwargs', [dict(authorization='other'), dict(backup_sha256=''), dict(backup_sha256='x'*64)])
def test_explicit_owner_and_backup(kwargs):
    r = repo(state())
    with pytest.raises(Conflict): activate(r, **kwargs)
    r.guard.assert_not_called()


@pytest.mark.parametrize('axis', ['target', 'workspace', 'missing_grant', 'foreign_grant', 'extra_grant',
                                  'wildcard', 'role', 'profile', 'foreign_registry', 'disabled'])
def test_fail_closed_before_writes(axis):
    s = state()
    r = repo(s)
    if axis == 'target': r.target.return_value = {}
    elif axis == 'workspace': r.identities.return_value['workspace']['id'] = 'foreign'
    elif axis == 'missing_grant': s['records']['core_module_full_access_grants'] = []
    elif axis == 'foreign_grant': s['records']['core_module_full_access_grants'][0]['organization_id'] = 'foreign'
    elif axis == 'extra_grant': s['records']['core_module_full_access_grants'] *= 2
    elif axis == 'wildcard': s['records']['core_permissions'].append(dict(id='other', permission_code='telchi.*'))
    elif axis in ('role', 'profile'): s['records']['core_'+axis+'_permissions'] = [dict(permission_id='p')]
    elif axis == 'foreign_registry': s['records']['core_workspace_capabilities'][0]['workspace_id'] = 'foreign'
    elif axis == 'disabled': s['records']['core_workspace_capabilities'][0]['enabled'] = False
    with pytest.raises(Conflict): activate(r)
    r.audit.assert_not_called()


def test_idempotent_no_assignments_or_full_access_changes():
    s = state()
    r = repo(s)
    with patch.object(m.ProvisioningRepository, 'ensure', AsyncMock(return_value={'id': 'p'})), \
         patch.object(m, 'one', AsyncMock(return_value=s['records']['core_workspace_capabilities'][0])):
        result = activate(r)
    assert not result['changed'] and not result['assignments_created'] and not result['full_access_changed']
    r.audit.assert_not_called()


def test_unrelated_permission_change_aborts():
    s = state()
    after = deepcopy(s)
    after['effective']['normal'] = [m.PERMISSION]
    r = repo(s)
    r.security_state.side_effect = [s, after]
    with patch.object(m.ProvisioningRepository, 'ensure', AsyncMock(return_value={'id': 'p'})), \
         patch.object(m, 'one', AsyncMock(return_value=s['records']['core_workspace_capabilities'][0])):
        with pytest.raises(Conflict): activate(r)
    r.audit.assert_not_called()


@pytest.mark.parametrize('environment', ['', 'production'])
def test_cli_dev_only(monkeypatch, environment):
    from modules.telchi.provisioning.ranking_cli import run
    monkeypatch.setenv('TEAM360_ENV', environment)
    with pytest.raises(Conflict): asyncio.run(run(SimpleNamespace(apply=True)))
