"""Meta configuration isolation; synthetic values only, no external services."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

FIELDS = (
    "WABA_TOKEN", "WABA_ID", "PHONE_NUMBER_ID", "VERIFY_TOKEN", "APP_SECRET",
    "GRAPH_VERSION",
)
LEGACY = (
    "META_VERTICE360_WABA_TOKEN", "META_VERTICE360_WABA_ID",
    "META_VERTICE360_PHONE_NUMBER_ID", "META_VERTICE360_VERIFY_TOKEN",
    "META_APP_SECRET_IMOTORSOFT", "META_GRAPH_VERSION",
)


@pytest.fixture
def load_config(monkeypatch):
    # Load a fresh, isolated module without changing other tests' globalVar.
    for field in FIELDS:
        monkeypatch.delenv(f"META_TEAM360_{field}", raising=False)
    for key in LEGACY:
        monkeypatch.setenv(key, "synthetic-legacy-value")

    def load():
        path = Path(__file__).resolve().parents[1] / "globalVar.py"
        spec = importlib.util.spec_from_file_location("isolated_meta_config", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load


def test_team360_meta_wins_when_legacy_is_present(monkeypatch, load_config):
    for field in FIELDS:
        monkeypatch.setenv(f"META_TEAM360_{field}", f"synthetic-team360-{field}")
    config = load_config()
    for field in FIELDS:
        assert getattr(config, f"TEAM360_META_{field}") == f"synthetic-team360-{field}"
    assert config.team360_meta_whatsapp_enabled() is True


def test_legacy_only_does_not_enable_team360_meta(load_config):
    config = load_config()
    for field in FIELDS[:-1]:
        assert getattr(config, f"TEAM360_META_{field}") == ""
    assert config.TEAM360_META_GRAPH_VERSION == "v20.0"
    assert config.team360_meta_whatsapp_enabled() is False


@pytest.mark.parametrize("missing", ["WABA_TOKEN", "PHONE_NUMBER_ID", "VERIFY_TOKEN"])
def test_missing_required_team360_value_has_no_legacy_fallback(
    monkeypatch, load_config, missing,
):
    for field in FIELDS:
        monkeypatch.setenv(f"META_TEAM360_{field}", "synthetic-team360-value")
    monkeypatch.delenv(f"META_TEAM360_{missing}")
    config = load_config()
    assert getattr(config, f"TEAM360_META_{missing}") == ""
    assert config.team360_meta_whatsapp_enabled() is False


def test_explicit_empty_team360_values_have_no_fallback(monkeypatch, load_config):
    for field in FIELDS:
        monkeypatch.setenv(f"META_TEAM360_{field}", "")
    config = load_config()
    for field in FIELDS:
        assert getattr(config, f"TEAM360_META_{field}") == ""
    assert config.team360_meta_whatsapp_enabled() is False


def test_no_meta_configuration_uses_only_nonsecret_default(monkeypatch, load_config):
    for key in LEGACY:
        monkeypatch.delenv(key)
    config = load_config()
    assert config.team360_meta_whatsapp_enabled() is False
    assert config.TEAM360_META_GRAPH_VERSION == "v20.0"
