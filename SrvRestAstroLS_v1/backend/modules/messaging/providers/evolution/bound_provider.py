"""Lab candidate: binding-credential adapter, never a legacy fallback."""
import base64
import hashlib
import re
import time

import httpx

from modules.db.transaction import transaction
from modules.messaging.domain.delivery import MessagingSendError
from modules.messaging.domain.egress import validate_egress
from modules.messaging.domain.messages import OutboundMessageReceipt
from modules.messaging.transport_repository import TransportRepository, canonical
from modules.messaging.transport_profile import trust_profile, credential_verifier


class BoundEvolutionProvider:
    def __init__(self, config, *, scope, revision, trust, signer, transport=None, admission_check=None):
        self.config, self.scope, self.revision = config, scope, revision
        self.trust, self.signer, self.transport = trust, signer, transport
        self.admission_check = admission_check
        self.profile = trust_profile(trust)
        if scope['environment'] != self.profile:
            raise ValueError('Transport scope/profile mismatch')
        self.verifier = credential_verifier(config.api_key, self.profile)

    async def check_transport_binding(self, conn, binding, *, require_active=True):
        row = await TransportRepository().binding_revision(conn, self.scope, self.revision, binding, require_active=require_active)
        targets = await TransportRepository().targets(conn)
        expected = {s:{k:v[k] for k in ('id','epoch')} for s,v in self.trust['targets'].items()}
        verifier = self.verifier
        if (targets != expected or row['credential_hash'] != verifier or
                row['prepared_receipt'].get('payload', {}).get('target') != expected['team360']):
            raise ValueError('Transport accreditation mismatch')

    async def prepare_transport(self, *, pool, binding, identity, destination, text):
        if self.admission_check:
            self.admission_check()
        async with transaction(pool) as conn:
            row, targets = await TransportRepository().admission(conn, self.scope, self.revision, identity, binding)
            expected_targets = {s:{k:v[k] for k in ('id','epoch')} for s,v in self.trust['targets'].items()}
            verifier = self.verifier
            if (targets != expected_targets or row['credential_hash'] != verifier or
                    row['prepared_receipt'].get('payload', {}).get('target') != expected_targets['team360']):
                raise ValueError('Transport accreditation mismatch')
            now = int(time.time())
            payload = dict(version=1, scope=self.scope, revision=self.revision,
                activation_id=str(row['activation_id']), targets=targets, identity=identity.wire(),
                envelope_hash=hashlib.sha256((destination+'\x00'+text).encode()).hexdigest(),
                issued_at=now, expires_at=now+60)
            sig = base64.b64encode(self.signer.sign(b'team360.transport.admission.v1\x00'+canonical(payload))).decode()
        return {'authorization': {'payload':payload,'signature':sig}}

    def send_text(self, **kwargs):
        raise MessagingSendError('binding_transport_requires_intent')

    def send_intent(self, *, destination, text, identity, authorization):
        if self.admission_check:
            self.admission_check()
        if (identity.provider_instance != self.scope['instance_name'] or
                not re.fullmatch(r'[1-9][0-9]{6,14}', destination) or not 0 < len(text) <= 4096):
            raise MessagingSendError('binding_transport_invalid_request')
        try:
            with httpx.Client(timeout=self.config.timeout, transport=self.transport,
                              trust_env=False, follow_redirects=False) as client:
                response = client.post(f'{self.config.base_url}/transport/v1/instances/{self.scope["instance_id"]}/sendText',
                    headers={'apikey':self.config.api_key}, json={'number':destination,'text':text,
                    'team360_egress':identity.wire(),'authorization':authorization})
        except httpx.HTTPError:
            raise MessagingSendError('binding_transport_unknown', uncertain=True) from None
        try:
            evidence = validate_egress(response.json()['egress'], identity)
        except (KeyError, ValueError, TypeError):
            raise MessagingSendError('binding_transport_invalid_evidence', uncertain=True) from None
        if evidence['acceptance'] == 'ACCEPTED':
            return OutboundMessageReceipt(evidence['provider_message_id'], destination, evidence)
        raise MessagingSendError('binding_transport_not_accepted',
            uncertain=evidence['acceptance'] == 'UNKNOWN', egress=evidence)
