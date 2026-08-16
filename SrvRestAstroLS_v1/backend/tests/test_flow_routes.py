"""Route export contract owned by Team360 Flow."""

from modules.flow.routes import ROUTE_HANDLERS


def test_flow_exports_explicit_route_handlers() -> None:
    assert isinstance(ROUTE_HANDLERS, tuple)
    assert len(ROUTE_HANDLERS) == 1


def test_flow_executive_route_path_and_method() -> None:
    handler = ROUTE_HANDLERS[0]
    assert "/api/team360-flow/executive/{request_id:str}" in handler.paths
    assert "GET" in handler.http_methods
