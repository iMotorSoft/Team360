from __future__ import annotations

import json
from pathlib import Path

import pytest

from .run_discovery import EVIDENCE_ROOT, GATE, WRITE_WORDS, ReadOnlyHana


REQUIRED = (
    "precheck.json", "sap_safety.json", "source_inventory.json",
    "table_schema_discovery.json", "document_identity.json", "invoice_contract.json",
    "payment_contract.json", "allocation_contract.json", "reconciliation_contract.json",
    "payment_method_contract.json", "payment_terms_investigation.json",
    "currency_contract.json", "date_semantics.json", "open_balance_contract.json",
    "historical_asof_contract.json", "relationship_cardinalities.json", "invariants.json",
    "data_quality_metrics.json", "history_window.json", "opening_balance_strategy.json",
    "cg2a_source_feasibility.json", "gold_cases.json", "gaps.json",
    "proposed_atomic_contract.json", "files_changed.json", "tests.json", "final_report.md",
)


def load(name: str):
    return json.loads((EVIDENCE_ROOT / name).read_text(encoding="utf-8"))


def test_all_required_evidence_exists() -> None:
    assert all((EVIDENCE_ROOT / name).is_file() for name in REQUIRED)


def test_sap_is_read_only_and_foundation_untouched() -> None:
    safety = load("sap_safety.json")
    files = load("files_changed.json")
    assert safety["SAP_ACCESSED"] == "YES"
    assert safety["SAP_READ_ONLY"] == "YES"
    assert safety["SAP_QUERY_COUNT"] > 0
    assert safety["SAP_WRITE_COUNT"] == 0
    assert files["foundation_modified"] is False
    assert files["data_root_modified"] is False
    assert files["sap_modified"] is False


def test_exact_lineage_and_semantic_separation() -> None:
    allocation = load("allocation_contract.json")
    terms = load("payment_terms_investigation.json")
    reconciliation = load("reconciliation_contract.json")
    assert "RCT2.DocNum = ORCT.DocEntry" in allocation["exact_join"]
    assert allocation["no_heuristic_link"] is True
    assert terms["PAYMENT_TERMS_IS_SETTLEMENT"] == "NO"
    assert "must not be added" in reconciliation["rule"]


def test_qr_uncertainty_is_not_fabricated() -> None:
    methods = load("payment_method_contract.json")
    assert methods["PAYMENT_METHOD_DISCOVERY_STATUS"] == "PARTIAL"
    assert methods["components"]["QR"]["can_identify"] == "NO"
    assert methods["components"]["QR"]["source"] == "UNRESOLVED"


def test_asof_and_cases_are_explicit() -> None:
    historical = load("historical_asof_contract.json")
    cases = load("gold_cases.json")["statuses"]
    assert historical["HISTORICAL_AS_OF_RECONSTRUCTION"] == "SUPPORTED"
    assert historical["supports_2026"] is True
    assert len(cases) == 15
    assert set(cases.values()) <= {"PROVEN", "PARTIAL", "NOT_FOUND", "UNRESOLVED"}


def test_proposed_model_does_not_define_is_cash_sale() -> None:
    proposed = load("proposed_atomic_contract.json")
    names = {item["entity_name"] for item in proposed["entities"]}
    assert "payment_method_component" in names
    assert "reconciliation_participant" in names
    assert "is_cash_sale" not in json.dumps(proposed).lower()


def test_read_only_guard_rejects_mutation_before_cursor() -> None:
    class Cursor:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("cursor must not execute mutation")

    class Guard:
        def checkpoint(self):
            return None

    hana = ReadOnlyHana(Cursor(), Guard())
    with pytest.raises(RuntimeError, match="non-SELECT"):
        hana.select("bad", "UPDATE OINV SET DocNum=1")
    assert hana.write_count == 1
    assert WRITE_WORDS.search("CALL MUTATING_PROC()")


def test_final_report_has_one_allowed_verdict() -> None:
    report = (EVIDENCE_ROOT / "final_report.md").read_text(encoding="utf-8")
    allowed = [f"{GATE}_{suffix}" for suffix in ("PASS", "DEGRADED", "FAIL", "STOP_RESOURCE_PRESSURE")]
    present = [verdict for verdict in allowed if verdict in report]
    assert present == [f"{GATE}_DEGRADED"]
    assert report.count(f"{GATE}_DEGRADED") == 1
    assert "CG2A_FINAL_CONTADO_CLASSIFICATION_EXECUTED=NO" in report
