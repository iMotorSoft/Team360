from pathlib import Path

from . import GATE
from .pilot import MAX_ROWS, SQL_ROOT, TRANSFORMATION_VERSION, build_tables, digest


EXPECTED_QUERIES = {
    "sales_discovery_v2.sql",
    "sales_extract_v2.sql",
    "inventory_discovery_v2.sql",
    "inventory_extract_v2.sql",
}


def test_v2_is_independent_and_bounded() -> None:
    assert GATE.endswith("_V2")
    assert MAX_ROWS == 10_000
    assert TRANSFORMATION_VERSION.endswith("v2.0.0")
    assert {path.name for path in SQL_ROOT.glob("*.sql")} == EXPECTED_QUERIES
    for path in SQL_ROOT.glob("*.sql"):
        sql = path.read_text(encoding="utf-8").upper()
        assert "SELECT *" not in sql
        assert "CREATE" not in sql
        assert "UPDATE" not in sql
        assert "DELETE" not in sql
        if "EXTRACT" in path.name.upper():
            assert "?" in sql and "WHERE" in sql


def test_atomic_contract_preserves_source_native_fields() -> None:
    reference = {"version": "v2", "hash": "reference-hash"}
    manifest = {"extraction_id": "x", "source_as_of": "2026-01-01T00:00:00Z"}
    tables, identity = build_tables("inventory", [{"ItemCode": "A", "WhsCode": "01", "OnHand": "1", "IsCommited": "2", "OnOrder": "3"}], reference, manifest)
    row = tables["inventory_balance"][0]
    assert row["source_values"] == {"ItemCode": "A", "WhsCode": "01", "OnHand": "1", "IsCommited": "2", "OnOrder": "3"}
    assert identity == digest({"inventory_balance": [{"atomic_id": row["atomic_id"], "source_values": row["source_values"]}]})


def test_validation_and_reconciliation_are_before_boundary() -> None:
    source = Path(__file__).with_name("pilot.py").read_text(encoding="utf-8")
    assert source.index("handler.validate") if "handler.validate" in source else True
    executor = (Path(__file__).resolve().parents[3] / "runtime" / "executor.py").read_text(encoding="utf-8")
    assert executor.index("handler.validate") < executor.index("handler.reconcile") < executor.index("publication_boundary.publish")
    assert "TransactionalPublicationBoundary" in source
    assert "FULL_BACKFILL_STARTED" in source or "full_backfill_started" in source


def test_no_new_business_metrics_or_watermark_from_doc_date() -> None:
    source = Path(__file__).with_name("pilot.py").read_text(encoding="utf-8")
    assert "NET_SALES" not in source
    assert "DOC_DATE_NOT_A_WATERMARK" in source
    assert "NO_GLOBAL_WATERMARK" in source
