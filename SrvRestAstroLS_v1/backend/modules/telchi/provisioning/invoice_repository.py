"""Incremental invoice-lines permission through the existing DEV RBAC procedure."""
from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.datalake.invoice_lines_query import PERMISSION, CAPABILITY
from .product_repository import ProductActivationRepository
from .sales_repository import SalesActivationRepository
from .repository import Conflict, ProvisioningRepository, one

AUTHORIZATION = 'TEAM360 / TELCHIAI — DOCUMENT CONTINUITY & INVOICE LINES V1'
ROLE = 'telchi_sales_invoice_lines_reader_v1'


class InvoiceActivationRepository(ProductActivationRepository):
    @staticmethod
    def sales_limits():
        return dict(environment='dev', modules=['telchi'], permissions=[PERMISSION],
                    capabilities=[CAPABILITY], roles=[ROLE], whole_workspace=True,
                    publication='foundation_afd08d9eca6a725be53cdc3f9d5709c9', snapshot=1408,
                    free_sql=False, line_amounts=False, physical_quantity_totals=False,
                    document_type='OINV', native_line_unit='not_published')

    async def snapshot(self, conn):
        result = await super().snapshot(conn)
        from .repository import canonical
        extra = await (await conn.execute('SELECT * FROM core_permissions WHERE permission_code=%s', (PERMISSION,))).fetchall()
        result['records']['permissions'].extend(canonical(extra))
        return result

    async def activate(self, conn, *, backup_sha256, authorization):
        if authorization != AUTHORIZATION:
            raise Conflict('explicit invoice owner authorization required')
        await self.guard(conn)
        identities = await self.identities(conn)
        actor, admin, pilot = [identities[k]['id'] for k in ('global', 'admin', 'pilot')]
        workspace = identities['workspace']['id']
        await SalesActivationRepository().approved(conn, workspace, admin)
        await self.delegated_actor(conn, admin, workspace)
        await self.user(conn, workspace, pilot)
        resolver = PermissionConsoleRepository()
        before = await resolver.list_effective_permissions(conn, workspace, pilot)
        repo, created = ProvisioningRepository(), []
        permission = await repo.ensure(conn, 'core_permissions', dict(permission_code=PERMISSION),
            dict(display_name='Telchi invoice products read V1', category='business',
                 description='DEV Foundation 1408: products and documentary quantity of one validated active OINV. No native line UoM, amounts, conversions or free SQL.'), created)
        role = await repo.ensure(conn, 'core_roles', dict(workspace_id=workspace, role_code=ROLE),
            dict(display_name='Telchi invoice products reader V1', status='active', is_system_role=False), created)
        await repo.ensure(conn, 'core_role_permissions', dict(role_id=str(role['id']), permission_id=str(permission['id'])), {}, created)
        if await one(conn, 'SELECT id FROM core_role_permissions WHERE role_id=%s AND permission_id<>%s', (role['id'], permission['id'])):
            raise Conflict('invoice role contains unrelated grants')
        after = dict(limits=self.sales_limits(), admin_id=admin)
        previous = await one(conn, "SELECT payload_jsonb FROM core_events WHERE workspace_id=%s AND event_name='telchi.admin.invoice-authorize' ORDER BY occurred_at_utc DESC,id DESC LIMIT 1", (workspace,))
        if previous and previous['payload_jsonb']['after'] != after:
            raise Conflict('invoice delegation differs')
        if not previous or created:
            await self.audit(conn, actor, workspace, 'invoice-authorize', dict(authorization=authorization,
                actor_kind='explicit_local_owner_dev_procedure', after=after, created=created,
                backup_sha256=backup_sha256, result='approved'))
        assignments = []
        await repo.ensure(conn, 'core_user_roles', dict(user_id=pilot, role_id=str(role['id'])), {}, assignments)
        effective = await resolver.list_effective_permissions(conn, workspace, pilot)
        if set(effective) != set(before) | {PERMISSION}:
            raise Conflict('invoice effective permissions postcondition failed')
        run_id = None
        if assignments:
            run_id = await self.audit(conn, admin, workspace, 'invoice-grant', dict(user_id=pilot,
                before=before, after=effective, permissions=[PERMISSION], created=assignments,
                backup_sha256=backup_sha256, actor_kind='explicit_local_owner_dev_procedure', result='granted'))
        return dict(changed=bool(created or assignments or not previous), run_id=run_id,
                    catalog_created=len(created), assignments_created=len(assignments), effective=effective,
                    delegation=after)
