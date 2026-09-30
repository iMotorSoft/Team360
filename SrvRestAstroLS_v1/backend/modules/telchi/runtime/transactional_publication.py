"""Single-transaction trusted publication boundary.

The boundary owns the only trusted commit.  Candidate construction, validation,
and reconciliation happen before :meth:`publish` is called; the writer callback
may only issue trusted-table mutations on the supplied connection.  The
publication record is inserted before the same explicit COMMIT, so a trusted
reader cannot observe data without its durable identity.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol

from .stores import PublicationReceipt


class PublicationFailurePoint(StrEnum):
    BEFORE_TRANSACTION = "BEFORE_TRANSACTION"
    AFTER_TRANSACTION_BEGIN = "AFTER_TRANSACTION_BEGIN"
    AFTER_FIRST_TRUSTED_WRITE = "AFTER_FIRST_TRUSTED_WRITE"
    AFTER_SECOND_TRUSTED_WRITE = "AFTER_SECOND_TRUSTED_WRITE"
    BEFORE_PUBLICATION_RECORD = "BEFORE_PUBLICATION_RECORD"
    AFTER_PUBLICATION_RECORD = "AFTER_PUBLICATION_RECORD"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    IMMEDIATELY_AFTER_COMMIT = "IMMEDIATELY_AFTER_COMMIT"


class UnknownCommitOutcome(RuntimeError):
    """The client lost the connection after COMMIT was sent."""

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(f"commit outcome is unknown for {idempotency_key}")
        self.idempotency_key = idempotency_key


class PublicationWriter(Protocol):
    def __call__(
        self,
        connection: Any,
        candidate: Any,
        publication_id: str,
        inject: Callable[[PublicationFailurePoint], None],
    ) -> None: ...


@dataclass(frozen=True)
class DurablePublicationRecord:
    publication_id: str
    idempotency_key: str
    content_identity: str
    published_at: str
    status: str
    snapshot_id: int | None = None


class TransactionalPublicationBoundary:
    """DuckDB/DuckLake publication with one explicit multi-table transaction."""

    def __init__(
        self,
        *,
        connection_factory: Callable[[], AbstractContextManager[Any]],
        record_table: str,
        writer: PublicationWriter,
        publication_id_factory: Callable[[str], str],
        content_identity: Callable[[Any], str] | None = None,
        failure_point: PublicationFailurePoint | None = None,
    ) -> None:
        self.connection_factory = connection_factory
        self.record_table = record_table
        self.writer = writer
        self.publication_id_factory = publication_id_factory
        self.content_identity = content_identity or self._default_content_identity
        self.failure_point = failure_point
        self.metrics: dict[str, int] = {
            "publication_count": 0,
            "commit_count": 0,
            "rollback_count": 0,
            "recovery_count": 0,
            "duplicate_retry_count": 0,
        }

    @staticmethod
    def _default_content_identity(candidate: Any) -> str:
        value = getattr(candidate, "content_identity", None)
        if value is None and isinstance(candidate, Mapping):
            value = candidate.get("content_identity")
        return str(value if value is not None else repr(candidate))

    def inject(self, point: PublicationFailurePoint) -> None:
        if self.failure_point is point:
            self.failure_point = None
            if point is PublicationFailurePoint.IMMEDIATELY_AFTER_COMMIT:
                raise UnknownCommitOutcome(self._active_idempotency_key)
            raise RuntimeError(f"injected publication failure at {point.value}")

    def publish(
        self,
        *,
        idempotency_key: str,
        candidate: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> PublicationReceipt:
        self._active_idempotency_key = idempotency_key
        publication_id = self.publication_id_factory(idempotency_key)
        existing = self.find(idempotency_key)
        if existing is not None:
            self.metrics["duplicate_retry_count"] += 1
            return existing
        self.metrics["publication_count"] += 1
        self.inject(PublicationFailurePoint.BEFORE_TRANSACTION)
        committed = False
        with self.connection_factory() as connection:
            try:
                connection.execute("BEGIN")
                self.inject(PublicationFailurePoint.AFTER_TRANSACTION_BEGIN)
                # Re-check inside the transaction.  Sequential retries are
                # idempotent; the durable record is also the recovery oracle.
                existing = self._find_on_connection(connection, idempotency_key)
                if existing is not None:
                    connection.execute("ROLLBACK")
                    self.metrics["duplicate_retry_count"] += 1
                    return existing
                self.writer(connection, candidate, publication_id, self.inject)
                self.inject(PublicationFailurePoint.BEFORE_PUBLICATION_RECORD)
                published_at = datetime.now(timezone.utc).isoformat()
                content_identity = self.content_identity(candidate)
                values = dict(metadata or {})
                connection.execute(
                    f"INSERT INTO {self.record_table} "
                    "(publication_id, idempotency_key, content_identity, published_at, status, "
                    "job_id, segment_id, attempt, source_identity, reference_version, transformation_version) "
                    "VALUES (?, ?, ?, ?, 'COMMITTED', ?, ?, ?, ?, ?, ?)",
                    [
                        publication_id,
                        idempotency_key,
                        content_identity,
                        published_at,
                        values.get("job_id"),
                        values.get("segment_id"),
                        values.get("attempt"),
                        values.get("source_identity"),
                        values.get("reference_version"),
                        values.get("transformation_version"),
                    ],
                )
                self.inject(PublicationFailurePoint.AFTER_PUBLICATION_RECORD)
                self.inject(PublicationFailurePoint.BEFORE_COMMIT)
                connection.execute("COMMIT")
                committed = True
                self.metrics["commit_count"] += 1
                self.inject(PublicationFailurePoint.IMMEDIATELY_AFTER_COMMIT)
                return PublicationReceipt(publication_id, idempotency_key, content_identity, published_at)
            except UnknownCommitOutcome:
                # COMMIT was already sent; rollback is neither possible nor
                # correct.  The caller must resolve by publication_id/key.
                raise
            except BaseException:
                if not committed:
                    try:
                        connection.execute("ROLLBACK")
                        self.metrics["rollback_count"] += 1
                    except Exception:
                        pass
                raise

    def _find_on_connection(self, connection: Any, idempotency_key: str) -> PublicationReceipt | None:
        try:
            row = connection.execute(
                f"SELECT publication_id, content_identity, published_at, status "
                f"FROM {self.record_table} WHERE idempotency_key = ?",
                [idempotency_key],
            ).fetchone()
        except Exception:
            return None
        if row is None or row[3] != "COMMITTED":
            return None
        return PublicationReceipt(row[0], idempotency_key, row[1], row[2])

    def find(self, idempotency_key: str) -> PublicationReceipt | None:
        with self.connection_factory() as connection:
            return self._find_on_connection(connection, idempotency_key)

    def resolve_unknown_commit(self, idempotency_key: str) -> PublicationReceipt | None:
        self.metrics["recovery_count"] += 1
        return self.find(idempotency_key)

    def trusted(self) -> Mapping[str, Any]:
        """The official reader must use its own connection and this record path."""
        return {"record_table": self.record_table, "candidate_visible": False}
