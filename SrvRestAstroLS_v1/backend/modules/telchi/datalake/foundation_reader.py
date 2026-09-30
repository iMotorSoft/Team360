"""Fail-closed read access to one committed Telchi Foundation publication.

Productive consumers must enter through :func:`get_current_foundation` (this
module) or one of the ``open_current_*`` helpers.  Atomic relations are pinned
to the DuckLake snapshot in which the selected foundation first became
``CURRENT``.  This matters while a later candidate is being built: querying the
latest Atomic snapshot directly could otherwise observe candidate component
writes before their global logical commit.

``DIRECT_ATOMIC_SQL_UNSAFE_FOR_PRODUCTIVE_FOUNDATION=YES``.  Arbitrary SQL is
not globally blocked, but this module never exposes an unpinned productive
relation and never falls back to a latest component or latest snapshot.
"""
from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .ducklake import DATA_ROOT, DuckLakeConnector
from .foundation_publication import (
    COMPONENT_NAMES,
    CURRENT,
    CurrentFoundation,
    FoundationPublication,
    FoundationPublicationStore,
    FoundationReaderError,
    get_current_foundation as _get_current_foundation_metadata,
)

GATE = "TELCHI_DATALAKE_FOUNDATION_READER_MIGRATION_AND_ACCESS_CONTRACT_V1"
DIRECT_ATOMIC_SQL_UNSAFE_FOR_PRODUCTIVE_FOUNDATION = "YES"

_COMPONENT_TABLES: Mapping[str, tuple[str, ...]] = {
    "sales": ("sales_document", "sales_line"),
    "credit_memo": ("credit_memo_document", "credit_memo_line"),
    "oinm": ("inventory_movement",),
    "oitw": ("inventory_balance",),
    "reference": (),
    "receivables_collections": (
        "receivable_settlement_status",
        "collection_method_fact",
        "commercial_term_classification",
    ),
}


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


@dataclass(frozen=True)
class FoundationAccess:
    """Resolved global publication plus immutable physical read references."""

    foundation: CurrentFoundation
    ducklake_snapshot_id: int
    foundation_resolution_ms: float
    reference_path: Path
    manifest: Mapping[str, Any]
    manifest_base_snapshot_id: int

    @property
    def foundation_publication_id(self) -> str:
        return self.foundation.foundation_publication_id

    @property
    def foundation_data_as_of(self) -> str | None:
        return self.foundation.data_as_of

    def relation(self, component: str, table: str) -> str:
        """Return a relation pinned to this foundation's commit snapshot."""
        allowed = _COMPONENT_TABLES.get(component)
        if allowed is None or table not in allowed:
            raise FoundationReaderError(
                f"table {table!r} is not part of foundation component {component!r}"
            )
        if component == "receivables_collections":
            entry = (self.manifest.get("components") or {}).get(component)
            datasets = entry.get("datasets") if isinstance(entry, dict) else None
            if not isinstance(datasets, dict) or table not in datasets:
                raise FoundationReaderError(
                    f"Receivables & Collections dataset {table!r} is not pinned"
                )
            return (
                f"(SELECT * FROM telchi.business.{_quoted(table)} "
                f"AT (VERSION => {int(self.manifest_base_snapshot_id)}))"
            )
        return (
            f"(SELECT * FROM telchi.atomic.{_quoted(table)} "
            f"AT (VERSION => {int(self.ducklake_snapshot_id)}))"
        )

    def sales(self, table: str) -> str:
        return self.relation("sales", table)

    def credit_memo(self, table: str) -> str:
        return self.relation("credit_memo", table)

    def oinm(self) -> str:
        return self.relation("oinm", "inventory_movement")

    def oitw(self) -> str:
        return self.relation("oitw", "inventory_balance")

    def receivables_collections(self, table: str) -> str:
        return self.relation("receivables_collections", table)

    def reference(self, dataset: str) -> Path:
        if not dataset or "/" in dataset or "\\" in dataset:
            raise FoundationReaderError("reference dataset must be a simple name")
        path = self.reference_path / dataset / "part-00000.parquet"
        if not path.is_file():
            raise FoundationReaderError(
                f"reference dataset {dataset!r} is absent from {self.foundation.reference_version}"
            )
        return path

    def as_dict(self) -> dict[str, Any]:
        result = self.foundation.as_dict()
        result.update(
            {
                "foundation_data_as_of": self.foundation_data_as_of,
                "ducklake_snapshot_id": self.ducklake_snapshot_id,
                "foundation_resolution_ms": self.foundation_resolution_ms,
                "reference_path": str(self.reference_path),
                "manifest_base_snapshot_id": self.manifest_base_snapshot_id,
                "logical_manifest_components": sorted((self.manifest.get("components") or {}).keys()),
                "FOUNDATION_PUBLICATION_ID_USED": self.foundation_publication_id,
            }
        )
        return result


@dataclass
class FoundationComponentSession:
    """One read-only connection and one already-resolved foundation binding."""

    connection: Any
    access: FoundationAccess
    component: str

    @property
    def foundation_publication_id(self) -> str:
        return self.access.foundation_publication_id

    def relation(self, table: str | None = None) -> str:
        if self.component == "sales":
            if table is None:
                raise FoundationReaderError("Sales requires sales_document or sales_line")
            return self.access.sales(table)
        if self.component == "credit_memo":
            if table is None:
                raise FoundationReaderError("Credit Memo requires credit_memo_document or credit_memo_line")
            return self.access.credit_memo(table)
        if self.component == "oinm":
            return self.access.oinm()
        if self.component == "oitw":
            return self.access.oitw()
        if self.component == "receivables_collections":
            if table is None:
                raise FoundationReaderError("Receivables & Collections requires an exact dataset")
            return self.access.receivables_collections(table)
        raise FoundationReaderError("Reference is file-backed; use reference(dataset)")

    def reference(self, dataset: str) -> Path:
        if self.component != "reference":
            raise FoundationReaderError("reference(dataset) is only valid for Reference")
        return self.access.reference(dataset)


SnapshotResolver = Callable[[Any, str], int]
ComponentVerifier = Callable[[Any, FoundationPublication, int], None]


class FoundationReader:
    """Canonical access root for coherent Foundation reads."""

    def __init__(
        self,
        connector: DuckLakeConnector | Any | None = None,
        *,
        snapshot_resolver: SnapshotResolver | None = None,
        component_verifier: ComponentVerifier | None = None,
        verify_reference_path: bool = True,
        metadata_catalog: str = "telchi",
    ) -> None:
        self.connector = connector or DuckLakeConnector()
        self.snapshot_resolver = snapshot_resolver or _resolve_commit_snapshot
        self.component_verifier = component_verifier or _verify_component_publications
        self.verify_reference_path = verify_reference_path
        self.metadata_catalog = metadata_catalog

    def resolve_on(self, connection: Any) -> FoundationAccess:
        started = time.perf_counter()

        @contextlib.contextmanager
        def same_connection() -> Iterator[Any]:
            yield connection

        store = FoundationPublicationStore(same_connection, catalog=self.metadata_catalog)
        current_count = store.current_count()
        if current_count != 1:
            raise FoundationReaderError(
                f"CURRENT_PUBLICATION_COUNT={current_count}; expected exactly one"
            )
        foundation = _get_current_foundation_metadata(store)
        publication = store.get(foundation.foundation_publication_id)
        if publication is None or publication.status != CURRENT:
            raise FoundationReaderError("CURRENT publication disappeared during resolution")
        _validate_manifest(publication, foundation)
        snapshot_id = int(self.snapshot_resolver(connection, foundation.foundation_publication_id))
        self.component_verifier(connection, publication, snapshot_id)
        base_snapshot_id = publication.manifest.get("base_snapshot_id")
        if not isinstance(base_snapshot_id, int):
            raise FoundationReaderError("foundation manifest base snapshot is missing (fail closed)")
        reference_path = DATA_ROOT / "reference" / "_versions" / foundation.reference_version
        if self.verify_reference_path and not reference_path.is_dir():
            raise FoundationReaderError(
                f"Reference {foundation.reference_version!r} has no immutable version directory"
            )
        return FoundationAccess(
            foundation=foundation,
            ducklake_snapshot_id=snapshot_id,
            foundation_resolution_ms=round((time.perf_counter() - started) * 1000, 3),
            reference_path=reference_path,
            manifest=publication.manifest,
            manifest_base_snapshot_id=base_snapshot_id,
        )

    def get_current_foundation(self) -> FoundationAccess:
        with self.connector.session(read_only=True) as connection:
            return self.resolve_on(connection)

    @contextlib.contextmanager
    def open_component(self, component: str) -> Iterator[FoundationComponentSession]:
        if component not in _COMPONENT_TABLES:
            raise FoundationReaderError(f"unknown foundation component {component!r}")
        with self.connector.session(read_only=True) as connection:
            access = self.resolve_on(connection)
            yield FoundationComponentSession(connection, access, component)


def _validate_manifest(
    publication: FoundationPublication, foundation: CurrentFoundation
) -> None:
    manifest = publication.manifest
    if not isinstance(manifest, dict) or not manifest:
        raise FoundationReaderError("foundation manifest is missing or corrupt (fail closed)")
    if manifest.get("foundation_publication_id") not in (
        None,
        foundation.foundation_publication_id,
    ):
        raise FoundationReaderError("foundation manifest publication id mismatch")
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise FoundationReaderError("foundation manifest components are missing or corrupt")
    expected = {
        "reference": foundation.reference_version,
        "sales": foundation.sales_publication_id,
        "credit_memo": foundation.credit_memo_publication_id,
        "oinm": foundation.oinm_publication_id,
        "oitw": foundation.oitw_publication_id,
    }
    for name, publication_id in expected.items():
        component = components.get(name)
        if not isinstance(component, dict) or component.get("publication_id") != publication_id:
            raise FoundationReaderError(
                f"foundation manifest component mismatch: {name} (fail closed)"
            )


def _snapshot_has_current(connection: Any, snapshot_id: int, foundation_id: str) -> bool:
    try:
        publication = connection.execute(
            "SELECT status FROM telchi.ops.foundation_publications_v1 "
            f"AT (VERSION => {int(snapshot_id)}) WHERE foundation_publication_id = ?",
            [foundation_id],
        ).fetchone()
        pointer = connection.execute(
            "SELECT foundation_publication_id FROM telchi.ops.foundation_current_v1 "
            f"AT (VERSION => {int(snapshot_id)}) WHERE slot = 1",
        ).fetchall()
    except Exception:
        return False
    return (
        publication is not None
        and publication[0] == CURRENT
        and len(pointer) == 1
        and str(pointer[0][0]) == foundation_id
    )


def _resolve_commit_snapshot(connection: Any, foundation_id: str) -> int:
    """Find the first DuckLake snapshot where this foundation was CURRENT.

    The predicate for the currently selected publication is monotonic: false
    before its logical commit and true afterwards.  Binary search avoids a scan
    over every historical snapshot and deliberately chooses the first true
    snapshot, never the latest snapshot.
    """
    rows = connection.execute(
        "SELECT snapshot_id FROM ducklake_snapshots('telchi') ORDER BY snapshot_id"
    ).fetchall()
    snapshot_ids = [int(row[0]) for row in rows]
    if not snapshot_ids:
        raise FoundationReaderError("DuckLake has no snapshots (fail closed)")
    low, high = 0, len(snapshot_ids) - 1
    first: int | None = None
    while low <= high:
        middle = (low + high) // 2
        snapshot_id = snapshot_ids[middle]
        if _snapshot_has_current(connection, snapshot_id, foundation_id):
            first = snapshot_id
            high = middle - 1
        else:
            low = middle + 1
    if first is None or not _snapshot_has_current(connection, first, foundation_id):
        raise FoundationReaderError(
            "CURRENT foundation has no coherent DuckLake commit snapshot (fail closed)"
        )
    return first


def _verify_component_publications(
    connection: Any, publication: FoundationPublication, snapshot_id: int
) -> None:
    expected = {
        "sales": publication.sales_publication_id,
        "credit_memo": publication.credit_memo_publication_id,
        "oinm": publication.oinm_publication_id,
        "oitw": publication.oitw_publication_id,
    }
    for component, publication_id in expected.items():
        if not publication_id:
            raise FoundationReaderError(f"foundation component {component} is missing")
        row = connection.execute(
            "SELECT idempotency_key, status, snapshot_id "
            "FROM telchi.ops.initial_publications_v1 "
            f"AT (VERSION => {int(snapshot_id)}) WHERE publication_id = ?",
            [publication_id],
        ).fetchone()
        if row is None or row[1] != "COMMITTED":
            raise FoundationReaderError(
                f"component publication {component}={publication_id} is not committed in foundation snapshot"
            )
        component_snapshot = int(row[2])
        if component_snapshot > snapshot_id:
            raise FoundationReaderError(
                f"component publication {component} postdates its foundation snapshot"
            )
        key = str(row[0] or "")
        domain_markers = (
            {
                "sales": "|MANUAL_UPDATE|sales|",
                "credit_memo": "|MANUAL_UPDATE|credit_memo|",
                "oinm": "|MANUAL_UPDATE|inventory_movement|",
                "oitw": "|MANUAL_UPDATE|inventory|",
            },
            {
                "sales": "FOUNDATION_INITIAL|sales|",
                "credit_memo": "FOUNDATION_INITIAL|credit_memo|",
                "oinm": "FOUNDATION_INITIAL|oinm|",
                "oitw": "FOUNDATION_INITIAL|oitw|",
            },
        )
        if not any(markers[component] in key for markers in domain_markers):
            raise FoundationReaderError(
                f"component publication {publication_id} has wrong domain binding"
            )


def get_current_foundation(
    connector: DuckLakeConnector | Any | None = None,
) -> FoundationAccess:
    """Resolve the sole CURRENT foundation; never infer an implicit latest."""
    return FoundationReader(connector).get_current_foundation()


@contextlib.contextmanager
def open_current_sales(
    connector: DuckLakeConnector | Any | None = None,
) -> Iterator[FoundationComponentSession]:
    with FoundationReader(connector).open_component("sales") as session:
        yield session


@contextlib.contextmanager
def open_current_credit_memo(
    connector: DuckLakeConnector | Any | None = None,
) -> Iterator[FoundationComponentSession]:
    with FoundationReader(connector).open_component("credit_memo") as session:
        yield session


@contextlib.contextmanager
def open_current_oinm(
    connector: DuckLakeConnector | Any | None = None,
) -> Iterator[FoundationComponentSession]:
    with FoundationReader(connector).open_component("oinm") as session:
        yield session


@contextlib.contextmanager
def open_current_oitw(
    connector: DuckLakeConnector | Any | None = None,
) -> Iterator[FoundationComponentSession]:
    with FoundationReader(connector).open_component("oitw") as session:
        yield session


@contextlib.contextmanager
def open_current_reference(
    connector: DuckLakeConnector | Any | None = None,
) -> Iterator[FoundationComponentSession]:
    with FoundationReader(connector).open_component("reference") as session:
        yield session


@contextlib.contextmanager
def open_current_receivables_collections(
    connector: DuckLakeConnector | Any | None = None,
) -> Iterator[FoundationComponentSession]:
    with FoundationReader(connector).open_component("receivables_collections") as session:
        yield session


__all__ = [
    "DIRECT_ATOMIC_SQL_UNSAFE_FOR_PRODUCTIVE_FOUNDATION",
    "FoundationAccess",
    "FoundationComponentSession",
    "FoundationReader",
    "get_current_foundation",
    "open_current_sales",
    "open_current_credit_memo",
    "open_current_oinm",
    "open_current_oitw",
    "open_current_reference",
    "open_current_receivables_collections",
]
