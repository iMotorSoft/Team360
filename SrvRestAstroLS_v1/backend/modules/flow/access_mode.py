"""Team360 Flow access policy (MVP default administrator mode).

For the LaMuni MVP, Flow runs without login: every visitor is treated as an
``administrator`` with full Flow capabilities, resolved centrally here instead
of per-endpoint. The authenticated mode (PASETO + persistent capabilities)
remains implemented and reachable via ``TEAM360_FLOW_ACCESS_MODE`` so the
future activation of authentication is an explicit product decision, not a
rewrite.

Flow access mode:
- ``default_admin`` (default for the MVP): no token required; the actor is
  ``flow-mvp-administrator`` with every Flow capability.
- ``authenticated``: the existing fail-closed guard (401 without/invalid
  token, 403 without the explicit capability) is preserved.
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


def flow_access_mode() -> str:
    """Return the current Flow access mode (default_admin by default)."""
    mode = os.environ.get(FLOW_ACCESS_MODE_ENV, DEFAULT_ADMIN_MODE).strip().lower()
    if mode in {DEFAULT_ADMIN_MODE, AUTHENTICATED_MODE}:
        return mode
    return DEFAULT_ADMIN_MODE


def default_admin_actor() -> FlowActor:
    """The MVP actor: implicit administrator with all Flow capabilities."""
    return FlowActor(
        role="administrator",
        user_id=MVP_ADMIN_USER_ID,
        capabilities=ALL_FLOW_CAPABILITIES,
    )


def is_default_admin_mode() -> bool:
    return flow_access_mode() == DEFAULT_ADMIN_MODE
