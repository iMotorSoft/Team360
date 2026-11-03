"""Pilot admission is independent of capability grants; offline security contracts."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, registration
from modules.console.repositories import PermissionConsoleRepository
from .test_whatsapp_dev import approval  # private temporary approval fixture
from .test_assistant import context, event, latest
from .test_sales_business_contract import setup, documentary_proposal


def policy(check=lambda: None):
    return BusinessPolicy('telchi', 'workspace', None, True, True,
                          pilot_access_check=check, pilot_user_id='user',
                          pilot_approval_sha256='fixture-digest')


def pilot_context(permissions=()):
    c = context()
    return replace(c, channel=replace(c.channel, tenant_id='telchi'),
                   sender_identity=replace(c.sender_identity, tenant_id='telchi',
                                           permissions=frozenset(permissions)))


def test_access_has_no_time_expiry_or_commercial_grant(approval):
    value, path = approval  # issued thirty days ago; no expiry
    dev.save_private(path, value)
    assert dev.read_approval(path) == value
    dev.unchanged_approval(path, value)


@pytest.mark.parametrize('change', [dict(revoked=True), dict(revoked=None),
    dict(access='other'), dict(permission='telchi.sales.source_quantity.read.v1'),
    dict(expires_at='2099-01-01T00:00:00+00:00'), dict(sender_sha256=''),
    dict(issued_at='2099-01-01T00:00:00+00:00')])
def test_invalid_or_legacy_access_is_not_silently_migrated(approval, change):
    value, path = approval
    dev.save_private(path, value | change)
    with pytest.raises((PermissionError, ValueError)):
        dev.read_approval(path)


def test_scope_change_and_deletion_revoke_running_access(approval):
    value, path = approval
    dev.save_private(path, value | dict(user_id='replacement'))
    with pytest.raises(PermissionError, match='changed'):
        dev.unchanged_approval(path, value)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        dev.unchanged_approval(path, value)


def test_no_grants_needed_to_enter_but_capability_requires_its_own_grant(monkeypatch):
    async def run():
        auth = BusinessAuthorization(policy())
        c = pilot_context()
        assert await auth.allowed(c)
        grant = 'telchi.sales.latest_documents.read.v1'
        assert not await auth.allowed(c, required_permission=grant)
        c = pilot_context([grant])  # no source_quantity grant
        assert await auth.allowed(c, required_permission=grant)
        effective = {grant}
        async def live(self, conn, workspace, user):
            assert workspace == 'workspace' and user == 'user'
            return effective
        monkeypatch.setattr(PermissionConsoleRepository, 'list_effective_permissions', live)
        assert await auth.allowed(c, object(), required_permission=grant)
        effective.clear()  # revoke while resolved identity still contains the grant
        assert not await auth.allowed(c, object(), required_permission=grant)
    asyncio.run(run())


@pytest.mark.parametrize('change', ['tenant', 'workspace', 'user', 'environment', 'public'])
def test_pilot_isolation(change):
    c = pilot_context()
    if change == 'tenant': c = replace(c, channel=replace(c.channel, tenant_id='other'))
    if change == 'workspace': c = replace(c, channel=replace(c.channel, workspace_id='other'))
    if change == 'user': c = replace(c, sender_identity=replace(c.sender_identity, user_id='other'))
    if change == 'environment': c = replace(c, channel=replace(c.channel, environment='prod'))
    if change == 'public': c = replace(c, public_capabilities=frozenset({'anything'}))
    assert not asyncio.run(BusinessAuthorization(policy()).allowed(c))


def test_revocation_before_execution_blocks_foundation():
    async def run():
        handler, store, calls, c = setup([documentary_proposal()])
        checks = []
        def check():
            checks.append(True)
            if len(checks) >= 3: raise PermissionError('revoked')
        handler.authorization = BusinessAuthorization(policy(check))
        result = await handler.handle(event('Mostrame las últimas 5 facturas de venta de Telchi.'), c)
        assert result.classification == 'DENIED' and not calls
    asyncio.run(run())


def test_latest_executes_without_source_quantity_and_audits_access():
    async def run():
        handler, store, calls, c = setup([documentary_proposal()])
        handler.authorization = BusinessAuthorization(policy())
        c = replace(c, sender_identity=replace(c.sender_identity,
            permissions=frozenset({'telchi.sales.latest_documents.read.v1'})))
        assert not registration(handler).required_permissions
        result = await handler.handle(event('Mostrame las últimas 5 facturas de venta de Telchi.'), c)
        assert result.classification == 'DIRECT_AVAILABLE' and calls == ['sales.latest_documents']
        audit = latest(store)
        assert audit['required_permission'] == 'telchi.sales.latest_documents.read.v1'
        assert audit['business_rbac_verified'] is True
        assert audit['pilot_approval_sha256'] == 'fixture-digest'
    asyncio.run(run())


def test_admitted_pilot_without_capability_permission_cannot_access_data():
    async def run():
        handler, store, calls, c = setup([documentary_proposal()], grants=False)
        handler.authorization = BusinessAuthorization(policy())
        assert await handler.authorization.allowed(c)
        result = await handler.handle(event('Mostrame las últimas 5 facturas de venta de Telchi.'), c)
        assert result.classification == 'DENIED'
        assert calls == []
    asyncio.run(run())


def test_missing_commercial_contract_cannot_execute():
    async def run():
        handler, *_ = setup([])
        handler.authorization = BusinessAuthorization(policy())
        handler.capabilities = SimpleNamespace(required_permissions=lambda _: [])
        assert not await handler._operation_permissions_allowed({}, pilot_context(), None)
    asyncio.run(run())


def test_top_items_requires_its_own_commercial_grant():
    from modules.telchi.assistant.capabilities import SalesCapabilities
    from .test_assistant import plan
    catalog = SalesCapabilities()
    grant = catalog.required_permission(plan())
    assert grant == 'telchi.sales.source_quantity.read.v1'
    c = pilot_context(['telchi.sales.latest_documents.read.v1'])
    assert not asyncio.run(BusinessAuthorization(policy()).allowed(c, required_permission=grant))


@pytest.mark.parametrize('tamper', [None, 'permission', 'approval', 'rbac'])
def test_latest_inspection_uses_capability_rbac_not_pilot_permission(tamper):
    from .test_whatsapp_dev import exchange
    from modules.telchi.assistant.whatsapp_dev_evidence import evaluate
    rows = exchange()
    approval = dict(access='assistant', workspace_id='workspace', user_id='pilot')
    audit = rows[0]['payload_jsonb']['telchi_assistant_v1']
    audit.update(required_permission='telchi.sales.latest_documents.read.v1',
                 pilot_approval_sha256=dev.approval_digest(approval), business_rbac_verified=True)
    audit['execution_result']['capability'] = 'sales.latest_documents.v1'
    if tamper == 'permission': audit['required_permission'] = 'telchi.sales.source_quantity.read.v1'
    if tamper == 'approval': audit['pilot_approval_sha256'] = 'different'
    if tamper == 'rbac': audit['business_rbac_verified'] = False
    if tamper:
        with pytest.raises(ValueError):
            evaluate(rows, SimpleNamespace(channel_id='channel'), approval, 'inbound')
    else:
        result = evaluate(rows, SimpleNamespace(channel_id='channel'), approval, 'inbound')
        assert result['capability'] == 'sales.latest_documents.v1'
        assert result['E2E'] == 'NOT_DECLARED'


def test_revocation_at_ingress_precedes_body_or_pipeline():
    async def run():
        called, responses = [], []
        async def app(*args): called.append(True)
        async def receive(): raise AssertionError('body read after revocation')
        async def send(value): responses.append(value)
        def revoked(): raise PermissionError('revoked')
        boundary = dev.PilotBoundary(app, SimpleNamespace(webhook_token='t'*32), None, None, revoked)
        await boundary(dict(type='http', path=dev.WEBHOOK, method='POST',
            headers=[(b'x-team360-webhook-token', b't'*32)]), receive, send)
        assert responses[0]['status'] == 403 and not called
    asyncio.run(run())
