"""Fail-closed helpers for environment-bound HTTP surfaces."""

from __future__ import annotations

import os

_EXPLICIT_DEVELOPMENT_ENVIRONMENTS = frozenset({"dev", "development"})


def is_explicit_development_environment() -> bool:
    """Return true only when TEAM360_ENV explicitly selects a DEV environment."""
    return os.environ.get("TEAM360_ENV", "").strip().lower() in _EXPLICIT_DEVELOPMENT_ENVIRONMENTS
