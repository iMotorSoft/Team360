from pathlib import Path

from modules.telchi.investigation.validation.agrotel_consignation_semantic_source_discovery_v1.runner import (
    CUSTOMER_CARDCODE,
    END_EXCLUSIVE,
    GATE,
    HISTORICAL_CUTOFF,
    SUPPLIER_CARDCODE,
    START_DATE,
    _document_chain,
    exact_same_name_roles,
    explicit_document_link,
    interpret_u_consignacion,
)


def test_gate_scope_and_historical_cutoff_are_fixed():
    assert GATE == "TELCHI_AGROTEL_CONSIGNATION_SEMANTIC_SOURCE_DISCOVERY_V1"
    assert START_DATE == "2026-01-01"
    assert HISTORICAL_CUTOFF == "2026-09-15"
    assert END_EXCLUSIVE == "2026-09-16"


def test_customer_supplier_roles_are_separate_and_keyed_by_cardcode():
    rows = [
        {"card_code": CUSTOMER_CARDCODE, "card_name": "AGROTEL", "card_type": "C"},
        {"card_code": SUPPLIER_CARDCODE, "card_name": "AGROTEL", "card_type": "S"},
    ]
    roles = exact_same_name_roles(rows)
    assert roles["customer"]["card_code"] == CUSTOMER_CARDCODE
    assert roles["supplier"]["card_code"] == SUPPLIER_CARDCODE
    assert exact_same_name_roles([{"card_code": "AGROTEL", "card_name": "AGROTEL"}]) == {"customer": None, "supplier": None}


def test_udf_value_interpretation_uses_ufd1_mapping_and_stays_bp_scoped():
    observed = interpret_u_consignacion("0", {"0": "NO", "1": "SI"})
    assert observed == {"value": "0", "label": "NO", "scope": "BUSINESS_PARTNER", "is_product_balance": False}
    assert interpret_u_consignacion("9")["label"] == "UNKNOWN"


def test_document_chain_accepts_only_explicit_keys():
    assert explicit_document_link(15, 347252, 5)
    assert not explicit_document_link(-1, None, None)
    chain = _document_chain(
        [{"DocEntry": 10, "DocDate": "2026-01-02", "LineNum": 0, "ItemCode": "X", "Quantity": "2", "BaseType": 15, "BaseEntry": 20, "BaseLine": 1}],
        [{"DocEntry": 20, "DocDate": "2026-01-02", "LineNum": 1, "ItemCode": "X", "Quantity": "2", "BaseType": 17, "BaseEntry": 30, "BaseLine": 0}],
        [{"DocEntry": 30, "DocDate": "2026-01-01", "LineNum": 0, "ItemCode": "X", "Quantity": "2"}],
        [],
    )
    assert chain["reconstruction_status"] == "YES"
    assert chain["links"][0]["status"] == "EXPLICIT_CHAIN"


def test_current_state_and_no_balance_contracts_are_visible_in_runner():
    source = Path(__file__).with_name("runner.py").read_text(encoding="utf-8")
    assert "OITW_CURRENT_STATE_ONLY" in source
    assert '"POTENTIAL_BALANCE_FORMULA": "NONE"' in source
    assert '"CONSIGNATION_BALANCE_COMPUTED": "NO"' in source
    assert "AI_INVOCATIONS" in source
    assert "SAP_WRITE_COUNT" in source
    assert "SELECT *" not in source
    assert "INSERT " not in source
    assert "UPDATE " not in source
    assert "DELETE " not in source
