from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from modules.telchi.investigation.validation.order_delivery_efficiency import (
    source_discovery_v1 as discovery,
)


def test_discovery_is_intentionally_bounded() -> None:
    assert discovery.WINDOW_DAYS == 30
    assert discovery.SAMPLE_LIMIT == 20
    assert discovery.SAP_WRITE_COUNT == 0


def test_json_default_preserves_temporal_and_decimal_values() -> None:
    assert discovery._json_default(date(2026, 9, 14)) == "2026-09-14"
    assert discovery._json_default(datetime(2026, 9, 14, 10, 30)) == "2026-09-14T10:30:00"
    assert discovery._json_default(Decimal("1.25")) == 1.25


def test_evidence_destination_is_external() -> None:
    assert discovery.EVIDENCE_DIR.is_absolute()
    assert "modules/telchi" not in discovery.EVIDENCE_DIR.as_posix()
    assert discovery.EVIDENCE_DIR.name == "evidence"
