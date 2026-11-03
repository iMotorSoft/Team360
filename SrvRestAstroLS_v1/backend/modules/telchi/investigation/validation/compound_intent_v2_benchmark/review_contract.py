"""Shared contract for the human certification of the Compound Intent V2 gold.

Investigation-only. This module never imports the runtime, never calls a model
and never reads candidate predictions. The review package is built exclusively
from the gold side (``annotated_seed.json`` or ``seed_gold``); the 20 sealed
holdout turns are kept out of the pilot.

The gold is ``PROVISIONAL_GOLD`` until a human reviewer (not the implementation
author) completes and adjudicates the review. No code path here writes to the
sealed holdout, to ``annotated_seed.json`` or to the runtime.
"""

import csv
import hashlib
import json
from pathlib import Path

from . import gold_schema, holdout, seed_gold

BENCHMARK_VERSION = 'compound_intent_v2_benchmark/1'

# Decisions a human reviewer may record. A blank cell means "not reviewed yet".
DECISIONS = ('ACCEPT', 'CORRECT', 'AMBIGUOUS', 'INSUFFICIENT_CONTEXT')
NON_ACCEPT = ('CORRECT', 'AMBIGUOUS', 'INSUFFICIENT_CONTEXT')

# The extension target named in the task: the frozen LlmFit corpus of run01.
LLMFIT_CORPUS_SIZE = 104
PILOT_SIZE = 10

CASE_COLUMNS = (
    'turn_id', 'conversation_id', 'turn_index', 'grupo',
    'mensaje_original', 'contexto_anterior', 'accion_esperada',
    'independencia_actual', 'resumen_requisitos',
    'decision_caso', 'observaciones_caso',
)
REQUIREMENT_COLUMNS = (
    'review_id', 'turn_id', 'conversation_id', 'turn_index', 'categoria',
    'procedencia', 'campo', 'requisito_propuesto', 'evidencia_literal',
    'estado_actual', 'accion_esperada',
    'decision_requisito', 'requisito_corregido', 'motivo',
)

REVIEWER_TEMPLATE = {
    'reviewer_id': '',
    'reviewer_name': '',
    'reviewer_role': '',
    'organization': '',
    'is_implementation_author': None,
    'no_candidate_predictions_used': None,
    'reviewed_at': '',
    'independence_statement': '',
}


def _discover_repo_root():
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / 'SrvRestAstroLS_v1').is_dir() and (candidate / 'data').is_dir():
            return candidate
    return Path.cwd()


REPO_ROOT = _discover_repo_root()
EVIDENCE_ROOT = REPO_ROOT / 'data' / 'reports' / 'telchi' / 'compound_intent_v2_benchmark'
DEFAULT_SEED = EVIDENCE_ROOT / 'annotated_seed.json'
DEFAULT_CORPUS = REPO_ROOT / 'data' / 'reports' / 'telchi' / 'compound_intent_v1' / 'run01' / 'rows.jsonl'
DEFAULT_REVIEW_DIR = EVIDENCE_ROOT / 'review'


# --------------------------------------------------------------------------- #
# Gold-side loading
# --------------------------------------------------------------------------- #

def holdout_ids():
    """Turn ids of the sealed holdout, computed from the authoring code."""
    return {case['turn_id'] for case in holdout.build_cases()}


def pilot_cases(seed_path=None):
    """Load the 10 known pilot cases and refuse any holdout leakage."""
    path = Path(seed_path) if seed_path else DEFAULT_SEED
    if path.is_file():
        data = json.loads(path.read_text(encoding='utf-8'))
        cases = data['cases'] if isinstance(data, dict) else data
    else:
        cases = seed_gold.build_cases()
    cases = [dict(case) for case in cases]
    _assert_pilot_safe(cases)
    return cases


def _assert_pilot_safe(cases):
    ids = [case['turn_id'] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate_pilot_turn_ids')
    if len(cases) != PILOT_SIZE:
        raise ValueError('pilot_size_expected_' + str(PILOT_SIZE) + '_got_' + str(len(cases)))
    leak = sorted(set(ids) & holdout_ids())
    if leak:
        raise ValueError('holdout_leak:' + ','.join(leak))
    messages = {case['turn_id']: case['user_message'] for case in cases}
    gold_schema.validate_set(cases, messages)


def corpus_turn_ids(corpus_path=None):
    """LlmFit turn ids from a frozen rows.jsonl, only when explicitly requested.

    The pilot package never reads the candidate rows by default: ``rows.jsonl``
    stores candidate predictions and the reviewer must not see them. Callers that
    only need the pending count rely on ``LLMFIT_CORPUS_SIZE`` instead.
    """
    if not corpus_path:
        return []
    path = Path(corpus_path)
    if not path.is_file():
        return []
    ids = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get('group') == 'llmfit':
            ids.append(row['id'])
    return sorted(set(ids))


# --------------------------------------------------------------------------- #
# Human-readable rendering of a proposed requirement
# --------------------------------------------------------------------------- #

def describe_requirement(req):
    value = req['value']
    if isinstance(value, dict) and 'predicate' in value:
        return '{subject} -> {predicate} -> {object} ({geography}) [{status}]'.format(
            subject=value.get('subject', ''), predicate=value.get('predicate', ''),
            object=value.get('object', ''), geography=value.get('geography', ''),
            status=value.get('status', ''))
    if isinstance(value, dict) and 'text' in value:
        return 'Afirmacion del usuario: {text} [{status}]'.format(
            text=value.get('text', ''), status=value.get('status', ''))
    if isinstance(value, dict) and 'start' in value and 'end_exclusive' in value:
        return '{start} -> {end_exclusive}'.format(
            start=value['start'], end_exclusive=value['end_exclusive'])
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def previous_message(case, cases):
    siblings = [c for c in cases if c['conversation_id'] == case['conversation_id']]
    previous = [c for c in siblings if c['turn_index'] == case['turn_index'] - 1]
    return previous[0]['user_message'] if previous else ''


# --------------------------------------------------------------------------- #
# Package rows
# --------------------------------------------------------------------------- #

def build_case_rows(cases):
    rows = []
    for case in cases:
        rows.append({
            'turn_id': case['turn_id'],
            'conversation_id': case['conversation_id'],
            'turn_index': case['turn_index'],
            'grupo': case['group'],
            'mensaje_original': case['user_message'],
            'contexto_anterior': previous_message(case, cases),
            'accion_esperada': case['expected_action'],
            'independencia_actual': case['independence']['level'],
            'resumen_requisitos': ' | '.join(r['req_id'] for r in case['requirements']),
            'decision_caso': '',
            'observaciones_caso': '',
        })
    return rows


def build_requirement_rows(cases):
    rows = []
    for case in cases:
        for req in case['requirements']:
            rows.append({
                'review_id': req['req_id'],
                'turn_id': case['turn_id'],
                'conversation_id': case['conversation_id'],
                'turn_index': case['turn_index'],
                'categoria': req['category'],
                'procedencia': req['provenance'],
                'campo': req['field'],
                'requisito_propuesto': describe_requirement(req),
                'evidencia_literal': req.get('evidence', ''),
                'estado_actual': req.get('status', ''),
                'accion_esperada': case['expected_action'],
                'decision_requisito': '',
                'requisito_corregido': '',
                'motivo': '',
            })
    return rows


# --------------------------------------------------------------------------- #
# CSV helpers
# --------------------------------------------------------------------------- #

def write_csv(path, columns, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction='raise')
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, '') for column in columns})


def read_csv(path):
    path = Path(path)
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Decision analysis
# --------------------------------------------------------------------------- #

def load_reviewer(path=None):
    path = Path(path) if path else None
    if path and path.is_file():
        data = json.loads(path.read_text(encoding='utf-8'))
    else:
        data = {}
    reviewer = {**REVIEWER_TEMPLATE, **{k: data.get(k, v) for k, v in REVIEWER_TEMPLATE.items()}}
    return reviewer


def _cell(row, column):
    return (row.get(column) or '').strip()


def analyze(cases, case_rows, req_rows, reviewer=None, corpus_ids=None):
    """Validate the decision sheets and compute coverage and certification status.

    Returns a report where ``errors`` are malformed or unsafe inputs, ``pending``
    is simply "not reviewed yet", and ``pending_adjudication`` is "a decision that
    still needs a written justification/correction".
    """
    reviewer = {**REVIEWER_TEMPLATE, **(reviewer or {})}
    corpus_ids = sorted(corpus_ids or [])
    errors, pending, pending_adjudication = [], [], []

    expected_cases = [case['turn_id'] for case in cases]
    expected_reqs = [req['req_id'] for case in cases for req in case['requirements']]
    holdout = holdout_ids()

    case_decision, case_observations = {}, {}
    seen_cases = set()
    for row in case_rows:
        turn_id = _cell(row, 'turn_id')
        if turn_id not in expected_cases:
            errors.append({'scope': 'case', 'id': turn_id, 'error': 'unknown_turn_id'})
            continue
        if turn_id in seen_cases:
            errors.append({'scope': 'case', 'id': turn_id, 'error': 'duplicate_turn_id'})
            continue
        seen_cases.add(turn_id)
        decision = _cell(row, 'decision_caso')
        observations = _cell(row, 'observaciones_caso')
        if decision and decision not in DECISIONS:
            errors.append({'scope': 'case', 'id': turn_id, 'error': 'invalid_decision', 'value': decision})
        if decision in NON_ACCEPT and not observations:
            pending_adjudication.append({'scope': 'case', 'id': turn_id, 'error': 'observations_required'})
        case_decision[turn_id] = decision
        case_observations[turn_id] = observations

    for turn_id in expected_cases:
        if turn_id not in seen_cases:
            pending.append({'scope': 'case', 'id': turn_id, 'error': 'missing_decision_row'})
        elif not case_decision.get(turn_id):
            pending.append({'scope': 'case', 'id': turn_id, 'error': 'not_reviewed'})

    req_decision, req_corrected, req_motive = {}, {}, {}
    seen_reqs = set()
    for row in req_rows:
        review_id = _cell(row, 'review_id')
        if review_id not in expected_reqs:
            errors.append({'scope': 'requirement', 'id': review_id, 'error': 'unknown_review_id'})
            continue
        if review_id in seen_reqs:
            errors.append({'scope': 'requirement', 'id': review_id, 'error': 'duplicate_review_id'})
            continue
        seen_reqs.add(review_id)
        decision = _cell(row, 'decision_requisito')
        corrected = _cell(row, 'requisito_corregido')
        motive = _cell(row, 'motivo')
        if decision and decision not in DECISIONS:
            errors.append({'scope': 'requirement', 'id': review_id, 'error': 'invalid_decision', 'value': decision})
        if decision == 'CORRECT':
            if not corrected:
                pending_adjudication.append({'scope': 'requirement', 'id': review_id, 'error': 'corrected_requirement_required'})
            if not motive:
                pending_adjudication.append({'scope': 'requirement', 'id': review_id, 'error': 'motivo_required'})
        elif decision in ('AMBIGUOUS', 'INSUFFICIENT_CONTEXT') and not motive:
            pending_adjudication.append({'scope': 'requirement', 'id': review_id, 'error': 'motivo_required'})
        req_decision[review_id] = decision
        req_corrected[review_id] = corrected
        req_motive[review_id] = motive

    for review_id in expected_reqs:
        if review_id not in seen_reqs:
            pending.append({'scope': 'requirement', 'id': review_id, 'error': 'missing_decision_row'})
        elif not req_decision.get(review_id):
            pending.append({'scope': 'requirement', 'id': review_id, 'error': 'not_reviewed'})

    # Safety: no row may reference a sealed holdout turn.
    for row in list(case_rows) + list(req_rows):
        if _cell(row, 'turn_id') in holdout:
            errors.append({'scope': 'row', 'id': _cell(row, 'turn_id'), 'error': 'holdout_leak'})

    case_summary = []
    for case in cases:
        turn_id = case['turn_id']
        requirements = []
        for req in case['requirements']:
            review_id = req['req_id']
            requirements.append({
                'review_id': review_id,
                'categoria': req['category'],
                'procedencia': req['provenance'],
                'decision': req_decision.get(review_id, ''),
                'corrected_requirement': req_corrected.get(review_id, ''),
                'motivo': req_motive.get(review_id, ''),
            })
        decided = all(item['decision'] for item in requirements)
        complete = bool(case_decision.get(turn_id)) and decided
        case_summary.append({
            'turn_id': turn_id,
            'decision': case_decision.get(turn_id, ''),
            'observations': case_observations.get(turn_id, ''),
            'complete': complete,
            'requirements': requirements,
        })

    cases_total = len(cases)
    cases_complete = sum(1 for case in case_summary if case['complete'])
    requirements_total = len(expected_reqs)
    requirements_decided = sum(1 for case in case_summary for r in case['requirements'] if r['decision'])
    case_decisions_recorded = sum(1 for case in case_summary if case['decision'])

    decision_counts = {decision: 0 for decision in DECISIONS}
    decision_counts['BLANK'] = 0
    for case in case_summary:
        key = case['decision'] if case['decision'] in DECISIONS else 'BLANK'
        decision_counts[key] += 1
        for req in case['requirements']:
            key = req['decision'] if req['decision'] in DECISIONS else 'BLANK'
            decision_counts[key] += 1

    pilot_complete = cases_complete == cases_total and cases_total > 0
    corpus_reviewed = 0  # the 104 LlmFit turns are not yet in the request-aware schema
    corpus_pending = max(len(corpus_ids), LLMFIT_CORPUS_SIZE) - corpus_reviewed
    any_decision = case_decisions_recorded > 0 or requirements_decided > 0

    criteria = {
        'independent_human_reviewer': (
            bool(reviewer.get('reviewer_id'))
            and reviewer.get('is_implementation_author') is False
            and reviewer.get('no_candidate_predictions_used') is True
        ),
        'pilot_review_complete': pilot_complete,
        'corrections_have_corrected_text': all(
            c['corrected_requirement'] for case in case_summary for c in case['requirements']
            if c['decision'] == 'CORRECT'
        ),
        'no_pending_adjudication': not pending_adjudication,
        'full_llmfit_corpus_reviewed': corpus_reviewed >= (len(corpus_ids) or LLMFIT_CORPUS_SIZE),
        'holdout_kept_sealed_and_separate': True,
        'corrections_applied_to_gold_and_revalidated': False,
    }

    if not any_decision:
        status = 'NOT_STARTED'
    elif not pilot_complete:
        status = 'PILOT_REVIEW_IN_PROGRESS'
    elif not criteria['full_llmfit_corpus_reviewed']:
        status = 'PILOT_COMPLETE_CORPUS_PENDING'
    elif not all(criteria.values()):
        status = 'CORPUS_REVIEWED_NOT_CERTIFIED'
    else:
        status = 'CERTIFIED'

    next_action = {
        'NOT_STARTED': 'Complete the pilot decision sheets and the reviewer declaration.',
        'PILOT_REVIEW_IN_PROGRESS': 'Finish the 10 pilot cases and every proposed requirement.',
        'PILOT_COMPLETE_CORPUS_PENDING': (
            'Validate the pilot instructions, then re-annotate and review the 104 LlmFit turns '
            'with the same schema and a separate holdout custody procedure.'
        ),
        'CORPUS_REVIEWED_NOT_CERTIFIED': 'Adjudicate corrections, apply them to the gold and revalidate the schema.',
        'CERTIFIED': 'Freeze the reviewed gold and hand it to authorization.py; V2 is still not implemented here.',
    }[status]

    decisions = {
        'benchmark_version': BENCHMARK_VERSION,
        'kind': 'HUMAN_REVIEW_DECISIONS',
        'reviewer': reviewer,
        'cases': case_summary,
        'validation': {'errors': errors, 'pending': pending, 'pending_adjudication': pending_adjudication},
    }
    coverage = {
        'benchmark_version': BENCHMARK_VERSION,
        'kind': 'REVIEW_COVERAGE',
        'status': status,
        'pilot': {
            'cases_total': cases_total,
            'cases_complete': cases_complete,
            'cases_pending': cases_total - cases_complete,
            'requirements_total': requirements_total,
            'requirements_decided': requirements_decided,
            'requirements_pending': requirements_total - requirements_decided,
            'coverage_percent': round(100.0 * cases_complete / cases_total, 2) if cases_total else 0.0,
        },
        'corpus': {
            'llmfit_turns': len(corpus_ids) or LLMFIT_CORPUS_SIZE,
            'in_request_aware_schema': 0,
            'reviewed': corpus_reviewed,
            'pending': corpus_pending,
        },
        'holdout': {
            'turns': len(holdout),
            'sealed': True,
            'included_in_pilot': False,
        },
        'decision_counts': decision_counts,
        'pending_cases': [c['turn_id'] for c in case_summary if not c['complete']],
        'pending_requirements': [
            r['review_id'] for c in case_summary for r in c['requirements'] if not r['decision']
        ],
        'validation_errors': errors,
    }
    status_report = {
        'benchmark_version': BENCHMARK_VERSION,
        'kind': 'REVIEW_CERTIFICATION_STATUS',
        'status': status,
        'certified': status == 'CERTIFIED',
        'certification_criteria': criteria,
        'certification_criteria_notes': {
            'independent_human_reviewer': 'reviewer_id set, is_implementation_author=false, no_candidate_predictions_used=true',
            'pilot_review_complete': 'all 10 pilot cases decided at case and requirement level',
            'corrections_have_corrected_text': 'every CORRECT carries requisito_corregido',
            'no_pending_adjudication': 'every non-ACCEPT decision has observations/motivo/correction',
            'full_llmfit_corpus_reviewed': 'the 104 LlmFit turns must be re-annotated, reviewed and adjudicated',
            'holdout_kept_sealed_and_separate': 'invariant of this package; holdout never enters the pilot',
            'corrections_applied_to_gold_and_revalidated': 'requires an explicit adjudication step not performed by this tool',
        },
        'validation': {'errors': errors, 'pending': pending, 'pending_adjudication': pending_adjudication},
        'next_action': next_action,
    }
    return {'decisions': decisions, 'coverage': coverage, 'status': status_report}


# --------------------------------------------------------------------------- #
# Report writers
# --------------------------------------------------------------------------- #

def write_reports(out_dir, report):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'review_decisions.json').write_text(
        json.dumps(report['decisions'], indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    (out / 'review_coverage.json').write_text(
        json.dumps(report['coverage'], indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    (out / 'review_status.json').write_text(
        json.dumps(report['status'], indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    (out / 'review_coverage.md').write_text(render_coverage_markdown(report), encoding='utf-8')
    return report


def render_coverage_markdown(report):
    coverage = report['coverage']
    status = report['status']
    pilot = coverage['pilot']
    corpus = coverage['corpus']
    lines = [
        '# Cobertura de revision humana',
        '',
        'Estado: **' + coverage['status'] + '**. Certificado: **' + ('SI' if status['certified'] else 'NO') + '**.',
        '',
        '| Ambito | Total | Revisado | Pendiente |',
        '| --- | ---: | ---: | ---: |',
        '| Piloto (casos conocidos) | ' + str(pilot['cases_total']) + ' | ' + str(pilot['cases_complete']) + ' | ' + str(pilot['cases_pending']) + ' |',
        '| Corpus LlmFit | ' + str(corpus['llmfit_turns']) + ' | ' + str(corpus['reviewed']) + ' | ' + str(corpus['pending']) + ' |',
        '| Holdout sellado | ' + str(coverage['holdout']['turns']) + ' | 0 | separado |',
        '',
        'Requisitos del piloto: ' + str(pilot['requirements_decided']) + '/' + str(pilot['requirements_total']) + ' decididos.',
        '',
        '## Decisiones registradas',
        '',
    ]
    for decision, count in sorted(coverage['decision_counts'].items()):
        lines.append('- ' + decision + ': ' + str(count))
    if status['validation']['errors']:
        lines += ['', '## Errores de consistencia', '']
        for error in status['validation']['errors']:
            lines.append('- ' + json.dumps(error, ensure_ascii=False, sort_keys=True))
    if status['validation']['pending_adjudication']:
        lines += ['', '## Adjudicacion pendiente', '']
        for item in status['validation']['pending_adjudication']:
            lines.append('- ' + json.dumps(item, ensure_ascii=False, sort_keys=True))
    lines += [
        '',
        '## Criterios para CERTIFIED',
        '',
    ]
    for criterion, ok in sorted(status['certification_criteria'].items()):
        lines.append('- ' + ('[x] ' if ok else '[ ] ') + criterion)
    lines += ['', 'Siguiente accion: ' + status['next_action'], '']
    return '\n'.join(lines)