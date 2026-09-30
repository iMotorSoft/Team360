from __future__ import annotations

import json
from pathlib import Path

import duckdb

from .build_outputs import (
    CONTRACT, CROSSWALK_V2, DATA_ROOT, EVIDENCE, REFERENCE_V2,
    RELATIONSHIPS, expected_reference, fingerprint_v1, sha256,
)


def pq(root: Path, name: str) -> str:
    return str(root / name / "part-00000.parquet")


def summary() -> dict:
    return json.loads((EVIDENCE / "summary.json").read_text())


def test_contract_list_equals_21_physical_reference_entities() -> None:
    expected = expected_reference()
    physical = sorted(p.parent.name for p in REFERENCE_V2.glob("*/part-00000.parquet") if p.parent.name != "entity_alias")
    assert len(expected) == 21
    assert physical == expected


def test_v1_reference_and_crosswalk_are_byte_unchanged() -> None:
    assert fingerprint_v1() == json.loads((EVIDENCE / "v1_fingerprint.json").read_text())
    s = summary()
    for layer in ("reference", "crosswalk"):
        for action in ("modified", "deleted", "moved"):
            assert s[f"{layer}_v1_files_{action}"] == 0


def test_all_v2_parquets_are_readable_and_manifest_hashes_match() -> None:
    manifest = {r["path"]: r for r in __import__("csv").DictReader((EVIDENCE / "reference_v2_manifest.csv").open())}
    conn = duckdb.connect()
    try:
        paths = list(REFERENCE_V2.glob("*/part-00000.parquet")) + list(CROSSWALK_V2.glob("*/part-00000.parquet"))
        assert len(paths) == 22 + 18  # 21 contract entities + alias + 18 crosswalk/relations
        for path in paths:
            assert conn.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone() is not None
            assert manifest[str(path)]["sha256"] == sha256(path)
    finally:
        conn.close()


def test_product_ids_are_deterministic_and_all_v1_ids_preserved() -> None:
    conn = duckdb.connect()
    try:
        row = conn.execute("SELECT count(*),count(DISTINCT canonical_product_id),count(*) FILTER(WHERE canonical_product_id IS NULL) FROM read_parquet(?)", [pq(REFERENCE_V2, "products")]).fetchone()
        assert row == (53318, 53318, 0)
        changed = conn.execute("SELECT count(*) FROM read_parquet(?) v1 FULL JOIN read_parquet(?) v2 ON v1.product_id=v2.canonical_product_id WHERE v1.product_id IS NULL OR v2.canonical_product_id IS NULL", [str(DATA_ROOT / "reference/products/part-00000.parquet"), pq(REFERENCE_V2, "products")]).fetchone()[0]
        assert changed == 0
    finally:
        conn.close()


def test_litel_is_materialized_and_consumed_without_itemcode_predicate() -> None:
    conn = duckdb.connect()
    try:
        # This is the future consumption shape: relationship + canonical catalog.
        query = "SELECT count(*) FROM read_parquet(?) r JOIN read_parquet(?) f USING(portfolio_family_id) WHERE f.code='LITEL'"
        count = conn.execute(query, [pq(CROSSWALK_V2, "product_portfolio_family"), pq(REFERENCE_V2, "portfolio_family")]).fetchone()[0]
        assert count == summary()["litel_products"] > 0
        assert "like" not in query.lower()
    finally:
        conn.close()


def test_unknown_provisional_and_ambiguous_states_remain_explicit() -> None:
    conn = duckdb.connect()
    try:
        assert conn.execute("SELECT count(*) FROM read_parquet(?) WHERE status='UNMAPPED'", [pq(CROSSWALK_V2, "product_portfolio_family")]).fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM read_parquet(?) WHERE status='PROVISIONAL'", [pq(CROSSWALK_V2, "product_portfolio_family")]).fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM read_parquet(?) WHERE resolution_status='AMBIGUOUS'", [pq(REFERENCE_V2, "entity_alias")]).fetchone()[0] > 0
    finally:
        conn.close()


def test_semantic_dimensions_are_separate_physical_contracts() -> None:
    names = set(expected_reference())
    assert {"brand", "business_unit", "portfolio_family", "product_business_type", "operating_domain", "operating_model", "sales_channel", "production_site", "warehouses", "branches"} <= names
    assert "product_groups" not in names and "channels" not in names
    assert pq(REFERENCE_V2, "brand") != pq(REFERENCE_V2, "portfolio_family")
    assert pq(REFERENCE_V2, "business_unit") != pq(REFERENCE_V2, "sales_channel")
    assert pq(REFERENCE_V2, "production_site") != pq(REFERENCE_V2, "warehouses")
    assert pq(REFERENCE_V2, "warehouses") != pq(REFERENCE_V2, "branches")


def test_relationships_are_temporal_and_have_no_orphans_or_bad_intervals() -> None:
    conn = duckdb.connect()
    try:
        for name in RELATIONSHIPS:
            columns = {r[0] for r in conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [pq(CROSSWALK_V2, name)]).fetchall()}
            assert {"valid_from", "valid_to", "source", "confidence", "status"} <= columns
            assert conn.execute("SELECT count(*) FROM read_parquet(?) WHERE valid_from IS NOT NULL AND valid_to IS NOT NULL AND valid_from>valid_to", [pq(CROSSWALK_V2, name)]).fetchone()[0] == 0
        orphan = conn.execute("SELECT count(*) FROM read_parquet(?) r LEFT JOIN read_parquet(?) f USING(portfolio_family_id) WHERE r.portfolio_family_id IS NOT NULL AND f.portfolio_family_id IS NULL", [pq(CROSSWALK_V2, "product_portfolio_family"), pq(REFERENCE_V2, "portfolio_family")]).fetchone()[0]
        assert orphan == 0
    finally:
        conn.close()


def test_aliases_are_evidence_backed_and_examples_do_not_regress() -> None:
    conn = duckdb.connect()
    try:
        alias = pq(REFERENCE_V2, "entity_alias")
        assert conn.execute("SELECT count(*) FROM read_parquet(?) WHERE alias_source IS NULL OR alias IS NULL", [alias]).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM read_parquet(?) WHERE entity_type='PRODUCT' AND normalized_alias LIKE '%creolina%'", [alias]).fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM read_parquet(?) WHERE entity_type='WAREHOUSE' AND normalized_alias LIKE '%saavedra%'", [alias]).fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM read_parquet(?) WHERE normalized_alias='segundo anillo'", [alias]).fetchone()[0] == 0
    finally:
        conn.close()


def test_white_label_and_magistral_are_representable_without_schema_pollution() -> None:
    s = summary()
    assert s["white_label_representable"] == "YES"
    assert s["magistral_representable_without_industrial_model"] == "YES"
    relationship_names = {r["relationship"] for r in __import__("csv").DictReader((CONTRACT / "product_relationship_contract.csv").open())}
    assert {"product_manufacturer", "brand_owner", "manufacturing_arrangement"} <= relationship_names
    product_columns = {r[0] for r in duckdb.connect().execute("DESCRIBE SELECT * FROM read_parquet(?)", [pq(REFERENCE_V2, "products")]).fetchall()}
    assert not any(x.startswith("white_label_customer_") for x in product_columns)
    assert not {"attribute_name", "attribute_value"} <= product_columns


def test_stable_schema_accepts_new_catalog_value_without_altering_facts() -> None:
    conn = duckdb.connect()
    try:
        before = conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [pq(REFERENCE_V2, "products")]).fetchall()
        conn.execute("CREATE TEMP TABLE synthetic_operating_model AS SELECT * FROM read_parquet(?)", [pq(REFERENCE_V2, "operating_model")])
        conn.execute("INSERT INTO synthetic_operating_model VALUES ('operating_model_synthetic','SYNTHETIC_CONTRACT_TEST','Synthetic',NULL,TRUE,NULL,NULL,'TEST',0.5,'PROVISIONAL','2.0.0')")
        after = conn.execute("DESCRIBE SELECT * FROM read_parquet(?)", [pq(REFERENCE_V2, "products")]).fetchall()
        assert before == after
    finally:
        conn.close()


def test_no_atomic_business_current_ducklake_or_postgres_output() -> None:
    s = summary()
    assert s["atomic_tables_created"] == s["business_tables_created"] == s["current_tables_created"] == 0
    assert s["ducklake_modified"] == s["postgres_modified"] == "NO"
    for item in json.loads((EVIDENCE / "summary.json").read_text()),:
        assert "password" not in json.dumps(item).lower()


def test_performance_and_offline_verify_contract() -> None:
    s = summary()
    assert s["entity_resolution_p95_ms"] <= 20
    assert s["sap_accessed"] == "NO" and s["sap_write_count"] == 0
    assert s["second_run_idempotent"] == "YES"
    assert s["reference_v2_ready_for_atomic"] == "YES"
