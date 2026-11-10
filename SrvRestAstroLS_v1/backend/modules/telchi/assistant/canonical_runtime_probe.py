"""Opt-in durable DEV probe. No listeners, service restarts or external delivery.

Run with uv run -m modules.telchi.assistant.canonical_runtime_probe --output PATH.
The existing pilot admission/approval gates are checked, never rewritten.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from time import perf_counter
from uuid import uuid4


async def probe(report, *, business_semantics_scenarios=False, composite_results_scenarios=False):
    from . import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
    report['phase'] = 'private_configuration'
    config = lifecycle.load_config(dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    approval_path = config.get('approval', dev.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json')
    approval = dev.read_approval(approval_path)
    srv, settings = dev.configuration()
    report['phase'] = 'real_identity_database_preflight'
    await dev.check_database(approval, settings, srv.evolution)
    report['identity_database_preflight'] = 'PASS'
    report['phase'] = 'pilot_admission_gates'
    # Same access policy as transport_dev/create_session_app. No fake grants or
    # regenerated evidence to admit a changed implementation.
    try:
        dev.gate_evidence(approval)
    except ValueError:
        evidence = json.loads(dev.private_file(approval['gates_file']).read_text())
        expected = dict(workspace_id=approval['workspace_id'], user_id=approval['user_id'],
            instance='team360-meta-dev', approval_sha256=dev.approval_digest(approval),
            source_sha256=dev.source_digest())
        report['gate_scope_mismatches'] = [key for key, value in expected.items()
                                            if evidence.get(key) != value]
        raise
    if os.getenv('TEAM360_TELCHI_DURABLE') != '1' or os.getenv('TEAM360_TELCHI_FREE_ANALYSIS') != '1':
        raise ValueError('durable_and_research_opt_in_required')

    from modules.db.pool import create_pool, open_pool, close_pool, set_pool
    from modules.db.settings import get_database_settings
    from modules.db.transaction import transaction
    from modules.messaging.webhooks.evolution_whatsapp import build_service
    from modules.messaging.handlers import MessageDispatcher
    from modules.messaging.durable import DurableWorker
    from modules.messaging.domain.messages import InboundMessage
    from modules.messaging.domain.delivery import MessagingSendError
    from .composition import create_telchi_handler
    from .handler import BusinessPolicy, registration

    def access_check():
        dev.unchanged_approval(approval_path, approval)
        dev.gate_evidence(approval)

    class Capture:
        document = {'scope': {'environment': 'dev'}}

        def sender(self):
            return self

        def send_text(self, *, destination, text):
            # Only the last I/O boundary is intercepted. Return NO receipt: a
            # captured intent must never be recorded as provider acceptance.
            report.setdefault('captured_outbound', []).append(dict(
                text_sha256=hashlib.sha256(text.encode()).hexdigest(), characters=len(text),
                external_delivery='NOT_ATTEMPTED'))
            raise MessagingSendError('internal_capture_no_external_delivery', uncertain=False)

    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=4))
    await open_pool(pool)
    set_pool(pool)  # This standalone process only; no shared runtime mutation.
    try:
        report['phase'] = 'canonical_composition'
        handler = create_telchi_handler(pool=pool, policy=BusinessPolicy(
            approval['tenant_id'], approval['workspace_id'], None,
            approval['module_enabled'], approval['whole_workspace_scope_verified'],
            pilot_access_check=access_check, pilot_approval_sha256=dev.approval_digest(approval),
            pilot_user_id=approval['user_id']))
        service = await build_service(settings, srv.evolution,
            handlers={'telchi': registration(handler)}, transport_runtime=Capture(), durable=True)
        # Isolate ONLY the conversation namespace. Preserve the real channel,
        # PostgreSQL identity resolver, handler, policies and functional pipeline.
        channel = service.dispatcher._channels[service.binding.channel_id]
        namespace = 'canonical-probe:' + uuid4().hex
        service.binding = replace(service.binding, receiver_context=namespace)
        service.dispatcher = MessageDispatcher(channels=(replace(channel, receiver_context=namespace),),
            handlers={'telchi': registration(handler)}, identities=service.dispatcher._identities)
        report['namespace_sha256'] = hashlib.sha256(namespace.encode()).hexdigest()
        worker = DurableWorker(service)
        questions = [
            '¿Qué proporción de la facturación documental de agosto de 2026 corresponde al canal horizontal '
            'y qué limitaciones tiene esa comparación? No confundas canal con categoría de vendedor.',
            'Sobre ese mismo resultado y período, ¿qué parte quedó sin canal acreditado? '
            'Reutilizá lo que ya calculaste si alcanza.',
            'Nueva consulta: ¿cuánto facturamos en agosto de 2026?',
        ]
        conversation_groups = [0] * len(questions)
        if business_semantics_scenarios:
            questions = questions[:2] + [
                'De la facturación documental bruta de septiembre de 2026, ¿qué participación corresponde '
                'al canal horizontal y cuál fue la variación de esa facturación horizontal frente a agosto '
                'de 2026? Separá participación del mes de variación entre meses y declará los límites de cobertura.',
                'Sobre esos mismos importes del canal horizontal, ¿cuál es la diferencia absoluta entre '
                'septiembre y agosto? Reutilizá los resultados anteriores si alcanzan.',
                questions[2],
            ]
            conversation_groups = [0, 0, 1, 1, 2]
        if composite_results_scenarios:
            questions = [
                'De la facturación documental bruta de septiembre de 2026, ¿qué participación corresponde '
                'al canal horizontal y cuál fue la variación de esa facturación horizontal frente a agosto '
                'de 2026? Separá participación del mes de variación entre meses y declará los límites de cobertura.',
                '¿Y cuál fue la diferencia absoluta?',
                'Investigá los importes de facturación documental bruta en BS de los tres canales con mayor '
                'facturación en septiembre de 2026, con sus nombres e importes y límites de cobertura.',
                'Ordenalos de menor a mayor por ese importe, usando el resultado anterior.',
                'Nueva consulta: ¿cuánto facturamos en agosto de 2026?',
            ]
            conversation_groups = [0, 0, 1, 1, 2]
        base_binding = service.binding
        base_channel = service.dispatcher._channels[base_binding.channel_id]
        identities = service.dispatcher._identities
        bindings = {}
        report['turns'] = []
        for index, question in enumerate(questions):
            group = conversation_groups[index]
            receiver = namespace if group == 0 else namespace + ':conversation-' + str(group)
            service.binding = replace(base_binding, receiver_context=receiver)
            service.dispatcher = MessageDispatcher(channels=(replace(base_channel, receiver_context=receiver),),
                handlers={'telchi': registration(handler)}, identities=identities)
            bindings[group] = service.binding
            report['phase'] = 'durable_turn_' + str(index + 1)
            event = InboundMessage(provider='evolution', channel='whatsapp',
                external_message_id=namespace + ':' + str(index), external_thread_id='', subject='',
                sender=settings.authorized_sender, recipients=(receiver,), text_body=question,
                received_at=datetime.now(timezone.utc), metadata={'provider_instance': srv.evolution.instance})
            started = perf_counter()
            assert await service.process(event, t0_ms=0, t1_ms=0) == 'queued'
            assert await worker.tick()
            assert await service.process(event, t0_ms=0, t1_ms=0) == 'duplicate'
            assert not await worker.tick()
            report['turns'].append(dict(total_ms=(perf_counter() - started) * 1000,
                conversation_group=group, ingress='queued', repeated_ingress='duplicate'))
        async with transaction(pool) as conn:
            evidence = []
            for binding in bindings.values():
                evidence.extend(await service.repository.evidence(conn, binding))
        report['durable_rows'] = [dict(direction=e['direction'],
            transport_status=e.get('transport_status')) for e in evidence]
        report.update(status='PARTIAL', limitation='Durable traversal observed; inspect business audit before functional certification.')
    finally:
        await close_pool(pool)
        report['pool_closed'] = pool.closed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--business-semantics-scenarios', action='store_true',
                        help='Same durable probe, two measure conversations plus the existing fast path')
    parser.add_argument('--composite-results-scenarios', action='store_true',
                        help='Composite calculation and a distinct multi-row ordering follow-up')
    args = parser.parse_args()
    os.umask(0o077)
    report = dict(status='BLOCKED', phase='initialization', external_whatsapp_e2e='NOT_TESTED',
        whatsapp_sends=0, sap_write_count=0, permission_changes=0, service_restarts=0)
    try:
        asyncio.run(probe(report, business_semantics_scenarios=args.business_semantics_scenarios,
                          composite_results_scenarios=args.composite_results_scenarios))
    except Exception as exc:
        report['error_class'] = type(exc).__name__
        # Identifier-only failure codes; never persist DSNs, phones or raw errors.
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,100}', str(exc)):
            report['reason'] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['status'] != 'BLOCKED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
