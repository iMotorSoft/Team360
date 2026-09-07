"""Runner P0-B Sulfato de Cobre — casos PRECIO + INDAPEC + QUIMERA. READ ONLY."""
from __future__ import annotations

import json
import statistics
import sys
from datetime import date
from pathlib import Path


from modules.telchi.investigation.datalake.commercial_opportunities import sources, stock_trace  # noqa: E402
from modules.telchi.investigation.datalake.commercial_opportunities.sap_queries import (  # noqa: E402
    get_item, get_invoices_for_item, get_movements, get_stock_now, get_customer_sales,
)
ITEM25 = "L01772"
ITEM1 = "L02909"

KEY_DATES = [(date(2026, 2, 20), 500, 69.0), (date(2026, 3, 6), 3000, 66.5),
             (date(2026, 5, 7), 500, 75.0), (date(2026, 9, 28), 1000, 75.0)]


def main():
    opps = sources.ingest_ventas_perdidas()
    item = get_item(ITEM25)
    item1 = get_item(ITEM1)
    movs = get_movements([ITEM25])
    rec = stock_trace.StockReconstruction(ITEM25, movs)
    recon25 = stock_trace.reconcile(ITEM25, movs)
    inv25 = get_invoices_for_item([ITEM25], start=date(2026, 1, 1), end=date(2026, 9, 30))
    inv1 = get_invoices_for_item([ITEM1], start=date(2026, 1, 1), end=date(2026, 9, 30))

    # precios reales venta 25kg y 1kg
    p25 = sorted(float(i["Price"]) for i in inv25 if i["Price"])
    p1 = sorted(float(i["Price"]) for i in inv1 if i["Price"])

    lines = []
    lines.append("=" * 82)
    lines.append(f"P0-B SULFATO DE COBRE — {item['ItemName']} ({ITEM25}) y {item1['ItemName']} ({ITEM1})")
    lines.append("=" * 82)
    lines.append(f"RECONCILIACIÓN HISTÓRICA {ITEM25}: {recon25.checked} whs, {len(recon25.mismatches)} mism, diff={recon25.total_diff_abs}")
    lines.append(f"PRECIO REAL VENTA {ITEM25} 2026 (n={len(inv25)}): mediana {statistics.median(p25):.2f} | p25 {p25[len(p25)//4]:.2f} | p75 {p25[3*len(p25)//4]:.2f} | min {p25[0]:.2f} | max {p25[-1]:.2f}")
    lines.append(f"PRECIO REAL VENTA {ITEM1} 2026 (n={len(inv1)}): mediana {statistics.median(p1):.2f} | min {p1[0]:.2f} | max {p1[-1]:.2f}")
    lines.append("")
    for d, qty, price in KEY_DATES:
        snap = rec.stock_by_warehouse_at(d)
        tot = sum(snap.values())
        cov = stock_trace.coverage(qty, tot)
        lines.append(f"--- {d.isoformat()} — oportunidad {qty} kg @ {price} Bs ---")
        lines.append(f"  Stock físico L01772 total: {tot:,.1f} kg | cobertura {cov}%")
        detail = ", ".join(f"{w}={v:,.1f}" for w, v in sorted(snap.items(), key=lambda x: -x[1]) if v != 0)
        lines.append(f"  Por almacén: {detail}")
    lines.append("")
    lines.append("VENTAS REALES QUIMERA (C011936) — L01772:")
    qrows = get_customer_sales(["QUIMERA"], start=date(2026, 1, 1), end=date(2026, 9, 30))
    qz = [r for r in qrows if r["ItemCode"] == ITEM25]
    for r in qz[:16]:
        lines.append(f"  {r['DocDate']} | {r['Quantity']:>6} kg | {r['Price']:>6} Bs | {r['WhsCode']}")
    lines.append(f"  → mediana precios QUIMERA: {statistics.median([float(r['Price']) for r in qz]):.2f} Bs/kg (n={len(qz)})")

    lines.append("")
    lines.append("COMPRA PARCIAL INDAPEC (C006302) — fuente ESTATUS CLIENTES 2025-10-01:")
    lines.append("  'L01772 SULFATO DE COBRE x25kg | 500 kg | 63.0 Bs | COMPRA 150KG | 17/10/2025 ENVIO DE "
                 "NEGOCIACIÓN PRECIO M... | A LA ESPERA DE NUEVA MERCADERÍA EN NOVIEMBRE'")
    id_rows = get_customer_sales(["INDAPEC"], start=date(2025, 1, 1), end=date(2026, 9, 30))
    idz = [r for r in id_rows if r["ItemCode"] == ITEM25]
    lines.append(f"  OINV INDAPEC L01772(2025-2026): {len(idz)} líneas")
    for r in idz[:12]:
        lines.append(f"  {r['DocDate']} | {r['Quantity']:>6} | {r['Price']:>6} Bs | {r['WhsCode']}")

    print("\n".join(lines))
    out = Path("validation/commercial_opportunities/evidence")
    out.mkdir(parents=True, exist_ok=True)
    (out / "p0_copper_summary.txt").write_text("\n".join(lines))


if __name__ == "__main__":
    main()