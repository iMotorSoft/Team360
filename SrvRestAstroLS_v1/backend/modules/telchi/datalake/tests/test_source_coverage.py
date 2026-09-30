from __future__ import annotations

import json
from pathlib import Path

from modules.telchi.datalake.create_initial import run_initial
from modules.telchi.datalake.planner import inventory_movement_segments_from_bounds
from modules.telchi.datalake.source_coverage import (
    GATE,
    build_full_initial_plan,
    discover_sap,
    overlap_summary,
)


class FakeHana:
    sap_write_count = 0

    def __init__(self) -> None:
        self.query_log: list[dict[str, object]] = []
        self.rows = {
            "connectivity_select_1": [{"ok": 1}],
            "sales_coverage_overall": [{"min_doc_date": "2022-03-31", "max_doc_date": "2022-04-30", "min_doc_entry": 10, "max_doc_entry": 30, "document_count": 3, "line_count": 5, "non_canceled_document_count": 2, "canceled_document_count": 1}],
            "sales_coverage_monthly": [{"year": 2022, "month": 3, "min_doc_date": "2022-03-31", "max_doc_date": "2022-03-31", "min_doc_entry": 10, "max_doc_entry": 10, "document_count": 1, "line_count": 1, "non_canceled_document_count": 1, "canceled_document_count": 0}],
            "sales_first_non_canceled": [{"doc_date": "2022-03-31", "doc_entry": 10, "doc_num": 100}],
            "sales_first_canceled": [{"doc_date": "2022-04-30", "doc_entry": 30, "doc_num": 300}],
            "sales_last_document": [{"doc_date": "2022-04-30", "doc_entry": 30, "doc_num": 300, "canceled": "Y"}],
            "sales_orphan_headers": [{"orphan_headers": 0}],
            "sales_orphan_lines": [{"orphan_lines": 0}],
            "inventory_movement_coverage_overall": [{"min_doc_date": "2022-03-31", "max_doc_date": "2022-04-30", "min_trans_num": 1, "max_trans_num": 250, "row_count": 250}],
            "inventory_movement_coverage_monthly": [{"year": 2022, "month": 3, "min_doc_date": "2022-03-31", "max_doc_date": "2022-03-31", "min_trans_num": 1, "max_trans_num": 100, "row_count": 100}],
            "inventory_movement_type_distribution": [{"trans_type": 13, "row_count": 100}],
            "inventory_state_current": [{"row_count": 2, "distinct_items": 2, "distinct_warehouses": 1, "source_as_of": "2026-09-17T00:00:00+00:00"}],
        }

    def _execute(self, query_id: str, sql: str, params=()):
        self.query_log.append({"query_id": query_id, "sap_access_mode": "READ_ONLY", "sap_write_count": 0})
        return self.rows[query_id]


def test_coverage_discovery_is_aggregate_only_and_read_only() -> None:
    result = discover_sap(FakeHana())
    assert result["connectivity_pass"] == "YES"
    assert result["sales"]["overall"]["min_doc_date"] == "2022-03-31"
    assert result["inventory_movements"]["overall"]["max_trans_num"] == 250
    assert result["inventory_state"]["source_type"] == "CURRENT_STATE"
    assert result["sap_write_count"] == 0
    assert all(item["sap_access_mode"] == "READ_ONLY" for item in result["query_log"])


def test_movement_segments_are_bounded_and_half_open() -> None:
    segments = inventory_movement_segments_from_bounds([("2022-03-01", "2022-04-01", 1, 250, 250)], max_transnum_per_segment=100)
    assert [(item.key_from, item.key_to) for item in segments] == [("1", "101"), ("101", "201"), ("201", "251")]
    assert all(item.strategy == "TRANSNUM_DATE_BOUNDED" for item in segments)


def test_full_plan_marks_trusted_sales_scope_and_current_state_separately() -> None:
    coverage = discover_sap(FakeHana())
    plan = build_full_initial_plan(coverage, {"trusted_scope_count": 1, "trusted_scopes": [{"domain": "sales", "segment_id": "sales-2022-03-01-0000", "business_date_from": "2022-03-01", "business_date_to": "2022-04-01", "source_key_from": "10", "source_key_to": "11"}], "table_counts": {"inventory_balance": 1}}, max_docentries=100)
    sales = plan["domains"][0]["segments"]
    assert sales[0]["status"] == "ALREADY_TRUSTED"
    state = plan["domains"][2]["segments"]
    assert state[0]["domain"] == "inventory_current_state"
    assert state[0]["source_type"] == "CURRENT_STATE"
    assert plan["legacy_merged"] is False


def test_overlap_is_documented_without_merge() -> None:
    result = overlap_summary({"min_date": "2018-01-31", "max_date": "2024-05-31"}, {"sales": {"overall": {"min_doc_date": "2022-03-31", "max_doc_date": "2026-09-17"}}})
    assert result["overlap_from"] == "2022-03-31"
    assert result["overlap_to"] == "2024-05-31"
    assert result["merge_executed"] == "NO"


def test_create_initial_plan_only_from_coverage_never_publishes(tmp_path: Path) -> None:
    coverage = discover_sap(FakeHana())
    bundle = {"coverage": coverage, "existing_ducklake": {"trusted_scope_count": 0, "trusted_scopes": [], "table_counts": {}}}
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(json.dumps(bundle), encoding="utf-8")
    result = run_initial(domains=["sales", "inventory"], start=None, end=None, plan_only=True, coverage_file=str(coverage_path), plan_output_dir=tmp_path)
    assert result["status"] == "PLAN_ONLY"
    assert result["published"] == "NO"
    assert result["full_historical_build_started"] == "NO"
    assert (tmp_path / "full_initial_build_plan.json").is_file()
    assert result["gate"] == GATE
