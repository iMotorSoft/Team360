from __future__ import annotations

from datetime import date

import pytest

from modules.telchi.datalake.create_initial import _publish_initial_foundation, publication_writer, reconcile_candidate, transform, validate_candidate
from modules.telchi.runtime.transactional_publication import PublicationFailurePoint, TransactionalPublicationBoundary
from modules.telchi.datalake.planner import inventory_segments_from_keys, plan_only_placeholders, sales_segments_from_bounds
from modules.telchi.datalake.sql import INVENTORY_EXTRACT_SQL, SALES_EXTRACT_SQL, assert_read_only_select, oinm_extract_sql
from modules.telchi.datalake.create_initial import ensure_inventory_movement_table


def _sales_row(doc: int = 10, line: int = 0) -> dict[str, object]:
    return {
        "DocEntry": doc, "DocNum": 100, "DocDate": "2025-03-01", "DocDueDate": "2025-03-31", "TaxDate": "2025-03-01",
        "DocStatus": "O", "CANCELED": "N", "DocCur": "BS", "DocTotal": "12.50", "DocTotalSy": "1.80", "DocTotalFC": "0", "CardCode": "C1", "HeaderSlpCode": 7, "Series": 1, "UserSign": 145,
        "ObjType": 13, "LineNum": line, "LineStatus": "O", "ItemCode": "I1", "WhsCode": "W1",
        "Quantity": "2", "LineCurrency": "BS", "LineTotal": "12.50", "Price": "6.25", "LineSlpCode": 7,
    }


def test_initial_foundation_publication_requires_all_components_and_non_dry_run():
    assert _publish_initial_foundation(
        run_id="partial", domains=["sales"], results=[], dry_run=False,
        connector=None, reference_version="v2-test",
    ) is None
    assert _publish_initial_foundation(
        run_id="dry", domains=["sales", "credit_memo", "inventory_movement", "inventory"],
        results=[], dry_run=True, connector=None, reference_version="v2-test",
    ) is None


def test_sales_planning_is_half_open_and_bounded() -> None:
    segments = sales_segments_from_bounds([("2025-03-01", "2025-04-01", 10, 25)], max_docentries_per_segment=5)
    assert [(item.key_from, item.key_to) for item in segments] == [("10", "15"), ("15", "20"), ("20", "25"), ("25", "26")]
    assert all(item.strategy == "DOCENTRY_RANGE" for item in segments)


def test_inventory_identity_is_item_warehouse_not_snapshot_row_number() -> None:
    segments = inventory_segments_from_keys([("I2", "W1"), ("I1", "W1")], max_pairs_per_segment=1)
    assert segments[0].key_from == "I1\x1fW1"
    assert segments[0].key_to == "I1\x1fW1"
    assert "ItemCode x WhsCode" in segments[0].scope


def test_sql_is_explicit_select_only_and_no_select_star() -> None:
    for sql in (SALES_EXTRACT_SQL, INVENTORY_EXTRACT_SQL):
        assert_read_only_select(sql)
        assert "SELECT *" not in sql.upper()
        assert "?" in sql


def test_sales_transform_preserves_docentry_linenum_item_and_warehouse() -> None:
    rows = [_sales_row()]
    candidate = transform("sales", rows, {"extraction_id": "e1", "source_as_of": "2025-03-01T00:00:00Z"})
    line = candidate.tables["sales_line"][0]
    document = candidate.tables["sales_document"][0]
    assert line["doc_entry"] == "10"
    assert line["line_num"] == 0
    assert line["item_code"] == "I1"
    assert line["whs_code"] == "W1"
    assert document["doc_entry"] == "10"
    assert validate_candidate(candidate, 10)["duplicate_source_keys"] == 0


def _movement_row(trans_num: int = 7, trans_seq: int = 2) -> dict[str, object]:
    return {
        "TransNum": trans_num, "TransSeq": trans_seq, "Instance": 0, "TransType": 67,
        "BaseRef": "B1", "DocDate": "2025-03-01 00:00:00", "ItemCode": "I1", "Warehouse": "W1",
        "InQty": "3", "OutQty": "1", "Price": "2.50", "CalcPrice": "2.00", "TransValue": "6.00",
        "CreatedBy": 10, "AppObjAbs": -1, "AppObjType": None, "DocLineNum": 0, "Ref1": "R1", "Ref2": None,
        "Comments": None, "JrnlMemo": None, "DocDueDate": None, "DocTime": 1200, "CardCode": None,
        "CardName": None, "Dscription": "Item", "Balance": "2", "SlpCode": -1, "UserSign": 1,
        "ApplObj": -1, "AppObjLine": -1,
    }


def test_oinm_sql_is_explicit_and_source_key_is_preserved() -> None:
    sql = oinm_extract_sql({"TransNum": "TransNum", "TransSeq": "TransSeq", "TransType": "TransType", "DocDate": "DocDate", "ItemCode": "ItemCode", "Warehouse": "Warehouse", "InQty": "InQty", "OutQty": "OutQty", "BaseRef": "BASE_REF"})
    assert_read_only_select(sql)
    assert "SELECT *" not in sql.upper()
    assert '"BASE_REF" AS "BaseRef"' in sql
    candidate = transform("inventory_movement", [_movement_row()], {"extraction_id": "e1", "source_as_of": "2025-03-01T00:00:00Z", "source_key_columns": ["TransNum", "TransSeq"]})
    row = candidate.tables["inventory_movement"][0]
    assert candidate.source_key_columns == ("TransNum", "TransSeq")
    assert row["trans_num"] == 7 and row["trans_seq"] == 2
    assert row["warehouse"] == "W1" and row["movement_qty"] == "2"
    assert validate_candidate(candidate, 10)["duplicate_source_keys"] == 0


def test_inventory_movement_publication_is_bulk_and_set_based() -> None:
    import duckdb
    connection = duckdb.connect()
    try:
        connection.execute("ATTACH ':memory:' AS telchi")
        ensure_inventory_movement_table(connection)
        candidate = transform("inventory_movement", [_movement_row(7, 2), _movement_row(8, 3)], {"extraction_id": "e1", "source_as_of": "2025-03-01T00:00:00Z", "source_key_columns": ["TransNum", "TransSeq"]})
        recorder = _RecordingConnection(connection)
        metrics: dict[str, int] = {}
        publication_writer({"sales_document": None, "sales_line": None, "inventory_balance_snapshot": None, "inventory_movement": "inventory_movement"}, metrics=metrics)(recorder, candidate, "p1", lambda _point: None)
        assert connection.execute("SELECT count(*) FROM telchi.atomic.inventory_movement").fetchone()[0] == 2
        target_inserts = [sql for sql in recorder.statements if sql.lstrip().upper().startswith("INSERT INTO TELCHI.ATOMIC")]
        assert len(target_inserts) == 1 and "SELECT" in target_inserts[0].upper()
        assert metrics == {"target_bulk_insert_count": 1, "target_rows_published": 2}
    finally:
        connection.close()


def test_inventory_reconciliation_is_exact_and_detects_source_change() -> None:
    rows = [{"ItemCode": "I1", "WhsCode": "W1", "OnHand": "3", "IsCommited": "1", "OnOrder": "2"}]
    candidate = transform("inventory", rows, {"extraction_id": "e1", "source_as_of": "2025-03-01T00:00:00Z"})
    assert reconcile_candidate(candidate, rows)["status"] == "EXACT"
    changed = [dict(rows[0], OnHand="4")]
    assert reconcile_candidate(candidate, changed)["status"] == "SOURCE_CHANGED_DURING_RECONCILIATION"


def test_plan_only_never_fakes_source_identity() -> None:
    plan = plan_only_placeholders(date(2025, 3, 1), date(2025, 4, 1), sales_count=1, inventory_count=1)
    assert len(plan) == 2
    assert all(item.key_from == "DISCOVERY_REQUIRED" for item in plan)


class _RecordingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.statements: list[str] = []

    def execute(self, sql, parameters=None):
        self.statements.append(sql)
        return self.connection.execute(sql) if parameters is None else self.connection.execute(sql, parameters)

    def executemany(self, sql, parameters):
        self.statements.append(sql)
        return self.connection.executemany(sql, parameters)


def _create_atomic_tables(connection) -> None:
    connection.execute("ATTACH ':memory:' AS telchi")
    connection.execute("CREATE SCHEMA telchi.atomic")
    connection.execute("CREATE TABLE telchi.atomic.sales_document (atomic_id VARCHAR, source_system VARCHAR, source_table VARCHAR, doc_entry VARCHAR, doc_num VARCHAR, doc_date VARCHAR, doc_due_date VARCHAR, tax_date VARCHAR, doc_status VARCHAR, canceled VARCHAR, currency VARCHAR, doc_total VARCHAR, doc_total_system VARCHAR, doc_total_foreign VARCHAR, card_code VARCHAR, slp_code VARCHAR, series VARCHAR, user_sign VARCHAR, sales_channel_code VARCHAR, sales_channel_name VARCHAR, sales_channel_semantic_status VARCHAR, source_as_of VARCHAR, raw_extraction_id VARCHAR, reference_version VARCHAR, reference_manifest_hash VARCHAR, transformation_version VARCHAR, schema_version VARCHAR)")
    connection.execute("CREATE TABLE telchi.atomic.sales_line (atomic_id VARCHAR, source_system VARCHAR, source_table VARCHAR, doc_entry VARCHAR, line_num VARCHAR, item_code VARCHAR, whs_code VARCHAR, quantity VARCHAR, currency VARCHAR, line_total VARCHAR, price VARCHAR, line_status VARCHAR, slp_code VARCHAR, attributed_slp_code VARCHAR, source_as_of VARCHAR, raw_extraction_id VARCHAR, reference_version VARCHAR, reference_manifest_hash VARCHAR, transformation_version VARCHAR, schema_version VARCHAR)")
    connection.execute("CREATE TABLE telchi.atomic.inventory_balance (atomic_id VARCHAR, source_system VARCHAR, source_table VARCHAR, item_code VARCHAR, whs_code VARCHAR, on_hand VARCHAR, is_commited VARCHAR, on_order VARCHAR, source_as_of VARCHAR, raw_extraction_id VARCHAR, reference_version VARCHAR, reference_manifest_hash VARCHAR, transformation_version VARCHAR, schema_version VARCHAR)")


def test_sales_publication_uses_one_bulk_insert_per_atomic_table() -> None:
    import duckdb

    connection = duckdb.connect()
    try:
        _create_atomic_tables(connection)
        candidate = transform("sales", [_sales_row(10, 0), _sales_row(10, 1), _sales_row(11, 0)], {"extraction_id": "e1", "source_as_of": "2025-03-01T00:00:00Z"})
        recorder = _RecordingConnection(connection)
        metrics: dict[str, int] = {}
        publication_writer({"sales_document": "sales_document", "sales_line": "sales_line", "inventory_balance_snapshot": None}, metrics=metrics)(recorder, candidate, "p1", lambda _point: None)
        assert connection.execute("SELECT count(*) FROM telchi.atomic.sales_document").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM telchi.atomic.sales_line").fetchone()[0] == 3
        target_inserts = [sql for sql in recorder.statements if sql.lstrip().upper().startswith("INSERT INTO TELCHI.ATOMIC")]
        assert len(target_inserts) == 2
        assert all("SELECT" in sql.upper() for sql in target_inserts)
        assert metrics == {"target_bulk_insert_count": 2, "target_rows_published": 5}
    finally:
        connection.close()


def test_bulk_publication_rolls_back_and_retries_without_duplicates() -> None:
    import duckdb
    from contextlib import contextmanager

    connection = duckdb.connect()
    try:
        _create_atomic_tables(connection)
        candidate = transform("sales", [_sales_row(10, 0), _sales_row(10, 1)], {"extraction_id": "e1", "source_as_of": "2025-03-01T00:00:00Z"})

        @contextmanager
        def connection_factory():
            yield connection

        boundary = TransactionalPublicationBoundary(
            connection_factory=connection_factory,
            record_table="telchi.ops.initial_publications_v1",
            writer=publication_writer({"sales_document": "sales_document", "sales_line": "sales_line", "inventory_balance_snapshot": None}),
            publication_id_factory=lambda key: "p-" + key,
            failure_point=PublicationFailurePoint.AFTER_PUBLICATION_RECORD,
        )
        with pytest.raises(RuntimeError):
            boundary.publish(idempotency_key="bulk-retry", candidate=candidate)
        assert connection.execute("SELECT count(*) FROM telchi.atomic.sales_document").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM telchi.atomic.sales_line").fetchone()[0] == 0
        receipt = boundary.publish(idempotency_key="bulk-retry", candidate=candidate)
        assert receipt.publication_identity == "p-bulk-retry"
        assert connection.execute("SELECT count(*) FROM telchi.atomic.sales_line").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM telchi.ops.initial_publications_v1").fetchone()[0] == 1
    finally:
        connection.close()


def test_inventory_publication_uses_one_bulk_insert_and_set_based_replace() -> None:
    import duckdb

    connection = duckdb.connect()
    try:
        _create_atomic_tables(connection)
        connection.execute("INSERT INTO telchi.atomic.inventory_balance VALUES ('old','SAP_B1_HANA','OITW','I1','W1','1','0','0','old','old','REFERENCE_V2','','v','1')")
        rows = [{"ItemCode": "I1", "WhsCode": "W1", "OnHand": "3", "IsCommited": "1", "OnOrder": "2"}, {"ItemCode": "I2", "WhsCode": "W1", "OnHand": "4", "IsCommited": "0", "OnOrder": "1"}]
        candidate = transform("inventory", rows, {"extraction_id": "e1", "source_as_of": "2025-03-01T00:00:00Z"})
        recorder = _RecordingConnection(connection)
        publication_writer({"sales_document": None, "sales_line": None, "inventory_balance_snapshot": "inventory_balance"})(recorder, candidate, "p1", lambda _point: None)
        values = connection.execute("SELECT item_code, on_hand FROM telchi.atomic.inventory_balance ORDER BY item_code").fetchall()
        assert values == [("I1", "3"), ("I2", "4")]
        target_inserts = [sql for sql in recorder.statements if sql.lstrip().upper().startswith("INSERT INTO TELCHI.ATOMIC")]
        assert len(target_inserts) == 1
        assert "SELECT" in target_inserts[0].upper()
        assert sum("DELETE FROM TELCHI.ATOMIC" in sql.upper() for sql in recorder.statements) == 1
    finally:
        connection.close()
