"""Synthetic-only regression: no production paths, catalogs or SAP calls."""
from __future__ import annotations

import contextlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import duckdb
import pytest

from modules.telchi.datalake import foundation_publication as fp
from modules.telchi.datalake import reference_update as ru
from modules.telchi.datalake import update
from modules.telchi.datalake import foundation_reader as reader
from modules.telchi.datalake.foundation_manifest import _hash, validate_manifest
from modules.telchi.datalake.reference_compatibility import reference_projection
from modules.telchi.datalake import receivables_collections_foundation as rc
from .test_reference_update import _make_root
from .test_receivables_collections_foundation import base, component


@pytest.fixture(autouse=True)
def no_sap(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("SAP access forbidden in offline tests")
    monkeypatch.setattr(ru.HanaReadOnlySource, "__init__", forbidden)


@pytest.mark.parametrize("code,label,state,status", [
    ("0", "NINGUNA", None, "UNCLASSIFIED"),
    ("1", "LIQUIDO", "LIQUID", "CLASSIFIED"),
    ("2", "SEMI-SOLIDO", "SEMISOLID", "CLASSIFIED"),
    ("3", "SOLIDO", "SOLID", "CLASSIFIED"),
    ("4", "MEDICAMENTO", None, "NOT_PHYSICAL"),
    ("5", "NO CORRESPONDE", None, "NOT_APPLICABLE"),
    (None, None, None, "MISSING"), ("", None, None, "MISSING"),
    ("  ", None, None, "MISSING"), ("99", None, None, "UNKNOWN"),
    ("01", None, None, "UNKNOWN"), (" 1 ", None, None, "UNKNOWN"),
])
def test_dictionary(code, label, state, status, tmp_path):
    result = ru.physical_classification(code, "observed")
    assert result["sap_forma_farmac_code"] == code
    assert result["physical_classification_label"] == label
    assert result["physical_state"] == state
    assert result["physical_classification_status"] == status
    assert result["physical_classification_observed_at"] == "observed"
    path = tmp_path / "test.parquet"
    ru.write_parquet(path, list(ru.PHYSICAL_FIELDS), ["VARCHAR"] * len(ru.PHYSICAL_FIELDS), [result])
    assert ru.read_parquet_rows(path)[2] == [result]


def test_classification_only_new_version_real_noop_and_commercial_preserved(tmp_path):
    root, fixtures = _make_root(tmp_path)
    first = ru.run_reference_update(data_root=root, fixture_dir=fixtures, evidence_root=tmp_path / "e1")
    pointer = json.loads((root / "manifests/reference_current.json").read_text())
    old = Path(pointer["reference_path"])
    # Enrich the isolated baseline as a curated publication would do.
    path = old / "products/part-00000.parquet"
    columns, types, rows = ru.read_parquet_rows(path)
    columns.append("commercial_category"); types.append("VARCHAR")
    rows[0]["commercial_category"] = "EXCIPIENT"
    ru.write_parquet(path, columns, types, rows)
    fixture_path = fixtures / "OITM.json"
    source = json.loads(fixture_path.read_text()); source[0]["U_FormaFarmac"] = "1"
    fixture_path.write_text(json.dumps(source))
    second = ru.run_reference_update(data_root=root, fixture_dir=fixtures, evidence_root=tmp_path / "e2")
    assert first["REFERENCE_NEW_VERSION"] != second["REFERENCE_NEW_VERSION"]
    assert second["PRODUCTS_SAP_ATTRIBUTE_CHANGED"] == 1
    new_pointer = json.loads((root / "manifests/reference_current.json").read_text())
    new = Path(new_pointer["reference_path"])
    result = ru.read_parquet_rows(new / "products/part-00000.parquet")[2][0]
    assert result["canonical_product_id"] == rows[0]["canonical_product_id"]
    assert result["commercial_category"] == "EXCIPIENT"
    assert result["physical_state"] == "LIQUID"
    reference_projection(old, new)
    # Formatting/location changes to a fixture do not generate versions.
    fixture_path.write_text(json.dumps(source, indent=4))
    third = ru.run_reference_update(data_root=root, fixture_dir=fixtures, evidence_root=tmp_path / "e3")
    assert third["REFERENCE_SECOND_RUN_NOOP"] == "YES"
    assert third["REFERENCE_NEW_VERSION"] == second["REFERENCE_NEW_VERSION"]
    assert ru.read_parquet_rows(path)[2] == rows


def test_identity_validation_rejects_duplicates_remaps_and_cross_source_merge():
    refs = [{"source_system": "SAP_HANA", "source_native_id": "P", "canonical_product_id": "stable"}]
    cw = [{"source_system": "SAP_HANA", "source_native_id": "P", "canonical_id": "stable"}]
    ru.validate_identity("product", refs, cw, refs, cw)
    for bad_refs, bad_cw in ((refs * 2, cw), (refs, cw * 2),
                             (refs, [{**cw[0], "canonical_id": "remapped"}]),
                             (refs + [{**refs[0], "source_system": "LEGACY_DS"}], cw)):
        with pytest.raises(RuntimeError):
            ru.validate_identity("product", bad_refs, bad_cw, refs, cw)


@pytest.fixture
def eight(tmp_path, monkeypatch):
    db = duckdb.connect(config={"threads": 2})
    @contextlib.contextmanager
    def factory():
        yield db
    store = fp.FoundationPublicationStore(factory, catalog="")
    store.ensure_schema()
    six = base(store)
    seven = rc.create_candidate(store, base_publication=six, base_snapshot_id=84,
                               component=component(), update_run_id="seven", candidate_created_at="created")
    rc.mark_ready(store, seven.foundation_publication_id)
    store.logical_commit(seven.foundation_publication_id)
    seven = store.current_publication()
    stable = {"contract_version": "1.0.0", "schema_version": "1.0.0",
              "source_provenance": {"fixture": "synthetic"}, "dataset_hashes": {"purchase": "a" * 64},
              "dependencies": {"foundation_publication_id": seven.foundation_publication_id,
                               "base_snapshot_id": 84, "reference_version": "ref-v1",
                               "components_hash": _hash(seven.manifest["components"])}}
    from modules.telchi.datalake.purchasing import ATOMIC, DERIVED, VERSION
    stable["lineage_algorithm_version"] = VERSION
    stable["dataset_hashes"] = {name: "a" * 64 for name in ATOMIC + DERIVED}
    sha = _hash(stable)
    purchasing = {"name": "purchasing", "publication_id": "purchasing_" + sha[:24],
                  "component_fingerprint": sha, "content_identity": sha, "stable_contract": stable,
                  "datasets": {name: {"logical_hash": "a" * 64, "file_references": [name + ".parquet"],
                                      "file_hashes": ["b" * 64], "row_count": 1} for name in ATOMIC + DERIVED}}
    from modules.telchi.datalake.purchasing_foundation import create_candidate
    cid = create_candidate(store, base_id=seven.foundation_publication_id, component=purchasing,
                           validation={"gold": "PASS", "parity": "PASS", "invariants": "PASS"}, run_id="eight")
    store.set_status(cid, fp.READY_TO_COMMIT); store.logical_commit(cid)
    root = tmp_path / "data"
    old = root / "reference/_versions/ref-v1"
    new = root / "reference/_versions/ref-v2"
    columns = ["canonical_product_id", "source_system", "source_native_id", "commercial_category"]
    rows = [{"canonical_product_id": "fixed", "source_system": "SAP_HANA", "source_native_id": "P1", "commercial_category": "EXCIPIENT"}]
    ru.write_parquet(old / "products/part-00000.parquet", columns, ["VARCHAR"] * len(columns), rows)
    ru.write_parquet(old / "warehouse_location/part-00000.parquet", ["id"], ["VARCHAR"], [{"id": "enriched"}])
    shutil.copytree(old, new)
    for version in ("ref-v1", "ref-v2"):
        ru.write_parquet(root / "crosswalk/_versions" / version / "product_crosswalk/part-00000.parquet",
            ["source_system", "source_native_id", "canonical_id"], ["VARCHAR"] * 3,
            [{"source_system": "SAP_HANA", "source_native_id": "P1", "canonical_id": "fixed"}])
    rows[0].update(ru.physical_classification("1", "observed"))
    columns += list(ru.PHYSICAL_FIELDS)
    ru.write_parquet(new / "products/part-00000.parquet", columns, ["VARCHAR"] * len(columns), rows)
    monkeypatch.setattr(update, "DATA_ROOT", root)
    monkeypatch.setattr(reader, "DATA_ROOT", root)
    yield store, root, new, cid
    db.close()


def publish(eight, fault=None):
    store, _, new, _ = eight
    return update.publish_reference_only(connector=None, foundation_store=store,
        reference={"reference_version": "ref-v2", "reference_path": str(new), "source_as_of": "observed"},
        fault_point=fault, base_data_snapshot_id=84)


def test_eight_preserved_readers_snapshots_history_and_idempotence(eight):
    store, root, new, old_id = eight
    old = store.get(old_id)
    old_manifest = deepcopy(old.manifest)
    validate_manifest(store, old)
    assert publish(eight)["status"] == "COMMITTED"
    current = store.current_publication()
    assert len(validate_manifest(store, current)) == 8
    for name, entry in old_manifest["components"].items():
        if name != "reference":
            assert current.manifest["components"][name] == entry
    assert current.manifest["base_snapshot_id"] == 84
    assert rc.resolve_current(store).snapshot_id == 84
    from modules.telchi.datalake.material_supply_candidate import resolve_current_material_supply
    assert resolve_current_material_supply(store).snapshot_id == 84
    seen = []
    access_reader = reader.FoundationReader(snapshot_resolver=lambda *_: 999,
        component_verifier=lambda connection, publication, snapshot: seen.append(snapshot), metadata_catalog="")
    with store.connection_factory() as connection:
        access = access_reader.resolve_on(connection)
    assert access.ducklake_snapshot_id == 84 and seen == [84]
    assert "VERSION => 84" in access.sales("sales_line")
    assert access.reference("warehouse_location").is_file()
    assert publish(eight)["status"] == "NOOP"
    assert store.current_pointer() == current.foundation_publication_id
    assert store.get(old_id).manifest == old_manifest
    assert validate_manifest(store, store.get(old_id)) == old_manifest["components"]


@pytest.mark.parametrize("fault", [fp.CommitFaultPoint.DURING_VALIDATION,
    fp.CommitFaultPoint.AFTER_REFERENCE, fp.CommitFaultPoint.BEFORE_LOGICAL_COMMIT,
    fp.CommitFaultPoint.DURING_LOGICAL_COMMIT])
def test_reference_only_faults_rollback_and_retry(eight, fault):
    store, _, _, old_id = eight
    before = deepcopy(store.get(old_id).manifest)
    with pytest.raises(fp.InjectedFailure):
        publish(eight, fault)
    assert store.current_pointer() == old_id and store.current_count() == 1
    assert store.get(old_id).manifest == before
    assert publish(eight)["status"] == "COMMITTED"
    assert publish(eight)["status"] == "NOOP"


@pytest.mark.parametrize("damage", ["commercial", "missing_dataset", "schema", "identity", "purchasing_contract", "crosswalk", "physical"])
def test_incompatible_reference_or_contract_rejected_before_commit(eight, damage):
    store, _, new, old_id = eight
    if damage == "missing_dataset":
        (new / "warehouse_location/part-00000.parquet").unlink()
    elif damage == "purchasing_contract":
        publication = store.get(old_id)
        publication.manifest["components"]["purchasing"]["stable_contract"]["dependencies"]["reference_version"] = "wrong"
        store.update_components(old_id, publication.components, manifest=publication.manifest)
    elif damage == "crosswalk":
        path = new.parents[2] / "crosswalk/_versions/ref-v2/product_crosswalk/part-00000.parquet"
        columns, types, rows = ru.read_parquet_rows(path)
        rows[0]["canonical_id"] = "WRONG"
        ru.write_parquet(path, columns, types, rows)
    else:
        path = new / "products/part-00000.parquet"
        columns, types, rows = ru.read_parquet_rows(path)
        if damage == "physical": rows[0]["physical_state"] = "SOLID"
        if damage == "commercial": rows[0]["commercial_category"] = "WRONG"
        if damage == "identity": rows[0]["canonical_product_id"] = "REMAPPED"
        if damage == "schema": columns.remove("commercial_category"); types.pop()
        ru.write_parquet(path, columns, types, rows)
    with pytest.raises((fp.FoundationReaderError, update.UpdateAbort)):
        publish(eight)
    assert store.current_pointer() == old_id and store.current_count() == 1
    with store.connection_factory() as db:
        assert db.execute("SELECT count(*) FROM ops.foundation_publications_v1 WHERE status='FAILED'").fetchone()[0] == 1


def test_five_component_reference_only_refresh(eight):
    store, _, _, old_id = eight
    old = store.get(old_id)
    manifest = {"foundation_publication_id": old_id, "base_snapshot_id": 84,
                "components": {name: entry for name, entry in old.manifest["components"].items() if name in fp.COMPONENT_NAMES}}
    store.update_components(old_id, old.components, manifest=manifest)
    assert publish(eight)["status"] == "COMMITTED"
    assert len(validate_manifest(store, store.current_publication())) == 5
    assert publish(eight)["status"] == "NOOP"


def test_fact_delta_with_sealed_dependencies_is_rejected(eight):
    store, _, new, old_id = eight
    candidate = fp.prepare_candidate(store, update_run_id="fact-delta", reference_version="ref-v2")
    with pytest.raises(update.UpdateAbort, match="REVALIDATION_REQUIRED"):
        update.commit_foundation(connector=None, foundation_store=store, candidate=candidate,
            applied={"sales": {"publication_id": "new-sales"}},
            reference={"reference_version": "ref-v2", "reference_path": str(new)},
            source_as_of="t", precommit_validation={"status": "PASS"}, run_id="fact-delta")
    assert store.current_pointer() == old_id
    assert store.get(candidate.foundation_publication_id).status == fp.FAILED


def test_postcommit_interruption_and_explicit_rollback(eight):
    store, _, _, old_id = eight
    with pytest.raises(fp.InjectedFailure):
        publish(eight, fp.CommitFaultPoint.AFTER_LOGICAL_COMMIT)
    committed = store.current_pointer()
    assert committed != old_id and store.current_count() == 1
    assert len(validate_manifest(store, store.current_publication())) == 8
    assert publish(eight)["status"] == "NOOP"
    store.fault_point = None
    store.logical_rollback(old_id, expected_current_foundation_publication_id=committed, reason="offline exercise")
    assert store.current_pointer() == old_id and store.current_count() == 1
    with pytest.raises(fp.PublicationBoundaryError, match="compare-and-swap"):
        store.logical_rollback(committed, expected_current_foundation_publication_id=committed, reason="stale")


def test_stale_candidate_cannot_overwrite_reference_commit(eight):
    store, _, _, old_id = eight
    stale = fp.prepare_candidate(store, update_run_id="stale", reference_version="ref-v1")
    old = store.get(old_id)
    store.update_components(stale.foundation_publication_id, old.components, manifest=old.manifest)
    store.set_status(stale.foundation_publication_id, fp.READY_TO_COMMIT)
    publish(eight)
    committed = store.current_pointer()
    with pytest.raises(fp.PublicationBoundaryError, match="compare-and-swap"):
        store.logical_commit(stale.foundation_publication_id)
    assert store.current_pointer() == committed


def test_new_and_legacy_products_are_source_scoped():
    cols = ["canonical_product_id", "source_system", "source_native_id", "item_code", "canonical_name", "active", "status"] + list(ru.PHYSICAL_FIELDS)
    cw_cols = ["source_system", "source_native_id", "canonical_id", "mapping_source", "confidence", "status"]
    legacy = {"source_system": "LEGACY_DS", "source_native_id": "P1", "canonical_product_id": "legacy-fixed"}
    sap = {"source_system": "SAP_HANA", "source_native_id": "P1", "canonical_product_id": "sap-curated"}
    old_cw = [{"source_system": row["source_system"], "source_native_id": "P1", "canonical_id": row["canonical_product_id"]} for row in (legacy, sap)]
    source = [{"ItemCode": "P1", "ItemName": "Same name", "U_FormaFarmac": "4", "_source_extracted_at": "observed"},
              {"ItemCode": "P2", "ItemName": "Same name", "U_FormaFarmac": "99", "_source_extracted_at": "observed"}]
    rows, cw, metrics = ru.merge_entity("product", source, [legacy, sap], cols, old_cw, cw_cols)
    ru.validate_identity("product", rows, cw, [legacy, sap], old_cw)
    assert metrics["new"] == 1
    assert next(r for r in rows if r["source_system"] == "LEGACY_DS") == legacy
    assert {r["canonical_product_id"] for r in rows} == {"legacy-fixed", "sap-curated", ru.canonical_id("product", "P2")}
    assert next(r for r in rows if r.get("source_native_id") == "P2")["physical_classification_status"] == "UNKNOWN"
    assert next(r for r in rows if r.get("canonical_product_id") == "sap-curated")["physical_state"] is None


def test_static_sap_cost_is_one_added_column_only():
    assert '"U_FormaFarmac"' in ru.OITM_SQL
    assert ru.OITM_SQL.count("SELECT") == 1 and "JOIN" not in ru.OITM_SQL
    assert ru.SAP_TABLES == ("OITM", "OCRD", "OWHS", "OSLP")
