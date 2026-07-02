from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


_LOGGER = logging.getLogger(__name__)


def _hash_value(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _normalize_request_id(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    return normalized[:128]


@dataclass(frozen=True)
class EmbedAuthAuditEvent:
    timestamp_utc: str
    event_type: str
    reason_code: str
    status_code: int
    client_id_hash: str | None
    origin_hash: str | None
    remote_ip_hash: str | None
    request_id: str | None
    user_agent_hash: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "event_type": self.event_type,
            "reason_code": self.reason_code,
            "status_code": self.status_code,
            "client_id_hash": self.client_id_hash,
            "origin_hash": self.origin_hash,
            "remote_ip_hash": self.remote_ip_hash,
            "request_id": self.request_id,
            "user_agent_hash": self.user_agent_hash,
        }


class EmbedAuthAuditor(Protocol):
    def record(self, event: EmbedAuthAuditEvent) -> None:
        ...


class LoggingEmbedAuthAuditor:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _LOGGER

    def record(self, event: EmbedAuthAuditEvent) -> None:
        self._logger.info(
            "embed_auth_audit %s",
            json.dumps(event.as_dict(), sort_keys=True, separators=(",", ":")),
        )


def build_embed_auth_audit_event(
    *,
    event_type: str,
    reason_code: str,
    status_code: int,
    client_id: str | None,
    origin: str | None,
    remote_ip: str | None,
    request_id: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> EmbedAuthAuditEvent:
    occurred_at = now or datetime.now(timezone.utc)
    return EmbedAuthAuditEvent(
        timestamp_utc=occurred_at.isoformat(),
        event_type=event_type,
        reason_code=reason_code,
        status_code=status_code,
        client_id_hash=_hash_value(client_id),
        origin_hash=_hash_value(origin),
        remote_ip_hash=_hash_value(remote_ip),
        request_id=_normalize_request_id(request_id),
        user_agent_hash=_hash_value(user_agent),
    )
