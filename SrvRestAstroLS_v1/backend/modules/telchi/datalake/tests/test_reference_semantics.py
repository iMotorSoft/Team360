from decimal import Decimal

import duckdb
import pytest

from modules.telchi.datalake.reference_closure import build_reference_closure
from modules.telchi.datalake.reference_semantics import (
    SECOND_ANILLO_WAREHOUSE_CODES,
    SEGUNDO_ANILLO,
    UomSemantic,
    WarehouseLocation,
    convert_quantity,
    multiple_sales_uom,
    resolve_warehouse_location,
    uom_semantic,
)


def _location(code: str = "2A-SAL") -> WarehouseLocation:
    return WarehouseLocation(
        code, SEGUNDO_ANILLO, "Segundo Anillo", "VALIDATED",
        "BUSINESS_CONFIRMED", "explicit", Decimal("1"),
    )


def test_2a_sal_is_explicit_business_confirmed_mapping():
    result = resolve_warehouse_location("2A-SAL", {"2A-SAL": _location()})
    assert result is not None
    assert result.business_location_code == SEGUNDO_ANILLO
    assert result.mapping_source == "BUSINESS_CONFIRMED"


def test_location_resolution_never_uses_prefix():
    assert resolve_warehouse_location("2A-UNKNOWN", {"2A-SAL": _location()}) is None


def test_unknown_related_warehouse_remains_unknown_without_explicit_row():
    assert resolve_warehouse_location("2A-NEW", {}) is None


def test_source_uom_is_preserved_and_item_name_is_not_an_input():
    semantic = uom_semantic("kg")
    assert semantic is not None
    assert semantic.source_uom_code == "kg"
    assert semantic.canonical_uom_code == "KG"
    assert uom_semantic(None) is None


def test_multiple_uom_per_item_is_preserved():
    assert multiple_sales_uom([("A", "KG"), ("A", "FCO"), ("B", "KG")]) == {"A"}


def test_identity_conversion_is_safe():
    kg = uom_semantic("KG")
    assert kg is not None
    assert convert_quantity(Decimal("3"), kg, kg) == Decimal("3")


def test_same_dimension_conversion_requires_provenance():
    kg = uom_semantic("KG")
    assert kg is not None
    gram = UomSemantic("G", "G", "G", "MASS")
    with pytest.raises(ValueError, match="PROVENANCE"):
        convert_quantity(Decimal("3"), kg, gram)
    assert convert_quantity(Decimal("3"), kg, gram, validated_factor=Decimal("1000")) == Decimal("3000")


def test_mass_volume_is_blocked_without_density():
    kg, litre = uom_semantic("KG"), uom_semantic("LT")
    assert kg is not None and litre is not None
    with pytest.raises(ValueError, match="DENSITY"):
        convert_quantity(Decimal("1"), kg, litre, validated_factor=Decimal("1"))


def test_unknown_dimension_cannot_be_converted():
    fco, comp = uom_semantic("FCO"), uom_semantic("COMP")
    assert fco is not None and comp is not None
    with pytest.raises(ValueError, match="UNRESOLVED"):
        convert_quantity(Decimal("1"), fco, comp, validated_factor=Decimal("1"))


def test_offline_builder_is_deterministic_and_idempotent(tmp_path):
    base = "exact_base"
    ref = tmp_path / "reference/_versions" / base
    cw = tmp_path / "crosswalk/_versions" / base
    (ref / "warehouses").mkdir(parents=True)
    (ref / "warehouse_roles").mkdir()
    (ref / "units_of_measure").mkdir()
    (cw / "seed").mkdir(parents=True)
    db = duckdb.connect()
    db.execute("CREATE TABLE wh(code VARCHAR,name VARCHAR,source_system VARCHAR,_source_snapshot_at VARCHAR,_source_extracted_at VARCHAR)")
    db.executemany(
        "INSERT INTO wh VALUES (?, ?, 'SAP_HANA', '2026-09-24T00:00:00Z', '2026-09-24T00:00:00Z')",
        [(code, code) for code in SECOND_ANILLO_WAREHOUSE_CODES] + [("SAA-M1", "Saavedra")],
    )
    db.execute(f"COPY wh TO '{ref / 'warehouses/part-00000.parquet'}' (FORMAT PARQUET)")
    db.execute("CREATE TABLE roles(warehouse_code VARCHAR, warehouse_role VARCHAR)")
    db.execute("INSERT INTO roles VALUES ('SAA-M1','RAW_MATERIAL')")
    db.execute(f"COPY roles TO '{ref / 'warehouse_roles/part-00000.parquet'}' (FORMAT PARQUET)")
    db.execute("CREATE TABLE empty_uom(code VARCHAR)")
    db.execute(f"COPY empty_uom TO '{ref / 'units_of_measure/part-00000.parquet'}' (FORMAT PARQUET)")
    db.execute("CREATE TABLE seed(value VARCHAR)")
    db.execute("INSERT INTO seed VALUES ('preserved')")
    db.execute(f"COPY seed TO '{cw / 'seed/part-00000.parquet'}' (FORMAT PARQUET)")
    sales_dir = tmp_path / "raw/sap/TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1/sales-1/run-fixed_x"
    sales_dir.mkdir(parents=True)
    db.execute("CREATE TABLE sales(ItemCode VARCHAR, unitMsr VARCHAR)")
    db.execute("INSERT INTO sales VALUES ('L00031','KG'),('L03192','KG'),('X','FCO'),('Y',NULL)")
    db.execute(f"COPY sales TO '{sales_dir / 'part-00000.parquet'}' (FORMAT PARQUET)")
    (sales_dir / "manifest.json").write_text('{"source_as_of":"2026-09-24T00:00:00Z"}')
    db.close()

    first = build_reference_closure(data_root=tmp_path, base_version=base, sales_run_id="run-fixed")
    second = build_reference_closure(data_root=tmp_path, base_version=base, sales_run_id="run-fixed")
    assert first["version"] == second["version"]
    assert first["reference_hash"] == second["reference_hash"]
    assert second["reused"] is True
    check = duckdb.connect()
    mapping = check.execute(
        "SELECT business_location_code,mapping_source FROM read_parquet(?) WHERE warehouse_code='2A-SAL'",
        [first["crosswalk_path"] + "/warehouse_business_location/part-00000.parquet"],
    ).fetchone()
    role = check.execute(
        "SELECT warehouse_role FROM read_parquet(?)",
        [first["reference_path"] + "/warehouse_roles/part-00000.parquet"],
    ).fetchone()
    uoms = check.execute(
        "SELECT source_uom_code,canonical_uom_code FROM read_parquet(?) ORDER BY 1",
        [first["crosswalk_path"] + "/uom_mapping/part-00000.parquet"],
    ).fetchall()
    check.close()
    assert mapping == (SEGUNDO_ANILLO, "BUSINESS_CONFIRMED")
    assert role == ("RAW_MATERIAL",)
    assert uoms == [("FCO", "FCO"), ("KG", "KG")]
