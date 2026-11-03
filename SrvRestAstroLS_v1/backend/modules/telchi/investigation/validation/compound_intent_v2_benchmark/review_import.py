"""Import human review decisions and validate their consistency.

Reads the completed decision sheets from a review package, validates them against
the gold schema and the pilot inventory, and regenerates the coverage and
certification reports. It never edits the gold, never touches the sealed holdout
and never declares ``CERTIFIED`` from an incomplete or unadjudicated review.

Emit with (from ``SrvRestAstroLS_v1/backend``)::

    uv run python -m modules.telchi.investigation.validation.compound_intent_v2_benchmark.review_import \\
      --review-dir ../../data/reports/telchi/compound_intent_v2_benchmark/review
"""

import argparse
import json
from pathlib import Path

from . import review_contract as contract

REQUIRED_FILES = ('pilot_cases.csv', 'pilot_requirements.csv')


def _resolve_from_manifest(review_dir, seed, corpus):
    manifest_path = Path(review_dir) / 'review_package_manifest.json'
    source_files = []
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        source_files = manifest.get('source_files_read') or []
    resolved_seed = seed or (source_files[0] if source_files else None)
    resolved_corpus = corpus or (source_files[1] if len(source_files) > 1 else None)
    return resolved_seed, resolved_corpus


def run(review_dir, seed_path=None, corpus_path=None, reviewer_path=None, reviewed_at=None):
    review_dir = Path(review_dir)
    missing = [name for name in REQUIRED_FILES if not (review_dir / name).is_file()]
    if missing:
        raise FileNotFoundError('missing_review_files:' + ','.join(missing))

    resolved_seed, resolved_corpus = _resolve_from_manifest(review_dir, seed_path, corpus_path)
    cases = contract.pilot_cases(resolved_seed)
    corpus_ids = contract.corpus_turn_ids(resolved_corpus)

    case_rows = contract.read_csv(review_dir / 'pilot_cases.csv')
    req_rows = contract.read_csv(review_dir / 'pilot_requirements.csv')

    reviewer = contract.load_reviewer(reviewer_path or (review_dir / 'reviewer.json'))
    if reviewed_at:
        reviewer['reviewed_at'] = reviewed_at

    report = contract.analyze(cases, case_rows, req_rows, reviewer, corpus_ids)
    contract.write_reports(review_dir, report)
    return report


def main(args):
    review_dir = Path(args.review_dir)
    missing = [name for name in REQUIRED_FILES if not (review_dir / name).is_file()]
    if missing:
        raise SystemExit('missing_review_files:' + ','.join(missing))
    report = run(
        review_dir,
        seed_path=args.seed,
        corpus_path=args.corpus,
        reviewer_path=args.reviewer,
        reviewed_at=args.reviewed_at,
    )
    coverage = report['coverage']
    status = report['status']
    print(json.dumps({
        'status': status['status'],
        'certified': status['certified'],
        'pilot_complete': coverage['pilot']['cases_complete'],
        'pilot_total': coverage['pilot']['cases_total'],
        'requirements_decided': coverage['pilot']['requirements_decided'],
        'requirements_total': coverage['pilot']['requirements_total'],
        'validation_errors': len(status['validation']['errors']),
        'pending_adjudication': len(status['validation']['pending_adjudication']),
        'next_action': status['next_action'],
    }, indent=2, ensure_ascii=False))
    if status['validation']['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--review-dir', required=True)
    parser.add_argument('--seed', default=None)
    parser.add_argument('--corpus', default=None)
    parser.add_argument('--reviewer', default=None)
    parser.add_argument('--reviewed-at', default=None)
    main(parser.parse_args())