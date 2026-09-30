from __future__ import annotations

import csv
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
INVESTIGATION = HERE.parents[1]
ARCHITECTURE = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ARCHITECTURE_V1.md"
ADR_INDEX = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ADR_INDEX_V1.md"
DECISIONS = HERE / "architecture_decisions.csv"
PRINCIPLES = HERE / "architecture_principles.csv"
GAPS = HERE / "known_semantic_gaps.csv"
PRODUCT_MODEL = HERE / "product_operating_model_contract.csv"
CURRENT_STATE = HERE / "current_state.json"
SUMMARY = HERE / "summary.json"

SOURCE_GATES = {
    "TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS",
    "TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED",
    "TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS",
    "TELCHI_DATALAKE_PHYSICAL_DESIGN_READINESS_V1_PASS",
    "TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS",
    "TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1_PASS",
    "TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1_PASS",
    "TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1_PASS",
    "TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED",
}


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_accepted_adrs_have_required_fields_and_unique_ids() -> None:
    text = ADR_INDEX.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^## (ADR-\d{3}) — .+$", text, re.MULTILINE))
    assert len(matches) == 38
    ids: list[str] = []
    required_fields = (
        "ADR ID",
        "Title",
        "Status",
        "Decision",
        "Rationale",
        "Consequences",
        "Evidence / source gates",
        "Supersedes",
        "Superseded by",
        "Date",
    )
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[match.start() : end]
        ids.append(match.group(1))
        expected_status = "PROVISIONAL" if match.group(1) == "ADR-024" else "ACCEPTED"
        assert f"| Status | {expected_status} |" in section
        for field in required_fields:
            assert f"| {field} |" in section, (match.group(1), field)
    assert len(ids) == len(set(ids))


def test_machine_registry_is_unique_and_consistent() -> None:
    rows = _csv_rows(DECISIONS)
    assert len(rows) == 29
    assert {row["status"] for row in rows} == {"ACCEPTED", "PROVISIONAL"}
    assert sum(row["status"] == "ACCEPTED" for row in rows) == 28
    assert sum(row["status"] == "PROVISIONAL" for row in rows) == 1
    assert len({row["adr_id"] for row in rows}) == len(rows)
    active_decisions = [
        (row["domain"].strip().casefold(), row["decision"].strip().casefold())
        for row in rows
        if row["status"] in {"ACCEPTED", "PROVISIONAL"}
    ]
    assert len(active_decisions) == len(set(active_decisions))
    for row in rows:
        assert all(row[field].strip() for field in ("adr_id", "title", "status", "domain", "decision", "source_gate"))


def test_architecture_documents_names_ownership_security_and_layers() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "DEV:  team360_telchi_ducklake" in text
    assert "PROD: team360_telchi_ducklake" in text
    assert "POSTGRES_CATALOG_DATABASE=team360_telchi_ducklake" in text
    assert "POSTGRES_RUNTIME_ROLE=team360_telchi_ducklake" in text
    assert "POSTGRES_METADATA_SCHEMA=public" in text
    assert "Raw is not DuckLake-owned" in text or "Raw no es DuckLake-owned" in text
    assert "DuckLake administra principalmente `atomic`, `business`, `current` y `ops`" in text
    assert "SECURITY BEFORE RETRIEVAL" in text
    assert "Atomic | NOT BUILT" in text
    assert "Business | NOT BUILT" in text
    assert "Current | NOT BUILT" in text
    assert "Cash versus credit sales" in text
    assert "`NET_SALES`" in text
    assert "Production count default" in text
    assert "Cost semantics" in text
    assert "FX policy" in text
    assert "Tax semantics" in text


def test_all_source_gates_are_referenced() -> None:
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    adr_index = ADR_INDEX.read_text(encoding="utf-8")
    for gate in SOURCE_GATES:
        assert gate in architecture
        assert gate in architecture + adr_index


def test_machine_outputs_and_current_state() -> None:
    principles = _csv_rows(PRINCIPLES)
    gaps = _csv_rows(GAPS)
    product_model = _csv_rows(PRODUCT_MODEL)
    current = json.loads(CURRENT_STATE.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert len(principles) == 18
    assert len({row["principle_id"] for row in principles}) == 18
    assert len(gaps) == 17
    assert len({row["gap_id"] for row in gaps}) == 17
    assert {row["concept"] for row in product_model} == {
        "brand", "business_unit", "operating_model", "sales_channel",
        "production_site", "warehouse", "branch", "product_family",
    }
    assert current["postgres_catalog_database"] == "team360_telchi_ducklake"
    assert current["postgres_runtime_role"] == "team360_telchi_ducklake"
    assert current["dev_prod_logical_names_identical"] is True
    assert current["atomic"] == current["business"] == current["current"] == "NOT_BUILT"
    assert current["sap_accessed"] is False
    assert current["sap_write_count"] == 0
    assert summary["adr_total"] == 20
    assert summary["architecture_principles"] == 15
    assert summary["known_semantic_gaps"] == 6
    assert summary["architecture_consolidated_ready_for_atomic"] is True
    assert summary["stop_and_review"] is True


def test_no_secret_values_in_new_documents_or_evidence() -> None:
    paths = [ARCHITECTURE, ADR_INDEX, DECISIONS, PRINCIPLES, GAPS, PRODUCT_MODEL, CURRENT_STATE, SUMMARY]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden_value_patterns = (
        r"(?i)(?:password|passwd|pwd|token|api[_-]?key)\s*[:=]\s*[^\s<]+",
        r"(?i)(?:postgres|postgresql|hana|sap)://[^\s/]+:[^\s@]+@",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    )
    for pattern in forbidden_value_patterns:
        assert re.search(pattern, combined) is None, pattern
