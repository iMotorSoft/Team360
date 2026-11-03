"""Reproduce the fourteen legacy rejections without alias whitelists or live I/O."""
from dataclasses import fields
import json

from .adaptive_sources import context_for_run
from .adaptive_verifier import reconstruct, verify_claim
from .contracts import Column, ExploratoryQueryResult
from .claim_evidence import expression_label


def diagnose(report):
    context = context_for_run()
    results = []
    for entry in report['reference_queries']:
        value = dict(entry['result'])
        value['schema'] = tuple(Column(**c) for c in value['schema'])
        value['rows'] = tuple(tuple(r) for r in value['rows'])
        results.append(ExploratoryQueryResult(**{k: v for k, v in value.items() if k in {f.name for f in fields(ExploratoryQueryResult)}}))
    tables, _ = reconstruct(context, results)
    output = []
    for number, check in enumerate(report['claim_verifications'], 1):
        if check['state'] != 'UNVERIFIED': continue
        turn = 2 if 5 <= number <= 12 else 1
        trace = report['turns'][turn-1]
        # Reuse the persisted admitted AST, never infer lineage from alias spelling.
        node = json.loads(trace['authorized']['admitted_tree_json'])['statements'][0]['node']
        mapping = {e['alias'] or e['column_names'][-1]: e['column_names'][-1]
                   for e in node['select_list'] if e['class'] == 'COLUMN_REF'}
        claim = check['claim']
        canonical_filters = {mapping.get(k, k): v for k, v in claim['filters'].items()}
        repaired = dict(claim, filters=canonical_filters)
        independent = verify_claim(repaired, tables['sales_operation'])
        output.append(dict(number=number, original_claim=claim, supporting_turn=turn,
            supporting_sql=trace['proposal']['sql'], aliases={k: mapping.get(k) for k in claim['filters']},
            real_fields=canonical_filters,
            metric_expression=next(expression_label(e) for e in node['select_list'] if e['alias'] == claim['metric']),
            semantic_limit=('NULL is absence of a published value, not the official code UNCLASSIFIED.' if number <= 12 else
                'CONFIRMED is the published status, not evidence for classifier causality.' if number <= 14 else
                'SUPPORTED is not CONFIRMED; this group cannot be presented as fully confirmed.'),
            count_semantics=('COUNT counts non-null source keys, not distinct documents. Independent key completeness validates it as line_count.' if claim['metric'] == 'line_count' else
                'SUM(line_total) is commercial line money BS, not header total, net billing or collections.'),
            rejection=check['reason'], classification='STRUCTURAL_ALIAS_BINDING',
            numeric_correct=independent.get('match'), independently_reconstructed_value=independent.get('expected'),
            business_interpretation=('Correct only as current published commercial line amount/count for this exact group. '
                'No causal claim, official classifier rule, historical completeness or whole-brand scope is accredited.'),
            provenance_ambiguity=('The same aliases in turn 4 refer to COALESCE calculations, not direct source values. '
                'Without result identity this claim cannot distinguish turns 1/2 from turn 4.'),
            required_behavior='Reject ambiguous legacy binding, return structured feedback; require issued result/column/group IDs.'))
    return output


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('trace')
    args = p.parse_args()
    with open(args.trace) as f:
        print(json.dumps(diagnose(json.load(f)), ensure_ascii=False, indent=2))
