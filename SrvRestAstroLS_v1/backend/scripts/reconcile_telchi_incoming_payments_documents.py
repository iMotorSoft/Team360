"""Reconcile historical Telchi incoming-payment documents with current HANA.

The probe is read-only.  It keeps the legacy ORCT definition, separates dates
present in both sources from physically absent Parquet dates, compares the
preserved fields for common DocEntry values, and uses external snapshot/HANA
timestamps only as diagnostic evidence.  It never writes either source.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from compare_telchi_incoming_payments_parquet_hana import (
    CENT,
    HANA_HOST,
    HANA_PORT,
    HANA_USER,
    PARQUET_PATTERN,
    PARQUET_ROOT,
    PRIVATE_ENV_FILE,
    SmokeBlocked,
    load_private_config,
    money,
    tcp_preflight,
    to_date,
)


START_DATE = date(2022, 4, 1)
END_DATE = date(2023, 5, 31)

LEGACY_FIELDS = (
    "TransId",
    "CashSum",
    "TrsfrSum",
    "CreditSum",
    "CheckSum",
    "DocTotal",
    "DocTotalFC",
    "DocEntry",
    "DocNum",
    "DocType",
    "Canceled",
    "DocDate",
    "DocTime",
    "DocDueDate",
    "TaxDate",
    "ClientCode",
    "ClientName",
    "Ref1",
    "Comments",
    "JrnlMemo",
)
MONEY_FIELDS = frozenset(
    {"CashSum", "TrsfrSum", "CreditSum", "CheckSum", "DocTotal", "DocTotalFC"}
)
DATE_FIELDS = frozenset({"DocDate", "DocDueDate", "TaxDate"})
INTEGER_FIELDS = frozenset({"TransId", "DocEntry", "DocNum", "DocTime"})

HANA_DOCUMENT_SQL = '''
SELECT "TransId", "CashSum", "TrsfrSum", "CreditSum", "CheckSum",
       "DocTotal", "DocTotalFC", "DocEntry", "DocNum", "DocType",
       "Canceled", "DocDate", "DocTime", "DocDueDate", "TaxDate",
       "CardCode", "CardName", "Ref1", "Comments", "JrnlMemo",
       CAST("CreateDate" AS DATE), "CreateTS",
       CAST("UpdateDate" AS DATE), "UpdateTS"
  FROM "TELCHI"."ORCT"
 WHERE "DocDate" >= ?
   AND "DocDate" <= ?
'''

CURRENT_DOCUMENT_KEYS_SQL = '''
SELECT "DocEntry"
  FROM "TELCHI"."ORCT"
 WHERE CAST("DocDate" AS DATE) >= ?
   AND CAST("DocDate" AS DATE) <= ?
'''

HANA_MONEY_METADATA_SQL = '''
SELECT "COLUMN_NAME", "DATA_TYPE_NAME", "SCALE"
  FROM "SYS"."TABLE_COLUMNS"
 WHERE "SCHEMA_NAME" = 'TELCHI'
   AND "TABLE_NAME" = 'ORCT'
   AND "COLUMN_NAME" IN ('DocTotal', 'DocTotalFC')
 ORDER BY "COLUMN_NAME"
'''

HANA_OBSERVED_SCALE_SQL = '''
SELECT SUM(CASE WHEN "DocTotal" != ROUND("DocTotal", 2) THEN 1 ELSE 0 END),
       SUM(CASE WHEN "DocTotalFC" != ROUND("DocTotalFC", 2) THEN 1 ELSE 0 END)
  FROM "TELCHI"."ORCT"
 WHERE "DocDate" >= ?
   AND "DocDate" <= ?
'''


@dataclass(frozen=True)
class PaymentDocument:
    values: Mapping[str, Any]
    create_at: datetime | None = None
    update_at: datetime | None = None

    @property
    def key(self) -> int:
        return int(self.values["DocEntry"])

    @property
    def day(self) -> date:
        return to_date(self.values["DocDate"])


@dataclass(frozen=True)
class SnapshotEvidence:
    path: Path
    month: str
    filesystem_mtime: datetime
    rows: int
    data_minimum: date
    data_maximum: date
    minimum_key: int
    maximum_key: int


@dataclass(frozen=True)
class SourceDocuments:
    documents: tuple[PaymentDocument, ...]
    by_key: Mapping[int, PaymentDocument]
    duplicate_keys: Mapping[int, int]
    duplicate_keys_by_day: Mapping[date, Mapping[int, int]]
    snapshots: Mapping[str, SnapshotEvidence]


@dataclass(frozen=True)
class FieldParity:
    exact: int
    amount_changed: int
    date_changed: int
    canceled_changed: int
    other_changed: int
    changed_any: int
    fields: Mapping[str, int]
    examples: Mapping[str, tuple[int, ...]]


@dataclass(frozen=True)
class Reconciliation:
    shared_dates: frozenset[date]
    missing_dates: tuple[date, ...]
    parquet_shared_keys: frozenset[int]
    hana_shared_keys: frozenset[int]
    both: frozenset[int]
    parquet_only: frozenset[int]
    hana_only: frozenset[int]
    missing_period_keys: frozenset[int]


def normalize_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if field in MONEY_FIELDS:
        return money(value)
    if field in DATE_FIELDS:
        return to_date(value)
    if field in INTEGER_FIELDS:
        return int(value)
    return value


def build_document(values: Sequence[Any], diagnostics: Sequence[Any] = ()) -> PaymentDocument:
    if len(values) != len(LEGACY_FIELDS):
        raise ValueError("INVALID_PAYMENT_DOCUMENT_WIDTH")
    normalized = {
        field: normalize_value(field, value)
        for field, value in zip(LEGACY_FIELDS, values, strict=True)
    }
    create_at = combine_sap_timestamp(*diagnostics[:2]) if diagnostics else None
    update_at = combine_sap_timestamp(*diagnostics[2:4]) if diagnostics else None
    return PaymentDocument(normalized, create_at, update_at)


def combine_sap_timestamp(raw_day: Any, raw_clock: Any) -> datetime | None:
    if raw_day is None:
        return None
    day = to_date(raw_day)
    encoded = f"{int(raw_clock or 0):06d}"
    try:
        clock = time(
            int(encoded[-6:-4]),
            int(encoded[-4:-2]),
            int(encoded[-2:]),
        )
    except ValueError as exc:
        raise ValueError("INVALID_SAP_TIMESTAMP") from exc
    return datetime.combine(day, clock)


def index_documents(
    documents: Iterable[PaymentDocument],
    snapshots: Mapping[str, SnapshotEvidence] | None = None,
) -> SourceDocuments:
    materialized = tuple(documents)
    counts = Counter(document.key for document in materialized)
    by_day_counts: dict[date, Counter[int]] = defaultdict(Counter)
    for document in materialized:
        by_day_counts[document.day][document.key] += 1
    return SourceDocuments(
        documents=materialized,
        by_key={document.key: document for document in materialized},
        duplicate_keys={key: count for key, count in counts.items() if count > 1},
        duplicate_keys_by_day={
            day: {key: count for key, count in counts.items() if count > 1}
            for day, counts in by_day_counts.items()
            if any(count > 1 for count in counts.values())
        },
        snapshots=snapshots or {},
    )


def load_parquet_documents(root: Path = PARQUET_ROOT) -> SourceDocuments:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SmokeBlocked("PYARROW_REQUIRED_USE_UV_WITH_PYARROW") from exc

    files = tuple(sorted(root.glob(PARQUET_PATTERN)))
    if not files:
        raise SmokeBlocked("TELCHI_PAYMENT_PARQUET_NOT_FOUND")
    documents: list[PaymentDocument] = []
    snapshots: dict[str, SnapshotEvidence] = {}
    for path in files:
        table = pq.read_table(path, columns=list(LEGACY_FIELDS))
        columns = [table[field].to_pylist() for field in LEGACY_FIELDS]
        current = [build_document(row) for row in zip(*columns, strict=True)]
        if not current:
            raise SmokeBlocked(f"EMPTY_PARQUET_FILE:{path.name}")
        documents.extend(current)
        days = [document.day for document in current]
        filename_end = date.fromisoformat(
            path.name.removeprefix("paymentB1-").removesuffix(".parq")
        )
        month = filename_end.strftime("%Y-%m")
        snapshots[month] = SnapshotEvidence(
            path=path,
            month=month,
            filesystem_mtime=datetime.fromtimestamp(path.stat().st_mtime),
            rows=len(current),
            data_minimum=min(days),
            data_maximum=max(days),
            minimum_key=min(document.key for document in current),
            maximum_key=max(document.key for document in current),
        )
    return index_documents(documents, snapshots)


def fetch_hana_documents(cursor: Any, start: date, end: date) -> SourceDocuments:
    if end < start or end > END_DATE:
        raise ValueError("INVALID_DOCUMENT_RECONCILIATION_RANGE")
    start_at = datetime.combine(start, time.min)
    end_at = datetime.combine(end, time(23, 59, 59))
    cursor.execute(HANA_DOCUMENT_SQL, (start_at, end_at))
    documents = [build_document(row[:20], row[20:24]) for row in cursor.fetchall()]
    if any(document.day > END_DATE for document in documents):
        raise RuntimeError("HANA_RESULT_EXCEEDS_PARQUET_MAX_DATE")
    return index_documents(documents)


def day_key_sets(source: SourceDocuments) -> dict[date, set[int]]:
    result: dict[date, set[int]] = defaultdict(set)
    for document in source.documents:
        result[document.day].add(document.key)
    return result


def reconcile_sets(parquet: SourceDocuments, hana: SourceDocuments) -> Reconciliation:
    parquet_days = day_key_sets(parquet)
    hana_days = day_key_sets(hana)
    shared_dates = frozenset(
        day for day, keys in parquet_days.items() if keys and hana_days.get(day)
    )
    missing_dates = tuple(
        sorted(
            day
            for day, keys in hana_days.items()
            if START_DATE <= day <= END_DATE and keys and not parquet_days.get(day)
        )
    )
    parquet_shared = frozenset(
        key for day in shared_dates for key in parquet_days[day]
    )
    hana_shared = frozenset(key for day in shared_dates for key in hana_days[day])
    return Reconciliation(
        shared_dates=shared_dates,
        missing_dates=missing_dates,
        parquet_shared_keys=parquet_shared,
        hana_shared_keys=hana_shared,
        both=parquet_shared & hana_shared,
        parquet_only=parquet_shared - hana_shared,
        hana_only=hana_shared - parquet_shared,
        missing_period_keys=frozenset(
            key for day in missing_dates for key in hana_days[day]
        ),
    )


def compare_common_documents(
    parquet: SourceDocuments,
    hana: SourceDocuments,
    keys: Iterable[int],
) -> FieldParity:
    counters: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    examples: dict[str, list[int]] = defaultdict(list)
    for key in keys:
        parquet_document = parquet.by_key[key]
        hana_document = hana.by_key[key]
        changed = tuple(
            field
            for field in LEGACY_FIELDS
            if parquet_document.values[field] != hana_document.values[field]
        )
        if not changed:
            counters["exact"] += 1
            continue
        counters["changed_any"] += 1
        fields.update(changed)
        amount_changed = bool({"DocTotal", "DocTotalFC"} & set(changed))
        date_changed = "DocDate" in changed
        canceled_changed = "Canceled" in changed
        other_changed = bool(
            set(changed) - {"DocTotal", "DocTotalFC", "DocDate", "Canceled"}
        )
        counters.update(
            name
            for name, active in (
                ("amount_changed", amount_changed),
                ("date_changed", date_changed),
                ("canceled_changed", canceled_changed),
                ("other_changed", other_changed),
            )
            if active
        )
        pattern = "+".join(changed)
        if len(examples[pattern]) < 5:
            examples[pattern].append(key)
    return FieldParity(
        exact=counters["exact"],
        amount_changed=counters["amount_changed"],
        date_changed=counters["date_changed"],
        canceled_changed=counters["canceled_changed"],
        other_changed=counters["other_changed"],
        changed_any=counters["changed_any"],
        fields=dict(sorted(fields.items())),
        examples={key: tuple(value) for key, value in sorted(examples.items())},
    )


def classify_hana_only_timing(
    document: PaymentDocument,
    snapshot: SnapshotEvidence | None,
) -> str:
    if snapshot is None:
        return "TIMING_UNRESOLVED"
    if document.create_at and document.create_at > snapshot.filesystem_mtime:
        return "DOCUMENT_CREATED_LATER"
    if document.update_at and document.update_at > snapshot.filesystem_mtime:
        return "DOCUMENT_UPDATED_LATER"
    if document.key > snapshot.maximum_key:
        return "RESTORED_OR_REINTRODUCED_POSSIBLE"
    return "HANA_CURRENT_STATE_DIFFERENCE"


def classify_hana_only(
    hana: SourceDocuments,
    snapshots: Mapping[str, SnapshotEvidence],
    keys: Iterable[int],
) -> Counter[str]:
    result: Counter[str] = Counter()
    for key in keys:
        document = hana.by_key[key]
        snapshot = snapshots.get(document.day.strftime("%Y-%m"))
        result[classify_hana_only_timing(document, snapshot)] += 1
    return result


def classify_common_change_timing(
    parquet: SourceDocuments,
    hana: SourceDocuments,
    keys: Iterable[int],
) -> Counter[str]:
    result: Counter[str] = Counter()
    for key in keys:
        preserved = parquet.by_key[key]
        current = hana.by_key[key]
        changed = {
            field
            for field in LEGACY_FIELDS
            if preserved.values[field] != current.values[field]
        }
        if not changed:
            continue
        snapshot = parquet.snapshots.get(preserved.day.strftime("%Y-%m"))
        changed_later = bool(
            snapshot
            and current.update_at
            and current.update_at > snapshot.filesystem_mtime
        )
        result[
            "DOCUMENT_UPDATED_AFTER_SNAPSHOT"
            if changed_later
            else "DOCUMENT_CHANGE_TIMING_UNRESOLVED"
        ] += 1
        if "Canceled" in changed:
            result[
                "DOCUMENT_CANCELED_LATER"
                if changed_later
                else "CANCELED_CHANGE_TIMING_UNRESOLVED"
            ] += 1
    return result


def contiguous_ranges(days: Sequence[date]) -> list[tuple[date, date]]:
    if not days:
        return []
    ranges: list[tuple[date, date]] = []
    start = previous = days[0]
    for day in days[1:]:
        if day != previous + timedelta(days=1):
            ranges.append((start, previous))
            start = day
        previous = day
    ranges.append((start, previous))
    return ranges


def document_sample(document: PaymentDocument) -> str:
    """Render diagnostic fields only; deliberately excludes customer identity."""

    return (
        f"DocEntry={document.key} DocNum={document.values['DocNum']} "
        f"DocDate={document.day} DocTotal={document.values['DocTotal']:.2f} "
        f"Canceled={document.values['Canceled']} "
        f"CreateAt={document.create_at or 'UNKNOWN'} "
        f"UpdateAt={document.update_at or 'UNKNOWN'}"
    )


def fetch_query_parity(cursor: Any, start: date, end: date) -> tuple[int, int, int]:
    cursor.execute(
        CURRENT_DOCUMENT_KEYS_SQL,
        (start.isoformat(), end.isoformat()),
    )
    current_keys = {int(row[0]) for row in cursor.fetchall()}
    start_at = datetime.combine(start, time.min)
    end_at = datetime.combine(end, time(23, 59, 59))
    cursor.execute(
        'SELECT "DocEntry" FROM "TELCHI"."ORCT" '
        'WHERE "DocDate" >= ? AND "DocDate" <= ?',
        (start_at, end_at),
    )
    legacy_keys = {int(row[0]) for row in cursor.fetchall()}
    return len(legacy_keys), len(current_keys), len(legacy_keys ^ current_keys)


def print_samples(
    label: str,
    keys: Sequence[int],
    source: SourceDocuments,
) -> None:
    print(label)
    for key in keys:
        print(f"  {document_sample(source.by_key[key])}")


def print_report(
    parquet: SourceDocuments,
    hana: SourceDocuments,
    reconciliation: Reconciliation,
    parity: FieldParity,
    timing: Counter[str],
    common_change_timing: Counter[str],
    query_parity: tuple[int, int, int],
    money_metadata: Sequence[Sequence[Any]],
    observed_scale_violations: Sequence[Any],
    show_samples: bool,
) -> None:
    print(f"WINDOW                     {START_DATE}..{END_DATE}")
    print(f"PARQUET ROWS               {len(parquet.documents)}")
    print(f"HANA ROWS                  {len(hana.documents)}")
    print(f"PARQUET DUPLICATE DOCENTRY {len(parquet.duplicate_keys)}")
    print(f"HANA DUPLICATE DOCENTRY    {len(hana.duplicate_keys)}")
    print(f"SHARED DATES               {len(reconciliation.shared_dates)}")
    print(f"SHARED PARQUET DOCS        {len(reconciliation.parquet_shared_keys)}")
    print(f"SHARED HANA DOCS           {len(reconciliation.hana_shared_keys)}")
    print(f"BOTH                       {len(reconciliation.both)}")
    print(f"PARQUET ONLY               {len(reconciliation.parquet_only)}")
    print(f"HANA ONLY                  {len(reconciliation.hana_only)}")
    print(f"EXACT DOCUMENT MATCH       {parity.exact}")
    print(f"AMOUNT CHANGED             {parity.amount_changed}")
    print(f"DATE CHANGED               {parity.date_changed}")
    print(f"CANCELED CHANGED           {parity.canceled_changed}")
    print(f"OTHER FIELDS CHANGED       {parity.other_changed}")
    print(f"ANY FIELD CHANGED          {parity.changed_any}")
    for field, count in parity.fields.items():
        print(f"CHANGED FIELD {field:<12} {count}")
    print("SAME-DOCENTRY CHANGE TIMING")
    for cause in (
        "DOCUMENT_UPDATED_AFTER_SNAPSHOT",
        "DOCUMENT_CANCELED_LATER",
        "DOCUMENT_CHANGE_TIMING_UNRESOLVED",
        "CANCELED_CHANGE_TIMING_UNRESOLVED",
    ):
        print(f"  {cause:<38} {common_change_timing[cause]}")

    print("MONTHLY DOCUMENT PARITY")
    parquet_days = day_key_sets(parquet)
    hana_days = day_key_sets(hana)
    changed_keys = {
        key
        for key in reconciliation.both
        if any(
            parquet.by_key[key].values[field] != hana.by_key[key].values[field]
            for field in LEGACY_FIELDS
        )
    }
    for month in sorted(parquet.snapshots):
        month_days = {day for day in reconciliation.shared_dates if day.strftime("%Y-%m") == month}
        parquet_keys = {key for day in month_days for key in parquet_days[day]}
        hana_keys = {key for day in month_days for key in hana_days[day]}
        print(
            f"  {month} parquet_only={len(parquet_keys-hana_keys)} "
            f"hana_only={len(hana_keys-parquet_keys)} "
            f"same_docentry_changed={len(changed_keys & parquet_keys & hana_keys)}"
        )

    print("MISSING DATE RANGES")
    for start, end in contiguous_ranges(reconciliation.missing_dates):
        days = (end - start).days + 1
        print(
            f"  {start}..{end} days={days} "
            f"hana_documents={len(reconciliation.missing_period_keys)}"
        )
    print(f"MISSING PERIOD DOCUMENTS   {len(reconciliation.missing_period_keys)}")

    print("SNAPSHOT EVIDENCE")
    for month, snapshot in sorted(parquet.snapshots.items()):
        print(
            f"  {month} file={snapshot.path.name} rows={snapshot.rows} "
            f"data={snapshot.data_minimum}..{snapshot.data_maximum} "
            f"keys={snapshot.minimum_key}..{snapshot.maximum_key} "
            f"filesystem_mtime={snapshot.filesystem_mtime}"
        )

    print("SHARED-DATE ROOT CAUSES")
    for cause in (
        "DOCUMENT_CREATED_LATER",
        "DOCUMENT_UPDATED_LATER",
        "RESTORED_OR_REINTRODUCED_POSSIBLE",
        "HANA_CURRENT_STATE_DIFFERENCE",
        "TIMING_UNRESOLVED",
    ):
        print(f"  {cause:<30} {timing[cause]}")

    presence_difference = len(reconciliation.hana_only) + len(
        reconciliation.missing_period_keys
    )
    print("PRESENCE ROOT CAUSE DISTRIBUTION")
    root_causes = {
        "MISSING_PARQUET_PERIOD": len(reconciliation.missing_period_keys),
        "LEGACY_QUERY_OMISSION": 0,
        "PARQUET_SAVE_OMISSION": 0,
        **{key: timing[key] for key in timing},
    }
    for cause, count in root_causes.items():
        percentage = (
            Decimal(count) / Decimal(presence_difference) * Decimal("100")
        ).quantize(CENT) if presence_difference else Decimal("0.00")
        print(f"  {cause:<35} {count:>6} {percentage:>6}%")

    legacy_count, current_count, symmetric_difference = query_parity
    print(f"LEGACY QUERY DOCUMENTS     {legacy_count}")
    print(f"CURRENT QUERY DOCUMENTS    {current_count}")
    print(f"QUERY SYMMETRIC DIFFERENCE {symmetric_difference}")
    print(
        "LEGACY QUERY STATUS        "
        + ("LEGACY_QUERY_VALID" if symmetric_difference == 0 else "LEGACY_QUERY_HAS_ISSUE")
    )
    print(
        "HANA MONEY METADATA        "
        + ",".join(f"{row[0]}:{row[1]}(scale={row[2]})" for row in money_metadata)
    )
    print(
        "OBSERVED >2DP VALUES       "
        f"DocTotal={int(observed_scale_violations[0] or 0)},"
        f"DocTotalFC={int(observed_scale_violations[1] or 0)}"
    )

    if show_samples:
        hana_only = sorted(reconciliation.hana_only)
        print_samples("FIRST 5 HANA_ONLY", hana_only[:5], hana)
        print_samples("LAST 5 HANA_ONLY", hana_only[-5:], hana)
        canceled = [
            key
            for key in sorted(reconciliation.both)
            if parquet.by_key[key].values["Canceled"]
            != hana.by_key[key].values["Canceled"]
        ]
        amount = [
            key
            for key in sorted(reconciliation.both)
            if parquet.by_key[key].values["DocTotal"]
            != hana.by_key[key].values["DocTotal"]
            or parquet.by_key[key].values["DocTotalFC"]
            != hana.by_key[key].values["DocTotalFC"]
        ]
        print_samples("FIRST 5 AMOUNT CHANGED", amount[:5], hana)
        print_samples("FIRST 5 CANCELED CHANGED", canceled[:5], hana)


def run_reconciliation(show_samples: bool = False) -> None:
    parquet = load_parquet_documents()
    if min(document.day for document in parquet.documents) != START_DATE:
        raise RuntimeError("PARQUET_START_DATE_CHANGED")
    if max(document.day for document in parquet.documents) != END_DATE:
        raise RuntimeError("PARQUET_END_DATE_CHANGED")
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
        hana = fetch_hana_documents(cursor, START_DATE, END_DATE)
        reconciliation = reconcile_sets(parquet, hana)
        parity = compare_common_documents(parquet, hana, reconciliation.both)
        timing = classify_hana_only(
            hana,
            parquet.snapshots,
            reconciliation.hana_only,
        )
        common_change_timing = classify_common_change_timing(
            parquet,
            hana,
            reconciliation.both,
        )
        query_parity = fetch_query_parity(cursor, START_DATE, END_DATE)
        cursor.execute(HANA_MONEY_METADATA_SQL)
        money_metadata = cursor.fetchall()
        cursor.execute(
            HANA_OBSERVED_SCALE_SQL,
            (
                datetime.combine(START_DATE, time.min),
                datetime.combine(END_DATE, time(23, 59, 59)),
            ),
        )
        observed_scale_violations = cursor.fetchone()
        print_report(
            parquet,
            hana,
            reconciliation,
            parity,
            timing,
            common_change_timing,
            query_parity,
            money_metadata,
            observed_scale_violations,
            show_samples,
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
        "--show-samples",
        action="store_true",
        help="Print limited non-personal diagnostic document samples.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_reconciliation(show_samples=args.show_samples)
    except (SmokeBlocked, ValueError, RuntimeError) as exc:
        print("TEAM360_TELCHI_INCOMING_PAYMENTS_DOCUMENT_RECONCILIATION_BLOCKED")
        print(f"BLOCKER: {exc}")
        return 2
    print("TEAM360_TELCHI_INCOMING_PAYMENTS_DOCUMENT_RECONCILIATION_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
