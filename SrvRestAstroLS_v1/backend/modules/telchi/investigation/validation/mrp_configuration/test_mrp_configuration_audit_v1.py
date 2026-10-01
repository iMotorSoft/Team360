from modules.telchi.investigation.validation.mrp_configuration.mrp_configuration_audit_v1 import (
    active,
    anomaly_rows,
    comparison_matrix,
    coverage,
    make_bom,
    parameter_quality,
    planning_semantic,
    procurement_semantic,
    status,
    tier,
)


def test_sap_semantics_preserve_unknown_values():
    assert planning_semantic("M") == "MRP"
    assert planning_semantic("N") == "NO_MRP"
    assert planning_semantic("X") == "UNKNOWN"
    assert procurement_semantic("M") == "MAKE"
    assert procurement_semantic("B") == "BUY"
    assert procurement_semantic("X") == "UNKNOWN"


def test_status_distinguishes_missing_and_zero():
    assert status(None) == "MISSING"
    assert status("") == "MISSING"
    assert status(0) == "ZERO"
    assert status(4) == "CONFIGURED"


def test_active_and_tiers_are_deterministic():
    row = {"ActiveFlag": "Y", "FrozenFlag": "N", "DeletedFlag": "N"}
    assert active(row)
    assert tier({"RecentSalesCount": 101}) == "A"
    assert tier({"RecentSalesCount": 1}) == "B"
    assert tier({}) == "C"


def test_bom_inventory_has_component_count_and_exact_parent_key():
    headers = [{"ItemCode": "FG1", "BOMTypeRaw": "P"}]
    lines = [{"ItemCode": "FG1"}, {"ItemCode": "FG1"}]
    rows, by_item = make_bom(headers, lines)
    assert rows[0]["ComponentCount"] == 2
    assert by_item["FG1"]["BOMExists"] is True


def test_parameter_quality_exposes_default_like_and_not_applicable():
    assert parameter_quality("ProcurementMethod", ["B"] * 9 + ["M"], "OITM", "PrcrmntMtd", "ITEM")["Quality"] == "DEFAULT_LIKE"
    assert parameter_quality("SafetyStock", [None, None], "SAP_STANDARD", "NOT_OBSERVED", "ITEM")["Quality"] == "NOT_APPLICABLE"


def test_coverage_is_reproducible():
    assert coverage([1, None, 0, ""], 4) == {"configured": 2, "universe": 4, "coverage_pct": 50.0}


def test_anomaly_detection_does_not_claim_incorrectness_against_operations():
    items = [{
        "ItemCode": "FG1", "ItemActive": True, "PlanningMethodStatus": "CONFIGURED",
        "ProcurementMethodStatus": "CONFIGURED", "ProcurementMethod": "MAKE",
        "LeadTimeStatus": "ZERO", "LeadTime": 0, "PreferredVendor": None,
        "MinimumInventory": 0, "MaximumInventory": 0, "OrderMultiple": 0, "MinimumOrderQty": 0,
        "RecentSalesCount": 1,
    }]
    anomalies = anomaly_rows(items, [], {})
    kinds = {row["AnomalyType"] for row in anomalies}
    assert "LEAD_TIME_ZERO" in kinds
    assert "PRODUCTION_WITHOUT_BOM" in kinds
    assert all("incorrect" not in row["PotentialMRPImpact"].lower() for row in anomalies)


def test_future_matrix_keeps_real_fields_empty():
    rows = comparison_matrix([{"ItemCode": "I1", "Warehouse": "W1", "PlanningMethodRaw": "M", "ProcurementMethodRaw": "B", "LeadTime": 3, "MinimumInventory": 1, "MaximumInventory": 2, "MinimumOrderQty": 1, "PreferredVendor": "V1"}], {}, set())
    assert rows[0]["REAL_LeadTime_Median"] is None
    assert rows[0]["SAP_PlanningMethod"] == "M"
