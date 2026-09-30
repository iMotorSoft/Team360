from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write_csv(name: str, rows: list[dict[str, object]]) -> None:
    path = ROOT / name
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


EVIDENCE = (
    "docs/TELCHI_HISTORICAL_DATA_INVENTORY_V1.md; "
    "docs/TELCHI_SAP_KNOWLEDGE_INVENTORY_V1.md"
)

CORE: list[tuple[str, str, str, str, str, str, str, str]] = [
    ("PRODUCT", "REFERENCE", "One canonical product identity; master attributes are versioned separately", "one row = one canonical product identity", "canonical_product_id", "YES", "validity of master attributes; extraction time for observed state", "SAP_HANA;LEGACY_DS"),
    ("PRODUCT_GROUP", "REFERENCE", "Business grouping of products", "one row = one product group identity/version", "canonical_product_group_id", "YES", "valid_from/valid_to for group assignment", "SAP_HANA;LEGACY_DS"),
    ("CUSTOMER", "REFERENCE", "Business partner acting as customer", "one row = one canonical customer identity", "canonical_customer_id", "YES", "identity validity plus observed master extraction", "SAP_HANA;LEGACY_DS"),
    ("SUPPLIER", "REFERENCE", "Business partner acting as supplier", "one row = one canonical supplier identity", "canonical_supplier_id", "YES", "identity validity plus observed master extraction", "SAP_HANA;LEGACY_DS"),
    ("WAREHOUSE", "REFERENCE", "Inventory location used by the business", "one row = one canonical warehouse identity", "canonical_warehouse_id", "YES", "identity validity and role validity", "SAP_HANA;LEGACY_DS;EXTERNAL_FILES"),
    ("BRANCH", "REFERENCE", "Office, branch, or organizational sales location", "one row = one canonical branch/office identity", "canonical_branch_id", "YES", "identity validity", "SAP_HANA;LEGACY_DS;EXTERNAL_FILES"),
    ("WAREHOUSE_BRANCH_MAPPING", "CORE_V1", "Temporal organizational assignment of warehouse to branch", "one row = warehouse × branch × non-overlapping validity interval", "canonical_warehouse_id+canonical_branch_id+valid_from", "YES", "valid_from/valid_to; source observation time", "EXTERNAL_FILES;SAP_HANA;LEGACY_DS"),
    ("SALE_DOCUMENT", "CORE_V1", "Commercial sales document header, including invoice state", "one row = one sales document instance", "source_system+source_native_id+document_type", "YES", "document_date, posting_date, due_date, cancellation/system time as available", "SAP_HANA;LEGACY_DS"),
    ("SALE_LINE", "CORE_V1", "Atomic line of a gross sale document", "one row = one sales document line", "source_system+source_document_id+source_line_id", "YES", "document_date/posting_date; extraction time; no snapshot concatenation", "SAP_HANA;LEGACY_DS"),
    ("CREDIT_NOTE", "CORE_V1", "Credit note header reducing or correcting a sale", "one row = one credit-note document instance", "source_system+source_native_id+document_type", "YES", "document_date, posting_date, cancellation/system time", "SAP_HANA;LEGACY_DS"),
    ("CREDIT_NOTE_LINE", "CORE_V1", "Atomic line of a credit note", "one row = one credit-note document line", "source_system+source_document_id+source_line_id", "YES", "document_date/posting_date; source snapshot only as observation", "SAP_HANA;LEGACY_DS"),
    ("INVENTORY_MOVEMENT", "CORE_V1", "Physical/accounting inventory movement event", "one row = one movement transaction line/event", "source_system+source_transaction_id+source_line_id (or documented fallback)", "YES", "event_time/document_date/posting_date; extraction time", "SAP_HANA;LEGACY_DS"),
    ("STOCK_SNAPSHOT", "CORE_V1", "Observed stock position at a declared cut", "one row = product × warehouse × snapshot_at", "canonical_product_id+canonical_warehouse_id+snapshot_at", "YES", "snapshot_date and source_snapshot_at required", "SAP_HANA;LEGACY_DS"),
    ("STOCK_CURRENT", "CORE_V1", "Current source-reported stock state", "one row = product × warehouse × current extraction", "canonical_product_id+canonical_warehouse_id+source_extracted_at", "YES", "current_state_at plus extraction/system time", "SAP_HANA"),
    ("PURCHASE_REQUEST", "CORE_V1", "Requested procurement requirement", "one row = one purchase-request line", "source_system+source_document_id+source_line_id", "YES", "document_date; requested/due date when present; extraction time", "SAP_HANA;LEGACY_DS"),
    ("PURCHASE_ORDER", "CORE_V1", "Committed supplier purchase order", "one row = one purchase-order line", "source_system+source_document_id+source_line_id", "YES", "document_date, due_date, close/cancel system time", "SAP_HANA;LEGACY_DS"),
    ("GOODS_RECEIPT", "CORE_V1", "Receipt of goods from a supplier", "one row = one goods-receipt line", "source_system+source_document_id+source_line_id", "YES", "event_time/document_date/posting_date", "SAP_HANA"),
    ("SUPPLIER_INVOICE", "CORE_V1", "Supplier/AP invoice line", "one row = one supplier-invoice line", "source_system+source_document_id+source_line_id", "YES", "document_date, posting_date, due_date, cancellation/system time", "SAP_HANA;LEGACY_DS"),
    ("PURCHASE_RETURN", "CORE_V1", "Return of goods to supplier", "one row = one purchase-return line", "source_system+source_document_id+source_line_id", "YES", "event_time/document_date/posting_date", "SAP_HANA;LEGACY_DS"),
    ("TRANSFER", "CORE_V1", "Warehouse transfer document header", "one row = one transfer document", "source_system+source_native_id+document_type", "YES", "document_date/posting_date; accounting system time", "SAP_HANA"),
    ("TRANSFER_LINE", "CORE_V1", "Atomic warehouse transfer line", "one row = one transfer document line", "source_system+source_document_id+source_line_id", "YES", "event_time/document_date/posting_date", "SAP_HANA"),
    ("BOM", "CORE_V1", "Bill-of-material parent/version", "one row = one parent product × BOM version/effective interval", "canonical_product_id+version+valid_from", "YES", "valid_from/valid_to; observed extraction", "SAP_HANA;LEGACY_DS"),
    ("BOM_COMPONENT", "CORE_V1", "Component requirement in a BOM", "one row = one parent × component × version/effective interval", "bom_id+canonical_component_product_id+line_or_position", "YES", "valid_from/valid_to; source extraction", "SAP_HANA;LEGACY_DS"),
    ("PRODUCTION_ORDER", "CORE_V1", "Production order and its planned execution", "one row = one production order", "source_system+source_native_id", "YES", "order date, due date, release/close system time", "SAP_HANA"),
    ("COMPONENT_CONSUMPTION", "CORE_V1", "Actual component issue to a production order", "one row = one actual consumption document line", "source_system+source_document_id+source_line_id", "YES", "event_time/document_date/posting_date", "SAP_HANA"),
    ("PRODUCTION_OUTPUT", "CORE_V1", "Actual finished/semi-finished output receipt", "one row = one output document line", "source_system+source_document_id+source_line_id", "YES", "event_time/document_date/posting_date", "SAP_HANA"),
    ("PAYMENT", "CORE_V1", "Incoming or outgoing payment event", "one row = one payment document", "source_system+source_native_id+payment_direction", "YES", "event_time/document_date/posting_date; settlement system time", "SAP_HANA;LEGACY_DS"),
    ("RECONCILIATION", "CORE_V1", "Settlement/reconciliation member event", "one row = one reconciliation × member/source document", "source_system+reconciliation_id+source_native_id+line", "YES", "event_time/reconciliation_date; as-of cutoff", "SAP_HANA;LEGACY_DS"),
    ("CUSTOMER_CREDIT_STATE", "CORE_V1", "Customer receivable/credit state at a cutoff", "one row = customer × as_of_date", "canonical_customer_id+as_of_date+semantic_version", "YES", "as_of_date and system/extraction time; derived state", "SAP_HANA;LEGACY_DS"),
    ("USER", "CORE_V1", "SAP/application user identity and current capability reference", "one row = one canonical user identity/version", "canonical_user_id", "YES", "validity/current extraction; historical authorization unavailable", "SAP_HANA;EXTERNAL_FILES"),
    ("SALESPERSON", "CORE_V1", "Commercial salesperson identity", "one row = one canonical salesperson identity/version", "canonical_salesperson_id", "YES", "identity validity; observed extraction", "SAP_HANA;LEGACY_DS"),
]

LATER = [
    ("EMPLOYEE", "CORE_LATER", "Employee identity and organizational attributes", "one row = one canonical employee identity/version", "canonical_employee_id", "YES", "validity; extraction time", "SAP_HANA;EXTERNAL_FILES"),
    ("FORECAST_DEFINITION", "CORE_LATER", "Forecast definition/header", "one row = one forecast definition/version", "source_system+source_native_id+version", "YES", "valid_from/valid_to; extraction time", "SAP_HANA;LEGACY_DS"),
    ("FORECAST_LINE", "CORE_LATER", "Forecast quantity/value by product and period", "one row = forecast × product × period", "forecast_id+canonical_product_id+period", "YES", "forecast period plus extraction time", "SAP_HANA;LEGACY_DS"),
    ("MRP_PARAMETER", "CORE_LATER", "Configured planning parameter", "one row = product × warehouse × parameter × validity interval", "product+warehouse+parameter+valid_from", "YES", "valid_from/valid_to; configuration extraction", "SAP_HANA"),
    ("CREDIT_RISK_EVENT", "CORE_LATER", "Observed credit authorization/risk exception event", "one row = one risk/authorization event", "source_system+source_transaction_id+event_type+event_time", "YES", "event_time/system time", "SAP_HANA;EXTERNAL_FILES"),
]

REFERENCE = [
    ("DOCUMENT_TYPE", "REFERENCE", "Stable document type vocabulary", "one row = one document type", "document_type_code", "NO", "validity if vocabulary changes", "SAP_HANA;LEGACY_DS"),
    ("PAYMENT_TERM", "REFERENCE", "Payment terms and due-date policy reference", "one row = one payment-term identity/version", "payment_term_code+valid_from", "YES", "valid_from/valid_to", "SAP_HANA"),
    ("CHANNEL", "REFERENCE", "Sales/channel classification", "one row = one channel identity/version", "channel_code+valid_from", "YES", "valid_from/valid_to", "SAP_HANA;LEGACY_DS"),
    ("UNIT_OF_MEASURE", "REFERENCE", "Quantity/unit vocabulary", "one row = one unit identity/conversion version", "unit_code+valid_from", "YES", "valid_from/valid_to", "SAP_HANA;LEGACY_DS"),
    ("WAREHOUSE_ROLE", "REFERENCE", "Operational role classification of a warehouse", "one row = warehouse × role × validity interval", "warehouse+role+valid_from", "YES", "valid_from/valid_to", "SAP_HANA;EXTERNAL_FILES"),
    ("CURRENCY", "REFERENCE", "Currency vocabulary and conversion context", "one row = one currency identity/version", "currency_code+valid_from", "YES", "validity", "SAP_HANA;LEGACY_DS"),
]

SPECIALIZED = [
    ("LOT_SERIAL", "SPECIALIZED", "Lot/serial identity and trace events", "one row = one lot/serial identity or transaction event, subtype explicit", "source_system+source_native_id+item+event", "YES", "event_time/validity; coverage partial", "SAP_HANA"),
    ("PRODUCT_TRACKING", "SPECIALIZED", "Legacy product tracking observation", "one row = product × tracking observation × observed date", "source_file+product+tracking_date+source_native_key", "YES", "tracking date plus source snapshot", "LEGACY_DS;SAP_HANA"),
    ("CASH_TRANSACTION", "SPECIALIZED", "Legacy/SAP cash movement observation", "one row = one cash transaction document/event", "source_system+source_native_id", "YES", "event/document date; snapshot source", "SAP_HANA;LEGACY_DS"),
    ("BANK_DEPOSIT", "SPECIALIZED", "Deposit and bank clearing event", "one row = one deposit document", "source_system+source_native_id", "YES", "event/document date; external reconciliation may be absent", "SAP_HANA"),
    ("GENERAL_LEDGER_ENTRY", "SPECIALIZED", "Accounting journal line", "one row = one journal-entry line", "source_system+source_document_id+source_line_id", "YES", "posting_date/document date/system time", "SAP_HANA"),
    ("SUPPLIER_EXPENSE", "SPECIALIZED", "Legacy purchase expense observation not yet reconciled to canonical invoice", "one row = one supplier-expense observation", "source_file+source_native_key+source_snapshot_at", "YES", "business date plus source snapshot", "LEGACY_DS"),
    ("APPROVAL_EVENT", "SPECIALIZED", "External or system authorization evidence", "one row = one approval/authorization event", "source_system+source_native_id+event_time", "YES", "event_time; historical coverage partial", "SAP_HANA;EXTERNAL_FILES"),
]

OUT_SCOPE = [
    ("PAYROLL_DETAIL", "OUT_OF_SCOPE", "Individual payroll facts", "one row = one employee payroll component", "external_payroll_id+employee+period", "YES", "period and extraction time", "EXTERNAL_FILES"),
    ("WHT_TRANSACTION_DETAIL", "OUT_OF_SCOPE", "Detailed withholding transaction fact", "one row = one withholding document line", "source_system+source_document_id+source_line_id", "YES", "document/posting time", "SAP_HANA"),
]

ALL_ENTITIES = CORE + LATER + REFERENCE + SPECIALIZED + OUT_SCOPE


def entity_rows() -> list[dict[str, object]]:
    rows = []
    for name, classification, definition, grain, natural_key, surrogate, time_semantics, sources in ALL_ENTITIES:
        concept = "EVENT" if name in {"SALE_DOCUMENT", "SALE_LINE", "CREDIT_NOTE", "CREDIT_NOTE_LINE", "INVENTORY_MOVEMENT", "PURCHASE_REQUEST", "PURCHASE_ORDER", "GOODS_RECEIPT", "SUPPLIER_INVOICE", "PURCHASE_RETURN", "TRANSFER", "TRANSFER_LINE", "PRODUCTION_ORDER", "COMPONENT_CONSUMPTION", "PRODUCTION_OUTPUT", "PAYMENT", "RECONCILIATION", "CREDIT_RISK_EVENT", "CASH_TRANSACTION", "BANK_DEPOSIT", "GENERAL_LEDGER_ENTRY", "APPROVAL_EVENT"} else "STATE" if name in {"STOCK_SNAPSHOT", "STOCK_CURRENT", "CUSTOMER_CREDIT_STATE", "MRP_PARAMETER", "FORECAST_DEFINITION", "FORECAST_LINE", "WAREHOUSE_BRANCH_MAPPING", "WAREHOUSE_ROLE", "PAYMENT_TERM"} else "DERIVED" if name in {"CUSTOMER_CREDIT_STATE", "FORECAST_LINE"} else "REFERENCE"
        if name == "CUSTOMER_CREDIT_STATE":
            concept = "DERIVED"
        if name == "FORECAST_LINE":
            concept = "DERIVED"
        status = "CONFIRMED" if classification == "CORE_V1" and name not in {"WAREHOUSE_BRANCH_MAPPING"} else "PROPOSED" if classification in {"CORE_LATER", "SPECIALIZED", "OUT_OF_SCOPE"} else "CONFIRMED"
        confidence = "CONFIRMED" if name in {"PRODUCT", "CUSTOMER", "SUPPLIER", "WAREHOUSE", "BRANCH", "SALE_DOCUMENT", "SALE_LINE", "INVENTORY_MOVEMENT", "STOCK_CURRENT", "PURCHASE_ORDER", "GOODS_RECEIPT", "SUPPLIER_INVOICE", "PURCHASE_RETURN", "TRANSFER", "TRANSFER_LINE", "PRODUCTION_ORDER", "COMPONENT_CONSUMPTION", "PRODUCTION_OUTPUT", "PAYMENT", "RECONCILIATION"} else "PROPOSED"
        rows.append({
            "canonical_entity": name,
            "classification": classification,
            "concept_type": concept,
            "business_definition": definition,
            "grain": grain,
            "natural_key_candidate": natural_key,
            "surrogate_key_needed": surrogate,
            "time_semantics": time_semantics,
            "source_systems": sources,
            "status": status,
            "confidence": confidence,
            "source_evidence": EVIDENCE,
        })
    return rows


RELATIONSHIPS = [
    ("PRODUCT", "PRODUCT_GROUP", "product_group_id", "N:1", "CONFIRMED", "Product belongs to product group", "OITM/OITB"),
    ("WAREHOUSE_BRANCH_MAPPING", "WAREHOUSE", "canonical_warehouse_id", "N:1", "CONFIRMED", "Mapping references warehouse", "almacenOficina.xlsx;OWHS"),
    ("WAREHOUSE_BRANCH_MAPPING", "BRANCH", "canonical_branch_id", "N:1", "PROPOSED", "Mapping references branch with temporal validity", "almacenOficina.xlsx has no validity"),
    ("SALE_DOCUMENT", "SALE_LINE", "canonical_sale_document_id", "1:N", "CONFIRMED", "Document header to lines", "OINV/INV1;legacy sale families"),
    ("CREDIT_NOTE", "CREDIT_NOTE_LINE", "canonical_credit_note_id", "1:N", "CONFIRMED", "Credit-note header to lines", "ORIN/RIN1"),
    ("SALE_DOCUMENT", "CUSTOMER", "canonical_customer_id", "N:1", "CONFIRMED", "Sales document business partner", "OINV.CardCode/OCRD"),
    ("SALE_LINE", "PRODUCT", "canonical_product_id", "N:1", "CONFIRMED", "Sold item", "INV1.ItemCode/OITM"),
    ("CREDIT_NOTE_LINE", "PRODUCT", "canonical_product_id", "N:1", "CONFIRMED", "Credited item", "RIN1.ItemCode/OITM"),
    ("INVENTORY_MOVEMENT", "PRODUCT", "canonical_product_id", "N:1", "CONFIRMED", "Movement item", "OINM.ItemCode"),
    ("INVENTORY_MOVEMENT", "WAREHOUSE", "canonical_warehouse_id", "N:1", "CONFIRMED", "Movement warehouse", "OINM.Warehouse/OWHS"),
    ("SALE_LINE", "INVENTORY_MOVEMENT", "source_document_id/base_reference", "1:N", "LIKELY", "Sale may generate stock movement; not universal", "saleSB1Product/movProductSB1;OINV/OINM"),
    ("STOCK_SNAPSHOT", "PRODUCT", "canonical_product_id", "N:1", "CONFIRMED", "Snapshot product", "movProduct;OITW/OINM"),
    ("STOCK_SNAPSHOT", "WAREHOUSE", "canonical_warehouse_id", "N:1", "CONFIRMED", "Snapshot warehouse", "movProduct;OITW/OINM"),
    ("STOCK_CURRENT", "PRODUCT", "canonical_product_id", "N:1", "CONFIRMED", "Current stock product", "OITW"),
    ("STOCK_CURRENT", "WAREHOUSE", "canonical_warehouse_id", "N:1", "CONFIRMED", "Current stock warehouse", "OITW"),
    ("PURCHASE_REQUEST", "PURCHASE_ORDER", "base_request_id", "0..N", "PROPOSED", "Request can precede order; approval not fully evidenced", "OPRQ/PRQ1;GAP-005"),
    ("PURCHASE_ORDER", "SUPPLIER_INVOICE", "BaseEntry/BaseType", "1:N", "CONFIRMED", "PO to AP invoice line", "OPOR/POR1→OPCH/PCH1"),
    ("SUPPLIER_INVOICE", "GOODS_RECEIPT", "BaseEntry/BaseType", "1:N", "CONFIRMED", "AP invoice to goods receipt", "OPCH/PCH1→OPDN/PDN1"),
    ("PURCHASE_ORDER", "GOODS_RECEIPT", "BaseEntry/BaseType", "1:N", "CONFIRMED", "Direct PO to goods receipt", "OPOR/POR1→OPDN/PDN1"),
    ("PURCHASE_RETURN", "SUPPLIER_INVOICE", "base_document_id", "N:0..1", "PROPOSED", "Return references prior purchase document when present", "ORPD/RPD1"),
    ("TRANSFER", "TRANSFER_LINE", "canonical_transfer_id", "1:N", "CONFIRMED", "Transfer header to lines", "OWTR/WTR1"),
    ("TRANSFER_LINE", "INVENTORY_MOVEMENT", "source_document_id/source_line_id", "1:2", "CONFIRMED", "Transfer creates origin out and destination in accounting movements", "WTR1→OINM TT67"),
    ("BOM", "BOM_COMPONENT", "bom_id", "1:N", "CONFIRMED", "BOM parent to components", "OITT/ITT1"),
    ("PRODUCTION_ORDER", "COMPONENT_CONSUMPTION", "source_document_id/base_entry", "1:N", "CONFIRMED", "Order to actual issue lines", "OWOR/IGE1"),
    ("PRODUCTION_ORDER", "PRODUCTION_OUTPUT", "source_document_id/base_entry", "1:N", "CONFIRMED", "Order to actual output lines", "OWOR/IGN1"),
    ("PRODUCTION_ORDER", "BOM_COMPONENT", "historical_order_component", "1:N", "CONFIRMED", "WOR1 preserves order-time recipe", "WOR1"),
    ("PAYMENT", "RECONCILIATION", "source_native_id", "1:N", "CONFIRMED", "Payment can participate in settlement", "ORCT/OVPM→ITR1/OITR"),
    ("SALE_DOCUMENT", "RECONCILIATION", "source_native_id", "1:N", "CONFIRMED", "Receivable settlement member", "OINV→ITR1/OITR"),
    ("RECONCILIATION", "CUSTOMER_CREDIT_STATE", "as_of_date", "N:1", "CONFIRMED", "Settlement contributes to as-of credit state", "OITR/ITR1"),
    ("CUSTOMER", "CUSTOMER_CREDIT_STATE", "canonical_customer_id", "1:N", "CONFIRMED", "Customer has dated credit states", "credit gates"),
    ("USER", "SALE_DOCUMENT", "source_user_id", "1:N", "CONFIRMED", "User of transaction where available", "OUSR/UserSign; attribution gates"),
    ("SALESPERSON", "SALE_DOCUMENT", "salesperson_id", "1:N", "CONFIRMED", "Salesperson attribution", "OSLP/OINV"),
    ("EMPLOYEE", "USER", "employee_id", "0..1:0..1", "CONFIRMED", "User-to-employee where populated", "OUSR/OHEM"),
    ("SALESPERSON", "EMPLOYEE", "salesperson_id", "N:1", "CONFIRMED", "Employee-to-salesperson where populated", "OHEM/OSLP"),
    ("FORECAST_DEFINITION", "FORECAST_LINE", "forecast_id", "1:N", "PROPOSED", "Forecast header to rows", "OFCT/FCT1"),
    ("MRP_PARAMETER", "PRODUCT", "canonical_product_id", "N:1", "PROPOSED", "Planning parameter product", "OITM/OITW"),
    ("LOT_SERIAL", "INVENTORY_MOVEMENT", "item/transaction reference", "0..N:1", "LIKELY", "Batch/serial trace where populated", "IBT1/OBTN"),
    ("GENERAL_LEDGER_ENTRY", "PAYMENT", "TransId", "0..1:1", "CONFIRMED", "Payment accounting entry", "ORCT/OVPM→OJDT/JDT1"),
    ("BANK_DEPOSIT", "GENERAL_LEDGER_ENTRY", "TransAbs/TransId", "1:1", "CONFIRMED", "Deposit accounting entry", "ODPS→OJDT"),
]

SOURCE_ROWS = []
DOMAIN_BY_ENTITY = {
    "PRODUCT": "PRODUCTOS",
    "PRODUCT_GROUP": "PRODUCTOS",
    "CUSTOMER": "CLIENTES",
    "SUPPLIER": "PROVEEDORES",
    "WAREHOUSE": "STOCK_E_INVENTARIOS",
    "BRANCH": "VENTAS",
    "WAREHOUSE_BRANCH_MAPPING": "STOCK_E_INVENTARIOS",
    "SALE_DOCUMENT": "VENTAS",
    "SALE_LINE": "VENTAS",
    "CREDIT_NOTE": "CRÉDITO_Y_DEUDORES",
    "CREDIT_NOTE_LINE": "CRÉDITO_Y_DEUDORES",
    "INVENTORY_MOVEMENT": "STOCK_E_INVENTARIOS",
    "STOCK_SNAPSHOT": "STOCK_E_INVENTARIOS",
    "STOCK_CURRENT": "STOCK_E_INVENTARIOS",
    "PURCHASE_REQUEST": "COMPRAS_Y_ABASTECIMIENTO",
    "PURCHASE_ORDER": "COMPRAS_Y_ABASTECIMIENTO",
    "GOODS_RECEIPT": "COMPRAS_Y_ABASTECIMIENTO",
    "SUPPLIER_INVOICE": "COMPRAS_Y_ABASTECIMIENTO",
    "PURCHASE_RETURN": "COMPRAS_Y_ABASTECIMIENTO",
    "TRANSFER": "TRANSFERENCIAS_Y_DEPÓSITOS",
    "TRANSFER_LINE": "TRANSFERENCIAS_Y_DEPÓSITOS",
    "BOM": "PRODUCCIÓN",
    "BOM_COMPONENT": "PRODUCCIÓN",
    "PRODUCTION_ORDER": "PRODUCCIÓN",
    "COMPONENT_CONSUMPTION": "PRODUCCIÓN",
    "PRODUCTION_OUTPUT": "PRODUCCIÓN",
    "PAYMENT": "COBRANZAS",
    "RECONCILIATION": "COBRANZAS",
    "CUSTOMER_CREDIT_STATE": "CRÉDITO_Y_DEUDORES",
    "USER": "USUARIOS_ROLES_Y_PERMISOS",
    "SALESPERSON": "VENTAS",
}
for name, classification, *_rest in CORE:
    primary = "SAP_HANA"
    secondary = "LEGACY_DS" if name in {"PRODUCT", "PRODUCT_GROUP", "CUSTOMER", "SUPPLIER", "WAREHOUSE", "BRANCH", "SALE_DOCUMENT", "SALE_LINE", "CREDIT_NOTE", "CREDIT_NOTE_LINE", "PAYMENT", "RECONCILIATION", "SUPPLIER_INVOICE"} else "NONE"
    historical = "LEGACY_DS" if name in {"PRODUCT", "PRODUCT_GROUP", "CUSTOMER", "SUPPLIER", "WAREHOUSE", "BRANCH", "SALE_DOCUMENT", "SALE_LINE", "CREDIT_NOTE", "CREDIT_NOTE_LINE", "INVENTORY_MOVEMENT", "STOCK_SNAPSHOT", "PURCHASE_REQUEST", "PURCHASE_ORDER", "SUPPLIER_INVOICE", "PAYMENT", "RECONCILIATION"} else "NONE"
    validation = "SAP_HANA" if primary == "SAP_HANA" else "NONE"
    period = "SAP_VALIDATED_CURRENT_AND_HISTORICAL;LEGACY_OBSERVED_2012-2024;cutover=NOT_DECLARED"
    confidence = "CONFIRMED" if name not in {"WAREHOUSE_BRANCH_MAPPING", "STOCK_SNAPSHOT", "PURCHASE_REQUEST"} else "PROPOSED"
    rationale = "SAP evidence is authoritative for validated operational concepts; legacy remains historical until crosswalk and temporal reconciliation close."
    if name == "WAREHOUSE_BRANCH_MAPPING":
        primary, secondary, historical, validation = "EXTERNAL_FILES", "SAP_HANA", "EXTERNAL_FILES", "SAP_HANA"
        rationale = "almacenOficina.xlsx confirms 51→7 current observed mapping; no historical validity is known."
    if name == "STOCK_SNAPSHOT":
        primary, secondary, historical, validation = "DERIVED_FROM_SOURCE_SNAPSHOT", "SAP_HANA", "LEGACY_DS", "SAP_HANA"
        rationale = "A snapshot is a dated observation, not an authority independent of its source cut."
    SOURCE_ROWS.append({"canonical_entity": name, "domain": DOMAIN_BY_ENTITY[name], "period_scope": period, "primary_source": primary, "secondary_source": secondary, "historical_source": historical, "validation_source": validation, "confidence": confidence, "rationale": rationale})

SNAPSHOTS = [
    ("movProductSB1", "INVENTORY_MOVEMENT", "PERIOD_SNAPSHOT", "No concatenation. Treat each file as an observation of movement rows; deduplicate only on strong source transaction identity. Unresolved collisions remain quarantined.", "2022-04..2024-05", "LIKELY", "TransNum+DocLineNum+ItemCode+Warehouse; candidate duplicates=181384"),
    ("movProduct", "STOCK_SNAPSHOT", "PERIOD_SNAPSHOT", "Interpret as product×warehouse×period aggregate evidence, not atomic movements and not directly as current stock.", "2017-01..2022-04", "CONFIRMED", "WareHouseCode+ProductCode+YMD; ProductMovCant"),
    ("saleProduct", "SALE_LINE", "PERIOD_SNAPSHOT", "Treat as legacy sales observation; select one declared cutoff per query and do not append overlapping monthly files.", "2018-01..2022-04", "LIKELY", "business/document fields; source key not fully formal"),
    ("saleSB1Product", "SALE_LINE", "PERIOD_SNAPSHOT", "Treat as enriched invoice-line observation, not new sales events per file; preserve source snapshot and deduplicate by document/line where valid.", "2018-01..2024-05", "LIKELY", "DocEntry+line/item candidates; 3.58M diagnostic duplicates with short key"),
    ("ncB1Product", "CREDIT_NOTE_LINE", "PERIOD_SNAPSHOT", "Credit-note observations remain separate from gross sales; apply one cutoff and document fu_* schema variants.", "2022-04..2024-06", "POSSIBLE", "DocEntry/line/item candidates"),
    ("purchase", "PURCHASE_ORDER", "PERIOD_SNAPSHOT", "Do not sum files. Select latest valid observation for a document line or event cutoff; preserve source snapshot.", "2012-03..2022-03", "LIKELY", "NroOrden+PurchaseProductCode"),
    ("purchaseExpense", "SUPPLIER_EXPENSE", "PERIOD_SNAPSHOT", "Supporting legacy expense observation; not a second supplier invoice fact until reconciled.", "2012-01..2022-04", "PROPOSED", "NroOrden+ProductCode has repeated observations"),
    ("cash", "CASH_TRANSACTION", "PERIOD_SNAPSHOT", "Observation family; never add monthly files without a transaction identity and cutoff rule.", "2019-01..2022-04", "PROPOSED", "NroTransaccion diagnostic key"),
    ("cuentasxCobrar", "CUSTOMER_CREDIT_STATE", "PERIOD_SNAPSHOT", "State at a cutoff, not a payment event; use as-of semantics and preserve open/paid classification source.", "2020-01..2022-03", "LIKELY", "customer/debt fields and filename snapshots"),
    ("productTracking", "PRODUCT_TRACKING", "PERIOD_SNAPSHOT", "Tracking observations are not inventory movements until lot/event equivalence is proven.", "2019-01..2022-04", "UNKNOWN", "NroTrasaccion+ProductCode+TrackingDate"),
    ("paymentB1", "PAYMENT", "PERIOD_SNAPSHOT", "Payment observations are not appended across snapshots; settlement authority remains OITR/ITR1 when SAP is available.", "2022-04..2023-05", "POSSIBLE", "DocEntry"),
    ("reconB1", "RECONCILIATION", "PERIOD_SNAPSHOT", "Use reconciliation identity and as-of date; do not replace SAP settlement semantics with snapshot totals.", "2022-04..2023-05", "LIKELY", "ReconNum+LineSeq"),
    ("product/productSB1/clientSB1/wareHouseSB1", "REFERENCE", "FULL_SNAPSHOT", "Master observation valid only at declared source snapshot; never silently backfill historical validity.", "static/2021-12..2024-06", "LIKELY", "native master IDs"),
    ("OITW", "STOCK_CURRENT", "CURRENT_STATE", "Current state only; use extraction time as system time and do not backdate it.", "SAP current", "CONFIRMED", "ItemCode+WhsCode"),
    ("OINM", "INVENTORY_MOVEMENT", "APPEND_ONLY_EVENT", "Inventory ledger events are atomic source facts; reversals/cancellations are events, not deleted history.", "SAP historical", "CONFIRMED", "TransNum+TransSeq"),
    ("OFCT/FCT1 and OITM/OITW planning fields", "FORECAST_DEFINITION/MRP_PARAMETER", "CURRENT_STATE", "Configuration is not observed behavior; version only when source validity or extraction supports it.", "SAP current", "CONFIRMED", "forecast/parameter native IDs"),
]

SNAPSHOT_ROWS = [{"source_family_or_dataset": a, "canonical_target": b, "snapshot_type": c, "policy": d, "observed_scope": e, "confidence": f, "identity_candidate": g} for a,b,c,d,e,f,g in SNAPSHOTS]

CROSSWALKS = [
    ("XW-001", "PRODUCT", "canonical_product_id", "legacy_product_code", "sap_item_code", "PROPOSED_CONTRACT", "UNKNOWN", "valid_from/valid_to", "manual+evidence mapping; never coalesce code changes silently"),
    ("XW-002", "CUSTOMER", "canonical_customer_id", "legacy_customer_code", "sap_card_code", "PROPOSED_CONTRACT", "UNKNOWN", "valid_from/valid_to", "CardCode likely stable only within SAP; historical identity needs reconciliation"),
    ("XW-003", "SUPPLIER", "canonical_supplier_id", "legacy_supplier_code", "sap_card_code", "PROPOSED_CONTRACT", "UNKNOWN", "valid_from/valid_to", "OCRD is SAP authority; legacy equivalence not closed"),
    ("XW-004", "WAREHOUSE", "canonical_warehouse_id", "legacy_warehouse_code", "sap_whs_code", "PROPOSED_CONTRACT", "PARTIAL", "valid_from/valid_to", "warehouse code systems differ; 51 legacy mapped rows vs 82 current SAP warehouses"),
    ("XW-005", "BRANCH", "canonical_branch_id", "legacy_office_code", "sap_branch_or_office_code", "PROPOSED_CONTRACT", "PARTIAL", "valid_from/valid_to", "almacenOficina.xlsx confirms current observed mapping without history"),
    ("XW-006", "SALESPERSON", "canonical_salesperson_id", "legacy_salesperson_code", "sap_slp_code", "PROPOSED_CONTRACT", "PARTIAL", "valid_from/valid_to", "OSLP and attribution evidence current; legacy identity not fully closed"),
    ("XW-007", "USER", "canonical_user_id", "legacy_user_id_or_name", "sap_user_id/login", "PROPOSED_CONTRACT", "PARTIAL", "valid_from/valid_to", "current OUSR/employee attribution exists; historical authorization unavailable"),
]
CROSSWALK_ROWS = [{"crosswalk_id": a, "canonical_entity": b, "canonical_id_contract": c, "legacy_native_id": d, "sap_native_id": e, "mapping_status": f, "confidence": g, "validity_contract": h, "mapping_source_and_rule": i} for a,b,c,d,e,f,g,h,i in CROSSWALKS]

LINEAGE_FIELDS = [
    ("source_system", "REQUIRED", "All", "Controlled value: SAP_HANA, LEGACY_DS, LEGACY_DS0, EXTERNAL_FILES, or explicitly derived source."),
    ("source_table_or_dataset", "REQUIRED", "All", "SAP table, legacy family, file dataset, or named upstream product."),
    ("source_native_key", "REQUIRED", "All", "Canonical serialized native key; UNKNOWN only with a quality flag."),
    ("source_document_type", "OPTIONAL", "Event/document products", "Required when source has a document type; not applicable to pure master rows."),
    ("source_document_id", "REQUIRED", "Document lines and document facts", "SAP DocEntry or legacy document key when available."),
    ("source_line_id", "REQUIRED", "Line products", "SAP LineNum/line key; required to avoid header fanout."),
    ("source_transaction_id", "REQUIRED", "Movement, payment, reconciliation, ledger, approval events", "TransNum, payment key, ReconNum/member, or equivalent."),
    ("source_file", "REQUIRED", "Legacy file-derived products", "Relative source path/name; immutable source identity."),
    ("source_snapshot_at", "REQUIRED", "Snapshot-derived products", "Observed cutoff/extraction declared by source evidence; never inferred from filename alone."),
    ("source_extracted_at", "REQUIRED", "All", "Timestamp when upstream was extracted/read."),
    ("ingested_at", "REQUIRED", "All future products", "Timestamp when canonical pipeline accepted the row."),
    ("transformation_version", "REQUIRED", "All transformed products", "Code/transformation contract version."),
    ("semantic_version", "REQUIRED", "All products and derived metrics", "Definition version; changes are not silent."),
    ("sap_objtype", "OPTIONAL", "SAP document-traceable products", "SAP ObjType when applicable; null for non-SAP or unavailable trace."),
    ("sap_docentry", "OPTIONAL", "SAP document-traceable products", "SAP DocEntry when available."),
    ("sap_linenum", "OPTIONAL", "SAP line-traceable products", "SAP LineNum when available."),
    ("sap_transnum", "OPTIONAL", "SAP movement-traceable products", "SAP TransNum when available."),
    ("sap_whscode", "OPTIONAL", "Warehouse-scoped SAP products", "SAP WhsCode when applicable."),
    ("sap_itemcode", "OPTIONAL", "Product-scoped SAP products", "SAP ItemCode when applicable."),
]
LINEAGE_PRODUCTS = [
    ("reference_master", "Reference/master rows", "REFERENCE"),
    ("document_header", "Atomic document headers", "EVENT"),
    ("document_line", "Atomic document lines", "EVENT"),
    ("movement_event", "Inventory/production movement events", "EVENT"),
    ("state_snapshot", "State/snapshot products", "STATE"),
    ("derived_state", "As-of or calculated state", "DERIVED"),
    ("legacy_observation", "Legacy family observations", "STATE/EVENT"),
    ("business_denormalized", "Enriched business products", "DERIVED"),
]
LINEAGE_ROWS = []
for product, applies, kind in LINEAGE_PRODUCTS:
    for field, requirement, field_scope, rule in LINEAGE_FIELDS:
        if field_scope == "All":
            req = requirement
        elif product == "reference_master":
            req = "NOT_APPLICABLE" if field in {"source_document_type", "source_document_id", "source_line_id", "source_transaction_id", "source_snapshot_at", "sap_linenum", "sap_transnum"} else ("OPTIONAL" if requirement == "REQUIRED" else requirement)
        elif product == "document_header":
            req = "NOT_APPLICABLE" if field in {"source_line_id", "source_transaction_id", "source_file", "source_snapshot_at", "sap_linenum", "sap_transnum"} else requirement
        elif product == "document_line":
            req = "NOT_APPLICABLE" if field in {"source_transaction_id", "source_file", "source_snapshot_at", "sap_transnum"} else requirement
        elif product == "movement_event":
            req = "NOT_APPLICABLE" if field in {"source_file", "source_snapshot_at"} else ("REQUIRED" if field == "source_transaction_id" else requirement)
        elif product == "state_snapshot":
            req = "NOT_APPLICABLE" if field in {"source_document_type", "source_document_id", "source_line_id", "source_transaction_id", "sap_linenum", "sap_transnum"} else ("REQUIRED" if field == "source_snapshot_at" else requirement)
        elif product == "derived_state":
            req = "NOT_APPLICABLE" if field in {"source_document_type", "source_document_id", "source_line_id", "source_transaction_id", "source_file", "sap_linenum", "sap_transnum"} else ("REQUIRED" if field in {"source_snapshot_at", "semantic_version"} else requirement)
        elif product == "legacy_observation":
            req = "NOT_APPLICABLE" if field in {"sap_objtype", "sap_docentry", "sap_linenum", "sap_transnum", "sap_whscode", "sap_itemcode"} else ("REQUIRED" if field in {"source_file", "source_snapshot_at"} else requirement)
        else:
            req = "OPTIONAL" if requirement == "REQUIRED" and field in {"source_document_id", "source_line_id", "source_transaction_id", "source_file", "source_snapshot_at"} else requirement
        LINEAGE_ROWS.append({"contract_profile": product, "field_name": field, "requirement": req, "applies_to": applies, "rule": rule})

SECURITY_ROWS = [
    ("inventory", "inventory_movements;stock_snapshots;stock_current;warehouse_transfers", "warehouse_id", "cost;movement_user;warehouse", "YES", "administrator/all in this gate", "future filter before retrieval"),
    ("sales", "sales_documents;sales_lines", "branch_id;salesperson_id;channel", "customer;price;cost;margin", "CONDITIONAL", "administrator/all in this gate", "scope before metrics and retrieval"),
    ("purchases", "purchase_cycle;purchase_requests", "supplier_id;branch_id", "supplier;purchase_price;cost", "CONDITIONAL", "administrator/all in this gate", "supplier and organization scope"),
    ("production", "bom;production_orders;production_consumption;production_output", "warehouse_id;plant_id", "formulation;cost;output", "CONDITIONAL", "administrator/all in this gate", "BOM/formulation may require column permission"),
    ("credit", "customer_credit_state;payments;reconciliations", "customer_id;portfolio_id", "credit_limit;customer_debt", "CONDITIONAL", "administrator/all in this gate", "as-of state filtered before retrieval"),
    ("finance", "payments;reconciliations;general_ledger", "legal_entity_id;branch_id", "bank_account;debt;margin", "CONDITIONAL", "administrator/all in this gate", "currency and entity scopes"),
    ("hr", "employee;payroll_detail", "organizational_scope", "salary;employee_identity", "NO_FOR_V1", "administrator/all in this gate", "payroll detail out of initial scope"),
    ("users", "user;approval_event", "organizational_scope", "user_activity;authorization", "CONDITIONAL", "administrator/all in this gate", "historical authorization unavailable"),
    ("configuration", "mrp_configuration;forecast", "company_id;warehouse_id", "forecast;policy;configuration", "CONDITIONAL", "administrator/all in this gate", "configuration is not behavior"),
]
SECURITY_CONTRACT_ROWS = [{"security_domain": a, "data_products": b, "organizational_scope_dimension": c, "sensitive_columns_or_metrics": d, "cross_scope_aggregation_allowed": e, "gate_access": f, "enforcement_contract": g} for a,b,c,d,e,f,g in SECURITY_ROWS]

PRODUCTS = [
    ("product_master", "REFERENCE", "PRODUCT/PRODUCT_GROUP", "atomic", "inventory", "product_id", "identity and master attributes"),
    ("customer_master", "REFERENCE", "CUSTOMER", "atomic", "credit;sales", "customer_id", "customer identity"),
    ("supplier_master", "REFERENCE", "SUPPLIER", "atomic", "purchases", "supplier_id", "supplier identity"),
    ("warehouse_master", "REFERENCE", "WAREHOUSE/WAREHOUSE_ROLE", "atomic", "inventory", "warehouse_id", "warehouse identity and role"),
    ("warehouse_branch_mapping", "REFERENCE", "WAREHOUSE_BRANCH_MAPPING/BRANCH", "atomic", "inventory;sales", "warehouse_id;branch_id;valid_from", "temporal organization map"),
    ("sales_documents", "ATOMIC", "SALE_DOCUMENT", "atomic", "sales", "sale_document_id", "document state and dates"),
    ("sales_lines", "ATOMIC", "SALE_LINE", "atomic", "sales", "sale_line_id", "gross sale lines"),
    ("credit_notes", "ATOMIC", "CREDIT_NOTE/CREDIT_NOTE_LINE", "atomic", "sales;credit", "credit_note_line_id", "credit reductions"),
    ("inventory_movements", "ATOMIC", "INVENTORY_MOVEMENT", "atomic", "inventory", "inventory_movement_id", "movement events"),
    ("stock_snapshots", "ATOMIC", "STOCK_SNAPSHOT", "atomic", "inventory", "product_id;warehouse_id;snapshot_at", "dated stock state"),
    ("stock_current", "ATOMIC", "STOCK_CURRENT", "atomic", "inventory", "product_id;warehouse_id", "current state"),
    ("purchase_cycle", "ATOMIC+BUSINESS", "PURCHASE_REQUEST/PURCHASE_ORDER/GOODS_RECEIPT/SUPPLIER_INVOICE/PURCHASE_RETURN", "mixed", "purchases", "document_line_id", "cycle view over atomic facts"),
    ("purchase_requests", "ATOMIC", "PURCHASE_REQUEST", "atomic", "purchases", "request_line_id", "requested procurement"),
    ("bom", "ATOMIC", "BOM/BOM_COMPONENT", "atomic", "production", "bom_component_id", "formula/version"),
    ("production_orders", "ATOMIC", "PRODUCTION_ORDER", "atomic", "production", "production_order_id", "planned production"),
    ("production_consumption", "ATOMIC", "COMPONENT_CONSUMPTION", "atomic", "production", "consumption_id", "actual component issues"),
    ("production_output", "ATOMIC", "PRODUCTION_OUTPUT", "atomic", "production", "output_id", "actual receipts"),
    ("warehouse_transfers", "ATOMIC", "TRANSFER/TRANSFER_LINE", "atomic", "inventory", "transfer_line_id", "accounting transfer event"),
    ("payments", "ATOMIC", "PAYMENT", "atomic", "credit;finance", "payment_id", "cash settlement events"),
    ("reconciliations", "ATOMIC", "RECONCILIATION", "atomic", "credit;finance", "reconciliation_member_id", "settlement evidence"),
    ("customer_credit_state", "DERIVED", "CUSTOMER_CREDIT_STATE", "derived", "credit", "customer_id;as_of_date", "historical customer state"),
    ("forecast", "CORE_LATER", "FORECAST_DEFINITION/FORECAST_LINE", "atomic+derived", "configuration", "forecast_line_id", "configured/observed forecast, never inferred behavior"),
    ("mrp_configuration", "CORE_LATER", "MRP_PARAMETER", "atomic", "configuration", "product_id;warehouse_id;parameter;valid_from", "planning parameters"),
    ("user_access_reference", "REFERENCE", "USER/SALESPERSON/EMPLOYEE", "atomic", "users", "user_id", "current identity/capability reference"),
    ("product_flow", "BUSINESS", "PRODUCT + SALE_LINE + INVENTORY_MOVEMENT + TRANSFER_LINE", "denormalized", "inventory;sales", "product_id;event_id", "fast product flow questions"),
    ("product_360", "BUSINESS", "PRODUCT + masters + sales + stock + purchase", "denormalized", "inventory;sales;purchases", "product_id", "product-centric conversational read model"),
    ("inventory_360", "BUSINESS", "stock + movements + warehouse mapping", "denormalized", "inventory", "product_id;warehouse_id", "inventory questions without runtime fanout"),
    ("sales_360", "BUSINESS", "sale document/line + customer + seller + credit/payment", "denormalized", "sales;credit", "sale_line_id", "sales and receivable questions"),
    ("purchase_360", "BUSINESS", "purchase cycle + supplier + stock impact", "denormalized", "purchases;inventory", "purchase_line_id", "procurement questions"),
]
PRODUCT_ROWS = [{"data_product": a, "layer": b, "canonical_entities": c, "shape": d, "security_domain": e, "scope_dimension": f, "business_justification": g, "lineage_profile": "business_denormalized" if d == "denormalized" else "state_snapshot" if "snapshot" in a or a in {"stock_current"} else "document_line" if "line" in a or a in {"sales_documents", "purchase_cycle", "purchase_requests", "production_orders", "payments", "reconciliations"} else "reference_master"} for a,b,c,d,e,f,g in PRODUCTS]

BLOCKING = [
    ("GAP-001", "BLOCKING_LINEAGE", "Formal source metadata is absent for legacy Parquet", "Physical rows need a stable nullable lineage envelope", "Carry required lineage fields and quarantine UNKNOWN source identity", "HIGH"),
    ("GAP-002", "BLOCKING_TEMPORAL_POLICY", "Filename and contained business dates differ", "Physical snapshots need cutoff and observation timestamps", "Never concatenate overlapping family files without declared cutoff", "HIGH"),
    ("GAP-003", "BLOCKING_CANONICAL_MODEL", "movProductSB1 candidate duplicates and non-universal OINM join", "Atomic movement key cannot be assumed from short candidate", "Preserve source transaction identity; classify unresolved rows", "HIGH"),
    ("GAP-004", "BLOCKING_TEMPORAL_POLICY", "Historical validity of masters and warehouse-branch map absent", "Physical dimensions need validity columns and unknown history policy", "Version identities; do not backfill history silently", "HIGH"),
    ("GAP-005", "NON_BLOCKING", "Purchase approval/MRP execution not demonstrated", "Does not prevent V1 atomic purchase facts", "Keep approval/MRP behavior CORE_LATER", "MEDIUM"),
    ("GAP-006", "NON_BLOCKING", "Forecast rows do not prove operational use", "Forecast can remain configured/observed, not behavior", "Separate forecast definition from observed usage", "HIGH"),
    ("GAP-007", "NON_BLOCKING", "Safety stock semantics not confirmed", "MRP is CORE_LATER", "Preserve raw parameter and semantic status", "HIGH"),
    ("GAP-008", "NON_BLOCKING", "No MRP execution history/versioning", "No V1 atomic dependency", "No inferred execution events", "MEDIUM"),
    ("GAP-009", "NON_BLOCKING", "Lot/serial coverage incomplete", "Atomic movement remains valid without complete lot enrichment", "Keep lot/serial optional and partial", "MEDIUM"),
    ("GAP-010", "BLOCKING_LINEAGE", "Production-to-dispatch link is heuristic", "Cannot promise full order-to-dispatch trace", "Preserve heuristic link with confidence and no FK assertion", "HIGH"),
    ("GAP-011", "NON_BLOCKING", "Transfer accounting is not physical dispatch proof", "Transfer event product is still defined", "Name physical logistics as unavailable/derived", "HIGH"),
    ("GAP-012", "BLOCKING_SECURITY", "Historical authorization unavailable", "Security contract must exist before retrieval", "Declare domain/scope/column/metric filters in every product", "HIGH"),
    ("GAP-013", "NON_BLOCKING", "Management approvals external/heuristic", "Approval event is specialized, not V1 core", "Keep external evidence boundary", "MEDIUM"),
    ("GAP-014", "OUT_OF_INITIAL_SCOPE", "Detailed payroll object not identified", "Individual payroll is excluded from V1", "Keep aggregate HR cost separate", "HIGH"),
    ("GAP-015", "OUT_OF_INITIAL_SCOPE", "WHT transactional path not established", "WHT detail is excluded from V1", "Do not represent configuration as transactions", "HIGH"),
    ("GAP-016", "NON_BLOCKING", "External bank reconciliation not demonstrated", "Treasury source facts can be preserved without external match", "Mark external reconciliation unavailable", "MEDIUM"),
    ("GAP-017", "BLOCKING_CANONICAL_MODEL", "Legacy purchaseExpense/productTransform/cash mappings incomplete", "Cannot silently merge legacy families into SAP facts", "Keep specialized legacy products and explicit crosswalk status", "MEDIUM"),
    ("GAP-018", "BLOCKING_TEMPORAL_POLICY", "Historical cancellations/payments have differing watermarks", "As-of physical design needs source-specific cutoffs", "Use source-effective/system-time pair and no cross-source implicit cutover", "HIGH"),
]
BLOCKING_ROWS = [{"gap_id": a, "classification": b, "evidence_gap": c, "impact_on_next_gate": d, "v1_policy_or_next_action": e, "priority": f} for a,b,c,d,e,f in BLOCKING]

DECISIONS = [
    ("DEC-001", "Is movProductSB1 atomic canonical?", "No. It is a denormalized business precursor over INVENTORY_MOVEMENT plus dimensions; its source rows remain evidence until keys reconcile.", "Treat as atomic movement; treat as business product", "Enriched joins and duplicate candidate keys make atomic interpretation unsafe.", "Historical inventory; MAP-001", "CONFIRMED", "inventory product boundary"),
    ("DEC-002", "What is movProduct?", "A PERIOD_SNAPSHOT of INVENTORY_PERIOD_AGGREGATE/stock evidence, not INVENTORY_MOVEMENT and not automatically STOCK_CURRENT.", "Stock movement event; period aggregate; current state", "No document/transaction identity; product×warehouse×YMD grain.", "Historical inventory; SNAP-002", "CONFIRMED", "snapshot policy"),
    ("DEC-003", "How are sales reconciled?", "SALE_LINE is gross atomic sale; CREDIT_NOTE_LINE is separate reduction; net sales is derived. Payment state is separate.", "One net sales table; invoice-only fact", "OINV/INV1 and ORIN/RIN1 are distinct; settlement is OITR/ITR1.", "SAP inventory; rules settlement/as-of", "CONFIRMED", "sales/credit products"),
    ("DEC-004", "How are purchase cycle facts modeled?", "Requests, orders, receipts, supplier invoices and returns remain independent atomic line entities; purchase_cycle is a derived view.", "One lifecycle table; independent facts", "Validated BaseEntry links and anti-fanout requirements.", "SAP relationships; purchase gates", "CONFIRMED", "purchase product"),
    ("DEC-005", "What is production reconciliation?", "Expected/actual classifications EXACT, OVER, UNDER, NOT_CONSUMED, PARTIAL, ZERO are derived metrics over BOM/order/consumption/output.", "Store classifications as atomic facts", "Evidence defines them as comparison outputs; raw events must remain traceable.", "Production reconciliation gates", "CONFIRMED", "production metrics"),
    ("DEC-006", "What is transfer semantics?", "TRANSFER is an accounting inventory event with origin and destination; physical dispatch/receipt is not asserted.", "Physical logistics event", "SAP gate explicitly labels PHYSICAL_DISPATCH_SEMANTICS=ACCOUNTING_ONLY.", "Transfer gate; GAP-011", "CONFIRMED", "transfer boundary"),
    ("DEC-007", "What is customer credit state?", "A dated derived state reconstructible as-of T from documents, notes, payments and reconciliations; current state is insufficient.", "Current balance only", "Validated OITR/ITR1 and as-of semantics.", "Credit gates; GAP-018", "CONFIRMED", "credit product"),
    ("DEC-008", "What is source authority?", "SAP is primary for validated operational SAP-era/current facts; legacy is historical source for observed legacy windows; no silent cutover date is assumed.", "Single global source/cutover", "SAP/legacy overlap and mappings are partial.", "Both inventories; MAP-001..010", "CONFIRMED", "source-of-truth contract"),
    ("DEC-009", "How are identities joined?", "Use canonical surrogate IDs backed by a versioned crosswalk containing native IDs, validity, confidence and evidence; unresolved mappings are not joined.", "String-code coalescing", "Native code systems and historical validity are not uniform.", "Crosswalk contract; GAP-004/GAP-017", "CONFIRMED", "identity contract"),
    ("DEC-010", "How is warehouse→branch modeled?", "As warehouse_branch_mapping with validity interval; current 51→7 evidence is not projected backward.", "Static warehouse branch column", "almacenOficina.xlsx has no temporal validity.", "almacenOficina.xlsx; GAP-004", "CONFIRMED", "organization scope"),
    ("DEC-011", "How are legacy snapshots deduplicated?", "By declared source snapshot and strong native identity; same event across snapshots is not a new event. Weak collisions become UNKNOWN/quarantine.", "Append all files", "Inventory found repeated rows and filename/business-date divergence.", "Snapshot policy; GAP-002", "CONFIRMED", "temporal contract"),
    ("DEC-012", "What lineage is required for SAP?", "Preserve ObjType/DocEntry/LineNum/TransNum/WhsCode/ItemCode when applicable, with nullable fields and trace class FULL/PARTIAL/AGGREGATE_ONLY.", "Require every SAP field for every row", "Not all concepts have documents or all fields.", "SAP catalog and lineage contract", "CONFIRMED", "lineage contract"),
    ("DEC-013", "What is security during this gate?", "administrator/administrators has ALL, but every product declares security domain, organizational scope, sensitive columns/metrics and aggregation policy.", "No security metadata until RBAC", "SECURITY BEFORE RETRIEVAL is an architectural invariant.", "SAP security inventory; GAP-012", "CONFIRMED", "security contract"),
    ("DEC-014", "Where does movProductSB1-like UX live?", "Business denormalized product_flow/product_360 over atomic truth; runtime should not reconstruct dozens of joins per question.", "Canonical atomic table with all joined columns", "Preserves atomic truth and provides conversational latency.", "Historical inventory; performance objective", "PROPOSED", "business boundary"),
    ("DEC-015", "Are MRP/forecast facts V1 core?", "No. Configuration/forecast definition are CORE_LATER; configured, observed, inferred and unknown usage remain separate.", "Treat configuration as demand behavior", "SAP evidence does not prove operational execution.", "GAP-005..008; MRP gates", "CONFIRMED", "scope"),
    ("DEC-016", "Are payroll/WHT detail V1 core?", "No. Individual payroll and WHT transaction detail are OUT_OF_SCOPE; aggregate accounting evidence remains separate.", "Include all finance/HR tables", "Inputs explicitly identify unresolved material gaps and no need for V1 physical model.", "GAP-014/GAP-015", "CONFIRMED", "scope"),
    ("DEC-017", "How are metric definitions versioned?", "Each derived metric declares name, semantic_version, definition, valid_from and deprecated_at; historical rows retain the version used.", "Rewrite historical metric values silently", "Definitions can change without changing past meaning.", "Gate objective; semantic contract", "PROPOSED", "metric contract"),
]
DECISION_ROWS = [{"decision_id": a, "question": b, "decision": c, "alternatives": d, "reason": e, "evidence": f, "confidence": g, "impact": h} for a,b,c,d,e,f,g,h in DECISIONS]


def main() -> None:
    write_csv("canonical_entities.csv", entity_rows())
    write_csv("canonical_grain.csv", [row for row in entity_rows() if row["classification"] == "CORE_V1"])
    write_csv("canonical_relationships.csv", [{"relationship_id": f"REL-{i:03d}", "from_entity": a, "to_entity": b, "join_contract": c, "cardinality": d, "confidence": e, "business_meaning": f, "evidence": g} for i,(a,b,c,d,e,f,g) in enumerate(RELATIONSHIPS, 1)])
    write_csv("source_of_truth.csv", SOURCE_ROWS)
    write_csv("snapshot_policy.csv", SNAPSHOT_ROWS)
    write_csv("historical_sap_crosswalk.csv", [{"mapping_id": f"MAP-{i:03d}", "historical_family": a, "sap_source": b, "matching_fields": c, "granularity_comparison": d, "coverage_comparison": e, "semantic_differences": f, "confidence": g, "evidence": h} for i,(a,b,c,d,e,f,g,h) in enumerate([
        ("movProductSB1", "OINM + source documents", "TransNum/DocLineNum vs movement keys; ItemCode; Warehouse/WhsCode; TransType/BASE_REF", "legacy enriched line vs SAP ledger", "2022-04..2024-05 vs SAP historical/current", "No universal document FK; duplicate candidate keys", "LIKELY", "historical inventory; production/stock/transfer reports"),
        ("saleSB1Product", "OINV + INV1", "DocEntry; ItemCode; document/date/amount", "enriched invoice-line observation", "2018-01..2024-05 vs SAP extended window", "snapshot overlap and no formal extractor lineage", "LIKELY", "historical inventory; financial invoice contract"),
        ("ncB1Product", "ORIN + RIN1", "DocEntry/line/item/date/amount", "legacy NC observation", "2022-04..2024-06", "fu_* schema variants; equivalence incomplete", "POSSIBLE", "historical inventory; credit-note evidence"),
        ("productSB1", "OITM", "ItemCode and product attributes", "master snapshot vs current master", "2022-03..2024-06", "historical validity absent", "LIKELY", "historical inventory; stock/MRP"),
        ("clientSB1", "OCRD", "CardCode/CardName", "master snapshot", "static historical vs current", "customer history absent", "LIKELY", "historical inventory; customer/credit"),
        ("owhsSB1", "OWHS", "WhsCode/name", "small historical master vs current census", "unknown vs 82 current warehouses", "retired/renamed validity absent", "POSSIBLE", "historical inventory; production schema"),
        ("wareHouseSB1", "OWHS", "warehouse code/name", "enriched warehouse reference", "2021-12..2024-06", "temporal semantics not formal", "POSSIBLE", "historical inventory"),
        ("paymentB1", "ORCT + ITR1/OITR", "DocEntry/amount/date/reconciliation", "payment snapshot vs settlement ledger", "2022-04..2023-05", "RCT2 not settlement authority", "POSSIBLE", "historical inventory; financial reconciliation"),
        ("reconB1", "OITR + ITR1", "ReconNum/LineSeq/date/amount", "reconciliation snapshot", "2022-04..2023-05", "watermark and cancellation history unknown", "LIKELY", "historical inventory; reconciliation"),
        ("productTracking", "OBTN/IBT1 and/or legacy-only", "product/tracking date/lot", "tracking observation", "2019-01..2022-04", "lot/serial equivalence incomplete", "UNKNOWN", "historical inventory"),
    ], 1)])
    write_csv("identity_crosswalk.csv", CROSSWALK_ROWS)
    write_csv("lineage_contract.csv", LINEAGE_ROWS)
    write_csv("data_product_candidates.csv", PRODUCT_ROWS)
    write_csv("security_contract.csv", SECURITY_CONTRACT_ROWS)
    write_csv("blocking_gaps.csv", BLOCKING_ROWS)
    write_csv("decision_log.csv", DECISION_ROWS)
    summary = {
        "gate": "TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS",
        "historical_inventory_used": True,
        "sap_knowledge_inventory_used": True,
        "sap_accessed": False,
        "sap_access_purpose": "NONE",
        "sap_write_count": 0,
        "canonical_entities": len(ALL_ENTITIES),
        "canonical_relationships": len(RELATIONSHIPS),
        "core_v1_entities": sum(1 for row in entity_rows() if row["classification"] == "CORE_V1"),
        "data_product_candidates": len(PRODUCTS),
        "snapshot_policies": len(SNAPSHOTS),
        "lineage_contracts": len(LINEAGE_PRODUCTS),
        "identity_crosswalks": len(CROSSWALKS),
        "security_domains": len(SECURITY_ROWS),
        "blocking_gaps": sum(1 for row in BLOCKING if row[1].startswith("BLOCKING_")),
        "non_blocking_gaps": sum(1 for row in BLOCKING if row[1] == "NON_BLOCKING"),
        "out_of_initial_scope_gaps": sum(1 for row in BLOCKING if row[1] == "OUT_OF_INITIAL_SCOPE"),
        "production_parquets_created": 0,
        "source_files_moved": 0,
        "source_files_deleted": 0,
        "datalake_physical_layout_created": 0,
        "source_evidence": ["docs/TELCHI_HISTORICAL_DATA_INVENTORY_V1.md", "docs/TELCHI_SAP_KNOWLEDGE_INVENTORY_V1.md"],
    }
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
