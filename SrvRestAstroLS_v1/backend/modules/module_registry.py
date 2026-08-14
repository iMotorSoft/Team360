"""Explicit registry for Team360 module-owned route handlers.

Each registered module exposes a ``ROUTE_HANDLERS`` sequence from its own
``routes.py``. Registering a module requires one coordinated import and one
entry below; adding routes to that module afterwards stays module-local.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from modules.flow.routes import ROUTE_HANDLERS as FLOW_ROUTE_HANDLERS

ModuleRouteHandlers = Sequence[Any]


# Keep registration explicit and deterministic. Add each module once here;
# handlers added later remain owned by that module's routes.py.
REGISTERED_MODULE_ROUTE_HANDLERS: tuple[ModuleRouteHandlers, ...] = (
    FLOW_ROUTE_HANDLERS,
)


def get_module_route_handlers() -> tuple[Any, ...]:
    """Return all handlers exported by registered modules, in registry order."""
    return tuple(
        handler
        for module_handlers in REGISTERED_MODULE_ROUTE_HANDLERS
        for handler in module_handlers
    )
