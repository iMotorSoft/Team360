from __future__ import annotations

import time
from pathlib import Path

import pytest

from modules.telchi.runtime.config import DuckDBSafetyProfile, RuntimeConfig, apply_duckdb_safety_profile, open_safe_duckdb
from modules.telchi.runtime.contracts import (
    CheckpointStatus,
    DirtyScope,
    DirtyScopeStatus,
    InvalidTransition,
    Job,
    JobStatus,
    JobType,
    ReconciliationResult,
    Segment,
    SegmentRange,
    SegmentStatus,
    ValidationResult,
    Watermark,
)
from modules.telchi.runtime.coverage import CoverageConflict, CoverageTracker
from modules.telchi.runtime.dirty_scope import DirtyScopeTracker
from modules.telchi.runtime.executor import SegmentExecutor
from modules.telchi.runtime.handler import HandlerContext
from modules.telchi.runtime.observability import InMemoryObservability
from modules.telchi.runtime.resource_guard import ResourceGuard, ResourceMetrics, ResourcePolicy, SafeAbort
from modules.telchi.runtime.segment import half_open_ranges, split_coverage, split_segment
from modules.telchi.runtime.sizing import SegmentSizingAdvisor, SegmentSizingDecision
from modules.telchi.runtime.stores import FailingCheckpointStore, InMemoryPublicationBoundary, InMemoryRuntimeStore
from modules.telchi.runtime.watermark import WatermarkSafetyError, WatermarkTracker


GOOD = ResourceMetrics(
    available_memory_bytes=8 * 1024**3,
    memory_used_percent=20,
    swap_used_percent=0,
    load_ratio=0.1,
    disk_free_bytes=20 * 1024**3,
    temp_disk_free_bytes=20 * 1024**3,
)


def guard_for(metrics):
    values = list(metrics if isinstance(metrics, list) else [metrics])
    index = 0

    def provider():
        nonlocal index
        value = values[min(index, len(values) - 1)]
        index += 1
        return value

    return ResourceGuard(
        ResourcePolicy(
            min_available_memory_bytes=1024,
            min_disk_free_bytes=1024,
            min_temp_free_bytes=1024,
            segment_timeout_seconds=2,
        ),
        temp_directory=Path("/tmp/telchi-runtime-test"),
        metrics_provider=provider,
    )


def make_job_segment(segment_id="s1", start=0, end=4):
    job = Job("job-1", JobType.INITIAL_INGESTION, "synthetic", "LOCAL_SYNTHETIC", coverage_from=0, coverage_to=4)
    segment = Segment(
        segment_id,
        job.job_id,
        "synthetic",
        "TEST",
        "LOCAL_SYNTHETIC",
        "BOUNDED_RANGE",
        SegmentRange(start, end),
        row_budget=100,
        byte_budget=10000,
        timeout_seconds=1,
        source_identity="source-v1",
        reference_version="reference-v1",
        transformation_version="transform-v1",
    )
    return job, segment


class SyntheticHandler:
    def __init__(self, phase=None, rows=4, delay=0):
        self.phase = phase
        self.rows = rows
        self.delay = delay
        self.cleaned = False
        self.max_inflight = 0

    def prepare(self, segment, context):
        if self.phase == "prepare":
            raise RuntimeError("prepare failure")

    def extract(self, segment, context):
        if self.phase == "extract":
            raise RuntimeError("extract failure")

        def source():
            for value in range(self.rows):
                if self.delay:
                    time.sleep(self.delay)
                yield value

        return source()

    def transform(self, rows, context):
        if self.phase == "transform":
            raise RuntimeError("transform failure")
        return (value * 2 for value in rows)

    def build_candidate(self, rows, context):
        if self.phase == "build":
            raise RuntimeError("candidate failure")
        count = 0
        digest = 0
        for value in rows:
            count += 1
            self.max_inflight = max(self.max_inflight, 1)
            digest += value
        return {"content_identity": f"rows:{count}:sum:{digest}", "count": count}

    def validate(self, candidate, context):
        if self.phase == "validate":
            return ValidationResult(False, "synthetic invalid")
        return ValidationResult(True)

    def reconcile(self, candidate, context):
        if self.phase == "reconcile":
            return ReconciliationResult(False, "synthetic divergence")
        return ReconciliationResult(True)

    def cleanup(self, segment, context):
        self.cleaned = True


@pytest.mark.parametrize("from_state,to_state", [
    (JobStatus.PLANNED, JobStatus.RUNNING),
    (JobStatus.RUNNING, JobStatus.PARTIAL),
])
def test_job_valid_transitions(from_state, to_state):
    job, _ = make_job_segment()
    job.status = from_state
    job.transition(to_state)
    assert job.status is to_state


def test_invalid_state_transitions_are_rejected():
    job, segment = make_job_segment()
    with pytest.raises(InvalidTransition):
        job.transition(JobStatus.COMPLETED)
    job.status = JobStatus.RUNNING
    with pytest.raises(InvalidTransition):
        job.transition(JobStatus.COMPLETED)
    with pytest.raises(InvalidTransition):
        segment.transition(SegmentStatus.PUBLISHED)


def test_success_publication_checkpoint_resume_and_idempotent_rerun():
    store = InMemoryRuntimeStore()
    coverage = CoverageTracker()
    boundary = InMemoryPublicationBoundary()
    telemetry = InMemoryObservability()
    executor = SegmentExecutor(
        job_store=store,
        segment_store=store,
        checkpoint_store=store,
        publication_boundary=boundary,
        resource_guard=guard_for(GOOD),
        coverage=coverage,
        observability=telemetry,
    )
    job, segment = make_job_segment()
    first = executor.execute(job, segment, SyntheticHandler())
    assert first.publication_committed and first.checkpoint_written
    assert segment.status is SegmentStatus.PUBLISHED
    assert segment.checkpoint_status is CheckpointStatus.WRITTEN
    assert coverage.contiguous_trusted(segment.scope)
    second = executor.execute(job, segment, SyntheticHandler())
    assert second.idempotent and second.recovered_publication
    assert len(boundary.trusted()) == 1
    assert len(telemetry.metrics) == 2


def test_failure_phases_fail_closed_without_trusted_candidate():
    for phase in ("prepare", "extract", "transform", "build", "validate", "reconcile"):
        store = InMemoryRuntimeStore()
        boundary = InMemoryPublicationBoundary()
        executor = SegmentExecutor(
            job_store=store,
            segment_store=store,
            checkpoint_store=store,
            publication_boundary=boundary,
            resource_guard=guard_for(GOOD),
        )
        job, segment = make_job_segment(segment_id=f"{phase}-segment")
        result = executor.execute(job, segment, SyntheticHandler(phase=phase))
        assert not result.publication_committed, phase
        assert not boundary.trusted(), phase
        assert segment.publication_status.value == "NOT_PUBLISHED"


def test_publication_failure_fail_closed():
    store = InMemoryRuntimeStore()
    boundary = InMemoryPublicationBoundary()
    boundary.fail_next = True
    executor = SegmentExecutor(
        job_store=store,
        segment_store=store,
        checkpoint_store=store,
        publication_boundary=boundary,
        resource_guard=guard_for(GOOD),
    )
    job, segment = make_job_segment()
    result = executor.execute(job, segment, SyntheticHandler())
    assert result.error_code == "UNHANDLED_EXCEPTION"
    assert not boundary.trusted()
    assert segment.status is SegmentStatus.FAILED


def test_publish_then_checkpoint_failure_is_recoverable_without_duplicate_publish():
    state = FailingCheckpointStore()
    boundary = InMemoryPublicationBoundary()
    executor = SegmentExecutor(
        job_store=state,
        segment_store=state,
        checkpoint_store=state,
        publication_boundary=boundary,
        resource_guard=guard_for(GOOD),
    )
    job, segment = make_job_segment()
    first = executor.execute(job, segment, SyntheticHandler())
    assert first.publication_committed and not first.checkpoint_written
    assert segment.status is SegmentStatus.PUBLISHED
    publication_count = len(boundary.trusted())
    second = executor.execute(job, segment, SyntheticHandler())
    assert second.recovered_publication and second.checkpoint_written
    assert len(boundary.trusted()) == publication_count


def test_resume_reuses_s1_s2_and_retries_only_safe_aborted_s3():
    state = InMemoryRuntimeStore()
    boundary = InMemoryPublicationBoundary()
    coverage = CoverageTracker()
    executor = SegmentExecutor(job_store=state, segment_store=state, checkpoint_store=state, publication_boundary=boundary, resource_guard=guard_for(GOOD), coverage=coverage)
    job, s1 = make_job_segment("s1", 0, 2)
    _, s2 = make_job_segment("s2", 2, 4)
    _, s3 = make_job_segment("s3", 4, 6)
    s2.job_id = s3.job_id = job.job_id
    assert executor.execute(job, s1, SyntheticHandler(rows=2)).publication_committed
    assert executor.execute(job, s2, SyntheticHandler(rows=2)).publication_committed
    executor.resource_guard = guard_for([GOOD, ResourceMetrics(0, 99, 99, 99, 0, 0)])
    aborted = executor.execute(job, s3, SyntheticHandler(rows=2))
    assert aborted.error_code == "SAFE_ABORT"
    trusted_before = dict(boundary.trusted())
    executor.resource_guard = guard_for(GOOD)
    resumed = executor.execute(job, s3, SyntheticHandler(rows=2))
    assert resumed.publication_committed
    assert set(boundary.trusted()) == set(trusted_before) | {s3.idempotency_key}
    assert executor.execute(job, s1, SyntheticHandler(rows=2)).idempotent
    assert executor.execute(job, s2, SyntheticHandler(rows=2)).idempotent


def test_job_completion_requires_trusted_contiguous_coverage():
    state = InMemoryRuntimeStore()
    coverage = CoverageTracker()
    executor = SegmentExecutor(job_store=state, segment_store=state, checkpoint_store=state, coverage=coverage, resource_guard=guard_for(GOOD))
    job, segment = make_job_segment()
    with pytest.raises(ValueError):
        executor.complete_job(job, segment.scope)
    from modules.telchi.runtime.contracts import CoverageEntry, CoverageStatus
    coverage.add(CoverageEntry("complete", segment.scope, CoverageStatus.TRUSTED))
    job.status = JobStatus.RUNNING
    executor.complete_job(job, segment.scope)
    assert job.status is JobStatus.COMPLETED


def test_sizing_advisor_emits_conservative_signals_only():
    warning = guard_for(ResourceMetrics(8 * 1024**3, 85, 30, 1.5, 5 * 1024**3, 5 * 1024**3)).preflight()
    advisor = SegmentSizingAdvisor()
    assert advisor.advise(warning).decision is SegmentSizingDecision.REDUCE_NEXT_SEGMENT
    assert advisor.advise(warning, split_requested=True).decision is SegmentSizingDecision.SPLIT_CURRENT_SEGMENT
    critical = guard_for(ResourceMetrics(1, 99, 99, 9, 1, 1)).assess()
    assert advisor.advise(critical).decision is SegmentSizingDecision.SAFE_ABORT


def test_safe_abort_preserves_previous_trusted_state():
    state = InMemoryRuntimeStore()
    boundary = InMemoryPublicationBoundary()
    coverage = CoverageTracker()
    executor = SegmentExecutor(
        job_store=state,
        segment_store=state,
        checkpoint_store=state,
        publication_boundary=boundary,
        resource_guard=guard_for(GOOD),
        coverage=coverage,
    )
    job, first = make_job_segment("s1", 0, 2)
    assert executor.execute(job, first, SyntheticHandler(rows=2)).publication_committed
    _, second = make_job_segment("s2", 2, 4)
    second.job_id = job.job_id
    critical = ResourceMetrics(0, 99, 99, 99, 0, 0)
    executor.resource_guard = guard_for([GOOD, critical])
    result = executor.execute(job, second, SyntheticHandler(rows=2))
    assert result.error_code == "SAFE_ABORT"
    assert not result.publication_committed
    assert len(boundary.trusted()) == 1
    assert state.get("s1") is not None  # previous checkpoint preserved


def test_timeout_is_cooperative_and_does_not_publish():
    state = InMemoryRuntimeStore()
    boundary = InMemoryPublicationBoundary()
    executor = SegmentExecutor(
        job_store=state,
        segment_store=state,
        checkpoint_store=state,
        publication_boundary=boundary,
        resource_guard=guard_for(GOOD),
    )
    job, segment = make_job_segment()
    segment.timeout_seconds = 0.02
    result = executor.execute(job, segment, SyntheticHandler(delay=0.05))
    assert result.error_code == "SAFE_ABORT"
    assert result.error_message == "SEGMENT_TIMEOUT"
    assert not boundary.trusted()
    time.sleep(0.08)  # allow the cooperative daemon worker to observe cancellation
    assert not boundary.trusted()


def test_resource_preflight_block_warning_and_continuous_abort():
    bad = ResourceMetrics(1, 95, 80, 5, 1, 1)
    guard = guard_for(bad)
    with pytest.raises(SafeAbort):
        guard.preflight()
    warning = ResourceMetrics(8 * 1024**3, 85, 30, 1.5, 5 * 1024**3, 5 * 1024**3)
    assessment = guard_for(warning).preflight()
    assert assessment.decision == "REDUCE_NEXT_SEGMENT"

    state = InMemoryRuntimeStore()
    boundary = InMemoryPublicationBoundary()
    executor = SegmentExecutor(
        job_store=state,
        segment_store=state,
        checkpoint_store=state,
        publication_boundary=boundary,
        resource_guard=guard_for([GOOD, bad]),
    )
    job, segment = make_job_segment()
    result = executor.execute(job, segment, SyntheticHandler())
    assert result.error_code == "SAFE_ABORT"
    assert not boundary.trusted()


def test_split_ranges_have_exact_parent_child_lineage_and_boundaries():
    parent = Segment("parent", "job", "d", "op", "mode", "range", SegmentRange(0, 10))
    children = split_segment(parent, 5, child_ids=("s1", "s2"))
    assert parent.status is SegmentStatus.SPLIT
    assert children[0].scope == SegmentRange(0, 5)
    assert children[1].scope == SegmentRange(5, 10)
    assert split_coverage(parent, children)[0].parent_segment_id == "parent"
    assert half_open_ranges(0, 10, 3) == (SegmentRange(0, 3), SegmentRange(3, 6), SegmentRange(6, 9), SegmentRange(9, 10))
    with pytest.raises(ValueError):
        SegmentRange(0, 10).split(0)


def test_coverage_detects_gap_and_rejects_overlap():
    coverage = CoverageTracker()
    from modules.telchi.runtime.contracts import CoverageEntry, CoverageStatus
    coverage.add(CoverageEntry("s1", SegmentRange(0, 2), CoverageStatus.TRUSTED))
    coverage.add(CoverageEntry("s2", SegmentRange(4, 6), CoverageStatus.TRUSTED))
    report = coverage.report(SegmentRange(0, 6))
    assert report.gaps == (SegmentRange(2, 4),)
    assert report.contiguous_trusted_to == 2
    with pytest.raises(CoverageConflict):
        coverage.add(CoverageEntry("overlap", SegmentRange(1, 3), CoverageStatus.PENDING))


def test_watermark_cannot_skip_gap():
    coverage = CoverageTracker()
    from modules.telchi.runtime.contracts import CoverageEntry, CoverageStatus
    coverage.add(CoverageEntry("s1", SegmentRange(0, 2), CoverageStatus.TRUSTED))
    coverage.add(CoverageEntry("s2", SegmentRange(2, 4), CoverageStatus.FAILED))
    store = InMemoryRuntimeStore()
    tracker = WatermarkTracker(store, coverage)
    tracker.record_detected("synthetic", 4)
    tracker.record_processed("synthetic", 4)
    tracker.record_validated("synthetic", 4)
    with pytest.raises(WatermarkSafetyError):
        tracker.advance_trusted("synthetic", SegmentRange(0, 4), 4)


def test_dirty_historical_scope_reprocesses_and_clears():
    store = InMemoryRuntimeStore()
    tracker = DirtyScopeTracker(store)
    scope = tracker.detect(DirtyScope("dirty-1", "synthetic", "BUSINESS_KEY", "2024-03", ("key-1",), "synthetic late source change", source_change_identity="change-9"))
    tracker.transition(scope.dirty_scope_id, DirtyScopeStatus.REPROCESSING)
    tracker.transition(scope.dirty_scope_id, DirtyScopeStatus.RECONCILING)
    cleared = tracker.transition(scope.dirty_scope_id, DirtyScopeStatus.CLEARED)
    assert cleared.status is DirtyScopeStatus.CLEARED
    with pytest.raises(InvalidTransition):
        tracker.transition(scope.dirty_scope_id, DirtyScopeStatus.REPROCESSING)


def test_bounded_handler_never_requires_source_materialization():
    handler = SyntheticHandler(rows=1000)
    executor = SegmentExecutor(resource_guard=guard_for(GOOD))
    job, segment = make_job_segment(end=1000)
    segment.row_budget = 1000
    result = executor.execute(job, segment, handler)
    assert result.publication_committed
    assert result.rows_processed == 1000
    assert handler.max_inflight == 1


def test_row_and_byte_budgets_abort_before_trusted_publish():
    executor = SegmentExecutor(resource_guard=guard_for(GOOD))
    job, segment = make_job_segment()
    segment.row_budget = 2
    result = executor.execute(job, segment, SyntheticHandler())
    assert result.error_code == "SAFE_ABORT"
    assert result.error_message == "ROW_BUDGET_EXCEEDED"

    class ByteBudgetHandler(SyntheticHandler):
        def build_candidate(self, rows, context):
            for row in rows:
                context.consume_bytes(10)
            return {"content_identity": "bytes", "count": 4}

    job, segment = make_job_segment(segment_id="bytes")
    segment.byte_budget = 5
    result = executor.execute(job, segment, ByteBudgetHandler())
    assert result.error_code == "SAFE_ABORT"
    assert result.error_message == "BYTE_BUDGET_EXCEEDED"


def test_duckdb_safety_profile_applies_explicit_settings(tmp_path):
    profile = DuckDBSafetyProfile("64MB", 1, tmp_path / "spill", "128MB")
    connection = open_safe_duckdb(":memory:", profile=profile)
    try:
        settings = {row[0]: row[1] for row in connection.execute("SELECT name, value FROM duckdb_settings() WHERE name IN ('memory_limit','threads','temp_directory','max_temp_directory_size')").fetchall()}
        assert settings["memory_limit"].endswith("MiB")
        assert float(settings["memory_limit"].split()[0]) > 50
        assert settings["threads"] == "1"
        assert str(profile.temp_directory) in settings["temp_directory"]
        assert settings["max_temp_directory_size"].endswith("MiB")
        assert float(settings["max_temp_directory_size"].split()[0]) > 100
    finally:
        connection.close()


def test_worker_limit_is_explicit_and_default_one():
    config = RuntimeConfig()
    assert config.max_ingestion_workers == 1
    assert config.max_hana_concurrent_queries == 1
    guard = ResourceGuard(config.resource_policy(), temp_directory=Path("/tmp/telchi-runtime-test"), metrics_provider=lambda: GOOD)
    guard.begin_segment()
    try:
        state = InMemoryRuntimeStore()
        executor = SegmentExecutor(job_store=state, segment_store=state, checkpoint_store=state, resource_guard=guard)
        job, segment = make_job_segment()
        result = executor.execute(job, segment, SyntheticHandler())
        assert result.error_code == "RESOURCE_BLOCKED"
    finally:
        guard.end_segment()
