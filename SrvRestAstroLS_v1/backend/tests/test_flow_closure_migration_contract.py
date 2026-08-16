from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/019_team360_flow_supervisor_closure_audit_v1.sql"
)


def test_migration_creates_resolution_approval_and_audit_tables():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table if not exists flow_request_resolutions" in sql
    assert "create table if not exists flow_closure_approvals" in sql
    assert "create table if not exists flow_case_audit_records" in sql


def test_migration_extends_request_lifecycle_status():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "'resolution_pending_approval'" in sql
    assert "'resolved'" in sql
    assert "authorized_approval_id" in sql
    assert "references flow_closure_approvals(id)" in sql


def test_migration_widens_operational_action_constraint():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "chk_flow_operational_action" in sql
    assert "'resolution_proposed'" in sql


def test_migration_configures_supervisor_policy():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "closure_approval_level" in sql
    assert "set closure_approval_level = 2" in sql


def test_migration_has_idempotency_and_integrity_constraints():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "unique (source_provider, source_external_message_id)" in sql
    assert "resolution_id" in sql and "unique references flow_request_resolutions" in sql
    assert "unique (request_id, schema_version)" in sql
    assert "uq_flow_approval_decision_source" in sql
    assert "chk_flow_audit_sha" in sql


def test_migration_adds_resolution_guard_trigger():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create or replace function fn_flow_request_resolution_guard" in sql
    assert "create trigger trg_flow_request_resolution_guard" in sql
    assert "terminal and cannot be degraded" in sql


def test_migration_has_no_n4_reopen_or_scheduler():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "alumbrado.n4" not in sql
    assert "reopened" not in sql
    assert "scheduler" in sql  # the header explicitly rules it out
