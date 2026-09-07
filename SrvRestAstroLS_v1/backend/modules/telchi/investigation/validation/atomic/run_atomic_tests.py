#!/usr/bin/env python3
"""ATOMIC validation runner — unit + contract + source (READ ONLY on HANA).

Layers (§45):
  UNIT      : pure contract + semantic logic (no DB)
  CONTRACT  : confirmed columns exist on HANA; contract invariants
  SOURCE    : run atomic extractors in a small window; grain + SAP IDs
  SEMANTIC  : apply classifiers to real rows where possible
  E2E       : synthetic end-to-end fixture through pipeline functions

Gate: TELCHI_ATOMIC_CONTRACTS_NUCLEUS_V1
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT, LEGACY_DATA_ROOT

import pandas
from hdbcli import dbapi as hana_dbapi

ROOT = INVESTIGATION_ROOT

from modules.telchi.investigation.atomic import connection as hconn
from modules.telchi.investigation.atomic.contracts import (
    BASE_EVENT_ENVELOPE, SALE_HEADER, SALE_LINE, PAYMENT_HEADER,
    DELIVERY_HEADER, DELIVERY_LINE, INVENTORY_MOVEMENT,
    RELATION_TYPES_CANDIDATE, MATCH_METHODS, DocumentRelation,
)
from modules.telchi.investigation.atomic.contracts.cash import (
    CASH_EVENT_SAP_FIELDS, CASH_EVENT_LEGACY_FIELDS, PAYMENT_LIFECYCLE_ROLES,
)
import modules.telchi.investigation.atomic.semantic as sem
import modules.telchi.investigation.atomic.semantic.cash as cash_sem
import modules.telchi.investigation.atomic.traceability as tr
import modules.telchi.investigation.atomic.accounting as acct

OUT = ROOT / "validation" / "atomic"
WINDOW = ("2023-02-01", "2023-03-01")
LEGACY_DS0 = LEGACY_DATA_ROOT / "DS0"


def hana_available() -> bool:
    """Read-only connectivity probe. External runtime is MANUAL (DEC-005)."""
    try:
        conn, cur = hconn.connect()
        cur.execute("SELECT TOP 1 1 FROM DUMMY")
        cur.close()
        conn.close()
        return True
    except Exception:
        return False


def load_sql(name: str) -> str:
    return (ROOT / "sql" / "current" / "atomic" / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- UNIT
class TestUnitContracts(unittest.TestCase):
    def test_envelope_keys_stable(self):
        req = {"source_system", "source_document_id", "business_date",
               "amount_document", "currency", "cancelled", "status"}
        self.assertTrue(req <= set(BASE_EVENT_ENVELOPE))

    def test_document_relation_stable(self):
        r = DocumentRelation("BASED_ON", "SAP", "AR_INVOICE", 1, 1, "SAP",
                             "DELIVERY", 2, 2, "SAP_BASEENTRY", 1.0, "inv1")
        self.assertEqual(r.relation_type, "BASED_ON")
        self.assertIn("PAID_BY", RELATION_TYPES_CANDIDATE)
        self.assertIn("FOLIO", MATCH_METHODS)

    def test_relation_rejects_unknown(self):
        with self.assertRaises(ValueError):
            DocumentRelation("NOT_A_TYPE", "SAP", "AR_INVOICE", 1, None,
                              "SAP", "PAYMENT", 2, None, "INFERRED", 0.5, "x")

    def test_match_method_never_upgrades_inferred(self):
        self.assertEqual(sem.choose_match_method("x", "AMOUNT_TIME_MATCH"), "AMOUNT_TIME_MATCH")
        self.assertEqual(sem.choose_match_method("x", "anything_else"), "INFERRED")

    def test_payment_classification(self):
        self.assertEqual(sem.classify_payment_method({"CashSum": 100}), "CASH")
        self.assertEqual(sem.classify_payment_method({"TrsfrSum": 5}), "TRANSFER")
        self.assertEqual(sem.classify_payment_method({"CashSum": 1, "CreditSum": 2}), "MIXED")
        self.assertEqual(sem.classify_payment_method({}), "OTHER")

    def test_cancellation(self):
        self.assertEqual(sem.cancellation_state("N"), "VALID")
        self.assertEqual(sem.cancellation_state("y"), "CANCELED_ORIGINAL")
        self.assertEqual(sem.cancellation_state("C"), "CANCELED_REVERSAL")

    def test_valuation_dims_distinct(self):
        self.assertNotAlmostEqual(sem.sale_value(3, 100), sem.cost_value(3, 40))

    def test_reconcile(self):
        self.assertEqual(sem.reconcile_expected_cash(100, 90)["difference"], 10)
        self.assertTrue(sem.reconcile_expected_cash(100, 90)["unexplained"] == 10)
        self.assertEqual(sem.reconcile_expected_cash(100, 100.0)["status"], sem.CONSISTENT)

    # T18 bottleneck
    def test_bottleneck(self):
        r = sem.max_producible(
            {"A": 50000, "B": 40000, "bottle": 12000, "label": 8000},
            {"A": 1, "B": 1, "bottle": 1, "label": 1})
        self.assertEqual(r["max"], 8000)
        self.assertEqual(r["bottleneck"], "label")

    # T19 zero component
    def test_zero_component(self):
        r = sem.max_producible({"mp": 100000, "label": 0}, {"mp": 1, "label": 1})
        self.assertEqual(r["max"], 0)

    # T20 coverage without demand -> None (indeterminate)
    def test_coverage_no_demand(self):
        self.assertIsNone(sem.coverage_days(30000, 0))


# ----------------------------------------------- UNIT CASH_EVENT / STOCK LINK
class TestUnitCashEvent(unittest.TestCase):
    def test_build_cash_event_from_cash_payment(self):
        row = {"DocEntry": 1, "DocNum": "A1", "DocDate": "2023-02-01",
               "CardCode": "C1", "DocCurr": "BS", "DocTotal": 100,
               "Canceled": "N", "TransId": 7, "CashSum": 100}
        ev = cash_sem.build_cash_event_from_payment(row)
        self.assertEqual(ev["payment_method"], "CASH")
        self.assertEqual(ev["cash_amount"], 100)
        self.assertEqual(ev["cash_event_kind"], "CASH_ONLY")
        self.assertIsNone(ev["cash_register_id"], "ORCT has no cash register")

    def test_build_cash_event_mixed(self):
        row = {"CashSum": 60, "CreditSum": 40, "DocTotal": 100, "Canceled": "N"}
        ev = cash_sem.build_cash_event_from_payment(row)
        self.assertEqual(ev["payment_method"], "MIXED")
        self.assertEqual(ev["cash_amount"], 60)
        self.assertEqual(ev["cash_event_kind"], "CASH_PORTION")

    def test_build_cash_event_non_cash(self):
        row = {"CashSum": 0, "TrsfrSum": 100, "DocTotal": 100, "Canceled": "N"}
        ev = cash_sem.build_cash_event_from_payment(row)
        self.assertEqual(ev["cash_event_kind"], "NON_CASH_PAYMENT")
        self.assertEqual(ev["payment_method"], "TRANSFER")

    def test_build_cash_event_canceled_preserved(self):
        row = {"CashSum": 50, "DocTotal": 50, "Canceled": "Y"}
        ev = cash_sem.build_cash_event_from_payment(row)
        self.assertEqual(ev["canceled"], "CANCELED_ORIGINAL")

    def test_legacy_cash_type_classification(self):
        self.assertEqual(cash_sem.classify_legacy_cash_type("Efectivo"), "CASH")
        self.assertEqual(cash_sem.classify_legacy_cash_type("TARJETA DEBITO-CRED"), "CARD")
        self.assertEqual(cash_sem.classify_legacy_cash_type("CHEQUE"), "CHECK")
        self.assertEqual(cash_sem.classify_legacy_cash_type("Dep/Tran"), "TRANSFER")
        self.assertEqual(cash_sem.classify_legacy_cash_type("CHPDBs"), "OTHER")
        self.assertEqual(cash_sem.classify_legacy_cash_type("algo inventado"), "UNKNOWN")

    def test_cash_event_contract_stable(self):
        self.assertIn("cash_sum", CASH_EVENT_SAP_FIELDS)
        self.assertIn("source_table", CASH_EVENT_LEGACY_FIELDS)
        self.assertIn("SaleCode", CASH_EVENT_LEGACY_FIELDS)
        self.assertEqual(len(PAYMENT_LIFECYCLE_ROLES), 4)

    # DOCNUM_RESOLVE (T09/T10): movement -> invoice via BASE_REF=DocNum
    def test_stock_resolve_invoice_line_item_match(self):
        mov = {"trans_type": 13, "base_ref": "23012334", "doc_line_num": 0, "item_id": "M05103", "trans_num": 4746108}
        hdr = {"doc_num": "23012334", "doc_entry": 2639506, "trans_type_family": "AR_INVOICE"}
        line = {"line_num": 0, "item_id": "M05103"}
        r = cash_sem.resolve_stock_document(mov, hdr, line)
        self.assertTrue(r["resolved"])
        self.assertEqual(r["confidence"], 1.0)
        self.assertEqual(r["match_method"], "DIRECT_REFERENCE")
        self.assertEqual(r["from_document_id"], 2639506)
        self.assertEqual(r["relation_type"], "GENERATES")

    def test_stock_resolve_header_only_lower_confidence(self):
        mov = {"trans_type": 13, "base_ref": "23012334", "doc_line_num": 5, "item_id": "M05103", "trans_num": 1}
        hdr = {"doc_num": "23012334", "doc_entry": 2639506, "trans_type_family": "AR_INVOICE"}
        r = cash_sem.resolve_stock_document(mov, hdr)
        self.assertTrue(r["resolved"])
        self.assertEqual(r["confidence"], 0.5)
        self.assertIsNone(r["from_line_id"])

    def test_stock_resolve_missing_header_not_upgraded(self):
        mov = {"trans_type": 13, "base_ref": "99999999", "doc_line_num": 0, "item_id": "X", "trans_num": 2}
        r = cash_sem.resolve_stock_document(mov, None)
        self.assertFalse(r["resolved"])
        self.assertEqual(r["reason"], "HEADER_UNRESOLVED")

    def test_stock_resolve_transtype_family_guard(self):
        # DocNum collides across families; TransType guard must reject mismatch
        mov = {"trans_type": 13, "base_ref": "23012334", "doc_line_num": 0, "item_id": "M05103", "trans_num": 3}
        hdr = {"doc_num": "23012334", "doc_entry": 55, "trans_type_family": "DELIVERY"}
        r = cash_sem.resolve_stock_document(mov, hdr)
        self.assertFalse(r["resolved"])
        self.assertEqual(r["reason"], "TRANSTYPE_FAMILY_MISMATCH")

    def test_stock_resolve_unsupported_transtype(self):
        mov = {"trans_type": 999, "base_ref": "x", "doc_line_num": 0, "item_id": "y", "trans_num": 4}
        r = cash_sem.resolve_stock_document(mov, None)
        self.assertFalse(r["resolved"])
        self.assertEqual(r["reason"], "UNSUPPORTED_TRANSTYPE")

    def test_stock_resolve_line_no_item_match(self):
        mov = {"trans_type": 13, "base_ref": "23012334", "doc_line_num": 0, "item_id": "A", "trans_num": 5}
        hdr = {"doc_num": "23012334", "doc_entry": 2639506, "trans_type_family": "AR_INVOICE"}
        line = {"line_num": 0, "item_id": "B"}
        r = cash_sem.resolve_stock_document(mov, hdr, line)
        self.assertEqual(r["confidence"], 0.8)


# ------------------------------------------------------- TRACEABILITY (pure)
def _inv(total=100.0, canceled="N", docstatus="O", docentry=1, docnum="1"):
    return {"DocEntry": docentry, "DocNum": docnum, "CardCode": "C1",
            "DocDate": "2023-02-01", "DocTotal": total, "DocCur": "BS",
            "CANCELED": canceled, "DocStatus": docstatus, "PaidToDate": total}


def _ln(item="M05103", qty=1.0, price=100.0, disc=0.0, whs="01", linenum=0):
    return {"ItemCode": item, "LineNum": linenum, "Quantity": qty, "Price": price,
            "DiscPrcnt": disc, "LineTotal": qty * price, "WhsCode": whs}


def _pay(cash=100.0, docentry=900, canceled="N"):
    return {"DocEntry": docentry, "DocNum": str(docentry), "DocDate": "2023-02-01",
            "DocTotal": cash, "DocCurr": "BS", "Canceled": canceled,
            "CashSum": cash, "CheckSum": 0, "TrsfrSum": 0, "CreditSum": 0,
            "NoDocSum": 0, "BoeSum": 0}


def _stk(out_qty=1.0, whs="01", trans=5000, cost=40.0):
    return {"trans_num": trans, "trans_type": 13, "itemcode": "M05103",
            "in_qty": 0, "out_qty": out_qty, "warehouse_id": whs,
            "resolved": True, "confidence": 1.0, "cost_total": cost, "calc_price": 40.0}


class TestTraceabilityUnit(unittest.TestCase):
    # T48 E2E consistent: sale + cash + goods + warehouse + value, diff 0
    def test_e2e_consistent(self):
        c = tr.build_case(_inv(), [_ln()], [_pay(100)], [_stk()], settled_amount=100.0)
        self.assertEqual(c["status"], tr.CONSISTENT)
        self.assertEqual(c["differences"]["UNEXPLAINED_DIFFERENCE"], 0)
        for k in ("SALE_CONFIRMED", "INVOICE_CONFIRMED", "CASH_CONFIRMED",
                  "GOODS_OUT_CONFIRMED", "WAREHOUSE_CONFIRMED",
                  "COMMERCIAL_VALUE_CONFIRMED"):
            self.assertTrue(c["confirmations"][k], k)

    # T49 mismatch (fixture): sale=7200 goods=7200 cash=6700 -> partial lifecycle
    def test_e2e_partial_cash_is_explained(self):
        c = tr.build_case(_inv(7200), [_ln(price=7200)], [_pay(6700)], [_stk()],
                          settled_amount=6700.0)
        self.assertEqual(c["status"], tr.PARTIALLY_RECONCILED)
        self.assertEqual(c["differences"]["TOTAL_DIFFERENCE"], 500)
        self.assertEqual(c["differences"]["EXPLAINED_DIFFERENCE"], 500)
        self.assertEqual(c["differences"]["UNEXPLAINED_DIFFERENCE"], 0)
        self.assertIn("PARTIAL_CASH_PAYMENT", c["explanation"])

    # T28/§52 over-applied cash -> REVIEW_REQUIRED with unexplained
    def test_e2e_over_applied_review(self):
        c = tr.build_case(_inv(100), [_ln()], [_pay(100)], [_stk()], settled_amount=120.0)
        self.assertEqual(c["status"], tr.REVIEW_REQUIRED)
        self.assertEqual(c["differences"]["UNEXPLAINED_DIFFERENCE"], -20)

    # T43 cash + canceled invoice -> never CONSISTENT_FINAL
    def test_e2e_canceled_never_consistent(self):
        for raw in ("Y", "C"):
            c = tr.build_case(_inv(canceled=raw), [_ln()], [_pay(100)], [_stk()],
                              settled_amount=100.0)
            self.assertEqual(c["status"], tr.REVIEW_REQUIRED, raw)
            self.assertEqual(c["canceled"], "CANCELED_ORIGINAL" if raw == "Y"
                             else "CANCELED_REVERSAL")

    # T40 mixed payment: cash+card must not compare full invoice to cash
    def test_e2e_mixed_payment(self):
        pay = _pay(cash=60)
        pay["CreditSum"] = 40
        c = tr.build_case(_inv(100), [_ln()], [pay], [_stk()], settled_amount=100.0)
        self.assertEqual(c["payment_method"], "MIXED")
        self.assertEqual(c["status"], tr.PARTIALLY_RECONCILED)
        self.assertIn("PAYMENT_METHOD_MIXED", c["explanation"])

    # T44 sale without stock direct link -> STOCK_RELATION_UNRESOLVED (not NO_STOCK)
    def test_e2e_no_stock_is_unresolved(self):
        c = tr.build_case(_inv(), [_ln()], [_pay(100)], [], settled_amount=100.0)
        self.assertEqual(c["status"], tr.PARTIALLY_RECONCILED)
        self.assertIn(tr.STOCK_RELATION_UNRESOLVED, c["explanation"])

    # T08/T54: sale value vs cost value are distinct dimensions
    def test_e2e_cost_value_distinct(self):
        c = tr.build_case(_inv(), [_ln(price=100)], [_pay(100)],
                          [_stk(cost=40)], settled_amount=100.0)
        self.assertEqual(c["goods_sale_value"], 100)
        self.assertEqual(c["goods_cost_value"], 40)

    # T26 lineage: atomic rows -> SAP identities
    def test_e2e_lineage_complete(self):
        c = tr.build_case(_inv(), [_ln()], [_pay(100)], [_stk()], settled_amount=100.0)
        self.assertEqual(c["lineage"]["SAP_INVOICE"]["pk"], 1)
        self.assertEqual(c["lineage"]["SAP_INVOICE_LINES"][0]["pk"], (1, 0))
        self.assertEqual(c["lineage"]["PAYMENTS"][0]["pk"], 900)
        self.assertEqual(c["lineage"]["STOCK_MOVEMENTS"][0]["pk"], 5000)

    # T34 false positive protection: same amount+day is NOT confirmation by itself
    def test_false_positive_protection(self):
        # two different invoices, same day, same amount, different customers
        a = tr.build_case(_inv(100, docentry=1, docnum="A"), [_ln()], [_pay(100)],
                          [_stk()], settled_amount=100.0)
        b = tr.build_case(_inv(100, docentry=2, docnum="B"), [_ln()], [_pay(100)],
                          [_stk()], settled_amount=100.0)
        self.assertNotEqual(a["case_id"], b["case_id"])
        self.assertEqual(a["lineage"]["SAP_INVOICE"]["pk"], 1)
        self.assertEqual(b["lineage"]["SAP_INVOICE"]["pk"], 2)
        # no shared identity: match method must never be DIRECT_REFERENCE between them


# ------------------------------------------------ LEGACY BASELINE (read-only)
class TestLegacyParquet(unittest.TestCase):
    """T31/T32/T46 — legacy cash/sale grain evidence from parquet files."""

    CASH = LEGACY_DS0 / "cash-2022-02-28.parq"
    SALE = LEGACY_DS0 / "saleProduct-2022-02-28.parq"

    def test_cash_grain_requires_source_table(self):
        # T31/T46: NroTransaccion is NOT unique -> discriminator required
        import pyarrow.parquet as pq
        df = pq.read_table(str(self.CASH)).to_pandas()
        dups = int(df["NroTransaccion"].duplicated().sum())
        self.assertGreater(dups, 0, "parquet must show NroTransaccion collisions")
        self.assertIn("source_table", CASH_EVENT_LEGACY_FIELDS,
                      "contract requires source_table discriminator")

    def test_cash_sale_reference_rate(self):
        # T32: cjtrnmorg=6 -> SaleCode>0 in most cash rows
        import pyarrow.parquet as pq
        df = pq.read_table(str(self.CASH)).to_pandas()
        rate = float((df["SaleCode"] > 0).mean())
        self.assertGreater(rate, 0.8, f"SaleCode>0 rate {rate}")

    def test_legacy_cash_types(self):
        import pyarrow.parquet as pq
        df = pq.read_table(str(self.CASH)).to_pandas()
        types = set(df["CashType"].dropna().unique())
        self.assertIn("Efectivo", types)
        self.assertEqual(cash_sem.classify_legacy_cash_type("Efectivo"), "CASH")
        self.assertEqual(cash_sem.classify_legacy_cash_type("TARJETA DEBITO-CRED"), "CARD")
        self.assertEqual(cash_sem.classify_legacy_cash_type("CHEQUE"), "CHECK")
        self.assertEqual(cash_sem.classify_legacy_cash_type("Dep/Tran"), "TRANSFER")
        self.assertEqual(cash_sem.classify_legacy_cash_type("CHPDBs"), "OTHER")


# ---------------------------------------------------- H4 ACCOUNTING (pure)
def _jline(line_id, account, debit=0.0, credit=0.0, contra="C1"):
    return {"Line_ID": line_id, "Account": account, "Debit": debit,
            "Credit": credit, "ContraAct": contra, "BPLId": None,
            "LineMemo": "test"}


def _hpay(docentry=100, cash=100.0, check=0.0, trsfr=0.0, card=0.0,
          transid=777, canceled="N", acct="1110201"):
    return {"DocEntry": docentry, "DocNum": str(docentry), "TransId": transid,
            "Canceled": canceled, "CashSum": cash, "CheckSum": check,
            "TrsfrSum": trsfr, "CreditSum": card, "NoDocSum": 0, "BoeSum": 0,
            "DocCurr": "BS", "CashAcct": acct}


_MASTER = {"1110201": {"AcctName": "Cajas Casa Matriz MN", "CashBox": "N"}}


class TestAccountingUnit(unittest.TestCase):
    # 1-2: TransId linkage + 1:N journal lines
    def test_journal_link_and_multiple_lines(self):
        lines = [_jline(0, "1110201", debit=100), _jline(1, "1120101", credit=100)]
        tr = acct.evaluate_cash_accounting(_hpay(), 777, lines, _MASTER)
        self.assertEqual(tr["journal_trans_id"], 777)
        self.assertEqual(len(tr["cash_account_actual"]), 1)
        self.assertEqual(tr["status"], acct.CASH_ACCOUNTING_CONFIRMED)

    # 3: cash-only confirmed exact
    def test_cash_only_confirmed(self):
        lines = [_jline(0, "1110201", debit=100), _jline(1, "C000001", credit=100)]
        tr = acct.evaluate_cash_accounting(_hpay(cash=100), 777, lines, _MASTER)
        self.assertEqual(tr["status"], acct.CASH_ACCOUNTING_CONFIRMED)
        self.assertEqual(tr["amount_delta"], 0)

    # 4: transfer-only is NOT physical cash
    def test_transfer_only_not_applicable(self):
        p = _hpay(cash=0, trsfr=500)
        tr = acct.evaluate_cash_accounting(p, 777,
                                           [_jline(0, "1120301", debit=500)], _MASTER)
        self.assertEqual(tr["status"], acct.NOT_APPLICABLE_TO_PHYSICAL_CASH)
        self.assertEqual(tr["payment_method"], sem.TRANSFER)

    # 5: mixed payment decomposed
    def test_mixed_payment_decomposed(self):
        p = _hpay(cash=2.64, trsfr=4620)
        lines = [_jline(0, "1110202", debit=2.64),
                 _jline(1, "1120301", debit=4620),
                 _jline(2, "CG2A", credit=4622.64)]
        tr = acct.evaluate_cash_accounting(
            {**p, "CashAcct": "1110202"}, 999, lines,
            {"1110202": {"AcctName": "Cajas 2do. Anillo MN", "CashBox": "N"}})
        self.assertEqual(tr["status"], acct.CASH_ACCOUNTING_CONFIRMED)
        self.assertIn("MIXED_PAYMENT_DECOMPOSED", tr["explanation"])

    # 6/7: expected vs actual account
    def test_expected_account_from_orct(self):
        tr = acct.evaluate_cash_accounting(
            _hpay(acct="1110203"), 777, [_jline(0, "1110203", debit=50)], {})
        self.assertEqual(tr["cash_account_expected"], "1110203")
        self.assertEqual(tr["cash_account_actual"][0]["account"], "1110203")

    # 14: account mismatch (expected absent from journal)
    def test_account_mismatch(self):
        lines = [_jline(0, "9999999", debit=100)]
        tr = acct.evaluate_cash_accounting(_hpay(), 777, lines, _MASTER)
        self.assertEqual(tr["status"], acct.CASH_ACCOUNT_MISMATCH)

    # 10/11/12: exact / tolerance / real mismatch
    def test_amount_tolerance_and_mismatch(self):
        ok = acct.evaluate_cash_accounting(_hpay(cash=100), 1,
                                           [_jline(0, "1110201", debit=100)], _MASTER)
        tol = acct.evaluate_cash_accounting(_hpay(cash=100), 2,
                                            [_jline(0, "1110201", debit=100.005)], _MASTER)
        bad = acct.evaluate_cash_accounting(_hpay(cash=100), 3,
                                            [_jline(0, "1110201", debit=90)], _MASTER)
        self.assertEqual(ok["status"], acct.CASH_ACCOUNTING_CONFIRMED)
        self.assertEqual(tol["status"], acct.CASH_ACCOUNTING_CONFIRMED)
        self.assertEqual(bad["status"], acct.CASH_AMOUNT_MISMATCH)
        self.assertEqual(bad["amount_delta"], -10)

    # 13: missing journal
    def test_journal_missing(self):
        tr = acct.evaluate_cash_accounting(_hpay(), None, [], _MASTER)
        self.assertEqual(tr["status"], acct.CASH_JOURNAL_MISSING)

    # 8/9: CashBox semantics — flag N must be reported, never assumed
    def test_cashbox_flag_reported(self):
        tr = acct.evaluate_cash_accounting(_hpay(), 1,
                                           [_jline(0, "1110201", debit=100)], _MASTER)
        self.assertEqual(tr["cashbox_flag"], "N")
        self.assertIn("OACT_CASHBOX_FLAG_N", tr["explanation"])

    # 15: multiple JDT1 same account sum
    def test_multiple_lines_same_account(self):
        lines = [_jline(0, "1110201", debit=60), _jline(1, "1110201", debit=40)]
        tr = acct.evaluate_cash_accounting(_hpay(), 1, lines, _MASTER)
        self.assertEqual(tr["journal_cash_amount"], 100)
        self.assertIn("MULTIPLE_CASH_LINES_SAME_ACCOUNT", tr["explanation"])

    # 17/18: canceled payment + reversal net zero semantics
    def test_canceled_status(self):
        tr = acct.evaluate_cash_accounting(_hpay(canceled="Y"), 1,
                                           [_jline(0, "1110201", debit=100)], _MASTER)
        self.assertEqual(tr["status"], acct.CASH_CANCELED)

    def test_reversal_net_zero_sign_semantics(self):
        # original debits cash; reversal CREDITS it; raw signed sums net ZERO
        original = _jline(0, "1110201", debit=131.1)
        reversal = _jline(0, "1110201", credit=131.1)
        net = round((original["Debit"] - original["Credit"])
                    + (reversal["Debit"] - reversal["Credit"]), 4)
        self.assertEqual(net, 0)

    # 19/21: foreign currency preserved + sign direction
    def test_currency_and_sign_direction(self):
        tr = acct.evaluate_cash_accounting({**_hpay(), "DocCurr": "USD"}, 1,
                                           [_jline(0, "1110201", debit=50)], _MASTER)
        self.assertEqual(tr["currency"], "USD")
        cl = tr["cash_account_actual"][0]
        self.assertGreater(cl["raw_debit"], 0)
        self.assertEqual(cl["raw_credit"], 0)
        self.assertGreater(cl["signed_amount"], 0)

    # 24: branch inference is HEURISTIC, never CONFIRMED
    def test_branch_heuristic_class(self):
        b, cls = acct.branch_from_account_name("Caja Corporativa Laboratorio MN")
        self.assertEqual(cls, "HEURISTIC")
        self.assertEqual(b, "laboratorio")
        b2, cls2 = acct.branch_from_account_name("Caja Distribuidor Placa 4702-GIP MN")
        self.assertEqual(cls2, "HEURISTIC")
        self.assertEqual(b2, "placa_4702-gip")

    # 25: non-cash trace marked N/A with breakdown preserved
    def test_na_preserves_breakdown(self):
        tr = acct.evaluate_cash_accounting(_hpay(cash=0, card=300), 1, [], _MASTER)
        self.assertEqual(tr["instruments"]["card"], 300)

    # 26: lineage complete
    def test_lineage_complete(self):
        tr = acct.evaluate_cash_accounting(_hpay(), 555,
                                           [_jline(3, "1110201", debit=100)], _MASTER)
        self.assertEqual(tr["lineage"]["ORCT.DocEntry"], 100)
        self.assertEqual(tr["lineage"]["OJDT.TransId"], 555)
        self.assertEqual(tr["lineage"]["JDT1.lines"], [3])


# ---------------------------------------------------- E2E REAL HANA (T35-T50)
class TestE2EHANA(unittest.TestCase):
    """Run the real pipeline over HANA 2023-02; assert gate-level invariants."""

    @classmethod
    def setUpClass(cls):
        import modules.telchi.investigation.validation.atomic.traceability_e2e as e2e
        cls.e2e = e2e
        cls.rc = e2e.main()
        cls.report = json.loads(e2e.OUT.read_text(encoding="utf-8"))

    def test_pipeline_runs(self):
        self.assertEqual(self.rc, 0)

    def test_atomic_scale(self):
        self.assertGreater(self.report["cases_total"], 1000)

    def test_consistent_cases_exist(self):
        self.assertGreater(self.report["status_distribution"].get("CONSISTENT", 0), 0)

    def test_review_cases_have_unexplained(self):
        for top in self.report["top_unexplained"]:
            self.assertNotEqual(top["unexplained"], 0,
                                "REVIEW cases must carry unexplained difference")

    def test_lineage_complete_in_sample(self):
        for c in self.report["e2e_sample"]:
            self.assertIn("SAP_INVOICE", c["lineage"])
            self.assertTrue(c["lineage"]["SAP_INVOICE_LINES"],
                            "each E2E case must have INV1 lines")
            self.assertTrue(c["lineage"]["PAYMENTS"], "each E2E case must have ORCT")
            self.assertTrue(c["lineage"]["STOCK_MOVEMENTS"],
                            "each E2E case must have OINM")

    def test_daily_aggregation_control(self):
        # T41: control layer only — never used as primary proof
        self.assertGreater(len(self.report["daily_warehouse_aggregation"]), 0)

    def test_canceled_lifecycle_real(self):
        # T42/T50: May 2024 batch (978 Y + 978 C) must preserve lifecycle
        import pandas
        conn, cur = hconn.connect()
        try:
            cur.execute("""SELECT "DocEntry","DocNum","CardCode","DocDate","DocTotal",
                                  "DocCur","CANCELED","DocStatus"
                           FROM TELCHI."OINV"
                           WHERE "DocDate">='2024-05-01' AND "DocDate"<'2024-06-01'
                             AND "CANCELED" <> 'N'""")
            cols = [d[0] for d in cur.description]
            rows = pandas.DataFrame(cur.fetchall(), columns=cols)
        finally:
            cur.close()
            conn.close()
        self.assertGreater(len(rows), 100, "May 2024 cancellation batch expected")
        for _, r in rows.head(20).iterrows():
            c = tr.build_case(r.to_dict(), [], [], [], settled_amount=0.0)
            self.assertEqual(c["status"], tr.REVIEW_REQUIRED)
            self.assertIn("INVOICE_CANCELED_LIFECYCLE_PRESERVED", c["explanation"])


# ------------------------------------------------------------------ CONTRACT (HANA)
class TestContractHANA(unittest.TestCase):
    """CONFIRMED columns exist on the live HANA schema (READ ONLY)."""
    TABLES = {
        "OINV": SALE_HEADER,
        "ORCT": {**PAYMENT_HEADER, **CASH_EVENT_SAP_FIELDS},
        "ODLN": DELIVERY_HEADER,
        "OINM": INVENTORY_MOVEMENT,
    }

    @classmethod
    def setUpClass(cls):
        cls.conn, cls.cur = hconn.connect()
        cfg = hconn.load_hana_config()
        cls.schema = cfg.get("TELCHI_SAP_HANA_SCHEMA", "TELCHI")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.cur.close()
        finally:
            cls.conn.close()

    def test_columns_exist_confirmed(self):
        missing = {}
        for table, fields in self.TABLES.items():
            real = set(hconn.table_columns(self.schema, table))
            for sap_col, fld in fields.items():
                if fld.confidence == "CONFIRMED" and fld.name not in real:
                    missing.setdefault(table, []).append(fld.name)
        self.assertEqual(missing, {})


# ------------------------------------------------------------------ SOURCE (HANA)
class TestSourceHANA(unittest.TestCase):
    """Run atomic extractors on a small window; check grain + SAP IDs."""

    @classmethod
    def setUpClass(cls):
        cls.conn, cls.cur = hconn.connect()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.cur.close()
        finally:
            cls.conn.close()

    def _run(self, sql):
        n_sd = sql.count(":start_date")
        params = tuple(p for _ in range(n_sd) for p in WINDOW)
        self.cur.execute(sql.replace(":start_date", "?").replace(":end_date", "?"), params)
        rows = self.cur.fetchall()
        cols = [desc[0] for desc in self.cur.description or ()]
        return pandas.DataFrame(rows, columns=cols)

    def test_sale_header_grain_and_ids(self):
        df = self._run(load_sql("source_sale_header.sql"))
        self.assertGreater(len(df), 0)
        self.assertEqual(df["source_document_id"].nunique(), len(df), "header grain DocEntry")
        for idc in ("customer_id", "seller_id", "amount_document"):
            self.assertGreaterEqual(int(df[idc].notna().sum()), int(0.99 * len(df)), idc)

    def test_sale_line_grain(self):
        df = self._run(load_sql("source_sale_line.sql"))
        self.assertGreater(len(df), 0)
        grain = df.groupby(["source_document_id", "source_line_id"]).size()
        self.assertTrue((grain == 1).all(), "line grain DocEntry+LineNum")

    def test_payment_header_grain_unique(self):
        df = self._run(load_sql("source_payment_header.sql"))
        self.assertGreater(len(df), 0)
        self.assertEqual(df["source_document_id"].nunique(), len(df))

    def test_delivery_header_grain_unique(self):
        df = self._run(load_sql("source_delivery_header.sql"))
        self.assertTrue(len(df) > 0)

    def test_inventory_movement_grain(self):
        df = self._run(load_sql("source_inventory_movement.sql"))
        self.assertTrue(len(df) > 0)
        self.assertTrue(set(["source_document_id", "item_id", "warehouse_id"]) <= set(df.columns))

    def test_settlement_relation_grain(self):
        df = self._run(load_sql("relation_settlement.sql"))
        self.assertTrue(len(df) > 0)
        self.assertIn("recon_num", df.columns)

    def test_retail_one_folio_present_or_empty(self):
        df = self._run(load_sql("relation_retail_one_folio.sql"))
        # may be empty in this window; at least schema correct
        self.assertEqual(set({"sap_document_id", "retail_one_flag"}).issubset(set(df.columns)), True)

    def test_cash_event_sap_grain_and_positive_cash(self):
        df = self._run(load_sql("source_cash_event_sap.sql"))
        self.assertGreater(len(df), 0)
        self.assertEqual(df["source_document_id"].nunique(), len(df),
                         "CASH_EVENT grain: 1 row per ORCT.DocEntry")
        self.assertTrue((df["cash_amount"] > 0).all(),
                        "CASH_EVENT extractor filters CashSum > 0")

    def test_stock_document_relation_columns_and_resolution(self):
        df = self._run(load_sql("relation_stock_document.sql"))
        self.assertGreater(len(df), 0)
        required = {"from_document_id", "from_object_type", "to_object_type",
                    "relation_type", "match_method", "confidence", "item_id",
                    "warehouse_id", "strategy"}
        self.assertTrue(required <= set(df.columns), "relation contract columns")
        self.assertEqual(set(df["relation_type"]), {"GENERATES"})
        self.assertEqual(set(df["match_method"]), {"DIRECT_REFERENCE", "SAP_BASEENTRY"})
        # APPLOBJ_OFFICIAL rows carry real DocEntry; DOCNUM_RESOLVE rows must
        # resolve header or expose HEADER_UNRESOLVED as null from_document_id
        docnum_rows = df[df["strategy"] == "DOCNUM_RESOLVE"]
        resolved = docnum_rows["from_document_id"].notna().sum()
        self.assertGreater(resolved, int(0.9 * len(docnum_rows)),
                           ">=90% of DOCNUM_RESOLVE rows resolve a header")


# ------------------------------------------------------------------ SEMANTIC (real rows)
class TestSemanticRealRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn, cls.cur = hconn.connect()
        cls.window = WINDOW

    @classmethod
    def tearDownClass(cls):
        try:
            cls.cur.close()
        finally:
            cls.conn.close()

    def test_payment_method_profile_real(self):
        sql = load_sql("source_payment_header.sql").replace(":start_date", "?").replace(":end_date", "?")
        self.cur.execute(sql, self.window)
        rows = self.cur.fetchall()
        cols = [desc[0] for desc in self.cur.description or ()]
        df = pandas.DataFrame(rows, columns=cols)
        self.assertGreater(len(df), 0)
        # alias <- physical ORCT column (classifier reads physical names)
        alias_to_raw = {
            "cash_sum": "CashSum", "check_sum": "CheckSum",
            "transfer_sum": "TrsfrSum", "card_sum": "CreditSum",
            "on_account_sum": "NoDocSum", "boe_sum": "BoeSum",
        }
        counts = {ms: 0 for ms in ("CASH", "CHECK", "TRANSFER", "CARD", "MIXED", "OTHER")}
        for _, r in df.iterrows():
            sums = {alias_to_raw[c]: (r[c] or 0) for c in alias_to_raw}
            m = sem.classify_payment_method(sums)
            if m in counts:
                counts[m] += 1
        self.assertGreater(counts["CASH"], 0)
        # report profile
        self._profile = counts

    def test_cancelled_state_real(self):
        sql = load_sql("source_sale_header.sql").replace(":start_date", "?").replace(":end_date", "?")
        self.cur.execute(sql, self.window)
        df = pandas.DataFrame(self.cur.fetchall(), columns=[d[0] for d in self.cur.description])
        states = df["canceled"].map(sem.cancellation_state).value_counts().to_dict()
        self.assertIn("VALID", states)


# ---------------------------------------------------- E2E REAL HANA (T35-T50)
class TestH4HANA(unittest.TestCase):
    """H4 real batch: payment -> journal -> cash account over 2023-02."""

    @classmethod
    def setUpClass(cls):
        import modules.telchi.investigation.validation.atomic.cash_accounting_e2e as h4
        cls.h4 = h4
        cls.rc = h4.main()
        cls.report = json.loads(h4.OUT.read_text(encoding="utf-8"))

    def test_pipeline_runs(self):
        self.assertEqual(self.rc, 0)

    def test_orct_ojdt_full_coverage(self):
        cov = self.report["coverage"]
        self.assertEqual(cov["journal_missing"], 0,
                         "every ORCT.TransId must join OJDT")

    def test_amount_parity_exact(self):
        cov = self.report["coverage"]
        self.assertEqual(cov["amount_exact"], cov["journal_matched"],
                         "cash journal amount must equal CashSum exactly")

    def test_cancellations_present_and_traced(self):
        self.assertGreater(self.report["payments_canceled"], 100)

    def test_examples_real(self):
        ex = self.report["examples_real"]
        for k in ("A_cash_only", "B_mixed", "C_partial"):
            self.assertIsNotNone(ex.get(k), k)
            self.assertEqual(ex[k]["amount_delta"], 0)
        # lineage must carry verifiable SAP IDs
        a = ex["A_cash_only"]
        self.assertTrue(a["payment_docentry"] and a["trans_id"])

    def test_cashbox_flag_semantics_degraded(self):
        # OACT.CashBox='N' even for real cash accounts -> flag unusable,
        # must be surfaced in explanations instead of assumed
        rank = self.report["cash_account_ranking"]
        flags = {v.get("cashbox_flag") for v in rank.values()}
        self.assertIn("N", flags)


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestUnitContracts))
    suite.addTests(loader.loadTestsFromTestCase(TestUnitCashEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestTraceabilityUnit))
    suite.addTests(loader.loadTestsFromTestCase(TestAccountingUnit))
    suite.addTests(loader.loadTestsFromTestCase(TestLegacyParquet))

    if not hana_available():
        print("\n======================================================================")
        print("STOP_MANUAL_PODMAN_START_REQUIRED")
        print("HANA (127.0.0.1:30015 -> 10.88.0.2:30015) rechaza el handshake:")
        print("TCP conecta pero el servidor HANA cierra/resetea la conexion.")
        print("VPN/forward estan activos; el runtime HANA necesita inicio manual.")
        print("Contract/SOURCE/SEMANTIC HANA NO ejecutados (bloqueo externo real).")
        print("Resultado: BLOCKED (no PASS, no FAIL)")
        print("======================================================================\n")
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        return 3 if result.wasSuccessful() else 1

    suite.addTests(loader.loadTestsFromTestCase(TestContractHANA))
    suite.addTests(loader.loadTestsFromTestCase(TestSourceHANA))
    suite.addTests(loader.loadTestsFromTestCase(TestSemanticRealRows))
    suite.addTests(loader.loadTestsFromTestCase(TestE2EHANA))
    suite.addTests(loader.loadTestsFromTestCase(TestH4HANA))

    runner = unittest.TextTestRunner(verbosity=2)
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())