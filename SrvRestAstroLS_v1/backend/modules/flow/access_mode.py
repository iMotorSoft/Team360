"""Flow HTTP access policy: authenticated by default, explicit DEV demo only.

``TEAM360_FLOW_ACCESS_MODE=default_admin`` requires explicit
``TEAM360_ENV=development`` or ``dev``. It is not a production policy.
Absent mode uses existing PASETO + persisted capabilities; invalid configuration
is rejected, never normalized into administrator access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

FLOW_ACCESS_MODE_ENV = "TEAM360_FLOW_ACCESS_MODE"
DEFAULT_ADMIN_MODE = "default_admin"
AUTHENTICATED_MODE = "authenticated"

FLOW_EXECUTIVE_READ = "flow.executive.read"
FLOW_CONFIGURATION_READ = "flow.configuration.read"
FLOW_CONFIGURATION_WRITE = "flow.configuration.write"

ALL_FLOW_CAPABILITIES = frozenset(
    {
        FLOW_EXECUTIVE_READ,
        FLOW_CONFIGURATION_READ,
        FLOW_CONFIGURATION_WRITE,
    }
)

# Canonical synthetic identity used when Flow runs in default-admin mode, so
# future logs/audit can attribute actions to the MVP administrator.
MVP_ADMIN_USER_ID = "flow-mvp-administrator"


@dataclass(frozen=True, slots=True)
class FlowActor:
    """Resolved Flow actor for the current request."""

    role: str
    user_id: str
    capabilities: frozenset[str]

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


class FlowAccessConfigurationError(ValueError):
    """Flow access configuration is unsafe or invalid."""


def flow_access_mode() -> str:
    """Resolve access policy; do not infer DEV from a default or hostname."""
    mode = os.environ.get(FLOW_ACCESS_MODE_ENV, AUTHENTICATED_MODE).strip().lower()
    if mode not in {DEFAULT_ADMIN_MODE, AUTHENTICATED_MODE}:
        raise FlowAccessConfigurationError("Invalid TEAM360_FLOW_ACCESS_MODE")
    if mode == DEFAULT_ADMIN_MODE:
        # TEAM360_ENV is the existing runtime authority. Its global default is
        # intentionally NOT sufficient to enable privileged demo access.
        environment = os.environ.get("TEAM360_ENV", "").strip().lower()
        if environment not in {"development", "dev"}:
            raise FlowAccessConfigurationError(
                "Flow default_admin requires explicit TEAM360_ENV=development or dev"
            )
    return mode


def default_admin_actor() -> FlowActor:
    """Create a synthetic administrator only under the explicit DEV policy."""
    if flow_access_mode() != DEFAULT_ADMIN_MODE:
        raise FlowAccessConfigurationError("Flow demo administrator is not enabled")
    return FlowActor(
        role="administrator",
        user_id=MVP_ADMIN_USER_ID,
        capabilities=ALL_FLOW_CAPABILITIES,
    )


def is_default_admin_mode() -> bool:
    return flow_access_mode() == DEFAULT_ADMIN_MODE
