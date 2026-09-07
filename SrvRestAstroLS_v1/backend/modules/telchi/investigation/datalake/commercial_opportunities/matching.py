"""TELCHI — Matching Proforma → Venta (§16) y venta posterior (§18).

Prioridad de evidencia:
  Nivel 1 EXACT_DOCUMENT_LINK  -> BaseType/BaseEntry SAP exacto
  Nivel 2 EXACT_EXTERNAL_REF   -> número de proforma/referencia conservado
  Nivel 3 STRONG_MATCH         -> cliente+producto+cantidad compatible+fecha cercana
  Nivel 4 HEURISTIC            -> coincidencia parcial (nunca presentar como exact)

Guardar match_method, match_confidence, evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MATCH_EXACT_DOCUMENT = "EXACT_DOCUMENT_LINK"
MATCH_EXACT_REF = "EXACT_EXTERNAL_REFERENCE"
MATCH_STRONG = "STRONG_MATCH"
MATCH_HEURISTIC = "HEURISTIC"


@dataclass
class SaleMatch:
    method: str
    confidence: str
    evidence: str = ""
    invoice_docnum: int | None = None
    invoice_date: object = None
    invoice_qty: float | None = None
    invoice_price: float | None = None
    salesperson: int | None = None
    channel: str | None = None
    warehouse: str | None = None


def match_proforma_to_sale(proforma: dict, invoices: list[dict]) -> SaleMatch | None:
    """Match nivel 1 a 3 entre una proforma (OQUT) y facturas (OINV/INV1)."""
    # Nivel 1: la factura referencia la proforma por BaseType=23 (EXACT)
    direct = [
        inv for inv in invoices
        if inv.get("BaseType") == 23 and inv.get("BaseEntry") == proforma.get("DocEntry")
    ]
    if direct:
        inv = direct[0]
        return SaleMatch(
            method=MATCH_EXACT_DOCUMENT,
            confidence="EXACT",
            evidence=f"INV1.BaseType=23 BaseEntry={proforma.get('DocEntry')} DocNum={inv.get('DocNum')}",
            invoice_docnum=inv.get("DocNum"),
            invoice_date=inv.get("DocDate"),
            invoice_qty=inv.get("Quantity"),
            invoice_price=inv.get("Price"),
            salesperson=inv.get("SlpCode"),
            channel=inv.get("U_ORIGIN"),
            warehouse=inv.get("WhsCode"),
        )
    # Nivel 2: la proforma conserva referencia externa (NumAtCard / Ref) y la factura la misma
    qut_ref = proforma.get("NumAtCard") or proforma.get("Ref1")
    if qut_ref:
        ref_matches = [inv for inv in invoices if (inv.get("BaseRef") == qut_ref or str(inv.get("BaseRef")) == str(qut_ref))]
        if ref_matches:
            inv = ref_matches[0]
            return SaleMatch(
                method=MATCH_EXACT_REF,
                confidence="EXACT",
                evidence=f"Ref {qut_ref} en factura {inv.get('DocNum')}",
                invoice_docnum=inv.get("DocNum"), invoice_date=inv.get("DocDate"),
                invoice_qty=inv.get("Quantity"), invoice_price=inv.get("Price"),
                salesperson=inv.get("SlpCode"), channel=inv.get("U_ORIGIN"), warehouse=inv.get("WhsCode"),
            )
    # Nivel 3: mismo cliente + mismo item + cantidad compatible + ventana 30d
    same = [
        inv for inv in invoices
        if inv.get("ItemCode") == proforma.get("ItemCode")
        and inv.get("CardCode") == proforma.get("CardCode")
    ]
    if same:
        inv = same[0]
        return SaleMatch(
            method=MATCH_STRONG,
            confidence="STRONG",
            evidence=f"mismo cliente/item {proforma.get('CardCode')}/{proforma.get('ItemCode')} qty factura={inv.get('Quantity')}",
            invoice_docnum=inv.get("DocNum"), invoice_date=inv.get("DocDate"),
            invoice_qty=inv.get("Quantity"), invoice_price=inv.get("Price"),
            salesperson=inv.get("SlpCode"), channel=inv.get("U_ORIGIN"), warehouse=inv.get("WhsCode"),
        )
    return None


def find_later_sale(opportunity_date, customer, item_code, invoices: list[dict], windows=(1, 3, 7, 14, 30, 60)) -> dict:
    """Venta posterior del mismo cliente + item (§18). Devuelve evidencia."""
    from datetime import timedelta

    best = None
    for win in windows:
        limit = opportunity_date + timedelta(days=win)
        for inv in invoices:
            if inv.get("ItemCode") != item_code:
                continue
            if customer and inv.get("CardCode") != customer and customer not in str(inv.get("CardName", "")):
                continue
            if inv.get("DocDate") and opportunity_date < inv["DocDate"].date() <= limit:
                days = (inv["DocDate"].date() - opportunity_date).days
                if best is None or days < best[0]:
                    best = (days, win, inv)
        if best:
            break
    if not best:
        return {"sold_later": False, "days_to_sale": None, "later_qty": None, "later_price": None,
                "later_salesperson": None, "later_channel": None, "later_warehouse": None}
    days, win, inv = best
    return {"sold_later": True, "days_to_sale": days, "later_qty": float(inv.get("Quantity") or 0),
            "later_price": float(inv.get("Price") or 0),
            "later_salesperson": inv.get("SlpCode"), "later_channel": inv.get("U_ORIGIN"),
            "later_warehouse": inv.get("WhsCode"),
            "evidence": f"DocNum={inv.get('DocNum')} fecha={inv.get('DocDate')}"}