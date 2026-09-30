"""Shared deterministic contracts for the first Telchi Atomic gate."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

GATE = "TELCHI_DATALAKE_ATOMIC_INVENTORY_AND_SALES_V1"
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
RAW_SAP_ROOT = DATA_ROOT / "raw" / "sap" / "query_extract"
REFERENCE_MANIFEST = DATA_ROOT / "manifests" / "reference_current.json"
REFERENCE_V2 = DATA_ROOT / "reference" / "_versions" / "v2"
CROSSWALK_V2 = DATA_ROOT / "crosswalk" / "_versions" / "v2"
LEGACY_ROOT = DATA_ROOT / "raw" / "legacy" / "parquet"
VALIDATION_ROOT = Path(__file__).resolve().parent
EVIDENCE_ROOT = VALIDATION_ROOT / "evidence"
SQL_ROOT = VALIDATION_ROOT.parents[2] / "sql" / "current" / "atomic_inventory_and_sales"
TRANSFORMATION_VERSION = "atomic-inventory-sales-v1.0.0"
SCHEMA_VERSION = "1.0.0"
DATASETS = (
    "sales_documents", "sales_lines", "credit_note_documents",
    "credit_note_lines", "inventory_movements", "inventory_balance_snapshots",
)
DOMAINS: dict[str, dict[str, Any]] = {
    "sales": {"query": "sales_extract_v1.sql", "tables": "OINV;INV1", "strategy": "UPDATE_DATE_TS_PLUS_DOCENTRY_WITH_35_DAY_LOOKBACK"},
    "credit_notes": {"query": "credit_notes_extract_v1.sql", "tables": "ORIN;RIN1", "strategy": "UPDATE_DATE_TS_PLUS_DOCENTRY_WITH_62_DAY_LOOKBACK"},
    "inventory_movements": {"query": "inventory_movements_extract_v1.sql", "tables": "OINM", "strategy": "TRANSNUM_PLUS_BOUNDED_62_DAY_DOCDATE_REREAD"},
    "inventory_balance_snapshot": {"query": "inventory_balance_snapshot_extract_v1.sql", "tables": "OITW;OITM;OWHS", "strategy": "OBSERVED_EXTRACTION_SNAPSHOT"},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def deterministic_id(namespace: str, *parts: object) -> str:
    material = "\x1f".join([namespace, *("" if part is None else str(part).strip() for part in parts)])
    return f"{namespace}_{hashlib.sha256(material.encode()).hexdigest()[:32]}"


def reference_identity() -> tuple[str, str, dict[str, Any]]:
    payload = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    return str(payload["current_reference_version"]), sha256_file(REFERENCE_MANIFEST), payload


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fields or (list(rows[0]) if rows else ["result"])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def month_ranges(start: date, end_exclusive: date):
    current = start
    while current < end_exclusive:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        boundary = min(next_month, end_exclusive)
        yield current, boundary
        current = boundary
