"""Explicit owner-authorized DEV operational read scope over Team360 RBAC.

No users, Presidency equivalence, technical permission or FULL_ACCESS changes.
Caller owns local-target checks, SERIALIZABLE transaction and private backup.
"""
from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.datalake.operational_query import OPERATIONS, PERMISSIONS
from .category_repository import CategoryRegistrationRepository, SECURITY_TABLES, TARGET, WORKSPACE, PILOT
from .repository import Conflict, ProvisioningRepository, canonical, one

ROLE = 'telchi_operational_observations_reader_v1'
AUTHORIZATION = 'TELCHI_OPERATIONAL_AUTHORIZED_E2E_V1'


class OperationalRegistrationRepository(CategoryRegistrationRepository):
    async def activate(self, conn, *, authorization, backup_sha256):
        if authorization != AUTHORIZATION or len(backup_sha256) != 64 or any(
                c not in '0123456789abcdef' for c in backup_sha256):
            raise Conflict('owner instruction and recoverable private backup required')
        await self.guard(conn)
        if await self.target(conn) != TARGET:
            raise Conflict('not the approved local DEV database')
        identities = await self.identities(conn)
        if identities['workspace']['id'] != WORKSPACE or identities['pilot']['id'] != PILOT:
            raise Conflict('existing DEV identity/workspace changed')
        await self.user(conn, WORKSPACE, PILOT)
        before = await self.security_state(conn)
        created = []
        repo = ProvisioningRepository()
        role = await repo.ensure(conn, 'core_roles', dict(workspace_id=WORKSPACE, role_code=ROLE),
            dict(display_name='Telchi operational observations reader V1', status='active', is_system_role=False), created)
        for metric, permission in PERMISSIONS.items():
            p = await repo.ensure(conn, 'core_permissions', dict(permission_code=permission),
                dict(display_name='Telchi '+metric+' read V1', category='business',
                     description='Read-only bounded published operational observations: '+metric+
                     '. Whole Telchi DEV workspace; native units and coverage retained. No SAP, writes, administration or complete historical balance.'), created)
            await repo.ensure(conn, 'core_role_permissions',
                dict(role_id=str(role['id']), permission_id=str(p['id'])), {}, created)
            capability = metric+'.v1'
            row = await one(conn, '''SELECT * FROM core_workspace_capabilities
                WHERE workspace_id=%s AND module='telchi' AND capability_code=%s FOR UPDATE''',
                (WORKSPACE, capability))
            if row and (str(row['permission_id']) != str(p['id']) or not row['enabled']):
                raise Conflict('conflicting or disabled operational binding: '+capability)
            if not row:
                row = await one(conn, '''INSERT INTO core_workspace_capabilities
                    (workspace_id,module,capability_code,permission_id,enabled)
                    VALUES (%s,'telchi',%s,%s,true) RETURNING *''', (WORKSPACE,capability,p['id']))
                created.append(dict(table='core_workspace_capabilities',row=canonical(row)))
        grants = await (await conn.execute('''SELECT p.permission_code FROM core_role_permissions rp
            JOIN core_permissions p ON p.id=rp.permission_id WHERE rp.role_id=%s''', (role['id'],))).fetchall()
        if {r['permission_code'] for r in grants} != set(PERMISSIONS.values()):
            raise Conflict('dedicated business role contains unrelated permissions')
        await repo.ensure(conn, 'core_user_roles', dict(user_id=PILOT,role_id=str(role['id'])), {}, created)
        after = await self.security_state(conn)
        for table in SECURITY_TABLES:
            expected = before['records'][table]+[r['row'] for r in created if r['table']==table]
            if sorted(expected,key=lambda r:str(sorted(r.items()))) != sorted(after['records'][table],key=lambda r:str(sorted(r.items()))):
                raise Conflict('unrelated security change: '+table)
        expected = {u:sorted(set(codes) | (set(PERMISSIONS.values()) if u==PILOT else set()))
                    for u,codes in before['effective'].items()}
        if expected != after['effective']:
            raise Conflict('effective permissions changed outside approved DEV identity')
        audit = None
        if created:
            audit = await self.audit(conn,identities['global']['id'],WORKSPACE,'operational-read-grant',dict(
                authorization=authorization,actor_kind='explicit_local_owner_dev_procedure',
                user_id=PILOT,role=ROLE,permissions=sorted(PERMISSIONS.values()),
                backup_sha256=backup_sha256,created=created,before=before['effective'],after=after['effective'],
                full_access_changed=False,technical_permissions_added=[]))
        return dict(changed=bool(created),run_id=audit,created=created,role=ROLE,
                    effective=after['effective'][PILOT],full_access_changed=False)

    async def registered(self, conn, workspace_id, metric):
        if metric not in OPERATIONS:
            return False
        row = await one(conn, '''SELECT c.enabled FROM core_workspace_capabilities c
            JOIN core_permissions p ON p.id=c.permission_id
            WHERE c.workspace_id=%s AND c.module='telchi' AND c.capability_code=%s
            AND p.permission_code=%s''', (workspace_id,metric+'.v1',PERMISSIONS[metric]))
        return bool(row and row['enabled'])
