from __future__ import annotations

import pytest

from modules.console.auth import (
    ConsoleAuthError,
    ConsolePrincipal,
    extract_bearer_token,
    verify_console_access_token,
)
from modules.security.paseto_tokens import PasetoKeyPair, issue_paseto_v4_public

_ISSUER = "team360"
_KEY_ID = "test-key-p4b"
_KEY_PAIR = PasetoKeyPair.generate(_KEY_ID)
_PUBLIC_KEYS = {_KEY_PAIR.key_id: _KEY_PAIR.public_pem}
_TTL = 900


def _issue_console_token(
    *,
    user_id: str = "user-42",
    token_type: str = "console_access",
    issuer: str = _ISSUER,
    ttl: int = _TTL,
    extra_claims: dict | None = None,
) -> str:
    claims = {"sub": f"user:{user_id}", "user_id": user_id}
    if extra_claims:
        claims.update(extra_claims)
    return issue_paseto_v4_public(
        claims,
        private_key_pem=_KEY_PAIR.private_pem,
        key_id=_KEY_ID,
        ttl_seconds=ttl,
        issuer=issuer,
        token_type=token_type,
    )


class TestExtractBearerToken:
    def test_extracts_valid_bearer(self):
        token = _issue_console_token()
        result = extract_bearer_token(f"Bearer {token}")
        assert result == token

    def test_rejects_missing_header(self):
        with pytest.raises(ConsoleAuthError, match="Authorization header is required"):
            extract_bearer_token(None)

    def test_rejects_empty_string(self):
        with pytest.raises(ConsoleAuthError, match="Authorization header is required"):
            extract_bearer_token("")

    def test_rejects_basic_auth(self):
        with pytest.raises(ConsoleAuthError, match="Authorization scheme must be Bearer"):
            extract_bearer_token("Basic dXNlcjpwYXNz")

    def test_rejects_empty_bearer(self):
        with pytest.raises(ConsoleAuthError, match="Bearer token is empty"):
            extract_bearer_token("Bearer ")


class TestVerifyConsoleAccessToken:
    def test_accepts_valid_console_token(self):
        token = _issue_console_token()
        principal = verify_console_access_token(token, public_keys_by_id=_PUBLIC_KEYS)
        assert isinstance(principal, ConsolePrincipal)
        assert principal.user_id == "user-42"
        assert principal.subject == "user:user-42"
        assert principal.claims["typ"] == "console_access"
        assert principal.claims["iss"] == _ISSUER

    def test_returns_console_principal_with_user_id(self):
        token = _issue_console_token(user_id="user-99")
        principal = verify_console_access_token(token, public_keys_by_id=_PUBLIC_KEYS)
        assert principal.user_id == "user-99"
        assert principal.subject == "user:user-99"

    def test_rejects_wrong_token_type(self):
        token = _issue_console_token(token_type="embed_turn")
        with pytest.raises(ConsoleAuthError, match="Expected typ"):
            verify_console_access_token(token, public_keys_by_id=_PUBLIC_KEYS)

    def test_rejects_wrong_issuer(self):
        token = _issue_console_token(issuer="wrong-issuer")
        with pytest.raises(ConsoleAuthError, match="Expected iss"):
            verify_console_access_token(token, public_keys_by_id=_PUBLIC_KEYS)

    def test_rejects_sub_without_user_prefix(self):
        token = issue_paseto_v4_public(
            {"sub": "client:demo", "user_id": "u1"},
            private_key_pem=_KEY_PAIR.private_pem,
            key_id=_KEY_ID,
            ttl_seconds=_TTL,
            issuer=_ISSUER,
            token_type="console_access",
        )
        with pytest.raises(ConsoleAuthError, match="Invalid subject"):
            verify_console_access_token(token, public_keys_by_id=_PUBLIC_KEYS)

    def test_rejects_missing_user_id_claim(self):
        token = issue_paseto_v4_public(
            {"sub": "user:u1"},
            private_key_pem=_KEY_PAIR.private_pem,
            key_id=_KEY_ID,
            ttl_seconds=_TTL,
            issuer=_ISSUER,
            token_type="console_access",
        )
        with pytest.raises(ConsoleAuthError, match="Missing user_id"):
            verify_console_access_token(token, public_keys_by_id=_PUBLIC_KEYS)

    def test_rejects_unknown_kid(self):
        token = _issue_console_token()
        wrong_keys = {"other-key": _KEY_PAIR.public_pem}
        with pytest.raises(ConsoleAuthError, match="Unknown key_id"):
            verify_console_access_token(token, public_keys_by_id=wrong_keys)

    def test_rejects_expired_token(self):
        token = _issue_console_token(ttl=-3600)
        with pytest.raises(ConsoleAuthError, match="Token expired"):
            verify_console_access_token(token, public_keys_by_id=_PUBLIC_KEYS)

    def test_rejects_malformed_token(self):
        with pytest.raises(ConsoleAuthError, match="Malformed"):
            verify_console_access_token("not-a-valid-token", public_keys_by_id=_PUBLIC_KEYS)


class TestEndToEndP4A:
    def test_token_from_bootstrap_verifies_via_console_auth(self):
        """Circuit test: token issued by P4A bootstrap can be verified by P4B verifier."""
        token = _issue_console_token(user_id="user-1")
        principal = verify_console_access_token(token, public_keys_by_id=_PUBLIC_KEYS)
        assert principal.user_id == "user-1"
        assert principal.subject == "user:user-1"
