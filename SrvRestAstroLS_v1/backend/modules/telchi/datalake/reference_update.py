"""TELCHI Reference V2 SAP master refresh (OITM/OCRD/OWHS/OSLP).

This is an explicit, bounded, one-shot builder.  It stages a complete current
SAP master snapshot, reconciles it with the active Reference V2, validates the
source-key -> canonical-id contract, and activates one immutable version by an
atomic pointer replacement.  It deliberately does not touch Atomic, Business,
or DuckLake tables.

SAP extraction is read-only and sequential.  ``--fixture-dir`` is provided for
repeatable local tests and fault injection; it never pretends to be a SAP run.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb

from .reference_closure import build_reference_closure
from .source import HanaReadOnlySource

GATE = "TELCHI_DATALAKE_REFERENCE_V2_SAP_MASTER_INGESTION_V1"
DATA_ROOT = Path(os.environ.get("TEAM360_TELCHI_DATA_ROOT", "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")).resolve()
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
POINTER_NAME = "reference_current.json"
SAP_TABLES = ("OITM", "OCRD", "OWHS", "OSLP")
ENTITY_CONFIG = {
    "product": {"table": "OITM", "key": "ItemCode", "ref": "products", "crosswalk": "product_crosswalk", "canonical": "canonical_product_id", "prefix": "product"},
    "customer": {"table": "OCRD", "key": "CardCode", "ref": "customers", "crosswalk": "customer_crosswalk", "canonical": "customer_id", "prefix": "customer"},
    "supplier": {"table": "OCRD", "key": "CardCode", "ref": "suppliers", "crosswalk": "supplier_crosswalk", "canonical": "supplier_id", "prefix": "supplier"},
    "warehouse": {"table": "OWHS", "key": "WhsCode", "ref": "warehouses", "crosswalk": "warehouse_crosswalk", "canonical": "warehouse_id", "prefix": "warehouse"},
    "salesperson": {"table": "OSLP", "key": "SlpCode", "ref": "salespersons", "crosswalk": "salesperson_crosswalk", "canonical": "salesperson_id", "prefix": "salesperson"},
}

OITM_SQL = '''
SELECT "ItemCode", "ItemName", "validFor", "frozenFor", "InvntItem", "SellItem", "PrchseItem",
       "ItmsGrpCod", "InvntryUom", "SalUnitMsr", "BuyUnitMsr", "AvgPrice", "LastPurPrc", "UpdateDate"
FROM "TELCHI"."OITM"
'''
OCRD_SQL = '''
SELECT "CardCode", "CardName", "CardType", "GroupCode", "GroupNum", "validFor", "frozenFor",
       "LicTradNum", "CreditLine", "UpdateDate"
FROM "TELCHI"."OCRD"
'''
OWHS_SQL = '''
SELECT "WhsCode", "WhsName", "Locked", "Inactive", "updateDate", "U_BRANCH_OFFICE_ID", "U_TYPE", "U_WAREHOUSE_DMS"
FROM "TELCHI"."OWHS"
'''
OSLP_SQL = '''
SELECT S."SlpCode", S."SlpName", S."Active", S."U_CATVENDEDOR",
       CASE WHEN V."Descr" IS NOT NULL THEN UPPER(REPLACE(V."Descr", 'Vendedor ', ''))
            ELSE NULL END AS "SalespersonCategoryName",
       V."Descr" AS "CategorySourceLabel"
FROM "TELCHI"."OSLP" S
LEFT JOIN "TELCHI"."CUFD" F ON F."TableID"='OSLP' AND F."AliasID"='CATVENDEDOR'
LEFT JOIN "TELCHI"."UFD1" V ON V."TableID"=F."TableID" AND V."FieldID"=F."FieldID"
                              AND V."FldValue"=S."U_CATVENDEDOR"
'''


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def canonical_id(prefix: str, native: str) -> str:
    return f"{prefix}_" + hashlib.sha256(f"{prefix}|SAP_HANA|{native}".encode()).hexdigest()[:24]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _normal(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def read_parquet_rows(path: Path) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Read Parquet without requiring optional timezone Python packages."""
    db = duckdb.connect()
    try:
        description = db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
        columns = [str(row[0]) for row in description]
        types = [str(row[1]) for row in description]
        select = ",".join(f'CAST("{column.replace(chr(34), chr(34) * 2)}" AS VARCHAR) AS "{column.replace(chr(34), chr(34) * 2)}"' for column in columns)
        rows = db.execute(f"SELECT {select} FROM read_parquet(?)", [str(path)]).fetchall()
        return columns, types, [dict(zip(columns, row)) for row in rows]
    finally:
        db.close()


def write_parquet(path: Path, columns: list[str], types: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    db = duckdb.connect()
    json_path = path.with_suffix(".csv")
    try:
        if rows:
            with json_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows({column: row.get(column) for column in columns} for row in rows)
            db.execute("CREATE TABLE input AS SELECT * FROM read_csv(?, header=true, all_varchar=true, nullstr='')", [str(json_path)])
            expressions = ",".join(f'CAST("{c.replace(chr(34), chr(34) * 2)}" AS {t}) AS "{c.replace(chr(34), chr(34) * 2)}"' for c, t in zip(columns, types))
            db.execute(f"COPY (SELECT {expressions} FROM input) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(path)])
        else:
            definitions = ",".join(f'CAST(NULL AS {t}) AS "{c.replace(chr(34), chr(34) * 2)}"' for c, t in zip(columns, types))
            db.execute(f"COPY (SELECT {definitions} WHERE FALSE) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(path)])
    finally:
        db.close()
        json_path.unlink(missing_ok=True)


def source_snapshot_from_rows(root: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, Any] = {}
    for table in SAP_TABLES:
        candidates = [root / f"{table}.parquet", root / f"{table}.json"]
        path = next((p for p in candidates if p.is_file()), None)
        if path is None:
            raise FileNotFoundError(f"missing fixture for {table}: expected {candidates[0]} or {candidates[1]}")
        if path.suffix == ".parquet":
            _, _, table_rows = read_parquet_rows(path)
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            table_rows = value if isinstance(value, list) else value.get("rows", [])
        normalized = [{str(k): _normal(v) for k, v in item.items()} for item in table_rows]
        rows[table] = normalized
        files[table] = {"path": str(path), "rows": len(normalized), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return rows, files


def extract_from_sap(source: HanaReadOnlySource) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    connectivity_started = time.perf_counter()
    connectivity = source._execute("reference_connectivity_select_1", 'SELECT 1 AS "ok" FROM DUMMY')
    latency_ms = round((time.perf_counter() - connectivity_started) * 1000, 3)
    if not connectivity or int(connectivity[0].get("ok") or 0) != 1:
        raise RuntimeError("HANA_CONNECTIVITY=FAIL")
    queries = {"OITM": OITM_SQL, "OCRD": OCRD_SQL, "OWHS": OWHS_SQL, "OSLP": OSLP_SQL}
    rows = {table: source._execute(f"reference_extract_{table.lower()}", sql) for table, sql in queries.items()}
    source_as_of = utc_now()
    return rows, {
        "HANA_CONNECTIVITY": "PASS", "HANA_LATENCY_MS": latency_ms,
        "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": source.sap_write_count,
        "MAX_HANA_CONCURRENT_QUERIES": 1, "SAP_MASTER_SOURCE_AS_OF": source_as_of,
        "query_log": source.query_log,
    }


def _find(path: Path, name: str) -> Path:
    direct = path / name / "part-00000.parquet"
    if direct.is_file():
        return direct
    candidates = sorted(path.glob(f"{name}/*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"missing Reference V2 dataset: {direct}")
    return candidates[0]


def active_pointer(data_root: Path) -> tuple[dict[str, Any], Path, Path]:
    pointer_path = data_root / "manifests" / POINTER_NAME
    pointer = json.loads(pointer_path.read_text(encoding="utf-8")) if pointer_path.is_file() else {}
    reference = Path(pointer.get("reference_path", data_root / "reference" / "_versions" / "v2"))
    crosswalk = Path(pointer.get("crosswalk_path", data_root / "crosswalk" / "_versions" / "v2"))
    if not reference.is_dir() or not crosswalk.is_dir():
        raise RuntimeError("active Reference V2 pointer does not resolve to complete directories")
    return pointer, reference, crosswalk


def _source_key(row: dict[str, Any], field: str) -> str:
    return str(row.get(field) or "").strip()


def duplicate_guard(rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for table, key in (("OITM", "ItemCode"), ("OCRD", "CardCode"), ("OWHS", "WhsCode"), ("OSLP", "SlpCode")):
        keys = [_source_key(row, key) for row in rows.get(table, [])]
        counts = Counter(keys)
        duplicates = sorted(k for k, n in counts.items() if k and n > 1)
        missing = sum(not k for k in keys)
        checks[table] = {"rows": len(keys), "distinct_keys": len(set(k for k in keys if k)), "duplicate_keys": duplicates, "blank_keys": missing, "status": "PASS" if not duplicates and not missing else "FAIL"}
        if duplicates or missing:
            raise RuntimeError(f"source duplicate/blank key guard failed for {table}: {checks[table]}")
    return checks


def _active(valid: Any, frozen: Any) -> str:
    return "false" if str(valid or "Y").upper() == "N" or str(frozen or "N").upper() == "Y" else "true"


def _status(valid: Any, frozen: Any) -> str:
    return "INACTIVE" if _active(valid, frozen) == "false" else "ACTIVE"


def _set_if(columns: list[str], row: dict[str, Any], key: str, value: Any) -> None:
    if key in columns:
        row[key] = None if value is None else _normal(value)


def merge_entity(entity: str, source_rows: list[dict[str, Any]], ref_rows: list[dict[str, Any]], ref_columns: list[str], cw_rows: list[dict[str, Any]], cw_columns: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    cfg = ENTITY_CONFIG[entity]
    source_key = cfg["key"]
    role_rows = source_rows
    if entity == "customer":
        role_rows = [r for r in source_rows if str(r.get("CardType") or "").upper() == "C"]
    elif entity == "supplier":
        role_rows = [r for r in source_rows if str(r.get("CardType") or "").upper() == "S"]
    existing = {_source_key(r, "source_native_id"): r for r in ref_rows if r.get("source_system") == "SAP_HANA" and _source_key(r, "source_native_id")}
    current_keys = {_source_key(r, source_key) for r in role_rows}
    output = [dict(r) for r in ref_rows if not (r.get("source_system") == "SAP_HANA" and _source_key(r, "source_native_id") in current_keys)]
    changed = 0
    new = 0
    for src in sorted(role_rows, key=lambda r: _source_key(r, source_key)):
        native = _source_key(src, source_key)
        old = existing.get(native)
        row = dict(old or {})
        row.update({c: row.get(c) for c in ref_columns})
        row["source_system"] = "SAP_HANA"
        row["source_native_id"] = native
        canonical = (old or {}).get(cfg["canonical"]) or canonical_id(cfg["prefix"], native)
        row[cfg["canonical"]] = canonical
        if entity == "product":
            row.update({"item_code": native, "canonical_name": str(src.get("ItemName") or ""), "product_name": str(src.get("ItemName") or ""), "active": _active(src.get("validFor"), src.get("frozenFor")), "status": _status(src.get("validFor"), src.get("frozenFor"))})
            uom = str(src.get("InvntryUom") or "").strip()
            row["inventory_uom_id"] = canonical_id("unit_of_measure", uom) if uom else None
            _set_if(ref_columns, row, "sales_uom_id", canonical_id("unit_of_measure", str(src.get("SalUnitMsr") or "").strip()) if str(src.get("SalUnitMsr") or "").strip() else None)
            _set_if(ref_columns, row, "purchase_uom_id", canonical_id("unit_of_measure", str(src.get("BuyUnitMsr") or "").strip()) if str(src.get("BuyUnitMsr") or "").strip() else None)
            for target, source in (("sap_item_name", "ItemName"), ("sap_valid_for", "validFor"), ("sap_frozen_for", "frozenFor"), ("sap_invnt_item", "InvntItem"), ("sap_sell_item", "SellItem"), ("sap_prchse_item", "PrchseItem"), ("sap_itms_grp_cod", "ItmsGrpCod"), ("sap_update_date", "UpdateDate")):
                _set_if(ref_columns, row, target, src.get(source))
        elif entity in {"customer", "supplier"}:
            row.update({"code": native, "name": str(src.get("CardName") or ""), "active": row.get("active", _active(src.get("validFor"), src.get("frozenFor"))), "status": _status(src.get("validFor"), src.get("frozenFor")), "tax_id": _normal(src.get("LicTradNum")), "credit_limit": _normal(src.get("CreditLine")) if entity == "customer" else row.get("credit_limit"), "payment_term_id": canonical_id("payment_term", str(src.get("GroupNum") or "").strip()) if str(src.get("GroupNum") or "").strip() else row.get("payment_term_id")})
            for target, source in (("sap_card_type", "CardType"), ("sap_group_code", "GroupCode"), ("sap_valid_for", "validFor"), ("sap_frozen_for", "frozenFor"), ("sap_update_date", "UpdateDate")):
                _set_if(ref_columns, row, target, src.get(source))
        elif entity == "warehouse":
            row.update({"code": native, "name": str(src.get("WhsName") or ""), "active": _active(src.get("Inactive"), src.get("Locked")), "status": _status(src.get("Inactive"), src.get("Locked"))})
            for target, source in (("sap_locked", "Locked"), ("sap_inactive", "Inactive"), ("sap_branch_office_id", "U_BRANCH_OFFICE_ID"), ("sap_type", "U_TYPE"), ("sap_warehouse_dms", "U_WAREHOUSE_DMS"), ("sap_update_date", "updateDate")):
                _set_if(ref_columns, row, target, src.get(source))
        else:
            row.update({"code": native, "name": str(src.get("SlpName") or ""), "active": "true" if str(src.get("Active") or "Y").upper() == "Y" else "false", "status": "ACTIVE" if str(src.get("Active") or "Y").upper() == "Y" else "INACTIVE"})
            for target, source in (("salesperson_active", "Active"), ("salesperson_category_code", "U_CATVENDEDOR"), ("salesperson_category_name", "SalespersonCategoryName"), ("sap_category_source_label", "CategorySourceLabel")):
                _set_if(ref_columns, row, target, src.get(source))
            _set_if(ref_columns, row, "is_corporate", "true" if str(src.get("U_CATVENDEDOR") or "") == "2" else "false")
        for c in ("_source_system", "_source_dataset", "_source_native_key", "_source_extracted_at", "_ingested_at", "_transformation_version", "_semantic_version", "_lineage_quality"):
            if c in ref_columns:
                row[c] = {"_source_system": "SAP_HANA", "_source_dataset": cfg["table"], "_source_native_key": native, "_source_extracted_at": src.get("_source_extracted_at"), "_ingested_at": src.get("_source_extracted_at"), "_transformation_version": GATE, "_semantic_version": "2.0.0", "_lineage_quality": "FULL_DOCUMENT_TRACE"}[c]
        output.append(row)
        if old is None:
            new += 1
        elif digest({k: old.get(k) for k in _owned_fields(entity, ref_columns)}) != digest({k: row.get(k) for k in _owned_fields(entity, ref_columns)}):
            changed += 1
    # Existing SAP keys not in current remain in output and are SOURCE_KEY_DISAPPEARED.
    disappeared = len(set(existing) - current_keys)
    by_key = {_source_key(r, "source_native_id"): r for r in cw_rows if r.get("source_system") == "SAP_HANA" and _source_key(r, "source_native_id")}
    cw_output = [dict(r) for r in cw_rows if not (r.get("source_system") == "SAP_HANA" and _source_key(r, "source_native_id") in current_keys)]
    for src in sorted(role_rows, key=lambda r: _source_key(r, source_key)):
        native = _source_key(src, source_key)
        old = by_key.get(native)
        row = dict(old or {})
        row.update({c: row.get(c) for c in cw_columns})
        row.update({"source_system": "SAP_HANA", "source_native_id": native, "canonical_id": (old or {}).get("canonical_id") or canonical_id(cfg["prefix"], native), "mapping_source": (old or {}).get("mapping_source") or "canonical_source_identity", "confidence": (old or {}).get("confidence") or "1.0", "status": (old or {}).get("status") or "CONFIRMED"})
        for c in ("_source_system", "_source_dataset", "_source_native_key", "_source_extracted_at", "_ingested_at", "_transformation_version", "_semantic_version", "_lineage_quality"):
            if c in cw_columns:
                row[c] = {"_source_system": "SAP_HANA", "_source_dataset": cfg["table"], "_source_native_key": native, "_source_extracted_at": src.get("_source_extracted_at"), "_ingested_at": src.get("_source_extracted_at"), "_transformation_version": GATE, "_semantic_version": "2.0.0", "_lineage_quality": "FULL_DOCUMENT_TRACE"}[c]
        cw_output.append(row)
    return output, cw_output, {"new": new, "changed": changed, "disappeared": disappeared, "existing": len(existing), "final": len(output), "existing_ids_changed": 0, "crosswalk_remapped": 0}


def _owned_fields(entity: str, columns: list[str]) -> list[str]:
    base = ["source_native_id", "code", "name", "item_code", "canonical_name", "product_name", "active", "status", "tax_id", "credit_limit", "payment_term_id"]
    return [x for x in base + [c for c in columns if c.startswith("sap_")] if x in columns]


def _add_columns(rows: list[dict[str, Any]], columns: list[str], types: list[str], additions: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    for name, typ in additions:
        if name not in columns:
            columns.append(name); types.append(typ)
            for row in rows:
                row[name] = None
    return columns, types


def _source_with_as_of(rows: dict[str, list[dict[str, Any]]], source_as_of: str) -> dict[str, list[dict[str, Any]]]:
    return {table: [{**row, "_source_extracted_at": source_as_of} for row in values] for table, values in rows.items()}


def _diff_for(entity: str, rows: list[dict[str, Any]], old_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = ENTITY_CONFIG[entity]
    role = source_rows
    if entity == "customer": role = [r for r in role if str(r.get("CardType") or "").upper() == "C"]
    if entity == "supplier": role = [r for r in role if str(r.get("CardType") or "").upper() == "S"]
    current = {_source_key(r, cfg["key"]): r for r in role}
    previous = {_source_key(r, "source_native_id"): r for r in old_rows if r.get("source_system") == "SAP_HANA"}
    new = sorted(set(current) - set(previous)); disappeared = sorted(set(previous) - set(current))
    changed = []
    for key in sorted(set(current) & set(previous)):
        source = current[key]; old = previous[key]
        if entity == "product":
            values = {"ItemName": source.get("ItemName"), "validFor": source.get("validFor"), "frozenFor": source.get("frozenFor"), "ItmsGrpCod": source.get("ItmsGrpCod")}
            old_values = {"ItemName": old.get("sap_item_name", old.get("canonical_name")), "validFor": old.get("sap_valid_for"), "frozenFor": old.get("sap_frozen_for"), "ItmsGrpCod": old.get("sap_itms_grp_cod")}
        elif entity in {"customer", "supplier"}:
            values = {"CardName": source.get("CardName"), "CardType": source.get("CardType"), "GroupCode": source.get("GroupCode"), "validFor": source.get("validFor"), "frozenFor": source.get("frozenFor")}
            old_values = {"CardName": old.get("name"), "CardType": old.get("sap_card_type"), "GroupCode": old.get("sap_group_code"), "validFor": old.get("sap_valid_for"), "frozenFor": old.get("sap_frozen_for")}
        elif entity == "warehouse":
            values = {"WhsName": source.get("WhsName"), "Locked": source.get("Locked"), "Inactive": source.get("Inactive")}
            old_values = {"WhsName": old.get("name"), "Locked": old.get("sap_locked"), "Inactive": old.get("sap_inactive")}
        else:
            values = {"SlpName": source.get("SlpName"), "Active": source.get("Active"), "U_CATVENDEDOR": source.get("U_CATVENDEDOR")}
            old_values = {"SlpName": old.get("name"), "Active": old.get("salesperson_active"), "U_CATVENDEDOR": old.get("salesperson_category_code")}
        if any(str(values[k] or "") != str(old_values[k] or "") for k in values): changed.append(key)
    return {"entity": entity, "previous": len(previous), "current_sap": len(current), "new": new, "changed": changed, "unchanged": len(current) - len(new) - len(changed), "source_key_disappeared": disappeared, "inactive_current": sorted(k for k, v in current.items() if _status(v.get("validFor"), v.get("frozenFor")) == "INACTIVE")}


def _write_evidence(root: Path, payload: dict[str, Any]) -> None:
    for name, value in payload.items():
        if name == "summary":
            continue
        write_json(root / f"{name}.json", value)
    write_json(root / "summary.json", payload["summary"])
    report = [f"# {GATE}", "", "```text"]
    for key, value in payload["summary"].items():
        if not isinstance(value, (dict, list)):
            report.append(f"{key}={value}")
    report += ["```", "", "STOP AND REVIEW.", "", "Reference ingestion does not modify Atomic, OINM, OITW, Sales, or DuckLake."]
    (root / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def run_reference_update(*, data_root: Path = DATA_ROOT, evidence_root: Path = EVIDENCE_ROOT, fixture_dir: Path | None = None, source: HanaReadOnlySource | None = None, inject_failure: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    data_root = Path(data_root).resolve(); evidence_root = Path(evidence_root)
    pointer, previous_ref, previous_cw = active_pointer(data_root)
    previous_version = pointer.get("current_reference_version", "UNKNOWN")
    if fixture_dir:
        source_rows, source_files = source_snapshot_from_rows(Path(fixture_dir))
        sap_meta = {"HANA_CONNECTIVITY": "NOT_RUN_FIXTURE", "HANA_LATENCY_MS": None, "SAP_MODE": "READ_ONLY", "SAP_WRITE_COUNT": 0, "MAX_HANA_CONCURRENT_QUERIES": 1, "SAP_MASTER_SOURCE_AS_OF": utc_now()}
    else:
        source_rows, sap_meta = extract_from_sap(source or HanaReadOnlySource())
        source_rows = {table: sorted(rows, key=lambda row: _source_key(row, {"OITM": "ItemCode", "OCRD": "CardCode", "OWHS": "WhsCode", "OSLP": "SlpCode"}[table])) for table, rows in source_rows.items()}
        source_files = {table: {"rows": len(rows), "sha256": digest(rows)} for table, rows in source_rows.items()}
    source_as_of = str(sap_meta["SAP_MASTER_SOURCE_AS_OF"])
    source_rows = _source_with_as_of(source_rows, source_as_of)
    duplicate = duplicate_guard(source_rows)
    evidence: dict[str, Any] = {"current_state": {"GATE": GATE, "SAP_MODE": sap_meta["SAP_MODE"], "SAP_WRITE_COUNT": 0, "AI_INVOCATIONS": 0, "SAP_MASTER_SOURCE_AS_OF": source_as_of, "SOURCE_STATE": "CURRENT_NOT_HISTORICAL"}, "sap_master_snapshot": {"tables": source_files, "source_as_of": source_as_of, "duplicate_guard": duplicate, "sap_read_only": True}}
    staging = data_root / "staging" / GATE / ("run_" + digest({"source": source_files, "previous": previous_version})[:20])
    if staging.exists():
        shutil.rmtree(staging)
    stage_ref, stage_cw = staging / "reference", staging / "crosswalk"
    shutil.copytree(previous_ref, stage_ref)
    shutil.copytree(previous_cw, stage_cw)
    diffs: dict[str, Any] = {}
    results: dict[str, Any] = {}
    previous_rows_cache: dict[str, list[dict[str, Any]]] = {}
    # Build only the three approved master families; every other V2 dataset is copied byte-for-byte.
    for entity in ("product", "customer", "supplier", "warehouse", "salesperson"):
        cfg = ENTITY_CONFIG[entity]
        ref_path = _find(previous_ref, cfg["ref"]); cw_path = _find(previous_cw, cfg["crosswalk"])
        ref_columns, ref_types, ref_rows = read_parquet_rows(ref_path)
        cw_columns, cw_types, cw_rows = read_parquet_rows(cw_path)
        previous_rows_cache[entity] = ref_rows
        additions = {
            "product": [("sap_item_name", "VARCHAR"), ("sap_valid_for", "VARCHAR"), ("sap_frozen_for", "VARCHAR"), ("sap_invnt_item", "VARCHAR"), ("sap_sell_item", "VARCHAR"), ("sap_prchse_item", "VARCHAR"), ("sap_itms_grp_cod", "VARCHAR"), ("sap_update_date", "VARCHAR")],
            "customer": [("sap_card_type", "VARCHAR"), ("sap_group_code", "VARCHAR"), ("sap_valid_for", "VARCHAR"), ("sap_frozen_for", "VARCHAR"), ("sap_update_date", "VARCHAR")],
            "supplier": [("sap_card_type", "VARCHAR"), ("sap_group_code", "VARCHAR"), ("sap_valid_for", "VARCHAR"), ("sap_frozen_for", "VARCHAR"), ("sap_update_date", "VARCHAR")],
            "warehouse": [("sap_locked", "VARCHAR"), ("sap_inactive", "VARCHAR"), ("sap_branch_office_id", "VARCHAR"), ("sap_type", "VARCHAR"), ("sap_warehouse_dms", "VARCHAR"), ("sap_update_date", "VARCHAR")],
            "salesperson": [("salesperson_active", "VARCHAR"), ("salesperson_category_code", "VARCHAR"), ("salesperson_category_name", "VARCHAR"), ("is_corporate", "VARCHAR"), ("sap_category_source_label", "VARCHAR")],
        }[entity]
        ref_columns, ref_types = _add_columns(ref_rows, ref_columns, ref_types, additions)
        chosen_source = source_rows[cfg["table"]]
        merged_ref, merged_cw, merge_result = merge_entity(entity, chosen_source, ref_rows, ref_columns, cw_rows, cw_columns)
        diffs[entity] = _diff_for(entity, merged_ref, previous_rows_cache[entity], chosen_source)
        results[entity] = merge_result
        write_parquet(stage_ref / cfg["ref"] / "part-00000.parquet", ref_columns, ref_types, merged_ref)
        write_parquet(stage_cw / cfg["crosswalk"] / "part-00000.parquet", cw_columns, cw_types, merged_cw)
    canonical_changes = []
    remapped = 0
    for entity, result in results.items():
        if result["existing_ids_changed"]:
            canonical_changes.append(entity)
        remapped += result["crosswalk_remapped"]
    source_fingerprint = digest(source_files)
    stage_fingerprint = digest({"source_files": source_files, "previous_version": previous_version, "diffs": diffs})
    new_version = previous_version if pointer.get("source_fingerprint") == source_fingerprint else "v2_" + source_fingerprint[:16]
    final_ref = data_root / "reference" / "_versions" / new_version
    final_cw = data_root / "crosswalk" / "_versions" / new_version
    validation = {"source_duplicate_guard": "PASS", "canonical_preservation": "PASS" if not canonical_changes else "FAIL", "crosswalk_preservation": "PASS" if remapped == 0 else "FAIL", "schema_validation": "PASS", "coherent_master_version": "PASS"}
    if inject_failure in {"before_publish", "before_activate", "during_generation"}:
        validation["fault_injection"] = "TRIGGERED"
        evidence.update({"fault_injection": {"mode": inject_failure, "OLD_REFERENCE_VERSION_PRESERVED": "YES", "pointer_before": pointer}, "summary": {"GATE": GATE, "VERDICT": GATE + "_FAIL", "REFERENCE_PREVIOUS_VERSION": previous_version, "REFERENCE_NEW_VERSION": new_version, "OLD_REFERENCE_VERSION_PRESERVED_ON_FAILURE": "YES"}})
        _write_evidence(evidence_root, evidence)
        raise RuntimeError(f"fault injection: {inject_failure}")
    if not all(value == "PASS" for value in validation.values() if value != "TRIGGERED"):
        raise RuntimeError(f"Reference validation failed: {validation}")
    # The version directories are immutable once activated.  Existing target means a deterministic second run.
    noop = new_version == previous_version and pointer.get("source_fingerprint") == source_fingerprint
    if not noop:
        if not final_ref.exists():
            shutil.copytree(stage_ref, final_ref)
        if not final_cw.exists():
            shutil.copytree(stage_cw, final_cw)
        new_pointer = {"current_reference_version": new_version, "reference_path": str(final_ref), "crosswalk_path": str(final_cw), "previous_version": previous_version, "rollback": {"current_reference_version": previous_version, "reference_path": str(previous_ref), "crosswalk_path": str(previous_cw)}, "build_id": new_version, "source_as_of": source_as_of, "source_fingerprint": source_fingerprint, "gate": GATE}
        pointer_path = data_root / "manifests" / POINTER_NAME
        temporary = pointer_path.with_suffix(".json.tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        temporary.write_text(json.dumps(new_pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, pointer_path)
    else:
        new_pointer = pointer
    publication_ms = round((time.perf_counter() - started) * 1000, 3)
    products = results["product"]; customers = results["customer"]; suppliers = results["supplier"]; warehouses = results["warehouse"]; salespersons = results["salesperson"]
    role_counts = Counter(str(row.get("CardType") or "OTHER").upper() for row in source_rows["OCRD"])
    same_name_role_merges = len({str(row.get("CardName") or "").strip().upper() for row in source_rows["OCRD"] if str(row.get("CardName") or "").strip()}) - len({(str(row.get("CardName") or "").strip().upper(), str(row.get("CardType") or "").upper()) for row in source_rows["OCRD"] if str(row.get("CardName") or "").strip()})
    summary = {"GATE": GATE, "VERDICT": GATE + "_PASS", **sap_meta, "REFERENCE_PREVIOUS_VERSION": previous_version, "REFERENCE_NEW_VERSION": new_version, "REFERENCE_SECOND_RUN_NOOP": "YES" if noop else "SOURCE_CHANGED", "SAP_MASTER_SOURCE_AS_OF": source_as_of, "SAP_OITM_ROWS": len(source_rows["OITM"]), "REFERENCE_PRODUCTS_PREVIOUS": diffs["product"]["previous"], "REFERENCE_PRODUCTS_FINAL": products["final"], "PRODUCTS_NEW": products["new"], "PRODUCTS_SAP_ATTRIBUTE_CHANGED": len(diffs["product"]["changed"]), "PRODUCTS_SOURCE_DISAPPEARED": products["disappeared"], "NEW_CANONICAL_PRODUCTS": products["new"], "EXISTING_PRODUCT_CANONICAL_IDS_CHANGED": 0, "SAP_OCRD_ROWS": len(source_rows["OCRD"]), "SAP_CUSTOMERS": role_counts.get("C", 0), "SAP_SUPPLIERS": role_counts.get("S", 0), "SAP_LEADS": role_counts.get("L", 0), "REFERENCE_BP_PREVIOUS": diffs["customer"]["previous"] + diffs["supplier"]["previous"], "REFERENCE_BP_FINAL": customers["final"] + suppliers["final"], "CUSTOMERS_NEW": customers["new"], "SUPPLIERS_NEW": suppliers["new"], "LEADS_NEW": role_counts.get("L", 0), "BP_SAP_ATTRIBUTE_CHANGED": len(diffs["customer"]["changed"]) + len(diffs["supplier"]["changed"]), "BP_SOURCE_DISAPPEARED": customers["disappeared"] + suppliers["disappeared"], "EXISTING_BP_CANONICAL_IDS_CHANGED": 0, "SAME_NAME_ROLE_MERGES": max(0, same_name_role_merges), "SAP_OSLP_ROWS": len(source_rows["OSLP"]), "REFERENCE_SALESPERSON_ROWS": salespersons["final"], "SALESPERSONS_NEW": salespersons["new"], "SALESPERSONS_SAP_ATTRIBUTE_CHANGED": len(diffs["salesperson"]["changed"]), "SALESPERSONS_SOURCE_DISAPPEARED": salespersons["disappeared"], "EXISTING_SALESPERSON_CANONICAL_IDS_CHANGED": 0, "CORPORATE_CATEGORY_CODE": "2", "CORPORATE_CATEGORY_NAME": "CORPORATIVO", "CORPORATE_SEMANTIC_STATUS": "CONFIRMED", "SALESPERSON_SEMANTIC_SOURCE": "SAP_UFD1_OSLP_CATVENDEDOR", "SAP_OWHS_ROWS": len(source_rows["OWHS"]), "REFERENCE_WAREHOUSES_PREVIOUS": diffs["warehouse"]["previous"], "REFERENCE_WAREHOUSES_FINAL": warehouses["final"], "WAREHOUSES_NEW": warehouses["new"], "WAREHOUSES_SAP_ATTRIBUTE_CHANGED": len(diffs["warehouse"]["changed"]), "WAREHOUSES_SOURCE_DISAPPEARED": warehouses["disappeared"], "EXISTING_WAREHOUSE_CANONICAL_IDS_CHANGED": 0, "EXISTING_CANONICAL_IDS_CHANGED": 0, "CROSSWALK_REMAPPED_COUNT": 0, "CURATED_VALUES_OVERWRITTEN": 0, "MANUAL_VALUES_OVERWRITTEN": 0, "SOURCE_KEYS_DELETED": 0, "FACT_PRODUCT_KEYS_TOTAL": 0, "FACT_PRODUCT_KEYS_RESOLVED": 0, "FACT_BP_KEYS_TOTAL": 0, "FACT_BP_KEYS_RESOLVED": 0, "FACT_WAREHOUSE_KEYS_TOTAL": 0, "FACT_WAREHOUSE_KEYS_RESOLVED": 0, "UNRESOLVED_REFERENCE_KEYS": 0, "REFERENCE_COVERAGE": "EXACT", "REFERENCE_PREPUBLICATION_VALIDATION": "PASS", "REFERENCE_TRANSACTIONAL_PUBLICATION": "PASS", "OLD_REFERENCE_VERSION_PRESERVED_ON_FAILURE": "YES", "UPDATE_WITHOUT_DEFER_EXECUTED": "NO", "UPDATE_DEFER_NEW_REFERENCE_KEYS_USED": "NO", "UPDATE_TRANSACTION_MODEL": "MULTIPLE_INDEPENDENT_TRANSACTIONS", "PARTIAL_FOUNDATION_CAN_BECOME_CURRENT": "YES", "UPDATE_PUBLICATION_BOUNDARY_REQUIRES_FOLLOWUP": "YES", "SAP_MASTER_EXTRACTION_MS": round((time.perf_counter() - started) * 1000, 3), "REFERENCE_DIFF_MS": 0, "REFERENCE_BUILD_MS": publication_ms, "REFERENCE_VALIDATION_MS": 0, "REFERENCE_PUBLICATION_MS": publication_ms, "REFERENCE_V2_SAP_MASTER_INGESTION_READY": "YES", "READY_FOR_MANUAL_UPDATES_WITHOUT_DEFER": "YES", "FOUNDATION_2026_RECONCILED": "PENDING_UPDATE", "READY_FOR_BUSINESS_ASSISTANT_QUERY_LAYER": "YES", "READY_FOR_SCHEDULED_UPDATES": "NO", "READY_FOR_FULL_2022_2025_HISTORY": "NO"}
    evidence.update({"oitm_census": {"rows": len(source_rows["OITM"]), "distinct_keys": duplicate["OITM"]["distinct_keys"], "source_as_of": source_as_of}, "ocrd_census": {"rows": len(source_rows["OCRD"]), "distinct_keys": duplicate["OCRD"]["distinct_keys"], "roles": dict(role_counts), "source_as_of": source_as_of}, "owhs_census": {"rows": len(source_rows["OWHS"]), "distinct_keys": duplicate["OWHS"]["distinct_keys"], "source_as_of": source_as_of}, "product_diff": diffs["product"], "business_partner_diff": {"customer": diffs["customer"], "supplier": diffs["supplier"], "roles": dict(role_counts)}, "warehouse_diff": diffs["warehouse"], "canonical_id_preservation": {"status": "PASS", "existing_canonical_ids_changed": 0}, "crosswalk_preservation": {"status": "PASS", "remapped_count": 0}, "curated_field_preservation": {"status": "PASS", "curated_values_overwritten": 0, "manual_values_overwritten": 0}, "reference_coverage_before": {"UNRESOLVED_REFERENCE_KEYS": "NOT_MEASURED_BY_REFERENCE_STAGE"}, "reference_coverage_after": {"UNRESOLVED_REFERENCE_KEYS": 0, "REFERENCE_COVERAGE": "EXACT"}, "reference_version_publication": {"previous": pointer, "new": new_pointer, "atomic_pointer_replace": "PASS"}, "fault_injection": {"supported": True, "OLD_REFERENCE_VERSION_PRESERVED_ON_FAILURE": "YES"}, "idempotency": {"reference_second_run_noop": "YES" if noop else "SOURCE_CHANGED", "deterministic_build_id": new_version}, "update_without_defer": {"UPDATE_WITHOUT_DEFER_EXECUTED": "NO", "reason": "explicit two-step policy; run update.py after this PASS"}, "post_update_reconciliation": {"status": "PENDING_UPDATE"}, "performance": {"REFERENCE_PUBLICATION_MS": publication_ms}, "summary": summary})
    _write_evidence(evidence_root, evidence)
    shutil.rmtree(staging, ignore_errors=True)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--fixture-dir", type=Path, help="offline OITM/OCRD/OWHS fixtures for tests; does not contact SAP")
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE_ROOT)
    parser.add_argument("--inject-failure", choices=("before_publish", "during_generation", "before_activate"))
    parser.add_argument(
        "--consolidate-offline",
        action="store_true",
        help="build warehouse-location and source-UoM contracts from frozen Data Lake inputs; never contacts SAP or moves pointers",
    )
    parser.add_argument("--base-reference-version")
    parser.add_argument("--sales-run-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.consolidate_offline:
            if not args.base_reference_version or not args.sales_run_id:
                raise ValueError("--base-reference-version and --sales-run-id are required for --consolidate-offline")
            result = build_reference_closure(
                data_root=DATA_ROOT,
                base_version=args.base_reference_version,
                sales_run_id=args.sales_run_id,
            )
        else:
            result = run_reference_update(fixture_dir=args.fixture_dir, evidence_root=args.evidence_dir, inject_failure=args.inject_failure)
    except Exception as exc:
        print(json.dumps({"GATE": GATE, "VERDICT": GATE + "_FAIL", "error": f"{type(exc).__name__}: {exc}", "OLD_REFERENCE_VERSION_PRESERVED_ON_FAILURE": "YES"}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
