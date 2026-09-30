from datetime import date

from modules.telchi.datalake.material_supply_foundation import (
    ACTIVE_SAAVEDRA_MATERIAL,
    GLOBAL_RAW_MATERIAL_NOT_RELEVANT_TO_SAAVEDRA,
    HISTORICAL_SAAVEDRA_MATERIAL,
    UNRESOLVED_SAAVEDRA_RELEVANCE,
    aggregate_origin_profile,
    aggregate_purchase_receipts,
    aggregate_warehouse_stock,
    choose_coverage_basis,
    classify_issue_line,
    classify_saavedra_relevance,
    expected_arrival,
    explicit_purchase_origin,
    group_receipts_by_po_line,
    lead_time_profile,
)


def test_issue_classification_requires_explicit_production_lineage():
    assert classify_issue_line(202) == "PRODUCTION_CONSUMPTION"
    assert classify_issue_line("67") == "TRANSFER"
    assert classify_issue_line(None) == "UNKNOWN"
    assert classify_issue_line(202.5) == "UNKNOWN"
    assert classify_issue_line(999) == "UNKNOWN"


def test_receipt_aggregation_keeps_partial_and_complete_quantities():
    rows = [
        {"Quantity": 4, "DocDate": "2026-03-02"},
        {"Quantity": 6, "DocDate": "2026-03-08"},
    ]
    partial = aggregate_purchase_receipts(12, rows)
    assert (partial.ordered_qty, partial.received_qty, partial.open_qty) == (12, 10, 2)
    assert partial.first_receipt_date == date(2026, 3, 2)
    assert partial.last_receipt_date == date(2026, 3, 8)
    assert partial.completion_date is None
    complete = aggregate_purchase_receipts(10, rows)
    assert complete.completion_date == date(2026, 3, 8)
    assert complete.receipt_count == 2


def test_origin_and_eta_are_explicit_and_fail_closed():
    assert explicit_purchase_origin("LF", local_values={"LF"}, imported_values={"IMP"}) == "LOCAL"
    assert explicit_purchase_origin("USD", local_values={"LF"}, imported_values={"IMP"}) == "UNKNOWN"
    assert expected_arrival(line_date="2026-04-01", header_date="2026-04-10")[1] == "LINE_EXPLICIT"
    assert expected_arrival(header_date="2026-04-10")[1] == "HEADER_EXPLICIT"
    assert expected_arrival(historical_date=date(2026, 4, 20))[1] == "HISTORICAL_LEAD_TIME_ESTIMATE"
    assert expected_arrival() == (None, "UNKNOWN")
    assert aggregate_origin_profile(["LOCAL", "IMPORTED"]) == "MIXED"
    assert aggregate_origin_profile(["UNKNOWN"]) == "UNKNOWN"


def test_lead_time_profile_and_coverage_precedence():
    assert lead_time_profile([]) == {"sample_count": 0, "p50_days": None, "p90_days": None}
    assert lead_time_profile([2, 4, 6, 8]) == {"sample_count": 4, "p50_days": 4, "p90_days": 8}
    assert choose_coverage_basis(production_consumption_available=True, commercial_equivalent_demand_available=True) == "ACTUAL_PRODUCTION_CONSUMPTION"
    assert choose_coverage_basis(production_consumption_available=False, commercial_equivalent_demand_available=True) == "COMMERCIAL_EQUIVALENT_DEMAND"
    assert choose_coverage_basis(production_consumption_available=False, commercial_equivalent_demand_available=False) == "UNRESOLVED"


def test_saavedra_relevance_requires_combined_current_evidence():
    active = classify_saavedra_relevance(
        item_active=True, current_target_stock=False, recent_target_movement=False,
        recent_linked_production_consumption=True, recent_saavedra_bom_use=False,
        open_po_to_target=False, historical_target_movement=True,
        historical_linked_production_consumption=True, historical_saavedra_bom_use=False,
    )
    assert active.classification == ACTIVE_SAAVEDRA_MATERIAL
    assert active.confidence == "HIGH"

    historical = classify_saavedra_relevance(
        item_active=True, current_target_stock=False, recent_target_movement=False,
        recent_linked_production_consumption=False, recent_saavedra_bom_use=False,
        open_po_to_target=False, historical_target_movement=True,
        historical_linked_production_consumption=False, historical_saavedra_bom_use=False,
    )
    assert historical.classification == HISTORICAL_SAAVEDRA_MATERIAL

    global_only = classify_saavedra_relevance(
        item_active=True, current_target_stock=False, recent_target_movement=False,
        recent_linked_production_consumption=False, recent_saavedra_bom_use=False,
        open_po_to_target=False, historical_target_movement=False,
        historical_linked_production_consumption=False, historical_saavedra_bom_use=False,
    )
    assert global_only.classification == GLOBAL_RAW_MATERIAL_NOT_RELEVANT_TO_SAAVEDRA

    unresolved = classify_saavedra_relevance(
        item_active=None, current_target_stock=True, recent_target_movement=True,
        recent_linked_production_consumption=False, recent_saavedra_bom_use=False,
        open_po_to_target=False, historical_target_movement=False,
        historical_linked_production_consumption=False, historical_saavedra_bom_use=False,
    )
    assert unresolved.classification == UNRESOLVED_SAAVEDRA_RELEVANCE


def test_inactive_material_is_never_active():
    result = classify_saavedra_relevance(
        item_active=False, current_target_stock=True, recent_target_movement=True,
        recent_linked_production_consumption=True, recent_saavedra_bom_use=True,
        open_po_to_target=True, historical_target_movement=True,
        historical_linked_production_consumption=True, historical_saavedra_bom_use=True,
    )
    assert result.classification == HISTORICAL_SAAVEDRA_MATERIAL
    assert "ITEM_INACTIVE" in result.basis


def test_local_and_global_stockout_are_independent_and_exclude_damaged():
    result = aggregate_warehouse_stock([
        {"whs_code": "SAA-M1", "on_hand": 0, "is_commited": 0},
        {"whs_code": "LAB-M1", "on_hand": 10, "is_commited": 0},
        {"whs_code": "SAA-DAN", "on_hand": 99, "is_commited": 0},
        {"whs_code": "SAA-T2", "on_hand": 50, "is_commited": 0},
        {"whs_code": "SAA-T3", "on_hand": 25, "is_commited": 0},
    ], valid_warehouses={"SAA-M1", "LAB-M1", "SAA-DAN", "SAA-T2", "SAA-T3"})
    assert result.local_stockout is True
    assert result.global_stockout is False
    assert result.other_location_usable_stock == 10
    assert {"SAA-DAN", "SAA-T2", "SAA-T3"} <= set(result.excluded_warehouses)


def test_global_stockout_fails_closed_when_uom_is_unresolved():
    result = aggregate_warehouse_stock(
        [{"whs_code": "SAA-M1", "on_hand": 0}], inventory_uom_resolved=False,
    )
    assert result.local_stockout is True
    assert result.global_stockout is None
    assert result.global_stock_status == "UNRESOLVED"


def test_receipts_must_keep_exact_po_lineage():
    rows = [
        {"BaseType": 22, "BaseEntry": 1, "BaseLine": 0},
        {"BaseType": 67, "BaseEntry": 2, "BaseLine": 0},
        {"BaseType": 22, "BaseEntry": 3, "BaseLine": None},
    ]
    assert group_receipts_by_po_line(rows) == {("1", "0"): [rows[0]]}
