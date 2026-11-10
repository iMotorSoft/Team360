"""First-attempt blind evaluation only; never imported by runtime."""
import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from modules.telchi.assistant.tests import live_investigative_completeness as existing

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent


def snapshot():
    backend = ROOT / 'SrvRestAstroLS_v1/backend'
    files = []
    for directory in ('modules/telchi', 'modules/messaging', 'modules/business_semantics', 'modules/db'):
        files.extend((backend / directory).rglob('*.py'))
    files.extend(backend.glob('*.py'))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(files)) if 'investigation' not in p.parts and '__pycache__' not in p.parts}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    questions = HERE / 'questions.json'
    cases = json.loads(questions.read_text())['cases']
    assert sum(map(len, cases.values())) == 12
    assert sum(len(q) > 1 for q in cases.values()) == 3
    control = json.loads(args.control.read_text())
    assert control['env'].get('TEAM360_TELCHI_DURABLE') == '1', 'do_not_override_composition'
    assert control['env'].get('TEAM360_TELCHI_FREE_ANALYSIS') == '1'
    before = snapshot()
    baseline = dict(head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    branch=subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
                    files=before, questions_sha256=hashlib.sha256(questions.read_bytes()).hexdigest(),
                    runtime_source_digest=existing.dev.source_digest(),
                    protocol='first attempts only; existing durable composition; no transport; no edits')
    save(args.output / 'freeze-before.json', baseline)
    existing.CASES = cases
    try:
        asyncio.run(existing.main(SimpleNamespace(control=args.control, output=args.output / 'live.json', case=None)))
    finally:
        after = snapshot()
        changed = [p for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)]
        save(args.output / 'freeze-after.json', dict(files=after, changed_paths=changed,
              frozen=not changed, runtime_source_digest=existing.dev.source_digest(),
              questions_unchanged=hashlib.sha256(questions.read_bytes()).hexdigest() == baseline['questions_sha256']))


if __name__ == '__main__':
    main()
