from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/018_team360_flow_n3_first_response_sla_v1.sql"
)


def test_n3_sla_migration_only_enables_catalog_policy_without_backfill():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "first_response_sla_seconds = 30" in sql
    assert "sector_id = 'alumbrado'" in sql
    assert "level = 3" in sql
    assert "not backfilled" in sql
    assert "insert into flow_request_slas" not in sql


def test_n3_sla_migration_adds_no_parallel_engine_or_n4():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table" not in sql
    assert "alumbrado.n4" not in sql
    assert "create trigger" not in sql
    assert "scheduler" in sql
