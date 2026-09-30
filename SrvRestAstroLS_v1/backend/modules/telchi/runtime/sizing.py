"""Conservative runtime signal, not an LLM heuristic or auto-growth loop."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .resource_guard import ResourceAssessment


class SegmentSizingDecision(StrEnum):
    CONTINUE_SAME_SIZE = "CONTINUE_SAME_SIZE"
    REDUCE_NEXT_SEGMENT = "REDUCE_NEXT_SEGMENT"
    SPLIT_CURRENT_SEGMENT = "SPLIT_CURRENT_SEGMENT"
    PAUSE = "PAUSE"
    SAFE_ABORT = "SAFE_ABORT"


@dataclass(frozen=True)
class SegmentSizeAdvice:
    decision: SegmentSizingDecision
    reason: str


class SegmentSizingAdvisor:
    """Only emits reduce/pause/abort signals; it never grows a segment automatically."""

    def advise(self, assessment: ResourceAssessment, *, split_requested: bool = False) -> SegmentSizeAdvice:
        if assessment.critical_reasons:
            return SegmentSizeAdvice(SegmentSizingDecision.SAFE_ABORT, ",".join(assessment.critical_reasons))
        if split_requested:
            return SegmentSizeAdvice(SegmentSizingDecision.SPLIT_CURRENT_SEGMENT, "handler requested bounded split")
        if assessment.warnings:
            return SegmentSizeAdvice(SegmentSizingDecision.REDUCE_NEXT_SEGMENT, ",".join(assessment.warnings))
        return SegmentSizeAdvice(SegmentSizingDecision.CONTINUE_SAME_SIZE, "no pressure signal")
