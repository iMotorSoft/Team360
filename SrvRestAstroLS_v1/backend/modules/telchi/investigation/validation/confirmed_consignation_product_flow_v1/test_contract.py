from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from modules.telchi.investigation.validation.confirmed_consignation_product_flow_v1.runner import (
    AGROTEL_CARDCODE,
    AGROTEL_U_CONSIGNACION,
    END_EXCLUSIVE,
    EXPLICIT_LINK_RULE,
    GATE,
    HISTORICAL_CUTOFF,
    START_DATE,
    compare_rowsets,
    customer_role_counts,
    historical_predicate,
    is_confirmed_consignment_customer,
    is_explicit_customer_linked_movement,
    potential_balance_model,
    quantity_sum,
    select_confirmed_consignment_customers,
)

RUNNER_SOURCE = Path(__file__).with_name("runner.py").read_text(encoding="utf-8")


def test_gate_constants_and_cutoff_are_fixed():
    assert GATE == "TELCHI_CONFIRMED_CONSIGNATION_PRODUCT_FLOW_V1"
    assert HISTORICAL_CUTOFF == "2026-09-15"
    assert START_DATE == "2026-01-01"
    assert END_EXCLUSIVE == "2026-09-16"
    assert historical_predicate() == "doc_date >= ? AND doc_date < ?"
    assert historical_predicate("DocDate") == "DocDate >= ? AND DocDate < ?"


def test_confirmed_selection_requires_positive_and_customer_role():
    rows = [
        {"card_code": "C001556", "card_type": "C", "u_consignacion": "1"},
        {"card_code": "C012133", "card_type": "C", "u_consignacion": "0"},
        {"card_code": "PL000700", "card_type": "S", "u_consignacion": "1"},
        {"card_code": "L000001", "card_type": "L", "u_consignacion": "1"},
    ]
    assert is_confirmed_consignment_customer(rows[0]) is True
    assert is_confirmed_consignment_customer(rows[1]) is False
    assert is_confirmed_consignment_customer(rows[2]) is False
    assert is_confirmed_consignment_customer(rows[3]) is False
    selected = select_confirmed_consignment_customers(rows)
    assert [row["card_code"] for row in selected] == ["C001556"]


def test_customer_role_filtering_never_merges_supplier_or_lead():
    rows = [
        {"card_code": "A", "card_type": "C", "u_consignacion": "1"},
        {"card_code": "B", "card_type": "S", "u_consignacion": "1"},
        {"card_code": "C", "card_type": "L", "u_consignacion": "1"},
    ]
    assert customer_role_counts(rows) == {"C": 1, "S": 1, "L": 1}
    assert [row["card_code"] for row in select_confirmed_consignment_customers(rows)] == ["A"]


def test_oinm_explicit_link_only_policy():
    row = {"trans_num": "1", "trans_seq": "1", "card_code": "C001556"}
    assert is_explicit_customer_linked_movement(row, "C001556") is True
    assert is_explicit_customer_linked_movement(row, "C012133") is False
    assert is_explicit_customer_linked_movement({"card_code": None}, "C001556") is False
    # Same date/quantity/item never substitutes for the source-native CardCode.
    assert is_explicit_customer_linked_movement({"trans_num": "1", "item_code": "L1", "out_qty": "12"}, "C001556") is False
    assert "CardCode" in EXPLICIT_LINK_RULE


def test_sales_rowset_comparison_uses_document_source_keys():
    left = [
        {"DocEntry": 2, "LineNum": 0, "Quantity": Decimal("12.000"), "DocDate": "2026-04-10T00:00:00"},
        {"DocEntry": 1, "LineNum": 1, "Quantity": "3", "DocDate": "2026-04-10T00:00:00"},
    ]
    right = [
        {"doc_entry": "1", "line_num": "1", "quantity": "3", "doc_date": "2026-04-10T00:00:00"},
        {"doc_entry": "2", "line_num": "0", "quantity": "12", "doc_date": "2026-04-10"},
    ]
    result = compare_rowsets(left, right, ("doc_entry", "line_num"))
    assert result["status"] == "EXACT"
    assert result["sap_hash"] == result["ducklake_hash"]


def test_oinm_rowset_comparison_preserves_transnum_transseq():
    result = compare_rowsets(
        [{"TransNum": 9, "TransSeq": 9, "InQty": "0", "OutQty": "12", "CardCode": "C001556"}],
        [{"trans_num": "9", "trans_seq": "9", "in_qty": "0", "out_qty": "12", "card_code": "C001556"}],
        ("trans_num", "trans_seq"),
    )
    assert result["status"] == "EXACT"


def test_document_source_keys_are_not_dropped_by_normalization():
    from modules.telchi.investigation.validation.confirmed_consignation_product_flow_v1.runner import normalize

    row = normalize([{"DocEntry": 8, "LineNum": 3, "BaseEntry": 99, "BaseType": 17, "TransNum": 5, "TransSeq": 5}])[0]
    assert row["doc_entry"] == "8"
    assert row["line_num"] == "3"
    assert row["base_entry"] == "99"
    assert row["trans_num"] == "5"
    assert row["trans_seq"] == "5"


def test_quantity_sum_is_source_native_only():
    assert quantity_sum([{"quantity": "12"}, {"quantity": Decimal("3")}, {"quantity": None}], "quantity") == "15"


def test_no_balance_calculation_is_ever_asserted():
    model = potential_balance_model()
    assert model["CONSIGNATION_BALANCE_COMPUTED"] == "NO"
    assert model["POTENTIAL_BALANCE_FORMULA"] == "NONE"
    assert model["BALANCE_FORMULA_CONFIDENCE"] == "UNRESOLVED"
    assert "delivered - invoiced - returned" in model["candidate_considered"]


def test_no_fuzzy_linking_contract_in_runner_source():
    assert "EXPLICIT_LINK_RULE" in RUNNER_SOURCE
    assert "no date, quantity or name matching" in RUNNER_SOURCE.lower()
    # No inference helpers based on same date/quantity are present.
    assert "same_date" not in RUNNER_SOURCE
    assert "same_quantity" not in RUNNER_SOURCE


def test_oitw_current_state_only_and_not_customer_bound():
    assert '"OITW_CURRENT_STATE_ONLY": "YES"' in RUNNER_SOURCE
    assert "carries no CardCode" in RUNNER_SOURCE
    assert "stock at the historical cutoff" not in RUNNER_SOURCE.lower()


def test_agrotel_is_not_reclassified():
    assert AGROTEL_CARDCODE == "C012133"
    assert AGROTEL_U_CONSIGNACION == "0"
    assert '"AGROTEL_RECLASSIFIED": "NO"' in RUNNER_SOURCE
    assert "AGROTEL_RECLASSIFIED\": \"NO\"" in RUNNER_SOURCE or '"reclassified": "NO"' in RUNNER_SOURCE


def test_no_sap_writes_or_ai_invocations_in_runner():
    upper = RUNNER_SOURCE.upper()
    assert "SAP_WRITE_COUNT" in upper
    assert "AI_INVOCATIONS" in upper
    assert "SELECT *" not in upper
    assert "INSERT " not in upper
    assert "UPDATE " not in upper
    assert "DELETE " not in upper
    assert GATE in RUNNER_SOURCE