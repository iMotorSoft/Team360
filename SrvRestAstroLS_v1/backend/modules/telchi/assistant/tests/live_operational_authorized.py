"""Five owner-authorized DEV questions through real identity/RBAC/Luna/PG.

Reuses the existing dispatcher probe; no mock, direct reader substitute,
listener, SAP, scheduler or transport. Diagnostic budgets are reported explicitly.
"""
import argparse
import asyncio
import json
from pathlib import Path
from .live_business_close import run

QUESTIONS = [
    '¿Cuánto stock tenemos del producto con código SAP E00003 por depósito?',
    '¿Cuántas líneas de consumo de producción registramos en octubre de 2026?',
    '¿Cuántas facturas de proveedores activas registramos en octubre de 2026 y cuál es su importe?',
    '¿Cuántos pagos activos registramos en octubre de 2026 y cuál es su importe?',
    '¿Cuántas líneas elegibles de consumo de materiales se registraron en octubre de 2026?',
]


async def main(args):
    args.output.mkdir(parents=True, exist_ok=True)
    for index, question in enumerate(QUESTIONS):
        path = args.output/f'luna-{index+1}.json'
        if path.exists():
            raise RuntimeError('refusing to overwrite evidence')
        result = await run(questions=[question], diagnostic_dev=True,
            diagnostic_worker_seconds=args.worker_seconds, diagnostic_turn_seconds=args.worker_seconds+60,
            checkpoint=path)
        result['budgets'] = dict(worker_seconds=args.worker_seconds,turn_seconds=args.worker_seconds+60,
                                 model_seconds=20,model_attempts=1,production_changed=False)
        path.write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker-seconds',type=int,default=180)
    asyncio.run(main(p.parse_args()))
