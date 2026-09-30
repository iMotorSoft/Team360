"""Bounded coverage tracking with explicit gap and overlap detection."""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import CoverageEntry, CoverageStatus, SegmentRange


class CoverageConflict(ValueError):
    pass


@dataclass(frozen=True)
class CoverageReport:
    required: SegmentRange
    contiguous_trusted_to: int
    gaps: tuple[SegmentRange, ...]
    overlaps: tuple[tuple[str, str], ...]

    @property
    def complete(self) -> bool:
        return self.contiguous_trusted_to >= self.required.end and not self.gaps and not self.overlaps


class CoverageTracker:
    def __init__(self) -> None:
        self.entries: dict[str, CoverageEntry] = {}

    def add(self, entry: CoverageEntry) -> None:
        existing = self.entries.get(entry.segment_id)
        if existing is not None:
            if existing == entry:
                return
            raise CoverageConflict(f"segment {entry.segment_id} already has different coverage")
        for other in self.entries.values():
            if other.segment_id == entry.segment_id or other.status is CoverageStatus.SPLIT:
                continue
            if other.scope.overlaps(entry.scope):
                raise CoverageConflict(f"overlap: {other.segment_id} and {entry.segment_id}")
        self.entries[entry.segment_id] = entry

    def set_status(self, segment_id: str, status: CoverageStatus) -> None:
        current = self.entries[segment_id]
        self.entries[segment_id] = CoverageEntry(current.segment_id, current.scope, status, current.parent_segment_id)

    def report(self, required: SegmentRange) -> CoverageReport:
        relevant = [e for e in self.entries.values() if e.scope.start < required.end and e.scope.end > required.start and e.status is not CoverageStatus.SPLIT]
        relevant.sort(key=lambda e: e.scope.start)
        overlaps: list[tuple[str, str]] = []
        gaps: list[SegmentRange] = []
        cursor = required.start
        trusted_cursor = required.start
        previous = None
        for entry in relevant:
            start = max(required.start, entry.scope.start)
            end = min(required.end, entry.scope.end)
            if previous is not None and start < previous[0]:
                overlaps.append((previous[1], entry.segment_id))
            if start > cursor:
                gaps.append(SegmentRange(cursor, start))
            cursor = max(cursor, end)
            if entry.status is CoverageStatus.TRUSTED and start <= trusted_cursor:
                if start > trusted_cursor:
                    break
                trusted_cursor = max(trusted_cursor, end)
            elif start <= trusted_cursor:
                # A failed/pending range stops contiguous trust at its beginning.
                break
            previous = (end, entry.segment_id)
        if cursor < required.end:
            gaps.append(SegmentRange(cursor, required.end))
        return CoverageReport(required, trusted_cursor, tuple(gaps), tuple(overlaps))

    def contiguous_trusted(self, required: SegmentRange) -> bool:
        report = self.report(required)
        return report.contiguous_trusted_to >= required.end and not report.overlaps

    def snapshot(self) -> list[CoverageEntry]:
        return list(self.entries.values())
