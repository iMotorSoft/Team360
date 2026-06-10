import importlib


def _reload_global_var():
    import globalVar

    return importlib.reload(globalVar)


class TestTeam360DatabaseGlobals:
    def test_exposes_team360_db_url(self, monkeypatch):
        monkeypatch.setenv("TEAM360_DB_URL", "postgresql+psycopg://u:p@h:5432/team360")
        monkeypatch.delenv("TEAM360_DB_URL_PSQL", raising=False)
        module = _reload_global_var()

        assert module.TEAM360_DB_URL == "postgresql+psycopg://u:p@h:5432/team360"
        assert module.get_team360_db_url() == "postgresql+psycopg://u:p@h:5432/team360"
        assert module.get_team360_db_url_psql() == "postgresql://u:p@h:5432/team360"

    def test_uses_team360_db_url_psql_fallback(self, monkeypatch):
        monkeypatch.delenv("TEAM360_DB_URL", raising=False)
        monkeypatch.setenv("TEAM360_DB_URL_PSQL", "postgresql://u:p@h:5432/team360")
        module = _reload_global_var()

        assert module.TEAM360_DB_URL == ""
        assert module.TEAM360_DB_URL_PSQL == "postgresql://u:p@h:5432/team360"
        assert module.get_team360_db_url() == "postgresql://u:p@h:5432/team360"

    def test_derives_team360_db_url_from_v360_source(self, monkeypatch):
        monkeypatch.delenv("TEAM360_DB_URL", raising=False)
        monkeypatch.delenv("TEAM360_DB_URL_PSQL", raising=False)
        monkeypatch.setenv("DB_PG_V360_URL", "postgresql://u:p@h:5432/v360")
        module = _reload_global_var()

        assert module.get_team360_db_url() == "postgresql://u:p@h:5432/team360"
        assert module.get_team360_db_url_psql() == "postgresql://u:p@h:5432/team360"

    def test_future_optional_helpers_remain_compatible(self, monkeypatch):
        monkeypatch.setenv("TEAM360_DB_URL", "postgresql+psycopg://u:p@h:5432/team360")
        module = _reload_global_var()

        assert module.FUTURE_OPTIONAL_TEAM360_DB_URL == module.TEAM360_DB_URL
        assert module.get_future_optional_team360_db_url() == module.get_team360_db_url()
        assert (
            module.get_future_optional_team360_db_url_psql()
            == module.get_team360_db_url_psql()
        )

    def test_active_team360_db_url_is_empty_without_env(self, monkeypatch):
        monkeypatch.delenv("TEAM360_DB_URL", raising=False)
        monkeypatch.delenv("TEAM360_DB_URL_PSQL", raising=False)
        monkeypatch.delenv("DB_PG_V360_URL", raising=False)
        module = _reload_global_var()

        assert module.get_team360_db_url() == ""
        assert module.get_team360_db_url_psql() == ""

    def test_future_optional_helper_keeps_legacy_placeholder(self, monkeypatch):
        monkeypatch.delenv("TEAM360_DB_URL", raising=False)
        monkeypatch.delenv("TEAM360_DB_URL_PSQL", raising=False)
        monkeypatch.delenv("DB_PG_V360_URL", raising=False)
        module = _reload_global_var()

        assert (
            module.get_future_optional_team360_db_url()
            == "postgresql+psycopg://user:pass@localhost:5432/team360"
        )
