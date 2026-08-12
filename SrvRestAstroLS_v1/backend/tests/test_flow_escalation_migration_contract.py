from pathlib import Path


MIGRATION = Path(__file__).parents[1] / "db/migrations/015_team360_flow_n1_to_n2_escalation_v1.sql"


def test_escalation_migration_preserves_multilevel_state_and_seeds_n2():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "primary key (routing_id)" in sql
    assert "idx_flow_work_states_request" in sql
    assert "'alumbrado', 2, 'email', 'alumbrado.n2@alquimiablue.com'" in sql
    assert "first_response_sla_seconds" in sql
    assert "create table if not exists flow_request_escalations" in sql
    assert "unique (trigger_sla_id, trigger_type)" in sql
    assert "to_routing_id" in sql


def test_escalation_migration_does_not_add_n3_or_scheduler():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "alumbrado.n3" not in sql
    assert "create trigger" not in sql
