from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compare_telchi_incoming_payments_parquet_hana as compare  # noqa: E402


def test_parquet_range_is_calculated_from_row_dates() -> None:
    rows = (
        (datetime(2023, 5, 8), 3, 10.0),
        (datetime(2022, 4, 2), 1, 20.0),
        (datetime(2023, 1, 1), 2, 30.0),
    )
    _, minimum, maximum = compare.build_metrics(rows)
    assert minimum == date(2022, 4, 2)
    assert maximum == date(2023, 5, 8)


def test_hana_query_is_bounded_by_parquet_max_date() -> None:
    class Cursor:
        parameters = None

        def execute(self, sql: str, parameters: tuple[str, str]) -> None:
            assert 'CAST("DocDate" AS DATE) <= ?' in sql
            self.parameters = parameters

        def fetchall(self) -> list[tuple[date, int, int, Decimal]]:
            return [(date(2023, 5, 31), 1, 1, Decimal("12.34"))]

    cursor = Cursor()
    result = compare.fetch_hana_daily(
        cursor,
        date(2022, 4, 1),
        date(2023, 5, 31),
    )
    assert cursor.parameters == ("2022-04-01", "2023-05-31")
    assert max(result) == date(2023, 5, 31)


def test_hana_result_after_parquet_max_is_rejected() -> None:
    class Cursor:
        def execute(self, sql: str, parameters: tuple[str, str]) -> None:
            pass

        def fetchall(self) -> list[tuple[date, int, int, Decimal]]:
            return [(date(2023, 6, 1), 1, 1, Decimal("1.00"))]

    with pytest.raises(RuntimeError, match="EXCEEDS_PARQUET_MAX_DATE"):
        compare.fetch_hana_daily(
            Cursor(), date(2022, 4, 1), date(2023, 5, 31)
        )


def test_missing_dates_are_aligned_with_zero_metrics() -> None:
    parquet = {date(2022, 4, 1): compare.Metrics(1, 1, Decimal("10.00"))}
    hana = {date(2022, 4, 2): compare.Metrics(2, 2, Decimal("20.00"))}
    result = compare.compare_daily(
        parquet,
        hana,
        date(2022, 4, 1),
        date(2022, 4, 2),
    )
    assert result[0].classifications == ("PARQUET_ONLY",)
    assert result[1].classifications == ("HANA_ONLY",)
    assert result[0].hana == compare.Metrics()
    assert result[1].parquet == compare.Metrics()


def test_differences_and_percentage_are_exact_decimal_values() -> None:
    parquet = {date(2022, 4, 1): compare.Metrics(2, 2, Decimal("10.00"))}
    hana = {date(2022, 4, 1): compare.Metrics(3, 3, Decimal("12.50"))}
    result = compare.compare_daily(
        parquet,
        hana,
        date(2022, 4, 1),
        date(2022, 4, 1),
    )[0]
    assert result.rows_diff == 1
    assert result.documents_diff == 1
    assert result.amount_diff == Decimal("2.50")
    assert result.amount_diff_pct == Decimal("25.0000")
    assert result.classifications == (
        "ROW_COUNT_DIFF",
        "DOCUMENT_COUNT_DIFF",
        "AMOUNT_DIFF",
    )


def test_decimal_conversion_avoids_binary_float_arithmetic() -> None:
    daily, _, _ = compare.build_metrics(
        (
            (date(2022, 4, 1), 1, 0.1),
            (date(2022, 4, 1), 2, 0.2),
        )
    )
    assert daily[date(2022, 4, 1)].amount == Decimal("0.30")


def test_script_never_prints_or_embeds_password_value() -> None:
    source = Path(compare.__file__).read_text(encoding="utf-8")
    forbidden_print = "print(" + "password"
    forbidden_interpolation = "f\"{" + "password"
    assert forbidden_print not in source.casefold()
    assert forbidden_interpolation not in source.casefold()
    assert "connection string" not in source.casefold()
