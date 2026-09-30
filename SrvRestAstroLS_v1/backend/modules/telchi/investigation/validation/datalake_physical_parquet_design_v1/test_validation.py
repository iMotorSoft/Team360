from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def columns_by_dataset() -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows("physical_columns.csv"):
        result[row["dataset_id"]].add(row["column_name"])
    return result


def test_every_dataset_has_required_physical_contract() -> None:
    datasets = rows("physical_datasets.csv")
    assert len(datasets) == 51
    required = {
        "dataset_id", "layer", "business_domain", "grain", "primary_candidate_key",
        "schema_version", "semantic_version", "transformation_version", "partitioning",
        "incremental_strategy", "security_domain", "rebuild_class", "path", "inputs",
    }
    assert all(all(row[field].strip() for field in required - {"inputs"}) for row in datasets)
    assert len({row["dataset_id"] for row in datasets}) == len(datasets)
    assert all(row["schema_version"] == "1.0.0" for row in datasets)


def test_security_domain_and_scope_are_declared_before_scan() -> None:
    datasets = rows("physical_datasets.csv")
    security = rows("security_physical_contract.csv")
    assert {row["dataset_id"] for row in datasets} == {row["dataset_id"] for row in security}
    assert all(row["security_domain"].strip() for row in security)
    assert all(row["enforcement_stage"] == "AUTHORIZED_SCOPE_BEFORE_PATH_RESOLUTION_AND_PARQUET_SCAN" for row in security)
    scoped_layers = {"reference", "crosswalk", "atomic", "business"}
    assert all(row["scope_columns"].strip() for row in datasets if row["layer"] in scoped_layers)


def test_events_have_explicit_event_or_document_time() -> None:
    datasets = rows("physical_datasets.csv")
    columns = columns_by_dataset()
    accepted = {"event_at", "document_date", "posting_date", "order_date", "reconciliation_date"}
    events = [row for row in datasets if row["data_kind"] == "EVENT"]
    assert events
    assert all(columns[row["dataset_id"]] & accepted for row in events)
    assert "date" not in {name for names in columns.values() for name in names}


def test_snapshot_datasets_have_snapshot_semantics() -> None:
    datasets = rows("physical_datasets.csv")
    columns = columns_by_dataset()
    snapshots = [row for row in datasets if row["data_kind"] == "SNAPSHOT"]
    assert {row["dataset_id"] for row in snapshots} == {"stock_snapshots"}
    assert all("snapshot_at" in columns[row["dataset_id"]] for row in snapshots)
    state = {row["dataset_id"] for row in datasets if row["data_kind"] == "STATE"}
    assert state == {"warehouse_branch_mapping"}
    assert {"valid_from", "valid_to"} <= columns["warehouse_branch_mapping"]


def test_rebuildable_datasets_have_explicit_inputs() -> None:
    datasets = rows("physical_datasets.csv")
    rebuildable = [row for row in datasets if row["rebuild_class"] == "REBUILDABLE"]
    assert rebuildable
    assert all(row["inputs"].strip() for row in rebuildable)
    assert all(row["layer"] in {"atomic", "business"} for row in rebuildable)


def test_raw_legacy_is_byte_preserved_and_has_no_transformation() -> None:
    datasets = {row["dataset_id"]: row for row in rows("physical_datasets.csv")}
    legacy = datasets["legacy_parquet_mirror"]
    assert legacy["rebuild_class"] == "PRESERVED_SOURCE"
    assert legacy["incremental_strategy"] == "IMMUTABLE_COPY"
    assert legacy["transformation_version"] == "NONE"
    assert legacy["compression"] == "SOURCE_PRESERVED"
    assert columns_by_dataset().get("legacy_parquet_mirror", set()) == set()
    assert legacy["path"] == "raw/legacy/parquet"
    decisions = " ".join(row["decision"] for row in rows("decision_log.csv"))
    assert "Preserve legacy mirror" in decisions


def test_crosswalk_allows_unmapped_without_fabricated_canonical_id() -> None:
    contracts = rows("physical_columns.csv")
    status_rows = [row for row in contracts if row["dataset_id"].endswith("_crosswalk") and row["column_name"] == "status"]
    canonical_rows = [row for row in contracts if row["dataset_id"].endswith("_crosswalk") and row["column_name"] == "canonical_id"]
    assert len(status_rows) == 7
    assert all("UNMAPPED" in row["semantic_meaning"] for row in status_rows)
    assert len(canonical_rows) == 7
    assert all(row["nullable"] == "YES" for row in canonical_rows)


def test_legacy_mirror_manifest_requires_sha256_and_verification_fields() -> None:
    contract = {row["field"]: row for row in rows("legacy_mirror_contract.csv")}
    required = {
        "source_relative_path", "source_filename", "destination_relative_path", "size_bytes",
        "sha256", "family", "schema_fingerprint", "row_count", "copied_at", "copy_status",
    }
    assert required <= contract.keys()
    assert contract["sha256"]["requirement"] == "REQUIRED"
    assert "source and destination" in contract["sha256"]["contract"]
    assert contract["filename_date"]["requirement"] == "OPTIONAL"


def test_types_are_explicit_and_money_is_not_float() -> None:
    columns = rows("physical_columns.csv")
    assert not {row["physical_type"] for row in columns} & {"float", "float32", "float64", "double"}
    money_names = {"amount", "line_amount", "cost_amount", "unit_price", "unit_cost", "open_amount", "credit_limit", "overdue_amount", "inventory_value"}
    money = [row for row in columns if row["column_name"] in money_names]
    assert money
    assert all(row["physical_type"].startswith("decimal128") for row in money)
    assert all(row["physical_type"] != "string" for row in columns if row["column_name"].endswith("_date"))


def test_registry_matches_dataset_authority() -> None:
    datasets = rows("physical_datasets.csv")
    registry = rows("dataset_registry.csv")
    assert {row["dataset_id"] for row in datasets} == {row["dataset_id"] for row in registry}
    assert all(row["compression"] == "ZSTD" for row in registry if row["dataset_id"] != "legacy_parquet_mirror")
    assert {row["compression"] for row in registry if row["dataset_id"] == "legacy_parquet_mirror"} == {"SOURCE_PRESERVED"}
    assert all(row["format"] == "PARQUET" for row in registry)


def test_every_declared_scope_column_is_physically_present() -> None:
    datasets = rows("physical_datasets.csv")
    columns = columns_by_dataset()
    normalized_layers = {"reference", "crosswalk", "atomic", "business"}
    for row in datasets:
        if row["layer"] in normalized_layers:
            declared = {value for value in row["scope_columns"].split(";") if value}
            assert declared <= columns[row["dataset_id"]], (row["dataset_id"], declared - columns[row["dataset_id"]])


def test_layout_eliminates_unjustified_durable_layers() -> None:
    layout = {row["relative_path"]: row for row in rows("physical_layout.csv")}
    assert layout["staging"]["decision"] == "ELIMINATE_AS_DURABLE_LAYER"
    assert layout["snapshots"]["decision"] == "ELIMINATE"
    assert layout["decision"]["decision"] == "ELIMINATE_FOR_V1"
    assert layout["raw/legacy/parquet"]["decision"] == "KEEP"


def test_summary_proves_design_only_and_gate_pass() -> None:
    summary = json.loads((ROOT / "summary.json").read_text(encoding="utf-8"))
    assert summary["gate"] == "TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS"
    assert summary["physical_parquet_design_ready"] is True
    assert summary["legacy_parquet_expected"] == 696
    assert summary["legacy_copy_executed"] is False
    assert summary["legacy_parquets_copied"] == 0
    assert summary["production_parquets_created"] == 0
    assert summary["sap_accessed"] is False
    assert summary["sap_write_count"] == 0
    assert summary["source_files_modified"] == 0
    assert summary["source_files_moved"] == 0
    assert summary["source_files_deleted"] == 0
    assert not list(ROOT.glob("*.parquet"))
    assert not list(ROOT.glob("*.parq"))
