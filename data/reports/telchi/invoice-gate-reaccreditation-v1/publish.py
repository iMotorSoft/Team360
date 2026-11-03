"""Publish reviewed current real evidence with EXISTING four-hour technical TTL.
No service lifecycle, grants, approval, transport or runtime changes.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BACKEND = ROOT / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
cp = d.PRIVATE_ROOT / 'whatsapp-dev-control.json'
config = l.load_config(cp)
ap = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
a = d.read_approval(ap)
s = json.loads((HERE / 'result.json').read_text())
p = d.private_file(s['artifact'])
assert sha(p) == s['sha256']
r = json.loads(p.read_text())
assert r['status'] == 'PASS' and r['pool_closed']
assert r['runner_sha256'] == sha(HERE / 'executed-runner.py')
assert r['source_sha256'] == d.source_digest()
assert r['approval_sha256'] == d.approval_digest(a)
assert r['configuration_sha256'] == sha(cp)
assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
for name in ('services_started_or_stopped', 'listeners_created', 'whatsapp_sent',
             'public_permission_mutations', 'pilot_access_mutations', 'webhook_mutations', 'own_processes_left_running'):
    assert r[name] == 0
required = {
    'http_auth': ['http_auth'],
    'identity_tenant_isolation': ['identity_tenant_isolation', 'persisted_result_recovery'],
    'business_authorization': ['revocation_between_turns', 'public_rbac_preserved', 'invoice_lines_authorized_execution', 'invoice_lines_revocation_and_recovery'],
    'durable_idempotency': ['durable_idempotency', 'invoice_lines_authorized_execution'],
    'assistant_foundation': ['assistant_foundation', 'persisted_result_recovery', 'invoice_lines_authorized_execution', 'invoice_lines_revocation_and_recovery'],
    'model_no_fallback': ['model_no_fallback', 'focused_evidence_reuse'],
}
assert set(required) == d.GATES
for names in required.values():
    assert all(r['observations'][n]['status'] == 'PASS' for n in names)
mp = d.private_file(a['gates_file'])
previous = mp.read_bytes()
assert sha(mp) == r['previous_manifest_sha256']
old = json.loads(previous)
for g in old['gates'].values():
    assert sha(d.private_file(g['artifact'])) == g['sha256']
# Confirm the existing renewal duration from the preexisting implementation.
policy_source = ROOT / 'data/reports/telchi/six-gates-current-v1/publish.py'
assert 'expiry = now + timedelta(hours=4)' in policy_source.read_text()
# Cheap, sequential focused checks, including committed PostgreSQL contracts.
os.environ.update(TEAM360_RESULT_REFERENCE_POSTGRES_TEST='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
cmd = ['uv', 'run', '--no-sync', 'pytest',
       'modules/telchi/assistant/tests/test_invoice_continuity.py',
       'modules/telchi/assistant/tests/test_invoice_continuity_postgres.py',
       'modules/telchi/datalake/tests/test_invoice_lines_query.py', '-q']
test_file = p.parent / 'focused-tests.txt'
with open(test_file, 'x') as f:
    result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=90)
assert result.returncode == 0, 'focused_tests_failed: see private evidence'
assert mp.read_bytes() == previous and d.source_digest() == r['source_sha256']
assert d.approval_digest(d.read_approval(ap)) == r['approval_sha256'] and sha(cp) == r['configuration_sha256']
backup = p.parent / 'previous-manifest.json'
with open(backup, 'xb') as f:
    f.write(previous)
    f.flush()
    os.fsync(f.fileno())
now = datetime.now(timezone.utc)
expiry = now + timedelta(hours=4)
manifest = dict(workspace_id=a['workspace_id'], user_id=a['user_id'], instance='team360-meta-dev',
    generated_at=now.isoformat(), expires_at=expiry.isoformat(), source_sha256=d.source_digest(),
    approval_sha256=d.approval_digest(a), previous_manifest=dict(artifact=str(backup), sha256=sha(backup)),
    renewal_basis='Owner-authorized current real invoice/document continuity reaccreditation; existing four-hour technical duration unchanged; no pilot expiration or new permission.',
    gates={name: dict(status='PASS', kind='real', artifact=str(p), sha256=sha(p), observations=names)
           for name, names in required.items()})
assert mp.read_bytes() == previous
l.atomic(mp, manifest)
try:
    d.gate_evidence(a)
    d.preflight(ap)  # Normal entry point, gates required: NO bypass.
    assert d.source_digest() == r['source_sha256']
    assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
except BaseException:
    l.atomic(mp, old)
    raise
summary = dict(branch='feature/console-backend-core', SIX_GATES='VALID', CURRENT_FINGERPRINT='VALID',
    PILOT_ACCESS='VALID', TECHNICAL_EXPIRATION=expiry.isoformat(), technical_duration_hours=4,
    READY_FOR_MANUAL_START='YES', preflight='PREFLIGHT_PASS', runtime='STOPPED',
    artifact=str(p), artifact_sha256=sha(p), manifest_sha256=sha(mp),
    source_sha256=d.source_digest(), approval_sha256=d.approval_digest(a),
    focused_tests=dict(command=cmd, artifact=str(test_file), sha256=sha(test_file), result='PASS'),
    services_started_or_stopped=0, whatsapp_sent=0, grants_changed=0, pilot_changed=0,
    own_processes_left_running=0, unrelated_processes_terminated=0,
    host_preflight=r['host_preflight'], concurrency=r['concurrency'],
    harness_corrections=['Accept existing SELECT_DOCUMENT action for document recovery',
                         'Explicit temporary search_path after recreating session-local RBAC copies; avoid prepared statements resolving public joins'],
    impact='Evidence/private manifest only. No runtime, expiration policy, infrastructure, grants or pilot changes.',
    limitations='Not WhatsApp E2E. Existing manual startup still owns container ingress check; no service started here.')
l.atomic(p.parent / 'closure.json', summary)
(HERE / 'closure.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({k: summary[k] for k in ('SIX_GATES', 'CURRENT_FINGERPRINT', 'PILOT_ACCESS', 'TECHNICAL_EXPIRATION', 'READY_FOR_MANUAL_START', 'runtime', 'preflight')}, indent=2))
