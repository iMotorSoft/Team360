"""Fail-closed category registration contracts; real DEV rehearsal is separate."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from modules.telchi.provisioning import category_repository as m
from modules.telchi.provisioning.repository import Conflict


def base():
    records = {t: [] for t in m.SECURITY_TABLES}
    records['core_module_full_access_grants'] = [dict(id='existing', workspace_id=m.WORKSPACE,
        organization_id=m.ORGANIZATION, module='telchi', user_id=m.PILOT, revoked_at_utc=None)]
    return dict(records=records, effective={m.PILOT: ['baseline'], 'normal': []})


def setup_repo(state):
    repo = m.CategoryRegistrationRepository()
    repo.guard = AsyncMock()
    repo.target = AsyncMock(return_value=m.TARGET)
    repo.identities = AsyncMock(return_value=dict(workspace=dict(id=m.WORKSPACE, organization_id=m.ORGANIZATION),
        pilot=dict(id=m.PILOT), **{'global': dict(id='owner')}))
    repo.security_state = AsyncMock(return_value=state)
    repo.audit = AsyncMock(return_value='audit')
    return repo


def activate(repo, conn, **kw):
    return asyncio.run(repo.activate(conn, authorization=kw.get('authorization', m.AUTHORIZATION),
                                    backup_sha256=kw.get('backup_sha256', 'a'*64)))


@pytest.mark.parametrize('kwargs', [dict(authorization='other'), dict(backup_sha256=''), dict(backup_sha256='x'*64)])
def test_owner_and_backup_before_any_query(kwargs):
    conn = AsyncMock()
    with pytest.raises(Conflict, match='authorization'):
        activate(m.CategoryRegistrationRepository(), conn, **kwargs)
    conn.execute.assert_not_called()


@pytest.mark.parametrize('axis', ['target', 'workspace', 'grant_missing', 'grant_foreign', 'grant_extra',
                                  'wildcard', 'role', 'profile', 'foreign_registry', 'disabled'])
def test_conflicts_before_catalog_writes(axis):
    state = base()
    repo = setup_repo(state)
    if axis == 'target':
        repo.target.return_value = {}
    elif axis == 'workspace':
        repo.identities.return_value['workspace']['id'] = 'foreign'
    elif axis == 'grant_missing':
        state['records']['core_module_full_access_grants'] = []
    elif axis == 'grant_foreign':
        state['records']['core_module_full_access_grants'][0]['organization_id'] = 'foreign'
    elif axis == 'grant_extra':
        state['records']['core_module_full_access_grants'].append(dict(
            state['records']['core_module_full_access_grants'][0], user_id='other'))
    elif axis == 'wildcard':
        state['records']['core_permissions'] = [dict(id='p', permission_code='telchi.*')]
    else:
        state['records']['core_permissions'] = [dict(id='p', permission_code=m.PERMISSION)]
        if axis in ('role', 'profile'):
            state['records']['core_'+axis+'_permissions'] = [dict(permission_id='p')]
        else:
            state['records']['core_workspace_capabilities'] = [dict(permission_id='p', capability_code=m.CAPABILITY,
                workspace_id='foreign' if axis == 'foreign_registry' else m.WORKSPACE,
                module='telchi', enabled=axis != 'disabled')]
    conn = AsyncMock()
    with pytest.raises(Conflict):
        activate(repo, conn)
    conn.execute.assert_not_called()


def test_already_registered_is_idempotent_without_assignments_or_audit():
    state = base()
    state['records']['core_permissions'] = [dict(id='p', permission_code=m.PERMISSION)]
    state['records']['core_workspace_capabilities'] = [dict(permission_id='p', capability_code=m.CAPABILITY,
        workspace_id=m.WORKSPACE, module='telchi', enabled=True)]
    state['effective'][m.PILOT].append(m.PERMISSION)
    state['effective'][m.PILOT].sort()
    repo = setup_repo(state)
    with patch.object(m.ProvisioningRepository, 'ensure', AsyncMock(return_value={'id':'p'})), \
         patch.object(m, 'one', AsyncMock(return_value=state['records']['core_workspace_capabilities'][0])):
        result = activate(repo, AsyncMock())
    assert result['changed'] is False
    assert result['assignments_created'] == 0 and result['full_access_changed'] is False
    repo.audit.assert_not_called()


@pytest.mark.parametrize('environment', ['', 'production'])
def test_cli_requires_explicit_dev_before_connection(monkeypatch, environment):
    from types import SimpleNamespace
    from modules.telchi.provisioning.category_cli import run
    monkeypatch.setenv('TEAM360_ENV', environment)
    with pytest.raises(Conflict, match='DEV environment'):
        asyncio.run(run(SimpleNamespace(apply=True)))


def test_unrelated_effective_delta_aborts():
    state = base()
    after = deepcopy(state)
    after['effective']['normal'] = [m.PERMISSION]
    repo = setup_repo(state)
    repo.security_state.side_effect = [state, after]
    with patch.object(m.ProvisioningRepository, 'ensure', AsyncMock(return_value={'id':'p'})), \
         patch.object(m, 'one', AsyncMock(return_value={'permission_id':'p'})):
        with pytest.raises(Conflict, match='effective permissions'):
            activate(repo, AsyncMock())
    repo.audit.assert_not_called()
