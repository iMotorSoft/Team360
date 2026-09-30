from __future__ import annotations

import csv
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
INVESTIGATION = HERE.parents[1]
ARCHITECTURE = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ARCHITECTURE_V1.md"
ADR_INDEX = INVESTIGATION / "docs" / "TELCHI_DATALAKE_ADR_INDEX_V1.md"
ARCHITECTURE_GATE = INVESTIGATION / "validation" / "datalake_architecture_and_adr_consolidation_v1"
DECISIONS = ARCHITECTURE_GATE / "architecture_decisions.csv"
PRINCIPLES = ARCHITECTURE_GATE / "architecture_principles.csv"
GAPS = ARCHITECTURE_GATE / "known_semantic_gaps.csv"
PRODUCT_MODEL = ARCHITECTURE_GATE / "product_operating_model_contract.csv"
SUMMARY = HERE / "summary.json"


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_adrs_021_to_029_exist_with_expected_statuses() -> None:
    text = ADR_INDEX.read_text(encoding="utf-8")
    rows = {row["adr_id"]: row for row in _csv_rows(DECISIONS)}
    assert len(rows) == 29
    assert sum(row["status"] == "ACCEPTED" for row in rows.values()) == 28
    assert sum(row["status"] == "PROVISIONAL" for row in rows.values()) == 1
    for number in range(21, 30):
        adr_id = f"ADR-{number:03d}"
        assert f"## {adr_id} —" in text
        assert adr_id in rows
    assert rows["ADR-024"]["status"] == "PROVISIONAL"
    assert rows["ADR-025"]["status"] == "ACCEPTED"
    # The index is cumulative: this gate introduced ADR-021..029 and later
    # Data Lake gates extended the same canonical index through ADR-038.
    assert "ADR_TOTAL=38" in text
    assert "ADR_ACCEPTED=37" in text
    assert "ADR_PROVISIONAL=1" in text


def test_product_concepts_are_distinct_and_taxonomies_are_not_fabricated() -> None:
    rows = {row["concept"]: row for row in _csv_rows(PRODUCT_MODEL)}
    expected = {
        "brand", "business_unit", "operating_model", "sales_channel",
        "production_site", "warehouse", "branch", "product_family",
    }
    assert set(rows) == expected
    assert rows["business_unit"]["status"] == "CONCEPT_CONFIRMED_TAXONOMY_PROVISIONAL"
    assert rows["operating_model"]["status"] == "CONCEPT_CONFIRMED_TAXONOMY_PROVISIONAL"
    assert rows["production_site"]["semantic_role"] != rows["warehouse"]["semantic_role"]
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    assert "Brand | Identidad comercial" in architecture
    assert "Business unit | Unidad económica" in architecture
    assert "Operating model | Forma en que" in architecture
    assert "Sales / distribution channel | Forma de comercialización" in architecture
    assert "`production_site != warehouse`" in architecture
    assert "`RETAIL` puede resultar canal, business unit o ambos" in architecture


def test_l_product_is_materialized_without_implying_operating_attributes() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "`L* → Litel`, `M* → Medi`" in text
    assert "`ItemCode LIKE 'L%'` sigue siendo evidencia histórica" in text
    assert "no un predicado de runtime" in text
    assert "`LIKE_L_REQUIRED_AT_QUERY_TIME=NO`" in text
    assert "El flag L no implica marca, pertenencia Telchi, business unit, operating model ni sitio productivo" in text
    assert "`is_telchi_product`, `is_l_product`, `brand`, `business_unit`, `operating_model`" in text


def test_stable_schema_reference_extensibility_and_no_generic_eav() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    principles = {row["name"] for row in _csv_rows(PRINCIPLES)}
    assert "PREFER CONTENT EVOLUTION OVER SCHEMA EVOLUTION" in principles
    assert "VERSIONED RELATIONSHIPS" in principles
    assert "NO GENERIC EAV BY DEFAULT" in principles
    assert "STABLE CANONICAL SCHEMA + EXTENSIBLE REFERENCE DATA" in text
    assert "preferir evolución de contenido sobre evolución de schema" in text
    assert "`attribute_name` y `attribute_value`" in text
    assert "`CONTRACT_PACKAGING` debe agregarse como contenido" in text
    assert "DuckLake soporta schema evolution" in text
    assert "concepto semántico genuinamente nuevo" in text


def test_temporal_product_site_relationship_and_read_model_boundaries() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for field in (
        "`canonical_product_id`", "`production_site_id`", "`operating_model_id`",
        "`valid_from`", "`valid_to`", "`status`", "`source`", "`confidence`",
    ):
        assert field in text
    for status in ("`CONFIRMED`", "`UNMAPPED`", "`AMBIGUOUS`", "`PROVISIONAL`"):
        assert status in text
    assert "fechas desconocidas quedan `NULL`, nunca ficticias" in text
    assert "La autoridad de clasificación reside en reference y relationships" in text
    assert "business/current son read models derivados" in text


def test_semantic_content_gaps_are_explicit_not_architecture_failures() -> None:
    rows = {row["name"]: row for row in _csv_rows(GAPS)}
    for gap in (
        "BUSINESS_UNIT_TAXONOMY",
        "OPERATING_MODEL_TAXONOMY",
        "PRODUCT_PRODUCTION_SITE_MAPPING",
        "BRAND_AUTHORITY",
        "CHANNEL_VS_BUSINESS_UNIT_BOUNDARY",
    ):
        assert gap in rows
        assert rows[gap]["atomic_blocking"] == "NO"


def test_no_runtime_or_data_mutations_and_stop_condition() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["reference_datasets_modified"] == 0
    assert summary["crosswalk_datasets_modified"] == 0
    assert summary["data_files_modified"] == 0
    assert summary["atomic_tables_created"] == 0
    assert summary["business_tables_created"] == 0
    assert summary["current_tables_created"] == 0
    assert summary["sap_accessed"] is False
    assert summary["sap_write_count"] == 0
    assert summary["postgres_modified"] is False
    assert summary["ducklake_modified"] is False
    assert summary["product_operating_model_contract_ready"] is True
    assert summary["stop_and_review"] is True


def test_no_secrets_in_contract_artifacts() -> None:
    paths = [ARCHITECTURE, ADR_INDEX, DECISIONS, PRINCIPLES, GAPS, PRODUCT_MODEL, SUMMARY]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden = (
        r"(?i)(?:password|passwd|pwd|token|api[_-]?key)\s*[:=]\s*[^\s<]+",
        r"(?i)(?:postgres|postgresql|hana|sap)://[^\s/]+:[^\s@]+@",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    )
    for pattern in forbidden:
        assert re.search(pattern, combined) is None, pattern
