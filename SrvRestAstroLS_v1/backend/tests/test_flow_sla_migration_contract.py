from pathlib import Path


MIGRATION = Path(__file__).parents[1] / "db/migrations/014_team360_flow_n1_first_response_sla_v1.sql"


def test_sla_migration_has_config_snapshot_constraints_and_seed():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "first_response_sla_seconds integer" in sql
    assert "first_response_sla_seconds > 0" in sql
    assert "set first_response_sla_seconds = 30" in sql
    assert "create table if not exists flow_request_slas" in sql
    assert "duration_seconds" in sql
    assert "started_at_utc" in sql
    assert "due_at_utc" in sql
    assert "'pending', 'met', 'breached'" in sql
    assert "unique (sla_id, event_type)" in sql


def test_sla_migration_has_no_escalation_or_upper_levels():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "supervisor_email" not in sql
    assert "level_2" not in sql
    assert "level_3" not in sql
