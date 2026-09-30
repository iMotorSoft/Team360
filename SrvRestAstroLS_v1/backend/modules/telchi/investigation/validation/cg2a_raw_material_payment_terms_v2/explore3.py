"""Read-only exploration 3: credit memos, location, multi-method, uom, products."""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
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
        CD, CL = access.credit_memo("credit_memo_document"), access.credit_memo("credit_memo_line")
        SET = access.receivables_collections("receivable_settlement_status")
        M = access.receivables_collections("collection_method_fact")
        manifest = access.manifest
        pbt_path = manifest["product_business_classification"]["crosswalk_path"]
        loc_path = manifest["reference_closure"]["warehouse_location_crosswalk"]
        review_path = manifest["generic_customer_raw_material_review"]["file_references"][0]
        ref = access.reference

        def q(sql, params=None):
            cur = c.execute(sql, params or [])
            names = [x[0] for x in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

        c.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{pbt_path}')")
        c.execute(f"CREATE TEMP VIEW wl AS SELECT * FROM read_parquet('{loc_path}')")
        c.execute(f"CREATE TEMP VIEW review AS SELECT * FROM read_parquet('{review_path}')")
        c.execute(f"""
        CREATE TEMP VIEW scoped_sales AS
        SELECT d.source_system, d.doc_entry, CAST(d.doc_date AS DATE) doc_date, l.line_num, l.item_code,
               l.whs_code, try_cast(l.quantity AS DECIMAL(38,6)) qty, try_cast(l.line_total AS DECIMAL(38,6)) gross
        FROM {S} d JOIN {L} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
        JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL'
        WHERE d.card_code='CG2A' AND coalesce(d.canceled,'N')<>'Y'
          AND CAST(d.doc_date AS DATE)>=DATE '2026-01-01' AND CAST(d.doc_date AS DATE)<DATE '2027-01-01'
        """)
        c.execute(f"""
        CREATE TEMP VIEW scoped_credits AS
        SELECT d.source_system, d.doc_entry credit_doc_entry, l.line_num credit_line_num, l.item_code,
               try_cast(l.quantity AS DECIMAL(38,6)) credit_qty, try_cast(l.line_total AS DECIMAL(38,6)) credit_amount,
               l.base_type, l.base_entry, l.base_line
        FROM {CD} d JOIN {CL} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
        JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL'
        WHERE d.card_code='CG2A' AND coalesce(d.canceled,'N')<>'Y'
          AND CAST(d.doc_date AS DATE)>=DATE '2026-01-01' AND CAST(d.doc_date AS DATE)<DATE '2027-01-01'
        """)
        out["credit_lines"] = c.execute("""
            SELECT count(*) n, coalesce(sum(credit_amount),0) amt FROM scoped_credits""").fetchall()
        out["credit_link"] = c.execute("""
            SELECT count(*) n, count(*) FILTER (WHERE s.doc_entry IS NOT NULL) linked,
                   coalesce(sum(c.credit_amount),0) amt,
                   coalesce(sum(c.credit_amount) FILTER (WHERE s.doc_entry IS NOT NULL),0) linked_amt
            FROM scoped_credits c LEFT JOIN scoped_sales s
              ON c.source_system=s.source_system AND try_cast(c.base_type AS INTEGER)=13
             AND CAST(c.base_entry AS VARCHAR)=CAST(s.doc_entry AS VARCHAR)
             AND CAST(c.base_line AS VARCHAR)=CAST(s.line_num AS VARCHAR) AND c.item_code=s.item_code""").fetchall()

        # cohort + settlement for multi-method docs
        c.execute(
            "CREATE TEMP VIEW cohort AS "
            "SELECT d.doc_entry, CAST(d.doc_date AS DATE) doc_date, d.slp_code, d.sales_channel_name, "
            "sum(try_cast(l.line_total AS DECIMAL(38,6))) gross, count(*) lines, "
            "string_agg(DISTINCT l.item_code, ',' ORDER BY l.item_code) item_codes, "
            "any_value(l.whs_code) whs_code "
            "FROM " + S + " d JOIN " + L + " l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry "
            "JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL' "
            "WHERE d.card_code='CG2A' AND coalesce(d.canceled,'N')<>'Y' "
            "AND CAST(d.doc_date AS DATE)>=DATE '2026-01-01' AND CAST(d.doc_date AS DATE)<DATE '2027-01-01' "
            "GROUP BY 1,2,3,4"
        )
        A = f'(SELECT * FROM telchi.atomic."collection_allocation" AT (VERSION => {base}))'
        P = f'(SELECT * FROM telchi.atomic."collection_payment" AT (VERSION => {base}))'
        c.execute("CREATE TEMP VIEW cohort_alloc AS SELECT CAST(ch.doc_entry AS VARCHAR) doc_entry, a.payment_doc_entry FROM cohort ch JOIN " + A + " a ON CAST(a.target_doc_entry AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR) AND a.target_object_type='13'")
        c.execute(
            "CREATE TEMP VIEW mixed_pay AS "
            "SELECT payment_id, max(is_mixed_payment) mixed FROM " + M + " GROUP BY 1"
        )

        out["multi_method"] = q("""
            SELECT count(DISTINCT ca.doc_entry) multi_method_docs
            FROM cohort_alloc ca JOIN mixed_pay mp ON mp.payment_id=ca.payment_doc_entry
            WHERE mp.mixed""")

        # settlement bucket per doc for product/seller attribution
        c.execute(f"""
        CREATE TEMP VIEW cs AS
        SELECT ch.*, s.document_total_local, s.due_date, s.settlement_state, s.fully_settled_date,
               s.days_document_to_full_settlement, s.payment_term_code, s.open_amount_local, s.cancelled
        FROM cohort ch JOIN {SET} s ON CAST(s.document_id AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR)""")

        out["location"] = q("""
            SELECT wl.business_location_code, count(*) n FROM cohort ch JOIN wl
              ON wl.warehouse_code=ch.whs_code AND wl.source_system='SAP_HANA' GROUP BY 1""")
        out["wh"] = q("SELECT whs_code, count(*) n FROM cohort GROUP BY 1")
        out["channel"] = q("SELECT sales_channel_name, count(*) n FROM cohort GROUP BY 1")

        out["uom_control"] = q("""
            SELECT item_code, count(*) n, count(DISTINCT uom) uoms, min(uom) uom FROM (
              SELECT ItemCode item_code, CASE WHEN count(DISTINCT uom)=1 THEN min(uom) ELSE 'MULTIPLE' END uom
              FROM review WHERE CardCode='CG2A' AND product_business_type='RAW_MATERIAL' GROUP BY ItemCode
            ) GROUP BY item_code ORDER BY item_code""")
        out["review_uom_dist"] = q("SELECT DISTINCT uom FROM review WHERE CardCode='CG2A' AND product_business_type='RAW_MATERIAL' LIMIT 10")
        out["control_products"] = q("""
            SELECT pbt.ItemCode, pbt.product_business_type FROM pbt WHERE pbt.ItemCode IN ('L00031','L03192')""")

        # products reference (uom from reference)
        c.execute(f"CREATE TEMP VIEW prod AS SELECT item_code, product_name FROM read_parquet('{ref('products')}') QUALIFY row_number() OVER (PARTITION BY item_code ORDER BY CASE source_system WHEN 'SAP_HANA' THEN 0 ELSE 1 END, canonical_product_id)=1")
        out["product_reference_control"] = q("SELECT item_code, product_name FROM prod WHERE item_code IN ('L00031','L03192')")

        # per-product net sales + settlement bucket (line grain, doc bucket)
        out["product_breakdown"] = q("""
            SELECT ss.item_code, coalesce(pr.product_name, ss.item_code) product_name,
                   count(DISTINCT ss.doc_entry) docs, sum(ss.qty) qty, sum(ss.gross) gross,
                   sum(coalesce(cm.amt,0)) credits, sum(ss.gross)-sum(coalesce(cm.amt,0)) net,
                   sum(CASE WHEN cs.days_document_to_full_settlement=0 THEN ss.gross ELSE 0 END) same_day_gross,
                   sum(CASE WHEN cs.days_document_to_full_settlement>0 THEN ss.gross ELSE 0 END) delayed_gross
            FROM scoped_sales ss
            JOIN cs ON CAST(cs.doc_entry AS VARCHAR)=CAST(ss.doc_entry AS VARCHAR)
            LEFT JOIN prod pr ON pr.item_code=ss.item_code
            LEFT JOIN (SELECT CAST(s.doc_entry AS VARCHAR) de, s.item_code,
                              sum(c.credit_amount) amt
                       FROM scoped_sales s LEFT JOIN scoped_credits c
                         ON c.source_system=s.source_system AND try_cast(c.base_type AS INTEGER)=13
                        AND CAST(c.base_entry AS VARCHAR)=CAST(s.doc_entry AS VARCHAR)
                        AND CAST(c.base_line AS VARCHAR)=CAST(s.line_num AS VARCHAR) AND c.item_code=s.item_code
                       GROUP BY 1,2) cm ON cm.de=CAST(ss.doc_entry AS VARCHAR) AND cm.item_code=ss.item_code
            GROUP BY 1,2 ORDER BY net DESC""")

        out["seller_breakdown"] = q("""
            SELECT cs.slp_code, count(*) docs, sum(cs.gross) gross,
                   count(*) FILTER (WHERE cs.days_document_to_full_settlement=0) same_day_docs,
                   count(*) FILTER (WHERE cs.days_document_to_full_settlement>0) delayed_docs,
                   count(*) FILTER (WHERE cs.settlement_state<>'FULLY_SETTLED') open_docs
            FROM cs GROUP BY 1 ORDER BY gross DESC""")

        # cancelled / exclusion check on settlement side for cohort
        out["cancelled_check"] = q("SELECT settlement_state, cancelled, count(*) n FROM cs GROUP BY 1,2")
        out["reopen_check"] = q("""
            SELECT count(*) FILTER (WHERE open_amount_local>.01) still_open,
                   count(*) FILTER (WHERE settlement_state='FULLY_SETTLED' AND fully_settled_date IS NULL) missing_date
            FROM cs""")

        # amount-weighted & doc-weighted percentages
        out["pct"] = c.execute("""
            SELECT
              count(*) total_docs, sum(document_total_local) total_amt,
              count(*) FILTER (WHERE days_document_to_full_settlement=0) sd_docs,
              sum(document_total_local) FILTER (WHERE days_document_to_full_settlement=0) sd_amt,
              count(*) FILTER (WHERE days_document_to_full_settlement<=1) d1_docs,
              sum(document_total_local) FILTER (WHERE days_document_to_full_settlement<=1) d1_amt,
              count(*) FILTER (WHERE days_document_to_full_settlement<=7) d7_docs,
              count(*) FILTER (WHERE days_document_to_full_settlement<=30) d30_docs
            FROM cs""").fetchone()
        out["days_quantiles"] = c.execute("""
            SELECT min(days_document_to_full_settlement),
                   quantile_cont(days_document_to_full_settlement,0.25),
                   quantile_cont(days_document_to_full_settlement,0.5),
                   quantile_cont(days_document_to_full_settlement,0.75),
                   quantile_cont(days_document_to_full_settlement,0.9),
                   quantile_cont(days_document_to_full_settlement,0.95),
                   max(days_document_to_full_settlement)
            FROM cs WHERE settlement_state='FULLY_SETTLED' AND days_document_to_full_settlement IS NOT NULL""").fetchone()

    (EV / "explore3.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str)[:9000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
