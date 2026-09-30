"""Focused tests for TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from modules.telchi.datalake.material_supply_fact_capture import (
    CaptureAbort,
    DatasetSpec,
    _f,
    build_control_select,
    build_select,
    dataset_segments,
    discover_columns,
    existing_segment_manifests,
    linkage_controls,
    offline_validate,
    reconcile_segment,
    run_capture,
    validate_logical_keys,
)
from modules.telchi.datalake.sql import assert_read_only_select

COLUMNS = {
    "OITT": {"Code": {}, "Name": {}, "TreeType": {}, "Qauntity": {}},
    "ITT1": {"Father": {}, "ChildNum": {}, "VisOrder": {}, "Code": {}, "Quantity": {}, "Warehouse": {}},
    "OPOR": {"DocEntry": {}, "DocNum": {}, "DocDate": {}, "CardCode": {}},
    "POR1": {"DocEntry": {}, "LineNum": {}, "ItemCode": {}, "Quantity": {}, "OpenQty": {}, "BaseType": {}, "BaseEntry": {}, "BaseLine": {}},
}

FULL_SPEC = DatasetSpec(
    name="bom_header", header_table="OITT", line_table=None, date_field=None,
    key_fields=("Code",), quantity_field=None, kind="full",
    fields=(_f("Code", "H"), _f("Name", "H", "Name", "ItemName"), _f("TreeType", "H"), _f("U_MEDIDA", "H")),
)
MONTH_SPEC = DatasetSpec(
    name="purchase_order_line", header_table="OPOR", line_table="POR1", date_field="DocDate",
    key_fields=("DocEntry", "LineNum"), quantity_field="Quantity",
    fields=(_f("DocEntry", "H"), _f("DocDate", "H"), _f("LineNum", "L"), _f("ItemCode", "L"), _f("Quantity", "L")),
)


class FakeSource:
    """Deterministic in-memory stand-in for the HANA read-only adapter."""

    def __init__(self, columns, capture_rows, control_rows=None):
        self.columns = columns
        self.capture_rows = capture_rows
        self.control_rows = control_rows or {}
        self.queries: list[tuple[str, str, tuple]] = []
        self.query_log: list[dict] = []
        self.sap_write_count = 0

    def query_read_only(self, query_id, sql, params=()):
        assert_read_only_select(sql)
        self.queries.append((query_id, sql, params))
        self.query_log.append({"query_id": query_id})
        if query_id.startswith("column_discovery_"):
            table = query_id[len("column_discovery_"):]
            return [{"COLUMN_NAME": name, "DATA_TYPE_NAME": "X"} for name in self.columns.get(table, {})]
        if query_id.startswith("control_"):
            entry = self.control_rows.get(query_id)
            return [entry] if entry is not None else []
        return self.capture_rows.get(query_id, [])


def _discovery(source, spec):
    available = {}
    for table in spec.tables:
        available[table] = discover_columns(source, table)
    return available


def test_build_select_is_explicit_and_read_only():
    source = FakeSource(COLUMNS, {})
    sql, absent = build_select(MONTH_SPEC, _discovery(source, MONTH_SPEC))
    assert sql.upper().startswith("SELECT")
    assert "SELECT *" not in sql.upper()
    assert 'H."DocEntry" AS "DocEntry"' in sql
    assert 'L."LineNum" AS "LineNum"' in sql
    assert 'JOIN "TELCHI"."POR1" L' in sql
    assert 'WHERE H."DocDate" >= ? AND H."DocDate" < ?' in sql
    assert "ORDER BY H.\"DocEntry\", L.\"LineNum\"" in sql
    assert absent == []


def test_column_discovery_marks_absent_optional_but_fails_missing_keys():
    source = FakeSource(COLUMNS, {})
    sql, absent = build_select(FULL_SPEC, _discovery(source, FULL_SPEC))
    assert "U_MEDIDA" in absent
    assert 'H."Name" AS "Name"' in sql

    missing_key_spec = DatasetSpec(
        name="bad", header_table="OITT", line_table=None, date_field=None,
        key_fields=("NotAColumn",), quantity_field=None, kind="full",
        fields=(_f("Code", "H"), _f("NotAColumn", "H")),
    )
    with pytest.raises(CaptureAbort):
        build_select(missing_key_spec, _discovery(source, missing_key_spec))


def test_control_select_is_read_only_aggregate():
    source = FakeSource(COLUMNS, {})
    sql = build_control_select(MONTH_SPEC, _discovery(source, MONTH_SPEC))
    assert "COUNT(*) AS \"row_count\"" in sql
    assert 'SUM(CASE WHEN L."Quantity" IS NULL' in sql
    assert_read_only_select(sql)


def test_segment_naming_is_stable():
    assert dataset_segments(FULL_SPEC, as_of=date(2026, 9, 24)) == [("full", ())]
    labels = [label for label, _ in dataset_segments(MONTH_SPEC, as_of=date(2026, 9, 24))]
    assert labels == [f"2026-{month:02d}" for month in range(1, 10)]
    january = dataset_segments(MONTH_SPEC, as_of=date(2026, 1, 15))
    assert january == [("2026-01", ("2026-01-01", "2026-02-01"))]


def test_logical_key_validation_detects_duplicates():
    rows = [{"DocEntry": 1, "LineNum": 0}, {"DocEntry": 1, "LineNum": 0}]
    with pytest.raises(CaptureAbort):
        validate_logical_keys(rows, ("DocEntry", "LineNum"), label="x")
    result = validate_logical_keys([{"DocEntry": 1, "LineNum": 0}, {"DocEntry": 1, "LineNum": 1}],
                                   ("DocEntry", "LineNum"), label="x")
    assert result["distinct_keys"] == 2
    assert result["duplicates"] == 0


def test_reconciliation_exact_and_source_movement():
    rows = [{"DocEntry": 1, "LineNum": 0, "Quantity": 5.0}]
    manifest = {"row_count": 1}
    exact = reconcile_segment(spec=MONTH_SPEC, captured_rows=rows, manifest=manifest,
                              control={"row_count": 1, "key_DocEntry_nonnull": 1,
                                       "key_LineNum_nonnull": 1, "quantity_sum": 5.0})
    assert exact["status"] == "EXACT"
    moved = reconcile_segment(spec=MONTH_SPEC, captured_rows=rows, manifest=manifest,
                              control={"row_count": 2, "key_DocEntry_nonnull": 2,
                                       "key_LineNum_nonnull": 2, "quantity_sum": 9.0})
    assert moved["status"] == "DEGRADED"
    assert moved["source_changed_after_capture"] is True
    corrupt = reconcile_segment(spec=MONTH_SPEC, captured_rows=rows, manifest={"row_count": 2}, control=None)
    assert corrupt["status"] == "MISMATCH"


def test_capture_writes_raw_and_is_idempotent(tmp_path):
    source = FakeSource(
        COLUMNS,
        {"capture_bom_header_full": [{"Code": "A", "Name": "Alpha", "TreeType": "I"}]},
        {"control_bom_header_full": {"row_count": 1, "key_Code_nonnull": 1}},
    )
    first = run_capture(source=source, datasets=[FULL_SPEC], root=tmp_path, as_of=date(2026, 9, 24),
                        logger=lambda *_: None)
    assert first["captured_rows"]["bom_header"] == 1
    manifests = existing_segment_manifests(tmp_path, FULL_SPEC, "full")
    assert len(manifests) == 1
    assert manifests[0]["row_count"] == 1
    parquet = Path(manifests[0]["file_references"][0])
    assert parquet.is_file()
    captures_after_first = [q for q in source.queries if q[0].startswith("capture_")]

    second = run_capture(source=source, datasets=[FULL_SPEC], root=tmp_path, as_of=date(2026, 9, 24),
                         logger=lambda *_: None)
    assert second["results"][0]["status"] == "SEGMENT_ALREADY_CAPTURED"
    # Only metadata discovery may run again; no fact capture query is issued.
    assert [q for q in source.queries if q[0].startswith("capture_")] == captures_after_first
    assert len(existing_segment_manifests(tmp_path, FULL_SPEC, "full")) == 1  # no duplicate


def test_empty_segment_is_skipped_without_writing(tmp_path):
    source = FakeSource(COLUMNS, {}, {})
    report = run_capture(source=source, datasets=[FULL_SPEC], root=tmp_path, as_of=date(2026, 9, 24),
                         logger=lambda *_: None)
    assert report["results"][0]["status"] == "SEGMENT_EMPTY_SKIPPED"
    assert not (tmp_path / "bom_header" / "full").exists()


def test_offline_validate_never_calls_hana(tmp_path):
    source = FakeSource(COLUMNS, {"capture_bom_header_full": [{"Code": "A", "Name": "Alpha"}]}, {})
    run_capture(source=source, datasets=[FULL_SPEC], root=tmp_path, as_of=date(2026, 9, 24),
                logger=lambda *_: None)

    class BombSource:
        def query_read_only(self, *args, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("HANA must not be contacted during offline validation")

    offline = offline_validate(tmp_path, ["bom_header"])
    assert offline["hana_query_count"] == 0
    assert offline["datasets"][0]["row_count"] == 1
    assert offline["all_manifests_consistent"] is True


def test_linkage_controls_are_source_native_only():
    captured = {
        "production_order": [{"DocEntry": 10}, {"DocEntry": 11}],
        "production_issue": [
            {"BaseType": 202, "BaseEntry": 10},
            {"BaseType": 202, "BaseEntry": 99},
            {"BaseType": -1, "BaseEntry": None},
        ],
        "purchase_order_line": [{"DocEntry": 5, "LineNum": 0}],
        "purchase_receipt_line": [
            {"BaseType": 22, "BaseEntry": 5, "BaseLine": 0},
            {"BaseType": 18, "BaseEntry": 5, "BaseLine": 0},
        ],
    }
    result = linkage_controls(captured)
    assert result["PRODUCTION_ISSUE_LINES_CAPTURED"] == 3
    assert result["PRODUCTION_ISSUE_BASETYPE_202"] == 2
    assert result["PRODUCTION_ISSUE_LINKED_TO_OWOR"] == 1
    assert result["PRODUCTION_ISSUE_NOT_LINKED_TO_OWOR"] == 2
    assert result["RECEIPT_LINES_WITH_PO_LINEAGE"] == 1
    assert result["RECEIPT_LINES_WITHOUT_PO_LINEAGE"] == 1


def test_manifest_row_count_matches_parquet(tmp_path):
    source = FakeSource(COLUMNS, {"capture_bom_header_full": [
        {"Code": "A", "Name": "Alpha"}, {"Code": "B", "Name": "Beta"}]}, {})
    run_capture(source=source, datasets=[FULL_SPEC], root=tmp_path, as_of=date(2026, 9, 24),
                logger=lambda *_: None)
    manifest_path = next((tmp_path / "bom_header" / "full").rglob("manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    offline = offline_validate(tmp_path, ["bom_header"])
    assert offline["datasets"][0]["row_count"] == manifest["row_count"] == 2


def test_resume_from_existing_completed_segment(tmp_path):
    source = FakeSource(COLUMNS, {"capture_bom_header_full": [{"Code": "A"}]}, {})
    run_capture(source=source, datasets=[FULL_SPEC], root=tmp_path, as_of=date(2026, 9, 24),
                logger=lambda *_: None)
    # A new run with a fresh source must resume, not recapture.
    resumed_source = FakeSource(COLUMNS, {"capture_bom_header_full": [{"Code": "A"}]}, {})
    report = run_capture(source=resumed_source, datasets=[FULL_SPEC], root=tmp_path,
                         as_of=date(2026, 9, 24), logger=lambda *_: None)
    assert report["results"][0]["status"] == "SEGMENT_ALREADY_CAPTURED"
    assert not any(query_id == "capture_bom_header_full" for query_id, _, _ in resumed_source.queries)