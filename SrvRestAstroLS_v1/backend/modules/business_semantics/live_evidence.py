"""Explicit DEV probe: real embeddings, published seed retrieval and rollback-only mutation tests."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from time import perf_counter
import httpx
import psycopg
from psycopg.rows import dict_row
from .embeddings import EmbeddingConfiguration,LiteLLMEmbeddingAdapter
from .repository import BusinessConceptRepository,rows
from .resolver import BusinessConceptResolver,VectorCandidatePolicy
from .service import BusinessConceptAdministration
from .telchi_seed import seed,CONCEPTS
from modules.db.settings import get_database_settings
from modules.automation_diagnosis.litellm_client import LiteLLMClient


async def run(output):
    if os.getenv('TEAM360_ENV')!='dev':
        raise PermissionError('DEV_only')
    config=EmbeddingConfiguration.from_env()
    adapter=LiteLLMEmbeddingAdapter(config)
    admin=BusinessConceptAdministration(embeddings=adapter)
    repo=admin.repository
    report={'configuration':config.__dict__,'queries':[],'embedding_generation':[]}
    client=LiteLLMClient()
    async with httpx.AsyncClient(trust_env=False,timeout=10) as h:
        headers={'Authorization':'Bearer '+client.api_key}
        info=await h.get(client.base_url.removesuffix('/v1')+'/model/info',headers=headers)
        info.raise_for_status()
        models=[m for m in info.json()['data'] if m.get('model_name')==config.alias]
        if len(models)!=1:
            raise ValueError('embedding_alias_not_unique')
        report['provider_model']=models[0].get('litellm_params',{}).get('model')
        settings=await h.get(client.base_url.removesuffix('/v1')+'/router/settings',headers=headers)
        settings.raise_for_status()
        rs=settings.json()['current_values']
        report['fallback_configuration']={k:rs[k] for k in ('fallbacks','context_window_fallbacks','content_policy_fallbacks')}
        if any(report['fallback_configuration'].values()):
            raise ValueError('silent_fallback_not_allowed_for_probe')
    vector=await adapter.embed('Preflight: definición empresarial persistente.')
    report['preflight']={'dimension':len(vector),**adapter.last_usage}
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn,row_factory=dict_row,connect_timeout=5) as conn:
        target=(await rows(conn,"SELECT current_database() AS db,current_setting('server_version_num') AS version,(pg_control_system()).system_identifier::text AS system_identifier"))[0]
        if target['db']!='team360' or target['system_identifier']!=os.getenv('TEAM360_SEMANTICS_DEV_SYSTEM_IDENTIFIER'):
            raise PermissionError('approved_DEV_target_required')
        report['target']=target
        ext=await rows(conn,"SELECT extname,extversion FROM pg_extension WHERE extname='vector'")
        report['extension']=ext
        w=(await rows(conn,"SELECT id::text,organization_id::text FROM core_workspaces WHERE slug='telchi_dev'"))[0]
        # Explicitly approved local-owner seed, not a Console login or token issuance.
        actor=(await rows(conn,"SELECT id::text FROM core_users WHERE workspace_id=%s AND email='admin@telchiai.com'",(w['id'],)))[0]['id']
        pilot=(await rows(conn,"SELECT id::text FROM core_users WHERE workspace_id=%s AND email='devfull@telchiai.com'",(w['id'],)))[0]['id']
        report['idempotent_seed']=await seed(conn,admin,actor_id=actor,workspace_id=w['id'])
        for c in report['idempotent_seed']:
            start=perf_counter()
            result=await admin.execute(conn,actor_id=actor,workspace_id=w['id'],module='telchi',action='embed',
                                       payload={'concept_id':c['concept_id'],'version':c['version']})
            report['embedding_generation'].append({'concept_id':c['concept_id'],'elapsed_ms':(perf_counter()-start)*1000,
                                                   'changed':result['changed'],
                                                   **(adapter.last_usage if result['changed'] else {'usage':{},'upstream_model':None})})
        report['administrative_catalog']=await admin.execute(conn,actor_id=actor,workspace_id=w['id'],module='telchi',action='list',payload={})
        report['published_catalog_count']=len(await repo.catalog(conn,w['organization_id'],w['id'],'telchi'))
        await conn.commit()
        resolver=BusinessConceptResolver(embeddings=adapter,vector_policy=VectorCandidatePolicy.from_env())
        questions=['Dame ventas de farmacia','¿Cuánto le vendimos a menona?','¿Qué hay que importar?',
                   'Dame las deudas','Mostrame las ventas perdidas','¿Qué negocios presupuestamos y no se concretaron?',
                   'Dame ventas de Calenta','Concepto inexistente ZXQ903718',
                   'ventas de productos farmacéuticos','ventas a clientes farmacias','deudas a proveedores']
        for text in questions:
            start=perf_counter()
            result=await resolver.resolve(conn,organization_id=w['organization_id'],workspace_id=w['id'],module='telchi',
                                           actor_id=pilot,text=text)
            report['queries'].append({'text':text,'elapsed_ms':(perf_counter()-start)*1000,**result})
        second_user=await resolver.resolve(conn,organization_id=w['organization_id'],workspace_id=w['id'],module='telchi',actor_id=actor,text='Dame ventas de farmacia')
        report['second_authorized_user_retrieval']=second_user['status']=='resolved'
        report['cross_tenant_catalog_count']=len(await repo.catalog(conn,'00000000-0000-0000-0000-000000000001',w['id'],'telchi'))
        try:
            await resolver.resolve(conn,organization_id='00000000-0000-0000-0000-000000000001',workspace_id=w['id'],module='telchi',actor_id=pilot,text='Dame ventas de farmacia')
        except PermissionError:
            report['scope_mismatch_denied']=True
        try:
            await admin.execute(conn,actor_id=pilot,workspace_id=w['id'],module='telchi',action='list',payload={})
        except PermissionError:
            report['non_admin_write_denied']=True
        class Offline:
            config=adapter.config
            async def embed(self,text):
                raise TimeoutError('simulated_outage')
        offline=BusinessConceptResolver(embeddings=Offline())
        report['offline_exact']=await offline.resolve(conn,organization_id=w['organization_id'],workspace_id=w['id'],module='telchi',actor_id=pilot,text='Dame las deudas')
        report['offline_text_miss']=await offline.resolve(conn,organization_id=w['organization_id'],workspace_id=w['id'],module='telchi',actor_id=pilot,text='sucursales clasificadas como farmacias')
        report['offline_text']=await offline.resolve(conn,organization_id=w['organization_id'],workspace_id=w['id'],module='telchi',actor_id=pilot,text='ventas sucursales farmacias')
        class BrokenVectorSQL(BusinessConceptRepository):
            async def vector_search(self, conn, *args):
                await conn.execute('SELECT 1/0')  # Controlled SQL fault, rolled back to savepoint.
        class PreflightVector:
            config=adapter.config
            async def embed(self, text):
                return vector  # Fault-path probe only; never returns a fabricated similarity.
        broken=BusinessConceptResolver(BrokenVectorSQL(),PreflightVector())
        report['simulated_vector_SQL_failure']=await broken.resolve(conn,organization_id=w['organization_id'],
            workspace_id=w['id'],module='telchi',actor_id=pilot,text='ventas sucursales farmacias')
        report['turn_transaction_survives_vector_SQL_failure']=(await rows(conn,'SELECT 1 AS alive'))[0]['alive']==1
        await conn.rollback()
        # Real SQL/version/embedding paths; no permanent extra definition or publication.
        async with conn.transaction(force_rollback=True):
            item=dict(CONCEPTS[0],code='telchi.test.business_semantics_versioning')
            v1=await admin.execute(conn,actor_id=actor,workspace_id=w['id'],module='telchi',action='propose',payload=item)
            await admin.execute(conn,actor_id=actor,workspace_id=w['id'],module='telchi',action='publish',payload=v1)
            await admin.execute(conn,actor_id=actor,workspace_id=w['id'],module='telchi',action='embed',payload=v1)
            item=dict(item,definition=item['definition']+' Versión de prueba auditada.',reason='Rollback-only versioning probe')
            v2=await admin.execute(conn,actor_id=actor,workspace_id=w['id'],module='telchi',action='propose',payload=item)
            await admin.execute(conn,actor_id=actor,workspace_id=w['id'],module='telchi',action='publish',payload=v2)
            await admin.execute(conn,actor_id=actor,workspace_id=w['id'],module='telchi',action='embed',payload=v2)
            history=await repo.history(conn,v1['concept_id'])
            report['versioning']={'versions':[v['version'] for v in history],
                                 'previous_version':history[1]['previous_version'],
                                 'definitions_distinct':history[0]['definition']!=history[1]['definition'],
                                 'embedding_count':(await rows(conn,'SELECT count(*) AS n FROM business_concept_embeddings WHERE concept_id=%s',(v1['concept_id'],)))[0]['n'],
                                 'rollback_only':True}
            try:
                async with conn.transaction():
                    await conn.execute("UPDATE business_concept_versions SET definition='forbidden' WHERE concept_id=%s AND version=1",(v1['concept_id'],))
            except psycopg.Error:
                report['published_definition_mutation_denied']=True
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,default=str,indent=2))
    print('Evidence written:',output)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    asyncio.run(run(p.parse_args().output))


if __name__=='__main__':
    main()
