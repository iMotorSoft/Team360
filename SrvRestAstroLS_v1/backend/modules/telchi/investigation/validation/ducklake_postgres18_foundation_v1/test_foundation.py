from __future__ import annotations

from pathlib import Path

import pytest

from .runtime import TelchiDuckLakeConfig


@pytest.fixture
def config(tmp_path: Path) -> TelchiDuckLakeConfig:
    return TelchiDuckLakeConfig(
        host="localhost",
        port=5432,
        database="team360_telchi_ducklake",
        user="team360_telchi_ducklake",
        password="runtime-only-secret",
        data_root=tmp_path,
        data_path=tmp_path / "ducklake" / "data",
        private_config=tmp_path / "private.env",
    )


def test_catalog_entry_has_no_password(config: TelchiDuckLakeConfig) -> None:
    assert config.password not in config.catalog_entry()
    assert "password" not in config.catalog_entry().lower()


def test_config_rejects_relative_data_paths(config: TelchiDuckLakeConfig) -> None:
    unsafe = config.__class__(**{**config.__dict__, "data_path": Path("relative/data")})
    with pytest.raises(ValueError, match="absolute"):
        unsafe.validate()


def test_config_rejects_raw_reference_and_crosswalk_ownership(config: TelchiDuckLakeConfig) -> None:
    for layer in ("raw", "reference", "crosswalk"):
        unsafe = config.__class__(**{**config.__dict__, "data_path": config.data_root / layer})
        with pytest.raises(ValueError, match="must not own"):
            unsafe.validate()


def test_redacted_config_does_not_expose_secret(config: TelchiDuckLakeConfig) -> None:
    redacted = config.redacted()
    assert config.password not in repr(redacted)
    assert redacted["password_configured"] == "YES"


def test_private_config_is_environment_driven(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    private = tmp_path / "ducklake.env"
    private.write_text(
        "TELCHI_DUCKLAKE_PG_HOST=localhost\n"
        "TELCHI_DUCKLAKE_PG_PORT=5432\n"
        "TELCHI_DUCKLAKE_PG_DATABASE=isolated\n"
        "TELCHI_DUCKLAKE_PG_USER=runtime\n"
        "TELCHI_DUCKLAKE_PG_PASSWORD=not-in-source\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEAM360_TELCHI_DUCKLAKE_PRIVATE_CONFIG", str(private))
    monkeypatch.setenv("TEAM360_TELCHI_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("TELCHI_DUCKLAKE_DATA_PATH", str(tmp_path / "ducklake" / "data"))
    loaded = TelchiDuckLakeConfig.from_environment()
    assert loaded.database == "isolated"
    assert loaded.user == "runtime"
    assert loaded.password == "not-in-source"
