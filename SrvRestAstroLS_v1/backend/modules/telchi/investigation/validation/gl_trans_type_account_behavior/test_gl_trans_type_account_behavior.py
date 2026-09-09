from modules.telchi.investigation.validation.gl_trans_type_account_behavior.gl_trans_type_account_behavior_v1 import (
    OBJECT_CANDIDATES,
    bucket_days,
    classify_journal,
    economic_classification,
)


def test_observed_object_catalog_has_exact_21_entries():
    assert len(OBJECT_CANDIDATES) == 21
    assert {"-3", "-2", "13", "30", "321"} <= set(OBJECT_CANDIDATES)


def test_manual_rule_is_reproducible_and_not_type_only():
    assert classify_journal("30", "O", "N")[0] == "MANUAL_JOURNAL_ENTRY"
    assert classify_journal("30", "I", "N")[0] == "INTEGRATION_GENERATED"
    assert classify_journal("30", "O", "Y")[0] == "SYSTEM_GENERATED"
    assert classify_journal("13", "O", "N")[0] == "DOCUMENT_GENERATED"


def test_unknown_origin_is_not_silently_manual():
    assert classify_journal("999", None, None)[0] == "UNCERTAIN"


def test_posting_timing_buckets():
    assert bucket_days(None) == "UNKNOWN"
    assert bucket_days(0) == "same_day"
    assert bucket_days(1) == "1_day"
    assert bucket_days(7) == "2_7_days"
    assert bucket_days(30) == "8_30_days"
    assert bucket_days(31) == ">30_days"


def test_economic_classification_preserves_sap_group_and_interpretation():
    assert economic_classification({"ACCTCODE": "2140105", "ACCTNAME": "IUE bienes", "GROUPMASK": "2"})[0] == "PASIVO.IMPUESTOS"
    assert economic_classification({"ACCTCODE": "1130205", "ACCTNAME": "Almacén Retención", "GROUPMASK": "1"})[0] == "ACTIVO.INVENTARIO"
    assert economic_classification({"ACCTCODE": "1111001", "ACCTNAME": "Banco BMSC", "GROUPMASK": "1"})[0] == "ACTIVO.BANCO"
    assert economic_classification({"ACCTCODE": "999", "ACCTNAME": "Cuenta transitoria", "GROUPMASK": "1"})[0] == "REVIEW.SEMANTIC_RISK"
    assert economic_classification({"ACCTCODE": "499", "ACCTNAME": "Ventas", "GROUPMASK": "4"})[0] == "INGRESOS"
