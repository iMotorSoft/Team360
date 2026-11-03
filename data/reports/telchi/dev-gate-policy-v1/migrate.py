"""One-off owner-authorized DEV transition. No services, model calls or WhatsApp.

Requires the private pre-edit baseline captured for this reviewed change. Does
not renew expired evidence automatically or accept arbitrary source drift.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT/'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    directory = dev.PRIVATE_ROOT/'dev-gate-policy-transition'
    baseline = lifecycle.read_json(directory/'baseline.json')
    previous = lifecycle.read_json(directory/'manifest-before.json')
    config_path = dev.PRIVATE_ROOT/'whatsapp-dev-control.json'
    config = lifecycle.load_config(config_path)
    approval_path = Path(config.get('approval', dev.PRIVATE_ROOT/'whatsapp-dev-session-approval.json'))
    approval = dev.read_approval(approval_path)
    manifest_path = dev.private_file(approval['gates_file'])
    assert manifest_path.read_bytes() == (directory/'manifest-before.json').read_bytes(), 'manifest_changed'
    assert baseline['source_sha256'] == previous['source_sha256'], 'baseline_not_accredited'
    assert previous['approval_sha256'] == dev.approval_digest(approval), 'approval_changed'
    assert os.environ.get('TEAM360_ENV') in {'dev', 'development'}, 'DEV_required'
    # The pre-edit digest was verified before any edits; per-file hashes now
    # establish exactly which implementations need focused revalidation.
    changed = {name for name, value in baseline['files'].items() if sha(BACKEND/name) != value}
    allowed = {'modules/telchi/assistant/whatsapp_dev.py',
               'modules/telchi/assistant/tests/test_whatsapp_dev.py'}
    assert changed == allowed, ('unreviewed_source_drift', sorted(changed))
    old_paths = set(baseline['files'])
    current_py = set()
    for root in ('telchi/assistant', 'telchi/datalake', 'messaging', 'console', 'db'):
        current_py.update(str(p.relative_to(BACKEND)) for p in (BACKEND/'modules'/root).rglob('*.py'))
    assert current_py - old_paths == {'modules/telchi/assistant/tests/test_dev_gate_policy.py'}
    assert set(previous['gates']) == dev.GATES
    for gate in previous['gates'].values():
        assert gate['status'] == 'PASS' and gate['kind'] == 'real'
        artifact = dev.private_file(gate['artifact'])
        assert sha(artifact) == gate['sha256'], 'artifact_changed'
        report = json.loads(artifact.read_text())
        assert report['status'] == 'PASS'
        assert report['source_sha256'] == baseline['source_sha256']
        assert report['approval_sha256'] == dev.approval_digest(approval)
        assert report['configuration_sha256'] == sha(config_path), 'configuration_changed_since_real_evidence'
        for name in gate['observations']:
            assert report['observations'][name]['status'] == 'PASS'
    # Cheap, real, read-only external checks before the focused offline contracts.
    dev.preflight(approval_path, require_gates=False)
    tests = ['modules/telchi/assistant/tests/'+name for name in (
        'test_dev_gate_policy.py', 'test_whatsapp_dev.py', 'test_whatsapp_dev_lifecycle.py',
        'test_whatsapp_dev_lifecycle_extra.py', 'test_pilot_access.py',
        'test_whatsapp_operational_contract.py', 'test_invoice_continuity.py')]
    tests += ['tests/test_telchi_assistant_srv05.py', 'tests/test_messaging_horizontal_runtime.py']
    # Permission-negative tests require the normal test umask; the parent and
    # all operational evidence remain private. Do not mask their 0755 fixture.
    process = subprocess.run([sys.executable, '-m', 'pytest', *tests, '-q'],
                             capture_output=True, text=True, timeout=180, umask=0o022)
    test_path = directory/('focused-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.txt')
    with open(test_path, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        stream.write(process.stdout + process.stderr)
    assert process.returncode == 0, 'focused_tests_failed'
    source = dev.source_digest()
    evidence = dict(status='PASS', issued_at=datetime.now(timezone.utc).isoformat(),
        owner_decision='DEV change-based validity; production unchanged',
        previous_manifest_sha256=sha(directory/'manifest-before.json'),
        baseline_sha256=sha(directory/'baseline.json'), source_sha256=source,
        configuration_sha256=dev.configuration_digest(), runner_sha256=sha(__file__),
        changed_python=sorted(changed), new_python=sorted(current_py-old_paths),
        reused_guarantees=sorted(dev.GATES),
        reuse_basis='Original runtime, business, identity, Foundation, idempotency and Luna unchanged; exact baseline and private operator configuration match real artifacts. Original observation dates retained.',
        revalidated_guarantees=['DEV admission/version/environment isolation',
            'code/config/contract/artifact invalidation', 'manual lifecycle with non-expiring gates',
            'dynamic RBAC and pilot revocation contracts', 'normal read-only preflight'],
        tests_sha256=sha(test_path), tests_summary=process.stdout.strip().splitlines()[-1],
        services_started_or_stopped=0, whatsapp_sent=0, grants_changed=0)
    evidence_path = directory/'transition-evidence.json'
    dev.save_private(evidence_path, evidence)
    manifest = dict(previous)
    manifest.pop('expires_at')
    manifest.update(schema_version=2, environment='dev', validity_policy=dev.DEV_GATE_POLICY,
        issued_at=evidence['issued_at'], source_sha256=source,
        configuration_sha256=dev.configuration_digest(),
        previous_manifest=dict(artifact=str(directory/'manifest-before.json'), sha256=sha(directory/'manifest-before.json')),
        transition=dict(artifact=str(evidence_path), sha256=sha(evidence_path)),
        renewal_basis='Owner-approved policy migration; original real evidence retained, not redated. Only admission/lifecycle changed and revalidated.')
    # Concurrent writers are not permitted to replace our baseline silently.
    assert manifest_path.read_bytes() == (directory/'manifest-before.json').read_bytes()
    assert dev.source_digest() == source
    lifecycle.atomic(manifest_path, manifest)
    assert manifest_path.stat().st_mode & 0o077 == 0
    dev.gate_evidence(approval)
    dev.preflight(approval_path)  # NORMAL path, all six gates required.
    lifecycle.atomic(directory/'result.json', dict(status='PASS', preflight='PASS',
        six_gates='VALID', source_sha256=source, tests=evidence['tests_summary'],
        manifest_sha256=sha(manifest_path), services_started_or_stopped=0,
        whatsapp_sent=0, own_processes_left_running=0))
    print('MIGRATION_PASS; normal PREFLIGHT_PASS; '+evidence['tests_summary'])


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('BLOCKED: '+type(error).__name__+'; inspect private evidence', file=sys.stderr)
        raise SystemExit(1)
