"""Security-boundary regressions for the experimental Console bootstrap."""

from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest

import routes.console_bootstrap as bootstrap_route
from ls_iMotorSoft_Srv01 import create_app
from modules.security.paseto_tokens import PasetoKeyPair, verify_paseto_v4_public
from test_console_bootstrap_service import _service


class _FixturePool:
    @asynccontextmanager
    async def connection(self):
        yield object()


def _request(payload: dict[str, str]):
    async def run():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://fixture") as client:
            return await client.post("/api/console/bootstrap", json=payload)

    return asyncio.run(run())


@pytest.mark.parametrize("environment", ["production", "staging", "", "unknown"])
def test_bootstrap_rejects_non_dev_environments_before_identity_lookup(monkeypatch, environment):
    monkeypatch.setenv("TEAM360_ENV", environment)
    service = _service(permissions=["package.view"], features=["events.basic"])
    with patch.object(bootstrap_route, "_SERVICE", service), patch.object(
        bootstrap_route, "get_pool", side_effect=AssertionError("DB lookup must not run")
    ):
        response = _request({"workspace_id": "workspace-1", "user_id": "user-1"})
    assert response.status_code == 404


def test_bootstrap_rejects_absent_environment_before_identity_lookup(monkeypatch):
    monkeypatch.delenv("TEAM360_ENV", raising=False)
    with patch.object(
        bootstrap_route, "get_pool", side_effect=AssertionError("DB lookup must not run")
    ):
        response = _request({"workspace_id": "workspace-1", "user_id": "user-1"})
    assert response.status_code == 404


@pytest.mark.parametrize("environment", ["dev", "development"])
def test_bootstrap_dev_flow_preserves_restricted_token_contract(monkeypatch, environment):
    pair = PasetoKeyPair.generate("bootstrap-boundary-test")
    monkeypatch.setenv("TEAM360_ENV", environment)
    monkeypatch.setenv("TEAM360_PASETO_ENABLED", "true")
    monkeypatch.setenv("TEAM360_PASETO_KEY_ID", pair.key_id)
    monkeypatch.setenv(
        "TEAM360_PASETO_PRIVATE_KEY_B64",
        base64.b64encode(pair.private_pem.encode()).decode(),
    )
    monkeypatch.setenv(
        "TEAM360_PASETO_PUBLIC_KEY_B64",
        base64.b64encode(pair.public_pem.encode()).decode(),
    )
    monkeypatch.setenv("TEAM360_CONSOLE_PASETO_TTL_SECONDS", "300")

    service = _service(permissions=["package.view"], features=["events.basic"])
    with patch.object(bootstrap_route, "_SERVICE", service), patch.object(
        bootstrap_route, "get_pool", return_value=_FixturePool()
    ):
        response = _request({"workspace_id": "workspace-1", "user_id": "user-1"})

    assert response.status_code == 201
    body = response.json()
    assert body["capabilities"] == ["can_view_alerts", "can_view_services"]
    assert body["expires_in"] == 300
    claims = verify_paseto_v4_public(
        body["access_token"],
        public_keys_by_id={pair.key_id: pair.public_pem},
        issuer="team360",
        expected_type="console_access",
    )
    assert claims["user_id"] == "user-1"
    assert claims["sub"] == "user:user-1"
    assert claims["exp"] - claims["iat"] == 300
