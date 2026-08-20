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


# Team360 database settings are active backend runtime configuration.
TEAM360_DB_NAME = os.environ.get("TEAM360_DB_NAME", "team360").strip() or "team360"
TEAM360_DB_SCHEMA = os.environ.get("TEAM360_DB_SCHEMA", "public").strip() or "public"
TEAM360_DB_URL = os.environ.get("TEAM360_DB_URL", "").strip()
TEAM360_DB_URL_PSQL = os.environ.get("TEAM360_DB_URL_PSQL", "").strip()
V360_SOURCE_DB_URL = os.environ.get("DB_PG_V360_URL", "").strip()

# Future optional catalog / retrieval settings.
# These values are preserved only for later experiments and are not used by the
# current Team360 runtime, browser lab, AG-UI/SSE core or conversational flow.
FUTURE_OPTIONAL_TEAM360_DB_NAME = TEAM360_DB_NAME
FUTURE_OPTIONAL_TEAM360_DB_SCHEMA = TEAM360_DB_SCHEMA
FUTURE_OPTIONAL_TARGET_CHANNEL = os.environ.get("TEAM360_TARGET_CHANNEL", "mercadolibre").strip() or "mercadolibre"
FUTURE_OPTIONAL_VECTOR_DIM = int(os.environ.get("TEAM360_VECTOR_DIM", "1536"))
FUTURE_OPTIONAL_EMBEDDING_MODEL = os.environ.get("TEAM360_EMBEDDING_MODEL", "text-embedding-3-small").strip()

FUTURE_OPTIONAL_V360_SOURCE_DB_URL = V360_SOURCE_DB_URL
FUTURE_OPTIONAL_OPENAI_API_KEY = (
    os.environ.get("OpenAI_Key_JAI_query")
    or os.environ.get("TEAM360_OPENAI_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("VERTICE360_OPENAI_KEY")
    or ""
).strip()


def get_team360_openai_key() -> str:
    """Return the Team360 OpenAI API key.

    Resolution priority:
    1. OpenAI_Key_JAI_query (used by JAI infrastructure)
    2. TEAM360_OPENAI_KEY
    3. OPENAI_API_KEY
    4. VERTICE360_OPENAI_KEY
    """
    return (
        os.environ.get("OpenAI_Key_JAI_query", "").strip()
        or os.environ.get("TEAM360_OPENAI_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
        or os.environ.get("VERTICE360_OPENAI_KEY", "").strip()
    )


def get_team360_openai_model() -> str:
    """Return the Team360 OpenAI model name.

    Resolution priority:
    1. TEAM360_OPENAI_MODEL
    2. Default: gpt-5-nano
    """
    return os.environ.get("TEAM360_OPENAI_MODEL", "").strip() or "gpt-5-nano"


def _to_psql_dsn(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _derive_team360_db_url() -> str:
    if V360_SOURCE_DB_URL and _is_postgresql_scheme(V360_SOURCE_DB_URL):
        return _replace_database_name(V360_SOURCE_DB_URL, TEAM360_DB_NAME)
    return ""


def _derive_future_optional_team360_db_url() -> str:
    return _derive_team360_db_url() or (
        f"postgresql+psycopg://user:pass@localhost:5432/{TEAM360_DB_NAME}"
    )


def get_team360_db_url() -> str:
    """Return the Team360 backend database DSN, with documented fallbacks."""
    return TEAM360_DB_URL or TEAM360_DB_URL_PSQL or _derive_team360_db_url()


# =========================
# Messaging / Gupshup WhatsApp (Team360)
# =========================
# Read from existing V360-compatible env vars (GUPSHUP_*) when available,
# fall back to TEAM360_-prefixed vars.
TEAM360_GUPSHUP_BASE_URL: str = os.environ.get(
    "TEAM360_GUPSHUP_BASE_URL",
    os.environ.get("GUPSHUP_BASE_URL", "https://api.gupshup.io"),
)
TEAM360_GUPSHUP_APP_NAME_DEV: str = os.environ.get(
    "TEAM360_GUPSHUP_APP_NAME_DEV",
    os.environ.get("GUPSHUP_APP_NAME_DEV", ""),
)
TEAM360_GUPSHUP_APP_NAME_PRO: str = os.environ.get(
    "TEAM360_GUPSHUP_APP_NAME_PRO",
    os.environ.get("GUPSHUP_APP_NAME_PRO", ""),
)
TEAM360_GUPSHUP_API_KEY_DEV: str = os.environ.get(
    "TEAM360_GUPSHUP_API_KEY_DEV",
    os.environ.get("GUPSHUP_API_KEY_DEV", ""),
)
TEAM360_GUPSHUP_API_KEY_PRO: str = os.environ.get(
    "TEAM360_GUPSHUP_API_KEY_PRO",
    os.environ.get("GUPSHUP_API_KEY_PRO", ""),
)
TEAM360_GUPSHUP_SRC_NUMBER_DEV: str = os.environ.get(
    "TEAM360_GUPSHUP_SRC_NUMBER_DEV",
    os.environ.get("GUPSHUP_SRC_NUMBER_DEV", ""),
)
TEAM360_GUPSHUP_SRC_NUMBER_PRO: str = os.environ.get(
    "TEAM360_GUPSHUP_SRC_NUMBER_PRO",
    os.environ.get("GUPSHUP_SRC_NUMBER_PRO", ""),
)
TEAM360_GUPSHUP_WA_SENDER: str = os.environ.get(
    "TEAM360_GUPSHUP_WA_SENDER",
    os.environ.get("GUPSHUP_WA_SENDER", ""),
).strip()
TEAM360_GUPSHUP_BASE_URL_DEV: str = os.environ.get(
    "TEAM360_GUPSHUP_BASE_URL_DEV",
    os.environ.get("GUPSHUP_BASE_URL_DEV", TEAM360_GUPSHUP_BASE_URL),
)
TEAM360_GUPSHUP_BASE_URL_PRO: str = os.environ.get(
    "TEAM360_GUPSHUP_BASE_URL_PRO",
    os.environ.get("GUPSHUP_BASE_URL_PRO", TEAM360_GUPSHUP_BASE_URL_DEV),
)

# =========================
# Messaging / Meta WhatsApp Cloud (Team360)
# =========================
TEAM360_META_WABA_TOKEN: str = os.environ.get(
    "META_VERTICE360_WABA_TOKEN", ""
)
TEAM360_META_WABA_ID: str = os.environ.get(
    "META_VERTICE360_WABA_ID", ""
)
TEAM360_META_PHONE_NUMBER_ID: str = os.environ.get(
    "META_VERTICE360_PHONE_NUMBER_ID", ""
)
TEAM360_META_VERIFY_TOKEN: str = os.environ.get(
    "META_VERTICE360_VERIFY_TOKEN", ""
)
TEAM360_META_APP_SECRET: str = os.environ.get(
    "META_APP_SECRET_IMOTORSOFT", ""
)
TEAM360_META_GRAPH_VERSION: str = os.environ.get(
    "META_GRAPH_VERSION", "v20.0"
)


# =========================
# Gupshup environment-aware selection
# =========================
def _team360_pick_env(dev: str, pro: str) -> str:
    """Select value based on DEFAULT_ENV."""
    return pro if DEFAULT_ENV == "production" else dev


def get_team360_gupshup_config() -> dict[str, str]:
    """Return resolved Gupshup config for the current environment."""
    app_name = _team360_pick_env(
        TEAM360_GUPSHUP_APP_NAME_DEV, TEAM360_GUPSHUP_APP_NAME_PRO
    )
    api_key = _team360_pick_env(
        TEAM360_GUPSHUP_API_KEY_DEV, TEAM360_GUPSHUP_API_KEY_PRO
    )
    src_number = _team360_pick_env(
        TEAM360_GUPSHUP_SRC_NUMBER_DEV, TEAM360_GUPSHUP_SRC_NUMBER_PRO
    )
    base_url = _team360_pick_env(
        TEAM360_GUPSHUP_BASE_URL_DEV, TEAM360_GUPSHUP_BASE_URL_PRO
    )
    sender = TEAM360_GUPSHUP_WA_SENDER
    return {
        "app_name": app_name,
        "api_key": api_key,
        "source_number": src_number,
        "base_url": base_url,
        "sender": sender,
    }


def get_team360_gupshup_config_masked() -> dict[str, str]:
    """Return Gupshup config with secrets masked for diagnostics."""
    cfg = get_team360_gupshup_config()
    return {
        "configured": bool(cfg["api_key"] and cfg["app_name"]),
        "app_name_present": bool(cfg["app_name"]),
        "api_key_present": bool(cfg["api_key"]),
        "source_present": bool(cfg["source_number"]),
        "base_url_present": bool(cfg["base_url"]),
        "sender_present": bool(cfg["sender"]),
    }


def team360_gupshup_enabled() -> bool:
    """True when Gupshup provider is configured for outbound."""
    cfg = get_team360_gupshup_config()
    return bool(cfg["api_key"] and cfg["app_name"] and cfg["source_number"])


def team360_meta_whatsapp_enabled() -> bool:
    """True when Meta WhatsApp provider is configured."""
    return bool(
        TEAM360_META_WABA_TOKEN
        and TEAM360_META_PHONE_NUMBER_ID
        and TEAM360_META_VERIFY_TOKEN
    )


def get_team360_db_url_psql() -> str:
    """Return a psql-compatible Team360 backend database DSN."""
    return _to_psql_dsn(get_team360_db_url())


FUTURE_OPTIONAL_TEAM360_DB_URL = TEAM360_DB_URL


def get_future_optional_team360_db_url() -> str:
    """Return the optional Team360 DB URL used only by future catalog experiments."""
    return get_team360_db_url() or _derive_future_optional_team360_db_url()


def get_future_optional_team360_db_url_psql() -> str:
    """Return a psql-compatible DSN for the optional Team360 catalog database."""
    return _to_psql_dsn(get_future_optional_team360_db_url())


def get_future_optional_v360_source_db_url() -> str:
    """Return the optional v360 source DSN used only by future catalog experiments."""
    return FUTURE_OPTIONAL_V360_SOURCE_DB_URL


def get_future_optional_v360_source_db_url_psql() -> str:
    """Return a psql-compatible DSN for the optional v360 source database."""
    return _to_psql_dsn(FUTURE_OPTIONAL_V360_SOURCE_DB_URL)
