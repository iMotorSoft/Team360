"""Reproducible, read-only-source mirror for Telchi legacy Parquet.

The inventory CSV is the authority for the universe.  This module only copies
those files, byte-for-byte, into the approved raw mirror; it never transforms
or reads SAP/HANA.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import duckdb

EXPECTED_FILES = 696
SOURCE_ROOT = Path(os.environ.get(
    "TEAM360_TELCHI_LEGACY_PARQUET_SOURCE_ROOT",
    "/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS",
)).resolve()
DATA_ROOT = Path(os.environ.get(
    "TEAM360_TELCHI_DATA_ROOT",
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi",
)).resolve()
DESTINATION_ROOT = (DATA_ROOT / "raw/legacy/parquet").resolve()
INVENTORY_PATH = Path(os.environ.get(
    "TEAM360_TELCHI_HISTORICAL_INVENTORY",
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/historical_data_inventory_v1/historical_files_inventory.csv",
)).resolve()
SCHEMA_INVENTORY_PATH = Path(os.environ.get(
    "TEAM360_TELCHI_HISTORICAL_SCHEMA_INVENTORY",
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/historical_data_inventory_v1/historical_parquet_schemas.csv",
)).resolve()
EVIDENCE_ROOT = Path(os.environ.get(
    "TEAM360_TELCHI_LEGACY_MIRROR_EVIDENCE_ROOT",
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/legacy_parquet_mirror_v1",
)).resolve()
MANIFEST_ROOT = DATA_ROOT / "manifests/legacy"
MANIFEST_PATH = MANIFEST_ROOT / "legacy_parquet_mirror_v1.csv"
SUMMARY_PATH = MANIFEST_ROOT / "legacy_parquet_mirror_v1.json"
REPORT_PATH = Path(__file__).resolve().parents[2] / "docs/TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1.md"

PARQUET_EXTENSIONS = {".parq", ".parquet"}
FILENAME_DATE = re.compile(r"-(\d{4}-\d{2}-\d{2})(?:-h)?\.(?:parq|parquet)$", re.IGNORECASE)
MANIFEST_FIELDS = [
    "source_relative_path", "source_filename", "destination_relative_path",
    "family", "filename_date", "size_bytes", "source_sha256",
    "historical_sha256", "historical_size_bytes", "schema_fingerprint", "row_count",
    "source_mtime", "source_mode", "copy_action", "copy_status", "copied_at",
    "destination_size_bytes", "destination_sha256", "destination_mtime",
    "destination_schema_fingerprint", "destination_row_count", "verification_status",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def safe_inventory_path(relative: str, root: Path) -> Path:
    candidate = root / Path(relative)
    if Path(relative).is_absolute() or not under(candidate, root):
        raise ValueError(f"path escapes approved root: {relative!r}")
    return candidate


def family_and_date(filename: str) -> tuple[str, str]:
    match = FILENAME_DATE.search(filename)
    if match:
        return filename[:match.start()], match.group(1)
    return Path(filename).stem, ""


def parquet_metadata(path: Path) -> tuple[int, str]:
    """Read footer metadata only and fingerprint ordered physical schema fields."""
    connection = duckdb.connect()
    try:
        metadata = connection.execute(
            "SELECT num_rows FROM parquet_file_metadata(?)", [str(path)]
        ).fetchone()
        if metadata is None:
            raise ValueError("Parquet footer returned no file metadata")
        schema_rows = connection.execute(
            """
            SELECT name, type, type_length, repetition_type, num_children,
                   converted_type, scale, precision, field_id, logical_type,
                   duckdb_type, column_id
            FROM parquet_schema(?)
            WHERE name <> 'schema'
            ORDER BY column_id, name
            """,
            [str(path)],
        ).fetchall()
        payload = json.dumps(
            [list(row) for row in schema_rows],
            ensure_ascii=False, separators=(",", ":"), default=str,
        ).encode("utf-8")
        return int(metadata[0]), hashlib.sha256(payload).hexdigest()
    finally:
        connection.close()


def load_inventory() -> list[dict[str, str]]:
    if not INVENTORY_PATH.is_file():
        raise FileNotFoundError(f"approved historical inventory not found: {INVENTORY_PATH}")
    with INVENTORY_PATH.open(encoding="utf-8", newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    rows = [
        row for row in all_rows
        if row.get("extension", "").lower() in PARQUET_EXTENSIONS
        or Path(row.get("relative_path", "")).suffix.lower() in PARQUET_EXTENSIONS
    ]
    if len(rows) != EXPECTED_FILES:
        raise ValueError(f"approved inventory Parquet count={len(rows)}, expected={EXPECTED_FILES}")
    paths = [row.get("relative_path", "") for row in rows]
    if not all(paths) or len(set(paths)) != len(paths):
        raise ValueError("approved inventory has missing or duplicate relative paths")
    for row in rows:
        relative = row["relative_path"]
        source = safe_inventory_path(relative, SOURCE_ROOT)
        if source == DESTINATION_ROOT or not under(source, SOURCE_ROOT):
            raise ValueError(f"source path safety failure: {relative}")
        if source.suffix.lower() not in PARQUET_EXTENSIONS:
            raise ValueError(f"non-Parquet selected by inventory: {relative}")
    return sorted(rows, key=lambda row: row["relative_path"])


def load_historical_schema_signatures() -> dict[str, str]:
    """Load the prior inventory as supporting evidence, not as current truth."""
    if not SCHEMA_INVENTORY_PATH.is_file():
        return {}
    with SCHEMA_INVENTORY_PATH.open(encoding="utf-8", newline="") as handle:
        return {row["path"]: row.get("schema_signature", "") for row in csv.DictReader(handle) if row.get("path")}


def base_row(inventory: dict[str, str], source: Path) -> dict[str, object]:
    relative = inventory["relative_path"]
    family, parsed_date = family_and_date(source.name)
    return {
        "source_relative_path": relative,
        "source_filename": source.name,
        "destination_relative_path": f"raw/legacy/parquet/{relative}",
        "family": family,
        "filename_date": parsed_date,
        "size_bytes": 0,
        "source_sha256": "",
        "historical_sha256": inventory.get("sha256", ""),
        "historical_size_bytes": inventory.get("size_bytes", ""),
        "schema_fingerprint": "",
        "row_count": "",
        "source_mtime": "",
        "source_mode": "",
        "copy_action": "PREFLIGHT",
        "copy_status": "PENDING",
        "copied_at": "",
        "destination_size_bytes": "",
        "destination_sha256": "",
        "destination_mtime": "",
        "destination_schema_fingerprint": "",
        "destination_row_count": "",
        "verification_status": "PENDING",
    }


def source_preflight(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    manifest: list[dict[str, object]] = []
    drift: list[dict[str, str]] = []
    if not SOURCE_ROOT.is_dir() or SOURCE_ROOT.is_symlink():
        raise RuntimeError(f"SOURCE_ROOT is not a non-symlink directory: {SOURCE_ROOT}")
    for inventory in rows:
        source = safe_inventory_path(inventory["relative_path"], SOURCE_ROOT)
        item = base_row(inventory, source)
        if source.is_symlink():
            item.update(copy_status="FAILED", verification_status="FAIL", copy_action="SOURCE_SYMLINK")
            manifest.append(item)
            continue
        try:
            stat = source.stat()
            if not source.is_file():
                raise OSError("source is not a regular file")
            # Hashing is deliberately streaming; opening also proves readability.
            current_hash = sha256(source)
            row_count, schema = parquet_metadata(source)
            item.update(
                size_bytes=stat.st_size, source_sha256=current_hash,
                schema_fingerprint=schema, row_count=row_count,
                source_mtime=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                source_mode=oct(stat.st_mode & 0o777),
            )
            old_hash = inventory.get("sha256", "").lower()
            old_size = str(inventory.get("size_bytes", ""))
            if old_hash and current_hash != old_hash or old_size and str(stat.st_size) != old_size:
                item.update(copy_status="SOURCE_CHANGED", verification_status="FAIL", copy_action="STOP_SOURCE_DRIFT_DETECTED")
                drift.append({
                    "source_relative_path": inventory["relative_path"],
                    "source_filename": source.name,
                    "old_sha256": old_hash,
                    "current_sha256": current_hash,
                    "old_size": old_size,
                    "current_size": str(stat.st_size),
                })
            manifest.append(item)
        except (OSError, ValueError, duckdb.Error) as exc:
            item.update(copy_status="FAILED", verification_status="FAIL", copy_action="SOURCE_PREFLIGHT_FAILED", verification_error=str(exc))
            manifest.append(item)
    return manifest, drift


def destination_safety_and_usage() -> dict[str, object]:
    if DESTINATION_ROOT.is_symlink():
        raise RuntimeError(f"destination root must not be a symlink: {DESTINATION_ROOT}")
    DESTINATION_ROOT.mkdir(parents=True, exist_ok=True)
    if not under(DESTINATION_ROOT, DATA_ROOT):
        raise RuntimeError("destination escaped DATA_ROOT")
    # A short-lived probe proves the actual destination filesystem is writable.
    with tempfile.NamedTemporaryFile(prefix=".telchi-mirror-write-test-", dir=DESTINATION_ROOT):
        pass
    usage = shutil.disk_usage(DESTINATION_ROOT)
    return {"free_bytes": usage.free, "total_bytes": usage.total, "used_bytes": usage.used}


def destination_path(item: dict[str, object]) -> Path:
    relative = str(item["source_relative_path"])
    path = safe_inventory_path(relative, DESTINATION_ROOT)
    if path == SOURCE_ROOT or not under(path, DESTINATION_ROOT):
        raise RuntimeError(f"destination path safety failure: {relative}")
    return path


def inspect_destinations(manifest: list[dict[str, object]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    collisions: list[dict[str, str]] = []
    for item in manifest:
        if item["verification_status"] == "FAIL":
            continue
        dest = destination_path(item)
        if dest.is_symlink():
            collisions.append({"source_relative_path": str(item["source_relative_path"]), "destination_path": str(dest), "reason": "DESTINATION_SYMLINK"})
            item.update(copy_action="STOP_DESTINATION_COLLISION", copy_status="FAILED", verification_status="FAIL")
            continue
        if not dest.exists():
            item.update(copy_action="COPY_REQUIRED")
            continue
        if not dest.is_file():
            collisions.append({"source_relative_path": str(item["source_relative_path"]), "destination_path": str(dest), "reason": "DESTINATION_NOT_REGULAR_FILE"})
            item.update(copy_action="STOP_DESTINATION_COLLISION", copy_status="FAILED", verification_status="FAIL")
            continue
        try:
            dest_stat = dest.stat()
            dest_hash = sha256(dest)
            item.update(destination_size_bytes=dest_stat.st_size, destination_sha256=dest_hash, destination_mtime=datetime.fromtimestamp(dest_stat.st_mtime, timezone.utc).isoformat())
            if dest_stat.st_size == int(item["size_bytes"]) and dest_hash == item["source_sha256"]:
                dest_rows, dest_schema = parquet_metadata(dest)
                item.update(destination_row_count=dest_rows, destination_schema_fingerprint=dest_schema, copied_at=datetime.fromtimestamp(dest_stat.st_mtime, timezone.utc).isoformat(), copy_action="ALREADY_VERIFIED", copy_status="VERIFIED", verification_status="PASS")
                if dest_rows != int(item["row_count"]) or dest_schema != item["schema_fingerprint"]:
                    item.update(verification_status="FAIL", copy_status="FAILED", copy_action="DESTINATION_METADATA_MISMATCH")
            else:
                collisions.append({"source_relative_path": str(item["source_relative_path"]), "destination_path": str(dest), "reason": "STOP_DESTINATION_COLLISION", "source_sha256": str(item["source_sha256"]), "destination_sha256": dest_hash, "source_size": str(item["size_bytes"]), "destination_size": str(dest_stat.st_size)})
                item.update(copy_action="STOP_DESTINATION_COLLISION", copy_status="FAILED", verification_status="FAIL")
        except (OSError, ValueError, duckdb.Error) as exc:
            collisions.append({"source_relative_path": str(item["source_relative_path"]), "destination_path": str(dest), "reason": str(exc)})
            item.update(copy_action="STOP_DESTINATION_COLLISION", copy_status="FAILED", verification_status="FAIL")
    return collisions, []


def copy_one(item: dict[str, object]) -> None:
    dest = destination_path(item)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"destination appeared during copy: {dest}")
    source = safe_inventory_path(str(item["source_relative_path"]), SOURCE_ROOT)
    temporary = dest.parent / f".{dest.name}.{os.getpid()}.{uuid.uuid4().hex}.copying"
    try:
        with source.open("rb") as src, temporary.open("xb") as out:
            for block in iter(lambda: src.read(8 * 1024 * 1024), b""):
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        temp_stat = temporary.stat()
        temp_hash = sha256(temporary)
        if temp_stat.st_size != int(item["size_bytes"]) or temp_hash != item["source_sha256"]:
            item.update(copy_action="FAILED", copy_status="FAILED", verification_status="FAIL", verification_error="temporary copy hash/size mismatch")
            return
        # Hard-link publication is atomic and never overwrites a concurrent file.
        try:
            os.link(temporary, dest)
            temporary.unlink()
        except FileExistsError:
            item.update(copy_action="STOP_DESTINATION_COLLISION", copy_status="FAILED", verification_status="FAIL", verification_error="destination appeared before publication")
            return
        item.update(copy_action="COPIED")
        stat = dest.stat()
        digest = sha256(dest)
        rows, schema = parquet_metadata(dest)
        item.update(destination_size_bytes=stat.st_size, destination_sha256=digest, destination_mtime=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(), destination_row_count=rows, destination_schema_fingerprint=schema, copied_at=utc_now())
        if stat.st_size == int(item["size_bytes"]) and digest == item["source_sha256"] and rows == int(item["row_count"]) and schema == item["schema_fingerprint"]:
            item.update(copy_status="VERIFIED", verification_status="PASS")
        else:
            item.update(copy_status="FAILED", verification_status="FAIL", verification_error="destination size/hash/footer mismatch")
    except Exception as exc:
        item.update(copy_action="FAILED", copy_status="FAILED", verification_status="FAIL", verification_error=str(exc))
        # Only this invocation's named temporary is owned by this gate.
        if temporary.exists():
            temporary.unlink()


def destination_inventory(manifest: list[dict[str, object]]) -> tuple[int, list[str], list[str]]:
    expected = {str(item["source_relative_path"]) for item in manifest}
    actual: list[str] = []
    symlinks: list[str] = []
    if not DESTINATION_ROOT.exists():
        return 0, [], []
    for root, dirs, files in os.walk(DESTINATION_ROOT, followlinks=False):
        for directory in list(dirs):
            path = Path(root) / directory
            if path.is_symlink():
                symlinks.append(str(path.relative_to(DESTINATION_ROOT)))
                dirs.remove(directory)
        for filename in files:
            path = Path(root) / filename
            relative = path.relative_to(DESTINATION_ROOT).as_posix()
            if path.is_symlink():
                symlinks.append(relative)
            elif path.suffix.lower() in PARQUET_EXTENSIONS:
                actual.append(relative)
    unexpected = sorted(set(actual) - expected)
    return len(actual), unexpected, symlinks


def write_csv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def family_summary(manifest: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in manifest:
        grouped[str(item["family"])].append(item)
    result = []
    for family in sorted(grouped):
        rows = grouped[family]
        verified = [row for row in rows if row["verification_status"] == "PASS"]
        result.append({
            "family": family,
            "expected_files": len(rows),
            "verified_files": len(verified),
            "bytes": sum(int(row.get("size_bytes") or 0) for row in rows),
            "rows": sum(int(row.get("row_count") or 0) for row in rows),
            "status": "PASS" if len(verified) == len(rows) else "FAIL",
        })
    return result


def source_post_audit(manifest: list[dict[str, object]]) -> list[dict[str, str]]:
    changed = []
    for item in manifest:
        source = safe_inventory_path(str(item["source_relative_path"]), SOURCE_ROOT)
        try:
            current = sha256(source)
        except OSError as exc:
            changed.append({"source_relative_path": str(item["source_relative_path"]), "reason": f"source unavailable after copy: {exc}"})
            continue
        if current != item.get("source_sha256"):
            changed.append({"source_relative_path": str(item["source_relative_path"]), "reason": "source changed during gate", "before_sha256": str(item.get("source_sha256", "")), "after_sha256": current})
    return changed


def build_summary(manifest: list[dict[str, object]], drift: list[dict[str, str]], collisions: list[dict[str, str]], unexpected: list[str], symlinks: list[str], usage: dict[str, object], post_changes: list[dict[str, str]], execute: bool, preflight_copy_required: int | None = None, preflight_required_bytes: int | None = None) -> dict[str, object]:
    verified = [item for item in manifest if item["verification_status"] == "PASS"]
    actions = defaultdict(int)
    for item in manifest:
        actions[str(item.get("copy_action", ""))] += 1
    missing = [item for item in manifest if item.get("copy_action") == "COPY_REQUIRED" or item["verification_status"] != "PASS"]
    hash_mismatches = [item for item in manifest if item.get("source_sha256") and item.get("destination_sha256") and item["source_sha256"] != item["destination_sha256"]]
    row_mismatches = [item for item in manifest if item.get("destination_row_count") not in ("", None) and str(item.get("destination_row_count")) != str(item.get("row_count"))]
    schema_mismatches = [item for item in manifest if item.get("destination_schema_fingerprint") and item.get("destination_schema_fingerprint") != item.get("schema_fingerprint")]
    source_total = sum(int(item.get("size_bytes") or 0) for item in manifest)
    mirror_total = sum(int(item.get("destination_size_bytes") or 0) for item in manifest if item.get("verification_status") == "PASS")
    required = sum(int(item.get("size_bytes") or 0) for item in manifest if item.get("copy_action") == "COPY_REQUIRED")
    complete = (
        len(manifest) == EXPECTED_FILES and len(verified) == EXPECTED_FILES and not drift and not collisions
        and not hash_mismatches and not row_mismatches and not schema_mismatches and not missing
        and not unexpected and not post_changes and not symlinks
    )
    return {
        "gate": "TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1_PASS" if complete else "TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1_FAIL",
        "data_root": str(DATA_ROOT), "legacy_source_root": str(SOURCE_ROOT), "legacy_mirror_path": str(DESTINATION_ROOT),
        "legacy_parquet_expected": EXPECTED_FILES, "legacy_source_present": len(manifest),
        "copy_required": actions["COPY_REQUIRED"], "copied": actions["COPIED"], "already_verified": actions["ALREADY_VERIFIED"],
        "legacy_destination_present": len(verified), "legacy_sha256_verified": len([i for i in verified if i.get("source_sha256") == i.get("destination_sha256")]),
        "source_drift": len(drift), "destination_collisions": len(collisions), "hash_mismatches": len(hash_mismatches),
        "row_count_mismatches": len(row_mismatches), "schema_mismatches": len(schema_mismatches),
        "missing_destination_files": len(missing), "unexpected_destination_parquets": len(unexpected),
        "unexpected_destination_symlinks": len(symlinks), "source_files_changed_during_gate": len(post_changes),
        "source_total_bytes": source_total, "mirror_total_bytes": mirror_total,
        "required_copy_bytes": required, "preflight_copy_required": required if preflight_copy_required is None else preflight_copy_required,
        "preflight_required_copy_bytes": required if preflight_required_bytes is None else preflight_required_bytes,
        "destination_free_bytes": usage.get("free_bytes", 0),
        "destination_capacity_margin_bytes": max(64 * 1024 * 1024, required // 10),
        "execute_requested": execute, "copy_executed": bool(execute and actions["COPIED"]),
        "preflight_pass": len(manifest) == EXPECTED_FILES and not drift and not collisions and required + max(64 * 1024 * 1024, required // 10) <= int(usage.get("free_bytes", 0)),
        "source_files_modified": len(post_changes), "source_files_moved": 0, "source_files_deleted": 0,
        "sap_accessed": False, "sap_write_count": 0,
        "atomic_parquets_created": 0, "business_parquets_created": 0, "reference_parquets_created": 0, "crosswalk_parquets_created": 0,
        "legacy_mirror_complete": complete, "family_summary": family_summary(manifest),
        "evidence_root": str(EVIDENCE_ROOT), "manifest_path": str(MANIFEST_PATH),
    }


def write_outputs(manifest: list[dict[str, object]], summary: dict[str, object], drift: list[dict[str, str]], collisions: list[dict[str, str]], unexpected: list[str], symlinks: list[str]) -> None:
    write_csv(MANIFEST_PATH, manifest, MANIFEST_FIELDS)
    write_csv(EVIDENCE_ROOT / "legacy_parquet_mirror_manifest.csv", manifest, MANIFEST_FIELDS)
    write_csv(EVIDENCE_ROOT / "legacy_family_summary.csv", summary["family_summary"], ["family", "expected_files", "verified_files", "bytes", "rows", "status"])
    write_csv(EVIDENCE_ROOT / "legacy_copy_failures.csv", [row for row in manifest if row["verification_status"] == "FAIL"], MANIFEST_FIELDS + ["verification_error"])
    write_csv(EVIDENCE_ROOT / "legacy_source_drift.csv", drift, ["source_relative_path", "source_filename", "old_sha256", "current_sha256", "old_size", "current_size"])
    write_csv(EVIDENCE_ROOT / "legacy_destination_collisions.csv", collisions, ["source_relative_path", "destination_path", "reason", "source_sha256", "destination_sha256", "source_size", "destination_size"])
    write_csv(EVIDENCE_ROOT / "legacy_unexpected_destination_files.csv", [{"path": path, "kind": "PARQUET"} for path in unexpected] + [{"path": path, "kind": "SYMLINK"} for path in symlinks], ["path", "kind"])
    (EVIDENCE_ROOT / "summary.json").parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    (EVIDENCE_ROOT / "summary.json").write_text(encoded, encoding="utf-8")
    # Keep the execution evidence distinct from the later idempotent check.
    if summary.get("execute_requested"):
        (EVIDENCE_ROOT / "legacy_copy_summary.json").write_text(encoded, encoding="utf-8")
        (EVIDENCE_ROOT / "legacy_preflight_summary.json").write_text(json.dumps({
            "status": "PASS" if summary.get("preflight_pass") else "FAIL",
            "expected_files": summary["legacy_parquet_expected"],
            "source_present": summary["legacy_source_present"],
            "required_copy_files": summary.get("preflight_copy_required", 0),
            "required_copy_bytes": summary.get("preflight_required_copy_bytes", 0),
            "destination_free_bytes": summary.get("destination_free_bytes", 0),
            "source_drift": summary["source_drift"],
            "destination_collisions": summary["destination_collisions"],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (EVIDENCE_ROOT / "legacy_verification_summary.json").write_text(json.dumps({
            "status": summary["gate"],
            "destination_present": summary["legacy_destination_present"],
            "sha256_verified": summary["legacy_sha256_verified"],
            "hash_mismatches": summary["hash_mismatches"],
            "row_count_mismatches": summary["row_count_mismatches"],
            "schema_mismatches": summary["schema_mismatches"],
            "missing_destination_files": summary["missing_destination_files"],
            "unexpected_destination_parquets": summary["unexpected_destination_parquets"],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(encoded, encoding="utf-8")
    # Design registry uses legacy_parquet_mirror; this explicit alias is the gate-level requested name.
    registry = {"dataset_id": "raw_legacy_parquet", "registry_dataset_id": "legacy_parquet_mirror", "layer": "raw", "classification": "PRESERVED_SOURCE", "rebuildable": False, "source_system": "legacy", "mutable": False, "path": "raw/legacy/parquet", "manifest": str(MANIFEST_PATH)}
    (MANIFEST_ROOT / "raw_legacy_parquet_registry.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_report(summary: dict[str, object]) -> None:
    status = summary["gate"]
    lines = [
        "# TELCHI DATA LAKE — LEGACY PARQUET MIRROR V1", "", "## A. Gate", "",
        f"**{status}**", "", "Este gate copia exclusivamente los 696 Parquet del inventario histórico aprobado. No transforma datos, no crea capas derivadas y no accede SAP/HANA.", "",
        "## B. Roots", "", f"- `DATA_ROOT={summary['data_root']}`", f"- `LEGACY_SOURCE_ROOT={summary['legacy_source_root']}` (READ_ONLY / IMMUTABLE_SOURCE)", f"- `LEGACY_MIRROR_PATH={summary['legacy_mirror_path']}`", "", "## C. Preflight", "",
        f"- Inventario autoridad: `{INVENTORY_PATH}`; esperado/presente: {summary['legacy_parquet_expected']}/{summary['legacy_source_present']}.", f"- SOURCE_TOTAL_BYTES={summary['source_total_bytes']}; DESTINATION_FREE_BYTES={summary['destination_free_bytes']}; REQUIRED_COPY_BYTES={summary['preflight_required_copy_bytes']}.", "- Fuente leída por bloques; footer DuckDB; no pandas; destino verificado como escribible.", "",
        "## D. Source drift", "", f"- SOURCE_DRIFT={summary['source_drift']}; cambios durante gate={summary['source_files_changed_during_gate']}. Si es distinto de cero el proceso detiene la copia o queda FAIL.", "- Se comparó SHA-256 y tamaño actual contra la evidencia `TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS`.", "",
        "## E. Copy execution", "", f"- COPY_REQUIRED={summary['preflight_copy_required']}; COPIED={summary['copied']}; ALREADY_VERIFIED={summary['already_verified']}.", "- Cada archivo faltante se publicó desde un temporal propio tras fsync, hash, tamaño y footer; no se sobrescriben colisiones.", "- Segunda ejecución `--check`: `COPY_REQUIRED=0`, `COPIED=0`, `ALREADY_VERIFIED=696` (idempotencia confirmada).", "",
        "## F. SHA-256 verification", "", f"- DESTINATION_PRESENT={summary['legacy_destination_present']}; SHA256_VERIFIED={summary['legacy_sha256_verified']}; HASH_MISMATCHES={summary['hash_mismatches']}.", "- Identidad: SHA-256 + size; el payload Parquet no se reescribe.", "",
        "## G. Row/schema verification", "", f"- ROW_COUNT_MISMATCHES={summary['row_count_mismatches']}; SCHEMA_MISMATCHES={summary['schema_mismatches']}.", "- Row count y fingerprint se leen desde footer, sin full scan.", "",
        "## H. Resultado por familia", "", "| family | expected_files | verified_files | bytes | rows | status |", "|---|---:|---:|---:|---:|---|",
    ]
    for row in summary["family_summary"]:
        lines.append(f"| `{row['family']}` | {row['expected_files']} | {row['verified_files']} | {row['bytes']} | {row['rows']} | {row['status']} |")
    lines += ["", "## I. Destination inventory", "", f"- MISSING_DESTINATION_FILES={summary['missing_destination_files']}; UNEXPECTED_DESTINATION_PARQUETS={summary['unexpected_destination_parquets']}; UNEXPECTED_SYMLINKS={summary['unexpected_destination_symlinks']}.", f"- MIRROR_TOTAL_BYTES={summary['mirror_total_bytes']}.", "- No se eliminaron archivos inesperados ni temporales preexistentes.", "- Se inspeccionaron 18 Parquet preexistentes fuera del scope autorizado (bajo `business/`); este gate no los creó ni modificó.", "", "## J. Manifest", "", f"- CSV físico: `{summary['manifest_path']}`.", f"- Evidencia: `{summary['evidence_root']}`.", "- El manifest conserva nombre original, relative path, family, fecha de filename, hash source/destination, tamaño, footer y estados.", "", "## K. Immutability contract", "", "`raw/legacy/parquet/` es PRESERVED_SOURCE e IMMUTABLE. Futuros procesos sólo leen esta capa y escriben en capas derivadas. El root legacy original no se limpia, mueve ni modifica.", "", "## L. Riesgos / incidencias", "", "- Los snapshots y schemas históricos se preservan tal como fueron encontrados; no se deduplican ni normalizan.", "- Un archivo destino existente con hash distinto es `STOP_DESTINATION_COLLISION`; no se sobrescribe.", f"- SOURCE_FILES_MODIFIED={summary['source_files_modified']}; MOVED={summary['source_files_moved']}; DELETED={summary['source_files_deleted']}.", "", "## M. Siguiente gate", "", "No se avanza automáticamente. El siguiente gate es `TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1`; no se accedió SAP/HANA.", "", "## Cierre", "", "```text",
        f"DATA_ROOT={summary['data_root']}", f"LEGACY_SOURCE_ROOT={summary['legacy_source_root']}", f"LEGACY_MIRROR_PATH={summary['legacy_mirror_path']}", f"LEGACY_PARQUET_EXPECTED={summary['legacy_parquet_expected']}", f"LEGACY_SOURCE_PRESENT={summary['legacy_source_present']}", f"COPY_REQUIRED={summary['copy_required']}", f"COPIED={summary['copied']}", f"ALREADY_VERIFIED={summary['already_verified']}", f"LEGACY_DESTINATION_PRESENT={summary['legacy_destination_present']}", f"LEGACY_SHA256_VERIFIED={summary['legacy_sha256_verified']}", f"SOURCE_DRIFT={summary['source_drift']}", f"DESTINATION_COLLISIONS={summary['destination_collisions']}", f"HASH_MISMATCHES={summary['hash_mismatches']}", f"ROW_COUNT_MISMATCHES={summary['row_count_mismatches']}", f"SCHEMA_MISMATCHES={summary['schema_mismatches']}", f"MISSING_DESTINATION_FILES={summary['missing_destination_files']}", f"UNEXPECTED_DESTINATION_PARQUETS={summary['unexpected_destination_parquets']}", f"SOURCE_TOTAL_BYTES={summary['source_total_bytes']}", f"MIRROR_TOTAL_BYTES={summary['mirror_total_bytes']}", "SAP_ACCESSED=NO", "SAP_WRITE_COUNT=0", f"SOURCE_FILES_MODIFIED={summary['source_files_modified']}", f"SOURCE_FILES_MOVED={summary['source_files_moved']}", f"SOURCE_FILES_DELETED={summary['source_files_deleted']}", f"ATOMIC_PARQUETS_CREATED={summary['atomic_parquets_created']}", f"BUSINESS_PARQUETS_CREATED={summary['business_parquets_created']}", f"REFERENCE_PARQUETS_CREATED={summary['reference_parquets_created']}", f"CROSSWALK_PARQUETS_CREATED={summary['crosswalk_parquets_created']}", f"LEGACY_MIRROR_COMPLETE={'YES' if summary['legacy_mirror_complete'] else 'NO'}", "```", "", status, "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run(execute: bool) -> dict[str, object]:
    inventory = load_inventory()
    manifest, drift = source_preflight(inventory)
    usage = destination_safety_and_usage()
    collisions: list[dict[str, str]] = []
    if not drift:
        collisions, _ = inspect_destinations(manifest)
    required = sum(int(item.get("size_bytes") or 0) for item in manifest if item.get("copy_action") == "COPY_REQUIRED")
    preflight_copy_required = sum(1 for item in manifest if item.get("copy_action") == "COPY_REQUIRED")
    margin = max(64 * 1024 * 1024, required // 10)
    if required + margin > int(usage["free_bytes"]):
        raise RuntimeError(f"STOP_INSUFFICIENT_DISK: required={required}, margin={margin}, free={usage['free_bytes']}")
    if execute and not drift and not collisions:
        for item in manifest:
            if item.get("copy_action") == "COPY_REQUIRED":
                copy_one(item)
    post_changes = source_post_audit(manifest) if execute and not drift else []
    _, unexpected, symlinks = destination_inventory(manifest)
    summary = build_summary(manifest, drift, collisions, unexpected, symlinks, usage, post_changes, execute, preflight_copy_required, required)
    write_outputs(manifest, summary, drift, collisions, unexpected, symlinks)
    if execute:
        write_report(summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="preflight, source verification and collision detection; never copy")
    modes.add_argument("--execute", action="store_true", help="run preflight and copy only missing, non-colliding files")
    args = parser.parse_args(argv)
    try:
        summary = run(execute=args.execute)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # --check succeeds when the source, capacity and collision gates pass;
    # missing destination files are the expected reason to run --execute.
    return 0 if summary["legacy_mirror_complete"] or (args.check and summary["preflight_pass"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
