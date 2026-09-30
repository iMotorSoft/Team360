from __future__ import annotations

import csv
import json
from pathlib import Path

from .build_outputs import ATOMIC, FAMILIES, GATE, METRICS, QUERIES, build

OUT = Path(__file__).parent


def _rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_build_is_reproducible_and_does_not_materialize_facts() -> None:
    summary = build()
    assert summary["gate"] == GATE
    assert summary["atomic_tables_created"] == 0
    assert summary["business_tables_created"] == 0
    assert summary["current_tables_created"] == 0
    assert summary["sap_write_count"] == 0
    assert not list(OUT.glob("*.parquet"))


def test_p0_queries_have_complete_execution_contract() -> None:
    rows = _rows("ceo_query_catalog.csv")
    p0 = [row for row in rows if row["priority"] == "P0"]
    assert p0
    assert all(json.loads(row["semantic_plan"])["scope"]["authorization"] == "REQUIRED" for row in p0)
    assert all(row["target_data_product"] for row in p0)
    assert all(row["latency_class"] in {"A", "B", "C", "D"} for row in p0)
    assert all(row["freshness_class"] for row in p0)
    assert all(row["drilldown_id"] for row in p0)
    assert all(row["llm_arithmetic_allowed"] == "NO" for row in p0)
    assert all(row["raw_legacy_direct"] == "NO" for row in p0)
    assert all(row["sap_live_query"] == "NO" for row in p0)


def test_catalog_coverage_and_ambiguity_are_explicit() -> None:
    assert {row["family"] for row in _rows("ceo_query_catalog.csv")} == set(FAMILIES)
    assert len(QUERIES) >= 50
    metric_rows = _rows("metric_catalog.csv")
    assert len(metric_rows) == len(METRICS)
    assert all(row["business_definition"] and row["formula_logical"] for row in metric_rows)
    assert all("@1" in row["semantic_version"] for row in metric_rows)
    assert {row["term"] for row in _rows("semantic_ambiguity_catalog.csv")} >= {"ventas", "stock", "crédito", "contado", "producción", "hoy"}


def test_financial_quantity_credit_and_routing_contracts_are_not_vague() -> None:
    metrics = {row["metric_id"]: row for row in _rows("metric_catalog.csv")}
    for metric_id in ("NET_SALES", "TOTAL_RECEIVABLE", "CURRENT_RECEIVABLE", "OVERDUE_RECEIVABLE", "PAYMENT_RECEIVED"):
        assert metrics[metric_id]["default_currency"]
        assert metrics[metric_id]["time_semantics"]
        assert metrics[metric_id]["sign_semantics"]
    for metric_id in ("QUANTITY_SOLD", "ON_HAND", "AVAILABLE", "ON_ORDER"):
        assert metrics[metric_id]["default_unit"]
    routing = {row["data_product"]: row for row in _rows("query_data_product_routing.csv")}
    assert routing["current.stock_current"]["grain"] == "product × warehouse"
    assert routing["current.customer_credit_current"]["grain"] == "customer or customer × document"
    assert routing["business.sales_flow"]["grain"] == "canonical commercial line"


def test_atomic_requirements_are_derived_but_not_built() -> None:
    rows = _rows("atomic_requirements.csv")
    assert len(rows) == len(ATOMIC)
    assert all(row["materialize_now"] == "NO" for row in rows)
    assert [row["build_priority"] for row in rows] == [str(i) for i in range(1, len(rows) + 1)]


def test_dev_prod_and_security_invariants() -> None:
    contract = json.loads((OUT / "semantic_plan_contract.json").read_text(encoding="utf-8"))
    assert contract["dev_prod_logical_names_identical"] is True
    assert contract["postgres_catalog_database"] == "team360_telchi_ducklake"
    assert contract["postgres_runtime_role"] == "team360_telchi_ducklake"
    assert contract["security_order"][:3] == ["identity", "authorization_context", "entity_resolution_within_scope"]
    assert contract["llm_rule"] == "LLM interprets and drafts; DuckDB computes"


def test_baseline_includes_required_probes_and_non_subsecond_targets() -> None:
    probes = {row["probe"]: row for row in _rows("benchmark_baseline.csv")}
    assert {"entity_resolution", "external_reference_lookup", "crosswalk_lookup", "semantic_catalog_lookup", "ducklake_warm_query"} <= probes.keys()
    assert float(probes["ducklake_warm_query"]["p95_ms"]) == 10.0535
    classes = {row["class"]: row for row in _rows("performance_classes.csv")}
    assert classes["A"]["target_p95_ms"] == "100"
    assert classes["B"]["target_p95_ms"] == "300"
    assert classes["C"]["target_p95_ms"] == "750"
