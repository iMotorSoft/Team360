"""Real Luna/Console/PostgreSQL/Foundation HTTP probe, no listener or outbound."""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb
from . import live_product_monetary_ranking as base


async def run(output):
    config = base.lifecycle.load_config(base.dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    approval_path = Path(config.get('approval', base.dev.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
    approval = base.dev.read_approval(approval_path)
    srv, settings = base.dev.configuration()
    binding = await base.dev.check_database(approval, settings, srv.evolution)
    source = base.dev.source_digest()
    report = dict(status='IN_PROGRESS',source_sha256=source,turns=[],whatsapp_sent=0,
        listeners=0,runtime_started_or_stopped=0,security_writes=0)
    def check():
        base.dev.unchanged_approval(approval_path, approval)
    policy = base.BusinessPolicy(approval['tenant_id'],approval['workspace_id'],None,
        approval['module_enabled'],approval['whole_workspace_scope_verified'],pilot_access_check=check,
        pilot_user_id=approval['user_id'],pilot_approval_sha256=base.dev.approval_digest(approval))
    pool = base.create_pool(replace(base.get_database_settings(),min_size=1,max_size=2))
    await base.open_pool(pool)
    try:
        app = base.create_telchi_app(policy=policy,pool=pool)
        base.set_pool(pool)
        app.register(base.DevAssistantController)
        token = secrets.token_urlsafe(48)
        app.state.dev_assistant_config = dict(token=token,phone=settings.authorized_sender,binding=binding,
            instance=binding.provider_instance,receiver_context=binding.receiver_context)
        handler = app.state.messaging_handlers['telchi'].handler
        fixture = json.loads(base.FIXTURE.read_text())
        async with pool.connection() as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            original = await (await conn.execute('SELECT metadata_jsonb FROM message_threads WHERE id=%s',
                (fixture['source_thread_id'],))).fetchone()
            security = await base.RankingRegistrationRepository().security_state(conn)
        model = base.LunaInterpreter()
        preflight = await model.interpret(text='¿Cuánto facturamos?',state=deepcopy(base.EMPTY),history={},turn_id='historical-preflight')
        assert preflight['action']=='ASK' and model.last_metadata['reasoning_echo_verified']
        report['model_preflight']=model.last_metadata
        conversation = 'historical-ranking-'+uuid4().hex
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
            async def turn(question):
                handler.interpreter=base.LunaInterpreter()
                handler.store=base.PostgresConversationStore(pool)
                response=await client.post(base.DEV_PATH+'/turn',json=dict(text=question,conversation=conversation),
                    headers={'x-team360-dev-token':token})
                assert response.status_code==200
                value=response.json()
                value.update(question=question,model=handler.interpreter.last_metadata)
                report['turns'].append(value)
                assert value['classification']=='DIRECT_AVAILABLE', dict(question=question,classification=value['classification'],text=value['text'],audit=value['audit'])
                return value
            seed=await turn('¿Cuánto vendimos de productos terminados en septiembre de 2026?')
            assert seed['conversation_id']!=fixture['source_thread_id']
            async with pool.connection() as conn:
                await conn.execute("UPDATE message_threads SET metadata_jsonb=jsonb_set(metadata_jsonb,'{telchi_assistant_v1,state}',%s) WHERE id=%s",
                    (Jsonb(fixture['previous_state']),seed['conversation_id']))
            a=await turn('¿Cuánto vendimos de productos terminados en septiembre?')
            assert a['audit']['previous_state']==fixture['previous_state']
            b=await turn('Dame los 5 más vendidos por precio de venta de los productos terminados')
            base.verify_ranking(b,'LAB_FINISHED_PRODUCT',5)
            c=await turn('decime el producto L03281')
            assert c['audit']['confirmed_state']['ranking_target_item_code']=='L03281'
            d=await turn('decime el producto L03281 en el mes julio y agosto en que puesto estuvo')
            result=d['audit']['execution_result']
            assert result['view']=='historical_position' and result['category']=='LAB_FINISHED_PRODUCT'
            assert len(result['periods'])==2
            for row, expected in zip(result['periods'], [('2026-07-01',2,283,'271255.49'),('2026-08-01',1,289,'314971.57')]):
                start,position,count,amount=expected
                assert row['period']['start']==start and row['status']=='verified'
                assert row['target']['position']==position and row['comparable_products']==count
                assert Decimal(row['target']['amount'])==Decimal(amount)
                assert Decimal(row['result']['reconciliation']['difference'])==0
            assert result['periods'][1]['result']['external_currency_anomalies'][0]['item_code']=='L01412'
            e=await turn('¿Qué diferencia hubo entre esos dos meses para ese producto?')
            assert '43.716,08' in e['text']
            f=await turn('Explicame si hubo documentos o anomalías que afecten esas posiciones')
            assert f['audit']['confirmed_state']['ranking_detail']=='exceptions'
            assert 'L01412' in f['text'] and 'fuera de la categoría' in f['text']
            assert 'No se excluyeron operaciones' in f['text']
            report['anomaly_followup']=dict(text=f['text'],decision=f['audit']['decision'])
        async with pool.connection() as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            assert original==await (await conn.execute('SELECT metadata_jsonb FROM message_threads WHERE id=%s',
                (fixture['source_thread_id'],))).fetchone()
            assert security==await base.RankingRegistrationRepository().security_state(conn)
        for t in report['turns']:
            m=t['model']
            assert m['model']=='gpt-5.6-luna' and m['reasoning']=='medium' and m['reasoning_echo_verified']
            assert m['provider']=='OpenAI direct'
        assert base.dev.source_digest()==source,'Concurrent source change'
        report.update(status='PASS',original_preserved=True,security_preserved=True,reload_every_turn=True)
    except BaseException as exc:
        report['failure']=dict(type=type(exc).__name__,reason=str(exc))
        raise
    finally:
        await base.close_pool(pool)
        report['pool_closed']=True
        with os.fdopen(os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
            json.dump(report,stream,ensure_ascii=False,indent=2,default=str)
    return dict(status=report['status'],turns=len(report['turns']),pool_closed=True,whatsapp_sent=0)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or not args.output.parent.resolve().is_relative_to(base.dev.PRIVATE_ROOT.resolve()):
        raise SystemExit('new private evidence output required')
    print(json.dumps(asyncio.run(run(args.output))))
