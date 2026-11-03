"""Deterministic layered evaluator for request-aware Compound Intent cases.

Four layers are scored independently and never merged:

1. ``source_ledger``          literal preservation of the original user message
2. ``request_extraction``     requested requirements vs gold (raw + canonical)
3. ``accepted_state``         accepted state/action vs gold
4. ``execution_eligibility``  allowed/blocked vs expected action (confusion matrix)

No provider calls, no SQL, no runtime imports. ``gold`` never enters the
candidate extraction path; this module only compares frozen records.
"""

from .canonicalize import atoms
from . import metrics


def _assertion_findings(intent, messages):
    """Check relations/claims stay unverified and literally grounded."""
    findings = []
    for kind in ('relations', 'claims'):
        items = intent.get(kind) or []
        for item in items:
            if not isinstance(item, dict):
                findings.append({'kind': kind, 'error': 'not_object'})
                continue
            if item.get('status') != 'USER_ASSERTED_UNVERIFIED':
                findings.append({'kind': kind, 'error': 'not_unverified', 'item': item})
                continue
            source = item.get('source_turn_id')
            evidence = item.get('evidence')
            if not isinstance(evidence, str) or not evidence:
                findings.append({'kind': kind, 'error': 'missing_evidence', 'item': item})
            elif source not in messages or evidence not in messages.get(source, ''):
                findings.append({'kind': kind, 'error': 'evidence_not_grounded', 'item': item})
    return findings


def evaluate_case(gold_case, candidate, messages=None):
    """Score one case across the four layers.

    ``candidate`` = {
        'turn_id', 'user_message', 'request_intent', 'accepted_intent',
        'allowed' (bool|None), 'sidecar_error' (str|None)
    }
    """
    messages = dict(messages or {})
    tid = gold_case['turn_id']
    messages.setdefault(tid, candidate.get('user_message') or gold_case['user_message'])

    literal_preserved = candidate.get('user_message') == gold_case['user_message']

    raw_extraction = metrics.score(gold_case['request_intent'], candidate.get('request_intent') or {},
                                   canonical=False)
    canon_extraction = metrics.score(gold_case['request_intent'], candidate.get('request_intent') or {},
                                     canonical=True)

    accepted_exact = None
    if gold_case.get('accepted_intent') is not None:
        accepted_exact = atoms(gold_case['accepted_intent']) == atoms(candidate.get('accepted_intent') or {})

    expected_execute = gold_case['expected_action'] == 'EXECUTE'
    allowed = candidate.get('allowed')
    if allowed is None:
        eligibility = {'outcome': 'NOT_RUN'}
    else:
        eligibility = {
            'outcome': 'TP' if allowed and expected_execute else
                       'FP' if allowed and not expected_execute else
                       'FN' if not allowed and expected_execute else 'TN',
            'expected_execute': expected_execute,
            'allowed': bool(allowed),
        }

    findings = _assertion_findings(candidate.get('request_intent') or {}, messages)
    return {
        'turn_id': tid,
        'group': gold_case['group'],
        'literal_preserved': literal_preserved,
        'request_raw': raw_extraction,
        'request_canonical': canon_extraction,
        'request_representation_is_sole_cause': metrics.representation_is_sole_cause(
            gold_case['request_intent'], candidate.get('request_intent') or {}),
        'accepted_state_exact': accepted_exact,
        'eligibility': eligibility,
        'assertion_findings': findings,
        'candidate_sidecar_error': candidate.get('sidecar_error'),
    }


def aggregate(results):
    """Aggregate layered results into benchmark metrics."""
    n = len(results)
    if not n:
        return {'turns': 0}
    raw_scores = [r['request_raw'] for r in results]
    canon_scores = [r['request_canonical'] for r in results]
    elig = [r['eligibility']['outcome'] for r in results]
    accepted = [r['accepted_state_exact'] for r in results if r['accepted_state_exact'] is not None]
    return {
        'turns': n,
        'literal_preservation': sum(r['literal_preserved'] for r in results),
        'literal_preservation_rate': sum(r['literal_preserved'] for r in results) / n,
        'request_raw': metrics.aggregate(raw_scores),
        'request_canonical': metrics.aggregate(canon_scores),
        'representation_sole_cause_turns': sum(r['request_representation_is_sole_cause'] for r in results),
        'accepted_state_scored_turns': len(accepted),
        'accepted_state_exact_turns': sum(bool(x) for x in accepted),
        'eligibility': {
            'TP': elig.count('TP'), 'FP': elig.count('FP'),
            'FN': elig.count('FN'), 'TN': elig.count('TN'),
            'NOT_RUN': elig.count('NOT_RUN'),
        },
        'assertion_findings': sum(len(r['assertion_findings']) for r in results),
        'sidecar_errors': sum(bool(r['candidate_sidecar_error']) for r in results),
    }