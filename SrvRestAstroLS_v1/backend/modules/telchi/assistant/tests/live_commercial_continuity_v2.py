"""Real persisted DEV pipeline; no WhatsApp, service changes or permission writes."""
import argparse
import asyncio
import json
from decimal import Decimal, localcontext
from pathlib import Path
from . import live_business_close as existing

QUESTIONS = [
    'Cuánto facturamos en septiembre de 2026',
    'y cuanto vendimos de productos terminados ese mes',
    'mostrame el top 5 de esos productos por importe vendido',
    'que puesto tuvo L03281 en julio y agosto de 2026',
    'cual fue el principal cliente facturado SAP de ese producto en esos dos meses',
    'cuanto nos compro ese cliente en cada uno de esos meses',
    'y que otros productos nos compro en esos meses',
    'ahora quiero la facturacion total global de septiembre de 2026, sin filtrar por cliente ni producto',
    'quiero saber el porcentaje de la venta total de septiembre cual es el porcentaje de productos terminados, medicamentos, materia prima, fraccionados',
    'el procentaje de venta de productos terminados',
    'y el porcentaje de materia prima de la venta total de agosto de 2026',
    'volvamos a la facturacion global de septiembre de 2026',
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    existing.QUESTIONS = QUESTIONS
    report = asyncio.run(existing.run())
    turns = report['turns']
    checks = []
    for index, turn in enumerate(turns):
        a = turn['audit']
        ok = turn['classification'] == 'DIRECT_AVAILABLE' and not a.get('contract_error')
        if index in (0, 7, 11):
            ok &= '8.891.439,79' in turn['text'] and a['confirmed_state']['period']['start'] == '2026-09-01'
        if index == 1:
            ok &= '2.679.208,66' in turn['text']
        if index == 2:
            ok &= '5.' in turn['text'] and '259.922,61' in turn['text']
        if index == 3:
            ok &= 'puesto 2' in turn['text'] and 'puesto 1' in turn['text']
        if index == 4:
            ok &= 'FARMACORP' in turn['text'] and '115.044,44' in turn['text']
        if index == 5:
            ok &= '72.383,99' in turn['text'] and '42.660,45' in turn['text']
        if index == 6:
            state = a['confirmed_state']
            ok &= (state['customer_target'] == 'C000061' and state['excluded_product'] == 'L03281'
                   and state['business_category'] is None and state['product_target'] is None
                   and state['period']['start'] == '2026-07-01' and 'L03281 ·' not in turn['text'])
            rows = [r for r in a['execution_result']['rows'] if r['key'] != 'L03281'][:5]
            ok &= len(rows) == 5 and all(r['key'] + ' · ' + r['label'] in turn['text'] for r in rows)
        if index in (8, 9):
            state = a['confirmed_state']
            analysis = a.get('category_analysis') or {}
            ok &= (state['period']['start'] == '2026-09-01' and not state.get('customer_target')
                   and not state.get('product_target') and not state.get('periods')
                   and analysis.get('denominator_status') == 'VERIFIED')
            denominator = analysis['denominator']
            with localcontext() as ctx:
                ctx.prec = 50
                whole = Decimal(denominator['total']['amount'])
                ok &= sum((Decimal(r['amount']) for r in denominator['full_breakdown']), Decimal(0)) == whole
                for code, value in analysis['percentages'].items():
                    amount = Decimal(analysis['components'][code]['result']['rows'][0]['amount'])
                    ok &= Decimal(value) == (amount / whole * 100).quantize(Decimal('0.01'))
            ok &= '2.679.208,66' in turn['text'] and '33,29' in turn['text']
        if index == 10:
            analysis = a.get('category_analysis') or {}
            component = analysis.get('components', {}).get('RAW_MATERIAL', {})
            ok &= (a['confirmed_state']['period']['start'] == '2026-08-01'
                   and bool(component.get('result')) and component['status'] == 'partial'
                   and 'Resultado parcial' in turn['text'] and not analysis['percentages'])
        checks.append(bool(ok))
    report['evaluation'] = dict(conversation_turns=len(turns), correct_turns=sum(checks), turn_checks=checks,
        all_correct=len(turns) == len(QUESTIONS) and all(checks),
        whatsapp_response_length=all(len(t['text']) <= 4096 for t in turns),
        response_lengths=[len(t['text']) for t in turns],
        scope='real local persisted dispatch; no WhatsApp E2E; category composition partial because medications are unclassified')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write('\n')
    for index, turn in enumerate(report['turns'], 1):
        print(json.dumps(dict(turn=index, question=turn['question'], classification=turn['classification'],
                             text=turn['text'], model=turn['model'],
                             contract_error=turn['audit'].get('contract_error')), ensure_ascii=False))


if __name__ == '__main__':
    main()
