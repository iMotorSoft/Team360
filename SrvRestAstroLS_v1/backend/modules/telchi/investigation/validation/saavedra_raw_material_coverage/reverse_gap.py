"""Reverse gap analysis for TELCHI_SAAVEDRA_RAW_MATERIAL_COVERAGE_SAP_DIRECT_V1.

Reads (READ ONLY) the current Data Lake Foundation publication, the Reference
datasets and the outside-Foundation MRP/BOM parquet, then classifies exactly the
capabilities consumed by the direct SAP answer. It changes nothing: no Data
Lake writes, no Foundation promotion, no scheduler.

Usage:
    uv run python -m modules.telchi.investigation.validation.saavedra_raw_material_coverage.reverse_gap
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector

EVIDENCE_DIR = Path(os.environ.get(
    "TELCHI_SAAVEDRA_EVIDENCE_DIR",
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/"
    "TELCHI_SAAVEDRA_RAW_MATERIAL_COVERAGE_SAP_DIRECT_V1",
))

BUSINESS_MRP = DATA_ROOT / "business" / "mrp_configuration_audit_v1"


def foundation_state() -> dict:
    """Persisted Foundation publication + Atomic table inventory (read only)."""
    c = DuckLakeConnector()
    with c.session(read_only=True) as con:
        cols = {r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='ops' AND table_name='foundation_publications_v1'").fetchall()}
        row = con.execute(
            "SELECT foundation_publication_id, status, reference_version, "
            "sales_publication_id, oinm_publication_id, oitw_publication_id, "
            "component_count, source_as_of, committed_at "
            "FROM telchi.ops.foundation_publications_v1 "
            "ORDER BY created_at DESC LIMIT 1").fetchone()
        pointer = con.execute(
            "SELECT foundation_publication_id FROM telchi.ops.foundation_current_v1 "
            "WHERE slot = 1").fetchone()
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='atomic' ORDER BY table_name").fetchall()]
        counts = {}
        for t in tables:
            counts[t] = con.execute(f"SELECT COUNT(*) FROM telchi.atomic.{t}").fetchone()[0]
        return {
            "foundation_publication_id": row[0], "status": row[1],
            "reference_version": row[2], "sales_publication_id": row[3],
            "oinm_publication_id": row[4], "oitw_publication_id": row[5],
            "component_count": row[6], "source_as_of": str(row[7]), "committed_at": str(row[8]),
            "current_pointer": pointer[0] if pointer else None,
            "metadata_has_credit_memo_column": "credit_memo_publication_id" in cols,
            "atomic_tables": tables, "atomic_row_counts": counts,
        }


def reference_state(ref_path: Path) -> dict:
    con = duckdb.connect()
    def q(rel: str) -> dict:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{ref_path}/{rel}/*.parquet')").fetchone()[0]
            return {"rows": n}
        except Exception as exc:  # pragma: no cover
            return {"rows": None, "error": str(exc)}
    whs_saa = con.execute(
        f"SELECT code, name, warehouse_role_id FROM read_parquet('{ref_path}/warehouses/*.parquet') "
        f"WHERE code LIKE 'SAA%'").fetchall()
    prod_cols = [c[0] for c in con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{ref_path}/products/*.parquet')").fetchall()]
    return {
        "products": q("products"),
        "warehouses": q("warehouses"),
        "warehouse_roles": q("warehouse_roles"),
        "production_site": q("production_site"),
        "units_of_measure": q("units_of_measure"),
        "saa_warehouse_rows": [
            {"code": r[0], "name": r[1], "warehouse_role_id": r[2]} for r in whs_saa],
        "products_columns": prod_cols,
    }


def outside_foundation() -> dict:
    con = duckdb.connect()
    out: dict = {}
    for name in ("mrp_bom_lines", "mrp_bom_inventory", "mrp_item_configuration"):
        path = BUSINESS_MRP / f"{name}.parquet"
        if not path.exists():
            out[name] = {"path": str(path), "exists": False}
            continue
        n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()[0]
        cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()]
        out[name] = {"path": str(path), "exists": True, "rows": n, "columns": cols}
    return out


GAPS = [
    {
        "capability": "SAAVEDRA_WAREHOUSE_MAPPING",
        "sap_source_used": "OWHS + role taxonomy",
        "data_lake_status": "PARTIAL_IN_FOUNDATION",
        "existing_dataset_path": "reference/warehouses (code/name present, warehouse_role_id NULL); reference/warehouse_roles (0 rows); reference/production_site (0 rows)",
        "what_must_be_integrated": "Populate warehouse_roles and map SAA-M1 -> Saavedra raw-material / production site",
        "priority": "HIGH",
    },
    {
        "capability": "CURRENT_RAW_MATERIAL_STOCK",
        "sap_source_used": "OITW",
        "data_lake_status": "PARTIAL_IN_FOUNDATION",
        "existing_dataset_path": "atomic.inventory_balance (on_hand, is_commited, on_order)",
        "what_must_be_integrated": "Raw-material classification + warehouse role to filter SAA-M1",
        "priority": "HIGH",
    },
    {
        "capability": "RAW_MATERIAL_CLASSIFICATION",
        "sap_source_used": "OITM + ITT1 + OWOR",
        "data_lake_status": "SEMANTIC_RULE_MISSING",
        "existing_dataset_path": "reference/products (sap_itms_grp_cod, sap_invnt_item, sap_sell_item, sap_prchse_item); investigation/validation/stock/stock_domain.py classify_item",
        "what_must_be_integrated": "Materialise is_produced / is_bom_component / item_class (RAW_MATERIAL / PACKAGING_MATERIAL / ...)",
        "priority": "HIGH",
    },
    {
        "capability": "BOM_HEADER",
        "sap_source_used": "OITT",
        "data_lake_status": "EXISTS_OUTSIDE_FOUNDATION",
        "existing_dataset_path": "business/mrp_configuration_audit_v1/mrp_bom_inventory.parquet",
        "what_must_be_integrated": "Promote validated OITT header incl. base quantity (Qauntity)",
        "priority": "HIGH",
    },
    {
        "capability": "BOM_LINES",
        "sap_source_used": "ITT1",
        "data_lake_status": "EXISTS_OUTSIDE_FOUNDATION",
        "existing_dataset_path": "business/mrp_configuration_audit_v1/mrp_bom_lines.parquet",
        "what_must_be_integrated": "Promote validated BOM lines into Foundation (parent, child, quantity, line)",
        "priority": "HIGH",
    },
    {
        "capability": "BOM_MULTI_LEVEL_RELATION",
        "sap_source_used": "OITT/ITT1",
        "data_lake_status": "NOT_AVAILABLE",
        "existing_dataset_path": "derivable from mrp_bom_lines.parquet",
        "what_must_be_integrated": "Recursive terminal-raw expansion rule with cycle guard",
        "priority": "HIGH",
    },
    {
        "capability": "UNIT_OF_MEASURE",
        "sap_source_used": "OITM.InvntryUom",
        "data_lake_status": "PARTIAL_IN_FOUNDATION",
        "existing_dataset_path": "reference/products.inventory_uom_id; reference/units_of_measure (0 rows)",
        "what_must_be_integrated": "Populate units_of_measure catalog",
        "priority": "MEDIUM",
    },
    {
        "capability": "BOM_CONVERSION_FACTOR",
        "sap_source_used": "ITT1.Quantity / OITT.Qauntity",
        "data_lake_status": "NOT_AVAILABLE",
        "existing_dataset_path": "business/mrp_configuration_audit_v1/mrp_bom_inventory.parquet (BOMQuantity); investigation/sql/current/equivalence/current_bom_v1.sql",
        "what_must_be_integrated": "Materialise qty_per_parent_unit per BOM edge",
        "priority": "HIGH",
    },
    {
        "capability": "DIRECT_RAW_MATERIAL_SALES",
        "sap_source_used": "OINV/INV1",
        "data_lake_status": "IN_FOUNDATION",
        "existing_dataset_path": "atomic.sales_line + atomic.sales_document",
        "what_must_be_integrated": "None (apply canceled='N' filter)",
        "priority": "-",
    },
    {
        "capability": "DERIVED_PRODUCT_SALES",
        "sap_source_used": "OINV/INV1 + BOM",
        "data_lake_status": "PARTIAL_IN_FOUNDATION",
        "existing_dataset_path": "atomic.sales_line (sales present) but BOM absent",
        "what_must_be_integrated": "BOM graph required to translate product sales into raw-material equivalents",
        "priority": "HIGH",
    },
    {
        "capability": "CREDIT_MEMOS",
        "sap_source_used": "ORIN/RIN1",
        "data_lake_status": "IN_PROGRESS",
        "existing_dataset_path": "concurrent credit_memo component (code added, not yet persisted); sql/current/atomic_inventory_and_sales/credit_notes_extract_v1.sql",
        "what_must_be_integrated": "Publish the credit_memo component (credit_memo_document + credit_memo_line)",
        "priority": "HIGH",
    },
    {
        "capability": "PRODUCTION_CONSUMPTION",
        "sap_source_used": "IGE1 + OWOR",
        "data_lake_status": "EXISTS_OUTSIDE_FOUNDATION",
        "existing_dataset_path": "atomic.inventory_movement (OINM trans_type, no base_type); investigation/validation/production/component_consumption_v1.py",
        "what_must_be_integrated": "Oinm is insufficient: integrate OWOR/IGE1 production-order consumption lineage",
        "priority": "MEDIUM",
    },
    {
        "capability": "TRANSFER_CLASSIFICATION",
        "sap_source_used": "OINM.TransType / OWTR",
        "data_lake_status": "PARTIAL_IN_FOUNDATION",
        "existing_dataset_path": "atomic.inventory_movement.trans_type",
        "what_must_be_integrated": "Semantic rule separating TransType 67 (transfer) from production issue",
        "priority": "MEDIUM",
    },
    {
        "capability": "PRODUCT_RELATIONSHIP",
        "sap_source_used": "ITT1",
        "data_lake_status": "NOT_AVAILABLE",
        "existing_dataset_path": "business/mrp_configuration_audit_v1/mrp_bom_lines.parquet",
        "what_must_be_integrated": "Promote the multi-level product/BOM graph",
        "priority": "HIGH",
    },
]


def main() -> dict:
    foundation = foundation_state()
    ref_path = DATA_ROOT / "reference" / "_versions" / foundation["reference_version"]
    reference = reference_state(ref_path)
    outside = outside_foundation()

    minimum_plan = [
        "1. Populate warehouse_roles and map SAA-M1 -> Saavedra raw-material site.",
        "2. Promote validated BOM (OITT/ITT1) from business/mrp_configuration_audit_v1 into Foundation.",
        "3. Materialise the BOM conversion factor (ITT1.Quantity / OITT.Qauntity).",
        "4. Materialise RAW_MATERIAL / PACKAGING_MATERIAL classification from BOM membership + OITM flags.",
        "5. Integrate ORIN/RIN1 credit memos (already in progress) for net demand.",
        "6. Optionally integrate OWOR/IGE1 production consumption for the actual-consumption coverage.",
    ]

    answer_now = "PARTIAL"
    if all(g["data_lake_status"] == "IN_FOUNDATION" for g in GAPS):
        answer_now = "YES"
    elif any(g["capability"] in ("BOM_LINES", "BOM_HEADER") and g["data_lake_status"] != "IN_FOUNDATION"
             for g in GAPS):
        answer_now = "PARTIAL"

    payload = {
        "gate": "TELCHI_SAAVEDRA_RAW_MATERIAL_COVERAGE_SAP_DIRECT_V1",
        "foundation": foundation,
        "reference_state": reference,
        "outside_foundation": outside,
        "gaps": GAPS,
        "minimum_integration_plan": minimum_plan,
        "FOUNDATION_PUBLICATION_ID": foundation["foundation_publication_id"],
        "SAAVEDRA_MAPPING_STATUS": "PARTIAL",
        "RAW_MATERIAL_CLASSIFICATION_STATUS": "MISSING",
        "BOM_STATUS": "EXISTS_OUTSIDE_FOUNDATION",
        "UNIT_CONVERSION_STATUS": "EXISTS_OUTSIDE_FOUNDATION",
        "CREDIT_MEMO_STATUS": "IN_PROGRESS",
        "PRODUCTION_CONSUMPTION_STATUS": "MISSING",
        "DATA_LAKE_CAN_ANSWER_THIS_QUERY_NOW": answer_now,
        "MINIMUM_FOUNDATION_GAPS": [
            "SAAVEDRA_MAPPING", "RAW_MATERIAL_CLASSIFICATION", "BOM_LINES",
            "BOM_CONVERSION_FACTOR", "CREDIT_MEMOS",
        ],
        "notes": [
            "warehouse_role_id is NULL for all SAA warehouses; warehouse_roles dataset is empty.",
            "production_site and units_of_measure datasets are empty.",
            "A concurrent change is adding a 5th Foundation component (credit_memo); the persisted "
            "metadata still has 4 components and no credit_memo column.",
            "atomic.sales_line has no unit_msr / num_per_msr column; UoM conversion is not persisted.",
        ],
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "datalake_reverse_gap.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "FOUNDATION_PUBLICATION_ID": payload["FOUNDATION_PUBLICATION_ID"],
        "DATA_LAKE_CAN_ANSWER_THIS_QUERY_NOW": payload["DATA_LAKE_CAN_ANSWER_THIS_QUERY_NOW"],
        "BOM_STATUS": payload["BOM_STATUS"],
        "CREDIT_MEMO_STATUS": payload["CREDIT_MEMO_STATUS"],
        "evidence": str(EVIDENCE_DIR / "datalake_reverse_gap.json"),
    }, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    main()