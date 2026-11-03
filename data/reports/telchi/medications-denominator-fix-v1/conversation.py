"""Continuous authenticated persisted regression; no listener or WhatsApp."""
import asyncio
import json
from pathlib import Path
from modules.telchi.assistant.tests import live_business_close as probe
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l

probe.QUESTIONS = [
    'Mostrame la composición global de ventas de septiembre de 2026: porcentaje de productos terminados, materias primas, fraccionados y medicamentos.',
    'y el porcentaje de productos terminados',
    'y el porcentaje de materias primas',
    'y el porcentaje de fraccionados',
    'entonces cuanto es el porcentaje de medicamentos vendidos',
    '¿por qué no podés calcularlo?',
    '¿qué información sí tenemos?',
    'volvamos al porcentaje de productos terminados',
]
l.load_config(d.PRIVATE_ROOT / 'whatsapp-dev-control.json')
assert l.status()['state'] == 'STOPPED'
d.preflight(Path(d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'), require_gates=False)
r = asyncio.run(probe.run())
private = d.PRIVATE_ROOT / ('medications-conversation-' + r['timestamp'].replace(':', '') + '.json')
d.save_private(private, r)
summary = dict(private_artifact=str(private), model_preflight=r['model_preflight'], turns=[])
for t in r['turns']:
    a = t['audit']
    summary['turns'].append(dict(question=t['question'], text=t['text'], classification=t['classification'],
        event_id=t['event_id'], thread_id=t['thread_id'], model=t['model'],
        confirmed_state=a.get('confirmed_state'), proposal=a.get('interpretation_proposed'),
        contract_error=a.get('contract_error'), denominator_status=(a.get('category_analysis') or {}).get('denominator_status')))
Path(__file__).with_name('conversation.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n')
print(json.dumps(summary, ensure_ascii=False))
