"""Restart-continuity probe: recover a durable Telchi conversation after a DEV restart.

Starts the DEV server, runs two turns, stops it, confirms the state is durable in
PostgreSQL, starts a new server instance and continues the same conversation.
Separates durable recovery, semantic continuity and execution accounting.
Does not replay an event: resend idempotency and the six operational gates remain
NOT_TESTED. Product mentions live in product_search_text, not necessarily entity.
A priority ("primero") must retain other requested metrics (luna.py contract).

Usage:
    uv run python -m modules.telchi.assistant.tests.runtime_http.restart_continuity --output <dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_battery as rb  # noqa: E402

def _persisted_state(conversation: str) -> dict:
    import globalVar
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(globalVar.get_team360_db_url_psql(), row_factory=dict_row) as conn:
        thread = conn.execute("""
            SELECT id, metadata_jsonb FROM message_threads
            WHERE contact_identity LIKE %s ORDER BY created_at_utc DESC LIMIT 1
            """, ('%#dev:' + conversation,)).fetchone()
        if not thread:
            return {}
        events = conn.execute("""
            SELECT count(*) AS n,
                   count(*) FILTER (WHERE payload_jsonb->'telchi_assistant_v1'->>'execution_status' = 'executed') AS executed
            FROM message_events WHERE thread_id=%s AND direction='inbound' AND event_type='message'
            """, (thread['id'],)).fetchone()
        saved = (thread['metadata_jsonb'] or {}).get('telchi_assistant_v1') or {}
        return dict(thread_id=str(thread['id']), state=saved.get('state'),
                    inbound_events=events['n'], executed_turns=events['executed'])


def _effective(state: dict) -> dict:
    return (state.get('pending') or {}).get('proposed') or state


def _record(result: dict, phase: str, text: str) -> dict:
    summary = rb._summary(result)
    summary['conversation_id'] = result['response'].get('conversation_id')
    return dict(phase=phase, user=text, summary=summary, raw=result)


def _execution_accounting(before: dict, after: dict, summaries: list[dict]) -> bool:
    """Count only new turns; executed before restart is not a duplicate.

    This is aggregate accounting, not proof of event-level resend idempotency.
    Missing counters/statuses must fail closed, not silently count as zero.
    """
    counts = [before.get('executed_turns'), after.get('executed_turns')]
    statuses = [s.get('execution_status') for s in summaries]
    return (all(type(n) is int and n >= 0 for n in counts)
            and all(s in {'executed', 'not_executed'} for s in statuses)
            and counts[1] - counts[0] == statuses.count('executed'))


def _checks(evidence: dict) -> dict:
    from modules.telchi.assistant import state_engine

    before, recovered, after = (evidence[k] for k in
                               ('after_stop', 'after_recovery', 'after_restart'))
    turns = evidence['turns']
    final = turns[-1]
    audit = final['raw']['response'].get('audit') or {}
    previous = audit.get('previous_state')
    proposal = audit.get('interpretation_proposed')
    confirmed = audit.get('confirmed_state') or {}
    known = _effective(before.get('state') or {})
    effective = _effective(confirmed)
    metrics = known.get('requested_metrics')
    # This scenario prioritizes amount; it does not withdraw quantity.
    expected = (['sales.net_amount'] + [m for m in metrics if m != 'sales.net_amount']
                if isinstance(metrics, list) and 'sales.net_amount' in metrics else None)
    replay = (state_engine.process(previous, proposal, {}, 'restart-contract-check')
              if isinstance(previous, dict) and isinstance(proposal, dict) else {})
    replay_state = _effective(replay.get('state_after') or {})
    thread = before.get('thread_id')
    ids = [t['summary'].get('conversation_id') for t in turns]
    return dict(
        persistence=dict(
            thread_recovered=bool(thread) and all(i == thread for i in ids)
                and recovered.get('thread_id') == after.get('thread_id') == thread,
            state_present=all(isinstance(s.get('state'), dict) and bool(s['state'])
                              for s in (before, recovered, after)),
            restart_snapshot_unchanged=bool(before) and recovered == before,
            handler_loaded_saved_state=bool(before.get('state')) and previous == before['state'],
            all_turns_committed=all(t['summary'].get('committed') is True
                                    and t['summary'].get('http_ok') is True for t in turns),
            inbound_count=before.get('inbound_events') == 2
                and after.get('inbound_events') == 3),
        semantics=dict(
            # Equality of absent fields alone is NOT product continuity evidence.
            product_context_preserved=bool(known.get('product_search_text'))
                and all(effective.get(k) == known.get(k) for k in
                        ('product_search_text', 'product_context', 'selected_item_codes')),
            entity_slot_preserved='entity_mention' in known
                and effective.get('entity_mention') == known['entity_mention'],
            priority_retains_metrics=expected is not None
                and effective.get('requested_metrics') == expected
                and effective.get('metric') == 'sales.net_amount',
            engine_matches_proposal=replay.get('committed') is True
                and all(replay_state.get(k) == effective.get(k)
                        for k in ('metric', 'requested_metrics', 'entity_mention', 'product_search_text')),
            unavailable_without_execution=final['summary'].get('classification') == 'DIRECT_UNAVAILABLE'
                and final['summary'].get('execution_status') == 'not_executed'),
        execution_accounting=dict(
            restart_did_not_execute=before.get('executed_turns') is not None
                and recovered.get('executed_turns') == before['executed_turns'],
            delta_matches_new_turns=_execution_accounting(before, after, [final['summary']])),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output_dir = Path(args.output)
    # Never overwrite an existing run's evidence (including server logs).
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error('--output must be an empty or new directory')
    output_dir.mkdir(parents=True, exist_ok=True)

    base_env = rb._load_env_file()
    phone = rb._pilot_phone('team360-meta-dev')
    metadata = rb._binding_metadata('telchi_dev', 'telchi_whatsapp_dev', 'team360-meta-dev')
    receiver = metadata.get('receiver_context', '')
    token = __import__('secrets').token_urlsafe(48)
    conversation = 'restart-continuity:' + __import__('datetime').datetime.now(
        __import__('datetime').timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    evidence = dict(conversation=conversation, transport='curl', turns=[])

    server1, base1 = rb.start_server(base_env, phone, receiver, rb._free_port(), token,
                                     output_dir / 'restart-server-1.log')
    try:
        for text in ['dame las ultimas ventas de calenta', 'las dos']:
            result = rb._curl_turn(base1, token, conversation, text)
            evidence['turns'].append(_record(result, 'before-restart', text))
    finally:
        rb.stop_server(server1)
    evidence['after_stop'] = _persisted_state(conversation)

    server2, base2 = rb.start_server(base_env, phone, receiver, rb._free_port(), token,
                                     output_dir / 'restart-server-2.log')
    try:
        # Read before the third turn, so restart recovery is not conflated with
        # an intentional conversational state transition.
        evidence['after_recovery'] = _persisted_state(conversation)
        text = 'primero dame el importe de las ventas del mes'
        result = rb._curl_turn(base2, token, conversation, text)
        evidence['turns'].append(_record(result, 'after-restart', text))
    finally:
        rb.stop_server(server2)
    evidence['after_restart'] = _persisted_state(conversation)

    evidence['checks'] = _checks(evidence)
    evidence['passed'] = all(v is True for group in evidence['checks'].values() for v in group.values())
    evidence['passed_scope'] = 'restart_persistence_semantics_execution_accounting_only'
    evidence['resend_idempotency'] = dict(status='NOT_TESTED',
        reason='No event resent; DEV HTTP creates a fresh event ID per request.')
    evidence['operational_gates'] = {name: dict(status='NOT_TESTED',
        reason='Not certified by this restart probe; requires independent real evidence.')
        for name in ('http_auth', 'identity_tenant_isolation', 'business_authorization',
                     'durable_idempotency', 'assistant_foundation', 'model_no_fallback')}
    (output_dir / 'restart_results.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'passed': evidence['passed'], 'checks': evidence['checks']}, indent=2))


if __name__ == '__main__':
    main()