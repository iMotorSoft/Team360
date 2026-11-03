"""Reuse reviewed six-gate probes; new evidence/output, no runtime session.

Owner authorizes isolated authorization fixtures only, never operational grants.
The existing runner's publish() requires real probes, all focused tests, unchanged
source/configuration, STOPPED/INTERNAL and normal post-publication preflight.
"""
from pathlib import Path
import asyncio
import json
import hashlib

original = Path(__file__).resolve().parent.parent / 'commercial-continuity-v2-final-reaccreditation/reaccredit.py'
ns = dict(__file__=__file__, __name__='reviewed_gate_library')
exec(compile(original.read_text(), str(original), 'exec'), ns)
d, l, r = ns['d'], ns['l'], ns['r']
r['reviewed_runner_sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
r['host_preflight'] = 'SAFE: 8 CPUs, load 1.05/1.48/1.68, 5980 MiB available; sequential runner, bounded PG max 3; no browsers. Swap monitored separately.'
r['correction'] = 'Independent denominator accreditation and owner-scoped explanation reuse; medications numerator absent; real 8-turn conversation and BIZ01 10/10 passed.'
try:
    status = l.status()
    assert status['state'] == 'STOPPED' and status['webhook'] == 'INTERNAL'
    d.preflight(ns['ap'], require_gates=False)
    r['initial_status'] = status
    report = asyncio.run(ns['http_gate']())
    d.save_private(ns['out'] / 'http-container.json', report)
    ns['gate']('http_auth', 'Fresh real inert authenticated HTTP/container boundary; lifespan off; no message, webhook mutation or WhatsApp.', artifact=str(ns['out'] / 'http-container.json'), sha256=ns['sha'](ns['out'] / 'http-container.json'))
    ns['observe']('http_auth', container_auth_reachability=report['container_auth_reachability'], listener_closed=report['listener_closed'])
    asyncio.run(ns['run']())
    assert ns['source'] == d.source_digest()
    assert ns['configuration'] == d.configuration_digest()
    summary = ns['publish']()
    Path(__file__).with_name('six-gates.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
except Exception as exc:
    r['status'] = 'BLOCKED'
    r['error_class'] = type(exc).__name__
    d.save_private(ns['out'] / 'accreditation.json', r)
    import traceback
    print(json.dumps(dict(SIX_GATES='INVALID', error_class=type(exc).__name__,
        frames=[dict(file=Path(f.filename).name, line=f.lineno) for f in traceback.extract_tb(exc.__traceback__)],
        evidence_directory=str(ns['out']), manifest_changed=ns['mp'].read_bytes() != ns['old_bytes'])))
    raise SystemExit(1) from None
