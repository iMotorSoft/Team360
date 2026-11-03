"""Reconciliation pins canonical JSON content, not seal's spaced byte encoding."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from modules.telchi.datalake import sales_incremental as durable
from modules.telchi.datalake.operational_query import execute_on
from modules.telchi.datalake.messaging_sales_query import TelchiQueryError


def test_seal_bytes_and_canonical_digest_are_distinct_contracts(tmp_path):
    report = {"contract": "CAPTURED_OPERATIONAL_OBSERVATIONS_V1", "rows": 3974}
    path = tmp_path / "reconciliation.json"
    durable.seal(path, report)
    assert path.read_bytes() == json.dumps(report, sort_keys=True, default=str).encode()
    assert durable.file_hash(path) != durable.digest(report)
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str).encode()
    assert hashlib.sha256(canonical).hexdigest() == durable.digest(durable.read_json(path))
    with pytest.raises(FileExistsError):
        durable.seal(path, {"rows": 0})
    assert durable.read_json(path) == report


def test_canonical_digest_ignores_only_serialization_not_content(tmp_path):
    path = tmp_path / "reconciliation.json"
    report = {"rows": 3974, "contract": "CAPTURED_OPERATIONAL_OBSERVATIONS_V1"}
    expected = durable.digest(report)
    path.write_text(json.dumps(report, indent=2))
    assert durable.digest(durable.read_json(path)) == expected
    path.write_text(json.dumps(dict(report, rows=3975), indent=2))
    assert durable.digest(durable.read_json(path)) != expected


def test_operational_reader_rechecks_changed_content_on_each_call(tmp_path):
    path = tmp_path / "reconciliation.json"
    original = {"rows": 3974}
    durable.seal(path, original)
    access = SimpleNamespace(manifest={"operational_observations": {
        "reconciliation_path": str(path),
        "reconciliation_sha256": durable.digest(original),
    }})
    # Mutation is confined to a disposable fixture, never the sealed Data Lake.
    path.write_text(json.dumps({"rows": 3975}))
    for _ in range(2):
        with pytest.raises(TelchiQueryError, match="operational_reconciliation_changed"):
            execute_on(None, access, "inventory.stock_by_warehouse", {"item_code": "E00003"})
