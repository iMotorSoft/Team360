"""Route export contract owned by Team360 Flow."""

from modules.flow.routes import ROUTE_HANDLERS


def test_flow_exports_explicit_route_handlers() -> None:
    assert isinstance(ROUTE_HANDLERS, tuple)
    assert ROUTE_HANDLERS == ()
