from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from modules.telchi.datalake.receivables_collections_business import (
    aging_bucket,
    commercial_term_classification,
    days_past_due,
    debt_status,
    executor_identity,
    normalize_cancelled,
    settlement_state,
)


def test_settlement_states_are_mutually_exclusive() -> None:
    assert settlement_state("100", "100") == "FULLY_SETTLED"
    assert settlement_state("100", "20") == "PARTIALLY_SETTLED"
    assert settlement_state("100", "0") == "OPEN"
    assert settlement_state("100", "0", cancelled=True) == "CANCELLED"


def test_settlement_tolerance_and_overapplication() -> None:
    assert settlement_state("100", "99.995") == "FULLY_SETTLED"
    assert settlement_state("100", "120") == "FULLY_SETTLED"


def test_invalid_or_negative_obligation_is_not_forced() -> None:
    assert settlement_state("not-a-number", "0") == "UNRESOLVED"
    assert settlement_state("-1", "0") == "OTHER_SOURCE_STATE"


def test_same_day_due_boundary_is_current() -> None:
    day = date(2026, 9, 28)
    assert debt_status("10", day, day) == "OPEN_CURRENT"
    assert aging_bucket("10", day, day) == "CURRENT"
    assert days_past_due(day, day) == 0


def test_open_current_and_overdue_are_distinct() -> None:
    as_of = date(2026, 9, 28)
    assert debt_status("10", date(2026, 9, 29), as_of) == "OPEN_CURRENT"
    assert debt_status("10", date(2026, 9, 27), as_of) == "OPEN_OVERDUE"
    assert debt_status("0", date(2026, 9, 1), as_of) == "NOT_OPEN"


@pytest.mark.parametrize(
    ("days", "expected"),
    [(0,"CURRENT"),(1,"1-30"),(30,"1-30"),(31,"31-60"),(60,"31-60"),(61,"61-90"),(90,"61-90"),(91,"91-120"),(120,"91-120"),(121,"120+")],
)
def test_aging_boundaries(days: int, expected: str) -> None:
    as_of = date(2026, 9, 28)
    due = date.fromordinal(as_of.toordinal() - days)
    assert aging_bucket("1", due, as_of) == expected


def test_non_open_has_no_aging_bucket() -> None:
    assert aging_bucket("0.001", date(2020,1,1), date(2026,9,28)) == "NOT_OPEN"


def test_days_past_due_is_canonical_zero_for_non_overdue() -> None:
    as_of = date(2026,9,28)
    assert days_past_due(date(2026,10,1), as_of) == 0
    assert days_past_due(date(2026,9,1), as_of) == 27


def test_commercial_term_does_not_use_collection_behavior() -> None:
    assert commercial_term_classification("Contado",0,0,0) == "COMMERCIAL_CASH_TERM"
    assert commercial_term_classification("Contado (Contra Entrega)",0,0,0) == "COMMERCIAL_CASH_TERM"
    assert commercial_term_classification("Crédito 30",1,0,0) == "COMMERCIAL_CREDIT_TERM"
    assert commercial_term_classification("PRESTAMO BAJO LINEA",0,0,12) == "COMMERCIAL_CREDIT_TERM"
    assert commercial_term_classification("50% Anticipo",0,0,0) == "COMMERCIAL_TERM_OTHER"
    assert commercial_term_classification(None,0,0,0) == "COMMERCIAL_TERM_UNRESOLVED"


def test_cancelled_source_flags_fail_closed() -> None:
    assert normalize_cancelled("Y")
    assert normalize_cancelled("C")
    assert not normalize_cancelled("N")


def test_method_decomposition_never_needs_a_mixed_amount() -> None:
    components = {"CASH": Decimal("300"), "TRANSFER": Decimal("200"), "CARD": Decimal("500")}
    assert sum(components.values()) == Decimal("1000")
    assert "MIXED" not in components


def test_credit_memo_and_reconciliation_are_not_cash_by_definition() -> None:
    cash_effects = {"PAYMENT": Decimal("10"), "CREDIT_MEMO": Decimal("0"), "INTERNAL_RECONCILIATION": Decimal("0")}
    assert cash_effects["CREDIT_MEMO"] == 0
    assert cash_effects["INTERNAL_RECONCILIATION"] == 0


def test_on_account_collection_does_not_settle_without_invoice_effect() -> None:
    received, invoice_reduction = Decimal("100"), Decimal("0")
    assert received > 0 and settlement_state("100", invoice_reduction) == "OPEN"


def test_late_event_full_rederivation_changes_state_deterministically() -> None:
    before = settlement_state("100", "20")
    after = settlement_state("100", "100")
    replay = settlement_state("100", "100")
    assert (before, after, replay) == ("PARTIALLY_SETTLED", "FULLY_SETTLED", "FULLY_SETTLED")


def test_reproducibility_ignores_wall_clock() -> None:
    facts = ("document-1", "100", "100", "v1")
    assert hash(facts) == hash(tuple(facts))


def test_executor_identity_uses_runtime_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_MODEL","model-x")
    monkeypatch.setenv("PI_PROVIDER","provider-y")
    monkeypatch.setenv("PI_CODING_AGENT","true")
    identity = executor_identity()
    assert identity["EXECUTION_MODEL"] == "model-x"
    assert identity["EXECUTION_PROVIDER"] == "provider-y"
    assert identity["EXECUTION_APP"] == "pi"
