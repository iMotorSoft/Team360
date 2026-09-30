"""Read-only exploration 4: financial grains, delayed docs, controls, as-of."""
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
        S, L = access.sales("sales_document"), access.sales("sales_line")
        SET = access.receivables_collections("receivable_settlement_status")
        M = access.receivables_collections("collection_method_fact")
        T = access.receivables_collections("commercial_term_classification")
        manifest = access.manifest
        rc = manifest["components"]["receivables_collections"]
        out["receivables_component"] = {k: rc.get(k) for k in (
            "source_as_of", "derivation_id", "derivation_version", "row_count",
            "qr_source_status", "final_contado_business_rule_defined", "currency_reporting_basis",
            "historical_asof_grain", "intraday_asof", "publication_id")}
        out["receivables_datasets"] = rc.get("datasets")
        out["manifest_reproducibility"] = {k: manifest.get(k) for k in ("foundation_candidate_created_at", "candidate_kind", "base_snapshot_id")}

        pbt_path = manifest["product_business_classification"]["crosswalk_path"]
        c.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{pbt_path}')")

        def q(sql, params=None):
            cur = c.execute(sql, params or [])
            names = [x[0] for x in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

        # cohort doc list
        c.execute(f"""
        CREATE TEMP VIEW cohort AS
        SELECT d.doc_entry, CAST(d.doc_date AS DATE) doc_date, CAST(d.doc_due_date AS DATE) doc_due_date,
               d.slp_code, any_value(l.whs_code) whs_code,
               sum(try_cast(l.line_total AS DECIMAL(38,6))) raw_gross, count(*) raw_lines
        FROM {S} d JOIN {L} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
        JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL'
        WHERE d.card_code='CG2A' AND coalesce(d.canceled,'N')<>'Y'
          AND CAST(d.doc_date AS DATE)>=DATE '2026-01-01' AND CAST(d.doc_date AS DATE)<DATE '2027-01-01'
        GROUP BY 1,2,3,4
        """)

        # ALL lines of cohort documents (any business type) vs raw vs doc total
        c.execute(f"""
        CREATE TEMP VIEW cohort_all_lines AS
        SELECT l.doc_entry,
               sum(try_cast(l.line_total AS DECIMAL(38,6))) AS all_lines_gross,
               count(*) AS all_lines,
               sum(try_cast(l.line_total AS DECIMAL(38,6))) FILTER (WHERE p.product_business_type='RAW_MATERIAL') AS raw_gross,
               count(*) FILTER (WHERE p.product_business_type='RAW_MATERIAL') AS raw_lines
        FROM {L} l JOIN pbt p ON p.ItemCode=l.item_code
        WHERE CAST(l.doc_entry AS VARCHAR) IN (SELECT CAST(doc_entry AS VARCHAR) FROM cohort)
        GROUP BY 1
        """)
        out["line_grain_compare"] = c.execute("""
            SELECT count(*) docs,
                   sum(all_lines_gross) all_lines_gross, sum(all_lines) all_lines,
                   sum(raw_gross) raw_gross, sum(raw_lines) raw_lines,
                   sum(all_lines_gross)-sum(raw_gross) non_raw
            FROM cohort_all_lines""").fetchall()

        # doc totals vs line totals vs tax
        c.execute(f"""
        CREATE TEMP VIEW cs AS
        SELECT ch.*, s.document_total_local, s.document_total_foreign, s.document_total_system,
               s.due_date, s.settlement_state, s.fully_settled_date, s.days_document_to_full_settlement,
               s.payment_term_code, s.open_amount_local, s.payment_settlement_effect_local,
               s.credit_memo_settlement_effect_local, s.internal_reconciliation_effect_local,
               s.multi_source_reconciliation_effect_local, s.economic_reduction_local, t.commercial_term_class
        FROM cohort ch JOIN {SET} s ON CAST(s.document_id AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR)
        LEFT JOIN {T} t USING(payment_term_code)""")
        out["grain_totals"] = c.execute("""
            SELECT count(*) docs, sum(document_total_local) doc_total,
                   sum(raw_gross) raw_gross, sum(raw_lines) raw_lines,
                   sum(document_total_local)-sum(raw_gross) delta
            FROM cs""").fetchall()

        # non-raw lines inside cohort documents by business type
        out["non_raw_lines"] = q(f"""
            SELECT coalesce(p.product_business_type,'NO_CLASS') bt, count(*) lines,
                   sum(try_cast(l.line_total AS DECIMAL(38,6))) gross
            FROM {L} l LEFT JOIN pbt p ON p.ItemCode=l.item_code
            WHERE CAST(l.doc_entry AS VARCHAR) IN (SELECT CAST(doc_entry AS VARCHAR) FROM cohort)
              AND coalesce(p.product_business_type,'NO_CLASS')<>'RAW_MATERIAL'
            GROUP BY 1 ORDER BY 3 DESC""")

        # the two delayed documents in full
        out["delayed_docs"] = q("""
            SELECT doc_entry, doc_date, document_total_local, fully_settled_date,
                   days_document_to_full_settlement, raw_gross, raw_lines, payment_term_code, commercial_term_class
            FROM cs WHERE days_document_to_full_settlement>0 ORDER BY days_document_to_full_settlement""")

        # controls L00031 / L03192 at raw-line grain
        out["control_products"] = q(f"""
            SELECT l.item_code, count(DISTINCT l.doc_entry) docs,
                   sum(try_cast(l.quantity AS DECIMAL(38,6))) qty,
                   sum(try_cast(l.line_total AS DECIMAL(38,6))) gross
            FROM {L} l JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL'
            WHERE CAST(l.doc_entry AS VARCHAR) IN (SELECT CAST(doc_entry AS VARCHAR) FROM cohort)
              AND l.item_code IN ('L00031','L03192')
            GROUP BY 1 ORDER BY 1""")

        # credit memo settlement effect at document grain vs raw-line credit
        out["credit_grains"] = c.execute("""
            SELECT sum(credit_memo_settlement_effect_local) doc_grain_credit_effect,
                   sum(payment_settlement_effect_local) payment_effect,
                   sum(internal_reconciliation_effect_local) internal_effect,
                   sum(multi_source_reconciliation_effect_local) multi_effect,
                   sum(economic_reduction_local) total_reduction,
                   sum(document_total_local) doc_total
            FROM cs""").fetchall()

        # delayed doc line detail
        out["delayed_doc_lines"] = q(f"""
            SELECT l.doc_entry, l.item_code, p.product_business_type,
                   try_cast(l.line_total AS DECIMAL(38,6)) gross
            FROM {L} l LEFT JOIN pbt p ON p.ItemCode=l.item_code
            WHERE CAST(l.doc_entry AS VARCHAR) IN (
              SELECT CAST(doc_entry AS VARCHAR) FROM cs WHERE days_document_to_full_settlement>0)
            ORDER BY l.doc_entry, l.item_code""")

        # settlement table as-of / built_at
        out["settlement_asof"] = c.execute(f"""
            SELECT min(source_as_of) mn, max(source_as_of) mx, min(built_at) bmn, max(built_at) bmx,
                   min(derivation_version) dvmn, max(derivation_version) dvmx
            FROM {SET}""").fetchall()
        out["settlement_cg2a_asof"] = c.execute(f"SELECT min(source_as_of), max(built_at) FROM {SET} WHERE customer_code='CG2A'").fetchall()

        # open debt cohort + cg2a account, with aging via due date
        out["open_debt_cohort"] = c.execute("""
            SELECT count(*) n, coalesce(sum(open_amount_local),0) amt FROM cs WHERE open_amount_local>.01""").fetchall()
        out["open_debt_cg2a"] = q(f"""
            SELECT count(*) n, coalesce(sum(open_amount_local),0) amt,
                   coalesce(sum(open_amount_local) FILTER (WHERE due_date>=DATE '2026-09-28'),0) current_amt,
                   coalesce(sum(open_amount_local) FILTER (WHERE due_date<DATE '2026-09-28'),0) overdue_amt
            FROM {SET} WHERE customer_code='CG2A' AND open_amount_local>.01""")
        out["open_debt_cg2a_detail"] = q(f"""
            SELECT document_id, document_date, due_date, document_total_local, open_amount_local, settlement_state
            FROM {SET} WHERE customer_code='CG2A' AND open_amount_local>.01""")

        # amount-weighted exact pcts
        row = c.execute("""
            SELECT count(*), sum(document_total_local),
                   count(*) FILTER (WHERE days_document_to_full_settlement=0),
                   sum(document_total_local) FILTER (WHERE days_document_to_full_settlement=0),
                   count(*) FILTER (WHERE days_document_to_full_settlement<=1),
                   sum(document_total_local) FILTER (WHERE days_document_to_full_settlement<=1),
                   count(*) FILTER (WHERE days_document_to_full_settlement<=7),
                   sum(document_total_local) FILTER (WHERE days_document_to_full_settlement<=7),
                   count(*) FILTER (WHERE days_document_to_full_settlement<=30),
                   sum(document_total_local) FILTER (WHERE days_document_to_full_settlement<=30)
            FROM cs""").fetchone()
        out["pct_exact"] = row

        # monthly method trend already captured; get collection months range for cohort payments
        A = f'(SELECT * FROM telchi.atomic."collection_allocation" AT (VERSION => {base}))'
        c.execute("CREATE TEMP VIEW ca AS SELECT CAST(ch.doc_entry AS VARCHAR) doc_entry, a.payment_doc_entry FROM cohort ch JOIN " + A + " a ON CAST(a.target_doc_entry AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR) AND a.target_object_type='13'")
        out["cohort_payment_months"] = q(f"""
            SELECT strftime(f.payment_date,'%Y-%m') m, f.collection_method,
                   sum(f.effective_amount_local) amt, count(DISTINCT f.payment_id) pays
            FROM {M} f WHERE f.payment_id IN (SELECT DISTINCT payment_doc_entry FROM ca)
              AND f.payment_date BETWEEN DATE '2026-01-01' AND DATE '2026-09-30'
            GROUP BY 1,2 ORDER BY 1,2""")
        out["method_recon"] = c.execute(f"""
            SELECT coalesce(sum(f.effective_amount_local),0) method_sum, count(DISTINCT f.payment_id) payments
            FROM {M} f WHERE f.payment_id IN (SELECT DISTINCT payment_doc_entry FROM ca)""").fetchone()
        out["payment_effect"] = c.execute("SELECT coalesce(sum(payment_settlement_effect_local),0) FROM cs").fetchone()

    (EV / "explore4.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str)[:9000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
