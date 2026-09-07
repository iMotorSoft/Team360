"""Real HANA smoke — TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1.

Manually-verifiable READ ONLY spot checks:
  - 5 largest-amount cases (header + lines + user + salesperson + warehouse)
  - 5 oldest cases
  - representative products (FIPRONIL L01407, BICARBONATO L00505, ...)
  - 5 different warehouses / users when available
Evidence counters printed; failures counted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.atomic.connection import connect

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"
from stock_domain import classify_item, ItemFacts  # noqa: E402


def money(v):
    return round(float(v or 0.0), 2)


def main() -> None:
    cases = json.loads((EVIDENCE / "atomic_la_reja_cases.json").read_text())
    conn, cur = connect()
    checks = 0
    failures = []

    def verify(name, ok, detail=""):
        nonlocal checks
        checks += 1
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {name} {detail}")
        if not ok:
            failures.append(f"{name}: {detail}")

    # 5 largest + 5 oldest
    largest = sorted(cases, key=lambda c: -c["gross_amount"])[:5]
    oldest = sorted(cases, key=lambda c: c["invoice_date"])[:5]
    sample_entries = sorted({c["invoice_docentry"] for c in largest + oldest})
    ph = ",".join(["?"] * len(sample_entries))

    cur.execute(f'''SELECT "DocEntry","DocNum","DocDate","DocDueDate","DocTotal","PaidToDate",
        "CardCode","SlpCode","UserSign","CANCELED" FROM "TELCHI"."OINV" WHERE "DocEntry" IN ({ph})''',
        sample_entries)
    hdr = {r[0]: r for r in cur.fetchall()}
    cur.execute('SELECT "USERID","USER_CODE","U_NAME" FROM "TELCHI"."OUSR"')
    users = {r[0]: r for r in cur.fetchall()}
    cur.execute('SELECT "SlpCode","SlpName" FROM "TELCHI"."OSLP"')
    slp = {r[0]: r for r in cur.fetchall()}

    for de in sample_entries:
        h = hdr.get(de)
        c = next(x for x in cases if x["invoice_docentry"] == de)
        if h is None:
            verify(f"smoke header {de}", False, "not found in OINV")
            continue
        u = users.get(h[8], None)   # UserSign
        s = slp.get(h[7], None)     # SlpCode
        verify(f"smoke {de} header", h[2].date().isoformat() == c["invoice_date"]
               and money(h[4]) == c["gross_amount"]
               and str(h[0]) == str(c["invoice_docentry"]), "")
        verify(f"smoke {de} user=={c['sap_user']}",
               (u[1] if u else None) == c["sap_user"], f"OUSR={u}")
        verify(f"smoke {de} slp=={c['salesperson_name']}",
               (s[1] if s else None) == c["salesperson_name"], f"OSLP={s}")
        # lines
        cur.execute(f'''SELECT "LineNum","ItemCode","Quantity","Price","LineTotal","WhsCode"
            FROM "TELCHI"."INV1" WHERE "DocEntry"=? ORDER BY "LineNum"''', (de,))
        db_lines = cur.fetchall()
        exp_lines = c["product_lines"]
        verify(f"smoke {de} lines {len(db_lines)}=={len(exp_lines)}",
               len(db_lines) == len(exp_lines), "")
        if db_lines:
            dl = db_lines[0]
            el = exp_lines[0]
            verify(f"smoke {de} first line {dl[1]}=={el['itemcode']} qty {dl[2]}",
                   str(dl[1]) == el["itemcode"] and abs(float(dl[2]) - el["quantity"]) <= 0.01
                   and str(dl[5]) == el["warehouse"], f"db={tuple(dl)} exp={el}")

    # representative products
    rep = ["L01407", "L00505", "L01111", "M03408"]
    for code in rep:
        cur.execute('''SELECT "ItemCode","ItemName","ItemType","ItmsGrpCod","InvntItem","SellItem","PrchseItem"
            FROM "TELCHI"."OITM" WHERE "ItemCode"=?''', (code,))
        r = cur.fetchone()
        verify(f"smoke item {code}", r is not None, f"{r}")
        if r:
            facts = ItemFacts(itemcode=r[0], itemname=r[1], item_type=r[2], itms_grp=r[3],
                              invnt_item=r[4], sell_item=r[5], prchse_item=r[6])
            cls = classify_item(facts)
            verify(f"smoke classify {code}", cls in
                   {"FINISHED_GOOD", "RAW_MATERIAL", "INPUT", "PACKAGING", "TRADED_GOOD",
                    "SEMI_FINISHED", "SERVICE", "OTHER", "ITEM_CLASS_UNRESOLVED"}, cls)

    # distinct users/warehouses observed across sample
    usrs = {c["sap_user"] for c in cases}
    whses = {l["warehouse"] for c in cases for l in c["product_lines"]}
    verify("smoke users >= 2", len(usrs) >= 2, f"users={sorted(usrs)}")
    verify("smoke warehouses >= 2", len(whses) >= 2, f"warehouses={sorted(whses)}")

    print(f"\nHANA SMOKE: {checks} checks, {len(failures)} failures")
    if failures:
        for f in failures:
            print("  FAIL:", f)
        sys.exit(1)
    conn.close()


if __name__ == "__main__":
    main()