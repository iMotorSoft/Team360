from modules.telchi.investigation.validation.branch_replenishment.branch_replenishment_gate_v1 import (
    branch_for,
    role,
)
from modules.telchi.investigation.validation.branch_replenishment.daily_stock_demand_v1 import (
    MAX_WORKERS,
    MIN_MEM_AVAILABLE_BYTES,
    ResourceGuard,
    adaptive_batch_size,
    assert_resource_safe,
    resource_snapshot,
)
from modules.telchi.investigation.validation.branch_replenishment.scale_up_v2 import LEVELS, LEVEL_ORDER


def test_requested_roles_are_evidence_driven():
    assert role("SAP-R1", "Almacén transito SAP - R1", "SAP", "1")[0] == "TRANSIT"
    assert role("2A-SAL", "Almacén Salón 2A", "SAP", "1")[0] == "BRANCH_SALES"
    assert role("LAB-D1", "Almacen Movil 4702", "DMS", "3")[0] == "MOBILE"
    assert role("LAB-T1", "Producto Terminado AGEMED", "DMS", "1")[0] == "FINISHED_GOODS"


def test_damaged_salon_is_not_mistaken_for_sales_branch():
    assert role("2A-DAN", "Almacén de Dañados Salon 2do Anillo", "SAP", "1")[0] == "OTHER"


def test_branch_mapping_preserves_unknowns_and_confidence():
    assert branch_for("2A-SAL") == ("2A", "2A", "EXACT")
    assert branch_for("2A-AMD") == ("2A", "2A", "STRONG")
    assert branch_for("LPZ-D1") == ("LPZ", "La Paz", "HEURISTIC")
    assert branch_for("SAP-R1") == (None, None, "UNKNOWN")


def test_resource_safety_contract_is_single_worker_and_local():
    snapshot = resource_snapshot()
    assert MAX_WORKERS == 1
    assert MIN_MEM_AVAILABLE_BYTES == 2 * 1024**3
    assert snapshot["mem_available_mb"] >= 0
    assert assert_resource_safe(snapshot) == snapshot


def test_resource_guard_records_partition_metrics(tmp_path):
    guard = ResourceGuard(tmp_path)
    metric = guard.check("sample", rows_read=5, rows_written=3, batch_size=1)
    assert metric["result"] == "PASS"
    assert metric["partition"] == "sample"
    assert (tmp_path / "resource_metrics.jsonl").read_text(encoding="utf-8").count("sample") == 1
    assert guard.summary()["MAX_WORKERS"] == 1


def test_batch_size_reduces_automatically_under_memory_pressure():
    assert adaptive_batch_size(10, {"mem_available_mb": 2500}) == 1
    assert adaptive_batch_size(10, {"mem_available_mb": 3500}) == 3
    assert adaptive_batch_size(10, {"mem_available_mb": 5000}) == 5


def test_controlled_scale_levels_change_one_dimension_in_order():
    assert LEVEL_ORDER == ("A", "B", "C", "D", "E")
    assert LEVELS["A"] == {"branches": ["2A"], "days": 90, "item_mode": "top", "requested_items": 10}
    assert LEVELS["B"]["branches"] == ["2A"] and LEVELS["B"]["days"] == 90
    assert LEVELS["C"]["branches"] == ["2A"] and LEVELS["C"]["days"] == 365
    assert LEVELS["D"]["branches"] == ["CM"] and LEVELS["D"]["days"] == 90
    assert LEVELS["E"]["branches"] == ["2A", "CM"] and LEVELS["E"]["days"] == 365
