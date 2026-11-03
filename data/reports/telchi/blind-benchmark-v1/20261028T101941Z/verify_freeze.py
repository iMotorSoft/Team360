"""Hash/inventory check only; no enterprise I/O or model calls."""
import hashlib
import json
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]

def files_in_scope():
    files=set()
    telchi=ROOT/'SrvRestAstroLS_v1/backend/modules/telchi'
    for path in telchi.rglob('*'):
        if path.is_file() and not any(p in {'__pycache__','investigation','.pytest_cache'} for p in path.relative_to(telchi).parts) and path.suffix in {'.py','.json','.md','.toml','.sql'}:
            files.add(path)
    for name in ('AGENTS.md','.agents/skills/team360-project/SKILL.md','SrvRestAstroLS_v1/backend/pyproject.toml','SrvRestAstroLS_v1/backend/uv.lock'):
        files.add(ROOT/name)
    agent=Path.home()/'.pi/agent'
    for name in ('settings.json','models.json'):
        if (agent/name).is_file(): files.add(agent/name)
    installed=Path('/home/issajar/.bun/install/global/node_modules/@earendil-works')
    for package in ('pi-coding-agent','pi-ai','pi-agent-core'):
        base=installed/package
        if (base/'package.json').is_file(): files.add(base/'package.json')
        for path in (base/'dist').rglob('*'):
            if path.is_file() and path.suffix in {'.js','.json'}: files.add(path)
    # Explicit launch disables extensions, MCP, skills and project context.
    # Record installed package sources anyway, without credentials or node_modules.
    for name in ('pi-opencode-bridge','pi-opencode-free','opencode-pi'):
        base=agent/'npm/node_modules'/name
        if base.is_dir():
            for path in base.rglob('*'):
                if path.is_file() and 'node_modules' not in path.relative_to(base).parts and path.suffix in {'.js','.ts','.json'}: files.add(path)
    for name in ('PI_RULES.txt','RUNBOOK.txt','prepare.py','verify_freeze.py','gates.json'):
        files.add(OUT/name)
    return sorted(files)

def digests():
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files_in_scope()}

if __name__=='__main__':
    freeze=OUT/'freeze.json'
    if '--create' in sys.argv:
        if freeze.exists(): raise SystemExit('Existing freeze preserved; create a new experiment directory instead')
        data=digests()
        payload={'scope':'Telchi code including untracked, contracts/tests/docs outside investigation; locks; Pi runtime/provider implementation and effective launch rules',
          'note':'Code/rules frozen; enterprise data binding BLOCKED, not a completed data freeze. No secrets/auth.json or mutable enterprise catalog hashed.',
          'files':data,'inventory_sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()}
        freeze.write_text(json.dumps(payload,indent=2)+'\n')
        print(payload['inventory_sha256'])
    else:
        expected=json.loads(freeze.read_text())['files']; current=digests()
        changed=[p for p in expected if p in current and expected[p]!=current[p]]
        added=sorted(set(current)-set(expected)); deleted=sorted(set(expected)-set(current))
        print(json.dumps({'unchanged':not(changed or added or deleted),'changed':changed,'added':added,'deleted':deleted},indent=2))
        raise SystemExit(bool(changed or added or deleted))
