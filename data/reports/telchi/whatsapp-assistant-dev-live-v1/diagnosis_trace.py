"""Bounded read-only reconstruction; no transport payloads/secrets exported."""
import asyncio
import json
import os
from pathlib import Path
from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row

OUT = Path(__file__).resolve().parent

async def main():
    for k, v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None:
            os.environ[k] = v
    from modules.db.settings import get_database_settings
    from modules.messaging.repository import MessagingRepository
    from modules.console.repositories import PermissionConsoleRepository
    async with await psycopg.AsyncConnection.connect(
        get_database_settings().dsn, row_factory=dict_row,
        options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=2000'
    ) as conn:
        preflight = await (await conn.execute('SELECT version(), current_setting(\'transaction_read_only\') AS read_only')).fetchone()
        binding = await MessagingRepository().binding(conn, workspace_slug='telchi_dev', channel_alias='telchi_whatsapp_dev', provider='evolution', instance='team360-meta-dev')
        rows = await (await conn.execute('''SELECT id, thread_id, correlation_id, direction, event_type, status, transport_status, occurred_at_utc, payload_jsonb
            FROM message_events WHERE channel_id=%s AND occurred_at_utc >= %s AND occurred_at_utc < %s
            ORDER BY occurred_at_utc LIMIT 100''', (binding.channel_id, '2026-10-11T23:41:00Z', '2026-10-11T23:46:00Z'))).fetchall()
        events = []
        for row in rows:
            payload = row.pop('payload_jsonb') or {}
            audit = payload.get('telchi_assistant_v1')
            event = {k: str(v) if v is not None else None for k, v in row.items()}
            if audit:
                event['audit'] = {k: audit.get(k) for k in ('previous_state', 'interpretation_proposed', 'validated_state', 'confirmed_state', 'committed', 'decision', 'execution_status', 'bmd', 'response_prepared')}
                result = audit.get('execution_result') or {}
                event['execution_binding'] = dict(capability=result.get('capability'), source=result.get('source'))
                owner = audit.get('owner')
                event['owner'] = owner
                event['current_permissions_not_historical'] = sorted(await PermissionConsoleRepository().list_effective_permissions(conn, binding.workspace_id, owner[-1])) if owner else None
            # Only explicitly whitelisted conversational fields. Never dump raw provider body.
            event['payload_keys'] = sorted(payload)
            event['text'] = payload.get('text')
            event['dispatch_result'] = payload.get('dispatch_result')
            events.append(event)
        threads = await (await conn.execute('SELECT id, metadata_jsonb FROM message_threads WHERE channel_id=%s LIMIT 20', (binding.channel_id,))).fetchall()
        durable = [{'thread_id': str(t['id']), 'assistant': (t['metadata_jsonb'] or {}).get('telchi_assistant_v1')} for t in threads]
        result = dict(preflight=preflight, channel_id=binding.channel_id, events=events, durable_threads=durable)
    (OUT / 'diagnosis-trace.json').write_text(json.dumps(result, indent=2, default=str, ensure_ascii=False)+'\n')
    print(json.dumps({'events': len(events), 'audited': sum('audit' in e for e in events), 'read_only': preflight['read_only']}))

if __name__ == '__main__':
    asyncio.run(main())
