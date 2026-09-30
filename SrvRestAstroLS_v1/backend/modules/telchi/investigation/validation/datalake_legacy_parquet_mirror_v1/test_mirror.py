from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

from . import mirror


def make_parquet(path: Path) -> None:
    connection = duckdb.connect()
    try:
        connection.execute("COPY (SELECT 1 AS id, 'x' AS value) TO ? (FORMAT PARQUET)", [str(path)])
    finally:
        connection.close()


def item_for(source: Path, destination_root: Path) -> dict[str, object]:
    rows, schema = mirror.parquet_metadata(source)
    return {
        "source_relative_path": source.name,
        "source_filename": source.name,
        "destination_relative_path": f"raw/legacy/parquet/{source.name}",
        "family": "fixture",
        "filename_date": "",
        "size_bytes": source.stat().st_size,
        "source_sha256": mirror.sha256(source),
        "historical_sha256": mirror.sha256(source),
        "historical_size_bytes": source.stat().st_size,
        "schema_fingerprint": schema,
        "row_count": rows,
        "copy_action": "COPY_REQUIRED",
        "copy_status": "PENDING",
        "verification_status": "PENDING",
        "destination_size_bytes": "",
        "destination_sha256": "",
        "destination_mtime": "",
        "destination_schema_fingerprint": "",
        "destination_row_count": "",
        "copied_at": "",
    }


def test_approved_inventory_has_exact_expected_count_and_unique_safe_paths() -> None:
    rows = mirror.load_inventory()
    assert len(rows) == mirror.EXPECTED_FILES == 696
    paths = [row["relative_path"] for row in rows]
    assert len(paths) == len(set(paths))
    assert all(Path(path).suffix.lower() in mirror.PARQUET_EXTENSIONS for path in paths)
    assert all(mirror.under(mirror.SOURCE_ROOT / path, mirror.SOURCE_ROOT) for path in paths)
    assert all(not (mirror.SOURCE_ROOT / path).resolve() == mirror.DESTINATION_ROOT for path in paths)


def test_manifest_and_destination_paths_are_unique_and_rooted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    parquet = source / "fixture.parq"
    make_parquet(parquet)
    item = item_for(parquet, destination)
    assert item["source_relative_path"] != str(destination)
    assert mirror.under(source / str(item["source_relative_path"]), source)
    assert mirror.under(destination / str(item["source_relative_path"]), destination)
    assert Path(str(item["source_relative_path"])).suffix.lower() in mirror.PARQUET_EXTENSIONS
    assert len({item["source_relative_path"]}) == 1
    assert len({item["destination_relative_path"]}) == 1


def test_idempotent_status_logic_returns_already_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    parquet = source / "fixture.parq"
    make_parquet(parquet)
    item = item_for(parquet, destination)
    monkeypatch.setattr(mirror, "DESTINATION_ROOT", destination)
    (destination / parquet.name).write_bytes(parquet.read_bytes())
    collisions, _ = mirror.inspect_destinations([item])
    assert not collisions
    assert item["copy_action"] == "ALREADY_VERIFIED"
    assert item["verification_status"] == "PASS"
    # Re-reading the same destination is still the same idempotent state.
    collisions, _ = mirror.inspect_destinations([item])
    assert not collisions
    assert item["copy_action"] == "ALREADY_VERIFIED"


def test_destination_collision_is_never_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    parquet = source / "fixture.parq"
    make_parquet(parquet)
    item = item_for(parquet, destination)
    monkeypatch.setattr(mirror, "DESTINATION_ROOT", destination)
    (destination / parquet.name).write_bytes(b"not-the-source")
    collisions, _ = mirror.inspect_destinations([item])
    assert len(collisions) == 1
    assert collisions[0]["reason"] == "STOP_DESTINATION_COLLISION"
    assert item["copy_action"] == "STOP_DESTINATION_COLLISION"
    assert item["verification_status"] == "FAIL"
    assert (destination / parquet.name).read_bytes() == b"not-the-source"


def test_copy_one_is_byte_identical_and_footer_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    parquet = source / "fixture.parq"
    make_parquet(parquet)
    item = item_for(parquet, destination)
    monkeypatch.setattr(mirror, "SOURCE_ROOT", source)
    monkeypatch.setattr(mirror, "DESTINATION_ROOT", destination)
    mirror.copy_one(item)
    target = destination / parquet.name
    assert target.read_bytes() == parquet.read_bytes()
    assert item["copy_action"] == "COPIED"
    assert item["copy_status"] == "VERIFIED"
    assert item["verification_status"] == "PASS"
    assert not list(destination.glob("*.copying"))


def test_source_path_traversal_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        mirror.safe_inventory_path("../outside.parq", tmp_path / "root")


def test_summary_requires_all_hashes_rows_schemas_and_no_unexpected_files() -> None:
    item = {
        "family": "fixture", "verification_status": "PASS", "copy_action": "COPIED",
        "source_sha256": "a", "destination_sha256": "a", "size_bytes": 10,
        "destination_size_bytes": 10, "row_count": 2, "destination_row_count": 2,
        "schema_fingerprint": "s", "destination_schema_fingerprint": "s",
    }
    summary = mirror.build_summary([item], [], [], [], [], {"free_bytes": 1000}, [], True)
    # The production gate is 696-file strict; a unit fixture must not pass globally.
    assert summary["legacy_mirror_complete"] is False
    assert summary["hash_mismatches"] == 0
    assert summary["row_count_mismatches"] == 0
    assert summary["schema_mismatches"] == 0
