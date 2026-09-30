from __future__ import annotations

import json
from pathlib import Path

import pytest

from . import audit


ROOT = Path("/tmp/team360-pg-durable-audit/src/pg_durable-0.2.8")
PACKAGE = Path("/tmp/team360-pg-durable-audit/pg-durable-postgresql-18_0.2.8-1_amd64.deb")


def test_stable_release_is_pg18_and_package_checksum_is_verified() -> None:
    result = audit.evaluate(ROOT, PACKAGE)
    assert result["stable_release"]["version"] == "0.2.8"
    assert result["stable_release"]["postgres_major"] == 18
    if not PACKAGE.is_file():
        pytest.skip("external package fixture is not present under /tmp")
    assert result["stable_release"]["package"]["sha256_matches_expected"] is True


def test_stable_source_proves_single_control_database_and_no_cross_database_graph() -> None:
    result = audit.evaluate(ROOT, PACKAGE)
    topology = result["topology"]
    assert topology["control_plane"]["namespace_api"].startswith("NO")
    assert topology["database_binding"]["target_database_parameter"].startswith("YES")
    assert topology["database_binding"]["one_invocation_spans_multiple_databases"] is False
    assert topology["database_binding"]["extension_installed_in_multiple_databases"] is False


def test_secret_and_chat_boundaries_fail_closed() -> None:
    result = audit.evaluate(ROOT, PACKAGE)
    assert result["secret_boundary"]["df_vars"].startswith("plaintext")
    assert result["secret_boundary"]["df_secrets"].startswith("NOT IMPLEMENTED")
    statuses = {row["capability"]: row["status"] for row in result["business_chat_fit"]}
    assert statuses["secret boundary"] == "NO"
    assert statuses["token streaming/SSE/resume"] == "NO"
    assert statuses["LLM invocation"] == "BRIDGE_REQUIRED"
    bridge = result["business_chat_bridge_contract"]
    assert bridge["opaque_payload_only"] == ["turn_id", "job_id", "publication_id", "workflow_type"]
    assert bridge["interactive_path"].startswith("do not put pg_durable")


def test_retry_and_http_policy_are_not_overstated() -> None:
    result = audit.evaluate(ROOT, PACKAGE)
    assert result["retry_semantics"]["generic_activity_retry_policy"].startswith("NO")
    assert result["http_security"]["generic_internal_litellm"] == "NO; internal host is not in the released allowlist"
    assert result["http_security"]["direct_external_llm"].startswith("NO")


def test_run_writes_redacted_read_only_evidence(tmp_path: Path) -> None:
    audit.EVIDENCE_ROOT = tmp_path
    audit.run(ROOT, PACKAGE)
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["RESULT"].endswith("_DEGRADED")
    assert summary["POSTGRES_WRITE_COUNT"] == 0
    assert summary["PG_DURABLE_INSTALLED_BY_GATE"] == "NO"
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "NO LISTO PARA INSTALACIÓN" in report
    assert "password" not in report.lower()
