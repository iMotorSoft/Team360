from __future__ import annotations

from pathlib import Path

from modules.telchi.investigation.validation.datalake_atomic_inventory_and_sales_real_segment_pilot_v1.pilot import (
    MAX_ROWS,
    SQL_ROOT,
    TRANSFORMATION_VERSION,
    canonical,
    digest,
)


QUERIES = tuple(SQL_ROOT.glob("*.sql"))


def test_queries_are_versioned_bounded_and_have_no_select_star() -> None:
    assert {path.name for path in QUERIES} == {
        "sales_discovery_v1.sql",
        "sales_extract_v1.sql",
        "inventory_discovery_v1.sql",
        "inventory_extract_v1.sql",
    }
    for path in QUERIES:
        sql = path.read_text(encoding="utf-8")
        assert "SELECT *" not in sql.upper()
        if "extract" in path.name:
            assert "?" in sql
            assert "WHERE" in sql.upper()


def test_sales_and_inventory_identity_is_deterministic() -> None:
    assert digest(("SAP_B1", "14582")) == digest(("SAP_B1", "14582"))
    assert digest(("SAP_B1", "A00001", "01")) != digest(("SAP_B1", "A00001", "02"))
    assert TRANSFORMATION_VERSION.startswith("atomic-inventory-sales-real-segment-pilot-v1")
    assert MAX_ROWS == 10_000


def test_source_native_inventory_authority_is_explicit() -> None:
    sql = (SQL_ROOT / "inventory_extract_v1.sql").read_text(encoding="utf-8")
    for field in ('W."ItemCode"', 'W."WhsCode"', 'W."OnHand"', 'W."IsCommited"', 'W."OnOrder"'):
        assert field in sql
    assert 'W."ItemCode" = ? AND W."WhsCode" = ?' in sql


def test_canonicalization_preserves_decimal_and_temporal_text() -> None:
    assert canonical(None) is None
    assert canonical("2022-03-31") == "2022-03-31"
    assert digest({"a": "1", "b": "2"}) == digest({"b": "2", "a": "1"})
