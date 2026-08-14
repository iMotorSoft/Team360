from __future__ import annotations

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import reconcile_telchi_incoming_payments_documents as reconcile  # noqa: E402


def document(
    key: int,
    day: date,
    *,
    amount: str = "10.00",
    canceled: str = "N",
    memo: str = "memo",
    create_at: datetime | None = None,
    update_at: datetime | None = None,
) -> reconcile.PaymentDocument:
    values = {
        field: None
        for field in reconcile.LEGACY_FIELDS
    }
    values.update(
        {
            "DocEntry": key,
            "DocNum": key + 1000,
            "DocDate": day,
            "DocTotal": Decimal(amount),
            "DocTotalFC": Decimal("0.00"),
            "Canceled": canceled,
            "JrnlMemo": memo,
        }
    )
    return reconcile.PaymentDocument(values, create_at, update_at)


def test_set_reconciliation_separates_missing_dates() -> None:
    parquet = reconcile.index_documents(
        [
            document(1, date(2022, 4, 1)),
            document(2, date(2022, 4, 2)),
        ]
    )
    hana = reconcile.index_documents(
        [
            document(1, date(2022, 4, 1)),
            document(3, date(2022, 4, 1)),
            document(4, date(2022, 4, 3)),
        ]
    )
    result = reconcile.reconcile_sets(parquet, hana)
    assert result.shared_dates == frozenset({date(2022, 4, 1)})
    assert result.both == frozenset({1})
    assert result.parquet_only == frozenset()
    assert result.hana_only == frozenset({3})
    assert result.missing_dates == (date(2022, 4, 3),)
    assert result.missing_period_keys == frozenset({4})


def test_duplicate_docentry_is_reported_globally_and_by_day() -> None:
    day = date(2022, 4, 1)
    source = reconcile.index_documents([document(1, day), document(1, day)])
    assert source.duplicate_keys == {1: 2}
    assert source.duplicate_keys_by_day == {day: {1: 2}}


def test_decimal_normalization_avoids_float_identity_errors() -> None:
    assert reconcile.normalize_value("DocTotal", 0.1 + 0.2) == Decimal("0.30")
    assert reconcile.normalize_value("DocTotalFC", "1.239") == Decimal("1.24")


def test_same_document_field_classification_is_exact_and_nonexclusive() -> None:
    day = date(2022, 4, 1)
    parquet = reconcile.index_documents(
        [
            document(1, day),
            document(2, day),
            document(3, day),
        ]
    )
    hana = reconcile.index_documents(
        [
            document(1, day),
            document(2, day, canceled="Y", memo="canceled later"),
            document(3, day, amount="11.00"),
        ]
    )
    result = reconcile.compare_common_documents(parquet, hana, {1, 2, 3})
    assert result.exact == 1
    assert result.changed_any == 2
    assert result.amount_changed == 1
    assert result.date_changed == 0
    assert result.canceled_changed == 1
    assert result.other_changed == 1
    assert result.fields == {"Canceled": 1, "DocTotal": 1, "JrnlMemo": 1}


def test_hana_only_timing_classification_uses_snapshot_evidence() -> None:
    snapshot = reconcile.SnapshotEvidence(
        path=Path("paymentB1-2022-04-30.parq"),
        month="2022-04",
        filesystem_mtime=datetime(2022, 5, 1, 12),
        rows=1,
        data_minimum=date(2022, 4, 1),
        data_maximum=date(2022, 4, 30),
        minimum_key=1,
        maximum_key=100,
    )
    assert (
        reconcile.classify_hana_only_timing(
            document(1, date(2022, 4, 1), create_at=datetime(2022, 5, 2)),
            snapshot,
        )
        == "DOCUMENT_CREATED_LATER"
    )
    assert (
        reconcile.classify_hana_only_timing(
            document(
                1,
                date(2022, 4, 1),
                create_at=datetime(2022, 4, 1),
                update_at=datetime(2022, 5, 2),
            ),
            snapshot,
        )
        == "DOCUMENT_UPDATED_LATER"
    )
    assert (
        reconcile.classify_hana_only_timing(
            document(1, date(2022, 4, 1), create_at=datetime(2022, 4, 1)),
            snapshot,
        )
        == "HANA_CURRENT_STATE_DIFFERENCE"
    )
    assert (
        reconcile.classify_hana_only_timing(
            document(101, date(2022, 4, 1), create_at=datetime(2022, 4, 1)),
            snapshot,
        )
        == "RESTORED_OR_REINTRODUCED_POSSIBLE"
    )


def test_common_document_changes_are_timed_against_snapshot() -> None:
    day = date(2022, 4, 1)
    snapshot = reconcile.SnapshotEvidence(
        path=Path("paymentB1-2022-04-30.parq"),
        month="2022-04",
        filesystem_mtime=datetime(2022, 5, 1, 12),
        rows=1,
        data_minimum=day,
        data_maximum=day,
        minimum_key=1,
        maximum_key=1,
    )
    parquet = reconcile.index_documents(
        [document(1, day)],
        {"2022-04": snapshot},
    )
    hana = reconcile.index_documents(
        [
            document(
                1,
                day,
                canceled="Y",
                update_at=datetime(2022, 5, 2),
            )
        ]
    )
    result = reconcile.classify_common_change_timing(parquet, hana, {1})
    assert result == {
        "DOCUMENT_UPDATED_AFTER_SNAPSHOT": 1,
        "DOCUMENT_CANCELED_LATER": 1,
    }


def test_hana_fetch_is_bounded_by_fixed_parquet_end_date() -> None:
    class Cursor:
        parameters: tuple[datetime, datetime] | None = None

        def execute(self, sql: str, parameters: tuple[datetime, datetime]) -> None:
            assert '"DocDate" <= ?' in sql
            self.parameters = parameters

        def fetchall(self) -> list[tuple[object, ...]]:
            return []

    cursor = Cursor()
    reconcile.fetch_hana_documents(cursor, reconcile.START_DATE, reconcile.END_DATE)
    assert cursor.parameters is not None
    assert cursor.parameters[1] == datetime(2023, 5, 31, 23, 59, 59)


def test_output_helpers_exclude_customer_identity_and_password() -> None:
    item = document(1, date(2022, 4, 1))
    rendered = reconcile.document_sample(item).casefold()
    assert "client" not in rendered
    assert "cardcode" not in rendered
    assert "password" not in rendered
    source = Path(reconcile.__file__).read_text(encoding="utf-8").casefold()
    assert "print(" + "password" not in source
    assert "connection string" not in source
