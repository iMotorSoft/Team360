import asyncio

import pytest
from litestar.testing import TestClient

from ls_iMotorSoft_Srv01 import create_app
from modules.flow.domain import FlowRequestNotFoundError
from modules.flow.executive_auth import FlowExecutiveAuthorizationService
from modules.security.paseto_tokens import PasetoKeyPair, issue_paseto_v4_public

_ISSUER = "team360"
_KEY_ID = "route-test-key"
_KEY_PAIR = PasetoKeyPair.generate(_KEY_ID)


@pytest.fixture(autouse=True)
def _authenticated_flow_mode(monkeypatch):
    # These tests verify the authenticated guard that default_admin mode will
    # use again in the future. default_admin behavior is covered separately.
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", "authenticated")


def _client():
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return issue_paseto_v4_public(
        {"sub": f"user:{user_id}", "user_id": user_id},
        private_key_pem=_KEY_PAIR.private_pem,
        key_id=_KEY_ID,
        ttl_seconds=900,
        issuer=_ISSUER,
        token_type="console_access",
    )


def _route_path(request_id: str) -> str:
    return f"/api/team360-flow/executive/{request_id}"


class _AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def transaction(self):
        return _AsyncContext()


class _Pool:
    def connection(self):
        return _AsyncContext(_Connection())


def _fake_pool(monkeypatch) -> None:
    monkeypatch.setattr("modules.flow.routes.get_pool", lambda: _Pool())


class _Authz:
    def __init__(self, authorized: bool = True):
        self.authorized = authorized

    async def has_flow_executive_read(self, conn, user_id):
        return self.authorized


class _AuthzByUser:
    def __init__(self, allowed: dict[str, bool]):
        self.allowed = allowed

    async def has_flow_executive_read(self, conn, user_id):
        return self.allowed.get(user_id, False)


class _Exec:
    def __init__(self, view=None, error=None):
        self.view = view or {"request_id": "r-1", "status": "RESOLVED"}
        self.error = error
        self.calls = 0

    async def query_case(self, request_id, question=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.view


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user_id)}"}


def test_no_token_returns_401(monkeypatch):
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda settings: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    _fake_pool(monkeypatch)
    with _client() as client:
        response = client.get(_route_path("814f38ce-9509-4cd6-a355-fa176e63edb2"))
    assert response.status_code == 401


def test_invalid_token_returns_401(monkeypatch):
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda settings: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    _fake_pool(monkeypatch)
    with _client() as client:
        response = client.get(
            _route_path("814f38ce-9509-4cd6-a355-fa176e63edb2"),
            headers={"Authorization": "Bearer not-a-paseto"},
        )
    assert response.status_code == 401


def test_authenticated_without_permission_403_and_no_llm_or_data(monkeypatch):
    exec_fake = _Exec()
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda settings: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    _fake_pool(monkeypatch)
    monkeypatch.setattr(
        "modules.flow.routes._authorization_service", lambda: _Authz(authorized=False)
    )
    monkeypatch.setattr("modules.flow.routes._executive_service", lambda pool, q: exec_fake)
    with _client() as client:
        response = client.get(
            _route_path("814f38ce-9509-4cd6-a355-fa176e63edb2"),
            headers=_auth_headers("common-user"),
        )
    assert response.status_code == 403
    assert exec_fake.calls == 0


def test_authorized_user_returns_200_with_existing_contract(monkeypatch):
    view = {"request_id": "r-1", "status": "RESOLVED", "data_source": "AUDIT_SNAPSHOT"}
    exec_fake = _Exec(view=view)
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda settings: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    _fake_pool(monkeypatch)
    monkeypatch.setattr(
        "modules.flow.routes._authorization_service", lambda: _Authz(authorized=True)
    )
    monkeypatch.setattr("modules.flow.routes._executive_service", lambda pool, q: exec_fake)
    with _client() as client:
        response = client.get(
            _route_path("814f38ce-9509-4cd6-a355-fa176e63edb2"),
            headers=_auth_headers("director-1"),
        )
    assert response.status_code == 200
    assert response.json()["request_id"] == "r-1"
    assert response.json()["data_source"] == "AUDIT_SNAPSHOT"
    assert exec_fake.calls == 1


def test_authorized_missing_request_returns_404(monkeypatch):
    exec_fake = _Exec(error=FlowRequestNotFoundError("Flow request not found: missing"))
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda settings: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    _fake_pool(monkeypatch)
    monkeypatch.setattr(
        "modules.flow.routes._authorization_service", lambda: _Authz(authorized=True)
    )
    monkeypatch.setattr("modules.flow.routes._executive_service", lambda pool, q: exec_fake)
    with _client() as client:
        response = client.get(
            _route_path("00000000-0000-4000-8000-000000000000"),
            headers=_auth_headers("director-1"),
        )
    assert response.status_code == 404


def test_unauthorized_missing_request_returns_403_no_enumeration(monkeypatch):
    exec_fake = _Exec()
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda settings: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    _fake_pool(monkeypatch)
    monkeypatch.setattr(
        "modules.flow.routes._authorization_service", lambda: _Authz(authorized=False)
    )
    monkeypatch.setattr("modules.flow.routes._executive_service", lambda pool, q: exec_fake)
    with _client() as client:
        response = client.get(
            _route_path("00000000-0000-4000-8000-000000000000"),
            headers=_auth_headers("common-user"),
        )
    assert response.status_code == 403
    assert exec_fake.calls == 0


def test_two_users_different_permissions(monkeypatch):
    exec_fake = _Exec()
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda settings: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    _fake_pool(monkeypatch)
    monkeypatch.setattr(
        "modules.flow.routes._authorization_service",
        lambda: _AuthzByUser({"user-a": True}),
    )
    monkeypatch.setattr("modules.flow.routes._executive_service", lambda pool, q: exec_fake)
    with _client() as client:
        ok = client.get(
            _route_path("814f38ce-9509-4cd6-a355-fa176e63edb2"),
            headers=_auth_headers("user-a"),
        )
        denied = client.get(
            _route_path("814f38ce-9509-4cd6-a355-fa176e63edb2"),
            headers=_auth_headers("user-b"),
        )
    assert ok.status_code == 200
    assert denied.status_code == 403


@pytest.mark.parametrize(
    "extra",
    [
        {"params": {"role": "director"}},
        {"headers": {"X-Role": "director"}},
        {"headers": {"X-Is-Admin": "true"}},
        {"headers": {"X-User-Email": "admin@alquimiablue.com"}},
    ],
)
def test_privilege_escalation_attempts_are_ignored(monkeypatch, extra):
    exec_fake = _Exec()
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda settings: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    _fake_pool(monkeypatch)
    monkeypatch.setattr(
        "modules.flow.routes._authorization_service", lambda: _Authz(authorized=False)
    )
    monkeypatch.setattr("modules.flow.routes._executive_service", lambda pool, q: exec_fake)
    headers = {"Authorization": f"Bearer {_token('attacker')}"}
    headers.update(extra.get("headers", {}))
    with _client() as client:
        response = client.get(
            _route_path("814f38ce-9509-4cd6-a355-fa176e63edb2"),
            headers=headers,
            params=extra.get("params"),
        )
    assert response.status_code == 403
    assert exec_fake.calls == 0


class _PermRepo:
    def __init__(self, permissions):
        self.permissions = permissions

    async def list_effective_permissions(self, conn, workspace_id, user_id):
        return self.permissions


class _WorkspaceRepo:
    def __init__(self, workspace_id):
        self.workspace_id = workspace_id

    async def get_user_workspace_id(self, conn, user_id):
        return self.workspace_id


class _Conn:
    pass


def test_authorization_service_grants_when_capability_present():
    service = FlowExecutiveAuthorizationService(
        repository=_WorkspaceRepo("ws-1"),
        permissions=_PermRepo(["task.view", "flow.executive.read"]),
    )
    assert asyncio.run(service.has_flow_executive_read(_Conn(), "u-1")) is True


def test_authorization_service_denies_without_capability():
    service = FlowExecutiveAuthorizationService(
        repository=_WorkspaceRepo("ws-1"),
        permissions=_PermRepo(["task.view"]),
    )
    assert asyncio.run(service.has_flow_executive_read(_Conn(), "u-1")) is False


def test_authorization_service_fails_closed_without_workspace():
    service = FlowExecutiveAuthorizationService(
        repository=_WorkspaceRepo(None),
        permissions=_PermRepo(["flow.executive.read"]),
    )
    assert asyncio.run(service.has_flow_executive_read(_Conn(), "u-1")) is False


def test_authorization_service_denies_domain_only_without_capability():
    service = FlowExecutiveAuthorizationService(
        repository=_WorkspaceRepo("ws-1"),
        permissions=_PermRepo([]),
    )
    assert asyncio.run(service.has_flow_executive_read(_Conn(), "u-1")) is False
