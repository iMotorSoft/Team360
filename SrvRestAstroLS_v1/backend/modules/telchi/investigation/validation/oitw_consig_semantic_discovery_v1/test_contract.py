from __future__ import annotations

from pathlib import Path

from modules.telchi.investigation.validation.oitw_consig_semantic_discovery_v1.runner import (
    AGROTEL_ITEM_CODES,
    BALANCE_RULE,
    CUSTOMER_ATTRIBUTION_RULE,
    GATE,
    YUAL_ITEM_CODES,
    classify_semantic_class,
    classify_value_semantic_type,
    datalake_relevance,
    historical_claim_allowed,
    is_agrotel_product,
    is_customer_attributable,
    is_negative_control_customer,
    is_yual_product,
    oitw_grain,
    potential_balance_model,
    summarize_value_distribution,
)

RUNNER_SOURCE = Path(__file__).with_name("runner.py").read_text(encoding="utf-8")


def test_gate_identity_and_grain_are_fixed():
    assert GATE == "TELCHI_OITW_CONSIG_SEMANTIC_DISCOVERY_V1"
    assert oitw_grain() == "ItemCode+WhsCode"
    assert "ItemCode x WhsCode" in RUNNER_SOURCE
    assert "no CardCode" in " ".join(RUNNER_SOURCE.split())


def test_oitw_alone_never_attributes_to_a_customer():
    assert is_customer_attributable(["ItemCode", "WhsCode", "Consig", "OnHand"]) is False
    assert is_customer_attributable(["ItemCode", "WhsCode"]) is False
    # Only an explicit source-native customer key enables attribution.
    assert is_customer_attributable(["ItemCode", "WhsCode", "CardCode"]) is True


def test_value_semantic_type_is_quantity_not_flag():
    assert classify_value_semantic_type(["-6500", "-1", "0", "1", "400"]) == "QUANTITY"
    assert classify_value_semantic_type(["0", "1"]) == "BOOLEAN_FLAG"
    assert classify_value_semantic_type([]) == "UNKNOWN"


def test_value_distribution_separates_null_zero_nonzero():
    rows = [
        {"value": "0", "row_count": 100},
        {"value": "1", "row_count": 2},
        {"value": "-30", "row_count": 1},
        {"value": None, "row_count": 3},
    ]
    summary = summarize_value_distribution(rows)
    assert summary["ZERO_COUNT"] == 100
    assert summary["ONE_COUNT"] == 2
    assert summary["NONZERO_COUNT"] == 3
    assert summary["NULL_COUNT"] == 3
    assert summary["OTHER_VALUE_COUNTS"] == {"-30": 1}
    assert summary["NONZERO_PERCENT"] == "2.830189"


def test_semantic_classification_prefers_warehouse_quantity():
    assert classify_semantic_class("QUANTITY", "REJECTED", "YES") == "ITEM_WAREHOUSE_QUANTITY"
    # A customer-specific interpretation would require unmistakable evidence.
    assert classify_semantic_class("QUANTITY", "CONFIRMED", "YES") == "CUSTOMER_CONSIGNMENT_FLAG"
    assert classify_semantic_class("UNKNOWN", "NOT_DEMONSTRATED", "UNKNOWN") == "UNKNOWN"


def test_yual_and_agrotel_fixtures_are_distinct():
    assert is_yual_product("L01730") is True
    assert is_yual_product("L00461") is False
    assert is_agrotel_product("L00461") is True
    assert is_agrotel_product("L01730") is False
    assert set(YUAL_ITEM_CODES).isdisjoint(set(AGROTEL_ITEM_CODES))
    assert len(YUAL_ITEM_CODES) == 5
    assert len(AGROTEL_ITEM_CODES) == 13


def test_negative_control_customer_is_not_positive():
    assert is_negative_control_customer("0") is True
    assert is_negative_control_customer("") is True
    assert is_negative_control_customer("1") is False


def test_no_historical_claim_without_audit_log():
    assert historical_claim_allowed("NO") is False
    assert historical_claim_allowed("UNKNOWN") is False
    assert historical_claim_allowed("YES") is True
    assert "current state only" in RUNNER_SOURCE.lower()


def test_no_balance_computation_is_ever_asserted():
    model = potential_balance_model()
    assert model["CONSIGNATION_BALANCE_COMPUTED"] == "NO"
    assert model["POTENTIAL_BALANCE_FORMULA"] == "NONE"
    assert model["BALANCE_FORMULA_CONFIDENCE"] == "UNRESOLVED"
    assert "no verified formula" in BALANCE_RULE


def test_datalake_relevance_is_optional_not_material():
    assert datalake_relevance(501) == "OPTIONAL"
    assert datalake_relevance(0) == "NOT_RELEVANT"


def test_no_sap_writes_or_ai_invocations_in_runner():
    upper = RUNNER_SOURCE.upper()
    assert "SAP_WRITE_COUNT" in upper
    assert "AI_INVOCATIONS" in upper
    assert "SELECT *" not in upper
    assert "INSERT " not in upper
    assert "UPDATE " not in upper
    assert "DELETE " not in upper
    assert GATE in RUNNER_SOURCE


def test_runner_declares_read_only_and_no_schema_writes():
    assert "HanaReadOnlySource" in RUNNER_SOURCE
    assert "DuckLakeConnector" in RUNNER_SOURCE
    assert '"DUCKLAKE_MODIFIED": "NO"' in RUNNER_SOURCE
    assert '"ATOMIC_MODIFIED": "NO"' in RUNNER_SOURCE
    assert '"REFERENCE_V2_MODIFIED": "NO"' in RUNNER_SOURCE
    assert "read_only=True" in RUNNER_SOURCE