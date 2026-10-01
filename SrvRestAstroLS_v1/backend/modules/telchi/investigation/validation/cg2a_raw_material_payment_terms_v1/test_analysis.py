from pathlib import Path

from .run_analysis import GATE, derive_verdict, render_sql


HERE = Path(__file__).resolve().parent


def test_missing_transactional_payment_evidence_is_degraded_not_cash() -> None:
    assert derive_verdict(documents=2136, transactional_payment_datasets=0) == f"{GATE}_DEGRADED"


def test_empty_business_universe_is_blocked() -> None:
    assert derive_verdict(documents=0, transactional_payment_datasets=0) == f"{GATE}_BLOCKED"


def test_sql_classifies_absence_conservatively() -> None:
    sql = (HERE / "analysis.sql").read_text(encoding="utf-8")
    assert "'NOT_DETERMINABLE' AS payment_classification" in sql
    assert "'CONTADO_CONFIRMED' AS payment_classification" not in sql
    assert "'CREDIT_CONFIRMED' AS payment_classification" not in sql
    assert "LIKE '2A%'" not in sql


def test_sql_uses_exact_credit_memo_lineage_and_no_payment_term_inference() -> None:
    sql = (HERE / "analysis.sql").read_text(encoding="utf-8")
    assert "try_cast(c.base_type AS INTEGER) = 13" in sql
    assert "CAST(c.base_entry AS VARCHAR) = CAST(s.doc_entry AS VARCHAR)" in sql
    assert "payment_term_documental" in sql
    assert "CAST(NULL AS VARCHAR) AS payment_term_documental" in sql


def test_render_sql_rejects_unresolved_placeholders() -> None:
    try:
        render_sql("SELECT * FROM __MISSING__", {})
    except RuntimeError as exc:
        assert "unresolved SQL placeholders" in str(exc)
    else:
        raise AssertionError("render_sql must fail closed")
