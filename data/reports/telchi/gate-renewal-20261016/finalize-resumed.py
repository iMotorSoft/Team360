"""Record the remaining provenance blocker; never issue a replacement manifest."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3] / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
cpath = d.PRIVATE_ROOT/'whatsapp-dev-control.json'
c = l.load_config(cpath)
apath = c.get('approval', d.PRIVATE_ROOT/'whatsapp-dev-session-approval.json')
a = d.read_approval(apath)
review = json.loads((HERE/'resume-review.json').read_text())
prior = json.loads((HERE/'closure.json').read_text())
audit = json.loads((HERE/'audit.json').read_text())
m = json.loads(d.private_file(a['gates_file']).read_text())
result = dict(generated_at=datetime.now(timezone.utc).isoformat(), branch='feature/console-backend-core', objective='Complete focused TelchiAI DEV renewal without runtime/configuration changes', result=dict(TELCHIAI_GATES='BLOCKED', MANIFEST='BLOCKED', PREFLIGHT='BLOCKED', READY_FOR_LIFECYCLE_TEST='NO'), ingress=review['http_probe'], evolution=review['evolution'], historical_review={})
for name in sorted(d.GATES - {'http_auth'}):
    old = prior['gate_review'][name]
    current = {p: sha(BACKEND/p) for p in old['current_scoped_hashes']}
    result['historical_review'][name] = dict(original_artifact=m['gates'][name]['artifact'], original_sha256=m['gates'][name]['sha256'], original_integrity=sha(m['gates'][name]['artifact']) == m['gates'][name]['sha256'], current_scoped_hashes=current, scoped_files_unchanged_since_prior_review=current == old['current_scoped_hashes'], historical_approval_matches=review['historical'][name]['approval_sha256'] == d.approval_digest(a), applicability='HISTORICAL_EVIDENCE_INTACT; CROSS_VERSION_PARITY_NOT_PROVEN', original_scope=m['gates'][name]['scope'])
result['code_review'] = dict(identity_tenant_isolation='PhoneIdentityRepository.resolve scopes provider/environment/tenant/workspace and verifies active user/workspace; check_session independently validates approved live pilot and effective permission.', business_authorization='BusinessAuthorization.allowed denies mismatched identity/scope, missing policy permission and absent operation-specific effective grants before capability execution.', durable_idempotency='MessagingService commits claim fence before dispatch; duplicate recovery resumes durable delivery intent, never handler execution. Recording egress in historical gate does not certify real delivery.', assistant_foundation='SalesCapabilities validates exact fixed period and lineage; messaging_sales_query opens read_only session. Historical publication/snapshot result not rerun or changed.', model_no_fallback='LunaInterpreter pins direct OpenAI endpoint/model/medium effort, trust_env=False, no retry/fallback, verifies response model/effort. No provider call repeated.', limitation='Current static invariants and unchanged hashes since the post-lifecycle inventory corroborate compatibility, but neither reconstructs the pre-lifecycle source/configuration baseline. Historical aggregate digest differs; mtimes are not historical content proof.')
try:
    d.gate_evidence(a)
    result['gate_evidence'] = 'VALID'
except (ValueError, PermissionError) as exc:
    result['gate_evidence'] = str(exc)
p = subprocess.run([sys.executable, '-m', d.MODULE, 'preflight', '--approval', str(apath)], capture_output=True, text=True, timeout=30, env=dict(os.environ))
result['preflight_cli'] = dict(command='python -m modules.telchi.assistant.whatsapp_dev preflight --approval PRIVATE_APPROVAL', exit_code=p.returncode, stdout=p.stdout.strip(), stderr=p.stderr.strip())
result['blocker'] = 'Missing complete historical per-file/configuration baseline tied to source digest '+m['source_sha256']+'; cannot independently establish applicability of five historical gates to current source '+d.source_digest()+'. Existing manifest is correctly rejected with gate_scope_mismatch.'
result['minimal_resolution'] = 'Recover the original source snapshot/per-file hashes and effective configuration record tied to the historical gates, then perform scoped comparison/impact attestation. No need to restart Evolution, repeat Luna/Foundation/idempotency/commercial batteries, or change grants/runtime.'
result['validation'] = dict(historical_manifest_unchanged=sha(a['gates_file']) == audit['historical_manifest_sha256'], approval_unchanged=d.approval_digest(a) == audit['approval_sha256'], config_unchanged=sha(cpath) == audit['config_sha256'], source_unchanged=d.source_digest() == audit['source_sha256'], webhook_unchanged=review['webhook_unchanged'], focused_checks='8 current HTTP cases plus inert container authentication/reachability PASS; DB read-only approved identity/permission and schema checks PASS', tests_reused='lifecycle-operational-closure-v1/validation.json: 84 focused tests PASS; source fingerprint identical; no runtime/test changes in this renewal', git_diff_check='PASS (executed before final evidence write)', resource_guard='BUSY_BUT_SAFE / sequential listeners; no scans, models or browsers', own_processes_left_running=review['http_probe']['own_processes_left_running'], unrelated_processes_terminated=0)
result['new_manifest_issued'] = False
result['impact'] = 'NONE: only additive evidence under gate-renewal-20261016 and PRIVATE_ROOT; no runtime/config/grants/Foundation/service/Git mutations.'
result['runner_sha256'] = {n: sha(HERE/n) for n in ('resume.py', 'http_probe.py', 'finalize-resumed.py')}
result['new_files'] = ['resume.py', 'http-result-resumed.json', 'resume-review.json', 'finalize-resumed.py', 'closure-resumed.json']
d.save_private(Path(review['http_probe']['artifact']).parent/'closure-resumed.json', result)
(HERE/'closure-resumed.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(dict(result=result['result'], gate_evidence=result['gate_evidence'], preflight_exit=p.returncode, validation=result['validation'], blocker=result['blocker'], minimal_resolution=result['minimal_resolution']), indent=2))
