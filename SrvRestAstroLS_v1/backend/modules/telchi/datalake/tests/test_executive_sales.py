from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from modules.telchi.datalake import executive_sales
from modules.telchi.datalake.create_initial import reconcile_candidate, transform


def _credit_row(**changes):
    row = {
        "DocEntry": 11, "DocNum": 9001, "DocDate": "2026-09-03", "CreateDate": "2026-09-03",
        "UpdateDate": "2026-09-04", "DocStatus": "C", "CANCELED": "N", "CardCode": "C1",
        "HeaderSlpCode": 7, "DocCur": "BS", "DocTotal": "100.00", "DocTotalSy": "14.00",
        "DocTotalFC": "0", "Series": 4, "UserSign": 145, "LineNum": 2, "LineStatus": "C",
        "ItemCode": "I1", "WhsCode": "W1", "Quantity": "-2", "LineCurrency": "BS",
        "LineTotal": "100.00", "TotalSumSy": "14.00", "TotalFrgn": "0", "LineSlpCode": 8,
        "BaseType": 13, "BaseEntry": 77, "BaseLine": 1,
    }
    return row | changes


def test_credit_memo_preserves_native_keys_amounts_and_cancellation_state():
    row = _credit_row(CANCELED="Y")
    candidate = transform("credit_memo", [row], {"extraction_id": "e1", "source_as_of": "t"})
    document = candidate.tables["credit_memo_document"][0]
    line = candidate.tables["credit_memo_line"][0]
    assert (document["doc_entry"], document["doc_num"], document["canceled"]) == ("11", 9001, "Y")
    assert (line["doc_entry"], line["line_num"], line["base_type"], line["base_entry"], line["base_line"]) == ("11", 2, 13, 77, 1)
    assert line["line_total"] == "100.00" and line["line_total_system"] == "14.00"
    assert line["slp_code"] == 8 and line["attributed_slp_code"] == 8
    assert reconcile_candidate(candidate, [row])["status"] == "EXACT"


def test_channel_dimensions_are_separate_and_unmapped_sign_fails_closed():
    assert executive_sales.classify_sales_channel(1248, 145) == ("HORIZONTAL", "CONFIRMED")
    assert executive_sales.classify_sales_channel(1265, 156) == ("SALON", "SUPPORTED")
    assert executive_sales.classify_sales_channel(999, 145) == (None, None)
    assert executive_sales.CORPORATE_CATEGORY_CODE == "2"
    assert executive_sales.CORPORATE_CATEGORY_NAME == "CORPORATIVO"


def test_corporate_query_uses_foundation_only_and_does_not_discover_semantics(monkeypatch):
    class Access:
        foundation_resolution_ms = 1.0
        foundation_publication_id = "foundation_test"
        foundation_data_as_of = "2026-09-24"

        def reference(self, name):
            assert name == "salespersons"
            return Path("/fixture/salespersons.parquet")

        def sales(self, name):
            assert name == "sales_document"
            return "(pinned_sales_documents)"

        def credit_memo(self, name):
            assert name == "credit_memo_document"
            return "(pinned_credit_memos)"

    class Reader:
        def __init__(self, connector):
            pass

        def resolve_on(self, connection):
            return Access()

    class Result:
        description = [(name,) for name in ("salesperson_name", "slp_code", "gross_invoice_sales", "credit_memo_amount", "net_invoice_sales_after_credit_memos")]

        def fetchall(self):
            return [("Seller", "7", 100, 25, 75)]

    class Connection:
        def execute(self, sql, params):
            assert "salesperson_category_code=?" in sql
            assert "ORDER BY net_invoice_sales_after_credit_memos DESC" in sql
            assert params[-1] == "2"
            return Result()

    class Connector:
        @contextmanager
        def session(self, *, read_only):
            assert read_only
            yield Connection()

    monkeypatch.setattr(executive_sales, "FoundationReader", Reader)
    result = executive_sales.corporate_sales_by_salesperson(year=2026, month=9, connector=Connector())
    assert result["rows"] == [{
        "salesperson_name": "Seller", "slp_code": "7", "gross_invoice_sales": "100.00",
        "credit_memo_amount": "25.00", "net_invoice_sales_after_credit_memos": "75.00",
    }]
    assert result["data_source"] == "DATA_LAKE_FOUNDATION"
    assert result["sap_accessed"] == "NO" and result["repo_discovery"] == "NO"
