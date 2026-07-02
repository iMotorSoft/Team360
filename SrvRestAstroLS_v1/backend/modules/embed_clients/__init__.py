from modules.embed_clients.audit import (
    EmbedAuthAuditEvent,
    EmbedAuthAuditor,
    LoggingEmbedAuthAuditor,
    build_embed_auth_audit_event,
)
from modules.embed_clients.auth import (
    DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
    SIGNATURE_HEADER_NAME,
    authorize_request,
    build_context,
    get_timestamp_tolerance_seconds,
    issue_signature,
    resolve_request_origin,
)
from modules.embed_clients.errors import (
    EmbedClientError,
    EmbedClientExpiredTimestampError,
    EmbedClientInactiveError,
    EmbedClientInvalidSessionError,
    EmbedClientInvalidSignatureError,
    EmbedClientNotFoundError,
    EmbedClientOriginDeniedError,
)
from modules.embed_clients.models import EmbedClient
from modules.embed_clients.rate_limit import (
    DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_KEYS,
    DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS,
    DEFAULT_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS,
    EmbedAuthRateLimitSettings,
    InMemoryRateLimiter,
    RateLimitDecision,
    build_embed_auth_rate_limit_key,
    get_embed_auth_rate_limit_settings,
)
from modules.embed_clients.repository import (
    EmbedClientRepository,
    InMemoryEmbedClientRepository,
    PostgresEmbedClientRepository,
)

__all__ = [
    "EmbedClient",
    "DEFAULT_TIMESTAMP_TOLERANCE_SECONDS",
    "DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_KEYS",
    "DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS",
    "DEFAULT_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS",
    "EmbedClientError",
    "EmbedAuthAuditEvent",
    "EmbedAuthAuditor",
    "EmbedAuthRateLimitSettings",
    "EmbedClientExpiredTimestampError",
    "EmbedClientInactiveError",
    "EmbedClientInvalidSessionError",
    "EmbedClientInvalidSignatureError",
    "EmbedClientNotFoundError",
    "EmbedClientOriginDeniedError",
    "EmbedClientRepository",
    "InMemoryEmbedClientRepository",
    "InMemoryRateLimiter",
    "LoggingEmbedAuthAuditor",
    "PostgresEmbedClientRepository",
    "RateLimitDecision",
    "SIGNATURE_HEADER_NAME",
    "authorize_request",
    "build_embed_auth_audit_event",
    "build_context",
    "build_embed_auth_rate_limit_key",
    "get_embed_auth_rate_limit_settings",
    "get_timestamp_tolerance_seconds",
    "issue_signature",
    "resolve_request_origin",
]
