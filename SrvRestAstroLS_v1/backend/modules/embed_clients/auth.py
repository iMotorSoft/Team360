from __future__ import annotations

import os
from time import time
from urllib.parse import urlsplit

from modules.embed_clients.errors import (
    EmbedClientExpiredTimestampError,
    EmbedClientInactiveError,
    EmbedClientInvalidSessionError,
    EmbedClientInvalidSignatureError,
    EmbedClientOriginDeniedError,
)
from modules.embed_clients.hmac import build_canonical_string, sign, verify
from modules.embed_clients.models import EmbedClient

SIGNATURE_HEADER_NAME = "X-T360-Signature"
DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 300


def get_timestamp_tolerance_seconds() -> int:
    raw_value = os.environ.get(
        "TEAM360_EMBED_CLIENT_TIMESTAMP_TOLERANCE_SECONDS",
        "",
    ).strip()
    if not raw_value:
        return DEFAULT_TIMESTAMP_TOLERANCE_SECONDS
    try:
        tolerance = int(raw_value)
    except ValueError:
        return DEFAULT_TIMESTAMP_TOLERANCE_SECONDS
    return tolerance if tolerance > 0 else DEFAULT_TIMESTAMP_TOLERANCE_SECONDS


def _normalise_origin(value: str | None) -> str | None:
    if not value:
        return None
    raw_value = value.strip()
    if not raw_value or raw_value.lower() == "null":
        return None
    parsed = urlsplit(raw_value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def resolve_request_origin(origin_header: str | None, referer_header: str | None) -> str | None:
    resolved_origin = _normalise_origin(origin_header)
    if resolved_origin:
        return resolved_origin
    return _normalise_origin(referer_header)


def build_context(embed_client: EmbedClient) -> dict[str, str]:
    return {
        "assistant_instance_code": embed_client.assistant_instance_code,
        "organization_code": embed_client.organization_code,
        "workspace_code": embed_client.workspace_code,
        "package_code": embed_client.package_code,
        "knowledge_scope_code": embed_client.knowledge_scope_code,
    }


def _parse_signature(signature_header: str | None) -> str:
    if not signature_header:
        raise EmbedClientInvalidSignatureError
    raw_value = signature_header.strip()
    prefix = "sha256="
    if not raw_value.lower().startswith(prefix):
        raise EmbedClientInvalidSignatureError
    signature = raw_value[len(prefix):].strip().lower()
    if len(signature) != 64:
        raise EmbedClientInvalidSignatureError
    if any(ch not in "0123456789abcdef" for ch in signature):
        raise EmbedClientInvalidSignatureError
    return signature


def _validate_origin(embed_client: EmbedClient, origin_header: str | None, referer_header: str | None) -> str:
    request_origin = resolve_request_origin(origin_header, referer_header)
    if not request_origin:
        raise EmbedClientOriginDeniedError
    allowed_origins = {
        normalized
        for normalized in (
            _normalise_origin(origin)
            for origin in embed_client.allowed_origins
        )
        if normalized
    }
    if request_origin not in allowed_origins:
        raise EmbedClientOriginDeniedError
    return request_origin


def _validate_timestamp(timestamp: int | None, now_seconds: int | None = None) -> int:
    if timestamp is None:
        raise EmbedClientExpiredTimestampError
    now_value = int(time()) if now_seconds is None else int(now_seconds)
    candidate = int(timestamp)
    if abs(now_value - candidate) > get_timestamp_tolerance_seconds():
        raise EmbedClientExpiredTimestampError
    return candidate


def authorize_request(
    embed_client: EmbedClient,
    *,
    session_id: str | None,
    message: str,
    timestamp: int | None,
    signature_header: str | None,
    origin_header: str | None,
    referer_header: str | None,
    now_seconds: int | None = None,
) -> dict[str, str]:
    if not embed_client.is_active:
        raise EmbedClientInactiveError

    normalized_session_id = (session_id or "").strip()
    if not normalized_session_id:
        raise EmbedClientInvalidSessionError

    _validate_origin(embed_client, origin_header, referer_header)
    validated_timestamp = _validate_timestamp(timestamp, now_seconds=now_seconds)
    expected_signature = _parse_signature(signature_header)
    canonical = build_canonical_string(
        client_id=embed_client.client_id,
        timestamp=validated_timestamp,
        session_id=normalized_session_id,
        message=message,
    )
    if not verify(canonical, embed_client.hmac_secret, expected_signature):
        raise EmbedClientInvalidSignatureError

    return build_context(embed_client)


def issue_signature(
    embed_client: EmbedClient,
    *,
    session_id: str | None,
    message: str,
    origin_header: str | None,
    referer_header: str | None,
    now_seconds: int | None = None,
) -> dict[str, str | int]:
    if not embed_client.is_active:
        raise EmbedClientInactiveError

    normalized_session_id = (session_id or "").strip()
    if not normalized_session_id:
        raise EmbedClientInvalidSessionError

    _validate_origin(embed_client, origin_header, referer_header)

    issued_timestamp = int(time()) if now_seconds is None else int(now_seconds)
    canonical = build_canonical_string(
        client_id=embed_client.client_id,
        timestamp=issued_timestamp,
        session_id=normalized_session_id,
        message=message,
    )

    return {
        "client_id": embed_client.client_id,
        "timestamp": issued_timestamp,
        "signature": f"sha256={sign(canonical, embed_client.hmac_secret)}",
    }
