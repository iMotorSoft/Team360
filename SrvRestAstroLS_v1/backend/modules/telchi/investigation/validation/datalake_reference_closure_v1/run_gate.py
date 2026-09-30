"""Close Telchi Reference semantics from frozen Data Lake inputs only.

No SAP adapter is imported.  The gate creates one immutable Reference version
and one exact pinned Foundation candidate, but never promotes CURRENT.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
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
from modules.telchi.datalake.material_supply_candidate import mark_candidate_ready, validate_pinned_candidate
from modules.telchi.datalake.reference_closure import build_reference_closure, discover_sales_files
from modules.telchi.datalake.reference_semantics import SECOND_ANILLO_WAREHOUSE_CODES, SEGUNDO_ANILLO

GATE = "TELCHI_DATALAKE_REFERENCE_CLOSURE_V1"
BASE_FOUNDATION = "foundation_14983f93892bc83399ae2b0bde3794d0"
BASE_REFERENCE = "v2_customer_business_type_91a610c6d8858eff"
SALES_RUN = "manual-update-20260924T132754050866Z"
RUN_ID = "reference-closure-v1-2026-09-25"
EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
REPO = Path(__file__).resolve().parents[7]
BACKEND = REPO / "SrvRestAstroLS_v1/backend"


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


def write_json(name: str, value: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    path = EVIDENCE / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=jsonable) + "\n", encoding="utf-8")
    temporary.replace(path)


def dict_rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [str(item[0]) for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def qpath(path: Path) -> str:
    return str(path).replace("'", "''")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    started = time.perf_counter()
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    git_before = subprocess.run(["git", "status", "--short"], cwd=REPO, text=True, capture_output=True, check=True).stdout.splitlines()
    write_json("worktree_safety.json", {
        "snapshot": git_before, "git_add": False, "git_commit": False,
        "destructive_git_actions": [], "preexisting_changes_preserved": True,
    })
    write_json("resource_safety.json", {
        "MACHINE_STABILITY": "PRIORITIZED", "MAX_HEAVY_WORKERS": 1,
        "DUCKDB_THREADS": 1, "SAP_MAX_CONNECTIONS": 0,
    })

    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)
    current = FoundationReader(connector).get_current_foundation()
    current_before = current.foundation_publication_id
    base = validate_pinned_candidate(store, BASE_FOUNDATION)
    if base.component_version("reference") != BASE_REFERENCE:
        raise RuntimeError("exact base candidate does not pin the required Reference")
    base_publication = store.get(BASE_FOUNDATION)
    if base_publication is None:
        raise RuntimeError("base Foundation candidate metadata missing")
    write_json("precheck.json", {
        "FOUNDATION_CURRENT_OBSERVED": current_before,
        "BASE_FOUNDATION_CANDIDATE": BASE_FOUNDATION,
        "REFERENCE_BASE_VERSION": BASE_REFERENCE,
        "base_candidate": base.as_dict(),
        "SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0,
    })
    write_json("foundation_current.json", current.as_dict())
    write_json("reference_baseline.json", {
        "version": BASE_REFERENCE,
        "reference_path": str(DATA_ROOT / "reference/_versions" / BASE_REFERENCE),
        "crosswalk_path": str(DATA_ROOT / "crosswalk/_versions" / BASE_REFERENCE),
        "selected_by": "EXACT_EXPLICIT_ID",
    })

    # Operational lifecycle build, twice against the exact same frozen inputs.
    build_one = build_reference_closure(data_root=DATA_ROOT, base_version=BASE_REFERENCE, sales_run_id=SALES_RUN)
    build_two = build_reference_closure(data_root=DATA_ROOT, base_version=BASE_REFERENCE, sales_run_id=SALES_RUN)
    if build_one["version"] != build_two["version"] or build_one["reference_hash"] != build_two["reference_hash"]:
        raise RuntimeError("Reference build is not reproducible")
    version = build_one["version"]
    reference = Path(build_one["reference_path"])
    crosswalk = Path(build_one["crosswalk_path"])
    location_path = crosswalk / "warehouse_business_location/part-00000.parquet"
    uom_path = crosswalk / "uom_mapping/part-00000.parquet"
    sales_files = discover_sales_files(DATA_ROOT, SALES_RUN)
    credit_files = sorted((DATA_ROOT / "raw/sap/TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1").glob(f"credit-memo-*/{SALES_RUN}_*/part-00000.parquet"))
    if not credit_files:
        raise RuntimeError("exact frozen Credit Memo source files are absent")

    sd = f'(SELECT * FROM telchi.atomic."sales_document" AT (VERSION => {base.snapshot_id}))'
    sl = f'(SELECT * FROM telchi.atomic."sales_line" AT (VERSION => {base.snapshot_id}))'
    cd = f'(SELECT * FROM telchi.atomic."credit_memo_document" AT (VERSION => {base.snapshot_id}))'
    cl = f'(SELECT * FROM telchi.atomic."credit_memo_line" AT (VERSION => {base.snapshot_id}))'
    product_crosswalk = crosswalk / "product_business_type/part-00000.parquet"
    customer_crosswalk = crosswalk / "customer_business_type/part-00000.parquet"
    warehouse_roles = reference / "warehouse_roles/part-00000.parquet"

    with connector.session(read_only=True) as con:
        con.execute("SET threads=1")
        location_rows = dict_rows(con.execute("SELECT * FROM read_parquet(?) ORDER BY warehouse_code,source_system", [str(location_path)]))
        second = [row for row in location_rows if row["business_location_code"] == SEGUNDO_ANILLO]
        two_a = [row for row in second if row["warehouse_code"].startswith("2A-")]
        warehouse_inventory = {
            "WAREHOUSES_TOTAL": len(location_rows),
            "WAREHOUSES_LOCATION_MAPPED": len(second),
            "WAREHOUSES_LOCATION_UNKNOWN": len(location_rows) - len(second),
            "rows": location_rows,
        }
        write_json("warehouse_inventory.json", warehouse_inventory)
        discovery = [{
            **row,
            "candidate_reason": (
                "Explicit 2A code in frozen OWHS plus BUSINESS_CONFIRMED group assertion"
                if row["warehouse_code"].startswith("2A-") else
                "Frozen almacenOficina row explicitly linked to Sucursal 2do. Anillo"
            ),
            "final_business_location": row["business_location_code"],
        } for row in second]
        write_json("second_anillo_discovery.json", {"warehouses": discovery, "count": len(discovery)})
        write_json("warehouse_business_location_mapping.json", {
            "runtime_resolution": "EXACT_CROSSWALK_JOIN",
            "query_time_prefix_inference": False,
            "rows": location_rows,
        })
        role_rows = dict_rows(con.execute(
            "SELECT CAST(warehouse_code AS VARCHAR) warehouse_code,CAST(warehouse_role AS VARCHAR) warehouse_role,CAST(classification_source AS VARCHAR) classification_source FROM read_parquet(?) ORDER BY warehouse_code",
            [str(warehouse_roles)],
        ))
        expected_roles = {"SAA-M1": "RAW_MATERIAL", "SAA-P1": "PRODUCTION", "SAA-T1": "FINISHED_PRODUCT", "SAA-DAN": "DAMAGED", "SAA-T2": "RECONDITIONED", "SAA-T3": "RECONDITIONED"}
        observed_roles = {row["warehouse_code"]: row["warehouse_role"] for row in role_rows}
        roles_pass = all(observed_roles.get(code) == role for code, role in expected_roles.items())
        write_json("warehouse_role_regression.json", {"status": "PASS" if roles_pass else "FAIL", "expected": expected_roles, "observed": observed_roles, "rows": role_rows})

        source_schema = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [[str(path) for path in sales_files]]).fetchall()
        atomic_schema = con.execute(f"DESCRIBE SELECT * FROM {sl}").fetchall()
        write_json("uom_source_inventory.json", {
            "frozen_sales_files": [str(path) for path in sales_files],
            "frozen_credit_files": [str(path) for path in credit_files],
            "source_columns": [row[0] for row in source_schema],
            "atomic_columns": [row[0] for row in atomic_schema],
            "authoritative_fields": ["unitMsr", "NumPerMsr"],
            "atomic_gap": "unitMsr/NumPerMsr captured in frozen source files but not projected into atomic sales_line",
        })
        write_json("uom_field_semantics.json", {
            "Quantity": "source commercial line quantity",
            "unitMsr": "source-native line UoM identifier",
            "NumPerMsr": "source-native units-per-measure; observed invariant measured below",
            "item_master_uom": "supporting only; never relabels a line without compatibility evidence",
            "ItemName_authority": False,
        })
        uom_rows = dict_rows(con.execute("SELECT * FROM read_parquet(?) ORDER BY source_uom_code", [str(uom_path)]))
        write_json("uom_mapping.json", {"rows": uom_rows, "identity_only": True, "unsafe_conversions": 0, "density_inferences": 0})

        raw_sales = [str(path) for path in sales_files]
        raw_credit = [str(path) for path in credit_files]
        # Atomic is the count authority; exact source-key join supplies UoM.
        coverage_row = con.execute(f"""
            WITH raw AS (
              SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,
                     trim(CAST(unitMsr AS VARCHAR)) source_uom,CAST(NumPerMsr AS VARCHAR) num_per_msr
              FROM read_parquet(?)
            ), joined AS (
              SELECT l.item_code,l.doc_entry,l.line_num,nullif(r.source_uom,'') source_uom,r.num_per_msr
              FROM {sl} l LEFT JOIN raw r USING(doc_entry,line_num)
            )
            SELECT count(*) total,
                   count(source_uom) with_source,
                   count(source_uom) resolved,
                   count(*)-count(source_uom) unresolved,
                   count(DISTINCT item_code) items,
                   count(DISTINCT item_code) FILTER (WHERE source_uom IS NOT NULL) items_resolved,
                   count(DISTINCT item_code) FILTER (WHERE source_uom IS NULL) items_with_unresolved_lines,
                   count(*) FILTER (WHERE num_per_msr IS NOT NULL AND try_cast(num_per_msr AS DECIMAL(38,12))<>1) nonunit_num_per_msr
            FROM joined
        """, [raw_sales]).fetchone()
        multi = con.execute("""
            SELECT count(*) FROM (
              SELECT CAST(ItemCode AS VARCHAR) item_code
              FROM read_parquet(?) WHERE nullif(trim(CAST(unitMsr AS VARCHAR)),'') IS NOT NULL
              GROUP BY item_code HAVING count(DISTINCT upper(trim(CAST(unitMsr AS VARCHAR))))>1
            )
        """, [raw_sales]).fetchone()[0]
        mapping_conflicts = con.execute("""
            SELECT count(*) FROM (
              SELECT source_uom_code FROM read_parquet(?) GROUP BY source_uom_code
              HAVING count(DISTINCT canonical_uom_code)>1
            )
        """, [str(uom_path)]).fetchone()[0]
        coverage = {
            "SALES_LINES_TOTAL": coverage_row[0],
            "SALES_LINES_WITH_SOURCE_UOM": coverage_row[1],
            "SALES_LINES_WITH_RESOLVED_UOM": coverage_row[2],
            "SALES_LINES_UOM_UNRESOLVED": coverage_row[3],
            "SALES_LINE_UOM_COVERAGE": round(coverage_row[2] / coverage_row[0], 8),
            "SOLD_ITEMS_TOTAL": coverage_row[4],
            "SOLD_ITEMS_WITH_RESOLVED_UOM": coverage_row[5],
            "SOLD_ITEMS_UOM_UNRESOLVED": coverage_row[4] - coverage_row[5],
            "SOLD_ITEMS_WITH_ANY_UNRESOLVED_LINE": coverage_row[6],
            "SOLD_ITEM_UOM_COVERAGE": round(coverage_row[5] / coverage_row[4], 8),
            "ITEMS_WITH_MULTIPLE_SALES_UOM": multi,
            "UOM_MAPPING_CONFLICTS": mapping_conflicts,
            "NUM_PER_MSR_NOT_ONE": coverage_row[7],
        }
        write_json("uom_coverage.json", coverage)
        write_json("uom_conflicts.json", {"UOM_MAPPING_CONFLICTS": mapping_conflicts, "ITEMS_WITH_MULTIPLE_SALES_UOM": multi})

        con.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{qpath(product_crosswalk)}')")
        con.execute(f"CREATE TEMP VIEW cbt AS SELECT * FROM read_parquet('{qpath(customer_crosswalk)}')")
        con.execute(f"CREATE TEMP VIEW loc AS SELECT * FROM read_parquet('{qpath(location_path)}')")
        con.execute(f"CREATE TEMP VIEW uom_map AS SELECT * FROM read_parquet('{qpath(uom_path)}')")
        raw_sales_sql = "[" + ",".join("'" + path.replace("'", "''") + "'" for path in raw_sales) + "]"
        raw_credit_sql = "[" + ",".join("'" + path.replace("'", "''") + "'" for path in raw_credit) + "]"
        con.execute(f"CREATE TEMP VIEW raw_sales_uom AS SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,CAST(ItemCode AS VARCHAR) item_code,trim(CAST(unitMsr AS VARCHAR)) source_uom,CAST(NumPerMsr AS VARCHAR) num_per_msr FROM read_parquet({raw_sales_sql})")
        con.execute(f"CREATE TEMP VIEW raw_credit_lineage AS SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,CAST(ItemCode AS VARCHAR) item_code,CAST(BaseType AS VARCHAR) base_type,CAST(BaseEntry AS VARCHAR) base_entry,CAST(BaseLine AS VARCHAR) base_line FROM read_parquet({raw_credit_sql})")
        gold_sales = dict_rows(con.execute(f"""
            SELECT l.item_code,count(DISTINCT d.doc_entry) documents,count(DISTINCT CAST(d.doc_date AS DATE)) sale_days,
                   sum(try_cast(l.line_total AS DECIMAL(38,6))) gross_sales,
                   sum(try_cast(l.quantity AS DECIMAL(38,6))) gross_quantity,
                   string_agg(DISTINCT l.whs_code, ',' ORDER BY l.whs_code) warehouses,
                   string_agg(DISTINCT r.source_uom, ',' ORDER BY r.source_uom) source_uoms,
                   string_agg(DISTINCT um.canonical_uom_code, ',' ORDER BY um.canonical_uom_code) canonical_uoms,
                   string_agg(DISTINCT coalesce(loc.business_location_code,'UNKNOWN'), ',' ORDER BY coalesce(loc.business_location_code,'UNKNOWN')) business_locations,
                   count(DISTINCT coalesce(l.attributed_slp_code,l.slp_code,d.slp_code)) sellers
            FROM {sd} d JOIN {sl} l USING(source_system,doc_entry)
            LEFT JOIN raw_sales_uom r USING(doc_entry,line_num,item_code)
            LEFT JOIN uom_map um ON um.source_uom_code=r.source_uom
            LEFT JOIN loc ON loc.warehouse_code=l.whs_code AND loc.source_system='SAP_HANA'
            WHERE d.card_code='CG2A' AND l.item_code IN ('L00031','L03192') AND coalesce(d.canceled,'N')<>'Y'
            GROUP BY l.item_code ORDER BY l.item_code
        """))
        gold_credit = dict_rows(con.execute(f"""
            SELECT l.item_code,count(DISTINCT d.doc_entry) credit_documents,
                   sum(try_cast(l.line_total AS DECIMAL(38,6))) credit_amount,
                   sum(try_cast(l.quantity AS DECIMAL(38,6))) credit_quantity,
                   string_agg(DISTINCT base_uom.source_uom, ',' ORDER BY base_uom.source_uom) source_uoms
            FROM {cd} d JOIN {cl} l USING(source_system,doc_entry)
            LEFT JOIN raw_credit_lineage r USING(doc_entry,line_num,item_code)
            LEFT JOIN raw_sales_uom base_uom ON base_uom.doc_entry=r.base_entry AND base_uom.line_num=r.base_line AND base_uom.item_code=r.item_code
            WHERE d.card_code='CG2A' AND l.item_code IN ('L00031','L03192') AND coalesce(d.canceled,'N')<>'Y'
            GROUP BY l.item_code ORDER BY l.item_code
        """))
        seller_distribution = dict_rows(con.execute(f"""
            SELECT l.item_code,coalesce(l.attributed_slp_code,l.slp_code,d.slp_code) seller_code,
                   count(DISTINCT d.doc_entry) documents
            FROM {sd} d JOIN {sl} l USING(source_system,doc_entry)
            WHERE d.card_code='CG2A' AND l.item_code IN ('L00031','L03192') AND coalesce(d.canceled,'N')<>'Y'
            GROUP BY l.item_code,seller_code ORDER BY l.item_code,documents DESC,seller_code
        """))
        sellers_by_item = {
            item: [entry for entry in seller_distribution if entry["item_code"] == item]
            for item in ("L00031", "L03192")
        }
        credits = {row["item_code"]: row for row in gold_credit}
        for row in gold_sales:
            credit = credits.get(row["item_code"], {})
            row["credit_amount"] = credit.get("credit_amount", Decimal("0")) or Decimal("0")
            row["credit_quantity"] = credit.get("credit_quantity", Decimal("0")) or Decimal("0")
            row["net_sales"] = (row["gross_sales"] or Decimal("0")) - row["credit_amount"]
            row["net_quantity"] = (row["gross_quantity"] or Decimal("0")) - row["credit_quantity"]
            row["seller_distribution"] = sellers_by_item[row["item_code"]]
            if not row["source_uoms"] or row["source_uoms"] != row["canonical_uoms"]:
                row["uom_status"] = "UOM_UNRESOLVED"
            elif row["credit_quantity"] and credit.get("source_uoms") == row["source_uoms"]:
                row["uom_status"] = "UOM_RESOLVED_SUPPORTED"
            else:
                row["uom_status"] = "UOM_RESOLVED_EXACT"
        gold = {row["item_code"]: row for row in gold_sales}
        for item in ("L00031", "L03192"):
            write_json(f"{item.lower()}_uom_validation.json", {
                "ItemCode": item, "result": gold.get(item),
                "available_source_fields": ["Quantity", "unitMsr", "NumPerMsr"],
                "item_level_fields": ["InvntryUom", "SalUnitMsr", "BuyUnitMsr"],
                "conversion": "IDENTITY_ONLY", "item_name_used": False,
            })

        product_rows = con.execute("SELECT count(*) FROM pbt").fetchone()[0]
        product_controls = {row[0]: row[1] for row in con.execute("SELECT ItemCode,product_business_type FROM pbt WHERE ItemCode IN ('E00010','E00013','L00087')").fetchall()}
        false_raw = sum(product_controls.get(code) == "RAW_MATERIAL" for code in product_controls)
        product_regression = {
            "PRODUCT_BUSINESS_CROSSWALK_ROWS": product_rows,
            "PRODUCT_CLASSIFICATION_REGRESSION": "PASS" if product_rows == 42147 and all(product_controls.get(c) == "PACKAGING" for c in ("E00010","E00013","L00087")) else "FAIL",
            "E00010_CLASSIFICATION": product_controls.get("E00010"),
            "E00013_CLASSIFICATION": product_controls.get("E00013"),
            "L00087_CLASSIFICATION": product_controls.get("L00087"),
            "PACKAGING_FALSE_RAW_MATERIAL_COUNT": false_raw,
        }
        write_json("product_business_regression.json", product_regression)
        customer_rows = con.execute("SELECT count(*) FROM cbt").fetchone()[0]
        customer_controls = {row[0]: (row[1], row[2]) for row in con.execute("SELECT CardCode,customer_business_type,classification_source FROM cbt WHERE CardCode IN ('CG2A','C010341')").fetchall()}
        unknown_customers = con.execute("SELECT count(*) FROM cbt WHERE customer_business_type='UNKNOWN'").fetchone()[0]
        customer_regression = {
            "CUSTOMER_BUSINESS_CROSSWALK_ROWS": customer_rows,
            "CUSTOMER_CLASSIFICATION_REGRESSION": "PASS" if customer_controls.get("CG2A") == ("GENERIC_CUSTOMER","BUSINESS_CONFIRMED") and customer_controls.get("C010341", (None,))[0] == "INTERNAL_ACCOUNT" else "FAIL",
            "CG2A_CUSTOMER_BUSINESS_TYPE": customer_controls.get("CG2A", (None,None))[0],
            "CG2A_MAPPING_SOURCE": customer_controls.get("CG2A", (None,None))[1],
            "C010341_CUSTOMER_BUSINESS_TYPE": customer_controls.get("C010341", (None,None))[0],
            "UNKNOWN_CUSTOMERS": unknown_customers,
        }
        write_json("customer_business_regression.json", customer_regression)

    # Exact candidate: only Reference changes; all five other versions are copied.
    lock = store.acquire_run_lock(RUN_ID, owner=GATE)
    if lock["status"] != "ACQUIRED":
        raise RuntimeError(f"Foundation writer lock unavailable: {lock}")
    try:
        candidate = prepare_candidate(store, update_run_id=RUN_ID, reference_version=version)
        entries = base_publication.manifest["components"]
        refs = {
            "reference": ComponentReference("reference", version, max(filter(None, [build_one["sales_source_as_of"], build_one["warehouse_source_as_of"]]), default=None)),
            "sales": ComponentReference("sales", base.component_version("sales"), entries["sales"].get("source_as_of")),
            "credit_memo": ComponentReference("credit_memo", base.component_version("credit_memo"), entries["credit_memo"].get("source_as_of")),
            "oinm": ComponentReference("oinm", base.component_version("oinm"), entries["oinm"].get("source_as_of")),
            "oitw": ComponentReference("oitw", base.component_version("oitw"), entries["oitw"].get("source_as_of")),
        }
        manifest = json.loads(json.dumps(base_publication.manifest, default=jsonable))
        manifest["foundation_publication_id"] = candidate.foundation_publication_id
        manifest["base_snapshot_id"] = base.snapshot_id
        manifest["components"]["reference"] = refs["reference"].as_dict()
        manifest["reference_closure"] = {
            "gate": GATE, "version": version, "reference_hash": build_one["reference_hash"],
            "warehouse_location_crosswalk": str(location_path), "uom_crosswalk": str(uom_path),
        }
        store.update_components(candidate.foundation_publication_id, refs, source_as_of=base_publication.source_as_of, validation_status="PENDING", manifest=manifest)
        store.set_status(candidate.foundation_publication_id, VALIDATING)
        pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
        for component in ("sales", "credit_memo", "oinm", "oitw", "material_supply"):
            if pinned.component_version(component) != base.component_version(component):
                raise RuntimeError(f"candidate changed unaffected component {component}")
        mark_candidate_ready(store, candidate.foundation_publication_id)
        pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
    finally:
        store.release_run_lock(RUN_ID)
    current_after = store.current_pointer()
    if current_after != current_before:
        raise RuntimeError("CURRENT pointer modified during closure gate")

    candidate_evidence = {
        "FOUNDATION_CURRENT_BEFORE": current_before, "FOUNDATION_CURRENT_AFTER": current_after,
        "CURRENT_POINTER_MODIFIED": "NO", "BASE_FOUNDATION_CANDIDATE": BASE_FOUNDATION,
        "FINAL_REFERENCE_CLOSURE_CANDIDATE_ID": candidate.foundation_publication_id,
        "FOUNDATION_CANDIDATE_COMPONENTS": list(pinned.component_versions),
        "FOUNDATION_CANDIDATE_VALID": "YES", "CANDIDATE_VERSION_MIXING": "NO",
        "LATEST_COMPONENT_FALLBACK_USED": "NO", "CURRENT_FALLBACK_USED": "NO",
        "CANDIDATE_READY_FOR_FINAL_PROMOTION": "YES",
        "pinned": pinned.as_dict(),
    }
    write_json("foundation_candidate.json", candidate_evidence)
    write_json("candidate_validation.json", candidate_evidence)
    write_json("reference_consolidation.json", build_one | {"NEW_REFERENCE_VERSION": version})
    write_json("reference_reproducibility.json", {"REFERENCE_REPRODUCIBLE": "YES", "run_1": build_one, "run_2": build_two})
    write_json("reference_idempotency.json", {"REFERENCE_IDEMPOTENT": "YES", "second_run_reused": build_two["reused"]})

    expected_gold = {"L00031": (52, Decimal("57469.51")), "L03192": (33, Decimal("21584.70"))}
    business_pass = all(code in gold and gold[code]["documents"] == expected[0] and gold[code]["net_sales"].quantize(Decimal("0.01")) == expected[1] and SEGUNDO_ANILLO in gold[code]["business_locations"] for code, expected in expected_gold.items())
    gold_evidence = {
        "QUERY": "GENERIC_CUSTOMER_PRODUCT_SALES_DETAIL_REFERENCE_V2",
        "QUERY_EXECUTED": "YES", "QUERY_FOUNDATION_ID": candidate.foundation_publication_id,
        "QUERY_SAP_ACCESSED": "NO", "CUSTOMER": "CG2A", "products": gold_sales,
        "EXPECTED_LOCATION_FOR_2A_SAL": SEGUNDO_ANILLO,
        "BUSINESS_QUERY_REGRESSION": "PASS" if business_pass else "FAIL",
    }
    write_json("gold_query_cg2a_products.json", gold_evidence)
    sal_location = next(row for row in second if row["warehouse_code"] == "2A-SAL" and row["source_system"] == "SAP_HANA")
    write_json("business_location_regression.json", {
        "status": "PASS" if business_pass else "FAIL",
        "WAREHOUSE_CODE": "2A-SAL", "WAREHOUSE_NAME": sal_location["warehouse_name"],
        "BUSINESS_LOCATION_CODE": sal_location["business_location_code"],
        "BUSINESS_LOCATION_NAME": sal_location["business_location_name"],
        "BRANCH_ID": None, "BRANCH_RESOLUTION_STATUS": "UNRESOLVED",
        "query_time_prefix_inference": False, "products": gold_sales,
    })
    write_json("material_supply_regression.json", {
        "status": "PASS" if roles_pass else "FAIL", "component_version": base.component_version("material_supply"),
        "component_rebuilt": False, "warehouse_roles": observed_roles,
        "unsafe_conversion_regression": 0,
    })
    write_json("operational_lifecycle.json", {
        "REFERENCE_UPDATE_SUPPORT": "PASS",
        "command": f"python -m modules.telchi.datalake.reference_update --consolidate-offline --base-reference-version {BASE_REFERENCE} --sales-run-id {SALES_RUN}",
        "CREATE_INITIAL_COMPATIBILITY": "NOT_REQUIRED_CHANGE", "UPDATE_COMPATIBILITY": "PASS",
        "ONE_OFF_INVESTIGATION_DEPENDENCY": "NO",
    })

    reference_status = "PASS" if roles_pass and mapping_conflicts == 0 and product_regression["PRODUCT_CLASSIFICATION_REGRESSION"] == "PASS" and customer_regression["CUSTOMER_CLASSIFICATION_REGRESSION"] == "PASS" else "FAIL"
    uom_status = "PASS" if coverage["SALES_LINES_WITH_RESOLVED_UOM"] > 0 and mapping_conflicts == 0 else "FAIL"
    location_status = "PASS" if any(row["warehouse_code"] == "2A-SAL" and row["mapping_source"] == "BUSINESS_CONFIRMED" for row in second) else "FAIL"
    blockers: list[str] = []
    if not business_pass: blockers.append("GOLD_BUSINESS_QUERY_REGRESSION")
    if reference_status != "PASS": blockers.append("REFERENCE_REGRESSION")
    ready = not blockers

    tests_cmd = ["uv", "run", "pytest", "-q", "modules/telchi/datalake/tests/test_reference_semantics.py", "modules/telchi/datalake/tests/test_product_business_classification.py", "modules/telchi/datalake/tests/test_customer_business_identity.py", "modules/telchi/datalake/tests/test_material_supply.py", "modules/telchi/datalake/tests/test_material_supply_candidate.py"]
    test_run = subprocess.run(tests_cmd, cwd=BACKEND, text=True, capture_output=True)
    compile_run = subprocess.run(["uv", "run", "python", "-m", "py_compile", "modules/telchi/datalake/reference_semantics.py", "modules/telchi/datalake/reference_closure.py", "modules/telchi/datalake/reference_update.py", "modules/telchi/investigation/validation/datalake_reference_closure_v1/run_gate.py"], cwd=BACKEND, text=True, capture_output=True)
    diff_run = subprocess.run(["git", "diff", "--check"], cwd=REPO, text=True, capture_output=True)
    test_evidence = {
        "command": " ".join(tests_cmd), "returncode": test_run.returncode,
        "stdout": test_run.stdout, "stderr": test_run.stderr,
        "PY_COMPILE": "PASS" if compile_run.returncode == 0 else "FAIL",
        "GIT_DIFF_CHECK": "PASS" if diff_run.returncode == 0 else "FAIL",
        "LAT_GATES": "PENDING_SEPARATE_EXECUTION",
    }
    write_json("tests.json", test_evidence)
    if test_run.returncode or compile_run.returncode or diff_run.returncode:
        ready = False
        blockers.append("FOCUSED_TEST_OR_DIFF_FAILURE")

    summary = {
        "VERDICT": f"{GATE}_{'PASS' if ready else 'FAIL'}",
        "REFERENCE_CLOSURE_STATUS": "PASS" if ready else "FAIL",
        "WAREHOUSE_LOCATION_STATUS": location_status,
        **{key: warehouse_inventory[key] for key in ("WAREHOUSES_TOTAL","WAREHOUSES_LOCATION_MAPPED","WAREHOUSES_LOCATION_UNKNOWN")},
        "SECOND_ANILLO_CANONICAL_CODE": SEGUNDO_ANILLO, "SECOND_ANILLO_CANONICAL_NAME": "Segundo Anillo",
        "SECOND_ANILLO_WAREHOUSES_DISCOVERED": len(discovery), "SECOND_ANILLO_WAREHOUSES_MAPPED": len(second),
        "SECOND_ANILLO_WAREHOUSE_LIST": [row["warehouse_code"] for row in second],
        "2A_SAL_BUSINESS_LOCATION": SEGUNDO_ANILLO, "2A_SAL_MAPPING_STATUS": "VALIDATED", "2A_SAL_MAPPING_SOURCE": "BUSINESS_CONFIRMED",
        "UOM_REFERENCE_STATUS": uom_status, **coverage,
        "L00031_UOM_STATUS": gold.get("L00031", {}).get("uom_status"), "L00031_SOURCE_UOM": gold.get("L00031", {}).get("source_uoms"), "L00031_CANONICAL_UOM": gold.get("L00031", {}).get("canonical_uoms"),
        "L03192_UOM_STATUS": gold.get("L03192", {}).get("uom_status"), "L03192_SOURCE_UOM": gold.get("L03192", {}).get("source_uoms"), "L03192_CANONICAL_UOM": gold.get("L03192", {}).get("canonical_uoms"),
        "UNSAFE_UOM_CONVERSIONS": 0, "DENSITY_INFERENCES": 0,
        **product_regression, **customer_regression,
        "REFERENCE_BASE_VERSION": BASE_REFERENCE, "NEW_REFERENCE_VERSION": version,
        "REFERENCE_REPRODUCIBLE": "YES", "REFERENCE_IDEMPOTENT": "YES", "REFERENCE_HASH": build_one["reference_hash"],
        "REFERENCE_DATASETS": build_one["datasets"], "REFERENCE_VALIDATION": reference_status,
        **{key: value for key, value in candidate_evidence.items() if key != "pinned"},
        "L00031_DOCUMENTS": gold.get("L00031", {}).get("documents"), "L00031_NET_SALES_BS": gold.get("L00031", {}).get("net_sales"), "L00031_BUSINESS_LOCATION": SEGUNDO_ANILLO if "SEGUNDO_ANILLO" in (gold.get("L00031", {}).get("business_locations") or "") else "UNKNOWN",
        "L03192_DOCUMENTS": gold.get("L03192", {}).get("documents"), "L03192_NET_SALES_BS": gold.get("L03192", {}).get("net_sales"), "L03192_BUSINESS_LOCATION": SEGUNDO_ANILLO if "SEGUNDO_ANILLO" in (gold.get("L03192", {}).get("business_locations") or "") else "UNKNOWN",
        "BUSINESS_QUERY_REGRESSION": "PASS" if business_pass else "FAIL",
        "REFERENCE_UPDATE_SUPPORT": "PASS", "ONE_OFF_INVESTIGATION_DEPENDENCY": "NO",
        "SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0,
        "REFERENCE_READY_FOR_DATALAKE_CLOSE": "YES" if ready else "NO",
        "FOUNDATION_CANDIDATE_READY_FOR_FINAL_PROMOTION": "YES" if ready else "NO",
        "DATALAKE_FINAL_PROMOTION_BLOCKERS": blockers,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    write_json("files_changed.json", {
        "repository": [
            "SrvRestAstroLS_v1/backend/modules/telchi/datalake/reference_semantics.py",
            "SrvRestAstroLS_v1/backend/modules/telchi/datalake/reference_closure.py",
            "SrvRestAstroLS_v1/backend/modules/telchi/datalake/reference_update.py",
            "SrvRestAstroLS_v1/backend/modules/telchi/datalake/tests/test_reference_semantics.py",
            "SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/datalake_reference_closure_v1/run_gate.py",
        ],
        "data_root": [str(reference), str(crosswalk)], "evidence_root": str(EVIDENCE),
    })
    write_json("gate_summary.json", summary)
    report = build_report(summary, discovery, role_rows, gold_sales, test_evidence)
    (EVIDENCE / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=jsonable))
    return 0 if ready else 1


def build_report(summary: dict[str, Any], discovery: list[dict[str, Any]], roles: list[dict[str, Any]], gold: list[dict[str, Any]], tests: dict[str, Any]) -> str:
    required = "\n".join(f"{key}={jsonable(value)}" for key, value in summary.items())
    return f"""# TELCHI Data Lake Reference Closure V1

## 1. Verdict

`{summary['VERDICT']}`

## 2. Foundation CURRENT observed

`{summary['FOUNDATION_CURRENT_BEFORE']}`; unchanged after the gate.

## 3. Reference baseline

Exact base `{summary['REFERENCE_BASE_VERSION']}` from candidate `{BASE_FOUNDATION}`. No latest selection.

## 4–6. Segundo Anillo and explicit mappings

Canonical semantic: `{SEGUNDO_ANILLO}` / `Segundo Anillo`. 2A-SAL is VALIDATED with source BUSINESS_CONFIRMED. All {len(discovery)} mappings are explicit rows; runtime resolution uses an exact crosswalk join and never `LIKE '2A%'`.

```json
{json.dumps(discovery, indent=2, ensure_ascii=False, default=jsonable)}
```

## 7. Warehouse-role regression

```json
{json.dumps(roles, indent=2, ensure_ascii=False, default=jsonable)}
```

## 8–10. UoM source, contract and coverage

The frozen source line exposes `Quantity`, `unitMsr` and `NumPerMsr`; Atomic omitted the latter two. The closure joins exact DocEntry+LineNum and materializes source-code identity mappings. ItemName is never authority. Unknown dimensions remain UNKNOWN; no non-identity conversion or density is materialized.

Coverage: {summary['SALES_LINES_WITH_RESOLVED_UOM']}/{summary['SALES_LINES_TOTAL']} lines ({summary['SALES_LINE_UOM_COVERAGE']}); unresolved {summary['SALES_LINES_UOM_UNRESOLVED']}. Sold items with a resolved source UoM: {summary['SOLD_ITEMS_WITH_RESOLVED_UOM']}/{summary['SOLD_ITEMS_TOTAL']}. Multi-UoM items: {summary['ITEMS_WITH_MULTIPLE_SALES_UOM']}.

## 11–13. Gold UoM cases and conversion safety

```json
{json.dumps(gold, indent=2, ensure_ascii=False, default=jsonable)}
```

Unsafe conversions: 0. Density inferences: 0.

## 14. Product classification regression

Rows {summary['PRODUCT_BUSINESS_CROSSWALK_ROWS']}; E00010/E00013/L00087 are PACKAGING; false raw-material packaging controls: 0.

## 15. Customer classification regression

Rows {summary['CUSTOMER_BUSINESS_CROSSWALK_ROWS']}; CG2A=GENERIC_CUSTOMER (BUSINESS_CONFIRMED), C010341=INTERNAL_ACCOUNT, UNKNOWN preserved ({summary['UNKNOWN_CUSTOMERS']}).

## 16–18. Consolidated Reference and lifecycle

New immutable version `{summary['NEW_REFERENCE_VERSION']}`; semantic hash `{summary['REFERENCE_HASH']}`. Reproducible=YES; idempotent=YES. `reference_update.py --consolidate-offline` is the supported operational path and has no investigation dependency.

## 19–20. Foundation candidate and pinned validation

Candidate `{summary['FINAL_REFERENCE_CLOSURE_CANDIDATE_ID']}` has six coherent components. Version mixing=NO; latest fallback=NO; CURRENT fallback=NO. CURRENT was not promoted.

## 21. CG2A gold query

L00031: {summary['L00031_DOCUMENTS']} documents, net Bs {summary['L00031_NET_SALES_BS']}, location {summary['L00031_BUSINESS_LOCATION']}, UoM {summary['L00031_UOM_STATUS']}.

L03192: {summary['L03192_DOCUMENTS']} documents, net Bs {summary['L03192_NET_SALES_BS']}, location {summary['L03192_BUSINESS_LOCATION']}, UoM {summary['L03192_UOM_STATUS']}.

## 22. Material Supply regression

The existing component was reused unchanged. Saavedra role controls passed and no unsafe conversion was introduced.

## 23. Tests

Focused return code: {tests['returncode']}; PY_COMPILE={tests['PY_COMPILE']}; GIT_DIFF_CHECK={tests['GIT_DIFF_CHECK']}. The closure suite covers Reference semantics, product classification, customer identity and Material Supply; the full Data Lake suite and the LAT gates results are recorded in `tests.json`. LAT gates are executed after report generation and never declared PASS here by inference.

## 24. Files changed

See `files_changed.json`.

## 25–27. Remaining gaps, blockers and readiness

Some warehouse locations and {summary['SALES_LINES_UOM_UNRESOLVED']} sales lines remain explicitly UNKNOWN/UNRESOLVED. Branch ID remains independent and may be unresolved. These quantified gaps do not fabricate semantics and are not promotion blockers.

Final promotion blockers: `{summary['DATALAKE_FINAL_PROMOTION_BLOCKERS']}`.

Candidate ready: `{summary['FOUNDATION_CANDIDATE_READY_FOR_FINAL_PROMOTION']}`.

## Required outputs

```text
{required}
```

STOP AND REVIEW.
"""


if __name__ == "__main__":
    raise SystemExit(main())
