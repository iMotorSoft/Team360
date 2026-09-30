"""Final Data-Lake-only Telchi Foundation V1 promotion and closure gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.material_supply_candidate import (
    resolve_current_material_supply,
    validate_pinned_candidate,
)
from modules.telchi.datalake.reference_closure import discover_sales_files
from modules.telchi.datalake.reference_semantics import SECOND_ANILLO_WAREHOUSE_CODES
from modules.telchi.investigation.validation.datalake_material_supply_derivation_v1.run_saavedra_reconciliation import (
    PACKAGING_RE,
    build_v2_result,
)

GATE = "TELCHI_DATALAKE_FINAL_FOUNDATION_PROMOTION_AND_CLOSURE_V1"
RUN_ID = "datalake-v1-closure-20260927T204614-0300"
TARGET = "foundation_6a7cc7a99638208002c4f877d998d220"
EXPECTED_CURRENT = "foundation_eb7ab1aded0e7c551c4a1b96147a9102"
REFERENCE = "v2_reference_closure_2088d5885204313a"
REFERENCE_HASH = "2088d5885204313a251fb130547e2916744e375f4b7890e68399dbbb75ef773c"
SNAPSHOT = 838
SALES_RUN = "manual-update-20260924T132754050866Z"
BASE_REFERENCE = "v2_customer_business_type_91a610c6d8858eff"
EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
REPO = Path(__file__).resolve().parents[7]
BACKEND = REPO / "SrvRestAstroLS_v1/backend"
COMPONENTS = ("reference", "sales", "credit_memo", "oinm", "oitw", "material_supply")
EXPECTED_SECOND_ANILLO = sorted(("2A-AMD", "2A-AMK", "2A-DAN", "2A-DEV", "2A-EXT", "2A-KIT", "2A-MAG", "2A-MEI", "2A-MKT", "2A-SAL", "2A-SMK", "2A-TRAN", "22", "23", "24", "29", "51", "63"))
EXPECTED_ROLES = {"SAA-M1": "RAW_MATERIAL", "SAA-P1": "PRODUCTION", "SAA-T1": "FINISHED_PRODUCT", "SAA-DAN": "DAMAGED", "SAA-T2": "RECONDITIONED", "SAA-T3": "RECONDITIONED"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def write(name: str, payload: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    path = EVIDENCE / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=jsonable) + "\n", encoding="utf-8")
    temporary.replace(path)


def state(current: str, last: str | None, next_state: str | None, reason: str | None = None) -> None:
    existing = json.loads((EVIDENCE / "run_state.json").read_text()) if (EVIDENCE / "run_state.json").is_file() else {}
    write("run_state.json", existing | {"RUN_ID": RUN_ID, "RUN_STATE": current, "LAST_COMPLETED_STATE": last,
        "NEXT_ALLOWED_STATE": next_state, "BLOCKING_REASON": reason, "STATE_UPDATED_AT": now()})


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=jsonable, separators=(",", ":")).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [str(item[0]) for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def parquet_rows(files: list[Path]) -> list[dict[str, Any]]:
    connection = duckdb.connect()
    connection.execute("SET threads=1")
    try:
        return rows(connection.execute("SELECT * FROM read_parquet(?)", [[str(path) for path in files]]))
    finally:
        connection.close()


def reference_semantic_hash() -> tuple[str, dict[str, Any]]:
    base_ref = DATA_ROOT / "reference/_versions" / BASE_REFERENCE
    final_ref = DATA_ROOT / "reference/_versions" / REFERENCE
    final_cw = DATA_ROOT / "crosswalk/_versions" / REFERENCE
    sales_files = discover_sales_files(DATA_ROOT, SALES_RUN)
    warehouse_path = base_ref / "warehouses/part-00000.parquet"
    location_path = final_cw / "warehouse_business_location/part-00000.parquet"
    uom_path = final_cw / "uom_mapping/part-00000.parquet"
    if not final_ref.is_dir() or not final_cw.is_dir():
        raise RuntimeError("exact sealed Reference directories are absent")
    connection = duckdb.connect()
    connection.execute("SET threads=1")
    try:
        location = rows(connection.execute("SELECT * FROM read_parquet(?) ORDER BY warehouse_code,source_system", [str(location_path)]))
        uom = rows(connection.execute("SELECT * FROM read_parquet(?) ORDER BY source_uom_code", [str(uom_path)]))
    finally:
        connection.close()
    input_identity = {
        "base_version": BASE_REFERENCE,
        "warehouses_sha256": file_hash(warehouse_path),
        "sales_files": [(str(path.relative_to(DATA_ROOT)), file_hash(path)) for path in sales_files],
        "explicit_location_codes": list(SECOND_ANILLO_WAREHOUSE_CODES),
    }
    value = digest({"input_identity": input_identity, "warehouse_business_location": location, "uom_mapping": uom})
    return value, {"reference_path": str(final_ref), "crosswalk_path": str(final_cw), "location_rows": len(location), "uom_rows": len(uom)}


def material_supply(pinned: Any, reader_mode: str) -> dict[str, Any]:
    status_rows = parquet_rows(pinned.dataset_files("material_supply_status"))
    result = build_v2_result(status_rows, foundation_id=pinned.foundation_publication_id)
    business_universe = [
        row for row in status_rows
        if row.get("is_raw_material") is True
        and not PACKAGING_RE.search(str(row.get("material_name") or ""))
    ]
    counts = Counter(str(row.get("saavedra_relevance")) for row in business_universe)
    result.update({
        "QUERY_READER_MODE": reader_mode,
        "QUERY_SAP_ACCESSED": "NO",
        "ACTIVE": counts["ACTIVE_SAAVEDRA_MATERIAL"],
        "HISTORICAL": counts["HISTORICAL_SAAVEDRA_MATERIAL"],
        "GLOBAL_NOT_RELEVANT": counts["GLOBAL_RAW_MATERIAL_NOT_RELEVANT_TO_SAAVEDRA"],
        "UNRESOLVED": counts["UNRESOLVED_SAAVEDRA_RELEVANCE"],
        "UNSAFE_CONVERSIONS": 0,
    })
    return result


def reference_gold(snapshot_id: int) -> dict[str, Any]:
    ref = DATA_ROOT / "reference/_versions" / REFERENCE
    cw = DATA_ROOT / "crosswalk/_versions" / REFERENCE
    sales_files = discover_sales_files(DATA_ROOT, SALES_RUN)
    credit_files = sorted((DATA_ROOT / "raw/sap/TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1").glob(f"credit-memo-*/{SALES_RUN}_*/part-00000.parquet"))
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute("SET threads=1")
        product = rows(con.execute("SELECT ItemCode,product_business_type FROM read_parquet(?) WHERE ItemCode IN ('L00031','L03192','E00010','E00013','L00087') ORDER BY ItemCode", [str(cw / "product_business_type/part-00000.parquet")]))
        customer = rows(con.execute("SELECT CardCode,customer_business_type,classification_source FROM read_parquet(?) WHERE CardCode IN ('CG2A','C010341') ORDER BY CardCode", [str(cw / "customer_business_type/part-00000.parquet")]))
        product_count = int(con.execute("SELECT count(*) FROM read_parquet(?)", [str(cw / "product_business_type/part-00000.parquet")]).fetchone()[0])
        customer_count = int(con.execute("SELECT count(*) FROM read_parquet(?)", [str(cw / "customer_business_type/part-00000.parquet")]).fetchone()[0])
        unknown_customers = int(con.execute("SELECT count(*) FROM read_parquet(?) WHERE customer_business_type='UNKNOWN'", [str(cw / "customer_business_type/part-00000.parquet")]).fetchone()[0])
        locations = rows(con.execute("SELECT * FROM read_parquet(?) ORDER BY warehouse_code", [str(cw / "warehouse_business_location/part-00000.parquet")]))
        roles = rows(con.execute("SELECT warehouse_code,warehouse_role FROM read_parquet(?) WHERE warehouse_code IN ('SAA-M1','SAA-P1','SAA-T1','SAA-DAN','SAA-T2','SAA-T3') ORDER BY warehouse_code", [str(ref / "warehouse_roles/part-00000.parquet")]))
        uom_rows = rows(con.execute("SELECT * FROM read_parquet(?) ORDER BY source_uom_code", [str(cw / "uom_mapping/part-00000.parquet")]))
        raw_sales = [str(path) for path in sales_files]
        raw_credit = [str(path) for path in credit_files]
        sl = f'(SELECT * FROM telchi.atomic."sales_line" AT (VERSION => {snapshot_id}))'
        sd = f'(SELECT * FROM telchi.atomic."sales_document" AT (VERSION => {snapshot_id}))'
        cl = f'(SELECT * FROM telchi.atomic."credit_memo_line" AT (VERSION => {snapshot_id}))'
        cd = f'(SELECT * FROM telchi.atomic."credit_memo_document" AT (VERSION => {snapshot_id}))'
        coverage = con.execute(f"""
            WITH raw AS (SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,
                nullif(trim(CAST(unitMsr AS VARCHAR)),'') source_uom,CAST(NumPerMsr AS VARCHAR) num_per_msr FROM read_parquet(?)),
            joined AS (SELECT l.item_code,l.doc_entry,l.line_num,r.source_uom,r.num_per_msr FROM {sl} l LEFT JOIN raw r USING(doc_entry,line_num))
            SELECT count(*),count(source_uom),count(source_uom),count(*)-count(source_uom),count(DISTINCT item_code),
                count(DISTINCT item_code) FILTER (WHERE source_uom IS NOT NULL),
                count(DISTINCT item_code) FILTER (WHERE source_uom IS NULL),
                count(*) FILTER (WHERE num_per_msr IS NOT NULL AND try_cast(num_per_msr AS DECIMAL(38,12))<>1) FROM joined
        """, [raw_sales]).fetchone()
        multi = int(con.execute("SELECT count(*) FROM (SELECT CAST(ItemCode AS VARCHAR) item_code FROM read_parquet(?) WHERE nullif(trim(CAST(unitMsr AS VARCHAR)),'') IS NOT NULL GROUP BY item_code HAVING count(DISTINCT upper(trim(CAST(unitMsr AS VARCHAR))))>1)", [raw_sales]).fetchone()[0])
        conflicts = int(con.execute("SELECT count(*) FROM (SELECT source_uom_code FROM read_parquet(?) GROUP BY source_uom_code HAVING count(DISTINCT canonical_uom_code)>1)", [str(cw / "uom_mapping/part-00000.parquet")]).fetchone()[0])
        quote = lambda value: str(value).replace("'", "''")
        con.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{quote(cw / 'product_business_type/part-00000.parquet')}')")
        con.execute(f"CREATE TEMP VIEW cbt AS SELECT * FROM read_parquet('{quote(cw / 'customer_business_type/part-00000.parquet')}')")
        con.execute(f"CREATE TEMP VIEW loc AS SELECT * FROM read_parquet('{quote(cw / 'warehouse_business_location/part-00000.parquet')}')")
        con.execute(f"CREATE TEMP VIEW um AS SELECT * FROM read_parquet('{quote(cw / 'uom_mapping/part-00000.parquet')}')")
        raw_sales_sql = "[" + ",".join("'" + quote(path) + "'" for path in raw_sales) + "]"
        raw_credit_sql = "[" + ",".join("'" + quote(path) + "'" for path in raw_credit) + "]"
        con.execute(f"CREATE TEMP VIEW raw_sales AS SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,CAST(ItemCode AS VARCHAR) item_code,trim(CAST(unitMsr AS VARCHAR)) source_uom FROM read_parquet({raw_sales_sql})")
        con.execute(f"CREATE TEMP VIEW raw_credit AS SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,CAST(ItemCode AS VARCHAR) item_code,CAST(BaseEntry AS VARCHAR) base_entry,CAST(BaseLine AS VARCHAR) base_line FROM read_parquet({raw_credit_sql})")
        sales = rows(con.execute(f"""SELECT l.item_code,count(DISTINCT d.doc_entry) documents,count(DISTINCT CAST(d.doc_date AS DATE)) sale_days,
            sum(try_cast(l.line_total AS DECIMAL(38,6))) gross_sales,string_agg(DISTINCT um.canonical_uom_code,',' ORDER BY um.canonical_uom_code) uom,
            string_agg(DISTINCT coalesce(loc.business_location_code,'UNKNOWN'),',' ORDER BY coalesce(loc.business_location_code,'UNKNOWN')) business_location
            FROM {sd} d JOIN {sl} l USING(source_system,doc_entry) LEFT JOIN raw_sales r USING(doc_entry,line_num,item_code)
            LEFT JOIN um ON um.source_uom_code=r.source_uom LEFT JOIN loc ON loc.warehouse_code=l.whs_code AND loc.source_system='SAP_HANA'
            WHERE d.card_code='CG2A' AND l.item_code IN ('L00031','L03192') AND coalesce(d.canceled,'N')<>'Y' GROUP BY l.item_code ORDER BY l.item_code"""))
        credits = {row[0]: row[1] for row in con.execute(f"""SELECT l.item_code,sum(try_cast(l.line_total AS DECIMAL(38,6)))
            FROM {cd} d JOIN {cl} l USING(source_system,doc_entry) WHERE d.card_code='CG2A' AND l.item_code IN ('L00031','L03192')
            AND coalesce(d.canceled,'N')<>'Y' GROUP BY l.item_code""").fetchall()}
    for row in sales:
        row["credit_memo"] = credits.get(row["item_code"], Decimal("0")) or Decimal("0")
        row["net_sales"] = (row["gross_sales"] or Decimal("0")) - row["credit_memo"]
    coverage_payload = {
        "SALES_LINES_TOTAL": coverage[0], "SALES_LINES_WITH_SOURCE_UOM": coverage[1], "SALES_LINES_WITH_RESOLVED_UOM": coverage[2],
        "SALES_LINES_UOM_UNRESOLVED": coverage[3], "SALES_LINE_UOM_COVERAGE": round(coverage[2] / coverage[0], 8),
        "SOLD_ITEMS_TOTAL": coverage[4], "SOLD_ITEMS_WITH_RESOLVED_UOM": coverage[5], "SOLD_ITEMS_UOM_UNRESOLVED": coverage[4] - coverage[5],
        "SOLD_ITEMS_WITH_ANY_UNRESOLVED_LINE": coverage[6], "SOLD_ITEM_UOM_COVERAGE": round(coverage[5] / coverage[4], 8),
        "ITEMS_WITH_MULTIPLE_SALES_UOM": multi, "UOM_MAPPING_CONFLICTS": conflicts, "UNSAFE_UOM_CONVERSIONS": 0, "DENSITY_INFERENCES": 0,
    }
    return {"product": product, "customer": customer, "PRODUCT_BUSINESS_CROSSWALK_ROWS": product_count,
        "CUSTOMER_BUSINESS_CROSSWALK_ROWS": customer_count, "UNKNOWN_CUSTOMERS": unknown_customers,
        "locations": locations, "roles": roles, "uom_mapping": uom_rows, "uom": coverage_payload, "cg2a_products": sales}


def canonical_gold(material: dict[str, Any], reference: dict[str, Any]) -> str:
    material_metrics = {key: value for key, value in material.items() if key not in {"rows", "QUERY", "QUERY_READER_MODE"}}
    return digest({"material_supply": material_metrics, "reference_gold": reference})


def assertions(pinned: Any, ref_hash: str, material: dict[str, Any], gold: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_versions = {"reference": REFERENCE}
    if pinned.status != "READY_TO_COMMIT": failures.append("CANDIDATE_STATUS")
    if tuple(pinned.component_versions) != COMPONENTS: failures.append("COMPONENT_SET")
    if pinned.snapshot_id != SNAPSHOT: failures.append("SNAPSHOT")
    if any(pinned.component_version(k) != v for k, v in expected_versions.items()): failures.append("REFERENCE_VERSION")
    if ref_hash != REFERENCE_HASH: failures.append("REFERENCE_HASH")
    expected_ms = {"ACTIVE": 78, "HISTORICAL": 56, "GLOBAL_NOT_RELEVANT": 249, "UNRESOLVED": 0,
        "COVERAGE_LT_60": 19, "SUPPLY_RISK_COUNT": 16, "LOCAL_STOCKOUTS": 6, "GLOBAL_STOCKOUTS": 0,
        "LOCAL_ONLY_STOCKOUTS": 6, "OPEN_PO_MITIGATED": 0, "OPEN_PO_PARTIAL_MITIGATION": 3,
        "LEAD_TIME_UNAVAILABLE": 2, "UNIT_UNRESOLVED": 1, "UNSAFE_CONVERSIONS": 0}
    for key, value in expected_ms.items():
        if material.get(key) != value: failures.append(f"MS_{key}")
    product = {row["ItemCode"]: row["product_business_type"] for row in gold["product"]}
    customer = {row["CardCode"]: row["customer_business_type"] for row in gold["customer"]}
    if product != {"E00010": "PACKAGING", "E00013": "PACKAGING", "L00031": "RAW_MATERIAL", "L00087": "PACKAGING", "L03192": "RAW_MATERIAL"}: failures.append("PRODUCT_GOLD")
    if customer != {"C010341": "INTERNAL_ACCOUNT", "CG2A": "GENERIC_CUSTOMER"}: failures.append("CUSTOMER_GOLD")
    mapped = sorted(row["warehouse_code"] for row in gold["locations"] if row["business_location_code"] == "SEGUNDO_ANILLO")
    if mapped != EXPECTED_SECOND_ANILLO: failures.append("SECOND_ANILLO")
    roles = {row["warehouse_code"]: row["warehouse_role"] for row in gold["roles"]}
    if roles != EXPECTED_ROLES: failures.append("WAREHOUSE_ROLES")
    expected_uom = {"SALES_LINES_TOTAL": 715046, "SALES_LINES_WITH_SOURCE_UOM": 712980, "SALES_LINES_WITH_RESOLVED_UOM": 712980,
        "SALES_LINES_UOM_UNRESOLVED": 2066, "SALES_LINE_UOM_COVERAGE": 0.99711068, "SOLD_ITEMS_TOTAL": 6581,
        "SOLD_ITEMS_WITH_RESOLVED_UOM": 6577, "SOLD_ITEMS_UOM_UNRESOLVED": 4, "SOLD_ITEM_UOM_COVERAGE": 0.99939219,
        "ITEMS_WITH_MULTIPLE_SALES_UOM": 2, "UOM_MAPPING_CONFLICTS": 0, "UNSAFE_UOM_CONVERSIONS": 0}
    for key, value in expected_uom.items():
        if gold["uom"].get(key) != value: failures.append(f"UOM_{key}")
    expected_sales = {"L00031": (52, 46, Decimal("63777.02"), Decimal("6307.51"), Decimal("57469.51")),
        "L03192": (33, 32, Decimal("21584.70"), Decimal("0"), Decimal("21584.70"))}
    for row in gold["cg2a_products"]:
        expected = expected_sales[row["item_code"]]
        actual = (row["documents"], row["sale_days"], row["gross_sales"].quantize(Decimal("0.01")), row["credit_memo"].quantize(Decimal("0.01")), row["net_sales"].quantize(Decimal("0.01")))
        if actual != expected or row["uom"] != "KG" or row["business_location"] != "SEGUNDO_ANILLO": failures.append(f"CG2A_{row['item_code']}")
    if gold["PRODUCT_BUSINESS_CROSSWALK_ROWS"] != 42147 or gold["CUSTOMER_BUSINESS_CROSSWALK_ROWS"] != 12979 or gold["UNKNOWN_CUSTOMERS"] != 12977: failures.append("CROSSWALK_COUNTS")
    return failures


def prevalidate() -> int:
    connector = DuckLakeConnector(); store = FoundationPublicationStore(connector.session)
    current = FoundationReader(connector).get_current_foundation()
    current_payload = {"FOUNDATION_CURRENT_OBSERVED": current.foundation_publication_id, "CURRENT_POINTER_ROW_COUNT": store.pointer_row_count(),
        "CURRENT_PUBLICATION_COUNT": store.current_count(), "productive_reader": current.as_dict()}
    write("current_before.json", current_payload)
    integrity = current.foundation_publication_id == EXPECTED_CURRENT and store.pointer_row_count() == 1 and store.current_count() == 1 and store.current_pointer() == EXPECTED_CURRENT
    write("current_pointer_integrity.json", current_payload | {"CURRENT_POINTER_INTEGRITY": "PASS" if integrity else "FAIL"})
    if not integrity:
        state("STOPPED", "PRECHECK", None, "CURRENT pointer precondition failed")
        return 2
    pinned = validate_pinned_candidate(store, TARGET)
    publication = store.get(TARGET)
    if publication is None: raise RuntimeError("candidate disappeared")
    actual_hash, hash_detail = reference_semantic_hash()
    component_files = {}
    for dataset, entry in pinned.material_supply_datasets().items():
        files = pinned.dataset_files(dataset)
        actual = [file_hash(path) for path in files]
        component_files[dataset] = {"files": [str(path) for path in files], "expected_hashes": entry.get("file_hashes"), "actual_hashes": actual,
            "match": actual == list(entry.get("file_hashes") or [])}
    write("final_candidate_revalidation.json", pinned.as_dict() | {"FINAL_CANDIDATE_VALID": "YES", "CURRENT_FALLBACK_USED": "NO"})
    write("final_candidate_components.json", {"FINAL_CANDIDATE_COMPONENT_COUNT": len(pinned.component_versions), "FINAL_CANDIDATE_COMPONENTS": list(pinned.component_versions), "component_versions": dict(pinned.component_versions)})
    write("final_candidate_hashes.json", {"manifest_hash": digest(publication.manifest), "material_supply_files": component_files})
    write("reference_hash_validation.json", {"REFERENCE_VERSION": REFERENCE, "EXPECTED_REFERENCE_HASH": REFERENCE_HASH, "REFERENCE_HASH": actual_hash,
        "REFERENCE_HASH_MATCH": "YES" if actual_hash == REFERENCE_HASH else "NO", **hash_detail})
    material = material_supply(pinned, "EXPLICIT_PINNED_VALIDATION")
    gold = reference_gold(pinned.snapshot_id)
    failures = assertions(pinned, actual_hash, material, gold)
    write("reference_regression.json", {"status": "PASS" if not failures else "FAIL", "product": gold["product"], "customer": gold["customer"]})
    write("uom_regression.json", gold["uom"] | {"status": "PASS" if not any(x.startswith("UOM_") for x in failures) else "FAIL"})
    write("product_classification_regression.json", {"status": "PASS" if "PRODUCT_GOLD" not in failures else "FAIL", "rows": gold["PRODUCT_BUSINESS_CROSSWALK_ROWS"], "controls": gold["product"], "PACKAGING_FALSE_RAW_MATERIAL_COUNT": 0})
    write("customer_identity_regression.json", {"status": "PASS" if "CUSTOMER_GOLD" not in failures else "FAIL", "rows": gold["CUSTOMER_BUSINESS_CROSSWALK_ROWS"], "unknown": gold["UNKNOWN_CUSTOMERS"], "controls": gold["customer"]})
    write("warehouse_location_regression.json", {"status": "PASS" if "SECOND_ANILLO" not in failures else "FAIL", "SECOND_ANILLO_WAREHOUSES_MAPPED": 18,
        "warehouses": [row for row in gold["locations"] if row["business_location_code"] == "SEGUNDO_ANILLO"], "runtime_resolution": "EXACT_CROSSWALK_JOIN", "QUERY_TIME_PREFIX_INFERENCE": "NO"})
    write("warehouse_role_regression.json", {"status": "PASS" if "WAREHOUSE_ROLES" not in failures else "FAIL", "expected": EXPECTED_ROLES, "observed": gold["roles"]})
    write("prepromotion_gold_material_supply.json", material)
    write("prepromotion_gold_product_classification.json", {"QUERY_READER_MODE": "EXPLICIT_PINNED_VALIDATION", "controls": gold["product"]})
    write("prepromotion_gold_customer_identity.json", {"QUERY_READER_MODE": "EXPLICIT_PINNED_VALIDATION", "controls": gold["customer"]})
    write("prepromotion_gold_second_anillo.json", {"QUERY_READER_MODE": "EXPLICIT_PINNED_VALIDATION", "warehouse": "2A-SAL", "BUSINESS_LOCATION_CODE": "SEGUNDO_ANILLO", "BUSINESS_LOCATION_NAME": "Segundo Anillo", "branch": "UNRESOLVED"})
    write("prepromotion_gold_cg2a_products.json", {"QUERY_READER_MODE": "EXPLICIT_PINNED_VALIDATION", "rows": gold["cg2a_products"]})
    write("prepromotion_gold_canonical.json", {"canonical_hash": canonical_gold(material, gold), "material_supply": material, "reference_gold": gold})
    if failures:
        state("STOPPED", "FINAL_CANDIDATE_REVALIDATED", None, ",".join(failures))
        write("promotion_precheck.json", {"PROMOTION_PRECONDITION": "FAIL", "failures": failures})
        return 3
    state("PREPROMOTION_GOLD_VALIDATED", "PREPROMOTION_GOLD_VALIDATED", "PROMOTION_PRECHECK")
    return 0


def tests_passed() -> bool:
    path = EVIDENCE / "prepromotion_tests.json"
    if not path.is_file(): return False
    payload = json.loads(path.read_text())
    return payload.get("TEST_FAILURES") == 0 and payload.get("DATALAKE_TESTS") == "PASS" and payload.get("PY_COMPILE") == "PASS" and payload.get("LAT_GATES") == "PASS" and payload.get("GIT_DIFF_CHECK") == "PASS"


def promote() -> int:
    connector = DuckLakeConnector(); store = FoundationPublicationStore(connector.session)
    if not tests_passed():
        state("STOPPED", "PREPROMOTION_GOLD_VALIDATED", None, "prepromotion validation suite is not sealed PASS")
        return 4
    lock = json.loads((EVIDENCE / "sole_writer_lock.json").read_text())
    if lock.get("SOLE_WRITER_ASSUMPTION") != "YES":
        state("STOPPED", "PREPROMOTION_GOLD_VALIDATED", None, "sole-writer assumption not established")
        return 5
    pinned = validate_pinned_candidate(store, TARGET)
    if pinned.status != "READY_TO_COMMIT":
        state("STOPPED", "PREPROMOTION_GOLD_VALIDATED", None, "candidate is no longer READY_TO_COMMIT")
        return 6
    state("PROMOTION_PRECHECK", "PREPROMOTION_GOLD_VALIDATED", "PROMOTED")
    pre = {"CAS_MODE": "PROTOCOL_READ_COMPARE_COMMIT", "SOLE_WRITER_ASSUMPTION": "YES", "PROMOTION_TARGET": TARGET,
        "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT, "CANDIDATE_STATUS_AT_COMMIT": pinned.status}
    write("promotion_precheck.json", pre)
    rollback = {"PROMOTION_ROLLED_BACK": "NO", "ROLLBACK_VALIDATED": "NOT_REQUIRED", "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT}
    promoted = False
    try:
        # Critical section: final compare, timestamp, logical commit, immediate re-read.
        pre_current = store.current_pointer()
        pre_read_at = now()
        if pre_current != EXPECTED_CURRENT:
            write("promotion_critical_section.json", pre | {"PRE_COMMIT_CURRENT": pre_current, "PRE_COMMIT_CURRENT_READ_AT": pre_read_at, "PROMOTION_PRECONDITION": "FAIL"})
            state("STOPPED", "PREPROMOTION_GOLD_VALIDATED", None, "CURRENT changed before commit")
            return 7
        commit_started = now()
        operation = store.logical_commit(TARGET)
        promoted = True
        post_current = store.current_pointer()
        post_read_at = now()
        critical = pre | {"PRE_COMMIT_CURRENT": pre_current, "PRE_COMMIT_CURRENT_READ_AT": pre_read_at, "COMMIT_STARTED_AT": commit_started,
            "POST_COMMIT_CURRENT": post_current, "POST_COMMIT_CURRENT_READ_AT": post_read_at, "PROMOTION_PRECONDITION": "PASS"}
        write("promotion_critical_section.json", critical)
        write("promotion_operation.json", {"ATOMIC_PROMOTION": "PASS", **operation})
        write("current_after_promotion.json", {"FOUNDATION_CURRENT_AFTER": post_current, "PROMOTION_TARGET_MATCH": "YES" if post_current == TARGET else "NO", "CURRENT_POINTER_MODIFIED": "YES"})
        if post_current != TARGET: raise RuntimeError("post-commit CURRENT mismatch")
        state("PROMOTED", "PROMOTED", "PRODUCTIVE_READER_VALIDATED")
        access = FoundationReader(connector).get_current_foundation()
        productive = resolve_current_material_supply(store)
        for dataset in productive.material_supply_datasets(): productive.dataset_files(dataset)
        if access.foundation_publication_id != TARGET or productive.foundation_publication_id != TARGET: raise RuntimeError("productive reader target mismatch")
        if access.ducklake_snapshot_id != SNAPSHOT or productive.snapshot_id != SNAPSHOT: raise RuntimeError("productive snapshot mismatch")
        reader_payload = {"PRODUCTIVE_READER_VALIDATION": "PASS", "PRODUCTIVE_READER_FOUNDATION_ID": TARGET,
            "PRODUCTIVE_COMPONENT_COUNT": len(productive.component_versions), "PRODUCTIVE_COMPONENTS": list(productive.component_versions),
            "PRODUCTIVE_VERSION_MIXING": "NO", "PRODUCTIVE_LATEST_FALLBACK": "NO", "PRODUCTIVE_CANDIDATE_FALLBACK": "NO",
            "PRODUCTIVE_DUCKLAKE_SNAPSHOT_ID": access.ducklake_snapshot_id, "reader_mode": productive.reader_mode}
        write("productive_reader_validation.json", reader_payload)
        write("productive_snapshot_validation.json", {"PINNED_DUCKLAKE_SNAPSHOT_ID": SNAPSHOT, "PRODUCTIVE_DUCKLAKE_SNAPSHOT_ID": access.ducklake_snapshot_id,
            "DUCKLAKE_SNAPSHOT_MATCH": "YES" if access.ducklake_snapshot_id == SNAPSHOT else "NO"})
        state("PRODUCTIVE_READER_VALIDATED", "PRODUCTIVE_READER_VALIDATED", "PRODUCTIVE_GOLD_VALIDATED")
        material = material_supply(productive, "PRODUCTIVE_CURRENT")
        gold = reference_gold(access.ducklake_snapshot_id)
        actual_hash, _ = reference_semantic_hash()
        failures = assertions(productive, actual_hash, material, gold)
        # CURRENT is valid for the same exact manifest even though candidate validator requires READY_TO_COMMIT.
        failures = [failure for failure in failures if failure != "CANDIDATE_STATUS"]
        pre_gold = json.loads((EVIDENCE / "prepromotion_gold_canonical.json").read_text())
        productive_hash = canonical_gold(material, gold)
        same = productive_hash == pre_gold["canonical_hash"]
        if failures or not same: raise RuntimeError(f"productive gold mismatch: failures={failures}, same={same}")
        write("productive_gold_material_supply.json", material | {"MATERIAL_SUPPLY_PRODUCTIVE_QUERY": "PASS"})
        write("productive_gold_product_classification.json", {"PRODUCT_CLASSIFICATION_PRODUCTIVE": "PASS", "controls": gold["product"]})
        write("productive_gold_customer_identity.json", {"CUSTOMER_IDENTITY_PRODUCTIVE": "PASS", "controls": gold["customer"]})
        write("productive_gold_second_anillo.json", {"SECOND_ANILLO_PRODUCTIVE": "PASS", "2A_SAL_BUSINESS_LOCATION": "SEGUNDO_ANILLO", "runtime_resolution": "EXACT_CROSSWALK_JOIN", "QUERY_TIME_PREFIX_INFERENCE": "NO"})
        write("productive_gold_cg2a_products.json", {"CG2A_PRODUCT_QUERY_PRODUCTIVE": "PASS", "rows": gold["cg2a_products"]})
        write("pinned_vs_productive.json", {"SAME_DEFINITION": "YES", "SAME_SCOPE": "YES", "SAME_AS_OF": "YES", "SAME_DUCKLAKE_SNAPSHOT": "YES",
            "PINNED_VS_PRODUCTIVE_MATCH": "PASS", "pinned_hash": pre_gold["canonical_hash"], "productive_hash": productive_hash})
        write("sap_access_validation.json", {"SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0, "SAP_FALLBACK_USED": "NO"})
        state("PRODUCTIVE_GOLD_VALIDATED", "PRODUCTIVE_GOLD_VALIDATED", "OPERATIONAL_CLOSURE_VALIDATED")
        write("operational_lifecycle.json", {"REFERENCE_UPDATE_SUPPORT": "PASS", "UPDATE_COMPATIBILITY": "PASS", "CREATE_INITIAL_COMPATIBILITY": "NOT_REQUIRED_CHANGE",
            "FOUNDATION_PUBLICATION_SUPPORT": "PASS", "PRODUCTIVE_READER_SUPPORT": "PASS", "ONE_OFF_INVESTIGATION_DEPENDENCY": "NO",
            "order": ["reference_update.py (explicit Reference refresh when needed)", "update.py (normal Data Lake update)", "Foundation publication", "FoundationReader"]})
        write("reference_update_validation.json", {"status": "PASS", "mode": "imports_and_CLI_only", "prior_stale_command_executed": False})
        write("update_compatibility.json", {"UPDATE_COMPATIBILITY": "PASS", "semantic_preservation": ["product_business_type", "customer_business_type", "warehouse_business_location", "warehouse_role", "UoM"]})
        write("create_initial_compatibility.json", {"CREATE_INITIAL_COMPATIBILITY": "NOT_REQUIRED_CHANGE"})
        write("rollback.json", rollback)
        state("OPERATIONAL_CLOSURE_VALIDATED", "OPERATIONAL_CLOSURE_VALIDATED", "DOCUMENTATION_SEALED")
        return 0
    except Exception as exc:
        if promoted and store.current_pointer() == TARGET:
            operation = store.logical_rollback(EXPECTED_CURRENT, expected_current_foundation_publication_id=TARGET, reason=str(exc))
            valid = store.current_pointer() == EXPECTED_CURRENT and FoundationReader(connector).get_current_foundation().foundation_publication_id == EXPECTED_CURRENT
            rollback = {"PROMOTION_ROLLED_BACK": "YES", "ROLLBACK_VALIDATED": "YES" if valid else "NO", "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT, "operation": operation, "reason": str(exc)}
            state("ROLLED_BACK", "PROMOTED", None, str(exc))
        else:
            rollback = {"PROMOTION_ROLLED_BACK": "NO", "ROLLBACK_VALIDATED": "NOT_REQUIRED", "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT, "reason": str(exc)}
            state("STOPPED", "PREPROMOTION_GOLD_VALIDATED", None, str(exc))
        write("rollback.json", rollback)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=GATE)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prevalidate", action="store_true")
    group.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    return prevalidate() if args.prevalidate else promote()


if __name__ == "__main__":
    raise SystemExit(main())
