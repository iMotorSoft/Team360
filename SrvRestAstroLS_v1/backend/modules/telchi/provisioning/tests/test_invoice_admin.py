"""Invoice permission is incremental and cannot replace owner/RBAC checks."""
import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from modules.telchi.provisioning.invoice_repository import InvoiceActivationRepository, AUTHORIZATION
from modules.telchi.provisioning.repository import Conflict
from modules.telchi.datalake.invoice_lines_query import PERMISSION, CAPABILITY


def test_specific_invoice_contract_not_product_or_global_grants():
    limits = InvoiceActivationRepository.sales_limits()
    assert limits['permissions'] == [PERMISSION]
    assert limits['capabilities'] == [CAPABILITY]
    assert limits['roles'] == ['telchi_sales_invoice_lines_reader_v1']
    assert limits['document_type'] == 'OINV'
    assert limits['free_sql'] is limits['line_amounts'] is limits['physical_quantity_totals'] is False


def test_missing_owner_authorization_zero_writes():
    conn = AsyncMock()
    with pytest.raises(Conflict, match='authorization'):
        asyncio.run(InvoiceActivationRepository().activate(conn, backup_sha256='fixture', authorization='other'))
    conn.execute.assert_not_called()


def test_missing_base_delegation_zero_writes():
    repo = InvoiceActivationRepository()
    repo.guard = AsyncMock()
    repo.identities = AsyncMock(return_value=dict(workspace={'id':'workspace'},
        **{k:{'id':k} for k in ('global','admin','pilot')}))
    conn = AsyncMock()
    with patch('modules.telchi.provisioning.invoice_repository.SalesActivationRepository.approved',
               AsyncMock(side_effect=Conflict('missing entitlement'))):
        with pytest.raises(Conflict, match='entitlement'):
            asyncio.run(repo.activate(conn, backup_sha256='fixture', authorization=AUTHORIZATION))
    conn.execute.assert_not_called()
