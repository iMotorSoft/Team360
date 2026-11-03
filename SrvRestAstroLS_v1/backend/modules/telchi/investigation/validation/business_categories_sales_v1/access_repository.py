"""Read-only Console inventory, not a grant or live authenticated session."""

from modules.console.repositories import PermissionConsoleRepository


class AccessInventoryRepository:
    async def inspect(self, conn):
        async def rows(sql, params=()):
            return await (await conn.execute(sql, params)).fetchall()

        result = {}
        result['transaction'] = await rows("SELECT current_setting('transaction_read_only') read_only")
        result['profiles'] = await rows('''SELECT p.profile_code,p.display_name,p.status,w.slug,
            (SELECT COUNT(*) FROM core_user_profiles u WHERE u.profile_id=p.id) assigned_users,
            (SELECT COUNT(*) FROM core_profile_permissions g WHERE g.profile_id=p.id) permissions
            FROM core_permission_profiles p LEFT JOIN core_workspaces w ON w.id=p.workspace_id
            WHERE w.slug='telchi_dev' OR lower(p.profile_code) LIKE '%%presiden%%'
            OR lower(p.display_name) LIKE '%%presiden%%' ORDER BY p.profile_code''')
        result['roles'] = await rows('''SELECT r.role_code,r.display_name,r.status,w.slug
            FROM core_roles r LEFT JOIN core_workspaces w ON w.id=r.workspace_id
            WHERE w.slug='telchi_dev' OR lower(r.role_code) LIKE '%%presiden%%'
            OR lower(r.display_name) LIKE '%%presiden%%' ORDER BY r.role_code''')
        pilot = await rows('''SELECT u.id,u.workspace_id FROM core_users u
            JOIN core_workspaces w ON w.id=u.workspace_id
            JOIN core_organizations o ON o.id=w.organization_id
            WHERE lower(trim(u.email))=%s AND w.slug=%s AND o.organization_code=%s''',
            ('devfull@telchiai.com', 'telchi_dev', 'telchi'))
        if len(pilot) != 1:
            raise ValueError('pilot_scope_not_verified')
        p = pilot[0]
        resolver = PermissionConsoleRepository()
        result['pilot_effective_permissions'] = await resolver.list_effective_permissions(conn, p['workspace_id'], p['id'])
        result['wrong_workspace_effective_permissions'] = await resolver.list_effective_permissions(
            conn, '00000000-0000-0000-0000-000000000000', p['id'])
        result['registered_category_capabilities'] = await rows('''SELECT c.capability_code,c.enabled
            FROM core_workspace_capabilities c JOIN core_workspaces w ON w.id=c.workspace_id
            WHERE w.slug=%s AND c.module=%s AND c.capability_code LIKE '%%category%%' ''',
            ('telchi_dev', 'telchi'))
        result['pilot_active_scoped_full_access'] = await rows('''SELECT COUNT(*) active_grants
            FROM core_module_full_access_grants g JOIN core_workspaces w ON w.id=g.workspace_id
            JOIN core_organizations o ON o.id=g.organization_id
            WHERE g.user_id=%s AND g.workspace_id=%s AND g.module=%s AND g.revoked_at_utc IS NULL
            AND w.organization_id=o.id AND w.status IN ('active','testing') AND o.status='active' ''',
            (p['id'], p['workspace_id'], 'telchi'))
        return result
