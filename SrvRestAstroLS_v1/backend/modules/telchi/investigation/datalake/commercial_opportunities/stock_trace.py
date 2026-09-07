"""TELCHI — Reconstrucción histórica de stock (READ ONLY).

Pregunta central (§9): ¿Cuánto había EN EL INSTANTE de la oportunidad?

Reconstrucción desde OINM (movimientos):

    stock_t(item, whs) = SUM(InQty) - SUM(OutQty)  para DocDate <= t

Reconciliación (gate TELCHI_HISTORICAL_STOCK_RECONSTRUCTION_V1):

    OITW.OnHand == stock_alltime(item, whs)      (tolerancia 0.001)

Sólo se declara PASS si la reconciliación es CUANTIFICADA (todas las
combinaciones ItemCode+Whs reconciliadas dentro de tolerancia exacta).

No confundir stock físico (OnHand) con stock suficiente/disponible:
  - available(item,whs,t) = stock_t - IsCommited_t (si se puede reconstruir)
  - OnOrder no es físico: es compra abierta aún no recibida.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from modules.telchi.investigation.datalake.commercial_opportunities.sap_queries import get_movements, get_stock_now

TOLERANCE = 0.001


@dataclass
class StockReconstruction:
    item_code: str
    movements: list[dict] = field(default_factory=list)

    def stock_at(self, whs: str, t: date) -> float:
        """Stock físico reconstruido a fecha t (cierre del día t)."""
        s = 0.0
        for m in self.movements:
            if m["Warehouse"] == whs and m["DocDate"].date() <= t:
                s += float(m["InQty"] or 0) - float(m["OutQty"] or 0)
        return round(s, 4)

    def stock_alltime(self, whs: str) -> float:
        s = sum(float(m["InQty"] or 0) - float(m["OutQty"] or 0) for m in self.movements if m["Warehouse"] == whs)
        return round(s, 4)

    def stock_by_warehouse_at(self, t: date) -> dict[str, float]:
        whs = {m["Warehouse"] for m in self.movements}
        return {w: self.stock_at(w, t) for w in sorted(whs)}

    def movements_after(self, whs: str, t: date) -> list[dict]:
        return [m for m in self.movements if m["Warehouse"] == whs and m["DocDate"].date() > t]


@dataclass
class ReconciliationResult:
    checked: int = 0
    mismatches: list[dict] = field(default_factory=list)
    total_diff_abs: float = 0.0

    @property
    def pass_recon(self) -> bool:
        return self.checked > 0 and not self.mismatches


def reconcile(item_code: str, movements: list[dict], stock_now: list[dict] | None = None) -> ReconciliationResult:
    """OITW.OnHand actual vs stock_alltime reconstruido desde OINM completo.

    movements debe ser el histórico COMPLETO del item (sin ventana de fechas),
    para que la reconstrucción cierre contra OITW actual.
    """
    stock_now = stock_now if stock_now is not None else get_stock_now([item_code])
    now = {s["WhsCode"]: float(s["OnHand"] or 0) for s in stock_now if s["ItemCode"] == item_code}
    acc: dict[str, float] = defaultdict(float)
    for m in movements:
        if m["ItemCode"] != item_code:
            continue
        acc[m["Warehouse"]] += float(m["InQty"] or 0) - float(m["OutQty"] or 0)
    res = ReconciliationResult()
    for whs in sorted(set(list(acc.keys()) + list(now.keys()))):
        rec = round(acc.get(whs, 0.0), 4)
        cur = now.get(whs, 0.0)
        res.checked += 1
        if abs(rec - cur) > TOLERANCE:
            res.mismatches.append({"warehouse": whs, "reconstructed": rec, "oitw": cur, "diff": round(rec - cur, 4)})
            res.total_diff_abs += abs(rec - cur)
    return res


def coverage(requested_qty: float, available_qty: float) -> float:
    """Cobertura porcentual de la cantidad requerida."""
    if requested_qty <= 0:
        return 0.0
    return round(min(100.0, available_qty / requested_qty * 100.0), 1)