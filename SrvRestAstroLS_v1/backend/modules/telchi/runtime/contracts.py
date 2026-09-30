"""Small explicit runtime contracts and state machines.

The models carry no SAP or business-table knowledge.  They describe execution
identity, bounded scope, and trust boundaries only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobType(StrEnum):
    INITIAL_INGESTION = "INITIAL_INGESTION"
    INCREMENTAL_UPDATE = "INCREMENTAL_UPDATE"
    RECONCILIATION = "RECONCILIATION"
    REBUILD = "REBUILD"
    DIRTY_SCOPE_REPROCESSING = "DIRTY_SCOPE_REPROCESSING"


class JobStatus(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SAFE_ABORTED = "SAFE_ABORTED"


class SegmentStatus(StrEnum):
    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    RECONCILING = "RECONCILING"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    RETRYABLE_FAILED = "RETRYABLE_FAILED"
    SAFE_ABORTED = "SAFE_ABORTED"
    SPLIT = "SPLIT"
    FAILED = "FAILED"


class CheckpointStatus(StrEnum):
    NOT_CREATED = "NOT_CREATED"
    PENDING = "PENDING"
    WRITTEN = "WRITTEN"
    FAILED = "FAILED"


class ValidationStatus(StrEnum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class ReconciliationStatus(StrEnum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"


class PublicationStatus(StrEnum):
    NOT_PUBLISHED = "NOT_PUBLISHED"
    CANDIDATE = "CANDIDATE"
    TRUSTED = "TRUSTED"


class DirtyScopeStatus(StrEnum):
    DIRTY = "DIRTY"
    REPROCESSING = "REPROCESSING"
    RECONCILING = "RECONCILING"
    CLEARED = "CLEARED"
    DIVERGED = "DIVERGED"


class CoverageStatus(StrEnum):
    TRUSTED = "TRUSTED"
    PENDING = "PENDING"
    DIRTY = "DIRTY"
    FAILED = "FAILED"
    SPLIT = "SPLIT"


class WatermarkStage(StrEnum):
    DETECTED = "DETECTED"
    PROCESSED = "PROCESSED"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"


@dataclass(frozen=True)
class QueryBudget:
    query_timeout_seconds: float | None = None
    row_budget: int | None = None
    byte_budget: int | None = None
    lookback_budget: int | None = None


class InvalidTransition(ValueError):
    """Raised when a job or segment state transition is not allowed."""


JOB_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PLANNED: frozenset({JobStatus.RUNNING, JobStatus.PAUSED}),
    JobStatus.RUNNING: frozenset({JobStatus.PARTIAL, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.SAFE_ABORTED, JobStatus.PAUSED}),
    JobStatus.PARTIAL: frozenset({JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.SAFE_ABORTED}),
    JobStatus.PAUSED: frozenset({JobStatus.RUNNING, JobStatus.SAFE_ABORTED, JobStatus.FAILED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset({JobStatus.PAUSED, JobStatus.RUNNING}),
    JobStatus.SAFE_ABORTED: frozenset({JobStatus.PAUSED, JobStatus.RUNNING}),
}

SEGMENT_TRANSITIONS: dict[SegmentStatus, frozenset[SegmentStatus]] = {
    SegmentStatus.PLANNED: frozenset({SegmentStatus.READY, SegmentStatus.SPLIT}),
    SegmentStatus.READY: frozenset({SegmentStatus.RUNNING, SegmentStatus.RETRYABLE_FAILED, SegmentStatus.SPLIT}),
    SegmentStatus.RUNNING: frozenset({SegmentStatus.VALIDATING, SegmentStatus.RECONCILING, SegmentStatus.PUBLISHING, SegmentStatus.RETRYABLE_FAILED, SegmentStatus.SAFE_ABORTED, SegmentStatus.FAILED}),
    SegmentStatus.VALIDATING: frozenset({SegmentStatus.RECONCILING, SegmentStatus.PUBLISHING, SegmentStatus.RETRYABLE_FAILED, SegmentStatus.SAFE_ABORTED, SegmentStatus.FAILED}),
    SegmentStatus.RECONCILING: frozenset({SegmentStatus.PUBLISHING, SegmentStatus.RETRYABLE_FAILED, SegmentStatus.SAFE_ABORTED, SegmentStatus.FAILED}),
    SegmentStatus.PUBLISHING: frozenset({SegmentStatus.PUBLISHED, SegmentStatus.RETRYABLE_FAILED, SegmentStatus.SAFE_ABORTED, SegmentStatus.FAILED}),
    SegmentStatus.PUBLISHED: frozenset(),
    SegmentStatus.RETRYABLE_FAILED: frozenset({SegmentStatus.READY, SegmentStatus.SAFE_ABORTED, SegmentStatus.FAILED}),
    SegmentStatus.SAFE_ABORTED: frozenset({SegmentStatus.READY, SegmentStatus.SPLIT, SegmentStatus.FAILED}),
    SegmentStatus.SPLIT: frozenset(),
    SegmentStatus.FAILED: frozenset({SegmentStatus.READY}),
}


@dataclass(frozen=True, order=True)
class SegmentRange:
    """A half-open, bounded range: ``[start, end)``."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("segment range must be non-empty and half-open")

    def overlaps(self, other: "SegmentRange") -> bool:
        return self.start < other.end and other.start < self.end

    def touches(self, other: "SegmentRange") -> bool:
        return self.end == other.start or other.end == self.start

    def split(self, split_at: int) -> tuple["SegmentRange", "SegmentRange"]:
        if not self.start < split_at < self.end:
            raise ValueError("split point must be strictly inside the range")
        return SegmentRange(self.start, split_at), SegmentRange(split_at, self.end)


@dataclass
class Job:
    job_id: str
    job_type: JobType | str
    domain: str
    ingestion_mode: str
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: JobStatus = JobStatus.PLANNED
    coverage_from: int | None = None
    coverage_to: int | None = None
    reference_version: str = ""
    transformation_version: str = ""
    resource_profile: str = "default"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def transition(self, target: JobStatus, *, coverage_complete: bool = False) -> None:
        if target is JobStatus.COMPLETED and not coverage_complete:
            raise InvalidTransition("job completion requires contiguous trusted coverage")
        if target not in JOB_TRANSITIONS[self.status]:
            raise InvalidTransition(f"job {self.job_id}: {self.status} -> {target}")
        self.status = target
        if target is JobStatus.RUNNING and self.started_at is None:
            self.started_at = utc_now()
        if target in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.SAFE_ABORTED}:
            self.completed_at = utc_now()


@dataclass
class Segment:
    segment_id: str
    job_id: str
    domain: str
    operation: str
    ingestion_mode: str
    segment_strategy: str
    scope: SegmentRange
    parent_segment_id: str | None = None
    affected_keys: tuple[str, ...] = ()
    attempt: int = 0
    status: SegmentStatus = SegmentStatus.PLANNED
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    row_budget: int | None = None
    byte_budget: int | None = None
    timeout_seconds: float = 300.0
    resource_profile: str = "default"
    checkpoint_status: CheckpointStatus = CheckpointStatus.NOT_CREATED
    validation_status: ValidationStatus = ValidationStatus.PENDING
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.PENDING
    publication_status: PublicationStatus = PublicationStatus.NOT_PUBLISHED
    error_code: str | None = None
    error_message: str | None = None
    source_identity: str = ""
    reference_version: str = ""
    transformation_version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def transition(self, target: SegmentStatus) -> None:
        if target not in SEGMENT_TRANSITIONS[self.status]:
            raise InvalidTransition(f"segment {self.segment_id}: {self.status} -> {target}")
        self.status = target
        if target is SegmentStatus.RUNNING:
            self.started_at = self.started_at or utc_now()
        if target in {SegmentStatus.PUBLISHED, SegmentStatus.SPLIT, SegmentStatus.FAILED, SegmentStatus.SAFE_ABORTED}:
            self.completed_at = utc_now()

    @property
    def scope_from(self) -> int:
        return self.scope.start

    @property
    def scope_to(self) -> int:
        return self.scope.end

    @property
    def idempotency_key(self) -> str:
        return "|".join((self.segment_id, self.source_identity, self.reference_version, self.transformation_version))


@dataclass(frozen=True)
class Checkpoint:
    job_id: str
    segment_id: str
    attempt: int
    published_at: datetime
    scope: SegmentRange
    validation_result: str
    reconciliation_result: str
    content_identity: str
    publication_identity: str


@dataclass
class Watermark:
    domain: str
    detected: int | None = None
    processed: int | None = None
    validated: int | None = None
    published: int | None = None


@dataclass
class DirtyScope:
    dirty_scope_id: str
    domain: str
    scope_type: str
    business_period: str
    affected_keys: tuple[str, ...]
    reason: str
    detected_at: datetime = field(default_factory=utc_now)
    status: DirtyScopeStatus = DirtyScopeStatus.DIRTY
    source_change_identity: str = ""

    def transition(self, target: DirtyScopeStatus) -> None:
        allowed = {
            DirtyScopeStatus.DIRTY: {DirtyScopeStatus.REPROCESSING, DirtyScopeStatus.DIVERGED},
            DirtyScopeStatus.REPROCESSING: {DirtyScopeStatus.RECONCILING, DirtyScopeStatus.DIVERGED},
            DirtyScopeStatus.RECONCILING: {DirtyScopeStatus.CLEARED, DirtyScopeStatus.DIVERGED},
            DirtyScopeStatus.CLEARED: set(),
            DirtyScopeStatus.DIVERGED: {DirtyScopeStatus.REPROCESSING},
        }
        if target not in allowed[self.status]:
            raise InvalidTransition(f"dirty scope {self.dirty_scope_id}: {self.status} -> {target}")
        self.status = target


@dataclass(frozen=True)
class CoverageEntry:
    segment_id: str
    scope: SegmentRange
    status: CoverageStatus
    parent_segment_id: str | None = None


@dataclass(frozen=True)
class PhaseResult:
    rows_processed: int = 0
    bytes_processed: int = 0
    content_identity: str = ""
    value: Any = None


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class ReconciliationResult:
    passed: bool
    detail: str = ""
