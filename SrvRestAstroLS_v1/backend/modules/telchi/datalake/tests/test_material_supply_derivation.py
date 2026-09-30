"""Contract tests for the deterministic Material Supply derivation kernels.

Pure functions only: no SAP, no DuckLake, no Data Root writes.
"""
from __future__ import annotations

from datetime import date

from modules.telchi.investigation.validation.datalake_material_supply_derivation_v1.run_saavedra_reconciliation import (
    build_v2_result,
)
from modules.telchi.datalake.material_supply_foundation import ACTIVE_SAAVEDRA_MATERIAL
from modules.telchi.datalake.material_supply_derivation import (
    aggregate_origin_profile,
    build_actual_consumption,
    build_equivalent_demand,
    build_lead_time_profiles,
    build_open_purchase_pipeline,
    build_parent_index,
    build_supply_status,
    classify_issue_line,
    classify_origin,
    select_lead_time,
    split_bom_raw_materials,
    usage_per_unit,
)

WINDOW_START = date(2026, 6, 26)
WINDOW_END = date(2026, 9, 24)


def test_classify_origin_is_fail_closed_on_undocumented_codes():
    assert classify_origin("IMP") == "IMPORTED"
    assert classify_origin("LP") == "LOCAL"
    assert classify_origin("SAA") == "LOCAL"
    assert classify_origin("LF") == "UNKNOWN"      # observed but undocumented
    assert classify_origin(None) == "UNKNOWN"


def test_aggregate_origin_profile():
    assert aggregate_origin_profile(["LOCAL", "LOCAL"]) == "LOCAL"
    assert aggregate_origin_profile(["IMPORTED"]) == "IMPORTED"
    assert aggregate_origin_profile(["LOCAL", "IMPORTED"]) == "MIXED"
    assert aggregate_origin_profile(["UNKNOWN"]) == "UNKNOWN"


def test_classify_issue_line_only_production_is_consumption():
    assert classify_issue_line(202) == "PRODUCTION_CONSUMPTION"
    assert classify_issue_line(67) == "TRANSFER"
    assert classify_issue_line(None) == "UNKNOWN"


def test_actual_consumption_window_and_basetype_are_enforced():
    lines = [
        {"BaseType": 202, "ItemCode": "A", "Quantity": 10, "DocDate": "2026-08-01"},
        {"BaseType": 202, "ItemCode": "A", "Quantity": 5, "DocDate": "2026-09-24"},
        {"BaseType": 202, "ItemCode": "A", "Quantity": 100, "DocDate": "2026-01-01"},  # outside window
        {"BaseType": 67, "ItemCode": "A", "Quantity": 100, "DocDate": "2026-08-01"},   # not consumption
        {"BaseType": 202, "ItemCode": "B", "Quantity": 7, "DocDate": "2026-07-01"},
    ]
    rows = {r["item_code"]: r["actual_consumption_qty"] for r in build_actual_consumption(
        lines, window_start=WINDOW_START, window_end=WINDOW_END)}
    assert rows == {"A": 15.0, "B": 7.0}


def test_split_bom_uses_header_quantity_and_drops_unusable_parents():
    lines = [{"Father": "P1", "Code": "M1", "Quantity": 5}, {"Father": "P2", "Code": "M2", "Quantity": 3}]
    edges = split_bom_raw_materials(lines, {"P1": 10.0, "P2": 0.0})
    assert edges == [{"parent": "P1", "child": "M1", "quantity": 5.0, "qty_per_parent_unit": 0.5}]


def test_usage_per_unit_sums_diamonds_and_protects_cycles():
    edges = [
        {"child": "M1", "parent": "P1", "qty_per_parent_unit": 2.0},
        {"child": "M1", "parent": "P2", "qty_per_parent_unit": 3.0},
        {"child": "P2", "parent": "P1", "qty_per_parent_unit": 4.0},  # M1 -> P2 -> P1 (diamond)
    ]
    usage = usage_per_unit("M1", build_parent_index(edges))
    # M1 -> P1 (2) and M1 -> P2 (3) -> P1 (3*4=12)
    assert usage["P1"] == 14.0
    assert usage["P2"] == 3.0
    # self-cycle must never amplify
    cyclic = [{"child": "X", "parent": "X", "qty_per_parent_unit": 9.0}]
    assert usage_per_unit("X", build_parent_index(cyclic)) == {}


def test_equivalent_demand_direct_plus_derived():
    parents = build_parent_index([{"child": "M1", "parent": "P1", "qty_per_parent_unit": 2.0}])
    rows = build_equivalent_demand(
        raw_materials=["M1"], parents=parents,
        sales_by_item={"M1": 4.0, "P1": 10.0}, credit_by_item={"P1": 1.0},
        window_start=WINDOW_START, window_end=WINDOW_END,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["direct_raw_material_demand"] == 4.0
    assert row["derived_product_raw_material_equivalent"] == 18.0  # (10-1)*2
    assert row["commercial_daily_equivalent_basis_qty"] == 22.0


def test_open_purchase_pipeline_uses_source_native_openqty_and_lineage():
    po_lines = [{"DocEntry": "900", "LineNum": "1", "ItemCode": "M1", "Quantity": 100, "OpenQty": 40,
                 "U_TIPOCOMPRA": "IMP", "CardCode": "C1", "WhsCode": "ALM-IMP", "ShipDate": "2026-10-10",
                 "DocDate": "2026-09-01"}]
    lineage = [{"po_docentry": "900", "po_linenum": "1", "receipt_quantity": 60,
                "receipt_docdate": "2026-09-15", "lineage_path_type": "INDIRECT_PO_RECEIPT_VIA_AP_INVOICE"}]
    row = build_open_purchase_pipeline(po_lines, lineage)[0]
    assert row["open_qty_source"] == 40.0
    assert row["received_qty_supported"] == 60.0
    assert row["procurement_origin"] == "IMPORTED"
    assert row["receipt_lineage_status"] == "INDIRECT_PO_RECEIPT_VIA_AP_INVOICE"


def test_open_purchase_pipeline_marks_unlinked_lines():
    po_lines = [{"DocEntry": "1", "LineNum": "0", "ItemCode": "X", "Quantity": 1, "OpenQty": 1}]
    row = build_open_purchase_pipeline(po_lines, [])[0]
    assert row["receipt_lineage_status"] == "NO_RECEIPT_LINK"
    assert row["procurement_origin"] == "UNKNOWN"


def test_lead_time_profiles_and_selection_precedence():
    samples = [
        {"itemcode": "M1", "supplier": "C1", "origin_code": "IMP", "order_to_receipt_days": 10},
        {"itemcode": "M1", "supplier": "C1", "origin_code": "IMP", "order_to_receipt_days": 20},
    ]
    profiles = build_lead_time_profiles(samples)
    selected = select_lead_time(profiles, "M1", "C1", "IMPORTED")
    assert selected["lead_time_days"] == 10  # p50 of the exact item+supplier+origin profile
    assert selected["lead_time_basis"] == "ITEM+SUPPLIER+ORIGIN"
    # an origin with no samples must stay unavailable, never fabricated
    assert select_lead_time(profiles, "NOPE", "C9", "LOCAL")["lead_time_confidence"] == "UNAVAILABLE"


def test_build_supply_status_zero_stock_is_stockout():
    status = build_supply_status(
        stock_rows=[{"item_code": "M1", "whs_code": "SAA-M1", "on_hand": 0.0}],
        items={"M1": {"canonical_name": "M1", "inventory_uom": "KG", "warehouse": "SAA-M1", "material_class": "RAW_MATERIAL"}},
        actual_consumption={"M1": 90.0},
        equivalent_demand={},
        open_pipeline=[], lead_profiles=[],
        source_as_of="2026-09-24T00:00:00Z", window_days=90,
    )[0]
    assert status["coverage_days"] == 0.0
    assert status["coverage_band"] == "QUIEBRE"
    assert status["local_stockout"] is True
    assert status["global_stockout"] is True
    assert status["supply_risk"] == "NO_INBOUND"
    assert status["is_raw_material"] is True


def test_build_supply_status_local_yes_global_no_with_usable_other_location():
    status = build_supply_status(
        stock_rows=[
            {"item_code": "M1", "whs_code": "SAA-M1", "on_hand": 0.0, "is_commited": 0.0},
            {"item_code": "M1", "whs_code": "LAB-M1", "on_hand": 10.0, "is_commited": 0.0},
            {"item_code": "M1", "whs_code": "SAA-DAN", "on_hand": 100.0, "is_commited": 0.0},
        ],
        items={"M1": {"canonical_name": "M1", "inventory_uom": "KG", "warehouse": "SAA-M1", "material_class": "RAW_MATERIAL"}},
        actual_consumption={"M1": 90.0}, equivalent_demand={}, open_pipeline=[], lead_profiles=[],
        source_as_of="2026-09-24T00:00:00Z", window_days=90,
        valid_warehouses={"SAA-M1", "LAB-M1", "SAA-DAN"},
    )[0]
    assert status["target_warehouse_usable_stock"] == 0.0
    assert status["other_location_usable_stock"] == 10.0
    assert status["global_usable_stock"] == 10.0
    assert status["local_stockout"] is True
    assert status["global_stockout"] is False


def test_saavedra_v2_query_filters_to_active_and_preserves_local_only():
    rows = [
        {"ItemCode": "M1", "material_name": "ACTIVE MATERIAL", "is_raw_material": True,
         "saavedra_relevance": ACTIVE_SAAVEDRA_MATERIAL, "coverage_days": 10.0,
         "local_stockout": True, "global_stockout": False, "supply_risk": "NO_INBOUND",
         "lead_time_days": 20.0},
        {"ItemCode": "M2", "material_name": "GLOBAL MATERIAL", "is_raw_material": True,
         "saavedra_relevance": "GLOBAL_RAW_MATERIAL_NOT_RELEVANT_TO_SAAVEDRA",
         "coverage_days": 0.0, "local_stockout": True, "global_stockout": True,
         "supply_risk": "NO_INBOUND", "lead_time_days": 20.0},
    ]
    result = build_v2_result(rows, foundation_id="foundation_test")
    assert result["QUERY_ROWS"] == 1
    assert result["LOCAL_STOCKOUTS"] == 1
    assert result["GLOBAL_STOCKOUTS"] == 0
    assert result["LOCAL_ONLY_STOCKOUTS"] == 1
    assert result["QUERY_SAP_ACCESSED"] == "NO"