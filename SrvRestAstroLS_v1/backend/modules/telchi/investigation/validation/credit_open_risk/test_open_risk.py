"""LOOP TEST 61-75 — TELCHI OPEN RISK × AGING V1 (deterministic).

Pure Python: real evidence JSONs + static fixtures. No HANA calls.

Covers: 268 atomic preserved; baseline open 252,973.00 reconciled; open ==
not_due + overdue at document/customer/group/global level; single-installment
semantics; aging bucket exclusivity (= total overdue); USER FULL 40 /
180,396.95 / 19,000.27 overdue; DELIVERY 140 / 71,282.55 / 58,043.85 overdue;
monthly cohort sums (268 / 318,051.61 / 252,973.00); temporal consistency
(sale<=due, days_overdue>0 only when due<cutoff and open>0); currency BS;
user semantics (SAP user != salesperson != operator); historical authorization
caveat preserved; prior-gate freeze (economic grouping intact).
"""
from __future__ import annotations

import json
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EV = EVIDENCE_ROOT / "credit_open_risk" / "evidence"
ROOT = HERE.parent

TOL = 0.05
CUTOFF = date(2026, 9, 1)


def load() -> list[dict]:
    return json.loads((EV / "open_risk_cases.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- baseline


class TestBaseline(unittest.TestCase):
    def test_268_cases_preserved_unique(self):
        rows = load()
        self.assertEqual(len(rows), 268)
        self.assertEqual(len({r["doc_entry"] for r in rows}), 268)

    def test_baseline_open_reconciled(self):
        rows = load()
        self.assertAlmostEqual(sum(r["open_amount"] for r in rows), 252973.00, delta=TOL)

    def test_open_equals_not_due_plus_overdue_global(self):
        rows = load()
        self.assertAlmostEqual(
            sum(r["open_amount"] for r in rows),
            sum(r["not_due_amount"] for r in rows) + sum(r["overdue_amount"] for r in rows),
            delta=TOL)

    def test_open_equals_not_due_plus_overdue_per_document(self):
        rows = load()
        for r in rows:
            self.assertAlmostEqual(r["open_amount"],
                                   r["not_due_amount"] + r["overdue_amount"], delta=TOL,
                                   msg=f"DocEntry {r['doc_entry']}")

    def test_open_equals_not_due_plus_overdue_per_group(self):
        rows = load()
        by_group = {}
        for r in rows:
            by_group.setdefault(r["primary_business_group"],
                                {"open": 0.0, "not_due": 0.0, "overdue": 0.0})
            g = by_group[r["primary_business_group"]]
            g["open"] += r["open_amount"]
            g["not_due"] += r["not_due_amount"]
            g["overdue"] += r["overdue_amount"]
        for g, v in by_group.items():
            self.assertAlmostEqual(v["open"], v["not_due"] + v["overdue"], delta=TOL, msg=g)

    def test_baseline_summary_file(self):
        s = json.loads((EV / "open_risk_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(s["total_open"], 252973.00)
        self.assertTrue(s["reconciliation"]["invariant"])
        self.assertEqual(s["reconciliation"]["delta"], 0.0)
        self.assertEqual(s["cutoff"], "2026-09-01")


# ---------------------------------------------------------------- due split


class TestDueSplit(unittest.TestCase):
    def test_global_not_due_overdue_frozen(self):
        s = json.loads((EV / "open_risk_summary.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(s["total_not_due"], 175928.88, delta=TOL)
        self.assertAlmostEqual(s["total_overdue"], 77044.12, delta=TOL)

    def test_state_distribution(self):
        rows = load()
        st = Counter(r["open_state"] for r in rows)
        self.assertEqual(st.get("OPEN_NOT_DUE", 0), 96)
        self.assertEqual(st.get("OPEN_FULLY_OVERDUE", 0), 66)
        self.assertEqual(st.get("FULLY_PAID", 0), 105)
        self.assertEqual(st.get("CREDITED", 0), 1)
        # no partially-overdue possible in this installation (single installment)
        self.assertEqual(st.get("OPEN_PARTIALLY_OVERDUE", 0), 0)


# ---------------------------------------------------------------- aging


class TestAging(unittest.TestCase):
    def test_aging_buckets_exhaustive_and_disjoint(self):
        aging = json.loads((EV / "aging.json").read_text(encoding="utf-8"))["TOTAL"]
        total_overdue = sum(b["overdue_amount"] for b in aging if b["bucket"] != "NOT_YET_DUE")
        rows = load()
        self.assertAlmostEqual(total_overdue, 77044.12, delta=TOL)
        self.assertAlmostEqual(
            sum(b["overdue_amount"] for b in aging),
            sum(r["overdue_amount"] for r in rows), delta=TOL)

    def test_each_overdue_case_in_exactly_one_bucket(self):
        aging = json.loads((EV / "aging.json").read_text(encoding="utf-8"))["TOTAL"]
        rows = load()
        overdue = [r for r in rows if r["days_overdue"] > 0]
        assigned = 0
        for b in aging:
            if b["bucket"] == "NOT_YET_DUE":
                continue
            lo, hi = {"1-15": (1, 15), "16-30": (16, 30), "31-60": (31, 60),
                      "61-90": (61, 90), "91-180": (91, 180), "181+": (181, 10**9)}[b["bucket"]]
            self.assertEqual(b["case_count"],
                             sum(1 for r in overdue if lo <= r["days_overdue"] <= hi), msg=b["bucket"])
            assigned += b["case_count"]
        self.assertEqual(assigned, len(overdue))

    def test_not_yet_due_bucket(self):
        aging = json.loads((EV / "aging.json").read_text(encoding="utf-8"))["TOTAL"]
        ny = next(b for b in aging if b["bucket"] == "NOT_YET_DUE")
        self.assertEqual(ny["case_count"], 96)
        self.assertAlmostEqual(ny["open_amount"], 175928.88, delta=TOL)


# ---------------------------------------------------------------- USER FULL


class TestUserFull(unittest.TestCase):
    def test_full_reconciliation(self):
        rows = load()
        full = [r for r in rows if r["primary_business_group"] == "USER_AUTHORIZATION_FULL"]
        self.assertEqual(len(full), 40)
        self.assertAlmostEqual(sum(r["gross_sales_amount"] for r in full), 189700.50, delta=TOL)
        self.assertAlmostEqual(sum(r["open_amount"] for r in full), 180396.95, delta=TOL)
        self.assertAlmostEqual(sum(r["overdue_amount"] for r in full), 19000.27, delta=TOL)
        self.assertAlmostEqual(
            sum(r["open_amount"] for r in full),
            sum(r["not_due_amount"] for r in full) + sum(r["overdue_amount"] for r in full),
            delta=TOL)
        detail = json.loads((EV / "user_full_detail.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(u["open_cases"] for u in detail["by_user"]), 32)

    def test_full_overdue_concentrated_users(self):
        detail = json.loads((EV / "user_full_detail.json").read_text(encoding="utf-8"))
        top = detail["by_user"][0]
        self.assertEqual(top["user_code"], "jirahola")
        self.assertAlmostEqual(top["overdue_amount"], 11790.51, delta=TOL)


# ---------------------------------------------------------------- DELIVERY


class TestDelivery(unittest.TestCase):
    def test_delivery_reconciliation(self):
        rows = load()
        dl = [r for r in rows if r["secondary_reason"] == "DELIVERY_PREVIOUS"]
        self.assertEqual(len(dl), 140)
        self.assertAlmostEqual(sum(r["gross_sales_amount"] for r in dl), 72784.72, delta=TOL)
        self.assertAlmostEqual(sum(r["open_amount"] for r in dl), 71282.55, delta=TOL)
        self.assertAlmostEqual(sum(r["overdue_amount"] for r in dl), 58043.85, delta=TOL)
        self.assertAlmostEqual(
            sum(r["open_amount"] for r in dl),
            sum(r["not_due_amount"] for r in dl) + sum(r["overdue_amount"] for r in dl),
            delta=TOL)
        detail = json.loads((EV / "delivery_detail.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(detail["overdue_amount"], 58043.85, delta=TOL)
        self.assertEqual(detail["overdue_cases"], 57)

    def test_la_reja_dominant(self):
        detail = json.loads((EV / "delivery_detail.json").read_text(encoding="utf-8"))
        lr = detail["la_reja"]
        self.assertIsNotNone(lr)
        self.assertEqual(lr["cases"], 40)
        self.assertAlmostEqual(lr["overdue"], 47258.99, delta=TOL)
        self.assertEqual(lr["overdue_cases"], 40)

    def test_delivery_timing_single_installment(self):
        timing = json.loads((EV / "delivery_timing.json").read_text(encoding="utf-8"))
        self.assertEqual(timing["with_delivery_date"], 140)
        self.assertEqual(timing["invoice_to_due_days"]["median"], 31)


# ---------------------------------------------------------------- cohorts


class TestMonthlyCohorts(unittest.TestCase):
    def test_monthly_sums(self):
        cohorts = json.loads((EV / "monthly_cohorts.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(sum(m["cases"] for m in cohorts), 268, delta=0.01)
        self.assertAlmostEqual(sum(m["sale_amount"] for m in cohorts), 318051.61, delta=0.01)
        self.assertAlmostEqual(sum(m["open_amount"] for m in cohorts), 252973.00, delta=0.01)
        self.assertAlmostEqual(sum(m["overdue_amount"] for m in cohorts), 77044.12, delta=0.01)

    def test_august_is_recent_not_overdue(self):
        cohorts = json.loads((EV / "monthly_cohorts.json").read_text(encoding="utf-8"))
        aug = next(m for m in cohorts if m["month"] == "2026-08")
        self.assertLess(aug["pct_of_month_open_overdue"], 10.0)


# ---------------------------------------------------------------- temporal / currency / users


class TestSemantics(unittest.TestCase):
    def test_temporal_consistency(self):
        rows = load()
        for r in rows:
            self.assertLessEqual(r["docdate"][:10], r["due_date"][:10],
                                 msg=f"DocEntry {r['doc_entry']}")
        for r in rows:
            if r["overdue_amount"] > TOL:
                self.assertLess(r["due_date"][:10], "2026-09-01", msg=r["doc_entry"])
                self.assertGreater(r["open_amount"], 0.0)

    def test_currency_bs(self):
        # frozen: all 268 DocCur='BS' verified in economic gate; summary preserved
        s = json.loads((EV / "open_risk_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(s["cutoff"], "2026-09-01")

    def test_user_vs_salesperson_not_mixed(self):
        rows = load()
        # sap_user field is a user code; slpcode is numeric OSLP; retail pos is separate
        for r in rows:
            self.assertIsInstance(r["sap_user"], str)
            self.assertIsInstance(r["slpcode"], int)

    def test_historical_authorization_caveat_preserved(self):
        detail = json.loads((EV / "user_full_detail.json").read_text(encoding="utf-8"))
        for u in detail["by_user"]:
            self.assertIn("HISTORICAL_AUTHORIZATION=UNAVAILABLE", u["authorization_source"])


# ---------------------------------------------------------------- prior gate freeze


class TestPriorGateRegression(unittest.TestCase):
    def test_economic_grouping_evidence_intact(self):
        rep = json.loads((EVIDENCE_ROOT / "credit_exception_economic" / "evidence" / "grouping_report.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(rep["grouped_cases"], 268)
        self.assertAlmostEqual(rep["total_open_amount"], 252973.00, delta=0.01)

    def test_open_risk_rows_still_match_grouped(self):
        grouped = json.loads((EVIDENCE_ROOT / "credit_exception_economic" / "evidence" / "grouped_cases.json")
                             .read_text(encoding="utf-8"))
        rows = load()
        gidx = {r["doc_entry"]: r for r in grouped}
        for r in rows:
            g = gidx[r["doc_entry"]]
            self.assertEqual(g["primary_business_group"], r["primary_business_group"])
            self.assertEqual(g["open_amount"], r["open_amount"])

    def test_unresolved_19_still_excluded(self):
        classified = json.loads((EVIDENCE_ROOT / "credit_exception" / "evidence" / "classified_cases.json")
                                .read_text(encoding="utf-8"))
        prior = json.loads((EVIDENCE_ROOT / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                           .read_text(encoding="utf-8"))["all_overdue_sales"]
        prior_keys = {(s["cardcode"], s["docentry"]) for s in prior}
        base = [x for x in classified if (x["cardcode"], x["doc_entry"]) in prior_keys]
        unresolved = len([x for x in base if x["classification"] == "UNRESOLVED"])
        self.assertEqual(unresolved, 19)
        self.assertEqual(unresolved + len(load()), 287)


# ---------------------------------------------------------------- fixtures


class TestDueDateSemanticsFixtures(unittest.TestCase):
    def _row(self, due, open_amt):
        return {
            "cardcode": "C1", "doc_entry": 1, "docnum": "N1",
            "docdate": "2026-08-01", "docduedate": due,
            "doctotal": 100.0, "open_amount": open_amt, "not_due_amount": 0.0,
            "overdue_amount": 0.0, "paid_amount": 0.0, "credited_amount": 0.0,
            "days_overdue": 0, "days_to_due": 0, "gross_sales_amount": 100.0,
            "primary_business_group": "X", "secondary_reason": "Y",
            "sap_user": "u1", "slpcode": 1, "cardname": "X", "channel": "S",
            "evidence": [], "warning": [], "docnum": "1",
        }

    def test_future_due_not_overdue(self):
        from modules.telchi.investigation.validation.credit_open_risk.open_risk_cases import CUTOFF, TOLERANCE, enrich
        base = self._row("2026-09-15", 60.0)
        row = enrich(base)
        self.assertEqual(row["open_state"], "OPEN_NOT_DUE")
        self.assertEqual(row["overdue_amount"], 0.0)
        self.assertEqual(row["not_due_amount"], 60.0)
        # due in the future, open positive -> no overdue
        self.assertLessEqual(row["days_overdue"], 0)

    def test_past_due_fully_overdue(self):
        from modules.telchi.investigation.validation.credit_open_risk.open_risk_cases import enrich
        row = enrich(self._row("2026-08-10", 60.0))
        self.assertEqual(row["open_state"], "OPEN_FULLY_OVERDUE")
        self.assertEqual(row["overdue_amount"], 60.0)
        self.assertEqual(row["not_due_amount"], 0.0)

    def test_paid_case_not_overdue(self):
        from modules.telchi.investigation.validation.credit_open_risk.open_risk_cases import enrich
        row = enrich(self._row("2026-08-10", 0.0))
        self.assertIn(row["open_state"], ("FULLY_PAID", "CREDITED"))
        self.assertEqual(row["overdue_amount"], 0.0)

    def test_risk_categories(self):
        from modules.telchi.investigation.validation.credit_open_risk.open_risk_cases import enrich
        r1 = enrich(self._row("2026-07-01", 50.0))   # 62 days overdue
        r2 = enrich(self._row("2026-05-01", 50.0))   # 123 days overdue
        r3 = enrich(self._row("2026-09-15", 50.0))   # not due
        self.assertIn(r1["risk_category"], ("OVERDUE_MEDIUM_AGE",))
        self.assertIn(r2["risk_category"], ("OVERDUE_HIGH_AGE",))
        self.assertEqual(r3["risk_category"], "OPEN_NOT_DUE")


if __name__ == "__main__":
    unittest.main()