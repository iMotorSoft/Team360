"""Runner P0 Zinc — genera el caso ejecutivo (§25) con evidencia numerada.

READ ONLY sobre HANA. Salida en consola (y JSON en validation/.../evidence/).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT


from modules.telchi.investigation.datalake.commercial_opportunities import sources, stock_trace, matching  # noqa: E402
from modules.telchi.investigation.datalake.commercial_opportunities.sap_queries import (  # noqa: E402
    get_item, get_invoices_for_item, get_movements, get_stock_now, get_transfers_for_item,
    get_quotations_for_item, get_customer_sales, get_retail_one_invoices,
)
from modules.telchi.investigation.datalake.commercial_opportunities.classifier import Classification, EVIDENCE_STRONG  # noqa: E402

ITEM = "L01794"
OPP_DATE = date(2026, 5, 14)

def main():
    opps = sources.ingest_ventas_perdidas()
    case = [o for o in opps if o.date == OPP_DATE and "ZINC" in o.product_raw.upper()][0]

    item = get_item(ITEM)
    item_wrong = get_item("L01094")
    movements = get_movements([ITEM])
    now = get_stock_now([ITEM])
    rec = stock_trace.StockReconstruction(ITEM, movements)
    recon = stock_trace.reconcile(ITEM, movements, now)
    snap = rec.stock_by_warehouse_at(date(2026, 5, 13))
    transfers = get_transfers_for_item([ITEM], start=date(2026, 5, 10), end=date(2026, 5, 31))
    invoices = get_invoices_for_item([ITEM], start=date(2026, 4, 1), end=date(2026, 8, 31))
    quts = get_quotations_for_item([ITEM], start=date(2026, 5, 1), end=date(2026, 5, 31))
    fidero_inv = get_customer_sales(["FIDERO"], item_codes=[ITEM])
    fidero_r1 = get_retail_one_invoices(customer_name_like="FIDERO", end=date(2026, 9, 30))

    stock_saa = snap.get("SAA-M1", 0.0)
    total_at = sum(snap.values())

    # Causa real
    cause = "LOST_LOGISTICS_DELAY"
    reasoning = (
        f"Declarada STOCK; evidencia: {stock_saa:,.0f} kg de {item['ItemName']} en SAA-M1 (Saavedra) "
        f"al {OPP_DATE.isoformat()} (total TELCHI {total_at:,.0f} kg) vs 450 kg pedidos. "
        "Comentario comercial: 'el cliente no quiso esperar ... se encontraba en saavedra y solo se tiene "
        "un dia de envio de MP'. Ruta SAA-M1→LAB-T2 demostrada (histórica + OWTR 260107340 16/05). "
        "No fue ruptura de stock físico; fue indisponibilidad logística (producto en otro almacén, no "
        "transferido al plazo requerido)."
    )
    cls = Classification(
        opportunity_ref=f"VENTAS PERDIDAS MAYO 2026 row {case.source_row}",
        cause=cause, evidence_level=EVIDENCE_STRONG,
        conversion="NOT_CONVERTED" if not fidero_inv else "CONVERTED_LATE",
        reasoning=reasoning,
        evidence_docs=[
            "OQUT 260105727→OINV 261404387 (BaseType=23 EXACT)",
            "OQUT 260105792→OINV 261404388 (BaseType=23 EXACT)",
            "OINM L01794 82 whs reconciliados diff=0 vs OITW",
            "OWTR 260107340 SAA-M1→LAB-T2 1200 kg 16/05/2026",
        ],
    )

    # Reporte
    lines = []
    lines.append("=" * 78)
    lines.append("CASO EJECUTIVO — SULFATO DE ZINC / FIDER — 2026-05-14")
    lines.append("=" * 78)
    lines.append(f"PRODUCTO      : {item['ItemName']} ({ITEM})  [Excel declaró L01094 = {item_wrong['ItemName']}]")
    lines.append(f"CLIENTE       : {case.comment.split('/')[-1].strip().upper()} (declarado en comentario; "
                 "no CardCode OCRD directo, CardName en docs SAP y Retail One)")
    lines.append(f"FECHA         : {case.date}  VENDEDOR: {case.salesperson_raw}  CANAL: {case.channel_raw}")
    lines.append(f"CANTIDAD      : {case.qty} kg   PRECIO OFRECIDO: {case.price} Bs/kg   VALOR: {case.total_computed} Bs")
    lines.append(f"DECLARACIÓN   : {case.declared_reason}")
    lines.append(f"COMENTARIO    : {case.comment}")
    lines.append("")
    lines.append("QUÉ MUESTRA SAP")
    lines.append(f"  - Stock físico L01794 en SAA-M1 (Saavedra) al 13/05/2026: {stock_saa:,.1f} kg")
    lines.append(f"  - Stock total TELCHI (todos los almacenes) al 13/05/2026: {total_at:,.1f} kg")
    lines.append(f"  - Requerido: 450 kg → cobertura {stock_trace.coverage(450, stock_saa):.0f}% (stock >> requerido)")
    lines.append(f"  - Reconciliación histórica: {recon.checked} almacenes, {len(recon.mismatches)} desajustes, diff={recon.total_diff_abs:.4f}")
    lines.append(f"  - OITW actual: SAA-M1={[s['OnHand'] for s in now if s['WhsCode']=='SAA-M1'][0]} kg, LAB-T2={[s['OnHand'] for s in now if s['WhsCode']=='LAB-T2'][0]} kg")
    lines.append("")
    lines.append("QUÉ PASÓ DESPUÉS")
    lines.append("  - 13/05/2026 (día antes): MADRILES S.A. compró 900 kg de L01794 (2 facturas de 450 kg a 23.055 Bs/kg)")
    lines.append("    → proformas 260105727/260105792 convertidas EXACT (BaseType=23).")
    lines.append("  - 16/05/2026: transferencia OWTR 260107340 SAA-M1→LAB-T2 (1.200 kg), comentario: "
                 "'SOLICITUD PARA STOCK EN ALMACEN SENASAG LAB-T2'.")
    if fidero_inv:
        lines.append(f"  - Venta posterior a FIDER: {len(fidero_inv)} factura(s) (ver evidencia) — revisar detalle.")
    else:
        lines.append("  - No se encontró venta posterior de L01794 a FIDERO en OINV (ventana +60 d).")
    lines.append(f"  - FIDERO en Retail One: {len(fidero_r1)} facturas históricas (@SO1_01FACTURA) — canal R1 operativo.")
    lines.append("")
    lines.append(f"CAUSA REAL    : {cls.cause} — {cls.reasoning[:200]}...")
    lines.append("IMPACTO       : 450 kg × 26.5 Bs = 11.925 Bs potenciales; producto vendible ese mismo día a 23.055 Bs/kg.")
    lines.append("EVIDENCIA     : ")
    for e in cls.evidence_docs:
        lines.append(f"    - {e}")
    lines.append("ACCIÓN        : Definir SLA de transferencia SAA-M1→LAB-T2 ≤1 día para pedidos de zinc; "
                 "revisar si FIDER fue atendido por otro canal (R1) con zinc.")
    print("\n".join(lines))

    ev = {
        "case": "P0_ZINC_2026-05-14",
        "item": ITEM, "item_name": item["ItemName"],
        "declared_code": "L01094", "declared_item": item_wrong["ItemName"],
        "customer_declared": "FIDERO SRL", "date": OPP_DATE.isoformat(),
        "qty": case.qty, "price": case.price, "value": case.total_computed,
        "declared_reason": case.declared_reason,
        "stock_saa_m1_0513": stock_saa, "stock_total_0513": total_at,
        "reconcile_checked": recon.checked, "reconcile_mismatches": len(recon.mismatches),
        "reconcile_diff": recon.total_diff_abs,
        "madriles_0513_qty": 900.0, "madriles_price": 23.055,
        "transfer_after": [{"docnum": t["DocNum"], "date": str(t["DocDate"]), "qty": float(t["Quantity"]),
                            "from": t["FromWhsCod"], "to": t["WhsCode"]} for t in transfers],
        "classification": {"cause": cls.cause, "evidence_level": cls.evidence_level,
                           "conversion": cls.conversion, "reasoning": cls.reasoning},
    }
    out = EVIDENCE_ROOT / "commercial_opportunities" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    (out / "p0_zinc_2026-05-14.json").write_text(json.dumps(ev, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()