"""Durable ingress/execution idempotency evidence for Srv05 + TelchiAI.

Real PostgreSQL DEV, the approved ``telchi_dev`` / ``telchi_whatsapp_dev`` /
``team360-meta-dev`` binding, the verified pilot identity and the real
``TelchiHandler`` reached through the horizontal ``MessagingService`` fence.
The Evolution egress is a *recording double*: this probe proves inbound claim
deduplication and at-most-once handler execution, and explicitly does NOT prove
effective WhatsApp delivery.

Reuses existing harness pieces (runtime_http helpers, Evolution normalizer,
MessagingRepository, TelchiHandler composition). Persistence is isolated from
the real pilot thread by overriding only ``receiver_context`` in an in-memory
copy of the resolved binding; the real channel/workspace/tenant/module and the
real verified telephone binding are still used. Nothing is written to the DB
configuration, and no Evolution webhook is touched.

Run (from ``SrvRestAstroLS_v1/backend`` with the private environment loaded):

    uv run python scripts/telchi_durable_idempotency_probe.py \
        --approval /media/issajar/.../private/telchi/whatsapp-dev-session-approval.json \
        --output /media/issajar/.../private/telchi/durable-idempotency-v1-<ts>
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

PRIVATE_ROOT = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi')
INSTANCE = 'team360-meta-dev'
WORKSPACE_SLUG = 'telchi_dev'
CHANNEL_ALIAS = 'telchi_whatsapp_dev'
PROVIDER = 'evolution'
PERMISSION = 'telchi.sales.source_quantity.read.v1'
DEFAULT_TEXT = 'dame las ultimas ventas de calenta'


def _sha(value: object) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


class RecordingSender:
    """Provider-neutral egress double. Records intent; never sends WhatsApp."""

    def __init__(self):
        self.calls: list[dict] = []
        self.error = None

    def send_text(self, *, destination, text):
        self.calls.append({'destination_sha256': _sha(destination), 'text_sha256': _sha(text),
                           'at': datetime.now(timezone.utc).isoformat()})
        if self.error is not None:
            raise self.error
        from modules.messaging.domain.messages import OutboundMessageReceipt
        return OutboundMessageReceipt(external_message_id=f'duridem-{uuid.uuid4().hex}',
                                      external_thread_id=_sha(destination))


class HandlerCounter:
    """Observational wrapper around the real TelchiHandler; no behaviour change."""

    def __init__(self, inner):
        self.inner = inner
        self.authorization = inner.authorization
        self.calls = 0

    async def handle(self, message, context):
        self.calls += 1
        return await self.inner.handle(message, context)


class CapabilityCounter:
    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def execute(self, state):
        self.calls += 1
        return await self.inner.execute(state)


def _event(phone: str, receiver: str, text: str, external_message_id: str):
    from modules.messaging.providers.evolution.mapper import normalize_events
    payload = {
        'event': 'messages.upsert', 'instance': INSTANCE,
        'data': {'key': {'id': external_message_id,
                         'remoteJid': f'{phone}@s.whatsapp.net', 'fromMe': False},
                 'message': {'conversation': text},
                 'messageTimestamp': int(time.time())},
    }
    events = normalize_events(payload, instance=INSTANCE, recipient=receiver,
                              received_at=datetime.now(timezone.utc))
    if len(events) != 1:
        raise RuntimeError('event_normalization_failed')
    return events[0]


async def _snapshot(pool, binding, external_message_id):
    from modules.db.transaction import transaction
    async with transaction(pool) as conn:
        inbound = await (await conn.execute("""
            SELECT id, thread_id, status, transport_status, payload_jsonb
            FROM message_events
            WHERE channel_id=%s AND provider_instance=%s AND direction='inbound'
              AND event_type='message' AND provider_message_id=%s
            """, (binding.channel_id, binding.storage_instance, external_message_id))).fetchall()
        outbound = []
        if inbound:
            inbound_id = str(inbound[0]['id'])
            outbound = await (await conn.execute("""
                SELECT id, status, transport_status, provider_message_id, correlation_id, payload_jsonb
                FROM message_events
                WHERE channel_id=%s AND provider_instance=%s AND direction='outbound'
                  AND event_type='message' AND correlation_id=%s
                """, (binding.channel_id, binding.storage_instance, inbound_id))).fetchall()
        return [dict(r) for r in inbound], [dict(r) for r in outbound]


def _audit_summary(inbound_row):
    payload = inbound_row.get('payload_jsonb') or {}
    audit = payload.get('telchi_assistant_v1') or {}
    return dict(classification=(payload.get('dispatch_result') or {}).get('classification'),
                decision=audit.get('decision'), committed=audit.get('committed'),
                execution_status=audit.get('execution_status'), capability_calls=audit.get('capability_calls'),
                interpretation_proposed=audit.get('interpretation_proposed') is not None,
                required_permission=audit.get('required_permission'),
                response_prepared=bool(audit.get('response_prepared')))


def _host_preflight():
    load = os.getloadavg()
    available_kb = None
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                available_kb = int(line.split()[1])
                break
    except OSError:
        pass
    return dict(load_1m=load[0], load_5m=load[1], load_15m=load[2],
                mem_available_mib=(available_kb // 1024) if available_kb else None)


async def run(args):
    from modules.telchi.assistant.whatsapp_dev import read_approval, source_digest, approval_digest
    from modules.telchi.assistant.tests.runtime_http import run_battery as rb
    from modules.db.settings import get_database_settings
    from modules.db.pool import create_pool, open_pool, close_pool
    from modules.db.transaction import transaction
    from modules.messaging.repository import MessagingRepository
    from modules.messaging.service import MessagingService
    from modules.messaging.handlers import ChannelContext, MessageDispatcher
    from modules.messaging.identity import PostgresPhoneIdentityResolver
    from modules.messaging.domain.delivery import MessagingSendError
    from modules.telchi.assistant.handler import (TelchiHandler, BusinessPolicy, BusinessAuthorization,
                                                  PostgresConversationStore, registration)

    env = rb._load_env_file()
    os.environ.update(env)
    os.environ.update({'TEAM360_ENV': 'dev', 'TEAM360_MESSAGING_DEV_ENABLED': '1',
                       'TEAM360_MESSAGING_DISPATCH_MODE': 'horizontal_v1',
                       'TEAM360_MESSAGING_DEV_SQL_TENANT': ''})

    approval = read_approval(Path(args.approval))
    if approval['tenant_id'] != 'telchi' or approval['permission'] != PERMISSION:
        raise PermissionError('approved_telchi_business_identity_required')

    pool = create_pool(get_database_settings())
    await open_pool(pool)
    repository = MessagingRepository()
    transport_schema = 'FAIL'
    try:
        async with transaction(pool) as conn:
            await repository.validate_transport_schema(conn)
            transport_schema = 'PASS'
            binding = await repository.binding(conn, workspace_slug=WORKSPACE_SLUG,
                                               channel_alias=CHANNEL_ALIAS, provider=PROVIDER,
                                               instance=INSTANCE)
        if (binding.environment != 'dev' or binding.module != 'telchi'
                or binding.tenant_id != 'telchi' or not binding.receiver_context
                or binding.provider_instance != INSTANCE):
            raise PermissionError('approved_DEV_telchi_binding_required')

        phone = rb._pilot_phone(INSTANCE)
        # Isolate the probe's persistence from the real pilot thread while keeping
        # the real channel/workspace/tenant/module and verified telephone binding.
        probe_binding = replace(binding, receiver_context=f'durable-idem-probe:{uuid.uuid4().hex[:12]}')

        channel = ChannelContext(probe_binding.channel_id, PROVIDER, INSTANCE,
                                 probe_binding.receiver_context, probe_binding.tenant_id,
                                 probe_binding.workspace_id, probe_binding.module,
                                 probe_binding.environment)
        policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], PERMISSION, True, True)
        real_handler = TelchiHandler(store=PostgresConversationStore(pool),
                                     authorization=BusinessAuthorization(policy))
        handler = HandlerCounter(real_handler)
        capability = CapabilityCounter(real_handler.capabilities)
        real_handler.capabilities = capability
        dispatcher = MessageDispatcher(channels=(channel,),
                                       handlers={'telchi': registration(handler)},
                                       identities=PostgresPhoneIdentityResolver(pool), environment='dev')
        sender = RecordingSender()
        service = MessagingService(pool=pool, repository=repository, binding=probe_binding,
                                   sender=sender, authorized_sender='', dispatcher=dispatcher)

        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        text = args.text
        scenarios = {}

        # S1: same provider_message_id three times, sequential.
        e1 = _event(phone, probe_binding.receiver_context, text, f'duridem-s1-{run_id}')
        r1a = await service.process(e1, t0_ms=0, t1_ms=0)
        r1b = await service.process(e1, t0_ms=0, t1_ms=0)
        r1c = await service.process(e1, t0_ms=0, t1_ms=0)
        i1, o1 = await _snapshot(pool, probe_binding, e1.external_message_id)
        scenarios['sequential_duplicate'] = dict(
            results=[r1a, r1b, r1c], inbound_count=len(i1), outbound_count=len(o1),
            handler_calls=handler.calls, capability_calls=capability.calls, sender_calls=len(sender.calls),
            audit=_audit_summary(i1[0]) if i1 else None,
            one_inbound=(len(i1) == 1), one_outbound_at_most=(len(o1) <= 1),
            duplicate_no_handler=(r1b == 'duplicate' and r1c == 'duplicate'))

        # S2: same provider_message_id twice, concurrent.
        h_before, c_before, s_before = handler.calls, capability.calls, len(sender.calls)
        e2 = _event(phone, probe_binding.receiver_context, text, f'duridem-s2-{run_id}')
        concurrent = await asyncio.gather(service.process(e2, t0_ms=0, t1_ms=0),
                                          service.process(e2, t0_ms=0, t1_ms=0))
        i2, o2 = await _snapshot(pool, probe_binding, e2.external_message_id)
        scenarios['concurrent_duplicate'] = dict(
            results=list(concurrent), accepted_count=sum(1 for r in concurrent if r == 'accepted'),
            other_results=sorted(r for r in concurrent if r != 'accepted'),
            inbound_count=len(i2), outbound_count=len(o2),
            handler_calls=handler.calls - h_before, capability_calls=capability.calls - c_before,
            sender_calls=len(sender.calls) - s_before,
            one_inbound=(len(i2) == 1), one_outbound_at_most=(len(o2) <= 1),
            audit=_audit_summary(i2[0]) if i2 else None,
            exactly_one_handler=((handler.calls - h_before) == 1))

        # S3: crash before egress leaves a durable intent that recovery resumes
        # without re-running the handler.
        h_before, c_before, s_before = handler.calls, capability.calls, len(sender.calls)
        e3 = _event(phone, probe_binding.receiver_context, text, f'duridem-s3-{run_id}')
        original_send = service._send_horizontal

        async def _crash(*_a, **_k):
            raise RuntimeError('controlled_interrupt_before_send')

        service._send_horizontal = _crash
        raised = None
        try:
            await service.process(e3, t0_ms=0, t1_ms=0)
        except RuntimeError as exc:
            raised = str(exc)
        finally:
            service._send_horizontal = original_send
        i3, o3 = await _snapshot(pool, probe_binding, e3.external_message_id)
        capability_after_interrupt = capability.calls
        resumed = await service.process(e3, t0_ms=0, t1_ms=0)
        i3b, o3b = await _snapshot(pool, probe_binding, e3.external_message_id)
        scenarios['recover_resumes_intent'] = dict(
            interrupted=raised is not None, interrupt_error=raised,
            pre_send_outbound_count=len(o3), resumed_result=resumed,
            handler_calls_total=handler.calls - h_before,
            capability_calls_during_recovery=capability.calls - capability_after_interrupt,
            final_inbound_count=len(i3b), final_outbound_count=len(o3b),
            audit=_audit_summary(i3b[0]) if i3b else None,
            sender_calls=len(sender.calls) - s_before,
            resume_did_not_reinvoke=((handler.calls - h_before) == 1),
            at_most_one_outbound=(len(o3b) <= 1))

        # S4: durable claim without a result must never replay a handler.
        h_before, c_before, s_before = handler.calls, capability.calls, len(sender.calls)
        e4 = _event(phone, probe_binding.receiver_context, text, f'duridem-s4-{run_id}')
        async with transaction(pool) as conn:
            claimed = await repository.claim(conn, probe_binding, e4, {'t0_ms': 0, 't1_ms': 0})
        if not claimed:
            raise RuntimeError('manual_claim_failed')
        uncertain = await service.recover_delivery(e4)
        i4, o4 = await _snapshot(pool, probe_binding, e4.external_message_id)
        scenarios['execution_uncertain'] = dict(
            result=uncertain, inbound_count=len(i4), outbound_count=len(o4),
            handler_calls=handler.calls - h_before, sender_calls=len(sender.calls) - s_before,
            no_handler_replay=((handler.calls - h_before) == 0), no_outbound=(len(o4) == 0))

        # S5: uncertain send outcome is never auto-retried and never re-executes.
        h_before, c_before, s_before = handler.calls, capability.calls, len(sender.calls)
        e5 = _event(phone, probe_binding.receiver_context, text, f'duridem-s5-{run_id}')
        sender.error = MessagingSendError('provider_timeout', uncertain=True)
        first5 = await service.process(e5, t0_ms=0, t1_ms=0)
        sender.error = None
        i5, o5 = await _snapshot(pool, probe_binding, e5.external_message_id)
        capability_after_first5 = capability.calls
        recover5 = await service.recover_delivery(e5)
        recover5r = await service.recover_delivery(e5, retry=True)
        i5b, o5b = await _snapshot(pool, probe_binding, e5.external_message_id)
        scenarios['uncertain_send_not_retried'] = dict(
            first_result=first5, recover_result=recover5, recover_retry_result=recover5r,
            outbound_transport=[r['transport_status'] for r in o5],
            handler_calls=handler.calls - h_before, sender_calls=len(sender.calls) - s_before,
            capability_calls_during_recovery=capability.calls - capability_after_first5,
            audit=_audit_summary(i5b[0]) if i5b else None,
            no_handler_replay=((handler.calls - h_before) == 1),
            no_resend=((len(sender.calls) - s_before) == 1),
            at_most_one_outbound=(len(o5b) <= 1))

        # S6: known failure can resume the persisted intent; still no handler replay.
        h_before, c_before, s_before = handler.calls, capability.calls, len(sender.calls)
        e6 = _event(phone, probe_binding.receiver_context, text, f'duridem-s6-{run_id}')
        sender.error = MessagingSendError('provider_rejected', uncertain=False)
        first6 = await service.process(e6, t0_ms=0, t1_ms=0)
        sender.error = None
        capability_after_first6 = capability.calls
        recover6 = await service.recover_delivery(e6)
        recover6r = await service.recover_delivery(e6, retry=True)
        i6, o6 = await _snapshot(pool, probe_binding, e6.external_message_id)
        scenarios['known_failure_controlled_retry'] = dict(
            first_result=first6, recover_result=recover6, recover_retry_result=recover6r,
            inbound_count=len(i6), outbound_count=len(o6),
            handler_calls=handler.calls - h_before, sender_calls=len(sender.calls) - s_before,
            capability_calls_during_recovery=capability.calls - capability_after_first6,
            audit=_audit_summary(i6[0]) if i6 else None,
            no_handler_replay=((handler.calls - h_before) == 1),
            resume_delivered=((len(sender.calls) - s_before) == 2),
            at_most_one_outbound=(len(o6) <= 1))

        model_metadata = real_handler.interpreter.last_metadata
        invariants = {
            'one_inbound_event_sequential': scenarios['sequential_duplicate']['one_inbound'],
            'at_most_one_outbound_sequential': scenarios['sequential_duplicate']['one_outbound_at_most'],
            'duplicate_does_not_reinvoke_handler': scenarios['sequential_duplicate']['duplicate_no_handler'],
            'concurrent_exactly_one_handler': scenarios['concurrent_duplicate']['exactly_one_handler'],
            'concurrent_one_inbound': scenarios['concurrent_duplicate']['one_inbound'],
            'concurrent_at_most_one_outbound': scenarios['concurrent_duplicate']['one_outbound_at_most'],
            'recover_resumes_intent_without_handler': scenarios['recover_resumes_intent']['resume_did_not_reinvoke'],
            'execution_uncertain_never_replays_handler': scenarios['execution_uncertain']['no_handler_replay'],
            'execution_uncertain_no_outbound': scenarios['execution_uncertain']['no_outbound'],
            'uncertain_send_not_auto_retried': scenarios['uncertain_send_not_retried']['no_resend'],
            'uncertain_send_no_handler_replay': scenarios['uncertain_send_not_retried']['no_handler_replay'],
            'known_failure_retry_no_handler_replay': scenarios['known_failure_controlled_retry']['no_handler_replay'],
            'recover_no_capability_reexecution': scenarios['recover_resumes_intent']['capability_calls_during_recovery'] == 0,
            'uncertain_send_no_capability_reexecution': scenarios['uncertain_send_not_retried']['capability_calls_during_recovery'] == 0,
            'known_failure_retry_no_capability_reexecution': scenarios['known_failure_controlled_retry']['capability_calls_during_recovery'] == 0,
        }
        all_pass = all(invariants.values())

        evidence = {
            'schema': 'telchi-durable-idempotency-v1',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'branch': _git('rev-parse', '--abbrev-ref', 'HEAD'),
            'head': _git('rev-parse', 'HEAD'),
            'source_sha256': source_digest(),
            'approval_sha256': approval_digest(approval),
            'probe_sha256': _file_sha(Path(__file__).resolve()),
            'environment': 'dev',
            'transport_schema_026': transport_schema,
            'tenant_id': approval['tenant_id'],
            'workspace_id_sha256': _sha(approval['workspace_id']),
            'binding': {
                'workspace_slug': WORKSPACE_SLUG, 'channel_alias': CHANNEL_ALIAS,
                'provider_instance': INSTANCE, 'channel_id_sha256': _sha(binding.channel_id),
                'environment': binding.environment, 'module': binding.module,
                'tenant_id': binding.tenant_id, 'storage_scope_sha256': _sha(binding.storage_instance),
                'probe_scope_sha256': _sha(probe_binding.storage_instance),
            },
            'identity': {
                'phone_sha256': _sha(phone), 'user_id_sha256': _sha(approval['user_id']),
                'permission': approval['permission'], 'verified_binding_used': True,
            },
            'interpreter': {
                'provider': 'OpenAI direct', 'requested_model': 'gpt-5.6-luna',
                'observed': _jsonable(model_metadata),
            },
            'egress': {'kind': 'recording_double', 'real_whatsapp_sends': 0},
            'delivery': 'NOT_TESTED',
            'scenarios': {name: _jsonable(value) for name, value in scenarios.items()},
            'persisted_audit_rows': {
                name: value.get('audit') for name, value in scenarios.items()
                if value.get('audit') is not None
            },
            'handler_invocations_total': handler.calls,
            'capability_invocations_total': capability.calls,
            'recording_sender_calls_total': len(sender.calls),
            'invariants': invariants,
            'durable_idempotency': 'PASS' if all_pass else 'FAIL',
            'scope': ('ingress claim deduplication + at-most-once TelchiAI handler execution '
                      'on real PostgreSQL DEV; effective WhatsApp delivery excluded'),
            'host_preflight': _host_preflight(),
        }
        return evidence
    finally:
        await close_pool(pool)


def _git(*argv):
    import subprocess
    try:
        return subprocess.run(['git', *argv], cwd=str(BACKEND), capture_output=True,
                              text=True, check=False).stdout.strip() or None
    except OSError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approval', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--text', default=DEFAULT_TEXT)
    args = parser.parse_args()

    output = args.output.resolve()
    if not output.is_relative_to(PRIVATE_ROOT):
        raise SystemExit('private_output_required')
    if output.exists() and any(output.iterdir()):
        raise SystemExit('output_must_be_new_or_empty')
    output.mkdir(mode=0o700, parents=True, exist_ok=True)

    evidence = asyncio.run(run(args))
    artifact = output / 'durable_idempotency.json'
    with open(artifact, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        json.dump(evidence, stream, indent=2, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'durable_idempotency': evidence['durable_idempotency'],
                      'invariants': evidence['invariants'],
                      'artifact': str(artifact),
                      'artifact_sha256': _file_sha(artifact)}, indent=2))
    if evidence['durable_idempotency'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()