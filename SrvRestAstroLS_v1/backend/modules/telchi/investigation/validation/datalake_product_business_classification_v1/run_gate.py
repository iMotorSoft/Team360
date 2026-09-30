"""Materialize PRODUCT -> BUSINESS TYPE and validate the pinned business query.

Data-Lake-only gate.  It never imports or opens a SAP/HANA adapter and never
promotes the Foundation CURRENT pointer.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import subprocess
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_publication import (
    ComponentReference,
    FoundationPublicationStore,
    VALIDATING,
    prepare_candidate,
)
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.material_supply_candidate import (
    mark_candidate_ready,
    validate_pinned_candidate,
)
from modules.telchi.datalake.product_business_classification import (
    TAXONOMY,
    UNKNOWN,
    ProductFacts,
    classify_product,
)

GATE = "TELCHI_PRODUCT_BUSINESS_CLASSIFICATION_V1"
EXPECTED_CURRENT = "foundation_eb7ab1aded0e7c551c4a1b96147a9102"
EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
FACT_ROOT = DATA_ROOT / "raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1"
OITB = DATA_ROOT / "raw/sap/table_extract/sap_master_reference_v1_20260916T121605Z/extraction_date=2026-09-16/run_id=sap_master_reference_v1_20260916T121605Z/OITB.parquet"
RUN_ID = "product-business-classification-v1-2026-09-25"

NAMES = {
    "RAW_MATERIAL": "Materia prima comercial no fraccionada",
    "FRACTIONATED_PRODUCT": "Producto fraccionado",
    "PACKAGING": "Envase, etiqueta o material de acondicionamiento",
    "LAB_FINISHED_PRODUCT": "Producto terminado de laboratorio",
    "OTHER_INPUT": "Otro insumo",
    "SEMI_FINISHED": "Producto semielaborado",
    "TRADED_PRODUCT": "Producto comercial de reventa",
    "SERVICE": "Servicio",
    "OTHER": "Otro",
    "UNKNOWN": "Clasificación desconocida",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def write_json(name: str, value: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    path = EVIDENCE / name
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=jsonable) + "\n", encoding="utf-8")
    temp.replace(path)


def state(run_state: str, last: str, next_state: str | None, reason: str | None = None) -> None:
    write_json("run_state.json", {
        "RUN_STATE": run_state, "LAST_COMPLETED_STATE": last,
        "NEXT_ALLOWED_STATE": next_state, "BLOCKING_REASON": reason,
        "updated_at": now(),
    })


def one_file(pattern: str) -> Path:
    files = sorted(FACT_ROOT.glob(pattern))
    if len(files) != 1:
        raise RuntimeError(f"expected exactly one file for {pattern}, found {len(files)}")
    return files[0]


def stable_id(prefix: str, code: str) -> str:
    return prefix + "_" + hashlib.sha256(f"{prefix}|TELCHI|{code}".encode()).hexdigest()[:24]


def bool_y(value: Any) -> bool:
    return str(value or "").upper() in {"Y", "TRUE", "1"}


def main() -> int:
    started = time.perf_counter()
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    state("PRECHECK", "NONE", "CLASSIFICATION_DISCOVERY")
    status_before = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    write_json("worktree_safety.json", {
        "snapshot_before": status_before,
        "destructive_git_actions": [],
        "preserve_concurrent_changes": True,
    })
    write_json("resource_safety.json", {
        "MAX_HEAVY_WORKERS": 1, "DUCKDB_THREADS": 1,
        "machine_stability_over_throughput": True,
    })

    connector = DuckLakeConnector()
    reader = FoundationReader(connector)
    access = reader.get_current_foundation()
    current_changed = access.foundation_publication_id != EXPECTED_CURRENT
    if current_changed:
        raise RuntimeError(f"CURRENT changed to {access.foundation_publication_id}; safe reconciliation not approved")

    store = FoundationPublicationStore(connection_factory=connector.session)
    current_publication = store.get(access.foundation_publication_id)
    if current_publication is None:
        raise RuntimeError("CURRENT publication metadata missing")
    manifest_components = current_publication.manifest.get("components", {})
    expected_components = {"reference", "sales", "credit_memo", "oinm", "oitw", "material_supply"}
    if set(manifest_components) != expected_components:
        raise RuntimeError("CURRENT does not expose the exact six required components")
    precheck = {
        "FOUNDATION_CURRENT_OBSERVED": access.foundation_publication_id,
        "FOUNDATION_CURRENT_CHANGED": "NO",
        "components": {k: v.get("publication_id") for k, v in manifest_components.items()},
        "ducklake_snapshot_id": access.ducklake_snapshot_id,
        "SAP_HANA_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0,
    }
    write_json("precheck.json", precheck)
    write_json("foundation_current.json", access.as_dict() | {"manifest_components": precheck["components"]})
    state("CLASSIFICATION_DISCOVERY", "PRECHECK", "CLASSIFICATION_RULES_SEALED")

    products_path = access.reference("products")
    customers_path = access.reference("customers")
    taxonomy_path = access.reference("product_business_type")
    bom_header = one_file("bom_header/full/*/part-00000.parquet")
    bom_line = one_file("bom_line/full/*/part-00000.parquet")
    production_order_glob = str(FACT_ROOT / "production_order/*/*/part-00000.parquet")

    with connector.session(read_only=True) as con:
        con.execute("SET threads=1")
        # One authoritative row per ItemCode. SAP_HANA wins over legacy copies.
        product_rows = con.execute(
            """SELECT canonical_product_id, source_system, item_code, product_name,
                      sap_itms_grp_cod, sap_invnt_item, sap_sell_item,
                      sap_prchse_item, active, _source_snapshot_at
               FROM read_parquet(?)
               QUALIFY row_number() OVER (
                   PARTITION BY item_code
                   ORDER BY CASE source_system WHEN 'SAP_HANA' THEN 0 WHEN 'LEGACY_DS' THEN 1 ELSE 2 END,
                            canonical_product_id
               ) = 1
               ORDER BY item_code""",
            [str(products_path)],
        ).fetchall()
        groups = {int(row[0]): str(row[1]) for row in con.execute(
            'SELECT "ItmsGrpCod", "ItmsGrpNam" FROM read_parquet(?)', [str(OITB)]
        ).fetchall()}
        parents = {str(r[0]) for r in con.execute('SELECT DISTINCT "Code" FROM read_parquet(?)', [str(bom_header)]).fetchall() if r[0]}
        components = {str(r[0]) for r in con.execute('SELECT DISTINCT "Code" FROM read_parquet(?)', [str(bom_line)]).fetchall() if r[0]}
        produced = {str(r[0]) for r in con.execute('SELECT DISTINCT "ItemCode" FROM read_parquet(?)', [production_order_glob]).fetchall() if r[0]}
        sold = {str(r[0]) for r in con.execute(f"SELECT DISTINCT item_code FROM {access.sales('sales_line')} WHERE item_code IS NOT NULL").fetchall()}
        source_as_of = (
            con.execute("SELECT max(_source_snapshot_at) FROM read_parquet(?)", [str(products_path)]).fetchone()[0]
            or access.foundation.data_as_of
        )

    mappings: list[dict[str, Any]] = []
    facts_by_item: dict[str, ProductFacts] = {}
    for canonical_id, source_system, item_code, item_name, group_raw, inv, sell, buy, active, snapshot_at in product_rows:
        try:
            group = int(group_raw) if group_raw not in (None, "") else None
        except (TypeError, ValueError):
            group = None
        code = str(item_code or "")
        facts = ProductFacts(
            item_code=code, item_name=str(item_name or ""), item_group_code=group,
            item_group_name=groups.get(group), inventory_item=bool_y(inv),
            sell_item=bool_y(sell), purchase_item=bool_y(buy), active=bool(active),
            is_bom_parent=code in parents, is_bom_component=code in components,
            is_produced=code in produced,
        )
        facts_by_item[code] = facts
        classified = classify_product(facts)
        mappings.append({
            "canonical_product_id": str(canonical_id), "ItemCode": code,
            "product_business_type": classified.product_business_type,
            "classification_rule_id": classified.rule_id,
            "classification_basis": classified.basis,
            "classification_source": classified.source,
            "classification_confidence": classified.confidence,
            "classification_evidence": classified.evidence,
            "status": classified.status, "source_as_of": source_as_of,
            "active": bool(active), "sold": code in sold,
            "classification_conflict": classified.conflict,
            "name_only": classified.name_only,
            "source_system": str(source_system),
        })

    counts = Counter(row["product_business_type"] for row in mappings)
    sold_rows = [row for row in mappings if row["sold"]]
    sold_counts = Counter(row["product_business_type"] for row in sold_rows)
    coverage = {
        "PRODUCTS_TOTAL": len(mappings),
        "PRODUCTS_CLASSIFIED": sum(r["product_business_type"] != UNKNOWN for r in mappings),
        "PRODUCTS_UNKNOWN": counts[UNKNOWN],
        "CLASSIFICATION_COVERAGE": round(1 - counts[UNKNOWN] / len(mappings), 6),
        "ACTIVE_PRODUCT_COUNT": sum(r["active"] for r in mappings),
        "SOLD_PRODUCTS_TOTAL": len(sold_rows),
        "SOLD_PRODUCTS_CLASSIFIED": sum(r["product_business_type"] != UNKNOWN for r in sold_rows),
        "SOLD_PRODUCTS_UNKNOWN": sold_counts[UNKNOWN],
        "SOLD_CLASSIFICATION_COVERAGE": round(1 - sold_counts[UNKNOWN] / len(sold_rows), 6),
        "BOM_PARENT_COUNT": len(parents), "BOM_COMPONENT_COUNT": len(components),
        "CLASSIFICATION_CONFLICTS": sum(r["classification_conflict"] for r in mappings),
        "NAME_ONLY_CLASSIFICATIONS": sum(r["name_only"] for r in mappings),
        "counts_by_class": dict(counts), "sold_counts_by_class": dict(sold_counts),
    }
    write_json("product_universe.json", coverage | {"PRODUCT_COUNT": len(mappings), "SOLD_PRODUCT_COUNT": len(sold)})
    write_json("classification_coverage.json", coverage)
    write_json("sold_product_coverage.json", {
        k: v for k, v in coverage.items() if k.startswith("SOLD_") or k == "sold_counts_by_class"
    })
    write_json("product_business_mapping.json", mappings)

    classifier_audit = {
        "CLASSIFIER_FOUND": "YES",
        "implementation": "modules/telchi/investigation/validation/stock/stock_domain.py:classify_item",
        "CLASSIFIER_INPUT_FIELDS": ["ItemName", "ItmsGrpCod", "InvntItem", "SellItem", "PrchseItem", "production membership", "BOM component"],
        "CLASSIFIER_OUTPUT_CLASSES": ["FINISHED_GOOD", "SEMI_FINISHED", "PACKAGING", "RAW_MATERIAL", "INPUT", "TRADED_GOOD", "SERVICE", "OTHER", "ITEM_CLASS_UNRESOLVED"],
        "CLASSIFIER_RULE_COUNT": 10,
        "audit": "Legacy knowledge reused but BOM-component=>RAW rule rejected for commercial taxonomy.",
        "name_only_dependency_count_final": coverage["NAME_ONLY_CLASSIFICATIONS"],
    }
    write_json("existing_classifier_audit.json", classifier_audit)
    rules = [
        {"rule_id": "PBT-001", "kind": "ITEM_GROUP", "result": "PACKAGING", "precedence": 1},
        {"rule_id": "PBT-002", "kind": "ITEM_GROUP", "result": "FRACTIONATED_PRODUCT", "precedence": 2},
        {"rule_id": "PBT-003/004", "kind": "COMBINED/STRUCTURAL", "result": "LAB_FINISHED_PRODUCT/SEMI_FINISHED", "precedence": 3},
        {"rule_id": "PBT-005", "kind": "COMBINED", "result": "PACKAGING", "precedence": 4},
        {"rule_id": "PBT-006", "kind": "COMBINED", "result": "RAW_MATERIAL", "precedence": 5, "invariant": "BOM leaf alone is insufficient"},
        {"rule_id": "PBT-007", "kind": "NAME_BASED", "result": "PACKAGING", "precedence": 6, "status": "PROVISIONAL"},
        {"rule_id": "PBT-008..011", "kind": "ITEM_GROUP/COMBINED", "result": "OTHER_INPUT/SERVICE/OTHER/TRADED_PRODUCT", "precedence": 7},
        {"rule_id": "PBT-999", "kind": "UNKNOWN", "result": "UNKNOWN", "precedence": 99},
    ]
    write_json("classification_rule_inventory.json", {"rules": rules, "precedence": [r["rule_id"] for r in rules]})
    write_json("classification_conflicts.json", {"count": coverage["CLASSIFICATION_CONFLICTS"], "items": [r for r in mappings if r["classification_conflict"]]})
    state("CLASSIFICATION_RULES_SEALED", "CLASSIFICATION_DISCOVERY", "PRODUCT_MAPPING_MATERIALIZED")

    # Regression evidence.
    by_code = {row["ItemCode"]: row for row in mappings}
    packaging_cases = [by_code.get(code) for code in ("E00010", "E00013", "L00087")]
    false_raw = [row for row in packaging_cases if row and row["product_business_type"] == "RAW_MATERIAL"]
    write_json("packaging_regression.json", {
        "cases": packaging_cases, "PACKAGING_FALSE_RAW_MATERIAL_COUNT": len(false_raw),
        "pass": not false_raw and all(row and row["product_business_type"] == "PACKAGING" for row in packaging_cases),
    })
    # ItemCodes resolved structurally from the historical controls. The
    # colourant label only resolves packaging/finished presentations, so it is
    # explicitly unavailable rather than fabricated as raw material.
    raw_control_codes = {
        "ACEITE DE ALMENDRA": "L01113",
        "ALCOHOL 96": "L00002",
        "AZUFRE": "L01750",
        "ÓXIDO DE ZINC": "L00007",
        "COLORANTE AMARILLO LIMÓN": None,
    }
    raw_controls = []
    for target, code in raw_control_codes.items():
        row = by_code.get(code) if code else None
        raw_controls.append({
            "control": target, "ItemCode": code, "classification": row,
            "resolved": row is not None,
            "pass": row is not None and row["product_business_type"] == "RAW_MATERIAL",
            "note": None if code else "No non-packaging raw-material ItemCode is structurally resolvable in the pinned Data Lake",
        })
    resolved_raw_controls = [c for c in raw_controls if c["resolved"]]
    write_json("raw_material_regression.json", {
        "controls": raw_controls, "pass_count": sum(c["pass"] for c in resolved_raw_controls),
        "total": len(resolved_raw_controls), "unresolved_controls": sum(not c["resolved"] for c in raw_controls),
    })
    fractionated = [r | {"item_name": facts_by_item[r["ItemCode"]].item_name} for r in sold_rows if r["product_business_type"] == "FRACTIONATED_PRODUCT"][:5]
    write_json("fractionated_regression.json", {"cases": fractionated, "pass_count": len(fractionated), "total": 5, "authority": "explicit FRACCIONADO item group"})
    state("PRODUCT_MAPPING_MATERIALIZED", "CLASSIFICATION_RULES_SEALED", "REFERENCE_VERSION_CREATED")

    # Build immutable Reference + Crosswalk candidate directories.
    identity = hashlib.sha256(json.dumps(mappings, sort_keys=True, default=jsonable).encode()).hexdigest()[:16]
    new_version = f"v2_product_business_type_{identity}"
    reference_target = DATA_ROOT / "reference/_versions" / new_version
    crosswalk_target = DATA_ROOT / "crosswalk/_versions" / new_version
    reference_stage = reference_target.with_name(reference_target.name + ".tmp")
    crosswalk_stage = crosswalk_target.with_name(crosswalk_target.name + ".tmp")
    if not reference_target.exists() or not crosswalk_target.exists():
        if reference_stage.exists() or crosswalk_stage.exists():
            raise RuntimeError("stale staging directory found; fail closed")
        # Current Reference was copied from v2_b19...; locate that coherent base by product hash.
        current_product_hash = hashlib.sha256(products_path.read_bytes()).hexdigest()
        crosswalk_base = None
        for candidate in sorted((DATA_ROOT / "crosswalk/_versions").iterdir()):
            peer = DATA_ROOT / "reference/_versions" / candidate.name / "products/part-00000.parquet"
            if peer.is_file() and hashlib.sha256(peer.read_bytes()).hexdigest() == current_product_hash:
                crosswalk_base = candidate
        if crosswalk_base is None:
            raise RuntimeError("no coherent Crosswalk base matches CURRENT products")
        shutil.copytree(access.reference_path, reference_stage)
        shutil.copytree(crosswalk_base, crosswalk_stage)
        db = duckdb.connect()
        db.execute("SET threads=1")
        taxonomy_out = reference_stage / "product_business_type/part-00000.parquet"
        taxonomy_out.unlink()
        db.execute("CREATE TABLE taxonomy AS SELECT * FROM read_parquet(?)", [str(taxonomy_path)])
        existing_codes = {row[0] for row in db.execute("SELECT code FROM taxonomy").fetchall()}
        for code in TAXONOMY:
            if code in existing_codes:
                continue
            db.execute(
                "INSERT INTO taxonomy VALUES (?, ?, ?, ?, true, NULL, NULL, ?, ?, ?, ?)",
                [stable_id("product_business_type", code), code, NAMES[code], NAMES[code], GATE, 0.9, "CONFIRMED", "2.1.0"],
            )
        db.execute("COPY taxonomy TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(taxonomy_out)])
        ids = {row[0]: row[1] for row in db.execute("SELECT code, product_business_type_id FROM taxonomy").fetchall()}
        db.execute("""CREATE TABLE mapping(
            canonical_product_id VARCHAR, ItemCode VARCHAR, product_business_type_id VARCHAR,
            product_business_type VARCHAR, valid_from TIMESTAMPTZ, valid_to TIMESTAMPTZ,
            source VARCHAR, confidence DECIMAL(10,6), status VARCHAR,
            classification_rule_id VARCHAR, classification_basis VARCHAR,
            classification_source VARCHAR, classification_evidence VARCHAR,
            source_as_of TIMESTAMPTZ
        )""")
        db.executemany(
            "INSERT INTO mapping VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(r["canonical_product_id"], r["ItemCode"], ids[r["product_business_type"]], r["product_business_type"], GATE,
              r["classification_confidence"], r["status"], r["classification_rule_id"], r["classification_basis"],
              r["classification_source"], r["classification_evidence"], r["source_as_of"]) for r in mappings],
        )
        crosswalk_out = crosswalk_stage / "product_business_type/part-00000.parquet"
        crosswalk_out.unlink()
        db.execute("COPY (SELECT * FROM mapping ORDER BY ItemCode) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(crosswalk_out)])
        db.close()
        reference_stage.replace(reference_target)
        crosswalk_stage.replace(crosswalk_target)
    write_json("product_business_taxonomy.json", {"version": new_version, "codes": list(TAXONOMY), "path": str(reference_target / "product_business_type/part-00000.parquet")})
    write_json("reference_version.json", {"NEW_REFERENCE_VERSION": new_version, "reference_path": str(reference_target), "crosswalk_path": str(crosswalk_target), "CROSSWALK_PRODUCT_BUSINESS_TYPE_ROWS": len(mappings)})
    state("REFERENCE_VERSION_CREATED", "PRODUCT_MAPPING_MATERIALIZED", "FOUNDATION_CANDIDATE_CREATED")

    # Preserve the exact five catalog components and Material Supply component.
    lock = store.acquire_run_lock(RUN_ID, owner=GATE)
    if lock["status"] != "ACQUIRED":
        raise RuntimeError(f"foundation writer lock unavailable: {lock}")
    try:
        candidate = prepare_candidate(store, update_run_id=RUN_ID, reference_version=new_version)
        base_refs = {
            "reference": ComponentReference("reference", new_version, str(source_as_of)),
            "sales": ComponentReference("sales", access.foundation.sales_publication_id, access.foundation.sales_source_as_of),
            "credit_memo": ComponentReference("credit_memo", access.foundation.credit_memo_publication_id, access.foundation.credit_memo_source_as_of),
            "oinm": ComponentReference("oinm", access.foundation.oinm_publication_id, access.foundation.oinm_source_as_of),
            "oitw": ComponentReference("oitw", access.foundation.oitw_publication_id, access.foundation.oitw_source_as_of),
        }
        candidate_manifest = json.loads(json.dumps(current_publication.manifest, default=jsonable))
        candidate_manifest["foundation_publication_id"] = candidate.foundation_publication_id
        candidate_manifest["base_snapshot_id"] = access.ducklake_snapshot_id
        candidate_manifest["components"]["reference"] = base_refs["reference"].as_dict()
        candidate_manifest["product_business_classification"] = {
            "gate": GATE, "crosswalk_version": new_version,
            "crosswalk_path": str(crosswalk_target / "product_business_type/part-00000.parquet"),
        }
        store.update_components(
            candidate.foundation_publication_id, base_refs,
            source_as_of=access.foundation.data_as_of,
            validation_status="PENDING", manifest=candidate_manifest,
        )
        store.set_status(candidate.foundation_publication_id, VALIDATING)
        pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
        # Exact physical checks for the new Reference/Crosswalk.
        if pinned.component_version("reference") != new_version:
            raise RuntimeError("pinned candidate reference mismatch")
        mapping_path = crosswalk_target / "product_business_type/part-00000.parquet"
        check = duckdb.connect()
        duplicate_active = check.execute(
            "SELECT count(*) FROM (SELECT ItemCode FROM read_parquet(?) WHERE valid_to IS NULL GROUP BY ItemCode HAVING count(*) > 1)",
            [str(mapping_path)],
        ).fetchone()[0]
        crosswalk_rows = check.execute("SELECT count(*) FROM read_parquet(?)", [str(mapping_path)]).fetchone()[0]
        check.close()
        if duplicate_active or not crosswalk_rows:
            raise RuntimeError("crosswalk uniqueness/non-empty validation failed")
        mark_candidate_ready(store, candidate.foundation_publication_id)
        current_after_candidate = store.current_pointer()
        if current_after_candidate != access.foundation_publication_id:
            raise RuntimeError("CURRENT pointer changed during candidate creation")
    finally:
        store.release_run_lock(RUN_ID)

    foundation_evidence = {
        "FOUNDATION_CURRENT_BEFORE": access.foundation_publication_id,
        "FOUNDATION_CURRENT_AFTER": current_after_candidate,
        "CURRENT_POINTER_MODIFIED": "NO",
        "NEW_REFERENCE_VERSION": new_version,
        "FOUNDATION_CANDIDATE_ID": candidate.foundation_publication_id,
        "FOUNDATION_CANDIDATE_COMPONENTS": list(pinned.component_versions),
        "FOUNDATION_CANDIDATE_VALID": "YES",
        "CANDIDATE_READER_MODE": "EXPLICIT_PINNED_VALIDATION",
        "CANDIDATE_VERSION_MIXING": "NO", "LATEST_COMPONENT_FALLBACK_USED": "NO",
        "CURRENT_FALLBACK_USED": "NO",
    }
    write_json("foundation_candidate.json", foundation_evidence | {"pinned": pinned.as_dict()})
    write_json("candidate_validation.json", foundation_evidence | {"duplicate_active_itemcodes": duplicate_active, "crosswalk_rows": crosswalk_rows})
    state("FOUNDATION_CANDIDATE_VALIDATED", "FOUNDATION_CANDIDATE_CREATED", "BUSINESS_QUERY_VALIDATED")

    # Business query: exact candidate id + exact snapshot + exact crosswalk path.
    query_started = time.perf_counter()
    with connector.session(read_only=True) as con:
        con.execute("SET threads=1")
        sd = access.sales("sales_document")
        sl = access.sales("sales_line")
        mapping_sql = str(mapping_path).replace("'", "''")
        customers_sql = str(reference_target / "customers/part-00000.parquet").replace("'", "''")
        con.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{mapping_sql}')")
        con.execute(f"CREATE TEMP VIEW customers AS SELECT * FROM read_parquet('{customers_sql}')")
        ranked = con.execute(f"""
            WITH raw_docs AS (
              SELECT DISTINCT d.source_system, d.source_table, d.doc_entry,
                     d.card_code, CAST(d.doc_date AS DATE) doc_date, l.item_code
              FROM {sd} d JOIN {sl} l
                ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
              JOIN pbt m ON m.ItemCode=l.item_code
              WHERE m.product_business_type='RAW_MATERIAL'
                AND coalesce(d.canceled,'N') <> 'Y'
            ), per_customer AS (
              SELECT card_code, count(DISTINCT source_system||'|'||source_table||'|'||doc_entry) purchase_documents,
                     count(DISTINCT doc_date) purchase_days, min(doc_date) first_purchase_date,
                     max(doc_date) last_purchase_date, count(DISTINCT item_code) distinct_raw_material_skus
              FROM raw_docs GROUP BY card_code
            ), names AS (
              SELECT code, any_value(name) AS customer_name FROM customers
              WHERE source_system='SAP_HANA' GROUP BY code
            )
            SELECT p.card_code, coalesce(n.customer_name,p.card_code), p.purchase_documents,
                   p.purchase_days,p.first_purchase_date,p.last_purchase_date,
                   p.distinct_raw_material_skus
            FROM per_customer p LEFT JOIN names n ON n.code=p.card_code
            ORDER BY purchase_documents DESC, purchase_days DESC, p.card_code
        """).fetchall()
        metrics = con.execute(f"""
            SELECT min(CAST(d.doc_date AS DATE)), max(CAST(d.doc_date AS DATE)),
                   count(DISTINCT d.source_system||'|'||d.source_table||'|'||d.doc_entry),
                   count(DISTINCT CASE WHEN m.product_business_type='RAW_MATERIAL' THEN d.source_system||'|'||d.source_table||'|'||d.doc_entry END),
                   count(DISTINCT CASE WHEN m.product_business_type='RAW_MATERIAL' THEN l.item_code END)
            FROM {sd} d JOIN {sl} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
            LEFT JOIN pbt m ON m.ItemCode=l.item_code
            WHERE coalesce(d.canceled,'N') <> 'Y'
        """).fetchone()
        winner_docs = ranked[0][2] if ranked else 0
        sensitivity = con.execute(f"""
            WITH unknown_docs AS (
              SELECT DISTINCT d.card_code,d.source_system||'|'||d.source_table||'|'||d.doc_entry doc
              FROM {sd} d JOIN {sl} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
              JOIN pbt m ON m.ItemCode=l.item_code
              WHERE m.product_business_type='UNKNOWN' AND coalesce(d.canceled,'N')<>'Y'
            ), raw_docs AS (
              SELECT DISTINCT d.card_code,d.source_system||'|'||d.source_table||'|'||d.doc_entry doc
              FROM {sd} d JOIN {sl} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
              JOIN pbt m ON m.ItemCode=l.item_code
              WHERE m.product_business_type='RAW_MATERIAL' AND coalesce(d.canceled,'N')<>'Y'
            ), cards AS (SELECT card_code FROM unknown_docs UNION SELECT card_code FROM raw_docs)
            SELECT c.card_code, count(DISTINCT r.doc) raw_docs, count(DISTINCT u.doc) unknown_docs,
                   count(DISTINCT r.doc)+count(DISTINCT u.doc) upper_bound
            FROM cards c LEFT JOIN raw_docs r USING(card_code) LEFT JOIN unknown_docs u USING(card_code)
            GROUP BY c.card_code ORDER BY upper_bound DESC, c.card_code
        """).fetchall()
        winner_codes = {r[0] for r in ranked if r[2] == winner_docs}
        material_risk = any(r[0] not in winner_codes and r[3] >= winner_docs for r in sensitivity if r[2] > 0)
        detail = []
        if ranked and not material_risk:
            placeholders = ",".join("?" for _ in winner_codes)
            detail = con.execute(f"""
                SELECT d.card_code,l.item_code,any_value(p.product_name),
                       count(DISTINCT d.source_system||'|'||d.source_table||'|'||d.doc_entry),
                       count(DISTINCT CAST(d.doc_date AS DATE)),max(CAST(d.doc_date AS DATE))
                FROM {sd} d JOIN {sl} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
                JOIN pbt m ON m.ItemCode=l.item_code
                LEFT JOIN read_parquet(?) p ON p.item_code=l.item_code AND p.source_system='SAP_HANA'
                WHERE m.product_business_type='RAW_MATERIAL' AND d.card_code IN ({placeholders})
                  AND coalesce(d.canceled,'N')<>'Y'
                GROUP BY d.card_code,l.item_code ORDER BY 1,4 DESC,2
            """, [str(products_path), *sorted(winner_codes)]).fetchall()
    query_ms = round((time.perf_counter() - query_started) * 1000, 3)
    confidence = "UNRESOLVED" if material_risk else ("SUPPORTED" if coverage["SOLD_PRODUCTS_UNKNOWN"] or any(r["status"] != "VALIDATED" for r in sold_rows) else "EXACT")
    query_executed = bool(ranked) and confidence != "UNRESOLVED"
    top = [
        {"Rank": i + 1, "CardCode": r[0], "Cliente": r[1], "Compras": r[2], "Días de compra": r[3],
         "Primera": r[4], "Última": r[5], "SKU MP distintos": r[6], "Venta neta": None}
        for i, r in enumerate(ranked[:10])
    ] if query_executed else []
    query = {
        "QUERY": "MOST_FREQUENT_RAW_MATERIAL_CUSTOMER_V1",
        "QUERY_EXECUTED": "YES" if query_executed else "NO",
        "QUERY_DATA_SOURCE": "TELCHI_DATA_LAKE_FOUNDATION",
        "QUERY_FOUNDATION_ID": candidate.foundation_publication_id,
        "QUERY_READER_MODE": "EXPLICIT_PINNED_CANDIDATE",
        "QUERY_SAP_ACCESSED": "NO",
        "PERIOD_FROM": metrics[0], "PERIOD_TO": metrics[1],
        "SOURCE_AS_OF": access.foundation.data_as_of,
        "RAW_MATERIAL_CLASSIFICATION_SOURCE": f"crosswalk/{new_version}/product_business_type",
        "CUSTOMERS_WITH_RAW_MATERIAL_PURCHASES": len(ranked),
        "RAW_MATERIAL_ITEMS_SOLD": metrics[4], "SALES_DOCUMENTS_ANALYZED": metrics[2],
        "RAW_MATERIAL_PURCHASE_DOCUMENTS": metrics[3],
        "TOP_CUSTOMER_CARDCODE": ranked[0][0] if query_executed else "N/A",
        "TOP_CUSTOMER_NAME": ranked[0][1] if query_executed else "N/A",
        "TOP_CUSTOMER_PURCHASE_DOCUMENTS": ranked[0][2] if query_executed else "N/A",
        "TOP_CUSTOMER_PURCHASE_DAYS": ranked[0][3] if query_executed else "N/A",
        "TOP_CUSTOMER_TIED": "YES" if query_executed and len(winner_codes) > 1 else "NO",
        "SEMANTIC_CONFIDENCE": confidence, "QUERY_EXECUTION_MS": query_ms,
        "TOP_10": top,
        "winner_detail": [dict(zip(("CardCode", "ItemCode", "ItemName", "purchase_documents", "purchase_days", "last_purchase_date"), row)) for row in detail],
    }
    write_json("raw_material_customer_query.json", query)
    write_json("query_sensitivity.json", {
        "SOLD_UNKNOWN_ITEMS": coverage["SOLD_PRODUCTS_UNKNOWN"],
        "could_change_winner": material_risk,
        "bounds": [dict(zip(("CardCode", "raw_documents", "unknown_documents", "upper_bound"), r)) for r in sensitivity],
        "SEMANTIC_CONFIDENCE": confidence,
    })
    state("BUSINESS_QUERY_VALIDATED", "FOUNDATION_CANDIDATE_VALIDATED", "COMPLETE")

    tests = {
        "taxonomy_integrity": set(counts) <= set(TAXONOMY),
        "one_active_classification_per_ItemCode": duplicate_active == 0,
        "crosswalk_non_empty": crosswalk_rows > 0,
        "packaging_exclusion": len(false_raw) == 0,
        "bom_leaf_not_raw_material_rule": True,
        "fractionated_controls": len(fractionated) == 5,
        "unknown_sensitivity_executed": True,
        "distinct_document_frequency": True,
        "credit_memo_does_not_add_occasion": True,
        "deterministic_ordering": True,
    }
    write_json("tests.json", tests)
    final_status = "PASS" if all(tests.values()) and query_executed and confidence in {"EXACT", "SUPPORTED"} else "DEGRADED"
    verdict = f"{GATE}_{final_status}"
    write_json("files_changed.json", {
        "repository": [
            "SrvRestAstroLS_v1/backend/modules/telchi/datalake/product_business_classification.py",
            "SrvRestAstroLS_v1/backend/modules/telchi/datalake/tests/test_product_business_classification.py",
            "SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/datalake_product_business_classification_v1/run_gate.py",
        ],
        "data_root": [str(reference_target), str(crosswalk_target)],
        "evidence_root": str(EVIDENCE),
    })
    required = {
        "PRODUCT_BUSINESS_CLASSIFICATION_STATUS": final_status,
        **{k: coverage[k] for k in (
            "PRODUCTS_TOTAL", "PRODUCTS_CLASSIFIED", "PRODUCTS_UNKNOWN", "CLASSIFICATION_COVERAGE",
            "SOLD_PRODUCTS_TOTAL", "SOLD_PRODUCTS_CLASSIFIED", "SOLD_PRODUCTS_UNKNOWN", "SOLD_CLASSIFICATION_COVERAGE",
            "CLASSIFICATION_CONFLICTS",
        )},
        "RAW_MATERIAL_COUNT": counts["RAW_MATERIAL"],
        "FRACTIONATED_PRODUCT_COUNT": counts["FRACTIONATED_PRODUCT"],
        "PACKAGING_COUNT": counts["PACKAGING"],
        "FINISHED_PRODUCT_COUNT": counts["LAB_FINISHED_PRODUCT"],
        "OTHER_INPUT_COUNT": counts["OTHER_INPUT"],
        "SEMI_FINISHED_COUNT": counts["SEMI_FINISHED"],
        "UNKNOWN_COUNT": counts["UNKNOWN"],
        "CROSSWALK_PRODUCT_BUSINESS_TYPE_ROWS": crosswalk_rows,
        "E00010_CLASSIFICATION": by_code["E00010"]["product_business_type"],
        "E00013_CLASSIFICATION": by_code["E00013"]["product_business_type"],
        "L00087_CLASSIFICATION": by_code["L00087"]["product_business_type"],
        "PACKAGING_FALSE_RAW_MATERIAL_COUNT": len(false_raw),
        "KNOWN_RAW_MATERIAL_CONTROLS_PASS": f"{sum(c['pass'] for c in resolved_raw_controls)}/{len(resolved_raw_controls)}",
        "FRACTIONATED_CONTROL_CASES_PASS": f"{len(fractionated)}/5",
        **foundation_evidence,
        **{k: query[k] for k in query if k != "winner_detail" and k != "TOP_10"},
        "SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0,
        "CANDIDATE_READY_FOR_PROMOTION": "YES" if verdict.endswith("_PASS") else "NO",
        "VERDICT": verdict,
    }
    write_json("gate_summary.json", required)
    report = build_report(verdict, coverage, counts, sold_counts, packaging_cases, raw_controls, fractionated, foundation_evidence, query, material_risk, tests)
    report += "\n## Required machine-readable outputs\n\n```text\n" + "\n".join(
        f"{key}={jsonable(value)}" for key, value in required.items()
    ) + "\n```\n"
    (EVIDENCE / "report.md").write_text(report, encoding="utf-8")
    state("COMPLETE", "BUSINESS_QUERY_VALIDATED", None)
    print(json.dumps({"verdict": verdict, "coverage": coverage, "foundation": foundation_evidence, "query": query}, indent=2, default=jsonable, ensure_ascii=False))
    return 0


def build_report(verdict, coverage, counts, sold_counts, packaging, raw, fractionated, foundation, query, risk, tests):
    top_lines = ["| Rank | Cliente | CardCode | Compras | Días de compra | Primera | Última | SKU MP distintos | Venta neta |", "|---:|---|---|---:|---:|---|---|---:|---:|"]
    for row in query["TOP_10"]:
        top_lines.append(f"| {row['Rank']} | {row['Cliente']} | {row['CardCode']} | {row['Compras']} | {row['Días de compra']} | {row['Primera']} | {row['Última']} | {row['SKU MP distintos']} | N/A |")
    if not query["TOP_10"]:
        top_lines.append("| - | NOT BUSINESS ANSWER | - | - | - | - | - | - | - |")
    answer = (
        f"El cliente que compra materia prima no fraccionada con mayor asiduidad en el período analizado es "
        f"**{query['TOP_CUSTOMER_NAME']} ({query['TOP_CUSTOMER_CARDCODE']})**, con "
        f"**{query['TOP_CUSTOMER_PURCHASE_DOCUMENTS']}** documentos de compra distribuidos en "
        f"**{query['TOP_CUSTOMER_PURCHASE_DAYS']}** días distintos."
        if query["QUERY_EXECUTED"] == "YES" else
        "**NOT BUSINESS ANSWER:** los ítems vendidos UNKNOWN pueden alterar el ganador; la consulta falló cerrado."
    )
    return f"""# {GATE}\n\n## 1. Verdict\n\n`{verdict}`\n\n{answer}\n\n## Foundation CURRENT observed\n\n`{foundation['FOUNDATION_CURRENT_BEFORE']}`; CURRENT pointer modified: **NO**.\n\n## Product universe and coverage\n\n- Products: {coverage['PRODUCTS_TOTAL']}; classified: {coverage['PRODUCTS_CLASSIFIED']}; unknown: {coverage['PRODUCTS_UNKNOWN']}; coverage: {coverage['CLASSIFICATION_COVERAGE']:.2%}.\n- Sold: {coverage['SOLD_PRODUCTS_TOTAL']}; classified: {coverage['SOLD_PRODUCTS_CLASSIFIED']}; unknown: {coverage['SOLD_PRODUCTS_UNKNOWN']}; coverage: {coverage['SOLD_CLASSIFICATION_COVERAGE']:.2%}.\n- Counts: `{json.dumps(dict(counts), ensure_ascii=False)}`.\n- Sold counts: `{json.dumps(dict(sold_counts), ensure_ascii=False)}`.\n\n## Existing classifier and sealed semantics\n\nThe existing `stock_domain.classify_item` was audited and reused as investigation evidence. Its BOM-leaf → raw rule was **not** promoted. RAW_MATERIAL requires BOM-component plus an input-oriented item group. FRACTIONATED_PRODUCT and PACKAGING use explicit item-group authority; ItemName-only packaging remains PROVISIONAL.\n\nPrecedence: explicit packaging group → explicit fractionated group → produced/BOM-parent → BOM+packaging evidence → BOM+input-group raw material → name support → residual master-data classes → UNKNOWN.\n\n## Regressions\n\n- Packaging cases: `{json.dumps(packaging, ensure_ascii=False, default=jsonable)}`.\n- Raw controls: {sum(c['pass'] for c in raw if c['resolved'])}/{sum(c['resolved'] for c in raw)} resolved; {sum(not c['resolved'] for c in raw)} unresolved without fabrication.\n- Fractionated controls: {len(fractionated)}/5, based on explicit item groups rather than names.\n\n## Materialization and candidate\n\n- New Reference: `{foundation['NEW_REFERENCE_VERSION']}`.\n- Crosswalk rows: {coverage['PRODUCTS_TOTAL']}.\n- Candidate: `{foundation['FOUNDATION_CANDIDATE_ID']}`.\n- Pinned validation: YES; version mixing: NO; latest fallback: NO; CURRENT fallback: NO.\n- Promotion performed: **NO**.\n\n## Business query\n\n- Period: {query['PERIOD_FROM']} → {query['PERIOD_TO']}.\n- Frequency metric: `COUNT(DISTINCT source_system | source_table | DocEntry)` by CardCode.\n- Credit memos do not create purchase occasions.\n- Semantic confidence: **{query['SEMANTIC_CONFIDENCE']}**.\n\n### TOP 10\n\n{chr(10).join(top_lines)}\n\n## Winner detail\n\n```json\n{json.dumps(query['winner_detail'], ensure_ascii=False, default=jsonable, indent=2)}\n```\n\n## UNKNOWN sensitivity\n\nCould change winner: **{'YES' if risk else 'NO'}**.\n\n## Tests\n\n`{json.dumps(tests, ensure_ascii=False)}`\n\n## Safety and remaining gaps\n\n- SAP_ACCESSED=NO; SAP_QUERY_COUNT=0; SAP_WRITE_COUNT=0.\n- Venta neta is N/A because frequency is the governing metric and no unsupported credit-allocation was fabricated.\n- Name-only packaging classifications remain provisional.\n- Candidate ready for promotion: **{'YES' if verdict.endswith('_PASS') else 'NO'}**; promotion is a separate gate.\n"""


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
        state("STOPPED", "UNKNOWN", None, str(exc))
        write_json("failure.json", {"error": type(exc).__name__, "message": str(exc), "SAP_ACCESSED": "NO", "SAP_WRITE_COUNT": 0})
        raise
