from __future__ import annotations

from modules.telchi.datalake.update import live_sap_postcheck


class StableSource:
    def discover_2026_bounds(self, start):
        return {
            "sales_source_max_date": "2026-09-24",
            "oinm_source_max_date": "2026-09-24",
            "oitw_source_as_of": "2026-09-24T14:00:00+00:00",
            "oitw_source_row_count": 10,
        }

    def _execute(self, query_name, sql, params):
        if "sales" in query_name:
            return [{"DOCUMENT_COUNT": 20}]
        return [{"DOCUMENT_COUNT": 5}]


def test_live_postcheck_detects_same_day_new_documents_even_when_max_date_is_unchanged():
    result = live_sap_postcheck(
        StableSource(), "2026-09-24T13:00:00+00:00",
        captured_sales_documents=19, captured_credit_memo_documents=5,
    )
    assert result["SAP_CHANGED_AFTER_CAPTURE"] == "YES"
    assert result["status"] == "SOURCE_CHANGED"
    assert result["same_day_document_count_changed"] == "YES"


def test_live_postcheck_reports_stable_same_day_counts():
    result = live_sap_postcheck(
        StableSource(), "2026-09-24T13:00:00+00:00",
        captured_sales_documents=20, captured_credit_memo_documents=5,
    )
    assert result["SAP_CHANGED_AFTER_CAPTURE"] == "NO"
    assert result["status"] == "LIVE_CHECKED"
