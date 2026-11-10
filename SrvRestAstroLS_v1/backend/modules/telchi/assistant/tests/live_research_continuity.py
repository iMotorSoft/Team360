"""Replay audited turns with real PostgreSQL, handler and Luna; no transport.

The explicit --backfill flag links an exact legacy private report to its existing
recovery row. All handler/thread/audit replay writes are rolled back.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path

from psycopg.types.json import Jsonb
from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.messaging.handlers import ChannelContext, MessageContext
from modules.messaging.identity import PhoneIdentityRepository
from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, TelchiHandler, PostgresConversationStore
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.tests.test_assistant import event
from modules.telchi.console_http import load_config
from modules.telchi.research_port import build_researcher


async def replay(args):
    control = json.loads(args.control.read_text())
    os.environ.update(control['env'])
    approval_path = Path(control['approval'])
    approval = dev.read_approval(approval_path)
    srv, settings = dev.configuration()
    binding = await dev.check_database(approval, settings, srv.evolution)
    channel = ChannelContext(binding.channel_id, 'evolution', srv.evolution.instance,
        binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=3))
    await open_pool(pool)
    try:
        async with pool.connection() as conn:
            identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
            row = await (await conn.execute('SELECT thread_id::text,payload_jsonb FROM message_events WHERE id=%s',
                                            (args.research_turn,))).fetchone()
        assert identity and identity.user_id == approval['user_id']
        ctx = MessageContext(channel, identity, settings.authorized_sender, row['thread_id'], args.research_turn, frozenset())
        port = build_researcher(pool=pool, config=load_config())
        scope = await port._resolve_scope(identity)
        async with pool.connection() as conn:
            saved = await port.recovery_repository.load(conn, scope, ctx)
        assert saved and row['payload_jsonb']['telchi_assistant_v1']['decision'] == 'RESEARCH'
        await port.revalidate(ctx, saved['receipt'])
        trace = args.trace.read_bytes()
        report = json.loads(trace.splitlines()[-1])
        assert report['question'] == saved['question']
        assert report['business_answer'] == saved['result']['business_answer']
        assert str(report['snapshot']) == saved['receipt']['binding']['snapshot']
        assert report['publication'] == saved['receipt']['binding']['publication']
        full = dict(question=report['question'], evidence_manifests=report['evidence_manifests'],
            claim_verifications=report['claim_verifications'], results=[{k: t['result'].get(k) for k in
                ('query_id', 'schema', 'rows', 'truncated', 'status')} for t in report['turns'] if t.get('result')])
        if args.backfill:
            async with pool.connection() as conn:
                async with conn.transaction():
                    current = await port.recovery_repository.load(conn, scope, ctx)
                    assert current == saved  # preserve concurrent changes
                    current.update(full_result=full, evidence_sha256=sha256(trace).hexdigest())
                    await port.recovery_repository.save(conn, scope, ctx, current)
        else:
            assert saved.get('full_result') == full, 'Exact legacy result needs explicit --backfill'
        policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
            approval['module_enabled'], approval['whole_workspace_scope_verified'],
            pilot_user_id=approval['user_id'], pilot_approval_sha256=dev.approval_digest(approval),
            pilot_access_check=lambda: dev.unchanged_approval(approval_path, approval))
        class RecordingLuna(LunaInterpreter):
            received = []
            async def interpret(self, **kwargs):
                self.received.append(deepcopy(kwargs.get('result_context')))
                return await super().interpret(**kwargs)
        luna = RecordingLuna()
        # Provider/auth/credit preflight; no SQL engine or semantic retrieval.
        from modules.telchi.assistant.state_engine import EMPTY
        preflight = await luna.interpret(text='¿Cuánto facturamos?', state=EMPTY, history={}, turn_id='preflight')
        assert preflight['action'] == 'ASK'
        async def forbidden_investigation(*args, **kwargs):
            raise AssertionError('Must not repeat the investigation')
        port.service.ask_scope = forbidden_investigation
        result = dict(provider_preflight=luna.last_metadata, turns=[], whatsapp_sends=0,
                      investigation_calls=0, analytic_sql_executions=0,
                      route='TelchiHandler -> PostgresConversationStore -> ConversationRepository (real PostgreSQL)',
                      replay_writes='ROLLBACK', legacy_backfill=args.backfill,
                      evidence_sha256=sha256(trace).hexdigest())
        async with pool.connection() as conn:
            async with conn.transaction(force_rollback=True):
                class ReplayPool:
                    @asynccontextmanager
                    async def connection(self):
                        yield conn
                class NoQueries:
                    def __getattr__(self, name):
                        if name in {'execute', 'query'}:
                            raise AssertionError('Must reuse the persisted records')
                        from modules.telchi.assistant.capabilities import SalesCapabilities
                        return getattr(SalesCapabilities(), name)
                handler = TelchiHandler(store=PostgresConversationStore(ReplayPool()),
                    authorization=BusinessAuthorization(policy), interpreter=luna,
                    capabilities=NoQueries(), researcher=port)
                # Restore pre-CONTINUE thread state, without changing original evidence.
                thread = await (await conn.execute('SELECT metadata_jsonb FROM message_threads WHERE id=%s FOR NO KEY UPDATE',
                                                   (ctx.conversation_id,))).fetchone()
                metadata = deepcopy(thread['metadata_jsonb'])
                prior = metadata['telchi_assistant_v1']
                for ident in (args.continue_turn, args.followup_turn):
                    prior['history'].pop(ident, None)
                    prior['history_order'] = [k for k in prior['history_order'] if k != ident]
                prior['state'] = row['payload_jsonb']['telchi_assistant_v1']['confirmed_state']
                prior['result_reference'] = None
                await conn.execute('UPDATE message_threads SET metadata_jsonb=%s WHERE id=%s',
                                   (Jsonb(metadata), ctx.conversation_id))
                for ident in (args.continue_turn, args.followup_turn):
                    inbound = await (await conn.execute('SELECT payload_jsonb FROM message_events WHERE id=%s', (ident,))).fetchone()
                    question = inbound['payload_jsonb']['text']
                    await conn.execute("UPDATE message_events SET payload_jsonb=payload_jsonb-'telchi_assistant_v1' WHERE id=%s", (ident,))
                    answer = await handler.handle(event(question), replace(ctx, correlation_id=ident))
                    audit = (await (await conn.execute("SELECT payload_jsonb->'telchi_assistant_v1' AS a FROM message_events WHERE id=%s", (ident,))).fetchone())['a']
                    result['turns'].append(dict(question=question, answer=answer.text,
                        classification=answer.classification, audit=audit, model=luna.last_metadata))
                    print(question, answer.classification, answer.text, flush=True)
                result['followup_interpreter_context'] = luna.received[-1]
                assert len(luna.received[-1]['rows']) == 7
                assert result['turns'][1]['audit']['decision'] == 'SELECT_RESULT'
                assert result['turns'][1]['audit']['research']['sql_executions'] == 0
                assert result['turns'][1]['audit']['capability_calls'] == 0
                # Exact expected outcome belongs ONLY in this regression, not runtime.
                assert 'BATEBOL S.A.' in result['turns'][1]['answer']
                assert 'Bs 380,63' in result['turns'][1]['answer']
                # Replay also traverses cached-answer live authorization.
                cached = await handler.handle(event(result['turns'][1]['question']), replace(ctx, correlation_id=args.followup_turn))
                assert cached.text == result['turns'][1]['answer']
                result['cached_replay'] = 'PASS'
        result['pass'] = True
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as out:
            json.dump(result, out, ensure_ascii=False, indent=2, default=str)
    finally:
        await close_pool(pool)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('control', 'trace', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    for name in ('research-turn', 'continue-turn', 'followup-turn'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--backfill', action='store_true')
    asyncio.run(replay(parser.parse_args()))


if __name__ == '__main__':
    main()
