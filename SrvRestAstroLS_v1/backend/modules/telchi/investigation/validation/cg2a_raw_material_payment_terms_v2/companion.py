"""Bounded companion query: required query timings + monthly credit memos.

Read-only over the productive Foundation. Produces ``companion.json`` only.
No SAP, no Foundation writes, no candidate/latest access.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

EV = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2")
EXPECTED = "foundation_d222a203801cc84e9a14164d26aa67a0"


def timed(conn, sql, params=None):
    started = time.perf_counter()
    cur = conn.execute(sql, params or [])
    rows = cur.fetchall()
    names = [c[0] for c in cur.description] if cur.description else []
    ms = round((time.perf_counter() - started) * 1000, 3)
    return [dict(zip(names, r)) for r in rows], ms


def main() -> int:
    conn = DuckLakeConnector()
    out = {"timings_ms": {}, "notes": []}
    with conn.session(read_only=True) as c:
        c.execute("SET threads=1")
        t0 = time.perf_counter()
        access = FoundationReader(conn).resolve_on(c)
        out["timings_ms"]["foundation_resolution"] = round((time.perf_counter() - t0) * 1000, 3)
        if access.foundation_publication_id != EXPECTED:
            raise RuntimeError("CURRENT changed; stop")
        out["foundation_after"] = access.foundation_publication_id
        out["components_after"] = len(access.manifest.get("components") or {})

        S, L = access.sales("sales_document"), access.sales("sales_line")
        CD, CL = access.credit_memo("credit_memo_document"), access.credit_memo("credit_memo_line")
        SET = access.receivables_collections("receivable_settlement_status")
        M = access.receivables_collections("collection_method_fact")
        T = access.receivables_collections("commercial_term_classification")
        pbt_path = access.manifest["product_business_classification"]["crosswalk_path"]
        c.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{pbt_path}')")

        # 1) cohort reconstruction
        cohort_sql = f"""
        CREATE TEMP VIEW cohort AS
        SELECT d.doc_entry, CAST(d.doc_date AS DATE) doc_date, d.slp_code, any_value(l.whs_code) whs_code,
               sum(try_cast(l.line_total AS DECIMAL(38,6))) raw_gross
        FROM {S} d JOIN {L} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
        JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL'
        WHERE d.card_code='CG2A' AND coalesce(d.canceled,'N')<>'Y'
          AND CAST(d.doc_date AS DATE)>=DATE '2026-01-01' AND CAST(d.doc_date AS DATE)<DATE '2027-01-01'
        GROUP BY 1,2,3"""
        started = time.perf_counter()
        c.execute(cohort_sql)
        cohort_count = c.execute("SELECT count(*) FROM cohort").fetchone()[0]
        out["timings_ms"]["cohort_reconstruction"] = round((time.perf_counter() - started) * 1000, 3)
        out["cohort_documents"] = int(cohort_count)

        # 2) settlement analysis
        rows, ms = timed(c, f"""
            SELECT settlement_state, count(*), sum(document_total_local)
            FROM {SET} WHERE CAST(document_id AS VARCHAR) IN
              (SELECT CAST(doc_entry AS VARCHAR) FROM cohort) GROUP BY 1""")
        out["timings_ms"]["settlement_analysis"] = ms

        # 3) collection-method analysis (allocation bridge pinned to foundation base)
        base = int(access.manifest_base_snapshot_id)
        A = f'(SELECT * FROM telchi.atomic."collection_allocation" AT (VERSION => {base}))'
        c.execute("CREATE TEMP VIEW ca AS SELECT CAST(ch.doc_entry AS VARCHAR) doc_entry, a.payment_doc_entry "
                  "FROM cohort ch JOIN " + A + " a ON CAST(a.target_doc_entry AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR) "
                  "AND a.target_object_type='13'")
        rows, ms = timed(c, f"""
            SELECT collection_method, coalesce(sum(effective_amount_local),0), count(DISTINCT payment_id)
            FROM {M} WHERE payment_id IN (SELECT DISTINCT payment_doc_entry FROM ca) GROUP BY 1 ORDER BY 1""")
        out["timings_ms"]["collection_method_analysis"] = ms
        out["method_rows"] = rows

        # 4) monthly trend (documents, gross, settlement buckets, term)
        rows, ms = timed(c, """
            SELECT strftime(doc_date,'%Y-%m') m, count(*), sum(raw_gross) FROM cohort GROUP BY 1 ORDER BY 1""")
        out["timings_ms"]["monthly_trend"] = ms

        # monthly settlement + credit memos (for net sales per month)
        rows, ms = timed(c, f"""
            WITH cs AS (
              SELECT ch.doc_entry, ch.doc_date, ch.raw_gross, s.document_total_local,
                     s.days_document_to_full_settlement, s.settlement_state, t.commercial_term_class
              FROM cohort ch JOIN {SET} s ON CAST(s.document_id AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR)
              LEFT JOIN {T} t USING(payment_term_code))
            SELECT strftime(doc_date,'%Y-%m') m, count(*) docs, sum(raw_gross) gross,
                   count(*) FILTER (WHERE days_document_to_full_settlement=0) same_day,
                   count(*) FILTER (WHERE days_document_to_full_settlement>0) delayed,
                   count(*) FILTER (WHERE settlement_state<>'FULLY_SETTLED') not_full,
                   count(*) FILTER (WHERE commercial_term_class='COMMERCIAL_CASH_TERM') cash_term,
                   count(*) FILTER (WHERE commercial_term_class='COMMERCIAL_CREDIT_TERM') credit_term,
                   sum(document_total_local) doc_amt
            FROM cs GROUP BY 1 ORDER BY 1""")
        out["timings_ms"]["monthly_settlement_trend"] = ms
        out["monthly_settlement"] = rows

        rows, ms = timed(c, f"""
            SELECT strftime(CAST(d.doc_date AS DATE),'%Y-%m') m, count(*) lines, sum(try_cast(l.line_total AS DECIMAL(38,6))) credits
            FROM {CD} d JOIN {CL} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
            JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL'
            WHERE d.card_code='CG2A' AND coalesce(d.canceled,'N')<>'Y'
              AND CAST(d.doc_date AS DATE)>=DATE '2026-01-01' AND CAST(d.doc_date AS DATE)<DATE '2027-01-01'
              AND try_cast(l.base_type AS INTEGER)=13
              AND CAST(l.base_entry AS VARCHAR) IN (SELECT CAST(doc_entry AS VARCHAR) FROM cohort)
            GROUP BY 1 ORDER BY 1""")
        out["timings_ms"]["monthly_credit_memos"] = ms
        out["monthly_credits"] = rows

        # mixed-method double-count control
        rows, ms = timed(c, f"""
            SELECT count(*) FILTER (WHERE is_mixed_payment) mixed_rows, count(DISTINCT payment_id) FILTER (WHERE is_mixed_payment) mixed_payments,
                   count(*) AS method_rows_n, count(DISTINCT payment_id) AS payments
            FROM {M} WHERE payment_id IN (SELECT DISTINCT payment_doc_entry FROM ca)""")
        out["timings_ms"]["mixed_method_control"] = ms
        out["mixed_control"] = rows[0] if rows else None

        # on-account cohort vs account
        rows, ms = timed(c, f"""
            SELECT count(*) FROM {M}
            WHERE payment_id IN (SELECT DISTINCT payment_doc_entry FROM ca) AND abs(coalesce(on_account_amount_local,0))>.01""")
        out["timings_ms"]["on_account_control"] = ms

    (EV / "companion.json").write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(out["timings_ms"], indent=2))
    print("cohort:", out["cohort_documents"], "foundation_after:", out["foundation_after"], "components:", out["components_after"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
