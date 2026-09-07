"""Executive case domain (pure formatting/assembly).

TELCHI_PURCHASE_EXECUTIVE_CASES_V1 (Gate 10).

Builds owner/management-readable cases from the coverage + risk layers. Each
case answers the ten executive questions without technical jargon:

  QUÉ PASA / POR QUÉ IMPORTA / CUÁNTO TENEMOS / CUÁNTO NECESITAMOS /
  CUÁNTO PODEMOS PRODUCIR / QUÉ ESTÁ PEDIDO / CUÁNTO TARDA /
  CUÁNDO APARECE EL RIESGO / QUÉ ACCIÓN SE RECOMIENDA / QUÉ TAN SEGURO ES
"""
from __future__ import annotations

from dataclasses import dataclass, field

DECISION_ACTIONS = {
    "BUY_NOW": "Comprar / acelerar de inmediato",
    "BUY_SOON": "Ordenar pronto (esta ventana)",
    "WATCH": "Monitorear (no ordenar todavía)",
    "SAFE": "Sin acción (cubierto)",
    "DO_NOT_BUY": "No comprar (ya cubierto por producto terminado)",
    "EXCESS_STOCK": "No comprar (sobre-stock)",
}

CONFIDENCE_LABELS = {"HIGH": "ALTA", "MEDIUM": "MEDIA", "LOW": "BAJA"}

FLAG_LABELS = {
    "IMPORT_DELAY_RISK": "riesgo de demora en importación",
    "SUPPLIER_RISK": "poca historia del proveedor",
    "PRODUCTION_BLOCKED": "bloquea producción",
    "IN_TRANSIT_UNRESOLVED": "en tránsito no confirmado",
    "UOM_UNRESOLVED": "unidad de medida no resuelta",
    "SEASONALITY_UNCERTAIN": "estacionalidad incierta",
}


def action_for(decision: str) -> str:
    return DECISION_ACTIONS.get(decision, decision)


def confidence_label(confidence: str) -> str:
    return CONFIDENCE_LABELS.get(confidence, confidence)


def flag_labels(flags: list[str]) -> list[str]:
    return [FLAG_LABELS.get(f, f) for f in flags]


def _fmt(qty: float, unit: str = "", decimals: int = 0) -> str:
    if qty is None:
        return "—"
    return f"{qty:,.{decimals}f}".rstrip("0").rstrip(".") + (f" {unit}" if unit else "")


def _fmt_month(month: tuple[int, int] | None) -> str:
    if month is None:
        return "—"
    return f"{month[0]}-{month[1]:02d}"


@dataclass
class ExecutiveCase:
    title: str
    what_happens: str
    why_matters: str
    have_physical: str
    have_equivalent: str
    have_open: str
    need_future: str
    can_produce: str
    open_order: str
    open_state: str
    lead_time: str
    risk_when: str
    action: str
    confidence: str
    flags: list[str] = field(default_factory=list)
    # Stable, presentation-neutral contract for future weekly executive
    # consumers.  The original explanatory fields above remain compatible.
    case_id: str = ""
    domain: str = "PURCHASE_MATERIAL_PLANNING"
    decision: str = ""
    severity: str = "MEDIUM"
    summary: str = ""
    action_code: str = ""
    affected_items: list[str] = field(default_factory=list)
    critical_date: str | None = None
    snapshot_date: str | None = None
    reason_code: str = ""
    evidence: dict = field(default_factory=dict)
    traceability: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "title": self.title, "what_happens": self.what_happens,
            "why_matters": self.why_matters,
            "have_physical": self.have_physical,
            "have_equivalent": self.have_equivalent,
            "have_open": self.have_open,
            "need_future": self.need_future,
            "can_produce": self.can_produce,
            "open_order": self.open_order,
            "open_state": self.open_state,
            "lead_time": self.lead_time,
            "risk_when": self.risk_when,
            "action": self.action,
            "confidence": self.confidence,
            "flags": self.flags,
            "case_id": self.case_id,
            "domain": self.domain,
            "decision": self.decision,
            "severity": self.severity,
            "summary": self.summary or self.what_happens,
            "action_code": self.action_code or self.decision,
            "affected_items": self.affected_items,
            "critical_date": self.critical_date,
            "snapshot_date": self.snapshot_date,
            "reason_code": self.reason_code,
            "evidence": self.evidence,
            "traceability": self.traceability,
        }

    def to_markdown(self) -> str:
        lines = [f"### {self.title}", "", self.what_happens, "",
                 f"- **Por qué importa:** {self.why_matters}",
                 f"- **Cuánto tenemos (físico):** {self.have_physical}",
                 f"- **Ya transformado en producto terminado:** {self.have_equivalent}"]
        if self.open_order and self.open_order != "—":
            lines.append(f"- **Pedido (abierto):** {self.open_order} — {self.open_state}")
        else:
            lines.append("- **Pedido (abierto):** —")
        lines += [
            f"- **Cuánto necesitamos:** {self.need_future}",
            f"- **Cuánto podemos producir:** {self.can_produce}",
            f"- **Cuánto tarda (lead time):** {self.lead_time}",
            f"- **Cuándo aparece el riesgo:** {self.risk_when}",
            f"- **Acción recomendada:** {self.action}",
            f"- **Confianza del análisis:** {self.confidence}",
        ]
        if self.flags:
            lines.append(f"- **Alertas:** {', '.join(flag_labels(self.flags))}")
        return "\n".join(lines)
