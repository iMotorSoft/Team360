"""Trusted transport delegation queries; caller owns async transactions."""
import hashlib
import json
from psycopg.types.json import Jsonb


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


class TransportRepository:
    async def targets(self, conn):
        rows = await (await conn.execute('SELECT side,target_id::text,epoch::text FROM ot_target')).fetchall()
        return {r['side']:{'id':r['target_id'],'epoch':r['epoch']} for r in rows}

    async def binding_revision(self, conn, scope, revision, binding, *, require_active=True):
        # A closed-admission reconciler needs historical reads, not catalog
        # mutation/locking privileges. Active sending retains the inventory lock.
        query = "SELECT scope FROM ot_inventory WHERE side='team360' AND binding_id=%s"
        if require_active:
            query += ' FOR UPDATE'
        row = await (await conn.execute(query, (scope['binding_id'],))).fetchone()
        if not row or row['scope'] != scope:
            raise ValueError('Transport inventory mismatch')
        row = await (await conn.execute("SELECT * FROM ot_revision WHERE side='team360' AND binding_id=%s AND revision=%s",
                                      (scope['binding_id'], revision))).fetchone()
        if not row or row['scope'] != scope or (require_active and row['state'] != 'active'):
            raise ValueError('Transport revision inactive')
        expected = dict(workspace_id=binding.workspace_id, channel_id=binding.channel_id,
                        provider_id=binding.provider_id, instance_name=binding.provider_instance,
                        environment=binding.environment, tenant_id=binding.tenant_id,
                        module=binding.module, receiver_context=binding.receiver_context)
        if any(scope.get(k) != v for k, v in expected.items()):
            raise ValueError('Transport binding mismatch')
        return row

    async def admission(self, conn, scope, revision, identity, binding):
        row = await self.binding_revision(conn, scope, revision, binding)
        event = await (await conn.execute('''SELECT payload_jsonb FROM message_events WHERE id=%s
            AND workspace_id=%s AND channel_id=%s AND provider_instance=%s
            AND direction='outbound' AND event_type='message' ''',
            (identity.outbound_intent_id, binding.workspace_id, binding.channel_id, binding.storage_instance))).fetchone()
        if not event or event['payload_jsonb'].get('outbound_identity') != {k:v for k,v in identity.wire().items() if k != 'version'}:
            raise ValueError('Transport intent not reserved')
        delegation = {'binding_id':scope['binding_id'], 'revision':revision, 'scope_hash':hashlib.sha256(canonical(scope)).hexdigest()}
        previous = event['payload_jsonb'].get('transport_delegation')
        if previous is not None and previous != delegation:
            raise ValueError('Attempt already accredited to another revision')
        await conn.execute("UPDATE message_events SET payload_jsonb=payload_jsonb || jsonb_build_object('transport_delegation',%s::jsonb) WHERE id=%s",
                           (Jsonb(delegation), identity.outbound_intent_id))
        targets = await (await conn.execute('SELECT side,target_id::text,epoch::text FROM ot_target')).fetchall()
        return row, {r['side']: {'id':r['target_id'], 'epoch':r['epoch']} for r in targets}

    async def callback_context(self, conn, payload, binding):
        scope = payload['scope']
        row = await (await conn.execute("SELECT scope FROM ot_revision WHERE side='team360' AND binding_id=%s AND revision=%s",
                                      (scope['binding_id'], payload['revision']))).fetchone()
        if not row or row['scope'] != scope:
            raise ValueError('Historical transport revision mismatch')
        identity = await (await conn.execute('''SELECT provider_message_id,payload_jsonb FROM message_events
            WHERE id=%s AND workspace_id=%s AND channel_id=%s AND provider_instance=%s
                AND direction='outbound' AND event_type='message' ''',
            (payload['outbound_intent_id'], binding.workspace_id, binding.channel_id, binding.storage_instance))).fetchone()
        if not identity:
            raise ValueError('Callback intent not found')
        document = identity['payload_jsonb']
        attempts = [{'identity': document.get('outbound_identity', {}), 'egress':document.get('egress'),
                     'transport_delegation':document.get('transport_delegation')}, *document.get('attempt_history', [])]
        expected = {'binding_id':scope['binding_id'], 'revision':payload['revision'],
                    'scope_hash':hashlib.sha256(canonical(scope)).hexdigest()}
        matches = [a for a in attempts if a.get('identity', {}).get('transport_attempt_id') == payload['transport_attempt_id']]
        if len(matches) != 1:
            raise ValueError('Callback attempt not found')
        stored = matches[0]['identity']
        known_meta = (matches[0].get('egress') or {}).get('provider_message_id')
        if known_meta is not None and known_meta != payload['provider_message_id']:
            raise ValueError('Callback Meta identity mismatch')
        if (stored.get('outbound_intent_id') != payload['outbound_intent_id'] or stored.get('workspace_id') != scope['workspace_id'] or stored.get('channel_id') != scope['channel_id'] or
                stored.get('provider_instance') != scope['instance_name'] or matches[0].get('transport_delegation') != expected):
            raise ValueError('Callback intent context mismatch')
        fingerprint = hashlib.sha256(canonical(payload)).hexdigest()
        old = await (await conn.execute('SELECT envelope_hash FROM ot_received_callback WHERE event_id=%s',
                                      (payload['event_id'],))).fetchone()
        if old:
            if old['envelope_hash'] != fingerprint:
                raise ValueError('Callback replay conflict')
            return False
        row = await (await conn.execute('''INSERT INTO ot_received_callback(event_id,envelope_hash,payload)
            VALUES (%s,%s,%s) ON CONFLICT(event_id) DO NOTHING RETURNING event_id''',
            (payload['event_id'], fingerprint, Jsonb(payload)))).fetchone()
        return bool(row)
