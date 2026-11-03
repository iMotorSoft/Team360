"""Recompute the frozen V1 baseline metrics under the stable measurement contract.

Read-only over ``data/reports/telchi/compound_intent_v1/run01``. No provider, SQL,
Foundation, server or runtime call. It does not re-run V1 and does not repair any
candidate output; it only re-scores the immutable stored rows.

Reproduce from ``SrvRestAstroLS_v1/backend`` as a module::

    uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.recompute_baseline \\
      --source ../../../data/reports/telchi/compound_intent_v1/run01 \\
      --output ../../../data/reports/telchi/compound_intent_v2_benchmark
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from . import metrics
from .canonicalize import EQUIVALENCES, atoms, end_key_only


def load_rows(source):
    return [json.loads(line) for line in (Path(source) / 'rows.jsonl').read_text().splitlines()]


def _end_key_score(gold, intent):
    g = atoms(gold)
    c = atoms({k: v for k, v in end_key_only(intent).items() if k in metrics.INTENT_FIELDS})
    return {'set_exact': g == c, 'preserved': len(g & c)}


def _score_pair(row, arm):
    gold = row['gold']
    intent = row[arm + '_intent']
    return {
        'raw': metrics.score(gold, intent, canonical=False),
        'canonical': metrics.score(gold, intent, canonical=True),
        'end_key_only': _end_key_score(gold, intent),
        'legacy_recall_family_exact': metrics.recall_family_exact(gold, intent),
        'legacy_gold_keys_exact': metrics.gold_keys_exact(gold, intent),
    }


def recompute(rows):
    report = {
        'criteria': {
            'universe': list(metrics.INTENT_FIELDS),
            'equivalences': list(EQUIVALENCES),
            'primary_regression_predicate': 'canonical SET_EXACT (no missing, no added, full field universe)',
            'secondary_predicate': 'canonical RECALL_COMPLETE (no missing atom)',
        },
        'resolution_12_vs_10': {
            'legacy_summarize_exact_llmfit': None,
            'legacy_raw_score_exact_llmfit': None,
            'disagreeing_turn_ids': [],
            'explanation': (
                'run.summarize filters candidate atoms to gold-populated field families, '
                'so facets added in gold-empty families are invisible (12). '
                'evaluate.raw_score restricts candidate atoms to gold top-level keys, so '
                'facets added in empty-but-present fields are visible (10). '
                'The stable contract reports both as named predicates and uses SET_EXACT as primary.'
            ),
        },
        'groups': {},
    }
    for group in ('llmfit', 'simple', 'abraham'):
        subset = [r for r in rows if r['group'] == group]
        entry = {'turns': len(subset)}
        for arm in ('baseline', 'candidate'):
            scores = [_score_pair(r, arm) for r in subset]
            entry[arm] = {
                'raw_full_set_exact_turns': sum(s['raw']['set_exact'] for s in scores),
                'raw_full_recall_complete_turns': sum(s['raw']['recall_complete'] for s in scores),
                'raw_preserved_atoms': sum(s['raw']['preserved'] for s in scores),
                'canonical_full_set_exact_turns': sum(s['canonical']['set_exact'] for s in scores),
                'canonical_full_recall_complete_turns': sum(s['canonical']['recall_complete'] for s in scores),
                'canonical_preserved_atoms': sum(s['canonical']['preserved'] for s in scores),
                'expected_atoms': sum(s['canonical']['expected'] for s in scores),
                'legacy_recall_family_exact_turns': sum(s['legacy_recall_family_exact'] for s in scores),
                'legacy_gold_keys_exact_turns': sum(s['legacy_gold_keys_exact'] for s in scores),
                'end_key_only_preserved_atoms': sum(s['end_key_only']['preserved'] for s in scores),
                'end_key_only_set_exact_turns': sum(s['end_key_only']['set_exact'] for s in scores),
            }
        base = [_score_pair(r, 'baseline') for r in subset]
        cand = [_score_pair(r, 'candidate') for r in subset]
        raw_regressions, canonical_regressions, representation_recovered = [], [], []
        for r, b, c in zip(subset, base, cand):
            raw_reg = b['raw']['set_exact'] and not c['raw']['set_exact']
            canon_reg = b['canonical']['set_exact'] and not c['canonical']['set_exact']
            if raw_reg:
                raw_regressions.append(r['id'])
            if canon_reg:
                canonical_regressions.append(r['id'])
            if raw_reg and not canon_reg:
                representation_recovered.append(r['id'])
        entry['raw_regressions'] = raw_regressions
        entry['canonical_regressions'] = canonical_regressions
        entry['representation_recovered_regressions'] = representation_recovered
        entry['genuine_canonical_regressions'] = canonical_regressions
        recovered = [r['id'] for r, c in zip(subset, cand)
                     if c['canonical']['set_exact'] and not c['raw']['set_exact']]
        entry['turns_recovered_by_representation_normalization'] = len(recovered)
        entry['recovered_turn_ids'] = recovered
        report['legacy_diagnostics'] = report.get('legacy_diagnostics', {})
        if group == 'llmfit':
            report['legacy_diagnostics'] = {
                'end_key_only_preserved_atoms': entry['candidate']['end_key_only_preserved_atoms'],
                'canonical_preserved_atoms': entry['candidate']['canonical_preserved_atoms'],
                'raw_preserved_atoms': entry['candidate']['raw_preserved_atoms'],
                'expected_atoms': entry['candidate']['expected_atoms'],
                'end_key_only_set_exact_turns': entry['candidate']['end_key_only_set_exact_turns'],
                'canonical_set_exact_turns': entry['candidate']['canonical_full_set_exact_turns'],
                'raw_set_exact_turns': entry['candidate']['raw_full_set_exact_turns'],
                'note': 'end-key-only and canonical are scorer-side diagnostics, not repaired candidate outputs.',
            }
        report['groups'][group] = entry

    llm = [r for r in rows if r['group'] == 'llmfit']
    family = [r['id'] for r in llm if metrics.recall_family_exact(r['gold'], r['candidate_intent'])]
    keys = [r['id'] for r in llm if metrics.gold_keys_exact(r['gold'], r['candidate_intent'])]
    report['resolution_12_vs_10']['legacy_summarize_exact_llmfit'] = len(family)
    report['resolution_12_vs_10']['legacy_raw_score_exact_llmfit'] = len(keys)
    report['resolution_12_vs_10']['disagreeing_turn_ids'] = sorted(set(family) ^ set(keys))
    return report


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(args):
    source = Path(args.source)
    rows = load_rows(source)
    report = recompute(rows)
    report['source'] = str(source)
    report['rows_sha256'] = _digest(source / 'rows.jsonl')
    report['provider_calls'] = 0
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'baseline_metrics.json'
    payload = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if target.exists() and target.read_text() != payload:
        raise SystemExit('refuse to overwrite different existing baseline_metrics.json')
    target.write_text(payload)
    print(json.dumps({
        'resolution_12_vs_10': report['resolution_12_vs_10'],
        'llmfit': report['groups']['llmfit'],
        'simple': report['groups']['simple'],
    }, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    main(parser.parse_args())