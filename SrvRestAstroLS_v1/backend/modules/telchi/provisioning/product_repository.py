"""Incremental, owner-authorized DEV product grants through existing RBAC ledger."""
from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.datalake.product_sales_query import PERMISSIONS
from modules.telchi.datalake.sales_query import PERMISSIONS as SALES_PERMISSIONS, MONETARY_PERMISSION
from .monetary_repository import MonetaryActivationRepository
from .sales_repository import SalesActivationRepository
from .repository import Conflict, ProvisioningRepository, PERMISSION, canonical, one

AUTHORIZATION = 'TEAM360 / TELCHIAI — PRODUCT SEARCH & SALES BY ITEM V1'
ROLES = {op: 'telchi_' + op.replace('.', '_') + '_reader_v1' for op in PERMISSIONS}


class ProductActivationRepository(MonetaryActivationRepository):
    @staticmethod
    def sales_limits():
        return dict(environment='dev', modules=['telchi'], permissions=list(PERMISSIONS.values()),
                    capabilities=[op+'.v1' for op in PERMISSIONS], roles=list(ROLES.values()),
                    whole_workspace=True, credential_enrollment=False, free_sql=False,
                    publication='foundation_afd08d9eca6a725be53cdc3f9d5709c9', snapshot=1408,
                    line_amounts=False, physical_quantity_totals=False, namespace='SAP_HANA')

    async def snapshot(self, conn):
        result = await super().snapshot(conn)
        extra = await (await conn.execute('SELECT * FROM core_permissions WHERE permission_code=ANY(%s)',
                                         (list(PERMISSIONS.values()),))).fetchall()
        result['records']['permissions'].extend(canonical(extra))
        return result

    async def activate(self, conn, *, backup_sha256, authorization):
        if authorization != AUTHORIZATION:
            raise Conflict('explicit product owner authorization required')
        await self.guard(conn)
        identities = await self.identities(conn)
        global_id, admin, pilot = [identities[k]['id'] for k in ('global', 'admin', 'pilot')]
        workspace = identities['workspace']['id']
        await SalesActivationRepository().approved(conn, workspace, admin)
        monetary = await one(conn, "SELECT payload_jsonb FROM core_events WHERE workspace_id=%s AND event_name='telchi.admin.monetary-authorize' ORDER BY occurred_at_utc DESC,id DESC LIMIT 1", (workspace,))
        if not monetary or monetary['payload_jsonb']['after'] != dict(limits=MonetaryActivationRepository.sales_limits(), admin_id=admin):
            raise Conflict('monetary entitlement/delegation not verified')
        baseline = {PERMISSION, *SALES_PERMISSIONS.values(), MONETARY_PERMISSION}
        resolver = PermissionConsoleRepository()
        before = await resolver.list_effective_permissions(conn, workspace, pilot)
        if not baseline <= set(before) or set(before) - baseline - set(PERMISSIONS.values()):
            raise Conflict('pilot baseline missing or unrelated grants')
        member = await one(conn, "SELECT id FROM core_organization_members WHERE organization_id=%s AND user_id=%s AND status='active'", (identities['workspace']['organization_id'], pilot))
        if not member:
            raise Conflict('active pilot organization membership required')
        repo, created = ProvisioningRepository(), []
        for op, code in PERMISSIONS.items():
            permission = await repo.ensure(conn, 'core_permissions', dict(permission_code=code),
                dict(display_name='Telchi '+op+' read V1', category='business',
                     description='DEV Foundation 1408; bounded read-only SAP product search or active OINV lines by verified natural ItemCodes. No SAP access, physical totals, net line amounts or free SQL.'), created)
            role = await repo.ensure(conn, 'core_roles', dict(workspace_id=workspace, role_code=ROLES[op]),
                dict(display_name='Telchi '+op+' reader V1', status='active', is_system_role=False), created)
            await repo.ensure(conn, 'core_role_permissions', dict(role_id=str(role['id']), permission_id=str(permission['id'])), {}, created)
            if await one(conn, 'SELECT id FROM core_role_permissions WHERE role_id=%s AND permission_id<>%s', (role['id'], permission['id'])):
                raise Conflict('product role has unrelated grants')
        after = dict(limits=self.sales_limits(), admin_id=admin)
        previous = await one(conn, "SELECT payload_jsonb FROM core_events WHERE workspace_id=%s AND event_name='telchi.admin.product-authorize' ORDER BY occurred_at_utc DESC,id DESC LIMIT 1", (workspace,))
        if previous and previous['payload_jsonb']['after'] != after:
            raise Conflict('product delegation differs')
        if not previous or created:
            await self.audit(conn, global_id, workspace, 'product-authorize', dict(authorization=authorization,
                actor_kind='explicit_local_owner_dev_procedure', after=after, created=created,
                backup_sha256=backup_sha256, result='approved'))
        await self.delegated_actor(conn, admin, workspace)
        await self.user(conn, workspace, pilot)
        assignments = []
        for role_code in ROLES.values():
            role = await one(conn, 'SELECT id FROM core_roles WHERE workspace_id=%s AND role_code=%s', (workspace, role_code))
            await repo.ensure(conn, 'core_user_roles', dict(user_id=pilot, role_id=str(role['id'])), {}, assignments)
        effective = await resolver.list_effective_permissions(conn, workspace, pilot)
        if set(effective) != baseline | set(PERMISSIONS.values()):
            raise Conflict('product effective permissions postcondition failed')
        run_id = None
        if assignments:
            run_id = await self.audit(conn, admin, workspace, 'product-grant', dict(user_id=pilot,
                before=before, after=effective, permissions=list(PERMISSIONS.values()), created=assignments,
                backup_sha256=backup_sha256, actor_kind='explicit_local_owner_dev_procedure', result='granted'))
        return dict(changed=bool(created or assignments or not previous), run_id=run_id,
                    catalog_created=len(created), assignments_created=len(assignments), effective=effective,
                    delegation=after)
