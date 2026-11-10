"""Minimal research recovery in existing core_events; no schema or queue.

DurableWorker/thread transaction supplies the execution fence. Every access is
scoped to the authenticated owner; correlation is the original inbox UUID.
"""
from uuid import UUID, uuid5

from psycopg.types.json import Jsonb

from .exploratory_sql.validator import canonical


class ResearchRecoveryRepository:
    def key(self, context):
        return str(uuid5(UUID('90572c7d-161c-40ab-a3d7-4fc7614b9685'),
                         str(context.correlation_id)))

    async def load(self, conn, scope, context):
        row = await (await conn.execute('''SELECT payload_jsonb FROM core_events
            WHERE id=%s AND workspace_id=%s AND actor_user_id=%s
              AND event_name='telchi.research.recovery' AND correlation_id=%s''',
            (self.key(context), scope.workspace, scope.user_id,
             str(context.correlation_id)))).fetchone()
        return row['payload_jsonb'] if row else None

    async def previous(self, conn, scope, context):
        row = await (await conn.execute('''SELECT payload_jsonb FROM core_events
            WHERE workspace_id=%s AND actor_user_id=%s
              AND event_name='telchi.research.recovery'
              AND payload_jsonb->>'conversation_id'=%s
              AND payload_jsonb->>'channel_id'=%s
              AND payload_jsonb->>'state'='COMPLETED' AND id<>%s
            ORDER BY created_at_utc DESC,id DESC LIMIT 1''',
            (scope.workspace, scope.user_id, str(context.conversation_id),
             str(context.channel.channel_id), self.key(context)))).fetchone()
        return row['payload_jsonb'] if row else None

    async def for_analysis(self, conn, scope, context, analysis_context_id):
        """Only research actually committed to this authenticated analysis."""
        row = await (await conn.execute('''SELECT r.payload_jsonb, m.id::text AS result_id
            FROM core_events r JOIN message_events m ON m.id::text=r.correlation_id
            WHERE r.workspace_id=%s AND r.actor_user_id=%s
              AND r.event_name='telchi.research.recovery'
              AND r.payload_jsonb->>'state'='COMPLETED'
              AND r.payload_jsonb->>'conversation_id'=%s
              AND r.payload_jsonb->>'channel_id'=%s
              AND m.thread_id=%s AND m.channel_id=%s AND m.workspace_id=%s
              AND m.payload_jsonb->'telchi_assistant_v1'->>'analysis_context_id'=%s
              AND m.payload_jsonb->'telchi_assistant_v1'->>'decision'='RESEARCH'
            ORDER BY m.created_at_utc DESC,m.id DESC LIMIT 1''',
            (scope.workspace, scope.user_id, str(context.conversation_id),
             str(context.channel.channel_id), context.conversation_id,
             context.channel.channel_id, scope.workspace, str(analysis_context_id)))).fetchone()
        return dict(row['payload_jsonb'], result_id=row['result_id']) if row else None

    async def save(self, conn, scope, context, value):
        cursor = await conn.execute('''INSERT INTO core_events(id,workspace_id,actor_user_id,
            event_name,entity_type,correlation_id,payload_jsonb)
            VALUES(%s,%s,%s,'telchi.research.recovery','telchi_research',%s,%s)
            ON CONFLICT(id) DO UPDATE SET payload_jsonb=EXCLUDED.payload_jsonb
            WHERE core_events.workspace_id=EXCLUDED.workspace_id
              AND core_events.actor_user_id=EXCLUDED.actor_user_id
              AND core_events.event_name=EXCLUDED.event_name
              AND core_events.correlation_id=EXCLUDED.correlation_id''',
            (self.key(context), scope.workspace, scope.user_id,
             str(context.correlation_id), Jsonb(value, dumps=canonical)))
        if cursor.rowcount != 1:
            raise ValueError('recovery_owner_mismatch')
