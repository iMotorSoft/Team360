"""LOOP TEST 35-41 — deterministic gate tests for the credit-control cycle.

Pure Python: reads the evidence JSONs + Excel model + static source scan.
No HANA connection required.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.validation.credit_control.excel_model import build_authorization_model
from modules.telchi.investigation.validation.credit_control.phase78_credit_state_sales import compute_sale_states
from modules.telchi.investigation.validation.credit_control.readonly import _WRITE_TOKENS, guard_sql

HERE = Path(__file__).parent
EV = EVIDENCE_ROOT / "credit_control" / "evidence"


class TestReadOnlyGuard(unittest.TestCase):
    def test_dml_attempts_blocked(self):
        for sql in [
            "INSERT INTO t VALUES (1)",
            "UPDATE OCRD SET CreditLine=1",
            "DELETE FROM t",
            "MERGE INTO t USING s ON 1=1",
            "CREATE TABLE t (x int)",
            "ALTER TABLE t ADD c int",
            "DROP TABLE t",
            "TRUNCATE TABLE t",
            "GRANT SELECT ON t TO u",
            "REVOKE SELECT ON t FROM u",
            "CALL SBO_SP_TRANSACTIONNOTIFICATION(...)",
            "SELECT 1; DELETE FROM t",
        ]:
            with self.assertRaises(RuntimeError, msg=sql):
                guard_sql(sql)

    def test_selects_allowed(self):
        guard_sql("SELECT * FROM DUMMY")
        guard_sql("SELECT \"CreditLimt\" FROM \"TELCHI\".\"OADM\"")
        guard_sql("SELECT COLUMN_NAME FROM SYS.TABLE_COLUMNS WHERE SCHEMA_NAME='TELCHI'")

    def _strip_docstrings(self, text):
        # drop triple-quoted blocks so docstring prose is not scanned
        import re
        return re.sub(r'""".*?"""', "", text, flags=re.S)

    def test_no_write_statements_in_cycle_source(self):
        # only statements actually passed to cursor.execute()/executemany() matter
        bad = []
        for py in sorted((HERE / "..").glob("credit_control/**/*.py")):
            text = self._strip_docstrings(py.read_text(encoding="utf-8"))
            for i, line in enumerate(text.splitlines(), 1):
                if "execute(" not in line and "executemany(" not in line:
                    continue
                body = line.split("#", 1)[0]
                if _WRITE_TOKENS.search(body):
                    bad.append((py.name, i, line.strip()))
        self.assertEqual(bad, [])


class TestExcelModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = build_authorization_model()
        cls.ev = json.loads((EV / "excel_authorization_model.json").read_text(encoding="utf-8"))

    def test_user_counts(self):
        self.assertEqual(self.m["users_total"], 188)
        self.assertEqual(self.m["unique_logins"], 170)
        self.assertEqual(self.m["users_without_group"], 111)

    def test_group_sheet_consistency(self):
        self.assertEqual(len(self.m["group_codes"]), 14)
        self.assertEqual(
            self.m["group_sheets_missing"],
            ["Auxiliares", "Plantilla de Ventas", "Platilla de Medicamentos"],
        )
        # no unknown authorization level text
        self.assertEqual(self.m["unknown_authorization_values"], {})
        self.assertGreater(self.m["distinct_asunto"], 1100)

    def test_multi_group_cardinality(self):
        self.assertEqual(len(self.m["duplicate_logins"]), 18)

    def test_confirm_credit_deviation_distribution(self):
        c = {}
        for u in self.m["users_by_login"]:
            lv = u["effective_credit_auth"]["CONFIRM_CREDIT_LINE_DEVIATION"]
            c[lv] = c.get(lv, 0) + 1
        self.assertEqual(c.get("FULL", 0), 48)
        self.assertEqual(c.get("NONE", 0), 11)

    def test_managers_and_technical_present(self):
        logins = [u["login"] for u in self.m["users_by_login"]]
        for who in ["manager", "dms", "soluone", "B1i", "Workflow", "EDsUser", "AlertSvc"]:
            self.assertIn(who.lower(), [str(l).lower() for l in logins])


class TestPermIdPattern(unittest.TestCase):
    def test_candidates_match_groups(self):
        ev = json.loads((EV / "perm_id_credit_pattern.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(ev["candidate_count"], 10)
        self.assertEqual(ev["excel_pattern"]["restricted_groups"], [37, 43])
        # every candidate is F in all full groups
        for p, g in ev["detail"].items():
            for grp, lv in g.items():
                if int(grp) not in (37, 43):
                    self.assertEqual(lv, "F", p)


class TestTNDiscovery(unittest.TestCase):
    def test_graph_content(self):
        ev = json.loads((EV / "hana_phase234_probes.json").read_text(encoding="utf-8"))
        tn = ev["tn_discovery"]["sbo_sp_transactionnotification"]
        self.assertIn("ACB_TN_OINV", tn["called_procedures"])
        self.assertIn("ACB_TN_ORDR", tn["called_procedures"])
        self.assertGreaterEqual(len(tn["called_procedures"]), 23)
        self.assertGreaterEqual(tn["referenced_tables_count"], 95)
        # source not visible → honest limitation
        self.assertIsNone(tn["definition_visible"])

    def test_movil_overdue_proc(self):
        ev = json.loads((EV / "hana_phase234_probes.json").read_text(encoding="utf-8"))
        names = [p["name"] for p in ev["tn_discovery"]["credit_check_procedures"]]
        self.assertIn("MOVIL_SP_EXISTE_FACTURAS_VENCIDAS", names)


class TestCompanyConfig(unittest.TestCase):
    def test_oadm(self):
        cfg = json.loads((EV / "hana_phase234_probes.json").read_text(encoding="utf-8"))[
            "company_credit_config"]
        self.assertEqual(cfg["CreditLimt"], "Y")
        self.assertEqual(cfg["OpenCredit"], "N")
        self.assertEqual(cfg["OpenCdt"], "N")
        self.assertEqual(cfg["CreditDay1"], 1)
        self.assertEqual(cfg["CreditDay2"], 15)
        self.assertEqual(cfg["DlnLimit"], "N")  # delivery limit check off


class TestChannels(unittest.TestCase):
    def test_channel_coverage(self):
        ev = json.loads((EV / "hana_phase234_probes.json").read_text(encoding="utf-8"))
        ch = {r["canal"]: r for r in ev["channel_summary"]}
        total = sum(r["docs_total"] for r in ch.values())
        self.assertAlmostEqual(ch["RETAIL_ONE"]["docs_total"] / total, 0.861, delta=0.02)
        self.assertAlmostEqual(ch["DMS"]["docs_total"] / total, 0.085, delta=0.02)
        self.assertAlmostEqual(ch["SAP_DIRECT"]["docs_total"] / total, 0.054, delta=0.02)
        self.assertTrue(all(r["docs_active"] > 0 for r in ch.values()))


class TestCardinality(unittest.TestCase):
    def test_no_silent_fanout(self):
        ev = json.loads((EV / "phase40_cardinality.json").read_text(encoding="utf-8"))
        self.assertEqual(ev["verdict"], "NO_SILENT_FANOUT")
        self.assertLessEqual(ev["invoice_to_itr1"]["dup_factor"], 1.1)
        self.assertLessEqual(ev["itr1_oitr_orct"]["dup_factor"], 1.1)
        self.assertLessEqual(ev["itr1_oitr_orct"]["settled_unmatched_ratio"], 0.05)


class TestSaleStateLogic(unittest.TestCase):
    @staticmethod
    def doc(entry, ddate, ddue, total, paid, canceled="N"):
        from datetime import datetime
        return {"docentry": entry, "docnum": entry, "docdate": datetime.strptime(ddate, "%Y-%m-%d"),
                "docduedate": datetime.strptime(ddue, "%Y-%m-%d"), "doctotal": total,
                "paidtodate": paid, "canceled": canceled, "usersign": 1,
                "u_origin": "SAP", "u_so1_01retailone": "N", "slpcode": None}

    def test_customer_no_overdue(self):
        docs = [self.doc(1, "2026-01-05", "2026-02-05", 1000, 0)]
        r = compute_sale_states("X", docs, 0, _d(2026, 1, 1))[0]
        self.assertFalse(r["overdue_at_sale"])
        self.assertFalse(r["over_limit_before"])

    def test_overdue_at_sale(self):
        # invoice 1 due 2026-02-05 unpaid; sale 2 on 2026-04-10 → overdue at sale
        import datetime
        docs = [self.doc(1, "2026-01-05", "2026-02-05", 1000, 0),
                self.doc(2, "2026-04-10", "2026-05-10", 300, 0)]
        r = compute_sale_states("X", docs, 0, datetime.date(2026, 1, 1))[1]
        self.assertTrue(r["overdue_at_sale"])
        self.assertEqual(r["overdue_amount_at_sale"], 1000.0)

    def test_paid_later_not_open(self):
        # invoice fully paid → not counted as open → not overdue at later sale
        import datetime
        docs = [self.doc(1, "2026-01-05", "2026-02-05", 1000, 1000),
                self.doc(2, "2026-04-10", "2026-05-10", 300, 0)]
        r = compute_sale_states("X", docs, 0, datetime.date(2026, 1, 1))[1]
        self.assertFalse(r["overdue_at_sale"])
        self.assertEqual(r["prior_open_bound"], 0.0)

    def test_over_limit_before(self):
        import datetime
        # limit 500; prior open 1000 (paid later? keep open) then new sale 300
        docs = [self.doc(1, "2026-01-05", "2026-02-05", 1000, 0),
                self.doc(2, "2026-04-10", "2026-05-10", 300, 0)]
        r = compute_sale_states("X", docs, 500, datetime.date(2026, 1, 1))[1]
        self.assertTrue(r["over_limit_before"])
        self.assertTrue(r["over_limit_after"])

    def test_canceled_invoice_excluded(self):
        import datetime
        docs = [self.doc(1, "2026-01-05", "2026-02-05", 1000, 0, canceled="Y"),
                self.doc(2, "2026-04-10", "2026-05-10", 300, 0)]
        r = [x for x in compute_sale_states("X", docs, 0, datetime.date(2026, 1, 1))
             if x["docentry"] == 2][0]
        self.assertFalse(r["overdue_at_sale"])

    def test_sale_itself_not_self_counted(self):
        import datetime
        docs = [self.doc(9, "2026-03-15", "2026-04-15", 700, 0)]
        r = compute_sale_states("X", docs, 500, datetime.date(2026, 1, 1))[0]
        self.assertFalse(r["over_limit_before"])


def _d(y, m, d):
    import datetime
    return datetime.date(y, m, d)


class TestPhase56Exception(unittest.TestCase):
    def test_exception_fields(self):
        ev = json.loads((EV / "phase56_exception_approval.json").read_text(encoding="utf-8"))
        udf = {k: {r["v"]: r["n"] for r in v} for k, v in ev["ocrd_udf_distributions"].items()}
        # U_ClienteExcepcional is uniformly '0'; VENCREVENC has exactly 2 'Y'
        self.assertEqual(udf["U_ClienteExcepcional"].get("0", 0), 14010)
        self.assertEqual(udf["U_SO1_01VENCREVENC"].get("Y", 0), 2)
        self.assertEqual(udf["U_SO1_01AUTORIZARCOM"].get("N", 0), 14010)
        # retail one default config: no credit block threshold active
        cfg = {k: v for k, v in ev["retail_one_credit_config"].items()}
        self.assertEqual(str(cfg.get("u_so1_montominvencre")), "0")
        self.assertEqual(cfg.get("u_so1_pedidoscredito"), "N")

    def test_retail_one_sales_not_flagged_credit(self):
        ev = json.loads((EV / "phase56_exception_approval.json").read_text(encoding="utf-8"))
        dist = {r["v"]: r["n"] for r in ev["retail_one_sale_distributions"]["U_SO1_CREDITO"]}
        # live table keeps growing; assert the magnitude and the all-'N' semantics
        self.assertGreaterEqual(dist.get("N", 0), 1790000)
        self.assertNotIn("Y", dist)

    def test_approval_log(self):
        ev = json.loads((EV / "phase56_exception_approval.json").read_text(encoding="utf-8"))
        log = ev["retail_one_authorization_log"]
        self.assertGreaterEqual(log["total"], 16000)
        self.assertGreater(log["self_vs_other"]["other_auth"], log["self_vs_other"]["self_auth"])
        self.assertIn("2022", str(log["date_range"]["mn"]))


class TestPhase78Sales(unittest.TestCase):
    def test_sales_universe(self):
        ev = json.loads((EV / "phase78_sale_credit_state.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(ev["universe_customers"], 170)
        self.assertGreaterEqual(ev["sales_in_window"], 5000)
        self.assertGreaterEqual(ev["sales_with_overdue_at_sale"], 250)
        # all three channels present in the window
        self.assertEqual(set(ev["channel_distribution"]), {"RETAIL_ONE", "SAP_DIRECT", "DMS"})

    def test_payment_trace(self):
        ev = json.loads((EV / "phase10_sale_payments.json").read_text(encoding="utf-8"))
        with_pay = [t for t in ev if t["payments"]]
        self.assertGreaterEqual(len(with_pay), 80)
        for t in with_pay:
            for p in t["payments"]:
                self.assertEqual(p["pay_canceled"], "N")


class TestEvidenceFiles(unittest.TestCase):
    def test_all_evidence_present(self):
        expected = [
            "excel_authorization_model.json",
            "hana_phase234_probes.json",
            "perm_id_credit_pattern.json",
            "phase56_exception_approval.json",
            "phase78_sale_credit_state.json",
            "phase78_traceable_sales.json",
            "phase10_sale_payments.json",
            "phase40_cardinality.json",
        ]
        for f in expected:
            self.assertTrue((EV / f).is_file(), f)


if __name__ == "__main__":
    unittest.main(verbosity=2)
