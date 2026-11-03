"""Owner-approved category registry increment, never grants or changes FULL_ACCESS.

Uses the existing DEV provisioning lock, catalog and administrative ledger.
Caller verifies local DEV target and owns SERIALIZABLE transaction/private backup.
"""
import json

from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.datalake.category_line_amount_query import CAPABILITY, PERMISSION
from .business_close_repository import BusinessCloseRepository
from .repository import Conflict, ProvisioningRepository, canonical, one

AUTHORIZATION = 'TEAM360 / TELCHIAI — ACTIVACIÓN SCOPED DE CATEGORY SALES V1'
WORKSPACE = '3fb026a1-a4ba-44b3-b65b-fab452df7fc9'
ORGANIZATION = '44b9b7ea-1c19-4a9f-a3d5-1f20622d2f99'
PILOT = '5015a69d-eb86-4ac9-b97f-c31dc06e2b59'
TARGET = dict(database='team360', system_identifier='7630993354699489317',
              server_address='172.18.0.2/32', server_port=5432)
# Fixed internal names. Full snapshots protect assignments and foreign scopes.
SECURITY_TABLES = ('core_permissions', 'core_roles', 'core_role_permissions',
    'core_user_roles', 'core_permission_profiles', 'core_profile_permissions',
    'core_user_profiles', 'core_module_full_access_grants', 'core_workspace_capabilities')


class CategoryRegistrationRepository(BusinessCloseRepository):
    async def security_state(self, conn):
        records = {}
        for table in SECURITY_TABLES:
            records[table] = canonical(await (await conn.execute(
                f'SELECT * FROM {table}')).fetchall())
            records[table].sort(key=lambda r: json.dumps(r, sort_keys=True))
        users = await (await conn.execute('SELECT id::text,workspace_id::text FROM core_users ORDER BY id')).fetchall()
        resolver = PermissionConsoleRepository()
        effective = {u['id']: await resolver.list_effective_permissions(conn, u['workspace_id'], u['id'])
                     for u in users if u['workspace_id']}
        return dict(records=records, effective=effective)

    async def snapshot(self, conn):
        result = await super().snapshot(conn)
        result['security'] = await self.security_state(conn)
        return result

    async def activate(self, conn, *, authorization, backup_sha256):
        if authorization != AUTHORIZATION or len(backup_sha256) != 64 or any(
                c not in '0123456789abcdef' for c in backup_sha256):
            raise Conflict('explicit category owner authorization and private backup required')
        await self.guard(conn)
        if await self.target(conn) != TARGET:
            raise Conflict('unapproved DEV database identity')
        identities = await self.identities(conn)
        if (identities['workspace'] != dict(id=WORKSPACE, organization_id=ORGANIZATION)
                or identities['pilot']['id'] != PILOT):
            raise Conflict('approved Telchi DEV scope changed')
        before = await self.security_state(conn)
        records = before['records']
        active = [g for g in records['core_module_full_access_grants']
                  if g['workspace_id'] == WORKSPACE and g['module'] == 'telchi' and g['revoked_at_utc'] is None]
        if len(active) != 1 or active[0]['user_id'] != PILOT or active[0]['organization_id'] != ORGANIZATION:
            raise Conflict('existing pilot-only scoped FULL_ACCESS required; no assignment changes allowed')
        permissions = records['core_permissions']
        if any('*' in p['permission_code'] for p in permissions):
            raise Conflict('wildcard catalog requires explicit review')
        existing = [p for p in permissions if p['permission_code'] == PERMISSION]
        permission_id = existing[0]['id'] if existing else None
        for table in ('core_role_permissions', 'core_profile_permissions'):
            if any(r['permission_id'] == permission_id for r in records[table]):
                raise Conflict('preexisting explicit category grant requires review')
        for row in records['core_workspace_capabilities']:
            if row['capability_code'] == CAPABILITY or row['permission_id'] == permission_id:
                if (row['workspace_id'] != WORKSPACE or row['module'] != 'telchi'
                        or row['capability_code'] != CAPABILITY or row['permission_id'] != permission_id
                        or row['enabled'] is not True):
                    raise Conflict('category registry conflict; no foreign scope or implicit reactivation')
        created = []
        permission = await ProvisioningRepository().ensure(conn, 'core_permissions',
            dict(permission_code=PERMISSION), dict(display_name='Telchi category commercial line amount read V1',
                category='business', description='Active BS commercial invoice lines by accredited business category and bounded period; line discount included, no line VAT, credit notes, global adjustments, net billing or collections.'), created)
        row = await one(conn, '''SELECT * FROM core_workspace_capabilities
            WHERE workspace_id=%s AND module='telchi' AND capability_code=%s FOR UPDATE''', (WORKSPACE, CAPABILITY))
        if not row:
            row = await one(conn, '''INSERT INTO core_workspace_capabilities
                (workspace_id,module,capability_code,permission_id,enabled)
                VALUES (%s,'telchi',%s,%s,true) RETURNING *''', (WORKSPACE, CAPABILITY, permission['id']))
            created.append(dict(table='core_workspace_capabilities', row=canonical(row)))
        after = await self.security_state(conn)
        for table in SECURITY_TABLES:
            expected = list(records[table]) + [c['row'] for c in created if c['table'] == table]
            if sorted(expected, key=lambda r: json.dumps(r, sort_keys=True)) != after['records'][table]:
                raise Conflict('unrelated security records changed: ' + table)
        expected_effective = {u: sorted(set(codes) | ({PERMISSION} if u == PILOT else set()))
                              for u, codes in before['effective'].items()}
        if after['effective'] != expected_effective:
            raise Conflict('effective permissions changed outside approved pilot increment')
        run_id = None
        if created:
            run_id = await self.audit(conn, identities['global']['id'], WORKSPACE, 'category-register', dict(
                authorization=authorization, actor_kind='explicit_local_owner_dev_procedure',
                organization_id=ORGANIZATION, module='telchi', capability=CAPABILITY, permission=PERMISSION,
                before=before, after=after, created=created, backup_sha256=backup_sha256,
                assignments_created=0, full_access_changed=False, result='registered'))
        return dict(changed=bool(created), run_id=run_id, created=created,
                    before=before['effective'][PILOT], effective=after['effective'][PILOT],
                    assignments_created=0, full_access_changed=False)
