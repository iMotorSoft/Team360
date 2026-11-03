"""Owner-authorized, local-only DEV enrollment; no authentication/token bypass.

Only the three approved emails may be enrolled. SQL stays in this repository;
caller supplies the pinned private manifest and owns the serializable transaction.
Credentials, phone proofs and runtime configuration are intentionally untouched.
"""
from uuid import uuid4

from psycopg.types.json import Jsonb
from modules.console.repositories import PermissionConsoleRepository
from .admin_repository import AdminRepository
from .repository import Conflict, ProvisioningRepository, Seed, PERMISSION, canonical, one

EMAILS = ('admin@team360.com', 'admin@telchiai.com', 'devfull@telchiai.com')
# Only permissions present in the implemented administrative contract.
# Do not invent catalog entries for future module/service administration.
GLOBAL_PERMISSIONS = ('user.manage', 'role.manage', 'audit.view')


class LiveRepository:
    async def identity(self, conn, email, ident, workspace, ledger):
        if email not in EMAILS:
            raise Conflict('identity outside owner-approved list')
        rows = await (await conn.execute(
            'SELECT * FROM core_users WHERE lower(trim(email))=%s FOR UPDATE', (email,))).fetchall()
        if rows:
            if len(rows) != 1 or str(rows[0]['id']) != ident or str(rows[0]['workspace_id']) != workspace or rows[0]['status'] != 'active':
                raise Conflict('identity conflict: no move, duplicate or reactivation allowed')
            return rows[0]
        row = await one(conn, """INSERT INTO core_users(id,workspace_id,email,display_name,role,status)
            VALUES (%s,%s,%s,%s,%s,'active') RETURNING *""",
            (ident, workspace, email, email.split('@')[0],
             'platform_admin' if email == EMAILS[0] else 'member'))
        ledger.append(dict(table='core_users', row=canonical(row)))
        return row

    async def apply(self, conn, manifest):
        admin = AdminRepository()
        await admin.guard(conn)
        if await admin.target(conn) != manifest['target']:
            raise Conflict('target mismatch')
        repo = ProvisioningRepository()
        ledger = []
        platform = await one(conn, "SELECT id FROM core_organizations WHERE organization_code='team360_platform' AND status='active'")
        if not platform:
            raise Conflict('existing active Team360 platform organization required')
        await repo.ensure(conn, 'core_workspaces', dict(slug='team360_admin_dev'),
            dict(id=manifest['platform_workspace_id'], display_name='Team360 Admin DEV',
                 organization_id=str(platform['id']), status='testing'), ledger)
        global_id, telchi_admin, pilot = manifest['user_ids']
        await self.identity(conn, EMAILS[0], global_id, manifest['platform_workspace_id'], ledger)
        role = await repo.ensure(conn, 'core_roles', dict(workspace_id=None, role_code='platform_admin'),
            dict(id=manifest['global_role_id'], display_name='Team360 Platform Admin',
                 is_system_role=True, status='active'), ledger)
        for code in GLOBAL_PERMISSIONS:
            permission = await one(conn, 'SELECT id FROM core_permissions WHERE permission_code=%s', (code,))
            if not permission:
                raise Conflict('required existing global permission missing: ' + code)
            await repo.ensure(conn, 'core_role_permissions',
                dict(role_id=str(role['id']), permission_id=str(permission['id'])), {}, ledger)
        await repo.ensure(conn, 'core_user_roles', dict(user_id=global_id, role_id=str(role['id'])), {}, ledger)
        scaffold = Seed(**manifest['seed'])
        scaffold_result = await admin.bootstrap(conn, global_id, scaffold)
        for email, ident in zip(EMAILS[1:], (telchi_admin, pilot)):
            await self.identity(conn, email, ident, scaffold.workspace_id, ledger)
        grants = Seed(workspace_id=scaffold.workspace_id, organization_id=scaffold.organization_id,
                      stage='grants', admin_id=telchi_admin, pilot_id=pilot)
        grants_result = await admin.bootstrap(conn, global_id, grants)
        await admin.global_actor(conn, global_id)
        await admin.delegated_actor(conn, telchi_admin, scaffold.workspace_id)
        permissions = {}
        for ident, workspace in ((global_id, manifest['platform_workspace_id']),
                                 (telchi_admin, scaffold.workspace_id), (pilot, scaffold.workspace_id)):
            permissions[ident] = await PermissionConsoleRepository().list_effective_permissions(conn, workspace, ident)
        if set(permissions[pilot]) != {PERMISSION} or permissions[telchi_admin]:
            raise Conflict('Telchi identities have unexpected effective RBAC')
        run_id = None
        if ledger:
            run_id = str(uuid4())
            await conn.execute("""INSERT INTO core_events(event_name,entity_type,correlation_id,payload_jsonb)
                VALUES ('telchi.dev.local_bootstrap','telchi_provisioning',%s,%s)""",
                (run_id, Jsonb(dict(authorization=manifest['authorization'], operator_uid=manifest['operator_uid'],
                                   actor_kind='local_owner_bootstrap_not_console_login', created=ledger,
                                   backup_sha256=manifest['backup_sha256'], passwords_activated=False))))
        return dict(local_run_id=run_id, local_created_count=len(ledger),
                    scaffold=scaffold_result, grants=grants_result, permissions=permissions,
                    passwords_activated=False, runtime_module_enabled=False)
