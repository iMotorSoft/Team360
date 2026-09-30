from __future__ import annotations

from datetime import date

import duckdb
import pytest

from modules.telchi.datalake.receivables_collections_atomic import (
    ENTITY_ORDER,
    HISTORY_START,
    SQL,
    Segment,
    ensure_tables,
    load_discovery_contract,
    plan_segments,
    publish_segment,
    transform_rows,
    validate_rows,
)
from modules.telchi.datalake.sql import assert_read_only_select
from modules.telchi.runtime.config import DuckDBSafetyProfile


def metadata() -> dict[str, str]:
    return {"run_id": "run-1", "source_as_of": "2026-09-28T23:59:59Z", "built_at": "2026-09-29T00:00:00Z"}


def invoice_row(doc: int = 10, installment: int = 1) -> dict[str, object]:
    return {
        "source_doc_entry": doc, "source_doc_num": 100, "source_object_type": 13,
        "customer_code": "C1", "document_date": "2026-01-02", "posting_date": "2026-01-02",
        "tax_date": "2026-01-02", "due_date": "2026-02-02", "currency": "BS",
        "document_rate": "1", "system_rate": "1", "document_total": "100",
        "document_total_foreign": "0", "document_total_system": "100", "paid_to_date": "20",
        "paid_foreign": "0", "paid_system": "20", "source_open_amount": "80",
        "source_open_amount_foreign": "0", "source_open_amount_system": "80",
        "cancelled": "N", "cancel_date": None, "source_document_status": "O",
        "payment_term_code": 3, "transaction_id": 7, "salesperson_code": 2, "branch_id": 1,
        "installment_id": installment, "installment_due_date": f"2026-02-0{installment}",
        "installment_status": "O", "installment_total": "50", "installment_total_foreign": "0",
        "installment_total_system": "50", "installment_paid": "10",
        "installment_paid_foreign": "0", "installment_paid_system": "10",
    }


def payment_row(doc: int = 20) -> dict[str, object]:
    return {
        "source_doc_entry": doc, "source_doc_num": 200, "source_object_type": 24,
        "customer_code": "C1", "payment_date": "2026-01-03", "posting_date": "2026-01-03",
        "tax_date": "2026-01-03", "due_date": "2026-01-03", "currency": "BS",
        "document_rate": "1", "system_rate": "1", "payment_total": "100",
        "payment_total_foreign": "0", "payment_total_system": "100", "cash_amount": "20",
        "cash_amount_foreign": "0", "cash_amount_system": "20", "transfer_amount": "80",
        "transfer_amount_foreign": "0", "transfer_amount_system": "80", "check_amount": "0",
        "check_amount_foreign": "0", "check_amount_system": "0", "card_amount": "0",
        "card_amount_foreign": "0", "card_amount_system": "0", "cancelled": "N",
        "cancel_date": None, "source_status": "O", "transaction_id": 8, "pay_no_document": "Y",
        "on_account_amount": "100", "on_account_amount_foreign": "0", "on_account_amount_system": "100",
        "source_open_balance": "100", "source_open_balance_foreign": "0",
        "source_open_balance_system": "100", "branch_id": 1,
    }


def test_sealed_discovery_contract_controls_required_entities() -> None:
    contract = load_discovery_contract()
    assert contract["required"]["receivable_event"] == "TBD"
    assert all(contract["required"][entity] == "YES" for entity in ENTITY_ORDER)
    assert len(contract["fingerprint"]) == 64


def test_history_plan_is_month_bounded_and_includes_terms_once() -> None:
    plan = plan_segments(HISTORY_START, date(2022, 5, 1))
    assert plan[0].start == HISTORY_START
    assert plan[-1] == Segment("payment_term", None, None)
    assert sum(item.entity == "payment_term" for item in plan) == 1
    assert all(item.end > item.start for item in plan[:-1])


def test_arbitrary_precoverage_history_is_rejected() -> None:
    with pytest.raises(Exception, match="sealed coverage"):
        plan_segments(date(2022, 1, 1), date(2022, 5, 1))


def test_every_source_query_is_select_only_and_explicit() -> None:
    for sql in SQL.values():
        assert_read_only_select(sql)
        assert "SELECT *" not in sql.upper()


def test_document_identity_and_installment_schedule_are_stable() -> None:
    rows = transform_rows("receivable_document", [invoice_row(10, 2), invoice_row(10, 1)], **metadata())
    assert len(rows) == 1
    assert rows[0]["source_row_identity"] == '["SAP_B1_HANA",13,10]'
    assert rows[0]["installment_count"] == 2
    assert rows[0]["installments_json"].index('"installment_id":1') < rows[0]["installments_json"].index('"installment_id":2')


def test_payment_identity_and_on_account_fields_are_preserved() -> None:
    row = transform_rows("collection_payment", [payment_row()], **metadata())[0]
    assert row["source_row_identity"] == '["SAP_B1_HANA",24,20]'
    assert row["pay_no_document"] == "Y"
    assert row["on_account_amount"] == "100"


def test_allocation_identity_uses_exact_source_grain_and_rejects_duplicate() -> None:
    source = {"payment_doc_entry": 20, "payment_date": "2026-01-03", "target_object_type": 13,
              "target_doc_entry": 10, "invoice_id": 1, "target_document_line": 0, "installment_id": 1,
              "link_date": "2026-01-03", "allocated_amount": "50", "allocated_amount_foreign": "0",
              "allocated_amount_system": "50", "document_rate": "1", "paid_amount": "50", "source_row_count": 2}
    rows = transform_rows("collection_allocation", [source, source.copy()], **metadata())
    validation = validate_rows("collection_allocation", rows)
    assert validation["duplicate_atomic_ids"] == 1
    assert validation["status"] == "FAIL"


def test_reconciliation_participant_identity_preserves_line_sequence() -> None:
    common = {"reconciliation_id": 30, "reconciliation_date": "2026-01-04", "reconciliation_cancelled": "N",
              "participant_short_name": "C1", "transaction_id": 1, "transaction_row_id": 0,
              "participant_object_type": 13, "participant_object_abs": 10, "reconciled_amount": "50",
              "reconciled_amount_foreign": "0", "reconciled_amount_system": "50", "foreign_currency": None,
              "sum_in_matching_currency": "50", "is_credit": "N", "account": "A", "installment_id": 1,
              "source_object_type": 321}
    rows = transform_rows("reconciliation_participant", [common | {"source_line_id": 0}, common | {"source_line_id": 1}], **metadata())
    assert len({row["atomic_id"] for row in rows}) == 2


def test_payment_method_components_preserve_mixed_and_never_infer_qr() -> None:
    base = {"payment_doc_entry": 20, "payment_date": "2026-01-03", "component_source_table": "ORCT",
            "source_line_id": "HEADER", "component_currency": "BS", "component_amount_foreign": "0",
            "component_amount_system": "10", "source_rate": "1", "source_due_date": None,
            "source_method_code": None, "cancelled": "N", "source_object_type": 24}
    rows = transform_rows("payment_method_component", [base | {"method_code": "CASH", "component_amount": "5"}, base | {"method_code": "TRANSFER", "component_amount": "5"}], **metadata())
    assert {row["method_code"] for row in rows} == {"CASH", "TRANSFER"}
    assert validate_rows("payment_method_component", rows)["qr_rows"] == 0


def test_qr_row_fails_closed() -> None:
    source = {"payment_doc_entry": 20, "payment_date": "2026-01-03", "method_code": "QR",
              "component_source_table": "ORCT", "source_line_id": "HEADER", "component_currency": "BS",
              "component_amount": "5", "component_amount_foreign": "0", "component_amount_system": "5",
              "source_rate": "1", "source_due_date": None, "source_method_code": None,
              "cancelled": "N", "source_object_type": 24}
    rows = transform_rows("payment_method_component", [source], **metadata())
    assert validate_rows("payment_method_component", rows)["status"] == "FAIL"


def test_hashes_are_idempotent_and_exclude_build_timestamp() -> None:
    first = transform_rows("collection_payment", [payment_row()], run_id="a", source_as_of="s", built_at="one")[0]
    second = transform_rows("collection_payment", [payment_row()], run_id="b", source_as_of="s", built_at="two")[0]
    assert first["atomic_id"] == second["atomic_id"]
    assert first["row_hash"] == second["row_hash"]
    assert first["built_at"] != second["built_at"]


def test_cancelled_payment_is_preserved_as_fact() -> None:
    source = payment_row() | {"cancelled": "Y", "cancel_date": "2026-01-04"}
    row = transform_rows("collection_payment", [source], **metadata())[0]
    assert row["cancelled"] == "Y"
    assert row["cancel_date"] == "2026-01-04"


def test_foreign_and_system_currency_axes_remain_separate() -> None:
    source = payment_row() | {"currency": "USD", "payment_total": "690", "payment_total_foreign": "100", "payment_total_system": "100"}
    row = transform_rows("collection_payment", [source], **metadata())[0]
    assert (row["payment_total"], row["payment_total_foreign"], row["payment_total_system"]) == ("690", "100", "100")


def test_segment_publication_replaces_scope_without_duplicates(tmp_path) -> None:
    connection = duckdb.connect()
    try:
        connection.execute("ATTACH ':memory:' AS telchi")
        ensure_tables(connection)
        segment = Segment("collection_payment", date(2026, 1, 1), date(2026, 2, 1))
        rows = transform_rows("collection_payment", [payment_row()], **metadata())
        profile = DuckDBSafetyProfile(temp_directory=tmp_path / "tmp")
        publish_segment(connection, segment, rows, profile=profile, staging_root=tmp_path)
        publish_segment(connection, segment, rows, profile=profile, staging_root=tmp_path)
        assert connection.execute("SELECT count(*) FROM telchi.atomic.collection_payment").fetchone()[0] == 1
    finally:
        connection.close()


def test_late_event_replay_replaces_changed_source_fact(tmp_path) -> None:
    connection = duckdb.connect()
    try:
        connection.execute("ATTACH ':memory:' AS telchi")
        segment = Segment("collection_payment", date(2026, 1, 1), date(2026, 2, 1))
        profile = DuckDBSafetyProfile(temp_directory=tmp_path / "tmp")
        publish_segment(connection, segment, transform_rows("collection_payment", [payment_row()], **metadata()), profile=profile, staging_root=tmp_path)
        changed = transform_rows("collection_payment", [payment_row() | {"cancelled": "Y"}], **metadata())
        publish_segment(connection, segment, changed, profile=profile, staging_root=tmp_path)
        assert connection.execute("SELECT cancelled FROM telchi.atomic.collection_payment").fetchone()[0] == "Y"
        assert connection.execute("SELECT count(*) FROM telchi.atomic.collection_payment").fetchone()[0] == 1
    finally:
        connection.close()
