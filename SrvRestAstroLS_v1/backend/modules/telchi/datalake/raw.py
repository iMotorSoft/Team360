"""Immutable raw/sap writer with manifest hashes and exact row accounting."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def write_raw(*, root: Path, segment_id: str, extraction_id: str, rows: list[dict[str, Any]], metadata: dict[str, Any], profile: DuckDBSafetyProfile | None = None) -> dict[str, Any]:
    """Write a new immutable extraction; never overwrite an existing run."""
    final_dir = root / segment_id / extraction_id
    temp_dir = final_dir.with_name(final_dir.name + ".tmp")
    if final_dir.exists() or temp_dir.exists():
        raise FileExistsError(f"raw extraction already exists: {final_dir}")
    temp_dir.mkdir(parents=True, mode=0o750)
    jsonl = temp_dir / "rows.jsonl"
    parquet = temp_dir / "part-00000.parquet"
    try:
        with jsonl.open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        if not rows:
            raise ValueError("empty SAP segment cannot become trusted Atomic")
        db = open_safe_duckdb(":memory:", profile=profile)
        try:
            # ``read_json_auto`` infers an all-null column as JSON.  A JSON
            # column is validated lazily, and a later ``UNION ALL`` over mixed
            # monthly files then coerces sibling VARCHAR columns to JSON and
            # fails on ordinary text (e.g. lot codes such as ``25-30-04``).
            # Pin the inferred schema explicitly and demote JSON to VARCHAR so
            # the immutable raw snapshot is always re-readable.
            described = db.execute(
                "DESCRIBE SELECT * FROM read_json_auto(?)", [str(jsonl)]
            ).fetchall()
            columns = {
                str(name): ("VARCHAR" if str(dtype).upper() == "JSON" else str(dtype))
                for name, dtype, *_ in described
            }
            if columns:
                db.execute(
                    "CREATE TABLE raw_rows AS FROM read_json_auto(?, columns=?, union_by_name=true)",
                    [str(jsonl), columns],
                )
            else:
                db.execute("CREATE TABLE raw_rows AS FROM read_json_auto(?)", [str(jsonl)])
            escaped = str(parquet).replace("'", "''")
            db.execute(f"COPY raw_rows TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        finally:
            db.close()
        jsonl.unlink()
        info = {"file": parquet.name, "bytes": parquet.stat().st_size, "sha256": file_hash(parquet)}
        manifest = dict(metadata)
        manifest.update({
            "extraction_id": extraction_id,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "row_count": len(rows),
            "files": [info],
            "file_references": [str(final_dir / parquet.name)],
            "file_hashes": [info["sha256"]],
            "total_bytes": info["bytes"],
            "status": "COMPLETED",
            "sap_access_mode": "READ_ONLY",
            "sap_write_count": 0,
        })
        manifest["manifest_hash"] = digest(manifest)
        (temp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        # The parent directory is renamed only after all files and hashes exist.
        # os.replace is intentionally not used: collision must fail closed.
        temp_dir.rename(final_dir)
        return manifest | {"path": str(final_dir / parquet.name), "manifest_path": str(final_dir / "manifest.json")}
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
