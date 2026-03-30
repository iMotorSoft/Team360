"""Global configuration for the current Team360 backend runtime.

Team360 current focus:
- real sales channels
- conversational flow and orchestration
- seller questions / inbox reading
- normalization into the orchestrator
- operational telemetry

Anything related to catalog sync, pgvector, retrieval or reuse from v360 is kept as
future optional infrastructure and is not part of the active runtime path today.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

SERVICE_NAME = "backend-team360"
SERVICE_VERSION = "0.1.0"
DEFAULT_ENV = os.environ.get("TEAM360_ENV", "development").strip().lower() or "development"
SSE_CHANNEL_NAME = "team360-events"


def _is_postgresql_scheme(url: str) -> bool:
    scheme = urlparse(url).scheme.lower().strip()
    return scheme in {"postgresql", "postgresql+psycopg", "postgres"}


def _replace_database_name(url: str, database_name: str) -> str:
    parsed = urlparse(url)
    path = f"/{database_name.lstrip('/')}"
    return urlunparse(parsed._replace(path=path))


# Future optional catalog / retrieval settings.
# These values are preserved only for later experiments and are not used by the
# current Team360 runtime, browser lab, AG-UI/SSE core or conversational flow.
FUTURE_OPTIONAL_TEAM360_DB_NAME = os.environ.get("TEAM360_DB_NAME", "team360").strip() or "team360"
FUTURE_OPTIONAL_TEAM360_DB_SCHEMA = os.environ.get("TEAM360_DB_SCHEMA", "public").strip() or "public"
FUTURE_OPTIONAL_TARGET_CHANNEL = os.environ.get("TEAM360_TARGET_CHANNEL", "mercadolibre").strip() or "mercadolibre"
FUTURE_OPTIONAL_VECTOR_DIM = int(os.environ.get("TEAM360_VECTOR_DIM", "1536"))
FUTURE_OPTIONAL_EMBEDDING_MODEL = os.environ.get("TEAM360_EMBEDDING_MODEL", "text-embedding-3-small").strip()

FUTURE_OPTIONAL_V360_SOURCE_DB_URL = os.environ.get("DB_PG_V360_URL", "").strip()
FUTURE_OPTIONAL_OPENAI_API_KEY = (
    os.environ.get("TEAM360_OPENAI_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("VERTICE360_OPENAI_KEY")
    or ""
).strip()


def _derive_future_optional_team360_db_url() -> str:
    if FUTURE_OPTIONAL_V360_SOURCE_DB_URL and _is_postgresql_scheme(FUTURE_OPTIONAL_V360_SOURCE_DB_URL):
        return _replace_database_name(FUTURE_OPTIONAL_V360_SOURCE_DB_URL, FUTURE_OPTIONAL_TEAM360_DB_NAME)
    return f"postgresql+psycopg://user:pass@localhost:5432/{FUTURE_OPTIONAL_TEAM360_DB_NAME}"


FUTURE_OPTIONAL_TEAM360_DB_URL = os.environ.get("TEAM360_DB_URL", "").strip()


def get_future_optional_team360_db_url() -> str:
    """Return the optional Team360 DB URL used only by future catalog experiments."""
    return FUTURE_OPTIONAL_TEAM360_DB_URL or _derive_future_optional_team360_db_url()


def get_future_optional_team360_db_url_psql() -> str:
    """Return a psql-compatible DSN for the optional Team360 catalog database."""
    candidate = get_future_optional_team360_db_url()
    if candidate.startswith("postgresql+psycopg://"):
        return "postgresql://" + candidate[len("postgresql+psycopg://") :]
    return candidate


def get_future_optional_v360_source_db_url() -> str:
    """Return the optional v360 source DSN used only by future catalog experiments."""
    return FUTURE_OPTIONAL_V360_SOURCE_DB_URL


def get_future_optional_v360_source_db_url_psql() -> str:
    """Return a psql-compatible DSN for the optional v360 source database."""
    candidate = FUTURE_OPTIONAL_V360_SOURCE_DB_URL
    if candidate.startswith("postgresql+psycopg://"):
        return "postgresql://" + candidate[len("postgresql+psycopg://") :]
    return candidate
