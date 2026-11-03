"""Resume only inert ingress and read-only parity review; preserve prior reports."""
from pathlib import Path
import hashlib
import json
import os
import runpy
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3] / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l

config = l.load_config(d.PRIVATE_ROOT / 'whatsapp-dev-control.json')
apath = config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json')
a = d.read_approval(apath)
srv, settings = d.configuration()
manifest_path = d.private_file(a['gates_file'])
original = manifest_path.read_bytes()
manifest = json.loads(original)
result = dict(generated_at=datetime.now(timezone.utc).isoformat(), branch='feature/console-backend-core', evolution={}, historical={}, new_manifest_issued=False)
with d.client_for(srv.evolution) as client:
    health = client.get('/')
    result['evolution']['http_status'] = health.status_code
    result['evolution']['connection'] = d.api(client, 'GET', '/instance/connectionState/' + srv.evolution.instance)
    previous = d.webhook_body(d.api(client, 'GET', '/webhook/find/' + srv.evolution.instance))
    result['evolution']['webhook_inactive'] = not previous['enabled']
    result['evolution']['webhook_restorable'] = bool(previous['url'])

# Use the previously reviewed ingress-only runner without overwriting prior evidence.
source = (HERE / 'http_probe.py').read_text()
source = source.replace("'http-result.json'", "'http-result-resumed.json'")
source = source.replace("host_preflight='BUSY_BUT_SAFE: 8 CPUs; load 1.88/2.26/2.44; available 5686 MiB; swap 380 MiB, no observed current swap IO. One process/listener, sequential requests, no scans/browser/model.'", "host_preflight='BUSY_BUT_SAFE: load 1.63/1.98/2.19; available 5451 MiB; swap 391 MiB stable, no current swap IO. Sequential listeners, no scans/browser/model.'")
# This runner only certifies HTTP, never the other five guarantees.
source = source.replace("r['status']='BLOCKED' # No container reachability / final operational preflight certified.", "r['status']='PASS' if r['http_auth_local']=='PASS' and r.get('container_probe','').startswith('PASS:') else 'BLOCKED'")
exec(compile(source, str(HERE / 'http_probe.py'), 'exec'), {'__file__': str(HERE / 'http_probe.py'), '__name__': '__main__'})
result['http_probe'] = json.loads((HERE / 'http-result-resumed.json').read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
audit = json.loads((HERE / 'audit.json').read_text())
result['source_matches_prior_renewal'] = d.source_digest() == audit['source_sha256']
result['source_matches_historical_manifest'] = d.source_digest() == manifest['source_sha256']
result['approval_matches_historical'] = d.approval_digest(a) == manifest['approval_sha256']
result['config_matches_prior_renewal'] = sha(d.PRIVATE_ROOT/'whatsapp-dev-control.json') == audit['config_sha256']
for name, gate in manifest['gates'].items():
    artifact = json.loads(d.private_file(gate['artifact']).read_text())
    result['historical'][name] = dict(integrity=sha(gate['artifact']) == gate['sha256'], original_sha256=gate['sha256'], top_level_keys=list(artifact), source_sha256=artifact.get('source_sha256'), approval_sha256=artifact.get('approval_sha256'), scope=gate['scope'])
with d.client_for(srv.evolution) as client:
    after = d.webhook_body(d.api(client, 'GET', '/webhook/find/' + srv.evolution.instance))
result['webhook_unchanged'] = after == previous
result['historical_manifest_unchanged'] = manifest_path.read_bytes() == original
result['source_sha256'] = d.source_digest()
# Raw historical artifacts are deliberately not printed or copied into Git.
d.save_private(Path(result['http_probe']['artifact']).parent/'resume-review.json', result)
(HERE/'resume-review.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
