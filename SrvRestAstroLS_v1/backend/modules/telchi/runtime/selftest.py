"""Opt-in bounded local runtime self-test; never runs on backend startup."""
from __future__ import annotations

import argparse
import json

from .contracts import Job, JobType, ReconciliationResult, Segment, SegmentRange, ValidationResult
from .executor import SegmentExecutor
from .handler import HandlerContext
from .resource_guard import ResourceGuard, ResourceMetrics, ResourcePolicy


class BoundedSyntheticHandler:
    def __init__(self, row_count: int) -> None:
        self.row_count = row_count

    def prepare(self, segment: Segment, context: HandlerContext) -> None:
        return None

    def extract(self, segment: Segment, context: HandlerContext):
        return (value for value in range(segment.scope.start, segment.scope.end))

    def transform(self, rows, context: HandlerContext):
        return (value * 2 for value in rows)

    def build_candidate(self, rows, context: HandlerContext):
        count = 0
        checksum = 0
        for value in rows:
            count += 1
            checksum += value
        return {"content_identity": f"synthetic:{count}:{checksum}", "count": count}

    def validate(self, candidate, context: HandlerContext) -> ValidationResult:
        return ValidationResult(candidate["count"] == self.row_count, "bounded count")

    def reconcile(self, candidate, context: HandlerContext) -> ReconciliationResult:
        return ReconciliationResult(True)

    def cleanup(self, segment: Segment, context: HandlerContext) -> None:
        return None


def run(row_count: int) -> dict[str, object]:
    metrics = ResourceMetrics(8 * 1024**3, 20, 0, 0.1, 20 * 1024**3, 20 * 1024**3)
    policy = ResourcePolicy(min_available_memory_bytes=1024, min_disk_free_bytes=1024, min_temp_free_bytes=1024)
    guard = ResourceGuard(policy, metrics_provider=lambda: metrics)
    executor = SegmentExecutor(resource_guard=guard)
    job = Job("selftest-job", JobType.INITIAL_INGESTION, "synthetic", "LOCAL_SYNTHETIC")
    segment = Segment("selftest-segment", job.job_id, "synthetic", "SELFTEST", "LOCAL_SYNTHETIC", "BOUNDED_RANGE", SegmentRange(0, row_count), timeout_seconds=5, source_identity="selftest", reference_version="v1", transformation_version="v1")
    result = executor.execute(job, segment, BoundedSyntheticHandler(row_count))
    return {"status": result.status.value, "publication_committed": result.publication_committed, "checkpoint_written": result.checkpoint_written, "rows_processed": result.rows_processed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an opt-in bounded Telchi segment runtime self-test")
    parser.add_argument("--rows", type=int, default=128)
    args = parser.parse_args()
    if not 1 <= args.rows <= 10_000:
        parser.error("--rows must be between 1 and 10000")
    print(json.dumps(run(args.rows), sort_keys=True))


if __name__ == "__main__":
    main()
