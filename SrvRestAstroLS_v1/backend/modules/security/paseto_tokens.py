from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from time import time
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pyseto import Key as PasetoKey
from pyseto import decode as paseto_decode
from pyseto import encode as paseto_encode


@dataclass(frozen=True)
class PasetoKeyPair:
    key_id: str
    private_pem: str
    public_pem: str

    @classmethod
    def generate(cls, key_id: str) -> PasetoKeyPair:
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return cls(key_id=key_id, private_pem=private_pem, public_pem=public_pem)


def _build_paseto_private_key(private_pem: str) -> PasetoKey:
    return PasetoKey.new(version=4, purpose="public", key=private_pem.encode("utf-8"))


def _build_paseto_public_key(public_pem: str) -> PasetoKey:
    return PasetoKey.new(version=4, purpose="public", key=public_pem.encode("utf-8"))


def issue_paseto_v4_public(
    claims: dict[str, Any],
    *,
    private_key_pem: str,
    key_id: str,
    ttl_seconds: int,
    issuer: str,
    token_type: str,
) -> str:
    now = int(time())
    payload = {
        **claims,
        "typ": token_type,
        "iss": issuer,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    footer = json.dumps({"kid": key_id}, separators=(",", ":"))
    pkey = _build_paseto_private_key(private_key_pem)
    token = paseto_encode(pkey, json.dumps(payload, separators=(",", ":")).encode("utf-8"), footer=footer.encode("utf-8"))
    return token.decode("utf-8")


def _extract_footer(token_str: str) -> dict[str, Any]:
    parts = token_str.split(".")
    if len(parts) != 4:
        raise PasetoVerificationError("Malformed PASETO: expected 4 dot-separated parts")
    if parts[1] != "public":
        raise PasetoVerificationError(f"Expected public purpose, got {parts[1]!r}")

    footer_b64 = parts[3]
    try:
        padded = footer_b64 + "=" * (-len(footer_b64) % 4)
        footer_bytes = base64.urlsafe_b64decode(padded)
    except Exception as exc:
        raise PasetoVerificationError(f"Invalid footer base64: {exc}") from exc

    try:
        return json.loads(footer_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PasetoVerificationError(f"Invalid footer JSON: {exc}") from exc


def verify_paseto_v4_public(
    token: str,
    *,
    public_keys_by_id: dict[str, str],
    issuer: str,
    expected_type: str,
    leeway_seconds: int = 30,
) -> dict[str, Any]:
    footer_data = _extract_footer(token)

    key_id = footer_data.get("kid", "")
    if not key_id:
        raise PasetoVerificationError("Missing kid in token footer")
    if key_id not in public_keys_by_id:
        raise PasetoVerificationError(f"Unknown key_id: {key_id}")

    public_pem = public_keys_by_id[key_id]
    pkey = _build_paseto_public_key(public_pem)
    token_bytes = token.encode("utf-8")

    try:
        decoded = paseto_decode(pkey, token_bytes)
    except Exception as exc:
        raise PasetoVerificationError(f"Signature verification failed: {exc}") from exc

    try:
        payload = json.loads(decoded.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PasetoVerificationError(f"Invalid payload JSON: {exc}") from exc

    now = int(time())

    token_type = payload.get("typ")
    if token_type != expected_type:
        raise PasetoVerificationError(
            f"Expected typ={expected_type!r}, got {token_type!r}"
        )

    token_issuer = payload.get("iss")
    if token_issuer != issuer:
        raise PasetoVerificationError(
            f"Expected iss={issuer!r}, got {token_issuer!r}"
        )

    exp = payload.get("exp")
    if exp is None:
        raise PasetoVerificationError("Missing exp claim")
    if now > int(exp) + leeway_seconds:
        raise PasetoVerificationError("Token expired")

    iat = payload.get("iat")
    if iat is None:
        raise PasetoVerificationError("Missing iat claim")

    jti = payload.get("jti")
    if jti is None:
        raise PasetoVerificationError("Missing jti claim")

    payload.setdefault("_key_id", key_id)
    return payload


class PasetoVerificationError(Exception):
    pass
