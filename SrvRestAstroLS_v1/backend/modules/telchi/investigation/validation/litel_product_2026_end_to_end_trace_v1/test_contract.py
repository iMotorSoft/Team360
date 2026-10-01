from __future__ import annotations

from decimal import Decimal

from .runner import (
    END_EXCLUSIVE,
    HISTORICAL_CUTOFF,
    GATE,
    _selection_sql,
    compare_rowsets,
    historical_predicate,
    normalize,
)


def test_litel_selection_uses_reference_v2_not_runtime_prefix():
    sql = _selection_sql()
    assert "reference/_versions/v2" in sql
    assert "product_portfolio_family" in sql
    assert "pf.code = 'LITEL'" in sql
    assert "LIKE 'L%'" not in sql


def test_cutoff_is_fixed_and_half_open():
    assert HISTORICAL_CUTOFF == "2026-09-15"
    assert END_EXCLUSIVE == "2026-09-16"
    assert historical_predicate('doc_date') == 'doc_date >= ? AND doc_date < ?'
    assert "2026-09-16" in _selection_sql()


def test_sales_rowset_comparison_is_deterministic_by_source_key():
    left = [{"DocEntry": 2, "LineNum": 0, "Quantity": Decimal("1.00")}, {"DocEntry": 1, "LineNum": 0, "Quantity": "2"}]
    right = [{"doc_entry": "1", "line_num": "0", "quantity": "2.000"}, {"doc_entry": "2", "line_num": "0", "quantity": "1"}]
    result = compare_rowsets(left, right, ("doc_entry", "line_num"))
    assert result["status"] == "EXACT"
    assert result["sap_hash"] == result["ducklake_hash"]


def test_oinm_rowset_comparison_preserves_transnum_transseq():
    result = compare_rowsets(
        [{"TransNum": 7, "TransSeq": 2, "InQty": "1.0"}],
        [{"trans_num": "7", "trans_seq": "2", "in_qty": "1"}],
        ("trans_num", "trans_seq"),
    )
    assert result["status"] == "EXACT"


def test_source_key_fields_are_not_dropped_by_normalization():
    row = normalize([{"TransNum": 8, "TransSeq": 3, "AppObjAbs": 99, "AppObjType": 13}])[0]
    assert row["trans_num"] == "8"
    assert row["trans_seq"] == "3"
    assert row["app_obj_abs"] == "99"


def test_no_fuzzy_sales_oinm_linking_contract():
    assert "fuzzy" not in _selection_sql().lower()
    # The runner only marks AppObjAbs/AppObjType links as explicit; this test
    # protects the source-key rule at the contract level.
    assert "AppObjAbs" in open(__import__('pathlib').Path(__file__).with_name('runner.py'), encoding='utf-8').read()


def test_oitw_current_state_label_is_explicit():
    source = open(__import__('pathlib').Path(__file__).with_name('runner.py'), encoding='utf-8').read()
    assert '"OITW_CURRENT_STATE_ONLY": "YES"' in source
    assert "stock at the historical cutoff" in source


def test_no_sap_writes_or_ai_invocations_in_runner():
    source = open(__import__('pathlib').Path(__file__).with_name('runner.py'), encoding='utf-8').read().upper()
    assert "SAP_WRITE_COUNT" in source
    assert "AI_INVOCATIONS" in source
    assert "INSERT " not in source and " UPDATE " not in source and " DELETE " not in source
    assert GATE in source
