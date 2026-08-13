from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/016_team360_flow_n2_first_response_sla_v1.sql"
)


def test_n2_sla_migration_enables_catalog_policy_without_backfill():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "set first_response_sla_seconds = 30" in sql
    assert "sector_id = 'alumbrado'" in sql
    assert "level = 2" in sql
    assert "insert into flow_request_slas" not in sql
    assert "assigned_at_utc" in sql


def test_n2_sla_migration_does_not_add_parallel_engine_or_n3():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table" not in sql
    assert "alumbrado.n3" not in sql
    assert "create trigger" not in sql
