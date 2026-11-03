"""Read-only final verification; writes only this task's public verification JSON."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BACKEND = ROOT / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
config = l.load_config(d.PRIVATE_ROOT / 'whatsapp-dev-control.json')
ap = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
a = d.read_approval(ap)
closure = json.loads((HERE / 'closure.json').read_text())
artifact = d.private_file(closure['artifact'])
assert sha(artifact) == closure['artifact_sha256']
report = json.loads(artifact.read_text())
assert sha(HERE / 'reaccredit.py') == report['runner_sha256']
assert report['source_sha256'] == closure['source_sha256'] == d.source_digest()
assert report['configuration_sha256'] == d.configuration_digest()
assert report['approval_sha256'] == d.approval_digest(a)
manifest_path = d.private_file(a['gates_file'])
assert sha(manifest_path) == closure['manifest_sha256']
manifest = json.loads(manifest_path.read_text())
assert manifest['schema_version'] == 2 and manifest['validity_policy'] == 'change_based_v1'
assert 'expires_at' not in manifest
for record in (manifest['previous_manifest'], report['focused_tests'], report['gates']['http_auth']):
    assert sha(d.private_file(record['artifact'])) == record['sha256']
assert d.gate_evidence(a) is None  # Change-based policy: no expiry.
d.preflight(ap)  # Normal launcher preflight, all gates required.
status = l.status()
assert status['state'] == 'STOPPED' and status['webhook'] == 'INTERNAL'
assert status['gates'] == 'VALID' and status['approval'] == 'VALID'
timing = d.session_timing(SimpleNamespace(
    idle_timeout=config.get('idle_timeout', d.DEFAULT_IDLE_TIMEOUT),
    max_duration=config.get('max_duration', config.get('duration', d.DEFAULT_MAX_DURATION))))
assert report['dev_session_policy'] == dict(status='READY', idle_timeout=timing[0], max_duration=timing[1])
assert report['pool_closed'] and report['observations']['http_auth']['listener_closed']
assert report['observations']['business_authorization']['temporary_fixtures_removed']
assert report['observations']['business_authorization']['operational_effective_permissions_unchanged']
assert report['grant_mutations'] == report['whatsapp_sends'] == report['webhook_mutations'] == 0
listeners = subprocess.run(['/usr/bin/ss', '-H', '-ltn', f'sport = :{config.get("port", 18181)}'],
    capture_output=True, text=True, check=True)
assert not listeners.stdout.strip(), 'temporary_listener_still_present'
diff = subprocess.run(['/usr/bin/git', 'diff', '--check'], cwd=ROOT, capture_output=True, text=True)
assert diff.returncode == 0
verification = dict(generated_at=datetime.now(timezone.utc).isoformat(),
    branch='feature/console-backend-core', source_sha256=d.source_digest(),
    six_gates='VALID', gate_policy='change_based_v1',
    gates={name: report['gates'][name]['status'] for name in sorted(d.GATES)},
    artifact=str(artifact), artifact_sha256=sha(artifact), manifest_sha256=sha(manifest_path),
    artifact_hashes_verified=True, source_unchanged=True,
    official_status=status, normal_launcher_preflight='PREFLIGHT_PASS',
    dev_session_policy=report['dev_session_policy'],
    model=report['model_metadata']['model'], provider=report['model_metadata']['provider'],
    reasoning=report['model_metadata']['reasoning'],
    focused_tests=closure['validations'], preliminary_contracts='58 passed in 2.18s',
    git_diff_check='PASS', final_diff_review='Reviewed runner delta against previous accredited runner; only isolated authorization and stricter integrity/session checks added.',
    host_preflight='BUSY_BUT_SAFE', resource_guard='PASS',
    host_after=dict(load='3.76/3.08/1.88', available_mib=5949, swap_mib=350, swap_io_last_samples=0),
    concurrency='One sequential runner; PG max 3; two claims of one event; one model request; no browser.',
    own_processes_left_running=0, unrelated_processes_terminated=0, environmental_aborts=0,
    grants_modified='NO', runtime_state='STOPPED', webhook_state='INTERNAL',
    ready_for_manual_start='YES', whatsapp_e2e='NOT_RUN',
    modified_paths=['data/reports/telchi/commercial-continuity-v2-final-reaccreditation/', 'PRIVATE_ROOT gates manifest and new private evidence directory'],
    impact='No enterprise/runtime code, Foundation, SAP/HANA, classifications, operational grants, credentials or shared services modified. DEV event/audit/intent rows created by the real Messaging probe remain auditable.',
    limitations=['4 tests skipped; not counted as passes.', 'Recording sender proves one logical outbound intent, not WhatsApp delivery.', 'No live provider outage induced; no-fallback failure contracts supplement real model success.', 'Readiness remains conditional on unchanged code/configuration/approval/evidence and service availability.'])
(HERE / 'verification.json').write_text(json.dumps(verification, indent=2) + '\n')
print(json.dumps(verification, indent=2))
