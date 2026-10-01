from modules.telchi.investigation.validation.treasury_cash_bank_deposit.treasury_cash_bank_deposit_v1 import (
    TOLERANCE,
    account_classification,
    bucket_lag,
    deposit_type,
    match_level,
    tender_method,
)


def test_tender_method_keeps_mixed_separate():
    assert tender_method(100, 0, 0, 0) == "CASH"
    assert tender_method(0, 0, 100, 0) == "BANK_TRANSFER"
    assert tender_method(40, 0, 60, 0) == "MIXED"
    assert tender_method(0, 0, 0, 0, 1) == "OTHER"


def test_deposit_type_is_explicit_and_conservative():
    assert deposit_type("C") == "CASH"
    assert deposit_type("K") == "CHECK"
    assert deposit_type("V") == "CREDIT_CARD"
    assert deposit_type("unknown") == "OTHER"


def test_account_classification_requires_evidence_for_proven():
    assert account_classification("BANCO FIE CTA MN", "1111006", {"HOUSE_BANK"}) == ("BANK", "PROVEN")
    assert account_classification("Cajas Casa Matriz MN", "1110201", {"ORCT_CASH"}) == ("CASH", "PROVEN")
    assert account_classification("Transferencias por Confirmar", "1120301", set()) == ("TRANSIT_CLEARING", "STRONG")


def test_link_levels_never_upgrade_ambiguous_matches():
    assert match_level(1, exact=False) == "STRONG_MATCH"
    assert match_level(1, exact=True) == "EXACT_LINK"
    assert match_level(2) == "HEURISTIC_MATCH"
    assert match_level(0) == "NO_LINK_AVAILABLE"


def test_cash_deposit_buckets_are_exhaustive():
    assert bucket_lag(0) == "SAME_DAY"
    assert bucket_lag(1) == "1_DAY"
    assert bucket_lag(2) == "2_DAYS"
    assert bucket_lag(3) == "3_DAYS"
    assert bucket_lag(7) == "4_7_DAYS"
    assert bucket_lag(15) == "8_15_DAYS"
    assert bucket_lag(30) == "16_30_DAYS"
    assert bucket_lag(31) == ">30_DAYS"
    assert bucket_lag(None) == "UNKNOWN"
    assert TOLERANCE == 0.01
