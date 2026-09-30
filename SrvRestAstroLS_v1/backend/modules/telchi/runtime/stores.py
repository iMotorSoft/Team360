"""Durable-state seams and an in-memory implementation for V1 tests."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import Checkpoint, DirtyScope, Job, Segment, Watermark


class JobStateStore(Protocol):
    def save_job(self, job: Job) -> None: ...
    def get_job(self, job_id: str) -> Job | None: ...


class SegmentStateStore(Protocol):
    def save_segment(self, segment: Segment) -> None: ...
    def get_segment(self, segment_id: str) -> Segment | None: ...
    def list_segments(self, job_id: str) -> list[Segment]: ...


class CheckpointStore(Protocol):
    def write(self, checkpoint: Checkpoint) -> None: ...
    def get(self, segment_id: str) -> Checkpoint | None: ...


class CoverageStore(Protocol):
    def save_coverage(self, entries: list[Any]) -> None: ...
    def get_coverage(self) -> list[Any]: ...


class WatermarkStore(Protocol):
    def get_watermark(self, domain: str) -> Watermark | None: ...
    def save_watermark(self, watermark: Watermark) -> None: ...


class DirtyScopeStore(Protocol):
    def save_dirty_scope(self, scope: DirtyScope) -> None: ...
    def get_dirty_scope(self, dirty_scope_id: str) -> DirtyScope | None: ...


class PublicationBoundary(Protocol):
    """Candidate/trusted boundary with an idempotent publication identity."""

    def publish(self, *, idempotency_key: str, candidate: Any, metadata: Mapping[str, Any] | None = None) -> "PublicationReceipt": ...
    def find(self, idempotency_key: str) -> "PublicationReceipt | None": ...
    def trusted(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class PublicationReceipt:
    publication_identity: str
    idempotency_key: str
    content_identity: str
    published_at: Any


class InMemoryRuntimeStore(JobStateStore, SegmentStateStore, CheckpointStore, WatermarkStore, DirtyScopeStore):
    """Test backend; it deliberately has no PostgreSQL/DuckLake side effects."""

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.segments: dict[str, Segment] = {}
        self.checkpoints: dict[str, Checkpoint] = {}
        self.watermarks: dict[str, Watermark] = {}
        self.dirty_scopes: dict[str, DirtyScope] = {}
        self.coverage: list[Any] = []

    def save_job(self, job: Job) -> None:
        self.jobs[job.job_id] = job

    def get_job(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def save_segment(self, segment: Segment) -> None:
        self.segments[segment.segment_id] = segment

    def get_segment(self, segment_id: str) -> Segment | None:
        return self.segments.get(segment_id)

    def list_segments(self, job_id: str) -> list[Segment]:
        return [s for s in self.segments.values() if s.job_id == job_id]

    def write(self, checkpoint: Checkpoint) -> None:
        existing = self.checkpoints.get(checkpoint.segment_id)
        if existing is not None and existing != checkpoint:
            raise ValueError("checkpoint identity conflict")
        self.checkpoints[checkpoint.segment_id] = checkpoint

    def get(self, segment_id: str) -> Checkpoint | None:
        return self.checkpoints.get(segment_id)

    def get_watermark(self, domain: str) -> Watermark | None:
        return self.watermarks.get(domain)

    def save_watermark(self, watermark: Watermark) -> None:
        self.watermarks[watermark.domain] = watermark

    def get_dirty_scope(self, dirty_scope_id: str) -> DirtyScope | None:
        return self.dirty_scopes.get(dirty_scope_id)

    def save_dirty_scope(self, scope: DirtyScope) -> None:
        self.dirty_scopes[scope.dirty_scope_id] = scope


class InMemoryPublicationBoundary(PublicationBoundary):
    """Atomic logical publication: candidate is never exposed by ``trusted``."""

    def __init__(self) -> None:
        self._receipts: dict[str, PublicationReceipt] = {}
        self._trusted: dict[str, Any] = {}
        self.fail_next = False

    @staticmethod
    def _content_identity(candidate: Any) -> str:
        identity = getattr(candidate, "content_identity", None)
        if identity:
            return str(identity)
        if isinstance(candidate, Mapping) and candidate.get("content_identity"):
            return str(candidate["content_identity"])
        return repr(candidate)

    def publish(self, *, idempotency_key: str, candidate: Any, metadata: Mapping[str, Any] | None = None) -> PublicationReceipt:
        existing = self._receipts.get(idempotency_key)
        if existing is not None:
            return existing
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("injected publication failure")
        import uuid
        from datetime import datetime, timezone

        receipt = PublicationReceipt(
            publication_identity=str(uuid.uuid4()),
            idempotency_key=idempotency_key,
            content_identity=self._content_identity(candidate),
            published_at=datetime.now(timezone.utc),
        )
        # The only mutation visible to trusted readers happens here.
        self._trusted[idempotency_key] = candidate
        self._receipts[idempotency_key] = receipt
        return receipt

    def find(self, idempotency_key: str) -> PublicationReceipt | None:
        return self._receipts.get(idempotency_key)

    def trusted(self) -> Mapping[str, Any]:
        return dict(self._trusted)


class FailingCheckpointStore(InMemoryRuntimeStore):
    """Failure-injection helper for the publish/checkpoint recovery contract."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_next = True

    def write(self, checkpoint: Checkpoint) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("injected checkpoint failure")
        super().write(checkpoint)
