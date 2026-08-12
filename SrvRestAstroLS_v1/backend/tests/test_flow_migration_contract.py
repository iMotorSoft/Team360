from pathlib import Path


MIGRATION = Path(__file__).parents[1] / "db/migrations/011_team360_flow_email_intake_v1.sql"


def test_flow_migration_is_additive_and_contains_idempotency_constraints():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table if not exists flow_conversations" in sql
    assert "create table if not exists flow_messages" in sql
    assert "create table if not exists flow_interpretations" in sql
    assert "create table if not exists flow_request_candidates" in sql
    assert "create table if not exists flow_requests" in sql
    assert "unique (provider, external_message_id)" in sql
    assert "unique (provider, external_thread_id)" in sql
    assert "status = 'confirmed'" in sql
    assert "routing" in sql and "no routing" in sql


def test_flow_migration_does_not_add_out_of_scope_operational_fields():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for forbidden in ("sla_deadline", "assigned_sector", "escalation_level", "assignee_id"):
        assert forbidden not in sql

