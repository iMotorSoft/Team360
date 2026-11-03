"""Narrow product grants cannot bypass existing owner/entitlement authorization."""
import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from modules.telchi.provisioning.product_repository import ProductActivationRepository, AUTHORIZATION
from modules.telchi.provisioning.repository import Conflict
from modules.telchi.datalake.product_sales_query import PERMISSIONS


def test_specific_catalog_no_full_access():
    limits=ProductActivationRepository.sales_limits()
    assert limits['permissions']==list(PERMISSIONS.values())
    assert limits['snapshot']==1408 and limits['free_sql'] is False
    assert limits['line_amounts'] is False and limits['physical_quantity_totals'] is False
    assert len(limits['roles'])==2


def test_missing_authorization_no_writes():
    conn=AsyncMock()
    with pytest.raises(Conflict,match='authorization'):
        asyncio.run(ProductActivationRepository().activate(conn,backup_sha256='fixture',authorization='other'))
    conn.execute.assert_not_called()


def test_missing_base_entitlement_no_writes():
    repo=ProductActivationRepository();repo.guard=AsyncMock()
    repo.identities=AsyncMock(return_value=dict(workspace={'id':'workspace'},
        **{k:{'id':k} for k in ('global','admin','pilot')}))
    conn=AsyncMock()
    with patch('modules.telchi.provisioning.product_repository.SalesActivationRepository.approved',
               AsyncMock(side_effect=Conflict('missing entitlement'))):
        with pytest.raises(Conflict,match='entitlement'):
            asyncio.run(repo.activate(conn,backup_sha256='fixture',authorization=AUTHORIZATION))
    conn.execute.assert_not_called()
