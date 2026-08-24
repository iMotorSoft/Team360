"""Route export contract owned by Team360 Flow."""

from modules.flow.routes import ROUTE_HANDLERS


def test_flow_exports_explicit_route_handlers() -> None:
    assert isinstance(ROUTE_HANDLERS, tuple)
    assert len(ROUTE_HANDLERS) == 9


def test_flow_executive_route_path_and_method() -> None:
    handler = ROUTE_HANDLERS[0]
    assert "/api/team360-flow/executive/{request_id:str}" in handler.paths
    assert "GET" in handler.http_methods


def test_flow_configuration_routes_exported() -> None:
    paths = {path for handler in ROUTE_HANDLERS for path in handler.paths}
    assert "/api/team360-flow/configuration" in paths
    assert "/api/team360-flow/configuration/{sector_id:str}" in paths
    methods = {method for handler in ROUTE_HANDLERS for method in handler.http_methods}
    assert "GET" in methods
    assert "PATCH" in methods


def test_flow_executive_list_route_exported() -> None:
    paths = {path for handler in ROUTE_HANDLERS for path in handler.paths}
    assert "/api/team360-flow/executive" in paths


def test_flow_operational_settings_routes_exported() -> None:
    paths = {path for handler in ROUTE_HANDLERS for path in handler.paths}
    assert "/api/team360-flow/operational-settings" in paths
    methods = {method for handler in ROUTE_HANDLERS for method in handler.http_methods}
    assert "GET" in methods
    assert "PATCH" in methods


def test_flow_scheduler_status_route_exported() -> None:
    paths = {path for handler in ROUTE_HANDLERS for path in handler.paths}
    assert "/api/team360-flow/scheduler/status" in paths


def test_flow_case_cleanup_route_exported() -> None:
    handlers = {
        path: handler
        for handler in ROUTE_HANDLERS
        for path in handler.paths
    }
    handler = handlers["/api/team360-flow/cases/clear"]
    assert "POST" in handler.http_methods
