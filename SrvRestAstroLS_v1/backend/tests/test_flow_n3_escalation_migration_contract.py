from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/017_team360_flow_n2_to_n3_escalation_v1.sql"
)


def test_n3_migration_seeds_catalog_without_sla_and_generalizes_levels():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "'alumbrado', 3, 'email', 'alumbrado.n3@alquimiablue.com', true, null" in sql
    assert "to_level > from_level" in sql
    assert "to_level = from_level + 1" not in sql


def test_n3_migration_adds_no_parallel_engine_n4_or_scheduler():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table" not in sql
    assert "alumbrado.n4" not in sql
    assert "create trigger" not in sql
