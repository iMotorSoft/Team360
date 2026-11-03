"""PG18 real integration; requires loopback, nonstandard port and dedicated database."""
import asyncio
from dataclasses import replace
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from modules.console.repositories import PermissionConsoleRepository
from modules.messaging.repository import MessagingRepository
from modules.messaging.handlers import ChannelContext
from modules.messaging.identity import PhoneIdentityRepository, InvalidPhoneBinding
from modules.telchi.provisioning.repository import Seed, ProvisioningRepository, Conflict, PERMISSION, runtime_policy
from modules.telchi.provisioning.cli import approved
from modules.telchi.provisioning.phone_binding import bind_verified_dev_phone

DSN = os.environ.get('TELCHI_PROVISIONING_TEST_DSN', '')
ROOT = Path(__file__).parent


def test_missing_approvals_fail_closed():
    with pytest.raises(Conflict):
        approved(dict(seed=dict(workspace_id=str(uuid4()), organization_id=str(uuid4()))))
    policy = runtime_policy(Seed(str(uuid4()), str(uuid4())))
    assert not policy.module_enabled and not policy.whole_workspace_scope_verified


@pytest.mark.skipif(not DSN, reason='explicit disposable PG18 required')
def test_pg18_seed_contracts():
    p = urlparse(DSN)
    assert p.hostname == '127.0.0.1' and p.port not in (None, 5432)
    assert p.path == '/telchi_provisioning_disposable'

    async def exercise():
        async with await psycopg.AsyncConnection.connect(DSN, autocommit=True, row_factory=dict_row) as conn:
            version = await (await conn.execute('SHOW server_version_num')).fetchone()
            assert version['server_version_num'].startswith('18')
            await conn.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
            for filename in ('001_team360_core_schema.sql', '002_team360_rbac_packages_workers_knowledge.sql'):
                await conn.execute((Path('db/migrations') / filename).read_text())
            # Read-only pg_dump of actual operational organization schema, no rows/PII.
            ddl = '\n'.join(line for line in (ROOT / 'organization_schema_pg18.sql').read_text().splitlines() if not line.startswith('\\'))
            await conn.execute(ddl)
            await conn.execute('SET search_path=public,pg_catalog')
            await conn.execute('ALTER TABLE core_workspaces ADD COLUMN organization_id uuid REFERENCES core_organizations(id) ON DELETE SET NULL')
            await conn.execute(Path('db/migrations/027_team360_messaging_phone_bindings.sql').read_text())
            repo = ProvisioningRepository()
            seed = Seed(str(uuid4()), str(uuid4()))
            # 1 initial scaffold; 2 idempotency; 3/4 mismatched org/workspace.
            async with conn.transaction():
                initial = await repo.provision(conn, seed)
            assert len(initial['created']) == 2
            # Untouched scaffold rollback removes only its audited creations.
            async with conn.transaction():
                await repo.rollback(conn, initial['run_id'])
            assert not await (await conn.execute("SELECT id FROM core_organizations WHERE organization_code='telchi'")).fetchone()
            async with conn.transaction():
                initial = await repo.provision(conn, seed)
            async with conn.transaction():
                assert not (await repo.provision(conn, seed))['created']
            for bad in (replace(seed, organization_id=str(uuid4())), replace(seed, workspace_id=str(uuid4()))):
                with pytest.raises(Conflict):
                    async with conn.transaction():
                        await repo.provision(conn, bad)
            # Existing synthetic test identities only; seed cannot create any user.
            admin, pilot, outsider, other = [str(uuid4()) for _ in range(4)]
            await conn.execute("INSERT INTO core_workspaces(id,slug,display_name) VALUES (%s,'other','Other tenant')", (other,))
            for ident, workspace in ((admin, seed.workspace_id), (pilot, seed.workspace_id), (outsider, other)):
                await conn.execute('INSERT INTO core_users(id,workspace_id) VALUES (%s,%s)', (ident, workspace))
            grants = replace(seed, stage='grants', admin_id=admin, pilot_id=pilot)
            with pytest.raises(Conflict):
                async with conn.transaction():
                    await repo.provision(conn, replace(grants, pilot_id=outsider))
            async with conn.transaction():
                assigned = await repo.provision(conn, grants)
            async with conn.transaction():
                assert not (await repo.provision(conn, grants))['created']
            # 5 existing admin reuse; 6 denied admin without explicit commercial grant.
            permissions = PermissionConsoleRepository()
            assert not await permissions.list_effective_permissions(conn, seed.workspace_id, admin)
            # 7 commercial grant; 9 workspace isolation.
            assert PERMISSION in await permissions.list_effective_permissions(conn, seed.workspace_id, pilot)
            assert not await permissions.list_effective_permissions(conn, other, pilot)
            assert not await permissions.list_effective_permissions(conn, seed.workspace_id, outsider)
            count = await (await conn.execute('SELECT count(*) AS n FROM core_users')).fetchone()
            assert count['n'] == 3
            # Channel uses existing horizontal metadata contract, no assistant installation.
            await conn.execute("INSERT INTO communication_providers(code,display_name) VALUES ('evolution','Test provider')")
            channel_seed = replace(grants, provider_instance='synthetic-instance', receiver_context='synthetic-receiver')
            async with conn.transaction():
                channel_result = await repo.provision(conn, channel_seed)
            binding = await MessagingRepository().binding(conn, workspace_slug='telchi_dev', channel_alias='telchi_whatsapp_dev', provider='evolution', instance='synthetic-instance')
            assert binding.environment == 'dev' and binding.tenant_id == 'telchi' and binding.module == 'telchi'
            channel = ChannelContext(binding.channel_id, 'evolution', 'synthetic-instance', 'synthetic-receiver', 'telchi', seed.workspace_id, 'telchi')
            phone = PhoneIdentityRepository()
            await phone.validate_schema(conn)
            assert await phone.resolve(conn, channel, '15550000001') is None
            phone_args = dict(workspace_id=seed.workspace_id, user_id=pilot, actor_user_id=admin,
                sender_identity='15550000001', verification_ref='synthetic-consent')
            with pytest.raises(Conflict):
                async with conn.transaction():
                    await bind_verified_dev_phone(conn, **phone_args)
            async with conn.transaction():
                phone_id = await bind_verified_dev_phone(conn, **phone_args, consent_verified=True)
            async with conn.transaction():
                assert await bind_verified_dev_phone(conn, **phone_args, consent_verified=True) == phone_id
            with pytest.raises(Conflict):
                async with conn.transaction():
                    await bind_verified_dev_phone(conn, **dict(phone_args, user_id=admin), consent_verified=True)
            with pytest.raises(Conflict):
                async with conn.transaction():
                    await bind_verified_dev_phone(conn, **dict(phone_args, verification_ref='different-proof'), consent_verified=True)
            identity = await phone.resolve(conn, channel, '15550000001')
            assert identity.permissions == frozenset({PERMISSION})
            # Cross-scope fixture exists only in a rolled-back transaction; no trigger bypass.
            async with conn.transaction():
                await conn.execute("""INSERT INTO messaging_phone_bindings(environment,provider,sender_identity,tenant_id,workspace_id,user_id,
                    verification_status,verified_at_utc,verification_ref,actor_user_id)
                    VALUES ('dev','evolution','15550000001','other',%s,%s,'verified',now(),'synthetic-other',%s)""", (seed.workspace_id, pilot, admin))
                with pytest.raises(Conflict):
                    async with conn.transaction():
                        await bind_verified_dev_phone(conn, **phone_args, consent_verified=True)
                assert (await phone.resolve(conn, channel, '15550000001')).user_id == pilot
                raise psycopg.Rollback()
            with pytest.raises(psycopg.errors.UniqueViolation):
                async with conn.transaction():
                    await conn.execute("""INSERT INTO messaging_phone_bindings(environment,provider,sender_identity,tenant_id,workspace_id,user_id,
                        verification_status,verified_at_utc,verification_ref,actor_user_id)
                        VALUES ('dev','evolution','15550000001','telchi',%s,%s,'verified',now(),'synthetic-duplicate',%s)""", (seed.workspace_id, pilot, admin))
            assert await phone.resolve(conn, replace(channel, environment='pro'), '15550000001') is None
            # 8 revocation immediately visible; do not duplicate permissions in binding.
            link = next(i for i in assigned['created'] if i['table'] == 'core_user_roles')
            await conn.execute('DELETE FROM core_user_roles WHERE id=%s', (link['row']['id'],))
            assert not (await phone.resolve(conn, channel, '15550000001')).permissions
            await conn.execute("UPDATE messaging_phone_bindings SET verification_status='revoked',revoked_at_utc=now()")
            with pytest.raises(InvalidPhoneBinding):
                await phone.resolve(conn, channel, '15550000001')
            # Restore only own exact test link to exercise safe rollback snapshots.
            row = link['row']
            await conn.execute('INSERT INTO core_user_roles(id,user_id,role_id,created_at_utc) VALUES (%s,%s,%s,%s)', tuple(row[k] for k in ('id','user_id','role_id','created_at_utc')))
            # 10 rollback grants preserves identities/scaffold/phone tombstone/audit.
            async with conn.transaction():
                await repo.rollback(conn, assigned['run_id'])
            async with conn.transaction():
                await repo.rollback(conn, assigned['run_id'])
            assert not await permissions.list_effective_permissions(conn, seed.workspace_id, pilot)
            assert (await (await conn.execute('SELECT count(*) AS n FROM core_users')).fetchone())['n'] == 3
            with pytest.raises(Conflict, match='surviving dependency'):
                async with conn.transaction():
                    await repo.rollback(conn, initial['run_id'])
            # A newly edited channel cannot be erased by rollback.
            await conn.execute("UPDATE communication_channels SET display_name='Changed by operator'")
            with pytest.raises(Conflict, match='changed'):
                async with conn.transaction():
                    await repo.rollback(conn, channel_result['run_id'])
            # A single approved identity may be both admin and pilot.
            async with conn.transaction():
                single = await repo.provision(conn, replace(grants, pilot_id=admin))
            assert PERMISSION in await permissions.list_effective_permissions(conn, seed.workspace_id, admin)
            async with conn.transaction():
                await repo.rollback(conn, single['run_id'])
            audit = await (await conn.execute("SELECT count(*) AS n FROM core_events WHERE event_name='telchi.provisioning.rolled_back'")).fetchone()
            assert audit['n'] == 3
    asyncio.run(exercise())
