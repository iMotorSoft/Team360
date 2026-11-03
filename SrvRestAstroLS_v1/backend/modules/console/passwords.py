"""Versioned scrypt password encoding; no plaintext or secrets in repr/logs."""
import base64
import hashlib
import hmac
import secrets

N, R, P = 131072, 8, 1  # OWASP scrypt minimum; ~128 MiB per sequential operation.
MAX_BYTES = 1024


def validate_password(password: str) -> None:
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError('password_length')
    if len(password.encode('utf-8')) > MAX_BYTES:
        raise ValueError('password_length')


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=N, r=R, p=P,
                          dklen=32, maxmem=256 * 1024 * 1024)


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt)
    return '$'.join(('scrypt', str(N), str(R), str(P),
                     base64.b64encode(salt).decode(), base64.b64encode(digest).decode()))


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or len(password) > 256 or len(password.encode('utf-8')) > MAX_BYTES:
        return False
    try:
        algorithm, n, r, p, salt64, digest64 = encoded.split('$')
        # Never accept attacker-controlled KDF work factors or unbounded allocation.
        if (algorithm, n, r, p) != ('scrypt', str(N), str(R), str(P)):
            return False
        salt = base64.b64decode(salt64, validate=True)
        digest = base64.b64decode(digest64, validate=True)
        if len(salt) != 16 or len(digest) != 32:
            return False
        return hmac.compare_digest(_derive(password, salt), digest)
    except (ValueError, TypeError):
        return False


# Fixed non-secret dummy verifier, same KDF cost for unknown/disabled users.
DUMMY_HASH = 'scrypt$131072$8$1$' + base64.b64encode(bytes(16)).decode() + '$' + base64.b64encode(bytes(32)).decode()
