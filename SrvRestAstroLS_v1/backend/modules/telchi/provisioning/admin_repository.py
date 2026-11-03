"""Small administrative adapter over the existing seed, Console RBAC and 027.

No credential enrollment, module installation or global configuration writes.
Caller owns transaction. Limits are recorded in the existing audit ledger, not
an alternative permission or module database.
"""
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from modules.console.repositories import PermissionConsoleRepository
from .repository import Conflict, ProvisioningRepository, PERMISSION, CAPABILITY, one
from .phone_binding import bind_verified_dev_phone

ROLE = 'telchi_source_quantity_reader_v1'


class AdminRepository:
    async def global_actor(self, conn, actor_id):
        actor = await one(conn, "SELECT * FROM core_users WHERE id=%s AND status='active'", (actor_id,))
        if not actor or not actor['workspace_id']:
            raise Conflict('active workspace-bound global actor required')
        role = await one(conn, """SELECT r.id FROM core_user_roles ur JOIN core_roles r ON r.id=ur.role_id
            WHERE ur.user_id=%s AND r.role_code='platform_admin' AND r.status='active'
            AND (r.workspace_id IS NULL OR r.workspace_id=%s)""", (actor_id, actor['workspace_id']))
        effective = await PermissionConsoleRepository().list_effective_permissions(conn, str(actor['workspace_id']), actor_id)
        if not role or 'user.manage' not in effective:
            raise Conflict('persisted platform_admin and user.manage required')

    async def delegated_actor(self, conn, actor_id, workspace_id, *, lock=True):
        actor = await one(conn, """SELECT m.id FROM core_organization_members m
            JOIN core_organization_member_roles r ON r.organization_member_id=m.id
            JOIN core_workspaces w ON w.organization_id=m.organization_id
            JOIN core_organizations o ON o.id=m.organization_id
            JOIN core_users u ON u.id=m.user_id
            WHERE w.id=%s AND w.slug='telchi_dev' AND w.status IN ('active','testing')
            AND o.organization_code='telchi' AND o.status='active' AND m.user_id=%s
            AND m.status='active' AND r.role_code='organization_admin' AND r.status='active'
            AND u.workspace_id=w.id AND u.status='active'""" + (' FOR UPDATE OF m,r,u,w' if lock else ''), (workspace_id, actor_id))
        if not actor:
            raise Conflict('active Telchi organization_admin required')
        policy = await one(conn, """SELECT payload_jsonb FROM core_events WHERE workspace_id=%s
            AND event_name='telchi.admin.bootstrap' ORDER BY occurred_at_utc DESC,id DESC LIMIT 1""", (workspace_id,))
        if not policy or policy['payload_jsonb'].get('limits') != self.limits():
            raise Conflict('global-approved DEV administrative limits missing or incompatible')

    @staticmethod
    def limits():
        return dict(environment='dev', modules=['telchi'], permissions=[PERMISSION],
                    roles=[ROLE], capability=CAPABILITY, credential_enrollment=False,
                    runtime_module_enabled=False)

    async def audit(self, conn, actor, workspace, action, payload):
        run = str(uuid4())
        await conn.execute("""INSERT INTO core_events(workspace_id,actor_user_id,event_name,
            entity_type,correlation_id,payload_jsonb) VALUES (%s,%s,%s,'telchi_admin',%s,%s)""",
            (workspace, actor, 'telchi.admin.' + action, run, Jsonb(payload)))
        return run

    async def bootstrap(self, conn, actor_id, seed):
        await self.global_actor(conn, actor_id)
        result = await ProvisioningRepository().provision(conn, seed, actor_id=actor_id)
        if seed.stage == 'scaffold':
            return dict(created_count=len(result['created']), seed_run_id=result['run_id'], delegation_enabled=False)
        existing = await one(conn, """SELECT payload_jsonb FROM core_events WHERE workspace_id=%s
            AND event_name='telchi.admin.bootstrap' ORDER BY occurred_at_utc DESC,id DESC LIMIT 1""", (seed.workspace_id,))
        payload = dict(limits=self.limits(), admin_id=seed.admin_id)
        if existing and existing['payload_jsonb'] != payload:
            raise Conflict('existing delegation differs; reconcile explicitly')
        if not existing:
            await self.audit(conn, actor_id, seed.workspace_id, 'bootstrap', payload)
        return dict(created_count=len(result['created']), seed_run_id=result['run_id'], limits=self.limits())

    async def user(self, conn, workspace, user_id, *, lock=True):
        user = await one(conn, 'SELECT id,status FROM core_users WHERE id=%s AND workspace_id=%s' + (' FOR UPDATE' if lock else ''), (user_id, workspace))
        if not user or user['status'] != 'active':
            raise Conflict('existing active identity in this workspace required; no move or enrollment')
        return user

    async def role(self, conn, workspace):
        role = await one(conn, "SELECT id FROM core_roles WHERE workspace_id=%s AND role_code=%s AND status='active' FOR UPDATE", (workspace, ROLE))
        if not role:
            raise Conflict('seed commercial role missing')
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute('SELECT p.permission_code FROM core_role_permissions rp JOIN core_permissions p ON p.id=rp.permission_id WHERE rp.role_id=%s', (role['id'],))
            codes = [r['permission_code'] for r in await cur.fetchall()]
        if codes != [PERMISSION]:
            raise Conflict('commercial role outside approved catalog')
        return role

    async def manage(self, conn, actor, workspace, operation):
        await self.delegated_actor(conn, actor, workspace)
        action = operation['action']
        if action == 'grant-sales':
            from .sales_repository import SalesActivationRepository
            return await SalesActivationRepository().grant_sales(conn, actor, workspace, operation['user_id'])
        if action == 'inspect':
            # No numbers, proof references, emails or names in CLI output.
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT id::text,user_id::text,verification_status FROM messaging_phone_bindings WHERE workspace_id=%s AND tenant_id='telchi' AND environment='dev' AND provider='evolution' ORDER BY id", (workspace,))
                bindings = await cur.fetchall()
                await cur.execute('SELECT user_id::text FROM core_organization_members WHERE organization_id=(SELECT organization_id FROM core_workspaces WHERE id=%s) AND status=\'active\' ORDER BY user_id', (workspace,))
                members = await cur.fetchall()
            users = [dict(user_id=m['user_id'], permissions=await PermissionConsoleRepository().list_effective_permissions(conn, workspace, m['user_id'])) for m in members]
            return dict(users=users, bindings=bindings, limits=self.limits())
        user_id = operation['user_id']
        await self.user(conn, workspace, user_id)
        role = await self.role(conn, workspace)
        changed = False
        if action == 'grant':
            effective = await PermissionConsoleRepository().list_effective_permissions(conn, workspace, user_id)
            if set(effective) - {PERMISSION}:
                raise Conflict('identity has out-of-catalog grants; manual reconciliation required')
            ledger = []
            org = await one(conn, 'SELECT organization_id FROM core_workspaces WHERE id=%s', (workspace,))
            repo = ProvisioningRepository()
            await repo.ensure(conn, 'core_organization_members', dict(organization_id=str(org['organization_id']), user_id=user_id), dict(status='active'), ledger)
            await repo.ensure(conn, 'core_user_roles', dict(user_id=user_id, role_id=str(role['id'])), {}, ledger)
            changed = bool(ledger)
        elif action == 'revoke-access':
            effective = await PermissionConsoleRepository().list_effective_permissions(conn, workspace, user_id)
            async with conn.cursor() as cur:
                await cur.execute('SELECT 1 FROM core_user_profiles WHERE user_id=%s', (user_id,))
                profiles = await cur.fetchone()
                await cur.execute('SELECT 1 FROM core_user_roles WHERE user_id=%s AND role_id<>%s', (user_id, role['id']))
                unrelated = await cur.fetchone()
            if profiles or unrelated or set(effective) - {PERMISSION} or user_id == actor:
                raise Conflict('revocation has unrelated grants or targets actor; global reconciliation required')
            cur = await conn.execute('DELETE FROM core_user_roles WHERE user_id=%s AND role_id=%s', (user_id, role['id']))
            changed = bool(cur.rowcount)
            # All DEV lines are revoked, while individual revoke-phone affects one only.
            cur = await conn.execute("UPDATE messaging_phone_bindings SET verification_status='revoked',revoked_at_utc=now(),actor_user_id=%s WHERE user_id=%s AND workspace_id=%s AND tenant_id='telchi' AND environment='dev' AND provider='evolution' AND verification_status<>'revoked'", (actor, user_id, workspace))
            changed |= bool(cur.rowcount)
            cur = await conn.execute("UPDATE core_organization_member_roles SET status='inactive' WHERE organization_member_id IN (SELECT m.id FROM core_organization_members m JOIN core_workspaces w ON w.organization_id=m.organization_id WHERE w.id=%s AND m.user_id=%s) AND status='active'", (workspace, user_id))
            changed |= bool(cur.rowcount)
            cur = await conn.execute("UPDATE core_organization_members SET status='inactive' WHERE organization_id=(SELECT organization_id FROM core_workspaces WHERE id=%s) AND user_id=%s AND status='active'", (workspace, user_id))
            changed |= bool(cur.rowcount)
        elif action == 'bind-phone':
            binding = await bind_verified_dev_phone(conn, workspace_id=workspace, user_id=user_id, actor_user_id=actor,
                sender_identity=operation['sender_identity'], verification_ref=operation['verification_ref'], consent_verified=operation['consent_verified'])
            return dict(binding_id=binding)  # 027 trigger is the authoritative audit.
        elif action == 'revoke-phone':
            row = await one(conn, "SELECT id,verification_status FROM messaging_phone_bindings WHERE id=%s AND user_id=%s AND workspace_id=%s AND environment='dev' AND tenant_id='telchi' AND provider='evolution' FOR UPDATE", (operation['binding_id'], user_id, workspace))
            if not row:
                raise Conflict('binding does not belong to requested user/DEV workspace')
            if row['verification_status'] != 'revoked':
                await conn.execute("UPDATE messaging_phone_bindings SET verification_status='revoked',revoked_at_utc=now(),actor_user_id=%s WHERE id=%s", (actor, row['id']))
                changed = True
        else:
            raise Conflict('unsupported operation')
        if changed:
            await self.audit(conn, actor, workspace, action, dict(user_id=user_id))
        effective = await PermissionConsoleRepository().list_effective_permissions(conn, workspace, user_id)
        if (action == 'grant' and PERMISSION not in effective) or (action == 'revoke-access' and effective):
            raise Conflict('effective permission postcondition failed')
        return dict(changed=changed, permissions=effective)

    async def guard(self, conn):
        await conn.execute('SET LOCAL search_path=public,pg_catalog')
        await conn.execute("SET LOCAL lock_timeout='3s'")
        await conn.execute("SET LOCAL statement_timeout='10s'")
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('telchi-provisioning-v1'))")
        version = await one(conn, 'SHOW server_version_num')
        if not version['server_version_num'].startswith('18'):
            raise Conflict('PG18 required')

    async def target(self, conn):
        return await one(conn, "SELECT current_database() AS database,(pg_control_system()).system_identifier::text AS system_identifier,inet_server_addr()::text AS server_address,inet_server_port() AS server_port")
