"""Opt-in focal probes, not a benchmark or WhatsApp delivery certification.

PG/auth/transport use explicitly simulated fixtures. Luna and/or Foundation are
real only with the respective flags. Business rows never enter model context.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.luna import LunaInterpreter, MODEL
from .test_assistant import setup, context, event, latest, plan


async def probe(luna, foundation, preflight=False):
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(), model=MODEL, reasoning='medium',
                  provider='OpenAI direct', simulated=['identity', 'business permission', 'PG persistence', 'transport'],
                  whatsapp_e2e=False, fallback=False, turns=[], foundation=None)
    if luna:
        handler, store, _, calls = setup([])
        handler.interpreter = LunaInterpreter()
        if foundation:
            handler.capabilities = SalesCapabilities()
        texts = ['¿Cuánto vendimos en septiembre?', 'De 2026.', '¿Y en Saavedra?',
                 'Comparalo con agosto.', 'Ahora solamente venta horizontal.',
                 'Quitá la restricción de sucursal y de canal y la comparación.',
                 'Nueva consulta independiente: top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros.']
        if preflight:
            texts = texts[:1]
        for n, text in enumerate(texts):
            result = await handler.handle(event(text), replace(context(), correlation_id=f'probe-{n}'))
            audit = latest(store) if store.audits else None
            report['turns'].append(dict(user_message=text, classification=result.classification,
                interpretation=audit['interpretation_proposed'] if audit else None,
                committed=audit.get('committed') if audit else False,
                decision=audit['decision'] if audit else 'ERROR',
                confirmed_state=audit['confirmed_state'] if audit else None,
                execution_status=audit['execution_status'] if audit else 'not_executed',
                timings=audit['timings'] if audit else None))
            if result.classification == 'ERROR':
                break
        report['controlled_capability_calls'] = len(calls)
        report['luna_metadata'] = handler.interpreter.last_metadata
        executed = [a for a in store.audits.values() if a['execution_status'] == 'executed']
        if foundation and executed:
            a = executed[-1]
            r = a['execution_result']
            report['foundation'] = dict(status='PASS', via='TelchiHandler with simulated PG/auth',
                source=r['source'], capability=r['capability'], period=r['period'], units=r['units'],
                coverage=r['coverage'], limitations=r['limitations'], row_count=len(r['rows']),
                result_hash=hashlib.sha256(json.dumps(r['rows'], sort_keys=True).encode()).hexdigest(),
                elapsed_ms=a['timings']['capability_ms'], sap_accessed=False, read_only=True)
        elif foundation:
            report['foundation'] = dict(status='BLOCKED', error_code='no_verified_handler_result')
    if foundation and not luna:
        # Independent authorized read-only probe, NOT phone-bound execution.
        from time import perf_counter
        start = perf_counter()
        try:
            result = await SalesCapabilities().execute(plan())
            report['foundation'] = dict(status='PASS', source=result['source'],
                capability=result['capability'], period=result['period'], units=result['units'],
                coverage=result['coverage'], limitations=result['limitations'],
                row_count=len(result['rows']), result_hash=hashlib.sha256(json.dumps(result['rows'], sort_keys=True).encode()).hexdigest(),
                elapsed_ms=(perf_counter()-start)*1000, sap_accessed=False, read_only=True)
        except Exception as exc:
            report['foundation'] = dict(status='BLOCKED', error_code=getattr(exc, 'code', type(exc).__name__),
                                        elapsed_ms=(perf_counter()-start)*1000)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--luna', action='store_true')
    parser.add_argument('--foundation', action='store_true')
    parser.add_argument('--preflight', action='store_true', help='Single safe ASK and metadata verification')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.preflight and (not args.luna or args.foundation):
        raise SystemExit('--preflight requires --luna without --foundation')
    report = asyncio.run(probe(args.luna, args.foundation, args.preflight))
    path = Path(args.output)
    if path.exists():
        raise SystemExit('Refusing to overwrite evidence')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'turns': len(report['turns']), 'foundation': (report['foundation'] or {}).get('status')}))


if __name__ == '__main__':
    main()
