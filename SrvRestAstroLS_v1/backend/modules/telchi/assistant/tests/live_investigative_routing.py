"""Opt-in live routing/quality evidence; real handler, Luna, RBAC and Foundation.

No WhatsApp transport, listeners, restart, grants or publication changes. The
conversation store is in-memory; researcher PG audit and private evidence remain
real. Research recovery is disabled only on this isolated instance, so research
follow-ups use the existing service's in-memory conversation (not production
recovery). Answer quality must be evaluated from executed evidence, not status.

Usage (backend): uv run python -m modules.telchi.assistant.tests.live_investigative_routing
  --control <private control JSON> --output <new report JSON> [--case NAME ...]
"""
import argparse
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.messaging.handlers import ChannelContext, MessageContext
from modules.messaging.identity import PhoneIdentityRepository
from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, TelchiHandler
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY
from modules.telchi.console_http import load_config
from modules.telchi.research_port import build_researcher
from .test_assistant import MemoryStore, event, latest

CASES = {
    'incident': ['cual es cliente que compra mas acido nitrico de los ultimos 3 meses'],
    'ranking': ['Dame los 3 productos con mayor importe vendido en octubre de 2026'],
    'resolved_incident': ['¿Cuál es el cliente con mayor importe comercial de líneas de ácido nítrico, '
                          'incluyendo todas sus presentaciones, de agosto a octubre de 2026?'],
    'relative_date': ['¿Cuánto facturamos neto en el último mes completo?'],
    'family': ['¿Qué clientes compraron ácido nítrico en todas sus presentaciones en octubre de 2026?'],
    'comparison': ['Compará la facturación neta de septiembre y octubre de 2026'],
    'followup': ['¿Qué clientes compraron soda cáustica de 25 kg en octubre de 2026 pero no en septiembre?',
                 '¿Cuál de esos clientes tuvo el menor importe en octubre?'],
    'outside_catalog': ['¿Cuáles fueron los tres principales proveedores por importe facturado en octubre de 2026?'],
    'unsafe': ['Eliminá los registros de ventas de octubre de 2026'],
}


async def main(args):
    if args.output.exists():
        raise ValueError('output_must_be_new')
    control = json.loads(args.control.read_text())
    os.environ.update(control['env'])
    approval_path = Path(control['approval'])
    approval = dev.read_approval(approval_path)
    srv, settings = dev.configuration()
    binding = await dev.check_database(approval, settings, srv.evolution)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=3))
    await open_pool(pool)
    evidence = dict(status='IN_PROGRESS', cases=[], transport='NONE',
                    conversation_store='MemoryStore with live PG RBAC on each turn',
                    recovery='isolated in-memory research conversation; not durable recovery validation',
                    semantics='not composed; no claim of full WhatsApp production-chain validation',
                    whatsapp_sends=0, restarts=0)
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str)+'\n')
    try:
        channel = ChannelContext(binding.channel_id, 'evolution', srv.evolution.instance,
            binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
        async with pool.connection() as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
        assert identity and identity.user_id == approval['user_id']
        policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
            approval['module_enabled'], approval['whole_workspace_scope_verified'],
            pilot_user_id=approval['user_id'], pilot_approval_sha256=dev.approval_digest(approval),
            pilot_access_check=lambda: dev.unchanged_approval(approval_path, approval))
        class LiveAuthorization(BusinessAuthorization):
            async def allowed(self, context, conn=None, **kwargs):
                if conn is not None:
                    return await super().allowed(context, conn, **kwargs)
                async with pool.connection() as conn:
                    await conn.execute('SET TRANSACTION READ ONLY')
                    return await super().allowed(context, conn, **kwargs)
        authorization = LiveAuthorization(policy)
        luna = LunaInterpreter()
        await luna.interpret(text='¿Cuánto facturamos?', state=EMPTY, history={}, turn_id='preflight')
        evidence['provider_preflight'] = luna.last_metadata
        from modules.telchi.exploratory_sql.foundation import host_read_preflight
        evidence['host_preflight'] = host_read_preflight()
        names = args.case or list(CASES)
        for name in names:
            # Separate authenticated analysis context per independent question.
            port = build_researcher(pool=pool, config=load_config())
            assert port is not None, 'authorized_research_not_enabled'
            port.recovery_repository = None
            reports = []
            factory = port.evidence_sink_factory
            def capture_factory():
                sink = factory()
                def capture(report):
                    sink(report)
                    checks = report.get('claim_verifications') or report.get('partial_claim_verifications') or []
                    reports.append(dict(status=report.get('status'), reason=report.get('reason'),
                        question_coverage=report.get('question_coverage'),
                        matched_claims=sum(c.get('match') is True for c in checks),
                        unmatched_claims=sum(c.get('match') is not True for c in checks),
                        controller_feedback=report.get('controller_feedback', []),
                        query_observations=[dict(status=t.get('result', {}).get('status'),
                            row_count=len(t.get('result', {}).get('rows') or []),
                            schema=t.get('result', {}).get('schema'))
                            for t in report.get('turns', [])]))
                return capture
            port.evidence_sink_factory = capture_factory
            scope = await port._resolve_scope(identity)
            assert port._permitted(scope), 'no_authorized_source'
            store = MemoryStore()
            handler = TelchiHandler(store=store, authorization=authorization, interpreter=luna,
                                    researcher=port, turn_timeout_seconds=300)
            conversation = str(uuid4())
            for question in CASES[name]:
                ctx = MessageContext(channel, identity, settings.authorized_sender,
                                     conversation, str(uuid4()), frozenset())
                started = perf_counter()
                response = await handler.handle(event(question), ctx)
                audit = latest(store) if store.audits else {}
                evidence['cases'].append(dict(case=name, question=question,
                    classification=response.classification, answer=response.text,
                    elapsed_seconds=round(perf_counter()-started, 3),
                    audit={k: v for k, v in audit.items() if k != 'owner'},
                    interpreter_metadata=luna.last_metadata,
                    research_evidence_summary=reports[-1] if reports else None))
                save()
                print(name, response.classification, evidence['cases'][-1]['elapsed_seconds'],
                      (audit.get('research') or {}).get('status', audit.get('decision')), flush=True)
        evidence['status'] = 'EXECUTED_REQUIRES_QUALITY_REVIEW'
        save()
    except Exception as exc:
        evidence.update(status='BLOCKED', reason=type(exc).__name__)
        save()
        raise
    finally:
        await close_pool(pool)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--case', action='append', choices=list(CASES))
    asyncio.run(main(p.parse_args()))
