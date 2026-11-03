"""Real DEV HTTP handler negative fixtures and durable product context restart.

Fixtures alter only this owned server's interpreter/authorization, never RBAC
rows or transport. Real Console negative grants are independently read-checked.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from . import run_battery as battery


def serve():
    import uvicorn
    from modules.telchi.assistant.dev_runtime_http import create_dev_app
    from modules.telchi.assistant.handler import BusinessAuthorization
    from modules.telchi.datalake.product_sales_query import PERMISSIONS
    app = create_dev_app()
    handler = app.app.state.messaging_handlers['telchi'].handler
    class Denial(BusinessAuthorization):
        async def allowed(self, context, conn=None, *, required_permission=None):
            if required_permission in PERMISSIONS.values(): return False
            return await super().allowed(context, conn, required_permission=required_permission)
    class Interpreter:
        async def interpret(self, *, text, state, **kw):
            fields = dict(metric='sales.by_products', schema_version=2,
                requested_metrics=['sales.by_products'], entity_mention=None, temporal_reference=None,
                product_search_text='Calenta', selected_item_codes=[])
            if text == 'REJECT': fields['unknown'] = 'EXECUTE'
            if text == 'INVENT': fields['selected_item_codes'] = ['MODEL_INVENTED_903718']
            if text == 'MAY':
                fields.pop('product_search_text'); fields.pop('selected_item_codes')
                fields['period'] = dict(start='2026-05-01',end_exclusive='2026-06-01')
            return dict(intent='NEW_QUERY' if text == 'SEED' else 'REFINE', action='EXECUTE',
                        state_delta=dict(set={'/'+k:v for k,v in fields.items()},unset=[]),clarification=None)
    if os.getenv('PRODUCT_DENIAL_FIXTURE') == '1':
        handler.authorization = Denial(handler.authorization.policy)
    handler.interpreter = Interpreter()
    uvicorn.run(app,host='127.0.0.1',port=int(os.environ['TEAM360_TELCHI_ASSISTANT_DEV_HTTP_PORT']),
                workers=1,access_log=False,log_level='warning')


def run(output):
    base = battery._load_env_file(); os.environ.update(base)
    phone = battery._pilot_phone('team360-meta-dev')
    binding = battery._binding_metadata('telchi_dev','telchi_whatsapp_dev','team360-meta-dev')
    token, port = secrets.token_urlsafe(48), battery._free_port()
    env = battery._server_env(token,phone,port,base,binding['receiver_context'])
    url = f'http://127.0.0.1:{port}'
    conversation = 'product-security-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    output.mkdir(parents=True,exist_ok=True)
    evidence = dict(fixture=True, endpoint='/api/telchi/assistant/dev/turn', cases={}, own_servers_reaped=[])
    def start(label, denied=False):
        child_env = dict(env,PRODUCT_DENIAL_FIXTURE='1' if denied else '0')
        with (output/(label+'.log')).open('w') as log:
            p = subprocess.Popen([sys.executable,'-m','modules.telchi.assistant.tests.runtime_http.product_security','--serve'],cwd=battery.BACKEND,env=child_env,stdout=log,stderr=subprocess.STDOUT)
        try: battery._wait_health(url,p)
        except BaseException:
            battery.stop_server(p); raise
        return p
    process = start('denied',True)
    try:
        r=battery._curl_turn(url,token,conversation+'-denied','SEED')
        assert r['response']['classification']=='DENIED' and r['response']['audit']['capability_calls']==0
        evidence['cases']['P13']=r
    finally:
        battery.stop_server(process); evidence['own_servers_reaped'].append(process.poll() is not None)
    process=start('security')
    try:
        seed=battery._curl_turn(url,token,conversation,'SEED')
        assert seed['response']['classification']=='DIRECT_AVAILABLE'
        for key,text in [('P14','REJECT'),('P15','INVENT')]:
            r=battery._curl_turn(url,token,conversation,text)
            a=r['response']['audit']
            assert a['committed'] is False and a['capability_calls']==0
            assert a['confirmed_state']==seed['response']['audit']['confirmed_state']
            evidence['cases'][key]=r
        evidence['seed']=seed
    finally:
        battery.stop_server(process); evidence['own_servers_reaped'].append(process.poll() is not None)
    process=start('restart')
    try:
        r=battery._curl_turn(url,token,conversation,'MAY')
        a=r['response']['audit']; prior=seed['response']['audit']['confirmed_state']
        assert r['response']['classification']=='DIRECT_AVAILABLE'
        assert a['previous_state']['product_context']==prior['product_context']
        assert a['confirmed_state']['selected_item_codes']==prior['selected_item_codes']
        assert a['confirmed_state']['period']==dict(start='2026-05-01',end_exclusive='2026-06-01')
        evidence['cases']['P18']=r
    finally:
        battery.stop_server(process); evidence['own_servers_reaped'].append(process.poll() is not None)
    (output/'security_restart_results.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n')
    print('P13 denial fixture, P14 real rejection, P15 invented ID, P18 PG context restart verified')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--serve',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    serve() if args.serve else run(args.output)
