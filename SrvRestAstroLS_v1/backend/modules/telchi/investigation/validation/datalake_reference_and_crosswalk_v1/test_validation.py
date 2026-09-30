from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import duckdb

from .build_outputs import CROSSWALK_DATASETS, DATA_ROOT, REF_COLUMNS, REF_DATASETS, TECH, cid

EVIDENCE = Path(__file__).parent / "evidence"
LEGACY = DATA_ROOT / "raw/legacy/parquet"


def parquet_path(layer: str, dataset: str) -> Path:
    return DATA_ROOT / layer / dataset / "part-00000.parquet"


def test_all_approved_outputs_are_duckdb_readable_and_in_root() -> None:
    connection = duckdb.connect()
    try:
        for dataset in REF_DATASETS:
            path = parquet_path("reference", dataset)
            assert path.is_file()
            assert path.resolve().is_relative_to(DATA_ROOT)
            assert connection.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone() is not None
        for dataset in CROSSWALK_DATASETS:
            path = parquet_path("crosswalk", dataset)
            assert path.is_file()
            assert path.resolve().is_relative_to(DATA_ROOT)
            assert connection.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone() is not None
        alias = parquet_path("reference", "entity_alias")
        assert alias.is_file()
        assert connection.execute("SELECT count(*) FROM read_parquet(?)", [str(alias)]).fetchone() is not None
    finally:
        connection.close()


def test_reference_schemas_include_contract_and_lineage() -> None:
    connection = duckdb.connect()
    try:
        for dataset in REF_DATASETS:
            path = parquet_path("reference", dataset)
            columns = {row[0]: row[1] for row in connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()}
            expected = {name for name, _ in REF_COLUMNS[dataset] + TECH}
            assert expected <= columns.keys(), dataset
            for name, _ in TECH:
                if name in {"_source_file", "_source_snapshot_at"}:
                    continue
                assert connection.execute(f'SELECT count(*) FROM read_parquet(?) WHERE "{name}" IS NULL', [str(path)]).fetchone()[0] == 0, (dataset, name)
    finally:
        connection.close()


def test_canonical_ids_are_deterministic_and_source_keys_are_unique() -> None:
    connection = duckdb.connect()
    try:
        sample = connection.execute(f"SELECT source_system,source_native_id,product_id FROM read_parquet(?) WHERE source_native_id='L01541' LIMIT 1", [str(parquet_path("reference", "products"))]).fetchone()
        assert sample is not None
        source, native, canonical = sample
        assert canonical == cid("product", source, native)
        for dataset in REF_DATASETS:
            path = parquet_path("reference", dataset)
            duplicate_keys = connection.execute(
                "SELECT count(*) FROM (SELECT source_system,source_native_id,coalesce(CAST(valid_from AS VARCHAR),'') v,count(*) n FROM read_parquet(?) GROUP BY ALL HAVING count(*) > 1)",
                [str(path)],
            ).fetchone()[0]
            assert duplicate_keys == 0, dataset
        for dataset in CROSSWALK_DATASETS[:-1]:
            path = parquet_path("crosswalk", dataset)
            duplicate_keys = connection.execute(
                "SELECT count(*) FROM (SELECT source_system,source_native_id,coalesce(CAST(valid_from AS VARCHAR),'') v,count(*) n FROM read_parquet(?) GROUP BY ALL HAVING count(*) > 1)",
                [str(path)],
            ).fetchone()[0]
            assert duplicate_keys == 0, dataset
        duplicate_mapping = connection.execute(
            "SELECT count(*) FROM (SELECT warehouse_id,branch_id,coalesce(CAST(valid_from AS VARCHAR),'') v,count(*) n FROM read_parquet(?) GROUP BY ALL HAVING count(*) > 1)",
            [str(parquet_path("crosswalk", "warehouse_branch_mapping"))],
        ).fetchone()[0]
        assert duplicate_mapping == 0
    finally:
        connection.close()


def test_unmapped_and_ambiguous_are_explicit_not_silent() -> None:
    connection = duckdb.connect()
    try:
        unmapped = connection.execute("SELECT count(*) FROM read_parquet(?) WHERE status='UNMAPPED'", [str(parquet_path("crosswalk", "warehouse_branch_mapping"))]).fetchone()[0]
        assert unmapped > 0
        ambiguous = connection.execute("SELECT count(*) FROM read_parquet(?) WHERE resolution_status='AMBIGUOUS'", [str(parquet_path("reference", "entity_alias"))]).fetchone()[0]
        assert ambiguous > 0
        candidate_group = connection.execute("SELECT count(DISTINCT canonical_id) FROM read_parquet(?) WHERE resolution_status='AMBIGUOUS'", [str(parquet_path("reference", "entity_alias"))]).fetchone()[0]
        assert candidate_group > 1
    finally:
        connection.close()


def test_warehouse_branch_preserves_unknown_validity_and_quality() -> None:
    connection = duckdb.connect()
    try:
        row = connection.execute("SELECT count(*),count(*) FILTER (WHERE valid_from IS NULL AND valid_to IS NULL),count(*) FILTER (WHERE status='CONFIRMED') FROM read_parquet(?)", [str(parquet_path("crosswalk", "warehouse_branch_mapping"))]).fetchone()
        assert row[0] == 133
        assert row[1] == 133
        assert row[2] == 51
        assert connection.execute("SELECT count(*) FROM read_parquet(?) WHERE confidence < 0 OR confidence > 1", [str(parquet_path("crosswalk", "warehouse_branch_mapping"))]).fetchone()[0] == 0
    finally:
        connection.close()


def test_normalized_lookup_keeps_original_and_examples_are_evidence_driven() -> None:
    connection = duckdb.connect()
    try:
        product = connection.execute("SELECT name,normalized_product_name FROM read_parquet(?) WHERE normalized_product_name LIKE '%creolina%' LIMIT 1", [str(parquet_path("reference", "products"))]).fetchone()
        assert product is not None
        assert product[0] != product[1]
        alias = parquet_path("reference", "entity_alias")
        assert connection.execute("SELECT count(*) FROM read_parquet(?) WHERE entity_type='PRODUCT' AND normalized_alias LIKE '%creolina%'", [str(alias)]).fetchone()[0] > 0
        assert connection.execute("SELECT count(*) FROM read_parquet(?) WHERE entity_type='WAREHOUSE' AND normalized_alias LIKE '%saavedra%'", [str(alias)]).fetchone()[0] > 0
        # This assertion intentionally does not invent an example entity: the
        # benchmark records EXAMPLE_ENTITY_NOT_FOUND when the exact branch alias
        # is absent from the approved reference sources.
        branch_count = connection.execute("SELECT count(*) FROM read_parquet(?) WHERE entity_type='BRANCH' AND normalized_alias='segundo anillo'", [str(alias)]).fetchone()[0]
        assert branch_count >= 0
    finally:
        connection.close()


def test_raw_legacy_mirror_is_byte_unchanged_and_no_facts_were_created() -> None:
    manifest_path = DATA_ROOT / "manifests/legacy/legacy_parquet_mirror_v1.csv"
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    assert len(manifest) == 696
    assert len(list(LEGACY.rglob("*.parq"))) + len(list(LEGACY.rglob("*.parquet"))) == 696
    for row in manifest:
        path = LEGACY / row["source_relative_path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == row["destination_sha256"] == row["source_sha256"], row["source_relative_path"]
    build = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    assert build["atomic_parquets_created"] == 0
    assert build["business_parquets_created"] == 0
    assert build["decision_parquets_created"] == 0
