from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/024_team360_flow_safe_mail_cutoff_v1.sql"
)


def test_migration_adds_safe_persistent_cutoff_without_rewriting_023() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "alter table flow_operational_settings" in sql
    assert "add column if not exists mail_cutoff_epoch bigint" in sql
    assert "default 1787239323" in sql
    assert "not null" in sql
    assert "where mail_cutoff_epoch = 1767225600" in sql


def test_migration_bounds_cutoff_and_documents_safe_query_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "between 1577836800 and 1893456000" in sql
    assert "chk_flow_ops_mail_cutoff_epoch" in sql
    assert "after:<epoch>" in sql
    assert "-after:" not in sql
