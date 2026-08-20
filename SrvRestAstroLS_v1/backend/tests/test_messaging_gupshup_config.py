"""Gupshup configuration tests for Team360.

Validates environment-aware config resolution, masking, and enabled checks.
No real secrets are exposed in tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

import globalVar  # noqa: E402
from modules.messaging.providers.gupshup.whatsapp.config import (  # noqa: E402
    GupshupConfig,
)


# ---------------------------------------------------------------------------
# GupshupConfig
# ---------------------------------------------------------------------------


def test_config_from_dict() -> None:
    cfg = GupshupConfig.from_dict({
        "base_url": "https://api.gupshup.io",
        "api_key": "key-123",
        "app_name": "testapp",
        "sender": "+5491122334455",
        "source_number": "5491122334455",
    })
    assert cfg.base_url == "https://api.gupshup.io"
    assert cfg.api_key == "key-123"
    assert cfg.app_name == "testapp"
    assert cfg.sender_e164 == "+5491122334455"
    assert cfg.source_number == "5491122334455"


def test_config_defaults() -> None:
    cfg = GupshupConfig.from_dict({})
    assert cfg.base_url == "https://api.gupshup.io"
    assert cfg.api_key == ""
    assert cfg.app_name == ""


# ---------------------------------------------------------------------------
# globalVar Gupshup helpers
# ---------------------------------------------------------------------------


def test_get_team360_gupshup_config_returns_dict() -> None:
    cfg = globalVar.get_team360_gupshup_config()
    assert isinstance(cfg, dict)
    assert "app_name" in cfg
    assert "api_key" in cfg
    assert "source_number" in cfg
    assert "base_url" in cfg
    assert "sender" in cfg


def test_get_team360_gupshup_config_masked_returns_dict() -> None:
    masked = globalVar.get_team360_gupshup_config_masked()
    assert isinstance(masked, dict)
    assert "configured" in masked
    assert "app_name_present" in masked
    assert "api_key_present" in masked
    assert "source_present" in masked
    assert "base_url_present" in masked
    assert "sender_present" in masked


def test_masked_config_does_not_expose_secrets() -> None:
    masked = globalVar.get_team360_gupshup_config_masked()
    for key, value in masked.items():
        assert isinstance(value, bool), f"Key {key} should be boolean"
    # All values are booleans — no secret values can leak


def test_team360_gupshup_enabled_returns_bool() -> None:
    result = globalVar.team360_gupshup_enabled()
    assert isinstance(result, bool)


def test_team360_meta_whatsapp_enabled_returns_bool() -> None:
    result = globalVar.team360_meta_whatsapp_enabled()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Environment-aware selection
# ---------------------------------------------------------------------------


def test_team360_pick_env_dev() -> None:
    result = globalVar._team360_pick_env("dev_value", "pro_value")
    # When DEFAULT_ENV is not "production", should pick dev
    if globalVar.DEFAULT_ENV == "production":
        assert result == "pro_value"
    else:
        assert result == "dev_value"
