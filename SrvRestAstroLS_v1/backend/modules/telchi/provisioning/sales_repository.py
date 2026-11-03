"""Two approved DEV sales grants over existing Console RBAC and admin ledger.

No enrollment, schema changes, runtime bypass or generic permission registration.
Caller owns a SERIALIZABLE transaction and the private backup/trust checks.
"""
from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.datalake.sales_query import PERMISSIONS
from .admin_repository import AdminRepository
from .repository import Conflict, ProvisioningRepository, PERMISSION, canonical, one

AUTHORIZATION = 'TEAM360 / TELCHIAI — SALES RBAC & BUSINESS RUNTIME V1'
CATALOG = {
    'sales.latest_documents': dict(role='telchi_sales_latest_documents_reader_v1',
        display_name='Telchi active latest invoices read V1',
        description='Only sales.latest_documents.v1; whole Telchi workspace; Foundation CURRENT 1408; active OINV N by DocDate, limit 1..50; no revenue, net sales, SAP, entity filters or pagination.'),
    'sales.coverage': dict(role='telchi_sales_coverage_reader_v1',
        display_name='Telchi active invoice coverage read V1',
        description='Only sales.coverage.v1; whole Telchi workspace; Foundation CURRENT 1408; active OINV N by DocDate, first/last date and month with rows; no certified complete month, revenue, net sales, SAP or entity filters.'),
}


class SalesActivationRepository(AdminRepository):
    async def identities(self, conn):
        result = {}
        for label, email in [('global', 'admin@team360.com'), ('admin', 'admin@telchiai.com'), ('pilot', 'devfull@telchiai.com')]:
            rows = await (await conn.execute('SELECT id::text,workspace_id::text,status FROM core_users WHERE lower(trim(email))=%s', (email,))).fetchall()
            if len(rows) != 1 or rows[0]['status'] != 'active':
                raise Conflict('approved existing active identity missing/ambiguous')
            result[label] = dict(rows[0])
        workspace = await one(conn, "SELECT w.id::text,w.organization_id::text FROM core_workspaces w JOIN core_organizations o ON o.id=w.organization_id WHERE w.slug='telchi_dev' AND w.status IN ('active','testing') AND o.organization_code='telchi' AND o.status='active'")
        if not workspace or any(result[k]['workspace_id'] != workspace['id'] for k in ('admin', 'pilot')):
            raise Conflict('Telchi identity/workspace mismatch')
        await self.global_actor(conn, result['global']['id'])
        await self.delegated_actor(conn, result['admin']['id'], workspace['id'], lock=False)
        result['workspace'] = workspace
        return result

    @staticmethod
    def sales_limits():
        return dict(environment='dev', modules=['telchi'], permissions=list(PERMISSIONS.values()),
                    capabilities=[k + '.v1' for k in CATALOG], roles=[v['role'] for v in CATALOG.values()],
                    whole_workspace=True, credential_enrollment=False, free_sql=False)

    async def snapshot(self, conn):
        identities = await self.identities(conn)
        workspace = identities['workspace']['id']
        # Recoverable private snapshot, including preexisting assignments and profiles.
        queries = {
            'permissions': ("SELECT * FROM core_permissions WHERE permission_code=ANY(%s)", (list(PERMISSIONS.values()) + [PERMISSION],)),
            'roles': ('SELECT * FROM core_roles WHERE workspace_id=%s', (workspace,)),
            'role_permissions': ('SELECT rp.* FROM core_role_permissions rp JOIN core_roles r ON r.id=rp.role_id WHERE r.workspace_id=%s', (workspace,)),
            'user_roles': ('SELECT ur.* FROM core_user_roles ur JOIN core_users u ON u.id=ur.user_id WHERE u.workspace_id=%s', (workspace,)),
            'user_profiles': ('SELECT up.* FROM core_user_profiles up JOIN core_users u ON u.id=up.user_id WHERE u.workspace_id=%s', (workspace,)),
            'admin_events': ("SELECT * FROM core_events WHERE workspace_id=%s AND event_name LIKE 'telchi.admin.%%'", (workspace,)),
        }
        result = dict(target=await self.target(conn), identities=identities, records={})
        for name, (query, params) in queries.items():
            result['records'][name] = canonical(await (await conn.execute(query, params)).fetchall())
        result['effective'] = await PermissionConsoleRepository().list_effective_permissions(conn, workspace, identities['pilot']['id'])
        return result

    async def approved(self, conn, workspace, admin):
        event = await one(conn, "SELECT payload_jsonb FROM core_events WHERE workspace_id=%s AND event_name='telchi.admin.sales-authorize' ORDER BY occurred_at_utc DESC,id DESC LIMIT 1", (workspace,))
        if not event or event['payload_jsonb']['after'] != dict(limits=self.sales_limits(), admin_id=admin):
            raise Conflict('global sales entitlement/delegation missing or incompatible')

    async def activate(self, conn, *, backup_sha256, authorization):
        if authorization != AUTHORIZATION:
            raise Conflict('explicit owner sales authorization required')
        await self.guard(conn)
        identities = await self.identities(conn)
        global_id, admin, pilot = [identities[k]['id'] for k in ('global', 'admin', 'pilot')]
        workspace = identities['workspace']['id']
        repo, created = ProvisioningRepository(), []
        # Registry contract, not an invented capability catalog.
        registry = SalesCapabilities()
        for operation, spec in CATALOG.items():
            if registry.required_permission({'metric': operation}) != PERMISSIONS[operation]:
                raise Conflict('runtime catalog contract differs')
            permission = await repo.ensure(conn, 'core_permissions', dict(permission_code=PERMISSIONS[operation]),
                dict(display_name=spec['display_name'], description=spec['description'], category='business'), created)
            role = await repo.ensure(conn, 'core_roles', dict(workspace_id=workspace, role_code=spec['role']),
                dict(display_name=spec['display_name'], status='active', is_system_role=False), created)
            await repo.ensure(conn, 'core_role_permissions', dict(role_id=str(role['id']), permission_id=str(permission['id'])), {}, created)
            extra = await one(conn, 'SELECT id FROM core_role_permissions WHERE role_id=%s AND permission_id<>%s', (role['id'], permission['id']))
            if extra:
                raise Conflict('role contains out-of-catalog permissions')
        previous = await one(conn, "SELECT payload_jsonb FROM core_events WHERE workspace_id=%s AND event_name='telchi.admin.sales-authorize' ORDER BY occurred_at_utc DESC,id DESC LIMIT 1", (workspace,))
        after = dict(limits=self.sales_limits(), admin_id=admin)
        if previous and previous['payload_jsonb']['after'] != after:
            raise Conflict('existing sales delegation differs')
        if not previous or created:
            await self.audit(conn, global_id, workspace, 'sales-authorize', dict(
                authorization=authorization, actor_kind='explicit_local_owner_dev_procedure',
                before=previous['payload_jsonb']['after'] if previous else None, after=after,
                created=created, backup_sha256=backup_sha256, result='approved'))
        await self.delegated_actor(conn, admin, workspace)
        await self.approved(conn, workspace, admin)
        result = await self.grant_sales(conn, admin, workspace, pilot, backup_sha256=backup_sha256)
        return dict(changed=bool(created or result['assignments_created'] or not previous),
                    catalog_created=len(created), identities=identities, delegation=after, **result)

    async def grant_sales(self, conn, admin, workspace, pilot, *, backup_sha256=None):
        await self.delegated_actor(conn, admin, workspace)
        await self.approved(conn, workspace, admin)
        await self.user(conn, workspace, pilot)
        repo = ProvisioningRepository()
        before = await PermissionConsoleRepository().list_effective_permissions(conn, workspace, pilot)
        preserved = set(before) - {PERMISSION, *PERMISSIONS.values()}
        if preserved:
            # A previously approved increment is preserved, never granted here.
            from .monetary_repository import MonetaryActivationRepository
            from modules.telchi.datalake.sales_query import MONETARY_PERMISSION
            event = await one(conn, "SELECT payload_jsonb FROM core_events WHERE workspace_id=%s AND event_name='telchi.admin.monetary-authorize' ORDER BY occurred_at_utc DESC,id DESC LIMIT 1", (workspace,))
            expected = dict(limits=MonetaryActivationRepository.sales_limits(), admin_id=admin)
            if preserved != {MONETARY_PERMISSION} or not event or event['payload_jsonb'].get('after') != expected:
                raise Conflict('pilot unrelated grants; manual reconciliation required')
        if PERMISSION not in before:
            raise Conflict('pilot base missing; manual reconciliation required')
        assignments = []
        member = await one(conn, 'SELECT id FROM core_organization_members WHERE organization_id=%s AND user_id=%s AND status=\'active\'', ((await one(conn, 'SELECT organization_id FROM core_workspaces WHERE id=%s', (workspace,)))['organization_id'], pilot))
        if not member:
            raise Conflict('active pilot organization membership required')
        for spec in CATALOG.values():
            role = await one(conn, 'SELECT id FROM core_roles WHERE workspace_id=%s AND role_code=%s', (workspace, spec['role']))
            await repo.ensure(conn, 'core_user_roles', dict(user_id=pilot, role_id=str(role['id'])), {}, assignments)
        effective = await PermissionConsoleRepository().list_effective_permissions(conn, workspace, pilot)
        if set(effective) != {PERMISSION, *PERMISSIONS.values()} | preserved:
            raise Conflict('effective sales permissions postcondition failed')
        run_id = None
        if assignments:
            run_id = await self.audit(conn, admin, workspace, 'sales-grant', dict(user_id=pilot,
                permissions=list(PERMISSIONS.values()), before=before, after=effective,
                created=assignments, backup_sha256=backup_sha256, result='granted',
                actor_kind='explicit_local_owner_dev_procedure'))
        return dict(run_id=run_id, assignments_created=len(assignments), effective=effective)

    async def rollback_assignments(self, conn, run_id):
        """Withdraw only this run's unchanged assignments; keep catalog/base grant."""
        await self.guard(conn)
        identities = await self.identities(conn)
        workspace, admin = identities['workspace']['id'], identities['admin']['id']
        event = await one(conn, "SELECT payload_jsonb FROM core_events WHERE correlation_id=%s AND workspace_id=%s AND actor_user_id=%s AND event_name='telchi.admin.sales-grant' FOR UPDATE", (run_id, workspace, admin))
        if not event:
            raise Conflict('no matching sales assignment ledger')
        if await one(conn, "SELECT id FROM core_events WHERE event_name='telchi.admin.sales-revoke-run' AND payload_jsonb->>'run_id'=%s", (run_id,)):
            return dict(changed=False)
        for item in reversed(event['payload_jsonb']['created']):
            snapshot = item['row']
            if item['table'] != 'core_user_roles' or snapshot['user_id'] != identities['pilot']['id']:
                raise Conflict('invalid assignment ledger')
            row = await one(conn, 'SELECT * FROM core_user_roles WHERE id=%s FOR UPDATE', (snapshot['id'],))
            if canonical(row) != snapshot:
                raise Conflict('assignment changed; rollback refused')
            await conn.execute('DELETE FROM core_user_roles WHERE id=%s', (snapshot['id'],))
        effective = await PermissionConsoleRepository().list_effective_permissions(conn, workspace, identities['pilot']['id'])
        await self.audit(conn, admin, workspace, 'sales-revoke-run', dict(run_id=run_id,
            before=event['payload_jsonb']['after'], after=effective, result='revoked_created_assignments_only'))
        return dict(changed=True, effective=effective)
