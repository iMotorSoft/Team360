from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/012_team360_flow_routing_n1_v1.sql"
)


def test_routing_migration_has_catalog_seed_and_idempotency_constraints():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table if not exists flow_sectors" in sql
    assert "create table if not exists flow_sector_levels" in sql
    assert "create table if not exists flow_request_routings" in sql
    assert "unique (request_id, routing_key)" in sql
    assert "'alumbrado', 'alumbrado público', true" in sql
    assert "'alumbrado', 1, 'email', 'alumbrado.n1@alquimiablue.com', true" in sql


def test_routing_migration_has_no_out_of_scope_sla_or_upper_level_seed():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "sla_deadline" not in sql
    assert "escalation_level" not in sql
    assert "delegated_to" not in sql
    assert "values ('alumbrado', 2" not in sql
    assert "values ('alumbrado', 3" not in sql
