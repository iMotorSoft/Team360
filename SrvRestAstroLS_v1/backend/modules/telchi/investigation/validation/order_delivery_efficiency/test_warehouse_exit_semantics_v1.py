from __future__ import annotations

from modules.telchi.investigation.validation.order_delivery_efficiency.warehouse_exit_semantics_v1 import (
    GATE2_ACTIVE_ORDERS,
    GATE2_FULL_MOVEMENT,
    GATE2_OVER_EXIT,
    GATE2_PARTIAL_MOVEMENT,
    GATE2_SNAPSHOT_DATE,
    GATE2_SNAPSHOT_TIME,
    GATE2_WITHOUT_POSTERIOR,
    MAX_ORDER_DOCENTRY,
    SAP_WRITE_COUNT,
    classify_quantity,
    evidence_class,
)


def test_quantity_classification_has_no_silent_tolerance() -> None:
    assert classify_quantity("10", "0") == "NO_MOVEMENT"
    assert classify_quantity("10", "9.999999") == "PARTIAL"
    assert classify_quantity("10", "10") == "EXACT"
    assert classify_quantity("10", "10.000001") == "OVER"


def test_registered_exit_evidence_classes() -> None:
    assert evidence_class(True, True) == "WAREHOUSE_EXIT_CONFIRMED"
    assert evidence_class(True, False) == "WAREHOUSE_EXIT_OPERATIONAL"
    assert evidence_class(False, True) == "NOT_AVAILABLE"


def test_gate2_snapshot_and_write_policy_are_immutable() -> None:
    assert MAX_ORDER_DOCENTRY == 215152
    assert GATE2_SNAPSHOT_DATE == "2026-09-14"
    assert GATE2_SNAPSHOT_TIME == 112115
    assert SAP_WRITE_COUNT == 0


def test_reconciled_coverage_preserves_gate2_cardinality() -> None:
    reserve_delivery_exits = 107
    complete = GATE2_FULL_MOVEMENT + GATE2_OVER_EXIT + reserve_delivery_exits
    first_exit = complete + GATE2_PARTIAL_MOVEMENT
    assert complete == 2561
    assert first_exit == 2631
    assert GATE2_ACTIVE_ORDERS - first_exit == 211
    assert GATE2_ACTIVE_ORDERS - first_exit - GATE2_WITHOUT_POSTERIOR == 4
