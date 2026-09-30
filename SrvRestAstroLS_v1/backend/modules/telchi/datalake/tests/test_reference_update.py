from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.telchi.datalake.reference_update import (
    GATE,
    canonical_id,
    duplicate_guard,
    run_reference_update,
    write_parquet,
)


def _make_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "data"
    reference = root / "reference" / "_versions" / "v2"
    crosswalk = root / "crosswalk" / "_versions" / "v2"
    (root / "manifests").mkdir(parents=True)
    schemas = {
        "products": ["canonical_product_id", "source_system", "source_native_id", "item_code", "canonical_name", "product_name", "active", "status"],
        "customers": ["source_system", "source_native_id", "customer_id", "code", "name", "status"],
        "suppliers": ["source_system", "source_native_id", "supplier_id", "code", "name", "status"],
        "warehouses": ["source_system", "source_native_id", "warehouse_id", "code", "name", "status"],
        "salespersons": ["source_system", "source_native_id", "salesperson_id", "code", "name", "status"],
    }
    for dataset, columns in schemas.items():
        write_parquet(reference / dataset / "part-00000.parquet", columns, ["VARCHAR"] * len(columns), [])
    for dataset in ("product_crosswalk", "customer_crosswalk", "supplier_crosswalk", "warehouse_crosswalk", "salesperson_crosswalk"):
        columns = ["canonical_id", "source_system", "source_native_id", "mapping_source", "confidence", "status"]
        write_parquet(crosswalk / dataset / "part-00000.parquet", columns, ["VARCHAR"] * len(columns), [])
    (root / "manifests" / "reference_current.json").write_text(json.dumps({
        "current_reference_version": "v2",
        "reference_path": str(reference),
        "crosswalk_path": str(crosswalk),
        "previous_version": "v1",
    }), encoding="utf-8")
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "OITM.json").write_text(json.dumps([{"ItemCode": "P1", "ItemName": "Original", "validFor": "Y", "frozenFor": "N"}]), encoding="utf-8")
    (fixture / "OCRD.json").write_text(json.dumps([
        {"CardCode": "C_TEST", "CardName": "AGROTEL", "CardType": "C", "validFor": "Y", "frozenFor": "N"},
        {"CardCode": "S_TEST", "CardName": "AGROTEL", "CardType": "S", "validFor": "Y", "frozenFor": "N"},
    ]), encoding="utf-8")
    (fixture / "OWHS.json").write_text(json.dumps([{"WhsCode": "W_TEST", "WhsName": "Unknown", "Locked": "N", "Inactive": "N"}]), encoding="utf-8")
    (fixture / "OSLP.json").write_text(json.dumps([{"SlpCode": 7, "SlpName": "Corporate Seller", "Active": "Y", "U_CATVENDEDOR": "2", "SalespersonCategoryName": "CORPORATIVO", "CategorySourceLabel": "Vendedor Corporativo"}]), encoding="utf-8")
    return root, fixture


def test_duplicate_guard_rejects_source_keys() -> None:
    with pytest.raises(RuntimeError, match="duplicate"):
        duplicate_guard({"OITM": [{"ItemCode": "P1"}, {"ItemCode": "P1"}], "OCRD": [], "OWHS": []})


def test_fixture_ingestion_creates_role_separated_crosswalks(tmp_path: Path) -> None:
    root, fixture = _make_root(tmp_path)
    result = run_reference_update(data_root=root, evidence_root=tmp_path / "evidence", fixture_dir=fixture)
    assert result["VERDICT"] == f"{GATE}_PASS"
    assert result["PRODUCTS_NEW"] == 1
    assert result["CUSTOMERS_NEW"] == 1
    assert result["SUPPLIERS_NEW"] == 1
    assert result["WAREHOUSES_NEW"] == 1
    assert result["SALESPERSONS_NEW"] == 1
    assert result["CORPORATE_SEMANTIC_STATUS"] == "CONFIRMED"
    assert result["SAME_NAME_ROLE_MERGES"] == 0
    assert result["EXISTING_CANONICAL_IDS_CHANGED"] == 0


def test_second_run_is_noop_and_fault_preserves_pointer(tmp_path: Path) -> None:
    root, fixture = _make_root(tmp_path)
    first = run_reference_update(data_root=root, evidence_root=tmp_path / "evidence", fixture_dir=fixture)
    pointer_path = root / "manifests" / "reference_current.json"
    pointer_before = pointer_path.read_text(encoding="utf-8")
    second = run_reference_update(data_root=root, evidence_root=tmp_path / "evidence2", fixture_dir=fixture)
    assert first["REFERENCE_NEW_VERSION"] == second["REFERENCE_NEW_VERSION"]
    assert second["REFERENCE_SECOND_RUN_NOOP"] == "YES"
    with pytest.raises(RuntimeError, match="fault injection"):
        run_reference_update(data_root=root, evidence_root=tmp_path / "fault", fixture_dir=fixture, inject_failure="before_activate")
    assert pointer_path.read_text(encoding="utf-8") == pointer_before


def test_canonical_id_is_deterministic_and_role_sensitive() -> None:
    assert canonical_id("product", "P1") == canonical_id("product", "P1")
    assert canonical_id("customer", "AGROTEL") != canonical_id("supplier", "AGROTEL")
