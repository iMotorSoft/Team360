class EmbedClientError(Exception):
    """Base exception for embed client operations."""


class EmbedClientNotFoundError(EmbedClientError):
    """Client ID does not correspond to any known embed client."""


class EmbedClientInactiveError(EmbedClientError):
    """Client exists but is not active."""


class EmbedClientOriginDeniedError(EmbedClientError):
    """Origin/Referer not in allowed_origins for this client."""


class EmbedClientInvalidSignatureError(EmbedClientError):
    """HMAC signature missing or does not match."""


class EmbedClientExpiredTimestampError(EmbedClientError):
    """Timestamp is outside the allowed window."""


class EmbedClientInvalidSessionError(EmbedClientError):
    """Embed request did not provide a stable session_id for signature binding."""
