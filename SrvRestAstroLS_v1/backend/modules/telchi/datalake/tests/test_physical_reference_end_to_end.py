"""One synthetic extraction through the real Reference builder and Foundation reader."""
from __future__ import annotations

import json
import shutil

import pytest

from copy import deepcopy
from types import SimpleNamespace

from .test_physical_reference_offline import eight, no_sap  # noqa: F401
from .test_reference_update import _make_root
from modules.telchi.datalake import reference_update as ru
from modules.telchi.datalake import update, foundation_reader as reader
from modules.telchi.datalake.foundation_manifest import validate_manifest


def test_simulated_extraction_to_eight_component_reader(eight, tmp_path):
    store, root, _, old_id = eight
    seed = tmp_path / "seed"
    seed.mkdir()
    seed_root, fixtures = _make_root(seed)
    codes = ["0", "1", "2", "3", "4", "5", None, "99", "ABSENT"]
    products = [{"ItemCode": f"P{i}", "ItemName": f"Synthetic {i}", "validFor": "Y", "frozenFor": "N"}
                for i in range(len(codes))]
    (fixtures / "OITM.json").write_text(json.dumps(products))
    ru.run_reference_update(data_root=seed_root, fixture_dir=fixtures, evidence_root=tmp_path / "seed-evidence")
    _, seed_ref, seed_cw = ru.active_pointer(seed_root)
    old_ref = root / "reference/_versions/ref-v1"
    old_cw = root / "crosswalk/_versions/ref-v1"
    shutil.copytree(seed_ref, old_ref, dirs_exist_ok=True)
    shutil.copytree(seed_cw, old_cw, dirs_exist_ok=True)
    product_path = old_ref / "products/part-00000.parquet"
    columns, types, rows = ru.read_parquet_rows(product_path)
    columns.append("commercial_category"); types.append("VARCHAR")
    for row in rows:
        row["commercial_category"] = "CURATED_SYNTHETIC"
    ru.write_parquet(product_path, columns, types, rows)
    ru.write_json(root / "manifests/reference_current.json", {
        "current_reference_version": "ref-v1", "reference_path": str(old_ref), "crosswalk_path": str(old_cw)})
    before_content = ru.digest(ru.version_content(old_ref, old_cw))
    old_manifest = deepcopy(store.get(old_id).manifest)
    for row, code in zip(products, codes):
        if code != "ABSENT":
            row["U_FormaFarmac"] = code
    source_rows = {table: json.loads((fixtures / f"{table}.json").read_text()) for table in ru.SAP_TABLES}
    source_rows["OITM"] = products
    calls = []
    def execute(query_id, sql):
        calls.append((query_id, sql))
        if query_id == "reference_connectivity_select_1":
            return [{"ok": 1}]
        return source_rows[query_id.removeprefix("reference_extract_").upper()]
    simulated = SimpleNamespace(_execute=execute, sap_write_count=0, query_log=[])
    result = ru.run_reference_update(data_root=root, source=simulated, evidence_root=tmp_path / "capture")
    assert len(calls) == 5
    assert [sql for _, sql in calls[1:]] == [ru.OITM_SQL, ru.OCRD_SQL, ru.OWHS_SQL, ru.OSLP_SQL]
    assert result["REFERENCE_NEW_VERSION"] != "ref-v1"
    assert result["PRODUCTS_SAP_ATTRIBUTE_CHANGED"] == 7
    assert store.current_pointer() == old_id  # capture never publishes Foundation
    pointer, new_ref, new_cw = ru.active_pointer(root)
    reference = {"reference_version": pointer["current_reference_version"], "reference_path": str(new_ref),
                 "source_as_of": pointer["source_as_of"]}
    def publish():
        return update.publish_reference_only(connector=None, foundation_store=store, reference=reference,
                                             base_data_snapshot_id=84)
    assert publish()["status"] == "COMMITTED"
    current = store.current_publication()
    assert len(validate_manifest(store, current)) == 8
    for name, entry in old_manifest["components"].items():
        if name != "reference":
            assert current.manifest["components"][name] == entry
    access_reader = reader.FoundationReader(snapshot_resolver=lambda *_: 999,
        component_verifier=lambda *args: None, metadata_catalog="")
    with store.connection_factory() as connection:
        access = access_reader.resolve_on(connection)
    assert access.ducklake_snapshot_id == 84
    actual = ru.read_parquet_rows(access.reference("products"))[2]
    for row in actual:
        i = int(row["source_native_id"][1:])
        expected = ru.physical_classification(None if codes[i] == "ABSENT" else codes[i], pointer["source_as_of"])
        assert all(row[field] == expected[field] for field in ru.PHYSICAL_FIELDS)
        assert row["commercial_category"] == "CURATED_SYNTHETIC"
        assert row["canonical_product_id"] == ru.canonical_id("product", row["source_native_id"])
    assert ru.read_parquet_rows(old_cw / "product_crosswalk/part-00000.parquet")[2] == ru.read_parquet_rows(new_cw / "product_crosswalk/part-00000.parquet")[2]
    assert ru.digest(ru.version_content(old_ref, old_cw)) == before_content
    assert store.get(old_id).manifest == old_manifest
    # Same capture is NOOP even with a later observation timestamp; publication also is NOOP.
    again = ru.run_reference_update(data_root=root, source=simulated, evidence_root=tmp_path / "repeat")
    assert again["REFERENCE_SECOND_RUN_NOOP"] == "YES"
    assert again["REFERENCE_NEW_VERSION"] == result["REFERENCE_NEW_VERSION"]
    assert publish()["status"] == "NOOP"
    assert store.current_pointer() == current.foundation_publication_id


@pytest.mark.parametrize("family", ["reference", "crosswalk"])
def test_interrupted_immutable_copy_fails_closed_until_quarantined(tmp_path, monkeypatch, family):
    root, fixtures = _make_root(tmp_path)
    ru.run_reference_update(data_root=root, fixture_dir=fixtures, evidence_root=tmp_path / "initial")
    pointer = root / "manifests/reference_current.json"
    before = pointer.read_bytes()
    _, old_ref, old_cw = ru.active_pointer(root)
    old_hash = ru.digest(ru.version_content(old_ref, old_cw))
    source_path = fixtures / "OITM.json"
    source = json.loads(source_path.read_text())
    source[0]["U_FormaFarmac"] = "2"
    source_path.write_text(json.dumps(source))
    copytree = ru.shutil.copytree
    interrupted = []
    def partial(src, dst, *args, **kwargs):
        dst = ru.Path(dst)
        if not interrupted and dst.parent == root / family / "_versions":
            dst.mkdir(parents=True)
            # One part only: neither this directory nor its counterpart is trusted.
            path = next(ru.Path(src).rglob("*.parquet"))
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            interrupted.append(dst)
            raise InterruptedError("synthetic interruption during immutable copy")
        return copytree(src, dst, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(ru.shutil, "copytree", partial)
        with pytest.raises(InterruptedError):
            ru.run_reference_update(data_root=root, fixture_dir=fixtures, evidence_root=tmp_path / "interrupted")
    assert pointer.read_bytes() == before
    with pytest.raises(RuntimeError, match="immutable version collision or interrupted preparation"):
        ru.run_reference_update(data_root=root, fixture_dir=fixtures, evidence_root=tmp_path / "retry-blocked")
    assert pointer.read_bytes() == before
    assert ru.digest(ru.version_content(old_ref, old_cw)) == old_hash
    # Isolated recovery exercise only: quarantine, never overwrite a partial target.
    version = interrupted[0].name
    for name in ("reference", "crosswalk"):
        target = root / name / "_versions" / version
        if target.exists():
            target.rename(target.with_name(version + ".quarantined"))
    recovered = ru.run_reference_update(data_root=root, fixture_dir=fixtures, evidence_root=tmp_path / "recovered")
    assert recovered["REFERENCE_NEW_VERSION"] == version
    assert ru.run_reference_update(data_root=root, fixture_dir=fixtures, evidence_root=tmp_path / "noop")["REFERENCE_SECOND_RUN_NOOP"] == "YES"
    assert ru.digest(ru.version_content(old_ref, old_cw)) == old_hash
