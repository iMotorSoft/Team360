"""Observation transport budget: measured, recoverable, always declared.

The budget is never raised and evidence is never silently truncated. A payload
that still does not fit ends the turn as a declared resource limit, reported with
the measured component sizes instead of being discarded downstream.
"""
import copy

import pytest

from .adaptive_research import (
    OBSERVATION_BUDGET, bounded_payload, payload_sizes, terminal_status,
)
from .validator import canonical


def manifest(number, columns=8):
    return dict(result_id=f'R{number}', publication='foundation_fixture', snapshot='1408',
                columns=[dict(column_id=f'C{number}{index}', alias=f'column_{index}',
                              sql_type='DECIMAL(38,6)', metric='amount', unit='BS',
                              currency='BS', grain='document', nullable=False)
                         for index in range(columns)],
                row_ids=[f'{number}-{row}' for row in range(10)],
                temporal_scope=['published_rows', 'not_complete_calendar'],
                filter_expression='doc_date>=? AND doc_date<?',
                limitations=['Observed rows only; calendar completeness not certified.'])


def observation(number, rows=3, columns=8):
    return dict(turn=number, objective='obj', hypothesis='hyp', evidence_manifest=manifest(number, columns),
                decision={'decision': 'ALLOW'}, schema={'columns': [f'c{i}' for i in range(columns)]},
                rows=[{'k': index, 'amount': '1.00'} for index in range(rows)], status='COMPLETED')


def feedback(number=0):
    return dict(status='BUSINESS_SCOPE_FEEDBACK', reason='Net requested: ' + 'x' * 900)


def size(payload):
    return len(canonical(payload).encode())


def test_measurement_reports_every_component_and_stage():
    payload = dict(question='q', conversation=[], catalog=dict(tables=[]),
                   observations=[observation(1)])
    stats = {}
    compact = bounded_payload(payload, stats)
    assert size(compact) <= OBSERVATION_BUDGET
    assert stats['limit'] == OBSERVATION_BUDGET
    assert stats['stages']['input'] > 0 and stats['stages']['delivered'] <= OBSERVATION_BUDGET
    sizes = payload_sizes(payload)
    assert sizes['total'] == size(payload)
    assert sizes['observations_detail'][0]['manifest'] > 0


def test_metadata_volume_is_compacted_before_any_evidence_is_dropped():
    payload = dict(question='q', conversation=[], catalog=dict(tables=[]),
                   observations=[observation(n, rows=3, columns=24) for n in range(1, 9)])
    assert size(payload) > OBSERVATION_BUDGET
    compact = bounded_payload(payload)
    assert size(compact) <= OBSERVATION_BUDGET
    # Every observation, its rows and its identifiers survive the compaction.
    assert [entry['turn'] for entry in compact['observations']] == list(range(1, 9))
    assert all(entry['rows'] for entry in compact['observations'])
    assert 'evidence_columns' in compact


def test_controller_feedback_leaves_the_wire_and_the_omission_is_declared():
    payload = dict(question='q', catalog=dict(tables=[]), conversation=[],
                   observations=[feedback() for _ in range(60)] + [observation(1, columns=12)])
    assert size(payload) > OBSERVATION_BUDGET
    compact = bounded_payload(payload)
    assert size(compact) <= OBSERVATION_BUDGET
    assert compact['omitted_feedback_entries'] > 0
    assert [entry['turn'] for entry in compact['observations']] == [1]


def test_prior_conversation_is_bounded_with_a_marker_never_silently():
    payload = dict(question='q', catalog=dict(tables=[]), observations=[observation(1)],
                   conversation=[dict(role='assistant', content='y' * 4000) for _ in range(12)])
    assert size(payload) > OBSERVATION_BUDGET
    compact = bounded_payload(payload)
    assert size(compact) <= OBSERVATION_BUDGET
    assert compact['conversation_bounded'] is True
    assert all('recortado en este envío' in entry['content'] for entry in compact['conversation'])
    assert compact['observations'][0]['rows']


def test_an_unrecoverable_payload_reports_the_measured_cause():
    payload = dict(question='q' * 40000, catalog=dict(tables=[]), conversation=[],
                   observations=[observation(1)])
    stats = {}
    with pytest.raises(RuntimeError, match='observation_byte_budget'):
        bounded_payload(payload, stats)
    assert stats['stages']['input'] > OBSERVATION_BUDGET
    assert stats['components']['question'] == size(payload['question'])
    assert stats['components']['observations'] > 0


def test_budget_is_never_expanded_and_input_is_not_mutated():
    payload = dict(question='q', catalog=dict(tables=[]), conversation=[],
                   observations=[observation(1)])
    original = copy.deepcopy(payload)
    bounded_payload(payload)
    assert payload == original
    assert OBSERVATION_BUDGET == 32768


@pytest.mark.parametrize('reason,status', [
    ('observation_byte_budget', 'RESOURCE_LIMITED'),
    ('model_call_budget_exhausted', 'BLOCKED'),
    ('execution_stopped:join_pair_budget', 'BLOCKED'),
    ('query_attempt_budget_exhausted', 'BLOCKED'),
])
def test_terminal_status_distinguishes_resource_limits(reason, status):
    assert terminal_status(reason) == status