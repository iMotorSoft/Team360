"""Objective gates to authorize or reject a future passive Compound Intent V2.

No implementation is authorized here. This module only encodes the decision
rules so a promotion cannot rest on a metric whose definition is unsettled.

Hard preconditions (any failure => INSUFFICIENT_EVIDENCE, never AUTHORIZE):

* gold must be independently certified (``gold_status == CERTIFIED``)
* the candidate arm must have been measured on frozen, sealed cases

Behavioural gates (all must hold on the frozen corpus + known controls + holdout):

* literal preservation = 100%
* zero new authorizations and zero new blocks on known-valid plans
* accepted state/action and reference lineage unchanged
* request set-exact and recall-complete not below the stable baseline
* zero assertion certifications
* zero additional LLM calls for the minimal design
* proposed local overhead within budget (p95 <= 50 ms and <= 2% of baseline p95)
"""

INDEPENDENT_GOLD = 'CERTIFIED'

BEHAVIOURAL_GATES = (
    ('literal_preservation', 'literal preservation must be 100%',
     lambda m: m['literal_preservation_rate'] == 1.0),
    ('no_new_authorizations', 'no new capability/authorization may appear',
     lambda m: m.get('new_authorizations', 0) == 0),
    ('no_new_blocks', 'no known-valid plan may become blocked',
     lambda m: m.get('new_blocks_on_known_valid', 0) == 0),
    ('accepted_state_unchanged', 'accepted state/action must be unchanged',
     lambda m: m.get('accepted_state_changed', 0) == 0),
    ('request_set_exact_not_regressed', 'request SET_EXACT must not fall below baseline',
     lambda m: m['request_canonical']['set_exact_turns'] >= m['baseline_request_set_exact_turns']),
    ('request_recall_not_regressed', 'request RECALL_COMPLETE must not fall below baseline',
     lambda m: m['request_canonical']['recall_complete_turns'] >= m['baseline_request_recall_turns']),
    ('no_assertion_certification', 'no user assertion may be certified',
     lambda m: m.get('assertion_findings', 0) == 0),
    ('no_extra_llm_calls', 'the minimal passive design must add zero LLM calls',
     lambda m: m.get('additional_llm_calls', 0) == 0),
    ('overhead_budget', 'local overhead p95 <= 50 ms and <= 2% of baseline p95',
     lambda m: m.get('overhead_p95_ms', 0) <= 50.0 and m.get('overhead_pct_p95', 0) <= 2.0),
)


def authorize(candidate, gold_status, baseline_status='FROZEN'):
    """Return an objective decision for a future V2 experiment.

    ``candidate`` carries aggregated layered metrics plus localization fields.
    """
    preconditions = [
        {'gate': 'independent_gold', 'ok': gold_status == INDEPENDENT_GOLD,
         'detail': 'gold_status=' + str(gold_status)},
        {'gate': 'frozen_baseline', 'ok': baseline_status == 'FROZEN',
         'detail': 'baseline_status=' + str(baseline_status)},
    ]
    if not all(p['ok'] for p in preconditions):
        return {'decision': 'INSUFFICIENT_EVIDENCE',
                'preconditions': preconditions, 'gates': [],
                'reason': 'gold is not independently certified or baseline is not frozen'}

    gates = []
    for name, detail, predicate in BEHAVIOURAL_GATES:
        try:
            ok = bool(predicate(candidate))
        except (KeyError, TypeError):
            ok = False
        gates.append({'gate': name, 'ok': ok, 'detail': detail})
    decision = 'AUTHORIZE' if all(g['ok'] for g in gates) else 'REJECT'
    return {'decision': decision, 'preconditions': preconditions, 'gates': gates,
            'reason': 'all behavioural gates satisfied' if decision == 'AUTHORIZE'
            else 'one or more behavioural gates failed'}