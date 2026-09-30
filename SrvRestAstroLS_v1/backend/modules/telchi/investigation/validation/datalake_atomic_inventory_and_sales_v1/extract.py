"""Immutable SAP -> raw/sap extractor for the first Atomic gate.

Only versioned SELECT statements are accepted. Data is written to a temporary
run directory and atomically renamed after hashes and row accounting succeed.
"""
from __future__ import annotations

import re
import shutil
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from modules.telchi.investigation.validation.sql_baseline.sql_baseline_harness import connect

from .common import DOMAINS, RAW_SAP_ROOT, canonical_json, month_ranges, sha256_bytes, sha256_file, utc_now, write_json

_FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|CREATE|ALTER|DROP|TRUNCATE|CALL|GRANT|REVOKE)\b", re.I)


def _query(domain: str) -> tuple[str, Path, str]:
    path = Path(__file__).resolve().parents[2] / "sql" / "current" / "atomic_inventory_and_sales" / DOMAINS[domain]["query"]
    sql = path.read_text(encoding="utf-8")
    executable = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    if _FORBIDDEN.search(executable) or not executable.lstrip().upper().startswith("SELECT"):
        raise ValueError(f"unsafe SAP query: {path}")
    return sql, path, sha256_bytes(sql.encode("utf-8"))


def _copy_frame(frame: pd.DataFrame, destination: Path) -> int:
    # DuckDB's pandas scanner may infer a narrow DECIMAL from early values and
    # then overflow on a later SAP value. Convert Decimal objects to their
    # exact textual representation and cast explicitly to the contract width.
    decimal_columns: set[str] = set()
    for column in frame.columns:
        sample = frame[column].dropna().head(1000)
        if any(isinstance(value, Decimal) for value in sample):
            decimal_columns.add(str(column))
            frame[column] = frame[column].map(lambda value: None if pd.isna(value) else str(value))
    projection = ", ".join(
        f'TRY_CAST("{column}" AS DECIMAL(38,12)) AS "{column}"' if column in decimal_columns else f'"{column}"'
        for column in frame.columns
    )
    connection = duckdb.connect()
    try:
        connection.register("source_chunk", frame)
        escaped = str(destination).replace("'", "''")
        connection.execute(f"COPY (SELECT {projection} FROM source_chunk) TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        connection.close()
    return len(frame)


def extract_domain(domain: str, start: date | None, end_exclusive: date | None, fetch_size: int = 100_000) -> dict[str, Any]:
    if domain not in DOMAINS:
        raise ValueError(f"unsupported domain: {domain}")
    sql, query_path, query_hash = _query(domain)
    started = utc_now()
    token = started.strftime("%Y%m%dT%H%M%S%fZ")
    extraction_id = f"{domain}_{token}_{query_hash[:12]}"
    final_dir = RAW_SAP_ROOT / domain / extraction_id
    temp_dir = final_dir.with_name(final_dir.name + ".tmp")
    if final_dir.exists() or temp_dir.exists():
        raise FileExistsError(f"immutable extraction path already exists: {final_dir}")
    temp_dir.mkdir(parents=True, mode=0o750)
    files: list[dict[str, Any]] = []
    row_count = 0
    source_min_date: str | None = None
    source_max_date: str | None = None
    source_min_change: str | None = None
    source_max_change: str | None = None
    conn = cursor = None
    try:
        conn, cursor = connect()
        ranges = [(None, None)] if domain == "inventory_balance_snapshot" else list(month_ranges(start or date(2022, 3, 31), end_exclusive or (date.today() + timedelta(days=1))))
        part = 0
        for range_start, range_end in ranges:
            cursor.execute(sql, () if range_start is None else (range_start.isoformat(), range_end.isoformat()))
            columns = [str(item[0]) for item in cursor.description]
            while True:
                rows = cursor.fetchmany(fetch_size)
                if not rows:
                    break
                frame = pd.DataFrame.from_records(rows, columns=columns)
                output = temp_dir / f"part-{part:05d}.parquet"
                count = _copy_frame(frame, output)
                file_info = {"file": output.name, "rows": count, "bytes": output.stat().st_size, "sha256": sha256_file(output)}
                files.append(file_info)
                row_count += count
                part += 1
                date_col = "DocDate" if "DocDate" in frame else None
                if date_col and not frame[date_col].dropna().empty:
                    low, high = str(frame[date_col].min())[:10], str(frame[date_col].max())[:10]
                    source_min_date = low if source_min_date is None else min(source_min_date, low)
                    source_max_date = high if source_max_date is None else max(source_max_date, high)
                if "UpdateDate" in frame and not frame["UpdateDate"].dropna().empty:
                    markers = frame["UpdateDate"].astype(str) + ":" + frame["UpdateTS"].fillna(0).astype(str)
                    low, high = markers.min(), markers.max()
                    source_min_change = low if source_min_change is None else min(source_min_change, low)
                    source_max_change = high if source_max_change is None else max(source_max_change, high)
        completed = utc_now()
        manifest: dict[str, Any] = {
            "extraction_id": extraction_id, "source_system": "SAP_B1_HANA", "domain": domain,
            "source_tables": DOMAINS[domain]["tables"].split(";"), "query_id": query_path.stem,
            "query_version": "1", "query_path": str(query_path.relative_to(Path(__file__).resolve().parents[5])),
            "query_hash": query_hash, "schema_version": "1.0.0",
            "watermark_strategy": DOMAINS[domain]["strategy"],
            "watermark_from": start.isoformat() if start else None,
            "watermark_to": end_exclusive.isoformat() if end_exclusive else None,
            "source_min_business_date": source_min_date, "source_max_business_date": source_max_date,
            "source_min_change_marker": source_min_change, "source_max_change_marker": source_max_change,
            "extracted_at": completed.isoformat(), "started_at": started.isoformat(),
            "snapshot_at": started.isoformat() if domain == "inventory_balance_snapshot" else None,
            "row_count": row_count, "file_count": len(files),
            "total_bytes": sum(item["bytes"] for item in files), "files": files,
            "status": "COMPLETED", "sap_access_mode": "READ_ONLY", "sap_write_count": 0,
        }
        manifest["manifest_hash"] = sha256_bytes(canonical_json(manifest))
        write_json(temp_dir / "manifest.json", manifest)
        final_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        temp_dir.rename(final_dir)
        return manifest
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def latest_manifests() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for domain in DOMAINS:
        candidates = sorted((RAW_SAP_ROOT / domain).glob("*/manifest.json"))
        complete = [path for path in candidates if __import__("json").loads(path.read_text())["status"] == "COMPLETED"]
        if complete:
            result[domain] = __import__("json").loads(complete[-1].read_text(encoding="utf-8")) | {"manifest_path": str(complete[-1])}
    return result
