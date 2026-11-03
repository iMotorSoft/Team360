"""Publish only reviewed PASS evidence; retain existing technical expiration.
No listener, model, Foundation, permission, webhook or service mutations.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3] / 'SrvRestAstroLS_v1/backend'
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
assert r['runner_sha256'] == sha(HERE / 'validate.py')
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
    'business_authorization': ['revocation_between_turns', 'public_rbac_preserved'],
    'durable_idempotency': ['durable_idempotency', 'persisted_result_recovery'],
    'assistant_foundation': ['assistant_foundation', 'persisted_result_recovery'],
    'model_no_fallback': ['model_no_fallback', 'focused_evidence_reuse'],
}
assert set(required) == d.GATES
for names in required.values():
    for name in names:
        assert r['observations'][name]['status'] == 'PASS'
mp = d.private_file(a['gates_file'])
previous = mp.read_bytes()
assert sha(mp) == r['previous_manifest_sha256']
old = json.loads(previous)
assert datetime.fromisoformat(old['expires_at']) > datetime.now(timezone.utc)
for g in old['gates'].values():
    assert sha(d.private_file(g['artifact'])) == g['sha256']
# Immutable backup and explicit original provenance, no extending technical TTL.
backup = p.parent / 'previous-manifest.json'
with open(backup, 'xb', opener=lambda path, flags: os.open(path, flags, 0o600)) as f:
    f.write(previous)
    f.flush()
    os.fsync(f.fileno())
manifest = dict(old)
manifest.update(generated_at=datetime.now(timezone.utc).isoformat(),
    source_sha256=r['source_sha256'], approval_sha256=r['approval_sha256'],
    previous_manifest=dict(artifact=str(backup), sha256=sha(backup)),
    renewal_basis='Focused result-reference real pipeline accreditation. Original technical expires_at unchanged. No new control or access expiry.',
    gates={name: dict(status='PASS', kind='real', artifact=str(p), sha256=sha(p),
        observations=names, previous_evidence=old['gates'][name]) for name, names in required.items()})
assert manifest['expires_at'] == old['expires_at']
assert mp.read_bytes() == previous
assert d.source_digest() == r['source_sha256']
l.atomic(mp, manifest)
try:
    d.gate_evidence(a)
    d.preflight(ap)
    assert d.source_digest() == r['source_sha256']
    assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
except BaseException:
    l.atomic(mp, old)
    raise
summary = dict(branch='feature/console-backend-core', RESULT_REFERENCE_PIPELINE='PASS',
    REVOCATION_BETWEEN_TURNS='PASS', SIX_GATES='VALID', CURRENT_FINGERPRINT='VALID',
    RUNTIME_BOOTSTRAP='RESOLVED', META_CALLBACK='UNKNOWN', READY_FOR_MANUAL_START='YES',
    source_sha256=r['source_sha256'], artifact=str(p), artifact_sha256=sha(p),
    manifest_sha256=sha(mp), technical_expires_at=manifest['expires_at'],
    technical_expiration='Preserved existing value; not added or extended',
    preflight='PREFLIGHT_PASS: normal gate_evidence and preflight, no bypass', runtime='STOPPED',
    revocation_scope='Real PostgreSQL and Console resolver on committed session-local copies of actual pilot RBAC joins. No operational permission/access changed. Both new and cached result reuse denied.',
    external_connectivity='Separate from six gate contracts. Meta not queried; no MATCH inferred. Container ingress check remains part of existing manual startup.',
    runner_sha256=sha(__file__), services_started_or_stopped=0, whatsapp_sent=0,
    own_processes_left_running=0, impact='New evidence and private gate manifest only; existing code/worktree/operational rows and records preserved.',
    prior_harness_aborts=[dict(reason='Progress file exclusive-create conflict', runtime_defect=False),
                         dict(reason='SELECT FOR UPDATE attempted inside READ ONLY', runtime_defect=False)],
    manual_action='SrvRestAstroLS_v1/scripts/telchi/telchiai-dev.sh start',
    meta_manual_verification=[
        'Open the EXISTING Team360 Meta app in Meta for Developers, WhatsApp > Configuration (or Webhooks > WhatsApp Business Account). Do not create a new app or edit/save configuration.',
        'Compare the displayed callback URL to the existing Cloudflare public URL plus the Evolution Meta webhook path shown in the existing Evolution configuration. Confirm the same Team360 app/WABA/phone-number asset and messages subscription.',
        'Exact URL/asset/subscription match -> MATCH; discrepancy -> MISMATCH; no access -> UNKNOWN. Do not press Test, send a message or change subscriptions to accredit the pipeline gates.'
    ])
(HERE / 'closure.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({k: summary[k] for k in ('RESULT_REFERENCE_PIPELINE', 'REVOCATION_BETWEEN_TURNS', 'SIX_GATES', 'CURRENT_FINGERPRINT', 'RUNTIME_BOOTSTRAP', 'META_CALLBACK', 'READY_FOR_MANUAL_START', 'technical_expires_at', 'runtime')}, indent=2))
