import os

import pytest

from modules.db.errors import (
    DatabaseConfigurationError,
    DatabasePoolNotInitializedError,
)
from modules.db.pool import create_pool, get_pool, reset_pool_for_tests, set_pool
from modules.db.settings import DatabaseSettings, get_database_settings, sanitize_dsn


class TestSanitizeDsn:
    def test_hides_password_standard(self):
        result = sanitize_dsn("postgresql://user:secret@host:5432/db")
        assert "secret" not in result
        assert "user" not in result
        assert "host:5432" in result

    def test_hides_password_psycopg_scheme(self):
        result = sanitize_dsn("postgresql+psycopg://admin:pass123@localhost:5432/team360")
        assert "pass123" not in result
        assert "admin" not in result

    def test_preserves_no_password_url(self):
        url = "postgresql://host:5432/db"
        assert sanitize_dsn(url) == url

    def test_handles_invalid_url(self):
        result = sanitize_dsn("not a url")
        assert isinstance(result, str)
        # urlparse passes through non-URL strings; no password to redact
        assert "not a url" in result


class TestDatabaseSettingsRepr:
    def test_repr_does_not_expose_password(self):
        settings = DatabaseSettings(
            dsn="postgresql://user:mysecretpassword@host:5432/db"
        )
        r = repr(settings)
        assert "mysecretpassword" not in r
        assert "DatabaseSettings(dsn=" in r
        assert "min_size=" in r
        assert "max_size=" in r
        assert "application_name=" in r

    def test_repr_contains_safe_info(self):
        settings = DatabaseSettings(dsn="postgresql://host/db", min_size=2, max_size=5)
        r = repr(settings)
        assert "min_size=2" in r
        assert "max_size=5" in r


class TestDatabaseSettingsDefaults:
    def test_default_values(self):
        settings = DatabaseSettings(dsn="postgresql://host/db")
        assert settings.min_size == 1
        assert settings.max_size == 10
        assert settings.connect_timeout == 10
        assert settings.application_name == "team360-backend"


class TestGetDatabaseSettings:
    def test_uses_team360_db_url(self, monkeypatch):
        monkeypatch.setenv("TEAM360_DB_URL", "postgresql://u:p@h:5432/team360")
        settings = get_database_settings()
        assert "team360" in settings.dsn
        assert "u:p@h:5432" in settings.dsn

    def test_uses_team360_db_url_psql(self, monkeypatch):
        monkeypatch.delenv("TEAM360_DB_URL", raising=False)
        monkeypatch.setenv("TEAM360_DB_URL_PSQL", "postgresql://u:p@h:5432/team360")
        settings = get_database_settings()
        assert "team360" in settings.dsn

    def test_uses_v360_url_fallback(self, monkeypatch):
        monkeypatch.delenv("TEAM360_DB_URL", raising=False)
        monkeypatch.delenv("TEAM360_DB_URL_PSQL", raising=False)
        monkeypatch.setenv("DB_PG_V360_URL", "postgresql://u:p@h:5432/v360")
        settings = get_database_settings()
        assert "team360" in settings.dsn
        assert "v360" not in settings.dsn

    def test_raises_when_no_dsn(self, monkeypatch):
        monkeypatch.delenv("TEAM360_DB_URL", raising=False)
        monkeypatch.delenv("TEAM360_DB_URL_PSQL", raising=False)
        monkeypatch.delenv("DB_PG_V360_URL", raising=False)
        with pytest.raises(DatabaseConfigurationError):
            get_database_settings()

    def test_non_postgresql_env_ignored(self, monkeypatch):
        monkeypatch.setenv("TEAM360_DB_URL", "sqlite:///test.db")
        monkeypatch.delenv("TEAM360_DB_URL_PSQL", raising=False)
        monkeypatch.delenv("DB_PG_V360_URL", raising=False)
        with pytest.raises(DatabaseConfigurationError):
            get_database_settings()

    def test_custom_parameters(self, monkeypatch):
        monkeypatch.setenv("TEAM360_DB_URL", "postgresql://u:p@h:5432/team360")
        settings = get_database_settings(min_size=3, max_size=20, connect_timeout=5, application_name="test-app")
        assert settings.min_size == 3
        assert settings.max_size == 20
        assert settings.connect_timeout == 5
        assert settings.application_name == "test-app"


class TestPoolLifecycle:
    def test_create_pool_no_auto_open(self):
        settings = DatabaseSettings(dsn="postgresql://u:p@localhost:5432/db")
        pool = create_pool(settings)
        assert pool is not None

    def test_get_pool_without_set_raises(self):
        reset_pool_for_tests()
        with pytest.raises(DatabasePoolNotInitializedError):
            get_pool()

    def test_set_and_get_pool(self):
        settings = DatabaseSettings(dsn="postgresql://u:p@localhost:5432/db")
        pool = create_pool(settings)
        set_pool(pool)
        retrieved = get_pool()
        assert retrieved is pool

    def test_reset_pool_for_tests_clears(self):
        settings = DatabaseSettings(dsn="postgresql://u:p@localhost:5432/db")
        set_pool(create_pool(settings))
        reset_pool_for_tests()
        with pytest.raises(DatabasePoolNotInitializedError):
            get_pool()


class TestImportDoesNotOpenConnection:
    def test_import_db_module(self):
        import importlib
        import modules.db
        importlib.reload(modules.db)
        with pytest.raises(DatabasePoolNotInitializedError):
            modules.db.get_pool()
