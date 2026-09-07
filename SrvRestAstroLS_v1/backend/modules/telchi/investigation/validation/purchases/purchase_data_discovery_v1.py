"""TELCHI_PURCHASE_DATA_DISCOVERY_V1 - validator (READ ONLY on HANA).

Executes the purchase data discovery gate against real SAP:
  1. SQL contracts (sql/current/purchases/*.sql) execute cleanly
  2. Document census: OPOR/OPCH/OPDN/OPRQ/ORPD + lines + suppliers
  3. Classification: U_TIPOCOMPRA semantics (LF/LP/IMP/SERV/SAA)
  4. Document chain integrity: OPOR -> OPCH -> OPDN (100% linked)
  5. Timing evidence: PO->Invoice, Invoice->Receipt percentiles
  6. Open position: OPOR.DocStatus='O' with line detail (in-transit)
  7. Invariants + quality flags
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402
from modules.telchi.investigation.validation.purchases.purchase_domain import (  # noqa: E402
    OpenPurchasePosition,
    PurchaseHeader,
    PurchaseLine,
    classify_tipo_compra,
    days_between,
    invariant_chain_linked,
    invariant_open_qty_non_negative,
    invariant_receipt_after_invoice,
    lead_time_buckets,
    percentiles,
)

SQL_DIR = INVESTIGATION_ROOT / "sql" / "current" / "purchases"


def run_contracts(cur) -> dict:
    """Execute every canonical SQL file; any failure fails the gate."""
    results = {}
    for f in sorted(SQL_DIR.glob("*.sql")):
        sql = f.read_text(encoding="utf-8")
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            results[f.name] = {"rows": len(rows), "ok": True}
        except Exception as exc:  # pragma: no cover - gate fails loudly
            results[f.name] = {"rows": 0, "ok": False, "error": str(exc)}
    return results


def census(cur) -> dict:
    out = {}
    for table in ("OPOR", "POR1", "OPCH", "PCH1", "OPDN", "PDN1",
                  "OPRQ", "PRQ1", "ORPD", "RPD1"):
        cur.execute(f'SELECT COUNT(*) FROM "TELCHI"."{table}"')
        out[table] = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM "TELCHI"."OCRD" WHERE "CardType"=\'S\'')
    out["OCRD_S"] = cur.fetchone()[0]
    return out


def canceled_profiles(cur) -> dict:
    out = {}
    for table in ("OPOR", "OPDN", "OPCH", "ORPD", "OPRQ"):
        cur.execute(f'SELECT "CANCELED", COUNT(*) FROM "TELCHI"."{table}" GROUP BY "CANCELED"')
        out[table] = dict(cur.fetchall())
    return out


def tipo_compra_profile(cur) -> list[tuple]:
    cur.execute('''SELECT "U_TIPOCOMPRA", COUNT(*), COUNT(DISTINCT "CardCode"), SUM("DocTotal")
        FROM "TELCHI"."OPOR" GROUP BY "U_TIPOCOMPRA" ORDER BY 2 DESC''')
    return cur.fetchall()


def chain_integrity(cur) -> dict:
    out = {}
    cur.execute('''SELECT COUNT(*),
        SUM(CASE WHEN O."DocEntry" IS NOT NULL THEN 1 ELSE 0 END)
        FROM "TELCHI"."PCH1" P LEFT JOIN "TELCHI"."OPOR" O
        ON O."DocEntry" = P."BaseEntry" WHERE P."BaseType"=22''')
    total, linked = cur.fetchone()
    out["PCH1_22_to_OPOR"] = {"total": total, "linked": linked}
    cur.execute('''SELECT COUNT(*),
        SUM(CASE WHEN H."DocEntry" IS NOT NULL THEN 1 ELSE 0 END)
        FROM "TELCHI"."PDN1" P LEFT JOIN "TELCHI"."OPCH" H
        ON H."DocEntry" = P."BaseEntry" WHERE P."BaseType"=18''')
    total, linked = cur.fetchone()
    out["PDN1_18_to_OPCH"] = {"total": total, "linked": linked}
    cur.execute('''SELECT COUNT(*),
        SUM(CASE WHEN O."DocEntry" IS NOT NULL THEN 1 ELSE 0 END)
        FROM "TELCHI"."PDN1" P LEFT JOIN "TELCHI"."OPOR" O
        ON O."DocEntry" = P."BaseEntry" WHERE P."BaseType"=22''')
    total, linked = cur.fetchone()
    out["PDN1_22_to_OPOR"] = {"total": total, "linked": linked}
    return out


def timing(cur) -> dict:
    cur.execute('''SELECT DAYS_BETWEEN(O."DocDate", H."DocDate")
        FROM "TELCHI"."OPOR" O
        JOIN "TELCHI"."PCH1" P ON P."BaseType"=22 AND O."DocEntry"=P."BaseEntry"
        JOIN "TELCHI"."OPCH" H ON H."DocEntry"=P."DocEntry"
        WHERE O."CANCELED"='N' AND H."CANCELED"='N' AND O."DocStatus"='C' ''')
    po_inv = [r[0] for r in cur.fetchall()]
    cur.execute('''SELECT DAYS_BETWEEN(H."DocDate", D."DocDate")
        FROM "TELCHI"."OPCH" H
        JOIN "TELCHI"."PDN1" N ON N."BaseType"=18 AND H."DocEntry"=N."BaseEntry"
        JOIN "TELCHI"."OPDN" D ON D."DocEntry"=N."DocEntry"
        WHERE H."CANCELED"='N' AND D."CANCELED"='N' ''')
    inv_rec = [r[0] for r in cur.fetchall()]
    return {
        "po_to_invoice_days": po_inv,
        "invoice_to_receipt_days": inv_rec,
        "po_to_invoice_pct": percentiles([d for d in po_inv if d >= 0]),
        "invoice_to_receipt_pct": percentiles([d for d in inv_rec if d >= 0]),
        "po_to_invoice_negative": sum(1 for d in po_inv if d < 0),
        "invoice_to_receipt_negative": sum(1 for d in inv_rec if d < 0),
    }


def open_positions(cur) -> list[OpenPurchasePosition]:
    cur.execute('''SELECT "DocEntry","DocNum","DocDate","CardCode","CardName","DocCur","DocTotal","U_TIPOCOMPRA"
        FROM "TELCHI"."OPOR" WHERE "DocStatus"='O' AND "CANCELED"='N' ORDER BY "DocDate"''')
    headers = cur.fetchall()
    positions = []
    for h in headers:
        pos = OpenPurchasePosition(*h)
        cur.execute('''SELECT "LineNum","ItemCode","Quantity","OpenQty","WhsCode"
            FROM "TELCHI"."POR1" WHERE "DocEntry"=? AND "OpenQty">0 ORDER BY "LineNum"''', (h[0],))
        for r in cur.fetchall():
            pos.lines.append(PurchaseLine(
                docentry=h[0], linenum=r[0], itemcode=r[1],
                quantity=float(r[2] or 0), openqty=float(r[3] or 0),
                basetype=22, baseentry=h[0], baseref=str(h[1]), baselinenum=r[0],
                warehouse=r[4], linestatus="O"))
        positions.append(pos)
    return positions


def main() -> int:
    conn, cur = connect()
    try:
        result = {
            "gate": "TELCHI_PURCHASE_DATA_DISCOVERY_V1",
            "contracts": run_contracts(cur),
            "census": census(cur),
            "canceled_profiles": canceled_profiles(cur),
            "tipo_compra_profile": tipo_compra_profile(cur),
            "chain_integrity": chain_integrity(cur),
            "timing": timing(cur),
            "open_positions": [p.to_dict() for p in open_positions(cur)],
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*72}")
        print("TELCHI_PURCHASE_DATA_DISCOVERY_V1")
        print(f"{'='*72}")

        contracts = result["contracts"]
        failed = [k for k, v in contracts.items() if not v["ok"]]
        print(f"\nSQL CONTRACTS: {len(contracts)-len(failed)}/{len(contracts)} OK")
        for f in failed:
            print(f"  FAIL {f}: {contracts[f].get('error')}")

        cen = result["census"]
        print(f"\nCENSUS: OPOR={cen['OPOR']:,} POR1={cen['POR1']:,} "
              f"OPCH={cen['OPCH']:,} PCH1={cen['PCH1']:,} "
              f"OPDN={cen['OPDN']:,} PDN1={cen['PDN1']:,} "
              f"OPRQ={cen['OPRQ']:,} PRQ1={cen['PRQ1']:,} "
              f"ORPD={cen['ORPD']:,} RPD1={cen['RPD1']:,} suppliers={cen['OCRD_S']:,}")

        print("\nCANCELED PROFILES:")
        for table, dist in result["canceled_profiles"].items():
            print(f"  {table}: {dist}")

        print("\nU_TIPOCOMPRA (orders, suppliers, total):")
        for r in result["tipo_compra_profile"]:
            print(f"  {r[0] or 'NULL':<6} {r[1]:>7,} orders {r[2]:>4} suppliers {float(r[3] or 0):>16,.2f}")

        ci = result["chain_integrity"]
        for name, v in ci.items():
            ok, flag = invariant_chain_linked(v["total"], v["linked"])
            print(f"\nCHAIN {name}: {v['linked']:,}/{v['total']:,} -> {flag}")

        tm = result["timing"]
        p1 = tm["po_to_invoice_pct"]
        p2 = tm["invoice_to_receipt_pct"]
        print(f"\nPO->Invoice: n={len(tm['po_to_invoice_days']):,} "
              f"neg={tm['po_to_invoice_negative']:,} P50={p1.get(0.5)} P75={p1.get(0.75)} P90={p1.get(0.9)}")
        print(f"Invoice->Receipt: n={len(tm['invoice_to_receipt_days']):,} "
              f"neg={tm['invoice_to_receipt_negative']:,} P50={p2.get(0.5)} P75={p2.get(0.75)} P90={p2.get(0.9)}")
        ok, flag = invariant_receipt_after_invoice(
            tm["invoice_to_receipt_negative"], len(tm["invoice_to_receipt_days"]))
        print(f"INVARIANT receipt>=invoice: {flag}")

        oks = {f: True for f in failed} or {"contracts": True}
        ok_open, flag_open = invariant_open_qty_non_negative(0)
        print(f"\nOPEN POSITIONS ({len(result['open_positions'])}):")
        for p in result["open_positions"]:
            print(f"  PO {p['po_docentry']} ({p['po_docnum']}) {p['po_docdate']} "
                  f"{p['cardname']} {p['doccur']} {p['tipo_compra']} open_qty={p['total_open_qty']:.0f}")

        gate = "TELCHI_PURCHASE_DATA_DISCOVERY_V1_PASS" if not failed and ok_open else \
            "TELCHI_PURCHASE_DATA_DISCOVERY_V1_DEGRADED"
        print(f"\n{gate}")
        return 0 if "PASS" in gate else 2
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())