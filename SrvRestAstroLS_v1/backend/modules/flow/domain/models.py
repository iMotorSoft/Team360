"""Validated internal contracts for Flow intake interpretation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CandidateRequest:
    description: str
    tentative_category: str | None
    location_text: str | None
    missing_data: tuple[str, ...] = ()
    context_notes: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("Candidate request description cannot be empty.")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Candidate request confidence must be between 0 and 1.")
        object.__setattr__(self, "missing_data", tuple(self.missing_data))

    def as_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "tentative_category": self.tentative_category,
            "location_text": self.location_text,
            "missing_data": list(self.missing_data),
            "context_notes": self.context_notes,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class InitialInterpretation:
    requests: tuple[CandidateRequest, ...]
    clarification_question: str | None = None
    provider: str = "unknown"
    model: str = "unknown"
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ReplyInterpretation:
    action: str
    requests: tuple[CandidateRequest, ...] = ()
    clarification_question: str | None = None
    provider: str = "unknown"
    model: str = "unknown"
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None

    def __post_init__(self) -> None:
        if self.action not in {"confirm_all", "correction", "reinterpret", "ambiguous"}:
            raise ValueError(f"Unsupported reply action: {self.action}")
        if self.action in {"correction", "reinterpret"} and not self.requests:
            raise ValueError(f"Reply action {self.action} requires the full revised request list.")

