"""Focal contracts; synthetic keys only, no network, messages or live DB writes."""
import base64
from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from modules.messaging.administration.contract import (
    Denied, authorize, confirmation, digest, preparation, signature,
)
from modules.messaging.administration.repository import Repository


NOW = 1800000000


def uid():
    return str(uuid4())


def public(key):
    return base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


@pytest.fixture
def packet():
    keys = {name: Ed25519PrivateKey.generate() for name in ('owner', 'team360', 'evolution')}
    scope = dict(binding_id=uid(), environment='dev', workspace_id=uid(), channel_id=uid(),
                 provider_id=uid(), instance_id=uid(), instance_name='synthetic',
                 organization_id=None, tenant_id='synthetic', module='telchi', receiver_context='fixture')
    targets = {side: dict(id=uid(), epoch=uid(), public_key=public(keys[side]))
               for side in ('team360', 'evolution')}
    trust = dict(version=1, laboratory_only=False, profile='dev', administration_mode='single_owner_dev',
                 owner_id='synthetic_owner', targets=targets, actors={
                     'synthetic_owner': dict(enabled=True, public_key=public(keys['owner']),
                         identity_ref='synthetic-test-identity', key_custody='owner',
                         not_before=NOW-1, not_after=NOW+3600,
                         grants=[dict(capability='administer', action=action, scope=deepcopy(scope))
                                 for action in ('prepare', 'activate', 'revoke')])})
    manifest = dict(version=1, administration_mode='single_owner_dev', owner='synthetic_owner',
                    operation_id=uid(), nonce=uid(), issued_at=NOW-1, expires_at=NOW+300,
                    action='prepare', scope=scope, revision=1, credential_hash='a'*64,
                    targets={s: {k: v[k] for k in ('id', 'epoch')} for s, v in targets.items()},
                    preparations={})
    manifest['confirmation'] = confirmation(manifest)
    return keys, trust, manifest


def signed(packet):
    keys, _, m = packet
    return dict(manifest=deepcopy(m), owner_signature=signature(
        keys['owner'], 'team360.offline.single_owner_dev.v1', m))


def check(packet, **kwargs):
    return authorize(signed(packet), packet[1], NOW, environment=kwargs.get('environment', 'dev'))


def test_valid_single_signature(packet):
    assert check(packet)['owner'] == 'synthetic_owner'
    assert set(signed(packet)) == {'manifest', 'owner_signature'}


@pytest.mark.parametrize('environment', [None, '', 'production', 'prod', 'staging', 'DEV'])
def test_cannot_enable_outside_explicit_dev(packet, environment):
    with pytest.raises(Denied, match='single_owner_dev_only'):
        check(packet, environment=environment)


@pytest.mark.parametrize('environment', ['dev', 'development'])
def test_dev_environment_aliases(packet, environment):
    assert check(packet, environment=environment)


@pytest.mark.parametrize('defect', ['signature', 'disabled', 'unknown_owner', 'other_workspace',
    'other_binding', 'missing_identity', 'custody', 'missing_mode', 'missing_owner', 'missing_key',
    'expired_actor', 'wrong_capability', 'missing_grant', 'no_confirmation', 'stale_confirmation',
    'production_trust', 'production_scope', 'laboratory_trust', 'extra_approver'])
def test_adversarial_signed_configuration(packet, defect):
    keys, trust, m = packet
    actor = trust['actors']['synthetic_owner']
    if defect == 'signature': keys['owner'] = Ed25519PrivateKey.generate()
    if defect == 'disabled': actor['enabled'] = False
    if defect == 'unknown_owner': m['owner'] = 'unauthorized'
    if defect == 'other_workspace': m['scope']['workspace_id'] = uid()
    if defect == 'other_binding': m['scope']['binding_id'] = uid(); m['confirmation'] = confirmation(m)
    if defect == 'missing_identity': actor.pop('identity_ref')
    if defect == 'custody': actor['key_custody'] = 'agent'
    if defect == 'missing_mode': trust.pop('administration_mode')
    if defect == 'missing_owner': trust.pop('owner_id')
    if defect == 'missing_key': actor['public_key'] = ''
    if defect == 'expired_actor': actor['not_after'] = NOW
    if defect == 'wrong_capability': actor['grants'][0]['capability'] = 'FULL_ACCESS'
    if defect == 'missing_grant': actor['grants'] = []
    if defect == 'no_confirmation': m.pop('confirmation')
    if defect == 'stale_confirmation': m['operation_id'] = uid()
    if defect == 'production_trust': trust['profile'] = 'production'
    if defect == 'production_scope': m['scope']['environment'] = 'production'
    if defect == 'laboratory_trust': trust.update(profile='laboratory', laboratory_only=True)
    if defect == 'extra_approver': m['approver'] = 'invented'
    with pytest.raises(Denied): check(packet)


@pytest.mark.parametrize('field', ['revision', 'credential_hash', 'scope', 'targets', 'action', 'confirmation'])
def test_signature_covers_every_authorization_field(packet, field):
    env = signed(packet)
    m = env['manifest']
    if field == 'revision': m[field] = 2
    if field == 'credential_hash': m[field] = 'b'*64
    if field == 'scope': m[field]['workspace_id'] = uid()
    if field == 'targets': m[field]['evolution']['epoch'] = uid()
    if field == 'action': m[field] = 'revoke'; m['confirmation'] = confirmation(m)
    if field == 'confirmation': m[field] = 'YES'
    with pytest.raises(Denied): authorize(env, packet[1], NOW, environment='dev')


def test_activation_still_requires_bilateral_target_signatures(packet):
    keys, trust, m = packet
    m.update(action='activate', preparations={})
    m['confirmation'] = confirmation(m)
    with pytest.raises(Denied): check(packet)
    for side in ('team360', 'evolution'):
        payload = preparation(m, side)
        m['preparations'][side] = dict(payload=payload, signature=signature(
            keys[side], 'team360.offline.preparation.v1', payload))
    assert check(packet)
    m['preparations']['evolution']['signature'] = m['preparations']['team360']['signature']
    with pytest.raises(Denied): check(packet)


def connection(packet, *, old=None, nonce=False, rows=None, local=None):
    """Controlled SQL responses: unit tests, NOT an operational durability claim."""
    _, _, m = packet
    conn = Mock()
    def execute(sql, params=None):
        result = Mock()
        row = None
        if 'extract(epoch' in sql: row = {'n': NOW}
        elif 'FROM ot_target' in sql: row = dict(target_id=m['targets']['team360']['id'], epoch=m['targets']['team360']['epoch'])
        elif 'FROM ot_inventory' in sql: row = dict(scope=deepcopy(m['scope']))
        elif 'SELECT envelope_hash,receipt' in sql: row = old
        elif 'AND nonce=' in sql: row = {'exists': True} if nonce else None
        elif 'SELECT * FROM ot_revision' in sql: row = local
        result.fetchone.return_value = row
        result.fetchall.return_value = rows or []
        return result
    conn.execute.side_effect = execute
    return conn


def apply(packet, conn):
    return Repository().apply(conn, signed(packet), packet[1], 'team360', packet[0]['team360'], environment='dev')


def test_audit_contains_actual_owner_and_complete_signed_envelope(packet):
    conn = connection(packet)
    assert apply(packet, conn)['disposition'] == 'applied'
    audit = [c for c in conn.execute.call_args_list if 'INSERT INTO ot_operation' in c.args[0]]
    assert len(audit) == 1
    params = audit[0].args[1]
    assert params[2] == 'synthetic_owner'
    assert params[5].obj == signed(packet)


def test_exact_replay_is_read_only(packet):
    env = signed(packet)
    receipt = dict(payload={'retained': True}, signature='retained')
    conn = connection(packet, old=dict(envelope_hash=digest(env), receipt=receipt))
    assert apply(packet, conn) == dict(disposition='already_applied', receipt=receipt)
    assert not any('INSERT' in c.args[0] or 'UPDATE ot_' in c.args[0] for c in conn.execute.call_args_list)


@pytest.mark.parametrize('kind,expected', [('conflict', 'operation_replay_conflict'),
    ('nonce', 'nonce_reused'), ('obsolete', 'obsolete_revision')])
def test_replays_and_obsolete_revision_denied(packet, kind, expected):
    conn = connection(packet, old=dict(envelope_hash='different', receipt={}) if kind == 'conflict' else None,
                      nonce=kind == 'nonce', rows=[dict(revision=1, state='revoked')] if kind == 'obsolete' else None)
    with pytest.raises(Denied, match=expected): apply(packet, conn)
    assert not any('INSERT' in c.args[0] for c in conn.execute.call_args_list)


def test_revoked_credential_cannot_be_reactivated(packet):
    keys, _, m = packet
    m['action'] = 'activate'
    for side in ('team360', 'evolution'):
        payload = preparation(m, side)
        m['preparations'][side] = dict(payload=payload, signature=signature(
            keys[side], 'team360.offline.preparation.v1', payload))
    m['confirmation'] = confirmation(m)
    local = dict(scope=m['scope'], credential_hash=m['credential_hash'], state='revoked')
    conn = connection(packet, rows=[dict(revision=1, state='revoked')], local=local)
    with pytest.raises(Denied, match='activation_not_prepared'): apply(packet, conn)


@pytest.mark.parametrize('action', ['revoke', 'prepare'])
def test_revocation_and_recovery_use_existing_monotonic_state_machine(packet, action):
    _, _, m = packet
    m['action'] = action
    if action == 'prepare':
        m['revision'] = 2
        m['credential_hash'] = 'b'*64
    m['confirmation'] = confirmation(m)
    local = dict(scope=m['scope'], credential_hash='a'*64, state='active')
    conn = connection(packet, rows=[dict(revision=1, state='active' if action == 'revoke' else 'revoked')],
                      local=local)
    assert apply(packet, conn)['disposition'] == 'applied'
    mutations = [c.args[0] for c in conn.execute.call_args_list]
    assert any(('INSERT INTO ot_revision' if action == 'prepare' else "SET state='revoked'") in s
               for s in mutations)
    assert any('INSERT INTO ot_operation' in s for s in mutations)
    assert not any('DELETE' in s or 'TRUNCATE' in s for s in mutations)


@pytest.mark.parametrize('profile', ['dev', 'laboratory'])
def test_existing_dual_control_still_requires_two_independent_actors(packet, profile):
    keys, trust, m = packet
    for name in ('administration_mode', 'owner_id'): trust.pop(name)
    trust.update(profile=profile, laboratory_only=profile == 'laboratory')
    m['scope']['environment'] = profile
    actor = trust['actors'].pop('synthetic_owner')
    keys['approver'] = Ed25519PrivateKey.generate()
    for name, capability in (('requester', 'request'), ('approver', 'approve')):
        trust['actors'][name] = {**actor, 'public_key': public(keys['owner'] if name == 'requester' else keys[name]),
                                'grants': [dict(capability=capability, action='prepare', scope=deepcopy(m['scope']))]}
    for name in ('administration_mode', 'owner', 'confirmation'): m.pop(name)
    m.update(requester='requester', approver='approver')
    def dual():
        request = signature(keys['owner'], 'team360.offline.request.v1', m)
        return dict(manifest=deepcopy(m), request_signature=request, approval_signature=signature(
            keys['approver'], 'team360.offline.approval.v1', dict(manifest=m, request_signature=request)))
    assert authorize(dual(), trust, NOW)
    m['approver'] = 'requester'
    with pytest.raises(Denied, match='separation_of_duties'): authorize(dual(), trust, NOW)
