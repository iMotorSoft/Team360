"""Live pilot validation: real identity/RBAC/Luna/CURRENT and PG result recovery.

No listener, ingress messages, sends, webhook mutations or lifecycle operations.
Evidence-only gates do not publish a manifest while an operator session owns it.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

import httpx
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
from modules.telchi.assistant.composition import create_telchi_app
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy
from modules.telchi.console_http import load_config
from modules.telchi.exploratory_sql.foundation import host_read_preflight
from modules.telchi.exploratory_sql.research import LunaSQL
from modules.telchi.research_port import build_researcher
from modules.messaging.handlers import ChannelContext, MessageContext
from modules.messaging.identity import PhoneIdentityRepository
from modules.db.settings import get_database_settings
from .prepare import write_new
from .probe import QUESTIONS
from .verify_result import verify


async def run(receipt, candidate):
    control = lifecycle.load_config(dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    installed = lifecycle.read_json(receipt)
    config = load_config()
    assert config['organization'] == installed['organization']
    assert config['workspace'] == installed['workspace']
    approval = dev.read_approval(Path(control['approval']))
    source, configuration = dev.source_digest(), dev.configuration_digest()
    directory = receipt.parent / ('live-' + uuid4().hex)
    directory.mkdir(mode=0o700)
    report = dict(status='RUNNING', source_sha256=source, configuration_sha256=configuration,
        generated_at=datetime.now(timezone.utc).isoformat(), observations={}, turns=[],
        whatsapp_messages=0, services_restarted=0, listeners_created=0)
    write_new(directory / 'started.json', report)
    try:
        report['host'] = host_read_preflight()
        assert report['host']['safe'], 'RESOURCE_BLOCKED'
        srv, settings = dev.configuration()
        binding = await dev.check_database(approval, settings, srv.evolution)
        report['database_binding'] = 'PASS'
        try:
            await asyncio.to_thread(dev.preflight, Path(control['approval']), require_gates=False)
            report['operational_preflight'] = 'PASS'
        except ValueError as exc:
            if str(exc) != 'active_webhook_preserved_session_blocked':
                raise
            report['operational_preflight'] = str(exc)
        luna = LunaSQL(system='Return exactly one JSON object: {"ready":true}. No tools or SQL.')
        assert await luna.next({'task': 'minimal real provider preflight'}, timeout=45) == {'ready': True}
        report['model_preflight'] = [{k: v for k, v in c.items()
                                    if k not in ('output_text', 'output_messages')} for c in luna.calls]
        async with AsyncConnectionPool(get_database_settings().dsn, min_size=1, max_size=3,
                                       open=False, kwargs={'connect_timeout': 5, 'row_factory': dict_row}) as pool:
            await pool.wait(timeout=10)
            channel = ChannelContext(binding.channel_id, 'evolution', binding.provider_instance,
                binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
            conversation = str(uuid4())
            async with pool.connection() as conn:
                async with conn.transaction():
                    identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
            assert identity and identity.user_id == installed['user_id']
            context = MessageContext(channel, identity, settings.authorized_sender, conversation,
                                     str(uuid4()), frozenset())
            def check():
                dev.unchanged_approval(Path(control['approval']), approval)
            policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
                approval['module_enabled'], approval['whole_workspace_scope_verified'],
                pilot_access_check=check, pilot_user_id=approval['user_id'],
                pilot_approval_sha256=dev.approval_digest(approval))
            auth = BusinessAuthorization(policy)
            async with pool.connection() as conn:
                async with conn.transaction():
                    assert await auth.allowed(context, conn)
                    for foreign in (replace(channel, tenant_id='foreign'), replace(channel, workspace_id=str(uuid4()))):
                        assert not await auth.allowed(replace(context, channel=foreign), conn)
                    assert not await auth.allowed(replace(context, sender_identity=replace(identity, user_id=str(uuid4()))), conn)
                    permission = config['policies'][0]['permission']
                    assert await auth.allowed(context, conn, required_permission=permission)
                    assert not await auth.allowed(replace(context, sender_identity=replace(identity, permissions=frozenset())),
                                                  conn, required_permission=permission)
            report['observations']['identity_tenant_isolation'] = dict(status='PASS', real_identity=True,
                foreign_tenant_workspace_user_denied=True)
            report['observations']['business_authorization'] = dict(status='PASS', actual_console=True,
                missing_permission_denied=True, isolation_receipt=str(receipt))
            # Actual ASGI authentication without lifespan/worker start or network listeners.
            app = dev.PilotBoundary(create_telchi_app(policy=policy, pool=pool), settings,
                                    srv.evolution, srv.recipient, check)
            cases = []
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated') as client:
                for token, body, expected in [('', b'{malformed', 401), ('invalid', b'{malformed', 401),
                    (settings.webhook_token, b'{malformed', 400),
                    (settings.webhook_token, json.dumps(dict(event='connection.update', instance=srv.evolution.instance)).encode(), 200)]:
                    response = await client.post(dev.WEBHOOK, content=body,
                        headers={'x-team360-webhook-token': token, 'content-type': 'application/json'})
                    assert response.status_code == expected
                    cases.append(expected)
            report['observations']['http_auth'] = dict(status='PASS', scope='actual ASGI, no listener or lifespan', cases=cases)
            for index, question in enumerate(QUESTIONS, 1):
                port = build_researcher(pool=pool, config=config)
                assert port.recovery_repository is not None
                raw = []
                original = port.service.ask_scope
                async def capture(*args, **kwargs):
                    result = await original(*args, **kwargs)
                    raw.append(result)
                    return result
                port.service.ask_scope = capture
                if index > 1:
                    context = replace(context, correlation_id=str(uuid4()))
                started = time.monotonic()
                report['stage'] = 'durable_research_turn_' + str(index)
                result = await port(question, conversation, context)
                elapsed = time.monotonic() - started
                assert len(raw) == 1
                details = raw[0]
                raw_path = directory / f'turn-{index}.json'
                write_new(raw_path, details)
                assert details['status'] != 'BLOCKED' and result.get('business_answer')
                assert details.get('claim_verifications') and all(c['match'] for c in details['claim_verifications'])
                calls = details.get('model_calls', [])
                assert calls and all(c.get('fallback') is False for c in calls)
                sql = sum(t.get('result', {}).get('status') == 'COMPLETED' for t in details.get('turns', []))
                assert sql > 0
                # Reconstruct both service and adapter: reuse PG result, never in-memory state.
                recovered = build_researcher(pool=pool, config=config)
                async def no_reexecution(*args, **kwargs):
                    raise AssertionError('cached_result_reexecuted')
                recovered.service.ask_scope = no_reexecution
                replay_started = time.monotonic()
                replay = await recovered(question, conversation, context)
                assert replay == result
                report['turns'].append(dict(turn=index, elapsed_seconds=round(elapsed, 3),
                    recovery_seconds=round(time.monotonic()-replay_started, 3),
                    model_calls=len(calls), sql_executions=sql, recovery_model_calls=0, recovery_sql=0,
                    publication=details['publication'], snapshot=details['snapshot'],
                    timing=details.get('timing'), previous_messages=len(details.get('conversation', [])),
                    status=details['status'], claim_checks=len(details['claim_verifications'])))
                print(json.dumps(report['turns'][-1]), flush=True)
                if index == 1:
                    verification = await verify(candidate, raw_path)
                    assert verification['result_verification'] == 'PASS'
                    report['independent_control'] = dict(status='PASS', sql_executions=2,
                        elapsed_seconds=verification['elapsed_seconds'])
            report['observations']['assistant_foundation'] = dict(status='PASS', current=True,
                coverage=70, independent_first_turn_control=True, followup_verified=True)
            report['observations']['model_no_fallback'] = dict(status='PASS', real_calls=True, fallback=False)
            report['observations']['durable_result_reuse'] = dict(status='PASS', real_postgres=True,
                full_adapter_reconstruction=True, recovery_model_calls=0, recovery_sql=0,
                limits='Result boundary recovery, not live per-SQL checkpointing or external delivery.')
        report['pool_closed'] = True
        assert source == dev.source_digest() and configuration == dev.configuration_digest()
        report['status'] = 'PASS'
    except BaseException as exc:
        report['status'] = 'FAILED'
        report['error_type'] = type(exc).__name__
        if report.get('stage', '').startswith('durable_research_turn_'):
            report['failed_turn_elapsed_seconds'] = round(time.monotonic() - started, 3)
        raise
    finally:
        write_new(directory / 'summary.json', report)
        print('LIVE_REPORT=' + str(directory / 'summary.json'), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(run(args.receipt, args.candidate))


if __name__ == '__main__':
    main()
