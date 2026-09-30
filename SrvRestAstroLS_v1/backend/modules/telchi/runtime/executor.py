"""Generic bounded segment executor with a candidate/trusted publication boundary."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from .contracts import (
    Checkpoint,
    CheckpointStatus,
    CoverageEntry,
    CoverageStatus,
    Job,
    JobStatus,
    PublicationStatus,
    ReconciliationStatus,
    Segment,
    SegmentStatus,
    ValidationStatus,
)
from .coverage import CoverageConflict, CoverageTracker
from .handler import HandlerContext, SegmentHandler
from .observability import InMemoryObservability, ObservabilitySink, SegmentMetric
from .resource_guard import ResourceAssessment, ResourceGuard, SafeAbort
from .stores import (
    CheckpointStore,
    InMemoryPublicationBoundary,
    InMemoryRuntimeStore,
    JobStateStore,
    PublicationBoundary,
    PublicationReceipt,
    SegmentStateStore,
)
from .transactional_publication import UnknownCommitOutcome


class PhaseFailure(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class ExecutionResult:
    segment_id: str
    status: SegmentStatus
    publication_committed: bool
    checkpoint_written: bool
    idempotent: bool = False
    recovered_publication: bool = False
    resource_decision: str = "CONTINUE_SAME_SIZE"
    error_code: str | None = None
    error_message: str | None = None
    rows_processed: int = 0
    bytes_processed: int = 0


class SegmentExecutor:
    """An explicitly invoked executor; it creates no scheduler or background task."""

    def __init__(
        self,
        *,
        job_store: JobStateStore | None = None,
        segment_store: SegmentStateStore | None = None,
        checkpoint_store: CheckpointStore | None = None,
        publication_boundary: PublicationBoundary | None = None,
        resource_guard: ResourceGuard | None = None,
        coverage: CoverageTracker | None = None,
        observability: ObservabilitySink | None = None,
    ) -> None:
        default_store = InMemoryRuntimeStore()
        self.job_store = job_store or default_store
        self.segment_store = segment_store or default_store
        self.checkpoint_store = checkpoint_store or default_store
        self.publication_boundary = publication_boundary or InMemoryPublicationBoundary()
        self.resource_guard = resource_guard or ResourceGuard()
        self.coverage = coverage
        self.observability = observability or InMemoryObservability()

    def complete_job(self, job: Job, required_scope) -> None:
        """Complete only after the required range is contiguous and trusted."""
        if self.coverage is None or not self.coverage.contiguous_trusted(required_scope):
            raise ValueError("job coverage is not complete/trusted")
        if job.status not in {JobStatus.RUNNING, JobStatus.PARTIAL}:
            raise ValueError(f"job cannot complete from {job.status}")
        job.transition(JobStatus.COMPLETED, coverage_complete=True)
        self.job_store.save_job(job)

    def execute(self, job: Job, segment: Segment, handler: SegmentHandler) -> ExecutionResult:
        self.job_store.save_job(job)
        self.segment_store.save_segment(segment)
        started = time.monotonic()

        if segment.status is SegmentStatus.PUBLISHED:
            return self._recover_published(segment, started)

        if not self.resource_guard.worker_slot_available():
            return self._fail_before_start(job, segment, "RESOURCE_BLOCKED", "MAX_INGESTION_WORKERS exceeded")
        try:
            assessment = self.resource_guard.preflight()
        except SafeAbort as exc:
            return self._fail_before_start(job, segment, "RESOURCE_BLOCKED", str(exc))

        if job.status is JobStatus.PLANNED:
            job.transition(JobStatus.RUNNING)
        elif job.status in {JobStatus.PAUSED, JobStatus.PARTIAL, JobStatus.SAFE_ABORTED}:
            job.transition(JobStatus.RUNNING)
        if segment.status is SegmentStatus.PLANNED:
            segment.transition(SegmentStatus.READY)
        if segment.status in {SegmentStatus.RETRYABLE_FAILED, SegmentStatus.SAFE_ABORTED, SegmentStatus.FAILED}:
            segment.transition(SegmentStatus.READY)
        segment.transition(SegmentStatus.RUNNING)
        segment.attempt += 1
        segment.checkpoint_status = CheckpointStatus.PENDING
        if self.coverage is not None and segment.segment_id not in self.coverage.entries:
            try:
                self.coverage.add(CoverageEntry(segment.segment_id, segment.scope, CoverageStatus.PENDING, segment.parent_segment_id))
            except CoverageConflict as exc:
                return self._finish_failure(job, segment, "COVERAGE_CONFLICT", str(exc), started, assessment)
        self.resource_guard.begin_segment()
        cancellation = threading.Event()
        box: dict[str, Any] = {}
        context = HandlerContext(segment, self.resource_guard, {}, cancellation)

        def run_phases() -> None:
            try:
                context.checkpoint()
                handler.prepare(segment, context)
                context.checkpoint()
                extracted = handler.extract(segment, context)
                transformed = handler.transform(self._guarded_rows(extracted, context, count=True), context)
                candidate = handler.build_candidate(self._guarded_rows(transformed, context, count=False), context)
                context.checkpoint()
                segment.transition(SegmentStatus.VALIDATING)
                validation = handler.validate(candidate, context)
                if not validation.passed:
                    raise PhaseFailure("VALIDATION_FAILED", validation.detail)
                segment.validation_status = ValidationStatus.PASSED
                context.checkpoint()
                segment.transition(SegmentStatus.RECONCILING)
                reconciliation = handler.reconcile(candidate, context)
                if not reconciliation.passed:
                    raise PhaseFailure("RECONCILIATION_FAILED", reconciliation.detail)
                segment.reconciliation_status = ReconciliationStatus.PASSED
                context.checkpoint()
                segment.transition(SegmentStatus.PUBLISHING)
                # The publication boundary is the last cooperative resource check.
                # A critical assessment fails closed before trusted state can be committed.
                context.checkpoint()
                receipt = self.publication_boundary.publish(
                    idempotency_key=segment.idempotency_key,
                    candidate=candidate,
                    metadata={
                        "job_id": segment.job_id,
                        "segment_id": segment.segment_id,
                        "attempt": segment.attempt,
                        "source_identity": segment.source_identity,
                        "reference_version": segment.reference_version,
                        "transformation_version": segment.transformation_version,
                    },
                )
                box["candidate"] = candidate
                box["receipt"] = receipt
                box["publication_committed"] = True
            except BaseException as exc:  # captured and classified by the owner thread
                box["exception"] = exc
            finally:
                try:
                    handler.cleanup(segment, context)
                except BaseException as cleanup_exc:
                    box.setdefault("cleanup_exception", cleanup_exc)

        worker = threading.Thread(target=run_phases, name=f"telchi-segment-{segment.segment_id}", daemon=True)
        worker.start()
        worker.join(timeout=segment.timeout_seconds)
        if worker.is_alive():
            cancellation.set()
            # A cleanup hang after publication must not be misreported as an
            # abort: the trusted boundary already committed and recovery must
            # materialize its checkpoint instead of publishing twice.
            if box.get("publication_committed"):
                self.resource_guard.end_segment()
                segment.publication_status = PublicationStatus.TRUSTED
                segment.transition(SegmentStatus.PUBLISHED)
                return self._recover_published(segment, started)
            return self._safe_abort(job, segment, "SEGMENT_TIMEOUT", started, assessment, rows=box.get("rows", 0))
        box["rows"] = int(context.metadata.get("rows_processed", 0))

        exc = box.get("exception")
        if isinstance(exc, UnknownCommitOutcome):
            # A commit exception is not evidence of rollback. Resolve the
            # durable publication identity before deciding whether a retry is
            # safe; never re-run trusted writes blindly.
            receipt = self.publication_boundary.find(exc.idempotency_key)
            if receipt is None:
                self.resource_guard.end_segment()
                return self._finish_failure(job, segment, "UNKNOWN_COMMIT_OUTCOME", str(exc), started, assessment, rows=box.get("rows", 0))
            box["receipt"] = receipt
            box["publication_committed"] = True
            exc = None
        if isinstance(exc, SafeAbort):
            return self._safe_abort(job, segment, exc.reason, started, assessment, rows=box.get("rows", 0))
        self.resource_guard.end_segment()
        if exc is not None:
            code = exc.code if isinstance(exc, PhaseFailure) else "UNHANDLED_EXCEPTION"
            return self._finish_failure(job, segment, code, str(exc), started, assessment, rows=box.get("rows", 0))

        receipt: PublicationReceipt = box["receipt"]
        segment.publication_status = PublicationStatus.TRUSTED
        segment.transition(SegmentStatus.PUBLISHED)
        checkpoint_written = False
        checkpoint_error: str | None = None
        checkpoint = Checkpoint(
            job_id=segment.job_id,
            segment_id=segment.segment_id,
            attempt=segment.attempt,
            published_at=receipt.published_at,
            scope=segment.scope,
            validation_result=segment.validation_status.value,
            reconciliation_result=segment.reconciliation_status.value,
            content_identity=receipt.content_identity,
            publication_identity=receipt.publication_identity,
        )
        try:
            self.checkpoint_store.write(checkpoint)
            segment.checkpoint_status = CheckpointStatus.WRITTEN
            checkpoint_written = True
        except Exception as checkpoint_exc:
            # Publication is already trusted. Recovery recognizes its identity and
            # retries only checkpoint materialization; it never publishes twice.
            segment.checkpoint_status = CheckpointStatus.FAILED
            checkpoint_error = str(checkpoint_exc)
        if checkpoint_written and self.coverage is not None:
            self.coverage.set_status(segment.segment_id, CoverageStatus.TRUSTED)
        result = ExecutionResult(
            segment.segment_id,
            SegmentStatus.PUBLISHED,
            True,
            checkpoint_written,
            resource_decision=assessment.decision,
            error_code="CHECKPOINT_FAILED" if checkpoint_error else None,
            error_message=checkpoint_error,
            rows_processed=box.get("rows", 0),
            bytes_processed=int(context.metadata.get("bytes_processed", 0)),
        )
        self._emit(segment, result, started, assessment)
        self.segment_store.save_segment(segment)
        self.job_store.save_job(job)
        return result

    @staticmethod
    def _guarded_rows(rows, context: HandlerContext, *, count: bool):
        for row in rows:
            context.checkpoint()
            if count:
                processed = context.metadata.get("rows_processed", 0) + 1
                if context.segment.row_budget is not None and processed > context.segment.row_budget:
                    raise SafeAbort("ROW_BUDGET_EXCEEDED")
                context.metadata["rows_processed"] = processed
            yield row

    def _recover_published(self, segment: Segment, started: float) -> ExecutionResult:
        receipt = self.publication_boundary.find(segment.idempotency_key)
        if receipt is None:
            segment.error_code = "PUBLISHED_WITHOUT_PUBLICATION_IDENTITY"
            segment.error_message = "cannot safely recover a published segment without publication identity"
            return ExecutionResult(segment.segment_id, SegmentStatus.FAILED, False, False, error_code=segment.error_code, error_message=segment.error_message)
        checkpoint = self.checkpoint_store.get(segment.segment_id)
        if checkpoint is None:
            checkpoint = Checkpoint(
                job_id=segment.job_id,
                segment_id=segment.segment_id,
                attempt=segment.attempt,
                published_at=receipt.published_at,
                scope=segment.scope,
                validation_result=segment.validation_status.value,
                reconciliation_result=segment.reconciliation_status.value,
                content_identity=receipt.content_identity,
                publication_identity=receipt.publication_identity,
            )
            try:
                self.checkpoint_store.write(checkpoint)
            except Exception as exc:
                segment.checkpoint_status = CheckpointStatus.FAILED
                result = ExecutionResult(segment.segment_id, SegmentStatus.PUBLISHED, True, False, recovered_publication=True, error_code="CHECKPOINT_FAILED", error_message=str(exc))
                self._emit(segment, result, started, None)
                self.segment_store.save_segment(segment)
                return result
            segment.checkpoint_status = CheckpointStatus.WRITTEN
            if self.coverage is not None and segment.segment_id in self.coverage.entries:
                self.coverage.set_status(segment.segment_id, CoverageStatus.TRUSTED)
        result = ExecutionResult(segment.segment_id, SegmentStatus.PUBLISHED, True, True, idempotent=True, recovered_publication=True)
        self._emit(segment, result, started, None)
        self.segment_store.save_segment(segment)
        return result

    def _fail_before_start(self, job: Job, segment: Segment, code: str, message: str) -> ExecutionResult:
        if segment.status is SegmentStatus.PLANNED:
            segment.transition(SegmentStatus.READY)
        if segment.status is SegmentStatus.READY:
            segment.transition(SegmentStatus.RETRYABLE_FAILED)
        segment.error_code, segment.error_message = code, message
        if job.status is JobStatus.PLANNED:
            job.transition(JobStatus.RUNNING)
        if job.status is JobStatus.RUNNING:
            job.transition(JobStatus.PARTIAL)
        self.segment_store.save_segment(segment)
        self.job_store.save_job(job)
        return ExecutionResult(segment.segment_id, segment.status, False, False, error_code=code, error_message=message)

    def _safe_abort(self, job: Job, segment: Segment, reason: str, started: float, assessment: ResourceAssessment, *, rows: int = 0) -> ExecutionResult:
        self.resource_guard.end_segment()
        if segment.status in {SegmentStatus.RUNNING, SegmentStatus.VALIDATING, SegmentStatus.RECONCILING, SegmentStatus.PUBLISHING}:
            segment.transition(SegmentStatus.SAFE_ABORTED)
        segment.publication_status = PublicationStatus.NOT_PUBLISHED
        segment.checkpoint_status = CheckpointStatus.FAILED
        segment.error_code, segment.error_message = "SAFE_ABORT", reason
        if self.coverage is not None and segment.segment_id in self.coverage.entries:
            self.coverage.set_status(segment.segment_id, CoverageStatus.FAILED)
        if job.status is JobStatus.RUNNING:
            job.transition(JobStatus.SAFE_ABORTED)
        result = ExecutionResult(segment.segment_id, segment.status, False, False, resource_decision="SAFE_ABORT", error_code="SAFE_ABORT", error_message=reason, rows_processed=rows)
        self._emit(segment, result, started, assessment, safe_abort_reason=reason)
        self.segment_store.save_segment(segment)
        self.job_store.save_job(job)
        return result

    def _finish_failure(self, job: Job, segment: Segment, code: str, message: str, started: float, assessment: ResourceAssessment, *, rows: int = 0) -> ExecutionResult:
        if segment.status in {SegmentStatus.RUNNING, SegmentStatus.VALIDATING, SegmentStatus.RECONCILING, SegmentStatus.PUBLISHING}:
            segment.transition(SegmentStatus.RETRYABLE_FAILED if code != "UNHANDLED_EXCEPTION" else SegmentStatus.FAILED)
        segment.publication_status = PublicationStatus.NOT_PUBLISHED
        segment.checkpoint_status = CheckpointStatus.FAILED
        segment.error_code, segment.error_message = code, message
        if self.coverage is not None and segment.segment_id in self.coverage.entries:
            self.coverage.set_status(segment.segment_id, CoverageStatus.FAILED)
        if job.status is JobStatus.RUNNING:
            job.transition(JobStatus.PARTIAL)
        result = ExecutionResult(segment.segment_id, segment.status, False, False, resource_decision=assessment.decision, error_code=code, error_message=message, rows_processed=rows)
        self._emit(segment, result, started, assessment)
        self.segment_store.save_segment(segment)
        self.job_store.save_job(job)
        return result

    def _emit(self, segment: Segment, result: ExecutionResult, started: float, assessment: ResourceAssessment | None, *, safe_abort_reason: str | None = None) -> None:
        metrics = assessment.metrics if assessment else None
        self.observability.emit(SegmentMetric(
            job_id=segment.job_id,
            segment_id=segment.segment_id,
            attempt=segment.attempt,
            status=result.status.value,
            duration_ms=int((time.monotonic() - started) * 1000),
            rows_processed=result.rows_processed,
            resource_warnings=list(assessment.warnings) if assessment else [],
            safe_abort_reason=safe_abort_reason,
            max_observed_memory_percent=metrics.memory_used_percent if metrics else None,
            max_observed_swap_percent=metrics.swap_used_percent if metrics else None,
            disk_pressure=bool(assessment and any("disk" in item for item in assessment.warnings)),
            timeout=result.error_code == "SAFE_ABORT" and result.error_message == "SEGMENT_TIMEOUT",
        ))
