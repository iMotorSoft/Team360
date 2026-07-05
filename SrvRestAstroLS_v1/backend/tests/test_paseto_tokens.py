from __future__ import annotations

import pytest

from modules.security.paseto_tokens import (
    PasetoKeyPair,
    PasetoVerificationError,
    issue_paseto_v4_public,
    verify_paseto_v4_public,
)

ISSUER = "team360"
TOKEN_TYPE = "embed_turn"
TTL = 300

_DEV_KEY_ID = "local-dev-key-1"


@pytest.fixture
def dev_key_pair() -> PasetoKeyPair:
    return PasetoKeyPair.generate(_DEV_KEY_ID)


@pytest.fixture
def public_keys_by_id(dev_key_pair: PasetoKeyPair) -> dict[str, str]:
    return {dev_key_pair.key_id: dev_key_pair.public_pem}


def _issue(claims: dict, *, private_key_pem: str, ttl: int = TTL) -> str:
    return issue_paseto_v4_public(
        claims,
        private_key_pem=private_key_pem,
        key_id=_DEV_KEY_ID,
        ttl_seconds=ttl,
        issuer=ISSUER,
        token_type=TOKEN_TYPE,
    )


def _verify(token: str, public_keys: dict[str, str]) -> dict:
    return verify_paseto_v4_public(
        token,
        public_keys_by_id=public_keys,
        issuer=ISSUER,
        expected_type=TOKEN_TYPE,
    )


class TestPasetoV4Public:
    def test_issue_and_verify_valid_token(self, dev_key_pair: PasetoKeyPair, public_keys_by_id: dict[str, str]):
        token = _issue({"sub": "client:local_embed_demo"}, private_key_pem=dev_key_pair.private_pem)
        assert isinstance(token, str)
        assert token.startswith("v4.public.")

        payload = _verify(token, public_keys_by_id)
        assert payload["sub"] == "client:local_embed_demo"
        assert payload["typ"] == TOKEN_TYPE
        assert payload["iss"] == ISSUER
        assert isinstance(payload["iat"], int)
        assert isinstance(payload["exp"], int)
        assert isinstance(payload["jti"], str)
        assert len(payload["jti"]) > 0
        assert payload["_key_id"] == _DEV_KEY_ID

    def test_fails_with_expired_token(self, dev_key_pair: PasetoKeyPair, public_keys_by_id: dict[str, str]):
        token = _issue({"sub": "test"}, private_key_pem=dev_key_pair.private_pem, ttl=-3600)
        with pytest.raises(PasetoVerificationError, match="Token expired"):
            _verify(token, public_keys_by_id)

    def test_fails_with_incorrect_issuer(self, dev_key_pair: PasetoKeyPair, public_keys_by_id: dict[str, str]):
        token = issue_paseto_v4_public(
            {"sub": "test"},
            private_key_pem=dev_key_pair.private_pem,
            key_id=_DEV_KEY_ID,
            ttl_seconds=TTL,
            issuer="wrong-issuer",
            token_type=TOKEN_TYPE,
        )
        with pytest.raises(PasetoVerificationError, match="Expected iss"):
            verify_paseto_v4_public(
                token,
                public_keys_by_id=public_keys_by_id,
                issuer=ISSUER,
                expected_type=TOKEN_TYPE,
            )

    def test_fails_with_incorrect_type(self, dev_key_pair: PasetoKeyPair, public_keys_by_id: dict[str, str]):
        token = issue_paseto_v4_public(
            {"sub": "test"},
            private_key_pem=dev_key_pair.private_pem,
            key_id=_DEV_KEY_ID,
            ttl_seconds=TTL,
            issuer=ISSUER,
            token_type="wrong_type",
        )
        with pytest.raises(PasetoVerificationError, match="Expected typ"):
            _verify(token, public_keys_by_id)

    def test_fails_with_unknown_key_id(self, dev_key_pair: PasetoKeyPair):
        token = _issue({"sub": "test"}, private_key_pem=dev_key_pair.private_pem)
        wrong_keys = {"other-key": dev_key_pair.public_pem}
        with pytest.raises(PasetoVerificationError, match="Unknown key_id"):
            _verify(token, wrong_keys)

    def test_fails_with_malformed_token(self, public_keys_by_id: dict[str, str]):
        with pytest.raises(PasetoVerificationError, match="Malformed PASETO"):
            _verify("not-a-valid-token", public_keys_by_id)

    def test_fails_with_tampered_token(self, dev_key_pair: PasetoKeyPair, public_keys_by_id: dict[str, str]):
        token = _issue({"sub": "test"}, private_key_pem=dev_key_pair.private_pem)
        parts = token.split(".")
        assert len(parts) == 4
        tampered = f"{parts[0]}.{parts[1]}.tampered.{parts[3]}"
        with pytest.raises(PasetoVerificationError, match="Signature verification failed"):
            _verify(tampered, public_keys_by_id)

    def test_preserves_custom_claims(self, dev_key_pair: PasetoKeyPair, public_keys_by_id: dict[str, str]):
        claims = {
            "sub": "client:demo",
            "client_id": "demo_client",
            "origin": "https://cliente.com",
            "session_id": "sess_001",
        }
        token = _issue(claims, private_key_pem=dev_key_pair.private_pem)
        payload = _verify(token, public_keys_by_id)
        assert payload["client_id"] == "demo_client"
        assert payload["origin"] == "https://cliente.com"
        assert payload["session_id"] == "sess_001"

    def test_format_is_paseto_not_jwt(self, dev_key_pair: PasetoKeyPair):
        token = _issue({"sub": "test"}, private_key_pem=dev_key_pair.private_pem)
        assert token.startswith("v4.public.")
        assert not token.startswith("eyJ")

    def test_keys_are_ed25519_not_hmac(self, dev_key_pair: PasetoKeyPair):
        assert "PRIVATE KEY" in dev_key_pair.private_pem
        assert "PUBLIC KEY" in dev_key_pair.public_pem
        assert "hmac" not in dev_key_pair.private_pem.lower()

    def test_kid_in_footer_selects_correct_key(self, dev_key_pair: PasetoKeyPair):
        kp2 = PasetoKeyPair.generate("local-dev-key-2")
        token = _issue({"sub": "client:from-k1"}, private_key_pem=dev_key_pair.private_pem)
        token2 = issue_paseto_v4_public(
            {"sub": "client:from-k2"},
            private_key_pem=kp2.private_pem,
            key_id="local-dev-key-2",
            ttl_seconds=TTL,
            issuer=ISSUER,
            token_type=TOKEN_TYPE,
        )

        both_keys = {
            _DEV_KEY_ID: dev_key_pair.public_pem,
            "local-dev-key-2": kp2.public_pem,
        }

        p1 = _verify(token, both_keys)
        assert p1["sub"] == "client:from-k1"
        assert p1["_key_id"] == _DEV_KEY_ID

        p2 = _verify(token2, both_keys)
        assert p2["sub"] == "client:from-k2"
        assert p2["_key_id"] == "local-dev-key-2"

    def test_iat_and_jti_included_by_default(self, dev_key_pair: PasetoKeyPair, public_keys_by_id: dict[str, str]):
        token = _issue({"sub": "test"}, private_key_pem=dev_key_pair.private_pem)
        payload = _verify(token, public_keys_by_id)
        assert "iat" in payload
        assert "jti" in payload
