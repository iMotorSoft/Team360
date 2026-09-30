"""Focused tests for the CG2A raw-material payment-terms V2 analytical gate."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from modules.telchi.investigation.validation.cg2a_raw_material_payment_terms_v2.analysis_kernel import (
    CASH_METHOD_IS_CONTADO,
    CONTADO_RULE_NOT_DEFINED,
    CREDIT_SETTLED_SAME_DAY,
    DELAYED_SETTLEMENT,
    DUE_AFTER,
    DUE_BEFORE,
    DUE_SAME_DAY,
    DUE_UNRESOLVED,
    OPEN,
    OPEN_NOT_DUE,
    OPEN_OVERDUE,
    PARTIAL,
    SETTLED_AFTER_DUE,
    SETTLED_ON_OR_BEFORE_DUE,
    STRICT_IMMEDIATE,
    credit_memo_is_cash,
    derive_verdict,
    due_relation,
    financial_reconciliation,
    is_cash_method_contado,
    method_amounts_do_not_double_count,
    method_sum_reconciles,
    on_account_receipt_counts_as_settlement,
    partition_is_exact,
    pct,
    quantile,
    reconciliation_is_new_cash,
    settlement_timing_bucket,
    settlement_vs_due,
    strict_behavior_class,
)

EV = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2")
EXPECTED_FOUNDATION = "foundation_d222a203801cc84e9a14164d26aa67a0"


def _load(name: str):
    return json.loads((EV / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- pure kernel
def test_settlement_bucket_boundaries() -> None:
    assert settlement_timing_bucket("FULLY_SETTLED", 0) == "SAME_DAY"
    assert settlement_timing_bucket("FULLY_SETTLED", 1) == "NEXT_DAY"
    assert settlement_timing_bucket("FULLY_SETTLED", 2) == "D2_7"
    assert settlement_timing_bucket("FULLY_SETTLED", 7) == "D2_7"
    assert settlement_timing_bucket("FULLY_SETTLED", 8) == "D8_30"
    assert settlement_timing_bucket("FULLY_SETTLED", 30) == "D8_30"
    assert settlement_timing_bucket("FULLY_SETTLED", 31) == "D31_PLUS"
    assert settlement_timing_bucket("PARTIALLY_SETTLED", 0) == "NOT_FULLY"
    assert settlement_timing_bucket("OPEN", None) == "NOT_FULLY"
    assert settlement_timing_bucket("CANCELLED", 0) == "CANCELLED"


def test_due_date_boundary() -> None:
    assert due_relation(date(2026, 3, 1), date(2026, 3, 1)) == DUE_SAME_DAY
    assert due_relation(date(2026, 3, 1), date(2026, 3, 31)) == DUE_AFTER
    assert due_relation(date(2026, 3, 31), date(2026, 3, 1)) == DUE_BEFORE
    assert due_relation(date(2026, 3, 1), None) == DUE_UNRESOLVED


def test_same_day_vs_delayed_classification() -> None:
    # cash term + settled same day -> strict immediate
    assert strict_behavior_class(
        commercial_term_class="COMMERCIAL_CASH_TERM", settlement_state="FULLY_SETTLED",
        days_to_full_settlement=0, still_open=False) == STRICT_IMMEDIATE
    # credit term + settled same day -> commercial credit settled same day (NOT immediate)
    assert strict_behavior_class(
        commercial_term_class="COMMERCIAL_CREDIT_TERM", settlement_state="FULLY_SETTLED",
        days_to_full_settlement=0, still_open=False) == CREDIT_SETTLED_SAME_DAY
    # delayed
    assert strict_behavior_class(
        commercial_term_class="COMMERCIAL_CASH_TERM", settlement_state="FULLY_SETTLED",
        days_to_full_settlement=3, still_open=False) == DELAYED_SETTLEMENT
    # partial / open / cancelled / unresolved
    assert strict_behavior_class(
        commercial_term_class="COMMERCIAL_CASH_TERM", settlement_state="PARTIALLY_SETTLED",
        days_to_full_settlement=None, still_open=True) == PARTIAL
    assert strict_behavior_class(
        commercial_term_class="COMMERCIAL_CASH_TERM", settlement_state="OPEN",
        days_to_full_settlement=None, still_open=True) == OPEN
    assert strict_behavior_class(
        commercial_term_class="COMMERCIAL_CASH_TERM", settlement_state="CANCELLED",
        days_to_full_settlement=None, still_open=False) == "CANCELLED_OR_EXCLUDED"
    # a later reversal that reopens the receivable must not count as immediate
    assert strict_behavior_class(
        commercial_term_class="COMMERCIAL_CASH_TERM", settlement_state="FULLY_SETTLED",
        days_to_full_settlement=0, still_open=False, reopened_by_reversal=True) == "UNRESOLVED"


def test_settlement_vs_due_relations() -> None:
    assert settlement_vs_due("FULLY_SETTLED", date(2026, 3, 1), date(2026, 3, 1),
                             date(2026, 9, 28)) == SETTLED_ON_OR_BEFORE_DUE
    assert settlement_vs_due("FULLY_SETTLED", date(2026, 3, 10), date(2026, 3, 1),
                             date(2026, 9, 28)) == SETTLED_AFTER_DUE
    assert settlement_vs_due("OPEN", None, date(2026, 9, 30),
                             date(2026, 9, 28)) == OPEN_NOT_DUE
    assert settlement_vs_due("OPEN", None, date(2026, 1, 1),
                             date(2026, 9, 28)) == OPEN_OVERDUE


def test_cash_method_is_not_contado() -> None:
    assert is_cash_method_contado() == "NO"
    assert CASH_METHOD_IS_CONTADO == "NO"


def test_credit_memo_is_not_cash_and_reconciliation_is_not_new_cash() -> None:
    assert credit_memo_is_cash() is False
    assert reconciliation_is_new_cash() is False


def test_on_account_semantics() -> None:
    # receipt date alone never settles; economic application is the gating event
    assert on_account_receipt_counts_as_settlement(date(2026, 3, 1), None) is False
    assert on_account_receipt_counts_as_settlement(date(2026, 3, 1), date(2026, 3, 5)) is True


def test_payment_method_no_double_count() -> None:
    # a mixed payment contributes each method exactly once
    mixed = [{"collection_method": "CASH"}, {"collection_method": "TRANSFER"}]
    assert method_amounts_do_not_double_count(mixed) is True
    # the same method appearing twice is rejected
    dup = [{"collection_method": "CASH"}, {"collection_method": "CASH"}]
    assert method_amounts_do_not_double_count(dup) is False


def test_method_sum_reconciles_and_financial_identity() -> None:
    assert method_sum_reconciles("568049.970000", "568049.970000") is True
    # a delta of exactly 0.01 is within the monetary tolerance
    assert method_sum_reconciles("568049.97", "568049.96") is True
    # a delta above 0.01 breaks the reconciliation
    assert method_sum_reconciles("568049.97", "568049.94") is False
    assert financial_reconciliation(
        document_total="585345.56", payment_effect="568049.97",
        credit_memo_effect="17295.59", internal_effect="0", multi_source_effect="0") is True
    assert financial_reconciliation(
        document_total="585345.56", payment_effect="100000",
        credit_memo_effect="0", internal_effect="0", multi_source_effect="0") is False


def test_partition_and_percent_helpers() -> None:
    assert partition_is_exact({"a": 2134, "b": 2}, 2136) is True
    assert partition_is_exact({"a": 2134, "b": 1}, 2136) is False
    assert partition_is_exact({"a": -1, "b": 2137}, 2136) is False
    assert pct(2134, 2136) == Decimal("99.9064")
    assert quantile([0, 1, 2], 0.5) == 1


def test_mature_cohort_sensitivity_excludes_right_censoring() -> None:
    mature = _load("mature_cohort_analysis.json")
    assert mature["MATURE_COHORT_ANALYSIS"] == "PASS"
    assert mature["mature_documents"] == 1911
    assert int(mature["late_cohort_2026_09_22_24"]["documents"]) == 21
    # all 21 late-September documents are fully settled, so censoring does not distort
    assert all(r["settlement_state"] == "FULLY_SETTLED"
               for r in mature["late_cohort_2026_09_22_24"]["state"])


# --------------------------------------------------- persisted evidence gates
def test_v1_v2_cohort_reconciliation_pass() -> None:
    recon = _load("v1_v2_cohort_reconciliation.json")
    assert recon["V1_V2_COHORT_RECONCILIATION"] == "PASS"
    assert all(recon["controls"].values())
    v2 = recon["v2"]
    assert v2["documents"] == 2136
    assert v2["sale_days"] == 246
    assert v2["skus"] == 20
    assert v2["first_date"] == "2026-01-02"
    assert v2["last_date"] == "2026-09-24"
    assert Decimal(v2["gross"]) == Decimal("395386.77")
    assert Decimal(v2["credits"]) == Decimal("9201.99")
    assert Decimal(v2["net"]) == Decimal("386184.78")


def test_exact_cohort_filters_cg2a_only_and_raw_material_only() -> None:
    cohort = _load("v2_cohort.json")
    assert cohort["customer_code"] == "CG2A"
    assert cohort["product_business_type"] == "RAW_MATERIAL"
    assert cohort["classification_source"].startswith("exact productive product_business_type")
    # all joined settlement rows are CG2A
    assert cohort["settlement_customer_on_join"] == [{"customer_code": "CG2A", "n": 2136}]


def test_commercial_term_partition_pass_and_all_cash() -> None:
    comm = _load("commercial_terms.json")
    assert comm["COMMERCIAL_TERM_PARTITION"] == "PASS"
    assert comm["COMMERCIAL_CASH_TERM_DOCS"] == 2136
    assert comm["COMMERCIAL_CREDIT_TERM_DOCS"] == 0
    assert comm["COMMERCIAL_OTHER_TERM_DOCS"] == 0
    assert comm["COMMERCIAL_UNRESOLVED_TERM_DOCS"] == 0
    assert comm["COMMERCIAL_TERM_IS_ACTUAL_PAYMENT"] == "NO"
    assert comm["classified_from_current_payment_status"] == "NO"


def test_settlement_partition_pass_and_overlap_zero() -> None:
    settle = _load("settlement_timing.json")
    assert settle["CG2A_DOCUMENT_PARTITION"] == "PASS"
    assert settle["CG2A_SETTLEMENT_OVERLAP"] == 0
    assert settle["CG2A_UNCLASSIFIED_SETTLEMENT"] == 0
    assert settle["SAME_DAY_FULLY_SETTLED_DOCS"] == 2134
    assert settle["NEXT_DAY_FULLY_SETTLED_DOCS"] == 1
    assert settle["SETTLED_2_7_DAYS_DOCS"] == 1
    assert settle["SETTLED_8_30_DAYS_DOCS"] == 0
    assert settle["SETTLED_31_PLUS_DAYS_DOCS"] == 0
    assert settle["PARTIALLY_SETTLED_DOCS"] == 0
    assert settle["OPEN_DOCS"] == 0
    assert settle["CANCELLED_OR_EXCLUDED_DOCS"] == 0
    total = (2134 + 1 + 1 + 0 + 0 + 0 + 0 + 0)
    assert total == 2136


def test_due_date_evidence_all_same_day() -> None:
    due = _load("due_date_analysis.json")
    assert due["DUE_SAME_DAY_DOCS"] == 2136
    assert due["DUE_AFTER_DOCUMENT_DATE_DOCS"] == 0
    assert due["DUE_BEFORE_DOCUMENT_DATE_DOCS"] == 0
    assert due["DUE_DATE_UNRESOLVED_DOCS"] == 0
    assert due["contractual_days_to_due"] == {"max": 0, "median": 0.0, "min": 0, "p90": 0.0}
    assert due["due_date_substituted_for_collection_date"] == "NO"


def test_collection_method_reconciliation_and_no_double_count() -> None:
    methods = _load("collection_methods.json")
    assert methods["CG2A_COLLECTION_METHOD_RECONCILIATION"] == "PASS"
    assert Decimal(methods["method_total"]) == Decimal(methods["payment_settlement_effect"])
    assert methods["CG2A_CASH_COLLECTED"] == "236513.620000"
    assert methods["CG2A_TRANSFER_COLLECTED"] == "251446.410000"
    assert methods["CG2A_CARD_COLLECTED"] == "74874.940000"
    assert methods["CG2A_CHECK_COLLECTED"] == "5215.000000"
    assert methods["CG2A_OTHER_COLLECTED"] in ("0", "0.000000")
    assert methods["CG2A_UNRESOLVED_METHOD"] in ("0", "0.000000")
    mixed = _load("mixed_payment_validation.json")
    assert mixed["CG2A_MIXED_METHOD_DOUBLE_COUNT"] == 0
    assert mixed["method_total_equals_payment_effect"] is True


def test_qr_remains_unresolved_and_not_inferred() -> None:
    qr = _load("qr_limitation.json")
    assert qr["QR_COLLECTION_STATUS"] == "UNRESOLVED_SOURCE_EVIDENCE"
    assert qr["QR_IS_NOT_INFERRED"] == "YES"
    assert qr["QR_IS_NOT_INFERRED_FROM_TRANSFER"] == "YES"
    assert qr["QR_IS_NOT_INFERRED_FROM_BANK_ACCOUNT"] == "YES"
    assert qr["QR_IS_NOT_INFERRED_FROM_TEXT"] == "YES"
    assert qr["qr_blocks_gate"] == "NO"


def test_credit_memo_not_cash_and_amount_revalidated() -> None:
    credit = _load("credit_memo_analysis.json")
    assert credit["CREDIT_MEMO_COUNTED_AS_CASH"] == "NO"
    assert credit["CREDIT_MEMO_COUNTED_AS_COLLECTION"] == "NO"
    assert credit["credit_memo_is_cash"] is False
    assert Decimal(credit["CG2A_CREDIT_MEMO_AMOUNT"]) == Decimal("9201.99")
    assert credit["CG2A_CREDIT_MEMO_DOCS_OR_LINKS"] == 14
    assert credit["credit_link_ratio"] == "14/14"


def test_reconciliation_not_counted_as_new_collection() -> None:
    rec = _load("reconciliation_analysis.json")
    assert rec["RECONCILIATION_COUNTED_AS_NEW_COLLECTION"] == "NO"
    assert rec["reconciliation_is_new_cash"] is False
    assert Decimal(rec["internal_reconciliation_effect"]) == Decimal(0)


def test_on_account_evidence_zero_for_cohort() -> None:
    oa = _load("on_account_analysis.json")
    assert oa["CG2A_ON_ACCOUNT_PAYMENT_COUNT"] == 0
    assert Decimal(oa["CG2A_ON_ACCOUNT_RECEIVED_AMOUNT"]) == Decimal(0)
    assert oa["CG2A_LATER_RECONCILED_AMOUNT"] in ("0", "0.000000")
    assert oa["receipt_date_counts_as_settlement_date"] == "NO"


def test_financial_and_method_reconciliations_pass() -> None:
    fin = _load("financial_reconciliation.json")
    assert fin["CG2A_FINANCIAL_RECONCILIATION"] == "PASS"
    assert Decimal(fin["residual_unexplained"]) == Decimal(0)
    assert fin["document_grain"]["remaining_open_balance"] == "0.000000"
    assert fin["raw_material_line_grain"]["identity"] == "net_sales = gross_sales - credit_memos"
    method = _load("method_reconciliation.json")
    assert method["CG2A_METHOD_SUM_RECONCILIATION"] == "PASS"
    assert Decimal(method["delta"]) == Decimal(0)


def test_strict_behavior_partition_pass_and_not_named_contado() -> None:
    strict = _load("strict_payment_behavior_classification.json")
    assert strict["STRICT_PAYMENT_BEHAVIOR_PARTITION"] == "PASS"
    assert strict["STRICT_IMMEDIATE_SETTLEMENT_DOCS"] == 2134
    assert strict["DELAYED_SETTLEMENT_DOCS"] == 2
    assert strict["COMMERCIAL_CREDIT_SETTLED_SAME_DAY_DOCS"] == 0
    assert strict["PARTIAL_DOCS"] == 0
    assert strict["OPEN_DOCS"] == 0
    assert strict["named_contado_confirmed"] == "NO"
    assert strict["same_day_is_not_automatically_contado"] == "YES"
    parts = strict["partitions"]
    assert sum(parts.values()) == 2136


def test_contado_rule_searched_and_not_fabricated() -> None:
    contado = _load("contado_business_rule_search.json")
    assert contado["TELCHI_CONTADO_RULE_STATUS"] == "NO_APPROVED_RULE_FOUND"
    assert contado["FINAL_CONTADO_CLASSIFICATION_RULE"] == CONTADO_RULE_NOT_DEFINED
    assert contado["no_rule_fabricated"] == "YES"
    assert contado["web_or_sap_used"] == "NO"
    assert contado["component_flag"] == "NO"


def test_open_debt_partition_and_cohort_zero() -> None:
    debt = _load("current_open_debt.json")
    assert debt["SETTLEMENT_AS_OF_DATE"] == "2026-09-28"
    assert debt["ASOF_GRAIN"] == "DAILY_CLOSE"
    assert debt["CG2A_OPEN_DEBT_PARTITION"] == "PASS"
    assert Decimal(debt["CG2A_TOTAL_OPEN_RECEIVABLES"]) == Decimal(0)
    assert Decimal(debt["CG2A_CURRENT_RECEIVABLES"]) == Decimal(0)
    assert Decimal(debt["CG2A_OVERDUE_RECEIVABLES"]) == Decimal(0)
    assert debt["cohort_open_documents"] == 0


def test_productive_only_reader_and_foundation_unchanged() -> None:
    pre = _load("foundation_precheck.json")
    assert pre["FOUNDATION_CURRENT_BEFORE"] == EXPECTED_FOUNDATION
    assert pre["FOUNDATION_CURRENT_AFTER"] == EXPECTED_FOUNDATION
    assert pre["FOUNDATION_CURRENT_MODIFIED"] == "NO"
    assert pre["FOUNDATION_ID_MATCH"] == "YES"
    assert pre["PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT"] == 7
    assert pre["required_components_present"] is True
    reader = _load("productive_reader.json")
    assert reader["PRODUCTIVE_READER_FOUNDATION_ID"] == EXPECTED_FOUNDATION
    assert reader["PRODUCTIVE_ONLY_POLICY"] == "PASS"
    assert reader["latest_fallback"] == "NO"
    assert reader["candidate_fallback"] == "NO"
    assert reader["version_mixing"] == "NO"
    assert reader["unavailable_facts"] == []


def test_no_sap_access() -> None:
    sap = _load("sap_safety.json")
    assert sap["SAP_ACCESSED"] == "NO"
    assert sap["SAP_QUERY_COUNT"] == 0
    assert sap["SAP_WRITE_COUNT"] == 0
    assert sap["SAP_USED_AS_ANALYTICAL_FALLBACK"] == "NO"


def test_location_channel_seller_not_payment_evidence() -> None:
    loc = _load("location_channel_control.json")
    assert loc["LOCATION_USED_AS_PAYMENT_EVIDENCE"] == "NO"
    assert loc["CHANNEL_USED_AS_PAYMENT_EVIDENCE"] == "NO"
    assert loc["matches_expected"] is True
    seller = _load("seller_control.json")
    assert seller["SELLER_USED_AS_PAYMENT_EVIDENCE"] == "NO"


def test_v1_result_preserved_as_historically_correct() -> None:
    v1 = _load("v1_vs_v2_explanation.json")
    assert v1["V1_RESULT_PRESERVED_AS_HISTORICALLY_CORRECT"] == "YES"
    assert v1["V1_was_wrong"] == "NO"
    assert v1["V1_data_lake_capability_changed"] == "YES"
    assert v1["cohort_reconciliation"] == "PASS"


def test_same_day_evidence_matrix_partitions_cohort() -> None:
    matrix = _load("same_day_evidence_matrix.json")
    assert matrix["matrix_partition_ok"] is True
    assert matrix["A_COMMERCIAL_CASH_TERM_SETTLED_SAME_DAY"]["docs"] == 2134
    assert matrix["B_COMMERCIAL_CASH_TERM_SETTLED_LATER"]["docs"] == 2
    assert matrix["C_COMMERCIAL_CREDIT_TERM_SETTLED_SAME_DAY"]["docs"] == 0
    assert matrix["G_ANY_TERM_PARTIAL_OR_OPEN"]["docs"] == 0
    assert matrix["cash_term_is_contado"] == "NO"


def test_derive_verdict_degraded_without_approved_rule() -> None:
    assert derive_verdict(
        contado_rule_status="NO_APPROVED_RULE_FOUND", foundation_ok=True, cohort_ok=True,
        financial_ok=True, method_ok=True, partitions_ok=True) == "DEGRADED"
    assert derive_verdict(
        contado_rule_status="APPROVED_EXISTING_RULE", foundation_ok=True, cohort_ok=True,
        financial_ok=True, method_ok=True, partitions_ok=True) == "PASS"
    # any broken safety/reconciliation invariant is a FAIL regardless of the rule
    assert derive_verdict(
        contado_rule_status="APPROVED_EXISTING_RULE", foundation_ok=False, cohort_ok=True,
        financial_ok=True, method_ok=True, partitions_ok=True) == "FAIL"
    assert derive_verdict(
        contado_rule_status="NO_APPROVED_RULE_FOUND", foundation_ok=True, cohort_ok=True,
        financial_ok=False, method_ok=True, partitions_ok=True) == "FAIL"


def test_verdict_emitted_is_exactly_one_and_degraded() -> None:
    verdict = _load("verdict.json")
    assert verdict["VERDICT"] == "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2_DEGRADED"
    assert verdict["foundation_ok"] is True
    assert verdict["cohort_ok"] is True
    assert verdict["financial_ok"] is True
    assert verdict["method_ok"] is True
    assert verdict["partitions_ok"] is True
    assert verdict["FOUNDATION_CURRENT_MODIFIED"] == "NO"
    assert verdict["SAP_ACCESSED"] == "NO"


def test_required_outputs_block_complete() -> None:
    req = _load("required_outputs.json")
    assert req["FOUNDATION_CURRENT"] == EXPECTED_FOUNDATION
    assert req["PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT"] == 7
    assert req["PRODUCTIVE_ONLY_POLICY"] == "PASS"
    assert req["V1_V2_COHORT_RECONCILIATION"] == "PASS"
    assert req["COMMERCIAL_TERM_PARTITION"] == "PASS"
    assert req["CG2A_DOCUMENT_PARTITION"] == "PASS"
    assert req["CG2A_OPEN_DEBT_PARTITION"] == "PASS"
    assert req["STRICT_PAYMENT_BEHAVIOR_PARTITION"] == "PASS"
    assert req["CG2A_FINANCIAL_RECONCILIATION"] == "PASS"
    assert req["CG2A_METHOD_SUM_RECONCILIATION"] == "PASS"
    assert req["CG2A_MIXED_METHOD_DOUBLE_COUNT"] == 0
    assert req["QR_COLLECTION_STATUS"] == "UNRESOLVED_SOURCE_EVIDENCE"
    assert req["TELCHI_CONTADO_RULE_STATUS"] == "NO_APPROVED_RULE_FOUND"
    assert req["VERDICT"].endswith("_DEGRADED")
