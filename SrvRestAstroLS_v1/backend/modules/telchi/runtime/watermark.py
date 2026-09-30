"""Detected/processed/validated/trusted watermark foundation."""
from __future__ import annotations

from .contracts import Watermark
from .coverage import CoverageTracker
from .contracts import SegmentRange
from .stores import WatermarkStore


class WatermarkSafetyError(ValueError):
    pass


class WatermarkTracker:
    def __init__(self, store: WatermarkStore, coverage: CoverageTracker) -> None:
        self.store = store
        self.coverage = coverage

    def record_detected(self, domain: str, value: int) -> Watermark:
        watermark = self.store.get_watermark(domain) or Watermark(domain)
        watermark.detected = max(watermark.detected or value, value)
        self.store.save_watermark(watermark)
        return watermark

    def record_processed(self, domain: str, value: int) -> Watermark:
        watermark = self.store.get_watermark(domain) or Watermark(domain)
        if watermark.detected is not None and value > watermark.detected:
            raise WatermarkSafetyError("processed watermark cannot exceed detected watermark")
        watermark.processed = max(watermark.processed or value, value)
        self.store.save_watermark(watermark)
        return watermark

    def record_validated(self, domain: str, value: int) -> Watermark:
        watermark = self.store.get_watermark(domain) or Watermark(domain)
        if watermark.processed is not None and value > watermark.processed:
            raise WatermarkSafetyError("validated watermark cannot exceed processed watermark")
        watermark.validated = max(watermark.validated or value, value)
        self.store.save_watermark(watermark)
        return watermark

    def advance_trusted(self, domain: str, required: SegmentRange, value: int) -> Watermark:
        if value > required.end:
            raise WatermarkSafetyError("trusted watermark cannot exceed requested coverage")
        if not self.coverage.contiguous_trusted(SegmentRange(required.start, value)):
            raise WatermarkSafetyError("trusted watermark cannot skip a coverage gap")
        watermark = self.store.get_watermark(domain) or Watermark(domain)
        if watermark.validated is not None and value > watermark.validated:
            raise WatermarkSafetyError("trusted watermark cannot exceed validated watermark")
        watermark.published = max(watermark.published or value, value)
        self.store.save_watermark(watermark)
        return watermark
