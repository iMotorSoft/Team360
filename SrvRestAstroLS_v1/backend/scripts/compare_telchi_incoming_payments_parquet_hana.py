"""Compare historical Telchi incoming-payment Parquet with current SAP HANA.

The legacy definition is reproduced exactly: one ORCT row per payment, DocDate
as the business date, DocEntry as the document key and DocTotal as local amount.
Canceled rows are intentionally retained because the legacy extractor retained
them. The script is read-only and never writes HANA or Parquet.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from smoke_telchi_sap_hana import (
    HANA_HOST,
    HANA_PORT,
    HANA_SCHEMA,
    HANA_USER,
    PRIVATE_ENV_FILE,
    SmokeBlocked,
    load_private_config,
    tcp_preflight,
)


PARQUET_ROOT = Path(
    "/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS"
)
PARQUET_PATTERN = "paymentB1-*.parq"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")

HANA_RANGE_SQL = '''
SELECT MIN("DocDate"), MAX("DocDate")
  FROM "TELCHI"."ORCT"
'''

HANA_DAILY_SQL = '''
SELECT CAST("DocDate" AS DATE) AS "PaymentDate",
       COUNT(*) AS "Rows",
       COUNT(DISTINCT "DocEntry") AS "Documents",
       SUM("DocTotal") AS "Amount"
  FROM "TELCHI"."ORCT"
 WHERE CAST("DocDate" AS DATE) >= ?
   AND CAST("DocDate" AS DATE) <= ?
 GROUP BY CAST("DocDate" AS DATE)
 ORDER BY CAST("DocDate" AS DATE)
'''


@dataclass(frozen=True)
class Metrics:
    rows: int = 0
    documents: int = 0
    amount: Decimal = ZERO

    def __add__(self, other: "Metrics") -> "Metrics":
        return Metrics(
            rows=self.rows + other.rows,
            documents=self.documents + other.documents,
            amount=money(self.amount + other.amount),
        )


@dataclass(frozen=True)
class DailyComparison:
    day: date
    parquet: Metrics
    hana: Metrics
    rows_diff: int
    documents_diff: int
    amount_diff: Decimal
    amount_diff_pct: Decimal | None
    classifications: tuple[str, ...]

    @property
    def matches(self) -> bool:
        return self.classifications == ("MATCH",)


@dataclass(frozen=True)
class ParquetEvidence:
    files: tuple[Path, ...]
    columns: tuple[str, ...]
    types: tuple[str, ...]
    minimum: date
    maximum: date
    daily: Mapping[date, Metrics]
    canceled: Mapping[str, int]


def money(value: Decimal | int | str | float) -> Decimal:
    """Normalize a local-currency amount to the observed two-decimal scale."""

    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("NON_FINITE_AMOUNT")
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_EVEN)


def to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def build_metrics(rows: Iterable[tuple[Any, Any, Any]]) -> tuple[dict[date, Metrics], date, date]:
    """Build daily metrics from payment date, document key and local amount."""

    row_counts: dict[date, int] = defaultdict(int)
    documents: dict[date, set[int]] = defaultdict(set)
    amounts: dict[date, Decimal] = defaultdict(lambda: ZERO)
    minimum: date | None = None
    maximum: date | None = None
    for raw_day, raw_document, raw_amount in rows:
        if raw_day is None or raw_document is None or raw_amount is None:
            raise ValueError("PARQUET_REQUIRED_FIELD_NULL")
        day = to_date(raw_day)
        row_counts[day] += 1
        documents[day].add(int(raw_document))
        amounts[day] += money(raw_amount)
        minimum = day if minimum is None or day < minimum else minimum
        maximum = day if maximum is None or day > maximum else maximum
    if minimum is None or maximum is None:
        raise SmokeBlocked("TELCHI_PAYMENT_PARQUET_EMPTY")
    daily = {
        day: Metrics(row_counts[day], len(documents[day]), money(amounts[day]))
        for day in row_counts
    }
    return daily, minimum, maximum


def load_parquet_evidence(root: Path = PARQUET_ROOT) -> ParquetEvidence:
    files = tuple(sorted(root.glob(PARQUET_PATTERN)))
    if not files:
        raise SmokeBlocked("TELCHI_PAYMENT_PARQUET_NOT_FOUND")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SmokeBlocked("PYARROW_REQUIRED_USE_UV_WITH_PYARROW") from exc

    expected: tuple[str, ...] | None = None
    types: tuple[str, ...] | None = None
    selected_tables = []
    canceled: dict[str, int] = defaultdict(int)
    for path in files:
        table = pq.read_table(
            path,
            columns=["DocDate", "DocEntry", "DocTotal", "Canceled"],
        )
        full_schema = pq.read_schema(path)
        names = tuple(full_schema.names)
        current_types = tuple(str(field.type) for field in full_schema)
        if expected is None:
            expected = names
            types = current_types
        elif names != expected or current_types != types:
            raise SmokeBlocked(f"PARQUET_SCHEMA_MISMATCH:{path.name}")
        selected_tables.append(table.select(["DocDate", "DocEntry", "DocTotal"]))
        for value in table["Canceled"]:
            canceled[str(value.as_py())] += 1

    combined = pa.concat_tables(selected_tables, promote_options="default")
    raw_rows = zip(
        (value.as_py() for value in combined["DocDate"]),
        (value.as_py() for value in combined["DocEntry"]),
        (value.as_py() for value in combined["DocTotal"]),
        strict=True,
    )
    daily, minimum, maximum = build_metrics(raw_rows)
    return ParquetEvidence(
        files=files,
        columns=expected or (),
        types=types or (),
        minimum=minimum,
        maximum=maximum,
        daily=daily,
        canceled=dict(sorted(canceled.items())),
    )


def fetch_hana_daily(cursor: Any, start: date, end: date) -> dict[date, Metrics]:
    if end < start:
        raise ValueError("INVALID_COMPARISON_RANGE")
    cursor.execute(HANA_DAILY_SQL, (start.isoformat(), end.isoformat()))
    daily: dict[date, Metrics] = {}
    for raw_day, rows, documents, amount in cursor.fetchall():
        day = to_date(raw_day)
        if day > end:
            raise RuntimeError("HANA_RESULT_EXCEEDS_PARQUET_MAX_DATE")
        daily[day] = Metrics(int(rows), int(documents), money(amount or ZERO))
    return daily


def classify(parquet: Metrics, hana: Metrics) -> tuple[str, ...]:
    if parquet == hana:
        return ("MATCH",)
    if parquet.rows and not hana.rows:
        return ("PARQUET_ONLY",)
    if hana.rows and not parquet.rows:
        return ("HANA_ONLY",)
    labels: list[str] = []
    if parquet.rows != hana.rows:
        labels.append("ROW_COUNT_DIFF")
    if parquet.documents != hana.documents:
        labels.append("DOCUMENT_COUNT_DIFF")
    if parquet.amount != hana.amount:
        labels.append("AMOUNT_DIFF")
    return tuple(labels or ("NEEDS_DETAIL_ANALYSIS",))


def compare_daily(
    parquet: Mapping[date, Metrics],
    hana: Mapping[date, Metrics],
    start: date,
    end: date,
) -> list[DailyComparison]:
    comparisons: list[DailyComparison] = []
    for day in date_range(start, end):
        parquet_metrics = parquet.get(day, Metrics())
        hana_metrics = hana.get(day, Metrics())
        amount_diff = money(hana_metrics.amount - parquet_metrics.amount)
        amount_diff_pct = None
        if parquet_metrics.amount != ZERO:
            amount_diff_pct = (
                amount_diff / parquet_metrics.amount * Decimal("100")
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
        comparisons.append(
            DailyComparison(
                day=day,
                parquet=parquet_metrics,
                hana=hana_metrics,
                rows_diff=hana_metrics.rows - parquet_metrics.rows,
                documents_diff=hana_metrics.documents - parquet_metrics.documents,
                amount_diff=amount_diff,
                amount_diff_pct=amount_diff_pct,
                classifications=classify(parquet_metrics, hana_metrics),
            )
        )
    return comparisons


def aggregate(comparisons: Sequence[DailyComparison]) -> tuple[Metrics, Metrics]:
    parquet = Metrics()
    hana = Metrics()
    for comparison in comparisons:
        parquet += comparison.parquet
        hana += comparison.hana
    return parquet, hana


def aggregate_monthly(
    comparisons: Sequence[DailyComparison],
) -> list[tuple[str, Metrics, Metrics]]:
    parquet: dict[str, Metrics] = defaultdict(Metrics)
    hana: dict[str, Metrics] = defaultdict(Metrics)
    for comparison in comparisons:
        month = comparison.day.strftime("%Y-%m")
        parquet[month] = parquet[month] + comparison.parquet
        hana[month] = hana[month] + comparison.hana
    return [(month, parquet[month], hana[month]) for month in sorted(parquet)]


def format_metrics(metrics: Metrics) -> str:
    return (
        f"rows={metrics.rows} documents={metrics.documents} "
        f"amount={metrics.amount:.2f}"
    )


def print_report(
    evidence: ParquetEvidence,
    hana_minimum: date,
    hana_maximum: date,
    comparisons: Sequence[DailyComparison],
    show_daily: bool,
) -> None:
    comparison_start = comparisons[0].day
    comparison_end = comparisons[-1].day
    parquet_total, hana_total = aggregate(comparisons)
    different = [row for row in comparisons if not row.matches]
    matches = len(comparisons) - len(different)
    match_pct = (
        Decimal(matches) / Decimal(len(comparisons)) * Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    first_difference = different[0].day if different else None
    last_difference = different[-1].day if different else None
    last_match_before = None
    if first_difference:
        prior = [row.day for row in comparisons if row.day < first_difference and row.matches]
        last_match_before = prior[-1] if prior else None

    print(f"PARQUET DATASET             {PARQUET_ROOT / PARQUET_PATTERN}")
    print(f"PARQUET FILES               {len(evidence.files)}")
    print(f"PARQUET COLUMNS             {','.join(evidence.columns)}")
    print(f"PARQUET TYPES               {','.join(evidence.types)}")
    print(
        "PARQUET CANCELED           "
        + ",".join(f"{key}={value}" for key, value in evidence.canceled.items())
    )
    print(f"PARQUET MIN DATE            {evidence.minimum}")
    print(f"PARQUET MAX DATE            {evidence.maximum}")
    print(f"HANA MIN DATE               {hana_minimum}")
    print(f"HANA MAX DATE               {hana_maximum}")
    print(f"COMPARISON START            {comparison_start}")
    print(f"COMPARISON END              {comparison_end}")
    print("COMPARISON END SOURCE       PARQUET_MAX_DATE")
    print(f"PARQUET MACRO               {format_metrics(parquet_total)}")
    print(f"HANA MACRO                  {format_metrics(hana_total)}")
    print(f"ROWS DIFF                   {hana_total.rows - parquet_total.rows}")
    print(f"DOCUMENTS DIFF              {hana_total.documents - parquet_total.documents}")
    print(f"AMOUNT DIFF                 {money(hana_total.amount - parquet_total.amount):.2f}")
    print(f"TOTAL DAYS COMPARED         {len(comparisons)}")
    print(f"MATCHING DAYS               {matches}")
    print(f"DIFFERENT DAYS              {len(different)}")
    print(f"MATCHING DAYS PCT           {match_pct}")
    print(f"FIRST DIFFERENCE DATE       {first_difference or 'NONE'}")
    print(f"LAST MATCH BEFORE DIFF      {last_match_before or 'NONE'}")
    print(f"LAST DIFFERENCE DATE        {last_difference or 'NONE'}")

    label_counts: dict[str, int] = defaultdict(int)
    for comparison in different:
        for label in comparison.classifications:
            label_counts[label] += 1
    for label in (
        "ROW_COUNT_DIFF",
        "DOCUMENT_COUNT_DIFF",
        "AMOUNT_DIFF",
        "PARQUET_ONLY",
        "HANA_ONLY",
        "NEEDS_DETAIL_ANALYSIS",
    ):
        print(f"DIFF {label:<20} {label_counts[label]}")

    print("MONTHLY DIFFERENCES")
    for month, parquet, hana in aggregate_monthly(comparisons):
        if parquet != hana:
            print(
                f"{month} parquet=({format_metrics(parquet)}) "
                f"hana=({format_metrics(hana)}) "
                f"diff=({hana.rows-parquet.rows},"
                f"{hana.documents-parquet.documents},"
                f"{money(hana.amount-parquet.amount):.2f})"
            )

    if show_daily:
        print("DAILY COMPARISON")
        for row in comparisons:
            pct = "N/A" if row.amount_diff_pct is None else str(row.amount_diff_pct)
            print(
                f"{row.day} parquet=({format_metrics(row.parquet)}) "
                f"hana=({format_metrics(row.hana)}) "
                f"diff=({row.rows_diff},{row.documents_diff},{row.amount_diff:.2f},"
                f"{pct}%) class={'|'.join(row.classifications)}"
            )


def run_comparison(show_daily: bool = False) -> None:
    evidence = load_parquet_evidence()
    tcp_preflight()
    config = load_private_config(PRIVATE_ENV_FILE)
    password = config.pop("TELCHI_SAP_HANA_PASSWORD")
    connection = None
    cursor = None
    try:
        from hdbcli import dbapi

        connection = dbapi.connect(
            address=HANA_HOST,
            port=HANA_PORT,
            user=HANA_USER,
            password=password,
        )
        password = ""
        config.clear()
        connection.setautocommit(False)
        cursor = connection.cursor()
        cursor.execute(HANA_RANGE_SQL)
        raw_minimum, raw_maximum = cursor.fetchone()
        hana_minimum = to_date(raw_minimum)
        hana_maximum = to_date(raw_maximum)
        comparison_start = max(evidence.minimum, hana_minimum)
        comparison_end = evidence.maximum
        hana_daily = fetch_hana_daily(cursor, comparison_start, comparison_end)
        comparisons = compare_daily(
            evidence.daily,
            hana_daily,
            comparison_start,
            comparison_end,
        )
        if comparisons[-1].day != evidence.maximum:
            raise RuntimeError("COMPARISON_END_IS_NOT_PARQUET_MAX_DATE")
        print_report(
            evidence,
            hana_minimum,
            hana_maximum,
            comparisons,
            show_daily,
        )
    finally:
        password = ""
        config.clear()
        if cursor is not None:
            cursor.close()
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-daily",
        action="store_true",
        help="Print every aligned day; default output keeps macro/monthly evidence.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_comparison(show_daily=args.show_daily)
    except (SmokeBlocked, ValueError, RuntimeError) as exc:
        print("TEAM360_TELCHI_INCOMING_PAYMENTS_PARQUET_HANA_PARITY_BLOCKED")
        print(f"BLOCKER: {exc}")
        return 2
    print("TEAM360_TELCHI_INCOMING_PAYMENTS_PARQUET_HANA_COMPARE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
