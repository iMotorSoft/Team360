from __future__ import annotations

from litestar.testing import TestClient

from ls_iMotorSoft_Srv01 import create_app
from modules.security.paseto_tokens import PasetoKeyPair, issue_paseto_v4_public

_ISSUER = "team360"
_KEY_ID = "route-test-key"
_KEY_PAIR = PasetoKeyPair.generate(_KEY_ID)
_PUBLIC_KEYS_B64 = _KEY_PAIR.public_pem.encode("utf-8")


def _client():
    return TestClient(create_app())


def _valid_token(**overrides) -> str:
    claims = {
        "sub": "user:route-user",
        "user_id": overrides.pop("user_id", "route-user"),
    }
    return issue_paseto_v4_public(
        claims,
        private_key_pem=overrides.pop("private_key_pem", _KEY_PAIR.private_pem),
        key_id=overrides.pop("key_id", _KEY_ID),
        ttl_seconds=overrides.pop("ttl", 900),
        issuer=overrides.pop("issuer", _ISSUER),
        token_type=overrides.pop("token_type", "console_access"),
    )


def test_no_auth_header_returns_401():
    with _client() as client:
        response = client.get("/api/console/me")
    assert response.status_code == 401


def test_empty_bearer_returns_401():
    with _client() as client:
        response = client.get("/api/console/me", headers={"Authorization": "Bearer "})
    assert response.status_code == 401


def test_basic_auth_returns_401():
    with _client() as client:
        response = client.get("/api/console/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401


def test_invalid_token_returns_401():
    with _client() as client:
        response = client.get(
            "/api/console/me",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
    assert response.status_code == 401


def test_valid_token_returns_200_and_user_id(monkeypatch):
    import base64

    monkeypatch.setenv("TEAM360_PASETO_PUBLIC_KEY_B64", base64.b64encode(_PUBLIC_KEYS_B64).decode("ascii"))
    monkeypatch.setenv("TEAM360_PASETO_KEY_ID", _KEY_ID)

    token = _valid_token(user_id="route-user")

    with _client() as client:
        response = client.get(
            "/api/console/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "route-user"
    assert data["subject"] == "user:route-user"
    assert data["token_type"] == "paseto_v4_public"


def test_valid_token_response_does_not_contain_access_token(monkeypatch):
    import base64

    monkeypatch.setenv("TEAM360_PASETO_PUBLIC_KEY_B64", base64.b64encode(_PUBLIC_KEYS_B64).decode("ascii"))
    monkeypatch.setenv("TEAM360_PASETO_KEY_ID", _KEY_ID)

    token = _valid_token()

    with _client() as client:
        response = client.get(
            "/api/console/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    data = response.json()
    assert "access_token" not in data
    assert "private" not in str(data).lower()
    assert "secret" not in str(data).lower()


def test_valid_token_response_does_not_contain_keys(monkeypatch):
    import base64

    monkeypatch.setenv("TEAM360_PASETO_PUBLIC_KEY_B64", base64.b64encode(_PUBLIC_KEYS_B64).decode("ascii"))
    monkeypatch.setenv("TEAM360_PASETO_KEY_ID", _KEY_ID)

    token = _valid_token()

    with _client() as client:
        response = client.get(
            "/api/console/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    data = response.json()
    assert "key" not in str(data).lower()
    assert "pem" not in str(data).lower()


def test_expired_token_returns_401(monkeypatch):
    import base64

    monkeypatch.setenv("TEAM360_PASETO_PUBLIC_KEY_B64", base64.b64encode(_PUBLIC_KEYS_B64).decode("ascii"))
    monkeypatch.setenv("TEAM360_PASETO_KEY_ID", _KEY_ID)

    token = _valid_token(ttl=-3600)

    with _client() as client:
        response = client.get(
            "/api/console/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 401


def test_wrong_token_type_returns_401(monkeypatch):
    import base64

    monkeypatch.setenv("TEAM360_PASETO_PUBLIC_KEY_B64", base64.b64encode(_PUBLIC_KEYS_B64).decode("ascii"))
    monkeypatch.setenv("TEAM360_PASETO_KEY_ID", _KEY_ID)

    token = _valid_token(token_type="embed_turn")

    with _client() as client:
        response = client.get(
            "/api/console/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 401
