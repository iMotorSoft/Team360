"""PHASE 6 — BUSINESS CAPABILITIES mapping (READ ONLY, pure logic).

Converts SAP B1 authorization codes (USR3/UGR1 PermId) and document
object types (ObjType) into a canonical business-capability taxonomy.

Mapping sources and confidence:
  - ObjType -> capability: EXACT (validated against real document tables)
  - SO1_AU_* addon permission names -> capability: STRONG (real names in OUPT)
  - Numeric standard B1 PermId (10001-10670) -> capability: HEURISTIC
    (standard SAP B1 authorization ID ranges; description table absent
    in TELCHI schema -> INFERRED, not VALIDATED)

Never asserts a capability without recording source + confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    EXACT = "EXACT"
    STRONG = "STRONG"
    HEURISTIC = "HEURISTIC"
    UNKNOWN = "UNKNOWN"


class MappingStatus(str, Enum):
    VALIDATED = "VALIDATED"
    INFERRED = "INFERRED"
    UNRESOLVED = "UNRESOLVED"


class AuthSource(str, Enum):
    DIRECT = "DIRECT"
    GROUP = "GROUP"
    SUPERUSER = "SUPERUSER"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CapabilityMapping:
    capability: str
    source: str
    code: str
    description: str
    sap_module: str
    mapping_status: MappingStatus
    confidence: Confidence
    evidence: str = ""


# ---------------------------------------------------------------------------
# ObjType -> capability (EXACT — validated against TELCHI document tables)
# ---------------------------------------------------------------------------
OBJTYPE_CAPABILITY: dict[str, CapabilityMapping] = {
    "13": CapabilityMapping("SALES_CREATE", "OBJTYPE", "13", "A/R Invoice",
                            "SALES", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OINV UserSign"),
    "14": CapabilityMapping("SALES_CREDIT_NOTE", "OBJTYPE", "14", "A/R Credit Note",
                            "SALES", MappingStatus.VALIDATED, Confidence.EXACT,
                            "ORIN UserSign"),
    "15": CapabilityMapping("SALES_DELIVERY", "OBJTYPE", "15", "Delivery",
                            "SALES", MappingStatus.VALIDATED, Confidence.EXACT,
                            "ODLN UserSign"),
    "16": CapabilityMapping("SALES_RETURN", "OBJTYPE", "16", "Returns",
                            "SALES", MappingStatus.VALIDATED, Confidence.EXACT,
                            "ORDN UserSign"),
    "17": CapabilityMapping("SALES_ORDER", "OBJTYPE", "17", "Sales Order",
                            "SALES", MappingStatus.VALIDATED, Confidence.EXACT,
                            "ORDR UserSign"),
    "18": CapabilityMapping("PURCHASE_CREATE", "OBJTYPE", "18", "A/P Invoice",
                            "PURCHASING", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OPCH UserSign"),
    "20": CapabilityMapping("PURCHASE_CREDIT_NOTE", "OBJTYPE", "20", "A/P Credit Note",
                            "PURCHASING", MappingStatus.VALIDATED, Confidence.EXACT,
                            "ORPC UserSign"),
    "22": CapabilityMapping("PURCHASE_ORDER", "OBJTYPE", "22", "Purchase Order",
                            "PURCHASING", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OPOR UserSign"),
    "24": CapabilityMapping("PAYMENT_CREATE", "OBJTYPE", "24", "Incoming Payment",
                            "CASH", MappingStatus.VALIDATED, Confidence.EXACT,
                            "ORCT UserSign"),
    "46": CapabilityMapping("OUTGOING_PAYMENT", "OBJTYPE", "46", "Outgoing Payment",
                            "CASH", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OVPM UserSign"),
    "59": CapabilityMapping("JOURNAL_ENTRY_CREATE", "OBJTYPE", "59", "Journal Entry",
                            "ACCOUNTING", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OJDT UserSign"),
    "60": CapabilityMapping("GOODS_ISSUE", "OBJTYPE", "60", "Goods Issue",
                            "INVENTORY", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OIGE UserSign"),
    "67": CapabilityMapping("STOCK_TRANSFER", "OBJTYPE", "67", "Inventory Transfer",
                            "INVENTORY", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OWTR UserSign"),
    "69": CapabilityMapping("GOODS_RECEIPT", "OBJTYPE", "69", "Goods Receipt",
                            "INVENTORY", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OIGN UserSign"),
    "147": CapabilityMapping("GOODS_RECEIPT_PO", "OBJTYPE", "147", "Goods Receipt PO",
                             "INVENTORY", MappingStatus.VALIDATED, Confidence.EXACT,
                             "OPDN UserSign"),
    "202": CapabilityMapping("PRODUCTION_ORDER", "OBJTYPE", "202", "Production Order",
                             "PRODUCTION", MappingStatus.VALIDATED, Confidence.EXACT,
                             "OWOR UserSign"),
    "203": CapabilityMapping("PRODUCTION_RECEIPT", "OBJTYPE", "203", "Production Receipt",
                             "PRODUCTION", MappingStatus.VALIDATED, Confidence.EXACT,
                             "OIGN/OWOR"),
    "321": CapabilityMapping("STOCK_ADJUST", "OBJTYPE", "321", "Stock Adjustment",
                             "INVENTORY", MappingStatus.INFERRED, Confidence.STRONG,
                             "OIAD (inferred)"),
}

# Canceled variants (UserSign2 = canceler)
OBJTYPE_CANCEL_CAPABILITY: dict[str, CapabilityMapping] = {
    "13": CapabilityMapping("SALES_CANCEL", "OBJTYPE", "13_CANCELED", "A/R Invoice Cancel",
                            "SALES", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OINV UserSign2 + CANCELED=Y"),
    "14": CapabilityMapping("SALES_CREDIT_NOTE_CANCEL", "OBJTYPE", "14_CANCELED", "A/R CN Cancel",
                            "SALES", MappingStatus.VALIDATED, Confidence.EXACT,
                            "ORIN UserSign2 + CANCELED=Y"),
    "24": CapabilityMapping("PAYMENT_CANCEL", "OBJTYPE", "24_CANCELED", "Incoming Payment Cancel",
                            "CASH", MappingStatus.VALIDATED, Confidence.EXACT,
                            "ORCT UserSign2 + Canceled=Y"),
    "46": CapabilityMapping("OUTGOING_PAYMENT_CANCEL", "OBJTYPE", "46_CANCELED", "Outgoing Payment Cancel",
                            "CASH", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OVPM UserSign2 + Canceled=Y"),
    "67": CapabilityMapping("STOCK_TRANSFER_CANCEL", "OBJTYPE", "67_CANCELED", "Transfer Cancel",
                            "INVENTORY", MappingStatus.VALIDATED, Confidence.EXACT,
                            "OWTR UserSign2 + Canceled=Y"),
}


# ---------------------------------------------------------------------------
# Retail One addon permissions (SO1_AU_*) -> capability
# Names are REAL (from OUPT), descriptions in Spanish from the addon.
# ---------------------------------------------------------------------------
SO1_CAPABILITY: dict[str, CapabilityMapping] = {
    "SO1_AU_01DescPorce": CapabilityMapping("DISCOUNT_OVERRIDE", "SO1_ADDON", "SO1_AU_01DescPorce",
        "Descuento en porcentaje", "RETAIL_ONE", MappingStatus.VALIDATED, Confidence.STRONG,
        "OUPT name"),
    "SO1_AU_01DescImporte": CapabilityMapping("DISCOUNT_OVERRIDE", "SO1_ADDON", "SO1_AU_01DescImporte",
        "Descuento en importe", "RETAIL_ONE", MappingStatus.VALIDATED, Confidence.STRONG,
        "OUPT name"),
    "SO1_AU_01DescEscala": CapabilityMapping("DISCOUNT_OVERRIDE", "SO1_ADDON", "SO1_AU_01DescEscala",
        "Descuento por escala", "RETAIL_ONE", MappingStatus.VALIDATED, Confidence.STRONG,
        "OUPT name"),
    "SO1_AU_01DescVolum": CapabilityMapping("DISCOUNT_OVERRIDE", "SO1_ADDON", "SO1_AU_01DescVolum",
        "Descuento por volumen", "RETAIL_ONE", MappingStatus.VALIDATED, Confidence.STRONG,
        "OUPT name"),
    "SO1_AU_01PrecUnico": CapabilityMapping("PRICE_OVERRIDE", "SO1_ADDON", "SO1_AU_01PrecUnico",
        "Precio único", "RETAIL_ONE", MappingStatus.VALIDATED, Confidence.STRONG,
        "OUPT name"),
    "SO1_AU_01CondCambPre": CapabilityMapping("PRICE_OVERRIDE", "SO1_ADDON", "SO1_AU_01CondCambPre",
        "Condiciones cambio de precio", "RETAIL_ONE", MappingStatus.VALIDATED, Confidence.STRONG,
        "OUPT name"),
    "SO1_AU_01ValDesc": CapabilityMapping("DISCOUNT_OVERRIDE", "SO1_ADDON", "SO1_AU_01ValDesc",
        "Vale de descuento", "RETAIL_ONE", MappingStatus.VALIDATED, Confidence.STRONG,
        "OUPT name"),
    "SO1_AU_01ValeDesc": CapabilityMapping("DISCOUNT_OVERRIDE", "SO1_ADDON", "SO1_AU_01ValeDesc",
        "Vale de descuento", "RETAIL_ONE", MappingStatus.VALIDATED, Confidence.STRONG,
        "OUPT name"),
    "SO1_AU_01FormaPago": CapabilityMapping("PAYMENT_CREATE", "SO1_ADDON", "SO1_AU_01FormaPago",
        "Formas de pago", "RETAIL_ONE", MappingStatus.INFERRED, Confidence.STRONG,
        "OUPT name (payment form config)"),
    "SO1_AU_01PagoConsol": CapabilityMapping("PAYMENT_RECONCILE", "SO1_ADDON", "SO1_AU_01PagoConsol",
        "Pagos globales", "RETAIL_ONE", MappingStatus.INFERRED, Confidence.STRONG,
        "OUPT name"),
    "SO1_AU_01PagosRPM": CapabilityMapping("PAYMENT_CREATE", "SO1_ADDON", "SO1_AU_01PagosRPM",
        "Notificación de pagos RPM", "RETAIL_ONE", MappingStatus.INFERRED, Confidence.STRONG,
        "OUPT name"),
}


# ---------------------------------------------------------------------------
# Numeric standard SAP B1 PermId -> capability (HEURISTIC by known ID ranges)
# ---------------------------------------------------------------------------
def numeric_perm_capability(perm_id: int) -> CapabilityMapping | None:
    """Classify standard SAP B1 authorization IDs by documented ranges.

    Confidence HEURISTIC: the TELCHI schema has no permission description
    table; ranges follow SAP B1 standard authorization numbering.
    """
    if 10001 <= perm_id <= 10099:
        return CapabilityMapping("SYSTEM_CONFIGURATION", "NUMERIC", str(perm_id),
            "Administration/General", "ADMINISTRATION",
            MappingStatus.INFERRED, Confidence.HEURISTIC, "B1 range 10001-10099")
    if 10100 <= perm_id <= 10199:
        return CapabilityMapping("ACCOUNTING_POST", "NUMERIC", str(perm_id),
            "Financials", "FINANCE", MappingStatus.INFERRED, Confidence.HEURISTIC,
            "B1 range 10100-10199")
    if 10200 <= perm_id <= 10299:
        return CapabilityMapping("SALES_CREATE", "NUMERIC", str(perm_id),
            "Sales Opportunities", "SALES", MappingStatus.INFERRED, Confidence.HEURISTIC,
            "B1 range 10200-10299")
    if 10300 <= perm_id <= 10399:
        return CapabilityMapping("SALES_CREATE", "NUMERIC", str(perm_id),
            "Sales A/R", "SALES", MappingStatus.INFERRED, Confidence.HEURISTIC,
            "B1 range 10300-10399")
    if 10400 <= perm_id <= 10499:
        return CapabilityMapping("PURCHASE_CREATE", "NUMERIC", str(perm_id),
            "Purchasing A/P", "PURCHASING", MappingStatus.INFERRED, Confidence.HEURISTIC,
            "B1 range 10400-10499")
    if 10500 <= perm_id <= 10599:
        return CapabilityMapping("MASTER_DATA_UPDATE", "NUMERIC", str(perm_id),
            "Business Partners", "MASTER_DATA", MappingStatus.INFERRED, Confidence.HEURISTIC,
            "B1 range 10500-10599")
    if 10600 <= perm_id <= 10699:
        return CapabilityMapping("STOCK_ADJUST", "NUMERIC", str(perm_id),
            "Inventory", "INVENTORY", MappingStatus.INFERRED, Confidence.HEURISTIC,
            "B1 range 10600-10699")
    return None


def resolve_perm_capability(perm_id: str) -> CapabilityMapping | None:
    """Resolve a single PermId (string) to a capability mapping."""
    if perm_id in SO1_CAPABILITY:
        return SO1_CAPABILITY[perm_id]
    try:
        num = int(perm_id)
        return numeric_perm_capability(num)
    except (ValueError, TypeError):
        return None


def capability_from_objtype(obj_type: str, canceled: bool = False) -> CapabilityMapping | None:
    """Resolve document ObjType to a capability (creation or cancellation)."""
    if canceled:
        return OBJTYPE_CANCEL_CAPABILITY.get(obj_type)
    return OBJTYPE_CAPABILITY.get(obj_type)


# Canonical capability taxonomy (stable names used across the audit)
CAPABILITY_TAXONOMY: dict[str, str] = {
    "SALES_CREATE": "SALES",
    "SALES_UPDATE": "SALES",
    "SALES_CANCEL": "SALES",
    "SALES_RETURN": "SALES",
    "SALES_DELIVERY": "SALES",
    "SALES_ORDER": "SALES",
    "SALES_CREDIT_NOTE": "SALES",
    "SALES_CREDIT_NOTE_CANCEL": "SALES",
    "PRICE_OVERRIDE": "PRICING",
    "DISCOUNT_OVERRIDE": "PRICING",
    "PRICE_LIST_CHANGE": "PRICING",
    "PAYMENT_CREATE": "CASH",
    "PAYMENT_UPDATE": "CASH",
    "PAYMENT_CANCEL": "CASH",
    "PAYMENT_RECONCILE": "CASH",
    "OUTGOING_PAYMENT": "CASH",
    "OUTGOING_PAYMENT_CANCEL": "CASH",
    "CUSTOMER_CREDIT_READ": "CREDIT",
    "CUSTOMER_CREDIT_UPDATE": "CREDIT",
    "CUSTOMER_TERMS_UPDATE": "CREDIT",
    "STOCK_TRANSFER": "INVENTORY",
    "STOCK_TRANSFER_CANCEL": "INVENTORY",
    "STOCK_ADJUST": "INVENTORY",
    "GOODS_ISSUE": "INVENTORY",
    "GOODS_RECEIPT": "INVENTORY",
    "GOODS_RECEIPT_PO": "INVENTORY",
    "WAREHOUSE_OPERATION": "INVENTORY",
    "PURCHASE_CREATE": "PURCHASING",
    "PURCHASE_UPDATE": "PURCHASING",
    "PURCHASE_CANCEL": "PURCHASING",
    "PURCHASE_CREDIT_NOTE": "PURCHASING",
    "PURCHASE_ORDER": "PURCHASING",
    "PRODUCTION_CREATE": "PRODUCTION",
    "PRODUCTION_ORDER": "PRODUCTION",
    "PRODUCTION_RECEIPT": "PRODUCTION",
    "PRODUCTION_RELEASE": "PRODUCTION",
    "PRODUCTION_ISSUE": "PRODUCTION",
    "PRODUCTION_CLOSE": "PRODUCTION",
    "JOURNAL_ENTRY_CREATE": "ACCOUNTING",
    "JOURNAL_ENTRY_UPDATE": "ACCOUNTING",
    "JOURNAL_ENTRY_CANCEL": "ACCOUNTING",
    "ACCOUNT_RECONCILE": "ACCOUNTING",
    "ACCOUNTING_POST": "ACCOUNTING",
    "CUSTOMER_CREATE": "MASTER_DATA",
    "CUSTOMER_UPDATE": "MASTER_DATA",
    "ITEM_CREATE": "MASTER_DATA",
    "ITEM_UPDATE": "MASTER_DATA",
    "WAREHOUSE_MASTER_UPDATE": "MASTER_DATA",
    "MASTER_DATA_UPDATE": "MASTER_DATA",
    "USER_ADMINISTRATION": "ADMINISTRATION",
    "AUTHORIZATION_ADMINISTRATION": "ADMINISTRATION",
    "SYSTEM_CONFIGURATION": "ADMINISTRATION",
    "SUPERUSER": "ADMINISTRATION",
}

# Sensitive capabilities (drives privilege findings)
SENSITIVE_CAPABILITIES: set[str] = {
    "SALES_CANCEL",
    "PAYMENT_CANCEL",
    "OUTGOING_PAYMENT_CANCEL",
    "SALES_CREDIT_NOTE",
    "SALES_CREDIT_NOTE_CANCEL",
    "PRICE_OVERRIDE",
    "DISCOUNT_OVERRIDE",
    "STOCK_ADJUST",
    "STOCK_TRANSFER",
    "STOCK_TRANSFER_CANCEL",
    "JOURNAL_ENTRY_CREATE",
    "ACCOUNTING_POST",
    "MASTER_DATA_UPDATE",
    "USER_ADMINISTRATION",
    "AUTHORIZATION_ADMINISTRATION",
    "SYSTEM_CONFIGURATION",
    "SUPERUSER",
}
