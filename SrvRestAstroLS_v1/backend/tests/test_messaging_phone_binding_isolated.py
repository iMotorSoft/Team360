"""Real PG18 tests, exclusively an explicitly named loopback disposable DB."""
import asyncio
from dataclasses import replace
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from modules.messaging.handlers import ChannelContext
from modules.messaging.identity import PhoneIdentityRepository, InvalidPhoneBinding

DSN = os.getenv('TEAM360_MESSAGING_ISOLATED_TEST_DSN', '')
pytestmark = pytest.mark.skipif(not DSN, reason='requires explicit disposable PG18 DSN')


def test_pg18_migration_identity_rbac_revocation_constraints_and_rollback():
    parsed = urlparse(DSN)
    assert parsed.hostname == '127.0.0.1' and parsed.path == '/messaging_disposable'

    async def exercise():
        async with await psycopg.AsyncConnection.connect(DSN, autocommit=True, row_factory=dict_row) as conn:
            assert (await (await conn.execute('SHOW server_version_num')).fetchone())['server_version_num'].startswith('18')
            migrations = Path('db/migrations')
            for name in ('001_team360_core_schema.sql', '002_team360_rbac_packages_workers_knowledge.sql',
                         '027_team360_messaging_phone_bindings.sql'):
                await conn.execute((migrations / name).read_text())
            w, other, user, role, permission = [uuid4() for _ in range(5)]
            for ident, slug in ((w, 'fixture'), (other, 'other')):
                await conn.execute("INSERT INTO core_workspaces(id,slug,display_name) VALUES (%s,%s,'Fixture')", (ident, slug))
            await conn.execute("INSERT INTO core_users(id,workspace_id) VALUES (%s,%s)", (user, w))
            await conn.execute("INSERT INTO communication_providers(code,display_name) VALUES ('evolution','Fixture') ON CONFLICT DO NOTHING")
            await conn.execute("INSERT INTO core_permissions(id,permission_code,display_name) VALUES (%s,'fixture.business.read','Fixture')", (permission,))
            await conn.execute("INSERT INTO core_roles(id,workspace_id,role_code,display_name) VALUES (%s,%s,'fixture','Fixture')", (role, w))
            await conn.execute('INSERT INTO core_role_permissions(role_id,permission_id) VALUES (%s,%s)', (role, permission))
            await conn.execute('INSERT INTO core_user_roles(user_id,role_id) VALUES (%s,%s)', (user, role))
            insert = """INSERT INTO messaging_phone_bindings(environment,provider,sender_identity,
                tenant_id,workspace_id,user_id,verification_status,verified_at_utc,verification_ref,actor_user_id)
                VALUES (%s,'evolution','15550000001','fixture',%s,%s,'verified',now(),'synthetic-proof',%s)"""
            await conn.execute(insert, ('dev', w, user, user))
            repo = PhoneIdentityRepository()
            await repo.validate_schema(conn)
            channel = ChannelContext('channel', 'evolution', 'instance', 'receiver', 'fixture', str(w), 'telchi')
            identity = await repo.resolve(conn, channel, '15550000001')
            assert identity.user_id == str(user)
            assert identity.permissions == frozenset({'fixture.business.read'})
            assert await repo.resolve(conn, replace(channel, environment='pro'), '15550000001') is None
            assert await repo.resolve(conn, replace(channel, workspace_id=str(other)), '15550000001') is None
            assert await repo.resolve(conn, replace(channel, tenant_id='other'), '15550000001') is None
            assert await repo.resolve(conn, channel, '15550000002') is None
            with pytest.raises(psycopg.errors.UniqueViolation):
                await conn.execute(insert, ('dev', w, user, user))
            with pytest.raises(psycopg.errors.RaiseException):
                await conn.execute(insert, ('dev', other, user, user))
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                await conn.execute(insert, ('pro', w, user, uuid4()))
            await conn.execute(insert, ('pro', w, user, user))
            assert (await repo.resolve(conn, replace(channel, environment='pro'), '15550000001')).environment == 'pro'
            await conn.execute('DELETE FROM core_user_roles WHERE user_id=%s', (user,))
            assert not (await repo.resolve(conn, channel, '15550000001')).permissions
            with pytest.raises(psycopg.errors.CheckViolation):
                await conn.execute("UPDATE messaging_phone_bindings SET verification_ref=NULL WHERE environment='dev'")
            with pytest.raises(psycopg.errors.RaiseException):
                await conn.execute("UPDATE messaging_phone_bindings SET tenant_id='other' WHERE environment='dev'")
            await conn.execute("UPDATE messaging_phone_bindings SET verification_status='revoked', revoked_at_utc=now() WHERE environment='dev'")
            with pytest.raises(InvalidPhoneBinding):
                await repo.resolve(conn, channel, '15550000001')
            with pytest.raises(psycopg.errors.RaiseException):
                await conn.execute("DELETE FROM messaging_phone_bindings WHERE environment='dev'")
            audit = await (await conn.execute("SELECT payload_jsonb FROM core_events WHERE entity_type='messaging_phone_binding'")).fetchall()
            assert len(audit) == 3
            assert all('15550000001' not in str(row) for row in audit)
            await conn.execute('BEGIN; DROP TABLE messaging_phone_bindings; DROP FUNCTION messaging_phone_binding_audit(); COMMIT;')
            with pytest.raises(psycopg.errors.UndefinedTable):
                await repo.resolve(conn, channel, '15550000001')
            await conn.execute((migrations / '027_team360_messaging_phone_bindings.sql').read_text())
            await repo.validate_schema(conn)
    asyncio.run(exercise())
