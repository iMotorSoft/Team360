from modules.telchi.investigation.validation.datalake_direct_business_query_validation_v1.runner import (
    CUTOFF,
    END_EXCLUSIVE,
    GATE,
    _normal,
)


def test_gate_constants_and_cutoff_are_fixed():
    assert GATE == "TELCHI_DATALAKE_DIRECT_BUSINESS_QUERY_VALIDATION_V1"
    assert CUTOFF == "2026-09-15"
    assert END_EXCLUSIVE == "2026-09-16"


def test_decimal_and_null_normalization_is_exact_and_distinct():
    assert _normal([{"quantity": "1.00", "empty": "", "zero": "0", "missing": None}]) == [
        {"quantity": "1", "empty": "", "zero": "0", "missing": None}
    ]


def test_date_normalization_only_removes_time_component():
    assert _normal([{"doc_date": "2026-09-15T12:30:00", "value": "2026-09-15T12:30:00"}]) == [
        {"doc_date": "2026-09-15", "value": "2026-09-15T12:30:00"}
    ]
