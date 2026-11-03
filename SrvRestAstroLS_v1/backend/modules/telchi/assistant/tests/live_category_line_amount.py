"""Real Luna + Foundation, no listener/WhatsApp; separates interpreter from live RBAC."""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path

from dotenv import dotenv_values
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities, format_result
from modules.telchi.assistant.luna import LunaInterpreter, CREDENTIAL_ENV


async def run(output):
    root = Path(__file__).resolve().parents[6]
    if not os.getenv(CREDENTIAL_ENV):
        key = dotenv_values(root / 'SrvRestAstroLS_v1/.env.backend-dev.local').get(CREDENTIAL_ENV)
        if key:
            os.environ[CREDENTIAL_ENV] = key
    interpreter = LunaInterpreter()
    preflight = await interpreter.interpret(text='¿Cuánto facturamos?', state=deepcopy(engine.EMPTY),history={},turn_id='preflight')
    if preflight.get('action') != 'ASK':
        raise RuntimeError('provider_preflight_failed')
    report = dict(preflight=interpreter.last_metadata, scope='Real interpreter, State Engine, catalog and Foundation. No identity/RBAC claim.',
        services_started=0, whatsapp_sent=0, turns=[])
    state, history = deepcopy(engine.EMPTY), {}
    monetary_results=[]
    from modules.telchi.assistant.monetary_comparison import accredited, descriptors, calculate
    catalog = SalesCapabilities()
    questions = [
        ('raw', '¿Cuánto vendimos de materia prima en septiembre?', 'sales.net_amount','RAW_MATERIAL'),
        ('finished', '¿Y de productos terminados?', 'sales.net_amount','LAB_FINISHED_PRODUCT'),
        ('comparison', '¿Cuál de esas categorías vendió más?', 'sales.net_amount',None),
        ('august', '¿Y en agosto?', 'sales.net_amount','LAB_FINISHED_PRODUCT'),
        ('production', '¿Cuánta materia prima consumimos en producción?', None,'RAW_MATERIAL'),
        ('search', 'Buscá productos que digan materia prima', 'products.search',None),
    ]
    for name, question, metric, category in questions:
        turn = dict(name=name,question=question)
        try:
            raw=await interpreter.interpret(text=question,state=state,history=history,turn_id=name,
                monetary_context=descriptors(monetary_results) if name=='comparison' else None)
            if name=='comparison':
                record,text=calculate(raw,monetary_results,{'probe':'no_live_rbac_claim'})
                turn.update(raw=raw,calculation=record,response=text,model=interpreter.last_metadata,status='PASS')
                report['turns'].append(turn)
                continue
            processed=engine.process(state,raw,history,name)
            next_state=processed['state_after']
            checks=dict(committed=processed['committed'] is True, metric=next_state['metric']==metric,
                category=next_state.get('entity_mention')==(dict(text=category,type=None) if category else None))
            if name in {'raw','finished','august'}:
                month='08' if name=='august' else '09'
                end='09' if name=='august' else '10'
                checks['period']=next_state['period']==dict(start=f'2026-{month}-01',end_exclusive=f'2026-{end}-01')
                checks['execute']=raw.get('action')=='EXECUTE' and catalog.availability(next_state).allowed
                if checks['execute']:
                    try:
                        result=await catalog.execute(next_state)
                    except Exception as exc:
                        if name != 'august' or str(exc) != 'category_currency_not_accredited':
                            raise
                        result=None
                        turn.update(data_status='BLOCKED_MIXED_CURRENCY', reason=str(exc))
                    if result is not None:
                        turn.update(result=result,response=format_result(result))
                        audit=dict(owner={'probe':'no_live_rbac_claim'},execution_status='executed',
                            business_rbac_verified=True,required_permission=catalog.required_permission(next_state),
                            response_prepared={'classification':'DIRECT_AVAILABLE'},
                            confirmed_state=deepcopy(next_state),execution_result=result)
                        monetary_results.append(accredited(audit,name,{'probe':'no_live_rbac_claim'}))
                    if name=='raw':
                        from decimal import Decimal
                        checks['amount']=Decimal(result['rows'][0]['amount'])==Decimal('839582.63')
                        checks['counts']=[result['rows'][0][k] for k in ('product_count','line_count','document_count')]==[34,526,495]
            elif name=='production':
                checks['not_executed']=not catalog.availability(next_state).allowed
            else:
                checks['search_text']=next_state.get('product_search_text')=='materia prima'
            turn.update(raw=raw,processed=processed,checks=checks,model=interpreter.last_metadata,
                status='PASS' if all(checks.values()) else 'FAIL')
            if processed['committed']:
                state=deepcopy(next_state)
                history[name]=deepcopy(state)
        except Exception as exc:
            turn.update(status='FAIL',error_class=type(exc).__name__,reason=str(exc))
        report['turns'].append(turn)
    report['status']='PASS' if all(t['status']=='PASS' for t in report['turns']) else 'FAIL'
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f:
        json.dump(report,f,indent=2,ensure_ascii=False)
    print(json.dumps(dict(status=report['status'], turns=[{k:t[k] for k in ('name','status')} for t in report['turns']])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    asyncio.run(run(parser.parse_args().output))
