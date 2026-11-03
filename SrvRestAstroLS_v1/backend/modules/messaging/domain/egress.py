"""Durable outbound identity. Wire scope is correlation, NEVER authorization."""
from dataclasses import asdict, dataclass
from uuid import UUID
import re


@dataclass(frozen=True, slots=True)
class OutboundIdentity:
    outbound_intent_id: str
    transport_attempt_id: str
    workspace_id: str
    channel_id: str
    provider_instance: str

    def __post_init__(self):
        for key in ('outbound_intent_id', 'transport_attempt_id', 'workspace_id', 'channel_id'):
            value = getattr(self, key)
            if str(UUID(value)) != value:
                raise ValueError('Noncanonical outbound identity')
        if (not isinstance(self.provider_instance, str) or not self.provider_instance
                or len(self.provider_instance) > 256):
            raise ValueError('Invalid provider instance')

    def wire(self):
        return {'version': 1, **asdict(self)}


def validate_egress(value, identity: OutboundIdentity):
    """Allowlist evidence; reject mismatched identity and impossible conclusions.

    ACCEPTED concerns Graph acceptance, not recipient delivery. HTTP error status
    at the Evolution boundary does not negate a genuine Meta acceptance.
    """
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or any(value.get(k) != v for k, v in identity.wire().items())):
        raise ValueError('Mismatched egress identity')
    state = value.get('acceptance')
    if not isinstance(state, str) or state not in {'UNKNOWN', 'ACCEPTED', 'REJECTED'}:
        raise ValueError('Invalid acceptance')
    message_id = value.get('provider_message_id')
    if message_id is not None and (not isinstance(message_id, str)
            or not re.fullmatch(r'wamid\.[A-Za-z0-9+/=_-]{1,506}', message_id)):
        raise ValueError('Invalid Meta ID')
    if (state == 'ACCEPTED' and not message_id) or (state == 'REJECTED' and message_id):
        raise ValueError('Contradictory egress evidence')
    if value.get('automatic_retry') is not False or value.get('durable') is not True:
        raise ValueError('Missing durable execution fence')
    result = {**identity.wire(), 'acceptance': state, 'provider_message_id': message_id,
              'automatic_retry': False, 'durable': True}
    for key in ('http_status', 'graph_code', 'graph_subcode'):
        item = value.get(key)
        if item is not None:
            if type(item) is not int or item < 0 or (key == 'http_status' and not 100 <= item <= 599):
                raise ValueError('Invalid numeric diagnostic')
            result[key] = item
    # Never retain provider response, exception text, headers, numbers or body.
    return result
