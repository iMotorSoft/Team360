"""TELCHI_DATALAKE_GLOBAL_LOGICAL_PUBLICATION_BOUNDARY_V1.

A deliberately small metadata + current-pointer layer that gives the whole 2026
foundation (Reference, Sales, OINM, OITW) **one logical commit** even though the
datasets are physically published in separate atomic transactions.

Conceptual model:

    Publication A = CURRENT
      Sales A + OINM A + OITW A + Reference A

    update starts -> candidate Publication B (PREPARING -> VALIDATING
    -> READY_TO_COMMIT) with Sales B / OINM B / OITW B / Reference B

    logical commit: set pointer CURRENT = B (one tiny transaction)

    readers see exactly one committed publication_id, never a mix.

This module does **not** redesign extraction, reconciliation, Reference V2
identity or the bulk writers. It only controls publication visibility. There is
no scheduler, cron, daemon, worker, queue, Temporal, pg_durable or LangGraph.

The metadata lives in the existing DuckLake PostgreSQL catalog under
``telchi.ops`` (no extra PostgreSQL). The physical datasets keep being written
by :class:`~modules.telchi.runtime.transactional_publication.TransactionalPublicationBoundary`;
the logical commit is one small metadata transaction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

GATE = "TELCHI_DATALAKE_GLOBAL_LOGICAL_PUBLICATION_BOUNDARY_V1"
GLOBAL_PUBLICATION_GATE = GATE

CATALOG = "telchi"
PUBLICATIONS_TABLE = f"{CATALOG}.ops.foundation_publications_v1"
CURRENT_POINTER_TABLE = f"{CATALOG}.ops.foundation_current_v1"
RUN_LOCK_TABLE = f"{CATALOG}.ops.foundation_run_lock_v1"

COMPONENT_NAMES = ("reference", "sales", "credit_memo", "oinm", "oitw")
FOUNDATION_COMPONENT_COUNT = len(COMPONENT_NAMES)

# Explicit publication states (spec section 8). CURRENT is only ever set by the
# logical commit; a candidate is never CURRENT before validated.
PREPARING = "PREPARING"
VALIDATING = "VALIDATING"
READY_TO_COMMIT = "READY_TO_COMMIT"
CURRENT = "CURRENT"
FAILED = "FAILED"
SUPERSEDED = "SUPERSEDED"

STATES = (PREPARING, VALIDATING, READY_TO_COMMIT, CURRENT, FAILED, SUPERSEDED)
TERMINAL_STATES = (CURRENT, FAILED, SUPERSEDED)


class PublicationBoundaryError(RuntimeError):
    """The logical publication boundary could not honour its contract."""


class FoundationReaderError(PublicationBoundaryError):
    """The reader cannot resolve exactly one coherent committed foundation."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


# ---------------------------------------------------------------------------
# Fault injection (spec section 48)
# ---------------------------------------------------------------------------


class CommitFaultPoint:
    """Where a synthetic failure can be injected around the logical commit.

    The names mirror the required fault-injection matrix. ``FAIL_DURING_COMMIT``
    occurs *inside* the pointer transaction; the transaction then rolls back,
    so the previous publication stays CURRENT and no ambiguity is possible.
    ``FAIL_AFTER_COMMIT`` occurs after the pointer transaction already
    committed, so the new publication is coherently CURRENT.
    """

    BEFORE_CANDIDATE = "FAIL_BEFORE_SALES"
    AFTER_SALES = "FAIL_AFTER_SALES"
    AFTER_CREDIT_MEMO = "FAIL_AFTER_CREDIT_MEMO"
    AFTER_OINM = "FAIL_AFTER_OINM"
    AFTER_OITW = "FAIL_AFTER_OITW"
    AFTER_REFERENCE = "FAIL_AFTER_REFERENCE_SELECTION"
    DURING_VALIDATION = "FAIL_DURING_VALIDATION"
    BEFORE_LOGICAL_COMMIT = "FAIL_BEFORE_LOGICAL_COMMIT"
    DURING_LOGICAL_COMMIT = "FAIL_DURING_LOGICAL_COMMIT"
    AFTER_LOGICAL_COMMIT = "FAIL_AFTER_LOGICAL_COMMIT"


class InjectedFailure(RuntimeError):
    """Raised when a fault-injection point fires."""


# ---------------------------------------------------------------------------
# Metadata schema (created in the existing DuckLake catalog, idempotent)
# ---------------------------------------------------------------------------

def _tables(catalog: str) -> tuple[str, str, str]:
    prefix = f"{catalog}.ops." if catalog else "ops."
    return (
        prefix + "foundation_publications_v1",
        prefix + "foundation_current_v1",
        prefix + "foundation_run_lock_v1",
    )


PUBLICATIONS_DDL = f"""
CREATE TABLE IF NOT EXISTS {PUBLICATIONS_TABLE} (
    foundation_publication_id VARCHAR,
    update_run_id VARCHAR,
    previous_foundation_publication_id VARCHAR,
    status VARCHAR,
    created_at VARCHAR,
    validated_at VARCHAR,
    committed_at VARCHAR,
    reference_version VARCHAR,
    sales_publication_id VARCHAR,
    credit_memo_publication_id VARCHAR,
    oinm_publication_id VARCHAR,
    oitw_publication_id VARCHAR,
    source_as_of VARCHAR,
    reference_source_as_of VARCHAR,
    sales_source_as_of VARCHAR,
    credit_memo_source_as_of VARCHAR,
    oinm_source_as_of VARCHAR,
    oitw_source_as_of VARCHAR,
    component_count INTEGER,
    component_hash VARCHAR,
    validation_status VARCHAR,
    manifest_json VARCHAR,
    failure_reason VARCHAR,
    read_binding_json VARCHAR
)
"""

CURRENT_POINTER_DDL = f"""
CREATE TABLE IF NOT EXISTS {CURRENT_POINTER_TABLE} (
    slot INTEGER,
    foundation_publication_id VARCHAR,
    updated_at VARCHAR
)
"""

RUN_LOCK_DDL = f"""
CREATE TABLE IF NOT EXISTS {RUN_LOCK_TABLE} (
    slot INTEGER,
    update_run_id VARCHAR,
    foundation_publication_id VARCHAR,
    status VARCHAR,
    started_at VARCHAR,
    heartbeat_at VARCHAR,
    owner VARCHAR
)
"""


def ensure_metadata_schema(connection: Any, *, catalog: str = CATALOG) -> None:
    publications_table, pointer_table, lock_table = _tables(catalog)
    if catalog:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.ops")
    else:
        connection.execute("CREATE SCHEMA IF NOT EXISTS ops")
    for ddl in (
        PUBLICATIONS_DDL.replace(PUBLICATIONS_TABLE, publications_table),
        CURRENT_POINTER_DDL.replace(CURRENT_POINTER_TABLE, pointer_table),
        RUN_LOCK_DDL.replace(RUN_LOCK_TABLE, lock_table),
    ):
        connection.execute(ddl)
    existing = {str(row[0]) for row in connection.execute(f"DESCRIBE {publications_table}").fetchall()}
    for column in ("credit_memo_publication_id", "credit_memo_source_as_of", "read_binding_json"):
        if column not in existing:
            connection.execute(f"ALTER TABLE {publications_table} ADD COLUMN {column} VARCHAR")


# ---------------------------------------------------------------------------
# Component references
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentReference:
    """One dataset publication belonging to a foundation publication."""

    name: str
    publication_id: str | None
    source_as_of: str | None = None
    row_count: int | None = None
    content_identity: str | None = None
    keyset_fingerprint: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "publication_id": self.publication_id,
            "source_as_of": self.source_as_of,
            "row_count": self.row_count,
            "content_identity": self.content_identity,
            "keyset_fingerprint": self.keyset_fingerprint,
        }


@dataclass
class FoundationPublication:
    foundation_publication_id: str
    update_run_id: str
    status: str = PREPARING
    previous_foundation_publication_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    validated_at: str | None = None
    committed_at: str | None = None
    reference_version: str | None = None
    components: dict[str, ComponentReference] = field(default_factory=dict)
    source_as_of: str | None = None
    validation_status: str | None = None
    manifest: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None

    def component(self, name: str) -> ComponentReference | None:
        return self.components.get(name)

    @property
    def component_count(self) -> int:
        return sum(
            1 for name in COMPONENT_NAMES
            if (self.component(name) or ComponentReference(name, None)).publication_id
        )

    @property
    def sales_publication_id(self) -> str | None:
        return (self.component("sales") or ComponentReference("sales", None)).publication_id

    @property
    def credit_memo_publication_id(self) -> str | None:
        return (self.component("credit_memo") or ComponentReference("credit_memo", None)).publication_id

    @property
    def oinm_publication_id(self) -> str | None:
        return (self.component("oinm") or ComponentReference("oinm", None)).publication_id

    @property
    def oitw_publication_id(self) -> str | None:
        return (self.component("oitw") or ComponentReference("oitw", None)).publication_id

    def as_row(self) -> dict[str, Any]:
        return {
            "foundation_publication_id": self.foundation_publication_id,
            "update_run_id": self.update_run_id,
            "previous_foundation_publication_id": self.previous_foundation_publication_id,
            "status": self.status,
            "created_at": self.created_at,
            "validated_at": self.validated_at,
            "committed_at": self.committed_at,
            "reference_version": self.reference_version,
            "sales_publication_id": (self.component("sales") or ComponentReference("sales", None)).publication_id,
            "credit_memo_publication_id": (self.component("credit_memo") or ComponentReference("credit_memo", None)).publication_id,
            "oinm_publication_id": (self.component("oinm") or ComponentReference("oinm", None)).publication_id,
            "oitw_publication_id": (self.component("oitw") or ComponentReference("oitw", None)).publication_id,
            "source_as_of": self.source_as_of,
            "reference_source_as_of": (self.component("reference") or ComponentReference("reference", None)).source_as_of,
            "sales_source_as_of": (self.component("sales") or ComponentReference("sales", None)).source_as_of,
            "credit_memo_source_as_of": (self.component("credit_memo") or ComponentReference("credit_memo", None)).source_as_of,
            "oinm_source_as_of": (self.component("oinm") or ComponentReference("oinm", None)).source_as_of,
            "oitw_source_as_of": (self.component("oitw") or ComponentReference("oitw", None)).source_as_of,
            "component_count": sum(1 for name in COMPONENT_NAMES if (self.component(name) or ComponentReference(name, None)).publication_id),
            "component_hash": self.component_hash(),
            "validation_status": self.validation_status,
            "manifest_json": json.dumps(self.manifest, sort_keys=True, default=str),
            "failure_reason": self.failure_reason,
        }

    def component_hash(self) -> str:
        import hashlib

        payload = {
            name: (self.components.get(name) or ComponentReference(name, None)).as_dict()
            for name in COMPONENT_NAMES
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        row = self.as_row()
        return {
            "foundation_publication_id": self.foundation_publication_id,
            "update_run_id": self.update_run_id,
            "previous_foundation_publication_id": self.previous_foundation_publication_id,
            "status": self.status,
            "created_at": self.created_at,
            "validated_at": self.validated_at,
            "committed_at": self.committed_at,
            "reference_version": self.reference_version,
            "sales_publication_id": row["sales_publication_id"],
            "credit_memo_publication_id": row["credit_memo_publication_id"],
            "oinm_publication_id": row["oinm_publication_id"],
            "oitw_publication_id": row["oitw_publication_id"],
            "source_as_of": self.source_as_of,
            "component_count": self.component_count,
            "components": {name: (self.component(name) or ComponentReference(name, None)).as_dict() for name in COMPONENT_NAMES},
            "validation_status": self.validation_status,
            "failure_reason": self.failure_reason,
        }


# ---------------------------------------------------------------------------
# Physical tables / connection protocol
# ---------------------------------------------------------------------------


class _ConnectionFactoryProtocol(Protocol):
    def __call__(self) -> Any: ...


def _unique_manifest_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate Foundation manifest key: {key}")
        result[key] = value
    return result


def _row_to_publication(row: tuple[Any, ...]) -> FoundationPublication:
    (
        foundation_publication_id, update_run_id, previous_foundation_publication_id, status,
        created_at, validated_at, committed_at, reference_version,
        sales_publication_id, credit_memo_publication_id, oinm_publication_id, oitw_publication_id,
        source_as_of, reference_source_as_of, sales_source_as_of, credit_memo_source_as_of, oinm_source_as_of, oitw_source_as_of,
        component_count, component_hash, validation_status, manifest_json, failure_reason,
    ) = row
    components = {
        "reference": ComponentReference("reference", reference_version, reference_source_as_of),
        "sales": ComponentReference("sales", sales_publication_id, sales_source_as_of),
        "credit_memo": ComponentReference("credit_memo", credit_memo_publication_id, credit_memo_source_as_of),
        "oinm": ComponentReference("oinm", oinm_publication_id, oinm_source_as_of),
        "oitw": ComponentReference("oitw", oitw_publication_id, oitw_source_as_of),
    }
    manifest: dict[str, Any] = {}
    if manifest_json:
        try:
            manifest = json.loads(manifest_json, object_pairs_hook=_unique_manifest_object)
        except (TypeError, ValueError):
            manifest = {}
    return FoundationPublication(
        foundation_publication_id=str(foundation_publication_id),
        update_run_id=str(update_run_id),
        previous_foundation_publication_id=previous_foundation_publication_id,
        status=str(status),
        created_at=str(created_at),
        validated_at=validated_at,
        committed_at=committed_at,
        reference_version=reference_version,
        components=components,
        source_as_of=source_as_of,
        validation_status=validation_status,
        manifest=manifest,
        failure_reason=failure_reason,
    )


_COLUMN_NAMES = (
    "foundation_publication_id", "update_run_id", "previous_foundation_publication_id", "status",
    "created_at", "validated_at", "committed_at", "reference_version",
    "sales_publication_id", "credit_memo_publication_id", "oinm_publication_id", "oitw_publication_id",
    "source_as_of", "reference_source_as_of", "sales_source_as_of", "credit_memo_source_as_of", "oinm_source_as_of", "oitw_source_as_of",
    "component_count", "component_hash", "validation_status", "manifest_json", "failure_reason",
)
_SELECT_COLUMNS = ", ".join(_COLUMN_NAMES)
_SELECT_COLUMNS_P = ", ".join(f"p.{name}" for name in _COLUMN_NAMES)


class FoundationPublicationStore:
    """Read/write access to the foundation publication metadata tables.

    It never writes physical datasets. Dataset publication is owned by the
    existing per-domain boundary; this store only tracks membership and the
    single current pointer.
    """

    def __init__(self, connection_factory: _ConnectionFactoryProtocol, *, fault_point: str | None = None, catalog: str = CATALOG) -> None:
        self.connection_factory = connection_factory
        self.fault_point = fault_point
        self.catalog = catalog
        self.publications_table, self.pointer_table, self.run_lock_table = _tables(catalog)
        self.metrics: dict[str, int] = {
            "logical_commit_count": 0,
            "logical_commit_rollback_count": 0,
            "candidate_create_count": 0,
        }

    # -- fault injection --------------------------------------------------

    def inject(self, point: str) -> None:
        if self.fault_point == point:
            self.fault_point = None
            raise InjectedFailure(f"injected failure at {point}")

    # -- setup ------------------------------------------------------------

    def ensure_schema(self) -> None:
        with self.connection_factory() as connection:
            ensure_metadata_schema(connection, catalog=self.catalog)

    def _ensure(self, connection: Any) -> None:
        ensure_metadata_schema(connection, catalog=self.catalog)

    # -- reads ------------------------------------------------------------

    def current_pointer(self) -> str | None:
        with self.connection_factory() as connection:
            try:
                row = connection.execute(
                    f"SELECT foundation_publication_id FROM {self.pointer_table} WHERE slot = 1"
                ).fetchone()
            except Exception:
                return None
        return str(row[0]) if row and row[0] is not None else None

    def current_publication(self) -> FoundationPublication | None:
        with self.connection_factory() as connection:
            return self._current_on_connection(connection)

    def _current_on_connection(self, connection: Any) -> FoundationPublication | None:
        try:
            row = connection.execute(
                f"SELECT {_SELECT_COLUMNS_P} FROM {self.publications_table} p "
                f"JOIN {self.pointer_table} c ON c.foundation_publication_id = p.foundation_publication_id "
                "WHERE c.slot = 1"
            ).fetchone()
        except Exception:
            return None
        return _row_to_publication(row) if row else None

    def get(self, foundation_publication_id: str) -> FoundationPublication | None:
        with self.connection_factory() as connection:
            row = connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM {self.publications_table} WHERE foundation_publication_id = ?",
                [foundation_publication_id],
            ).fetchone()
        return _row_to_publication(row) if row else None

    def current_count(self) -> int:
        with self.connection_factory() as connection:
            return int(connection.execute(
                f"SELECT count(*) FROM {self.publications_table} WHERE status = ?", [CURRENT]
            ).fetchone()[0])

    def pointer_row_count(self) -> int:
        with self.connection_factory() as connection:
            try:
                return int(connection.execute(f"SELECT count(*) FROM {self.pointer_table}").fetchone()[0])
            except Exception:
                return 0

    def list_publications(self, *, limit: int = 50) -> list[FoundationPublication]:
        with self.connection_factory() as connection:
            rows = connection.execute(
                f"SELECT {_SELECT_COLUMNS} FROM {self.publications_table} ORDER BY created_at DESC LIMIT ?",
                [limit],
            ).fetchall()
        return [_row_to_publication(row) for row in rows]

    def read_binding(self, publication_id: str) -> dict[str, Any]:
        """Read only a publisher-issued receipt; legacy schemas fail closed."""
        with self.connection_factory() as connection:
            try:
                rows = connection.execute(
                    f"SELECT read_binding_json FROM {self.publications_table} WHERE foundation_publication_id = ?",
                    [publication_id],
                ).fetchall()
                if len(rows) != 1 or not rows[0][0]:
                    raise ValueError('missing receipt')
                return json.loads(rows[0][0], object_pairs_hook=_unique_manifest_object)
            except Exception as exc:
                raise FoundationReaderError('FOUNDATION_READ_BINDING_REQUIRED') from exc

    def accredit_read_binding(self, publication: FoundationPublication, binding: dict[str, Any]) -> None:
        """Explicit legacy reaccreditation of an already selected publication.

        New activations use logical_commit(accredit=...) instead: selection and
        receipt are committed atomically. This method preserves the existing
        migration path; it is never invoked by ordinary readers.
        """
        from .foundation_read_binding import validate_binding
        validate_binding(publication, binding)
        with self.connection_factory() as connection:
            self._ensure(connection)
            try:
                connection.execute('BEGIN')
                current = self._current_on_connection(connection)
                if (current is None or current.status != CURRENT
                        or current.foundation_publication_id != publication.foundation_publication_id
                        or current.manifest != publication.manifest
                        or current.as_row() != publication.as_row()):
                    raise PublicationBoundaryError('READ_BINDING_CURRENT_CHANGED')
                rows = connection.execute(
                    f'SELECT read_binding_json FROM {self.publications_table} WHERE foundation_publication_id = ?',
                    [publication.foundation_publication_id],
                ).fetchall()
                if len(rows) != 1:
                    raise PublicationBoundaryError('READ_BINDING_DUPLICATE_PUBLICATION')
                encoded = json.dumps(binding, sort_keys=True)
                if rows[0][0] and json.loads(rows[0][0]) != binding:
                    raise PublicationBoundaryError('READ_BINDING_IMMUTABLE')
                connection.execute(
                    f'UPDATE {self.publications_table} SET read_binding_json = ? WHERE foundation_publication_id = ?',
                    [encoded, publication.foundation_publication_id],
                )
                connection.execute('COMMIT')
            except BaseException:
                connection.execute('ROLLBACK')
                raise

    # -- writes (individual statements; visibility is controlled by commit) --

    def create_candidate(self, publication: FoundationPublication) -> FoundationPublication:
        """Insert a PREPARING candidate. Never changes the current pointer."""
        with self.connection_factory() as connection:
            self._ensure(connection)
            existing = connection.execute(
                f"SELECT 1 FROM {self.publications_table} WHERE foundation_publication_id = ?",
                [publication.foundation_publication_id],
            ).fetchone()
            if existing is not None:
                raise PublicationBoundaryError(
                    f"foundation publication id collision: {publication.foundation_publication_id}"
                )
            columns = tuple(publication.as_row())
            placeholders = ", ".join("?" for _ in columns)
            connection.execute(
                f"INSERT INTO {self.publications_table} ({', '.join(_q(c) for c in columns)}) VALUES ({placeholders})",
                [publication.as_row()[c] for c in columns],
            )
        self.metrics["candidate_create_count"] += 1
        return publication

    def set_status(self, foundation_publication_id: str, status: str, *, validated_at: str | None = None, failure_reason: str | None = None) -> None:
        """Update a *candidate* state. Refuses to touch CURRENT via this path."""
        if status == CURRENT:
            raise PublicationBoundaryError("set_status cannot set CURRENT; use logical_commit")
        with self.connection_factory() as connection:
            if validated_at is not None:
                connection.execute(
                    f"UPDATE {self.publications_table} SET status = ?, validated_at = ? WHERE foundation_publication_id = ?",
                    [status, validated_at, foundation_publication_id],
                )
            else:
                connection.execute(
                    f"UPDATE {self.publications_table} SET status = ?, failure_reason = COALESCE(?, failure_reason) WHERE foundation_publication_id = ?",
                    [status, failure_reason, foundation_publication_id],
                )

    def update_components(self, foundation_publication_id: str, components: dict[str, ComponentReference], *, source_as_of: str | None = None, validation_status: str | None = None, manifest: dict[str, Any] | None = None) -> None:
        publication = self.get(foundation_publication_id)
        if publication is None:
            raise PublicationBoundaryError(f"unknown publication {foundation_publication_id}")
        publication.components.update(components)
        if source_as_of is not None:
            publication.source_as_of = source_as_of
        if validation_status is not None:
            publication.validation_status = validation_status
        if manifest is not None:
            publication.manifest = manifest
        row = publication.as_row()
        with self.connection_factory() as connection:
            connection.execute(
                f"UPDATE {self.publications_table} SET reference_version = ?, sales_publication_id = ?, credit_memo_publication_id = ?, "
                "oinm_publication_id = ?, oitw_publication_id = ?, source_as_of = ?, "
                "reference_source_as_of = ?, sales_source_as_of = ?, credit_memo_source_as_of = ?, oinm_source_as_of = ?, oitw_source_as_of = ?, "
                "component_count = ?, component_hash = ?, validation_status = ?, manifest_json = ? "
                "WHERE foundation_publication_id = ?",
                [
                    row["reference_version"], row["sales_publication_id"], row["credit_memo_publication_id"], row["oinm_publication_id"],
                    row["oitw_publication_id"], row["source_as_of"], row["reference_source_as_of"],
                    row["sales_source_as_of"], row["credit_memo_source_as_of"], row["oinm_source_as_of"], row["oitw_source_as_of"],
                    row["component_count"], row["component_hash"], row["validation_status"],
                    row["manifest_json"], foundation_publication_id,
                ],
            )

    def mark_failed(self, foundation_publication_id: str, reason: str) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                f"UPDATE {self.publications_table} SET status = ?, failure_reason = ? "
                "WHERE foundation_publication_id = ? AND status != ?",
                [FAILED, reason, foundation_publication_id, CURRENT],
            )

    # -- the logical commit ----------------------------------------------

    def logical_commit(self, foundation_publication_id: str, *, accredit=None) -> dict[str, Any]:
        """Atomically make ``foundation_publication_id`` the one CURRENT publication.

        One transaction against the metadata catalog:

        1. previous CURRENT -> SUPERSEDED
        2. candidate -> CURRENT (committed_at set)
        3. the single current pointer row -> candidate
        4. publisher accreditation gates and receipt, when supplied

        Steps remain invisible to concurrent readers until COMMIT. Once an
        accredited CURRENT exists, subsequent commits require accreditation.

        If anything fails, the transaction rolls back and the previous pointer
        and statuses remain exactly as before (``CURRENT=A``). It never rewrites
        facts. Committing sets ``CURRENT=B`` with all components already
        recorded as belonging to B.
        """
        with self.connection_factory() as connection:
            self._ensure(connection)
            try:
                connection.execute("BEGIN")
                candidate_row = connection.execute(
                    f"SELECT {_SELECT_COLUMNS} FROM {self.publications_table} WHERE foundation_publication_id = ?",
                    [foundation_publication_id],
                ).fetchone()
                if candidate_row is None:
                    raise PublicationBoundaryError(f"unknown candidate {foundation_publication_id}")
                candidate = _row_to_publication(candidate_row)
                if candidate.status == CURRENT:
                    if accredit is not None:
                        from .foundation_read_binding import validate_binding
                        encoded = connection.execute(
                            f'SELECT read_binding_json FROM {self.publications_table} WHERE foundation_publication_id = ?',
                            [foundation_publication_id],
                        ).fetchone()
                        if not encoded or not encoded[0]:
                            raise PublicationBoundaryError('CURRENT_REACCREDITATION_REQUIRED')
                        validate_binding(candidate, json.loads(encoded[0]))
                    connection.execute("ROLLBACK")
                    return {"status": "ALREADY_CURRENT", "foundation_publication_id": foundation_publication_id}
                if candidate.status not in (READY_TO_COMMIT, PREPARING, VALIDATING):
                    raise PublicationBoundaryError(
                        f"candidate {foundation_publication_id} is {candidate.status}; only a validated candidate may commit"
                    )
                if candidate.component_count != FOUNDATION_COMPONENT_COUNT:
                    raise PublicationBoundaryError(
                        f"candidate {foundation_publication_id} has {candidate.component_count} components, expected {FOUNDATION_COMPONENT_COUNT}"
                    )
                previous_id = self._pointer_on_connection(connection)
                if previous_id != candidate.previous_foundation_publication_id:
                    raise PublicationBoundaryError("publication compare-and-swap failed: CURRENT changed since preparation")
                if previous_id and accredit is None:
                    approved = connection.execute(
                        f'SELECT read_binding_json FROM {self.publications_table} WHERE foundation_publication_id = ?',
                        [previous_id],
                    ).fetchone()
                    if approved and approved[0]:
                        raise PublicationBoundaryError('ATOMIC_ACCREDITATION_REQUIRED')
                # Pre-commit fault points: the transaction has not yet mutated
                # anything, so a failure here rolls back to A with no ambiguity.
                self.inject(CommitFaultPoint.DURING_VALIDATION)
                self.inject(CommitFaultPoint.AFTER_REFERENCE)
                self.inject(CommitFaultPoint.BEFORE_LOGICAL_COMMIT)
                self.inject(CommitFaultPoint.DURING_LOGICAL_COMMIT)
                # 1. previous -> SUPERSEDED (and any other non-terminal CURRENT, fail closed).
                connection.execute(
                    f"UPDATE {self.publications_table} SET status = ? WHERE status = ? AND foundation_publication_id != ?",
                    [SUPERSEDED, CURRENT, foundation_publication_id],
                )
                # 2. candidate -> CURRENT.
                committed_at = utc_now()
                connection.execute(
                    f"UPDATE {self.publications_table} SET status = ?, committed_at = ? WHERE foundation_publication_id = ?",
                    [CURRENT, committed_at, foundation_publication_id],
                )
                # 3. pointer (always exactly one row; replace defensively so a
                # duplicated pointer can never survive the logical commit).
                connection.execute(f"DELETE FROM {self.pointer_table}")
                connection.execute(
                    f"INSERT INTO {self.pointer_table} (slot, foundation_publication_id, updated_at) VALUES (1, ?, ?)",
                    [foundation_publication_id, committed_at],
                )
                if accredit is not None:
                    # The full publisher reader sees our uncommitted selection;
                    # other readers still see the previous approved publication.
                    # No receipt or pointer becomes visible until this COMMIT.
                    from .foundation_read_binding import validate_binding
                    selected = self._current_on_connection(connection)
                    binding = accredit(selected, connection)
                    validate_binding(selected, binding)
                    previous_binding = connection.execute(
                        f'SELECT read_binding_json FROM {self.publications_table} WHERE foundation_publication_id = ?',
                        [foundation_publication_id],
                    ).fetchone()[0]
                    if previous_binding and json.loads(previous_binding) != binding:
                        raise PublicationBoundaryError('READ_BINDING_IMMUTABLE')
                    connection.execute(
                        f'UPDATE {self.publications_table} SET read_binding_json = ? WHERE foundation_publication_id = ?',
                        [json.dumps(binding, sort_keys=True), foundation_publication_id],
                    )
                connection.execute("COMMIT")
                self.metrics["logical_commit_count"] += 1
            except BaseException:
                try:
                    connection.execute("ROLLBACK")
                    self.metrics["logical_commit_rollback_count"] += 1
                except Exception:
                    pass
                raise
        self.inject(CommitFaultPoint.AFTER_LOGICAL_COMMIT)
        return {
            "status": "COMMITTED",
            "foundation_publication_id": foundation_publication_id,
            "previous_foundation_publication_id": previous_id,
            "committed_at": committed_at,
        }

    def logical_rollback(
        self,
        foundation_publication_id: str,
        *,
        expected_current_foundation_publication_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Atomically restore one exact superseded publication.

        This is the rollback arm of the existing logical publication boundary,
        not a second pointer mechanism.  The expected-current argument provides
        compare-and-swap semantics so a concurrent pointer change fails closed.
        """
        with self.connection_factory() as connection:
            self._ensure(connection)
            try:
                connection.execute("BEGIN")
                current_id = self._pointer_on_connection(connection)
                if current_id != expected_current_foundation_publication_id:
                    raise PublicationBoundaryError(
                        "rollback compare-and-swap failed: CURRENT changed"
                    )
                if foundation_publication_id == current_id:
                    connection.execute("ROLLBACK")
                    return {
                        "status": "ALREADY_CURRENT",
                        "foundation_publication_id": foundation_publication_id,
                    }
                target_row = connection.execute(
                    f"SELECT {_SELECT_COLUMNS} FROM {self.publications_table} "
                    "WHERE foundation_publication_id = ?",
                    [foundation_publication_id],
                ).fetchone()
                if target_row is None:
                    raise PublicationBoundaryError(
                        f"unknown rollback target {foundation_publication_id}"
                    )
                target = _row_to_publication(target_row)
                if target.status != SUPERSEDED:
                    raise PublicationBoundaryError(
                        f"rollback target {foundation_publication_id} is {target.status}; "
                        "expected SUPERSEDED"
                    )
                if target.component_count != FOUNDATION_COMPONENT_COUNT:
                    raise PublicationBoundaryError(
                        f"rollback target has {target.component_count} components, "
                        f"expected {FOUNDATION_COMPONENT_COUNT}"
                    )
                source_binding = connection.execute(
                    f'SELECT read_binding_json FROM {self.publications_table} WHERE foundation_publication_id = ?',
                    [current_id],
                ).fetchone()
                target_binding = connection.execute(
                    f'SELECT read_binding_json FROM {self.publications_table} WHERE foundation_publication_id = ?',
                    [foundation_publication_id],
                ).fetchone()
                if source_binding and source_binding[0]:
                    if not target_binding or not target_binding[0]:
                        raise PublicationBoundaryError('ROLLBACK_TARGET_UNACCREDITED')
                    from .foundation_read_binding import validate_binding
                    validate_binding(target, json.loads(target_binding[0]))
                rolled_back_at = utc_now()
                connection.execute(
                    f"UPDATE {self.publications_table} SET status = ?, failure_reason = ? "
                    "WHERE foundation_publication_id = ?",
                    [SUPERSEDED, f"ROLLED_BACK: {reason}", current_id],
                )
                connection.execute(
                    f"UPDATE {self.publications_table} SET status = ?, committed_at = ?, "
                    "failure_reason = NULL WHERE foundation_publication_id = ?",
                    [CURRENT, rolled_back_at, foundation_publication_id],
                )
                connection.execute(f"DELETE FROM {self.pointer_table}")
                connection.execute(
                    f"INSERT INTO {self.pointer_table} "
                    "(slot, foundation_publication_id, updated_at) VALUES (1, ?, ?)",
                    [foundation_publication_id, rolled_back_at],
                )
                connection.execute("COMMIT")
            except BaseException:
                try:
                    connection.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return {
            "status": "ROLLED_BACK",
            "foundation_publication_id": foundation_publication_id,
            "replaced_foundation_publication_id": current_id,
            "rolled_back_at": rolled_back_at,
            "reason": reason,
        }

    def _pointer_on_connection(self, connection: Any) -> str | None:
        row = connection.execute(
            f"SELECT foundation_publication_id FROM {self.pointer_table} WHERE slot = 1"
        ).fetchone()
        return str(row[0]) if row and row[0] is not None else None

    # -- active run lock / stale recovery ---------------------------------

    def acquire_run_lock(self, update_run_id: str, *, owner: str = "manual", stale_after_seconds: int = 6 * 60 * 60) -> dict[str, Any]:
        """Simple single-writer guard backed by the metadata table (spec 38-41).

        If a non-terminal run exists it is either reported as active (abort) or,
        when older than ``stale_after_seconds``, marked ABANDONED. The current
        foundation is never modified by recovery.
        """
        now = utc_now()
        with self.connection_factory() as connection:
            self._ensure(connection)
            try:
                connection.execute("BEGIN")
                row = connection.execute(
                    f"SELECT update_run_id, status, started_at, heartbeat_at FROM {self.run_lock_table} WHERE slot = 1"
                ).fetchone()
                stale = False
                if row is not None and str(row[1]) not in ("COMPLETED", "ABANDONED", "FAILED"):
                    started = str(row[3] or row[2] or now)
                    try:
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds()
                    except ValueError:
                        age = 0
                    if age < stale_after_seconds:
                        connection.execute("ROLLBACK")
                        return {
                            "status": "ACTIVE_UPDATE_RUN_DETECTED",
                            "active_run_id": str(row[0]),
                            "started_at": started,
                            "STALE_CANDIDATE_FOUND": "NO",
                            "current_pointer_unchanged": "YES",
                        }
                    stale = True
                    connection.execute(
                        f"UPDATE {self.run_lock_table} SET status = 'ABANDONED', heartbeat_at = ? WHERE slot = 1",
                        [now],
                    )
                connection.execute(f"DELETE FROM {self.run_lock_table}")
                connection.execute(
                    f"INSERT INTO {self.run_lock_table} (slot, update_run_id, status, started_at, heartbeat_at, owner) "
                    "VALUES (1, ?, 'RUNNING', ?, ?, ?)",
                    [update_run_id, now, now, owner],
                )
                connection.execute("COMMIT")
            except BaseException:
                try:
                    connection.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return {
            "status": "ACQUIRED",
            "update_run_id": update_run_id,
            "STALE_CANDIDATE_FOUND": "YES" if stale else "NO",
            "current_pointer_unchanged": "YES",
        }

    def release_run_lock(self, update_run_id: str, *, status: str = "COMPLETED") -> None:
        with self.connection_factory() as connection:
            self._ensure(connection)
            connection.execute(
                f"UPDATE {self.run_lock_table} SET status = ?, heartbeat_at = ? WHERE slot = 1 AND update_run_id = ?",
                [status, utc_now(), update_run_id],
            )

    def abandon_stale_candidates(self, *, keep_foundation_publication_id: str | None = None) -> list[str]:
        """Mark old PREPARING/VALIDATING/READY_TO_COMMIT candidates ABANDONED.

        Only used when the caller has confirmed a stale run. CURRENT and
        SUPERSEDED rows are never touched; the current pointer is never moved.
        """
        with self.connection_factory() as connection:
            rows = connection.execute(
                f"SELECT foundation_publication_id FROM {self.publications_table} "
                "WHERE status IN (?, ?, ?)",
                [PREPARING, VALIDATING, READY_TO_COMMIT],
            ).fetchall()
            abandoned = [str(row[0]) for row in rows if str(row[0]) != keep_foundation_publication_id]
            for foundation_publication_id in abandoned:
                connection.execute(
                    f"UPDATE {self.publications_table} SET status = ?, failure_reason = 'STALE_CANDIDATE_ABANDONED' "
                    "WHERE foundation_publication_id = ?",
                    [FAILED, foundation_publication_id],
                )
        return abandoned


# ---------------------------------------------------------------------------
# The reader contract (spec sections 11, 52, 53)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CurrentFoundation:
    foundation_publication_id: str
    reference_version: str
    sales_publication_id: str
    credit_memo_publication_id: str
    oinm_publication_id: str
    oitw_publication_id: str
    data_as_of: str | None
    reference_source_as_of: str | None
    sales_source_as_of: str | None
    credit_memo_source_as_of: str | None
    oinm_source_as_of: str | None
    oitw_source_as_of: str | None
    validated_at: str | None
    committed_at: str | None
    component_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "foundation_publication_id": self.foundation_publication_id,
            "reference_version": self.reference_version,
            "sales_publication_id": self.sales_publication_id,
            "credit_memo_publication_id": self.credit_memo_publication_id,
            "oinm_publication_id": self.oinm_publication_id,
            "oitw_publication_id": self.oitw_publication_id,
            "data_as_of": self.data_as_of,
            "reference_source_as_of": self.reference_source_as_of,
            "sales_source_as_of": self.sales_source_as_of,
            "credit_memo_source_as_of": self.credit_memo_source_as_of,
            "oinm_source_as_of": self.oinm_source_as_of,
            "oitw_source_as_of": self.oitw_source_as_of,
            "validated_at": self.validated_at,
            "committed_at": self.committed_at,
            "component_count": self.component_count,
        }


def get_current_foundation(store: FoundationPublicationStore) -> CurrentFoundation:
    """Deterministic, fail-closed access path for future consumers.

    Returns exactly the four components recorded for the single CURRENT
    publication. It never selects "latest available" per dataset. If the
    pointer is missing/corrupt, the publication row is not CURRENT, there is
    more than one CURRENT, or a component is missing, it raises
    :class:`FoundationReaderError` instead of guessing.
    """
    current_count = store.current_count()
    if current_count != 1:
        raise FoundationReaderError(f"CURRENT_PUBLICATION_COUNT={current_count}; expected exactly one")
    pointer_rows = store.pointer_row_count()
    if pointer_rows > 1:
        raise FoundationReaderError(f"current pointer has {pointer_rows} rows; expected at most one (fail closed)")
    pointer_id = store.current_pointer()
    current = store.current_publication()
    if current is None:
        raise FoundationReaderError("no CURRENT foundation publication is resolvable (fail closed)")
    if pointer_id is not None and pointer_id != current.foundation_publication_id:
        raise FoundationReaderError("current pointer is inconsistent with publication state (fail closed)")
    missing = [
        name for name in COMPONENT_NAMES
        if not (current.component(name) and (current.component(name) or ComponentReference(name, None)).publication_id)
    ]
    if missing:
        raise FoundationReaderError(f"current foundation is missing components: {missing} (fail closed)")
    if current.component_count != FOUNDATION_COMPONENT_COUNT:
        raise FoundationReaderError(f"current foundation component_count={current.component_count}; expected {FOUNDATION_COMPONENT_COUNT}")
    return CurrentFoundation(
        foundation_publication_id=current.foundation_publication_id,
        reference_version=current.reference_version or "",
        sales_publication_id=(current.component("sales") or ComponentReference("sales", None)).publication_id or "",
        credit_memo_publication_id=(current.component("credit_memo") or ComponentReference("credit_memo", None)).publication_id or "",
        oinm_publication_id=(current.component("oinm") or ComponentReference("oinm", None)).publication_id or "",
        oitw_publication_id=(current.component("oitw") or ComponentReference("oitw", None)).publication_id or "",
        data_as_of=current.source_as_of,
        reference_source_as_of=(current.component("reference") or ComponentReference("reference", None)).source_as_of,
        sales_source_as_of=(current.component("sales") or ComponentReference("sales", None)).source_as_of,
        credit_memo_source_as_of=(current.component("credit_memo") or ComponentReference("credit_memo", None)).source_as_of,
        oinm_source_as_of=(current.component("oinm") or ComponentReference("oinm", None)).source_as_of,
        oitw_source_as_of=(current.component("oitw") or ComponentReference("oitw", None)).source_as_of,
        validated_at=current.validated_at,
        committed_at=current.committed_at,
        component_count=current.component_count,
    )


# ---------------------------------------------------------------------------
# Candidate build orchestration (small; no framework)
# ---------------------------------------------------------------------------


def build_foundation_publication_id(update_run_id: str, component_hash: str) -> str:
    import hashlib

    return "foundation_" + hashlib.sha256(f"{update_run_id}|{component_hash}".encode()).hexdigest()[:32]


def bootstrap_previous_foundation(
    store: FoundationPublicationStore,
    connector: Any,
    *,
    dataset_table: str = "telchi.ops.initial_publications_v1",
    reference_version: str | None = None,
    source_as_of: str | None = None,
) -> FoundationPublication | None:
    """Represent the already-published foundation as the initial CURRENT A.

    This is a one-time migration aid: before the logical boundary existed, the
    three domain datasets were published in independent transactions with no
    global marker. This reads the latest committed Sales/OINM/OITW publication
    ids from the existing publication table and records them as a single
    CURRENT foundation. It is idempotent: if a CURRENT publication already
    exists, it is returned untouched.
    """
    existing = store.current_publication()
    if existing is not None:
        return existing
    with connector.session(read_only=True) as connection:
        rows = connection.execute(
            f"SELECT idempotency_key, publication_id, published_at FROM {dataset_table} "
            "WHERE status = 'COMMITTED' ORDER BY published_at DESC LIMIT 200"
        ).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for idempotency_key, publication_id, published_at in rows:
        key = str(idempotency_key or "")
        domain = None
        if "|MANUAL_UPDATE|sales|" in key:
            domain = "sales"
        elif "|MANUAL_UPDATE|credit_memo|" in key:
            domain = "credit_memo"
        elif "|MANUAL_UPDATE|inventory_movement|" in key:
            domain = "oinm"
        elif "|MANUAL_UPDATE|inventory|" in key:
            domain = "oitw"
        if domain and domain not in latest:
            latest[domain] = {"publication_id": str(publication_id), "published_at": str(published_at)}
    if len(latest) != 4:
        return None
    candidate = prepare_candidate(store, update_run_id="bootstrap-previous-foundation", reference_version=reference_version)
    components = {
        "reference": ComponentReference("reference", reference_version, source_as_of, None, reference_version),
        "sales": ComponentReference("sales", latest["sales"]["publication_id"], latest["sales"]["published_at"], None, None),
        "credit_memo": ComponentReference("credit_memo", latest["credit_memo"]["publication_id"], latest["credit_memo"]["published_at"], None, None),
        "oinm": ComponentReference("oinm", latest["oinm"]["publication_id"], latest["oinm"]["published_at"], None, None),
        "oitw": ComponentReference("oitw", latest["oitw"]["publication_id"], latest["oitw"]["published_at"], None, None),
    }
    store.update_components(
        candidate.foundation_publication_id, components,
        source_as_of=source_as_of, validation_status="BOOTSTRAP_PREVIOUS_FOUNDATION",
        manifest={"bootstrap": True, "components": {name: c.as_dict() for name, c in components.items()}},
    )
    store.set_status(candidate.foundation_publication_id, READY_TO_COMMIT, validated_at=utc_now())
    store.logical_commit(candidate.foundation_publication_id)
    return store.get(candidate.foundation_publication_id)


def prepare_candidate(
    store: FoundationPublicationStore,
    *,
    update_run_id: str,
    reference_version: str | None,
) -> FoundationPublication:
    """Create a PREPARING candidate bound to the current publication as previous."""
    current = store.current_publication()
    previous_id = current.foundation_publication_id if current else None
    placeholder = FoundationPublication(
        foundation_publication_id="",
        update_run_id=update_run_id,
        status=PREPARING,
        previous_foundation_publication_id=previous_id,
        reference_version=reference_version,
        components={name: ComponentReference(name, None) for name in COMPONENT_NAMES},
    )
    foundation_publication_id = build_foundation_publication_id(update_run_id, placeholder.component_hash())
    placeholder.foundation_publication_id = foundation_publication_id
    store.inject(CommitFaultPoint.BEFORE_CANDIDATE)
    store.create_candidate(placeholder)
    return placeholder


__all__ = [
    "GATE",
    "GLOBAL_PUBLICATION_GATE",
    "PUBLICATIONS_TABLE",
    "CURRENT_POINTER_TABLE",
    "RUN_LOCK_TABLE",
    "COMPONENT_NAMES",
    "FOUNDATION_COMPONENT_COUNT",
    "PREPARING",
    "VALIDATING",
    "READY_TO_COMMIT",
    "CURRENT",
    "FAILED",
    "SUPERSEDED",
    "STATES",
    "TERMINAL_STATES",
    "ComponentReference",
    "FoundationPublication",
    "FoundationPublicationStore",
    "FoundationReaderError",
    "PublicationBoundaryError",
    "InjectedFailure",
    "CommitFaultPoint",
    "get_current_foundation",
    "CurrentFoundation",
    "prepare_candidate",
    "bootstrap_previous_foundation",
    "build_foundation_publication_id",
    "ensure_metadata_schema",
    "utc_now",
]
