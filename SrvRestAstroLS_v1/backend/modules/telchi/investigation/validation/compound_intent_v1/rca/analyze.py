"""Read-only differential audit of run01. Standard library; no model/runtime imports.

Writes only to the explicitly supplied NEW RCA output directory. Never re-runs V1.
Primary buckets are observable failure locations, not inferred model reasoning.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

IGNORED = {'pending_clarification', 'pending', 'intent', 'schema_version',
           'status', 'evidence', 'source_turn_id'}
EXTRAS = {'segments', 'granularities', 'geographies', 'relations', 'claims',
          'unresolved_requirements'}


def atoms(value):
    out = set()
    def visit(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                if k not in IGNORED:
                    visit(x, path + '/' + k)
        elif isinstance(v, list):
            for x in v:
                visit(x, path)
        elif v is not None and v != '':
            out.add((path, json.dumps(v, ensure_ascii=False, sort_keys=True)))
    visit(value, '')
    return out


def score(gold, value):
    g = atoms(gold)
    c = atoms({k: v for k, v in value.items() if k in gold})
    return {'exact': g == c, 'preserved': len(g & c), 'expected': len(g),
            'missing': sorted(g - c), 'unexpected': sorted(c - g)}


def end_keys(value):
    """Published diagnostic only: top-level time.periods, not comparison repair."""
    v = deepcopy(value)
    for period in (v.get('time') or {}).get('periods', []):
        if 'end' in period and 'end_exclusive' not in period:
            period['end_exclusive'] = period.pop('end')
    return v


def representation(value):
    """Restricted equivalences, scorer-only; no state/permission changes."""
    v = end_keys(value)
    if isinstance(v.get('sort'), dict):
        v['sort'] = [v['sort']]
    clauses = v.get('filters') or []
    for clause in clauses:
        for f in clause:
            if f.get('op') == 'in' and len(f.get('values', [])) == 1:
                f['op'] = 'eq'
    # ORs of equality on the SAME field equal one IN clause; no general DNF rewrite.
    if len(clauses) > 1 and all(len(c) == 1 and c[0].get('op') == 'eq' for c in clauses):
        fields = {c[0]['field'] for c in clauses}
        if len(fields) == 1:
            v['filters'] = [[dict(field=next(iter(fields)), op='in',
                                 values=[x for c in clauses for x in c[0]['values']])]]
    return v


def guard_reasons(row):
    """Mirror V1 plan_current predicates, returning ALL applicable reasons."""
    c = row['candidate_intent']
    s = row['candidate_plan']['state_engine']['state_after']
    reasons = []
    for k in ('dimensions', 'filters', 'segments', 'granularities', 'geographies',
              'relations', 'claims', 'unresolved_requirements', 'sort'):
        if c.get(k):
            reasons.append('blanket_nonempty:' + k)
    scope = c.get('scope')
    if scope is not None and not isinstance(scope, dict):
        reasons.append('scope_shape')
    if isinstance(scope, dict) and any(scope.get(k) for k in ('warehouse_ids', 'branch_ids')):
        reasons.append('nonempty_scope')
    if set(c.get('metrics', [])) - set(s.get('requested_metrics') or [s['metric']]):
        reasons.append('metric_not_in_plan')
    represented = dict(kind='PERIOD', as_of=None, periods=[s['period']]) if s['period'] else None
    if c.get('time') != represented:
        reasons.append('time_exact_dict_mismatch')
    if c.get('comparison') or c.get('reference'):
        reasons.append('comparison_or_reference_nonempty')
    if c.get('business_domain') not in (None, 'SALES'):
        reasons.append('domain_not_SALES')
    if c.get('limit') not in (None, s.get('limit', 10)):
        reasons.append('limit_mismatch')
    m = c.get('measure_context')
    if m is not None and not isinstance(m, dict):
        reasons.append('measure_context_shape')
    if isinstance(m, dict) and any(m.values()):
        reasons.append('measure_context_nonempty')
    if row['sidecar_error']:
        reasons.append('sidecar_error')
    return reasons


def audit(source, llmfit):
    rows = [json.loads(l) for l in (source / 'rows.jsonl').read_text().splitlines()]
    old_details = {x['id']: x for x in json.loads((source / 'errors_and_regressions.json').read_text())}
    manifest = json.loads((source / 'manifest.json').read_text())
    inputs = {}
    for name, expected in manifest['inputs'].items():
        # Relocatable LlmFit root while preserving manifest suffix.
        path = llmfit / name.split('/conversation_state_v1/', 1)[1]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, ('input_drift', str(path))
        inputs[str(path)] = actual
    data = json.loads((llmfit / 'dataset.json').read_text())
    frozen = {x['turn_id']: x for x in map(json.loads, (llmfit / 'hybrid_router_validation/LUNA_ONLY/turns.jsonl').read_text().splitlines())}
    raw = {r['id']: r for r in rows}
    previous = {}
    dataset_turns = {}
    for conv in data['conversations']:
        prev = None
        for turn in conv['turns']:
            dataset_turns[turn['turn_id']] = turn
            previous[turn['turn_id']] = prev
            prev = turn['turn_id']
    details = []
    simple_states = {}
    scorer_disagreements = []
    summary_exact_llmfit = 0
    counts = Counter()
    features = Counter()
    for row in rows:
        group, tid = row['group'], row['id']
        b, c, gold = row['baseline_intent'], row['candidate_intent'], row['gold']
        bs, cs = score(gold, b), score(gold, c)
        for arm, current in [('baseline', bs), ('candidate', cs)]:
            serial = json.loads(json.dumps(current))
            assert all(serial[k] == old_details[tid]['scores'][arm][k] for k in serial), (tid, arm)
        # Zero accepted rows changed extraction: nested shapes passed as inert JSON.
        assert row['candidate_call']['value']['requested_business_intent'] == c
        assert not row['sidecar_error'] and not row['candidate_call']['error']
        normalized = representation(c)
        norm_score = score(representation(gold), normalized)
        differing = sorted({p.split('/')[1] for p, _ in norm_score['missing'] + norm_score['unexpected']})
        reg = bs['exact'] and not cs['exact']
        roots = {p.split('/')[1] for p, _ in atoms(gold)}
        summary_exact = atoms(gold) == {(p, v) for p, v in atoms(c) if p.split('/')[1] in roots}
        if group == 'llmfit':
            summary_exact_llmfit += int(summary_exact)
            if summary_exact != cs['exact']:
                scorer_disagreements.append(tid)
        entry = dict(id=tid, group=group, message=row['text'], baseline_score=bs,
                     candidate_score=cs, end_only_score=score(gold, end_keys(c)),
                     representation_diagnostic_score=norm_score, regression=reg,
                     original_luna=row['baseline_call'], baseline_intent=b,
                     candidate_raw_extraction=row['candidate_call']['value'],
                     candidate_accepted_intent=c, gold=gold, residual_fields=differing,
                     extraction_equals_accepted=True, first_observable_divergence=(
                         'additional_model_output' if not cs['exact'] else None))
        if group == 'llmfit':
            base = frozen[tid]
            prev_id = previous[tid]
            entry.update(state_before=base['state_before'], original_luna=base['output'],
                         original_luna_raw=base['raw_output'], frozen_action=base['output']['action'],
                         frozen_plan=dict(committed=base['committed'], feedback=base['feedback'],
                                          delivered_results=base['delivered_results']),
                         previous_sidecar=raw[prev_id]['candidate_intent'] if prev_id else None,
                         previous_id=prev_id, candidate_state_engine_plan=None,
                         candidate_state_engine_plan_note='NOT_RUN; evaluate.replay_eligibility only')
            inherited = []
            propagated = []
            if prev_id:
                prev = raw[prev_id]
                for field in differing:
                    if atoms({field: gold[field]}) == atoms({field: prev['gold'].get(field)}):
                        inherited.append(field)
                        if atoms({field: normalized.get(field)}) == atoms({field: representation(prev['candidate_intent']).get(field)}):
                            propagated.append(field)
            entry.update(inherited_residual_fields=inherited, propagated_residual_fields=propagated)
            gate = []
            if any(c.get(k) for k in EXTRAS):
                gate.append('any_extra_facet')
            if atoms({k:v for k,v in b.items() if k not in {'intent','pending_clarification'}}) != atoms({k:v for k,v in c.items() if k not in EXTRAS}):
                gate.append('baseline_candidate_atom_inequality')
            eligible = bool(row['baseline_allowed'] and not gate)
            assert eligible == old_details[tid]['candidate_allowed']
            entry.update(baseline_allowed=row['baseline_allowed'], candidate_allowed=eligible,
                         guard_predicates=gate)
            bucket = None
            if reg:
                if entry['end_only_score']['exact']:
                    bucket = 'END_KEY_ONLY'
                elif norm_score['exact']:
                    bucket = 'OTHER_REPRESENTATION_ONLY'
                elif base['output']['action'] != 'EXECUTE':
                    bucket = 'REQUEST_VS_ACCEPTED_STATE_TARGET'
                elif tid.startswith('TCS_026_'):
                    bucket = 'RESULT_CONTEXT_NOT_SUPPLIED'
                elif propagated:
                    bucket = 'PROPAGATED_SIDECAR_DIVERGENCE'
                elif inherited:
                    bucket = 'INHERITED_FIELD_DIVERGENCE'
                else:
                    bucket = 'NEW_EXTRACTION_DIVERGENCE'
                counts[bucket] += 1
                if any('/end_exclusive' in p for p, _ in cs['missing']):
                    features['missing_end_exclusive'] += 1
                if inherited:
                    features['inherited_field_divergence'] += 1
                if propagated:
                    features['propagated_field_divergence'] += 1
                if base['output']['action'] != 'EXECUTE':
                    features['non_execute_gold_target'] += 1
                for field in differing:
                    features['residual_field:' + field] += 1
            entry['primary_observable_bucket'] = bucket
        else:
            cid = tid if group == 'abraham' else tid.split('_')[0]
            empty = dict(metric=None, period=None, branches=[], sales_channel=None,
                         comparison=None, reference=None, pending=None)
            before = deepcopy(simple_states.get(cid, empty))
            simple_states[cid] = deepcopy(row['candidate_plan']['state_engine']['state_after'])
            entry.update(state_before=before, state_before_method='reconstructed from EMPTY and prior frozen plan',
                         candidate_plan=row['candidate_plan'], guard_predicates=guard_reasons(row),
                         baseline_allowed=row['baseline_allowed'], candidate_allowed=row['candidate_allowed'])
            assert row['candidate_allowed'] == bool(row['baseline_allowed'] and not entry['guard_predicates'])
        details.append(entry)
    assert len(rows) == 114
    assert sum(counts.values()) == 86
    summary = dict(primary_86_regressions=dict(counts), overlapping_features=dict(features),
                   input_hashes=inputs, rows_sha256=hashlib.sha256((source/'rows.jsonl').read_bytes()).hexdigest(),
                   all_raw_extractions_equal_accepted=True, provider_calls=0,
                   summary_vs_detail_exact_disagreements=scorer_disagreements,
                   candidate_summary_exact_llmfit=summary_exact_llmfit,
                   candidate_detail_exact_llmfit=sum(x['candidate_score']['exact'] for x in details if x['group']=='llmfit'),
                   groups={g:dict(turns=sum(x['group']==g for x in details),
                       baseline_exact=sum(x['baseline_score']['exact'] for x in details if x['group']==g),
                       candidate_exact=sum(x['candidate_score']['exact'] for x in details if x['group']==g),
                       regressions=sum(x['regression'] for x in details if x['group']==g),
                       baseline_allowed=sum(x['baseline_allowed'] for x in details if x['group']==g),
                       candidate_allowed=sum(x['candidate_allowed'] for x in details if x['group']==g))
                       for g in ('llmfit','simple','abraham')})
    return summary, details


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--llmfit', type=Path, required=True, help='conversation_state_v1 directory')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert args.output.resolve() != args.source.resolve()
    summary, details = audit(args.source, args.llmfit)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary.json', summary), ('turn_differentials.json', details)]:
        target = args.output / name
        if target.exists():
            assert json.loads(target.read_text()) == value, 'Refusing to overwrite different evidence'
        else:
            target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
