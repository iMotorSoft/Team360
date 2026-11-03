import json

from . import review_contract as contract
from . import review_import, review_package


def _build(tmp_path):
    return review_package.build_package(tmp_path)


def _write_reviewer(tmp_path, **overrides):
    reviewer = dict(contract.REVIEWER_TEMPLATE)
    reviewer.update({
        'reviewer_id': 'REV-001',
        'reviewer_name': 'Responsable de negocio',
        'is_implementation_author': False,
        'no_candidate_predictions_used': True,
    })
    reviewer.update(overrides)
    (tmp_path / 'reviewer.json').write_text(json.dumps(reviewer), encoding='utf-8')


def _fill(tmp_path, case_decision='ACCEPT', req_decision='ACCEPT'):
    case_rows = contract.read_csv(tmp_path / 'pilot_cases.csv')
    for row in case_rows:
        row['decision_caso'] = case_decision
        row['observaciones_caso'] = '' if case_decision == 'ACCEPT' else 'observado'
    contract.write_csv(tmp_path / 'pilot_cases.csv', contract.CASE_COLUMNS, case_rows)
    req_rows = contract.read_csv(tmp_path / 'pilot_requirements.csv')
    for row in req_rows:
        row['decision_requisito'] = req_decision
        if req_decision == 'CORRECT':
            row['requisito_corregido'] = row['requisito_propuesto']
            row['motivo'] = 'corregido'
    contract.write_csv(tmp_path / 'pilot_requirements.csv', contract.REQUIREMENT_COLUMNS, req_rows)


def _append_case_row(tmp_path, row):
    case_rows = contract.read_csv(tmp_path / 'pilot_cases.csv')
    case_rows.append({column: row.get(column, '') for column in contract.CASE_COLUMNS})
    contract.write_csv(tmp_path / 'pilot_cases.csv', contract.CASE_COLUMNS, case_rows)


def test_blank_review_is_not_started(tmp_path):
    _build(tmp_path)
    report = review_import.run(tmp_path)
    assert report['coverage']['status'] == 'NOT_STARTED'
    assert report['status']['certified'] is False
    assert report['status']['validation']['errors'] == []
    assert len(report['status']['validation']['pending']) == 36  # 10 cases + 26 requirements


def test_independent_full_pilot_is_not_certified_without_corpus(tmp_path):
    _build(tmp_path)
    _fill(tmp_path)
    _write_reviewer(tmp_path)
    report = review_import.run(tmp_path)
    coverage = report['coverage']
    status = report['status']
    assert coverage['pilot']['cases_complete'] == 10
    assert coverage['pilot']['requirements_decided'] == coverage['pilot']['requirements_total']
    assert status['status'] == 'PILOT_COMPLETE_CORPUS_PENDING'
    assert status['certified'] is False
    assert status['certification_criteria']['pilot_review_complete'] is True
    assert status['certification_criteria']['independent_human_reviewer'] is True
    assert status['certification_criteria']['full_llmfit_corpus_reviewed'] is False


def test_new_reports_are_written_to_disk(tmp_path):
    _build(tmp_path)
    _fill(tmp_path)
    _write_reviewer(tmp_path)
    review_import.run(tmp_path)
    coverage = json.loads((tmp_path / 'review_coverage.json').read_text(encoding='utf-8'))
    assert coverage['pilot']['cases_complete'] == 10
    assert 'Cobertura de revision humana' in (tmp_path / 'review_coverage.md').read_text(encoding='utf-8')


def test_correction_without_text_needs_adjudication(tmp_path):
    _build(tmp_path)
    _fill(tmp_path, req_decision='CORRECT')
    req_rows = contract.read_csv(tmp_path / 'pilot_requirements.csv')
    req_rows[0]['requisito_corregido'] = ''
    req_rows[0]['motivo'] = ''
    contract.write_csv(tmp_path / 'pilot_requirements.csv', contract.REQUIREMENT_COLUMNS, req_rows)
    _write_reviewer(tmp_path)
    report = review_import.run(tmp_path)
    errors = report['status']['validation']['pending_adjudication']
    assert any(e['error'] == 'corrected_requirement_required' for e in errors)
    assert any(e['error'] == 'motivo_required' for e in errors)
    assert report['status']['certification_criteria']['no_pending_adjudication'] is False


def test_ambiguous_case_requires_observations(tmp_path):
    _build(tmp_path)
    _fill(tmp_path, case_decision='AMBIGUOUS')
    case_rows = contract.read_csv(tmp_path / 'pilot_cases.csv')
    case_rows[0]['observaciones_caso'] = ''
    contract.write_csv(tmp_path / 'pilot_cases.csv', contract.CASE_COLUMNS, case_rows)
    _write_reviewer(tmp_path)
    report = review_import.run(tmp_path)
    assert any(e['error'] == 'observations_required'
               for e in report['status']['validation']['pending_adjudication'])


def test_invalid_decision_is_a_hard_error(tmp_path):
    _build(tmp_path)
    _fill(tmp_path)
    case_rows = contract.read_csv(tmp_path / 'pilot_cases.csv')
    case_rows[0]['decision_caso'] = 'MAYBE'
    contract.write_csv(tmp_path / 'pilot_cases.csv', contract.CASE_COLUMNS, case_rows)
    _write_reviewer(tmp_path)
    report = review_import.run(tmp_path)
    assert any(e['error'] == 'invalid_decision' for e in report['status']['validation']['errors'])


def test_unknown_turn_id_is_a_hard_error(tmp_path):
    _build(tmp_path)
    _fill(tmp_path)
    _append_case_row(tmp_path, {'turn_id': 'TCS_999_T99'})
    _write_reviewer(tmp_path)
    report = review_import.run(tmp_path)
    assert any(e['error'] == 'unknown_turn_id' for e in report['status']['validation']['errors'])


def test_holdout_reference_is_rejected(tmp_path):
    _build(tmp_path)
    _fill(tmp_path)
    _append_case_row(tmp_path, {'turn_id': 'H1_1'})
    _write_reviewer(tmp_path)
    report = review_import.run(tmp_path)
    assert any(e['error'] == 'holdout_leak' for e in report['status']['validation']['errors'])


def test_author_reviewer_does_not_count_as_independent(tmp_path):
    _build(tmp_path)
    _fill(tmp_path)
    _write_reviewer(tmp_path, is_implementation_author=True)
    report = review_import.run(tmp_path)
    assert report['status']['certification_criteria']['independent_human_reviewer'] is False
    assert report['status']['certified'] is False