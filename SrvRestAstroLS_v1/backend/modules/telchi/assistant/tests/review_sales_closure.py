"""Independent observable comparisons for the existing fifteen-case battery.

Not a semantic PASS generator: final business verdicts require SQL/scope and
coverage review in matrix.tsv. No old live answers are loaded.
"""
import argparse
import csv
import json
import re
from decimal import Decimal
from pathlib import Path


def money(value):
    return format(Decimal(str(value)), ',.2f').replace(',', '_').replace('.', ',').replace('_', '.')


def run(root):
    baseline = list(csv.DictReader((root.parent/'sales-reliability-v1/matrix.tsv').open(), delimiter='\t'))
    live = json.loads((root/'live-frozen.json').read_text())
    control = json.loads((root/'independent-sql.json').read_text())
    controls = {c['name']: c['rows'] for c in control['controls']}
    by_question = {c['question']: (i, c) for i, c in enumerate(live['cases'])}
    checks = []
    def record(ident, name, passed, **details):
        checks.append(dict(id=ident, check=name, passed=bool(passed), **details))
    def get(ident):
        question = next(b['pregunta'] for b in baseline if b['id'] == ident)
        i, c = by_question[question]
        return c
    for ident, name in [('P01', 'sulfate25_ranking'), ('F01', 'nitric_ranking'), ('H01', 'soda1_heldout_ranking')]:
        expected = controls[name][0]
        c = get(ident)
        record(ident, 'observed_leader_and_amount_delivered', expected['card_code'] in c['answer'] and money(expected['amount']) in c['answer'], expected=expected)
    for ident, name in [('E01', 'soda25_exclusion'), ('H02', 'sulfate25_exclusion_heldout')]:
        expected = controls[name]
        answer = get(ident)['answer']
        codes = set(re.findall(r'card_code=([^,\s]+)', answer))
        record(ident, 'exact_account_set_delivered', codes == {r['card_code'] for r in expected}, delivered=sorted(codes), expected=expected)
        if ident == 'H02':
            record(ident, 'all_amounts_delivered', all(money(r['amount']) in answer for r in expected))
    c = get('E02')
    expected = controls['soda25_exclusion'][0]
    record('E02', 'durable_minimum_without_sql', expected['card_code'] in c['answer'] and money(expected['amount']) in c['answer'] and c['audit'].get('research', {}).get('sql_executions') == 0, expected=expected)
    for sku in [r['item_code'] for r in controls['soda_universe']]:
        expected = controls['quantity_'+sku][0]
        answer = get('Q01')['answer']
        record('Q01', 'independent_quantity_leader_'+sku, sku in answer and expected['card_code'] in answer and money(expected['quantity']) in answer, expected=expected)
    for ident, name, hidden in [
        ('R01', 'global_products_2026-10', set()),
        ('G01', 'global_products_2026-10', {controls['global_products_2026-10'][0]['item_code']}),
        ('G02', 'global_products_2026-09', {controls['global_products_2026-10'][0]['item_code']}),
        ('C01', 'customer_products_2026-10', set()),
        ('C02', 'customer_products_2026-10', {controls['customer_products_2026-10'][0]['item_code']}),
        ('C03', 'customer_products_2026-09', {controls['customer_products_2026-10'][0]['item_code']}),
    ]:
        c = get(ident)
        expected = [r for r in controls[name] if r['item_code'] not in hidden]
        displayed = re.findall(r'^(?:\d+\. )?([A-Z][A-Za-z0-9_.-]+) ·', c['answer'], re.M)
        record(ident, 'ordered_page_codes_and_amounts', bool(displayed) and displayed == [r['item_code'] for r in expected[:len(displayed)]] and all(money(r['amount']) in c['answer'] for r in expected[:len(displayed)]), delivered=displayed, expected=expected[:len(displayed)])
        result = c['audit'].get('execution_result') or {}
        total = result.get('total', {}).get('amount')
        record(ident, 'unchanged_universe_total', total is not None and Decimal(total) == sum((Decimal(r['amount']) for r in controls[name]), Decimal(0)), expected_total=str(sum((Decimal(r['amount']) for r in controls[name]), Decimal(0))), actual_total=total)
    # List controls intentionally do not equate count delivery with enumeration.
    for ident, name in [('L01', 'nitric_october_accounts'), ('C04', 'customer_products_two_months')]:
        c = get(ident)
        record(ident, 'independent_population', True, count=len(controls[name]), durable_results=c['durable_results'], classification=c['classification'], delivery_guard=c['audit'].get('delivery_guard'))
    for ident in [b['id'] for b in baseline]:
        c = get(ident)
        record(ident, 'no_transport_guard_omissions', c['audit'].get('delivery_guard') is None, answer_characters=len(c['answer']))
    c = get('L01')
    lists = [(q['result'] or {}) for q in c['research_evidence']['queries']
             if len((q['result'] or {}).get('rows', [])) == 100
             and 'card_code' in [s['name'] for s in (q['result'] or {}).get('schema', [])]]
    if len(lists) == 1:
        result = lists[0]
        names = [s['name'] for s in result['schema']]
        observed = [dict(zip(names, row)) for row in result['rows']]
        expected = controls['nitric_october_accounts'][:100]
        record('L01', 'recovered_prefix_is_exact_but_not_the_universe',
               [r['card_code'] for r in observed] == [r['card_code'] for r in expected],
               universe=len(controls['nitric_october_accounts']), recovered=len(observed),
               unrecovered=len(controls['nitric_october_accounts'])-len(observed))
    c = get('C04')
    lists = [(q['result'] or {}) for q in c['research_evidence']['queries']
             if len((q['result'] or {}).get('rows', [])) == len(controls['customer_products_two_months'])]
    record('C04', 'full_product_population_retained_including_hidden_reference', len(lists) == 1)
    if len(lists) == 1:
        result = lists[0]
        names = [s['name'] for s in result['schema']]
        observed = [dict(zip(names, row)) for row in result['rows']]
        amount_key = next(k for k in names if 'amount' in k)
        actual = {r['item_code']: Decimal(r[amount_key]) for r in observed}
        expected = {r['item_code']: Decimal(r['amount']) for r in controls['customer_products_two_months']}
        record('C04', 'all_durable_product_amounts_independently_equal', actual == expected)
    for case, ident, expected, key in [
        ('list', 'L01', controls['nitric_october_accounts'][3:8], 'card_code'),
        ('display_customer', 'C04', controls['customer_products_two_months'][10:15], 'item_code'),
    ]:
        page = next(c for c in live['cases'] if c['case'] == case and c['question'].startswith('Mostrame los siguientes'))
        shown = re.findall(key + r': ([^,\s]+)', page['answer'])
        record(ident, 'durable_continuation_exact_and_without_sql', shown == [r[key] for r in expected]
               and page['audit'].get('research', {}).get('sql_executions') == 0,
               shown=shown, expected=[r[key] for r in expected])
    expected_publication = control['foundation']['foundation_publication_id']
    expected_snapshot = str(control['foundation']['ducklake_snapshot_id'])
    for b in baseline:
        c = get(b['id'])
        source = ((c['audit'].get('execution_result') or {}).get('source')
                  or c['audit'].get('result_provenance') or c['audit'].get('research') or {})
        publication = source.get('publication_id', source.get('publication'))
        snapshot = source.get('snapshot_id', source.get('snapshot'))
        record(b['id'], 'same_independently_pinned_publication_snapshot',
               publication == expected_publication and str(snapshot) == expected_snapshot,
               publication=publication, snapshot=snapshot)
    output = dict(publication=control['foundation']['foundation_publication_id'], snapshot=control['foundation']['ducklake_snapshot_id'], checks=checks,
                  meaning='Numeric/prefix/control observations only; business verdict and predicate review are in the single comparative matrix.',
                  cases=[dict(id=b['id'], evidence='live-frozen.json#/cases/'+str(by_question[b['pregunta']][0])) for b in baseline])
    (root/'comparison.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    print('Checks:', len(checks), 'not satisfied:', sum(not c['passed'] for c in checks))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('../../data/reports/telchi/sales-reliability-closure-v1'))
    run(parser.parse_args().root)
