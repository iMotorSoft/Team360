from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/020_team360_flow_director_authorization_v1.sql"
)


def test_migration_seeds_flow_executive_read_permission():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "flow.executive.read" in sql
    assert "core_permissions" in sql
    assert "on conflict (permission_code) do nothing" in sql


def test_migration_has_no_user_grants_or_rbac_redesign():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "core_user_roles" not in sql
    assert "core_roles" not in sql
    assert "insert into core_permissions" in sql
    assert "alter table" not in sql
