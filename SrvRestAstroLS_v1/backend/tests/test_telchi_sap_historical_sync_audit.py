from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_telchi_sap_historical_sync as audit  # noqa: E402


def test_probe_inventory_is_complete_and_unique() -> None:
    ids = [probe.probe_id for probe in audit.PROBES]
    assert len(ids) == 15
    assert len(ids) == len(set(ids))
    assert {
        "PRODUCTS",
        "CUSTOMERS",
        "WAREHOUSE_MASTER",
        "ITEM_WAREHOUSE",
        "SALES",
        "CREDIT_NOTES",
        "INVENTORY_MOVEMENTS",
        "BOM",
        "PURCHASES",
        "PURCHASE_EXPENSES",
        "SALES_TARGETS",
    } <= set(ids)


def test_every_hana_probe_is_single_statement_read_only_sql() -> None:
    for probe in audit.PROBES:
        audit.validate_read_only_sql(probe.current_sql)
        if probe.legacy_sql:
            audit.validate_read_only_sql(probe.legacy_sql)


@pytest.mark.parametrize(
    "sql",
    (
        'UPDATE "TELCHI"."OINV" SET "DocStatus" = \'C\'',
        'DELETE FROM "TELCHI"."OINV"',
        'SELECT 1 FROM DUMMY; DROP TABLE X',
    ),
)
def test_write_or_multi_statement_sql_is_rejected(sql: str) -> None:
    with pytest.raises(ValueError):
        audit.validate_read_only_sql(sql)


def test_status_and_cursor_contracts_are_explicit() -> None:
    for probe in audit.PROBES:
        assert probe.status in audit.ALLOWED_STATUSES
        assert probe.objects
        assert probe.cursor != ""


def test_historical_endpoint_is_absent() -> None:
    source = Path(audit.__file__).read_text(encoding="utf-8")
    historical_endpoint = ".".join(("192", "168", "21", "4"))
    assert historical_endpoint not in source
