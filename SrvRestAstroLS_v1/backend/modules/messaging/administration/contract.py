"""V1 offline delegation with explicit owner-only DEV administration.

The process environment is a caller-supplied deployment boundary, never read
from a signed manifest. Owner accreditation/public keys come only from pinned
local trust, not from requests. Existing two-person envelopes remain unchanged.
"""
import base64
import hashlib
import json
import re
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class Denied(Exception):
    """Only safe, constant diagnostics are exposed by the CLI."""


def require(condition, message='contract_denied'):
    if not condition:
        raise Denied(message)


def exact(value, fields):
    require(isinstance(value, dict) and set(value) == set(fields), 'invalid_fields')


def uuid(value):
    require(isinstance(value, str), 'invalid_uuid')
    try:
        require(str(UUID(value)) == value, 'invalid_uuid')
    except ValueError:
        raise Denied('invalid_uuid') from None


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def loads(data):
    require(len(data) <= 65536, 'document_too_large')
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_float=lambda _: (_ for _ in ()).throw(Denied('non_integer_json')),
                          parse_constant=lambda _: (_ for _ in ()).throw(Denied('non_finite_json')))
    except (ValueError, UnicodeError):
        raise Denied('invalid_json') from None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def unb64(value, size):
    require(isinstance(value, str), 'invalid_encoding')
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError:
        raise Denied('invalid_encoding') from None
    require(len(raw) == size and base64.b64encode(raw).decode() == value, 'invalid_encoding')
    return raw


def signature(key, domain, value):
    return base64.b64encode(key.sign(domain.encode() + b'\x00' + canonical(value))).decode()


def verify(key, sig, domain, value):
    try:
        Ed25519PublicKey.from_public_bytes(unb64(key, 32)).verify(
            unb64(sig, 64), domain.encode() + b'\x00' + canonical(value))
    except Exception:
        raise Denied('invalid_signature') from None


SCOPE_FIELDS = ('binding_id', 'environment', 'workspace_id', 'channel_id', 'provider_id',
                'instance_id', 'instance_name', 'organization_id', 'tenant_id', 'module', 'receiver_context')


def trust_profile(trust):
    require(trust.get('version') == 1, 'invalid_trust_root')
    if trust.get('laboratory_only') is True and trust.get('profile', 'laboratory') == 'laboratory':
        return 'laboratory'
    require(trust.get('laboratory_only') is False and trust.get('profile') == 'dev', 'invalid_trust_root')
    return 'dev'


def scope(value, profile='laboratory'):
    exact(value, SCOPE_FIELDS)
    for name in ('binding_id', 'workspace_id', 'channel_id', 'provider_id'):
        uuid(value[name])
    if value['organization_id'] is not None:
        uuid(value['organization_id'])
    require(value['environment'] == profile and profile in {'laboratory', 'dev'}, 'scope_profile_mismatch')
    for name in ('instance_id', 'instance_name', 'tenant_id', 'module', 'receiver_context'):
        require(isinstance(value[name], str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value[name]), 'invalid_scope')


def single_owner(manifest):
    return manifest.get('administration_mode') == 'single_owner_dev'


def confirmation(manifest):
    """Human-readable acknowledgement, itself covered by the owner signature."""
    return (f"CONFIRM {manifest['action']} {manifest['operation_id']} "
            f"{manifest['scope']['binding_id']} revision={manifest['revision']}")


def validate(manifest, now, profile='laboratory', *, environment=None):
    require(isinstance(manifest, dict), 'invalid_fields')
    owner_mode = single_owner(manifest)
    fields = ('version', 'operation_id', 'nonce', 'issued_at', 'expires_at', 'action',
              'scope', 'revision', 'credential_hash', 'targets', 'preparations')
    exact(manifest, fields + (('administration_mode', 'owner', 'confirmation') if owner_mode
                              else ('requester', 'approver')))
    if owner_mode:
        require(profile == 'dev' and environment in ('dev', 'development'), 'single_owner_dev_only')
    require(type(manifest['version']) is int and manifest['version'] == 1, 'invalid_version')
    for name in ('operation_id', 'nonce'):
        uuid(manifest[name])
    require(type(manifest['issued_at']) is int and type(manifest['expires_at']) is int, 'invalid_time')
    require(manifest['issued_at'] <= now < manifest['expires_at'] and
            0 < manifest['expires_at'] - manifest['issued_at'] <= 3600, 'expired_or_future')
    require(manifest['action'] in ('prepare', 'activate', 'revoke'), 'invalid_action')
    require(type(manifest['revision']) is int and 1 <= manifest['revision'] < 2**31, 'invalid_revision')
    require(isinstance(manifest['credential_hash'], str) and
            re.fullmatch('[0-9a-f]{64}', manifest['credential_hash']), 'invalid_verifier')
    for name in (('owner',) if owner_mode else ('requester', 'approver')):
        require(isinstance(manifest[name], str) and re.fullmatch('[a-z][a-z0-9_-]{0,63}', manifest[name]), 'invalid_actor')
    if not owner_mode:
        require(manifest['requester'] != manifest['approver'], 'separation_of_duties')
    scope(manifest['scope'], profile)
    if owner_mode:
        require(manifest['confirmation'] == confirmation(manifest), 'explicit_confirmation_required')
    exact(manifest['targets'], ('team360', 'evolution'))
    for target in manifest['targets'].values():
        exact(target, ('id', 'epoch'))
        uuid(target['id'])
        uuid(target['epoch'])
    require(isinstance(manifest['preparations'], dict), 'invalid_preparations')
    if manifest['action'] == 'activate':
        exact(manifest['preparations'], ('team360', 'evolution'))
    else:
        require(not manifest['preparations'], 'unexpected_preparations')
    return manifest


def authorize(envelope, trust, now, *, environment=None):
    require(isinstance(envelope, dict) and isinstance(envelope.get('manifest'), dict), 'invalid_fields')
    owner_mode = single_owner(envelope['manifest'])
    exact(envelope, ('manifest', 'owner_signature') if owner_mode
          else ('manifest', 'request_signature', 'approval_signature'))
    m = validate(envelope['manifest'], now, trust_profile(trust), environment=environment)
    if owner_mode:
        require(trust.get('administration_mode') == 'single_owner_dev' and
                trust.get('owner_id') == m['owner'], 'owner_not_accredited')
        checks = (('owner', 'administer', 'owner_signature', 'team360.offline.single_owner_dev.v1', m),)
    else:
        # A single-owner trust root cannot also authorize legacy admin envelopes.
        require(trust.get('administration_mode', 'dual_control_v1') == 'dual_control_v1', 'administration_mode_mismatch')
        checks = (
            ('requester', 'request', 'request_signature', 'team360.offline.request.v1', m),
            ('approver', 'approve', 'approval_signature', 'team360.offline.approval.v1',
             {'manifest': m, 'request_signature': envelope['request_signature']}),
        )
    for actor_field, capability, sig_field, domain, content in checks:
        actor = trust.get('actors', {}).get(m[actor_field])
        require(actor is not None and actor.get('enabled') is True, 'actor_not_accredited')
        if owner_mode:
            require(isinstance(actor.get('identity_ref'), str) and bool(actor['identity_ref'].strip())
                    and actor.get('key_custody') == 'owner', 'owner_accreditation_incomplete')
        require(type(actor.get('not_before')) is int and type(actor.get('not_after')) is int and
                actor['not_before'] <= now < actor['not_after'], 'actor_expired')
        # Exact scope equality: no wildcard, tenant/org inference or caller-selected public keys.
        require(any(g == {'capability': capability, 'action': m['action'], 'scope': m['scope']}
                    for g in actor.get('grants', [])), 'actor_outside_scope')
        verify(actor['public_key'], envelope[sig_field], domain, content)
    for side, target in m['targets'].items():
        trusted = trust.get('targets', {}).get(side)
        require(trusted is not None and target == {k: trusted[k] for k in ('id', 'epoch')}, 'wrong_target')
    if m['action'] == 'activate':
        for side, receipt in m['preparations'].items():
            exact(receipt, ('payload', 'signature'))
            expected = preparation(m, side)
            require(receipt['payload'] == expected, 'preparation_mismatch')
            verify(trust['targets'][side]['public_key'], receipt['signature'],
                   'team360.offline.preparation.v1', expected)
    return m


def preparation(m, side):
    return {'version': 1, 'side': side, 'target': m['targets'][side],
            'scope': m['scope'], 'revision': m['revision'], 'credential_hash': m['credential_hash']}
