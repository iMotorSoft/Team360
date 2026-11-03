"""Reuse bounded Full Gate runner; unit tests only, external opt-ins removed."""
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND / 'scripts'))
from validate_team360_full_stack import run_child, host_preflight
names = sorted(p.name for p in (BACKEND / 'tests').glob('test_sales_diagnosis*.py'))
names += ['test_diagnosis_public_router.py', 'test_embed_clients_contract.py', 'test_knowledge_scope_resolver.py', 'test_automation_diagnosis_litellm.py']
env = dict(os.environ, AUTOMATION_DIAGNOSIS_REPOSITORY='memory', TEAM360_AI_PROVIDER='mock')
for key in list(env):
    if key.endswith(('_POSTGRES_TEST', '_INTEGRATION_TEST')):
        env.pop(key)
command = [sys.executable, '-m', 'pytest', '-q', '--tb=no', '-p', 'no:cacheprovider', *['tests/' + n for n in names]]
r = {'timestamp': datetime.now(timezone.utc).isoformat(), 'host': host_preflight(), 'command': command[1:]}
if r['host']['status'] == 'SAFE':
    c = run_child(command, env, 180)
    r.update(returncode=c.returncode, pid=c.pid, session_cleanup_verified=True,
             output=c.stdout, status='PASS' if c.returncode == 0 else 'FUNCTIONAL_FAILURE')
else:
    r['status'] = 'RESOURCE_BLOCKED'
Path(__file__).with_name('supplemental-tests.json').write_text(json.dumps(r, indent=2) + '\n')
print(r['status']); print(r.get('output', '')[-2000:])
