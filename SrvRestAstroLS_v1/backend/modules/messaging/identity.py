"""Read-only telephone identity adapter. No enrollment or implicit verification.

Requires an operator-approved GLOBAL schema for messaging_phone_bindings;
absence/schema errors fail closed. Migration 027 is operator-applied only;
this adapter never creates the table.
"""
from modules.console.repositories import PermissionConsoleRepository
from modules.db.transaction import transaction
from .handlers import SenderIdentity, InvalidIdentityBinding


class InvalidPhoneBinding(InvalidIdentityBinding):
    pass


class PhoneIdentityRepository:
    async def validate_schema(self, conn):
        # Read-only column/relationship probe; never create or enroll identities.
        await conn.execute("""
            SELECT b.id, b.environment, b.provider, b.sender_identity,
                   b.user_id, b.tenant_id, b.workspace_id, b.verification_status,
                   b.verified_at_utc, b.verification_ref, b.revoked_at_utc,
                   b.actor_user_id, u.workspace_id
            FROM messaging_phone_bindings b JOIN core_users u ON u.id=b.user_id
            LIMIT 0
        """)

    async def resolve(self, conn, channel, sender):
        # Deliberately do not filter revoked records or inactive users away:
        # their existence must not be interpreted as anonymous/public access.
        rows = await (await conn.execute("""
            SELECT b.user_id, b.tenant_id, b.workspace_id, b.environment,
                   b.verification_status, b.verified_at_utc, b.verification_ref,
                   u.status AS user_status, u.workspace_id AS user_workspace_id
            FROM messaging_phone_bindings b
            LEFT JOIN core_users u ON u.id=b.user_id
            WHERE b.environment=%s AND b.provider=%s AND b.sender_identity=%s
              AND b.tenant_id=%s AND b.workspace_id=%s
            """, (channel.environment, channel.provider, sender,
                  channel.tenant_id, channel.workspace_id))).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise InvalidPhoneBinding('Ambiguous telephone binding')
        row = rows[0]
        if (row['verification_status'] != 'verified' or not row['verified_at_utc']
                or not row['verification_ref'] or row['user_status'] not in {'active', 'testing'}
                or str(row['user_workspace_id']) != channel.workspace_id
                or str(row['workspace_id']) != channel.workspace_id
                or str(row['tenant_id']) != channel.tenant_id
                or row['environment'] != channel.environment):
            raise InvalidPhoneBinding('Invalid telephone binding')
        permissions = await PermissionConsoleRepository().list_effective_permissions(
            conn, channel.workspace_id, str(row['user_id']))
        return SenderIdentity(str(row['user_id']), channel.tenant_id, channel.workspace_id,
                              channel.environment, frozenset(permissions))


class PostgresPhoneIdentityResolver:
    def __init__(self, pool, repository=None):
        self.pool = pool
        self.repository = repository or PhoneIdentityRepository()

    async def resolve(self, channel, sender_phone):
        async with transaction(self.pool) as conn:
            return await self.repository.resolve(conn, channel, sender_phone)
