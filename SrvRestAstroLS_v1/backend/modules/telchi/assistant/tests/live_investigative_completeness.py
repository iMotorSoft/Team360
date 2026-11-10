"""Opt-in sequential sufficiency battery: real handler/Luna/CURRENT, durable PG.

No transport, services, restart, grants or publication changes. Fresh isolated
Messaging receiver per case; real persisted thread/audit and research recovery.
Results require a business review; this runner never declares quality PASS.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
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
from modules.messaging.repository import MessagingRepository
from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, PostgresConversationStore, TelchiHandler
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY
from modules.telchi.console_http import load_config
from modules.telchi.research_port import build_researcher
from .live_investigative_routing import CASES as BASE_CASES
from .test_assistant import event

# Held out from prompt design: different entity/metric/account/product questions.
CASES = dict(BASE_CASES, unseen_quantity=[
    '¿Qué cuenta SAP compró más soda cáustica por cantidad documental en octubre de 2026? '
    'Separá las presentaciones si sus unidades no son comparables.'], unseen_accounts=[
    '¿Hay nombres de clientes compartidos por varias cuentas SAP con ventas en octubre de 2026? '
    'Mostrame los tres nombres con mayor importe y sus cuentas, sin fusionarlas como una sola empresa.'],
    unseen_coverage=['¿Quién encabeza las compras de ácido clorhídrico por importe comercial en noviembre de 2026, '
                     'y qué parte de ese mes está realmente publicada?'],
    heldout_net_change=['¿Cuánto aumentó o bajó la facturación neta entre agosto y septiembre de 2026, '
                        'en bolivianos y porcentaje?'],
    heldout_account=['¿Qué cuenta SAP fue primera por importe comercial de sulfato de cobre de 25 kg '
                     'en septiembre de 2026? No agrupes cuentas diferentes por nombre.'])


def semantics():
    if os.getenv('TEAM360_BUSINESS_SEMANTICS') != '1':
        return None, None
    from modules.business_semantics.resolver import BusinessConceptResolver, VectorCandidatePolicy
    from modules.business_semantics.embeddings import EmbeddingConfiguration, LiteLLMEmbeddingAdapter
    from modules.business_semantics.runtime_connection import RestrictedSemanticsConnection
    config = os.environ['TEAM360_SEMANTICS_AUTH_CONFIG']
    adapter = (LiteLLMEmbeddingAdapter(EmbeddingConfiguration.from_env())
               if os.getenv('TEAM360_SEMANTICS_EMBEDDING_ALIAS') else None)
    return (BusinessConceptResolver(embeddings=adapter, vector_policy=VectorCandidatePolicy.from_env()),
            RestrictedSemanticsConnection(config))


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
    report = dict(status='IN_PROGRESS', cases=[], transport='NONE', restarts=0,
                  conversation_store='PostgresConversationStore', recovery='real PG; fresh port each turn',
                  semantics='same conditional composition as assistant/composition.py',
                  source_sha256=dev.source_digest())
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+'\n')
    try:
        live_channel = ChannelContext(binding.channel_id, 'evolution', srv.evolution.instance,
            binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
        async with pool.connection() as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            identity = await PhoneIdentityRepository().resolve(conn, live_channel, settings.authorized_sender)
        assert identity and identity.user_id == approval['user_id']
        policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
            approval['module_enabled'], approval['whole_workspace_scope_verified'],
            pilot_user_id=approval['user_id'], pilot_approval_sha256=dev.approval_digest(approval),
            pilot_access_check=lambda: dev.unchanged_approval(approval_path, approval))
        resolver, restricted = semantics()
        report['semantics_enabled'] = resolver is not None
        luna = LunaInterpreter()
        await luna.interpret(text='¿Cuánto facturamos?', state=EMPTY, history={}, turn_id='preflight')
        report['provider_preflight'] = luna.last_metadata
        from modules.telchi.exploratory_sql.foundation import host_read_preflight
        report['host_preflight'] = host_read_preflight()
        save()
        for name in args.case or list(CASES):
            isolated = replace(binding, receiver_context='sufficiency-'+uuid4().hex)
            channel = replace(live_channel, receiver_context=isolated.receiver_context)
            for question in CASES[name]:
                message = replace(event(question, uuid4().hex), sender=settings.authorized_sender,
                                  recipients=(isolated.receiver_context,))
                async with pool.connection() as conn:
                    claimed = await MessagingRepository().claim(conn, isolated, message, {})
                assert claimed
                ctx = MessageContext(channel, identity, settings.authorized_sender,
                                     claimed['thread_id'], claimed['id'], frozenset())
                port = build_researcher(pool=pool, config=load_config())
                assert port is not None and port.recovery_repository is not None
                scope = await port._resolve_scope(identity)
                assert port._permitted(scope)
                reports = []
                original = port.evidence_sink_factory
                def factory():
                    sink = original()
                    def capture(evidence):
                        sink(evidence)
                        reports.append(evidence)
                    return capture
                port.evidence_sink_factory = factory
                failures = []
                class ObservedStore(PostgresConversationStore):
                    @asynccontextmanager
                    async def turn(self, context):
                        try:
                            async with super().turn(context) as turn:
                                yield turn
                        except Exception as exc:
                            failures.append(dict(type=type(exc).__name__, detail=str(exc)[:1000]))
                            raise
                handler = TelchiHandler(store=ObservedStore(pool),
                    authorization=BusinessAuthorization(policy), interpreter=luna, researcher=port,
                    concept_resolver=resolver, semantics_connection=restricted,
                    capabilities=SalesCapabilities(timeout_seconds=180), turn_timeout_seconds=300)
                started = perf_counter()
                answer = await handler.handle(message, ctx)
                elapsed = perf_counter()-started
                async with pool.connection() as conn:
                    await conn.execute('SET TRANSACTION READ ONLY')
                    audit = (await (await conn.execute(
                        "SELECT payload_jsonb->'telchi_assistant_v1' AS a FROM message_events WHERE id=%s",
                        (claimed['id'],))).fetchone())['a'] or {}
                    saved = await port.recovery_repository.load(conn, scope, ctx)
                summary = None
                if reports:
                    evidence = reports[-1]
                    summary = {k: evidence.get(k) for k in (
                        'status', 'reason', 'question_coverage', 'model_answer', 'controller_feedback',
                        'claim_verifications', 'model_calls', 'metrics', 'resource_accounting',
                        'model_events', 'host_preflight')}
                    summary['queries'] = [dict(sql=t.get('proposal', {}).get('sql'),
                        decision=t.get('decision'), result=t.get('result')) for t in evidence.get('turns', [])]
                report['cases'].append(dict(case=name, question=question, answer=answer.text,
                    classification=answer.classification, elapsed_seconds=round(elapsed, 3),
                    conversation_id=ctx.conversation_id, turn_id=ctx.correlation_id, audit=audit,
                    durable_state=saved['state'] if saved else None,
                    durable_results=len(saved['full_result']['results']) if saved and saved.get('full_result') else 0,
                    interpreter_metadata=luna.last_metadata, research_evidence=summary,
                    handler_failures=failures))
                save()
                if (summary or {}).get('reason') in {'execution_stopped:host_io_or_memory_pressure',
                                                       'host_io_or_memory_pressure'}:
                    report['status'] = 'RESOURCE_BLOCKED'
                    save()
                    break
                print(name, answer.classification, round(elapsed, 3),
                      (audit.get('research') or {}).get('status', audit.get('decision')), flush=True)
        report['status'] = 'EXECUTED_REQUIRES_BUSINESS_REVIEW'
        save()
    except Exception as exc:
        report.update(status='BLOCKED', reason=type(exc).__name__)
        save()
        raise
    finally:
        await close_pool(pool)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', action='append', choices=list(CASES))
    asyncio.run(main(parser.parse_args()))
