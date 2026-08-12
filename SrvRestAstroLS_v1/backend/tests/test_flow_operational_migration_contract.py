from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/013_team360_flow_n1_operational_reply_v1.sql"
)


def test_operational_migration_tracks_state_events_and_observed_rfc_id():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "outbound_observed_rfc_message_id" in sql
    assert "create table if not exists flow_request_work_states" in sql
    assert "create table if not exists flow_request_operational_events" in sql
    assert "first_response_at_utc" in sql
    assert "unique (provider, inbound_external_message_id)" in sql
    assert "'assigned', 'in_progress'" in sql


def test_operational_migration_excludes_future_workflow_states():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "sla_deadline" not in sql
    assert "'resolved'" not in sql
    assert "'escalated'" not in sql
    assert "level_2" not in sql
    assert "level_3" not in sql
