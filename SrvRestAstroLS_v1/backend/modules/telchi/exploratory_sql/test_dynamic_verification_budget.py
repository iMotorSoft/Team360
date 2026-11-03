"""Offline transport/diagnostic regressions; never accredit missing grain."""
import copy
from types import SimpleNamespace

import pytest

from .adaptive_research import bounded_payload
from .ask_sources import context_for_run
from .ask_verifier import AskRegistry
from .claim_evidence import verification_feedback
from .validator import canonical


def test_feedback_column_reference_is_lossless_and_budgeted():
    column = dict(column_id='column-1', alias='arbitrary_presentation',
        sql_type='DECIMAL(38,6)', expression='x' * 2500,
        source_fields=['published.field'], source_or_calculation='CALCULATION',
        metric=None, metric_definition=None, grain='unaccredited',
        transformations=[], unit=None, currency=None,
        classification='DERIVED_NOT_OFFICIAL', limitations=['not accredited'])
    evidence = dict(result_id='result-1', column=column, row_id='row-1', observed='500')
    check = dict(claim=dict(kind='measure', result_id='result-1', column_id='column-1',
        row_id='row-1', value='500'), state='UNVERIFIED', match=False,
        reason='independent_value_contradiction_or_join_fanout',
        required='Reconcile the fanout; do not assert billing.', evidence=[evidence])
    payload = dict(context='p' * 28000, observations=[dict(
        evidence_manifest=dict(result_id='result-1', columns=[column], row_ids=['row-1'], limitations=[]),
        rows=[['500']], truncated=False), verification_feedback([check])])
    original = copy.deepcopy(payload)
    assert len(canonical(payload).encode()) > 32768
    compact = bounded_payload(payload)
    assert len(canonical(compact).encode()) <= 32768
    feedback = compact['observations'][1]['rejected_claims'][0]
    referenced = feedback['evidence'][0]
    restored = dict(zip(compact['evidence_column_fields'], compact['evidence_columns'][referenced['column_ref']]))
    restored['alias'] = referenced['column_alias']
    assert restored == column
    assert feedback['reason'] == check['reason']
    assert feedback['required'] == check['required']
    assert feedback['claim'] == check['claim']
    assert referenced['observed'] == '500'
    assert compact['observations'][0]['rows'] == [['500']]
    assert not compact['observations'][0]['truncated']
    assert payload == original


def test_uncompressible_observation_still_fails_closed():
    with pytest.raises(RuntimeError, match='observation_byte_budget'):
        bounded_payload(dict(observations=[dict(status='ERROR', reason='x' * 32768)]))


def test_missing_grain_diagnostic_reaches_claim_feedback():
    registry = AskRegistry(context_for_run(), executor_factory=lambda *a, **k: SimpleNamespace(close=lambda: None))
    try:
        registry.audit.append(dict(result_id='result-1', state='UNVERIFIED',
            reason='discovered_grain_and_business_semantics_not_accredited'))
        check = registry.verify(dict(kind='measure', result_id='result-1', value='100'))
        assert check['state'] == 'UNVERIFIED' and not check['match']
        assert check['reason'] == 'discovered_grain_and_business_semantics_not_accredited'
        feedback = verification_feedback([check])
        assert feedback['rejected_claims'][0]['reason'] == check['reason']
        assert 'not a numerical contradiction' in feedback['instruction']
        assert 'Repeating an aggregate cannot establish' in feedback['instruction']
    finally:
        registry.close()
