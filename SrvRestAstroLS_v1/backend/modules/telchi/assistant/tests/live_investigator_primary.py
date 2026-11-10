"""Opt-in sequential comparison of the existing direct and integrated researcher.

Backend: uv run python -m modules.telchi.assistant.tests.live_investigator_primary
 --control PRIVATE.json --output NEW_DIRECTORY --reference diagnostic/comparison.json
No transports, listeners, policy/grant changes or service restarts. MemoryStore
is intentional: durable guarantees need separate regression tests, not this probe.
"""
import argparse
import asyncio
from dataclasses import asdict, replace
from hashlib import sha256
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
from modules.telchi.exploratory_sql.contracts import DevResearchBudget
from .test_assistant import MemoryStore, event, latest


async def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    control = json.loads(args.control.read_text())
    os.environ.update(control['env'])
    approval_path = Path(control['approval'])
    approval = dev.read_approval(approval_path)
    srv, settings = dev.configuration()
    channel_binding = await dev.check_database(approval, settings, srv.evolution)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=3))
    await open_pool(pool)
    evidence = dict(status='IN_PROGRESS', runs=[], budget=asdict(DevResearchBudget()),
        transport='NONE', restarts=0, policy_changes=0, conversation_store='MemoryStore',
        limitation='No durable worker or WhatsApp delivery exercised; separate regressions required.')
    def write(name, value):
        (args.output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n')
    try:
        channel = ChannelContext(channel_binding.channel_id, 'evolution', srv.evolution.instance,
            channel_binding.receiver_context, channel_binding.tenant_id, channel_binding.workspace_id,
            channel_binding.module, channel_binding.environment)
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
        luna = LunaInterpreter()
        await luna.interpret(text='¿Cuánto facturamos?', state=EMPTY, history={}, turn_id='preflight')
        evidence['provider_preflight'] = luna.last_metadata
        from modules.telchi.exploratory_sql.foundation import host_read_preflight
        evidence['host_preflight'] = host_read_preflight()
        questions = json.loads(args.reference.read_text())['questions'] + [
            'En agosto de 2026, en BS y sin documentos anulados, ¿cuántas notas de crédito hubo y cuál fue su importe documental total? No necesito facturas ni ventas netas.',
            '¿Cuál es la primera y última fecha observada de facturas de compra en cada fuente autorizada que las publique? Separá las fuentes; no sumes poblaciones posiblemente superpuestas ni lo interpretes como cobertura completa.',
        ]
        if getattr(args, 'questions', None):
            questions = json.loads(args.questions.read_text())
        evidence['questions'] = questions
        if args.controls_only:
            port = build_researcher(pool=pool, config=load_config())
            assert port is not None
            scope = await port._resolve_scope(identity)
            loop = asyncio.get_running_loop()
            def fresh():
                return asyncio.run_coroutine_threadsafe(port._resolve_scope(identity), loop).result(timeout=10)
            specs = json.loads(args.control_specifications.read_text()) if getattr(args, 'control_specifications', None) else None
            result = await asyncio.to_thread(independent_controls, port.service.reader, fresh, port.policies, specs)
            assert await port._resolve_scope(identity) == scope
            write('independent.json', result)
            return
        for number, question in enumerate(questions, 1):
            for route in getattr(args, 'routes', ('direct', 'integrated')):
                host = host_read_preflight()
                port = build_researcher(pool=pool, config=load_config())
                assert port is not None
                port.recovery_repository = None
                scope = await port._resolve_scope(identity)
                assert port._permitted(scope)
                scope_hash = sha256(json.dumps(asdict(scope), sort_keys=True, default=lambda x: sorted(x)).encode()).hexdigest()
                reports = []
                factory = port.evidence_sink_factory
                def capture_factory():
                    sink = factory()
                    def capture(report):
                        sink(report)
                        reports.append(report)
                        write(f'q{number}-{route}-research.json', report)
                    return capture
                port.evidence_sink_factory = capture_factory
                conversation = str(uuid4())
                context = MessageContext(channel, identity, settings.authorized_sender, conversation, str(uuid4()), frozenset())
                started = perf_counter()
                if route == 'direct':
                    report = await port(question, conversation, context)
                    row = dict(status=report.get('status'), answer=report.get('business_answer'), audit=None)
                else:
                    store = MemoryStore()
                    handler = TelchiHandler(store=store, authorization=LiveAuthorization(policy),
                        interpreter=luna, researcher=port, turn_timeout_seconds=300)
                    response = await handler.handle(event(question), context)
                    row = dict(classification=response.classification, answer=response.text,
                        audit={k:v for k,v in latest(store).items() if k != 'owner'},
                        interpreter_metadata=luna.last_metadata)
                report = reports[-1] if reports else {}
                row.update(question=number, route=route, scope_sha256=scope_hash,
                    host=host, elapsed_seconds=perf_counter()-started,
                    research_status=report.get('status'), publication=report.get('publication'),
                    snapshot=report.get('snapshot'), question_coverage=report.get('question_coverage'),
                    model_calls=len(report.get('model_calls', [])),
                    sql_attempts=len(report.get('turns', [])),
                    sql_completed=sum(t.get('result', {}).get('status') == 'COMPLETED' for t in report.get('turns', [])))
                evidence['runs'].append(row)
                write('comparison.json', evidence)
                print(number, route, row.get('research_status'), round(row['elapsed_seconds'],2), flush=True)
        evidence['status'] = 'EXECUTED_REQUIRES_BUSINESS_REVIEW'
        write('comparison.json', evidence)
    except BaseException as exc:
        evidence.update(status='ABORTED', reason=type(exc).__name__)
        write('comparison.json', evidence)
        raise
    finally:
        await close_pool(pool)


def independent_controls(reader, fresh_scope, policies, specifications=None):
    """Validation only: raw authorized populations, Python Decimal/sets, no LLM.

    Three fixed diagnostic controls, never a runtime query or answer path.
    Do not add header money across line-grain ap_invoice duplicates.
    """
    from collections import defaultdict
    from decimal import Decimal
    import threading
    from modules.telchi.exploratory_sql.authorized_foundation import open_binding
    from modules.telchi.exploratory_sql.validator import identifier
    binding, gaps = open_binding(reader=reader, resolve_scope=fresh_scope,
        policies=policies, investigation_id=str(uuid4()))
    result = dict(publication=binding.context.publication, snapshot=binding.context.snapshot,
        method='Raw authorized columns; streamed rows; Python Decimal/set controls; 5s per source, one thread, 512MiB',
        sources={})
    try:
        specifications = specifications or [dict(source=source, start=start, end=end)
            for source, start, end in [('credit_memo_document', '2026-08-01', '2026-09-01'),
                ('ap_invoice', '2026-10-01', '2026-10-16'), ('observed_ap_invoice', '2026-10-01', '2026-10-16')]]
        for spec in specifications:
            source = spec['source']
            binding.check()
            table = next(t for t in binding.context.catalog.tables if t.name == source)
            available = {c.name for c in table.columns}
            columns = [c for c in ('doc_entry', 'doc_date', 'canceled', 'currency', 'doc_cur',
                                  'doc_total', 'card_code', 'card_name') if c in available]
            h = sha256()
            count = 0
            first = last = None
            scoped = {}
            scoped_dates = set()
            keys = set()
            with reader.connector.session(read_only=True) as db:
                access = reader.resolve_on(db)
                assert access.foundation_publication_id == binding.context.publication
                db.execute("SET threads=1")
                db.execute("SET memory_limit='512MB'")
                timer = threading.Timer(5, db.interrupt)
                timer.start()
                try:
                    cursor = db.execute('SELECT ' + ','.join(identifier(c) for c in columns)
                                        + ' FROM ' + binding.projections[source])
                    while rows := cursor.fetchmany(1000):
                        for raw in rows:
                            count += 1
                            h.update(json.dumps(raw, default=str).encode())
                            row = dict(zip(columns, raw))
                            keys.add(str(row['doc_entry']))
                            day = str(row['doc_date'])[:10] if row['doc_date'] is not None else None
                            if day:
                                first = min(first or day, day)
                                last = max(last or day, day)
                            start, end = spec['start'], spec['end']
                            if (day and start <= day < end and row['canceled'] == 'N'
                                    and row.get('currency', row.get('doc_cur')) == 'BS'):
                                scoped_dates.add(day)
                                key = str(row['doc_entry'])
                                value = (row.get('card_code'), row.get('card_name'), str(row['doc_total']))
                                assert key not in scoped or scoped[key] == value, 'inconsistent_header'
                                scoped[key] = value
                finally:
                    timer.cancel()
                    timer.join()
            groups = defaultdict(lambda: [Decimal(0), 0, set()])
            for code, name, amount in scoped.values():
                groups[code][0] += Decimal(amount)
                groups[code][1] += 1
                if name:
                    groups[code][2].add(name)
            result['sources'][source] = dict(raw_rows=count, raw_sha256=h.hexdigest(),
                first_date=first, last_date=last, distinct_keys=len(keys), scope=spec,
                scoped_first_date=min(scoped_dates, default=None), scoped_last_date=max(scoped_dates, default=None),
                scoped_documents=len(scoped),
                scoped_amount=str(sum((Decimal(v[2]) for v in scoped.values()), Decimal(0))),
                top_suppliers=[dict(code=code, amount=str(v[0]), invoices=v[1], names=sorted(v[2]))
                    for code,v in sorted(groups.items(), key=lambda kv: (-kv[1][0], kv[0]))[:3]])
        binding.check()
        from modules.telchi.exploratory_sql.contracts import ExploratoryQueryProposal, Decision
        from modules.telchi.exploratory_sql.validator import validate
        result['security_probes'] = []
        for sql, sources in (
            ('SELECT count(*) AS n FROM forbidden_internal', ('forbidden_internal',)),
            ('DELETE FROM credit_memo_document', ('credit_memo_document',)),
            ("SELECT count(*) AS n FROM read_parquet('/etc/passwd')", ()),
        ):
            proposal = ExploratoryQueryProposal(sql, 'negative_control', 'validation only',
                sources, 'aggregate', 'must not execute')
            decision, query = validate(proposal, binding.context)
            assert query is None and decision.decision != Decision.ALLOW
            result['security_probes'].append(dict(decision=decision.decision, reason=decision.reason,
                                                  executed=False))
        return result
    finally:
        binding.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--controls-only', action='store_true')
    parser.add_argument('--control-specifications', type=Path, help='Validation-only raw source/date controls; never sent to Luna')
    parser.add_argument('--questions', type=Path, help='Explicit focused questions, without appending historical cases')
    parser.add_argument('--routes', nargs='+', choices=('direct', 'integrated'), default=['direct', 'integrated'])
    asyncio.run(main(parser.parse_args()))
