from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_ROOT = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi"
LEGACY_ROOT = "/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS"
GATE = "TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS"

STR = "string"
BOOL = "bool"
I32 = "int32"
I64 = "int64"
DATE = "date32"
TS = "timestamp[us,UTC]"
QTY = "decimal128(38,12)"
MONEY = "decimal128(38,6)"
RATE = "decimal128(38,12)"

LAYOUT = [
    ("raw/legacy/parquet", "PRESERVED_SOURCE", "Byte-identical legacy Parquet mirror; preserve source-relative directories and filenames.", "KEEP"),
    ("raw/legacy/reference_sources", "PRESERVED_SOURCE", "Approved reference originals such as almacenOficina.xlsx; copied only by a dedicated later gate.", "KEEP"),
    ("raw/legacy/auxiliary_sources", "PRESERVED_SOURCE", "Approved CSV or code provenance; temporary files are inventory-only and excluded by default.", "KEEP"),
    ("raw/sap/table_extract", "PRESERVED_SOURCE", "Immutable SAP table extraction runs, distinguished from query extracts.", "KEEP"),
    ("raw/sap/query_extract", "PRESERVED_SOURCE", "Immutable named SAP query extraction runs with query hash and parameters in manifests.", "KEEP"),
    ("reference", "REFERENCE", "Normalized, version-aware dimensions and controlled vocabularies.", "KEEP"),
    ("crosswalk", "REFERENCE", "Versioned source-native to canonical identity mappings, including UNMAPPED.", "KEEP"),
    ("atomic", "REBUILDABLE", "Canonical facts at minimum justified grain.", "KEEP"),
    ("business", "REBUILDABLE", "Versioned denormalized read models with physical lineage.", "KEEP"),
    ("manifests/legacy_mirror", "METADATA", "One manifest row per legacy source file and verification attempt.", "KEEP"),
    ("manifests/runs", "METADATA", "SAP extraction, atomic build, business build and snapshot run manifests.", "KEEP"),
    ("manifests/watermarks", "METADATA", "Per-dataset successful and attempted incremental cursors.", "KEEP"),
    ("manifests/registry", "METADATA", "Versioned JSON dataset registry generated from the CSV authority.", "KEEP"),
    ("staging", "EPHEMERAL", "Use process-local temporary storage only; do not make a durable lake layer.", "ELIMINATE_AS_DURABLE_LAYER"),
    ("snapshots", "REDUNDANT", "Represent snapshot semantics in named atomic/business datasets, not a generic duplicate layer.", "ELIMINATE"),
    ("decision", "DEFERRED", "No justified V1 decision data product; add only with a concrete consumer and grain.", "ELIMINATE_FOR_V1"),
]

# id, layer, domain, grain, key, sources, kind, partition, sort, incremental, security, scope, sensitive, inputs
DATASETS: list[dict[str, str]] = []

def ds(dataset_id: str, layer: str, domain: str, grain: str, key: str, sources: str,
       kind: str, partition: str, sort: str, incremental: str, security: str,
       scope: str, sensitive: str, inputs: str, classification: str = "REBUILDABLE",
       path: str | None = None, lineage_profile: str = "") -> None:
    DATASETS.append({
        "dataset_id": dataset_id, "layer": layer, "business_domain": domain, "grain": grain,
        "primary_candidate_key": key, "source_systems": sources, "data_kind": kind,
        "partitioning": partition, "sort_order": sort, "incremental_strategy": incremental,
        "security_domain": security, "scope_columns": scope, "sensitive_columns": sensitive,
        "inputs": inputs, "rebuild_class": classification, "schema_version": "1.0.0",
        "semantic_version": "1.0.0", "transformation_version": "NONE" if classification == "PRESERVED_SOURCE" else "physical-design-v1",
        "path": path or f"{layer}/{dataset_id}", "lineage_profile": lineage_profile or kind.lower(),
        "format": "PARQUET", "compression": "SOURCE_PRESERVED" if dataset_id == "legacy_parquet_mirror" else "ZSTD", "active": "YES",
    })

# Raw entries are registry-level dataset families. Their payload schema remains source-preserved.
ds("legacy_parquet_mirror", "raw", "transversal", "one source file preserved at its relative path", "source_relative_path", "LEGACY_DS", "SOURCE_FILE", "NO_PARTITION", "SOURCE_ORDER", "IMMUTABLE_COPY", "source", "", "", "", "PRESERVED_SOURCE", "raw/legacy/parquet", "source_file")
ds("sap_table_extracts", "raw", "transversal", "one immutable extraction row in a named SAP table run", "extract_id+source_native_key+observation_sequence", "SAP_HANA", "SOURCE_ROW", "EXTRACTION_DATE", "source_native_key", "DATASET_SPECIFIC", "source", "", "", "", "PRESERVED_SOURCE", "raw/sap/table_extract", "sap_raw")
ds("sap_query_extracts", "raw", "transversal", "one immutable result row in a named SAP query run", "extract_id+query_row_key+observation_sequence", "SAP_HANA", "SOURCE_ROW", "EXTRACTION_DATE", "query_row_key", "DATASET_SPECIFIC", "source", "", "", "", "PRESERVED_SOURCE", "raw/sap/query_extract", "sap_raw")

REFERENCE = [
    ("products", "inventory", "one product identity version", "product_id+valid_from", "product_id", "standard_cost;last_purchase_price"),
    ("product_groups", "inventory", "one product-group identity version", "product_group_id+valid_from", "product_group_id", ""),
    ("customers", "sales;credit", "one customer identity version", "customer_id+valid_from", "customer_id", "credit_limit;tax_id"),
    ("suppliers", "purchases", "one supplier identity version", "supplier_id+valid_from", "supplier_id", "tax_id;payment_terms"),
    ("warehouses", "inventory", "one warehouse identity version", "warehouse_id+valid_from", "warehouse_id", ""),
    ("branches", "organization", "one branch identity version", "branch_id+valid_from", "branch_id", ""),
    ("document_types", "configuration", "one document-type code version", "document_type+valid_from", "company_id", ""),
    ("payment_terms", "credit", "one payment-term version", "payment_term_id+valid_from", "branch_id", "credit_days"),
    ("channels", "sales", "one sales-channel version", "channel_id+valid_from", "branch_id", ""),
    ("units_of_measure", "inventory", "one unit-of-measure version", "unit_of_measure_id+valid_from", "company_id", ""),
    ("warehouse_roles", "inventory", "one warehouse-role version", "warehouse_role_id+valid_from", "warehouse_id", ""),
    ("currencies", "finance", "one currency code version", "currency_code+valid_from", "legal_entity_id", ""),
    ("users", "users", "one user identity version", "user_id+valid_from", "organizational_scope", "user_name"),
    ("salespersons", "sales", "one salesperson identity version", "salesperson_id+valid_from", "salesperson_id;branch_id", "salesperson_name"),
]
for name, domain, grain, key, scope, sensitive in REFERENCE:
    ds(name, "reference", domain, grain, key, "SAP_HANA;LEGACY_DS;EXTERNAL_FILES", "REFERENCE", "NO_PARTITION", f"{key.split('+')[0]},valid_from", "SNAPSHOT_UPSERT_SCD2", domain, scope, sensitive, "raw/sap;raw/legacy", "REFERENCE", lineage_profile="reference")

for entity in ("product", "customer", "supplier", "warehouse", "branch", "salesperson", "user"):
    ds(f"{entity}_crosswalk", "crosswalk", "identity", "one source-native identity mapping validity interval",
       "source_system+source_native_id+valid_from", "SAP_HANA;LEGACY_DS;EXTERNAL_FILES", "REFERENCE",
       "NO_PARTITION", "source_system,source_native_id,valid_from", "SNAPSHOT_UPSERT_SCD2", "identity",
       "canonical_id", "", f"reference/{entity}s;raw/legacy;raw/sap", "REFERENCE", lineage_profile="crosswalk")
ds("warehouse_branch_mapping", "crosswalk", "organization", "one warehouse to branch mapping validity interval",
   "warehouse_id+branch_id+valid_from", "EXTERNAL_FILES;SAP_HANA;LEGACY_DS", "STATE", "NO_PARTITION",
   "warehouse_id,valid_from", "SNAPSHOT_UPSERT_SCD2", "inventory;sales", "warehouse_id;branch_id", "",
   "raw/legacy/reference_sources;reference/warehouses;reference/branches", "REFERENCE", lineage_profile="crosswalk")

ATOMIC = [
    ("sales_documents", "sales", "one sales document", "source_system+source_document_type+source_document_id", "DOCUMENT_WATERMARK", "posting_year_month", "customer_id;branch_id;salesperson_id", "gross_amount;open_amount"),
    ("sales_lines", "sales", "one sales document line", "source_system+source_document_type+source_document_id+source_line_id", "DOCUMENT_WATERMARK", "posting_year_month", "branch_id;salesperson_id", "quantity;unit_price;line_amount;cost_amount"),
    ("credit_notes", "sales;credit", "one credit-note document", "source_system+source_document_id", "DOCUMENT_WATERMARK", "posting_year_month", "customer_id;branch_id", "gross_amount"),
    ("credit_note_lines", "sales;credit", "one credit-note document line", "source_system+source_document_id+source_line_id", "DOCUMENT_WATERMARK", "posting_year_month", "branch_id;salesperson_id", "quantity;line_amount;cost_amount"),
    ("inventory_movements", "inventory", "one inventory transaction line or declared fallback event", "source_system+source_transaction_id+source_line_id", "UPDATE_WATERMARK", "event_year_month", "warehouse_id", "quantity_in;quantity_out;unit_cost;total_cost"),
    ("stock_snapshots", "inventory", "one product × warehouse × snapshot_at", "product_id+warehouse_id+snapshot_at", "SNAPSHOT_WATERMARK", "snapshot_date", "warehouse_id", "on_hand;committed;ordered;available"),
    ("purchase_requests", "purchases", "one purchase-request line", "source_system+source_document_id+source_line_id", "UPDATE_WATERMARK", "document_year_month", "branch_id;warehouse_id", "quantity;estimated_amount"),
    ("purchase_orders", "purchases", "one purchase-order line", "source_system+source_document_id+source_line_id", "UPDATE_WATERMARK", "document_year_month", "supplier_id;branch_id", "quantity;unit_price;line_amount"),
    ("goods_receipts", "purchases", "one goods-receipt line", "source_system+source_document_id+source_line_id", "UPDATE_WATERMARK", "posting_year_month", "supplier_id;warehouse_id", "quantity;unit_cost;line_amount"),
    ("supplier_invoices", "purchases;finance", "one supplier-invoice line", "source_system+source_document_id+source_line_id", "UPDATE_WATERMARK", "posting_year_month", "supplier_id;branch_id", "quantity;unit_price;line_amount;open_amount"),
    ("purchase_returns", "purchases", "one purchase-return line", "source_system+source_document_id+source_line_id", "UPDATE_WATERMARK", "posting_year_month", "supplier_id;warehouse_id", "quantity;line_amount"),
    ("transfer_documents", "inventory", "one warehouse-transfer document", "source_system+source_document_id", "UPDATE_WATERMARK", "posting_year_month", "from_warehouse_id;to_warehouse_id", ""),
    ("transfer_lines", "inventory", "one warehouse-transfer line", "source_system+source_document_id+source_line_id", "UPDATE_WATERMARK", "posting_year_month", "from_warehouse_id;to_warehouse_id", "quantity;unit_cost"),
    ("boms", "production", "one parent product × BOM version/effective interval", "parent_product_id+bom_version+valid_from", "SNAPSHOT_WATERMARK", "none", "warehouse_id;plant_id", "formula"),
    ("bom_components", "production", "one BOM parent × component × version × position", "bom_id+component_product_id+component_position", "SNAPSHOT_WATERMARK", "none", "warehouse_id;plant_id", "required_quantity;formula"),
    ("production_orders", "production", "one production order", "source_system+source_document_id", "UPDATE_WATERMARK", "order_year_month", "warehouse_id;plant_id", "planned_quantity;completed_quantity"),
    ("production_component_consumptions", "production", "one actual component issue line", "source_system+source_document_id+source_line_id", "UPDATE_WATERMARK", "posting_year_month", "warehouse_id;plant_id", "quantity;unit_cost;total_cost"),
    ("production_outputs", "production", "one actual production receipt line", "source_system+source_document_id+source_line_id", "UPDATE_WATERMARK", "posting_year_month", "warehouse_id;plant_id", "quantity;unit_cost;total_cost"),
    ("payments", "credit;finance", "one payment document and direction", "source_system+source_document_id+payment_direction", "UPDATE_WATERMARK", "posting_year_month", "customer_id;supplier_id;branch_id", "amount;bank_account"),
    ("reconciliations", "credit;finance", "one reconciliation × member document", "source_system+source_reconciliation_id+source_document_id+source_line_id", "UPDATE_WATERMARK", "reconciliation_year_month", "customer_id;supplier_id;branch_id", "reconciled_amount"),
]
for name, domain, grain, key, incremental, part, scope, sensitive in ATOMIC:
    partition = "NO_PARTITION" if part == "none" else ("SNAPSHOT_DATE" if part == "snapshot_date" else "YEAR_MONTH")
    sort = ("snapshot_at,warehouse_id,product_id" if name == "stock_snapshots" else
            "product_id,warehouse_id,event_at" if name == "inventory_movements" else
            "posting_date,source_document_id,source_line_id")
    ds(name, "atomic", domain, grain, key, "SAP_HANA;LEGACY_DS", "SNAPSHOT" if name == "stock_snapshots" else ("REFERENCE" if name in {"boms", "bom_components"} else "EVENT"),
       partition, sort, incremental, domain, scope, sensitive, "raw/sap;raw/legacy;reference;crosswalk", lineage_profile="snapshot" if name == "stock_snapshots" else "event")

BUSINESS = [
    ("product_flow", "inventory;sales;purchases;production", "one product-affecting event line", "flow_event_id", "YEAR_MONTH", "product_id,warehouse_id,event_at", "inventory_movements;sales_lines;credit_note_lines;transfer_lines;goods_receipts;purchase_returns;production_component_consumptions;production_outputs", "warehouse_id;branch_id;salesperson_id", "quantity_in;quantity_out;unit_cost;unit_price;amount"),
    ("inventory_position", "inventory", "one product × warehouse × snapshot_at", "product_id+warehouse_id+snapshot_at", "SNAPSHOT_DATE", "snapshot_at,warehouse_id,product_id", "stock_snapshots;warehouse_branch_mapping;products", "warehouse_id;branch_id", "on_hand;available;inventory_value"),
    ("sales_line_read_model", "sales;credit", "one gross sale line with document and dimension attributes", "sale_line_id", "YEAR_MONTH", "customer_id,document_date,sale_line_id", "sales_lines;sales_documents;products;customers;salespersons;warehouse_branch_mapping", "branch_id;salesperson_id", "customer_name;unit_price;line_amount;cost_amount;margin_amount"),
    ("purchase_cycle_line", "purchases", "one procurement source line with resolved base-document links", "purchase_cycle_line_id", "YEAR_MONTH", "supplier_id,document_date,purchase_cycle_line_id", "purchase_requests;purchase_orders;goods_receipts;supplier_invoices;purchase_returns;suppliers", "supplier_id;branch_id;warehouse_id", "unit_price;line_amount;open_amount"),
    ("production_order_flow", "production", "one production order × product/component role", "production_order_id+product_id+flow_role", "YEAR_MONTH", "warehouse_id,order_date,production_order_id", "production_orders;boms;bom_components;production_component_consumptions;production_outputs", "warehouse_id;plant_id", "planned_quantity;actual_quantity;variance_quantity;cost_amount;formula"),
    ("customer_credit_state", "credit", "one customer × as_of_date × semantic version", "customer_id+as_of_date+semantic_version", "SNAPSHOT_DATE", "as_of_date,branch_id,customer_id", "sales_documents;credit_notes;payments;reconciliations;customers", "customer_id;branch_id", "credit_limit;open_amount;overdue_amount;aging_buckets",),
]
for name, domain, grain, key, partition, sort, inputs, scope, sensitive in BUSINESS:
    ds(name, "business", domain, grain, key, "DERIVED", "DERIVED", partition, sort,
       "REBUILD_ON_INPUT_CHANGE", domain, scope, sensitive, inputs, "REBUILDABLE", lineage_profile="derived")

BASE_LINEAGE = [
    ("_source_system", STR, "REQUIRED", "Controlled source system."),
    ("_source_dataset", STR, "REQUIRED", "Source table, query extract, legacy family or upstream dataset."),
    ("_source_native_key", STR, "REQUIRED", "Canonical serialization of the source-native key; never replaced by canonical_id."),
    ("_source_file", STR, "OPTIONAL", "Source-relative file path; required for legacy rows."),
    ("_source_snapshot_at", TS, "OPTIONAL", "Observed source cutoff; required for snapshot observations."),
    ("_source_extracted_at", TS, "REQUIRED", "Time source was read."),
    ("_ingested_at", TS, "REQUIRED", "Time row entered this layer."),
    ("_transformation_version", STR, "REQUIRED", "Build code/contract version."),
    ("_semantic_version", STR, "REQUIRED", "Meaning/metric contract version."),
    ("_lineage_quality", STR, "REQUIRED", "FULL_DOCUMENT_TRACE, PARTIAL_TRACE, AGGREGATE_ONLY or UNKNOWN."),
]
EVENT_LINEAGE = [
    ("_source_document_type", STR, "OPTIONAL", "Native document type when applicable."),
    ("_source_document_id", STR, "OPTIONAL", "Native document identifier when applicable."),
    ("_source_line_id", STR, "OPTIONAL", "Native line identifier when applicable."),
    ("_source_transaction_id", STR, "OPTIONAL", "Native transaction identifier when applicable."),
]

COMMON_ID = [("source_system", STR, False, "Source system discriminator"), ("source_native_id", STR, False, "Unmodified source-native identifier")]
REFERENCE_IDS = {
    "products": "product_id", "product_groups": "product_group_id", "customers": "customer_id",
    "suppliers": "supplier_id", "warehouses": "warehouse_id", "branches": "branch_id",
    "document_types": "document_type", "payment_terms": "payment_term_id", "channels": "channel_id",
    "units_of_measure": "unit_of_measure_id", "warehouse_roles": "warehouse_role_id",
    "currencies": "currency_code", "users": "user_id", "salespersons": "salesperson_id",
}
REFERENCE_EXTRA = {
    "products": [("product_group_id", STR, True, "Canonical product group"), ("unit_of_measure_id", STR, True, "Canonical inventory UOM"), ("standard_cost", MONEY, True, "Observed standard cost"), ("last_purchase_price", MONEY, True, "Observed last purchase price")],
    "customers": [("branch_id", STR, True, "Owning branch when evidenced"), ("tax_id", STR, True, "Sensitive tax identifier"), ("credit_limit", MONEY, True, "Observed credit limit"), ("payment_term_id", STR, True, "Canonical payment term")],
    "suppliers": [("branch_id", STR, True, "Owning branch when evidenced"), ("tax_id", STR, True, "Sensitive tax identifier"), ("payment_term_id", STR, True, "Canonical payment term")],
    "warehouses": [("warehouse_role_id", STR, True, "Canonical warehouse role")],
    "document_types": [("company_id", STR, False, "Legal company scope")],
    "payment_terms": [("branch_id", STR, True, "Branch scope"), ("credit_days", I32, True, "Contractual credit days")],
    "channels": [("branch_id", STR, True, "Branch scope")],
    "units_of_measure": [("company_id", STR, False, "Legal company scope")],
    "warehouse_roles": [("warehouse_id", STR, True, "Warehouse scope when role is local")],
    "currencies": [("legal_entity_id", STR, False, "Legal entity scope"), ("decimal_places", I32, True, "Display/accounting decimal places")],
    "users": [("organizational_scope", STR, True, "Observed organizational scope; not historical authorization")],
    "salespersons": [("branch_id", STR, True, "Branch scope")],
}

COLUMNS: dict[str, list[tuple[str, str, bool, str]]] = {}
for row in DATASETS:
    if row["layer"] == "reference":
        identity = REFERENCE_IDS[row["dataset_id"]]
        COLUMNS[row["dataset_id"]] = COMMON_ID + [
            (identity, STR, False, "Stable canonical identifier"),
            ("code", STR, False, "Business code preserved as identifier"),
            ("name", STR, True, "Observed display name"),
            ("valid_from", TS, True, "Known validity start"),
            ("valid_to", TS, True, "Known validity end; null means open or unknown per status"),
            ("status", STR, False, "ACTIVE, INACTIVE or UNKNOWN"),
        ] + REFERENCE_EXTRA.get(row["dataset_id"], [])
for row in DATASETS:
    if row["layer"] == "crosswalk":
        if row["dataset_id"] == "warehouse_branch_mapping":
            COLUMNS[row["dataset_id"]] = [("warehouse_id", STR, False, "Canonical warehouse ID"), ("branch_id", STR, True, "Canonical branch ID; nullable when historical mapping is unknown"), ("valid_from", TS, True, "Known validity start; null when unknown"), ("valid_to", TS, True, "Known validity end; null when unknown"), ("mapping_source", STR, False, "Mapping evidence source"), ("confidence", RATE, False, "Confidence from 0 to 1"), ("status", STR, False, "CONFIRMED, PROPOSED, UNKNOWN or UNMAPPED")]
        else:
            COLUMNS[row["dataset_id"]] = [("canonical_id", STR, True, "Canonical ID; nullable only for UNMAPPED"), ("source_system", STR, False, "Source system"), ("source_native_id", STR, False, "Unmodified native ID"), ("valid_from", TS, True, "Known validity start"), ("valid_to", TS, True, "Known validity end"), ("mapping_source", STR, False, "Evidence or method"), ("confidence", RATE, False, "Confidence from 0 to 1"), ("status", STR, False, "CONFIRMED, PROPOSED, UNKNOWN or UNMAPPED")]

DOC = [("document_id", STR, False, "Canonical document ID"), ("document_type", STR, False, "Business document type"), ("document_date", DATE, False, "Document date"), ("posting_date", DATE, True, "Accounting posting date"), ("due_date", DATE, True, "Due date"), ("is_cancelled", BOOL, False, "Cancellation state"), ("currency_code", STR, False, "ISO or preserved business currency code"), ("exchange_rate", RATE, True, "Document exchange rate")]
LINE = [("line_id", STR, False, "Canonical line ID"), ("document_id", STR, False, "Canonical parent document ID"), ("source_line_number", I32, True, "Native numeric line number where available"), ("product_id", STR, True, "Canonical product ID"), ("warehouse_id", STR, True, "Canonical warehouse ID"), ("quantity", QTY, True, "Signed or direction-specific quantity"), ("unit_price", MONEY, True, "Unit price"), ("line_amount", MONEY, True, "Line amount"), ("cost_amount", MONEY, True, "Line cost")]
COLUMNS.update({
    "sales_documents": DOC + [("customer_id", STR, False, "Canonical customer ID"), ("branch_id", STR, True, "Canonical branch scope"), ("salesperson_id", STR, True, "Canonical salesperson ID"), ("user_id", STR, True, "Canonical user ID"), ("gross_amount", MONEY, False, "Gross document amount"), ("open_amount", MONEY, True, "Observed open amount; not historical payment truth alone")],
    "sales_lines": LINE + [("customer_id", STR, False, "Canonical customer ID"), ("branch_id", STR, True, "Canonical branch scope"), ("salesperson_id", STR, True, "Canonical salesperson ID"), ("document_date", DATE, False, "Document date"), ("posting_date", DATE, True, "Posting date")],
    "credit_notes": DOC + [("customer_id", STR, False, "Canonical customer ID"), ("branch_id", STR, True, "Canonical branch scope"), ("gross_amount", MONEY, False, "Credit amount")],
    "credit_note_lines": LINE + [("customer_id", STR, False, "Canonical customer ID"), ("branch_id", STR, True, "Canonical branch scope"), ("salesperson_id", STR, True, "Canonical salesperson ID"), ("document_date", DATE, False, "Document date"), ("posting_date", DATE, True, "Posting date")],
    "inventory_movements": [("inventory_movement_id", STR, False, "Canonical movement ID"), ("product_id", STR, False, "Canonical product ID"), ("warehouse_id", STR, False, "Canonical warehouse ID"), ("branch_id", STR, True, "Mapped branch when evidenced"), ("event_at", TS, True, "Operational event timestamp"), ("document_date", DATE, True, "Source document date"), ("posting_date", DATE, False, "Accounting date"), ("movement_type", STR, False, "Controlled movement direction/type"), ("quantity_in", QTY, False, "Inbound quantity, non-negative"), ("quantity_out", QTY, False, "Outbound quantity, non-negative"), ("unit_cost", MONEY, True, "Unit cost"), ("total_cost", MONEY, True, "Extended cost"), ("customer_id", STR, True, "Customer when applicable"), ("supplier_id", STR, True, "Supplier when applicable"), ("salesperson_id", STR, True, "Salesperson when applicable"), ("user_id", STR, True, "Source user when applicable")],
    "stock_snapshots": [("stock_snapshot_id", STR, False, "Canonical snapshot row ID"), ("product_id", STR, False, "Canonical product ID"), ("warehouse_id", STR, False, "Canonical warehouse ID"), ("branch_id", STR, True, "Mapped branch when evidenced"), ("snapshot_at", TS, False, "Snapshot truth time"), ("on_hand", QTY, False, "On-hand quantity"), ("committed", QTY, True, "Committed quantity"), ("ordered", QTY, True, "Ordered quantity"), ("available", QTY, True, "Available quantity under semantic version"), ("inventory_value", MONEY, True, "Valuation under semantic version")],
})
for name in ("purchase_requests", "purchase_orders", "goods_receipts", "supplier_invoices", "purchase_returns"):
    COLUMNS[name] = LINE + [("supplier_id", STR, True, "Canonical supplier ID"), ("branch_id", STR, True, "Canonical branch ID"), ("document_date", DATE, False, "Document date"), ("posting_date", DATE, True, "Posting date"), ("due_date", DATE, True, "Due/requested date"), ("base_document_id", STR, True, "Canonical base document when evidenced"), ("base_line_id", STR, True, "Canonical base line when evidenced"), ("open_amount", MONEY, True, "Observed open amount")]
COLUMNS["transfer_documents"] = DOC + [("from_warehouse_id", STR, False, "Origin warehouse"), ("to_warehouse_id", STR, False, "Destination warehouse")]
COLUMNS["transfer_lines"] = LINE + [("from_warehouse_id", STR, False, "Origin warehouse"), ("to_warehouse_id", STR, False, "Destination warehouse"), ("event_at", TS, True, "Transfer event timestamp"), ("posting_date", DATE, False, "Posting date")]
COLUMNS["boms"] = [("bom_id", STR, False, "Canonical BOM version ID"), ("parent_product_id", STR, False, "Parent product"), ("bom_version", STR, False, "Version identifier"), ("valid_from", TS, True, "Known validity start"), ("valid_to", TS, True, "Known validity end"), ("planned_quantity", QTY, False, "BOM basis quantity"), ("warehouse_id", STR, True, "Warehouse scope"), ("plant_id", STR, True, "Plant scope")]
COLUMNS["bom_components"] = [("bom_component_id", STR, False, "Canonical component row ID"), ("bom_id", STR, False, "Parent BOM"), ("component_product_id", STR, False, "Component product"), ("component_position", STR, False, "Source position preserved as identifier"), ("required_quantity", QTY, False, "Required quantity per basis"), ("unit_of_measure_id", STR, True, "Canonical UOM"), ("warehouse_id", STR, True, "Warehouse scope inherited from versioned BOM"), ("plant_id", STR, True, "Plant scope inherited from versioned BOM")]
COLUMNS["production_orders"] = DOC + [("production_order_id", STR, False, "Canonical production order ID"), ("product_id", STR, False, "Output product"), ("warehouse_id", STR, False, "Production warehouse"), ("plant_id", STR, True, "Plant scope"), ("order_date", DATE, False, "Order date"), ("release_date", DATE, True, "Release date"), ("close_date", DATE, True, "Close date"), ("planned_quantity", QTY, False, "Planned output"), ("completed_quantity", QTY, True, "Observed completed output")]
for name in ("production_component_consumptions", "production_outputs"):
    COLUMNS[name] = LINE + [("production_order_id", STR, False, "Canonical production order"), ("event_at", TS, True, "Operational event timestamp"), ("posting_date", DATE, False, "Posting date"), ("plant_id", STR, True, "Plant scope"), ("unit_cost", MONEY, True, "Unit cost"), ("total_cost", MONEY, True, "Extended cost")]
COLUMNS["payments"] = DOC + [("payment_id", STR, False, "Canonical payment ID"), ("payment_direction", STR, False, "INCOMING or OUTGOING"), ("customer_id", STR, True, "Canonical customer"), ("supplier_id", STR, True, "Canonical supplier"), ("branch_id", STR, True, "Branch scope"), ("amount", MONEY, False, "Payment amount"), ("bank_account", STR, True, "Sensitive bank account reference")]
COLUMNS["reconciliations"] = [("reconciliation_member_id", STR, False, "Canonical reconciliation member ID"), ("reconciliation_id", STR, False, "Canonical reconciliation ID"), ("document_id", STR, False, "Member document ID"), ("source_line_number", I32, True, "Member line"), ("customer_id", STR, True, "Canonical customer"), ("supplier_id", STR, True, "Canonical supplier"), ("branch_id", STR, True, "Branch scope"), ("reconciliation_date", DATE, False, "Reconciliation effective date"), ("reconciled_amount", MONEY, False, "Amount settled by this member")]
COLUMNS.update({
    "product_flow": [("flow_event_id", STR, False, "Stable derived event ID"), ("event_type", STR, False, "SALE, CREDIT_NOTE, MOVEMENT, TRANSFER, RECEIPT, RETURN, CONSUMPTION or OUTPUT"), ("product_id", STR, False, "Canonical product"), ("document_id", STR, True, "Canonical source document"), ("movement_id", STR, True, "Canonical movement"), ("event_at", TS, True, "Event timestamp"), ("document_date", DATE, True, "Document date"), ("posting_date", DATE, True, "Posting date"), ("warehouse_id", STR, True, "Warehouse scope"), ("branch_id", STR, True, "Branch scope"), ("customer_id", STR, True, "Customer when applicable"), ("supplier_id", STR, True, "Supplier when applicable"), ("salesperson_id", STR, True, "Salesperson when applicable"), ("user_id", STR, True, "User when applicable"), ("quantity_in", QTY, False, "Inbound quantity"), ("quantity_out", QTY, False, "Outbound quantity"), ("unit_cost", MONEY, True, "Unit cost"), ("unit_price", MONEY, True, "Unit price"), ("amount", MONEY, True, "Event amount")],
    "inventory_position": [("product_id", STR, False, "Canonical product"), ("warehouse_id", STR, False, "Canonical warehouse"), ("branch_id", STR, True, "Mapped branch"), ("snapshot_at", TS, False, "Snapshot truth time"), ("on_hand", QTY, False, "On-hand"), ("committed", QTY, True, "Committed"), ("ordered", QTY, True, "Ordered"), ("available", QTY, True, "Available"), ("inventory_value", MONEY, True, "Valuation")],
    "sales_line_read_model": LINE + [("sale_line_id", STR, False, "Canonical sale line"), ("document_date", DATE, False, "Document date"), ("posting_date", DATE, True, "Posting date"), ("due_date", DATE, True, "Due date"), ("customer_id", STR, False, "Customer"), ("customer_name", STR, True, "Observed customer name"), ("branch_id", STR, True, "Branch"), ("salesperson_id", STR, True, "Salesperson"), ("margin_amount", MONEY, True, "Versioned line margin")],
    "purchase_cycle_line": [("purchase_cycle_line_id", STR, False, "Stable cycle line ID"), ("cycle_stage", STR, False, "REQUEST, ORDER, RECEIPT, INVOICE or RETURN"), ("document_id", STR, False, "Stage document"), ("line_id", STR, False, "Stage line"), ("base_document_id", STR, True, "Linked predecessor"), ("base_line_id", STR, True, "Linked predecessor line"), ("product_id", STR, True, "Product"), ("supplier_id", STR, True, "Supplier"), ("warehouse_id", STR, True, "Warehouse"), ("branch_id", STR, True, "Branch"), ("document_date", DATE, False, "Document date"), ("quantity", QTY, True, "Quantity"), ("unit_price", MONEY, True, "Price"), ("line_amount", MONEY, True, "Amount"), ("open_amount", MONEY, True, "Open amount")],
    "production_order_flow": [("production_order_id", STR, False, "Production order"), ("product_id", STR, False, "Product/component"), ("flow_role", STR, False, "OUTPUT or COMPONENT"), ("warehouse_id", STR, False, "Warehouse"), ("plant_id", STR, True, "Plant"), ("order_date", DATE, False, "Order date"), ("planned_quantity", QTY, True, "Planned quantity"), ("actual_quantity", QTY, True, "Actual quantity"), ("variance_quantity", QTY, True, "Versioned variance"), ("cost_amount", MONEY, True, "Cost")],
    "customer_credit_state": [("customer_id", STR, False, "Canonical customer"), ("branch_id", STR, True, "Branch scope"), ("as_of_date", DATE, False, "Semantic cutoff"), ("credit_limit", MONEY, True, "Observed credit limit"), ("open_amount", MONEY, False, "Open amount as-of"), ("overdue_amount", MONEY, False, "Overdue amount as-of"), ("not_due_amount", MONEY, False, "Not-due amount as-of"), ("aging_0_30", MONEY, False, "0-30 days overdue"), ("aging_31_60", MONEY, False, "31-60 days overdue"), ("aging_61_90", MONEY, False, "61-90 days overdue"), ("aging_91_plus", MONEY, False, "91+ days overdue")],
})

# Raw registry families do not reinterpret payload columns. These are extraction envelope columns for future SAP raw files.
COLUMNS["sap_table_extracts"] = [("extract_id", STR, False, "Immutable extraction run ID"), ("source_native_key", STR, False, "Serialized native key"), ("observation_sequence", I64, False, "Stable row sequence in run"), ("_source_extracted_at", TS, False, "Extraction timestamp")]
COLUMNS["sap_query_extracts"] = [("extract_id", STR, False, "Immutable extraction run ID"), ("query_row_key", STR, False, "Declared query result key"), ("observation_sequence", I64, False, "Stable row sequence in run"), ("_source_extracted_at", TS, False, "Extraction timestamp")]
COLUMNS["legacy_parquet_mirror"] = []


def write_csv(name: str, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0])
    with (ROOT / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    write_csv("physical_layout.csv", [{"relative_path": p, "responsibility": r, "description": d, "decision": x} for p, r, d, x in LAYOUT])
    write_csv("physical_datasets.csv", DATASETS)

    column_rows: list[dict[str, object]] = []
    for dataset in DATASETS:
        dataset_id = dataset["dataset_id"]
        for position, (name, typ, nullable, meaning) in enumerate(COLUMNS[dataset_id], 1):
            column_rows.append({"dataset_id": dataset_id, "column_position": position, "column_name": name, "physical_type": typ, "nullable": "YES" if nullable else "NO", "semantic_meaning": meaning, "source_lineage": "SOURCE_OR_TRANSFORMATION_DECLARED", "column_role": "BUSINESS"})
        if dataset["layer"] not in {"raw"}:
            existing = {c[0] for c in COLUMNS[dataset_id]}
            next_position = len(COLUMNS[dataset_id]) + 1
            for name, typ, requirement, meaning in BASE_LINEAGE + (EVENT_LINEAGE if dataset["data_kind"] in {"EVENT", "DERIVED"} else []):
                if name not in existing:
                    column_rows.append({"dataset_id": dataset_id, "column_position": next_position, "column_name": name, "physical_type": typ, "nullable": "NO" if requirement == "REQUIRED" else "YES", "semantic_meaning": meaning, "source_lineage": requirement, "column_role": "TECHNICAL"})
                    next_position += 1
    write_csv("physical_columns.csv", column_rows)

    partition_rows = []
    for row in DATASETS:
        strategy = row["partitioning"]
        columns = {"NO_PARTITION": "", "YEAR_MONTH": "year,month", "SNAPSHOT_DATE": "snapshot_date", "EXTRACTION_DATE": "extraction_date"}.get(strategy, "dataset_specific")
        partition_rows.append({"dataset_id": row["dataset_id"], "strategy": strategy, "partition_columns": columns, "rationale": "Prune dominant temporal scans without high-cardinality partitions." if strategy != "NO_PARTITION" else "Current/expected size or update pattern does not justify partitions.", "small_file_policy": "Target 128-512 MiB files and 64-128 MiB row groups; compact only within an affected partition; never rewrite preserved raw.", "sort_order": row["sort_order"]})
    write_csv("partition_strategy.csv", partition_rows)

    incremental_rows = []
    watermark_rows = []
    for row in DATASETS:
        strategy = row["incremental_strategy"]
        field = {"DOCUMENT_WATERMARK": "source_update_at + source_document_id", "UPDATE_WATERMARK": "source_update_at + source_native_key", "SNAPSHOT_WATERMARK": "snapshot_at", "SNAPSHOT_UPSERT_SCD2": "source_extracted_at", "REBUILD_ON_INPUT_CHANGE": "input_manifest_ids", "DATASET_SPECIFIC": "declared_per_extract", "IMMUTABLE_COPY": "sha256"}[strategy]
        late = "N/A" if strategy == "IMMUTABLE_COPY" else ("Rebuild from immutable input manifests." if strategy == "REBUILD_ON_INPUT_CHANGE" else "Re-read a configurable overlap window, compare source update/native keys, preserve restatements, and reconcile to source maxima.")
        incremental_rows.append({"dataset_id": row["dataset_id"], "strategy": strategy, "watermark_field": field, "late_arrival_policy": late, "write_mode": "IMMUTABLE" if row["layer"] == "raw" else "APPEND_NEW_VERSION_AND_COMPACT_AFFECTED_PARTITIONS", "source_correction_policy": "Preserve prior source/build manifests; corrections create a new observation or build version."})
        if strategy not in {"IMMUTABLE_COPY", "REBUILD_ON_INPUT_CHANGE"}:
            watermark_rows.append({"dataset_id": row["dataset_id"], "watermark_type": strategy, "watermark_field": field, "last_success_value": "nullable", "last_attempt_value": "nullable", "source_max_value": "nullable", "extraction_started_at": "timestamp[us,UTC]", "extraction_completed_at": "timestamp[us,UTC], nullable", "status": "PENDING|RUNNING|SUCCEEDED|FAILED|RECONCILED", "backfill_window": "dataset-configured; never global", "manifest_path": f"manifests/watermarks/{row['dataset_id']}.json"})
    write_csv("incremental_strategy.csv", incremental_rows)
    write_csv("watermark_contract.csv", watermark_rows)

    profiles = {
        "source_file": {"required": "source_relative_path;destination_relative_path;size_bytes;sha256;copy_status", "optional": "schema_fingerprint;row_count;filename_date;family", "not_applicable": "row-level canonical lineage"},
        "sap_raw": {"required": "_source_system;_source_dataset;_source_native_key;_source_extracted_at;_ingested_at", "optional": "_source_document_type;_source_document_id;_source_line_id;_source_transaction_id", "not_applicable": "_source_file unless exported via an intermediate file"},
        "reference": {"required": "_source_system;_source_dataset;_source_native_key;_source_extracted_at;_ingested_at;_transformation_version;_semantic_version;_lineage_quality", "optional": "_source_file;_source_snapshot_at", "not_applicable": "document/transaction fields unless source supports them"},
        "crosswalk": {"required": "mapping_source;confidence;status;_source_system;_source_dataset;_source_native_key;_ingested_at;_transformation_version;_semantic_version", "optional": "_source_file;_source_snapshot_at;_source_extracted_at", "not_applicable": "document line fields"},
        "event": {"required": "_source_system;_source_dataset;_source_native_key;_source_extracted_at;_ingested_at;_transformation_version;_semantic_version;_lineage_quality", "optional": "_source_document_type;_source_document_id;_source_line_id;_source_transaction_id;_source_file;_source_snapshot_at", "not_applicable": "none; applicability depends on native source"},
        "snapshot": {"required": "snapshot_at;_source_system;_source_dataset;_source_native_key;_source_snapshot_at;_source_extracted_at;_ingested_at;_transformation_version;_semantic_version;_lineage_quality", "optional": "_source_file", "not_applicable": "document/transaction fields unless supported"},
        "derived": {"required": "_source_system=DERIVED;_source_dataset;_source_native_key;_source_extracted_at;_ingested_at;_transformation_version;_semantic_version;_lineage_quality", "optional": "_source_document_type;_source_document_id;_source_line_id;_source_transaction_id;_source_file;_source_snapshot_at", "not_applicable": "none"},
    }
    lineage_rows = []
    for profile, groups in profiles.items():
        for requirement, fields in groups.items():
            lineage_rows.append({"contract_profile": profile, "requirement": requirement.upper(), "fields": fields, "rule": "Technical columns use a leading underscore; business keys do not. Null never fabricates unavailable lineage."})
    write_csv("lineage_physical_contract.csv", lineage_rows)

    legacy_fields = [
        ("source_relative_path", "REQUIRED", "POSIX path relative to LEGACY_ROOT; must not escape root."),
        ("source_filename", "REQUIRED", "Original filename, byte-for-byte spelling preserved."),
        ("destination_relative_path", "REQUIRED", "raw/legacy/parquet/<source_relative_path>."),
        ("size_bytes", "REQUIRED", "Source size and verified destination size."),
        ("sha256", "REQUIRED", "Lowercase SHA-256 computed independently on source and destination; values must match."),
        ("family", "REQUIRED", "Inventory family; UNKNOWN allowed but not blank."),
        ("filename_date", "OPTIONAL", "Parsed filename date; never treated as business or snapshot truth without family policy."),
        ("schema_fingerprint", "REQUIRED", "Fingerprint from ordered physical Parquet schema metadata without rewriting payload."),
        ("row_count", "REQUIRED", "Footer row count read without transformation."),
        ("copied_at", "REQUIRED_ON_SUCCESS", "UTC completion timestamp."),
        ("copy_status", "REQUIRED", "PENDING, COPIED_UNVERIFIED, VERIFIED, FAILED or SOURCE_CHANGED."),
    ]
    write_csv("legacy_mirror_contract.csv", [{"field": f, "requirement": r, "contract": c} for f, r, c in legacy_fields])

    security_rows = []
    for row in DATASETS:
        security_rows.append({"dataset_id": row["dataset_id"], "security_domain": row["security_domain"], "scope_columns": row["scope_columns"], "sensitive_columns": row["sensitive_columns"], "sensitive_metrics": row["sensitive_columns"], "cross_scope_aggregation": "ADMIN_ONLY_OR_EXPLICIT_CAPABILITY" if row["sensitive_columns"] else "POLICY_CONTROLLED", "enforcement_stage": "AUTHORIZED_SCOPE_BEFORE_PATH_RESOLUTION_AND_PARQUET_SCAN", "gate_access": "administrator:FULL_ACCESS"})
    write_csv("security_physical_contract.csv", security_rows)

    registry_fields = ["dataset_id", "layer", "path", "schema_version", "semantic_version", "transformation_version", "grain", "partitioning", "security_domain", "scope_columns", "source_systems", "inputs", "rebuild_class", "lineage_profile", "format", "compression", "active"]
    write_csv("dataset_registry.csv", [{k: row[k] for k in registry_fields} for row in DATASETS], registry_fields)

    decisions = [
        ("PD-001", "Use one DATA_ROOT with source and derived separation.", "ACCEPTED", "Avoid permanent dependency on external roots while preserving evidence."),
        ("PD-002", "Preserve legacy mirror at raw/legacy/parquet/<source_relative_path>.", "ACCEPTED", "Prevents filename collisions and proves byte identity without renaming."),
        ("PD-003", "Do not keep durable staging, generic snapshots or decision layers in V1.", "ACCEPTED", "They add duplication without a concrete consumer; staging is process-local."),
        ("PD-004", "Use ZSTD by default for generated Parquet.", "ACCEPTED", "Good compression/read performance and broad DuckDB/PyArrow support; raw mirror is never recompressed."),
        ("PD-005", "Use decimal128(38,6) money, decimal128(38,12) quantity/rate.", "ACCEPTED", "Avoid float and avoid precision below known source; overflow/scale incompatibility stops the affected dataset."),
        ("PD-006", "Store canonical and native IDs separately as strings.", "ACCEPTED", "Business codes retain zeros/semantics; optional SAP numeric trace may coexist."),
        ("PD-007", "Use 128-512 MiB generated files and 64-128 MiB row groups as targets, not hard limits.", "ACCEPTED", "Fits moderate machines and avoids premature micro-partitioning."),
        ("PD-008", "Partition only temporal high-volume datasets.", "ACCEPTED", "YEAR_MONTH or SNAPSHOT_DATE supports pruning without product/customer/warehouse fanout."),
        ("PD-009", "Represent current stock and current credit as DuckDB views over latest authorized snapshots.", "ACCEPTED", "Avoid redundant materialization until a measured latency need exists."),
        ("PD-010", "Replace ambiguous 360 names with grain-bearing business names.", "ACCEPTED", "product_flow, inventory_position, sales_line_read_model, purchase_cycle_line, production_order_flow and customer_credit_state expose grain."),
        ("PD-011", "Registry source is CSV plus generated JSON at deployment/build time.", "ACCEPTED", "CSV is reviewable and dependency-free; JSON is the runtime-friendly projection; no SQLite/Python config split."),
        ("PD-012", "Raw keeps Legacy and SAP overlap; atomic selects authority per concept/window and quarantines unresolved overlap.", "ACCEPTED", "Preserves evidence and prevents silent double count."),
        ("PD-013", "Generated Parquet uses immutable run manifests and partition replacement only after validation.", "ACCEPTED", "Supports rollback/rebuild without mutating preserved source."),
        ("PD-014", "DuckDB resolves dataset IDs through registry-backed views.", "ACCEPTED", "Consumers use logical names; views call read_parquet(path, hive_partitioning=true, union_by_name=false)."),
        ("PD-015", "Schema evolution is explicit and union_by_name is disabled by default.", "ACCEPTED", "Prevents silent schema drift; compatibility views are versioned."),
    ]
    write_csv("decision_log.csv", [{"decision_id": i, "decision": d, "status": s, "rationale": r} for i, d, s, r in decisions])

    counts = Counter(row["layer"] for row in DATASETS)
    summary = {
        "gate": GATE, "data_root": DATA_ROOT, "legacy_root": LEGACY_ROOT,
        "physical_datasets": len(DATASETS), "atomic_datasets": counts["atomic"],
        "business_datasets": counts["business"], "reference_datasets": counts["reference"],
        "crosswalk_datasets": counts["crosswalk"], "raw_dataset_families": counts["raw"],
        "legacy_parquet_expected": 696, "legacy_mirror_path": f"{DATA_ROOT}/raw/legacy/parquet",
        "legacy_copy_executed": False, "partition_strategies": len({r["partitioning"] for r in DATASETS}),
        "incremental_strategies": len({r["incremental_strategy"] for r in DATASETS}),
        "watermark_contracts": len(watermark_rows), "lineage_physical_contracts": len(profiles),
        "security_physical_contracts": len(security_rows), "sap_accessed": False, "sap_write_count": 0,
        "production_parquets_created": 0, "legacy_parquets_copied": 0,
        "source_files_modified": 0, "source_files_moved": 0, "source_files_deleted": 0,
        "physical_parquet_design_ready": True, "compression_default": "ZSTD",
        "row_group_target": "64-128 MiB", "file_target": "128-512 MiB",
        "sap_physical_decision_stops": [],
    }
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
