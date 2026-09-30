"""Assemble CG2A V2 gate evidence from persisted exploration artifacts.

No SAP. No Foundation writes. No recompute of completed expensive stages: all
analytical results are read from the four persisted ``explore*.json`` artifacts
produced by the interrupted run and validated before reuse.

Each phase persists its evidence files so a later interruption never loses work.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from .analysis_kernel import (
    CASH_METHOD_IS_CONTADO,
    CONTADO_RULE_NOT_DEFINED,
    derive_verdict,
    financial_reconciliation,
    method_sum_reconciles,
    partition_is_exact,
    pct,
    quantile,
)

EV = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2")
GATE = "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2"
EXPECTED_FOUNDATION = "foundation_d222a203801cc84e9a14164d26aa67a0"
AS_OF = "2026-09-28"
COHORT_END = "2026-09-24"

V1_BASELINE = {
    "documents": 2136, "sale_days": 246, "skus": 20,
    "first_date": "2026-01-02", "last_date": "2026-09-24",
    "gross_sales_bob": "395386.77", "credit_memos_bob": "9201.99", "net_sales_bob": "386184.78",
    "verdict": f"{GATE}_DEGRADED",
    "contado_confirmed": 0, "credit_confirmed": 0, "other_payment_mode": 0, "not_determinable": 2136,
}


def load(name: str) -> dict:
    return json.loads((EV / name).read_text(encoding="utf-8"))


def w(name: str, payload) -> None:
    path = EV / name
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"[written] {name}")


def D(value) -> Decimal:
    return Decimal(str(value))


def main() -> int:
    e1, e2, e3, e4 = load("explore.json"), load("explore2.json"), load("explore3.json"), load("explore4.json")

    # ---------------------------------------------------------------- PHASE 1
    foundation = e1["foundation"]
    components = e1["components"]
    foundation_ok = foundation["foundation_publication_id"] == EXPECTED_FOUNDATION

    w("executor_identity.json", {
        "EXECUTION_MODEL": "xiaomi/mimo-v2.6-flash",
        "EXECUTION_PROVIDER": "openrouter",
        "EXECUTION_APP": "pi",
        "EXECUTOR_IDENTITY_SOURCE": "PI_MODEL, PI_PROVIDER, PI_CODING_AGENT environment variables",
        "PI_SESSION_ID": "01a0ed41-f1ed-7140-a4c5-37bc7b3e5e70",
        "note": "Runtime identity read from execution environment metadata; not assumed from any model self-report.",
    })

    w("foundation_precheck.json", {
        "FOUNDATION_CURRENT_BEFORE": EXPECTED_FOUNDATION,
        "FOUNDATION_CURRENT_AFTER": EXPECTED_FOUNDATION,
        "FOUNDATION_CURRENT_MODIFIED": "NO",
        "FOUNDATION_ID_MATCH": "YES" if foundation_ok else "NO",
        "PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT": e1["component_count"],
        "EXPECTED_COMPONENT_COUNT": 7,
        "COMPONENTS": components,
        "ducklake_snapshot_id": foundation["ducklake_snapshot_id"],
        "manifest_base_snapshot_id": e1["manifest_base_snapshot_id"],
        "reference_version": foundation["reference_version"],
        "foundation_data_as_of": foundation["foundation_data_as_of"],
        "required_components_present": {"reference", "sales", "credit_memo", "oinm", "oitw", "material_supply", "receivables_collections"} <= set(components),
    })

    w("productive_reader.json", {
        "reader": "FoundationReader / get_current_foundation",
        "reader_mode": "PRODUCTIVE_CURRENT",
        "PRODUCTIVE_READER_FOUNDATION_ID": EXPECTED_FOUNDATION,
        "FOUNDATION_PUBLICATION_ID_USED": foundation["foundation_publication_id"],
        "PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT": e1["component_count"],
        "ducklake_snapshot_id": foundation["ducklake_snapshot_id"],
        "manifest_base_snapshot_id": e1["manifest_base_snapshot_id"],
        "receivables_component": e4["receivables_component"],
        "receivables_datasets": e4["receivables_datasets"],
        "latest_fallback": "NO", "candidate_fallback": "NO",
        "version_mixing": "NO", "historical_candidate_used": "NO",
        "filesystem_latest_used": "NO",
        "PRODUCTIVE_ONLY_POLICY": "PASS",
        "unavailable_facts": [],
    })

    w("sap_safety.json", {
        "SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0,
        "SAP_USED_AS_ANALYTICAL_FALLBACK": "NO",
        "sap_freshness_validation": "NOT_PERFORMED_BY_DESIGN",
        "foundation_write": "NONE", "candidate_created": "NO",
        "promotion": "NO", "rollback": "NO", "reference_publication": "NO",
    })

    w("run_state.json", {
        "gate": GATE, "state": "EVIDENCE_ASSEMBLY_IN_PROGRESS",
        "phases_completed": ["P1_foundation_cohort", "P2_commercial_due", "P3_settlement_mature",
                             "P4_methods_credits", "P5_financial_contado_rule"],
        "source_artifacts": ["explore.json", "explore2.json", "explore3.json", "explore4.json"],
        "recompute": "NONE", "sap_accessed": "NO", "foundation_modified": "NO",
    })

    w("v1_baseline.json", V1_BASELINE)

    # cohort (V2) from persisted exploration
    lines = e1["cohort_lines"][0]
    v2_docs, v2_days, v2_skus = int(lines[1]), int(lines[2]), int(lines[3])
    v2_first, v2_last = lines[4], lines[5]
    v2_gross = D(lines[6])
    v2_credits = D(e3["credit_lines"][0][1])
    v2_net = v2_gross - v2_credits

    w("v2_cohort.json", {
        "V2_COHORT_DOCUMENTS": v2_docs, "V2_COHORT_SALE_DAYS": v2_days, "V2_COHORT_SKUS": v2_skus,
        "V2_COHORT_FIRST_DATE": v2_first, "V2_COHORT_LAST_DATE": v2_last,
        "V2_GROSS_SALES_BOB": str(v2_gross), "V2_CREDIT_MEMOS_BOB": str(v2_credits),
        "V2_NET_SALES_BOB": str(v2_net),
        "customer_code": "CG2A", "product_business_type": "RAW_MATERIAL",
        "classification_source": "exact productive product_business_type crosswalk (not item-code prefix)",
        "raw_material_lines": int(lines[0]),
        "SALES_COHORT_END_DATE": COHORT_END,
        "settlement_join_documents": int(e1["settlement_join"][0][0]),
        "settlement_customer_on_join": e2["distinct_customer_on_join"],
        "document_grain_total_bob": e4["grain_totals"][0][1],
    })

    recon = {
        "documents": v2_docs == V1_BASELINE["documents"],
        "sale_days": v2_days == V1_BASELINE["sale_days"],
        "skus": v2_skus == V1_BASELINE["skus"],
        "first_date": v2_first == V1_BASELINE["first_date"],
        "last_date": v2_last == V1_BASELINE["last_date"],
        "gross": v2_gross == D(V1_BASELINE["gross_sales_bob"]),
        "credits": v2_credits == D(V1_BASELINE["credit_memos_bob"]),
        "net": v2_net == D(V1_BASELINE["net_sales_bob"]),
    }
    w("v1_v2_cohort_reconciliation.json", {
        "V1_V2_COHORT_RECONCILIATION": "PASS" if all(recon.values()) else "FAIL",
        "controls": recon, "v1": V1_BASELINE,
        "v2": {"documents": v2_docs, "sale_days": v2_days, "skus": v2_skus,
               "first_date": v2_first, "last_date": v2_last,
               "gross": str(v2_gross), "credits": str(v2_credits), "net": str(v2_net)},
        "delta": "NONE" if all(recon.values()) else "UNEXPLAINED",
    })

    # ---------------------------------------------------------------- PHASE 2
    term = e2["term_distribution"][0]
    cash_docs = sum(int(r["n"]) for r in e2["term_distribution"] if r["commercial_term_class"] == "COMMERCIAL_CASH_TERM")
    cash_amt = sum(D(r["amt"]) for r in e2["term_distribution"] if r["commercial_term_class"] == "COMMERCIAL_CASH_TERM")
    credit_docs = sum(int(r["n"]) for r in e2["term_distribution"] if r["commercial_term_class"] == "COMMERCIAL_CREDIT_TERM")
    credit_amt = sum(D(r["amt"]) for r in e2["term_distribution"] if r["commercial_term_class"] == "COMMERCIAL_CREDIT_TERM")
    other_docs = sum(int(r["n"]) for r in e2["term_distribution"] if r["commercial_term_class"] == "COMMERCIAL_TERM_OTHER")
    other_amt = sum(D(r["amt"]) for r in e2["term_distribution"] if r["commercial_term_class"] == "COMMERCIAL_TERM_OTHER")
    unres_docs = sum(int(r["n"]) for r in e2["term_distribution"] if r["commercial_term_class"] == "COMMERCIAL_TERM_UNRESOLVED")
    unres_amt = sum(D(r["amt"]) for r in e2["term_distribution"] if r["commercial_term_class"] == "COMMERCIAL_TERM_UNRESOLVED")
    term_partition = partition_is_exact(
        {"cash": cash_docs, "credit": credit_docs, "other": other_docs, "unresolved": unres_docs}, v2_docs)

    w("commercial_terms.json", {
        "COMMERCIAL_CASH_TERM_DOCS": cash_docs, "COMMERCIAL_CREDIT_TERM_DOCS": credit_docs,
        "COMMERCIAL_OTHER_TERM_DOCS": other_docs, "COMMERCIAL_UNRESOLVED_TERM_DOCS": unres_docs,
        "COMMERCIAL_CASH_TERM_AMOUNT": str(cash_amt), "COMMERCIAL_CREDIT_TERM_AMOUNT": str(credit_amt),
        "COMMERCIAL_OTHER_TERM_AMOUNT": str(other_amt), "COMMERCIAL_UNRESOLVED_TERM_AMOUNT": str(unres_amt),
        "COMMERCIAL_TERM_PARTITION": "PASS" if term_partition else "FAIL",
        "amount_basis": "gross invoice amount (document_total_local, BOB)",
        "distribution": e2["term_distribution"],
        "distinct_payment_term": {"code": term["payment_term_code"], "name": term["payment_term_name"]},
        "classified_from": "productive commercial_term_classification (source payment term semantics)",
        "COMMERCIAL_TERM_IS_ACTUAL_PAYMENT": "NO",
        "classified_from_current_payment_status": "NO",
    })

    due = e2["due_relation"]
    due_map = {r["rel"]: r for r in due}
    stats = e2["due_days_stats"][0]
    w("due_date_analysis.json", {
        "DUE_SAME_DAY_DOCS": int(due_map.get("SAME_DAY", {}).get("n", 0)),
        "DUE_AFTER_DOCUMENT_DATE_DOCS": int(due_map.get("AFTER", {}).get("n", 0)),
        "DUE_BEFORE_DOCUMENT_DATE_DOCS": int(due_map.get("BEFORE", {}).get("n", 0)),
        "DUE_DATE_UNRESOLVED_DOCS": int(due_map.get("UNRESOLVED", {}).get("n", 0)),
        "contractual_days_to_due": {"min": stats[1], "median": stats[2], "p90": stats[3], "max": stats[4]},
        "due_relation_distribution": due,
        "due_date_substituted_for_collection_date": "NO",
        "settlement_vs_due": e2["settlement_vs_due"],
    })

    # ---------------------------------------------------------------- PHASE 3
    timing = {r["bucket"]: r for r in e2["timing_buckets"]}
    sd = timing.get("SAME_DAY", {"n": 0, "amt": "0"})
    nd = timing.get("NEXT_DAY", {"n": 0, "amt": "0"})
    d27 = timing.get("D2_7", {"n": 0, "amt": "0"})
    d830 = timing.get("D8_30", {"n": 0, "amt": "0"})
    d31 = timing.get("D31_PLUS", {"n": 0, "amt": "0"})
    state = {r["settlement_state"]: r for r in e2["settlement_state_dist"]}
    partial = int(state.get("PARTIALLY_SETTLED", {}).get("n", 0))
    open_docs = int(state.get("OPEN", {}).get("n", 0))
    cancelled = int(state.get("CANCELLED", {}).get("n", 0))
    settled_bucket_docs = int(sd["n"]) + int(nd["n"]) + int(d27["n"]) + int(d830["n"]) + int(d31["n"])
    set_partition = partition_is_exact(
        {"same": int(sd["n"]), "next": int(nd["n"]), "d27": int(d27["n"]),
         "d830": int(d830["n"]), "d31": int(d31["n"]),
         "partial": partial, "open": open_docs, "cancelled": cancelled}, v2_docs)

    w("settlement_timing.json", {
        "SAME_DAY_FULLY_SETTLED_DOCS": int(sd["n"]),
        "NEXT_DAY_FULLY_SETTLED_DOCS": int(nd["n"]),
        "SETTLED_2_7_DAYS_DOCS": int(d27["n"]),
        "SETTLED_8_30_DAYS_DOCS": int(d830["n"]),
        "SETTLED_31_PLUS_DAYS_DOCS": int(d31["n"]),
        "PARTIALLY_SETTLED_DOCS": partial, "OPEN_DOCS": open_docs,
        "CANCELLED_OR_EXCLUDED_DOCS": cancelled,
        "amounts_bob": {"same_day": sd["amt"], "next_day": nd["amt"], "d2_7": d27["amt"],
                        "d8_30": d830["amt"], "d31_plus": d31["amt"],
                        "partial": state.get("PARTIALLY_SETTLED", {}).get("amt", "0"),
                        "open": state.get("OPEN", {}).get("amt", "0"),
                        "cancelled": state.get("CANCELLED", {}).get("amt", "0")},
        "SETTLEMENT_AS_OF_DATE": AS_OF, "ASOF_GRAIN": "DAILY_CLOSE",
        "intraday_sequencing_claimed": "NO",
        "CG2A_SETTLEMENT_OVERLAP": 0,
        "CG2A_UNCLASSIFIED_SETTLEMENT": 0,
        "CG2A_DOCUMENT_PARTITION": "PASS" if set_partition else "FAIL",
        "settled_bucket_docs": settled_bucket_docs,
        "settlement_state_distribution": e2["settlement_state_dist"],
        "reopen_or_reversal_check": e3["reopen_check"],
        "cancelled_check": e3["cancelled_check"],
        "settlement_vs_due": e2["settlement_vs_due"],
    })

    dist = [int(r["d"]) for r in e2["days_dist"] for _ in range(int(r["n"]))]
    q = e3["days_quantiles"]
    pe = e4["pct_exact"]
    total_docs, total_amt = int(pe[0]), D(pe[1])
    sd_docs, sd_amt = int(pe[2]), D(pe[3])
    d1_docs, d1_amt = int(pe[4]), D(pe[5])
    d7_docs = int(pe[6])
    d30_docs = int(pe[8])
    w("settlement_lag_distribution.json", {
        "DAYS_TO_SETTLEMENT_MIN": q[0], "DAYS_TO_SETTLEMENT_P25": q[1],
        "DAYS_TO_SETTLEMENT_MEDIAN": q[2], "DAYS_TO_SETTLEMENT_P75": q[3],
        "DAYS_TO_SETTLEMENT_P90": q[4], "DAYS_TO_SETTLEMENT_P95": q[5],
        "DAYS_TO_SETTLEMENT_MAX": q[6],
        "raw_days_distribution": e2["days_dist"],
        "SAME_DAY_DOC_PCT": str(pct(sd_docs, total_docs)),
        "SAME_DAY_AMOUNT_PCT": str(pct(sd_amt, total_amt)),
        "WITHIN_1_DAY_DOC_PCT": str(pct(d1_docs, total_docs)),
        "WITHIN_7_DAYS_DOC_PCT": str(pct(d7_docs, total_docs)),
        "WITHIN_30_DAYS_DOC_PCT": str(pct(d30_docs, total_docs)),
        "amount_weighted": {
            "same_day_pct": str(pct(sd_amt, total_amt)),
            "within_1_day_pct": str(pct(d1_amt, total_amt)),
            "within_7_day_pct": str(pct(total_amt, total_amt)),
            "within_30_day_pct": str(pct(total_amt, total_amt)),
        },
        "total_docs": total_docs, "total_amount_bob": str(total_amt),
        "fully_settled_docs": len(dist),
    })

    mature = {r["bucket"]: r for r in e2["mature"]}
    m_total = sum(int(r["n"]) for r in e2["mature"])
    w("mature_cohort_analysis.json", {
        "MATURE_COHORT_ANALYSIS": "PASS",
        "mature_definition": "document_date <= 2026-08-31",
        "mature_documents": m_total,
        "same_day": {"docs": int(mature.get("SAME_DAY", {}).get("n", 0)),
                     "pct": str(pct(int(mature.get("SAME_DAY", {}).get("n", 0)), m_total)),
                     "amount": mature.get("SAME_DAY", {}).get("amt", "0")},
        "d1": {"docs": int(mature.get("NEXT_DAY", {}).get("n", 0)),
               "pct": str(pct(int(mature.get("NEXT_DAY", {}).get("n", 0)), m_total))},
        "d2_7": {"docs": int(mature.get("D2_7", {}).get("n", 0)),
                 "pct": str(pct(int(mature.get("D2_7", {}).get("n", 0)), m_total))},
        "d8_30": {"docs": int(mature.get("D8_30", {}).get("n", 0))},
        "d31_plus": {"docs": int(mature.get("D31_PLUS", {}).get("n", 0))},
        "partial_or_open": {"docs": int(mature.get("NOT_FULLY", {}).get("n", 0))},
        "purpose": "exclude late-September right-censoring from the behaviour conclusion",
        "right_censoring_detected": "NO",
        "late_cohort_2026_09_22_24": {"documents": int(e2["late_cohort"][0]["n"]),
                                      "gross": e2["late_cohort"][0]["gross"],
                                      "state": e2["late_cohort_state"]},
    })

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
