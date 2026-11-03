"""Replay persisted analytical evidence with current verification code; no live I/O.

Replay IDs are explicitly distinct from the original execution IDs. Original
claims and digests remain in the audit; no historic trace is rewritten.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path

from .adaptive_sources import context_for_run
from .adaptive_verifier import reconstruct
from .claim_evidence import EvidenceRegistry
from .contracts import Column, ExploratoryQueryResult, ExploratoryQueryProposal, CandidateRelation, TypedParameter
from .foundation import START, END
from .foundation_dev import DevBudget
from .research import code_digest
from .validator import validate


def decode_result(raw):
    value = dict(raw)
    value['schema'] = tuple(Column(**c) for c in value['schema'])
    value['rows'] = tuple(tuple(r) for r in value['rows'])
    for key in ('evidence', 'limitations', 'aggregates'):
        value[key] = tuple(value[key])
    return ExploratoryQueryResult(**value)


def decode_proposal(raw):
    value = dict(raw)
    value['requested_budget'] = DevBudget(**value['requested_budget'])
    value['candidate_relations'] = tuple(CandidateRelation(**r) for r in value['candidate_relations'])
    value['parameters'] = tuple(TypedParameter(**(r | {'value': Decimal(r['value'])} if r['sql_type'] == 'DECIMAL(18,2)' else r)) for r in value['parameters'])
    return ExploratoryQueryProposal(**value)


def replay(report):
    context = context_for_run()
    tables, summary = reconstruct(context, [decode_result(r['result']) for r in report['reference_queries']])
    registry = EvidenceRegistry(context, tables, (START, END))
    mapping = {}
    for turn in report['turns']:
        old = turn['model_observation'].get('evidence_manifest')
        if not old: continue
        _, query = validate(decode_proposal(turn['proposal']), context)
        if query is None or query.query_id != turn['authorized']['query_id']:
            raise ValueError('replay_query_binding_mismatch')
        new = registry.register(query, decode_result(turn['result']), tuple(tuple(r) for r in turn['model_observation']['rows']))
        mapping[old['result_id']] = old, new
    def translate(claim):
        value = dict(claim)
        if 'dependencies' in value: value['dependencies'] = [translate(d) for d in value['dependencies']]
        if value.get('result_id') in mapping:
            old, new = mapping[value['result_id']]
            value['result_id'] = new['result_id']
            if value.get('row_id') in old['row_ids']:
                value['row_id'] = new['row_ids'][old['row_ids'].index(value['row_id'])]
            indexes = [i for i, c in enumerate(old['columns']) if c['column_id'] == value.get('column_id')]
            if indexes: value['column_id'] = new['columns'][indexes[0]]['column_id']
        return value
    checks = [registry.verify(translate(c['claim'])) for c in report['claim_verifications']]
    return dict(original_code_digest=report['code_digest'], claim_count=len(checks), checks=checks,
        independent_summary=summary, business_answer=registry.render(checks),
        original_claims=[c['claim'] for c in report['claim_verifications']])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('traces', nargs='+')
    args = p.parse_args()
    audit = dict(mode='OFFLINE_ARTIFACT_REPLAY_NO_FOUNDATION_IO', code_digest=code_digest(), runs={})
    for name in args.traces:
        path = Path(name)
        audit['runs'][path.name] = replay(json.loads(path.read_text()))
    with Path(args.output).open('x') as f:
        f.write(json.dumps(audit, ensure_ascii=False, indent=2, default=str)+'\n')
    print({k: [len(v['checks']), sum(c['match'] for c in v['checks'])] for k, v in audit['runs'].items()})


if __name__ == '__main__': main()
