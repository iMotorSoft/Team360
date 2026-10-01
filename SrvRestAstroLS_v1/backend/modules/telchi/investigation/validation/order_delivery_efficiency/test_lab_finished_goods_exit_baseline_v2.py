from datetime import datetime

from modules.telchi.investigation.validation.order_delivery_efficiency.lab_finished_goods_exit_baseline_v2 import (
    LAB_PRODUCT_FINISHED_WAREHOUSES,
    _build_records,
    _finalize,
)


def _frozen(key: int, qty: float = 10.0) -> dict:
    return {
        key: {
            "OrderKey": key,
            "OrderNumber": key + 1000,
            "OrderDateTime": "2026-09-01T09:00:00",
            "InvoiceDateTime": "2026-09-01T09:01:00",
            "CurrentCancelledFlag": False,
            "OrderStatus": "C",
            "LQuantity": qty,
            "LOrderedInvQty": qty,
            "RouteType": "FACTURA_DIRECTA",
        }
    }


def _row(key: int, line: int, warehouse: str, qty: float, when: datetime) -> dict:
    return {
        "order_entry": key,
        "source_route": "FACTURA_DIRECTA",
        "source_type": 13,
        "source_entry": 9000 + key,
        "source_number": 8000 + key,
        "source_line": line,
        "order_line": line,
        "item_code": f"L{line:05d}",
        "source_warehouse": warehouse,
        "movement_warehouse": warehouse,
        "ordered_inv_qty": qty,
        "source_inv_qty": qty,
        "source_create_date": when.date(),
        "source_create_ts": when.hour * 10000 + when.minute * 100 + when.second,
        "out_qty": qty,
    }


def test_lab_family_is_exactly_finished_goods_t1_to_t4() -> None:
    assert LAB_PRODUCT_FINISHED_WAREHOUSES == ("LAB-T1", "LAB-T2", "LAB-T3", "LAB-T4")


def test_classification_keeps_multi_t_and_lab_plus_other_separate() -> None:
    frozen = _frozen(1, 10) | _frozen(2, 10)
    rows = [
        _row(1, 0, "LAB-T1", 5, datetime(2026, 9, 1, 9, 2)),
        _row(1, 1, "LAB-T2", 5, datetime(2026, 9, 1, 9, 3)),
        _row(2, 0, "LAB-T3", 4, datetime(2026, 9, 1, 9, 2)),
        _row(2, 1, "SAA-T1", 6, datetime(2026, 9, 1, 9, 4)),
    ]

    records = _build_records(frozen, rows)
    _finalize(records)

    by_key = {record["OrderKey"]: record for record in records}
    assert by_key[1]["WarehouseExitClass"] == "LAB_MULTI_T"
    assert by_key[1]["LabCompleteApplicable"] is True
    assert by_key[1]["LabCompleteExitDateTime"] is not None
    assert by_key[2]["WarehouseExitClass"] == "LAB_PLUS_OTHER"
    assert by_key[2]["LabCompleteApplicable"] is False
    assert by_key[2]["LabCompleteExitDateTime"] is None
    assert by_key[2]["LabExitedInvQty"] == 4.0
    assert by_key[2]["OtherExitedInvQty"] == 6.0


def test_first_and_complete_exit_are_distinct_when_lab_output_is_split() -> None:
    frozen = _frozen(3, 10)
    rows = [
        _row(3, 0, "LAB-T4", 4, datetime(2026, 9, 1, 9, 2)),
        _row(3, 1, "LAB-T4", 6, datetime(2026, 9, 1, 10, 2)),
    ]

    records = _build_records(frozen, rows)
    _finalize(records)

    record = records[0]
    assert record["WarehouseExitClass"] == "LAB_ONLY"
    assert record["LabFirstExitDateTime"] < record["LabCompleteExitDateTime"]
    assert record["OrderToLabFirstExitMinutes"] == 2.0
    assert record["OrderToLabCompleteExitMinutes"] == 62.0
