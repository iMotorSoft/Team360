"""Structured, dependency-free execution observability."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass
class SegmentMetric:
    job_id: str
    segment_id: str
    attempt: int
    status: str
    duration_ms: int
    rows_processed: int = 0
    bytes_processed: int = 0
    resource_warnings: list[str] = field(default_factory=list)
    safe_abort_reason: str | None = None
    max_observed_memory_percent: float | None = None
    max_observed_swap_percent: float | None = None
    disk_pressure: bool = False
    timeout: bool = False
    split_requested: bool = False


class ObservabilitySink(Protocol):
    def emit(self, metric: SegmentMetric) -> None: ...


class InMemoryObservability:
    def __init__(self) -> None:
        self.metrics: list[SegmentMetric] = []

    def emit(self, metric: SegmentMetric) -> None:
        self.metrics.append(metric)


class StructuredLogger:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("team360.telchi.segment_runtime")

    def emit(self, metric: SegmentMetric) -> None:
        self.logger.info(json.dumps(asdict(metric), sort_keys=True, default=str))
