"""Contract tests for the Material Supply Foundation candidate + pinned harness.

In-memory DuckDB only.  Never touches Data Root, DuckLake or CURRENT.
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from modules.telchi.datalake.foundation_publication import (
    FoundationPublicationStore,
    prepare_candidate,
)
from modules.telchi.datalake.material_supply_candidate import (
    CANDIDATE_COMPONENT_NAMES,
    CANDIDATE_KIND,
    MATERIAL_SUPPLY_COMPONENT,
    CandidateValidationError,
    build_material_supply_component,
    create_material_supply_candidate,
    mark_candidate_ready,
    resolve_current_material_supply,
    validate_pinned_candidate,
)


@pytest.fixture()
def store() -> FoundationPublicationStore:
    connection = duckdb.connect(":memory:")

    @contextlib.contextmanager
    def _open():
        yield connection

    result = FoundationPublicationStore(connection_factory=lambda: _open(), catalog="")
    result.ensure_schema()
    return result


def _base_foundation() -> SimpleNamespace:
    return SimpleNamespace(
        reference_version="v2_test", reference_source_as_of="2026-09-24T00:00:00Z",
        sales_publication_id="pub_sales", sales_source_as_of="t",
        credit_memo_publication_id="pub_credit", credit_memo_source_as_of="t",
        oinm_publication_id="pub_oinm", oinm_source_as_of="t",
        oitw_publication_id="pub_oitw", oitw_source_as_of="t",
    )


def _dataset_manifests(tmp_path: Path) -> dict:
    parquet = tmp_path / "part.parquet"
    duckdb.connect().execute(f"COPY (SELECT 1 AS ItemCode) TO '{parquet}' (FORMAT PARQUET)")
    return {
        "material_supply_status": {
            "manifest_path": str(tmp_path / "m.json"), "file_references": [str(parquet)],
            "file_hashes": ["h"], "row_count": 1,
        }
    }


def _create(store, tmp_path, run_id="run-1"):
    manifests = _dataset_manifests(tmp_path)
    component = build_material_supply_component("material_supply_test", manifests, source_as_of="2026-09-24T00:00:00Z")
    return create_material_supply_candidate(
        store, base_foundation=_base_foundation(), base_snapshot_id=42,
        component=component, dataset_manifests=manifests, update_run_id=run_id,
        source_as_of="2026-09-24T00:00:00Z",
    )


def _set_manifest(store, candidate_id, manifest):
    # update_components reads the existing row first, so an empty component map
    # preserves the five base components while replacing the manifest.
    store.update_components(candidate_id, {}, manifest=manifest, validation_status="PENDING")


def test_candidate_pins_six_components_and_validates(store, tmp_path):
    candidate = _create(store, tmp_path)
    pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
    assert tuple(pinned.component_versions) == CANDIDATE_COMPONENT_NAMES
    assert pinned.snapshot_id == 42
    assert pinned.reader_mode == "EXPLICIT_PINNED_VALIDATION"
    assert pinned.dataset_files("material_supply_status")
    assert set(pinned.material_supply_datasets()) == {"material_supply_status"}
    assert pinned.as_dict()["CANDIDATE_VERSION_MIXING"] == "NO"


def test_missing_candidate_fails_closed(store):
    with pytest.raises(CandidateValidationError):
        validate_pinned_candidate(store, "")
    with pytest.raises(CandidateValidationError):
        validate_pinned_candidate(store, "foundation_does_not_exist")


def test_wrong_manifest_kind_fails_closed(store):
    candidate = prepare_candidate(store, update_run_id="k", reference_version=None)
    store.update_components(candidate.foundation_publication_id, {}, manifest={"components": {}}, validation_status="PENDING")
    with pytest.raises(CandidateValidationError):
        validate_pinned_candidate(store, candidate.foundation_publication_id)


def test_component_set_mismatch_fails_closed(store, tmp_path):
    candidate = _create(store, tmp_path)
    publication = store.get(candidate.foundation_publication_id)
    manifest = json.loads(json.dumps(publication.manifest))
    del manifest["components"][MATERIAL_SUPPLY_COMPONENT]
    _set_manifest(store, candidate.foundation_publication_id, manifest)
    with pytest.raises(CandidateValidationError):
        validate_pinned_candidate(store, candidate.foundation_publication_id)


def test_missing_manifest_datasets_fails_closed(store, tmp_path):
    candidate = _create(store, tmp_path)
    publication = store.get(candidate.foundation_publication_id)
    manifest = json.loads(json.dumps(publication.manifest))
    manifest["components"][MATERIAL_SUPPLY_COMPONENT]["datasets"] = {}
    _set_manifest(store, candidate.foundation_publication_id, manifest)
    with pytest.raises(CandidateValidationError):
        validate_pinned_candidate(store, candidate.foundation_publication_id)


def test_missing_parquet_file_fails_closed(store, tmp_path):
    candidate = _create(store, tmp_path)
    publication = store.get(candidate.foundation_publication_id)
    manifest = json.loads(json.dumps(publication.manifest))
    manifest["components"][MATERIAL_SUPPLY_COMPONENT]["datasets"]["material_supply_status"]["file_references"] = [str(tmp_path / "gone.parquet")]
    _set_manifest(store, candidate.foundation_publication_id, manifest)
    pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
    with pytest.raises(CandidateValidationError):
        pinned.dataset_files("material_supply_status")


def test_candidate_version_mismatch_between_row_and_manifest_fails_closed(store, tmp_path):
    candidate = _create(store, tmp_path)
    publication = store.get(candidate.foundation_publication_id)
    manifest = json.loads(json.dumps(publication.manifest))
    manifest["components"]["sales"]["publication_id"] = "pub_tampered"
    _set_manifest(store, candidate.foundation_publication_id, manifest)
    with pytest.raises(CandidateValidationError):
        validate_pinned_candidate(store, candidate.foundation_publication_id)


def test_mark_candidate_ready_never_promotes_current(store, tmp_path):
    candidate = _create(store, tmp_path)
    assert store.current_pointer() is None
    validate_pinned_candidate(store, candidate.foundation_publication_id)
    mark_candidate_ready(store, candidate.foundation_publication_id)
    assert store.get(candidate.foundation_publication_id).status == "READY_TO_COMMIT"
    assert store.current_pointer() is None


def test_productive_reader_resolves_material_supply_only_through_current(store, tmp_path):
    candidate = _create(store, tmp_path)
    mark_candidate_ready(store, candidate.foundation_publication_id)
    store.logical_commit(candidate.foundation_publication_id)
    current = resolve_current_material_supply(store)
    assert current.foundation_publication_id == candidate.foundation_publication_id
    assert current.reader_mode == "PRODUCTIVE_CURRENT"
    assert tuple(current.component_versions) == CANDIDATE_COMPONENT_NAMES
    assert current.dataset_files("material_supply_status")


def test_productive_reader_never_falls_back_to_ready_candidate(store, tmp_path):
    candidate = _create(store, tmp_path)
    mark_candidate_ready(store, candidate.foundation_publication_id)
    with pytest.raises(CandidateValidationError, match="CURRENT"):
        resolve_current_material_supply(store)