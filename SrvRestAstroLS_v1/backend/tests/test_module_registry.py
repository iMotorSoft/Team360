"""Contract tests for the explicit Team360 module route registry."""

from __future__ import annotations

from litestar import get
from litestar.testing import TestClient

import ls_iMotorSoft_Srv01 as backend_entrypoint
from modules.flow.routes import ROUTE_HANDLERS as FLOW_ROUTE_HANDLERS
import modules.module_registry as module_registry


@get("/api/test-module/first")
async def _first_module_route() -> dict[str, str]:
    return {"route": "first"}


@get("/api/test-module/second")
async def _second_module_route() -> dict[str, str]:
    return {"route": "second"}


@get("/api/test-module/third")
async def _third_module_route() -> dict[str, str]:
    return {"route": "third"}


def _application_paths() -> list[str]:
    return [route.path for route in backend_entrypoint.create_app().routes]


def test_current_backend_routes_remain_registered_with_flow_module() -> None:
    assert module_registry.REGISTERED_MODULE_ROUTE_HANDLERS == (
        FLOW_ROUTE_HANDLERS,
    )
    assert module_registry.get_module_route_handlers() == tuple(FLOW_ROUTE_HANDLERS)

    paths = _application_paths()
    assert len(paths) == len(set(paths))
    assert {
        "/api/health",
        "/health",
        "/api/automation-diagnosis/session/start",
        "/api/automation-diagnosis/session/{session_id:str}/answer",
        "/api/automation-diagnosis/session/{session_id:str}/classify",
        "/api/diagnosis/start",
        "/api/diagnosis/message",
        "/api/diagnosis/session/{session_id:str}",
        "/api/diagnosis/submit-checklist",
        "/api/diagnosis/lead",
        "/api/diagnosis/embed/auth",
        "/api/diagnosis/turn",
        "/api/sales-diagnosis-runtime/turn",
        "/api/dev/sales-diagnosis-runtime/turn",
        "/api/console/bootstrap",
        "/api/console/me",
    }.issubset(paths)


def test_registry_composition_preserves_lifecycle_and_cors() -> None:
    app = backend_entrypoint.create_app()

    assert app.on_startup == [
        backend_entrypoint._open_db_pool,
        backend_entrypoint._start_flow_scheduler,
    ]
    assert app.on_shutdown == [
        backend_entrypoint._stop_flow_scheduler,
        backend_entrypoint._close_db_pool,
    ]
    assert app.cors_config is not None
    assert app.cors_config.allow_methods == ["*"]
    assert app.cors_config.allow_headers == ["*"]
    assert set(app.cors_config.allow_origins) == {
        "http://localhost:3050",
        "http://127.0.0.1:3050",
        "http://localhost:3060",
        "http://127.0.0.1:3060",
        "http://localhost:3061",
        "http://127.0.0.1:3061",
        "https://team360.live",
        "https://mamamia360.com",
        "https://www.mamamia360.com",
    }


def test_registered_module_can_add_and_grow_its_own_routes(monkeypatch) -> None:
    module_routes = (_first_module_route, _second_module_route)
    monkeypatch.setattr(
        module_registry,
        "REGISTERED_MODULE_ROUTE_HANDLERS",
        (module_routes,),
    )

    with TestClient(backend_entrypoint.create_app()) as client:
        assert client.get("/api/test-module/first").json() == {"route": "first"}
        assert client.get("/api/test-module/second").json() == {"route": "second"}

    module_routes = (*module_routes, _third_module_route)
    monkeypatch.setattr(
        module_registry,
        "REGISTERED_MODULE_ROUTE_HANDLERS",
        (module_routes,),
    )

    with TestClient(backend_entrypoint.create_app()) as client:
        assert client.get("/api/test-module/third").json() == {"route": "third"}
