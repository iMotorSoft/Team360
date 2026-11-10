"""Live replay: a discovered customer becomes the subject of a new investigation.

Uses the real TelchiHandler, PostgreSQL conversation store/recovery, real Luna
and Foundation CURRENT. Handler writes are rolled back; the research recovery
row is read-only. No transport, service restart or message is sent.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

from psycopg.types.json import Jsonb

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.messaging.handlers import ChannelContext, MessageContext
from modules.messaging.identity import PhoneIdentityRepository
from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant.handler import (
    BusinessPolicy, BusinessAuthorization, TelchiHandler, PostgresConversationStore)
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.tests.test_assistant import event
from modules.telchi.console_http import load_config
from modules.telchi.research_port import build_researcher


async def replay(args):
    control = json.loads(args.control.read_text())
    import os
    os.environ.update(control['env'])
    approval_path = Path(control['approval'])
    approval = dev.read_approval(approval_path)
    srv, settings = dev.configuration()
    binding = await dev.check_database(approval, settings, srv.evolution)
    channel = ChannelContext(binding.channel_id, 'evolution', srv.evolution.instance,
        binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module,
        binding.environment)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=3))
    await open_pool(pool)
    try:
        async with pool.connection() as conn:
            identity = await PhoneIdentityRepository().resolve(conn, channel,
                settings.authorized_sender)
            research = await (await conn.execute(
                'SELECT thread_id::text,payload_jsonb FROM message_events WHERE id=%s',
                (args.research_turn,))).fetchone()
        assert identity and identity.user_id == approval['user_id']
        research_audit = research['payload_jsonb']['telchi_assistant_v1']
        assert research_audit['decision'] == 'RESEARCH'
        port = build_researcher(pool=pool, config=load_config())
        base = MessageContext(channel, identity, settings.authorized_sender,
            research['thread_id'], args.research_turn, frozenset())
        scope = await port._resolve_scope(identity)
        async with pool.connection() as conn:
            saved = await port.recovery_repository.load(conn, scope, base)
        assert saved and saved['state'] == 'COMPLETED'
        assert saved.get('full_result', {}).get('results')
        await port.revalidate(base, saved['receipt'])

        policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
            approval['module_enabled'], approval['whole_workspace_scope_verified'],
            pilot_user_id=approval['user_id'],
            pilot_approval_sha256=dev.approval_digest(approval),
            pilot_access_check=lambda: dev.unchanged_approval(approval_path, approval))
        luna = LunaInterpreter()

        async def forbidden_investigation(*args, **kwargs):
            raise AssertionError('Must not repeat the research or invoke free analysis')
        # The research turn already happened. Replaying it must not run it again.
        port.service.ask_scope = forbidden_investigation

        report = dict(
            route='TelchiHandler -> PostgresConversationStore -> ConversationRepository '
                  '(real PostgreSQL), real Luna, real Foundation CURRENT',
            research_turn=args.research_turn,
            select_turn=args.select_turn,
            investigate_turn=args.investigate_turn,
            replay_writes='ROLLBACK',
            whatsapp_sends=0,
            investigation_calls=0,
            turns=[])

        async with pool.connection() as conn:
            async with conn.transaction(force_rollback=True):
                class ReplayPool:
                    @asynccontextmanager
                    async def connection(self):
                        yield conn
                handler = TelchiHandler(
                    store=PostgresConversationStore(ReplayPool()),
                    authorization=BusinessAuthorization(policy),
                    interpreter=luna, researcher=port)
                thread = await (await conn.execute(
                    'SELECT metadata_jsonb FROM message_threads WHERE id=%s FOR NO KEY UPDATE',
                    (base.conversation_id,))).fetchone()
                metadata = deepcopy(thread['metadata_jsonb'])
                prior = metadata['telchi_assistant_v1']
                # Start again after the research answer, without its later turns.
                later = set(prior['history_order'])
                later.discard(args.research_turn)
                for ident in later:
                    prior['history'].pop(ident, None)
                prior['history_order'] = [args.research_turn] if args.research_turn in prior['history'] else []
                prior['state'] = deepcopy(research_audit['confirmed_state'])
                prior['result_reference'] = None
                prior['document_reference'] = None
                prior['reference_focus'] = 'result'
                prior['monetary_comparison'] = None
                await conn.execute('UPDATE message_threads SET metadata_jsonb=%s WHERE id=%s',
                                   (Jsonb(metadata), base.conversation_id))
                for ident in (args.select_turn, args.investigate_turn):
                    inbound = await (await conn.execute(
                        'SELECT payload_jsonb FROM message_events WHERE id=%s', (ident,))).fetchone()
                    assert inbound, ident
                    question = inbound['payload_jsonb']['text']
                    await conn.execute("UPDATE message_events "
                        "SET payload_jsonb=payload_jsonb-'telchi_assistant_v1' WHERE id=%s", (ident,))
                    answer = await handler.handle(event(question),
                        replace(base, correlation_id=ident))
                    audit = (await (await conn.execute(
                        "SELECT payload_jsonb->'telchi_assistant_v1' AS a FROM message_events "
                        "WHERE id=%s", (ident,))).fetchone())['a']
                    report['turns'].append(dict(
                        turn_id=ident, question=question, answer=answer.text,
                        classification=answer.classification,
                        decision=audit.get('decision'),
                        execution_status=audit.get('execution_status'),
                        capability_calls=audit.get('capability_calls'),
                        required_permission=audit.get('required_permission'),
                        interpretation_proposed=audit.get('interpretation_proposed'),
                        confirmed_state=audit.get('confirmed_state'),
                        parameters=(audit.get('execution_result') or {}).get('parameters'),
                        source=(audit.get('execution_result') or {}).get('source'),
                        rows=(audit.get('execution_result') or {}).get('rows'),
                        model=luna.last_metadata))
                    print(question, answer.classification, answer.text, flush=True)

                select, investigate = report['turns']
                assert select['decision'] == 'SELECT_RESULT'
                assert select['capability_calls'] == 0
                assert 'BATEBOL S.A.' in select['answer'] and 'Bs 380,63' in select['answer']
                state = investigate['confirmed_state']
                assert state['customer_target'] == 'C001077'
                assert state['group_by'] == 'sap_product'
                assert state['period'] == {'start': '2026-10-01', 'end_exclusive': '2026-11-01'}
                assert state.get('excluded_product') or state.get('excluded_products')
                assert 'excluyendo' in investigate['answer']
                assert investigate['decision'] == 'EXECUTE'
                assert investigate['execution_status'] == 'executed'
                assert investigate['capability_calls'] == 1
                assert investigate['required_permission'] == (
                    'telchi.sales.commercial_line_amount_by.read.v1')
                params = investigate['parameters']
                assert params['filters']['card_code'] == 'C001077'
                assert params['group_by'] == 'sap_product'
                assert params['date_from'] == '2026-10-01'
                assert params['date_to_exclusive'] == '2026-11-01'
                assert investigate['source']['publication_id']
                assert investigate['source']['snapshot_id']
                assert investigate['rows']
                assert 'No pude interpretar' not in investigate['answer']
                assert 'Bs ' in investigate['answer']
                report['provider_preflight'] = luna.last_metadata
                report['research_recovery'] = dict(
                    state=saved['state'], question=saved['question'],
                    binding=saved['receipt']['binding'],
                    full_result_results=len(saved['full_result']['results']))
        report['pass'] = True
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as out:
            json.dump(report, out, ensure_ascii=False, indent=2, default=str)
    finally:
        await close_pool(pool)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('control', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    for name in ('research-turn', 'select-turn', 'investigate-turn'):
        parser.add_argument('--' + name, required=True)
    asyncio.run(replay(parser.parse_args()))


if __name__ == '__main__':
    main()