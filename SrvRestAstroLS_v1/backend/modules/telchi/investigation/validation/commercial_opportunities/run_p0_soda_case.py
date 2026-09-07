"""Runner P0 Soda Cáustica — casos PIL (05/03), PIL Andina (15/05), Unilever (27/05),
Cervecería (13/05), LURI (05/05). READ ONLY.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path


from modules.telchi.investigation.datalake.commercial_opportunities import sources, stock_trace  # noqa: E402
from modules.telchi.investigation.datalake.commercial_opportunities.sap_queries import (  # noqa: E402
    get_item, get_invoices_for_item, get_movements, get_stock_now,
    get_quotations_for_item, get_customer_sales,
)
from modules.telchi.investigation.datalake.commercial_opportunities.classifier import Classification, EVIDENCE_STRONG  # noqa: E402

ITEM = "L01010"
FOCUS_DATES = {
    date(2026, 3, 5): "PIL 35.000+15.000",
    date(2026, 5, 13): "CERVECERIA NACIONAL POTOSI 2.000",
    date(2026, 5, 15): "PIL ANDINA 14.000",
    date(2026, 5, 27): "UNILEVER 6.000 'NO HAY STOCK'",
}


def main():
    opps = sources.ingest_ventas_perdidas()
    soda = [o for o in opps if o.item_code_report == ITEM]
    item = get_item(ITEM)
    movements = get_movements([ITEM])
    recon = stock_trace.reconcile(ITEM, movements)
    rec = stock_trace.StockReconstruction(ITEM, movements)
    now = get_stock_now([ITEM])
    invoices = get_invoices_for_item([ITEM], start=date(2026, 1, 1), end=date(2026, 9, 30))

    # Precios reales de venta 2026
    import statistics
    real_prices = sorted(float(i["Price"]) for i in invoices if i["Price"])
    med = statistics.median(real_prices)
    p_min, p_max = real_prices[0], real_prices[-1]

    lines = []
    lines.append("=" * 80)
    lines.append(f"P0-A SODA CÁUSTICA — {item['ItemName']} ({ITEM})")
    lines.append("=" * 80)
    lines.append(f"RECONCILIACIÓN HISTÓRICA: {recon.checked} almacenes, {len(recon.mismatches)} desajustes, diff={recon.total_diff_abs}")
    lines.append(f"OITW actual: " + ", ".join(f"{s['WhsCode']}={s['OnHand']:,.0f}" for s in now if float(s['OnHand']) != 0))
    lines.append(f"PRECIO REAL VENTA 2026 (n={len(invoices)} líneas): mediana {med:.2f} Bs/kg (min {p_min:.2f} / max {p_max:.2f})")
    lines.append("")
    for d, label in sorted(FOCUS_DATES.items()):
        snap = rec.stock_by_warehouse_at(d)
        tot = sum(snap.values())
        case = [o for o in soda if o.date == d]
        reqs = [o.qty for o in case]
        req = sum(reqs) if reqs else None
        cov = stock_trace.coverage(req, tot) if req else None
        lines.append(f"--- {label} — {d.isoformat()} ---")
        lines.append(f"  Stock físico TELCHI total: {tot:,.1f} kg | requerido: {req:,} kg | cobertura: {cov}%")
        detail = ", ".join(f"{w}={v:,.1f}" for w, v in sorted(snap.items(), key=lambda x: -x[1]) if v != 0)
        lines.append(f"  Por almacén: {detail}")
        for o in case:
            lines.append(f"  Excel r{ o.source_row}: {o.qty:,} kg @ {o.price} Bs = {o.total_computed:,} Bs | MOTIVO={o.declared_reason} | {o.comment[:70]}")
    # ventas posteriores relevantes
    lines.append("")
    lines.append("VENTAS REALES DESPUÉS DE LOS CASOS (mismo ítem):")
    for inv in sorted(invoices, key=lambda x: x["DocDate"])[-8:]:
        lines.append(f"  {inv['DocDate']} | {str(inv['CardName'])[:30]:30} | {inv['Quantity']:>8} kg | {inv['Price']:>6} Bs | {inv['WhsCode']}")

    # Ventas por cliente clave con L01010
    for name in ["PIL", "UNILEVER", "CERVECERIA", "LURI", "ANDINA"]:
        rows = get_customer_sales([name], start=date(2026, 1, 1), end=date(2026, 9, 30))
        z = [r for r in rows if r["ItemCode"] == ITEM]
        if z:
            lines.append(f"\n  VENTAS {name}: {len(z)} líneas L01010: precios " +
                         ", ".join(f"{r['DocDate']}@{r['Price']}x{r['Quantity']}" for r in z[:6]))

    out_text = "\n".join(lines)
    print(out_text)
    out = Path("validation/commercial_opportunities/evidence")
    out.mkdir(parents=True, exist_ok=True)
    (out / "p0_soda_summary.txt").write_text(out_text)
    ev = {
        "item": ITEM, "item_name": item["ItemName"],
        "reconcile": {"checked": recon.checked, "mismatches": len(recon.mismatches), "diff": recon.total_diff_abs},
        "real_price_2026": {"median": med, "min": p_min, "max": p_max, "n": len(invoices)},
        "cases": [{"date": d.isoformat(), "label": label, "stock_total": round(sum(rec.stock_by_warehouse_at(d).values()), 1)} for d, label in FOCUS_DATES.items()],
    }
    (out / "p0_soda_2026.json").write_text(json.dumps(ev, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()