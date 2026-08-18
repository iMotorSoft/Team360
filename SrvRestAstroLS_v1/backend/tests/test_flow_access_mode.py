"""Unit tests for the Flow access policy (MVP default administrator)."""

from modules.flow.access_mode import (
    AUTHENTICATED_MODE,
    DEFAULT_ADMIN_MODE,
    FLOW_CONFIGURATION_READ,
    FLOW_CONFIGURATION_WRITE,
    FLOW_EXECUTIVE_READ,
    MVP_ADMIN_USER_ID,
    default_admin_actor,
    flow_access_mode,
    is_default_admin_mode,
)


def test_default_access_mode_is_default_admin(monkeypatch):
    monkeypatch.delenv("TEAM360_FLOW_ACCESS_MODE", raising=False)
    assert flow_access_mode() == DEFAULT_ADMIN_MODE
    assert is_default_admin_mode() is True


def test_access_mode_reads_authenticated_env(monkeypatch):
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", AUTHENTICATED_MODE)
    assert flow_access_mode() == AUTHENTICATED_MODE
    assert is_default_admin_mode() is False


def test_invalid_access_mode_falls_back_to_default_admin(monkeypatch):
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", "surprise")
    assert flow_access_mode() == DEFAULT_ADMIN_MODE


def test_default_admin_actor_has_all_flow_capabilities():
    actor = default_admin_actor()
    assert actor.role == "administrator"
    assert actor.user_id == MVP_ADMIN_USER_ID
    assert actor.has(FLOW_EXECUTIVE_READ) is True
    assert actor.has(FLOW_CONFIGURATION_READ) is True
    assert actor.has(FLOW_CONFIGURATION_WRITE) is True


def test_default_admin_actor_is_flow_scoped():
    actor = default_admin_actor()
    assert actor.has("organizations.read") is False
    assert actor.has("user.manage") is False
