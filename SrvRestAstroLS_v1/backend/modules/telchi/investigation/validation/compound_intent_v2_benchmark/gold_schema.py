"""Gold schema for request-aware Compound Intent evaluation.

The legacy gold encoded only an accepted state. For ASK/BLOCK turns that hides
everything the user requested but the interpreter did not accept. This schema
keeps four provenance classes apart and refuses to certify anything that cannot
be grounded:

``CURRENT_REQUEST``            expressed by the current user message
``INHERITED_CONTEXT``          carried from the previously accepted state
``USER_ASSERTED_UNVERIFIED``   user claim, never a certified fact
``VERIFIED_EVIDENCE``          backed by an explicit recorded evidence id

Grounding rule: an atom may not exist in gold without literal evidence. The
schema is deliberately unable to express "the model probably meant".
"""

from copy import deepcopy
import json
from pathlib import Path

from .canonicalize import atoms

PROVENANCE = (
    'CURRENT_REQUEST',
    'INHERITED_CONTEXT',
    'USER_ASSERTED_UNVERIFIED',
    'VERIFIED_EVIDENCE',
)
STATUS = ('CERTIFIED', 'PROVISIONAL', 'PENDING_ADJUDICATION')
INDEPENDENCE = (
    'HUMAN_INDEPENDENT',
    'MODEL_ASSISTED_PROVISIONAL',
    'MACHINE_DERIVED_LEGACY',
)
ACTIONS = ('EXECUTE', 'ASK', 'BLOCK')
REQUIREMENT_CATEGORIES = (
    'metric', 'entity_product', 'segment_geography', 'temporal_periodicity',
    'relation', 'negation', 'correction', 'reference', 'assertion', 'ambiguity',
    'non_executable',
)

CASE_FIELDS = (
    'turn_id', 'group', 'conversation_id', 'turn_index', 'user_message',
    'independence', 'request_intent', 'accepted_intent', 'expected_action',
    'requirements', 'verified_evidence', 'ambiguities', 'non_executable', 'notes',
)
REQUIRED_CASE_FIELDS = (
    'turn_id', 'group', 'conversation_id', 'turn_index', 'user_message',
    'independence', 'request_intent', 'expected_action', 'requirements',
)


def _require(condition, code, detail=''):
    if not condition:
        raise ValueError(code + (':' + detail if detail else ''))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def validate_case(case, messages=None):
    """Validate one gold case. ``messages`` optionally maps turn_id -> text."""
    _require(isinstance(case, dict), 'gold_not_object')
    _require(set(case) <= set(CASE_FIELDS), 'unknown_case_field', ','.join(sorted(set(case) - set(CASE_FIELDS))))
    for field in REQUIRED_CASE_FIELDS:
        _require(field in case, 'missing_case_field', field)
    _require(isinstance(case['turn_id'], str) and case['turn_id'], 'invalid_turn_id')
    _require(isinstance(case['user_message'], str) and case['user_message'], 'empty_user_message')
    _require(case['expected_action'] in ACTIONS, 'invalid_action', str(case['expected_action']))
    ind = case['independence']
    _require(isinstance(ind, dict) and ind.get('level') in INDEPENDENCE, 'invalid_independence')
    _require(isinstance(ind.get('human_reviewer'), bool), 'independence_missing_human_flag')
    _require(isinstance(case['request_intent'], dict), 'invalid_request_intent')

    messages = dict(messages or {})
    messages.setdefault(case['turn_id'], case['user_message'])
    evidence_ids = {e['evidence_id'] for e in case.get('verified_evidence', [])}
    _require(isinstance(case.get('verified_evidence', []), list), 'invalid_verified_evidence')

    request_atoms = atoms(case['request_intent'])
    req_ids = set()
    for req in case['requirements']:
        _require(isinstance(req, dict), 'invalid_requirement')
        _require(set(req) <= {'req_id', 'category', 'field', 'value', 'provenance',
                              'evidence', 'source_turn_id', 'status', 'note'}, 'unknown_requirement_field')
        for field in ('req_id', 'category', 'field', 'value', 'provenance', 'status'):
            _require(field in req, 'missing_requirement_field', field)
        _require(req['req_id'] not in req_ids, 'duplicate_req_id', req['req_id'])
        req_ids.add(req['req_id'])
        _require(req['category'] in REQUIREMENT_CATEGORIES, 'invalid_category', req['category'])
        _require(req['provenance'] in PROVENANCE, 'invalid_provenance', req['provenance'])
        _require(req['status'] in STATUS, 'invalid_status', req['status'])

        # Grounding: a requirement must be explicitly traceable.
        if req['provenance'] == 'VERIFIED_EVIDENCE':
            _require(req.get('evidence') in evidence_ids, 'unrecorded_verified_evidence', req['req_id'])
            _require(req['status'] == 'CERTIFIED', 'verified_evidence_not_certified', req['req_id'])
        else:
            source = req.get('source_turn_id') or case['turn_id']
            _require(source in messages, 'unknown_source_turn', str(source))
            _require(isinstance(req.get('evidence'), str) and req['evidence'], 'missing_evidence', req['req_id'])
            _require(req['evidence'] in messages[source], 'evidence_not_in_source', req['req_id'])
            # A user assertion can never be certified.
            if req['provenance'] == 'USER_ASSERTED_UNVERIFIED':
                _require(req['status'] != 'CERTIFIED', 'assertion_certified', req['req_id'])

        # Consistency: every requirement atom must appear under its field.
        _require(_value_in_request(req, case['request_intent'], request_atoms),
                 'requirement_not_in_request_intent', req['req_id'])
    return True


def _value_in_request(req, request_intent, request_atoms):
    value = req['value']
    if req['field'] in ('relations', 'claims'):
        return value in request_intent.get(req['field'], [])
    if req['field'] == 'time' and isinstance(value, dict):
        periods = (request_intent.get('time') or {}).get('periods', [])
        if value in periods:
            return True
    matching = [v for p, v in request_atoms
                if p == '/' + req['field'] or p.startswith('/' + req['field'] + '/')]
    return any(v == _json(value) for v in matching)


def validate_set(cases, messages=None):
    ids = [c['turn_id'] for c in cases]
    _require(len(ids) == len(set(ids)), 'duplicate_turn_ids')
    for case in cases:
        validate_case(case, messages)
    return len(cases)


def load_cases(path):
    data = json.loads(Path(path).read_text())
    cases = data['cases'] if isinstance(data, dict) else data
    return cases


def independence_summary(cases):
    counts = {}
    for case in cases:
        level = case['independence']['level']
        counts[level] = counts.get(level, 0) + 1
    human = sum(1 for c in cases if c['independence'].get('human_reviewer'))
    certified = sum(1 for c in cases if c['independence']['level'] == 'HUMAN_INDEPENDENT')
    return {
        'cases': len(cases),
        'by_level': counts,
        'human_reviewed_cases': human,
        'certified_gold_cases': certified,
        'gold_status': 'CERTIFIED' if certified == len(cases) and cases else 'PROVISIONAL_GOLD',
    }


def clone(case):
    return deepcopy(case)