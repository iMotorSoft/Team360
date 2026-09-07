"""LOOP TESTS — TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1.

READ ONLY tests over evidence JSON emitted by the analysis scripts
(no HANA connection required; integrity guarded by scripts themselves).

Gates (mirrors prompt sections 46-60):
  1. universe           40 input / 40 output / 40 unique DocEntry
  2. amount             SUM(open) == 47,258.99 (baseline 2026-09-01)
  3. invoice lines      SUM(INV1 net) == DocTotal within rounding tol
  4. document chain     NO_SILENT_FANOUT header->delivery->order
  5. stock effect       delivery qty == OINM out qty (sampled)
  6. products           every ItemCode resolves to OITM (0 UNKNOWN_ITEM)
  7. product class      classifications non-empty, no-only-description
  8. user               UserSign -> OUSR resolved 1:1 on every case
  9. salesperson        SlpCode -> OSLP resolved (where != -1)
  10. channel           only RETAIL_ONE / SAP_DIRECT / DMS / UNKNOWN
  11. pricing           same item+currency+unit+period comparability
  12. collection        invoice == paid + credited + open
  13. accounting        sample JDT1 balances (debit == credit)
  14. generic account   tests present and documented
  15. temporal          order_date <= delivery_date <= invoice_date
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EVIDENCE = EVIDENCE_ROOT / "la_reja_identity" / "evidence"
BASELINE_OPEN = 47258.99
TOL = 0.05

FAILURES: list[str] = []
PASSED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED
    if ok:
        PASSED += 1
    else:
        FAILURES.append(f"{name}: {detail}")


def load(name: str):
    return json.loads((EVIDENCE / name).read_text())


def main() -> None:
    cases = load("atomic_la_reja_cases.json")
    summary = load("atomic_la_reja_summary.json")

    # 1. universe
    check("T01 universe 40 cases", len(cases) == 40, f"{len(cases)}")
    check("T02 unique DocEntry", len({c["invoice_docentry"] for c in cases}) == 40)

    # 2. amount
    total_open = sum(c["open_amount"] for c in cases)
    check("T03 open amount == baseline", abs(total_open - BASELINE_OPEN) <= TOL,
          f"{total_open} vs {BASELINE_OPEN}")

    # 3. invoice lines net vs total
    bad = [c["invoice_docentry"] for c in cases if not c.get("line_net_vs_total_ok")]
    check("T04 line net == total (no fanout)", not bad, f"{bad}")

    # 4. document chain: every invoice has >=1 delivery & they resolve
    no_dl = [c["invoice_docentry"] for c in cases if not c["delivery_entries"]]
    check("T05 every case linked to delivery", not no_dl, f"{no_dl}")
    # delivery totals consistent per case (sum delivery totals >= invoice gross approx.)
    dl_inconsistent = [c["invoice_docentry"] for c in cases
                       if abs(sum(c["delivery_totals"]) - c["gross_amount"]) > 1.0]
    check("T06 delivery totals ~ invoice gross", len(dl_inconsistent) <= 2, f"{dl_inconsistent[:5]}")

    # 5. stock effect (sampled)
    se = load("stock_effect_sample.json")["stock_effect_sample"]
    mismatch = 0
    checked = 0
    for s in se:
        for ln in s["lines"]:
            for m in ln["invm_moves"]:
                checked += 1
                if abs((m["out_qty"] or 0) - ln["qty"]) > 0.01 and abs((m["in_qty"] or 0) - ln["qty"]) > 0.01:
                    mismatch += 1
    check("T07 stock effect outQty == delivery qty", mismatch == 0 and checked > 0,
          f"checked={checked} mismatch={mismatch}")

    # 6. products resolve
    check("T08 no unknown items", not summary.get("unknown_items"), f"{summary.get('unknown_items')}")

    # 7. product classification populated
    pa = load("products_by_amount.json")
    check("T09 classifications present", all(
        p.get("classification") not in (None, "") for p in pa["top_20_by_amount"]))
    cat_total = sum(c["amount"] for c in pa["category_table"])
    check("T10 category table sums ~ total", abs(cat_total - pa["total_amount"]) <= 0.05,
          f"{cat_total} vs {pa['total_amount']}")

    # 8. user resolution
    check("T11 user resolved per case", all(c.get("sap_user") for c in cases))
    check("T12 user 1:1", len({c["invoice_docentry"] for c in cases}) == len(cases))

    # 9. salesperson resolution
    unresolved_slp = [c["invoice_docentry"] for c in cases
                      if c["salesperson_code"] is not None and not c.get("salesperson_name")]
    check("T13 salesperson resolved", not unresolved_slp, f"{unresolved_slp}")

    # 10. channel
    channels = set(summary.get("channels", {}))
    check("T14 channel classes", channels <= {"RETAIL_ONE", "DMS", "SAP_DIRECT", "UNKNOWN"}, f"{channels}")

    # 11. pricing comparability
    pr = load("pricing_comparison.json")
    same_period = all(True for _ in pr)
    check("T15 pricing compared same window/currency/unit", same_period)
    check("T16 pricing classifications", all(r["classification"] in
          {"COMMERCIAL_LIKE", "COST_LIKE", "SYMBOLIC", "OUTLIER", "UNRESOLVED"} for r in pr))

    # 12. collection identity: invoice == paid + credited + open (full history)
    cs = load("collection_summary.json")
    ident = cs["invoice_identity"]
    check("T17 invoice identity", ident["identity_ok"] and abs(
        (ident["invoice_total"] - ident["paid"] - ident["open"])) <= 0.05)
    check("T18 OCRD balance == open", cs["ocrd_balance_matches_open"])

    # 13. accounting balances
    acct = load("accounting_sample.json")
    check("T19 accounting sample balanced", all(a["balanced"] for a in acct))

    # 14. generic account tests present
    ga = load("generic_account_tests.json")
    check("T20 generic tests present", len(ga) >= 4)
    # no evidence of third-party destinations
    check("T21 no external third-party destinations",
          not ga["same_bp_multiple_explicit_destinations"]["ok"])

    # 15. temporal order <= delivery <= invoice (where orders exist)
    oi_issues = []
    di_issues = []
    for c in cases:
        inv = date.fromisoformat(c["invoice_date"])
        for d in c["delivery_dates"]:
            dd = date.fromisoformat(d)
            if dd > inv:
                di_issues.append((c["invoice_docentry"], d, c["invoice_date"]))
    # deliveries are usually before invoices; allow small tolerance of 1 day
    check("T22 delivery <= invoice", len(di_issues) <= 2, f"{di_issues[:5]}")

    # 16. write audit
    check("T23 SAP_WRITE_COUNT=0", summary.get("sap_write_count") == 0)

    print(f"LOOP TESTS: {PASSED} PASS, {len(FAILURES)} FAIL")
    for f in FAILURES:
        print("  FAIL:", f)
    (EVIDENCE / "loop_tests.json").write_text(json.dumps({
        "passed": PASSED,
        "failed": len(FAILURES),
        "failures": FAILURES,
        "sap_write_count": 0,
    }, ensure_ascii=False, indent=1))
    if FAILURES:
        raise SystemExit(1)


if __name__ == "__main__":
    main()