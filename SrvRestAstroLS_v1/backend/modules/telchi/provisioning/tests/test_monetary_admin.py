"""Incremental monetary delegation is narrow and preserves the old catalog."""
import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from modules.telchi.provisioning.monetary_repository import MonetaryActivationRepository, AUTHORIZATION
from modules.telchi.provisioning.sales_repository import SalesActivationRepository
from modules.telchi.provisioning.repository import Conflict, PERMISSION
from modules.telchi.datalake.sales_query import MONETARY_PERMISSION, PERMISSIONS


def test_catalogs_remain_disjoint():
    assert SalesActivationRepository.sales_limits()['permissions'] == list(PERMISSIONS.values())
    assert MonetaryActivationRepository.sales_limits()['permissions'] == [MONETARY_PERMISSION]
    assert MonetaryActivationRepository.sales_limits()['entity_filters'] is False


def test_no_authorization_no_writes():
    conn = AsyncMock()
    with pytest.raises(Conflict, match='authorization'):
        asyncio.run(MonetaryActivationRepository().activate(conn, backup_sha256='fixture', authorization='other'))
    conn.execute.assert_not_called()


@pytest.mark.parametrize('effective', [[PERMISSION], [PERMISSION, *PERMISSIONS.values(), 'user.manage']])
def test_missing_baseline_or_unrelated_grants_refused(effective):
    repo = MonetaryActivationRepository()
    repo.guard = AsyncMock()
    repo.identities = AsyncMock(return_value=dict(workspace={'id': 'workspace'},
        **{k: {'id': k} for k in ['global', 'admin', 'pilot']}))
    conn = AsyncMock()
    with patch('modules.telchi.provisioning.monetary_repository.PermissionConsoleRepository.list_effective_permissions',
               AsyncMock(return_value=effective)):
        with pytest.raises(Conflict, match='baseline'):
            asyncio.run(repo.activate(conn, backup_sha256='fixture', authorization=AUTHORIZATION))
    conn.execute.assert_not_called()


def test_missing_prior_module_entitlement_prevents_catalog_writes():
    repo = MonetaryActivationRepository()
    repo.guard = AsyncMock()
    repo.identities = AsyncMock(return_value=dict(workspace={'id': 'workspace'},
        **{k: {'id': k} for k in ['global', 'admin', 'pilot']}))
    conn = AsyncMock()
    with patch('modules.telchi.provisioning.monetary_repository.PermissionConsoleRepository.list_effective_permissions',
               AsyncMock(return_value=[PERMISSION, *PERMISSIONS.values()])), \
         patch('modules.telchi.provisioning.monetary_repository.SalesActivationRepository.approved',
               AsyncMock(side_effect=Conflict('missing entitlement'))):
        with pytest.raises(Conflict, match='entitlement'):
            asyncio.run(repo.activate(conn, backup_sha256='fixture', authorization=AUTHORIZATION))
    conn.execute.assert_not_called()
