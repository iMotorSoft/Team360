"""Read-only final attestation checks. Does not issue or overwrite a manifest."""
import asyncio, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
B=Path(__file__).resolve().parents[4]/'SrvRestAstroLS_v1/backend'
R=Path(__file__).parent
sys.path.insert(0,str(B));os.chdir(B)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
cpath=d.PRIVATE_ROOT/'whatsapp-dev-control.json';c=l.load_config(cpath)
apath=c.get('approval',d.PRIVATE_ROOT/'whatsapp-dev-session-approval.json')
a=d.read_approval(apath);srv,settings=d.configuration()
m=json.loads(d.private_file(a['gates_file']).read_text());audit=json.loads((R/'audit.json').read_text());http=json.loads((R/'http-result.json').read_text())
r=dict(generated_at=datetime.now(timezone.utc).isoformat(),branch='feature/console-backend-core',objective='Focused six-gate renewal only; no lifecycle session',approval='VALID',source_sha256=d.source_digest(),approval_sha256=d.approval_digest(a),config_sha256=sha(cpath),source_fingerprint='VALID' if d.source_digest()==audit['source_sha256'] else 'INVALID',historical_manifest_unchanged=sha(a['gates_file'])==audit['historical_manifest_sha256'],historical_manifest_backup=str(Path(http['artifact']).parent/'historical-manifest.json'),new_manifest_issued=False,http_probe=http,gate_review={},files_created=['audit.py','audit.json','http_probe.py','http-result.json','close.py','closure.json'],cross_module_impact='NONE: no runtime/tests/shared documentation/service configuration changed')
for name,g in sorted(m['gates'].items()):
 artifact=json.loads(d.private_file(g['artifact']).read_text())
 scopes={'identity_tenant_isolation':['modules/messaging/identity.py','modules/messaging/handlers.py','modules/telchi/assistant/whatsapp_dev_repository.py'], 'business_authorization':['modules/telchi/assistant/handler.py','modules/messaging/handlers.py','modules/telchi/assistant/whatsapp_dev_repository.py'], 'durable_idempotency':['modules/messaging/service.py','modules/messaging/repository.py','modules/telchi/assistant/repository.py','modules/db/transaction.py'], 'assistant_foundation':['modules/telchi/assistant/capabilities.py','modules/telchi/datalake/messaging_sales_query.py','modules/telchi/datalake/foundation_reader.py','modules/telchi/datalake/foundation_publication.py'], 'model_no_fallback':['modules/telchi/assistant/luna.py'], 'http_auth':['modules/telchi/assistant/whatsapp_dev.py','modules/messaging/webhooks/evolution_whatsapp.py']}
 r['gate_review'][name]=dict(historical_artifact=g['artifact'],historical_sha256=g['sha256'],historical_integrity=sha(g['artifact'])==g['sha256'],historical_scope=g['scope'],current_scoped_hashes={p:sha(B/p) for p in scopes[name]},decision='NEW_LOCAL_HTTP_PASS; CONTAINER_INGRESS_BLOCKED' if name=='http_auth' else 'HISTORICAL_REUSE_CANDIDATE_NOT_REEXECUTED',review_basis='Approval/sender/workspace/instance match historical evidence; scope implementation matches prior closure per-file inventory. Only launcher/helper/tests have post-historical mtimes. Mtimes are corroboration, NOT cryptographic historical parity.',limitations='Historical aggregate source hash lacks a complete pre-lifecycle per-file/config baseline. Do not claim an independently proven cross-version identity or a new live run.')
 if name in {'identity_tenant_isolation','business_authorization'}:r['gate_review'][name]['fixture_limit']='Synthetic negative fixtures were deactivated; their permission to create/use expired after the recorded run. No fixture reactivation authorized or performed.'
 if name=='durable_idempotency':r['gate_review'][name]['scope_limit']='Historical real PG inbox/outbox and handler-at-most-once only; recording sender, not real delivery.'
 if name=='assistant_foundation':r['gate_review'][name]['scope_limit']='Fixed source_quantity period 2026-01-01..2026-09-16 exclusive; recorded publication foundation_afd08d9eca6a725be53cdc3f9d5709c9 snapshot 1408. No business query repeated; no new current publication attestation issued.'
 if name=='model_no_fallback':r['gate_review'][name]['scope_limit']='Historical real OpenAI direct gpt-5.6-luna / medium. Adapter pins model/effort, checks response echo, trust_env=False and no retries/fallback. No generation/benchmark repeated; present provider availability is not claimed.'
try:
 asyncio.run(d.check_database(a,settings,srv.evolution));r['postgres_read_only']='PASS: binding, approved identity, receiver, effective permission, transport and identity schema'
except Exception as exc:r['postgres_read_only']='BLOCKED:'+type(exc).__name__
try:d.gate_evidence(a);r['gate_evidence']='VALID'
except Exception as exc:r['gate_evidence']=dict(result='BLOCKED',error_class=type(exc).__name__,code=str(exc) if isinstance(exc,(ValueError,PermissionError)) else 'private')
# Execute the actual module CLI with the same sanitized effective configuration.
p=subprocess.run([sys.executable,'-m',d.MODULE,'preflight','--approval',str(apath)],capture_output=True,text=True,timeout=30,env=dict(os.environ))
r['preflight_cli']=dict(command='python -m modules.telchi.assistant.whatsapp_dev preflight --approval PRIVATE_APPROVAL',exit_code=p.returncode,stdout=p.stdout.strip(),stderr=p.stderr.strip())
try:
 with d.client_for(srv.evolution) as client:d.api(client,'GET','/instance/connectionState/'+srv.evolution.instance)
 r['evolution_read_only']='CONNECTED'
except Exception as exc:r['evolution_read_only']=dict(result='BLOCKED',error_class=type(exc).__name__,endpoint='127.0.0.1:18180',container_state='created (read-only podman inspect)')
r['historical_backup_exact']=Path(r['historical_manifest_backup']).read_bytes()==Path(a['gates_file']).read_bytes()
r['source_stable_at_end']=d.source_digest()==audit['source_sha256'];r['config_stable_at_end']=sha(cpath)==audit['config_sha256'];r['approval_stable_at_end']=d.approval_digest(d.read_approval(apath))==audit['approval_sha256']
r['result']=dict(TELCHIAI_GATES='BLOCKED',SOURCE_FINGERPRINT=r['source_fingerprint'],APPROVAL='VALID',MANIFEST='BLOCKED',PREFLIGHT='PASS' if p.returncode==0 else 'BLOCKED',READY_FOR_LIFECYCLE_TEST='NO')
r['blockers']=['Evolution is unavailable on 127.0.0.1:18180 and the configured evolution-api container is created, not running. No container-to-owned-listener auth/reachability or inactive/restorable webhook readback could be certified. No authority to start it.', 'Historical scoped evidence is intact, but its aggregate digest does not supply complete historical per-file/config parity. Candidates and exact current hashes retained; no automatic six-PASS inheritance or replacement manifest issued.']
r['next_action']='Operator makes the existing Evolution service available without changing the approved DEV scope. Then complete the inert container ingress/readback and scoped parity review before issuing a manifest; do not repeat business/model/idempotency batteries.'
(R/'closure.json').write_text(json.dumps(r,indent=2)+'\n')
d.save_private(Path(http['artifact']).parent/'renewal-closure.json',r)
print(json.dumps(dict(result=r['result'],postgres=r['postgres_read_only'],gate_evidence=r['gate_evidence'],preflight_exit=p.returncode,historical_backup_exact=r['historical_backup_exact'],source_stable_at_end=r['source_stable_at_end'],next_action=r['next_action']),indent=2))
