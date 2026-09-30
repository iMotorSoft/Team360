from __future__ import annotations

import json

import pytest

from . import audit


def test_read_only_sql_guard_allows_only_select_and_show() -> None:
    audit.assert_read_only_sql("SELECT version()")
    audit.assert_read_only_sql("SHOW server_version")
    for sql in ("INSERT INTO x VALUES (1)", "UPDATE x SET y=1", "CREATE EXTENSION pg_durable", "WITH x AS (SELECT 1) SELECT * FROM x"):
        with pytest.raises(ValueError):
            audit.assert_read_only_sql(sql)


def test_redaction_preserves_non_secret_status_flags() -> None:
    value = audit.redact(
        {
            "password": "real-password",
            "api_key": "real-key",
            "SECRETS_REDACTED": "YES",
            "dsn": "postgresql://administrator:real-password@localhost:5432/team360",
        }
    )
    assert value["password"] == "<REDACTED>"
    assert value["api_key"] == "<REDACTED>"
    assert value["SECRETS_REDACTED"] == "YES"
    assert "real-password" not in json.dumps(value)


def test_isolation_matrix_for_unavailable_package_is_explicitly_degraded() -> None:
    matrix = audit.isolation_matrix(
        {
            "pg_durable_available_on_server": "NO",
            "pg_durable_extension_installed": "NO",
        }
    )
    assert matrix["GLOBAL_UNNAMESPACED_PG_DURABLE_STATE_ALLOWED"] == "NO"
    assert matrix["PG_DURABLE_NAMESPACE_CAPABILITY"] == "UNKNOWN"
    assert next(row for row in matrix["matrix"] if row["level"] == "DATABASE")["supported"] == "YES"
    assert next(row for row in matrix["matrix"] if row["level"] == "QUEUE/NAMESPACE")["supported"] == "UNKNOWN"


def test_safe_evidence_serialization_redacts_secret(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "EVIDENCE_ROOT", tmp_path)
    audit.write_json(
        "safe.json",
        {"user": "administrator", "password": "not-for-evidence", "SECRETS_REDACTED": "YES"},
    )
    content = (tmp_path / "safe.json").read_text(encoding="utf-8")
    assert "not-for-evidence" not in content
    assert '"password": "<REDACTED>"' in content
    assert '"SECRETS_REDACTED": "YES"' in content
