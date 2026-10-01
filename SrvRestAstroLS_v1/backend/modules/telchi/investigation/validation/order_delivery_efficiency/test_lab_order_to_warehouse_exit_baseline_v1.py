from modules.telchi.investigation.validation.order_delivery_efficiency.lab_order_to_warehouse_exit_baseline_v1 import (
    _warehouse_decision,
)


def test_lab_scope_fails_closed_when_multiple_finished_goods_warehouses_exist() -> None:
    warehouses = [
        {"whscode": "LAB-T1", "whsname": "Almacén Producto Terminado AGEMED"},
        {"whscode": "LAB-T2", "whsname": "Almacén Producto Terminado SENASAG"},
        {"whscode": "LAB-DES", "whsname": "Almacén Despacho Laboratorio."},
    ]
    movements = [
        {"movement_warehouse": "LAB-T1", "orders": 45, "source_documents": 45},
        {"movement_warehouse": "LAB-T2", "orders": 19, "source_documents": 19},
    ]

    decision = _warehouse_decision(warehouses, movements)

    assert decision["canonical_lab_warehouse_code"] is None
    assert decision["decision"] == "BLOCKED_AMBIGUOUS_LAB_FINISHED_GOODS_SCOPE"
    assert decision["candidate_codes"] == ["LAB-T1", "LAB-T2"]
    assert decision["dispatch_warehouse_evidence"]["LAB-DES"]["movement_orders"] == 0
