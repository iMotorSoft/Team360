"""BIZ01 through the existing persisted local dispatcher, without outbound."""
import asyncio
import json
from pathlib import Path
from modules.telchi.assistant.tests import live_business_close as probe
from modules.telchi.assistant.tests.runtime_http.run_battery import ACTIVATION_SCENARIOS
from modules.telchi.assistant.tests.runtime_http.biz01_evaluator import evaluate
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
l.load_config(d.PRIVATE_ROOT / 'whatsapp-dev-control.json')
assert l.status()['state'] == 'STOPPED'
d.preflight(d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json', require_gates=False)
probe.QUESTIONS = next(s['turns'] for s in ACTIVATION_SCENARIOS if s['id'] == 'BIZ01')
r = asyncio.run(probe.run())
private = d.PRIVATE_ROOT / ('medications-biz01-' + r['timestamp'].replace(':', '') + '.json')
d.save_private(private, r)
evidence = dict(run_id=r['timestamp'], scenarios=[dict(id='BIZ01', conversation=r['turns'][0]['thread_id'],
    turns=[dict(t, user_text=t['question'], response_text=t['text']) for t in r['turns']])])
ep = private.with_name(private.stem + '-evaluator.json')
d.save_private(ep, evidence)
evaluation = evaluate(ep)
Path(__file__).with_name('biz01.json').write_text(json.dumps(evaluation, indent=2, ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in evaluation.items() if k!='turns'}, ensure_ascii=False))
