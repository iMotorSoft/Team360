"""Owner-authorized DEV pilot FULL_ACCESS. No per-capability pilot assignments.

Catalog registration enables implemented operations in one workspace. Ordinary
users still require their normal roles/profiles. Grant/revoke append the existing
administrative ledger and retain revoked rows. Caller owns transaction/backup.
"""
from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.datalake.invoice_amount_query import CAPABILITY, PERMISSION
from .repository import Conflict, ProvisioningRepository, canonical, one
from .sales_repository import SalesActivationRepository

AUTHORIZATION = 'TEAM360 / TELCHIAI — CIERRE FUNCIONAL DEL ASISTENTE DE NEGOCIOS'
REGISTRY = {
    'telchi.sales_top_items.source_quantity.20260101_20260915.v1': 'telchi.sales.source_quantity.read.v1',
    'sales.latest_documents.v1': 'telchi.sales.latest_documents.read.v1',
    'sales.coverage.v1': 'telchi.sales.coverage.read.v1',
    'sales.period_billed_amount.v1': 'telchi.sales.period_billed_amount.read.v1',
    'products.search.v1': 'telchi.products.search.read.v1',
    'sales.by_products.v1': 'telchi.sales.by_products.read.v1',
    'sales.invoice_lines.v1': 'telchi.sales.invoice_lines.read.v1',
    CAPABILITY: PERMISSION,
}


class BusinessCloseRepository(SalesActivationRepository):
    async def snapshot(self, conn):
        result = await super().snapshot(conn)
        workspace = result['identities']['workspace']['id']
        for name in ('core_workspace_capabilities', 'core_module_full_access_grants'):
            # Fixed internal table names only.
            result['records'][name] = canonical(await (await conn.execute(
                f'SELECT * FROM {name} WHERE workspace_id=%s', (workspace,))).fetchall())
        return result

    async def activate(self, conn, *, authorization, backup_sha256):
        if authorization != AUTHORIZATION or not backup_sha256:
            raise Conflict('owner authorization and private backup required')
        await self.guard(conn)
        identities = await self.identities(conn)
        w = identities['workspace']
        actor, pilot = identities['global']['id'], identities['pilot']['id']
        await self.user(conn, w['id'], pilot)
        # Explicit scope, not a change to preexisting sales delegations.
        resolver = PermissionConsoleRepository()
        before = await resolver.list_effective_permissions(conn, w['id'], pilot)
        created = []
        repo = ProvisioningRepository()
        permission = await repo.ensure(conn, 'core_permissions', dict(permission_code=PERMISSION),
            dict(display_name='Telchi individual invoice amount read V1', category='business',
                 description='One validated active Foundation OINV header DocTotal in native currency. No line amounts, collections or outstanding balance.'), created)
        role = await repo.ensure(conn, 'core_roles', dict(workspace_id=w['id'], role_code='telchi_sales_invoice_amount_reader_v1'),
            dict(display_name='Telchi individual invoice amount reader V1', status='active', is_system_role=False), created)
        await repo.ensure(conn, 'core_role_permissions', dict(role_id=str(role['id']), permission_id=str(permission['id'])), {}, created)
        # The normal-user role is deliberately NOT assigned to the FULL_ACCESS pilot.
        for capability, code in REGISTRY.items():
            p = await one(conn, 'SELECT id FROM core_permissions WHERE permission_code=%s', (code,))
            if not p:
                raise Conflict('implemented permission not registered: ' + code)
            row = await one(conn, '''SELECT permission_id::text,enabled FROM core_workspace_capabilities
                WHERE workspace_id=%s AND module='telchi' AND capability_code=%s FOR UPDATE''', (w['id'], capability))
            if row and (row['permission_id'] != str(p['id']) or not row['enabled']):
                raise Conflict('existing capability differs or was disabled; no implicit reactivation')
            if not row:
                await conn.execute('''INSERT INTO core_workspace_capabilities(workspace_id,module,capability_code,permission_id,enabled)
                    VALUES (%s,'telchi',%s,%s,true)''', (w['id'], capability, p['id']))
                created.append(dict(capability=capability, permission=code))
        grant = await one(conn, '''SELECT id::text,organization_id::text FROM core_module_full_access_grants
            WHERE workspace_id=%s AND module='telchi' AND user_id=%s AND revoked_at_utc IS NULL FOR UPDATE''', (w['id'], pilot))
        if grant and grant['organization_id'] != w['organization_id']:
            raise Conflict('grant tenant mismatch')
        new_grant = not grant
        if new_grant:
            grant = await one(conn, '''INSERT INTO core_module_full_access_grants
                (organization_id,workspace_id,module,user_id,granted_by) VALUES (%s,%s,'telchi',%s,%s) RETURNING id::text''',
                (w['organization_id'], w['id'], pilot, actor))
        after = await resolver.list_effective_permissions(conn, w['id'], pilot)
        if set(after) != set(before) | set(REGISTRY.values()):
            raise Conflict('effective permission postcondition failed')
        if created or new_grant:
            await self.audit(conn, actor, w['id'], 'full-access-grant', dict(authorization=authorization,
                actor_kind='explicit_local_owner_dev_procedure', user_id=pilot, module='telchi',
                organization_id=w['organization_id'], grant_id=grant['id'], before=before, after=after,
                created=created, backup_sha256=backup_sha256, result='granted'))
        return dict(changed=bool(created or new_grant), grant_id=grant['id'], identities=identities,
                    before=before, effective=after, individual_pilot_assignments_created=0)

    async def revoke(self, conn, *, authorization, backup_sha256):
        if authorization != AUTHORIZATION or not backup_sha256:
            raise Conflict('owner authorization and private backup required')
        await self.guard(conn)
        identities = await self.identities(conn)
        w, pilot, actor = identities['workspace'], identities['pilot']['id'], identities['global']['id']
        resolver = PermissionConsoleRepository()
        before = await resolver.list_effective_permissions(conn, w['id'], pilot)
        rows = await (await conn.execute('''UPDATE core_module_full_access_grants
            SET revoked_at_utc=now(),revoked_by=%s
            WHERE organization_id=%s AND workspace_id=%s AND module='telchi' AND user_id=%s AND revoked_at_utc IS NULL
            RETURNING id::text''', (actor, w['organization_id'], w['id'], pilot))).fetchall()
        after = await resolver.list_effective_permissions(conn, w['id'], pilot)
        if rows:
            await self.audit(conn, actor, w['id'], 'full-access-revoke', dict(authorization=authorization,
                user_id=pilot, grant_ids=[r['id'] for r in rows], before=before, after=after,
                backup_sha256=backup_sha256, result='revoked', actor_kind='explicit_local_owner_dev_procedure'))
        return dict(changed=bool(rows), effective=after)
