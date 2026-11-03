"""Isolated administrative rejection/delegation contracts; no operational users."""
import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from modules.telchi.provisioning.admin_service import validate, AdminService
from modules.telchi.provisioning.sales_repository import SalesActivationRepository, PERMISSIONS
from modules.telchi.provisioning.repository import Conflict


def manifest():
    return dict(version=1, environment='dev', command='manage-client', actor_id=str(uuid4()),
        workspace_id=str(uuid4()), operations=[dict(action='grant-sales', user_id=str(uuid4()),
            permissions=list(PERMISSIONS.values()), modules=['telchi'])])


@pytest.mark.parametrize('case', ['global_permission', 'extra', 'other_module', 'prod', 'unknown_action'])
def test_sales_catalog_closed(case):
    data = manifest()
    if case == 'global_permission': data['operations'][0]['permissions'] = ['user.manage']
    if case == 'extra': data['operations'][0]['permissions'].append('telchi.sales.net_amount.read.v1')
    if case == 'other_module': data['operations'][0]['modules'] = ['flow']
    if case == 'prod': data['environment'] = 'production'
    if case == 'unknown_action': data['operations'][0]['action'] = 'free-sql'
    with pytest.raises(Conflict): validate(data)


def test_valid_exact_grant():
    assert validate(manifest())['operations'][0]['action'] == 'grant-sales'


def test_missing_global_entitlement_stops_before_user_or_grant(monkeypatch):
    repo = SalesActivationRepository()
    repo.delegated_actor = AsyncMock()
    repo.user = AsyncMock()
    monkeypatch.setattr('modules.telchi.provisioning.sales_repository.one', AsyncMock(return_value=None))
    conn = AsyncMock()
    with pytest.raises(Conflict, match='entitlement'):
        asyncio.run(repo.grant_sales(conn, 'admin', 'workspace', 'pilot'))
    repo.user.assert_not_called()
    conn.execute.assert_not_called()


def test_wrong_delegated_actor_stops_before_entitlement():
    repo = SalesActivationRepository()
    repo.delegated_actor = AsyncMock(side_effect=Conflict('wrong tenant'))
    repo.approved = AsyncMock()
    with pytest.raises(Conflict, match='wrong tenant'):
        asyncio.run(repo.grant_sales(AsyncMock(), 'outsider', 'workspace', 'pilot'))
    repo.approved.assert_not_called()
