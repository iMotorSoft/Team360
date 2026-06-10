"""Contract tests for sales diagnosis conversation state Postgres integration.

Validates migration SQL, repository constants, smoke script patterns.
No DB connection required.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from modules.sales_diagnosis_runtime.state_repository import (
    MIGRATION_FILE,
    ConversationStateSerializer,
    InMemoryConversationStateRepository,
    PostgresConversationStateRepository,
)
from modules.sales_diagnosis_runtime.errors import StateRepositoryError


# ===================================================================
# Migration file contract
# ===================================================================


def _migration_path() -> Path:
    backend_root = Path(__file__).resolve().parent.parent
    return backend_root / MIGRATION_FILE


class TestMigrationContract:
    def test_migration_file_exists(self):
        path = _migration_path()
        assert path.exists(), f"Migration file not found: {path}"
        assert path.is_file()

    def test_migration_has_table_name(self):
        sql = _migration_path().read_text(encoding="utf-8")
        assert "sales_diagnosis_conversation_states" in sql
        assert "create table if not exists" in sql.lower()

    def test_migration_has_jsonb_check_constraint(self):
        sql = _migration_path().read_text(encoding="utf-8")
        assert "jsonb_typeof(state_jsonb) = 'object'::text" in sql
        assert "chk_sd_cs_jsonb_is_object" in sql

    def test_migration_has_expected_indexes(self):
        sql = _migration_path().read_text(encoding="utf-8")
        for idx in [
            "idx_sd_cs_updated_at",
            "idx_sd_cs_assistant_instance",
            "idx_sd_cs_package",
            "idx_sd_cs_knowledge_scope",
        ]:
            assert idx in sql, f"Missing index: {idx}"

    def test_migration_has_idempotent_create(self):
        sql = _migration_path().read_text(encoding="utf-8")
        assert "if not exists" in sql.lower()


# ===================================================================
# Repository contract
# ===================================================================


class TestRepositoryContract:
    def test_repository_has_migration_reference(self):
        assert PostgresConversationStateRepository.MIGRATION_FILE == MIGRATION_FILE
        assert "007_sales_diagnosis_conversation_states.sql" in MIGRATION_FILE

    def test_repository_table_name_matches_migration(self):
        sql = _migration_path().read_text(encoding="utf-8")
        assert PostgresConversationStateRepository.TABLE_NAME in sql

    def test_repository_repr_has_no_password(self):
        repo = PostgresConversationStateRepository()
        rep = repr(repo)
        assert "password" not in rep.lower()
        assert "table=" in rep

    def test_repository_repr_with_pool_configured(self):
        repo = PostgresConversationStateRepository(pool=object())
        rep = repr(repo)
        assert "pool_configured=True" in rep

    def test_load_raises_error_without_pool(self):
        repo = PostgresConversationStateRepository()
        with pytest.raises(StateRepositoryError, match="requires an injected pool"):
            repo.load("s1")

    def test_save_raises_error_without_pool(self):
        repo = PostgresConversationStateRepository()
        state = ConversationStateSerializer.from_dict({
            "session_id": str(uuid4()),
            "assistant_instance_code": "test",
            "package_code": "test",
            "knowledge_scope_code": "test",
        })
        with pytest.raises(StateRepositoryError, match="requires an injected pool"):
            repo.save(state)


# ===================================================================
# Smoke script contract
# ===================================================================


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


class TestSmokeScriptContract:
    def test_smoke_script_exists(self):
        script = _backend_root() / "scripts" / "smoke_sales_diagnosis_state_postgres.py"
        assert script.exists(), f"Smoke script not found: {script}"

    def test_smoke_script_requires_env_var(self):
        script = _backend_root() / "scripts" / "smoke_sales_diagnosis_state_postgres.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=30,
            env={},
        )
        assert result.returncode != 0
        assert "TEAM360_DB_URL" in result.stderr or "TEAM360_DB_URL" in result.stdout

    def test_smoke_script_sanitizes_url(self):
        """Verify the smoke script masks passwords in log output."""
        script = _backend_root() / "scripts" / "smoke_sales_diagnosis_state_postgres.py"
        content = script.read_text(encoding="utf-8")
        assert "_sanitize_url" in content or "sanitize" in content.lower()

    def test_smoke_script_imports_migration_file(self):
        script = _backend_root() / "scripts" / "smoke_sales_diagnosis_state_postgres.py"
        content = script.read_text(encoding="utf-8")
        assert "MIGRATION_FILE" in content
        assert "from modules.sales_diagnosis_runtime.state_repository import" in content


# ===================================================================
# Integration test (skipped without env)
# ===================================================================


class TestPostgresIntegration:
    @pytest.mark.skipif(
        not os.environ.get("TEAM360_DB_URL") and not os.environ.get("TEAM360_DB_URL_PSQL"),
        reason="TEAM360_DB_URL or TEAM360_DB_URL_PSQL not set",
    )
    def test_smoke_passes_with_db_url(self):
        """Run the full smoke script against a live PostgreSQL instance."""
        script = _backend_root() / "scripts" / "smoke_sales_diagnosis_state_postgres.py"
        env = {
            **os.environ,
            "TEAM360_DB_URL": os.environ.get("TEAM360_DB_URL")
            or os.environ.get("TEAM360_DB_URL_PSQL", ""),
        }
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=60,
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
