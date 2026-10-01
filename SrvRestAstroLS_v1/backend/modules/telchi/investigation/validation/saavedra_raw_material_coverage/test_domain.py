"""Focused unit tests for the Saavedra raw-material coverage domain.

No SAP access. Deterministic pure-logic contracts.
"""
from __future__ import annotations

import math

from modules.telchi.investigation.validation.saavedra_raw_material_coverage.domain import (
    BomEdge,
    ItemFacts,
    build_parent_index,
    build_result,
    classify_coverage,
    classify_item,
    days_of_coverage,
    derived_demand,
    normalise_bom,
    usage_per_unit,
    CLASS_FINISHED_PRODUCT,
    CLASS_FRACTIONATED_PRODUCT,
    CLASS_PACKAGING_MATERIAL,
    CLASS_RAW_MATERIAL,
    CLASS_SEMI_FINISHED,
    RISK_ALTO,
    RISK_ATENCION,
    RISK_CRITICO,
    RISK_NO_DEMAND,
    RISK_OK,
    RISK_QUIEBRE,
)


def _facts(**overrides) -> ItemFacts:
    base = dict(
        itemcode="X", itemname="ITEM", itms_grp=129, group_name="INSUMO",
        invnt_uom="KG", invnt_item=True, sell_item=False, prchse_item=True,
        is_produced=False, is_bom_component=False, is_bom_parent=False,
    )
    base.update(overrides)
    return ItemFacts(**base)


def test_classify_raw_material_is_structural() -> None:
    assert classify_item(_facts(is_bom_component=True)) == CLASS_RAW_MATERIAL


def test_classify_packaging_by_group_and_name() -> None:
    assert classify_item(_facts(itms_grp=130, group_name="MAT. ACONDICIONADO",
                                is_bom_component=True)) == CLASS_PACKAGING_MATERIAL
    assert classify_item(_facts(itemname="TAPA PET BLANCA", is_bom_component=True)) == CLASS_PACKAGING_MATERIAL


def test_classify_produced_and_fractionated() -> None:
    assert classify_item(_facts(is_produced=True, sell_item=True)) == CLASS_FINISHED_PRODUCT
    assert classify_item(_facts(is_produced=True, itms_grp=127)) == CLASS_FRACTIONATED_PRODUCT


def test_classify_semi_finished_intermediate() -> None:
    assert classify_item(_facts(is_produced=True, is_bom_parent=True, sell_item=False)) == CLASS_SEMI_FINISHED


def test_bom_normalisation_uses_base_quantity() -> None:
    edges = [
        BomEdge("P", "R", quantity=144, base_quantity=1200),  # 0.12
        BomEdge("P", "R", quantity=36, base_quantity=1200),   # 0.03
        BomEdge("P", "Q", quantity=10, base_quantity=0),      # unresolvable
    ]
    children = normalise_bom(edges)
    assert math.isclose(children["P"]["R"], 0.15, rel_tol=1e-9)
    assert "Q" not in children["P"]


def test_multilevel_usage_is_compounded() -> None:
    # R -> S (2 per S) -> P (3 per P)
    children = {"S": {"R": 2.0}, "P": {"S": 3.0}}
    parents = build_parent_index(children)
    usage = usage_per_unit("R", parents)
    assert math.isclose(usage["S"], 2.0, rel_tol=1e-9)
    assert math.isclose(usage["P"], 6.0, rel_tol=1e-9)


def test_diamond_convergence_is_summed_not_duplicated() -> None:
    # R used twice inside the same parent via distinct intermediate paths.
    children = {"A": {"R": 2.0}, "B": {"R": 5.0}, "P": {"A": 3.0, "B": 4.0}}
    parents = build_parent_index(children)
    usage = usage_per_unit("R", parents)
    # 3*2 + 4*5 = 26 per P
    assert math.isclose(usage["P"], 26.0, rel_tol=1e-9)


def test_cycle_is_bounded() -> None:
    children = {"A": {"B": 1.0}, "B": {"A": 1.0}}
    parents = build_parent_index(children)
    usage = usage_per_unit("A", parents, max_depth=8)
    assert usage  # terminates, does not raise
    assert usage.get("A") is None


def test_derived_demand_and_top_contributors() -> None:
    children = {"P1": {"R": 0.12}, "P2": {"R": 0.03}}
    parents = build_parent_index(children)
    sales = {"P1": 1000.0, "P2": 500.0, "OTHER": 999.0}
    total, per = derived_demand("R", parents, sales)
    assert math.isclose(total, 1000 * 0.12 + 500 * 0.03, rel_tol=1e-9)
    assert set(per) == {"P1", "P2"}


def test_coverage_and_risk_thresholds() -> None:
    assert days_of_coverage(420, 0) is None
    assert days_of_coverage(420, 9.1) == 420 / 9.1
    assert classify_coverage(0, 0) == RISK_QUIEBRE
    assert classify_coverage(10, 100) == RISK_CRITICO
    assert classify_coverage(20, 100) == RISK_ALTO
    assert classify_coverage(45, 100) == RISK_ATENCION
    assert classify_coverage(60, 100) == RISK_OK
    assert classify_coverage(None, 100) == RISK_NO_DEMAND


def test_build_result_prefers_actual_consumption() -> None:
    facts = _facts(itemcode="R", itemname="RAW", invnt_uom="KG", is_bom_component=True)
    result = build_result(
        facts, CLASS_RAW_MATERIAL, stock=420.0, committed=0.0, on_order=0.0,
        demand_window_days=90, direct_sales_qty=0.0, derived_demand_qty=900.0,
        actual_consumption_qty=900.0, transfer_out_qty=0.0, contributors={},
    )
    assert result.executive_basis == "ACTUAL_CONSUMPTION"
    assert math.isclose(result.coverage_days, 420 / (900 / 90), rel_tol=1e-9)
    assert result.risk == RISK_ATENCION


def test_build_result_uses_commercial_when_no_actual() -> None:
    facts = _facts(itemcode="R", itemname="RAW", invnt_uom="KG", is_bom_component=True)
    result = build_result(
        facts, CLASS_RAW_MATERIAL, stock=1800.0, committed=0.0, on_order=0.0,
        demand_window_days=90, direct_sales_qty=100.0, derived_demand_qty=800.0,
        actual_consumption_qty=0.0, transfer_out_qty=0.0,
        contributors={"P1": 800.0},
    )
    assert result.executive_basis == "COMMERCIAL_EQUIVALENT_DEMAND"
    assert math.isclose(result.commercial_demand_qty, 900.0, rel_tol=1e-9)
    assert result.risk == RISK_OK


def test_stockout_is_quiebre_even_without_demand() -> None:
    facts = _facts(itemcode="R", itemname="RAW")
    result = build_result(
        facts, CLASS_RAW_MATERIAL, stock=0.0, committed=0.0, on_order=0.0,
        demand_window_days=90, direct_sales_qty=0.0, derived_demand_qty=0.0,
        actual_consumption_qty=0.0, transfer_out_qty=0.0, contributors={},
    )
    assert result.risk == RISK_QUIEBRE