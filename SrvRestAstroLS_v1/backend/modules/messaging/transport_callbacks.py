"""Authenticated V1 callback consumer; merges into the existing messaging ledger."""
import base64
from datetime import datetime, timezone
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from modules.db.transaction import transaction
from .domain.delivery import DeliveryEvent
from .repository import MessagingRepository
from .transport_repository import TransportRepository, canonical


class TransportCallbackReceiver:
    def __init__(self, *, trust, scope, binding):
        self.trust, self.scope, self.binding = trust, scope, binding

    async def receive(self, pool, envelope):
        if not isinstance(envelope, dict) or set(envelope) != {'payload','signature'}:
            raise ValueError('Invalid callback envelope')
        p = envelope['payload']
        required = {'version','event_id','scope','revision','outbound_intent_id','transport_attempt_id',
                    'provider_message_id','status','provider_timestamp','code','targets'}
        if not isinstance(p, dict) or set(p) != required:
            raise ValueError('Invalid callback fields')
        try:
            key = Ed25519PublicKey.from_public_bytes(base64.b64decode(self.trust['targets']['evolution']['public_key'], validate=True))
            key.verify(base64.b64decode(envelope['signature'], validate=True),
                       b'team360.transport.callback.v1\x00'+canonical(p))
        except Exception:
            raise ValueError('Invalid callback signature') from None
        targets = {s:{k:v[k] for k in ('id','epoch')} for s,v in self.trust['targets'].items()}
        if (type(p['version']) is not int or p['version'] != 1 or type(p['revision']) is not int or p['revision'] < 1
                or p['scope'] != self.scope or p['targets'] != targets
                or p['status'] not in {'sent','delivered','read','failed'}
                or not isinstance(p['event_id'], str) or not re.fullmatch('[0-9a-f]{64}', p['event_id'])
                or not isinstance(p['provider_message_id'], str) or not re.fullmatch(r'wamid\.[A-Za-z0-9+/=_-]{1,506}', p['provider_message_id'])):
            raise ValueError('Callback context mismatch')
        if p['code'] is not None and (type(p['code']) is not int or p['code'] < 0):
            raise ValueError('Invalid callback code')
        if not isinstance(p['provider_timestamp'], str) or not re.fullmatch('[0-9]{1,12}', p['provider_timestamp']):
            raise ValueError('Invalid callback timestamp')
        when = datetime.fromtimestamp(int(p['provider_timestamp']), timezone.utc)
        async with transaction(pool) as conn:
            if await TransportRepository().targets(conn) != targets:
                raise ValueError('Callback target epoch mismatch')
            # Same lock protects concurrent duplicate validation and the existing merge.
            await MessagingRepository().lock_receipt(conn, self.binding.provider_id,
                self.binding.storage_instance, p['provider_message_id'])
            if not await TransportRepository().callback_context(conn, p, self.binding):
                return 'duplicate'
            event = DeliveryEvent('evolution', self.binding.provider_instance, p['provider_message_id'], p['status'], when)
            await MessagingRepository().delivery(conn, self.binding, event)
        return 'applied'
