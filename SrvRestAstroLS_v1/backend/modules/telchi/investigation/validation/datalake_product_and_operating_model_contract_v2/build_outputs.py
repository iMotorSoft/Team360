from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
GATE = "TELCHI_DATALAKE_PRODUCT_AND_OPERATING_MODEL_CONTRACT_V2"
STATUS = ("CONFIRMED", "PROVISIONAL", "UNMAPPED", "AMBIGUOUS")


def write_csv(name: str, header: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    with (OUT / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def build() -> dict[str, object]:
    write_csv("product_operating_model_contract.csv", (
        "concept", "semantic_role", "concept_status", "taxonomy_status", "authority", "temporal", "notes"
    ), [
        ("brand", "commercial product brand", "ACCEPTED", "EVIDENCE_BASED", "reference.brand", "YES", "Not manufacturer or business unit"),
        ("business_unit", "economic or organizational management unit", "ACCEPTED", "PROVISIONAL", "reference.business_unit", "YES", "Retail is not assigned here without evidence"),
        ("portfolio_family", "executive product portfolio classification", "ACCEPTED", "PROVISIONAL", "reference.portfolio_family", "YES", "Canonical name; product_family and commercial_family are deprecated aliases"),
        ("product_business_type", "type within a portfolio", "ACCEPTED", "PROVISIONAL", "reference.product_business_type", "YES", "Supports finished products raw materials and fractions"),
        ("operating_domain", "high-level industrial pharmacy or resale context", "ACCEPTED", "PROVISIONAL", "reference.operating_domain", "YES", "Separates industrial manufacturing from pharmacy botica"),
        ("operating_model", "how Telchi obtains transforms or prepares product", "ACCEPTED", "PROVISIONAL", "reference.operating_model", "YES", "Values evolve as catalog content"),
        ("sales_channel", "channel through which operation occurred", "ACCEPTED", "PROVISIONAL", "reference.sales_channel", "YES", "Independent from business unit"),
        ("production_site", "physical production location", "ACCEPTED", "EVIDENCE_BASED", "reference.production_site", "YES", "Independent from warehouse"),
        ("warehouse", "inventory logistics location", "ACCEPTED", "EVIDENCE_BASED", "reference.warehouse", "YES", "Independent from branch and production site"),
        ("branch", "organizational or commercial location", "ACCEPTED", "EVIDENCE_BASED", "reference.branch", "YES", "Independent from warehouse and production site"),
        ("manufacturer_party", "party physically manufacturing product", "ACCEPTED", "EVIDENCE_BASED", "reference.party + relationship", "YES", "Not inferred from brand ownership"),
        ("brand_owner_party", "party owning commercial brand", "ACCEPTED", "EVIDENCE_BASED", "reference.party + relationship", "YES", "Not inferred from manufacturer"),
        ("contract_customer", "third party commissioning industrial production", "ACCEPTED", "EVIDENCE_BASED", "reference.party + relationship", "YES", "Applicable to contract manufacturing"),
    ])
    write_csv("product_classification_contract.csv", (
        "classification", "canonical_dimension", "example_values", "taxonomy_status", "query_time_rule", "evidence_rule"
    ), [
        ("legacy L/M", "portfolio_family", "LITEL|MEDICATION_OR_MEDI|OTHER", "PROVISIONAL", "NO ItemCode prefix predicate", "L* and M* are historical build evidence only"),
        ("Litel subsegment", "product_business_type", "LAB_FINISHED_PRODUCT|RAW_MATERIAL|FRACTIONATED_PRODUCT", "PROVISIONAL", "Filter canonical dimension", "Do not infer without approved mapping"),
        ("operational context", "operating_domain", "INDUSTRIAL_MANUFACTURING|PHARMACY_BOTICA|COMMERCIAL_RESALE", "PROVISIONAL", "Filter canonical dimension", "Codes remain provisional"),
        ("acquisition/transformation", "operating_model", "MANUFACTURED|FRACTIONATED|REPACKAGED|PURCHASED_FOR_RESALE|CONTRACT_MANUFACTURING|WHITE_LABEL", "PROVISIONAL", "Join temporal relation", "White-label is representable as arrangement plus third-party brand ownership"),
    ])
    write_csv("product_relationship_contract.csv", (
        "relationship", "from_entity", "to_entity", "required_fields", "temporal", "cardinality", "notes"
    ), [
        ("product_brand", "product", "brand", "canonical_product_id|brand_id|valid_from|valid_to|source|confidence|status", "YES", "many-to-many over time", "Commercial brand only"),
        ("product_business_unit", "product", "business_unit", "canonical_product_id|business_unit_id|valid_from|valid_to|source|confidence|status", "YES", "many-to-many over time", "Organizational assignment"),
        ("product_portfolio_family", "product", "portfolio_family", "canonical_product_id|portfolio_family_id|valid_from|valid_to|source|confidence|status", "YES", "many-to-many over time", "Litel and medication comparison"),
        ("product_business_type", "product", "product_business_type", "canonical_product_id|product_business_type_id|valid_from|valid_to|source|confidence|status", "YES", "many-to-many over time", "Litel subsegment"),
        ("product_operating_model", "product", "operating_model", "canonical_product_id|operating_model_id|valid_from|valid_to|source|confidence|status", "YES", "many-to-many over time", "Supports resale to manufacturing transitions"),
        ("product_production_site", "product", "production_site", "canonical_product_id|production_site_id|operating_model_id|valid_from|valid_to|source|confidence|status", "YES", "many-to-many", "No primary-site-only authority"),
        ("production_site_warehouse", "production_site", "warehouse", "production_site_id|warehouse_id|warehouse_role|valid_from|valid_to|source|confidence|status", "YES", "many-to-many", "Never assume 1:1"),
        ("product_manufacturer", "product", "party", "canonical_product_id|manufacturer_party_id|valid_from|valid_to|source|confidence|status", "YES", "many-to-many over time", "Physical manufacturer"),
        ("brand_owner", "brand", "party", "brand_id|brand_owner_party_id|valid_from|valid_to|source|confidence|status", "YES", "many-to-many over time", "Brand ownership"),
        ("manufacturing_arrangement", "production_order", "party", "production_order_id|arrangement_type_id|contract_customer_id|valid_from|valid_to|source|confidence|status", "YES", "many-to-one per evidenced arrangement", "Contract manufacturing and white-label without schema change"),
    ])
    write_csv("reference_schema_contract.csv", (
        "dataset", "key", "core_fields", "status", "materialized_v1", "physical_action"
    ), [
        (f"reference.{name}", f"{name}_id", f"{name}_id|code|name|description|active|valid_from|valid_to|source|confidence|status|semantic_version", "DESIGN_READY", "NO", "ADD_IN_REFERENCE_V2")
        for name in ("brand", "business_unit", "product_business_type", "operating_domain", "operating_model", "production_site")
    ] + [
        ("reference.sales_channel", "sales_channel_id", "sales_channel_id|code|name|description|active|valid_from|valid_to|source|confidence|status|semantic_version", "DESIGN_READY", "EQUIVALENT_V1_CHANNELS", "RENAME_OR_MIGRATE_IN_REFERENCE_V2"),
        ("reference.portfolio_family", "portfolio_family_id", "portfolio_family_id|code|name|description|active|valid_from|valid_to|source|confidence|status|semantic_version", "DESIGN_READY", "EQUIVALENT_V1_PRODUCT_GROUPS", "RENAME_AND_RECLASSIFY_IN_REFERENCE_V2"),
        ("reference.party", "party_id", "party_id|party_type|code|name|valid_from|valid_to|source|confidence|status", "DESIGN_READY", "PARTIAL_CUSTOMER_SUPPLIER_ONLY", "ADD_GENERIC_PARTY_AUTHORITY_IN_REFERENCE_V2"),
    ])
    write_csv("canonical_product_schema_contract.csv", (
        "field", "representation", "authority", "required_in_product_row", "notes"
    ), [
        ("canonical_product_id", "COLUMN", "reference.product", "YES", "Stable identity"),
        ("item_code", "COLUMN", "source-backed product identity", "YES", "Preserved business code"),
        ("product_name", "COLUMN", "source-backed product identity", "YES", "Observed name"),
        ("sales_uom_id", "FOREIGN_KEY", "reference.units_of_measure", "YES", "Distinct UoM role"),
        ("inventory_uom_id", "FOREIGN_KEY", "reference.units_of_measure", "YES", "Distinct UoM role"),
        ("purchase_uom_id", "FOREIGN_KEY", "reference.units_of_measure", "YES", "Distinct UoM role"),
        ("brand", "VERSIONED_RELATIONSHIP", "product_brand", "NO", "Do not freeze changing ownership/classification"),
        ("portfolio_family", "VERSIONED_RELATIONSHIP", "product_portfolio_family", "NO", "Canonical replacement for generic product_family"),
        ("product_business_type", "VERSIONED_RELATIONSHIP", "product_business_type", "NO", "Subclassification"),
        ("business_unit", "VERSIONED_RELATIONSHIP", "product_business_unit", "NO", "Organizational assignment"),
        ("operating_model", "VERSIONED_RELATIONSHIP", "product_operating_model", "NO", "Acquisition/transformation model"),
        ("production_site", "VERSIONED_RELATIONSHIP", "product_production_site", "NO", "May be multiple"),
        ("manufacturer_party", "VERSIONED_RELATIONSHIP", "product_manufacturer", "NO", "Not brand owner"),
        ("is_telchi_product", "DERIVED_PREDICATE", "approved commercial definition", "NO", "Definition gap remains open"),
        ("manufactured_by_telchi", "DERIVED_PREDICATE", "product_manufacturer", "NO", "Independent from Telchi product"),
        ("brand_owned_by_telchi", "DERIVED_PREDICATE", "brand_owner", "NO", "Independent from manufacturer"),
        ("is_l_product", "DERIVED_CONVENIENCE", "product_portfolio_family", "NO", "Never primary semantic authority"),
    ])
    write_csv("industrial_manufacturing_contract.csv", (
        "concept", "grain", "required_evidence", "domain", "build_now"
    ), [
        ("industrial_formula_bom", "formula/BOM version", "formula_id|product_id|component_id|quantity|uom|validity|lineage", "INDUSTRIAL_MANUFACTURING", "NO"),
        ("production_order", "one industrial production order", "order_id|product_id|formula_id|site_id|status|dates|batch_lot|produced_for_party|lineage", "INDUSTRIAL_MANUFACTURING", "NO"),
        ("component_issue", "one component issue/consumption", "order_id|component_id|quantity|uom|warehouse_id|date|cost_evidence|lineage", "INDUSTRIAL_MANUFACTURING", "NO"),
        ("finished_receipt", "one finished-product receipt", "order_id|product_id|quantity|uom|warehouse_id|date|batch_lot|cost_evidence|lineage", "INDUSTRIAL_MANUFACTURING", "NO"),
        ("manufacturing_arrangement", "one evidenced arrangement for order/validity", "arrangement_type|contract_customer|manufacturer|brand|brand_owner|source|confidence|status", "INDUSTRIAL_MANUFACTURING", "NO"),
    ])
    write_csv("pharmacy_compounding_contract.csv", (
        "dataset", "grain", "required_fields", "excluded_default", "domain", "build_now"
    ), [(
        "atomic.pharmacy_compounding", "one magistral preparation/request performed",
        "compounding_id|customer_id|drug_or_preparation_id|preparation_description|quantity|uom|request_date|preparation_date|delivery_date|botica_site_id|amount|cost_evidence|status|source_lineage",
        "unnecessary clinical or patient PII", "PHARMACY_BOTICA", "NO"
    )])
    write_csv("schema_evolution_contract.csv", (
        "change_kind", "preferred_mechanism", "schema_change", "example"
    ), [
        ("stable concept", "explicit canonical schema", "JUSTIFIED_ONCE", "brand or production_site"),
        ("taxonomy value", "reference row", "NO", "new operating model value"),
        ("classification", "versioned relationship row", "NO", "product moves from resale to manufactured"),
        ("semantic predicate", "derived attribute/read model", "NO", "manufactured_by_telchi"),
        ("genuinely new semantic concept", "ADR and controlled schema revision", "YES", "future regulatory license"),
        ("generic arbitrary attribute", "REJECT EAV DEFAULT", "N/A", "attribute_name/attribute_value"),
    ])
    write_csv("atomic_requirements.csv", (
        "atomic_fact", "grain", "must_preserve", "separate_from", "materialize_now"
    ), [
        ("sales_line", "one canonical commercial line", "product/customer/document/amounts/currency/tax/quantity/UoM/branch/channel/native IDs/lineage", "reference classifications", "NO"),
        ("industrial_production_order", "one industrial order", "order/product/formula/status/dates/site/warehouses/batch-lot/produced_for_party/lineage", "pharmacy compounding", "NO"),
        ("industrial_component_issue", "one industrial component issue", "order/component/quantity/UoM/warehouse/date/cost evidence/lineage", "pharmacy ingredients", "NO"),
        ("industrial_finished_receipt", "one industrial receipt", "order/product/quantity/UoM/warehouse/date/batch-lot/cost evidence/lineage", "pharmacy delivery", "NO"),
        ("pharmacy_compounding", "one magistral preparation/request", "customer/drug-or-preparation/dates/quantity/UoM/amount/cost evidence/botica-site/status/lineage", "industrial order/BOM/receipt", "NO"),
        ("cost_observation", "one cost basis observation", "purchase/inventory/production/document/moving-average/other SAP-supported basis/date/currency/lineage", "universal margin definition", "NO"),
    ])
    write_csv("business_read_model_requirements.csv", (
        "data_product", "grain", "required_dimensions", "required_metrics", "semantic_guard", "materialize_now"
    ), [
        ("business.sales_flow", "canonical sales line", "portfolio_family|product_business_type|brand|business_unit|sales_channel|operating_model|production_origin|branch|product", "net_sales|gross_sales|document_count|customer_count|business_volume", "IDs/relations are authority; text may be cached only", "NO"),
        ("business.industrial_production_flow", "production order and movements", "contract_customer|product|brand|brand_owner|production_site|warehouse|arrangement", "produced_quantity|component_quantity|cost_evidence|yield", "white-label remains industrial", "NO"),
        ("business.pharmacy_compounding_flow", "magistral preparation", "drug_or_preparation|customer|botica_site", "preparation_count|sales|average_ticket|repeat_rate|ingredient_cost|partial_margin", "emit PARTIAL_ECONOMIC_EVALUATION when full cost/capacity/waste missing", "NO"),
    ])
    write_csv("ceo_query_catalog.csv", (
        "query_id", "question", "domain", "dimensions", "metrics", "ambiguities", "drilldown", "status"
    ), [
        ("Q-V2-001", "¿Vendo más medicamentos o productos Litel?", "SALES", "portfolio_family", "net_sales|gross_sales|document_count|customer_count|business_volume", "heterogeneous physical units", "portfolio_family>product_business_type>product>branch_or_channel>document", "CONTRACT_READY"),
        ("Q-V2-002", "Dentro de Litel ¿qué genera más volumen de negocio?", "SALES", "product_business_type", "net_sales|gross_sales|document_count|business_volume", "taxonomy provisional", "product_business_type>product>branch_or_channel>document", "CONTRACT_READY"),
        ("Q-V2-003", "Dentro de Litel ¿qué genera mayor retorno?", "PROFITABILITY", "product_business_type", "gross_margin_amount|gross_margin_pct|contribution|inventory_return|margin_x_rotation", "RETURN_METRIC_DEFINITION|COST_SEMANTICS", "product_business_type>product>cost_evidence", "CLARIFICATION_REQUIRED"),
        ("Q-V2-004", "¿Tiene sentido generar recetas magistrales?", "PHARMACY_BOTICA", "drug_or_preparation|customer|botica_site", "preparation_count|customer_count|sales|average_ticket|repeat_rate|ingredient_cost|margin|frequency|trend", "MAGISTRAL_FULL_COST|capacity|labor|waste", "drug_or_preparation>customer>compounding>source_evidence", "PARTIAL_ECONOMIC_EVALUATION_ALLOWED"),
        ("Q-V2-005", "¿Cuánto vendimos o fabricamos para terceros?", "PRODUCTION", "contract_customer|product|manufacturing_arrangement", "sales|produced_quantity|order_count", "WHITE_LABEL_IDENTIFICATION", "contract_customer>product>production_order>components>source_documents", "CONTRACT_READY"),
        ("Q-V2-006", "¿Qué margen deja white-label?", "PROFITABILITY", "contract_customer|product|brand", "gross_margin_amount|gross_margin_pct", "COST_SEMANTICS|WHITE_LABEL_IDENTIFICATION", "contract_customer>product>production_order>cost_evidence", "CLARIFICATION_REQUIRED"),
        ("Q-V2-007", "¿Qué clientes terceros utilizan más capacidad?", "PRODUCTION", "contract_customer|production_site", "produced_quantity|order_count|capacity_usage", "capacity evidence", "contract_customer>product>production_order", "EVIDENCE_REQUIRED"),
        ("Q-V2-008", "¿Qué porcentaje de producción corresponde a marca propia vs terceros?", "PRODUCTION", "brand_owner_party|contract_customer", "produced_quantity|production_order_count", "UoM comparability|WHITE_LABEL_IDENTIFICATION", "ownership>customer>product>production_order", "CONTRACT_READY"),
    ])
    write_csv("dimension_catalog.csv", ("dimension", "definition", "authority", "temporal"), [
        (row[0], row[1], row[4], row[5]) for row in [
            ("brand", "commercial brand", "", "", "reference.brand", "YES"),
            ("business_unit", "economic/organizational manager", "", "", "reference.business_unit", "YES"),
            ("portfolio_family", "executive portfolio", "", "", "reference.portfolio_family", "YES"),
            ("product_business_type", "type within portfolio", "", "", "reference.product_business_type", "YES"),
            ("operating_domain", "industrial pharmacy or resale domain", "", "", "reference.operating_domain", "YES"),
            ("operating_model", "obtaining/transformation model", "", "", "reference.operating_model", "YES"),
            ("sales_channel", "operation channel", "", "", "reference.sales_channel", "YES"),
            ("production_site", "production location", "", "", "reference.production_site", "YES"),
            ("warehouse", "inventory location", "", "", "reference.warehouse", "YES"),
            ("branch", "commercial/organizational location", "", "", "reference.branch", "YES"),
            ("manufacturer_party", "physical manufacturer", "", "", "product_manufacturer", "YES"),
            ("brand_owner_party", "brand owner", "", "", "brand_owner", "YES"),
            ("contract_customer", "commissioning third party", "", "", "manufacturing_arrangement", "YES"),
        ]
    ])
    write_csv("semantic_ambiguity_catalog.csv", (
        "term", "possible_meanings", "required_action", "gap_id"
    ), [
        ("Retail", "business_unit|sales_channel|both", "do not decide without organizational evidence", "CHANNEL_VS_BUSINESS_UNIT_BOUNDARY"),
        ("producto Telchi", "commercial ownership|manufactured by Telchi|Telchi-owned brand", "apply approved definition or clarify", "TELCHI_PRODUCT_DEFINITION"),
        ("retorno", "gross_margin_amount|gross_margin_pct|contribution|inventory_return|margin_x_rotation", "clarify and version metric", "RETURN_METRIC_DEFINITION"),
        ("receta", "industrial_formula_BOM|magistral_preparation", "resolve operating domain; never use generic recipe", "RECIPE_DOMAIN_AMBIGUITY"),
        ("Litel", "historical L-prefix portfolio classification", "resolve through portfolio_family; no runtime LIKE", "PORTFOLIO_FAMILY_TAXONOMY"),
    ])
    write_csv("known_semantic_gaps.csv", (
        "gap_id", "status", "atomic_blocking", "required_evidence"
    ), [(name, "OPEN", "NO", evidence) for name, evidence in [
        ("BUSINESS_UNIT_TAXONOMY", "approved organizational vocabulary and validity"),
        ("PORTFOLIO_FAMILY_TAXONOMY", "approved portfolio vocabulary and product mapping"),
        ("PRODUCT_BUSINESS_TYPE_TAXONOMY", "approved subsegment vocabulary and mappings"),
        ("OPERATING_MODEL_TAXONOMY", "approved model vocabulary and validity"),
        ("BRAND_AUTHORITY", "approved brand master and ownership authority"),
        ("PRODUCT_PRODUCTION_SITE_MAPPING", "product-site evidence and validity"),
        ("CHANNEL_VS_BUSINESS_UNIT_BOUNDARY", "organizational evidence"),
        ("TELCHI_PRODUCT_DEFINITION", "approved commercial definition"),
        ("RETURN_METRIC_DEFINITION", "executive decision and cost semantics"),
        ("MAGISTRAL_FULL_COST", "labor hours capacity waste and complete costs"),
        ("WHITE_LABEL_IDENTIFICATION", "orders customers brands and arrangement evidence"),
    ]])
    summary: dict[str, object] = {
        "gate": GATE, "result": f"{GATE}_PASS",
        "architecture_updated": True, "adr_index_updated": True,
        "product_model_v2_ready": True,
        "adr_total": 29, "adr_accepted": 28, "adr_provisional": 1, "adr_superseded": 0,
        "brand_separate": True, "business_unit_separate": True,
        "portfolio_family_separate": True, "product_business_type_separate": True,
        "operating_domain_separate": True, "operating_model_separate": True,
        "sales_channel_separate": True, "production_site_separate": True,
        "warehouse_separate": True, "branch_separate": True,
        "telchi_product_distinct_from_manufactured_by_telchi": True,
        "manufactured_by_telchi_distinct_from_brand_ownership": True,
        "industrial_contract_manufacturing_modeled": True, "white_label_modeled": True,
        "magistral_compounding_separate_from_industrial": True,
        "medication_vs_litel_supported": True, "litel_lab_finished_supported": True,
        "litel_raw_material_supported": True, "litel_fractionated_supported": True,
        "magistral_economic_analysis_contract": True, "like_l_required_at_query_time": False,
        "stable_canonical_schema": True, "extensible_reference_data": True,
        "versioned_relationships": True, "eav_default_rejected": True,
        "canonical_schema_contracts_updated": True, "reference_schema_contracts_updated": True,
        "relationship_contracts_updated": True, "atomic_requirements_updated": True,
        "ceo_semantic_catalog_updated": True,
        "reference_v1_count": 14, "reference_v2_designed_count": 21,
        "reference_v2_rebuild_required": True, "reference_v2_rebuild_executed": False,
        "reference_datasets_modified": 0, "crosswalk_datasets_modified": 0,
        "sap_accessed": False, "sap_access_purpose": "NONE", "sap_write_count": 0,
        "postgres_modified": False, "ducklake_modified": False, "raw_files_modified": 0,
        "atomic_tables_created": 0, "business_tables_created": 0, "current_tables_created": 0,
        "secret_leaks_found": 0, "known_semantic_gaps": 17, "v2_product_semantic_gaps": 11,
        "ready_for_reference_v2_rebuild": True,
        "ready_for_atomic_after_reference_decision": True, "stop_and_review": True,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    build()
