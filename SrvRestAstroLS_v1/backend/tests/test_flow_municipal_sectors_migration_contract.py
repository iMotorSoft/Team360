from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "db/migrations/025_team360_flow_municipal_single_level_sectors_v1.sql"
)


def test_migration_seeds_only_single_level_baches_and_residuos():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "('baches', 'baches', true, null)" in sql
    assert "('residuos', 'residuos', true, null)" in sql
    assert "('baches', 1, 'email', 'baches.n1@alquimiablue.com'" in sql
    assert "('residuos', 1, 'email', 'residuos.n1@alquimiablue.com'" in sql
    assert "on conflict (sector_id) do update" in sql
    assert "on conflict (sector_id, level) do update" in sql


def test_migration_does_not_add_upper_levels_or_touch_other_modules():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "baches', 2" not in sql
    assert "baches', 3" not in sql
    assert "residuos', 2" not in sql
    assert "residuos', 3" not in sql
    assert "truncate" not in sql
    assert "drop table" not in sql
    assert "diagnosis" not in sql
