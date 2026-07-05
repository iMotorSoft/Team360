"""Protected console endpoint — GET /api/console/me.

Requires PASETO v4.public Bearer token (typ=console_access).
Returns current principal identity extracted from the token.
"""

from __future__ import annotations

from litestar import get
from litestar.connection import Request
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_401_UNAUTHORIZED

from modules.console.auth import ConsoleAuthError, extract_bearer_token, verify_console_access_token
from modules.security.paseto_tokens import get_dev_public_keys_by_id, paseto_console_settings_from_env


@get("/api/console/me")
async def console_me(
    request: Request | None = None,
) -> dict[str, str]:
    if request is None:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
        )

    authorization = request.headers.get("Authorization")

    try:
        token = extract_bearer_token(authorization)
    except ConsoleAuthError as exc:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    settings = paseto_console_settings_from_env()
    public_keys = _resolve_public_keys(settings)

    try:
        principal = verify_console_access_token(
            token,
            public_keys_by_id=public_keys,
            issuer=settings.issuer,
        )
    except ConsoleAuthError as exc:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    return {
        "user_id": principal.user_id,
        "subject": principal.subject,
        "token_type": "paseto_v4_public",
    }


def _resolve_public_keys(
    settings: object,
) -> dict[str, str]:
    public_pem: str | None = getattr(settings, "public_key_pem", None)
    if public_pem:
        return {getattr(settings, "key_id", "console-key"): public_pem}
    return get_dev_public_keys_by_id()
