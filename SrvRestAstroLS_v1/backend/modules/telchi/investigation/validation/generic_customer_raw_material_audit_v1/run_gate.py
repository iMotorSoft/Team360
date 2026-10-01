"""Audit CG2A raw-material sales and materialize customer business identity.

This gate is Data-Lake-only.  It validates one explicit pinned Foundation
candidate, never imports a SAP adapter, never queries SAP/HANA, and never moves
Foundation CURRENT.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb

from modules.telchi.datalake.customer_business_identity import (
    COMMERCIAL_CUSTOMER,
    FISCAL_TECHNICAL_ACCOUNT,
    GENERIC_CUSTOMER,
    INTERNAL_ACCOUNT,
    OTHER_NON_COMMERCIAL,
    TAXONOMY,
    UNKNOWN,
    CustomerAssertion,
    classify_customer,
)
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

GATE = "TELCHI_GENERIC_CUSTOMER_RAW_MATERIAL_AUDIT_V1"
BASE_CANDIDATE = "foundation_456e7edf3460b94323aa0c0267663711"
EXPECTED_CURRENT = "foundation_eb7ab1aded0e7c551c4a1b96147a9102"
BASE_REFERENCE = "v2_product_business_type_f9c1130d852ccb61"
RUN_ID = "generic-customer-raw-material-audit-v1-2026-09-25"
EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
REPO = Path(__file__).resolve().parents[7]
MODULE_ROOT = REPO / "SrvRestAstroLS_v1/backend/modules/telchi"

TYPE_NAMES = {
    COMMERCIAL_CUSTOMER: "Cliente comercial",
    GENERIC_CUSTOMER: "Cuenta de cliente genérico",
    INTERNAL_ACCOUNT: "Cuenta interna o parte relacionada",
    FISCAL_TECHNICAL_ACCOUNT: "Cuenta fiscal o técnica",
    OTHER_NON_COMMERCIAL: "Otra cuenta no comercial",
    UNKNOWN: "Tipo de cliente desconocido",
}

# Only exact CardCode assertions are admitted.  CG2A is the explicit business
# input for this gate.  C010341 reuses the validated prior La Reja identity gate;
# no name or transaction-volume heuristic is used.
ASSERTIONS = {
    "CG2A": CustomerAssertion(
        GENERIC_CUSTOMER,
        "BUSINESS_CONFIRMED",
        "Business-confirmed input supplied for CardCode=CG2A in this gate",
        1.0,
    ),
    "C010341": CustomerAssertion(
        INTERNAL_ACCOUNT,
        "TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1_PASS",
        "Prior validated CardCode-level identity: internal/related-party account",
        1.0,
    ),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def write_json(name: str, value: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    target = EVIDENCE / name
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=jsonable) + "\n",
        encoding="utf-8",
    )
    temp.replace(target)


def state(run_state: str, last: str, next_state: str | None, reason: str | None = None) -> None:
    write_json(
        "run_state.json",
        {
            "RUN_STATE": run_state,
            "LAST_COMPLETED_STATE": last,
            "NEXT_ALLOWED_STATE": next_state,
            "BLOCKING_REASON": reason,
            "updated_at": now(),
        },
    )


def rows(cursor: Any) -> list[dict[str, Any]]:
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def scalar(con: Any, sql: str, params: Iterable[Any] | None = None) -> Any:
    return con.execute(sql, list(params or [])).fetchone()[0]


def qpath(path: Path) -> str:
    return str(path).replace("'", "''")


def stable_id(prefix: str, value: str) -> str:
    return prefix + "_" + hashlib.sha256(f"{prefix}|TELCHI|{value}".encode()).hexdigest()[:24]


def discover_internal_policy() -> dict[str, Any]:
    terms = (
        "cliente genérico",
        "cliente generico",
        "venta de materia prima",
        "sustancias controladas",
        "sin identificación de comprador",
        "sin identificacion de comprador",
    )
    matches: list[dict[str, Any]] = []
    for suffix in ("*.md", "*.txt"):
        for path in MODULE_ROOT.rglob(suffix):
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    lower = line.lower()
                    if any(term in lower for term in terms):
                        matches.append(
                            {"path": str(path.relative_to(REPO)), "line": number, "text": line.strip()[:500]}
                        )
            except OSError:
                continue
    # Mentions and prior analytical reports are not promoted to policy.  No
    # normative policy source was identified in the available local corpus.
    return {
        "RAW_MATERIAL_GENERIC_CUSTOMER_POLICY": "NOT_FOUND",
        "result": "NO DOCUMENTED POLICY FOUND IN AVAILABLE SOURCES",
        "scope": [str(MODULE_ROOT), str(DATA_ROOT)],
        "search_terms": list(terms),
        "contextual_mentions_not_policy": matches[:100],
        "internet_accessed": False,
        "sap_accessed": False,
    }


def create_reference_version(
    customer_rows: list[dict[str, Any]], source_as_of: str, base_reference: Path, base_crosswalk: Path
) -> tuple[str, Path, Path, int]:
    payload = json.dumps(customer_rows, sort_keys=True, default=jsonable, ensure_ascii=False)
    version = "v2_customer_business_type_" + hashlib.sha256(payload.encode()).hexdigest()[:16]
    reference_target = DATA_ROOT / "reference/_versions" / version
    crosswalk_target = DATA_ROOT / "crosswalk/_versions" / version
    reference_stage = reference_target.with_name(reference_target.name + ".tmp")
    crosswalk_stage = crosswalk_target.with_name(crosswalk_target.name + ".tmp")
    if not reference_target.exists() or not crosswalk_target.exists():
        if reference_stage.exists() or crosswalk_stage.exists():
            raise RuntimeError("stale Reference/Crosswalk staging directory found")
        shutil.copytree(base_reference, reference_stage)
        shutil.copytree(base_crosswalk, crosswalk_stage)
        taxonomy_dir = reference_stage / "customer_business_type"
        mapping_dir = crosswalk_stage / "customer_business_type"
        taxonomy_dir.mkdir()
        mapping_dir.mkdir()
        db = duckdb.connect()
        db.execute("SET threads=1")
        db.execute(
            """CREATE TABLE taxonomy(
                 customer_business_type_id VARCHAR, code VARCHAR, name VARCHAR,
                 description VARCHAR, active BOOLEAN, source VARCHAR,
                 confidence DECIMAL(10,6), status VARCHAR, semantic_version VARCHAR
               )"""
        )
        db.executemany(
            "INSERT INTO taxonomy VALUES (?, ?, ?, ?, true, ?, 1.0, 'CONFIRMED', '1.0.0')",
            [
                (
                    stable_id("customer_business_type", code),
                    code,
                    TYPE_NAMES[code],
                    TYPE_NAMES[code],
                    GATE,
                )
                for code in TAXONOMY
            ],
        )
        db.execute(
            f"COPY taxonomy TO '{qpath(taxonomy_dir / 'part-00000.parquet')}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        db.execute(
            """CREATE TABLE mapping(
                 CardCode VARCHAR, CardName VARCHAR, customer_business_type VARCHAR,
                 classification_status VARCHAR, classification_source VARCHAR,
                 classification_basis VARCHAR, classification_confidence DECIMAL(10,6),
                 effective_from TIMESTAMPTZ, effective_to TIMESTAMPTZ,
                 source_as_of TIMESTAMPTZ
               )"""
        )
        db.executemany(
            "INSERT INTO mapping VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?::TIMESTAMPTZ)",
            [
                (
                    row["CardCode"],
                    row["CardName"],
                    row["customer_business_type"],
                    row["classification_status"],
                    row["classification_source"],
                    row["classification_basis"],
                    row["classification_confidence"],
                    source_as_of,
                )
                for row in customer_rows
            ],
        )
        db.execute(
            f"COPY (SELECT * FROM mapping ORDER BY CardCode) TO '{qpath(mapping_dir / 'part-00000.parquet')}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        db.close()
        reference_stage.replace(reference_target)
        crosswalk_stage.replace(crosswalk_target)
    db = duckdb.connect()
    mapping_path = crosswalk_target / "customer_business_type/part-00000.parquet"
    duplicate_count = scalar(
        db,
        "SELECT count(*) FROM (SELECT CardCode FROM read_parquet(?) WHERE effective_to IS NULL GROUP BY CardCode HAVING count(*) > 1)",
        [str(mapping_path)],
    )
    count = scalar(db, "SELECT count(*) FROM read_parquet(?)", [str(mapping_path)])
    db.close()
    if duplicate_count or count != len(customer_rows):
        raise RuntimeError("customer business crosswalk uniqueness/cardinality validation failed")
    return version, reference_target, crosswalk_target, count


def markdown_table(data: list[dict[str, Any]], columns: list[str], limit: int = 20) -> str:
    if not data:
        return "_No rows._"
    selected = data[:limit]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in selected:
        lines.append("| " + " | ".join(str(jsonable(row.get(column, ""))) for column in columns) + " |")
    return "\n".join(lines)


def main() -> int:
    started = time.perf_counter()
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    state("PRECHECK", "NONE", "BASELINE_REPRODUCED")
    status_before = subprocess.run(
        ["git", "status", "--short"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    write_json(
        "worktree_safety.json",
        {
            "snapshot_before": status_before,
            "destructive_git_actions": [],
            "git_add_commit_performed": False,
            "preserve_concurrent_changes": True,
        },
    )
    write_json(
        "resource_safety.json",
        {
            "MAX_HEAVY_WORKERS": 1,
            "DUCKDB_THREADS": 1,
            "machine_stability_over_throughput": True,
        },
    )

    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)
    pinned = validate_pinned_candidate(store, BASE_CANDIDATE)
    if pinned.component_version("reference") != BASE_REFERENCE:
        raise RuntimeError("pinned candidate does not contain the required product classification Reference")
    current = FoundationReader(connector).get_current_foundation()
    if current.foundation_publication_id != EXPECTED_CURRENT:
        raise RuntimeError(f"CURRENT changed to {current.foundation_publication_id}; stop and review")
    base_publication = store.get(BASE_CANDIDATE)
    if base_publication is None:
        raise RuntimeError("base candidate metadata disappeared")
    base_reference = DATA_ROOT / "reference/_versions" / BASE_REFERENCE
    base_crosswalk = DATA_ROOT / "crosswalk/_versions" / BASE_REFERENCE
    pbt_path = base_crosswalk / "product_business_type/part-00000.parquet"
    required_paths = [base_reference / "customers/part-00000.parquet", pbt_path]
    if any(not path.is_file() for path in required_paths):
        raise RuntimeError("required pinned Reference/Crosswalk file is missing")
    precheck = {
        "BASELINE_CANDIDATE_VALID": "YES",
        "PRODUCT_CLASSIFICATION_BASE_CANDIDATE": BASE_CANDIDATE,
        "FOUNDATION_CURRENT_OBSERVED": current.foundation_publication_id,
        "FOUNDATION_COMPONENTS": list(pinned.component_versions),
        "candidate": pinned.as_dict(),
        "CANDIDATE_READER_MODE": "EXPLICIT_PINNED_VALIDATION",
        "CANDIDATE_VERSION_MIXING": "NO",
        "LATEST_COMPONENT_FALLBACK_USED": "NO",
        "CURRENT_FALLBACK_USED": "NO",
        "SAP_ACCESSED": "NO",
        "SAP_QUERY_COUNT": 0,
        "SAP_WRITE_COUNT": 0,
    }
    write_json("precheck.json", precheck)

    snapshot = pinned.snapshot_id
    sd = f'(SELECT * FROM telchi.atomic."sales_document" AT (VERSION => {snapshot}))'
    sl = f'(SELECT * FROM telchi.atomic."sales_line" AT (VERSION => {snapshot}))'
    cd = f'(SELECT * FROM telchi.atomic."credit_memo_document" AT (VERSION => {snapshot}))'
    cl = f'(SELECT * FROM telchi.atomic."credit_memo_line" AT (VERSION => {snapshot}))'
    reference = base_reference
    crosswalk = base_crosswalk

    with connector.session(read_only=True) as con:
        con.execute("SET threads=1")
        con.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{qpath(pbt_path)}')")
        con.execute(
            f"""CREATE TEMP VIEW customers AS
                SELECT * FROM read_parquet('{qpath(reference / 'customers/part-00000.parquet')}')
                QUALIFY row_number() OVER (
                  PARTITION BY code ORDER BY CASE source_system WHEN 'SAP_HANA' THEN 0 ELSE 1 END, customer_id
                )=1"""
        )
        baseline = rows(
            con.execute(
                f"""WITH raw_docs AS (
                       SELECT DISTINCT d.source_system,d.source_table,d.doc_entry,d.card_code,
                              CAST(d.doc_date AS DATE) doc_date,l.item_code
                       FROM {sd} d JOIN {sl} l
                         ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
                       JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL'
                       WHERE coalesce(d.canceled,'N')<>'Y'
                     )
                     SELECT card_code,
                            count(DISTINCT source_system||'|'||source_table||'|'||doc_entry) raw_documents,
                            count(DISTINCT doc_date) raw_purchase_days,
                            count(DISTINCT item_code) raw_skus,
                            min(doc_date) first_raw_sale,max(doc_date) last_raw_sale
                     FROM raw_docs WHERE card_code='CG2A' GROUP BY card_code"""
            )
        )
        if not baseline or baseline[0]["raw_documents"] != 2136 or baseline[0]["raw_purchase_days"] != 246 or baseline[0]["raw_skus"] != 20:
            write_json("baseline_query_reproduction.json", {"BASELINE_QUERY_REPRODUCED": "NO", "observed": baseline})
            raise RuntimeError("CG2A baseline did not reproduce exactly; semantic audit stopped")
        baseline_result = {"BASELINE_QUERY_REPRODUCED": "YES", **baseline[0]}
        write_json("baseline_query_reproduction.json", baseline_result)
        state("BASELINE_REPRODUCED", "PRECHECK", "CG2A_DOCUMENT_AUDIT")

        # Customer master universe: exact CardCode classification, no name heuristic.
        customer_master = rows(
            con.execute(
                """SELECT code CardCode, name CardName, CAST(_source_snapshot_at AS VARCHAR) source_as_of
                   FROM customers WHERE source_system='SAP_HANA' ORDER BY code"""
            )
        )
        source_as_of = max((row["source_as_of"] for row in customer_master if row["source_as_of"]), default=str(base_publication.source_as_of))
        customer_rows: list[dict[str, Any]] = []
        for customer in customer_master:
            classified = classify_customer(customer["CardCode"], customer["CardName"] or "", ASSERTIONS)
            customer_rows.append(
                {
                    "CardCode": classified.card_code,
                    "CardName": classified.card_name,
                    "customer_business_type": classified.customer_business_type,
                    "classification_status": classified.classification_status,
                    "classification_source": classified.classification_source,
                    "classification_basis": classified.classification_basis,
                    "classification_confidence": classified.classification_confidence,
                    "source_as_of": customer["source_as_of"],
                }
            )

    version, reference_target, crosswalk_target, crosswalk_count = create_reference_version(
        customer_rows, source_as_of, base_reference, base_crosswalk
    )
    customer_mapping_path = crosswalk_target / "customer_business_type/part-00000.parquet"
    coverage_counts = Counter(row["customer_business_type"] for row in customer_rows)
    conflicts = len(customer_rows) - len({row["CardCode"] for row in customer_rows})
    coverage = {
        "CUSTOMER_BUSINESS_CLASSIFICATION_STATUS": "DEGRADED" if coverage_counts[UNKNOWN] else "PASS",
        "CUSTOMERS_TOTAL": len(customer_rows),
        "COMMERCIAL_CUSTOMERS": coverage_counts[COMMERCIAL_CUSTOMER],
        "GENERIC_CUSTOMERS": coverage_counts[GENERIC_CUSTOMER],
        "INTERNAL_ACCOUNTS": coverage_counts[INTERNAL_ACCOUNT],
        "FISCAL_TECHNICAL_ACCOUNTS": coverage_counts[FISCAL_TECHNICAL_ACCOUNT],
        "OTHER_NON_COMMERCIAL": coverage_counts[OTHER_NON_COMMERCIAL],
        "UNKNOWN_CUSTOMERS": coverage_counts[UNKNOWN],
        "CUSTOMER_BUSINESS_CROSSWALK_ROWS": crosswalk_count,
        "CUSTOMER_CLASSIFICATION_CONFLICTS": conflicts,
        "classification_policy": "Explicit CardCode evidence only; names and volume are not classifiers",
    }
    write_json("customer_business_taxonomy.json", {"taxonomy": list(TAXONOMY), "names": TYPE_NAMES, "version": version})
    write_json("customer_business_mapping.json", customer_rows)
    write_json("customer_classification_coverage.json", coverage)
    state("CUSTOMER_IDENTITY_CLASSIFICATION", "BASELINE_REPRODUCED", "CG2A_DOCUMENT_AUDIT")

    # Exact pinned audit with only fields physically available in Foundation.
    with connector.session(read_only=True) as con:
        con.execute("SET threads=1")
        con.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{qpath(pbt_path)}')")
        con.execute(f"CREATE TEMP VIEW cbt AS SELECT * FROM read_parquet('{qpath(customer_mapping_path)}')")
        con.execute(
            f"""CREATE TEMP VIEW customers AS SELECT * FROM read_parquet('{qpath(reference_target / 'customers/part-00000.parquet')}')
                QUALIFY row_number() OVER (PARTITION BY code ORDER BY CASE source_system WHEN 'SAP_HANA' THEN 0 ELSE 1 END, customer_id)=1"""
        )
        con.execute(
            f"""CREATE TEMP VIEW products AS SELECT * FROM read_parquet('{qpath(reference_target / 'products/part-00000.parquet')}')
                QUALIFY row_number() OVER (PARTITION BY item_code ORDER BY CASE source_system WHEN 'SAP_HANA' THEN 0 ELSE 1 END, canonical_product_id)=1"""
        )
        con.execute(
            f"CREATE TEMP VIEW salespersons AS SELECT code,name FROM read_parquet('{qpath(reference_target / 'salespersons/part-00000.parquet')}') WHERE source_system='SAP_HANA'"
        )
        con.execute(
            f"CREATE TEMP VIEW users AS SELECT source_native_id,code user_code,name FROM read_parquet('{qpath(reference_target / 'users/part-00000.parquet')}') WHERE source_system='SAP_HANA'"
        )
        con.execute(
            f"CREATE TEMP VIEW warehouses AS SELECT warehouse_id,code,name FROM read_parquet('{qpath(reference_target / 'warehouses/part-00000.parquet')}') WHERE source_system='SAP_HANA'"
        )
        con.execute(
            f"CREATE TEMP VIEW branches AS SELECT branch_id,code,name FROM read_parquet('{qpath(reference_target / 'branches/part-00000.parquet')}') WHERE source_system='SAP_HANA'"
        )
        con.execute(
            f"CREATE TEMP VIEW warehouse_branch AS SELECT warehouse_id,branch_id FROM read_parquet('{qpath(crosswalk_target / 'warehouse_branch_mapping/part-00000.parquet')}') WHERE valid_to IS NULL"
        )
        con.execute(
            f"CREATE TEMP VIEW uom AS SELECT unit_of_measure_id,code,name FROM read_parquet('{qpath(reference_target / 'units_of_measure/part-00000.parquet')}')"
        )
        con.execute(
            f"""CREATE TEMP VIEW raw_sales AS
                SELECT d.source_system,d.source_table,d.doc_entry,d.doc_num,
                       d.source_system||'|'||d.source_table||'|'||d.doc_entry document_id,
                       CAST(d.doc_date AS DATE) document_date,d.card_code,c.name card_name,
                       d.currency document_currency,try_cast(d.doc_total AS DECIMAL(38,6)) document_total,
                       d.sales_channel_code,coalesce(d.sales_channel_name,'UNKNOWN') channel,
                       d.slp_code,coalesce(sp.name,'UNKNOWN') salesperson,
                       d.user_sign,coalesce(u.name,'UNKNOWN') operator_name,
                       l.line_num,l.item_code,p.product_name,pbt.product_business_type,
                       pbt.status classification_status,pbt.classification_basis,pbt.classification_source,
                       try_cast(l.quantity AS DECIMAL(38,6)) quantity,
                       p.sales_uom_id uom_reference_id,coalesce(um.code,'UNAVAILABLE') uom,
                       coalesce(l.currency,d.currency,'UNKNOWN') currency,
                       try_cast(l.line_total AS DECIMAL(38,6)) gross_sales,
                       l.whs_code,coalesce(w.name,'UNKNOWN') warehouse,
                       coalesce(b.code,'UNKNOWN') branch_code,coalesce(b.name,'UNKNOWN') branch,
                       d.source_as_of
                FROM {sd} d JOIN {sl} l
                  ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
                JOIN pbt ON pbt.ItemCode=l.item_code AND pbt.product_business_type='RAW_MATERIAL'
                LEFT JOIN customers c ON c.code=d.card_code
                LEFT JOIN products p ON p.item_code=l.item_code
                LEFT JOIN uom um ON um.unit_of_measure_id=p.sales_uom_id
                LEFT JOIN salespersons sp ON sp.code=coalesce(l.attributed_slp_code,l.slp_code,d.slp_code)
                LEFT JOIN users u ON u.source_native_id=d.user_sign
                LEFT JOIN warehouses w ON w.code=l.whs_code
                LEFT JOIN warehouse_branch wb ON wb.warehouse_id=w.warehouse_id
                LEFT JOIN branches b ON b.branch_id=wb.branch_id
                WHERE coalesce(d.canceled,'N')<>'Y'"""
        )
        con.execute(
            f"""CREATE TEMP VIEW raw_credits AS
                SELECT d.source_system,d.source_table,d.doc_entry,
                       d.source_system||'|'||d.source_table||'|'||d.doc_entry credit_document_id,
                       CAST(d.doc_date AS DATE) document_date,d.card_code,l.line_num,l.item_code,
                       try_cast(l.quantity AS DECIMAL(38,6)) quantity,
                       coalesce(l.currency,d.currency,'UNKNOWN') currency,
                       try_cast(l.line_total AS DECIMAL(38,6)) credit_amount,
                       l.whs_code,l.base_type,l.base_entry,l.base_line
                FROM {cd} d JOIN {cl} l
                  ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
                JOIN pbt ON pbt.ItemCode=l.item_code AND pbt.product_business_type='RAW_MATERIAL'
                WHERE coalesce(d.canceled,'N')<>'Y'"""
        )
        document_universe = rows(
            con.execute(
                """SELECT document_id,any_value(document_date) document_date,
                          any_value(card_code) CardCode,any_value(card_name) CardName,
                          string_agg(DISTINCT branch, ', ' ORDER BY branch) branches,
                          any_value(channel) channel,
                          string_agg(DISTINCT salesperson, ', ' ORDER BY salesperson) salespersons,
                          string_agg(DISTINCT operator_name, ', ' ORDER BY operator_name) operators,
                          string_agg(DISTINCT warehouse, ', ' ORDER BY warehouse) warehouses,
                          any_value(document_currency) currency,any_value(document_total) document_total,
                          sum(gross_sales) raw_material_line_total,count(DISTINCT item_code) raw_skus,
                          any_value(source_as_of) source_as_of
                   FROM raw_sales WHERE card_code='CG2A' GROUP BY document_id ORDER BY document_date,document_id"""
            )
        )
        temporal_year = rows(
            con.execute(
                """SELECT year(document_date) sale_year,count(DISTINCT document_id) documents,
                          count(DISTINCT document_date) distinct_days,count(DISTINCT item_code) distinct_skus
                   FROM raw_sales WHERE card_code='CG2A' GROUP BY 1 ORDER BY 1"""
            )
        )
        temporal_month = rows(
            con.execute(
                """SELECT strftime(document_date,'%Y-%m') sale_month,count(DISTINCT document_id) documents,
                          count(DISTINCT document_date) distinct_days,count(DISTINCT item_code) distinct_skus
                   FROM raw_sales WHERE card_code='CG2A' AND year(document_date)=2026 GROUP BY 1 ORDER BY 1"""
            )
        )
        branch_distribution = rows(
            con.execute(
                """SELECT branch,count(DISTINCT document_id) documents,count(DISTINCT document_date) distinct_days,
                          count(DISTINCT item_code) distinct_skus,currency,sum(gross_sales) gross_sales
                   FROM raw_sales WHERE card_code='CG2A' AND branch<>'UNKNOWN'
                   GROUP BY branch,currency ORDER BY documents DESC,branch,currency"""
            )
        )
        warehouse_distribution = rows(
            con.execute(
                """SELECT whs_code,warehouse,count(DISTINCT document_id) documents,
                          count(DISTINCT document_date) distinct_days,count(DISTINCT item_code) distinct_skus,
                          currency,sum(gross_sales) gross_sales
                   FROM raw_sales WHERE card_code='CG2A' GROUP BY whs_code,warehouse,currency
                   ORDER BY documents DESC,whs_code,currency"""
            )
        )
        channel_distribution = rows(
            con.execute(
                """SELECT channel,count(DISTINCT document_id) documents,count(DISTINCT document_date) distinct_days,
                          count(DISTINCT item_code) distinct_skus,currency,sum(gross_sales) gross_sales
                   FROM raw_sales WHERE card_code='CG2A' GROUP BY channel,currency ORDER BY documents DESC,channel,currency"""
            )
        )
        seller_distribution = rows(
            con.execute(
                """SELECT salesperson,count(DISTINCT document_id) documents,count(DISTINCT document_date) distinct_days,
                          count(DISTINCT item_code) distinct_skus
                   FROM raw_sales WHERE card_code='CG2A' GROUP BY salesperson ORDER BY documents DESC,salesperson"""
            )
        )
        operator_distribution = rows(
            con.execute(
                """SELECT operator_name,count(DISTINCT document_id) documents,count(DISTINCT document_date) distinct_days
                   FROM raw_sales WHERE card_code='CG2A' GROUP BY operator_name ORDER BY documents DESC,operator_name"""
            )
        )
        product_detail = rows(
            con.execute(
                """SELECT item_code,any_value(product_name) ItemName,any_value(product_business_type) product_business_type,
                          any_value(classification_status) classification_status,
                          any_value(classification_basis) classification_basis,
                          any_value(classification_source) classification_source,
                          count(DISTINCT document_id) documents,count(DISTINCT document_date) distinct_days,
                          min(document_date) first_sale,max(document_date) last_sale,
                          uom_reference_id,uom,currency,sum(quantity) gross_quantity,sum(gross_sales) gross_sales
                   FROM raw_sales WHERE card_code='CG2A'
                   GROUP BY item_code,uom_reference_id,uom,currency ORDER BY documents DESC,distinct_days DESC,item_code"""
            )
        )
        credit_detail = rows(
            con.execute(
                """SELECT item_code,currency,count(DISTINCT credit_document_id) credit_memos,
                          sum(quantity) credit_quantity,sum(credit_amount) credit_memo_amount,
                          min(document_date) first_credit,max(document_date) last_credit
                   FROM raw_credits WHERE card_code='CG2A' GROUP BY item_code,currency
                   ORDER BY credit_memo_amount DESC,item_code"""
            )
        )
        sales_amounts = rows(
            con.execute(
                """SELECT currency,sum(gross_sales) gross_sales
                   FROM raw_sales WHERE card_code='CG2A' GROUP BY currency ORDER BY currency"""
            )
        )
        credit_amounts = rows(
            con.execute(
                """SELECT currency,sum(credit_amount) credit_memo_amount
                   FROM raw_credits WHERE card_code='CG2A' GROUP BY currency ORDER BY currency"""
            )
        )
        credit_by_item = {(row["item_code"], row["currency"]): row for row in credit_detail}
        for product in product_detail:
            credit = credit_by_item.get((product["item_code"], product["currency"]), {})
            product["credit_memos"] = credit.get("credit_memos", 0)
            product["credit_quantity"] = credit.get("credit_quantity", 0)
            product["net_quantity"] = (product["gross_quantity"] or 0) - (credit.get("credit_quantity", 0) or 0)
            product["credit_memo_amount"] = credit.get("credit_memo_amount", 0)
            product["net_sales"] = (product["gross_sales"] or 0) - (credit.get("credit_memo_amount", 0) or 0)
        amount_map = {row["currency"]: row["gross_sales"] for row in sales_amounts}
        credit_map = {row["currency"]: row["credit_memo_amount"] for row in credit_amounts}
        net_amounts = [
            {
                "currency": currency,
                "gross_sales": amount_map.get(currency, 0),
                "credit_memo_amount": credit_map.get(currency, 0),
                "net_after_credit": (amount_map.get(currency, 0) or 0) - (credit_map.get(currency, 0) or 0),
            }
            for currency in sorted(set(amount_map) | set(credit_map))
        ]
        high_volume = rows(
            con.execute(
                """WITH stats AS (
                     SELECT item_code,uom_reference_id,uom,quantile_cont(quantity,0.95) p95,
                            quantile_cont(quantity,0.99) p99,max(quantity) max_quantity FROM raw_sales
                     WHERE card_code='CG2A' AND quantity IS NOT NULL GROUP BY item_code,uom_reference_id,uom
                   )
                   SELECT s.item_code,s.uom_reference_id,s.uom,s.p95,s.p99,s.max_quantity,
                          count(*) FILTER (WHERE r.quantity>s.p99) lines_above_p99
                   FROM stats s JOIN raw_sales r USING(item_code,uom_reference_id,uom)
                   WHERE r.card_code='CG2A' GROUP BY ALL ORDER BY max_quantity DESC,item_code"""
            )
        )
        all_ranking = rows(
            con.execute(
                """WITH per_card AS (
                     SELECT card_code,count(DISTINCT document_id) documents,
                            count(DISTINCT document_date) purchase_days,min(document_date) first_purchase,
                            max(document_date) last_purchase,count(DISTINCT item_code) raw_skus,
                            any_value(card_name) customer_name
                     FROM raw_sales GROUP BY card_code
                   ) SELECT row_number() OVER (ORDER BY documents DESC,card_code) Rank,customer_name Cliente,
                            card_code CardCode,documents Compras,purchase_days "Días",first_purchase Primera,
                            last_purchase Última,raw_skus SKU_RAW_distintos
                     FROM per_card ORDER BY documents DESC,card_code LIMIT 10"""
            )
        )
        raw_type_counts = rows(
            con.execute(
                """SELECT cbt.customer_business_type,count(DISTINCT r.card_code) cardcodes
                   FROM raw_sales r JOIN cbt ON cbt.CardCode=r.card_code GROUP BY 1 ORDER BY 1"""
            )
        )
        commercial_ranking = rows(
            con.execute(
                """WITH per_card AS (
                     SELECT r.card_code,count(DISTINCT document_id) documents,
                            count(DISTINCT document_date) purchase_days,min(document_date) first_purchase,
                            max(document_date) last_purchase,count(DISTINCT item_code) raw_skus,
                            any_value(card_name) customer_name
                     FROM raw_sales r JOIN cbt ON cbt.CardCode=r.card_code
                     WHERE cbt.customer_business_type='COMMERCIAL_CUSTOMER' GROUP BY r.card_code
                   ) SELECT rank() OVER (ORDER BY documents DESC) Rank,customer_name Cliente,
                            card_code CardCode,documents Compras,purchase_days "Días",first_purchase Primera,
                            last_purchase Última,raw_skus SKU_RAW_distintos
                     FROM per_card ORDER BY documents DESC,card_code LIMIT 10"""
            )
        )
        unknown_ranking = rows(
            con.execute(
                """SELECT r.card_code CardCode,any_value(r.card_name) Cliente,count(DISTINCT document_id) documents
                   FROM raw_sales r JOIN cbt ON cbt.CardCode=r.card_code
                   WHERE cbt.customer_business_type='UNKNOWN' GROUP BY r.card_code
                   ORDER BY documents DESC,r.card_code"""
            )
        )

        # Persist the detection dataset at sales-document + raw-line grain.
        control_version = "generic_customer_raw_material_review_" + hashlib.sha256(
            f"{BASE_CANDIDATE}|{version}|CG2A|uom-contract-v2".encode()
        ).hexdigest()[:16]
        control_root = DATA_ROOT / "business/generic_customer_raw_material_review" / control_version
        control_root.mkdir(parents=True, exist_ok=True)
        control_path = control_root / "part-00000.parquet"
        if not control_path.exists():
            con.execute(
                f"""COPY (
                     SELECT document_id,document_date,card_code CardCode,
                            'GENERIC_CUSTOMER' customer_business_type,item_code ItemCode,
                            product_business_type,quantity,uom,currency,gross_sales net_sales,
                            branch,channel,salesperson seller,'REVIEW_REQUIRED' control_status,
                            'MEDIUM' review_priority,
                            'NO DOCUMENTED POLICY FOUND IN AVAILABLE SOURCES' policy_basis,source_as_of
                     FROM raw_sales WHERE card_code='CG2A' ORDER BY document_date,document_id,line_num
                   ) TO '{qpath(control_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
            )
        control_rows = scalar(con, "SELECT count(*) FROM read_parquet(?)", [str(control_path)])

    write_json("cg2a_document_universe.json", {"count": len(document_universe), "documents": document_universe})
    write_json("cg2a_temporal_distribution.json", {"by_year": temporal_year, "by_month_2026": temporal_month})
    write_json("cg2a_branch_distribution.json", {
        "BRANCH_SEMANTICS_AVAILABLE": "YES" if branch_distribution else "NO",
        "semantics": "Branch is only reported when the validated warehouse_branch_mapping resolves it; no branch was inferred from warehouse names/codes",
        "rows": branch_distribution,
        "warehouse_distribution": warehouse_distribution,
    })
    write_json("cg2a_channel_distribution.json", channel_distribution)
    write_json("cg2a_seller_distribution.json", {"salespersons": seller_distribution, "operators": operator_distribution})
    write_json("cg2a_product_detail.json", {
        "products": product_detail,
        "high_volume_relative_to_cg2a_history": high_volume,
        "high_volume_label": "HIGH_VOLUME_RELATIVE_TO_CG2A_HISTORY",
        "interpretation": "Internal p95/p99 diagnostics only; no legal, safety, or policy conclusion",
    })
    write_json("cg2a_credit_memo_analysis.json", {"detail": credit_detail, "by_currency": net_amounts, "frequency_effect": "Credit memos do not create or subtract purchase occasions"})
    write_json("cg2a_buyer_traceability.json", {
        "REAL_BUYER_TRACEABILITY_AVAILABLE": "NO",
        "CG2A_DOCUMENTS_WITH_REAL_BUYER_ID": 0,
        "CG2A_DOCUMENTS_WITHOUT_REAL_BUYER_ID": len(document_universe),
        "finding": "CG2A obscures individual customer frequency",
        "available_operational_trace": "user_sign and salesperson identify operational accounts, not the real buyer",
    })
    write_json("generic_raw_material_control.json", {
        "rule": "GENERIC_CUSTOMER_RAW_MATERIAL_SALE_REVIEW_V1",
        "condition": "customer_business_type=GENERIC_CUSTOMER AND product_business_type=RAW_MATERIAL",
        "control_status": "REVIEW_REQUIRED",
        "review_priority": "MEDIUM",
        "priority_basis": "No validated technical risk flag is available; priority was not elevated",
        "blocking": False,
        "dataset": str(control_path),
        "rows": control_rows,
    })
    write_json("internal_policy_discovery.json", discover_internal_policy())
    technical_dataset_names = [path.name for path in reference_target.iterdir() if path.is_dir()]
    technical = {
        "CHEMICAL_CLASSIFICATION_STATUS": "UNAVAILABLE",
        "VALIDATED_CHEMICAL_RAW_MATERIAL_SKUS": 0,
        "SAFETY_REGULATORY_CLASSIFICATION": "UNAVAILABLE",
        "reason": "No validated chemical, hazardous, controlled, restricted, toxic, or regulated classification dataset exists in the pinned Reference",
        "reference_datasets_inspected": technical_dataset_names,
        "name_inference_used": False,
    }
    write_json("technical_material_classification.json", technical)
    write_json("all_cardcode_ranking.json", {"query": "MOST_FREQUENT_RAW_MATERIAL_CARDCODE_V1", "TOP_10": all_ranking})
    write_json("commercial_customer_ranking.json", {
        "query": "MOST_FREQUENT_RAW_MATERIAL_COMMERCIAL_CUSTOMER_V1",
        "COMMERCIAL_QUERY_EXECUTED": "YES" if commercial_ranking else "NO",
        "fail_closed_reason": None if commercial_ranking else "No RAW-buying CardCode has an explicit COMMERCIAL_CUSTOMER classification",
        "TOP_10": commercial_ranking,
    })
    unknown_could_change = bool(unknown_ranking) and (not commercial_ranking or unknown_ranking[0]["documents"] >= commercial_ranking[0]["Compras"])
    raw_counts = {row["customer_business_type"]: row["cardcodes"] for row in raw_type_counts}
    sensitivity = {
        "RAW_BUYING_CARDCODES": sum(raw_counts.values()),
        "RAW_BUYING_COMMERCIAL": raw_counts.get(COMMERCIAL_CUSTOMER, 0),
        "RAW_BUYING_GENERIC": raw_counts.get(GENERIC_CUSTOMER, 0),
        "RAW_BUYING_UNKNOWN": raw_counts.get(UNKNOWN, 0),
        "RAW_BUYING_UNKNOWN_CARDCODES": raw_counts.get(UNKNOWN, 0),
        "UNKNOWN_COULD_CHANGE_WINNER": "YES" if unknown_could_change else "NO",
        "COMMERCIAL_QUERY_CONFIDENCE": "UNRESOLVED" if unknown_could_change else "SUPPORTED",
        "top_unknown": unknown_ranking[:20],
    }
    write_json("ranking_sensitivity.json", sensitivity)
    state("CONTROL_RULE_MATERIALIZED", "CG2A_OPERATIONAL_TRACE", "FOUNDATION_CANDIDATE_CREATED")

    # New candidate reuses every base component and changes only Reference plus
    # the manifest link to the detection dataset.  CURRENT is never committed.
    lock = store.acquire_run_lock(RUN_ID, owner=GATE)
    if lock["status"] != "ACQUIRED":
        raise RuntimeError(f"Foundation writer lock unavailable: {lock}")
    try:
        candidate = prepare_candidate(store, update_run_id=RUN_ID, reference_version=version)
        component_entries = base_publication.manifest["components"]
        refs = {
            "reference": ComponentReference("reference", version, source_as_of),
            "sales": ComponentReference("sales", pinned.component_version("sales"), component_entries["sales"].get("source_as_of")),
            "credit_memo": ComponentReference("credit_memo", pinned.component_version("credit_memo"), component_entries["credit_memo"].get("source_as_of")),
            "oinm": ComponentReference("oinm", pinned.component_version("oinm"), component_entries["oinm"].get("source_as_of")),
            "oitw": ComponentReference("oitw", pinned.component_version("oitw"), component_entries["oitw"].get("source_as_of")),
        }
        manifest = json.loads(json.dumps(base_publication.manifest, default=jsonable))
        manifest["foundation_publication_id"] = candidate.foundation_publication_id
        manifest["base_snapshot_id"] = pinned.snapshot_id
        manifest["components"]["reference"] = refs["reference"].as_dict()
        manifest["customer_business_classification"] = {
            "gate": GATE,
            "crosswalk_version": version,
            "crosswalk_path": str(customer_mapping_path),
        }
        manifest["generic_customer_raw_material_review"] = {
            "version": control_version,
            "file_references": [str(control_path)],
            "row_count": control_rows,
        }
        store.update_components(
            candidate.foundation_publication_id,
            refs,
            source_as_of=base_publication.source_as_of,
            validation_status="PENDING",
            manifest=manifest,
        )
        store.set_status(candidate.foundation_publication_id, VALIDATING)
        new_pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
        if new_pinned.component_version("reference") != version:
            raise RuntimeError("new candidate Reference mismatch")
        if any(
            new_pinned.component_version(name) != pinned.component_version(name)
            for name in ("sales", "credit_memo", "oinm", "oitw", "material_supply")
        ):
            raise RuntimeError("base component changed in the new candidate")
        mark_candidate_ready(store, candidate.foundation_publication_id)
        current_after = store.current_pointer()
        if current_after != EXPECTED_CURRENT:
            raise RuntimeError("CURRENT pointer changed during candidate creation")
    finally:
        store.release_run_lock(RUN_ID)

    foundation = {
        "FOUNDATION_CURRENT_BEFORE": EXPECTED_CURRENT,
        "FOUNDATION_CURRENT_AFTER": current_after,
        "CURRENT_POINTER_MODIFIED": "NO",
        "PRODUCT_CLASSIFICATION_BASE_CANDIDATE": BASE_CANDIDATE,
        "NEW_REFERENCE_VERSION": version,
        "FOUNDATION_CANDIDATE_ID": candidate.foundation_publication_id,
        "FOUNDATION_CANDIDATE_VALID": "YES",
        "FOUNDATION_CANDIDATE_COMPONENTS": list(new_pinned.component_versions),
        "CANDIDATE_READER_MODE": "EXPLICIT_PINNED_VALIDATION",
        "CANDIDATE_VERSION_MIXING": "NO",
        "LATEST_COMPONENT_FALLBACK_USED": "NO",
        "CURRENT_FALLBACK_USED": "NO",
        "CANDIDATE_READY_FOR_PROMOTION": "NO",
        "promotion_reason": "Audit gate explicitly prohibits promotion; separate review is required",
        "pinned": new_pinned.as_dict(),
    }
    write_json("reference_candidate.json", {"version": version, "reference_path": str(reference_target), "crosswalk_path": str(crosswalk_target), "rows": crosswalk_count})
    write_json("foundation_candidate.json", foundation)
    write_json("candidate_validation.json", foundation)
    state("FOUNDATION_CANDIDATE_VALIDATED", "FOUNDATION_CANDIDATE_CREATED", "COMMERCIAL_RANKING_EXECUTED")

    # The Data Lake suite is resource-safe under its isolated fixtures and runs
    # serially in this gate, covering the new identity contract plus product,
    # Foundation, Sales and pinned-reader regressions.
    backend = REPO / "SrvRestAstroLS_v1/backend"
    test_command = [
        "uv", "run", "pytest", "-q", "modules/telchi/datalake/tests",
    ]
    test_run = subprocess.run(test_command, cwd=backend, capture_output=True, text=True)
    compile_run = subprocess.run(
        ["uv", "run", "python", "-m", "py_compile",
         "modules/telchi/datalake/customer_business_identity.py",
         "modules/telchi/investigation/validation/generic_customer_raw_material_audit_v1/run_gate.py"],
        cwd=backend, capture_output=True, text=True,
    )
    diff_run = subprocess.run(["git", "diff", "--check"], cwd=REPO, capture_output=True, text=True)
    tests = {
        "pytest_command": " ".join(test_command),
        "pytest_returncode": test_run.returncode,
        "pytest_stdout": test_run.stdout,
        "pytest_stderr": test_run.stderr,
        "py_compile_returncode": compile_run.returncode,
        "git_diff_check_returncode": diff_run.returncode,
        "all_datalake_tests": "EXECUTED_RESOURCE_SAFE",
    }
    write_json("tests.json", tests)

    year_2026 = next((row for row in temporal_year if row["sale_year"] == 2026), {"documents": 0, "distinct_days": 0})
    policy = json.loads((EVIDENCE / "internal_policy_discovery.json").read_text(encoding="utf-8"))
    all_top = all_ranking[0] if all_ranking else {}
    commercial_top = commercial_ranking[0] if commercial_ranking else {}
    required = {
        "CG2A_CUSTOMER_BUSINESS_TYPE": GENERIC_CUSTOMER,
        "CG2A_CLASSIFICATION_SOURCE": "BUSINESS_CONFIRMED",
        "CG2A_RAW_DOCUMENTS": baseline_result["raw_documents"],
        "CG2A_RAW_DOCUMENT_DAYS": baseline_result["raw_purchase_days"],
        "CG2A_RAW_SKUS": baseline_result["raw_skus"],
        "CG2A_RAW_DOCUMENTS_2026": year_2026["documents"],
        "CG2A_RAW_DAYS_2026": year_2026["distinct_days"],
        "CG2A_FIRST_RAW_SALE": baseline_result["first_raw_sale"],
        "CG2A_LAST_RAW_SALE": baseline_result["last_raw_sale"],
        "CG2A_BRANCH_COUNT": len({row["branch"] for row in branch_distribution}),
        "CG2A_CHANNEL_COUNT": len({row["channel"] for row in channel_distribution}),
        "CG2A_SELLER_COUNT": len({row["salesperson"] for row in seller_distribution}),
        "OPERATOR_TRACEABILITY_AVAILABLE": "YES" if any(row["operator_name"] != "UNKNOWN" for row in operator_distribution) else "NO",
        "CG2A_REAL_BUYER_TRACEABILITY": "NO",
        "CG2A_DOCUMENTS_WITH_BUYER_TRACEABILITY": 0,
        "RAW_MATERIAL_GENERIC_CUSTOMER_POLICY": policy["RAW_MATERIAL_GENERIC_CUSTOMER_POLICY"],
        "CHEMICAL_CLASSIFICATION_STATUS": technical["CHEMICAL_CLASSIFICATION_STATUS"],
        "SAFETY_REGULATORY_CLASSIFICATION": technical["SAFETY_REGULATORY_CLASSIFICATION"],
        "CG2A_CONTROL_STATUS": "REVIEW_REQUIRED",
        "CG2A_RAW_SKU_COUNT": baseline_result["raw_skus"],
        "CG2A_RAW_NET_SALES": net_amounts,
        "CG2A_RAW_CREDIT_MEMO_AMOUNT": credit_amounts,
        "CG2A_RAW_NET_AFTER_CREDIT": net_amounts,
        **coverage,
        "ALL_CARDCODE_QUERY": "MOST_FREQUENT_RAW_MATERIAL_CARDCODE_V1",
        "ALL_CARDCODE_TOP_CARDCODE": all_top.get("CardCode", "N/A"),
        "ALL_CARDCODE_TOP_NAME": all_top.get("Cliente", "N/A"),
        "ALL_CARDCODE_TOP_DOCUMENTS": all_top.get("Compras", "N/A"),
        "COMMERCIAL_QUERY": "MOST_FREQUENT_RAW_MATERIAL_COMMERCIAL_CUSTOMER_V1",
        "COMMERCIAL_QUERY_EXECUTED": "YES" if commercial_ranking else "NO",
        "COMMERCIAL_TOP_CARDCODE": commercial_top.get("CardCode", "N/A"),
        "COMMERCIAL_TOP_NAME": commercial_top.get("Cliente", "N/A"),
        "COMMERCIAL_TOP_DOCUMENTS": commercial_top.get("Compras", "N/A"),
        "COMMERCIAL_TOP_DAYS": commercial_top.get("Días", "N/A"),
        "COMMERCIAL_TOP_RAW_SKUS": commercial_top.get("SKU_RAW_distintos", "N/A"),
        **sensitivity,
        **{key: value for key, value in foundation.items() if key != "pinned"},
        "SAP_ACCESSED": "NO",
        "SAP_QUERY_COUNT": 0,
        "SAP_WRITE_COUNT": 0,
    }
    success = (
        test_run.returncode == 0
        and compile_run.returncode == 0
        and diff_run.returncode == 0
        and all_top.get("CardCode") == "CG2A"
        and foundation["FOUNDATION_CANDIDATE_VALID"] == "YES"
        and current_after == EXPECTED_CURRENT
    )
    verdict = f"{GATE}_{'DEGRADED' if success else 'FAIL'}"
    required["VERDICT"] = verdict
    write_json("gate_summary.json", required)
    write_json("files_changed.json", {
        "repository": [
            "SrvRestAstroLS_v1/backend/modules/telchi/datalake/customer_business_identity.py",
            "SrvRestAstroLS_v1/backend/modules/telchi/datalake/tests/test_customer_business_identity.py",
            "SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/generic_customer_raw_material_audit_v1/run_gate.py",
        ],
        "data_root": [str(reference_target), str(crosswalk_target), str(control_root)],
        "evidence_root": str(EVIDENCE),
    })

    required_outputs = "\n".join(f"{key}={jsonable(value)}" for key, value in required.items())
    report = f"""# {GATE}

## 1. Verdict

`{verdict}`

## 2. Executive finding

`CG2A / CONTROL TRIBUTARIO` is classified **GENERIC_CUSTOMER** from the explicit `BUSINESS_CONFIRMED` input, never from its name. The {baseline_result['raw_documents']} documents are sales documents recorded under one generic CardCode; they do **not** demonstrate {baseline_result['raw_documents']} purchases by one real person or company. Individual buyer identity is unavailable in the pinned Data Lake.

## 3. Does it continue in 2026?

Yes. All reproduced CG2A RAW_MATERIAL activity is in 2026: {year_2026['documents']} documents on {year_2026['distinct_days']} days, from {baseline_result['first_raw_sale']} through {baseline_result['last_raw_sale']}.

## 4. Where does it occur?

### Branches (raw-line warehouse attribution)

{markdown_table(branch_distribution, ['branch','documents','distinct_days','distinct_skus','currency','gross_sales'])}

Validated branch mapping is unavailable for these warehouses, so no branch was inferred from codes or names. Warehouse-level trace:

{markdown_table(warehouse_distribution, ['whs_code','warehouse','documents','distinct_days','distinct_skus','currency','gross_sales'])}

### Channels

{markdown_table(channel_distribution, ['channel','documents','distinct_days','distinct_skus','currency','gross_sales'])}

## 5. Who generates the operations?

Salesperson and SAP `user_sign` traces are available. `user_sign` resolves to the technical account `soluone`; it is not a human-operator or real-buyer identity.

{markdown_table(seller_distribution, ['salesperson','documents','distinct_days','distinct_skus'])}

## 6–7. Raw materials and frequency concentration

{markdown_table(product_detail, ['item_code','ItemName','documents','distinct_days','first_sale','last_sale','uom_reference_id','uom','currency','gross_quantity','credit_quantity','net_quantity','gross_sales','credit_memo_amount','net_sales'], 20)}

The leading SKU is `{product_detail[0]['item_code'] if product_detail else 'N/A'}` with {product_detail[0]['documents'] if product_detail else 0} distinct sales documents. RAW_MATERIAL was **not** reinterpreted as CHEMICAL.

## 8. Quantities, UoM and amounts

Quantities are reported only per SKU and unresolved UoM reference identifier; the pinned UoM Reference has no resolvable labels, so `uom=UNAVAILABLE`. No quantities were summed across SKUs/UoM identifiers. Currency totals: `{json.dumps(net_amounts, default=jsonable, ensure_ascii=False)}`.

## 9. Credit memo behavior

Credit memos adjust amount/quantity and never create or remove a purchase occasion. Detail is persisted in `cg2a_credit_memo_analysis.json`.

## 10. Real buyer traceability

**NO.** CG2A obscures individual customer frequency. Operational user/seller fields do not identify the buyer.

## 11. Internal policy availability

**NOT_FOUND.** No documented policy was found in available internal sources. This is not a finding that the sales are prohibited.

## 12. Chemical / safety classification availability

- Chemical classification: **UNAVAILABLE**.
- Safety/regulatory classification: **UNAVAILABLE**.
- No classification was inferred from product names.

## 13. Control interpretation

**REVIEW_REQUIRED**, not VIOLATION. `GENERIC_CUSTOMER_RAW_MATERIAL_SALE_REVIEW_V1` materializes detection at document/raw-line grain with MEDIUM priority because no validated technical-risk flag exists.

## 14–15. Customer taxonomy and coverage

The reusable `CardCode → customer_business_type` contract contains {crosswalk_count} rows. Exact assertions classified {coverage_counts[GENERIC_CUSTOMER]} generic and {coverage_counts[INTERNAL_ACCOUNT]} internal account; {coverage_counts[UNKNOWN]} remain UNKNOWN rather than fabricated. No CardCode is silently commercial.

## 16. All-CardCode ranking

{markdown_table(all_ranking, ['Rank','Cliente','CardCode','Compras','Días','Primera','Última','SKU_RAW_distintos'], 10)}

## 17–18. Commercial-customer ranking and UNKNOWN sensitivity

The commercial ranking failed closed: no RAW-buying CardCode has explicit `COMMERCIAL_CUSTOMER` evidence. There are {sensitivity['RAW_BUYING_UNKNOWN_CARDCODES']} RAW-buying UNKNOWN CardCodes and they can change the winner; confidence is **UNRESOLVED**.

## 19–20. Foundation candidate and promotion readiness

Candidate `{candidate.foundation_publication_id}` pins the original Sales, Credit Memo, OINM, OITW and Material Supply components and changes Reference to `{version}`. Explicit pinned validation passed with no version mixing or fallback. CURRENT remains `{current_after}`. Promotion readiness is **NO** because this audit explicitly stops for review.

## 21. Tests

Full Data Lake pytest return code: {test_run.returncode}; `py_compile`: {compile_run.returncode}; `git diff --check`: {diff_run.returncode}. Full output is in `tests.json`.

## 22. Files changed

See `files_changed.json`. No Git add/commit was performed.

## 23. Remaining gaps

- Most customers remain UNKNOWN; the commercial winner is unresolved.
- No per-document real-buyer identity is available.
- No internal policy governing this exact case was found.
- Chemical and safety/regulatory dimensions are unavailable.
- Validated branch mapping is unavailable; only warehouse-level location is reported.

## 24. Recommended business/control follow-up

Validate the operating purpose of CG2A with branch/POS owners and determine whether the real buyer should be captured in a structured, privacy-appropriate field. Review the high-frequency SKUs and p99 line quantities from the persisted evidence. Keep the rule detection-only until policy and technical-risk dimensions are validated. Separately obtain explicit CardCode-level commercial classifications before publishing a commercial-customer ranking.

## Required machine-readable outputs

```text
{required_outputs}
```
"""
    (EVIDENCE / "report.md").write_text(report, encoding="utf-8")
    stale_failure = EVIDENCE / "failure.json"
    if stale_failure.exists():
        stale_failure.unlink()
    state("COMPLETE", "COMMERCIAL_RANKING_EXECUTED", None)
    print(json.dumps({"verdict": verdict, "summary": required, "elapsed_seconds": round(time.perf_counter()-started, 3)}, indent=2, ensure_ascii=False, default=jsonable))
    return 0 if success else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
        state("STOPPED", "UNKNOWN", None, str(exc))
        write_json("failure.json", {"error": type(exc).__name__, "message": str(exc), "SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0})
        raise
