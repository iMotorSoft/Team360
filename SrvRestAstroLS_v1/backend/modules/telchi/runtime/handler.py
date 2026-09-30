"""Domain-agnostic handler protocol and cooperative phase context."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Any, Iterable, Protocol

from .contracts import ReconciliationResult, Segment, ValidationResult
from .resource_guard import ResourceGuard


@dataclass
class HandlerContext:
    segment: Segment
    resource_guard: ResourceGuard
    metadata: dict[str, Any]
    cancellation: Event | None = None

    def checkpoint(self) -> None:
        if self.cancellation is not None and self.cancellation.is_set():
            from .resource_guard import SafeAbort
            raise SafeAbort("SEGMENT_TIMEOUT")
        self.resource_guard.checkpoint()
        self.resource_guard.ensure_timeout(self.segment.timeout_seconds)

    def consume_bytes(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("byte consumption cannot be negative")
        total = self.metadata.get("bytes_processed", 0) + amount
        if self.segment.byte_budget is not None and total > self.segment.byte_budget:
            from .resource_guard import SafeAbort
            raise SafeAbort("BYTE_BUDGET_EXCEEDED")
        self.metadata["bytes_processed"] = total


class SegmentHandler(Protocol):
    """Future domain handlers implement bounded, separately testable phases."""

    def prepare(self, segment: Segment, context: HandlerContext) -> None: ...
    def extract(self, segment: Segment, context: HandlerContext) -> Iterable[Any]: ...
    def transform(self, rows: Iterable[Any], context: HandlerContext) -> Iterable[Any]: ...
    def validate(self, candidate: Any, context: HandlerContext) -> ValidationResult: ...
    def reconcile(self, candidate: Any, context: HandlerContext) -> ReconciliationResult: ...
    def build_candidate(self, rows: Iterable[Any], context: HandlerContext) -> Any: ...
    def cleanup(self, segment: Segment, context: HandlerContext) -> None: ...
