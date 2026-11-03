"""Operation-local reuse of deterministic projections of verified file bytes.

Never a persisted accreditation or a path/mtime cache. Every lookup hashes the
actual file. The outer canonical validation owns and discards the entire scope,
including on failure; a subsequent read must independently verify its bytes.
"""
from contextvars import ContextVar
from functools import wraps
import hashlib

_ACTIVE = ContextVar('telchi_file_verification_scope', default=None)


def verification_scope(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _ACTIVE.get() is not None:
            return function(*args, **kwargs)
        token = _ACTIVE.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _ACTIVE.reset(token)
    return wrapped


def verified_projection(path, contract, build):
    cache = _ACTIVE.get()
    if cache is None:
        return build()
    if path.is_symlink():
        raise ValueError('SYMLINK_IN_VERIFIED_PROJECTION')
    fingerprint = hashlib.sha256(path.read_bytes()).digest()
    key = (contract, fingerprint)
    if key not in cache:
        value = build()
        if hashlib.sha256(path.read_bytes()).digest() != fingerprint:
            raise ValueError('BYTES_CHANGED_DURING_VERIFIED_PROJECTION')
        cache[key] = value
    return cache[key]
