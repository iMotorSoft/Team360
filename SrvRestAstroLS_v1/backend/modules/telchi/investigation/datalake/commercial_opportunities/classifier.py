"""TELCHI — Clasificador de causa real y score de evidencia (§21, §22).

Taxonomía auditable. NO fuerza clasificación cuando la evidencia no alcanza.
Lineage: cada clasificación conserva source de evidencia (documentos SAP,
movimientos, ventas, proformas) y método de matching.
"""
from __future__ import annotations

from dataclasses import dataclass, field

EVIDENCE_EXACT = "EXACT"
EVIDENCE_STRONG = "STRONG"
EVIDENCE_PROBABLE = "PROBABLE"
EVIDENCE_UNRESOLVED = "UNRESOLVED"

VALID_EVIDENCE = {EVIDENCE_EXACT, EVIDENCE_STRONG, EVIDENCE_PROBABLE, EVIDENCE_UNRESOLVED}

# Causas (§21)
CAUSES = {
    "LOST_REAL_NO_STOCK": "No existía suficiente cantidad en TELCHI.",
    "LOST_PARTIAL_STOCK": "Existía stock pero menor al requerimiento.",
    "LOST_STOCK_OTHER_LOCATION": "Había stock suficiente en otro almacén.",
    "LOST_LOGISTICS_DELAY": "Existía físicamente pero no disponible en el plazo requerido.",
    "LOST_NO_TRANSFER": "Había stock transferible y no se realizó el movimiento.",
    "LOST_PRODUCTION_CONSTRAINT": "Faltaba PT, producción limitada.",
    "LOST_RAW_MATERIAL_CONSTRAINT": "Faltaba MP específica.",
    "LOST_PROCUREMENT_DELAY": "Compra/importación tardía.",
    "LOST_PRICE_REAL": "Precio realmente fuera de mercado interno.",
    "LOST_PRICE_BUT_MARGIN_AVAILABLE": "Precio podía aceptarse con margen.",
    "LOST_PRICE_AUTHORIZATION_DELAY": "Demora en autorización de precio.",
    "LOST_CREDIT": "Problema de crédito/cobranza.",
    "LOST_SPECIFICATION": "Especificación técnica no satisfecha.",
    "LOST_MINIMUM_ORDER": "Pedido mínimo no cumplido.",
    "LOST_DOCUMENTATION": "Documentación faltante.",
    "SOLD_FULL": "Vendido completo.",
    "SOLD_PARTIAL": "Vendido parcialmente.",
    "SOLD_LATER": "Vendido después de la oportunidad.",
    "SOLD_OTHER_CHANNEL": "Vendido en otro canal/vendedor/sucursal.",
    "DUPLICATE_RECORD": "Registro duplicado.",
    "BAD_PRODUCT_CODE": "Código de producto incorrecto en fuente.",
    "BAD_SOURCE_DATA": "Dato fuente defectuoso.",
    "CAUSE_UNRESOLVED": "Sin evidencia suficiente.",
}

CONVERSION = {
    "CONVERTED_FULL": "Cantidad vendida comparable con presupuestada.",
    "CONVERTED_PARTIAL": "Parte de la cantidad se convirtió.",
    "CONVERTED_LATE": "Se realizó después de una ventana razonable.",
    "SUBSTITUTE_PURCHASE": "Cliente compró producto sustituto.",
    "OTHER_CHANNEL_CONVERSION": "La venta ocurrió en otro canal.",
    "NOT_CONVERTED": "No se encontró venta.",
    "SOLD_LATER": "Se vendió después de la oportunidad.",
    "UNRESOLVED": "Sin evidencia suficiente.",
}


@dataclass
class Classification:
    opportunity_ref: str
    cause: str
    evidence_level: str
    conversion: str = "UNRESOLVED"
    reasoning: str = ""
    evidence_docs: list[str] = field(default_factory=list)

    def __post_init__(self):
        assert self.cause in CAUSES, f"causa desconocida: {self.cause}"
        assert self.evidence_level in VALID_EVIDENCE, f"evidence inválido: {self.evidence_level}"
        assert self.conversion in CONVERSION, f"conversion inválida: {self.conversion}"