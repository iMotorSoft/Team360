import pytest
from litestar.testing import TestClient

from ls_iMotorSoft_Srv01 import create_app
from modules.flow.configuration_service import (
    FlowConfigurationValidationError,
    FlowSectorNotFoundError,
)
from modules.security.paseto_tokens import PasetoKeyPair, issue_paseto_v4_public

_ISSUER = "team360"
_KEY_ID = "config-route-test-key"
_KEY_PAIR = PasetoKeyPair.generate(_KEY_ID)

_LIST_PATH = "/api/team360-flow/configuration"
_ONE_PATH = "/api/team360-flow/configuration/alumbrado"


@pytest.fixture(autouse=True)
def _authenticated_flow_mode(monkeypatch):
    # Authenticated is the safe default; explicit DEV demo is tested below.
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


def _keys(monkeypatch) -> None:
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda settings: {_KEY_ID: _KEY_PAIR.public_pem},
    )


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user_id)}"}


class _Authz:
    def __init__(self, can_read: bool = True, can_write: bool = False):
        self.can_read_value = can_read
        self.can_write_value = can_write

    async def can_read(self, conn, user_id):
        return self.can_read_value

    async def can_write(self, conn, user_id):
        return self.can_write_value


class _Service:
    def __init__(
        self,
        *,
        list_result=None,
        get_result=None,
        update_result=None,
        operational_result=None,
        error=None,
    ):
        self.list_result = list_result or {"sectors": []}
        self.get_result = get_result
        self.update_result = update_result
        self.operational_result = operational_result or {
            "automation_enabled": False,
            "scheduler_interval_seconds": 15,
            "mail_intake_enabled": True,
            "mail_batch_limit": 500,
            "mail_after_cutoff": True,
            "mail_cutoff_epoch": 1787239323,
        }
        self.error = error
        self.calls = {
            "list": 0,
            "get": 0,
            "update": 0,
            "get_operational": 0,
            "update_operational": 0,
            "clear_cases": 0,
        }

    async def list_configurations(self):
        self.calls["list"] += 1
        return self.list_result

    async def get_configuration(self, sector_id):
        self.calls["get"] += 1
        if self.get_result is None:
            return None
        return self.get_result

    async def update_configuration(self, sector_id, *, levels, closure_approval_level):
        self.calls["update"] += 1
        if self.error is not None:
            raise self.error
        return self.update_result

    async def get_operational_settings(self):
        self.calls["get_operational"] += 1
        return self.operational_result

    async def update_operational_settings(self, **changes):
        self.calls["update_operational"] += 1
        if self.error is not None:
            raise self.error
        self.operational_result = {**self.operational_result, **changes}
        return self.operational_result

    async def clear_cases(self):
        self.calls["clear_cases"] += 1
        return {
            "status": "cleared",
            "cases_before": 3,
            "cases_after": 0,
            "before": {"flow_requests": 3},
            "deleted": {"flow_requests": 3},
            "after": {"flow_requests": 0},
        }


def _canonical_sector():
    return {
        "sector_id": "alumbrado",
        "display_name": "Alumbrado Público",
        "active": True,
        "closure_approval_level": 2,
        "levels": [
            {"level": 1, "channel": "email", "destination": "alumbrado.n1@alquimiablue.com", "active": True},
            {"level": 2, "channel": "email", "destination": "alumbrado.n2@alquimiablue.com", "active": True},
            {"level": 3, "channel": "email", "destination": "alumbrado.n3@alquimiablue.com", "active": True},
        ],
    }


def _patch_config(monkeypatch, authz, service):
    _fake_pool(monkeypatch)
    _keys(monkeypatch)
    monkeypatch.setattr(
        "modules.flow.routes._configuration_authorization_service",
        lambda: authz,
    )
    monkeypatch.setattr(
        "modules.flow.routes._configuration_service",
        lambda pool: service,
    )
    monkeypatch.setattr(
        "modules.flow.routes._case_cleanup_service",
        lambda pool: service,
    )


# ---------------------------------------------------------------- GET list ---

def test_list_no_token_401(monkeypatch):
    _keys(monkeypatch)
    _fake_pool(monkeypatch)
    with _client() as client:
        response = client.get(_LIST_PATH)
    assert response.status_code == 401


def test_list_invalid_token_401(monkeypatch):
    _keys(monkeypatch)
    _fake_pool(monkeypatch)
    with _client() as client:
        response = client.get(_LIST_PATH, headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_list_without_read_permission_403_and_no_data(monkeypatch):
    service = _Service()
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    with _client() as client:
        response = client.get(_LIST_PATH, headers=_auth_headers("reader"))
    assert response.status_code == 403
    assert service.calls["list"] == 0


def test_list_authorized_200_canonical(monkeypatch):
    sector = _canonical_sector()
    service = _Service(list_result={"sectors": [sector]})
    _patch_config(monkeypatch, _Authz(can_read=True, can_write=False), service)
    with _client() as client:
        response = client.get(_LIST_PATH, headers=_auth_headers("reader"))
    assert response.status_code == 200
    data = response.json()
    assert data["sectors"][0]["sector_id"] == "alumbrado"
    assert [l["level"] for l in data["sectors"][0]["levels"]] == [1, 2, 3]
    assert service.calls["list"] == 1


# ------------------------------------------------------------------ GET one ---

def test_get_one_authorized_404_unknown(monkeypatch):
    service = _Service(get_result=None)
    _patch_config(monkeypatch, _Authz(can_read=True, can_write=False), service)
    with _client() as client:
        response = client.get(
            "/api/team360-flow/configuration/inexistente",
            headers=_auth_headers("reader"),
        )
    assert response.status_code == 404


def test_get_one_unauthorized_403_no_enumeration(monkeypatch):
    service = _Service(get_result=None)
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    with _client() as client:
        response = client.get(
            "/api/team360-flow/configuration/inexistente",
            headers=_auth_headers("reader"),
        )
    assert response.status_code == 403
    assert service.calls["get"] == 0


# -------------------------------------------------------------------- PATCH ---

def test_patch_no_token_401(monkeypatch):
    _keys(monkeypatch)
    _fake_pool(monkeypatch)
    with _client() as client:
        response = client.patch(
            _ONE_PATH,
            json={"levels": [], "closure_approval_level": None},
        )
    assert response.status_code == 401


def test_patch_read_permission_does_not_imply_write(monkeypatch):
    service = _Service()
    _patch_config(monkeypatch, _Authz(can_read=True, can_write=False), service)
    with _client() as client:
        response = client.patch(
            _ONE_PATH,
            headers=_auth_headers("reader"),
            json={"levels": [], "closure_approval_level": None},
        )
    assert response.status_code == 403
    assert service.calls["update"] == 0


def test_patch_mass_assignment_rejected(monkeypatch):
    service = _Service()
    _patch_config(monkeypatch, _Authz(can_read=True, can_write=True), service)
    with _client() as client:
        response = client.patch(
            _ONE_PATH,
            headers=_auth_headers("admin"),
            json={
                "levels": [],
                "closure_approval_level": None,
                "request.status": "RESOLVED",
                "sector.internal_id": 123,
            },
        )
    assert response.status_code == 422
    assert "campos no permitidos" in response.json()["detail"]
    assert service.calls["update"] == 0


def test_patch_authorized_success_200(monkeypatch):
    sector = _canonical_sector()
    service = _Service(update_result=sector)
    _patch_config(monkeypatch, _Authz(can_read=True, can_write=True), service)
    with _client() as client:
        response = client.patch(
            _ONE_PATH,
            headers=_auth_headers("admin"),
            json={
                "levels": [
                    {"level": 1, "destination": "nuevo.n1@alquimiablue.com"},
                    {"level": 2, "destination": "alumbrado.n2@alquimiablue.com"},
                    {"level": 3, "destination": "alumbrado.n3@alquimiablue.com"},
                ],
                "closure_approval_level": 2,
            },
        )
    assert response.status_code == 200
    assert response.json()["sector_id"] == "alumbrado"
    assert service.calls["update"] == 1


def test_patch_unknown_sector_404(monkeypatch):
    service = _Service(
        error=FlowSectorNotFoundError("Flow sector not found: x"),
        update_result=None,
    )
    _patch_config(monkeypatch, _Authz(can_read=True, can_write=True), service)
    with _client() as client:
        response = client.patch(
            "/api/team360-flow/configuration/inexistente",
            headers=_auth_headers("admin"),
            json={"levels": [], "closure_approval_level": None},
        )
    assert response.status_code == 404


def test_patch_validation_error_422(monkeypatch):
    service = _Service(
        error=FlowConfigurationValidationError("destination es obligatorio"),
        update_result=None,
    )
    _patch_config(monkeypatch, _Authz(can_read=True, can_write=True), service)
    with _client() as client:
        response = client.patch(
            _ONE_PATH,
            headers=_auth_headers("admin"),
            json={"levels": [], "closure_approval_level": None},
        )
    assert response.status_code == 422


def test_patch_missing_required_fields_422(monkeypatch):
    service = _Service()
    _patch_config(monkeypatch, _Authz(can_read=True, can_write=True), service)
    with _client() as client:
        response = client.patch(
            _ONE_PATH,
            headers=_auth_headers("admin"),
            json={"levels": []},
        )
    assert response.status_code == 422
    assert service.calls["update"] == 0


# ------------------------------------------------------------ default_admin ---

def _default_admin(monkeypatch) -> None:
    # Explicitly select the DEV demo policy after the autouse
    # authenticated fixture; no token is required in this mode.
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", "default_admin")
    monkeypatch.setenv("TEAM360_ENV", "development")


def test_default_admin_list_no_token_200(monkeypatch):
    sector = _canonical_sector()
    service = _Service(list_result={"sectors": [sector]})
    _default_admin(monkeypatch)
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    with _client() as client:
        response = client.get(_LIST_PATH)
    assert response.status_code == 200
    assert response.json()["sectors"][0]["sector_id"] == "alumbrado"
    assert service.calls["list"] == 1


def test_default_admin_get_one_no_token_200(monkeypatch):
    service = _Service(get_result=_canonical_sector())
    _default_admin(monkeypatch)
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    with _client() as client:
        response = client.get(_ONE_PATH)
    assert response.status_code == 200
    assert service.calls["get"] == 1


def test_default_admin_patch_no_token_200(monkeypatch):
    service = _Service(update_result=_canonical_sector())
    _default_admin(monkeypatch)
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    with _client() as client:
        response = client.patch(
            _ONE_PATH,
            json={"levels": [], "closure_approval_level": None},
        )
    assert response.status_code == 200
    assert service.calls["update"] == 1


def test_default_admin_mass_assignment_still_rejected(monkeypatch):
    service = _Service()
    _default_admin(monkeypatch)
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    with _client() as client:
        response = client.patch(
            _ONE_PATH,
            json={"levels": [], "closure_approval_level": None, "role": "hack"},
        )
    assert response.status_code == 422
    assert service.calls["update"] == 0


def test_default_admin_unknown_sector_404(monkeypatch):
    service = _Service(get_result=None)
    _default_admin(monkeypatch)
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    with _client() as client:
        response = client.get("/api/team360-flow/configuration/inexistente")
    assert response.status_code == 404


def test_default_admin_operational_settings_get_and_patch(monkeypatch):
    service = _Service()
    _default_admin(monkeypatch)
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    path = "/api/team360-flow/operational-settings"
    with _client() as client:
        read = client.get(path)
        updated = client.patch(
            path,
            json={
                "automation_enabled": False,
                "scheduler_interval_seconds": 20,
                "mail_intake_enabled": True,
                "mail_batch_limit": 17,
                "mail_after_cutoff": True,
                "mail_cutoff_epoch": 1787239368,
            },
        )
    assert read.status_code == 200
    assert read.json()["mail_cutoff_epoch"] == 1787239323
    assert updated.status_code == 200
    assert updated.json()["scheduler_interval_seconds"] == 20
    assert updated.json()["mail_cutoff_epoch"] == 1787239368
    assert service.calls["get_operational"] == 1
    assert service.calls["update_operational"] == 1


def test_default_admin_scheduler_status_get(monkeypatch):
    class _SchedulerRepository:
        async def get_state(self, conn):
            return {
                "last_started_at_utc": None,
                "last_finished_at_utc": None,
                "last_result": "PASS",
                "last_error_class": None,
                "processed_count": 2,
                "cycle_count": 3,
            }

    _default_admin(monkeypatch)
    _fake_pool(monkeypatch)
    monkeypatch.setattr(
        "modules.flow.operational_settings_repository.FlowSchedulerStateRepository",
        _SchedulerRepository,
    )
    with _client() as client:
        response = client.get("/api/team360-flow/scheduler/status")
    assert response.status_code == 200
    assert response.json()["last_result"] == "PASS"
    assert response.json()["cycle_count"] == 3


# --------------------------------------------------------------- case cleanup -

def test_clear_cases_no_token_401(monkeypatch):
    _keys(monkeypatch)
    _fake_pool(monkeypatch)
    with _client() as client:
        response = client.post(
            "/api/team360-flow/cases/clear", json={"confirm": True}
        )
    assert response.status_code == 401


def test_clear_cases_read_permission_does_not_imply_write(monkeypatch):
    service = _Service()
    _patch_config(monkeypatch, _Authz(can_read=True, can_write=False), service)
    with _client() as client:
        response = client.post(
            "/api/team360-flow/cases/clear",
            headers=_auth_headers("reader"),
            json={"confirm": True},
        )
    assert response.status_code == 403
    assert service.calls["clear_cases"] == 0


def test_default_admin_clear_cases_returns_zero(monkeypatch):
    service = _Service()
    _default_admin(monkeypatch)
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    with _client() as client:
        response = client.post(
            "/api/team360-flow/cases/clear", json={"confirm": True}
        )
    assert response.status_code == 200
    assert response.json()["cases_after"] == 0
    assert service.calls["clear_cases"] == 1


def test_clear_cases_requires_explicit_confirmation(monkeypatch):
    service = _Service()
    _default_admin(monkeypatch)
    _patch_config(monkeypatch, _Authz(can_read=False, can_write=False), service)
    with _client() as client:
        response = client.post("/api/team360-flow/cases/clear", json={})
    assert response.status_code == 422
    assert service.calls["clear_cases"] == 0
