"""Shared builder for schema-valid gold cases."""

from copy import deepcopy

EMPTY_INTENT = {
    'business_domain': None, 'metrics': [], 'dimensions': [], 'filters': [],
    'scope': {'branch_ids': [], 'warehouse_ids': []}, 'time': None,
    'comparison': None, 'reference': None, 'limit': None, 'sort': [],
    'measure_context': None, 'segments': [], 'granularities': [],
    'geographies': [], 'relations': [], 'claims': [], 'unresolved_requirements': [],
}

_REQ_NAMES = ('req_id', 'category', 'field', 'value', 'provenance', 'evidence',
              'status', 'source_turn_id', 'note')


def requirement(r):
    values = list(r) + [''] * (len(_REQ_NAMES) - len(r))
    if not values[6]:
        values[6] = 'PROVISIONAL'
    return dict(zip(_REQ_NAMES, values[:len(_REQ_NAMES)]))


def period(start, end_exclusive):
    return {'start': start, 'end_exclusive': end_exclusive}


def relation(object_, geography, evidence, turn_id, subject='Citrato de magnesio'):
    return {'subject': subject, 'predicate': 'distribution', 'object': object_,
            'geography': geography, 'evidence': evidence, 'source_turn_id': turn_id,
            'status': 'USER_ASSERTED_UNVERIFIED'}


def claim(text, evidence, turn_id):
    return {'text': text, 'evidence': evidence, 'source_turn_id': turn_id,
            'status': 'USER_ASSERTED_UNVERIFIED'}


def make_case(turn_id, conversation_id, turn_index, user_message, request,
              requirements, expected_action, group='holdout', ambiguities=None,
              non_executable=None, notes='', independence=None):
    request_intent = deepcopy(EMPTY_INTENT)
    request_intent.update(request)
    return {
        'turn_id': turn_id,
        'group': group,
        'conversation_id': conversation_id,
        'turn_index': turn_index,
        'user_message': user_message,
        'independence': independence or {
            'level': 'MODEL_ASSISTED_PROVISIONAL',
            'method': 'benchmark-author annotation, no candidate output inspected',
            'human_reviewer': False,
            'reviewer': None,
        },
        'request_intent': request_intent,
        'expected_action': expected_action,
        'requirements': [requirement(r) for r in requirements],
        'verified_evidence': [],
        'ambiguities': ambiguities or [],
        'non_executable': non_executable or [],
        'notes': notes,
    }