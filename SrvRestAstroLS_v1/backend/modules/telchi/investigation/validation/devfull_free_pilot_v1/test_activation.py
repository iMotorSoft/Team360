"""Publication scope and byte-exact CAS rollback; no operational configuration."""
import pytest

from modules.telchi.investigation.validation.devfull_free_pilot_v1 import activate as a


def test_rollback_preserves_exact_bytes_and_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(a.dev, 'PRIVATE_ROOT', tmp_path)
    tmp_path.chmod(0o700)
    control = tmp_path / 'whatsapp-dev-control.json'
    old, installed = b'{ "env": {} }\n', b'{"env":{"TEAM360_TELCHI_FREE_ANALYSIS":"1"}}'
    a.restore_bytes(control, installed)
    (tmp_path / 'control.backup').write_bytes(old)
    receipt = tmp_path / 'receipt.json'
    a.lifecycle.atomic(receipt, dict(control=str(control), original_sha256=a.digest(old),
                                    installed_sha256=a.digest(installed)))
    a.rollback(receipt)
    assert control.read_bytes() == old
    assert control.stat().st_mode & 0o777 == 0o600


def test_rollback_never_overwrites_a_later_writer(tmp_path, monkeypatch):
    monkeypatch.setattr(a.dev, 'PRIVATE_ROOT', tmp_path)
    tmp_path.chmod(0o700)
    control = tmp_path / 'whatsapp-dev-control.json'
    control.write_bytes(b'newer owner bytes')
    (tmp_path / 'control.backup').write_bytes(b'old')
    receipt = tmp_path / 'receipt.json'
    a.lifecycle.atomic(receipt, dict(control=str(control), original_sha256=a.digest(b'old'),
                                    installed_sha256=a.digest(b'installed')))
    with pytest.raises(AssertionError, match='later_configuration_preserved'):
        a.rollback(receipt)
    assert control.read_bytes() == b'newer owner bytes'


@pytest.mark.parametrize('missing', ['select', 'insert', 'update'])
def test_missing_canonical_storage_privilege_blocks_before_publication(missing):
    privileges = dict(select=True, insert=True, update=True)
    a.require_storage_privileges(privileges)
    privileges[missing] = False
    with pytest.raises(PermissionError, match='canonical_runtime_core_events'):
        a.require_storage_privileges(privileges)


def test_storage_precheck_accepts_column_grants(monkeypatch):
    import asyncio
    import psycopg
    from types import SimpleNamespace
    statements = []

    class Connection:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def execute(self, sql):
            statements.append(sql)
            return self
        async def fetchone(self):
            return dict(select=True, insert=True, update=True)

    async def connect(*args, **kwargs): return Connection()
    monkeypatch.setattr(psycopg.AsyncConnection, 'connect', connect)
    monkeypatch.setattr('modules.db.settings.get_database_settings',
                        lambda: SimpleNamespace(dsn='fixture'))
    asyncio.run(a.check_runtime_storage())
    sql = statements[0]
    assert "has_column_privilege" in sql
    assert "'payload_jsonb','UPDATE'" in sql
    assert "'entity_type', 'correlation_id', 'payload_jsonb'" in sql
    assert "'core_events','INSERT'" not in sql
    assert "'core_events','UPDATE'" not in sql
    assert sql.count('has_table_privilege') == 1


def test_partial_other_holder_blocks_activation():
    anchors = {'one', 'two'}
    pilot = dict(id='pilot', email='devfull@telchiai.com', organization=a.ORG,
                 workspace=a.WORKSPACE, researcher_anchors=sorted(anchors))
    audit = dict(users=[pilot], telchi_workspaces=[dict(id=a.WORKSPACE, slug='telchi_dev')])
    assert a.isolated(audit, anchors) == 'pilot'
    audit['users'].append(dict(pilot, id='other', email='other@example.invalid',
                               researcher_anchors=['one']))
    with pytest.raises(ValueError, match='devfull_isolation_required'):
        a.isolated(audit, anchors)
