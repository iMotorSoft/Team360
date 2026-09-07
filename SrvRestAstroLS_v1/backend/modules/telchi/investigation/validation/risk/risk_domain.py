"""Purchase risk engine domain (pure logic, READ ONLY).

TELCHI_PURCHASE_RISK_ENGINE_V1 (Gate 8).

Converts Gate 7 coverage positions into explainable purchase decisions. There
is NO opaque score: every decision derives from visible variables (coverage,
stockout month, lead time, open purchase, supply confidence, seasonality,
component criticality, shared-component exposure).

Decisions:
  BUY_NOW      latest safe order month already elapsed (<= snapshot month)
  BUY_SOON     inside the documented warning window
  WATCH        stockout projected but not yet urgent (or open order pending)
  SAFE         covered >= horizon, no action
  DO_NOT_BUY   material already transformed into FG covers the requirement
  EXCESS_STOCK declining/discontinued demand with abundant coverage

Risk flags (coexist with a decision):
  PRODUCTION_BLOCKED  packaging/input is the limiting component for a FG
  SEASONAL_RISK       seasonal demand concentration
  IMPORT_DELAY_RISK   import supply with coverage ~= lead time
  SUPPLIER_RISK       lead-time sample too small / supplier history low

LATEST_SAFE_ORDER_MONTH = STOCKOUT_MONTH - ceil((LEAD_TIME_P90 + SAFETY_BUFFER)/30.44)
Monthly resolution only: no invented daily date.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from modules.telchi.investigation.validation.coverage.coverage_domain import FLAG_IN_TRANSIT_UNRESOLVED, month_add, month_span

DEC_BUY_NOW = "BUY_NOW"
DEC_BUY_SOON = "BUY_SOON"
DEC_WATCH = "WATCH"
DEC_SAFE = "SAFE"
DEC_DO_NOT_BUY = "DO_NOT_BUY"
DEC_EXCESS_STOCK = "EXCESS_STOCK"

FLAG_PRODUCTION_BLOCKED = "PRODUCTION_BLOCKED"
FLAG_SEASONAL_RISK = "SEASONAL_RISK"
FLAG_IMPORT_DELAY = "IMPORT_DELAY_RISK"
FLAG_SUPPLIER = "SUPPLIER_RISK"

PROCUREMENT_PRODUCED = "PRODUCED"
PROCUREMENT_PURCHASED = "PURCHASED"
PROCUREMENT_MIXED = "MIXED"

IMPORT_CLASS = "IMPORT_OR_LOGISTICS"

WARNING_WINDOW_MONTHS = 2
LOW_SAMPLE_CONFIDENCES = {"LOW", "VERY_LOW", "NO_PURCHASE_HISTORY"}


@dataclass
class MaterialRiskInput:
    component: str
    physical_available: float
    equivalent_in_fg: float
    open_purchase: float
    total_required: float
    stockout_month: tuple[int, int] | None
    covered_through_month: tuple[int, int] | None
    lead_time_p90: int | None
    procurement_mode: str
    import_class: str
    supplier_confidence: str
    is_shared: bool = False
    is_packaging: bool = False
    forecast_uncertain: bool = False
    declining_or_discontinued: bool = False


@dataclass
class Recommendation:
    component: str
    decision: str
    latest_safe_order_month: tuple[int, int] | None
    reason: str
    confidence: str
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "decision": self.decision,
            "latest_safe_order_month": list(self.latest_safe_order_month) if self.latest_safe_order_month else None,
            "reason": self.reason,
            "confidence": self.confidence,
            "flags": self.flags,
        }


def safety_buffer_days(is_shared: bool, supplier_confidence: str,
                       forecast_uncertain: bool) -> int:
    """HEURISTIC safety buffer (documented, not a universal 30 days).

    Base 7 days + 7 if forecast is uncertain + 7 if shared component + 14 if
    lead-time sample is low. Scales with the documented uncertainty sources
    (lead-time variability is approximated by supplier sample confidence).
    """
    days = 7
    if forecast_uncertain:
        days += 7
    if is_shared:
        days += 7
    if supplier_confidence in LOW_SAMPLE_CONFIDENCES:
        days += 14
    return days


def latest_safe_order_month(stockout_month: tuple[int, int],
                            lead_time_days: int,
                            safety_buffer_days: int) -> tuple[int, int]:
    """STOCKOUT_MONTH shifted back by lead time + buffer (monthly resolution)."""
    total_days = int(lead_time_days) + int(safety_buffer_days)
    months_back = math.ceil(total_days / 30.44)
    return month_add(stockout_month[0], stockout_month[1], -months_back)


def classify_material(inp: MaterialRiskInput,
                      snapshot: tuple[int, int]) -> Recommendation:
    """Explainable rule-based purchase decision for one material."""
    flags: list[str] = []
    confidence = "HIGH"

    if inp.procurement_mode == PROCUREMENT_PRODUCED:
        return Recommendation(inp.component, DEC_SAFE, None,
                              "producido internamente; el riesgo de compra vive en sus componentes terminales",
                              "MEDIUM", flags)

    if inp.import_class == IMPORT_CLASS:
        flags.append(FLAG_IMPORT_DELAY)
    if inp.supplier_confidence in LOW_SAMPLE_CONFIDENCES:
        flags.append(FLAG_SUPPLIER)
        confidence = "LOW"
    if inp.is_packaging and inp.stockout_month is not None:
        flags.append(FLAG_PRODUCTION_BLOCKED)

    # Nothing to buy when there is no future requirement
    if inp.total_required <= 0:
        return Recommendation(inp.component, DEC_SAFE, None,
                              "sin requerimiento futuro proyectado",
                              "HIGH", flags)

    # Material already positioned across layers covers the requirement. The
    # equivalent-in-FG DOES offset the future requirement here (it covers
    # demand without new production) — this is a demand-coverage decision, NOT
    # a production-capacity statement (never sum equivalent into producible).
    total_covered = inp.equivalent_in_fg + inp.physical_available + inp.open_purchase
    if total_covered >= inp.total_required:
        if inp.declining_or_discontinued:
            return Recommendation(inp.component, DEC_EXCESS_STOCK, None,
                                  "demanda en declive/discontinuada con cobertura abundante",
                                  "MEDIUM", flags)
        if inp.physical_available >= inp.total_required:
            return Recommendation(inp.component, DEC_SAFE, None,
                                  "stock físico cubre el requerimiento",
                                  "HIGH", flags)
        if inp.equivalent_in_fg >= inp.total_required:
            return Recommendation(inp.component, DEC_DO_NOT_BUY, None,
                                  "material ya transformado en PT cubre la demanda futura; comprar MP sería doble conteo",
                                  "MEDIUM", flags)
        # physical + equivalent insufficient; the open order covers the rest
        return Recommendation(inp.component, DEC_SAFE, None,
                              "suministro abierto cubre el faltante; monitorear llegada (no re-comprar aún)",
                              "MEDIUM", flags + [FLAG_IN_TRANSIT_UNRESOLVED])

    # Net shortfall -> a purchase is needed. Compute urgency.
    if inp.stockout_month is None:
        return Recommendation(inp.component, DEC_SAFE, None,
                              "cobertura física >= horizonte de 12 meses",
                              "HIGH", flags)

    if inp.lead_time_p90 is None:
        return Recommendation(inp.component, DEC_WATCH, None,
                              "stockout proyectado pero sin lead time de compra (n=0); derivar lead time y monitorear",
                              "LOW", flags)

    buffer = safety_buffer_days(inp.is_shared, inp.supplier_confidence, inp.forecast_uncertain)
    lso = latest_safe_order_month(inp.stockout_month, inp.lead_time_p90, buffer)

    if inp.open_purchase > 0:
        flags.append(FLAG_IN_TRANSIT_UNRESOLVED)

    if lso <= snapshot:
        return Recommendation(inp.component, DEC_BUY_NOW, lso,
                              "LATEST_SAFE_ORDER_MONTH ya vencido (<= snapshot); ordenar/acelerar de inmediato",
                              confidence, flags)
    if month_span(snapshot, lso) <= WARNING_WINDOW_MONTHS:
        return Recommendation(inp.component, DEC_BUY_SOON, lso,
                              "dentro de la ventana de advertencia documentada; ordenar pronto",
                              confidence, flags)
    return Recommendation(inp.component, DEC_WATCH, lso,
                          "stockout futuro; ordenar antes de LATEST_SAFE_ORDER_MONTH",
                          confidence, flags)


def decision_priority(decision: str) -> int:
    """Ordering for reporting (most urgent first)."""
    order = {DEC_BUY_NOW: 0, DEC_BUY_SOON: 1, DEC_WATCH: 2, DEC_SAFE: 3,
             DEC_DO_NOT_BUY: 4, DEC_EXCESS_STOCK: 5}
    return order.get(decision, 9)
