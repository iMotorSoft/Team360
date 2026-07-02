"""HMAC-SHA256 signing and verification for embed client requests.

Canonical string: ``client_id.timestamp.session_id.message``

Each part is the raw string value; the separator is a single dot (``.``).
If any part contains a dot, the canonicalisation is still unambiguous because the
timestamp is a fixed integer and the other fields are compared by the receiver.

Security notes:
    - Always use ``hmac.compare_digest`` for constant-time comparison.
    - Never log the secret or the computed signature.
    - The signature is sent in the ``X-T360-Signature`` header as ``sha256=<hex>``.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac


def build_canonical_string(
    client_id: str,
    timestamp: int,
    session_id: str,
    message: str,
) -> str:
    """Build the canonical string that is signed by the HMAC.

    Format: ``client_id.timestamp.session_id.message``
    """
    return f"{client_id}.{timestamp}.{session_id}.{message}"


def sign(canonical: str, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest for the given canonical string."""
    return _hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify(canonical: str, secret: str, expected_signature: str) -> bool:
    """Constant-time comparison of computed vs expected HMAC hex digest.

    The expected signature should be the raw hex string (64 chars for SHA-256).
    """
    computed = sign(canonical, secret)
    return _hmac.compare_digest(computed, expected_signature)
