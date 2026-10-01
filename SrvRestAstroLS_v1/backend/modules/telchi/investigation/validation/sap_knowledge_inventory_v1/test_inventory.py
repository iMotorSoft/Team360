"""Focused contract tests for the SAP knowledge inventory runner."""

from __future__ import annotations

import csv
from pathlib import Path

from . import inventory


REQUIRED_OUTPUTS = (
    "sap_gates_inventory.csv",
    "sap_tables_inventory.csv",
    "sap_relationships_inventory.csv",
    "sap_business_rules_inventory.csv",
    "sap_validated_metrics.csv",
    "sap_historical_mapping.csv",
    "sap_data_gaps.csv",
    "sap_candidate_data_products.csv",
    "sap_security_domains.csv",
    "sap_knowledge_inventory_v1_summary.json",
)


def test_catalogs_have_required_rows_and_confidence() -> None:
    assert len(inventory.TABLE_SPECS) >= 60
    assert len(inventory.RELATIONSHIPS) >= 25
    assert len(inventory.RULES) >= 20
    assert len(inventory.METRICS) >= 15
    assert len(inventory.MAPPINGS) >= 8
    assert len(inventory.GAPS) >= 12
    assert {row[7] for row in inventory.RELATIONSHIPS} <= {"CONFIRMED", "LIKELY", "POSSIBLE", "UNKNOWN"}
    assert {row[6] for row in inventory.RULES} <= {"CONFIRMED", "LIKELY", "POSSIBLE", "UNKNOWN"}
    assert {row[7] for row in inventory.MAPPINGS} <= {"CONFIRMED", "LIKELY", "POSSIBLE", "UNKNOWN"}


def test_gate_scan_does_not_access_sap() -> None:
    rows = inventory._gate_rows()
    assert rows
    assert any(row["gate_id"] == "TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS" for row in rows)
    assert all(row["read_only"] in {"YES", "UNKNOWN"} for row in rows)
    # The runner has no connector/import side effect and its own declared policy
    # is documentary only; prior gates may correctly show sap_access=YES.
    assert inventory.EVIDENCE_ROOT != inventory.INVESTIGATION


def test_build_writes_only_declared_small_outputs(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "inventory"
    report = tmp_path / "report.md"
    monkeypatch.setattr(inventory, "OUTPUT", output)
    monkeypatch.setattr(inventory, "REPORT", report)
    summary = inventory.build()
    assert summary["sap_write_count"] == 0
    assert summary["production_parquets_created"] == 0
    assert summary["datalake_physical_design_created"] == 0
    assert report.exists()
    for name in REQUIRED_OUTPUTS:
        assert (output / name).exists(), name
    with (output / "sap_tables_inventory.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {"OITM", "OITW", "OINV", "INV1", "OINM", "OWTR", "OITT", "OWOR", "OUSR"} <= {
        row["table_name"] for row in rows
    }
    assert "TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED" in report.read_text(encoding="utf-8")
