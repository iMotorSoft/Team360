"""Read-only renewal inventory. No credentials printed, no services started."""
import sys, os, json, hashlib
from pathlib import Path
from datetime import datetime, timezone
B=Path(__file__).resolve().parents[4]/'SrvRestAstroLS_v1/backend'
sys.path.insert(0,str(B)); os.chdir(B)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
config_path=d.PRIVATE_ROOT/'whatsapp-dev-control.json'
config=l.load_config(config_path)
a=d.read_approval(config.get('approval',d.PRIVATE_ROOT/'whatsapp-dev-session-approval.json'))
srv,settings=d.configuration()
m=json.loads(d.private_file(a['gates_file']).read_text())
paths={B/'ls_iMotorSoft_Srv05.py',B/'ls_iMotorSoft_Srv01.py',B/'modules/srv05_settings.py'}
for root in ('telchi/assistant','telchi/datalake','messaging','console','db'):paths.update((B/'modules'/root).rglob('*.py'))
files={str(p.relative_to(B)):sha(p) for p in sorted(paths)}
old=json.loads((B.parents[1]/'data/reports/telchi/lifecycle-operational-closure-v1/inventory.json').read_text())['covered_python_files']
r=dict(generated_at=datetime.now(timezone.utc).isoformat(),source_sha256=d.source_digest(),approval_sha256=d.approval_digest(a),approval_expires_at=a['expires_at'],approval_valid=True,config_sha256=sha(config_path),host=config['host'],port=config['port'],covered_python_files=files,changes_since_closure=[p for p in sorted(set(files)|set(old)) if files.get(p)!=old.get(p)],historical_manifest_sha256=sha(a['gates_file']),historical_source_sha256=m['source_sha256'],gates={},post_historical_source_mtimes={str(p.relative_to(B)):datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat() for p in paths if p.stat().st_mtime>datetime.fromisoformat(m['generated_at']).timestamp()})
for name,g in m['gates'].items():
 p=d.private_file(g['artifact']); artifact=json.loads(p.read_text())
 r['gates'][name]=dict(integrity=sha(p)==g['sha256'],sha256=sha(p),approval_matches=artifact.get('approval_sha256')==d.approval_digest(a),source_matches_historical=artifact.get('source_sha256')==m['source_sha256'],scope=g['scope'])
# Fingerprint secrets as part of the whole private file only, not low-entropy values.
r['config_scope']=dict(workspace=settings.workspace_slug,channel=settings.channel_alias,instance=srv.evolution.instance,sender_matches=hashlib.sha256(settings.authorized_sender.encode()).hexdigest()==a['sender_sha256'])
out=Path(__file__).parent/'audit.json';out.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='covered_python_files'},indent=2))
