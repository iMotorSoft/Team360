"""Incremental DEV-only monetary grant using the existing admin audit and RBAC.

Keeps the previous sales delegation intact; no new users, profiles, schemas or
module installation. Caller owns SERIALIZABLE transaction and private backup.
"""
from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.datalake.sales_query import MONETARY_PERMISSION, MONETARY_OPERATION, PERMISSIONS
from .sales_repository import SalesActivationRepository
from .repository import Conflict, ProvisioningRepository, PERMISSION, canonical, one

AUTHORIZATION = 'TEAM360 / TELCHIAI — SALES MONETARY & ENTITY RESOLUTION V1'
ROLE = 'telchi_sales_period_billed_amount_reader_v1'


class MonetaryActivationRepository(SalesActivationRepository):
    @staticmethod
    def sales_limits():
        return dict(environment='dev', modules=['telchi'], permissions=[MONETARY_PERMISSION],
                    capabilities=[MONETARY_OPERATION+'.v1'], roles=[ROLE], whole_workspace=True,
                    currency='BS', metrics=['SALES_VALID_GROSS', 'SALES_CREDIT_NOTES', 'SALES_NET'],
                    credential_enrollment=False, free_sql=False, entity_filters=False)

    async def snapshot(self, conn):
        # Explicit base-class snapshot (dynamic sales_limits is not consulted).
        result = await super().snapshot(conn)
        extra = await (await conn.execute('SELECT * FROM core_permissions WHERE permission_code=%s',
                                         (MONETARY_PERMISSION,))).fetchall()
        result['records']['permissions'].extend(canonical(extra))
        return result

    async def activate(self, conn, *, backup_sha256, authorization):
        if authorization != AUTHORIZATION:
            raise Conflict('explicit monetary owner authorization required')
        await self.guard(conn)
        identities = await self.identities(conn)
        workspace = identities['workspace']['id']
        global_id, admin, pilot = [identities[k]['id'] for k in ('global', 'admin', 'pilot')]
        # Require the existing base business access and prior module delegation.
        baseline = {PERMISSION, *PERMISSIONS.values()}
        resolver = PermissionConsoleRepository()
        before = await resolver.list_effective_permissions(conn, workspace, pilot)
        if not baseline <= set(before) or set(before)-baseline-{MONETARY_PERMISSION}:
            raise Conflict('pilot baseline missing or unrelated grants present')
        # Existing global module sales entitlement must precede this increment.
        await SalesActivationRepository().approved(conn, workspace, admin)
        member = await one(conn, "SELECT id FROM core_organization_members WHERE organization_id=%s AND user_id=%s AND status='active'",
                           (identities['workspace']['organization_id'], pilot))
        if not member:
            raise Conflict('active pilot organization membership required')
        repo, created = ProvisioningRepository(), []
        permission = await repo.ensure(conn, 'core_permissions', dict(permission_code=MONETARY_PERMISSION),
            dict(display_name='Telchi period documentary billing read V1', category='business',
                 description='Foundation CURRENT 1408; BS active OINV and ORIN DocTotal by bounded DocDate period; gross billing, credit amount and historical SALES_NET; no cash, SAP, entity filters or product allocation.'), created)
        role = await repo.ensure(conn, 'core_roles', dict(workspace_id=workspace, role_code=ROLE),
                                 dict(display_name='Telchi period documentary billing reader V1', status='active', is_system_role=False), created)
        await repo.ensure(conn, 'core_role_permissions', dict(role_id=str(role['id']), permission_id=str(permission['id'])), {}, created)
        if await one(conn, 'SELECT id FROM core_role_permissions WHERE role_id=%s AND permission_id<>%s', (role['id'], permission['id'])):
            raise Conflict('monetary role contains unrelated permissions')
        previous = await one(conn, "SELECT payload_jsonb FROM core_events WHERE workspace_id=%s AND event_name='telchi.admin.monetary-authorize' ORDER BY occurred_at_utc DESC,id DESC LIMIT 1", (workspace,))
        after = dict(limits=self.sales_limits(), admin_id=admin)
        if previous and previous['payload_jsonb']['after'] != after:
            raise Conflict('existing monetary delegation differs')
        if not previous or created:
            await self.audit(conn, global_id, workspace, 'monetary-authorize', dict(authorization=authorization,
                actor_kind='explicit_local_owner_dev_procedure', after=after,
                before=previous['payload_jsonb']['after'] if previous else None,
                created=created, backup_sha256=backup_sha256, result='approved'))
        # Delegated actor checks remain those of the original administrative policy.
        await self.delegated_actor(conn, admin, workspace)
        await self.user(conn, workspace, pilot)
        assignments = []
        await repo.ensure(conn, 'core_user_roles', dict(user_id=pilot, role_id=str(role['id'])), {}, assignments)
        effective = await resolver.list_effective_permissions(conn, workspace, pilot)
        if set(effective) != baseline | {MONETARY_PERMISSION}:
            raise Conflict('monetary effective permission postcondition failed')
        run_id = None
        if assignments:
            run_id = await self.audit(conn, admin, workspace, 'monetary-grant', dict(user_id=pilot,
                before=before, after=effective, permissions=[MONETARY_PERMISSION], created=assignments,
                backup_sha256=backup_sha256, actor_kind='explicit_local_owner_dev_procedure', result='granted'))
        return dict(changed=bool(created or assignments or not previous), run_id=run_id,
                    catalog_created=len(created), assignments_created=len(assignments),
                    identities=identities, effective=effective, delegation=after)
