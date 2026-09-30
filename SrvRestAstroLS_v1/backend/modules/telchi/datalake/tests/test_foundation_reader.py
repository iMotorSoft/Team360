from __future__ import annotations

import contextlib
from pathlib import Path

import duckdb
import pytest

from modules.telchi.datalake.foundation_publication import (
    CURRENT,
    READY_TO_COMMIT,
    ComponentReference,
    FoundationPublicationStore,
    FoundationReaderError,
    prepare_candidate,
)
from modules.telchi.datalake.foundation_reader import FoundationReader, _verify_component_publications
from modules.telchi.datalake.foundation_reader_scan import reader_inventory, scan_direct_reads


class SharedConnector:
    def __init__(self) -> None:
        self.connection = duckdb.connect(":memory:")

    @contextlib.contextmanager
    def session(self, *, read_only: bool = False):
        yield self.connection

    def factory(self):
        @contextlib.contextmanager
        def open_connection():
            yield self.connection

        return open_connection


@pytest.fixture()
def connector() -> SharedConnector:
    return SharedConnector()


@pytest.fixture()
def store(connector: SharedConnector) -> FoundationPublicationStore:
    result = FoundationPublicationStore(connector.factory(), catalog="")
    result.ensure_schema()
    return result


def complete(store: FoundationPublicationStore, suffix: str, *, commit: bool = True):
    candidate = prepare_candidate(store, update_run_id=f"run-{suffix}", reference_version=f"ref-{suffix}")
    components = {
        "reference": ComponentReference("reference", f"ref-{suffix}", f"ref-time-{suffix}"),
        "sales": ComponentReference("sales", f"sales-{suffix}", f"sales-time-{suffix}", 10),
        "credit_memo": ComponentReference("credit_memo", f"credit-{suffix}", f"credit-time-{suffix}", 5),
        "oinm": ComponentReference("oinm", f"oinm-{suffix}", f"oinm-time-{suffix}", 20),
        "oitw": ComponentReference("oitw", f"oitw-{suffix}", f"oitw-time-{suffix}", 30),
    }
    store.update_components(
        candidate.foundation_publication_id,
        components,
        source_as_of=f"foundation-time-{suffix}",
        validation_status="PASS",
        manifest={
            "foundation_publication_id": candidate.foundation_publication_id,
            "base_snapshot_id": 42,
            "components": {name: value.as_dict() for name, value in components.items()},
        },
    )
    store.set_status(candidate.foundation_publication_id, READY_TO_COMMIT, validated_at=f"validated-{suffix}")
    if commit:
        store.logical_commit(candidate.foundation_publication_id)
    return candidate


def reader(connector: SharedConnector) -> FoundationReader:
    return FoundationReader(
        connector,
        snapshot_resolver=lambda _connection, _foundation_id: 42,
        component_verifier=lambda _connection, _publication, _snapshot: None,
        verify_reference_path=False,
        metadata_catalog="",
    )


def test_single_current_resolution_exposes_ids_and_as_of(
    connector: SharedConnector, store: FoundationPublicationStore
) -> None:
    candidate = complete(store, "A")
    access = reader(connector).get_current_foundation()
    assert access.foundation_publication_id == candidate.foundation_publication_id
    assert access.foundation.reference_version == "ref-A"
    assert access.foundation.sales_publication_id == "sales-A"
    assert access.foundation.credit_memo_publication_id == "credit-A"
    assert access.foundation.oinm_publication_id == "oinm-A"
    assert access.foundation.oitw_publication_id == "oitw-A"
    assert access.foundation_data_as_of == "foundation-time-A"
    assert access.foundation.sales_source_as_of == "sales-time-A"
    assert access.foundation.credit_memo_source_as_of == "credit-time-A"
    assert access.foundation.oinm_source_as_of == "oinm-time-A"
    assert access.foundation.oitw_source_as_of == "oitw-time-A"
    assert access.foundation.reference_source_as_of == "ref-time-A"
    assert access.ducklake_snapshot_id == 42


def test_candidate_preparing_and_ready_are_not_visible(
    connector: SharedConnector, store: FoundationPublicationStore
) -> None:
    current = complete(store, "A")
    preparing = prepare_candidate(store, update_run_id="run-preparing", reference_version="ref-B")
    assert reader(connector).get_current_foundation().foundation_publication_id == current.foundation_publication_id
    complete(store, "B", commit=False)
    assert store.get(preparing.foundation_publication_id) is not None
    assert reader(connector).get_current_foundation().foundation_publication_id == current.foundation_publication_id


def test_commit_switch_returns_all_four_components_from_b(
    connector: SharedConnector, store: FoundationPublicationStore
) -> None:
    complete(store, "A")
    candidate_b = complete(store, "B", commit=False)
    before = reader(connector).get_current_foundation()
    assert (before.foundation.reference_version, before.foundation.sales_publication_id, before.foundation.oinm_publication_id, before.foundation.oitw_publication_id) == (
        "ref-A", "sales-A", "oinm-A", "oitw-A"
    )
    store.logical_commit(candidate_b.foundation_publication_id)
    after = reader(connector).get_current_foundation()
    assert (after.foundation.reference_version, after.foundation.sales_publication_id, after.foundation.oinm_publication_id, after.foundation.oitw_publication_id) == (
        "ref-B", "sales-B", "oinm-B", "oitw-B"
    )


def test_no_current_fails_without_latest_fallback(
    connector: SharedConnector, store: FoundationPublicationStore
) -> None:
    complete(store, "candidate", commit=False)
    with pytest.raises(FoundationReaderError):
        reader(connector).get_current_foundation()


def test_multiple_current_fails_closed(
    connector: SharedConnector, store: FoundationPublicationStore
) -> None:
    first = complete(store, "A")
    complete(store, "B")
    with store.connection_factory() as connection:
        connection.execute(
            "UPDATE ops.foundation_publications_v1 SET status=? WHERE foundation_publication_id=?",
            [CURRENT, first.foundation_publication_id],
        )
    with pytest.raises(FoundationReaderError):
        reader(connector).get_current_foundation()


def test_missing_component_in_current_fails_closed(
    connector: SharedConnector, store: FoundationPublicationStore
) -> None:
    candidate = complete(store, "A")
    with store.connection_factory() as connection:
        connection.execute(
            "UPDATE ops.foundation_publications_v1 SET oitw_publication_id=NULL WHERE foundation_publication_id=?",
            [candidate.foundation_publication_id],
        )
    with pytest.raises(FoundationReaderError):
        reader(connector).get_current_foundation()


def test_component_manifest_mismatch_fails_closed(
    connector: SharedConnector, store: FoundationPublicationStore
) -> None:
    candidate = complete(store, "A")
    publication = store.get(candidate.foundation_publication_id)
    assert publication is not None
    publication.manifest["components"]["oinm"]["publication_id"] = "oinm-other"
    with store.connection_factory() as connection:
        connection.execute(
            "UPDATE ops.foundation_publications_v1 SET manifest_json=? WHERE foundation_publication_id=?",
            [__import__("json").dumps(publication.manifest), candidate.foundation_publication_id],
        )
    with pytest.raises(FoundationReaderError, match="oinm"):
        reader(connector).get_current_foundation()


def test_corrupt_manifest_fails_closed(
    connector: SharedConnector, store: FoundationPublicationStore
) -> None:
    candidate = complete(store, "A")
    with store.connection_factory() as connection:
        connection.execute(
            "UPDATE ops.foundation_publications_v1 SET manifest_json='{broken' WHERE foundation_publication_id=?",
            [candidate.foundation_publication_id],
        )
    with pytest.raises(FoundationReaderError, match="manifest"):
        reader(connector).get_current_foundation()


@pytest.mark.parametrize(
    ("component", "table", "expected"),
    [
        ("sales", "sales_document", '(SELECT * FROM telchi.atomic."sales_document" AT (VERSION => 42))'),
        ("sales", "sales_line", '(SELECT * FROM telchi.atomic."sales_line" AT (VERSION => 42))'),
        ("oinm", "inventory_movement", '(SELECT * FROM telchi.atomic."inventory_movement" AT (VERSION => 42))'),
        ("oitw", "inventory_balance", '(SELECT * FROM telchi.atomic."inventory_balance" AT (VERSION => 42))'),
    ],
)
def test_component_readers_use_same_foundation_snapshot(
    connector: SharedConnector,
    store: FoundationPublicationStore,
    component: str,
    table: str,
    expected: str,
) -> None:
    complete(store, "A")
    with reader(connector).open_component(component) as session:
        assert session.foundation_publication_id == reader(connector).get_current_foundation().foundation_publication_id
        assert session.relation(table) == expected


def test_reference_reader_is_bound_to_version_directory(
    connector: SharedConnector, store: FoundationPublicationStore
) -> None:
    complete(store, "A")
    with reader(connector).open_component("reference") as session:
        assert session.access.reference_path.name == "ref-A"
        assert session.foundation_publication_id == session.access.foundation_publication_id


def test_productive_and_shared_static_scan_are_clean() -> None:
    scan = scan_direct_reads()
    assert scan["DIRECT_READ_PATTERNS_PRODUCTIVE"] == 0
    assert scan["PRODUCTIVE_DIRECT_ATOMIC_READERS"] == 0
    assert scan["SHARED_LIBRARY_DIRECT_ATOMIC_READERS"] == 0
    assert scan["UNCLASSIFIED_DIRECT_READS"] == 0


def test_investigation_validation_direct_reads_are_explicitly_allowlisted() -> None:
    inventory = reader_inventory()
    validation = [item for item in inventory if item["path"].startswith("investigation/validation/")]
    assert validation
    assert all(item["classification"] in {"VALIDATION_ONLY", "TEST_ONLY"} for item in validation)
    assert all(item["allowlisted"] for item in validation)


def test_component_publication_verifier_accepts_initial_group_markers():
    class Publication:
        sales_publication_id = "sales-initial"
        credit_memo_publication_id = "credit-initial"
        oinm_publication_id = "oinm-initial"
        oitw_publication_id = "oitw-initial"

    class Connection:
        def execute(self, sql, params):
            component = {
                "sales-initial": "sales",
                "credit-initial": "credit_memo",
                "oinm-initial": "oinm",
                "oitw-initial": "oitw",
            }[params[0]]
            return type("Result", (), {"fetchone": lambda self: (f"FOUNDATION_INITIAL|{component}|run|hash", "COMMITTED", 40)})()

    _verify_component_publications(Connection(), Publication(), 42)


def test_no_implicit_latest_fallback_in_canonical_reader() -> None:
    source = (Path(__file__).parents[1] / "foundation_reader.py").read_text(encoding="utf-8").lower()
    assert "max(publication_id)" not in source
    assert "order by created_at desc limit 1" not in source
    assert "latest available" not in source
