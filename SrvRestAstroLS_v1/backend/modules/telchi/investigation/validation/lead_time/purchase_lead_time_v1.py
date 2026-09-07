"""TELCHI_PURCHASE_LEAD_TIME_V1 - validator (READ ONLY on HANA).

Executes the purchase lead time gate:
  1. SQL contract (atomic receipt events through PO->invoice->receipt chain)
  2. Build LeadTimeEvent per PO line; first/full receipt lead time
  3. Status classification (full/partial/open/closed-without-receipt)
  4. Stats: median/p75/p90 by item, supplier, item+supplier
  5. Negative lead time / partial / open / receipt-without-PO anomalies
  6. Procurement mode cross-check (purchased vs produced)
  7. Critical Gate-4 components cross-check (L00205 etiqueta, L00838 precinto)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402
from modules.telchi.investigation.validation.lead_time.lead_time_domain import (  # noqa: E402
    LeadTimeEvent, ReceiptEvent, classify_procurement_mode,
    invariant_negative_controlled, sample_confidence, summarize,
)

SQL_DIR = INVESTIGATION_ROOT / "sql" / "current" / "lead_time"


def run_contracts(cur) -> dict:
    out = {}
    for f in sorted(SQL_DIR.glob("*.sql")):
        try:
            cur.execute(f.read_text(encoding="utf-8"))
            n = len(cur.fetchall())
            out[f.name] = {"rows": n, "ok": True}
        except Exception as exc:  # pragma: no cover
            out[f.name] = {"rows": 0, "ok": False, "error": str(exc)}
    return out


def load_events(cur) -> list[LeadTimeEvent]:
    cur.execute('''SELECT L.po_entry, L.po_line, L."ItemCode", L.ordered_qty,
        L.order_date, L."CardCode", L."CardName", L."U_TIPOCOMPRA", L."DocCur", L."DocStatus",
        R.rec_entry, R.rec_line, R.rec_qty, R.rec_date, R.rec_whs
        FROM (SELECT P."DocEntry" AS po_entry, P."LineNum" AS po_line, P."ItemCode",
                 P."Quantity" AS ordered_qty, O."DocDate" AS order_date, O."CardCode", O."CardName",
                 O."U_TIPOCOMPRA", O."DocCur", O."DocStatus"
              FROM "TELCHI"."POR1" P JOIN "TELCHI"."OPOR" O ON O."DocEntry"=P."DocEntry"
              WHERE O."CANCELED"='N') L
        LEFT JOIN (
          SELECT P."DocEntry" AS po_entry, P."LineNum" AS po_line, R."DocEntry" AS rec_entry,
                 R."LineNum" AS rec_line, R."Quantity" AS rec_qty, D."DocDate" AS rec_date, R."WhsCode" AS rec_whs
          FROM "TELCHI"."POR1" P
          JOIN "TELCHI"."PCH1" I ON I."BaseType"=22 AND I."BaseEntry"=P."DocEntry" AND I."BaseLine"=P."LineNum"
          JOIN "TELCHI"."PDN1" R ON R."BaseType"=18 AND R."BaseEntry"=I."DocEntry" AND R."BaseLine"=I."LineNum"
          JOIN "TELCHI"."OPDN" D ON D."DocEntry"=R."DocEntry" WHERE D."CANCELED"='N'
          UNION ALL
          SELECT P."DocEntry", P."LineNum", R."DocEntry", R."LineNum", R."Quantity", D."DocDate", R."WhsCode"
          FROM "TELCHI"."POR1" P
          JOIN "TELCHI"."PDN1" R ON R."BaseType"=22 AND R."BaseEntry"=P."DocEntry" AND R."BaseLine"=P."LineNum"
          JOIN "TELCHI"."OPDN" D ON D."DocEntry"=R."DocEntry" WHERE D."CANCELED"='N'
        ) R ON R.po_entry = L.po_entry AND R.po_line = L.po_line
        ORDER BY L.po_entry, L.po_line, R.rec_date''')
    rows = cur.fetchall()
    events: dict[tuple[int, int], LeadTimeEvent] = {}
    for r in rows:
        po_entry, po_line, item, oqty, odate, card, cname, tipo, curc, docstatus, \
            rec_entry, rec_line, rqty, rdate, rwhs = r
        key = (po_entry, po_line)
        if key not in events:
            events[key] = LeadTimeEvent(
                po_entry=po_entry, po_line=po_line, item_code=item,
                ordered_qty=float(oqty or 0), order_date=odate, card_code=card,
                card_name=cname, tipo_compra=tipo, doc_cur=curc, doc_status=docstatus)
        if rec_entry is not None:
            events[key].receipts.append(ReceiptEvent(
                rec_entry=rec_entry, rec_line=rec_line, rec_qty=float(rqty or 0),
                rec_date=rdate, rec_whs=rwhs))
    return list(events.values())


def main() -> int:
    conn, cur = connect()
    try:
        contracts = run_contracts(cur)
        events = load_events(cur)

        # status distribution
        status_cnt = Counter(e.status for e in events)
        n_receipt = sum(1 for e in events if e.receipts)
        n_partial = sum(1 for e in events if e.status == "PARTIAL_RECEIPT")
        n_open = sum(1 for e in events if e.status == "OPEN_UNRECEIVED")

        # first lead time overall
        first_days = [e.first_lead_days for e in events if e.first_lead_days is not None]
        full_days = [e.full_lead_days for e in events if e.full_lead_days is not None]
        first_stats = summarize(first_days)
        full_stats = summarize(full_days)

        # negative lead time
        neg = invariant_negative_controlled(events)
        neg_stats = summarize([e.first_lead_days for e in neg])

        # supplier / item+supplier stats
        supp_days = defaultdict(list)
        item_supp_days = defaultdict(list)
        item_days = defaultdict(list)
        for e in events:
            if e.first_lead_days is None:
                continue
            if e.card_code:
                supp_days[e.card_code].append(e.first_lead_days)
            if e.item_code and e.card_code:
                item_supp_days[(e.item_code, e.card_code)].append(e.first_lead_days)
            if e.item_code:
                item_days[e.item_code].append(e.first_lead_days)

        multi_supplier_items = set()
        item_suppliers = defaultdict(set)
        for (item, supp) in item_supp_days:
            item_suppliers[item].add(supp)
        multi_supplier_items = {i for i, s in item_suppliers.items() if len(s) >= 2}

        # sample size distribution (item+supplier pairs)
        ss_dist = Counter()
        for k, v in item_supp_days.items():
            ss_dist[sample_confidence(len(v))] += 1

        # critical components (Gate 4 limiters)
        crit = {}
        for comp in ("L00205", "L00838", "L00219", "L00097"):
            days = item_days.get(comp, [])
            crit[comp] = {"n": len(days), "stats": summarize(days)}

        # procurement mode
        cur.execute('SELECT DISTINCT "ItemCode" FROM "TELCHI"."OWOR" WHERE "Type"=\'S\'')
        produced_set = {r[0] for r in cur.fetchall()}
        purchased_items = {e.item_code for e in events if e.item_code}
        mode_cnt = Counter()
        for item in set(purchased_items) | produced_set:
            mode_cnt[classify_procurement_mode(item in purchased_items, item in produced_set)] += 1

        # lead time by tipo compra
        tipo_days = defaultdict(list)
        for e in events:
            if e.first_lead_days is not None and e.tipo_compra:
                tipo_days[e.tipo_compra].append(e.first_lead_days)
        by_tipo = {k: summarize(v) for k, v in sorted(tipo_days.items(), key=lambda x: -len(x[1]))}

        # open PO age (physical supply proxy)
        cur.execute('''SELECT DAYS_BETWEEN(O."DocDate", CURRENT_DATE) FROM "TELCHI"."POR1" P
            JOIN "TELCHI"."OPOR" O ON O."DocEntry"=P."DocEntry"
            WHERE O."CANCELED"='N' AND O."DocStatus"='O' ''')
        open_age = summarize([r[0] for r in cur.fetchall()])

        result = {
            "gate": "TELCHI_PURCHASE_LEAD_TIME_V1",
            "contracts": contracts,
            "po_lines": len(events),
            "status_dist": dict(status_cnt),
            "first_receipt_stats": first_stats,
            "full_receipt_stats": full_stats,
            "negative_lead_time": {"count": len(neg), "stats": neg_stats},
            "lead_time_by_tipo": by_tipo,
            "open_po_age": open_age,
            "multi_supplier_items": len(multi_supplier_items),
            "item_supplier_pairs": len(item_supp_days),
            "sample_size_dist": dict(ss_dist),
            "critical_components": crit,
            "procurement_mode": dict(mode_cnt),
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*72}\nTELCHI_PURCHASE_LEAD_TIME_V1\n{'='*72}")
        failed = [k for k, v in contracts.items() if not v["ok"]]
        print(f"SQL CONTRACTS: {len(contracts)-len(failed)}/{len(contracts)} OK")
        for f in failed:
            print(f"  FAIL {f}: {contracts[f].get('error')}")

        print(f"\nPO LINES: {len(events):,} | status: {dict(status_cnt)}")
        print(f"FIRST RECEIPT LEAD TIME: {first_stats}")
        print(f"FULL RECEIPT LEAD TIME: {full_stats}")
        print(f"NEGATIVE LEAD TIME: {len(neg)} events -> {neg_stats}")
        print(f"LEAD TIME BY TIPO COMPRA: {by_tipo}")
        print(f"OPEN PO AGE (physical proxy): {open_age}")

        print(f"\nSUPPLIER STATS (top 10 by n):")
        for supp, days in sorted(supp_days.items(), key=lambda x: -len(x[1]))[:10]:
            s = summarize(days)
            print(f"  {supp}: n={s['n']} median={s['median']} p90={s['p90']} max={s['max']}")

        print(f"\nITEM+SUPPLIER: {len(item_supp_days)} pairs | multi-supplier items: {len(multi_supplier_items)}")
        print(f"sample size dist: {dict(ss_dist)}")

        print(f"\nCRITICAL COMPONENTS (Gate 4 limiters) lead time:")
        for comp, v in crit.items():
            print(f"  {comp}: {v}")

        print(f"\nPROCUREMENT MODE: {dict(mode_cnt)}")

        # lineage: sample 6 real cases
        print("\nLINEAGE SAMPLE:")
        for e in events[:6]:
            if e.receipts:
                print(f"  PO {e.po_entry} line {e.po_line} item {e.item_code} supp {e.card_code} "
                      f"order {e.order_date.date() if e.order_date else None} "
                      f"first {e.first_receipt_date.date() if e.first_receipt_date else None} "
                      f"lead {e.first_lead_days}d recs={[(r.rec_entry, r.rec_line) for r in e.receipts]}")

        gate = "TELCHI_PURCHASE_LEAD_TIME_V1_PASS" if not failed else \
            "TELCHI_PURCHASE_LEAD_TIME_V1_DEGRADED"
        print(f"\n{gate}")
        return 0 if "PASS" in gate else 2
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())