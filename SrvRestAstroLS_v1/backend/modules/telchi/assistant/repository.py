"""Telchi JSON namespace in existing Messaging rows. No schema creation.

Caller holds thread lock before event lock (same order as Messaging claim).
State + execution result + prepared response commit together; outbound intent
remains Messaging-owned in its subsequent transaction, not atomically coupled.
"""
from copy import deepcopy
from psycopg.types.json import Jsonb

from .state_engine import EMPTY
from .result_references import presentation, MAX_BYTES


class ConversationRepository:
    async def controlled_transport_evidence(self, conn, binding, inbound_ids):
        """Bounded, read-only evidence for explicitly selected controlled exchanges."""
        return await (await conn.execute('''SELECT id::text,thread_id::text,direction,event_type,status,
            transport_status,provider_message_id,correlation_id,payload_jsonb,occurred_at_utc
            FROM message_events WHERE workspace_id=%s AND channel_id=%s AND provider_instance=%s
              AND (id=ANY(%s::uuid[]) OR correlation_id=ANY(%s::text[]))
            ORDER BY created_at_utc,id LIMIT 100''',
            (binding.workspace_id, binding.channel_id, binding.storage_instance, inbound_ids, inbound_ids))).fetchall()

    async def load(self, conn, context):
        c, i = context.channel, context.sender_identity
        await conn.execute("SET LOCAL lock_timeout='3s'")
        await conn.execute("SET LOCAL statement_timeout='5s'")
        thread = await (await conn.execute('''
            SELECT metadata_jsonb FROM message_threads
            WHERE id=%s AND channel_id=%s AND workspace_id=%s FOR NO KEY UPDATE
        ''', (context.conversation_id, c.channel_id, c.workspace_id))).fetchone()
        event = await (await conn.execute('''
            SELECT payload_jsonb FROM message_events
            WHERE id=%s AND thread_id=%s AND channel_id=%s AND workspace_id=%s
              AND direction='inbound' AND event_type='message' FOR UPDATE
        ''', (context.correlation_id, context.conversation_id, c.channel_id, c.workspace_id))).fetchone()
        if (thread is None or event is None
                or (event['payload_jsonb'] or {}).get('environment') != c.environment):
            raise ValueError('conversation_not_owned')
        owner = [c.environment, c.tenant_id, c.workspace_id, c.channel_id, i.user_id]
        saved = (thread['metadata_jsonb'] or {}).get('telchi_assistant_v1')
        if saved and saved['owner'] != owner:
            raise ValueError('conversation_identity_changed')
        audit = (event['payload_jsonb'] or {}).get('telchi_assistant_v1')
        if audit and audit['owner'] != owner:
            raise ValueError('turn_identity_changed')
        return dict(owner=owner, analysis_context_id=(saved.get('analysis_context_id', context.conversation_id)
                    if saved else context.conversation_id), state=deepcopy(saved['state'] if saved else EMPTY),
                    history=({k: deepcopy(saved['history'][k]) for k in saved['history_order']}
                             if saved else {}), cached=audit, conn=conn,
                    result_reference=deepcopy(saved.get('result_reference')) if saved else None,
                    result_reference_initialized=bool(saved and 'result_reference' in saved),
                    document_reference=deepcopy(saved.get('document_reference')) if saved else None,
                    reference_focus=saved.get('reference_focus', 'result') if saved else 'result',
                    monetary_comparison=deepcopy(saved.get('monetary_comparison')) if saved else None)

    async def load_result(self, conn, context, turn):
        """Fetch at most one bounded audit, never another conversation/identity.

        Legacy successful audits are usable without migration. The thread retains
        only an event pointer and selection; commercial rows stay in existing audits.
        """
        pointer = turn.get('result_reference')
        ids = ([pointer['result_id']] if pointer else [] if turn.get('result_reference_initialized')
               else list(turn['history'])[-20:])
        if not ids:
            return None
        row = await (await conn.execute('''
            SELECT id::text AS result_id,
                   CASE WHEN octet_length((payload_jsonb->'telchi_assistant_v1')::text)<=%s
                        THEN payload_jsonb->'telchi_assistant_v1' ELSE NULL END AS audit
            FROM message_events
            WHERE thread_id=%s AND channel_id=%s AND workspace_id=%s
              AND direction='inbound' AND event_type='message'
              AND id::text=ANY(%s::text[])
              AND payload_jsonb->>'environment'=%s
              AND payload_jsonb->'telchi_assistant_v1'->>'execution_status'='executed'
            ORDER BY array_position(%s::text[],id::text) DESC LIMIT 1
        ''', (MAX_BYTES, context.conversation_id, context.channel.channel_id, context.channel.workspace_id,
              ids, context.channel.environment, ids))).fetchone()
        if row is None:
            return None
        return presentation(row['audit'], row['result_id'], turn['owner'], context.conversation_id)

    async def load_category_analysis(self, conn, context, turn, state):
        """One bounded, owner-scoped prior composition; never execution authority."""
        ids = list(turn['history'])[-20:]
        if not ids:
            return None
        row = await (await conn.execute('''WITH candidate AS (
            SELECT id::text AS result_id,
                (payload_jsonb->'telchi_assistant_v1'
                    #- '{category_analysis,denominator,full_breakdown}'
                    #- '{category_analysis,denominator,rows}') AS value
            FROM message_events WHERE thread_id=%s AND channel_id=%s AND workspace_id=%s
              AND direction='inbound' AND event_type='message' AND id::text=ANY(%s::text[])
              AND payload_jsonb->>'environment'=%s
              AND payload_jsonb->'telchi_assistant_v1'->>'execution_status'='executed'
              AND payload_jsonb->'telchi_assistant_v1' ? 'category_analysis'
            ORDER BY array_position(%s::text[],id::text) DESC LIMIT 1)
            SELECT result_id, CASE WHEN octet_length(value::text)<=%s THEN value ELSE NULL END AS audit
            FROM candidate''',
            (context.conversation_id, context.channel.channel_id, context.channel.workspace_id,
             ids, context.channel.environment, ids, MAX_BYTES))).fetchone()
        audit = row['audit'] if row else None
        if (not audit or audit.get('owner') != turn['owner']
                or audit.get('business_rbac_verified') is not True
                or audit.get('confirmed_state') != state):
            return None
        return dict(result_id=row['result_id'], analysis=audit['category_analysis'])

    async def load_monetary_results(self, conn, context, turn):
        from .monetary_comparison import accredited
        ids = list(turn['history'])[-20:]
        if not ids:
            return []
        rows = await (await conn.execute('''SELECT id::text AS result_id,
            CASE WHEN octet_length((payload_jsonb->'telchi_assistant_v1')::text)<=%s
                 THEN payload_jsonb->'telchi_assistant_v1' ELSE NULL END AS audit
            FROM message_events WHERE thread_id=%s AND channel_id=%s AND workspace_id=%s
              AND direction='inbound' AND event_type='message' AND id::text=ANY(%s::text[])
              AND payload_jsonb->>'environment'=%s
            ORDER BY array_position(%s::text[],id::text) DESC LIMIT 20''',
            (MAX_BYTES, context.conversation_id, context.channel.channel_id, context.channel.workspace_id,
             ids, context.channel.environment, ids))).fetchall()
        results, periods = [], set()
        for row in rows:
            result = accredited(row['audit'], row['result_id'], turn['owner'])
            if result:
                key = (result['metric'], result.get('category'),
                       result['period']['date_from'], result['period']['date_to_exclusive'])
                if key not in periods:
                    results.append(result)
                    periods.add(key)
        return results

    async def save(self, conn, context, turn, audit):
        history = dict(turn['history'])
        history[context.correlation_id] = deepcopy(audit['confirmed_state'])
        history = dict(list(history.items())[-20:])
        pointer = deepcopy(turn.get('result_reference'))
        if audit.get('execution_status') == 'executed':
            view = presentation(audit, context.correlation_id, turn['owner'], context.conversation_id)
            pointer = dict(result_id=context.correlation_id, selected_ordinal=None) if view else None
        elif audit.get('decision') == 'SELECT_RESULT':
            pointer = deepcopy(audit['result_reference'])
        elif (audit.get('interpretation_proposed') or {}).get('intent') == 'NEW_QUERY':
            pointer = None
        document = deepcopy(turn.get('document_reference'))
        if 'document_reference' in audit:
            document = deepcopy(audit['document_reference'])
        elif audit.get('execution_status') == 'executed' or (audit.get('interpretation_proposed') or {}).get('intent') == 'NEW_QUERY':
            document = None
        focus = audit.get('reference_focus', turn.get('reference_focus', 'result'))
        if document is None:
            focus = 'result'
        saved = dict(owner=turn['owner'], analysis_context_id=audit.get('analysis_context_id', context.conversation_id),
                     state=audit['confirmed_state'], history=history,
                     history_order=list(history), result_reference=pointer, document_reference=document,
                     reference_focus=focus,
                     monetary_comparison=(deepcopy(audit['monetary_comparison_pointer'])
                         if 'monetary_comparison_pointer' in audit else
                         None if audit.get('execution_status') == 'executed'
                         or (audit.get('interpretation_proposed') or {}).get('intent') == 'NEW_QUERY'
                         else deepcopy(turn.get('monetary_comparison'))))
        await conn.execute('''UPDATE message_threads SET metadata_jsonb=metadata_jsonb || %s
            WHERE id=%s AND channel_id=%s AND workspace_id=%s''',
            (Jsonb({'telchi_assistant_v1': saved}), context.conversation_id,
             context.channel.channel_id, context.channel.workspace_id))
        await conn.execute('''UPDATE message_events SET payload_jsonb=payload_jsonb || %s
            WHERE id=%s AND thread_id=%s AND channel_id=%s AND workspace_id=%s''',
            (Jsonb({'telchi_assistant_v1': audit}), context.correlation_id, context.conversation_id,
             context.channel.channel_id, context.channel.workspace_id))
