from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from modules.db.errors import DatabaseConfigurationError


def _is_postgresql_scheme(url: str) -> bool:
    scheme = urlparse(url).scheme.lower().strip()
    return scheme in {"postgresql", "postgresql+psycopg", "postgres"}


def _replace_database_name(url: str, database_name: str) -> str:
    parsed = urlparse(url)
    path = f"/{database_name.lstrip('/')}"
    return urlunparse(parsed._replace(path=path))


def _normalize_psycopg_dsn(url: str) -> str:
    """Convert SQLAlchemy-style psycopg URLs into libpq-compatible DSNs."""
    parsed = urlparse(url)
    if parsed.scheme.lower().strip() == "postgresql+psycopg":
        return urlunparse(parsed._replace(scheme="postgresql"))
    return url


def sanitize_dsn(dsn: str) -> str:
    """Remove password from a DSN for safe logging.

    Supports postgresql://, postgresql+psycopg:// and postgres:// schemes.
    """
    try:
        parsed = urlparse(dsn)
        if parsed.password:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc = f"{parsed.hostname}:{parsed.port}"
            parsed = parsed._replace(netloc=netloc)
        return urlunparse(parsed)
    except Exception:
        return "<invalid-dsn>"


@dataclass(frozen=True)
class DatabaseSettings:
    dsn: str
    min_size: int = 1
    max_size: int = 10
    connect_timeout: int = 10
    application_name: str = "team360-backend"

    def __repr__(self) -> str:
        return (
            f"DatabaseSettings(dsn={sanitize_dsn(self.dsn)!r}, "
            f"min_size={self.min_size}, max_size={self.max_size}, "
            f"connect_timeout={self.connect_timeout}, "
            f"application_name={self.application_name!r})"
        )


_TEAM360_DB_URL_ENV = "TEAM360_DB_URL"
_TEAM360_DB_URL_PSQL_ENV = "TEAM360_DB_URL_PSQL"
_V360_SOURCE_DB_URL_ENV = "DB_PG_V360_URL"
_DEFAULT_TEAM360_DB_NAME = "team360"
_DEFAULT_MIN_SIZE = 1
_DEFAULT_MAX_SIZE = 10
_DEFAULT_CONNECT_TIMEOUT = 10
_DEFAULT_APP_NAME = "team360-backend"


def _resolve_dsn() -> str:
    """Resolve the Team360 DSN from environment variables."""
    team360_url = os.environ.get(_TEAM360_DB_URL_ENV, "").strip()
    if team360_url and _is_postgresql_scheme(team360_url):
        return _normalize_psycopg_dsn(team360_url)

    team360_url_psql = os.environ.get(_TEAM360_DB_URL_PSQL_ENV, "").strip()
    if team360_url_psql and _is_postgresql_scheme(team360_url_psql):
        return _normalize_psycopg_dsn(team360_url_psql)

    v360_url = os.environ.get(_V360_SOURCE_DB_URL_ENV, "").strip()
    if v360_url and _is_postgresql_scheme(v360_url):
        return _normalize_psycopg_dsn(
            _replace_database_name(v360_url, _DEFAULT_TEAM360_DB_NAME)
        )

    msg = (
        f"Cannot resolve DSN: set {_TEAM360_DB_URL_ENV}, "
        f"{_TEAM360_DB_URL_PSQL_ENV} or {_V360_SOURCE_DB_URL_ENV} "
        "with a valid PostgreSQL connection string."
    )
    raise DatabaseConfigurationError(msg)


def get_database_settings(
    min_size: int | None = None,
    max_size: int | None = None,
    connect_timeout: int | None = None,
    application_name: str | None = None,
) -> DatabaseSettings:
    """Build DatabaseSettings from environment.

    DSN resolution priority:
        1. TEAM360_DB_URL
        2. TEAM360_DB_URL_PSQL
        3. DB_PG_V360_URL (replace database name with 'team360')

    All other parameters fall back to defaults if not provided.
    """
    dsn = _resolve_dsn()
    return DatabaseSettings(
        dsn=dsn,
        min_size=min_size if min_size is not None else _DEFAULT_MIN_SIZE,
        max_size=max_size if max_size is not None else _DEFAULT_MAX_SIZE,
        connect_timeout=connect_timeout if connect_timeout is not None else _DEFAULT_CONNECT_TIMEOUT,
        application_name=application_name if application_name is not None else _DEFAULT_APP_NAME,
    )
