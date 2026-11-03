import json
from pathlib import Path

from . import review_contract as contract
from . import review_package


def _build(tmp_path):
    return review_package.build_package(tmp_path)


def test_pilot_has_ten_diverse_known_cases():
    cases = contract.pilot_cases()
    assert len(cases) == 10
    ids = {case['turn_id'] for case in cases}
    assert {'ABRAHAM_001', 'ABRAHAM_002'} <= ids
    assert {'S05_2', 'S06_2'} <= ids  # follow-up conversational cases
    assert ids.isdisjoint(contract.holdout_ids())


def test_package_excludes_holdout_and_predictions(tmp_path):
    manifest = _build(tmp_path)
    assert manifest['pilot_size'] == 10
    assert manifest['holdout_included_in_pilot'] is False
    assert manifest['candidate_predictions_included'] is False
    assert len(manifest['source_files_read']) == 1
    assert manifest['source_files_read'][0].endswith('annotated_seed.json')
    assert all('rows.jsonl' not in source for source in manifest['source_files_read'])
    text = (tmp_path / 'pilot_cases.csv').read_text(encoding='utf-8-sig')
    text += (tmp_path / 'pilot_requirements.csv').read_text(encoding='utf-8-sig')
    for holdout_id in contract.holdout_ids():
        assert holdout_id not in text
    assert 'candidate_intent' not in text
    assert 'baseline_intent' not in text


def test_package_emits_expected_files_and_columns(tmp_path):
    _build(tmp_path)
    for name in ('pilot_cases.csv', 'pilot_requirements.csv', 'reviewer.json',
                 'pilot_review_guide.md', 'pilot_review.md', 'review_decisions.json',
                 'review_coverage.json', 'review_status.json', 'review_coverage.md',
                 'review_package_manifest.json'):
        assert (tmp_path / name).is_file(), name
    case_rows = contract.read_csv(tmp_path / 'pilot_cases.csv')
    req_rows = contract.read_csv(tmp_path / 'pilot_requirements.csv')
    assert list(case_rows[0]) == list(contract.CASE_COLUMNS)
    assert list(req_rows[0]) == list(contract.REQUIREMENT_COLUMNS)
    assert all(not row['decision_caso'] for row in case_rows)
    assert all(not row['decision_requisito'] for row in req_rows)


def test_followup_cases_carry_previous_context(tmp_path):
    _build(tmp_path)
    rows = {row['turn_id']: row for row in contract.read_csv(tmp_path / 'pilot_cases.csv')}
    assert rows['S05_2']['contexto_anterior'] == 'Ventas de mayo de 2026'
    assert rows['S06_2']['contexto_anterior'] == 'Quiero importes y cantidades'
    assert rows['S01_1']['contexto_anterior'] == ''


def test_initial_coverage_is_not_started(tmp_path):
    _build(tmp_path)
    coverage = json.loads((tmp_path / 'review_coverage.json').read_text(encoding='utf-8'))
    status = json.loads((tmp_path / 'review_status.json').read_text(encoding='utf-8'))
    assert coverage['status'] == 'NOT_STARTED'
    assert coverage['pilot']['cases_complete'] == 0
    assert coverage['pilot']['cases_total'] == 10
    assert coverage['holdout']['turns'] == 20
    assert status['certified'] is False


def test_package_build_is_deterministic(tmp_path):
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    _build(first)
    _build(second)
    for name in ('pilot_cases.csv', 'pilot_requirements.csv', 'pilot_review.md'):
        assert Path(first, name).read_bytes() == Path(second, name).read_bytes()