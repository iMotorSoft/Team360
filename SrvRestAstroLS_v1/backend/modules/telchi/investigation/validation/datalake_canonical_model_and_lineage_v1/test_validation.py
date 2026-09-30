from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_summary_contract() -> None:
    summary = json.loads((ROOT / "summary.json").read_text(encoding="utf-8"))
    assert summary["gate"] == "TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS"
    assert summary["historical_inventory_used"] is True
    assert summary["sap_knowledge_inventory_used"] is True
    assert summary["sap_accessed"] is False
    assert summary["sap_write_count"] == 0
    assert summary["canonical_entities"] == 51
    assert summary["core_v1_entities"] == 25
    assert summary["production_parquets_created"] == 0
    assert summary["datalake_physical_layout_created"] == 0


def test_entity_classes_and_core_grain_are_complete() -> None:
    entities = rows("canonical_entities.csv")
    grain = rows("canonical_grain.csv")
    assert len(entities) == 51
    assert len(grain) == 25
    assert {row["classification"] for row in entities} == {
        "CORE_V1", "CORE_LATER", "REFERENCE", "SPECIALIZED", "OUT_OF_SCOPE"
    }
    assert all(row["grain"] and row["natural_key_candidate"] for row in grain)
    assert all(row["surrogate_key_needed"] in {"YES", "NO"} for row in grain)


def test_temporal_and_lineage_contracts_are_explicit() -> None:
    snapshot = rows("snapshot_policy.csv")
    lineage = rows("lineage_contract.csv")
    assert len(snapshot) == 16
    assert {row["snapshot_type"] for row in snapshot} >= {
        "APPEND_ONLY_EVENT", "PERIOD_SNAPSHOT", "FULL_SNAPSHOT", "CURRENT_STATE"
    }
    assert len(lineage) == 152
    assert {row["requirement"] for row in lineage} == {
        "REQUIRED", "OPTIONAL", "NOT_APPLICABLE"
    }
    assert any(row["source_family_or_dataset"] == "movProductSB1" and row["canonical_target"] == "INVENTORY_MOVEMENT" for row in snapshot)
    assert any(row["source_family_or_dataset"] == "movProduct" and row["canonical_target"] == "STOCK_SNAPSHOT" for row in snapshot)


def test_crosswalk_security_and_gap_counts() -> None:
    crosswalk = rows("identity_crosswalk.csv")
    gaps = rows("blocking_gaps.csv")
    security = rows("security_contract.csv")
    assert len(crosswalk) == 7
    assert all(row["mapping_status"] == "PROPOSED_CONTRACT" for row in crosswalk)
    assert len(gaps) == 18
    assert sum(row["classification"].startswith("BLOCKING_") for row in gaps) == 8
    assert sum(row["classification"] == "NON_BLOCKING" for row in gaps) == 8
    assert sum(row["classification"] == "OUT_OF_INITIAL_SCOPE" for row in gaps) == 2
    assert len(security) == 9
    assert {row["security_domain"] for row in security} >= {"inventory", "sales", "credit", "users"}


def test_no_physical_outputs_are_present() -> None:
    assert not list(ROOT.glob("*.parquet"))
    assert not list(ROOT.glob("*.parq"))
