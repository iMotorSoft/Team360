from datetime import date

from modules.telchi.datalake.customer_business_identity import (
    COMMERCIAL_CUSTOMER,
    GENERIC_CUSTOMER,
    INTERNAL_ACCOUNT,
    UNKNOWN,
    CustomerAssertion,
    RawMaterialSale,
    classify_customer,
    generic_raw_material_control_status,
    rank_all_cardcodes,
    rank_commercial_customers,
    unknown_could_change_winner,
)


def assertion(kind=GENERIC_CUSTOMER, source="BUSINESS_CONFIRMED"):
    return CustomerAssertion(kind, source, "Exact CardCode assertion", 1.0)


def sale(doc, card="CG2A", kind=GENERIC_CUSTOMER, item="R1", document_type="SALES"):
    return RawMaterialSale("SAP_HANA", document_type, doc, card, date(2026, 1, 2), item, kind)


def test_cg2a_business_confirmed_classification_and_provenance():
    result = classify_customer("CG2A", "CONTROL TRIBUTARIO", {"CG2A": assertion()})
    assert result.customer_business_type == GENERIC_CUSTOMER
    assert result.classification_source == "BUSINESS_CONFIRMED"
    assert result.classification_status == "VALIDATED"
    assert result.classification_confidence == 1.0


def test_name_never_classifies_a_generic_account():
    result = classify_customer("X", "CLIENTE GENERICO CONTROL", {})
    assert result.customer_business_type == UNKNOWN
    assert result.classification_source == "NO_EXPLICIT_EVIDENCE"


def test_one_assertion_has_one_active_type_per_cardcode():
    assertions = {"CG2A": assertion(), "C010341": assertion(INTERNAL_ACCOUNT, "VALIDATED_PRIOR_GATE")}
    assert len(assertions) == 2
    assert len({classify_customer(code, code, assertions).customer_business_type for code in assertions}) == 2


def test_generic_account_is_excluded_from_commercial_ranking():
    rows = rank_commercial_customers([sale("1"), sale("2", card="C1", kind=COMMERCIAL_CUSTOMER)])
    assert [row["card_code"] for row in rows] == ["C1"]


def test_explicit_commercial_customer_is_included():
    rows = rank_commercial_customers([sale("1", card="C1", kind=COMMERCIAL_CUSTOMER)])
    assert rows[0]["purchase_documents"] == 1


def test_unknown_fails_closed_from_commercial_ranking():
    assert rank_commercial_customers([sale("1", card="U1", kind=UNKNOWN)]) == []


def test_generic_raw_material_control_is_detection_only():
    assert generic_raw_material_control_status(GENERIC_CUSTOMER) == "REVIEW_REQUIRED"
    assert generic_raw_material_control_status(COMMERCIAL_CUSTOMER) == "NOT_APPLICABLE"


def test_multiple_raw_lines_in_same_document_count_once():
    rows = rank_all_cardcodes([sale("1", item="R1"), sale("1", item="R2")])
    assert rows[0]["purchase_documents"] == 1
    assert rows[0]["distinct_raw_material_skus"] == 2


def test_credit_memo_does_not_create_frequency_occasion():
    rows = rank_all_cardcodes([sale("1"), sale("CM1", document_type="CREDIT_MEMO")])
    assert rows[0]["purchase_documents"] == 1


def test_all_cardcode_and_commercial_rankings_are_separate():
    lines = [sale("1"), sale("2"), sale("3", card="C1", kind=COMMERCIAL_CUSTOMER)]
    assert rank_all_cardcodes(lines)[0]["card_code"] == "CG2A"
    assert rank_commercial_customers(lines)[0]["card_code"] == "C1"


def test_unknown_sensitivity_fails_closed():
    assert unknown_could_change_winner({}, {"U1": 1})
    assert unknown_could_change_winner({"C1": 5}, {"U1": 5})
    assert not unknown_could_change_winner({"C1": 5}, {"U1": 4})


def test_assertion_requires_provenance():
    try:
        CustomerAssertion(GENERIC_CUSTOMER, "", "")
    except ValueError as exc:
        assert "provenance" in str(exc)
    else:
        raise AssertionError("missing provenance must fail closed")
