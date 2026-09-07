"""Production reconciliation domain (pure logic + read-only SQL).

Semantics (validated against real SAP 2026-08-26):
  - EXPECTED_FOR_PLAN = (BaseQtyNum/BaseQtyDen) * OWOR.PlannedQty
  - EXPECTED_FOR_ACTUAL_OUTPUT = (BaseQtyNum/BaseQtyDen) * NET_ACTUAL_OUTPUT_QTY
  - NET_ACTUAL_CONSUMPTION = SUM(IGE1.Quantity) BT=202
  - NET_ACTUAL_OUTPUT_QTY = SUM(IGN1.Quantity) BT=202
  - Three distinct variances: output-plan, component-plan, normalized
  - NORMALIZED variance is the gate's primary metric
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from modules.telchi.investigation.validation.production.recipe_bom_domain import expected_qty


@dataclass
class ReconciliationLine:
    """Atomic reconciliation per order x WOR1 line."""
    production_docentry: int
    production_docnum: int
    parent_item: str
    wor1_line: int
    component_item: str
    issue_method: str
    planned_output_qty: Decimal
    actual_output_qty: Decimal
    base_qty_num: Decimal
    base_qty_den: Decimal
    expected_for_plan: Decimal
    expected_for_actual_output: Decimal
    actual_consumption: Decimal
    plan_variance_qty: Decimal
    normalized_variance_qty: Decimal
    normalized_variance_pct: float | None
    consumption_ratio: float | None
    output_completion_ratio: float | None
    plan_classification: str
    normalized_classification: str
    is_produced_component: bool
    produced_parent_count: int
    is_rework: bool
    uom_confirmation: str = "EXACT"
    confidence: str = "EXACT_DOCUMENT_LINK"

    def to_dict(self) -> dict:
        return {
            "production_docentry": self.production_docentry,
            "production_docnum": self.production_docnum,
            "parent_item": self.parent_item,
            "wor1_line": self.wor1_line,
            "component_item": self.component_item,
            "issue_method": self.issue_method,
            "planned_output_qty": str(self.planned_output_qty),
            "actual_output_qty": str(self.actual_output_qty),
            "expected_for_plan": str(self.expected_for_plan),
            "expected_for_actual_output": str(self.expected_for_actual_output),
            "actual_consumption": str(self.actual_consumption),
            "plan_variance_qty": str(self.plan_variance_qty),
            "normalized_variance_qty": str(self.normalized_variance_qty),
            "normalized_variance_pct": self.normalized_variance_pct,
            "consumption_ratio": self.consumption_ratio,
            "output_completion_ratio": self.output_completion_ratio,
            "plan_classification": self.plan_classification,
            "normalized_classification": self.normalized_classification,
            "is_produced_component": self.is_produced_component,
            "produced_parent_count": self.produced_parent_count,
            "is_rework": self.is_rework,
            "uom_confirmation": self.uom_confirmation,
            "confidence": self.confidence,
        }


def classify_variance(expected: Decimal, actual: Decimal, tol: Decimal) -> str:
    """Classify a variance pair."""
    if expected == 0:
        if actual == 0:
            return "EXPECTED_ZERO_ACTUAL_ZERO"
        return "EXPECTED_ZERO_ACTUAL_POSITIVE"
    if actual == 0:
        return "EXPECTED_NOT_CONSUMED"
    if abs(actual - expected) <= tol:
        return "EXACT"
    if actual > expected:
        return "OVER"
    return "UNDER"


def build_line(
    order: tuple,
    wor1: tuple,
    actual_output: Decimal,
    actual_consumption: Decimal,
    is_produced_component: bool,
    produced_parent_count: int,
    tol: Decimal = Decimal("0.001"),
) -> ReconciliationLine:
    """Build a reconciliation line.

    order: (docentry, docnum, parent_item, planned_qty)
    wor1:  (line, component, num, den, method)
    """
    de, docnum, parent, planned = order
    line, comp, num, den, method = wor1
    factor = Decimal(str(num)) / (Decimal(str(den)) if den else Decimal(1))

    exp_plan = factor * planned
    exp_norm = factor * actual_output

    plan_cls = classify_variance(exp_plan, actual_consumption, tol)
    norm_cls = classify_variance(exp_norm, actual_consumption, tol)

    plan_var = actual_consumption - exp_plan
    norm_var = actual_consumption - exp_norm
    norm_pct = float(norm_var / exp_norm * 100) if exp_norm != 0 else None
    ratio = float(actual_consumption / exp_norm) if exp_norm != 0 else None
    comp_ratio = float(actual_output / planned) if planned != 0 else None

    return ReconciliationLine(
        production_docentry=de, production_docnum=docnum, parent_item=parent,
        wor1_line=line, component_item=comp, issue_method=method,
        planned_output_qty=planned, actual_output_qty=actual_output,
        base_qty_num=Decimal(str(num)), base_qty_den=Decimal(str(den)),
        expected_for_plan=exp_plan, expected_for_actual_output=exp_norm,
        actual_consumption=actual_consumption,
        plan_variance_qty=plan_var, normalized_variance_qty=norm_var,
        normalized_variance_pct=norm_pct, consumption_ratio=ratio,
        output_completion_ratio=comp_ratio,
        plan_classification=plan_cls, normalized_classification=norm_cls,
        is_produced_component=is_produced_component,
        produced_parent_count=produced_parent_count,
        is_rework=(parent == comp),
    )