import asyncio
import base64
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from modules.console.auth import ConsolePrincipal, verify_console_access_token
from modules.console.repositories import PermissionConsoleRepository
from modules.messaging.handlers import ChannelContext
from modules.messaging.repository import MessagingRepository
from modules.messaging.domain.messages import InboundMessage
from modules.messaging.identity import PhoneIdentityRepository, InvalidPhoneBinding
from modules.security.paseto_tokens import PasetoKeyPair, issue_paseto_v4_public
from modules.telchi.provisioning.admin_repository import AdminRepository, ROLE
from modules.telchi.provisioning.admin_service import AdminService, validate
from modules.telchi.provisioning.repository import Seed, Conflict, PERMISSION, ProvisioningRepository
from modules.telchi.provisioning.tests.test_provisioning_pg18 import DSN, ROOT
from urllib.parse import urlparse


def uid():
    return str(uuid4())


def principal(user):
    # Real Console signing/verifier; synthetic key exists only inside the test.
    key = PasetoKeyPair.generate('test-admin')
    token = issue_paseto_v4_public(dict(sub='user:' + user, user_id=user), private_key_pem=key.private_pem,
        key_id=key.key_id, ttl_seconds=60, issuer='team360', token_type='console_access')
    return verify_console_access_token(token, public_keys_by_id={key.key_id: key.public_pem})


def manifest(actor, workspace, operations):
    return dict(version=1, environment='dev', actor_id=actor, workspace_id=workspace,
                command='manage-client', operations=operations)


def grant(user):
    return dict(action='grant', user_id=user, role=ROLE, permissions=[PERMISSION], modules=['telchi'])


@pytest.mark.parametrize('change', ['prod', 'module', 'permission', 'role', 'password', 'enrollment', 'phone', 'consent', 'proof'])
def test_manifest_rejections(change):
    user = uid()
    data = manifest(uid(), uid(), [grant(user)])
    if change == 'prod': data['environment'] = 'pro'
    elif change == 'module': data['operations'][0]['modules'] = ['flow']
    elif change == 'permission': data['operations'][0]['permissions'] = ['user.manage']
    elif change == 'role': data['operations'][0]['role'] = 'platform_admin'
    elif change == 'password': data['password'] = 'not-accepted'
    elif change == 'enrollment': data['operations'] = [dict(action='create-user', user_id=user)]
    else:
        op = dict(action='bind-phone', user_id=user, sender_identity='15550000001', consent_verified=True, verification_ref='opaque-test-proof')
        if change == 'phone': op['sender_identity'] = '+15550000001'
        if change == 'consent': op['consent_verified'] = False
        if change == 'proof': op['verification_ref'] = ''
        data['operations'] = [op]
    with pytest.raises(Conflict): validate(data)


def test_legacy_execution_is_disabled(monkeypatch):
    from modules.telchi.provisioning.cli import main
    monkeypatch.setattr(sys, 'argv', ['seed-cli', '--manifest', '/not-read.json', '--apply'])
    with pytest.raises(Conflict, match='legacy unauthenticated execution disabled'):
        asyncio.run(main())


def test_actor_not_manifest_identity():
    data = manifest(uid(), uid(), [dict(action='inspect')])
    with pytest.raises(Conflict, match='actor mismatch'):
        asyncio.run(AdminService().execute(None, data, principal(uid())))


@pytest.mark.skipif(not DSN, reason='explicit disposable PG18 required')
def test_admin_pg18_contracts():
    p = urlparse(DSN)
    assert p.hostname == '127.0.0.1' and p.port not in (None, 5432) and p.path == '/telchi_provisioning_disposable'

    async def exercise():
        async with await psycopg.AsyncConnection.connect(DSN, autocommit=True, row_factory=dict_row) as conn:
            await conn.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
            for filename in ('001_team360_core_schema.sql', '002_team360_rbac_packages_workers_knowledge.sql'):
                await conn.execute((Path('db/migrations') / filename).read_text())
            await conn.execute('\n'.join(line for line in (ROOT / 'organization_schema_pg18.sql').read_text().splitlines() if not line.startswith('\\')))
            await conn.execute('SET search_path=public,pg_catalog')
            await conn.execute('ALTER TABLE core_workspaces ADD COLUMN organization_id uuid REFERENCES core_organizations(id) ON DELETE SET NULL')
            await conn.execute(Path('db/migrations/027_team360_messaging_phone_bindings.sql').read_text())
            await conn.execute(Path('db/migrations/026_team360_messaging_transport_v1.sql').read_text())
            repo, service = AdminRepository(), AdminService()
            global_id, global_ws, admin, pilot, second, outsider, outsider_ws = [uid() for _ in range(7)]
            await conn.execute("INSERT INTO core_workspaces(id,slug,display_name) VALUES (%s,'platform','Platform'),(%s,'other','Other')", (global_ws, outsider_ws))
            await conn.execute('INSERT INTO core_users(id,workspace_id) VALUES (%s,%s),(%s,%s)', (global_id, global_ws, outsider, outsider_ws))
            other_org = uid()
            await conn.execute("INSERT INTO core_organizations(id,organization_code,display_name,primary_type,status) VALUES (%s,'other','Other','client','active')", (other_org,))
            await conn.execute('UPDATE core_workspaces SET organization_id=%s WHERE id=%s', (other_org, outsider_ws))
            member = await (await conn.execute("INSERT INTO core_organization_members(organization_id,user_id,status) VALUES (%s,%s,'active') RETURNING id", (other_org, outsider))).fetchone()
            await conn.execute("INSERT INTO core_organization_member_roles(organization_member_id,role_code,status) VALUES (%s,'organization_admin','active')", (member['id'],))
            role = await (await conn.execute("INSERT INTO core_roles(workspace_id,role_code,display_name) VALUES (%s,'platform_admin','Platform admin') RETURNING id", (global_ws,))).fetchone()
            await conn.execute('INSERT INTO core_user_roles(user_id,role_id) VALUES (%s,%s)', (global_id, role['id']))
            await conn.execute("INSERT INTO core_role_permissions(role_id,permission_id) SELECT %s,id FROM core_permissions WHERE permission_code='user.manage'", (role['id'],))
            seed = Seed(uid(), uid())
            bootstrap = dict(version=1, environment='dev', actor_id=global_id, workspace_id=seed.workspace_id, command='bootstrap-client', seed=dict(workspace_id=seed.workspace_id, organization_id=seed.organization_id, stage='scaffold'))
            async def apply(data):
                async with conn.transaction():
                    await conn.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
                    return await service.execute(conn, data, principal(data['actor_id']), dry_run=False)
            # Global actor is resolved in DB, not legacy role strings or manifest approvals.
            with pytest.raises(Conflict):
                await apply(dict(bootstrap, actor_id=outsider))
            initial = await apply(bootstrap)
            assert initial['created_count'] == 2
            assert (await apply(bootstrap))['created_count'] == 0
            for user in (admin, pilot, second):
                await conn.execute('INSERT INTO core_users(id,workspace_id) VALUES (%s,%s)', (user, seed.workspace_id))
            bootstrap['seed'].update(stage='grants', admin_id=admin, pilot_id=admin)
            async with conn.transaction():
                await conn.execute('SET TRANSACTION READ ONLY')
                plan = await service.execute(conn, bootstrap, principal(global_id))
                assert plan['stage'] == 'grants'
            result = await apply(bootstrap)
            assert result['created_count'] > 0 and not result['limits']['runtime_module_enabled']
            assert (await apply(bootstrap))['created_count'] == 0
            count = await (await conn.execute("SELECT count(*) AS n FROM core_events WHERE event_name='telchi.admin.bootstrap'")).fetchone()
            assert count['n'] == 1
            # DB READ ONLY is proof that dry-run does not simulate writes then rollback.
            async with conn.transaction():
                await conn.execute('SET TRANSACTION READ ONLY')
                plan = await service.execute(conn, manifest(admin, seed.workspace_id, [grant(pilot)]), principal(admin))
                assert plan['mode'] == 'READ_ONLY_PLAN'
            assert not await PermissionConsoleRepository().list_effective_permissions(conn, seed.workspace_id, pilot)
            # CLI runs with owner-only files outside Git and a real verified test token.
            with tempfile.TemporaryDirectory(prefix='telchi-admin-test-') as directory:
                key = PasetoKeyPair.generate('cli-test')
                token = issue_paseto_v4_public(dict(sub='user:' + admin, user_id=admin), private_key_pem=key.private_pem, key_id=key.key_id, ttl_seconds=60, issuer='team360', token_type='console_access')
                path, trust_path = Path(directory) / 'manifest.json', Path(directory) / 'trust.json'
                path.write_text(json.dumps(manifest(admin, seed.workspace_id, [grant(pilot)])))
                trust_path.write_text(json.dumps(dict(environment='dev', target=await repo.target(conn), approvals=dict(dev_isolation='synthetic-disposable', explicit_application='test', backup_restore='discardable-test', authenticated_issuer='synthetic-test-only'))))
                path.chmod(0o600); trust_path.chmod(0o600)
                env = dict(os.environ, TELCHI_ADMIN_TRUST_CONFIG=str(trust_path), TELCHI_PROVISIONING_DSN=DSN, TEAM360_PASETO_ENABLED='true', TEAM360_PASETO_KEY_ID=key.key_id, TEAM360_PASETO_PUBLIC_KEY_B64=base64.b64encode(key.public_pem.encode()).decode())
                async def cli(mode, input_token):
                    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'modules.telchi.provisioning.admin_cli', 'manage-client', '--manifest', str(path), mode, env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    out, err = await process.communicate((input_token + '\n').encode())
                    return process.returncode, out, err
                code, out, err = await cli('--dry-run', token)
                assert code == 0 and json.loads(out)['mode'] == 'READ_ONLY_PLAN', err
                assert not await PermissionConsoleRepository().list_effective_permissions(conn, seed.workspace_id, pilot)
                assert (await cli('--apply', 'invalid-token'))[0] == 1
                original_trust = json.loads(trust_path.read_text())
                incorrect = dict(original_trust, environment='pro')
                trust_path.write_text(json.dumps(incorrect))
                assert (await cli('--apply', token))[0] == 1
                incorrect = dict(original_trust, target=dict(original_trust['target'], database='wrong'))
                trust_path.write_text(json.dumps(incorrect))
                assert (await cli('--apply', token))[0] == 1
                trust_path.write_text(json.dumps(original_trust))
                assert not await PermissionConsoleRepository().list_effective_permissions(conn, seed.workspace_id, pilot)
                code, out, err = await cli('--apply', token)
                assert code == 0 and json.loads(out)[0]['changed'], err
                # Restore only this test grant for subsequent rollback/denial scenarios.
                await conn.execute('DELETE FROM core_user_roles WHERE user_id=%s', (pilot,))
            for denied in (outsider, pilot):
                with pytest.raises(Conflict): await apply(manifest(denied, seed.workspace_id, [grant(second)]))
            with pytest.raises(Conflict): await apply(manifest(admin, outsider_ws, [grant(outsider)]))
            # Transaction failure rolls back the first otherwise-valid grant.
            with pytest.raises(Conflict):
                await apply(manifest(admin, seed.workspace_id, [grant(pilot), grant(outsider)]))
            assert not await PermissionConsoleRepository().list_effective_permissions(conn, seed.workspace_id, pilot)
            assert (await apply(manifest(admin, seed.workspace_id, [grant(pilot)])))[0]['changed']
            assert not (await apply(manifest(admin, seed.workspace_id, [grant(pilot)])))[0]['changed']
            await conn.execute("INSERT INTO communication_providers(code,display_name) VALUES ('evolution','Test')")
            channel = ChannelContext(uid(), 'evolution', 'synthetic-instance', 'synthetic-receiver', 'telchi', seed.workspace_id, 'telchi')
            phone = PhoneIdentityRepository()
            numbers = ['15550000001', '15550000002', '15550000003']
            async def bind(user, number):
                return (await apply(manifest(admin, seed.workspace_id, [dict(action='bind-phone', user_id=user, sender_identity=number, verification_ref='synthetic-independent-proof-' + number, consent_verified=True)])))[0]['binding_id']
            b1, b2 = await bind(pilot, numbers[0]), await bind(pilot, numbers[1])
            assert await bind(pilot, numbers[0]) == b1
            assert b1 != b2
            # Existing horizontal conversation storage keeps two lines independent.
            async with conn.transaction():
                await ProvisioningRepository().provision(conn, replace(seed, stage='grants', admin_id=admin, pilot_id=admin, provider_instance='synthetic-instance', receiver_context='synthetic-receiver'))
            messaging = MessagingRepository()
            binding = await messaging.binding(conn, workspace_slug='telchi_dev', channel_alias='telchi_whatsapp_dev', provider='evolution', instance='synthetic-instance')
            channel = replace(channel, channel_id=binding.channel_id)
            threads = []
            for n in numbers[:2]:
                message = InboundMessage('evolution', 'whatsapp', uid(), '', n, ('synthetic-receiver',), '', 'synthetic-message', datetime.now(timezone.utc))
                async with conn.transaction():
                    claimed = await messaging.claim(conn, binding, message, {})
                threads.append(claimed['thread_id'])
            assert threads[0] != threads[1]
            for n in numbers[:2]:
                identity = await phone.resolve(conn, channel, n)
                assert identity.user_id == pilot and identity.permissions == frozenset({PERMISSION})
                assert await phone.resolve(conn, replace(channel, environment='pro'), n) is None
                assert await phone.resolve(conn, replace(channel, provider='unknown'), n) is None
            with pytest.raises(Conflict): await bind(admin, numbers[0])
            with pytest.raises(Conflict):
                await apply(manifest(admin, seed.workspace_id, [dict(action='revoke-phone', user_id=second, binding_id=b1)]))
            # Second user has membership but zero permissions; no cross-user grant leakage.
            await conn.execute("INSERT INTO core_organization_members(organization_id,user_id,status) VALUES (%s,%s,'active')", (seed.organization_id, second))
            await conn.execute("INSERT INTO messaging_phone_bindings(environment,provider,sender_identity,tenant_id,workspace_id,user_id,verification_status,verified_at_utc,verification_ref,actor_user_id) VALUES ('dev','evolution',%s,'telchi',%s,%s,'verified',now(),'synthetic-second',%s)", (numbers[2], seed.workspace_id, second, admin))
            assert not (await phone.resolve(conn, channel, numbers[2])).permissions
            # Permission re-read on both lines (not copied to bindings).
            await conn.execute('DELETE FROM core_user_roles WHERE user_id=%s', (pilot,))
            for n in numbers[:2]: assert not (await phone.resolve(conn, channel, n)).permissions
            await apply(manifest(admin, seed.workspace_id, [grant(pilot)]))
            revoke = manifest(admin, seed.workspace_id, [dict(action='revoke-phone', user_id=pilot, binding_id=b1)])
            assert (await apply(revoke))[0]['changed']
            assert not (await apply(revoke))[0]['changed']
            with pytest.raises(InvalidPhoneBinding): await phone.resolve(conn, channel, numbers[0])
            assert (await phone.resolve(conn, channel, numbers[1])).permissions == frozenset({PERMISSION})
            with pytest.raises(Conflict): await bind(pilot, numbers[0])
            # Revocation closes all remaining DEV lines and scoped membership, not identity.
            await apply(manifest(admin, seed.workspace_id, [dict(action='revoke-access', user_id=pilot)]))
            with pytest.raises(InvalidPhoneBinding): await phone.resolve(conn, channel, numbers[1])
            assert not await PermissionConsoleRepository().list_effective_permissions(conn, seed.workspace_id, pilot)
            assert not (await phone.resolve(conn, channel, numbers[2])).permissions
            assert not (await apply(manifest(admin, seed.workspace_id, [dict(action='revoke-access', user_id=pilot)])))[0]['changed']
            view = (await apply(manifest(admin, seed.workspace_id, [dict(action='inspect')])))[0]
            assert len(view['bindings']) == 3 and 'sender_identity' not in str(view)
            events = await (await conn.execute("SELECT count(*) AS n FROM core_events WHERE event_name LIKE 'telchi.admin.%' AND actor_user_id IS NULL")).fetchone()
            assert events['n'] == 0
            # Protected seed rollback refuses live dependencies, never erases people.
            with pytest.raises(Conflict):
                async with conn.transaction(): await ProvisioningRepository().rollback(conn, initial['seed_run_id'])
            assert (await (await conn.execute('SELECT count(*) AS n FROM core_users')).fetchone())['n'] == 5
    asyncio.run(exercise())
