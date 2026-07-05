from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.security.paseto_tokens import verify_paseto_v4_public


@dataclass(frozen=True)
class ConsolePrincipal:
    user_id: str
    subject: str
    claims: dict[str, Any]


class ConsoleAuthError(Exception):
    pass


def extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise ConsoleAuthError("Authorization header is required")

    raw = authorization_header.strip()
    if not raw:
        raise ConsoleAuthError("Authorization header is required")

    parts = raw.split(None, 1)
    if not parts or parts[0].lower() != "bearer":
        raise ConsoleAuthError("Authorization scheme must be Bearer")

    token = parts[1] if len(parts) > 1 else ""
    if not token.strip():
        raise ConsoleAuthError("Bearer token is empty")

    return token


def verify_console_access_token(
    token: str,
    *,
    public_keys_by_id: dict[str, str],
    issuer: str = "team360",
    leeway_seconds: int = 30,
) -> ConsolePrincipal:
    try:
        payload = verify_paseto_v4_public(
            token,
            public_keys_by_id=public_keys_by_id,
            issuer=issuer,
            expected_type="console_access",
            leeway_seconds=leeway_seconds,
        )
    except Exception as exc:
        raise ConsoleAuthError(str(exc)) from exc

    sub = payload.get("sub", "")
    if not sub.startswith("user:"):
        raise ConsoleAuthError("Invalid subject: must start with 'user:'")

    user_id = payload.get("user_id")
    if not user_id:
        raise ConsoleAuthError("Missing user_id claim")

    return ConsolePrincipal(
        user_id=str(user_id),
        subject=sub,
        claims=payload,
    )
