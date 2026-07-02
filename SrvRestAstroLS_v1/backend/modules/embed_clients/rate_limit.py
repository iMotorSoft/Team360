from __future__ import annotations

import hashlib
import os
from collections import deque
from dataclasses import dataclass
from time import time


DEFAULT_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS = 20
DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_KEYS = 10_000


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class EmbedAuthRateLimitSettings:
    window_seconds: int = DEFAULT_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS
    max_requests: int = DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS
    max_keys: int = DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_KEYS


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    remaining_requests: int = 0


def get_embed_auth_rate_limit_settings() -> EmbedAuthRateLimitSettings:
    return EmbedAuthRateLimitSettings(
        window_seconds=_positive_int_from_env(
            "TEAM360_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS",
            DEFAULT_EMBED_AUTH_RATE_LIMIT_WINDOW_SECONDS,
        ),
        max_requests=_positive_int_from_env(
            "TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS",
            DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_REQUESTS,
        ),
        max_keys=_positive_int_from_env(
            "TEAM360_EMBED_AUTH_RATE_LIMIT_MAX_KEYS",
            DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_KEYS,
        ),
    )


def build_embed_auth_rate_limit_key(
    client_id: str | None,
    origin: str | None,
    remote_ip: str | None,
) -> str:
    normalized_client_id = (client_id or "").strip().lower() or "<missing-client>"
    normalized_origin = (origin or "").strip().lower() or "<missing-origin>"
    normalized_remote_ip = (remote_ip or "").strip().lower() or "<missing-ip>"
    raw_key = f"{normalized_client_id}|{normalized_origin}|{normalized_remote_ip}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class InMemoryRateLimiter:
    def __init__(
        self,
        *,
        window_seconds: int,
        max_requests: int,
        max_keys: int = DEFAULT_EMBED_AUTH_RATE_LIMIT_MAX_KEYS,
        time_source=time,
    ) -> None:
        self._window_seconds = max(1, int(window_seconds))
        self._max_requests = max(1, int(max_requests))
        self._max_keys = max(1, int(max_keys))
        self._time_source = time_source
        self._store: dict[str, deque[float]] = {}

    def allow(self, key: str, *, now: float | None = None) -> RateLimitDecision:
        current_time = float(self._time_source() if now is None else now)
        self._prune_expired(current_time)

        bucket = self._store.get(key)
        if bucket is None:
            self._evict_if_needed(current_time)
            bucket = deque()
            self._store[key] = bucket

        cutoff = current_time - self._window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= self._max_requests:
            retry_after = max(1, int(bucket[0] + self._window_seconds - current_time))
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=retry_after,
                remaining_requests=0,
            )

        bucket.append(current_time)
        return RateLimitDecision(
            allowed=True,
            retry_after_seconds=0,
            remaining_requests=max(0, self._max_requests - len(bucket)),
        )

    def _prune_expired(self, current_time: float) -> None:
        cutoff = current_time - self._window_seconds
        expired_keys: list[str] = []
        for key, bucket in self._store.items():
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                expired_keys.append(key)
        for key in expired_keys:
            self._store.pop(key, None)

    def _evict_if_needed(self, current_time: float) -> None:
        if len(self._store) < self._max_keys:
            return

        oldest_key = min(
            self._store,
            key=lambda candidate: self._store[candidate][0] if self._store[candidate] else current_time,
        )
        self._store.pop(oldest_key, None)
