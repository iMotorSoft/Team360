"""Characterize current RBAC; PASS does NOT mean FULL_ACCESS is implemented.

No database writes, production capability registration or Foundation access.
The synthetic permission exists only in these isolated authorization calls.
"""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy
from modules.messaging.handlers import SenderIdentity

NEW_PERMISSION = 'telchi.audit.synthetic_operation.read.v1'


def context(permissions=()):
    channel = SimpleNamespace(module='telchi', environment='dev', tenant_id='telchi',
                              workspace_id='workspace')
    identity = SenderIdentity('pilot', 'telchi', 'workspace', 'dev', frozenset(permissions))
    return SimpleNamespace(channel=channel, sender_identity=identity, public_capabilities=frozenset())


def authorization(**overrides):
    values = dict(tenant_id='telchi', workspace_id='workspace', permission=None,
                  module_enabled=True, whole_workspace_scope_verified=True,
                  pilot_access_check=lambda: None, pilot_user_id='pilot')
    return BusinessAuthorization(BusinessPolicy(**(values | overrides)))


@pytest.mark.parametrize('grants', [(), ('FULL_ACCESS',), ('*',), ('telchi.*',),
                                  ('telchi.sales.latest_documents.read.v1',)])
def test_new_permission_is_not_implicitly_authorized(grants):
    assert not asyncio.run(authorization().allowed(context(grants), required_permission=NEW_PERMISSION))


def test_specific_new_permission_is_authorized():
    assert asyncio.run(authorization().allowed(context([NEW_PERMISSION]), required_permission=NEW_PERMISSION))


@pytest.mark.parametrize('axis,value', [('workspace_id', 'other'), ('tenant_id', 'other'),
                                       ('environment', 'prod')])
def test_foreign_identity_is_rejected_even_with_specific_permission(axis, value):
    c = context([NEW_PERMISSION, 'FULL_ACCESS'])
    c.sender_identity = replace(c.sender_identity, **{axis: value})
    assert not asyncio.run(authorization().allowed(c, required_permission=NEW_PERMISSION))


def test_disabled_module_rejected_even_with_specific_permission():
    assert not asyncio.run(authorization(module_enabled=False).allowed(
        context([NEW_PERMISSION]), required_permission=NEW_PERMISSION))


def test_live_resolver_revocation_overrides_stale_identity(monkeypatch):
    effective = [NEW_PERMISSION]

    async def resolve(self, conn, workspace, user):
        assert workspace == 'workspace' and user == 'pilot'
        return effective.copy()

    monkeypatch.setattr(PermissionConsoleRepository, 'list_effective_permissions', resolve)

    async def run():
        auth, c = authorization(), context([NEW_PERMISSION])
        assert await auth.allowed(c, object(), required_permission=NEW_PERMISSION)
        effective.clear()
        assert not await auth.allowed(c, object(), required_permission=NEW_PERMISSION)

    asyncio.run(run())
