"""Read-only exploration 2: settlement timing, due dates, method lineage, on-account."""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

EV = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2")


def main() -> int:
    conn = DuckLakeConnector()
    out = {}
    with conn.session(read_only=True) as c:
        c.execute("SET threads=1")
        access = FoundationReader(conn).resolve_on(c)
        base = int(access.manifest_base_snapshot_id)
        S = access.sales("sales_document")
        L = access.sales("sales_line")
        SET = access.receivables_collections("receivable_settlement_status")
        M = access.receivables_collections("collection_method_fact")
        T = access.receivables_collections("commercial_term_classification")
        pbt_path = (access.manifest.get("product_business_classification") or {}).get("crosswalk_path")
        c.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{pbt_path}')")
        c.execute(f"""
        CREATE TEMP VIEW cohort AS
        SELECT d.doc_entry, CAST(d.doc_date AS DATE) AS doc_date, CAST(d.doc_due_date AS DATE) AS doc_due_date,
               d.currency, d.sales_channel_name, d.slp_code, d.doc_status,
               sum(try_cast(l.line_total AS DECIMAL(38,6))) AS gross,
               count(*) AS lines, count(DISTINCT l.item_code) AS sku_lines,
               any_value(l.whs_code) AS whs_code
        FROM {S} d JOIN {L} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
        JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL'
        WHERE d.card_code='CG2A' AND coalesce(d.canceled,'N')<>'Y'
          AND CAST(d.doc_date AS DATE)>=DATE '2026-01-01' AND CAST(d.doc_date AS DATE)<DATE '2027-01-01'
        GROUP BY 1,2,3,4,5,6,7
        """)
        c.execute(f"""
        CREATE TEMP VIEW cs AS
        SELECT ch.*, s.customer_code, s.document_date, s.document_total_local, s.due_date, s.settlement_state,
               s.fully_settled_date, s.days_document_to_full_settlement, s.days_due_to_full_settlement,
               s.payment_term_code, s.open_amount_local, s.payment_settlement_effect_local,
               s.credit_memo_settlement_effect_local, s.internal_reconciliation_effect_local,
               s.multi_source_reconciliation_effect_local, s.economic_reduction_local,
               t.commercial_term_class, t.payment_term_name
        FROM cohort ch JOIN {SET} s ON CAST(s.document_id AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR)
        LEFT JOIN {T} t USING(payment_term_code)
        """)

        def q(sql, params=None):
            cur = c.execute(sql, params or [])
            names = [x[0] for x in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

        out["cohort_row_count"] = c.execute("SELECT count(*) FROM cs").fetchone()[0]
        out["distinct_customer_on_join"] = q("SELECT customer_code, count(*) n FROM cs GROUP BY 1")
        out["term_distribution"] = q("SELECT commercial_term_class, payment_term_code, payment_term_name, count(*) n, sum(document_total_local) amt FROM cs GROUP BY 1,2,3 ORDER BY n DESC")
        out["settlement_state_dist"] = q("SELECT settlement_state, count(*) n, sum(document_total_local) amt, sum(open_amount_local) open_amt FROM cs GROUP BY 1 ORDER BY n DESC")
        out["timing_buckets"] = q("""
            SELECT settlement_state,
                   CASE WHEN fully_settled_date IS NULL THEN 'NOT_FULLY'
                        WHEN days_document_to_full_settlement=0 THEN 'SAME_DAY'
                        WHEN days_document_to_full_settlement=1 THEN 'NEXT_DAY'
                        WHEN days_document_to_full_settlement<=7 THEN 'D2_7'
                        WHEN days_document_to_full_settlement<=30 THEN 'D8_30'
                        ELSE 'D31_PLUS' END AS bucket,
                   count(*) n, sum(document_total_local) amt
            FROM cs GROUP BY 1,2 ORDER BY n DESC""")
        out["days_dist"] = q("""
            SELECT days_document_to_full_settlement d, count(*) n, sum(document_total_local) amt
            FROM cs WHERE settlement_state='FULLY_SETTLED' AND days_document_to_full_settlement IS NOT NULL
            GROUP BY 1 ORDER BY 1""")
        out["due_relation"] = q("""
            SELECT CASE WHEN due_date IS NULL THEN 'UNRESOLVED'
                        WHEN due_date=document_date THEN 'SAME_DAY'
                        WHEN due_date>document_date THEN 'AFTER'
                        ELSE 'BEFORE' END AS rel,
                   count(*) n, sum(document_total_local) amt,
                   min(date_diff('day', document_date, due_date)) mn,
                   max(date_diff('day', document_date, due_date)) mx
            FROM cs GROUP BY 1 ORDER BY n DESC""")
        out["due_days_stats"] = c.execute("""
            SELECT count(*), min(date_diff('day',document_date,due_date)),
                   quantile_cont(date_diff('day',document_date,due_date),0.5),
                   quantile_cont(date_diff('day',document_date,due_date),0.9),
                   max(date_diff('day',document_date,due_date))
            FROM cs WHERE due_date IS NOT NULL""").fetchall()
        out["settlement_vs_due"] = q("""
            SELECT CASE
                     WHEN settlement_state='FULLY_SETTLED' AND fully_settled_date<=due_date THEN 'SETTLED_ON_OR_BEFORE_DUE'
                     WHEN settlement_state='FULLY_SETTLED' AND fully_settled_date>due_date THEN 'SETTLED_AFTER_DUE'
                     WHEN settlement_state IN ('OPEN','PARTIALLY_SETTLED') AND due_date<DATE '2026-09-28' THEN 'OPEN_OVERDUE'
                     WHEN settlement_state IN ('OPEN','PARTIALLY_SETTLED') THEN 'OPEN_NOT_DUE'
                     ELSE settlement_state END AS rel,
                   count(*) n, sum(document_total_local) amt
            FROM cs GROUP BY 1 ORDER BY n DESC""")
        out["effect_mix"] = q("""
            SELECT
              sum(payment_settlement_effect_local) pay,
              sum(credit_memo_settlement_effect_local) cm,
              sum(internal_reconciliation_effect_local) internal,
              sum(multi_source_reconciliation_effect_local) multi,
              sum(economic_reduction_local) total_reduction,
              sum(document_total_local) total_doc,
              sum(open_amount_local) open_amt
            FROM cs""")
        out["channel_wh_seller"] = q("""
            SELECT sales_channel_name, whs_code, count(*) n FROM cs GROUP BY 1,2 ORDER BY n DESC""")
        out["sellers"] = q("SELECT slp_code, count(*) n, sum(gross) gross FROM cs GROUP BY 1 ORDER BY n DESC")
        out["doc_status"] = q("SELECT doc_status, count(*) n FROM cs GROUP BY 1")

        # ---- method lineage via allocation (pinned to foundation base snapshot) ----
        A = f'(SELECT * FROM telchi.atomic."collection_allocation" AT (VERSION => {base}))'
        P = f'(SELECT * FROM telchi.atomic."collection_payment" AT (VERSION => {base}))'
        c.execute(
            "CREATE TEMP VIEW cohort_alloc AS "
            "SELECT CAST(ch.doc_entry AS VARCHAR) AS doc_entry, a.payment_doc_entry, "
            "try_cast(a.allocated_amount AS DECIMAL(38,6)) AS allocated_amount "
            "FROM cohort ch JOIN " + A + " a "
            "ON CAST(a.target_doc_entry AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR) AND a.target_object_type='13'"
        )
        out["alloc_summary"] = q("""
            SELECT count(*) alloc_rows, count(DISTINCT doc_entry) docs, count(DISTINCT payment_doc_entry) payments,
                   sum(allocated_amount) allocated
            FROM cohort_alloc""")
        out["payment_touch_summary"] = q(f"""
            SELECT count(*) payments,
                   count(*) FILTER (WHERE is_mixed) mixed_payments,
                   sum(cohort_allocated) cohort_allocated,
                   sum(payment_total) payment_total,
                   sum(cohort_allocated_for_other) serves_other
            FROM (
              SELECT ca.payment_doc_entry,
                     sum(ca.allocated_amount) cohort_allocated,
                     bool_or(m.is_mixed_payment) is_mixed,
                     max(try_cast(p.payment_total AS DECIMAL(38,6))) payment_total,
                     max(try_cast(p.payment_total AS DECIMAL(38,6))) - sum(ca.allocated_amount) cohort_allocated_for_other
              FROM cohort_alloc ca
              JOIN {P} p ON CAST(p.source_doc_entry AS VARCHAR)=ca.payment_doc_entry AND p.cancelled NOT IN ('Y','C')
              LEFT JOIN (SELECT payment_id, max(is_mixed_payment) is_mixed_payment FROM {M} GROUP BY 1) m
                ON m.payment_id = ca.payment_doc_entry
              GROUP BY 1
            ) x""")
        out["method_by_payment_profile"] = q(f"""
            SELECT f.collection_method,
                   sum(f.effective_amount_local) method_total_for_touching_payments,
                   count(DISTINCT f.payment_id) payments
            FROM {M} f
            WHERE f.payment_id IN (SELECT DISTINCT payment_doc_entry FROM cohort_alloc)
            GROUP BY 1 ORDER BY 2 DESC""")
        out["on_account"] = q(f"""
            SELECT count(DISTINCT p.source_doc_entry) n_payments,
                   sum(try_cast(p.on_account_amount AS DECIMAL(38,6))) on_account_amt
            FROM {P} p
            WHERE p.cancelled NOT IN ('Y','C')
              AND CAST(p.source_doc_entry AS VARCHAR) IN (SELECT DISTINCT payment_doc_entry FROM cohort_alloc)
              AND (p.pay_no_document='Y' OR abs(coalesce(try_cast(p.on_account_amount AS DECIMAL(38,6)),0))>.01)""")
        out["cg2a_all_on_account"] = q(f"""
            SELECT count(*) n, sum(try_cast(on_account_amount AS DECIMAL(38,6))) amt
            FROM {P} WHERE customer_code='CG2A' AND cancelled NOT IN ('Y','C')
              AND (pay_no_document='Y' OR abs(coalesce(try_cast(on_account_amount AS DECIMAL(38,6)),0))>.01)""")
        out["late_cohort"] = q("""
            SELECT count(*) n, sum(gross) gross FROM cohort WHERE doc_date BETWEEN DATE '2026-09-22' AND DATE '2026-09-24'""")
        out["late_cohort_state"] = q("""
            SELECT settlement_state, count(*) n, sum(document_total_local) amt FROM cs
            WHERE doc_date BETWEEN DATE '2026-09-22' AND DATE '2026-09-24' GROUP BY 1""")
        out["mature"] = q("""
            SELECT settlement_state,
                   CASE WHEN days_document_to_full_settlement=0 THEN 'SAME_DAY'
                        WHEN days_document_to_full_settlement=1 THEN 'NEXT_DAY'
                        WHEN days_document_to_full_settlement<=7 THEN 'D2_7'
                        WHEN days_document_to_full_settlement<=30 THEN 'D8_30'
                        WHEN days_document_to_full_settlement>30 THEN 'D31_PLUS'
                        ELSE 'NOT_FULL' END AS bucket,
                   count(*) n, sum(document_total_local) amt
            FROM cs WHERE doc_date<=DATE '2026-08-31' GROUP BY 1,2 ORDER BY n DESC""")
        out["monthly"] = q("""
            SELECT strftime(doc_date,'%Y-%m') m, count(*) docs, sum(gross) gross,
                   sum(document_total_local) doc_amt,
                   count(*) FILTER (WHERE days_document_to_full_settlement=0) same_day,
                   count(*) FILTER (WHERE days_document_to_full_settlement>0) delayed,
                   count(*) FILTER (WHERE settlement_state<>'FULLY_SETTLED') not_full,
                   count(*) FILTER (WHERE commercial_term_class='COMMERCIAL_CASH_TERM') cash_term
            FROM cs GROUP BY 1 ORDER BY 1""")
        out["monthly_method"] = q(f"""
            SELECT strftime(f.payment_date,'%Y-%m') m, f.collection_method,
                   sum(f.effective_amount_local) amt, count(DISTINCT f.payment_id) pays
            FROM {M} f WHERE f.payment_id IN (SELECT DISTINCT payment_doc_entry FROM cohort_alloc)
              AND f.payment_date BETWEEN DATE '2026-01-01' AND DATE '2026-09-30'
            GROUP BY 1,2 ORDER BY 1,2""")
        out["open_debt_asof"] = q("""
            SELECT count(*) n, sum(open_amount_local) amt FROM cs WHERE open_amount_local>.01""")
        out["cg2a_open_all"] = c.execute(f"SELECT count(*), coalesce(sum(open_amount_local),0) FROM {SET} WHERE customer_code='CG2A' AND open_amount_local>.01").fetchall()

    (EV / "explore2.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str)[:12000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
