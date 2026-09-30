"""Explicit, domain-agnostic runtime foundation for bounded Telchi segments.

This package is intentionally opt-in: importing it does not start workers,
schedulers, database connections, SAP access, or background tasks.
"""

from .contracts import (
    Checkpoint,
    DirtyScope,
    Job,
    Segment,
    SegmentRange,
    Watermark,
    QueryBudget,
)
from .executor import ExecutionResult, SegmentExecutor
from .resource_guard import ResourceGuard, ResourceMetrics, ResourcePolicy, SafeAbort
from .sizing import SegmentSizeAdvice, SegmentSizingAdvisor, SegmentSizingDecision
from .transactional_publication import (
    DurablePublicationRecord,
    PublicationFailurePoint,
    TransactionalPublicationBoundary,
    UnknownCommitOutcome,
)

__all__ = [
    "Checkpoint",
    "DirtyScope",
    "ExecutionResult",
    "Job",
    "ResourceGuard",
    "ResourceMetrics",
    "ResourcePolicy",
    "SafeAbort",
    "QueryBudget",
    "SegmentSizeAdvice",
    "SegmentSizingAdvisor",
    "SegmentSizingDecision",
    "DurablePublicationRecord",
    "PublicationFailurePoint",
    "TransactionalPublicationBoundary",
    "UnknownCommitOutcome",
    "Segment",
    "SegmentExecutor",
    "SegmentRange",
    "Watermark",
]
