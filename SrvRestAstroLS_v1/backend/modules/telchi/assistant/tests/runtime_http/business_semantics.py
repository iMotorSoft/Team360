"""Natural HTTP questions through the existing DEV adapter; own servers only."""
import argparse
import json
import os
from pathlib import Path
import secrets
import uuid
import httpx
from .run_battery import (_load_env_file,_pilot_phone,_binding_metadata,_free_port,start_server,stop_server)


QUESTIONS=[
 ('S01','Dame ventas de farmacia'),('S02','¿Cuánto le vendimos a menona?'),
 ('S03','¿Qué hay que importar?'),('S04','Dame las deudas'),('S05','Mostrame las ventas perdidas'),
 ('S06','¿Qué negocios presupuestamos y no se concretaron?'),
 ('A01','Dame las ventas horizontales de septiembre'),
 ('A02','¿Cuánto vendió el canal corporativo en mayo?'),
 ('A03','Mostrame las ventas de Selva Rojas'),('A04','¿Cuánto vendió la Dra. Luz?'),
 ('A05','¿Cuáles son los vendedores corporativos?'),('A06','Compará ventas corporativas y horizontales'),
 ('S07','Dame ventas de Calenta'),('S08','Dame el indicador empresarial ZXQ903718'),
 ('R01','Ventas de mayo de 2026'),('R02','Ventas de junio de 2026'),
 ('R03','Dame las últimas 10 facturas de venta registradas'),
 ('R04','¿Cuál es la última fecha de ventas registrada?'),
 ('R05','Top 10 por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros')]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--only', help='Comma-separated case IDs; preserves previous full evidence')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if os.getenv('TEAM360_ENV')!='dev' or os.getenv('TEAM360_BUSINESS_SEMANTICS')!='1':
        raise ValueError('explicit_semantics_DEV_required')
    base=_load_env_file()
    instance=base.get('TEAM360_EVOLUTION_INSTANCE') or os.getenv('TEAM360_EVOLUTION_INSTANCE','')
    if not instance:
        raise ValueError('existing_instance_configuration_required')
    metadata=_binding_metadata('telchi_dev','telchi_whatsapp_dev',instance)
    phone=_pilot_phone(instance)
    receiver=metadata.get('receiver_context') or metadata.get('receiver_phone_number_id')
    if not receiver:
        raise ValueError('existing_receiver_context_required')
    port=_free_port();token=secrets.token_hex(32);run=str(uuid.uuid4())[:8]
    report={'run_id':run,'turns':[],'own_processes_left_running':None,'unrelated_processes_terminated':0}
    process=None
    try:
        process,url=start_server(base,phone,receiver,port,token,args.output/'http-server.log')
        def turn(case,text,conversation):
            with httpx.Client(trust_env=False,timeout=100) as client:
                response=client.post(url+'/api/telchi/assistant/dev/turn',
                                     headers={'x-team360-dev-token':token},json={'text':text,'conversation':conversation})
            body=response.json()
            audit=body.get('audit') or {}
            body['audit']={k:v for k,v in audit.items() if k!='owner'}
            report['turns'].append({'case':case,'question':text,'http_status':response.status_code,**body})
            (args.output/'http_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(case,response.status_code,body.get('classification'),audit.get('committed'),flush=True)
            return body
        selected=set(args.only.split(',')) if args.only else None
        for case,text in QUESTIONS:
            if selected is None or case in selected:
                turn(case,text,run+'-'+case)
        if selected is None or 'S07' in selected:
            turn('S07_LATEST','Dame las últimas ventas de Calenta',run+'-product-latest')
            turn('S07_SEARCH','Buscá Calenta',run+'-product-search')
            turn('S07_FROM_SEARCH','Mostrame las últimas ventas de todos esos productos',run+'-product-search')
        if selected is None or 'FOLLOWUP' in selected:
            turn('KNOWN_START','Dame ventas de menona',run+'-known-followup')
            turn('KNOWN_PERIOD','Mayo de 2026',run+'-known-followup')
            turn('KNOWN_NEW_QUERY','Nueva consulta: ventas de mayo de 2026',run+'-known-followup')
        turn('NEW_CONVERSATION','Dame ventas de farmacia',run+'-new')
        stop_server(process);process=None
        process,url=start_server(base,phone,receiver,port,token,args.output/'http-server-restart.log')
        turn('AFTER_RESTART','Dame ventas de farmacia',run+'-after-restart')
        report['restart_completed']=True
    finally:
        if process is not None:
            stop_server(process)
        report['own_processes_left_running']=0
        (args.output/'http_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
