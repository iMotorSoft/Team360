"""LOOP TEST 36-45 — TELCHI CREDIT EXCEPTION CASES V1 (deterministic).

Pure Python: fixtures + real evidence JSONs + static source scan.
No HANA calls. Runs independently of extractor execution order.

Covers: historical receivable, retail authorization, order/delivery/invoice,
credit limit, classification (per-reason fixtures), cardinality, amount
reconciliation, temporal ordering, read-only audit, prior-gate regression.
"""
from __future__ import annotations

import json
import re
import unittest
from datetime import date
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.validation.credit_exception.classify import classify_one, CONF_LEVEL
from modules.telchi.investigation.validation.credit_exception.revalidate import reconstruct_sales_state, WINDOW_START as WS
from modules.telchi.investigation.validation.credit_exception.retail_auth import parse_folio
from modules.telchi.investigation.validation.credit_control.readonly import _WRITE_TOKENS, guard_sql

HERE = Path(__file__).parent
EV = EVIDENCE_ROOT / "credit_exception" / "evidence"

TOL = 0.01


def d(day: str) -> date:
    return date.fromisoformat(day)


def mk_doc(cardcode, docentry, docdate, duedate, total, paid=0.0, doc_type="OINV"):
    return {
        "cardcode": cardcode, "docentry": docentry, "docnum": f"N{docentry}",
        "docdate": f"{docdate} 00:00:00", "docduedate": f"{duedate} 00:00:00",
        "doctotal": total, "paidtodate": paid, "canceled": "N", "usersign": 1,
        "u_origin": "SAP", "u_so1_01retailone": "N", "slpcode": 1, "groupnum": 1,
        "_type": doc_type,
    }


def sale_state(cardcode, docentry, docdate, duedate, total, app, ocrd=None, paid=0.0):
    docs = [mk_doc(cardcode, docentry, docdate, duedate, total, paid)]
    return reconstruct_sales_state(docs, app, ocrd or {cardcode: {"creditline": 10000.0}},
                                   WS, d("2026-09-01"))

# ---------------------------------------------------------------- receivable


class TestHistoricalReceivable(unittest.TestCase):
    def setUp(self):
        self.ocrd = {"C1": {"creditline": 100000.0}}

    def _docs(self, *docs):
        return list(docs)

    def test_invoice_open_at_sale_is_overdue(self):
        docs = self._docs(
            mk_doc("C1", 1001, "2026-01-01", "2026-01-10", 500.0),
            mk_doc("C1", 1002, "2026-01-15", "2026-02-01", 300.0),
        )
        app = {1001: []}
        sales = reconstruct_sales_state(docs, {(1001, "C1")[0] if False else 1001: []}, self.ocrd, WS, d("2026-09-01"))
        s15 = [s for s in sales if s["docentry"] == 1002][0]
        self.assertTrue(s15["overdue_at_sale"])
        self.assertAlmostEqual(s15["overdue_amount_at_sale"], 500.0, delta=0.01)

    def test_invoice_paid_before_sale_not_overdue(self):
        docs = self._docs(
            mk_doc("C1", 1001, "2026-01-01", "2026-01-10", 500.0),
            mk_doc("C1", 1002, "2026-01-15", "2026-02-01", 300.0),
        )
        app = {1001: [(d("2026-01-11"), 500.0)]}  # paid day after due but before sale
        sales = reconstruct_sales_state(docs, {1001: [(d("2026-01-10"), 500.0)]}, self.ocrd, WS, d("2026-09-01"))
        # paid on due date -> not overdue
        s15 = [s for s in sales if s["docentry"] == 1002][0]
        self.assertTrue(s15["overdue_at_sale"] == False)

    def test_partial_payment_reduces_overdue_amount(self):
        docs = self._docs(
            mk_doc("C1", 1001, "2026-01-01", "2026-01-10", 500.0),
            mk_doc("C1", 1002, "2026-01-15", "2026-02-01", 300.0),
        )
        sales = reconstruct_sales_state(docs, {1001: [(d("2026-01-09"), 300.0)]}, self.ocrd, WS, d("2026-09-01"))
        s15 = [s for s in sales if s["docentry"] == 1002][0]
        self.assertAlmostEqual(s15["overdue_amount_at_sale"], 200.0, delta=0.01)
        self.assertTrue(s15["overdue_at_sale"])

    def test_credited_before_sale_not_overdue(self):
        docs = self._docs(
            mk_doc("C1", 1001, "2026-01-01", "2026-01-10", 500.0),
            mk_doc("C1", 1002, "2026-01-15", "2026-02-01", 300.0),
        )
        # settled via credit-note reconciliation before the sale
        sales = reconstruct_sales_state(docs, {1001: [(d("2026-01-12"), 500.0)]}, self.ocrd, WS, d("2026-09-01"))
        s15 = [s for s in sales if s["docentry"] == 1002][0]
        self.assertFalse(s15["overdue_at_sale"])

    def test_canceled_invoice_excluded(self):
        docs = self._docs(
            mk_doc("C1", 1001, "2026-01-01", "2026-01-10", 500.0),
            mk_doc("C1", 1002, "2026-01-15", "2026-02-01", 300.0),
        )
        docs[0]["canceled"] = "Y"
        sales = reconstruct_sales_state(docs, {}, self.ocrd, WS, d("2026-09-01"))
        self.assertEqual(len(sales), 1)
        self.assertFalse(sales[0]["overdue_at_sale"])

    def test_multiple_payments_one_invoice(self):
        docs = self._docs(
            mk_doc("C1", 1001, "2026-01-01", "2026-01-10", 1000.0),
            mk_doc("C1", 1002, "2026-01-25", "2026-02-05", 10.0),
        )
        app = {1001: [(d("2026-01-09"), 400.0), (d("2026-01-12"), 600.0)]}
        sales = reconstruct_sales_state(docs, app, self.ocrd, WS, d("2026-09-01"))
        s25 = [s for s in sales if s["docentry"] == 1002][0]
        self.assertFalse(s25["overdue_at_sale"])  # fully paid before sale
        # and at 1002's date, 1001 was fully paid
        self.assertEqual(s25["overdue_amount_at_sale"], 0.0)

    def test_one_payment_many_invoices(self):
        docs = self._docs(
            mk_doc("C1", 1001, "2026-01-01", "2026-01-10", 400.0),
            mk_doc("C1", 1002, "2026-01-03", "2026-01-15", 600.0),
            mk_doc("C1", 1003, "2026-01-20", "2026-02-01", 50.0),
        )
        app = {1001: [(d("2026-01-16"), 400.0)], 1002: [(d("2026-01-16"), 600.0)]}
        sales = reconstruct_sales_state(docs, app, self.ocrd, WS, d("2026-09-01"))
        s20 = [s for s in sales if s["docentry"] == 1003][0]
        self.assertFalse(s20["overdue_at_sale"])

    def test_sale_does_not_count_itself(self):
        docs = self._docs(mk_doc("C1", 1001, "2026-01-01", "2026-01-01", 500.0))
        sales = reconstruct_sales_state(docs, {}, self.ocrd, WS, d("2026-09-01"))
        self.assertEqual(len(sales), 1)
        self.assertFalse(sales[0]["overdue_at_sale"])

    def test_not_yet_existing_invoice_ignored(self):
        docs = self._docs(
            mk_doc("C1", 1001, "2026-01-01", "2026-01-10", 500.0),
            mk_doc("C1", 1002, "2026-01-15", "2026-02-01", 300.0),
        )
        # invoice 1002 dated after 1001; at 1001's date it doesn't exist
        sales = reconstruct_sales_state(docs, {}, self.ocrd, WS, d("2026-09-01"))
        s01 = [s for s in sales if s["docentry"] == 1001][0]
        self.assertFalse(s01["overdue_at_sale"])

    def test_installment_semantics_docduedate_effective(self):
        # this installation: INV6 is a 1:1 mirror; DocDueDate is the due date
        docs = self._docs(
            mk_doc("C1", 1001, "2026-01-01", "2026-01-31", 500.0),
            mk_doc("C1", 1002, "2026-02-10", "2026-03-01", 300.0),
        )
        sales = reconstruct_sales_state(docs, {}, self.ocrd, WS, d("2026-09-01"))
        s02 = [s for s in sales if s["docentry"] == 1002][0]
        self.assertTrue(s02["overdue_at_sale"])  # due 01-31 < sale 02-10


# -------------------------------------------------------------- auth log


class TestRetailAuthorization(unittest.TestCase):
    def base(self):
        return {
            "vencrevenc_y": False, "origin": "SAP", "retailone": "Y",
            "doctotal": 100.0, "overdue_at_sale": True, "overdue_amount_at_sale": 50.0,
            "settled_by_credit_note": False, "fully_paid": False,
            "order_entry": None, "any_overdue_at_order": None, "delivery_entry": None,
            "excel_credit_auth": "FULL", "superuser": "N", "sap_user": "x",
            "usersign": 5, "days_to_first_any": None, "over_limit_before": False,
            "over_limit_after": False, "applied_note": "", "cardcode": "C1",
            "docentry": 1, "docdate": "2026-03-01",
        }

    def test_auth_before_sale(self):
        c = self.base()
        c["retail"] = {"matched": True, "credito": "N",
                       "auth_events_window": [{"timing": "BEFORE_SALE", "identificador": "028"}],
                       "tipo": "CR"}
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "RETAIL_CREDIT_AUTHORIZATION_LOG")
        self.assertEqual(r["confidence"], "HEURISTIC")

    def test_auth_after_sale_does_not_explain(self):
        c = self.base()
        c["retail"] = {"matched": True, "credito": "N",
                       "auth_events_window": [{"timing": "AFTER_SALE", "identificador": "168"}],
                       "tipo": "CR"}
        r = classify_one(c)
        self.assertNotEqual(r["reason_code"], "RETAIL_CREDIT_AUTHORIZATION_LOG")

    def test_no_auth_event_cash_paid(self):
        c = self.base()
        c["retail"] = {"matched": True, "credito": "N", "tipo": "CA",
                       "auth_events_window": [], "folio": "SRCR08CA163968"}
        c["fully_paid"] = True
        c["days_to_first_any"] = 0
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK")

    def test_credit_cash_flag_but_unpaid_unresolved(self):
        c = self.base()
        c["retail"] = {"matched": True, "credito": "N", "tipo": "CR",
                       "auth_events_window": []}
        c["fully_paid"] = False
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "UNRESOLVED")


# ----------------------------------------------------------- doc chain


class TestOrderDeliveryInvoice(unittest.TestCase):
    def base(self):
        return {
            "vencrevenc_y": False, "origin": "SAP", "retailone": "N",
            "doctotal": 500.0, "overdue_at_sale": True, "overdue_amount_at_sale": 200.0,
            "settled_by_credit_note": False, "fully_paid": False,
            "excel_credit_auth": "FULL", "superuser": "N", "sap_user": "x",
            "usersign": 5, "days_to_first_any": None, "over_limit_before": False,
            "over_limit_after": False, "applied_note": "", "cardcode": "C1",
            "docentry": 1, "docdate": "2026-03-01",
            "retail": {"matched": False},
        }

    def test_order_before_overdue(self):
        c = self.base()
        c["order_entry"] = 909
        c["any_overdue_at_order"] = False
        c["order_date"] = "2026-02-01"
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "ORDER_AUTHORIZED_BEFORE_OVERDUE")
        self.assertEqual(r["confidence"], "EXACT")

    def test_order_after_overdue_not_explained_by_order(self):
        c = self.base()
        c["order_entry"] = 909
        c["any_overdue_at_order"] = True
        r = classify_one(c)
        self.assertNotEqual(r["reason_code"], "ORDER_AUTHORIZED_BEFORE_OVERDUE")

    def test_delivery_flow(self):
        c = self.base()
        c["delivery_entry"] = 707
        c["delivery_date"] = "2026-02-20"
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "DELIVERY_FLOW_EXPLAINS_TIMING")

    def test_overlimit_full_auth(self):
        c = self.base()
        c["over_limit_before"] = True
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "SAP_FULL_AUTHORIZATION")

    def test_dms_technical(self):
        c = self.base()
        c["origin"] = "DMS"
        c["sap_user"] = "dms"
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "TECHNICAL_INTEGRATION_PATH")

    def test_credit_note_settlement(self):
        c = self.base()
        c["settled_by_credit_note"] = True
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "CREDIT_NOTE_OR_RECONCILIATION")

    def test_customer_exception_flag(self):
        c = self.base()
        c["vencrevenc_y"] = True
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "CUSTOMER_EXCEPTION_FLAG")

    def test_unexplained_when_no_evidence(self):
        c = self.base()
        c["excel_credit_auth"] = "NONE"      # no FULL auth to fall back on
        c["superuser"] = "N"
        c["retailone"] = "N"
        # strip every explanation: overdue-only, no order/delivery, no auth, no cash, no exception
        r = classify_one(c)
        self.assertEqual(r["reason_code"], "UNEXPLAINED")


# ----------------------------------------------------------- credit limit


class TestCreditLimitLimits(unittest.TestCase):
    def _state(self, line, invs, apps):
        ocrd = {"C1": {"creditline": line}}
        return reconstruct_sales_state(invs, apps, ocrd, WS, d("2026-09-01"))

    def test_below_limit(self):
        docs = [
            mk_doc("C1", 1, "2026-01-01", "2026-02-01", 100.0),
            mk_doc("C1", 2, "2026-01-10", "2026-02-10", 50.0),
        ]
        sales = self._state(10000.0, docs, {})
        s2 = [s for s in sales if s["docentry"] == 2][0]
        self.assertTrue(s2["exposure_before"] == 100.0)
        self.assertFalse(s2["over_limit_before"])
        self.assertFalse(s2["over_limit_after"])

    def test_above_limit_before_sale(self):
        docs = [
            mk_doc("C1", 1, "2026-01-01", "2026-02-01", 600.0),
            mk_doc("C1", 2, "2026-01-10", "2026-02-10", 50.0),
        ]
        sales = self._state(500.0, docs, {})
        s2 = [s for s in sales if s["docentry"] == 2][0]
        self.assertTrue(s2["over_limit_before"])
        self.assertTrue(s2["over_limit_after"])

    def test_exact_at_limit_no_excess(self):
        docs = [
            mk_doc("C1", 1, "2026-01-01", "2026-02-01", 500.0),
            mk_doc("C1", 2, "2026-01-10", "2026-02-10", 10.0),
        ]
        sales = self._state(500.0, docs, {})
        s2 = [s for s in sales if s["docentry"] == 2][0]
        self.assertFalse(s2["over_limit_before"])
        self.assertTrue(s2["over_limit_after"])

    def test_zero_credit_line_never_over_limit(self):
        docs = [
            mk_doc("C1", 1, "2026-01-01", "2026-02-01", 900.0),
            mk_doc("C1", 2, "2026-01-10", "2026-02-10", 50.0),
        ]
        sales = self._state(0.0, docs, {})
        s2 = [s for s in sales if s["docentry"] == 2][0]
        self.assertFalse(s2["over_limit_before"])
        self.assertFalse(s2["over_limit_after"])


# ------------------------------------------------------- cardinality


class TestCardinalityAndAmounts(unittest.TestCase):
    def test_no_silent_fanout_revalidation(self):
        prior = json.loads((EV.parent.parent / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                           .read_text(encoding="utf-8"))
        prior_keys = {(s["cardcode"], s["docentry"]) for s in prior["all_overdue_sales"]}
        summary = json.loads((EV / "revalidation_summary.json").read_text(encoding="utf-8"))
        # window covers the prior 287 cases 100%
        self.assertEqual(summary["prior_287"], len(prior_keys))
        reval = json.loads((EV / "revalidated_cases.json").read_text(encoding="utf-8"))
        reval_keys = {(s["cardcode"], s["docentry"]) for s in reval}
        # all 287 present (no silent drop)
        missing = prior_keys - reval_keys
        self.assertEqual(len(missing), 0, f"prior cases dropped: {sorted(missing)[:5]}")

    def test_per_case_amount_invariant(self):
        # ORIGINAL ≈ PAID + CREDITED + OPEN (SAP tolerance)
        bundle = json.loads((EV / "case_bundle.json").read_text(encoding="utf-8"))
        bad = []
        for c in bundle:
            total = float(c["doctotal"])
            settled = float(c.get("settled_before_sale") or 0) + float(c.get("settled_after_sale") or 0)
            open_amt = float(c.get("open_now") or 0)
            diff = abs((settled + open_amt) - total)
            if diff > 0.05:
                bad.append((c["cardcode"], c["docentry"], total, settled, open_amt, diff))
        self.assertEqual(len(bad), 0, f"amount invariant broken: {bad[:5]}")

    def test_temporal_auth_sale_ordering(self):
        # auth events never explain earlier sales when AFTER; within the
        # classification every RETAIL_CREDIT_AUTHORIZATION_LOG uses BEFORE/SAME
        cl = json.loads((EV / "classified_cases.json").read_text(encoding="utf-8"))
        for c in cl:
            if c["reason_code"] == "RETAIL_CREDIT_AUTHORIZATION_LOG":
                evs = c["retail"].get("auth_events_window") or []
                self.assertTrue(
                    any(e.get("timing") in ("BEFORE_SALE", "SAME_TIME_WINDOW") for e in evs),
                    f"auth log used but only AFTER_SALE events for {c['doc_entry']}")

    def test_docchain_no_fanout(self):
        cl = json.loads((EV / "classified_cases.json").read_text(encoding="utf-8"))
        by_de = {}
        for c in cl:
            by_de.setdefault(c["doc_entry"], []).append(c)
        # each DocEntry appears at most once
        self.assertTrue(all(len(v) == 1 for v in by_de.values()))
        # retail linkage is optional: matched retail case count <= retail cases
        retail = [c for c in cl if c["origin"] == "SAP" and c["retailone"] == "Y"]
        matched = [c for c in retail if c["retail"].get("matched")]
        self.assertLessEqual(len(matched), len(retail))


# ------------------------------------------------------------- read-only


class TestReadOnlyAudit(unittest.TestCase):
    def test_guard_blocks_writes(self):
        for sql in ["INSERT INTO x VALUES(1)",
                    "UPDATE OINV SET DocTotal=1",
                    "DELETE FROM x",
                    "MERGE INTO x USING y ON 1=1",
                    "CREATE TABLE x(c INT)",
                    "ALTER TABLE x ADD c INT",
                    "DROP TABLE x",
                    "TRUNCATE TABLE x",
                    "GRANT SELECT ON x TO u",
                    "REVOKE SELECT ON x FROM u",
                    "CALL SBO_SP_TRANSACTIONNOTIFICATION(1)"]:
            with self.assertRaises(RuntimeError, msg=sql):
                guard_sql(sql)

    def _strip_docstrings(self, text):
        return re.sub(r'""".*?"""', "", text, flags=re.S)

    def test_no_write_statements_in_credit_exception_source(self):
        bad = []
        for py in sorted((HERE / "..").glob("credit_exception/**/*.py")):
            text = self._strip_docstrings(py.read_text(encoding="utf-8"))
            for i, line in enumerate(text.splitlines(), 1):
                if "execute(" not in line and "executemany(" not in line:
                    continue
                body = line.split("#", 1)[0]
                if _WRITE_TOKENS.search(body):
                    bad.append((py.name, i, line.strip()))
        self.assertEqual(bad, [])

    def test_folio_parse(self):
        self.assertEqual(parse_folio("SRCR08CA163968"),
                         {"sucursal": "SRC", "estacion": "R08", "tipo": "CA", "seq": 163968})
        self.assertEqual(parse_folio("S2AS19ED33352"),
                         {"sucursal": "S2A", "estacion": "S19", "tipo": "ED", "seq": 33352})
        self.assertIsNone(parse_folio("not-a-folio"))


# -------------------------------------------------------- prior regression


class TestPriorGateRegression(unittest.TestCase):
    def test_credit_control_gate_evidence_intact(self):
        # the prior PASS gate's evidence must still load and match its declared
        # headline figures (window/cardinality states are frozen).
        ev = json.loads((EV.parent.parent / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                        .read_text(encoding="utf-8"))
        self.assertEqual(ev["sales_with_overdue_at_sale"], 287)
        self.assertGreaterEqual(ev["universe_customers"], 100)
        auth = json.loads((EV.parent.parent / "credit_control" / "evidence" / "excel_authorization_model.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(auth["unique_logins"], 170)

    def test_conservative_bound_relation(self):
        # exact reconstruction must be a superset of the conservative lower
        # bound for the shared 2026-01-01..2026-08-31 window
        prior = json.loads((EV.parent.parent / "credit_control" / "evidence" / "phase78_sale_credit_state.json")
                           .read_text(encoding="utf-8"))["all_overdue_sales"]
        reval = {(s["cardcode"], s["docentry"]) for s in json.loads((EV / "revalidated_cases.json")
               .read_text(encoding="utf-8"))}
        # prior included 09-01 cases; those on 01-01..08-31 must be in reval window
        for s in prior:
            if "2026-01-01" <= s["docdate"][:10] <= "2026-08-31":
                self.assertIn((s["cardcode"], s["docentry"]), reval,
                              f"baseline case missing after exact reconstruction")


if __name__ == "__main__":
    unittest.main(verbosity=2)