"""Unit boundaries only; fake verifier/DB ports do NOT certify authenticated HTTP."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from litestar.exceptions import HTTPException
import pytest

from modules.console.auth import ConsoleAuthError
from modules.telchi.assistant import dev_runtime_http as runtime


def request_and_config(header='Bearer explicit-unit-stub'):
    connection = object()
    @asynccontextmanager
    async def restricted():
        yield connection
    verifier = AsyncMock(return_value=SimpleNamespace(user_id='unit-subject'))
    handler = SimpleNamespace(semantics_connection=restricted)
    state = SimpleNamespace(messaging_handlers={'telchi': SimpleNamespace(handler=handler)},
                            dev_assistant_login_service=SimpleNamespace(verify_session=verifier))
    request = SimpleNamespace(headers={'authorization': header}, app=SimpleNamespace(state=state))
    config = dict(requires_human_session=True, binding=SimpleNamespace(workspace_id='unit-workspace'))
    return request, config, connection, verifier


def test_existing_session_verifier_uses_restricted_port_and_binding_workspace():
    request, config, conn, verifier = request_and_config()
    assert asyncio.run(runtime._human_subject(request, config)) == 'unit-subject'
    verifier.assert_awaited_once_with(conn, 'explicit-unit-stub', workspace_id='unit-workspace')


@pytest.mark.parametrize('header', ['', 'Basic ignored', 'Bearer '+('x'*16384)])
def test_session_missing_or_malformed_never_reaches_db(header):
    request, config, conn, verifier = request_and_config(header)
    with pytest.raises(HTTPException) as error:
        asyncio.run(runtime._human_subject(request, config))
    assert error.value.status_code == 401
    verifier.assert_not_awaited()


def test_expired_foreign_or_revoked_session_fails_closed():
    request, config, conn, verifier = request_and_config()
    verifier.side_effect = ConsoleAuthError('unit-invalid-session')
    with pytest.raises(HTTPException) as error:
        asyncio.run(runtime._human_subject(request, config))
    assert error.value.status_code == 401


def test_wrong_phone_subject_rejected_before_event_persistence(monkeypatch):
    identities = SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(user_id='other-unit-subject')))
    monkeypatch.setattr(runtime, 'PostgresPhoneIdentityResolver', lambda pool: identities)
    tx = AsyncMock(side_effect=AssertionError('must not persist an event'))
    monkeypatch.setattr(runtime, 'transaction', tx)
    binding = SimpleNamespace(channel_id='unit-channel', provider_instance='unit-instance',
        receiver_context='unit-receiver', tenant_id='unit-tenant', workspace_id='unit-workspace',
        module='telchi', environment='dev')
    with pytest.raises(PermissionError):
        asyncio.run(runtime._run_turn(pool=object(), registrations={}, binding=binding,
            message=SimpleNamespace(sender='unit-phone'), conversation_key='unit-conversation',
            authenticated_user_id='unit-subject'))
    tx.assert_not_called()


def test_rebinding_at_dispatch_is_also_rejected():
    underlying = SimpleNamespace(resolve=AsyncMock(side_effect=[SimpleNamespace(user_id='subject'),
                                                               SimpleNamespace(user_id='changed-subject')]))
    bound = runtime._SessionBoundPhoneIdentity(underlying, 'subject')
    async def exercise():
        assert (await bound.resolve(None, 'phone')).user_id == 'subject'
        with pytest.raises(PermissionError):
            await bound.resolve(None, 'phone')
    asyncio.run(exercise())
