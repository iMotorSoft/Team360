"""Deterministic first-response SLA domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class FirstResponseSLAStatus(StrEnum):
    PENDING = "PENDING"
    MET = "MET"
    BREACHED = "BREACHED"


@dataclass(frozen=True, slots=True)
class FirstResponseSLA:
    id: str
    routing_id: str
    request_id: str
    duration_seconds: int
    started_at: datetime
    due_at: datetime
    status: FirstResponseSLAStatus
    first_response_at: datetime | None
    met_at: datetime | None = None
    breached_at: datetime | None = None
    evaluated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SLAEvaluation:
    status: FirstResponseSLAStatus
    reconciled: bool = False


def sla_due_at(started_at: datetime, duration_seconds: int) -> datetime:
    if duration_seconds <= 0:
        raise ValueError("First-response SLA seconds must be positive.")
    return started_at + timedelta(seconds=duration_seconds)


def evaluate_first_response_sla(
    *,
    current_status: FirstResponseSLAStatus,
    due_at: datetime,
    first_response_at: datetime | None,
    now: datetime,
) -> SLAEvaluation:
    if first_response_at is not None:
        if first_response_at <= due_at:
            return SLAEvaluation(
                FirstResponseSLAStatus.MET,
                reconciled=current_status == FirstResponseSLAStatus.BREACHED,
            )
        return SLAEvaluation(FirstResponseSLAStatus.BREACHED)
    if current_status in {
        FirstResponseSLAStatus.MET,
        FirstResponseSLAStatus.BREACHED,
    }:
        return SLAEvaluation(current_status)
    if now > due_at:
        return SLAEvaluation(FirstResponseSLAStatus.BREACHED)
    return SLAEvaluation(FirstResponseSLAStatus.PENDING)
