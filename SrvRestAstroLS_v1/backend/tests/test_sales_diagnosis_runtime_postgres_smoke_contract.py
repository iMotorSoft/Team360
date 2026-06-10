"""Contract tests for the backend-only runtime Postgres smoke script.

Validates script structure, fake providers, guardrail cases, cleanup.
No DB connection required.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _smoke_script() -> Path:
    return _backend_root() / "scripts" / "smoke_sales_diagnosis_runtime_postgres.py"


def _read_smoke() -> str:
    return _smoke_script().read_text(encoding="utf-8")


class TestSmokeScriptExists:
    def test_smoke_script_exists(self):
        assert _smoke_script().exists(), f"Not found: {_smoke_script()}"


class TestSmokeScriptUsesDbUrl:
    def test_uses_team360_db_url(self):
        content = _read_smoke()
        assert "get_team360_db_url" in content or "TEAM360_DB_URL" in content

    def test_does_not_print_raw_db_url(self):
        content = _read_smoke()
        forbidden = [
            "print.*TEAM360_DB_URL",
            "print.*dsn",
            "print.*db_url",
            "print.*conninfo",
        ]
        for pattern in forbidden:
            import re
            assert not re.search(pattern, content, re.IGNORECASE), (
                f"Found potential URL leak: {pattern}"
            )

    def test_fails_without_team360_db_url(self):
        result = subprocess.run(
            [sys.executable, str(_smoke_script())],
            capture_output=True,
            text=True,
            timeout=30,
            env={},
        )
        assert result.returncode != 0
        combined = (result.stderr + result.stdout).lower()
        assert "team360_db_url" in combined or "not set" in combined or "error" in combined


class TestSmokeScriptUsesFakes:
    def test_uses_fake_retrieval_not_milvus(self):
        content = _read_smoke()
        assert "FakeRetrievalProvider" in content
        assert "class FakeRetrievalProvider" in content

    def test_uses_fake_llm_not_openai(self):
        content = _read_smoke()
        assert "FakeLLMProvider" in content
        assert "class FakeLLMProvider" in content
        assert "def generate" in content


class TestSmokeScriptGuardrail:
    def test_has_guardrail_failure_case(self):
        content = _read_smoke()
        assert "unsafe_claim" in content or "UnsafeResponseError" in content
        assert "guardrail" in content.lower()


class TestSmokeScriptCleanup:
    def test_cleans_up_smoke_session(self):
        content = _read_smoke()
        assert "_delete_smoke_session" in content or "DELETE" in content
        assert "finally" in content


class TestSmokeScriptMigrationReference:
    def test_references_migration_007(self):
        content = _read_smoke()
        assert "007" in content and "migration" in content.lower()


class TestIntegrationPostgres:
    @pytest.mark.skipif(
        not os.environ.get("TEAM360_DB_URL") and not os.environ.get("TEAM360_DB_URL_PSQL"),
        reason="TEAM360_DB_URL or TEAM360_DB_URL_PSQL not set",
    )
    def test_runtime_postgres_smoke_real_db(self):
        """Run the full runtime smoke against a live PostgreSQL instance."""
        env = {
            **os.environ,
            "TEAM360_DB_URL": (
                os.environ.get("TEAM360_DB_URL")
                or os.environ.get("TEAM360_DB_URL_PSQL", "")
            ),
        }
        result = subprocess.run(
            [sys.executable, str(_smoke_script())],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if result.returncode != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
        assert result.returncode == 0, (
            f"Smoke failed with exit code {result.returncode}\n"
            f"STDERR: {result.stderr}"
        )
        assert "SMOKE PASSED" in result.stdout
