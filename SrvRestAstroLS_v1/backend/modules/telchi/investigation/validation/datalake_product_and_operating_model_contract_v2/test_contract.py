from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .build_outputs import GATE, build

HERE = Path(__file__).resolve().parent
INVESTIGATION = HERE.parents[1]
ARCHITECTURE = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ARCHITECTURE_V1.md"
ADR_INDEX = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ADR_INDEX_V1.md"
REGISTRY = INVESTIGATION / "validation" / "datalake_architecture_and_adr_consolidation_v1" / "architecture_decisions.csv"


def rows(name: str) -> list[dict[str, str]]:
    with (HERE / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_build_is_reproducible_and_does_not_materialize_data() -> None:
    summary = build()
    assert summary["gate"] == GATE
    assert summary["result"] == f"{GATE}_PASS"
    assert summary["reference_v2_rebuild_required"] is True
    assert summary["reference_v2_rebuild_executed"] is False
    for key in ("reference_datasets_modified", "crosswalk_datasets_modified", "raw_files_modified", "atomic_tables_created", "business_tables_created", "current_tables_created", "sap_write_count", "secret_leaks_found"):
        assert summary[key] == 0
    assert summary["postgres_modified"] is summary["ducklake_modified"] is False
    assert not list(HERE.glob("*.parquet"))


def test_product_axes_are_separate_and_taxonomies_remain_provisional() -> None:
    concepts = {row["concept"]: row for row in rows("product_operating_model_contract.csv")}
    expected = {"brand", "business_unit", "portfolio_family", "product_business_type", "operating_domain", "operating_model", "sales_channel", "production_site", "warehouse", "branch", "manufacturer_party", "brand_owner_party", "contract_customer"}
    assert set(concepts) == expected
    for concept in ("business_unit", "portfolio_family", "product_business_type", "operating_domain", "operating_model", "sales_channel"):
        assert concepts[concept]["taxonomy_status"] == "PROVISIONAL"
    roles = {concepts[name]["semantic_role"] for name in expected}
    assert len(roles) == len(expected)


def test_classification_uses_reference_content_not_runtime_prefix_or_flags() -> None:
    classifications = {row["canonical_dimension"]: row for row in rows("product_classification_contract.csv")}
    assert classifications["portfolio_family"]["query_time_rule"] == "NO ItemCode prefix predicate"
    assert "L* and M*" in classifications["portfolio_family"]["evidence_rule"]
    schema = {row["field"]: row for row in rows("canonical_product_schema_contract.csv")}
    assert schema["is_l_product"]["representation"] == "DERIVED_CONVENIENCE"
    for field in ("is_telchi_product", "manufactured_by_telchi", "brand_owned_by_telchi"):
        assert schema[field]["representation"] == "DERIVED_PREDICATE"
        assert schema[field]["required_in_product_row"] == "NO"
    evolution = {row["change_kind"]: row for row in rows("schema_evolution_contract.csv")}
    assert evolution["generic arbitrary attribute"]["preferred_mechanism"] == "REJECT EAV DEFAULT"
    assert evolution["taxonomy value"]["schema_change"] == "NO"


def test_versioned_relationships_cover_sites_ownership_and_white_label() -> None:
    relationships = {row["relationship"]: row for row in rows("product_relationship_contract.csv")}
    required = {"product_brand", "product_business_unit", "product_portfolio_family", "product_business_type", "product_operating_model", "product_production_site", "production_site_warehouse", "product_manufacturer", "brand_owner", "manufacturing_arrangement"}
    assert required <= relationships.keys()
    assert all(relationships[name]["temporal"] == "YES" for name in required)
    assert "many-to-many" in relationships["production_site_warehouse"]["cardinality"]
    assert "without schema change" in relationships["manufacturing_arrangement"]["notes"]
    for relationship in relationships.values():
        if relationship["relationship"] not in {"manufacturing_arrangement"}:
            assert all(field in relationship["required_fields"].split("|") for field in ("source", "confidence", "status"))


def test_industrial_and_magistral_are_distinct_atomic_contracts() -> None:
    industrial = rows("industrial_manufacturing_contract.csv")
    pharmacy = rows("pharmacy_compounding_contract.csv")[0]
    assert industrial and all(row["domain"] == "INDUSTRIAL_MANUFACTURING" for row in industrial)
    assert pharmacy["domain"] == "PHARMACY_BOTICA"
    assert pharmacy["dataset"] == "atomic.pharmacy_compounding"
    assert "unnecessary clinical or patient PII" == pharmacy["excluded_default"]
    atomic = {row["atomic_fact"]: row for row in rows("atomic_requirements.csv")}
    assert atomic["industrial_production_order"]["separate_from"] == "pharmacy compounding"
    assert "industrial order" in atomic["pharmacy_compounding"]["separate_from"]
    assert all(row["materialize_now"] == "NO" for row in atomic.values())


def test_ceo_catalog_contains_required_decisions_and_partial_evaluation() -> None:
    catalog = {row["query_id"]: row for row in rows("ceo_query_catalog.csv")}
    assert "medicamentos o productos Litel" in catalog["Q-V2-001"]["question"]
    assert catalog["Q-V2-001"]["dimensions"] == "portfolio_family"
    assert catalog["Q-V2-002"]["dimensions"] == "product_business_type"
    assert "RETURN_METRIC_DEFINITION" in catalog["Q-V2-003"]["ambiguities"]
    assert catalog["Q-V2-004"]["status"] == "PARTIAL_ECONOMIC_EVALUATION_ALLOWED"
    assert any("white-label" in row["question"] for row in catalog.values())
    dimensions = {row["dimension"] for row in rows("dimension_catalog.csv")}
    assert {"brand", "business_unit", "portfolio_family", "product_business_type", "operating_domain", "operating_model", "sales_channel", "production_site", "warehouse", "branch", "manufacturer_party", "brand_owner_party", "contract_customer"} <= dimensions


def test_reference_v2_impact_and_open_gaps_are_explicit() -> None:
    refs = {row["dataset"]: row for row in rows("reference_schema_contract.csv")}
    assert refs["reference.portfolio_family"]["materialized_v1"] == "EQUIVALENT_V1_PRODUCT_GROUPS"
    assert refs["reference.sales_channel"]["materialized_v1"] == "EQUIVALENT_V1_CHANNELS"
    assert refs["reference.brand"]["physical_action"] == "ADD_IN_REFERENCE_V2"
    gaps = {row["gap_id"] for row in rows("known_semantic_gaps.csv")}
    assert gaps == {"BUSINESS_UNIT_TAXONOMY", "PORTFOLIO_FAMILY_TAXONOMY", "PRODUCT_BUSINESS_TYPE_TAXONOMY", "OPERATING_MODEL_TAXONOMY", "BRAND_AUTHORITY", "PRODUCT_PRODUCTION_SITE_MAPPING", "CHANNEL_VS_BUSINESS_UNIT_BOUNDARY", "TELCHI_PRODUCT_DEFINITION", "RETURN_METRIC_DEFINITION", "MAGISTRAL_FULL_COST", "WHITE_LABEL_IDENTIFICATION"}


def test_adrs_and_living_architecture_are_consistent() -> None:
    decisions = rows_from(REGISTRY)
    assert len(decisions) == 29
    assert sum(row["status"] == "ACCEPTED" for row in decisions) == 28
    assert sum(row["status"] == "PROVISIONAL" for row in decisions) == 1
    adr_text = ADR_INDEX.read_text(encoding="utf-8")
    for number in range(26, 30):
        assert f"## ADR-{number:03d} —" in adr_text
    assert "No se crea un ADR-030 redundante" in adr_text
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in ("PRODUCT_AND_OPERATING_MODEL_CONTRACT_V2", "portfolio_family", "PHARMACY_BOTICA", "PARTIAL_ECONOMIC_EVALUATION", "REFERENCE_V2_REBUILD_REQUIRED=YES", "LIKE_L_REQUIRED_AT_QUERY_TIME=NO"):
        assert phrase in architecture


def rows_from(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_contract_artifacts_contain_no_obvious_secret_values() -> None:
    paths = list(HERE.glob("*.csv")) + [HERE / "summary.json", ARCHITECTURE, ADR_INDEX]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for pattern in (r"(?i)(?:password|passwd|pwd|token|api[_-]?key)\s*[:=]\s*[^\s<]+", r"(?i)(?:postgres|postgresql|hana|sap)://[^\s/]+:[^\s@]+@", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"):
        assert re.search(pattern, combined) is None
