"""Isolated in-process acceptance probe; no live configuration or WhatsApp writes.

Consumes the READY policy candidate from prepare.py. Uses real RBAC, Foundation,
Luna and existing PostgreSQL research audit. Raw evidence stays private.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time
from uuid import uuid4

from psycopg_pool import AsyncConnectionPool

from modules.console.repositories import PermissionConsoleRepository
from modules.db.settings import get_database_settings
from modules.telchi.console_http import AccreditedReader, evidence_sink
from modules.telchi.exploratory_sql.authorized_foundation import EffectiveScope, SourcePolicy
from modules.telchi.exploratory_sql.console_bridge import ConsoleResearchService
from modules.telchi.exploratory_sql.console_repository import ResearchConsoleRepository
from modules.telchi.exploratory_sql.foundation import host_read_preflight
from modules.telchi.exploratory_sql.research import LunaSQL
from .prepare import ORG, WORKSPACE, write_new

QUESTIONS = (
    '¿Qué clientes compraron soda cáustica x25 kg en octubre de 2026, pero no en septiembre?',
    '¿Cuánto representan esas ventas y cuáles fueron los principales clientes?',
)


async def probe(candidate):
    config = json.loads(candidate.read_text())
    assert config['state'] == 'READY_NOT_ACTIVE'
    assert (config['organization'], config['workspace']) == (ORG, WORKSPACE)
    directory = candidate.parent / ('probe-' + uuid4().hex)
    directory.mkdir(mode=0o700)
    summary = dict(mode='ISOLATED_IN_PROCESS_NOT_RUNTIME_ACTIVATION', turns=[],
                   whatsapp_sent=0, configuration_activated=False, services_restarted=0,
                   persistence='REAL_PG_AUTHORIZATION_AUDIT; CONVERSATION_IN_MEMORY; NO_PERSISTENT_RESUME',
                   durable_execution='FAIL', six_gates='DEGRADED')
    try:
        summary['host_preflight'] = host_read_preflight()
        if not summary['host_preflight']['safe']:
            raise RuntimeError('RESOURCE_BLOCKED')
        luna = LunaSQL(system='Return exactly one JSON object: {"ready":true}. No tools or SQL.')
        answer = await luna.next({'task': 'minimal real provider preflight'}, timeout=45)
        assert answer == {'ready': True}
        metadata = [{k: v for k, v in c.items() if k not in ('output_text', 'output_messages')}
                    for c in luna.calls]
        summary['model_preflight'] = metadata
        async with AsyncConnectionPool(get_database_settings().dsn, min_size=1, max_size=2,
                                       open=False, kwargs={'connect_timeout': 5}) as pool:
            await pool.wait(timeout=10)
            identities, permissions = ResearchConsoleRepository(), PermissionConsoleRepository()

            async def resolve():
                async with pool.connection() as conn:
                    async with conn.transaction():
                        identity = await identities.identity(conn, config['user_id'])
                        if not identity or (identity['organization'], identity['workspace']) != (ORG, WORKSPACE):
                            raise RuntimeError('identity_out_of_scope')
                        effective = await permissions.list_effective_permissions(conn, WORKSPACE, config['user_id'])
                        enabled = await identities.enabled_permissions(conn, WORKSPACE)
                        return EffectiveScope(config['user_id'], ORG, WORKSPACE, frozenset(effective) & enabled)

            service = ConsoleResearchService(pool=pool, public_keys_by_id={}, organization=ORG,
                workspace=WORKSPACE, policies=tuple(SourcePolicy(**p) for p in config['policies']),
                reader=AccreditedReader(config['foundation_publication_id']), enabled=True, environment='dev')
            conversation = 'devfull-acceptance-' + uuid4().hex
            for number, question in enumerate(QUESTIONS, 1):
                started = time.monotonic()
                report = await service.ask_scope(resolve, question, evidence_sink(directory),
                    progress=lambda event: None, conversation_id=conversation)
                write_new(directory / f'turn-{number}.json', report)
                calls = report.get('model_calls', [])
                turns = report.get('turns', [])
                result = dict(turn=number, elapsed_seconds=round(time.monotonic()-started, 3),
                    status=report.get('status'), reason=report.get('reason'),
                    model_calls=len(calls), model_preflight_calls=len(report.get('model_preflight_calls', [])),
                    sql_attempts=len(turns),
                    sql_executions=sum(t.get('result', {}).get('status') == 'COMPLETED' for t in turns),
                    timing=report.get('timing', {}),
                    model_input_max_bytes=max(report.get('model_input_sizes', [0])),
                    claim_checks=len(report.get('claim_verifications', [])),
                    claim_checks_matched=sum(c.get('match') is True for c in report.get('claim_verifications', [])),
                    catalog_discoveries=report.get('catalog_discoveries', []),
                    business_answer_present=bool(report.get('business_answer')),
                    previous_messages=len(report.get('conversation', [])),
                    fallback=any(c.get('fallback') is not False for c in calls))
                summary['turns'].append(result)
                print(json.dumps(result), flush=True)
    except Exception as exc:
        # Transport exceptions can contain credentials; never persist arbitrary exception text.
        summary['abort'] = type(exc).__name__
        raise
    finally:
        write_new(directory / 'summary.json', summary)
        print('PRIVATE_EVIDENCE=' + str(directory), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    summary = asyncio.run(probe(args.candidate))
    if (len(summary['turns']) != 2 or any(t['status'] == 'BLOCKED' or not t['model_calls']
                                         or not t['sql_executions'] for t in summary['turns'])):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
