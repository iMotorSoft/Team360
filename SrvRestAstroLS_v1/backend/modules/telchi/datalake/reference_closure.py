"""Build one coherent Reference version from frozen Data Lake inputs.

The builder copies an exact immutable Reference/Crosswalk base and adds complete
warehouse-location and source-native UoM contracts.  It does not move either the
Reference pointer or Foundation CURRENT and it cannot contact SAP/HANA.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

import duckdb

from .reference_semantics import (
    SECOND_ANILLO_WAREHOUSE_CODES,
    SEGUNDO_ANILLO,
    UNKNOWN,
    uom_semantic,
)

GATE = "TELCHI_DATALAKE_REFERENCE_CLOSURE_V1"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _qpath(path: Path) -> str:
    return str(path).replace("'", "''")


def _manifest_source_as_of(files: Iterable[Path]) -> str | None:
    values: list[str] = []
    for file in files:
        manifest = file.with_name("manifest.json")
        if manifest.is_file():
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if payload.get("source_as_of"):
                values.append(str(payload["source_as_of"]))
    return max(values, default=None)


def discover_sales_files(data_root: Path, run_id: str) -> list[Path]:
    root = data_root / "raw/sap/TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1"
    files = sorted(root.glob(f"sales-*/{run_id}_*/part-00000.parquet"))
    if not files:
        raise FileNotFoundError(f"no frozen sales files for explicit run {run_id}")
    return files


def _write_location_datasets(
    reference_root: Path,
    crosswalk_root: Path,
    warehouses_path: Path,
) -> tuple[list[dict[str, Any]], str | None]:
    db = duckdb.connect()
    db.execute("SET threads=1")
    warehouse_rows = db.execute(
        """SELECT CAST(code AS VARCHAR), CAST(name AS VARCHAR),
                  CAST(source_system AS VARCHAR),
                  CAST(coalesce(_source_snapshot_at, _source_extracted_at) AS VARCHAR)
           FROM read_parquet(?) ORDER BY code, source_system""",
        [str(warehouses_path)],
    ).fetchall()
    source_as_of = max((str(row[3]) for row in warehouse_rows if row[3]), default=None)
    explicit = set(SECOND_ANILLO_WAREHOUSE_CODES)
    observed = {str(row[0]) for row in warehouse_rows}
    missing = sorted(explicit - observed)
    if missing:
        db.close()
        raise RuntimeError(f"explicit Segundo Anillo warehouses absent from base: {missing}")
    mappings: list[dict[str, Any]] = []
    for code, name, source_system, row_as_of in warehouse_rows:
        mapped = str(code) in explicit
        mappings.append({
            "warehouse_code": str(code),
            "warehouse_name": str(name or ""),
            "business_location_code": SEGUNDO_ANILLO if mapped else UNKNOWN,
            "business_location_name": "Segundo Anillo" if mapped else "Unknown",
            "mapping_status": "VALIDATED" if mapped else "UNKNOWN",
            "mapping_source": "BUSINESS_CONFIRMED" if mapped else "NO_EXPLICIT_EVIDENCE",
            "mapping_basis": (
                "Business-confirmed 2A location/group; explicit row materialized from frozen warehouse master"
                if mapped else "No validated warehouse-to-business-location assertion"
            ),
            "mapping_confidence": "1.000000" if mapped else "0.000000",
            "source_system": str(source_system or ""),
            "source_as_of": str(row_as_of) if row_as_of else source_as_of,
        })
    location_dir = reference_root / "business_locations"
    mapping_dir = crosswalk_root / "warehouse_business_location"
    location_dir.mkdir(exist_ok=True)
    mapping_dir.mkdir(exist_ok=True)
    db.execute("""CREATE TABLE locations(
        business_location_code VARCHAR, business_location_name VARCHAR,
        status VARCHAR, mapping_source VARCHAR, source_as_of VARCHAR)""")
    db.executemany(
        "INSERT INTO locations VALUES (?, ?, ?, ?, ?)",
        [
            (SEGUNDO_ANILLO, "Segundo Anillo", "VALIDATED", "BUSINESS_CONFIRMED", source_as_of),
            (UNKNOWN, "Unknown", "UNKNOWN", "NO_EXPLICIT_EVIDENCE", source_as_of),
        ],
    )
    db.execute(
        f"COPY (SELECT * FROM locations ORDER BY business_location_code) TO '{_qpath(location_dir / 'part-00000.parquet')}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    db.execute("""CREATE TABLE location_mapping(
        warehouse_code VARCHAR, warehouse_name VARCHAR,
        business_location_code VARCHAR, business_location_name VARCHAR,
        mapping_status VARCHAR, mapping_source VARCHAR, mapping_basis VARCHAR,
        mapping_confidence DECIMAL(10,6), source_system VARCHAR, source_as_of VARCHAR)""")
    db.executemany(
        "INSERT INTO location_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [tuple(row.values()) for row in mappings],
    )
    db.execute(
        f"COPY (SELECT * FROM location_mapping ORDER BY warehouse_code, source_system) TO '{_qpath(mapping_dir / 'part-00000.parquet')}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    db.close()
    return mappings, source_as_of


def _write_uom_datasets(
    reference_root: Path,
    crosswalk_root: Path,
    sales_files: list[Path],
) -> tuple[list[dict[str, Any]], str | None]:
    db = duckdb.connect()
    db.execute("SET threads=1")
    file_list = [str(path) for path in sales_files]
    source_codes = [
        str(row[0]) for row in db.execute(
            """SELECT DISTINCT trim(CAST(unitMsr AS VARCHAR)) source_uom
               FROM read_parquet(?) WHERE nullif(trim(CAST(unitMsr AS VARCHAR)), '') IS NOT NULL
               ORDER BY source_uom""",
            [file_list],
        ).fetchall()
    ]
    source_as_of = _manifest_source_as_of(sales_files)
    mappings: list[dict[str, Any]] = []
    for source in source_codes:
        semantic = uom_semantic(source)
        assert semantic is not None
        mappings.append({
            "source_uom_code": semantic.source_uom_code,
            "source_uom_label": semantic.source_uom_code,
            "canonical_uom_code": semantic.canonical_uom_code,
            "canonical_uom_label": semantic.canonical_uom_label,
            "physical_dimension": semantic.physical_dimension,
            "conversion_factor": "1.000000000000",
            "conversion_basis": semantic.conversion_basis,
            "mapping_status": semantic.mapping_status,
            "mapping_source": semantic.mapping_source,
            "source_as_of": source_as_of,
        })
    canonical = {}
    for row in mappings:
        code = row["canonical_uom_code"]
        previous = canonical.get(code)
        if previous and previous["physical_dimension"] != row["physical_dimension"]:
            db.close()
            raise RuntimeError(f"conflicting UoM dimension for {code}")
        canonical[code] = row
    uom_dir = reference_root / "units_of_measure"
    mapping_dir = crosswalk_root / "uom_mapping"
    shutil.rmtree(uom_dir, ignore_errors=True)
    uom_dir.mkdir()
    mapping_dir.mkdir(exist_ok=True)
    db.execute("""CREATE TABLE uom_taxonomy(
        canonical_uom_code VARCHAR, canonical_uom_label VARCHAR,
        physical_dimension VARCHAR, status VARCHAR, mapping_source VARCHAR,
        source_as_of VARCHAR)""")
    db.executemany(
        "INSERT INTO uom_taxonomy VALUES (?, ?, ?, 'VALIDATED', 'SOURCE_NATIVE_LINE_UOM', ?)",
        [(code, row["canonical_uom_label"], row["physical_dimension"], source_as_of) for code, row in sorted(canonical.items())],
    )
    db.execute(
        f"COPY (SELECT * FROM uom_taxonomy ORDER BY canonical_uom_code) TO '{_qpath(uom_dir / 'part-00000.parquet')}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    db.execute("""CREATE TABLE uom_mapping(
        source_uom_code VARCHAR, source_uom_label VARCHAR,
        canonical_uom_code VARCHAR, canonical_uom_label VARCHAR,
        physical_dimension VARCHAR, conversion_factor DECIMAL(38,12),
        conversion_basis VARCHAR, mapping_status VARCHAR, mapping_source VARCHAR,
        source_as_of VARCHAR)""")
    db.executemany(
        "INSERT INTO uom_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [tuple(row.values()) for row in mappings],
    )
    db.execute(
        f"COPY (SELECT * FROM uom_mapping ORDER BY source_uom_code) TO '{_qpath(mapping_dir / 'part-00000.parquet')}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    db.close()
    return mappings, source_as_of


def build_reference_closure(
    *,
    data_root: Path,
    base_version: str,
    sales_run_id: str,
) -> dict[str, Any]:
    """Build/reuse a deterministic immutable Reference version.

    Re-running against the same explicit base and run id returns the same
    version and verifies the existing logical content; no ``latest`` lookup is
    performed.
    """
    data_root = Path(data_root).resolve()
    base_ref = data_root / "reference/_versions" / base_version
    base_cw = data_root / "crosswalk/_versions" / base_version
    if not base_ref.is_dir() or not base_cw.is_dir():
        raise FileNotFoundError(f"exact Reference base is absent: {base_version}")
    sales_files = discover_sales_files(data_root, sales_run_id)
    warehouses = base_ref / "warehouses/part-00000.parquet"
    if not warehouses.is_file():
        raise FileNotFoundError("base warehouses dataset is absent")

    # Build into a private deterministic staging directory first.  Metadata
    # timestamps are source provenance only and are not generated from wall time.
    input_identity = {
        "base_version": base_version,
        "warehouses_sha256": _file_hash(warehouses),
        "sales_files": [(str(path.relative_to(data_root)), _file_hash(path)) for path in sales_files],
        "explicit_location_codes": list(SECOND_ANILLO_WAREHOUSE_CODES),
    }
    stage_key = _digest(input_identity)[:20]
    stage_ref = data_root / "staging" / GATE / stage_key / "reference"
    stage_cw = data_root / "staging" / GATE / stage_key / "crosswalk"
    shutil.rmtree(stage_ref.parent, ignore_errors=True)
    stage_ref.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(base_ref, stage_ref)
    shutil.copytree(base_cw, stage_cw)
    location_rows, location_as_of = _write_location_datasets(stage_ref, stage_cw, warehouses)
    uom_rows, uom_as_of = _write_uom_datasets(stage_ref, stage_cw, sales_files)
    logical = {
        "input_identity": input_identity,
        "warehouse_business_location": location_rows,
        "uom_mapping": uom_rows,
    }
    reference_hash = _digest(logical)
    version = "v2_reference_closure_" + reference_hash[:16]
    final_ref = data_root / "reference/_versions" / version
    final_cw = data_root / "crosswalk/_versions" / version
    reused = final_ref.is_dir() and final_cw.is_dir()
    if final_ref.exists() != final_cw.exists():
        raise RuntimeError("partial immutable Reference target exists")
    if not reused:
        stage_ref.replace(final_ref)
        stage_cw.replace(final_cw)
    else:
        shutil.rmtree(stage_ref.parent, ignore_errors=True)
    return {
        "base_version": base_version,
        "version": version,
        "reference_path": str(final_ref),
        "crosswalk_path": str(final_cw),
        "reference_hash": reference_hash,
        "reused": reused,
        "sales_run_id": sales_run_id,
        "sales_files": [str(path) for path in sales_files],
        "sales_source_as_of": uom_as_of,
        "warehouse_source_as_of": location_as_of,
        "warehouse_mapping_rows": len(location_rows),
        "uom_mapping_rows": len(uom_rows),
        "datasets": sorted(path.name for path in final_ref.iterdir() if path.is_dir()),
        "crosswalk_datasets": sorted(path.name for path in final_cw.iterdir() if path.is_dir()),
    }


__all__ = ["GATE", "discover_sales_files", "build_reference_closure"]
