"""Reuse the canonical inert six-gate probes and atomic publisher, unchanged.

Same window-wrapper pattern as ``whatsapp-orphan-recovery-v1/reaccredit.py`` and
``business-semantics-runtime-closure-v1/reaccredit.py``: the canonical runner
(``data/reports/telchi/six-gates-reaccreditation-20261021/reaccredit.py``) is
loaded as a library and every assertion, probe and publisher stays untouched.

The only adaptation is offline pytest isolation: the canonical runner clears
``os.environ`` and installs the private operational configuration before it
shells out to pytest, which leaks real ``TEAM360_*``/``META_TEAM360_*`` inputs
into unit fixtures. The focused suite is therefore executed with the original
caller environment (captured before the canonical module is loaded) and the
normal ``0o022`` fixture umask, exactly as the previous window documented. The
real HTTP/container, identity, authorization, durable, Foundation and model
observations all run against the current code and private configuration.

No session, no runtime start, no webhook mutation, no WhatsApp message, no
grant, binding, approval, credential or Foundation mutation.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
# Captured BEFORE the canonical module runs load_config(), which clears env.
original_environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
                            PYTHONDONTWRITEBYTECODE='1')
canonical = ROOT / 'data/reports/telchi/six-gates-reaccreditation-20261021/reaccredit.py'
ns = runpy.run_path(str(canonical), run_name='probe_library_only')
d, l, r = ns['d'], ns['l'], ns['r']
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def host_preflight():
    load = Path('/proc/loadavg').read_text().split()[:3]
    mem = {line.split(':')[0]: line.split()[1] for line in
           Path('/proc/meminfo').read_text().splitlines()}
    available_gib = int(mem['MemAvailable']) / 1024 / 1024
    return (f"SAFE: {os.cpu_count()} CPUs; load {'/'.join(load)}; "
            f"MemAvailable {available_gib:.1f} GiB; sequential runner; PG max 3")


r.update(runner_sha256=sha(__file__), canonical_runner_sha256=sha(canonical),
         host_preflight=host_preflight(),
         harness_adaptation='Offline pytest subprocess only: original caller environment without the '
                            'private operational configuration, plus the normal 0o022 fixture umask. '
                            'Real probes and publisher unchanged.')


def focused_tests():
    command = [sys.executable, '-m', 'pytest', 'modules/telchi/assistant/tests',
               'tests/test_messaging_evolution.py', 'tests/test_messaging_horizontal_runtime.py',
               'tests/test_messaging_handlers.py', '-q']
    result = subprocess.run(command, cwd=ns['BACKEND'], capture_output=True, text=True,
                            timeout=900, umask=0o022, env=original_environment)
    path = ns['out'] / 'focused-tests.txt'
    with open(path, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        stream.write(result.stdout + result.stderr)
    tail = result.stdout.strip().splitlines()[-1:]
    return dict(command=command, exit_code=result.returncode, artifact=str(path),
                sha256=sha(path), result=tail[0] if tail else 'NO OUTPUT')


ns['publish'].__globals__['focused_tests'] = focused_tests
try:
    ns['assert_inert_session']()
    runtime = l.status()
    assert runtime['state'] == 'STOPPED' and not runtime['review_reasons']
    assert runtime['webhook'] in {'INTERNAL', 'INACTIVE'}
    r['runtime_review'] = runtime
    http = asyncio.run(ns['http_gate']())
    path = ns['out'] / 'http-container.json'
    d.save_private(path, http)
    ns['gate']('http_auth', http['scope'], artifact=str(path), sha256=sha(path),
               generated_at=http['generated_at'])
    ns['observe']('http_auth', cases=http['observations'],
                  container_auth_reachability=http['container_auth_reachability'],
                  listener_closed=http['listener_closed'], whatsapp_sends=0)
    asyncio.run(ns['run']())
    assert ns['source'] == d.source_digest(), 'source_changed_during_run'
    assert ns['configuration'] == d.configuration_digest(), 'configuration_changed_during_run'
    assert set(r['gates']) == d.GATES
    summary = ns['publish']()
except Exception as exc:
    r.update(status='BLOCKED', error_class=type(exc).__name__,
             error_code=str(exc) if str(exc).replace('_', '').isalnum() else 'private_error',
             error_frames=[dict(file=f.filename, line=f.lineno)
                           for f in traceback.extract_tb(exc.__traceback__)])
    d.save_private(ns['out'] / 'blocked.json', r)
    summary = dict(SIX_GATES='DEGRADED', error_class=type(exc).__name__,
                   error_code=r['error_code'], private_artifact=str(ns['out'] / 'blocked.json'),
                   manifest_changed=ns['mp'].read_bytes() != ns['old_bytes'],
                   error_frames=r['error_frames'])
(HERE / 'reaccreditation.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
sys.exit(0 if summary['SIX_GATES'] == 'VALID' else 1)