"""Console credential SQL; caller owns connections and transaction boundaries."""
import os

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class ConsoleLoginRepository:
    async def target(self, conn):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT current_database() AS database, (pg_control_system()).system_identifier::text AS system_identifier")
            return dict(await cur.fetchone())

    async def runtime_role(self, conn):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""SELECT current_user AS name,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,
                EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE c.relowner=r.oid AND n.nspname='public') AS owns_public_tables,
                EXISTS(SELECT 1 FROM pg_roles p WHERE p.oid<>r.oid
                    AND (p.rolsuper OR p.rolbypassrls OR p.rolcreaterole OR p.rolcreatedb)
                    AND pg_has_role(r.oid,p.oid,'MEMBER')) AS member_of_privileged_roles
                FROM pg_roles r WHERE rolname=current_user""")
            return dict(await cur.fetchone())

    async def actor(self, conn, user_id, workspace_id):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""SELECT u.id::text AS user_id,u.workspace_id::text AS workspace_id
                FROM core_users u JOIN core_workspaces w ON w.id=u.workspace_id
                JOIN core_organizations o ON o.id=w.organization_id
                WHERE u.id=%s AND u.workspace_id=%s AND u.status='active'
                AND w.status IN ('active','testing') AND o.status='active'""", (user_id,workspace_id))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def credential(self, conn, workspace_slug, email):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""SELECT u.id::text AS user_id,u.workspace_id::text AS workspace_id,
                p.password_hash,p.credential_version,p.disabled
                FROM core_users u JOIN core_workspaces w ON w.id=u.workspace_id
                JOIN core_organizations o ON o.id=w.organization_id
                JOIN console_password_credentials p ON p.user_id=u.id
                WHERE w.slug=%s AND lower(btrim(u.email))=%s AND u.status='active'
                AND w.status IN ('active','testing') AND o.status='active'""", (workspace_slug,email))
            values = await cur.fetchall()
            return dict(values[0]) if len(values) == 1 else None

    async def throttle(self, conn, key):
        await conn.execute("INSERT INTO console_login_attempts(account_key) VALUES(%s) ON CONFLICT DO NOTHING", (key,))
        # Serialize even concurrent invalid attempts before doing the expensive KDF.
        await conn.execute('SELECT account_key FROM console_login_attempts WHERE account_key=%s FOR UPDATE', (key,))
        await conn.execute("""UPDATE console_login_attempts SET attempts=0,window_started_at_utc=clock_timestamp()
            WHERE account_key=%s AND window_started_at_utc < clock_timestamp()-interval '15 minutes'""", (key,))
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute('SELECT attempts FROM console_login_attempts WHERE account_key=%s', (key,))
            return (await cur.fetchone())['attempts'] < 5

    async def failed(self, conn, key):
        await conn.execute('UPDATE console_login_attempts SET attempts=attempts+1 WHERE account_key=%s', (key,))

    async def succeeded(self, conn, key):
        await conn.execute('UPDATE console_login_attempts SET attempts=0,window_started_at_utc=clock_timestamp() WHERE account_key=%s', (key,))

    async def enroll(self, conn, user_id, encoded):
        await conn.execute("""INSERT INTO console_password_credentials(user_id,password_hash) VALUES(%s,%s)
            ON CONFLICT(user_id) DO UPDATE SET password_hash=EXCLUDED.password_hash,
            credential_version=console_password_credentials.credential_version+1,
            disabled=false,updated_at_utc=now()""", (user_id,encoded))

    async def session_active(self, conn, user_id, workspace_id, version):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""SELECT p.user_id FROM console_password_credentials p
                JOIN core_users u ON u.id=p.user_id JOIN core_workspaces w ON w.id=u.workspace_id
                JOIN core_organizations o ON o.id=w.organization_id
                WHERE p.user_id=%s AND u.workspace_id=%s AND p.credential_version=%s
                AND NOT p.disabled AND u.status='active' AND w.status IN ('active','testing') AND o.status='active'""",
                (user_id,workspace_id,version))
            return bool(await cur.fetchone())

    async def audit(self, conn, user_id, workspace_id, operation):
        payload = {'method':'password'}
        actor = user_id
        if operation == 'enroll':
            # Enrollment operator is the authenticated OS owner, not the target person.
            actor = None
            payload = {'method':'local_owner_enrollment','operator_uid':os.getuid(),'subject_user_id':user_id}
        await conn.execute("""INSERT INTO core_events(workspace_id,actor_user_id,event_name,entity_type,payload_jsonb)
            VALUES(%s,%s,%s,'console_identity',%s)""",
            (workspace_id,actor,'console.auth.'+operation,Jsonb(payload)))
