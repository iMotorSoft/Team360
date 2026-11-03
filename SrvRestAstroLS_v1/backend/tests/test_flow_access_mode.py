"""Fail-closed access configuration and explicit DEV demo regression tests."""

from types import SimpleNamespace

import pytest
from litestar import Litestar
from litestar.testing import TestClient

from modules.flow.access_mode import (
    AUTHENTICATED_MODE,
    DEFAULT_ADMIN_MODE,
    FLOW_CONFIGURATION_READ,
    FLOW_CONFIGURATION_WRITE,
    FLOW_EXECUTIVE_READ,
    MVP_ADMIN_USER_ID,
    FlowAccessConfigurationError,
    default_admin_actor,
    flow_access_mode,
    is_default_admin_mode,
)
from modules.flow.routes import ROUTE_HANDLERS


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch):
    monkeypatch.delenv("TEAM360_ENV", raising=False)
    monkeypatch.delenv("TEAM360_FLOW_ACCESS_MODE", raising=False)


def test_absent_mode_is_authenticated():
    assert flow_access_mode() == AUTHENTICATED_MODE
    assert not is_default_admin_mode()
    with pytest.raises(FlowAccessConfigurationError):
        default_admin_actor()


@pytest.mark.parametrize("environment", ["development", "dev", " DEV "])
def test_explicit_dev_demo(monkeypatch, environment):
    monkeypatch.setenv("TEAM360_ENV", environment)
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", "default_admin")
    assert flow_access_mode() == DEFAULT_ADMIN_MODE
    assert is_default_admin_mode()
    actor = default_admin_actor()
    assert actor.role == "administrator"
    assert actor.user_id == MVP_ADMIN_USER_ID
    assert actor.capabilities == frozenset({
        FLOW_EXECUTIVE_READ, FLOW_CONFIGURATION_READ, FLOW_CONFIGURATION_WRITE,
    })
    assert not actor.has("user.manage")
    assert not actor.has("organizations.read")


@pytest.mark.parametrize("environment", [None, "", " ", "production", "prod", "staging", "demo", "foo"])
def test_demo_rejected_outside_explicit_dev(monkeypatch, environment):
    if environment is not None:
        monkeypatch.setenv("TEAM360_ENV", environment)
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", "default_admin")
    with pytest.raises(FlowAccessConfigurationError):
        flow_access_mode()
    with pytest.raises(FlowAccessConfigurationError):
        default_admin_actor()


@pytest.mark.parametrize("mode", ["foo", "admin", "unknown", "", " ", "default_admn", "surprise"])
@pytest.mark.parametrize("environment", ["development", "production"])
def test_invalid_mode_rejected(monkeypatch, mode, environment):
    monkeypatch.setenv("TEAM360_ENV", environment)
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", mode)
    with pytest.raises(FlowAccessConfigurationError):
        flow_access_mode()
    with pytest.raises(FlowAccessConfigurationError):
        default_admin_actor()


@pytest.mark.parametrize("environment", [None, "development", "production"])
def test_authenticated_mode_preserved(monkeypatch, environment):
    if environment is not None:
        monkeypatch.setenv("TEAM360_ENV", environment)
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", " AUTHENTICATED ")
    assert flow_access_mode() == AUTHENTICATED_MODE
    assert not is_default_admin_mode()


_OPERATIONS = [
    ("GET", "/api/team360-flow/executive"),
    ("GET", "/api/team360-flow/executive/r-1"),
    ("GET", "/api/team360-flow/configuration"),
    ("GET", "/api/team360-flow/configuration/alumbrado"),
    ("PATCH", "/api/team360-flow/configuration/alumbrado"),
    ("GET", "/api/team360-flow/operational-settings"),
    ("PATCH", "/api/team360-flow/operational-settings"),
    ("GET", "/api/team360-flow/scheduler/status"),
    ("POST", "/api/team360-flow/cases/clear"),
    ("POST", "/api/team360-flow/executive/r-1/resend-approval"),
]


@pytest.mark.parametrize("method,path", _OPERATIONS)
@pytest.mark.parametrize("environment,mode,status", [
    ("production", "default_admin", 503),
    (None, "default_admin", 503),
    ("development", "foo", 503),
    ("development", "admin", 503),
    ("production", "unknown", 503),
    ("development", "", 503),
    ("development", " ", 503),
    ("development", "default_admn", 503),
    ("production", None, 401),
    ("production", "authenticated", 401),
])
def test_http_rejects_before_data_access(monkeypatch, method, path, environment, mode, status):
    if environment is not None:
        monkeypatch.setenv("TEAM360_ENV", environment)
    if mode is not None:
        monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", mode)

    def forbidden_pool():
        pytest.fail("Rejected access must not reach PostgreSQL/data services")

    monkeypatch.setattr("modules.flow.routes.get_pool", forbidden_pool)
    with TestClient(Litestar(route_handlers=list(ROUTE_HANDLERS))) as client:
        response = client.request(method, path, json={} if method in {"POST", "PATCH"} else None)
    assert response.status_code == status


@pytest.mark.parametrize("mode", ["future_mode", "unknown"])
def test_guard_never_treats_new_mode_as_admin(monkeypatch, mode):
    monkeypatch.setattr("modules.flow.routes.flow_access_mode", lambda: mode)
    with TestClient(Litestar(route_handlers=list(ROUTE_HANDLERS))) as client:
        response = client.get("/api/team360-flow/executive")
    assert response.status_code == 503


@pytest.mark.parametrize("path", ["/api/team360-flow/executive", "/api/team360-flow/executive/r-1"])
def test_explicit_dev_demo_directorio_without_token(monkeypatch, path):
    monkeypatch.setenv("TEAM360_ENV", "development")
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", "default_admin")

    async def list_cases(**kwargs):
        return {"items": [], "demo": True}

    async def query_case(request_id, **kwargs):
        return {"request_id": request_id, "demo": True}

    monkeypatch.setattr("modules.flow.routes.get_pool", lambda: object())
    monkeypatch.setattr("modules.flow.routes._executive_list_service", lambda pool: SimpleNamespace(list_cases=list_cases))
    monkeypatch.setattr("modules.flow.routes._executive_service", lambda pool, question: SimpleNamespace(query_case=query_case))
    with TestClient(Litestar(route_handlers=list(ROUTE_HANDLERS))) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.json()["demo"] is True
