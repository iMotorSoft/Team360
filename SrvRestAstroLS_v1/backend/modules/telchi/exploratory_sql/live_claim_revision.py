"""Opt-in LIVE Luna / ISOLATED SYNTHETIC data verification scenario.

Validation harness only. Uses test fixture executor, never Foundation or services.
The initial test hypothesis is model-generated; the controller compiles its
explicit equality test into references after the requested observation arrives.
"""
import argparse
import asyncio
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
import time

from .adaptive_research import SYSTEM
from .adaptive_verifier import reconstruct
from .claim_evidence import EvidenceRegistry, verification_feedback
from .foundation import START, END
from .research import LunaSQL, code_digest
from .test_adaptive_research import fixture_results
from .test_claim_evidence import observe, claim_for


async def run(output):
    start = time.monotonic()
    report = dict(identifier='SYNTHETIC_LIVE_CLAIM_REVISION_V1', scope='ISOLATED_SYNTHETIC_ONLY',
                  real_foundation=False, status='PARTIAL', code_digest=code_digest(), turns=[],
                  model='gpt-5.6-luna', reasoning='medium', fallback=False, queries_cap=4, calls_cap=5)
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+'\n')
    luna = LunaSQL(system=SYSTEM)
    probe = LunaSQL(system='Return exactly a JSON object {"ready":true}.')
    try:
        report['preflight'] = await probe.next({'purpose': 'DEV isolated synthetic claim revision'}, timeout=45)
        if report['preflight'] != {'ready': True}: raise RuntimeError('preflight_failed')
        ctx, refs = fixture_results()
        tables, _ = reconstruct(ctx, refs)
        tables['sales_operation'].append(dict(tables['sales_operation'][0], doc_entry='2', line_num='0',
            sales_channel_code='X', sales_channel_semantic_status='SUPPORTED', line_total=Decimal('0.70')))
        registry = EvidenceRegistry(ctx, tables, (START, END))
        m, q, result = observe(registry, 'SELECT sum(line_total) AS missing_amount FROM sales_operation WHERE sales_channel_code IS NULL')
        initial = dict(scope='ISOLATED SYNTHETIC. These are not real sales.',
            question='¿Es plausible que todas las ventas de este universo carezcan de canal, o sólo una parte? Proponé esa igualdad como hipótesis de trabajo falsable, no como hecho. Elegí tu propia consulta para contrastarla.',
            instruction='For this initial test-plan turn only return {hypothesis:string,hypothesis_state:OPEN,test:equal_missing_and_total,sql:string}. SQL must obtain the full-universe sum of line_total, with any alias you choose. Do not invent the total. Later turns use the normal action contract.',
            observation=dict(evidence_manifest=m, rows=result.rows), catalog=asdict(ctx.catalog))
        value = await luna.next(initial, timeout=90)
        report['initial_hypothesis'] = value
        save()
        if value.get('test') != 'equal_missing_and_total': raise RuntimeError('unsupported_test_plan')
        full, q, result = observe(registry, value['sql'])
        report['turns'].append(dict(sql=value['sql'], authorized=asdict(q), result=asdict(result), evidence_manifest=full))
        # Locate by accredited expression semantics, never model alias.
        index = next(i for i, c in enumerate(full['columns']) if c['metric'] == 'line_amount_bs')
        original = dict(kind='hypothesis_equal', text=value['hypothesis'], dependencies=[
            claim_for(m, value='0.30'), claim_for(full, index, value=str(result.rows[0][index]))])
        check = registry.verify(original)
        report['hypothesis_verification'] = check
        if check['match'] or check['reason'] != 'hypothesis_contradicted_by_observation':
            raise RuntimeError('test_hypothesis_not_contradicted')
        history = [dict(evidence_manifest=m, rows=[['0.30']]),
                   dict(evidence_manifest=full, rows=result.rows), verification_feedback([check])]
        report['feedback'] = history[-1]
        save()
        for _ in range(3):
            value = await luna.next(dict(question='Revisá tu hipótesis inicial a la luz de la contradicción. Podés consultar de nuevo o descartarla; entregá sólo hechos respaldados y distinguí incertidumbre.',
                catalog=asdict(ctx.catalog), observations=history, remaining_query_budget=3-len(report['turns'])), timeout=90)
            report.setdefault('revision_events', []).append(value)
            save()
            if value.get('action') == 'query':
                if len(report['turns']) >= 3:
                    raise RuntimeError('synthetic_query_budget_exhausted')
                manifest, q, result = observe(registry, value['sql'])
                report['turns'].append(dict(sql=value['sql'], authorized=asdict(q), result=asdict(result), evidence_manifest=manifest))
                history.append(dict(evidence_manifest=manifest, rows=result.rows))
                continue
            if value.get('action') != 'final': raise RuntimeError('invalid_revision_action')
            checks = [registry.verify(c) for c in value.get('claims', [])]
            report['final_verifications'] = checks
            report['business_answer'] = registry.render(checks)
            # The original equality cannot become a final accredited fact.
            report['status'] = 'PASS' if checks and all(c['match'] for c in checks) and all(c['claim'].get('kind') != 'hypothesis_equal' for c in checks) else 'PARTIAL'
            return
        report['reason'] = 'model_call_budget'
    except (RuntimeError, ValueError, KeyError, StopIteration) as exc:
        report.update(status='BLOCKED', reason=str(exc)[:180])
    finally:
        report.update(calls=luna.calls, preflight_calls=probe.calls, elapsed_seconds=time.monotonic()-start)
        save()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    output = Path(args.output)
    with output.open('x'): pass
    asyncio.run(run(output))
    print(output)


if __name__ == '__main__': main()
