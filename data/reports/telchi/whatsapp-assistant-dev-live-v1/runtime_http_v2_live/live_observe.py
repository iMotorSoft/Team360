"""Bounded read-only correlation of the WhatsApp live retest V2.

Reads only the Telchi DEV channel events for a time window, anonymizes the
thread id and never exports telephone values or provider payloads. Usage:

    uv run python <this file> --since 2026-10-12T14:17:00Z [--until ...]
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

BACKEND = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend')
sys.path.insert(0, str(BACKEND))
from dotenv import dotenv_values  # noqa: E402

OUT = Path(__file__).resolve().parent


def _anon(value):
    if value is None:
        return None
    return hashlib.sha256(str(value).encode()).hexdigest()[:12]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', required=True)
    parser.add_argument('--until', default='2100-01-01T00:00:00Z')
    parser.add_argument('--label', default='live')
    args = parser.parse_args()
    for k, v in dotenv_values(str(BACKEND.parent / '.env.backend-dev.local')).items():
        if v is not None:
            os.environ[k] = v

    import psycopg
    from psycopg.rows import dict_row
    from modules.db.settings import get_database_settings
    from modules.messaging.repository import MessagingRepository
    from modules.console.repositories import PermissionConsoleRepository

    async with await psycopg.AsyncConnection.connect(
        get_database_settings().dsn, row_factory=dict_row,
        options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=2000',
    ) as conn:
        read_only = (await (await conn.execute(
            "SELECT current_setting('transaction_read_only') AS ro, version() AS v")).fetchone())
        binding = await MessagingRepository().binding(
            conn, workspace_slug='telchi_dev', channel_alias='telchi_whatsapp_dev',
            provider='evolution', instance='team360-meta-dev')
        rows = await (await conn.execute('''
            SELECT id, thread_id, correlation_id, direction, event_type, status, transport_status,
                   occurred_at_utc, payload_jsonb
            FROM message_events WHERE channel_id=%s AND occurred_at_utc >= %s AND occurred_at_utc < %s
            ORDER BY occurred_at_utc LIMIT 500''',
            (binding.channel_id, args.since, args.until))).fetchall()
        events = []
        for row in rows:
            payload = row.pop('payload_jsonb') or {}
            audit = payload.get('telchi_assistant_v1')
            event = {k: str(v) if v is not None else None for k, v in row.items()}
            event['thread_anon'] = _anon(event.pop('thread_id', None))
            event['correlation_anon'] = _anon(event.get('correlation_id'))
            event['text'] = payload.get('text')
            event['dispatch_result'] = payload.get('dispatch_result')
            event['transport_status_payload'] = payload.get('transport_status')
            if audit:
                effective = audit.get('confirmed_state') or {}
                if effective.get('pending'):
                    effective = effective['pending'].get('proposed') or effective
                event['audit'] = {
                    'committed': audit.get('committed'),
                    'decision': audit.get('decision'),
                    'execution_status': audit.get('execution_status'),
                    'bmd_category': (audit.get('bmd') or {}).get('category'),
                    'requested_metrics': effective.get('requested_metrics'),
                    'metric': effective.get('metric'),
                    'entity': (effective.get('entity_mention') or {}).get('text'),
                    'temporal_reference': effective.get('temporal_reference'),
                    'period': effective.get('period'),
                    'response_prepared': audit.get('response_prepared'),
                    'execution_binding': {
                        'capability': (audit.get('execution_result') or {}).get('capability'),
                        'source': (audit.get('execution_result') or {}).get('source'),
                        'row_count': len((audit.get('execution_result') or {}).get('rows') or []),
                    },
                }
            events.append(event)
        threads = await (await conn.execute(
            'SELECT id FROM message_threads WHERE channel_id=%s ORDER BY created_at_utc DESC LIMIT 30',
            (binding.channel_id,))).fetchall()
        result = {
            'label': args.label, 'since': args.since, 'until': args.until,
            'read_only': read_only, 'channel_anon': _anon(binding.channel_id),
            'event_count': len(events),
            'inbound': sum(1 for e in events if e['direction'] == 'inbound'),
            'outbound': sum(1 for e in events if e['direction'] == 'outbound'),
            'events': events,
            'recent_threads_anon': [_anon(t['id']) for t in threads],
        }
    (OUT / f'live-observe-{args.label}.json').write_text(json.dumps(result, indent=2, default=str, ensure_ascii=False) + '\n')
    print(json.dumps({'event_count': result['event_count'], 'inbound': result['inbound'],
                      'outbound': result['outbound'], 'read_only': read_only['ro']}))


if __name__ == '__main__':
    asyncio.run(main())