from __future__ import annotations

import pytest

from modules.telchi.investigation.validation.order_delivery_efficiency.document_chain_v1 import (
    MAX_ORDER_DOCENTRY,
    SAP_WRITE_COUNT,
    classify_quantity,
    classify_route,
)


def _route_row(deliveries: int = 0, direct: int = 0, via_delivery: int = 0) -> dict:
    return {
        "active_delivery_count": deliveries,
        "active_direct_invoice_count": direct,
        "active_delivery_invoice_count": via_delivery,
    }


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (_route_row(), "ORDER_WITHOUT_ACTIVE_POSTERIOR_DOCUMENT"),
        (_route_row(direct=1), "ORDER_TO_INVOICE_DIRECT"),
        (_route_row(deliveries=1), "ORDER_TO_DELIVERY"),
        (_route_row(deliveries=1, via_delivery=1), "ORDER_TO_DELIVERY_TO_INVOICE"),
    ],
)
def test_route_classification(row: dict, expected: str) -> None:
    assert classify_route(row) == expected


@pytest.mark.parametrize(
    ("ordered", "exited", "expected"),
    [
        (10, 0, "NO_EXIT"),
        (10, 4, "PARTIAL_EXIT"),
        (10, 10, "FULL_EXIT"),
        (10, 11, "OVER_EXIT"),
    ],
)
def test_quantity_classification(ordered: int, exited: int, expected: str) -> None:
    assert classify_quantity(ordered, exited) == expected


def test_gate_1_cohort_and_write_policy_are_frozen() -> None:
    assert MAX_ORDER_DOCENTRY == 215152
    assert SAP_WRITE_COUNT == 0
