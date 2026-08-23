"""Regression tests for the canonical fail-safe Flow Gmail query."""

from __future__ import annotations

import pytest

from modules.flow.escalate_once import _parser as escalate_parser
from modules.flow.mail_query import (
    DEFAULT_MAIL_CUTOFF_EPOCH,
    build_mail_query,
    build_mail_query_from_settings,
)
from modules.flow.poll_once import _parser as poll_parser
from modules.flow.run_automatic_once import _parser as automatic_parser


def test_configured_cutoff_uses_after_epoch() -> None:
    query = build_mail_query(
        mail_after_cutoff=True,
        mail_cutoff_epoch=DEFAULT_MAIL_CUTOFF_EPOCH,
    )
    assert query == "in:inbox after:1787239323"


def test_explicit_cutoff_opt_out_uses_inbox_only() -> None:
    query = build_mail_query(
        mail_after_cutoff=False,
        mail_cutoff_epoch=DEFAULT_MAIL_CUTOFF_EPOCH,
    )
    assert query == "in:inbox"


@pytest.mark.parametrize(
    "value",
    [None, "invalid", True, 0, -1, 9999999999],
)
def test_invalid_epoch_falls_back_to_canonical_safe_cutoff(value: object) -> None:
    query = build_mail_query(
        mail_after_cutoff=True,
        mail_cutoff_epoch=value,
    )
    assert query == "in:inbox after:1787239323"


@pytest.mark.parametrize("value", [None, "false", 0, 1])
def test_invalid_cutoff_toggle_remains_protected(value: object) -> None:
    query = build_mail_query(
        mail_after_cutoff=value,
        mail_cutoff_epoch=DEFAULT_MAIL_CUTOFF_EPOCH,
    )
    assert query == "in:inbox after:1787239323"


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"mail_after_cutoff": True},
        {"mail_cutoff_epoch": DEFAULT_MAIL_CUTOFF_EPOCH},
        {"mail_after_cutoff": True, "mail_cutoff_epoch": None},
        {"mail_after_cutoff": True, "mail_cutoff_epoch": "invalid"},
        {"mail_after_cutoff": None, "mail_cutoff_epoch": 0},
    ],
)
def test_missing_or_invalid_settings_fail_safe(settings: dict) -> None:
    query = build_mail_query_from_settings(settings)
    assert query == "in:inbox after:1787239323"


def test_query_never_uses_historical_negation() -> None:
    settings_cases = [
        {},
        {"mail_after_cutoff": True, "mail_cutoff_epoch": 1787239323},
        {"mail_after_cutoff": True, "mail_cutoff_epoch": -1},
        {"mail_after_cutoff": False, "mail_cutoff_epoch": 1787239323},
    ]
    for settings in settings_cases:
        query = build_mail_query_from_settings(settings)
        assert query.startswith("in:inbox")
        assert "-after:" not in query
        assert "before:" not in query


def test_cutoff_contract_excludes_historical_and_selects_new_mail() -> None:
    cutoff = DEFAULT_MAIL_CUTOFF_EPOCH
    historical_internal_date_ms = (cutoff - 1) * 1000
    new_internal_date_ms = (cutoff + 1) * 1000

    assert historical_internal_date_ms // 1000 <= cutoff
    assert new_internal_date_ms // 1000 > cutoff
    assert build_mail_query(
        mail_after_cutoff=True,
        mail_cutoff_epoch=cutoff,
    ) == f"in:inbox after:{cutoff}"


@pytest.mark.parametrize(
    "parser_factory",
    [poll_parser, automatic_parser, escalate_parser],
)
def test_manual_runners_default_to_postgres_cutoff_not_env(
    monkeypatch, parser_factory
) -> None:
    monkeypatch.setenv("TEAM360_FLOW_GMAIL_QUERY", "in:inbox")

    args = parser_factory().parse_args([])

    assert args.query is None
