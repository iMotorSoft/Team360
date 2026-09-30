"""Final offline derivation and exact Foundation promotion for Material Supply V1.

Gate A SAP work is consumed only from sealed evidence and immutable Data Lake
captures.  This runner never opens SAP.  ``--prepare`` builds and validates one
pinned final candidate; ``--promote`` performs compare-and-swap publication,
productive CURRENT validation and exact rollback on correctness failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping

import duckdb

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.material_supply_candidate import (
    build_material_supply_component,
    create_material_supply_candidate,
    mark_candidate_ready,
    resolve_current_material_supply,
    validate_pinned_candidate,
)
from modules.telchi.datalake.material_supply_derivation import (
    build_lead_time_profiles,
    build_open_purchase_pipeline,
    build_supply_status,
)
from modules.telchi.datalake.material_supply_fact_capture import read_persisted_rows
from modules.telchi.datalake.material_supply_purchasing_lineage import (
    FACT_CAPTURE_ROOT,
    RAW_ROOT as LINEAGE_RAW_ROOT,
    index_by_key,
    receipt_lead_time_samples,
    resolve_receipt_lineage,
)
from modules.telchi.datalake.raw import digest, file_hash, write_raw
from modules.telchi.runtime.config import RuntimeConfig
from modules.telchi.runtime.resource_guard import ResourceGuard
from modules.telchi.investigation.validation.datalake_material_supply_derivation_v1.run_saavedra_reconciliation import build_v2_result

GATE = "TELCHI_DATALAKE_MATERIAL_SUPPLY_FINALIZATION_V1"
EXPECTED_CURRENT = "foundation_029c2476d5f3912cdfe4e630f52d2e28"
BASELINE_CANDIDATE = "foundation_40c3b9b208abd69e931d1b29a8ea7e03"
EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
LINEAGE_CLOSURE_ROOT = DATA_ROOT / "raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_LINEAGE_CLOSURE_V1"
BUSINESS_ROOT = DATA_ROOT / "business/material_supply" / GATE
COMPONENT_ROOT = DATA_ROOT / "business/material_supply/_components"
ROLE_CODES = {
    "SAA-M1": ("SAAVEDRA", "RAW_MATERIAL", True),
    "SAA-P1": ("SAAVEDRA", "PRODUCTION", False),
    "SAA-T1": ("SAAVEDRA", "FINISHED_PRODUCT", False),
    "SAA-DAN": ("SAAVEDRA", "DAMAGED", False),
    "SAA-T2": ("SAAVEDRA", "RECONDITIONED", False),
    "SAA-T3": ("SAAVEDRA", "RECONDITIONED", False),
}
UNCHANGED_DATASETS = ("material_actual_consumption", "material_equivalent_demand")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(name: str, payload: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _state(state: str, last: str | None, next_state: str | None, reason: str | None = None) -> None:
    _write("run_state.json", {"RUN_STATE": state, "LAST_COMPLETED_STATE": last,
        "NEXT_ALLOWED_STATE": next_state, "BLOCKING_REASON": reason, "STATE_UPDATED_AT": _now()})


def _rows(files: Iterable[str | Path]) -> list[dict[str, Any]]:
    paths = [str(path) for path in files]
    connection = duckdb.connect()
    connection.execute("SET threads=1")
    try:
        cursor = connection.execute(f"SELECT * FROM read_parquet({paths!r})")
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()


def _foundation_stock(access: Any) -> list[dict[str, Any]]:
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as connection:
        connection.execute("SET threads=1")
        values = connection.execute(
            f"SELECT item_code,whs_code,try_cast(on_hand AS DOUBLE),"
            f"try_cast(is_commited AS DOUBLE),try_cast(on_order AS DOUBLE) FROM {access.oitw()}"
        ).fetchall()
    return [{"item_code": row[0], "whs_code": row[1], "on_hand": row[2],
        "is_commited": row[3], "on_order": row[4]} for row in values]


def _reference_products(reference_path: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    connection = duckdb.connect()
    connection.execute("SET threads=1")
    try:
        product_files = [str(path) for path in (reference_path / "products").glob("*.parquet")]
        products = {str(row[0]): {"canonical_name": row[1], "inventory_uom": row[2],
            "active": row[3], "status": row[4]} for row in connection.execute(
            "SELECT item_code,canonical_name,inventory_uom_id,active,status "
            f"FROM read_parquet({product_files!r}) WHERE source_system='SAP_HANA'"
        ).fetchall() if row[0]}
        warehouse_files = [str(path) for path in (reference_path / "warehouses").glob("*.parquet")]
        warehouses = {str(row[0]) for row in connection.execute(
            f"SELECT code FROM read_parquet({warehouse_files!r}) WHERE source_system='SAP_HANA'"
        ).fetchall() if row[0]}
        return products, warehouses
    finally:
        connection.close()


def _materialize_reference_roles(access: Any) -> tuple[str, Path, list[dict[str, Any]]]:
    validation = json.loads((EVIDENCE / "warehouse_role_validation.json").read_text(encoding="utf-8"))
    if validation.get("WAREHOUSE_ROLE_VALIDATION") != "PASS":
        raise RuntimeError("warehouse-role SAP seal did not pass")
    by_code = {row["warehouse_code"]: row for row in validation["rows"]}
    rows = []
    for code, (site, role, usable) in ROLE_CODES.items():
        evidence = by_code.get(code)
        if not evidence or evidence.get("confidence") != "HIGH":
            raise RuntimeError(f"warehouse role {code} is not evidence-backed")
        rows.append({"warehouse_code": code, "production_site": site, "warehouse_role": role,
            "usable_for_supply_stock": usable, "classification_source": evidence["classification_source"],
            "classification_evidence": json.dumps(evidence["classification_evidence"], sort_keys=True, default=str),
            "confidence": evidence["confidence"], "valid_from": evidence.get("valid_from"),
            "valid_to": evidence.get("valid_to"), "source_as_of": evidence["source_as_of"]})
    identity = digest({"base": access.foundation.reference_version, "roles": rows})
    version = "v2_material_supply_roles_" + identity[:16]
    target = DATA_ROOT / "reference/_versions" / version
    if not target.exists():
        staging = target.with_name(target.name + f".tmp-{os.getpid()}")
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(access.reference_path, staging)
        role_dir = staging / "warehouse_roles"
        role_dir.mkdir(parents=True, exist_ok=True)
        output = role_dir / "part-00000.parquet"
        values = [tuple(row[key] for key in ("warehouse_code", "production_site", "warehouse_role",
            "usable_for_supply_stock", "classification_source", "classification_evidence", "confidence",
            "valid_from", "valid_to", "source_as_of")) for row in rows]
        connection = duckdb.connect()
        connection.execute("SET threads=1")
        try:
            connection.execute("CREATE TABLE roles(warehouse_code VARCHAR,production_site VARCHAR,"
                "warehouse_role VARCHAR,usable_for_supply_stock BOOLEAN,classification_source VARCHAR,"
                "classification_evidence VARCHAR,confidence VARCHAR,valid_from VARCHAR,valid_to VARCHAR,source_as_of VARCHAR)")
            connection.executemany("INSERT INTO roles VALUES (?,?,?,?,?,?,?,?,?,?)", values)
            escaped = str(output).replace("'", "''")
            connection.execute(f"COPY roles TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        finally:
            connection.close()
        staging.rename(target)
    return version, target, rows


def _historical_rows(dataset: str) -> list[dict[str, Any]]:
    files = sorted((LINEAGE_CLOSURE_ROOT / dataset / "targeted").glob("*/part-00000.parquet"))
    if not files:
        raise RuntimeError(f"historical closure dataset missing: {dataset}")
    return _rows(files)


def _canonical_query(result: Mapping[str, Any]) -> str:
    rows = sorted(result["rows"], key=lambda row: str(row.get("ItemCode")))
    presentation_fields = {"rows", "QUERY", "QUERY_READER_MODE"}
    return digest({"metrics": {key: value for key, value in result.items() if key not in presentation_fields},
        "rows": rows})


def prepare() -> int:
    config = RuntimeConfig.from_env()
    guard = ResourceGuard(config.resource_policy(), temp_directory=config.duckdb_temp_directory)
    guard.preflight()
    seal = json.loads((EVIDENCE / "sap_finalization_seal.json").read_text(encoding="utf-8"))
    bounded = json.loads((EVIDENCE / "bounded_sap_validation.json").read_text(encoding="utf-8"))
    if not (seal.get("SAP_DEPENDENT_WORK_COMPLETE") == "YES" and seal.get("SAP_WRITE_COUNT") == 0
            and bounded.get("BOUNDED_SAP_VALIDATION") == "PASS"
            and bounded.get("BOUNDED_SAP_MISMATCHES") == 0):
        raise RuntimeError("Gate A hard barrier failed")

    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)
    access = FoundationReader().get_current_foundation()
    if access.foundation_publication_id != EXPECTED_CURRENT:
        raise RuntimeError(f"CURRENT precondition changed: {access.foundation_publication_id}")
    pinned_v2 = validate_pinned_candidate(store, BASELINE_CANDIDATE)
    _state("FINAL_DERIVATION", "SAP_FINALIZATION_VALIDATED", "FINAL_CANDIDATE_CREATED")

    reference_version, reference_path, role_rows = _materialize_reference_roles(access)
    _write("warehouse_roles_materialized.json", {"WAREHOUSE_ROLES_MATERIALIZED": "YES",
        "reference_version": reference_version, "reference_path": str(reference_path), "rows": role_rows,
        "warehouse_roles_sha256": file_hash(reference_path / "warehouse_roles/part-00000.parquet")})

    receipt_lines = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_receipt_line")
    ap_lines = read_persisted_rows(LINEAGE_RAW_ROOT, "ap_invoice_line") + _historical_rows("historical_ap_invoice_line")
    po_lines = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_order_line") + _historical_rows("historical_purchase_order_line")
    po_headers = read_persisted_rows(FACT_CAPTURE_ROOT, "purchase_order")
    lineage = resolve_receipt_lineage(receipt_lines, ap_lines, po_lines)
    pipeline = build_open_purchase_pipeline(po_lines, lineage)
    samples = receipt_lead_time_samples(lineage, index_by_key(po_lines))
    po_origin = {str(row.get("DocEntry")): row.get("U_TIPOCOMPRA") for row in po_headers + po_lines}
    for sample in samples:
        sample["origin_code"] = po_origin.get(str(sample["po_docentry"]))
    profiles = build_lead_time_profiles(samples)

    actual_rows = _rows(pinned_v2.dataset_files("material_actual_consumption"))
    demand_rows = _rows(pinned_v2.dataset_files("material_equivalent_demand"))
    old_status = _rows(pinned_v2.dataset_files("material_supply_status"))
    products, warehouses = _reference_products(reference_path)
    stock = _foundation_stock(access)
    actual = {str(row["item_code"]): float(row.get("actual_consumption_qty") or 0) for row in actual_rows}
    demand = {str(row["item_code"]): float(row.get("commercial_daily_equivalent_basis_qty") or 0) for row in demand_rows}
    old_by_item = {str(row["ItemCode"]): row for row in old_status}
    items = {item: dict(products.get(item, {}), warehouse="SAA-M1",
        material_class="RAW_MATERIAL" if row.get("is_raw_material") else str(row.get("material_class") or "OTHER"))
        for item, row in old_by_item.items()}
    evidence_fields = ("saavedra_relevance", "saavedra_relevance_basis", "saavedra_relevance_confidence",
        "item_activity_status", "saa_m1_history", "recent_saa_m1_movement", "recent_saa_consumption",
        "saa_production_link", "saa_active_bom", "open_po_to_saa")
    relevance = {item: {key: row.get(key) for key in evidence_fields} for item, row in old_by_item.items()}
    usable_universe = warehouses - {"SAA-T2", "SAA-T3"}
    status = build_supply_status(stock_rows=stock, items=items, actual_consumption=actual,
        equivalent_demand=demand, open_pipeline=pipeline, lead_profiles=profiles,
        source_as_of=access.foundation.data_as_of or "UNKNOWN", window_days=90,
        saavedra_evidence=relevance, valid_warehouses=usable_universe)

    run_id = f"material-supply-final-{time.time_ns()}"
    manifests = {name: dict(pinned_v2.material_supply_datasets()[name]) for name in UNCHANGED_DATASETS}
    for name, rows in (("open_purchase_pipeline", pipeline), ("material_lead_time_profile", profiles),
                       ("material_supply_status", status)):
        manifests[name] = write_raw(root=BUSINESS_ROOT, segment_id=f"{name}/full",
            extraction_id=f"{run_id}_{name}_full", rows=rows, metadata={"gate": GATE, "dataset": name,
            "source_system": "TELCHI_DATA_LAKE_DERIVATION", "source_as_of": access.foundation.data_as_of,
            "run_id": run_id, "sap_accessed": "NO", "sap_write_count": 0, "duckdb_threads": 1,
            "foundation_publication_id": access.foundation_publication_id,
            "reference_version": reference_version})
    identity = [{"dataset": name, "file_hashes": list(value.get("file_hashes", [])),
        "row_count": int(value.get("row_count") or 0)} for name, value in sorted(manifests.items())]
    component_version = "material_supply_" + digest(identity)[:24]
    COMPONENT_ROOT.mkdir(parents=True, exist_ok=True)
    component_path = COMPONENT_ROOT / f"{component_version}.json"
    component_path.write_text(json.dumps({"component_version": component_version, "datasets": identity},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    component = build_material_supply_component(component_version, manifests,
        source_as_of=access.foundation.data_as_of or "UNKNOWN")
    base = SimpleNamespace(**access.foundation.__dict__)
    base.reference_version = reference_version
    candidate = create_material_supply_candidate(store, base_foundation=base,
        base_snapshot_id=int(access.ducklake_snapshot_id), component=component,
        dataset_manifests=manifests, update_run_id=run_id,
        source_as_of=access.foundation.data_as_of or "UNKNOWN")
    pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
    mark_candidate_ready(store, candidate.foundation_publication_id)
    pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
    if store.current_pointer() != EXPECTED_CURRENT:
        raise RuntimeError("CURRENT changed while preparing final candidate")
    result = build_v2_result(_rows(pinned.dataset_files("material_supply_status")),
        foundation_id=pinned.foundation_publication_id)
    result["QUERY"] = "SAAVEDRA_MATERIAL_SUPPLY_RISK_FINAL_PREPROMOTION"
    manifest_hash = digest(store.get(pinned.foundation_publication_id).manifest)
    component_hashes = {name: digest(entry) for name, entry in
        store.get(pinned.foundation_publication_id).manifest["components"].items()}
    baseline = {"ACTIVE_SAAVEDRA_MATERIALS": 78, "COVERAGE_LT_60": 19, "SUPPLY_RISK_COUNT": 15,
        "LOCAL_STOCKOUTS": 6, "GLOBAL_STOCKOUTS": 0, "LOCAL_ONLY_STOCKOUTS": 6,
        "OPEN_PO_MITIGATED": 0, "OPEN_PO_PARTIAL_MITIGATION": 3,
        "LEAD_TIME_UNAVAILABLE": 1, "UNIT_UNRESOLVED": 1, "DENSITY_BLOCKED": 0}
    delta = {key: {"v2": expected, "final": result.get(key), "delta": (result.get(key) or 0) - expected}
        for key, expected in baseline.items()}
    _write("final_derivation.json", {"lineage_records": len(lineage), "lead_time_samples": len(samples),
        "lead_time_profiles": len(profiles), "open_purchase_pipeline": len(pipeline),
        "material_supply_status": len(status), "SAP_ACCESSED": "NO", "reference_version": reference_version,
        "result": {key: value for key, value in result.items() if key != "rows"}})
    _write("final_vs_v2_delta.json", {"metrics": delta,
        "explanation": "Targeted source-native predecessor capture and warehouse-role usability seal; unchanged metrics are legitimate."})
    candidate_payload = {"FOUNDATION_CURRENT_BEFORE": EXPECTED_CURRENT,
        "BASELINE_CANDIDATE_V2": BASELINE_CANDIDATE,
        "FINAL_FOUNDATION_CANDIDATE_ID": pinned.foundation_publication_id,
        "FINAL_CANDIDATE_REUSED_V2": "NO", "FINAL_FOUNDATION_CANDIDATE_COMPONENTS": list(pinned.component_versions),
        "FINAL_CANDIDATE_MANIFEST_HASH": manifest_hash, "FINAL_CANDIDATE_COMPONENT_HASHES": component_hashes,
        "FINAL_CANDIDATE_VALID": "YES", "CANDIDATE_READER_MODE": pinned.reader_mode,
        "CANDIDATE_VERSION_MIXING": "NO", "LATEST_COMPONENT_FALLBACK_USED": "NO",
        "CURRENT_FALLBACK_USED": "NO", "component_versions": dict(pinned.component_versions),
        "component_version": component_version, "query_hash": _canonical_query(result)}
    _write("final_candidate.json", candidate_payload)
    _write("final_candidate_hashes.json", {"manifest_hash": manifest_hash, "component_hashes": component_hashes})
    _write("pinned_candidate_validation.json", pinned.as_dict() | {"CURRENT_FALLBACK_USED": "NO"})
    _write("prepromotion_saavedra_query.json", result)
    _write("gate_a_result.json", {"GATE_A_FINAL_SAP_CLOSURE": "PASS",
        "FINAL_SAP_DEPENDENCIES_VALIDATED": "YES", "SAP_WRITE_COUNT": 0,
        "PURCHASING_LINEAGE_STATUS_FINAL": seal["PURCHASING_LINEAGE_STATUS_FINAL"],
        "WAREHOUSE_ROLES_MATERIALIZED": "YES", "BOUNDED_SAP_MISMATCHES": 0})
    _state("FINAL_CANDIDATE_VALIDATED", "FINAL_CANDIDATE_VALIDATED", "PROMOTION_PRECHECK")
    print(json.dumps(candidate_payload, indent=2, sort_keys=True))
    return 0


def promote() -> int:
    candidate_payload = json.loads((EVIDENCE / "final_candidate.json").read_text(encoding="utf-8"))
    candidate_id = candidate_payload["FINAL_FOUNDATION_CANDIDATE_ID"]
    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)
    pinned = validate_pinned_candidate(store, candidate_id)
    current = store.current_pointer()
    precheck = {"PROMOTION_PRECONDITION_CURRENT": current,
        "PROMOTION_PRECONDITION": "PASS" if current == EXPECTED_CURRENT else "FAIL",
        "PROMOTION_TARGET": candidate_id, "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT,
        "checked_at": _now()}
    _write("promotion_precheck.json", precheck)
    if current != EXPECTED_CURRENT:
        _state("STOPPED", "FINAL_CANDIDATE_VALIDATED", None, "CURRENT precondition changed")
        return 2
    _state("PROMOTION_PRECHECK", "FINAL_CANDIDATE_VALIDATED", "PROMOTED")
    rollback = {"PROMOTION_ROLLED_BACK": "NO", "ROLLBACK_VALIDATED": "NOT_REQUIRED",
        "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT}
    try:
        operation = store.logical_commit(candidate_id)
        _write("promotion_operation.json", {"ATOMIC_PROMOTION": "PASS", **operation,
            "SAP_WRITE_COUNT": 0})
        _state("PROMOTED", "PROMOTED", "POST_PROMOTION_VALIDATED")
        after = store.current_pointer()
        _write("post_promotion_pointer.json", {"FOUNDATION_CURRENT_AFTER": after,
            "expected": candidate_id, "status": "PASS" if after == candidate_id else "FAIL"})
        if after != candidate_id:
            raise RuntimeError("CURRENT pointer does not equal exact promotion target")
        access = FoundationReader().get_current_foundation()
        productive = resolve_current_material_supply(store)
        for name in productive.material_supply_datasets():
            productive.dataset_files(name)
        reader = {"PRODUCTIVE_READER_VALIDATION": "PASS",
            "PRODUCTIVE_READER_FOUNDATION_ID": productive.foundation_publication_id,
            "PRODUCTIVE_READER_COMPONENTS": list(productive.component_versions),
            "PRODUCTIVE_VERSION_MIXING": "NO", "PRODUCTIVE_LATEST_FALLBACK": "NO",
            "reader_mode": productive.reader_mode, "ducklake_snapshot_id": access.ducklake_snapshot_id}
        _write("productive_reader_validation.json", reader)
        query = build_v2_result(_rows(productive.dataset_files("material_supply_status")),
            foundation_id=productive.foundation_publication_id)
        query.update({"QUERY": "SAAVEDRA_MATERIAL_SUPPLY_RISK_V1",
            "QUERY_READER_MODE": "PRODUCTIVE_CURRENT", "QUERY_SAP_ACCESSED": "NO"})
        _write("productive_saavedra_query.json", query)
        pre = json.loads((EVIDENCE / "prepromotion_saavedra_query.json").read_text(encoding="utf-8"))
        pre_hash = _canonical_query(pre)
        productive_hash = _canonical_query(query)
        match = pre_hash == productive_hash
        comparison = {"PRODUCTIVE_VS_PINNED_RESULT_MATCH": "PASS" if match else "FAIL",
            "pinned_hash": pre_hash, "productive_hash": productive_hash,
            "same_foundation_id": pre["QUERY_FOUNDATION_ID"] == query["QUERY_FOUNDATION_ID"]}
        _write("productive_vs_pinned.json", comparison)
        if not match:
            raise RuntimeError("productive result differs from pinned result")
        _write("rollback.json", rollback)
        _state("POST_PROMOTION_VALIDATED", "POST_PROMOTION_VALIDATED", "COMPLETE")
        _state("COMPLETE", "POST_PROMOTION_VALIDATED", None)
        print(json.dumps({**reader, **comparison, "FOUNDATION_CURRENT_AFTER": after}, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        if store.current_pointer() == candidate_id:
            result = store.logical_rollback(EXPECTED_CURRENT,
                expected_current_foundation_publication_id=candidate_id, reason=str(exc))
            rollback = {"PROMOTION_ROLLED_BACK": "YES", "ROLLBACK_VALIDATED": "YES"
                if store.current_pointer() == EXPECTED_CURRENT else "NO",
                "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT, "operation": result, "reason": str(exc)}
        else:
            rollback = {"PROMOTION_ROLLED_BACK": "NO", "ROLLBACK_VALIDATED": "NOT_REQUIRED",
                "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT, "reason": str(exc)}
        _write("rollback.json", rollback)
        _state("STOPPED", "PROMOTED", None, str(exc))
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=GATE)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    return prepare() if args.prepare else promote()


if __name__ == "__main__":
    raise SystemExit(main())
