"""Operator procedure after 027, verified consent and destination approval. No enrollment."""
from modules.console.repositories import PermissionConsoleRepository
from modules.messaging.identity import PhoneIdentityRepository
from .repository import Conflict, PERMISSION, one


async def bind_verified_dev_phone(conn, *, workspace_id, user_id, actor_user_id,
                                  sender_identity, verification_ref, consent_verified=False):
    """Caller MUST hold approved DEV transaction; proof validated out of band, not by number."""
    if not consent_verified or not verification_ref or not verification_ref.strip():
        raise Conflict('external consent and identity proof required')
    await PhoneIdentityRepository().validate_schema(conn)
    actor = await one(conn, """SELECT m.id FROM core_organization_members m
        JOIN core_organization_member_roles r ON r.organization_member_id=m.id
        JOIN core_organizations o ON o.id=m.organization_id
        JOIN core_workspaces w ON w.organization_id=o.id
        JOIN core_users u ON u.id=m.user_id
        WHERE w.id=%s AND o.organization_code='telchi' AND o.status='active'
        AND m.user_id=%s AND m.status='active' AND r.role_code='organization_admin' AND r.status='active'
        AND u.workspace_id=w.id AND u.status='active'""", (workspace_id, actor_user_id))
    member = await one(conn, """SELECT m.id FROM core_organization_members m
        JOIN core_workspaces w ON w.organization_id=m.organization_id
        WHERE w.id=%s AND m.user_id=%s AND m.status='active'""", (workspace_id, user_id))
    if not actor or not member:
        raise Conflict('approved Telchi admin/member required')
    if PERMISSION not in await PermissionConsoleRepository().list_effective_permissions(conn, workspace_id, user_id):
        raise Conflict('pilot lacks commercial permission')
    # Global DEV sender advisory lock prevents concurrent ambiguous bindings from this procedure.
    await conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('telchi-phone-dev:' + sender_identity,))
    async with conn.cursor() as cur:
        await cur.execute("SELECT id,user_id::text,workspace_id::text,tenant_id,verification_status,verification_ref FROM messaging_phone_bindings WHERE environment='dev' AND provider='evolution' AND sender_identity=%s FOR UPDATE", (sender_identity,))
        rows = await cur.fetchall()
    # Cursor factory inherited from caller; use explicit dict helper for stable results.
    if rows:
        existing = await one(conn, "SELECT * FROM messaging_phone_bindings WHERE environment='dev' AND provider='evolution' AND sender_identity=%s", (sender_identity,))
        if (len(rows) != 1 or str(existing['user_id']) != user_id or str(existing['workspace_id']) != workspace_id
                or existing['tenant_id'] != 'telchi' or existing['verification_status'] != 'verified'
                or existing['verification_ref'] != verification_ref):
            raise Conflict('ambiguous, revoked or differently verified binding; manual review')
        return str(existing['id'])
    row = await one(conn, """INSERT INTO messaging_phone_bindings(environment,provider,sender_identity,
        tenant_id,workspace_id,user_id,verification_status,verified_at_utc,verification_ref,actor_user_id)
        VALUES ('dev','evolution',%s,'telchi',%s,%s,'verified',now(),%s,%s) RETURNING id""",
        (sender_identity, workspace_id, user_id, verification_ref, actor_user_id))
    return str(row['id'])
