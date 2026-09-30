from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parents[1] / "docs"
EVIDENCE = json.loads((HERE / "discovery_evidence.json").read_text(encoding="utf-8"))
CONTRACT = (DOCS / "TELCHI_SETTLEMENT_BUSINESS_CONTRACT_V1.md").read_text(encoding="utf-8")
SOURCE_MAP = (DOCS / "TELCHI_SETTLEMENT_SOURCE_MAP_V1.md").read_text(encoding="utf-8")


def test_read_only_gate_and_required_cases() -> None:
    assert EVIDENCE["gate"].endswith("_PASS")
    assert EVIDENCE["sap_query_count"] == 46
    assert EVIDENCE["sap_write_count"] == 0
    assert len(EVIDENCE["real_cases"]) == 10


def test_canonical_keys_are_unique_where_promised() -> None:
    controls = EVIDENCE["key_controls"]
    for key in (
        "OINV_docentry_duplicates",
        "ORIN_docentry_duplicates",
        "ORCT_docentry_duplicates",
        "OITR_reconnum_duplicates",
        "ITR1_reconnum_lineseq_duplicates",
    ):
        assert controls[key] == 0
    assert controls["RCT2_rows"] > controls["RCT2_aggregate_keys"]


def test_payment_allocation_join_direction_is_proven() -> None:
    relationships = EVIDENCE["relationship_controls"]
    assert relationships["rct2_docnum_to_orct"] == EVIDENCE["table_counts"]["RCT2"]
    assert relationships["rct2_type13_docentry_to_oinv"] == relationships["rct2_type13_rows"]
    assert relationships["rct2_invoiceid_to_oinv"] == 0
    assert relationships["multi_invoice_payments"] > 0
    assert relationships["multi_payment_invoices"] > 0
    assert relationships["active_n_to_n_reconciliations"] > 0


def test_contract_separates_terms_payments_and_settlement() -> None:
    assert "condición comercial" in CONTRACT
    assert "pago/cobranza" in CONTRACT
    assert "settlement" in CONTRACT
    assert "no es un pago" in CONTRACT
    assert "se publican miembros, no pares inventados" in CONTRACT


def test_as_of_and_contado_decision_are_explicit() -> None:
    for token in (
        "open_amount_as_of",
        "SAME_DAY_PAYMENT",
        "SAME_DAY_FULLY_SETTLED",
        "IMMEDIATE_SETTLEMENT(N)",
        "EVENTUALLY_PAID",
        "Decisión requerida de TELCHI",
    ):
        assert token in CONTRACT


def test_source_map_has_explicit_lineage_and_payment_terms_diagnosis() -> None:
    for token in (
        "RCT2.DocNum = ORCT.DocEntry",
        "RCT2.DocEntry = OINV.DocEntry",
        "OITR/ITR1",
        "Dataset existe vacío",
        "No es “otro medio”",
    ):
        assert token in SOURCE_MAP
    terms = EVIDENCE["payment_terms"]
    assert terms["sap_octg_rows"] == 37
    assert terms["foundation_payment_terms_rows"] == 0
    assert terms["settlement_dependency"] == "NONE"
