"""Durable inbox in Messaging rows; no parallel queue or schema installation."""
from psycopg.types.json import Jsonb


class DurableInboxRepository:
    async def find_id(self, conn, binding, external_message_id):
        row = await (await conn.execute('''SELECT id::text FROM message_events
            WHERE workspace_id=%s AND channel_id=%s AND provider_instance=%s
              AND provider_message_id=%s AND direction='inbound' AND event_type='message'
              AND payload_jsonb ? 'durable_job' ''',
            (binding.workspace_id, binding.channel_id, binding.storage_instance, external_message_id))).fetchone()
        return row['id'] if row else None

    async def candidates(self, conn, binding):
        # The oldest nonterminal turn fences subsequent turns of the same thread.
        return await (await conn.execute('''WITH oldest AS (SELECT DISTINCT ON (thread_id)
            id::text, thread_id::text, payload_jsonb, created_at_utc FROM message_events
            WHERE workspace_id=%s AND channel_id=%s AND provider_instance=%s
              AND direction='inbound' AND event_type='message'
              AND payload_jsonb ? 'durable_job'
              AND payload_jsonb->'durable_job'->>'state' NOT IN
                  ('OUTBOUND_ACCEPTED','FAILED_FINAL','CANCELED')
            ORDER BY thread_id, created_at_utc, id)
            SELECT id,thread_id FROM oldest WHERE
                COALESCE((payload_jsonb->'durable_job'->>'next_attempt_at')::timestamptz,
                         '-infinity'::timestamptz)<=clock_timestamp()
            ORDER BY created_at_utc,id LIMIT 16''',
            (binding.workspace_id, binding.channel_id, binding.storage_instance))).fetchall()

    async def lock(self, conn, binding, thread_id):
        row = await (await conn.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS locked',
            ('messaging-durable:' + binding.storage_instance + ':' + thread_id,))).fetchone()
        return row['locked']

    async def load(self, conn, binding, event_id):
        return await (await conn.execute('''SELECT id::text,thread_id::text,provider_message_id,
            payload_jsonb,occurred_at_utc FROM message_events
            WHERE id=%s AND workspace_id=%s AND channel_id=%s AND provider_instance=%s
              AND direction='inbound' AND event_type='message' ''',
            (event_id, binding.workspace_id, binding.channel_id, binding.storage_instance))).fetchone()

    async def state(self, conn, binding, event_id, state, *, attempt=False, error=None):
        await conn.execute('''UPDATE message_events SET payload_jsonb=jsonb_set(payload_jsonb,
            '{durable_job}', COALESCE(payload_jsonb->'durable_job','{}'::jsonb) ||
            jsonb_build_object('state',%s::text,'updated_at',clock_timestamp(),
                'attempts',COALESCE((payload_jsonb->'durable_job'->>'attempts')::int,0)+%s,
                'error',%s::text, 'next_attempt_at',
                CASE WHEN %s::text='FAILED_RETRYABLE' THEN clock_timestamp()+interval '30 seconds' ELSE NULL END,
                'transitions',
                COALESCE(payload_jsonb->'durable_job'->'transitions','[]'::jsonb) ||
                    jsonb_build_array(jsonb_build_object('state',%s::text,'at',clock_timestamp()))))
                WHERE id=%s AND workspace_id=%s AND channel_id=%s
                AND provider_instance=%s''',
            (state, int(attempt), error, state, state, event_id, binding.workspace_id,
             binding.channel_id, binding.storage_instance))

    async def cancel_outbound(self, conn, binding, outbound_id):
        # Never change an uncertain/accepted attempt into permission to resend.
        await conn.execute('''UPDATE message_events SET status='failed',
            payload_jsonb=payload_jsonb || %s WHERE id=%s AND workspace_id=%s
              AND channel_id=%s AND provider_instance=%s
              AND payload_jsonb->>'initial_result'='dispatch_intent' ''',
            (Jsonb({'initial_result': 'authorization_revoked'}), outbound_id,
             binding.workspace_id, binding.channel_id, binding.storage_instance))
