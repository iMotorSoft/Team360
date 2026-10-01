from modules.telchi.investigation.validation.agrotel_consignation_ducklake_vs_sap_v1.runner import (
    CUSTOMER_CARDCODE,
    END_EXCLUSIVE,
    GATE,
    HISTORICAL_CUTOFF,
    START_DATE,
    compare_rows,
    deterministic_hash,
    historical_predicate,
    select_exact_agrotel_candidate,
)


def test_gate_constants_and_cutoff_are_fixed():
    assert GATE == "TELCHI_AGROTEL_CONSIGNATION_DUCKLAKE_VS_SAP_V1"
    assert HISTORICAL_CUTOFF == "2026-09-15"
    assert START_DATE == "2026-01-01"
    assert END_EXCLUSIVE == "2026-09-16"
    assert historical_predicate() == "doc_date >= ? AND doc_date < ?"


def test_exact_identity_selection_never_fuzzy_selects():
    candidates = [
        {"card_code": "C012133", "card_name": "AGROTEL"},
        {"card_code": "PL000700", "card_name": "AGROTEL"},
    ]
    assert select_exact_agrotel_candidate(candidates, card_code=CUSTOMER_CARDCODE)["card_code"] == CUSTOMER_CARDCODE
    assert select_exact_agrotel_candidate(candidates, card_code="AGROTEL") is None


def test_deterministic_hash_and_source_keys_are_order_independent():
    left = [{"doc_entry": "2", "line_num": "0"}, {"doc_entry": "1", "line_num": "0"}]
    right = list(reversed(left))
    assert deterministic_hash(sorted(left, key=lambda row: (row["doc_entry"], row["line_num"]))) == deterministic_hash(sorted(right, key=lambda row: (row["doc_entry"], row["line_num"])))
    comparison = compare_rows(left, right, ("doc_entry", "line_num"))
    assert comparison["status"] == "EXACT"


def test_historical_boundary_is_inclusive_only_through_cutoff():
    assert historical_predicate("DocDate") == "DocDate >= ? AND DocDate < ?"
    assert END_EXCLUSIVE > HISTORICAL_CUTOFF


def test_no_sap_write_or_ai_contract_in_runner_source():
    from pathlib import Path
    source = Path(__file__).with_name("runner.py").read_text(encoding="utf-8")
    assert "AI_INVOCATIONS" in source
    assert "SELECT *" not in source
    assert "UPDATE " not in source
    assert "INSERT " not in source
    assert "DELETE " not in source
