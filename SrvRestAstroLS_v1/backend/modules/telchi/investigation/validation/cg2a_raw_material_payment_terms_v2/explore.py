"""Read-only exploration of productive Foundation for CG2A V2 (no writes, no SAP)."""
from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

EV = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2")
EXPECTED = "foundation_d222a203801cc84e9a14164d26aa67a0"


def rows(cur):
    names = [c[0] for c in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def main() -> int:
    conn = DuckLakeConnector()
    out = {}
    with conn.session(read_only=True) as c:
        c.execute("SET threads=1")
        access = FoundationReader(conn).resolve_on(c)
        out["foundation"] = access.as_dict()
        comps = sorted((access.manifest.get("components") or {}).keys())
        out["components"] = comps
        out["component_count"] = len(comps)

        rels = {
            "sales_document": access.sales("sales_document"),
            "sales_line": access.sales("sales_line"),
            "credit_memo_document": access.credit_memo("credit_memo_document"),
            "credit_memo_line": access.credit_memo("credit_memo_line"),
            "settlement": access.receivables_collections("receivable_settlement_status"),
            "method": access.receivables_collections("collection_method_fact"),
            "term": access.receivables_collections("commercial_term_classification"),
        }
        base = int(access.manifest_base_snapshot_id)
        atomic_bridge = {
            "allocation": f'(SELECT * FROM telchi.atomic."collection_allocation" AT (VERSION => {base}))',
            "payment": f'(SELECT * FROM telchi.atomic."collection_payment" AT (VERSION => {base}))',
            "recon_participant": f'(SELECT * FROM telchi.atomic."reconciliation_participant" AT (VERSION => {base}))',
            "receivable_document": f'(SELECT * FROM telchi.atomic."receivable_document" AT (VERSION => {base}))',
        }
        schemas = {}
        for name, rel in {**rels, **atomic_bridge}.items():
            try:
                schemas[name] = [r[0] for r in c.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()]
                schemas[name + "_count"] = int(c.execute(f"SELECT count(*) FROM {rel}").fetchone()[0])
            except Exception as e:  # noqa: BLE001
                schemas[name] = f"ERROR: {e}"
        out["schemas"] = schemas
        # manifest components detail
        out["manifest_components_detail"] = {
            k: {kk: vv for kk, vv in v.items() if kk in ("publication_id", "datasets", "row_count", "final_contado_business_rule_defined", "qr_source_status")}
            for k, v in (access.manifest.get("components") or {}).items() if isinstance(v, dict)
        }
        out["manifest_base_snapshot_id"] = base

        # Cohort build
        pbt_path = (access.manifest.get("product_business_classification") or {}).get("crosswalk_path")
        out["pbt_path"] = pbt_path
        c.execute(f"CREATE TEMP VIEW pbt AS SELECT * FROM read_parquet('{str(pbt_path).replace(chr(39), chr(39)*2)}')")
        cohort_sql = f"""
        SELECT d.doc_entry, CAST(d.doc_date AS DATE) AS doc_date, CAST(d.doc_due_date AS DATE) AS doc_due_date,
               d.doc_status, d.canceled, d.currency, d.sales_channel_name, d.slp_code, l.item_code, l.whs_code,
               try_cast(l.quantity AS DECIMAL(38,6)) AS qty, try_cast(l.line_total AS DECIMAL(38,6)) AS gross
        FROM {rels['sales_document']} d
        JOIN {rels['sales_line']} l ON l.source_system=d.source_system AND l.doc_entry=d.doc_entry
        JOIN pbt p ON p.ItemCode=l.item_code AND p.product_business_type='RAW_MATERIAL'
        WHERE d.card_code='CG2A' AND coalesce(d.canceled,'N')<>'Y'
          AND CAST(d.doc_date AS DATE)>=DATE '2026-01-01' AND CAST(d.doc_date AS DATE)<DATE '2027-01-01'
        """
        c.execute(f"CREATE TEMP VIEW cohort_lines AS {cohort_sql}")
        out["cohort_lines"] = c.execute("""
          SELECT count(*) lines, count(DISTINCT doc_entry) docs, count(DISTINCT doc_date) AS sale_days,
                 count(DISTINCT item_code) skus, min(doc_date) AS first_date, max(doc_date) AS last_date,
                 sum(gross) gross
          FROM cohort_lines""").fetchall()

        # link to settlement
        c.execute(f"CREATE TEMP VIEW cohort AS SELECT doc_entry, min(doc_date) doc_date, min(doc_due_date) doc_due_date, sum(gross) gross FROM cohort_lines GROUP BY 1")
        out["settlement_join"] = c.execute(f"""
          SELECT count(*) FROM cohort ch JOIN {rels['settlement']} s ON CAST(s.document_id AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR)
        """).fetchall()
        out["settlement_cg2a_total"] = c.execute(f"SELECT count(*) FROM {rels['settlement']} WHERE customer_code='CG2A'").fetchone()
        out["settlement_sample"] = c.execute(f"SELECT * FROM {rels['settlement']} WHERE customer_code='CG2A' LIMIT 3").fetchall()
        out["settlement_cols"] = schemas["settlement"]
        out["method_cols"] = schemas["method"]
        out["term_sample"] = c.execute(f"SELECT payment_term_code,payment_term_name,commercial_term_class FROM {rels['term']} LIMIT 20").fetchall()

        # cohort settlement commercial terms
        out["cohort_terms"] = c.execute(f"""
          SELECT coalesce(t.commercial_term_class,'NO_TERM') cls, count(DISTINCT ch.doc_entry) docs, sum(s.document_total_local) amt
          FROM cohort ch JOIN {rels['settlement']} s ON CAST(s.document_id AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR)
          LEFT JOIN {rels['term']} t USING(payment_term_code)
          GROUP BY 1 ORDER BY 2 DESC""").fetchall()

        out["cohort_settlement_state"] = c.execute(f"""
          SELECT s.settlement_state, count(*) docs, sum(s.document_total_local) amt
          FROM cohort ch JOIN {rels['settlement']} s ON CAST(s.document_id AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR)
          GROUP BY 1 ORDER BY 2 DESC""").fetchall()

        # allocation linkage
        out["alloc_join"] = c.execute(f"""
          SELECT count(DISTINCT ch.doc_entry) docs_with_alloc
          FROM cohort ch JOIN {atomic_bridge['allocation']} a
            ON CAST(a.target_doc_entry AS VARCHAR)=CAST(ch.doc_entry AS VARCHAR) AND a.target_object_type='13'""").fetchall()

        # method fact for CG2A
        out["method_cg2a"] = c.execute(f"""
          SELECT collection_method, sum(effective_amount_local) amt, count(DISTINCT payment_id) pays
          FROM {rels['method']} WHERE customer_code='CG2A' GROUP BY 1 ORDER BY 2 DESC""").fetchall()

        # Does cohort doc_entry overlap with all CG2A settlement docs?
        out["cg2a_settlement_docs"] = c.execute(f"SELECT count(DISTINCT document_id) FROM {rels['settlement']} WHERE customer_code='CG2A'").fetchone()

    EV.mkdir(parents=True, exist_ok=True)
    (EV / "explore.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str)[:8000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
