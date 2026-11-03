"""Idempotent DEV catalog increment; no assignments, resolver or FULL_ACCESS changes."""
import json

from .category_repository import CategoryRegistrationRepository, SECURITY_TABLES, TARGET, WORKSPACE, ORGANIZATION, PILOT
from .repository import Conflict, ProvisioningRepository, canonical, one
from modules.telchi.datalake.product_line_amount_ranking_query import CAPABILITY, PERMISSION

AUTHORIZATION = 'TEAM360 / TELCHIAI — PRODUCT MONETARY RANKING V1'


class RankingRegistrationRepository(CategoryRegistrationRepository):
    async def activate(self, conn, *, authorization, backup_sha256):
        if authorization != AUTHORIZATION or len(backup_sha256) != 64 or any(c not in '0123456789abcdef' for c in backup_sha256):
            raise Conflict('explicit ranking owner authorization and private backup required')
        await self.guard(conn)
        if await self.target(conn) != TARGET:
            raise Conflict('unapproved DEV database identity')
        identities = await self.identities(conn)
        if (identities['workspace'] != dict(id=WORKSPACE, organization_id=ORGANIZATION)
                or identities['pilot']['id'] != PILOT):
            raise Conflict('approved Telchi DEV scope changed')
        before = await self.security_state(conn)
        records = before['records']
        active = [g for g in records['core_module_full_access_grants'] if g['workspace_id'] == WORKSPACE
                  and g['module'] == 'telchi' and g['revoked_at_utc'] is None]
        if len(active) != 1 or active[0]['user_id'] != PILOT or active[0]['organization_id'] != ORGANIZATION:
            raise Conflict('existing scoped FULL_ACCESS required; assignments cannot change')
        if any('*' in p['permission_code'] for p in records['core_permissions']):
            raise Conflict('wildcard catalog requires review')
        existing = [p for p in records['core_permissions'] if p['permission_code'] == PERMISSION]
        permission_id = existing[0]['id'] if existing else None
        for table in ('core_role_permissions', 'core_profile_permissions'):
            if any(r['permission_id'] == permission_id for r in records[table]):
                raise Conflict('preexisting explicit ranking grant requires review')
        for row in records['core_workspace_capabilities']:
            if row['capability_code'] == CAPABILITY or row['permission_id'] == permission_id:
                if (row['workspace_id'] != WORKSPACE or row['module'] != 'telchi'
                        or row['capability_code'] != CAPABILITY or row['permission_id'] != permission_id
                        or row['enabled'] is not True):
                    raise Conflict('ranking registry conflict; no implicit reactivation')
        created = []
        permission = await ProvisioningRepository().ensure(conn, 'core_permissions', dict(permission_code=PERMISSION),
            dict(display_name='Telchi product commercial line amount ranking read V1', category='business',
                description='Active BS commercial invoice line amounts by SAP product within accredited category and period; descending amount, ascending code, reconciled full universe before limit. No line VAT, credit notes, header adjustments or unit prices.'), created)
        row = await one(conn, '''SELECT * FROM core_workspace_capabilities WHERE workspace_id=%s
            AND module='telchi' AND capability_code=%s FOR UPDATE''', (WORKSPACE, CAPABILITY))
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
        expected = {u: sorted(set(codes) | ({PERMISSION} if u == PILOT else set())) for u, codes in before['effective'].items()}
        if after['effective'] != expected:
            raise Conflict('effective permissions changed outside approved increment')
        run_id = None
        if created:
            run_id = await self.audit(conn, identities['global']['id'], WORKSPACE, 'ranking-register', dict(
                authorization=authorization, actor_kind='explicit_local_owner_dev_procedure',
                organization_id=ORGANIZATION, module='telchi', capability=CAPABILITY, permission=PERMISSION,
                before=before, after=after, created=created, backup_sha256=backup_sha256,
                assignments_created=0, full_access_changed=False, result='registered'))
        return dict(changed=bool(created), run_id=run_id, created=created, before=before['effective'][PILOT],
                    effective=after['effective'][PILOT], assignments_created=0, full_access_changed=False)
