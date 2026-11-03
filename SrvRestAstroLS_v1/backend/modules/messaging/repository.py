"""Provider-neutral PostgreSQL conversation ownership; caller owns transactions."""
from __future__ import annotations

from dataclasses import dataclass
import json
from uuid import uuid4
from psycopg.types.json import Jsonb

from .domain.delivery import DeliveryEvent
from .domain.egress import OutboundIdentity, validate_egress
from .domain.messages import InboundMessage


@dataclass(frozen=True)
class ChannelBinding:
    workspace_id: str
    channel_id: str
    provider_id: str
    provider_instance: str
    environment: str | None = None
    module: str | None = None
    tenant_id: str | None = None
    receiver_context: str | None = None
    provider: str = 'evolution'

    @property
    def storage_instance(self):
        # Preserve legacy keys; horizontal keys isolate shared-PG environments,
        # channels, deduplication, delivery locks and callback correlation.
        if self.environment is None:
            return self.provider_instance
        return 'horizontal-v1:' + json.dumps(
            [self.environment, self.provider, self.provider_id, self.provider_instance,
             self.channel_id, self.workspace_id, self.tenant_id, self.module, self.receiver_context],
            separators=(',', ':'), ensure_ascii=True)


class MessagingRepository:
    async def validate_transport_schema(self, conn) -> None:
        """Read-only capability preflight; never applies migration 026."""
        row = await (await conn.execute("""
            SELECT count(*) AS n FROM pg_indexes WHERE schemaname=current_schema()
              AND indexname IN ('uq_messaging_transport_thread','uq_messaging_transport_message',
                                'uq_messaging_transport_reply','uq_messaging_transport_status')
            """)).fetchone()
        if row['n'] != 4:
            raise ValueError('Messaging migration 026 required')

    async def binding(self, conn, *, workspace_slug: str, channel_alias: str,
                      provider: str, instance: str) -> ChannelBinding:
        row = await (await conn.execute("""
            SELECT c.workspace_id, c.id AS channel_id, c.provider_id, c.metadata_jsonb
            FROM communication_channels c
            JOIN core_workspaces w ON w.id=c.workspace_id
            JOIN communication_providers p ON p.id=c.provider_id
            WHERE w.slug=%s AND c.channel_alias=%s AND p.code=%s
              AND c.channel_type='whatsapp' AND c.status IN ('active','testing')
              AND w.status IN ('active','testing') AND p.status IN ('active','testing')
              AND c.metadata_jsonb->>'provider_instance'=%s
              AND c.metadata_jsonb->>'dev_only'='true'
            """, (workspace_slug, channel_alias, provider, instance))).fetchone()
        if not row:
            raise ValueError("DEV channel binding missing")
        metadata = row['metadata_jsonb']
        dispatcher = metadata.get('dispatcher')
        if dispatcher not in {None, 'horizontal_v1'}:
            raise ValueError('Unknown channel dispatcher')
        scope = {}
        if dispatcher == 'horizontal_v1':
            if (metadata.get('environment') != 'dev'
                    or not all(isinstance(metadata.get(k), str) and metadata[k].strip()
                               for k in ('module', 'tenant_id', 'receiver_context'))):
                raise ValueError('Incomplete horizontal DEV channel')
            scope = {k: metadata[k] for k in ('environment', 'module', 'tenant_id', 'receiver_context')}
        return ChannelBinding(*(str(row[k]) for k in ('workspace_id', 'channel_id', 'provider_id')),
                              instance, provider=provider, **scope)

    async def provision_dev_channel(self, conn, *, workspace_slug, channel_alias, provider, instance):
        """Explicit operator setup only; refuses to adopt or overwrite existing channels."""
        workspace = await (await conn.execute(
            "SELECT id FROM core_workspaces WHERE slug=%s", (workspace_slug,))).fetchone()
        if not workspace:
            raise ValueError("Existing Team360 workspace required")
        p = await (await conn.execute("""
            INSERT INTO communication_providers(code,display_name,provider_kind,status)
            VALUES (%s,%s,'whatsapp','testing') ON CONFLICT (code) DO UPDATE SET code=EXCLUDED.code
            RETURNING id
            """, (provider, provider))).fetchone()
        await conn.execute("""
            INSERT INTO communication_channels(workspace_id,provider_id,channel_type,
                channel_alias,display_name,status,metadata_jsonb)
            VALUES (%s,%s,'whatsapp',%s,'Team360 Messaging DEV','testing',%s)
            ON CONFLICT (workspace_id,channel_alias) DO NOTHING
            """, (workspace['id'], p['id'], channel_alias,
                  Jsonb({'dev_only': True, 'provider_instance': instance})))
        return await self.binding(conn, workspace_slug=workspace_slug, channel_alias=channel_alias,
                                  provider=provider, instance=instance)

    async def claim(self, conn, binding: ChannelBinding, message: InboundMessage, timings, *, durable=False):
        if durable:
            # Existing turns may be locked by a long handler. A replay needs no
            # row lock, and a new inbound must not UPDATE that conversation.
            existing = await (await conn.execute('''SELECT id FROM message_events
                WHERE channel_id=%s AND provider_instance=%s AND provider_message_id=%s
                  AND direction='inbound' AND event_type='message' ''',
                (binding.channel_id, binding.storage_instance, message.external_message_id))).fetchone()
            if existing:
                return None
            await conn.execute('''INSERT INTO message_threads
                (workspace_id,channel_id,provider_instance,contact_identity,last_message_at_utc)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                (binding.workspace_id, binding.channel_id, binding.storage_instance,
                 message.sender, message.received_at))
            thread = await (await conn.execute('''SELECT id FROM message_threads
                WHERE workspace_id=%s AND channel_id=%s AND provider_instance=%s AND contact_identity=%s''',
                (binding.workspace_id, binding.channel_id, binding.storage_instance, message.sender))).fetchone()
        else:
            thread = await (await conn.execute("""
            INSERT INTO message_threads(workspace_id,channel_id,provider_instance,contact_identity,last_message_at_utc)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (channel_id,provider_instance,contact_identity) WHERE provider_instance IS NOT NULL
            DO UPDATE SET last_message_at_utc=GREATEST(message_threads.last_message_at_utc,EXCLUDED.last_message_at_utc),
                          updated_at_utc=now()
            RETURNING id
            """, (binding.workspace_id, binding.channel_id, binding.storage_instance,
                  message.sender, message.received_at))).fetchone()
        row = await (await conn.execute("""
            INSERT INTO message_events(workspace_id,thread_id,channel_id,provider_id,provider_instance,
                provider_message_id,direction,event_type,status,transport_status,contact_identity,payload_jsonb,occurred_at_utc)
            VALUES (%s,%s,%s,%s,%s,%s,'inbound','message',%s,'received',%s,%s,%s)
            ON CONFLICT DO NOTHING RETURNING id,thread_id
            """, (binding.workspace_id, thread['id'], binding.channel_id, binding.provider_id,
                  binding.storage_instance, message.external_message_id,
                  'running' if binding.environment else 'completed', message.sender,
                  Jsonb({'text': message.text_body, 'sender': message.sender,
                         'recipients': list(message.recipients), 'channel': message.channel,
                         'provider': message.provider, 'metadata': dict(message.metadata), 'timings': timings,
                         'environment': binding.environment,
                         'processing_state': ('queued' if durable else 'execution_uncertain') if binding.environment else 'legacy',
                         **({'durable_job': {'state': 'QUEUED', 'attempts': 0}} if durable else {})}),
                  message.received_at))).fetchone()
        return None if not row else {'id': str(row['id']), 'thread_id': str(row['thread_id'])}

    async def record_sql_gate(self, conn, binding, claimed, audit):
        """Team360-only metadata; never mutate Telchi data or the workspace tenant."""
        # Same lock order as claim: thread BEFORE inbound event. Reversed order
        # deadlocks with a duplicate holding the thread while waiting on inbound.
        await conn.execute('''
            UPDATE message_threads SET metadata_jsonb=metadata_jsonb || %s WHERE id=%s AND channel_id=%s
            ''', (Jsonb({'dev_sql_tenant': audit['tenant'], 'dev_only': True}),
                  claimed['thread_id'], binding.channel_id))
        await conn.execute('''
            UPDATE message_events SET payload_jsonb=payload_jsonb || %s
            WHERE id=%s AND channel_id=%s AND provider_instance=%s
            ''', (Jsonb({'sql_gate': audit}), claimed['id'], binding.channel_id, binding.storage_instance))

    async def intent(self, conn, binding, claimed, message, text, timings):
        outbound_id = str(uuid4())
        row = await (await conn.execute("""
            INSERT INTO message_events(id,workspace_id,thread_id,channel_id,provider_id,provider_instance,
                direction,event_type,status,contact_identity,correlation_id,payload_jsonb)
            VALUES (%s,%s,%s,%s,%s,%s,'outbound','message','pending',%s,%s,%s)
            ON CONFLICT (thread_id,correlation_id) WHERE provider_instance IS NOT NULL
                AND direction='outbound' AND event_type='message' AND correlation_id IS NOT NULL
            DO UPDATE SET correlation_id=EXCLUDED.correlation_id
            RETURNING id
            """, (outbound_id, binding.workspace_id, claimed['thread_id'], binding.channel_id,
                  binding.provider_id, binding.storage_instance, message.sender, claimed['id'],
                  Jsonb({'text': text, 'timings': timings, 'environment': binding.environment,
                         'initial_result': 'dispatch_intent'})))).fetchone()
        return str(row['id'])

    async def finish(self, conn, outbound_id, *, receipt=None, error=None, timings):
        evidence = getattr(receipt if receipt else error, 'egress', None)
        if evidence is not None:
            row = await (await conn.execute(
                'SELECT payload_jsonb FROM message_events WHERE id=%s FOR UPDATE',
                (outbound_id,))).fetchone()
            context = row['payload_jsonb']['outbound_identity']
            evidence = validate_egress(evidence, OutboundIdentity(**context))
            if receipt and (evidence['acceptance'] != 'ACCEPTED'
                            or evidence['provider_message_id'] != receipt.external_message_id):
                raise ValueError('Receipt contradicts egress')
        await conn.execute("""
            UPDATE message_events SET provider_message_id=%s,status=%s,transport_status=%s,
                payload_jsonb=payload_jsonb || %s WHERE id=%s
            """, (receipt.external_message_id if receipt else None,
                  'completed' if receipt else 'failed',
                  None if receipt else ('unknown' if error.uncertain else 'failed'),
                  Jsonb({'initial_result': 'accepted' if receipt else error.code, 'timings': timings,
                         **({'egress': evidence} if evidence is not None else {})}), outbound_id))
        if receipt:
            row = await (await conn.execute(
                'SELECT provider_id,provider_instance,provider_message_id FROM message_events WHERE id=%s',
                (outbound_id,))).fetchone()
            await self._merge_delivery(conn, row['provider_id'], row['provider_instance'], row['provider_message_id'])

    async def delivery(self, conn, binding, event: DeliveryEvent):
        # Same advisory lock as acceptance: closes the callback-before-commit race.
        await self.lock_receipt(conn, binding.provider_id, binding.storage_instance, event.external_message_id)
        await conn.execute("""
            INSERT INTO message_events(workspace_id,channel_id,provider_id,provider_instance,provider_message_id,
                direction,event_type,status,transport_status,payload_jsonb,occurred_at_utc)
            VALUES (%s,%s,%s,%s,%s,'outbound','status','completed',%s,%s,%s)
            ON CONFLICT DO NOTHING
            """, (binding.workspace_id, binding.channel_id, binding.provider_id, binding.storage_instance,
                  event.external_message_id, event.status,
                  Jsonb({'provider': event.provider, 'status': event.status, 'environment': binding.environment,
                         't_callback_ms': event.received_at.timestamp()*1000}),
                  event.received_at))
        await self._merge_delivery(conn, binding.provider_id, binding.storage_instance, event.external_message_id)

    async def lock_receipt(self, conn, provider_id, instance, message_id):
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                           (f'{provider_id}:{instance}:{message_id}',))

    async def _merge_delivery(self, conn, provider_id, instance, message_id):
        await conn.execute("""
            UPDATE message_events m SET transport_status=s.transport_status,
                payload_jsonb=m.payload_jsonb || jsonb_build_object('t6_ms',d.t6)
            FROM (SELECT transport_status FROM message_events
                  WHERE provider_id=%s AND provider_instance=%s AND provider_message_id=%s AND event_type='status'
                  ORDER BY CASE transport_status WHEN 'read' THEN 4 WHEN 'delivered' THEN 3
                      WHEN 'failed' THEN 2 WHEN 'sent' THEN 1 ELSE 0 END DESC LIMIT 1) s,
                 (SELECT min((payload_jsonb->>'t_callback_ms')::double precision) AS t6 FROM message_events
                  WHERE provider_id=%s AND provider_instance=%s AND provider_message_id=%s
                    AND event_type='status' AND transport_status='delivered') d
            WHERE m.provider_id=%s AND m.provider_instance=%s AND m.provider_message_id=%s AND m.event_type='message'
              AND m.direction='outbound'
            """, (provider_id,instance,message_id)*3)
        await conn.execute("""
            UPDATE message_events s SET thread_id=m.thread_id,correlation_id=m.correlation_id
            FROM message_events m WHERE s.provider_id=m.provider_id AND s.provider_instance=m.provider_instance
              AND s.provider_message_id=m.provider_message_id AND s.event_type='status' AND m.event_type='message'
              AND m.direction='outbound' AND m.provider_id=%s AND m.provider_instance=%s AND m.provider_message_id=%s
            """, (provider_id,instance,message_id))

    async def complete_dispatch(self, conn, binding, claimed, result):
        await conn.execute("""
            UPDATE message_events SET status='completed', payload_jsonb=payload_jsonb || %s
            WHERE id=%s AND channel_id=%s AND provider_instance=%s
            """, (Jsonb({'processing_state': 'result_persisted',
                         'dispatch_result': {'text': result.text, 'classification': result.classification,
                                             'correlation_id': result.correlation_id}}),
                  claimed['id'], binding.channel_id, binding.storage_instance))

    async def recoverable_intent(self, conn, binding, message):
        # A duplicate may resume delivery, NEVER dispatch a handler again.
        return await (await conn.execute("""
            SELECT o.id, o.payload_jsonb, o.status, o.transport_status, o.contact_identity
            FROM message_events i JOIN message_events o ON o.correlation_id=i.id::text
                AND o.thread_id=i.thread_id AND o.channel_id=i.channel_id
                AND o.provider_instance=i.provider_instance
            WHERE i.channel_id=%s AND i.provider_instance=%s AND i.direction='inbound'
                AND i.event_type='message' AND i.provider_message_id=%s
                AND o.direction='outbound' AND o.event_type='message'
            """, (binding.channel_id, binding.storage_instance, message.external_message_id))).fetchone()

    async def begin_send(self, conn, binding, outbound_id, *, retry=False):
        # A reserved attempt is committed BEFORE I/O. A crash even before the
        # call is conservatively UNKNOWN, never permission to auto-retry.
        identity = OutboundIdentity(str(outbound_id), str(uuid4()), str(binding.workspace_id),
                                    str(binding.channel_id), binding.provider_instance)
        row = await (await conn.execute("""
            UPDATE message_events SET status='pending', transport_status='unknown',
                payload_jsonb=(payload_jsonb - 'egress' - 'transport_delegation') || jsonb_build_object(
                    'initial_result','sending', 'outbound_identity',%s::jsonb,
                    'attempt_history', COALESCE(payload_jsonb->'attempt_history','[]'::jsonb) ||
                        CASE WHEN payload_jsonb ? 'outbound_identity' THEN
                            jsonb_build_array(jsonb_build_object('identity',payload_jsonb->'outbound_identity',
                                'egress',payload_jsonb->'egress') ||
                                CASE WHEN payload_jsonb ? 'transport_delegation' THEN
                                    jsonb_build_object('transport_delegation',payload_jsonb->'transport_delegation')
                                ELSE '{}'::jsonb END) ELSE '[]'::jsonb END)
            WHERE id=%s AND workspace_id=%s AND channel_id=%s AND provider_instance=%s
              AND direction='outbound' AND event_type='message'
              AND ((status='pending' AND payload_jsonb->>'initial_result'='dispatch_intent')
                   OR (%s AND status='failed' AND transport_status='failed'))
            RETURNING id
            """, (Jsonb({k: v for k, v in identity.wire().items() if k != 'version'}),
                  outbound_id, binding.workspace_id, binding.channel_id, binding.storage_instance, retry))).fetchone()
        return row is not None

    async def send_identity(self, conn, binding, outbound_id):
        row = await (await conn.execute('''
            SELECT payload_jsonb->'outbound_identity' AS identity FROM message_events
            WHERE id=%s AND workspace_id=%s AND channel_id=%s AND provider_instance=%s
                AND direction='outbound' AND event_type='message'
            ''', (outbound_id, binding.workspace_id, binding.channel_id,
                  binding.storage_instance))).fetchone()
        if not row or not row['identity']:
            raise ValueError('Outbound execution fence missing')
        return OutboundIdentity(**row['identity'])

    async def evidence(self, conn, binding):
        return await (await conn.execute("""
            SELECT id,thread_id,direction,event_type,status,transport_status,provider_message_id,
                   correlation_id,payload_jsonb,occurred_at_utc
            FROM message_events WHERE channel_id=%s AND provider_instance=%s ORDER BY created_at_utc,id
            """, (binding.channel_id,binding.storage_instance))).fetchall()
