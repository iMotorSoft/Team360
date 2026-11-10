"""Reconcile the delivered L01 population against independently authored SQL.

Reads one live run, rebuilds the durable presentation of the recovered account
list from PG and compares it with the control query that never saw Luna SQL.
Evidence only: no service restart, no WhatsApp traffic, no new research.
"""
import argparse
import json
import os
from pathlib import Path

import psycopg

from modules.telchi.assistant.result_references import research_presentation


def load_environment(control):
    os.environ.update(json.loads(control.read_text())['env'])


def recovery_payload(conversation_id):
    with psycopg.connect(os.environ['TEAM360_DB_URL']) as connection:
        row = connection.execute(
            """SELECT id::text, payload_jsonb FROM core_events
               WHERE event_name='telchi.research.recovery'
                 AND payload_jsonb->>'conversation_id'=%s
               ORDER BY created_at_utc DESC LIMIT 1""", (conversation_id,)).fetchone()
    return dict(row[1], result_id=row[0]) if row else None


def control_accounts(independent):
    controls = json.loads(independent.read_text())['controls']
    control = next(c for c in controls if c['name'] == 'nitric_october_accounts')
    return {row['card_code'] for row in control['rows']}


def verify(run, independent, control):
    report = json.loads(run.read_text())
    first = report['cases'][0]
    verdict = dict(L01='BLOCKED', ACREDITED_ACCOUNTS=311, RECOVERED_ACCOUNTS=0, DUPLICATES=None,
                   DURABLE_RESULT='FAIL', FOLLOWUP_WITHOUT_RESEARCH='FAIL', BLOCKER=None)
    payload = recovery_payload(first['conversation_id'])
    if payload is None:
        verdict['BLOCKER'] = 'durable_payload_missing'
        return verdict, report
    full = payload['full_result']
    recovered = {key: value for key, value in (full.get('population_recovery') or {}).items()
                 if value.get('complete') and value.get('entity_column') == 'card_code'}
    if len(recovered) != 1:
        verdict['BLOCKER'] = 'no_single_recovered_account_population'
        return verdict, report
    key, recovery = next(iter(recovered.items()))
    verdict['RECOVERED_ACCOUNTS'] = recovery['recovered_records']
    verdict['RECOVERY_PAGES'] = recovery['pages']
    manifest = next((m for m in full['evidence_manifests'] if m['result_id'] == key), None)
    view = research_presentation(payload, first['audit']['owner'], first['conversation_id']) \
        if manifest else None
    if view is None:
        verdict['BLOCKER'] = 'durable_presentation_unavailable'
        return verdict, report
    codes = [row['card_code'] for row in view['rows']]
    verdict['DUPLICATES'] = len(codes) - len(set(codes))
    verdict['DURABLE_RECORDS'] = len(codes)
    verdict['DURABLE_NEXT_ORDINAL'] = view['next_ordinal']
    verdict['RECONCILED_WITH_INDEPENDENT_SQL'] = set(codes) == control_accounts(independent)
    continuation = report['cases'][1]
    verdict['FOLLOWUP_SQL_EXECUTIONS'] = continuation['audit'].get('research', {}).get('sql_executions')
    verdict['FOLLOWUP_WITHOUT_RESEARCH'] = ('PASS' if verdict['FOLLOWUP_SQL_EXECUTIONS'] == 0
                                            and continuation['classification'] == 'DIRECT_AVAILABLE' and
                                            continuation['answer'].lstrip().startswith(
                                                str(view['next_ordinal']) + '.') else 'FAIL')
    verdict['DURABLE_RESULT'] = ('PASS' if verdict['RECONCILED_WITH_INDEPENDENT_SQL']
                                 and verdict['DUPLICATES'] == 0 and len(codes) == 311 else 'FAIL')
    if (verdict['DURABLE_RESULT'] == 'PASS' and verdict['FOLLOWUP_WITHOUT_RESEARCH'] == 'PASS'
            and verdict['RECOVERED_ACCOUNTS'] == verdict['ACREDITED_ACCOUNTS']):
        verdict['L01'] = 'COMPLETE'
    else:
        verdict['BLOCKER'] = 'delivered_population_or_continuation_differs'
    return verdict, report


def semantic_closure(reconciliation):
    """Deterministic L01 labels from accredited accounting, not Luna prose.

    The 311 accounts are a union over the six accredited SKUs (at least one),
    never evidence that every account purchased all six. Population, calendar
    and business certification are independent dimensions.
    """
    complete = (reconciliation.get('RECONCILED_WITH_INDEPENDENT_SQL') is True
                and reconciliation.get('DUPLICATES') == 0
                and reconciliation.get('DURABLE_RESULT') == 'PASS'
                and reconciliation.get('ACREDITED_ACCOUNTS') == 311
                and reconciliation.get('RECOVERED_ACCOUNTS') == 311
                and reconciliation.get('DURABLE_RECORDS') == 311)
    return dict(SEMANTIC_OR='PASS',
                SEMANTIC_CONTRACT='AT_LEAST_ONE_ACCREDITED_SKU; NOT_EVERY_SKU_PER_ACCOUNT',
                POPULATION_COVERAGE='COMPLETE' if complete else 'NOT_CERTIFIED',
                TEMPORAL_COVERAGE='NOT_CERTIFIED',
                BUSINESS_INTERPRETATION='NOT_INDEPENDENTLY_CERTIFIED',
                BLOCKER=reconciliation.get('BLOCKER') if complete else 'population_reconciliation_not_accredited')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--independent', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args()
    load_environment(arguments.control)
    verdict, report = verify(arguments.run, arguments.independent, arguments.control)
    verdict.update(semantic_closure(verdict))
    verdict['run_status'] = report['status']
    verdict['question_coverage'] = report['cases'][0]['research_evidence']['question_coverage']
    text = json.dumps(verdict, indent=2, ensure_ascii=False, sort_keys=True)
    if arguments.output:
        arguments.output.write_text(text + '\n')
    print(text)


if __name__ == '__main__':
    main()