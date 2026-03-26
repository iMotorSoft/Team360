"""Helpers for runtime paths used by the browser lab."""

from datetime import datetime, timezone
from pathlib import Path

from .config import (
    DEFAULT_PROFILE_NAME,
    PROFILES_DIR,
    RUNTIME_DIR,
    SCREENSHOTS_DIR,
    STORAGE_STATE_DIR,
)


def _safe_name(value: str) -> str:
    """Keep generated runtime names filesystem-friendly."""
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value).strip("_") or "default"


def ensure_runtime_dirs() -> None:
    """Create runtime directories if they do not exist yet."""
    for path in (RUNTIME_DIR, PROFILES_DIR, STORAGE_STATE_DIR, SCREENSHOTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def get_profile_dir(profile_name: str = DEFAULT_PROFILE_NAME) -> Path:
    """Return the persistent Chromium profile directory."""
    ensure_runtime_dirs()
    return PROFILES_DIR / _safe_name(profile_name)


def get_storage_state_path(profile_name: str = DEFAULT_PROFILE_NAME) -> Path:
    """Return the storage-state JSON path for a profile."""
    ensure_runtime_dirs()
    return STORAGE_STATE_DIR / f"{_safe_name(profile_name)}.json"


def get_screenshot_path(prefix: str = "smoke_login") -> Path:
    """Return a timestamped screenshot path."""
    ensure_runtime_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return SCREENSHOTS_DIR / f"{_safe_name(prefix)}_{stamp}.png"
