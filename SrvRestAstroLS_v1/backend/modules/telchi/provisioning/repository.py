"""Explicit Telchi seed; caller owns connection and transaction. No user creation."""
from dataclasses import dataclass
from uuid import UUID, uuid4
import json

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.assistant.handler import BusinessPolicy

PERMISSION = 'telchi.sales.source_quantity.read.v1'
CAPABILITY = 'telchi.sales_top_items.source_quantity.20260101_20260915.v1'
DESCRIPTION = ('Only ' + CAPABILITY + '; whole Telchi workspace; Foundation only; '
               'source invoice quantities, no revenue, SAP, branches, channels or other capabilities.')
TABLES = frozenset(('core_organizations', 'core_workspaces', 'core_organization_roles',
    'core_organization_members', 'core_organization_member_roles', 'core_permissions',
    'core_roles', 'core_role_permissions', 'core_user_roles', 'communication_channels'))


class Conflict(ValueError):
    pass


@dataclass(frozen=True)
class Seed:
    workspace_id: str
    organization_id: str
    stage: str = 'scaffold'
    admin_id: str | None = None
    pilot_id: str | None = None
    provider_instance: str | None = None
    receiver_context: str | None = None

    def validate(self):
        UUID(self.workspace_id)
        UUID(self.organization_id)
        if self.stage not in ('scaffold', 'grants'):
            raise Conflict('unknown stage')
        if self.stage == 'grants' and not (self.admin_id and self.pilot_id):
            raise Conflict('approved existing admin and pilot UUIDs required')
        for ident in (self.admin_id, self.pilot_id):
            if ident:
                UUID(ident)
        if bool(self.provider_instance) != bool(self.receiver_context):
            raise Conflict('instance and receiver context must both be approved')


async def one(conn, query, params=()):
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        return await cursor.fetchone()


def canonical(row):
    return json.loads(json.dumps(row, default=str))


class ProvisioningRepository:
    async def ensure(self, conn, table, key, values, ledger):
        if table not in TABLES:
            raise Conflict('unsupported entity')
        where = sql.SQL(' AND ').join(sql.SQL('{} IS NOT DISTINCT FROM %s').format(sql.Identifier(k)) for k in key)
        row = await one(conn, sql.SQL('SELECT * FROM {} WHERE {} FOR UPDATE').format(sql.Identifier(table), where), tuple(key.values()))
        if row:
            if any(canonical(row[k]) != canonical(v) for k, v in values.items()):
                raise Conflict('existing entity differs: ' + table)
            return row
        fields = dict(key, **values)
        fields.setdefault('id', str(uuid4()))
        adapted = tuple(Jsonb(v) if isinstance(v, dict) else v for v in fields.values())
        row = await one(conn, sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING *').format(
            sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, fields)),
            sql.SQL(',').join(sql.Placeholder() for _ in fields)), adapted)
        ledger.append(dict(table=table, row=canonical(row)))
        return row

    async def provision(self, conn, seed, *, approval_refs=None, actor_id=None):
        seed.validate()
        await conn.execute("SET LOCAL search_path=public,pg_catalog")
        await conn.execute("SET LOCAL lock_timeout='3s'")
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('telchi-provisioning-v1'))")
        version = await one(conn, 'SHOW server_version_num')
        if not str(version['server_version_num']).startswith('18'):
            raise Conflict('PG18 required')
        ledger = []
        org = await self.ensure(conn, 'core_organizations', {'organization_code': 'telchi'},
            dict(id=seed.organization_id, display_name='Telchi', primary_type='client', status='active'), ledger)
        # Reject equivalent organizations under a different code; do not silently duplicate.
        duplicate = await one(conn, "SELECT id FROM core_organizations WHERE lower(trim(display_name))='telchi' AND id<>%s", (org['id'],))
        if duplicate:
            raise Conflict('equivalent organization under another code; reconcile manually')
        workspace = await self.ensure(conn, 'core_workspaces', {'slug': 'telchi_dev'},
            dict(id=seed.workspace_id, display_name='Telchi DEV', organization_id=str(org['id']), status='testing'), ledger)
        duplicate = await one(conn, 'SELECT id FROM core_workspaces WHERE organization_id=%s AND id<>%s', (org['id'], workspace['id']))
        if duplicate:
            raise Conflict('existing organization workspace; approve reuse instead of duplication')
        if seed.stage == 'grants':
            # Never move a user from a different workspace, revive it or duplicate it.
            for ident in set((seed.admin_id, seed.pilot_id)):
                user = await one(conn, 'SELECT * FROM core_users WHERE id=%s FOR UPDATE', (ident,))
                if not user or str(user['workspace_id']) != seed.workspace_id or user['status'] != 'active':
                    raise Conflict('existing active human identity must belong to Telchi workspace')
            await self.ensure(conn, 'core_organization_roles',
                dict(organization_id=str(org['id']), role_code='client'), dict(status='active'), ledger)
            members = {}
            for ident in set((seed.admin_id, seed.pilot_id)):
                members[ident] = await self.ensure(conn, 'core_organization_members',
                    dict(organization_id=str(org['id']), user_id=ident), dict(status='active'), ledger)
            await self.ensure(conn, 'core_organization_member_roles',
                dict(organization_member_id=str(members[seed.admin_id]['id']), role_code='organization_admin'),
                dict(status='active'), ledger)
            permission = await self.ensure(conn, 'core_permissions', {'permission_code': PERMISSION},
                dict(display_name='Telchi source quantity read V1', description=DESCRIPTION, category='business'), ledger)
            role = await self.ensure(conn, 'core_roles', dict(workspace_id=seed.workspace_id, role_code='telchi_source_quantity_reader_v1'),
                dict(display_name='Telchi source quantity reader V1', status='active', is_system_role=False), ledger)
            await self.ensure(conn, 'core_role_permissions', dict(role_id=str(role['id']), permission_id=str(permission['id'])), {}, ledger)
            extra = await one(conn, 'SELECT id FROM core_role_permissions WHERE role_id=%s AND permission_id<>%s', (role['id'], permission['id']))
            if extra:
                raise Conflict('commercial role has unrelated permissions')
            await self.ensure(conn, 'core_user_roles', dict(user_id=seed.pilot_id, role_id=str(role['id'])), {}, ledger)
            effective = await PermissionConsoleRepository().list_effective_permissions(conn, seed.workspace_id, seed.pilot_id)
            if PERMISSION not in effective:
                raise Conflict('effective commercial grant missing')
        if seed.provider_instance:
            provider = await one(conn, "SELECT * FROM communication_providers WHERE code='evolution'")
            if not provider or provider['status'] not in ('active', 'testing'):
                raise Conflict('existing Evolution provider required; no transport changes')
            await self.ensure(conn, 'communication_channels', dict(workspace_id=seed.workspace_id, channel_alias='telchi_whatsapp_dev'),
                dict(provider_id=str(provider['id']), channel_type='whatsapp', display_name='Telchi WhatsApp DEV', status='testing',
                     metadata_jsonb=dict(dev_only=True, provider_instance=seed.provider_instance,
                         dispatcher='horizontal_v1', environment='dev', module='telchi', tenant_id='telchi',
                         receiver_context=seed.receiver_context)), ledger)
        run_id = str(uuid4())
        # Audit retained independently of deletable scaffold. No telephone or secrets.
        if ledger:
            await conn.execute("INSERT INTO core_events(actor_user_id,event_name,entity_type,correlation_id,payload_jsonb) VALUES (%s,'telchi.provisioning.created','telchi_provisioning',%s,%s)",
                (actor_id or seed.admin_id, run_id, Jsonb(dict(stage=seed.stage, created=ledger, approval_refs=approval_refs or {}))))
        return dict(run_id=run_id, created=ledger, workspace_id=seed.workspace_id, organization_id=seed.organization_id,
                    module_enabled=False, capability=CAPABILITY, permission=PERMISSION)

    async def rollback(self, conn, run_id):
        """Only audited inserted rows; changed rows or any surviving FK abort atomically."""
        await conn.execute("SET LOCAL search_path=public,pg_catalog")
        await conn.execute("SET LOCAL lock_timeout='3s'")
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('telchi-provisioning-v1'))")
        event = await one(conn, "SELECT payload_jsonb FROM core_events WHERE correlation_id=%s AND event_name='telchi.provisioning.created' FOR UPDATE", (run_id,))
        if not event:
            raise Conflict('no creation ledger')
        if await one(conn, "SELECT id FROM core_events WHERE correlation_id=%s AND event_name='telchi.provisioning.rolled_back'", (run_id,)):
            return
        for item in reversed(event['payload_jsonb']['created']):
            table, snapshot = item['table'], item['row']
            if table not in TABLES:
                raise Conflict('invalid ledger')
            row = await one(conn, sql.SQL('SELECT * FROM {} WHERE id=%s FOR UPDATE').format(sql.Identifier(table)), (snapshot['id'],))
            if canonical(row) != snapshot:
                raise Conflict('created row changed; manual revocation required')
            # Organizational role code has no physical FK; guard its logical consumers too.
            if table == 'core_organization_roles':
                logical = await one(conn, 'SELECT r.id FROM core_organization_member_roles r JOIN core_organization_members m ON m.id=r.organization_member_id WHERE m.organization_id=%s AND r.role_code=%s LIMIT 1', (snapshot['organization_id'], snapshot['role_code']))
                if logical:
                    raise Conflict('surviving logical role dependency; rollback refused')
            # Includes CASCADE and SET NULL: do not let DELETE mutate unrelated rows.
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""SELECT ns.nspname,cl.relname,a.attname,cardinality(c.conkey) AS n
                    FROM pg_constraint c JOIN pg_class cl ON cl.oid=c.conrelid
                    JOIN pg_namespace ns ON ns.oid=cl.relnamespace
                    JOIN pg_attribute a ON a.attrelid=cl.oid AND a.attnum=c.conkey[1]
                    WHERE c.contype='f' AND c.confrelid=%s::regclass""", (table,))
                refs = await cur.fetchall()
            for ref in refs:
                if ref['n'] != 1:
                    raise Conflict('composite dependency requires manual review')
                dependent = await one(conn, sql.SQL('SELECT 1 FROM {}.{} WHERE {}=%s LIMIT 1').format(
                    sql.Identifier(ref['nspname']), sql.Identifier(ref['relname']), sql.Identifier(ref['attname'])), (snapshot['id'],))
                if dependent:
                    raise Conflict('surviving dependency; rollback refused')
            await conn.execute(sql.SQL('DELETE FROM {} WHERE id=%s').format(sql.Identifier(table)), (snapshot['id'],))
        await conn.execute("INSERT INTO core_events(event_name,entity_type,correlation_id,payload_jsonb) VALUES ('telchi.provisioning.rolled_back','telchi_provisioning',%s,'{}')", (run_id,))


def runtime_policy(seed, *, module_enable_approved=False, whole_workspace_approved=False):
    """Explicit existing handler contract; never enables a module from seed success."""
    seed.validate()
    if (module_enable_approved or whole_workspace_approved) and seed.stage != 'grants':
        raise Conflict('grant-stage identity required for runtime enablement')
    return BusinessPolicy(tenant_id='telchi', workspace_id=seed.workspace_id, permission=PERMISSION,
        module_enabled=module_enable_approved, whole_workspace_scope_verified=whole_workspace_approved)
