"""Bounded read of existing transport history; no send/webhook change/replay."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import re

from verify_activation import ROOT, dump


async def main():
    import httpx
    from modules.messaging.providers.evolution.config import EvolutionConfig
    config = EvolutionConfig.from_env()
    result = dict(read_only=True, limit=100, no_message_sent=True, no_webhook_changed=True)
    async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
        headers = {'apikey': config.api_key}
        try:
            response = await client.post(config.base_url + '/chat/findMessages/' + config.instance,
                                         headers=headers, json={'where': {}, 'page': 1, 'offset': 100})
            result['http_status'] = response.status_code
            if response.status_code == 200:
                messages = response.json()['messages']
                result['total'] = messages['total']
                result['history_complete_within_bound'] = messages['total'] <= 100
                result['matches'] = []
                for record in messages['records']:
                    msg = record.get('message') or {}
                    text = msg.get('conversation') or (msg.get('extendedTextMessage') or {}).get('text') or ''
                    norm = re.sub(r'\s+', ' ', text.lower()).strip().rstrip('.?!')
                    if norm not in {'ventas de mayo 2026', 'ventas de mayo de 2026'}:
                        continue
                    timestamp = record.get('messageTimestamp')
                    result['matches'].append(dict(
                        provider_id_sha256=hashlib.sha256(str(record['key']['id']).encode()).hexdigest(),
                        from_me=record['key'].get('fromMe'), timestamp=timestamp,
                        status=record.get('status'), matching_phrase=True))
            webhook = await client.get(config.base_url + '/webhook/find/' + config.instance, headers=headers)
            result['webhook_read_status'] = webhook.status_code
            if webhook.status_code == 200:
                data = webhook.json()
                data = data.get('webhook', data)
                result['current_webhook_not_historical'] = dict(enabled=data.get('enabled'),
                    events=data.get('events'), url_configured=bool(data.get('url')))
        except Exception as exc:
            result['error_type'] = type(exc).__name__
    dump('evolution_trace.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    asyncio.run(main())
