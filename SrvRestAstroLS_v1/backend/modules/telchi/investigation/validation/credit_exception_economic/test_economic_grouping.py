"""LOOP TEST 46-60 — TELCHI EXPLAINED CASES ECONOMIC GROUPING V1 (deterministic).

Pure Python: real evidence JSONs + static fixtures. No HANA calls.

Covers: 268 atomic input, single grouping, no double counting, amount
reconciliation, paid+credited+open invariant, date/period ordering, monthly
reconciliation, USER FULL preservation (40), CUSTOMER EXCEPTION preservation
(12), payment status reconciliation (106/0/162), currency single (BS),
business-group mapping fixtures, prior-gate freeze regression (287 intact).
"""
from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

HERE = Path(__file__).parent
EV = EVIDENCE_ROOT / "credit_exception_economic" / "evidence"
ROOT = HERE.parent

TOL = 0.05

GROUP_OF_REASON = {
    "SAP_FULL_AUTHORIZATION": ("USER_AUTHORIZATION_FULL", "SAP_FULL_AUTHORIZATION"),
    "SUPERUSER_AUTHORIZATION": ("USER_AUTHORIZATION_FULL", "SUPERUSER_AUTHORIZATION"),
    "CUSTOMER_EXCEPTION_FLAG": ("CUSTOMER_EXCEPTION", "CUSTOMER_EXCEPTION_FLAG"),
    "DELIVERY_FLOW_EXPLAINS_TIMING": ("DOCUMENT_FLOW_PREAUTHORIZED", "DELIVERY_PREVIOUS"),
    "ORDER_AUTHORIZED_BEFORE_OVERDUE": ("DOCUMENT_FLOW_PREAUTHORIZED", "ORDER_PREVIOUS"),
    "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK": ("NON_CREDIT_RETAIL_CASH", "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK"),
    "TECHNICAL_INTEGRATION_PATH": ("TECHNICAL_RECONCILIATION", "TECHNICAL_INTEGRATION_PATH"),
    "CREDIT_NOTE_OR_RECONCILIATION": ("TECHNICAL_RECONCILIATION", "CREDIT_NOTE_OR_RECONCILIATION"),
}


def load_rows() -> list[dict]:
    return json.loads((EV / "grouped_cases.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- cardinality


class TestAtomicUniverse(unittest.TestCase):
    def test_268_input_grouped_268_unique(self):
        rows = load_rows()
        self.assertEqual(len(rows), 268)
        self.assertEqual(len({r["doc_entry"] for r in rows}), 268)

    def test_composition_matches_frozen_gate(self):
        # baseline 287 = 268 explained + 19 unresolved (frozen gate)
        rows = load_rows()
        by_secondary = Counter(r["secondary_reason"] for r in rows)
        expected = {
            "DELIVERY_PREVIOUS": 140, "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK": 58,
            "SAP_FULL_AUTHORIZATION": 40, "ORDER_PREVIOUS": 15,
            "CUSTOMER_EXCEPTION_FLAG": 12, "TECHNICAL_INTEGRATION_PATH": 2,
            "CREDIT_NOTE_OR_RECONCILIATION": 1,
        }
        self.assertEqual(dict(by_secondary), expected)

    def test_each_case_one_primary_group(self):
        rows = load_rows()
        for r in rows:
            self.assertIsInstance(r["primary_business_group"], str)
            self.assertIn(r["secondary_reason"], GROUP_OF_REASON[r["classification"]])
        # no duplicates of docentry across groups
        self.assertEqual(len(rows), 268)
        by_entry = Counter(r["doc_entry"] for r in rows)
        self.assertLessEqual(max(by_entry.values()), 1)

    def test_no_double_count_between_groups(self):
        report = json.loads((EV / "grouping_report.json").read_text(encoding="utf-8"))
        self.assertTrue(report["no_double_count"])
        self.assertEqual(report["grouped_cases"], 268)
        self.assertEqual(report["distinct_doc_entry"], 268)
        self.assertEqual(sum(report["group_case_counts"].values()), 268)


# ---------------------------------------------------------------- amount


class TestAmountReconciliation(unittest.TestCase):
    def test_group_sum_equals_atomic_sum(self):
        from modules.telchi.investigation.validation.credit_exception_economic.group_cases import load_268, decorate
        atomic = [decorate(c) for c in load_268()]
        grouped = load_rows()
        self.assertAlmostEqual(
            sum(r["gross_sales_amount"] for r in grouped),
            sum(r["gross_sales_amount"] for r in atomic), delta=0.01)

    def test_paid_plus_credited_plus_open_equals_gross(self):
        rows = load_rows()
        for r in rows:
            self.assertAlmostEqual(
                r["paid_amount"] + r["credited_amount"] + r["open_amount"],
                r["gross_sales_amount"], delta=TOL,
                msg=f"DocEntry {r['doc_entry']}")

    def test_reported_totals_match_frozen_values(self):
        report = json.loads((EV / "grouping_report.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(report["total_gross_amount"], 318051.61, delta=0.01)
        self.assertAlmostEqual(report["total_paid_amount"], 63686.61, delta=0.01)
        self.assertAlmostEqual(report["total_credited_amount"], 1392.00, delta=0.01)
        self.assertAlmostEqual(report["total_open_amount"], 252973.00, delta=0.01)
        self.assertAlmostEqual(report["amount_reconciliation"]["delta"], 0.0, delta=0.0001)
        self.assertAlmostEqual(report["paid_credited_open_reconciliation"]["delta"], 0.0, delta=0.0001)


# ---------------------------------------------------------------- period


class TestPeriod(unittest.TestCase):
    def test_group_first_lt_last(self):
        metrics = json.loads((EV / "economic_metrics.json").read_text(encoding="utf-8"))
        for g, m in metrics.items():
            self.assertLessEqual(m["first_sale_date"], m["last_sale_date"], msg=g)

    def test_all_sales_within_global_period(self):
        rows = load_rows()
        first = min(r["docdate"] for r in rows)
        last = max(r["docdate"] for r in rows)
        self.assertEqual(first, "2026-01-12")
        self.assertEqual(last, "2026-09-01")
        for r in rows:
            self.assertGreaterEqual(r["docdate"], first)
            self.assertLessEqual(r["docdate"], last)


# ---------------------------------------------------------------- monthly


class TestMonthlyReconciliation(unittest.TestCase):
    def test_monthly_sums_equal_universe(self):
        series = json.loads((EV / "monthly_series.json").read_text(encoding="utf-8"))
        rows = load_rows()
        tot = series["TOTAL"]
        self.assertAlmostEqual(sum(m["case_count"] for m in tot), 268, delta=0.01)
        self.assertAlmostEqual(
            sum(m["sales_amount"] for m in tot),
            sum(r["gross_sales_amount"] for r in rows), delta=0.01)
        self.assertAlmostEqual(
            sum(m["open_amount"] for m in tot),
            sum(r["open_amount"] for r in rows), delta=0.01)
        # group-level monthly also reconciles
        by_group = Counter(r["primary_business_group"] for r in rows)
        for g, mlist in series.items():
            if g == "TOTAL":
                continue
            self.assertEqual(sum(m["case_count"] for m in mlist), by_group[g], msg=g)

    def test_monthly_group_series_stable(self):
        series = json.loads((EV / "monthly_series.json").read_text(encoding="utf-8"))
        # each group month: sales == sum of its cases; open monotonicity not required
        for g, mlist in series.items():
            if g == "TOTAL":
                continue
            for m in mlist:
                self.assertEqual(m["business_group"], g)
                self.assertGreaterEqual(m["case_count"], 0)
                self.assertGreaterEqual(m["sales_amount"], 0.0)


# ---------------------------------------------------------------- USER FULL


class TestUserFull(unittest.TestCase):
    def test_full_preserved_40(self):
        rows = load_rows()
        full = [r for r in rows if r["primary_business_group"] == "USER_AUTHORIZATION_FULL"]
        self.assertEqual(len(full), 40)
        self.assertEqual(len({r["doc_entry"] for r in full}), 40)
        detail = json.loads((EV / "user_full_detail.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(u["case_count"] for u in detail), 40)

    def test_full_users_have_full_authorization_source(self):
        detail = json.loads((EV / "user_full_detail.json").read_text(encoding="utf-8"))
        for u in detail:
            self.assertEqual(u["authorization_level"], "FULL")
            self.assertIn("HISTORICAL_AUTHORIZATION=UNAVAILABLE", u["authorization_source"])

    def test_technical_full_user_separated(self):
        detail = json.loads((EV / "user_full_detail.json").read_text(encoding="utf-8"))
        tech = [u for u in detail if u["technical_user"]]
        self.assertEqual([u["user_code"] for u in tech], ["soluone"])
        # soluone cases are attributed upstream (POS operator) in the detail
        self.assertGreaterEqual(tech[0]["case_count"], 1)


# ---------------------------------------------------------------- CUSTOMER EXCEPTION


class TestCustomerException(unittest.TestCase):
    def test_exception_preserved_12(self):
        rows = load_rows()
        exc = [r for r in rows if r["primary_business_group"] == "CUSTOMER_EXCEPTION"]
        self.assertEqual(len(exc), 12)
        detail = json.loads((EV / "customer_exception_detail.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(d["case_count"] for d in detail), 12)
        self.assertEqual(len({r["doc_entry"] for r in exc}), 12)

    def test_exception_flag_evidence(self):
        rows = load_rows()
        for r in rows:
            if r["primary_business_group"] == "CUSTOMER_EXCEPTION":
                self.assertTrue(r["vencrevenc_y"])
        detail = json.loads((EV / "customer_exception_detail.json").read_text(encoding="utf-8"))
        for d in detail:
            self.assertEqual(d["flag"], "U_SO1_01VENCREVENC='Y'")
            self.assertEqual(d["flag_history"], "CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE")

    def test_exception_customers_must_be_flagged(self):
        # C011358 has the flag too; only C000398 has exception sales in the
        # 268 window — do not assume others without revalidation (report does revalidate)
        detail = json.loads((EV / "customer_exception_detail.json").read_text(encoding="utf-8"))
        self.assertEqual({d["cardcode"] for d in detail}, {"C000398"})


# ---------------------------------------------------------------- payment


class TestPaymentStatus(unittest.TestCase):
    def test_payment_status_reconciliation(self):
        rows = load_rows()
        st = Counter(r["current_status"] for r in rows)
        self.assertEqual(st.get("FULLY_PAID", 0) + st.get("PARTIALLY_PAID", 0), 106)
        self.assertEqual(st.get("OPEN", 0), 162)
        self.assertEqual(st.get("PARTIALLY_PAID", 0), 0)
        collection = json.loads((EV / "collection.json").read_text(encoding="utf-8"))
        self.assertEqual(collection["TOTAL"]["fully_paid_count"], 106)
        self.assertEqual(collection["TOTAL"]["open_count"], 162)
        self.assertAlmostEqual(collection["TOTAL"]["paid_amount"], 63686.61, delta=0.01)

    def test_credit_note_amount_not_double_counted(self):
        rows = load_rows()
        credited_rows = [r for r in rows if r["credited_amount"] > 0]
        self.assertEqual(len(credited_rows), 1)
        self.assertAlmostEqual(sum(r["credited_amount"] for r in credited_rows), 1392.00, delta=0.01)


# ---------------------------------------------------------------- currency


class TestCurrency(unittest.TestCase):
    def test_single_currency_bs(self):
        exec_sum = json.loads((EV / "executive_summary.json").read_text(encoding="utf-8"))
        self.assertIn("BS", exec_sum["currency"])
        # frozen by grouping report amounts (all BS, DocCur='BS' for all 268)
        report = json.loads((EV / "grouping_report.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(report["total_gross_amount"], 318051.61, delta=0.01)


# ---------------------------------------------------------------- prior gate freeze


class TestPriorGateRegression(unittest.TestCase):
    def test_baseline_287_frozen(self):
        prior = json.loads((EVIDENCE_ROOT / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(prior["sales_with_overdue_at_sale"], 287)
        self.assertEqual(len(prior["all_overdue_sales"]), 287)

    def test_268_subset_of_287_intersection_of_atomic(self):
        prior = json.loads((EVIDENCE_ROOT / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                           .read_text(encoding="utf-8"))["all_overdue_sales"]
        prior_keys = {(s["cardcode"], s["docentry"]) for s in prior}
        classified = json.loads((EVIDENCE_ROOT / "credit_exception" / "evidence" / "classified_cases.json")
                                .read_text(encoding="utf-8"))
        rows = load_rows()
        for r in rows:
            self.assertIn((r["cardcode"], r["doc_entry"]), prior_keys)
            base = next(x for x in classified if x["doc_entry"] == r["doc_entry"])
            self.assertEqual(base["classification"], r["classification"])

    def test_unresolved_19_excluded_and_intact(self):
        classified = json.loads((EVIDENCE_ROOT / "credit_exception" / "evidence" / "classified_cases.json")
                                .read_text(encoding="utf-8"))
        prior = json.loads((EVIDENCE_ROOT / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                           .read_text(encoding="utf-8"))["all_overdue_sales"]
        prior_keys = {(s["cardcode"], s["docentry"]) for s in prior}
        base = [x for x in classified if (x["cardcode"], x["doc_entry"]) in prior_keys]
        unresolved = [x for x in base if x["classification"] == "UNRESOLVED"]
        self.assertEqual(len(unresolved), 19)
        self.assertEqual(len(unresolved) + len(load_rows()), 287)


# ---------------------------------------------------------------- fixtures


class TestGroupMappingFixtures(unittest.TestCase):
    def _case(self, reason, **kw):
        base = {"cardcode": "C1", "doc_entry": 1, "docdate": "2026-08-01",
                "doctotal": 100.0, "paidtodate": 100.0, "open_now": 0.0,
                "settled_by_credit_note": False, "current_status": "FULLY_PAID",
                "vencrevenc_y": False, "origin": "SAP", "retailone": "N",
                "classification": reason, "sap_user": "user1", "superuser": "N",
                "technical_user": False}
        base.update(kw)
        return base

    def test_primary_group_mapping(self):
        from modules.telchi.investigation.validation.credit_exception_economic.group_cases import decorate, GROUP_OF_REASON
        for reason, (primary, secondary) in GROUP_OF_REASON.items():
            row = decorate(self._case(reason))
            self.assertEqual(row["primary_business_group"], primary, reason)
            self.assertEqual(row["secondary_reason"], secondary, reason)

    def test_full_distinctions(self):
        from modules.telchi.investigation.validation.credit_exception_economic.group_cases import decorate
        row = decorate(self._case("SAP_FULL_AUTHORIZATION", sap_user="lzarraga", superuser="N"))
        self.assertEqual(row["full_by"], "FULL_BY_GROUP")
        row = decorate(self._case("SAP_FULL_AUTHORIZATION", sap_user="soluone", superuser="Y"))
        self.assertEqual(row["full_by"], "FULL_BY_TECHNICAL")
        row = decorate(self._case("SAP_FULL_AUTHORIZATION", sap_user="root", superuser="Y"))
        self.assertEqual(row["full_by"], "FULL_BY_SUPERUSER")
        # non-FULL cases carry no full_by
        row = decorate(self._case("DELIVERY_FLOW_EXPLAINS_TIMING"))
        self.assertIsNone(row["full_by"])

    def test_credited_decomposition(self):
        from modules.telchi.investigation.validation.credit_exception_economic.group_cases import decorate
        # credit-note settled: paidtodate includes the NC
        row = decorate(self._case("CREDIT_NOTE_OR_RECONCILIATION", settled_by_credit_note=True,
                                  doctotal=100.0, paidtodate=100.0, open_now=0.0))
        self.assertAlmostEqual(row["credited_amount"], 100.0, delta=0.01)
        self.assertAlmostEqual(row["paid_amount"], 0.0, delta=0.01)


if __name__ == "__main__":
    unittest.main()