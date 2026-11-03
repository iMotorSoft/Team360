"""Focused real Luna/Console/PostgreSQL/Foundation probe, never WhatsApp outbound."""
import argparse
import asyncio
import json
from pathlib import Path

from . import live_business_close as existing

QUESTIONS = [
    'Cuánto facturamos en septiembre de 2026',
    '¿Cuánto facturamos en septiembre de 2026?',
    '¿Y en agosto?',
    '¿Cuál fue la diferencia?',
    '¿Y en porcentaje?',
    'Mostrame las últimas cinco facturas.',
    '¿Qué productos tiene la primera?',
    '¿Cuánto vale esa factura?',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    existing.QUESTIONS = QUESTIONS
    report = asyncio.run(existing.run())
    turns = report['turns']
    report['quality_pass'] = (len(turns) == 8 and all(t['classification'] == 'DIRECT_AVAILABLE' for t in turns)
        and all(t['audit']['capability_calls'] == 0 and t['audit'].get('monetary_calculation') for t in turns[3:5])
        and '-1.673.673,34' in turns[3]['text'] and '-15,84' in turns[4]['text']
        and all('parcial' in t['text'] for t in turns[3:5]))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:
        json.dump(report,f,indent=2,ensure_ascii=False)
        f.write('\n')
    print(json.dumps({'quality_pass':report['quality_pass'], 'turns':[
        {k:t[k] for k in ('question','classification','text')} for t in turns]},ensure_ascii=False,indent=2))
    if not report['quality_pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
