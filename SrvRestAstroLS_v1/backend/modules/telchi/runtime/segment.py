"""Range helpers and conservative segment splitting foundation."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from .contracts import CoverageEntry, CoverageStatus, Segment, SegmentRange, SegmentStatus


def half_open_ranges(start: int, end: int, size: int) -> tuple[SegmentRange, ...]:
    if end <= start or size <= 0:
        raise ValueError("invalid bounded range or size")
    return tuple(SegmentRange(cursor, min(cursor + size, end)) for cursor in range(start, end, size))


def split_segment(segment: Segment, split_at: int, *, child_ids: tuple[str, str] | None = None) -> tuple[Segment, Segment]:
    if segment.status not in {SegmentStatus.PLANNED, SegmentStatus.READY, SegmentStatus.SAFE_ABORTED}:
        raise ValueError("only unstarted or safely aborted segments can be split")
    left_range, right_range = segment.scope.split(split_at)
    ids = child_ids or (f"{segment.segment_id}-a-{uuid4().hex[:8]}", f"{segment.segment_id}-b-{uuid4().hex[:8]}")
    if len(ids) != 2 or ids[0] == ids[1]:
        raise ValueError("two distinct child ids are required")
    segment.transition(SegmentStatus.SPLIT)
    common = {
        "job_id": segment.job_id,
        "domain": segment.domain,
        "operation": segment.operation,
        "ingestion_mode": segment.ingestion_mode,
        "segment_strategy": segment.segment_strategy,
        "parent_segment_id": segment.segment_id,
        "row_budget": segment.row_budget,
        "byte_budget": segment.byte_budget,
        "timeout_seconds": segment.timeout_seconds,
        "resource_profile": segment.resource_profile,
        "source_identity": segment.source_identity,
        "reference_version": segment.reference_version,
        "transformation_version": segment.transformation_version,
    }
    return (
        Segment(segment_id=ids[0], scope=left_range, **common),
        Segment(segment_id=ids[1], scope=right_range, **common),
    )


def split_coverage(parent: Segment, children: tuple[Segment, Segment]) -> tuple[CoverageEntry, ...]:
    if children[0].scope.end != children[1].scope.start or children[0].scope.start != parent.scope.start or children[1].scope.end != parent.scope.end:
        raise ValueError("children must exactly cover parent without overlap or gap")
    if any(child.parent_segment_id != parent.segment_id for child in children):
        raise ValueError("child lineage is not preserved")
    return tuple(CoverageEntry(child.segment_id, child.scope, CoverageStatus.PENDING, parent.segment_id) for child in children)
