"""Opt-in bounded DEV evidence. No SAP, publication, entitlement or service changes.

--readers: canonical reader + independent Python Decimal/raw-capture controls.
--luna: actual approved identity/Console/PG/Luna pipeline (denial is not PASS).
"""
import argparse
import asyncio
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path
from time import perf_counter

from modules.telchi.datalake.operational_query import execute_on, validate_result, PERMISSIONS

PERIOD = dict(date_from='2026-10-01',date_to_exclusive='2026-11-01',limit=50)
QUESTIONS = {
    'production.consumption':'¿Qué materias primas consumimos durante octubre de 2026?',
    'purchasing.invoiced_amount':'¿Cuánto facturaron los proveedores durante octubre de 2026?',
    'collections.received_amount':'¿Cuánto cobramos durante octubre de 2026?',
    'material_supply.consumption':'¿Qué materiales registraron mayor consumo durante octubre de 2026?',
}


def readers():
    from modules.telchi.datalake.ducklake import DuckLakeConnector
    from modules.telchi.datalake.foundation_reader import FoundationReader
    from modules.telchi.datalake.operational_domains import files_relation, records, literal
    from modules.telchi.datalake import sales_incremental as durable
    from modules.telchi.datalake.query_profile import Trace
    from modules.telchi.assistant.capabilities import format_result
    connector = DuckLakeConnector()
    trace = Trace()
    with trace.activate(), connector.session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        access = FoundationReader(connector).resolve_on(con)
        stable = access.manifest['operational_observations']
        proof = durable.read_json(Path(stable['reconciliation_path']))
        assert durable.digest(proof) == stable['reconciliation_sha256']
        captures = proof['captures']['captured_datasets']
        def raw(name):
            files = captures[name]['file_hashes']
            for f in files:
                assert durable.file_hash(Path(f['path'])) == f['sha256']
            return files_relation([f['path'] for f in files])
        # Select a real code from captured issue identities, not a fabricated X.
        issues = records(con,'SELECT * FROM '+raw('production_issue'))
        code = sorted({r['ItemCode'] for r in issues if r['ItemCode']})[0]
        questions = {'inventory.stock_by_warehouse':f'¿Cuánto stock tenemos del producto con código SAP {code} por depósito?'} | QUESTIONS
        result = dict(foundation=access.as_dict(), tests=[], question_matrix=[],model_or_auth_exercised=False,
                      publications=0,sap_queries=0, entitlement_changes=0)
        orders = {r['DocEntry'] for r in records(con,'SELECT "DocEntry" FROM '+raw('production_order'))}
        items = {r['ItemCode'] for r in records(con,'SELECT "ItemCode" FROM '+raw('oitm'))}
        for metric, question in questions.items():
            started = perf_counter()
            options = {'item_code':code,'limit':50} if metric.startswith('inventory.') else dict(PERIOD)
            actual = validate_result(metric,options,execute_on(con,access,metric,options))
            if metric.startswith('inventory.'):
                stock = records(con,'SELECT "WhsCode","OnHand","IsCommited" FROM '+raw('stock')+' WHERE "ItemCode"='+literal(code))
                expected = sorted([(r['WhsCode'],Decimal(str(r['OnHand'])),Decimal(str(r['IsCommited']))) for r in stock])
                observed = sorted([(r['warehouse'],Decimal(r['on_hand_qty']),Decimal(r['committed_qty'])) for r in actual['rows']])
                assert actual['total_rows']==len(expected)
                assert expected[:options['limit']]==observed
                control = {'positions':len(expected),'presented_native_quantities_exact':True,'omitted_positions':actual['omitted_rows']}
            elif metric.startswith('purchasing.'):
                source = records(con,'SELECT * FROM '+raw('ap_invoice'))
                expected = defaultdict(lambda:[0,Decimal(0)])
                for r in source:
                    if '2026-10-01' <= str(r['DocDate'])[:10] < '2026-11-01' and r['CANCELED']=='N' and r['DocCur']=='BS':
                        expected[r['DocStatus']][0]+=1
                        expected[r['DocStatus']][1]+=Decimal(r['DocTotal'])
                assert {r['document_status']:(r['documents'],Decimal(r['amount'])) for r in actual['rows']} == {k:tuple(v) for k,v in expected.items()}
                control = {k:{'documents':v[0],'amount_bs':str(v[1])} for k,v in expected.items()}
            elif metric.startswith('collections.'):
                source = records(con,'SELECT * FROM '+raw('collection_payment'))
                paid = [r for r in source if '2026-10-01'<=str(r['payment_date'])[:10]<'2026-11-01' and r['cancelled']=='N' and r['currency']=='BS']
                expected = sum((Decimal(r['payment_total']) for r in paid),Decimal(0))
                assert actual['rows'][0]['payments']==len(paid) and Decimal(actual['rows'][0]['amount'])==expected
                control = dict(payments=len(paid),amount_bs=str(expected))
            else:
                expected = defaultdict(lambda:[0,Decimal(0)])
                for r in issues:
                    if not ('2026-10-01'<=str(r['DocDate'])[:10]<'2026-11-01' and r['CANCELED']=='N' and Decimal(str(r['BaseType']))==202):
                        continue
                    if metric.startswith('material_supply.') and not (r['ItemCode'] in items and r['BaseEntry'] in orders and (str(r['unitMsr'] or '').strip() or str(r['UomCode'] or '').strip())):
                        continue
                    k=tuple(r[f] for f in ('ItemCode','unitMsr','UomCode','NumPerMsr'))
                    expected[k][0]+=1; expected[k][1]+=Decimal(r['Quantity'])
                for r in actual['rows']:
                    k=tuple(r[f] for f in ('item_code','unit','uom_code','native_factor'))
                    assert (r['issue_lines'],Decimal(r['quantity']))==tuple(expected[k])
                assert actual['total_rows']==len(expected)
                assert actual['controls']['included_issue_lines']==sum(v[0] for v in expected.values())
                control = dict(all_groups=len(expected),included_lines=sum(v[0] for v in expected.values()),
                               presented_groups_exact=True, source_native_decimal_control=True)
            entry = dict(question=question,capability=actual['capability'], reader='FoundationReader / FoundationAccess',
                datasets=actual['source']['datasets'],metric=metric,permission=PERMISSIONS[metric],coverage=actual['coverage'],
                response=format_result(actual),result=actual,independent_control=control, parity='EXACT',elapsed_ms=(perf_counter()-started)*1000,
                authorization='NOT_EXERCISED_IN_READER_CONTROL')
            result['question_matrix'].append(entry)
        result['supplemental_readers']=[]
        from modules.telchi.datalake.operational_query import OPERATIONS
        bom_code=con.execute('SELECT "Father" FROM '+access.operational_observation('production','bom_line')+' ORDER BY "Father" LIMIT 1').fetchone()[0]
        for metric in OPERATIONS.keys()-questions.keys():
            options={'item_code':bom_code,'limit':10} if metric=='production.bom' else dict(PERIOD,limit=10)
            actual=validate_result(metric,options,execute_on(con,access,metric,options))
            result['supplemental_readers'].append(dict(metric=metric,result=actual,guarantee='REAL_READER_EXECUTION_NOT_AUTHORIZED_RUNTIME_OR_INDEPENDENT_PARITY'))
        result['legacy_components']=access.manifest['components']
        result['trace']=trace.export()
        return result


async def luna(questions):
    from .live_business_close import run
    result = {'turns':[],'entitlement_changes':0,'whatsapp_sent':0}
    for question in questions:
        report = await run(questions=[question],diagnostic_dev=True,diagnostic_worker_seconds=180,diagnostic_turn_seconds=240)
        result['model_preflight']=report['model_preflight']
        result['turns'].extend(report['turns'])
    result['business_runtime_pass']=len(result['turns'])==5 and all(t['classification']=='DIRECT_AVAILABLE' for t in result['turns'])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--readers',action='store_true')
    p.add_argument('--metric',choices=list(PERMISSIONS),help='Only this question in a focused Luna recheck')
    p.add_argument('--luna',type=Path,help='Reader evidence supplies real stock code/question')
    a=p.parse_args()
    if a.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    if a.readers:
        report=readers()
    elif a.luna:
        evidence=json.loads(a.luna.read_text())
        report=asyncio.run(luna([r['question'] for r in evidence['question_matrix'] if a.metric is None or r['metric']==a.metric]))
    else:
        p.error('choose --readers or --luna')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:
        json.dump(report,f,ensure_ascii=False,indent=2,default=str)
        f.write('\n')
    print(json.dumps({'output':str(a.output),'questions':len(report.get('question_matrix',report.get('turns',[]))),
                      'business_runtime_pass':report.get('business_runtime_pass')},ensure_ascii=False))


if __name__=='__main__':
    main()
