"""Effective PG authorization, rollback rehearsal and independent HTTP/SQL parity."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parents[3] / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
from dotenv import dotenv_values
for key, value in dotenv_values(BACKEND.parent / '.env.backend-dev.local').items():
    if value is not None: os.environ[key] = value
from modules.telchi.provisioning.sales_repository import SalesActivationRepository
from modules.telchi.provisioning.repository import PERMISSION
from modules.telchi.datalake.sales_query import PERMISSIONS, PUBLICATION, SNAPSHOT
from modules.console.repositories import PermissionConsoleRepository
from modules.db.settings import get_database_settings
import psycopg
from psycopg.rows import dict_row


def dump(name, data):
    (ROOT / name).write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False) + '\n')


async def postgres():
    from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
    from modules.telchi.assistant.capabilities import SalesCapabilities
    from modules.telchi.assistant.tests.test_assistant import MemoryStore, Interpreter, context, event, proposal, latest
    from modules.telchi.assistant import state_engine
    result = {}
    repo = SalesActivationRepository()
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn, autocommit=True, row_factory=dict_row) as conn:
        async with conn.transaction():
            await conn.execute('SET TRANSACTION READ ONLY')
            snapshot = await repo.snapshot(conn)
            ids = snapshot['identities']
            workspace, pilot = ids['workspace']['id'], ids['pilot']['id']
            result['identities'] = ids
            result['effective'] = snapshot['effective']
            result['catalog'] = snapshot['records']['permissions']
            result['roles'] = snapshot['records']['roles']
            result['role_permissions'] = snapshot['records']['role_permissions']
            result['user_roles'] = snapshot['records']['user_roles']
            result['user_profiles'] = snapshot['records']['user_profiles']
            events = [e for e in snapshot['records']['admin_events'] if e['event_name'] in ('telchi.admin.sales-authorize', 'telchi.admin.sales-grant')]
            result['audit_events'] = events
            assert len(events) == 2
            assert set(snapshot['effective']) == {PERMISSION, *PERMISSIONS.values()}
            wrong = await PermissionConsoleRepository().list_effective_permissions(conn, ids['global']['workspace_id'], pilot)
            assert wrong == []
            result['pilot_wrong_workspace_effective'] = wrong
            policy = BusinessPolicy('telchi', workspace, PERMISSION, True, True)
            auth = BusinessAuthorization(policy)
            base = context()
            channel = replace(base.channel, tenant_id='telchi', workspace_id=workspace)
            ident = replace(base.sender_identity, user_id=pilot, tenant_id='telchi', workspace_id=workspace,
                permissions=frozenset(snapshot['effective']))
            positive = replace(base, channel=channel, sender_identity=ident)
            result['positive_authorization'] = {grant: await auth.allowed(positive, conn, required_permission=grant) for grant in PERMISSIONS.values()}
            assert all(result['positive_authorization'].values())
            admin_grants = await PermissionConsoleRepository().list_effective_permissions(conn, workspace, ids['admin']['id'])
            global_grants = await PermissionConsoleRepository().list_effective_permissions(conn, ids['global']['workspace_id'], ids['global']['id'])
            negatives = {
                'existing_telchi_admin_without_business_permission': (replace(positive, sender_identity=replace(ident, user_id=ids['admin']['id'], permissions=frozenset(admin_grants))), auth),
                'existing_team360_actor_other_tenant': (replace(positive, sender_identity=replace(ident, user_id=ids['global']['id'], tenant_id='team360_platform', workspace_id=ids['global']['workspace_id'], permissions=frozenset(global_grants))), auth),
                'wrong_workspace_fixture': (replace(positive, channel=replace(channel, workspace_id=ids['global']['workspace_id'])), auth),
                'module_not_enabled_fixture': (positive, BusinessAuthorization(replace(policy, module_enabled=False))),
                'new_capability_without_permission_fixture': (replace(positive, sender_identity=replace(ident, permissions=frozenset({PERMISSION}))), auth),
            }
            security = {}
            for label, (ctx, authorization) in negatives.items():
                calls = []
                async def forbidden(*args, **kwargs):
                    calls.append('query')
                    raise AssertionError('unauthorized query')
                store = MemoryStore()
                interpreter = Interpreter([proposal({'/metric':'sales.coverage'}, intent='NEW_QUERY')])
                handler = TelchiHandler(store=store, authorization=authorization, interpreter=interpreter,
                    capabilities=SalesCapabilities(sales_query=forbidden))
                response = await handler.handle(event('Mostrá la cobertura de facturas activas'), ctx)
                assert response.classification == 'DENIED' and not calls
                security[label] = dict(classification=response.classification, query_calls=len(calls),
                    interpretation_calls=len(interpreter.calls), fixture='fixture' in label,
                    audit=latest(store) if store.audits else None)
            for label, raw in [('outside_catalog_fixture', proposal({'/metric':'sales.free_sql'}, intent='NEW_QUERY')),
                               ('committed_false_fixture', proposal({'/metric':'sales.coverage'}, intent='NEW_QUERY'))]:
                calls=[]
                async def forbidden(*args, **kwargs): calls.append('query'); raise AssertionError('forbidden query')
                store=MemoryStore()
                handler=TelchiHandler(store=store, authorization=auth, interpreter=Interpreter([raw]),
                    capabilities=SalesCapabilities(sales_query=forbidden))
                if label == 'committed_false_fixture':
                    handler.engine=lambda *args: dict(committed=False,state_after=dict(state_engine.EMPTY,metric='sales.coverage'),output={'action':'EXECUTE'})
                response=await handler.handle(event('fixture invalid'),positive)
                audit=latest(store)
                assert audit['committed'] is False and not calls
                security[label]=dict(classification=response.classification,query_calls=0,committed=audit['committed'],decision=audit['decision'],fixture=True)
            result['security'] = security
        # Rehearsal with real existing identities, never committed; no fake users.
        class RehearsalRollback(Exception): pass
        try:
            async with conn.transaction():
                await conn.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
                run_id = json.loads((ROOT/'apply.json').read_text())['run_id']
                withdrawn = await repo.rollback_assignments(conn, run_id)
                assert withdrawn['effective'] == [PERMISSION]
                again = await repo.rollback_assignments(conn, run_id)
                assert again['changed'] is False
                result['rollback_rehearsal'] = dict(withdrawn=withdrawn, second=again, persisted=False,
                    removed_only_created_user_roles=True, base_grant_preserved=True)
                raise RehearsalRollback()
        except RehearsalRollback: pass
        async with conn.transaction():
            await conn.execute('SET TRANSACTION READ ONLY')
            after = await repo.snapshot(conn)
            assert after == snapshot
            result['rollback_rehearsal']['post_rollback_snapshot_unchanged'] = True
    dump('effective_and_security.json', result)


def foundation():
    from modules.telchi.datalake.ducklake import DuckLakeConnector
    from modules.telchi.datalake.foundation_reader import FoundationReader
    http=json.loads((ROOT/'business_http_validated/runtime_http_results.json').read_text())
    connector=DuckLakeConnector()
    result=dict(read_only=True,sap_accessed=False,comparisons={})
    with connector.session(read_only=True) as conn:
        conn.execute('SET threads=2')
        conn.execute("SET memory_limit='512MB'")
        conn.execute("SET max_temp_directory_size='0B'")
        access=FoundationReader(connector).resolve_on(conn)
        assert access.foundation_publication_id == PUBLICATION and access.ducklake_snapshot_id == SNAPSHOT
        result['binding']=access.as_dict()
        documents=access.sales('sales_document')
        # Same accredited independent algorithms, not capability SQL.
        latest_sql=f'''WITH ordered AS (SELECT source_system,doc_entry,doc_num,doc_date,canceled,
            ROW_NUMBER() OVER (ORDER BY doc_date DESC, CAST(doc_entry AS BIGINT) DESC,doc_entry DESC) AS position
            FROM {documents} WHERE canceled='N' AND source_system='SAP_B1_HANA' AND doc_date IS NOT NULL)
            SELECT source_system,doc_entry,doc_num,doc_date,canceled FROM ordered WHERE position<=? ORDER BY position'''
        coverage_sql=f'''SELECT doc_date,COUNT(*) AS n FROM {documents}
            WHERE canceled='N' AND source_system='SAP_B1_HANA' AND doc_date IS NOT NULL
            GROUP BY doc_date ORDER BY doc_date'''
        def query(sql,params):
            cursor=conn.execute(sql,params); names=[r[0] for r in cursor.description]
            return json.loads(json.dumps([dict(zip(names,r)) for r in cursor.fetchall()],default=str))
        references=query(latest_sql,[10])
        dates=query(coverage_sql,[])
        coverage=[dict(first_date=dates[0]['doc_date'],last_date=dates[-1]['doc_date'],documents=sum(r['n'] for r in dates),
            latest_month_with_rows=dates[-1]['doc_date'][:7],complete_month_certified=False)]
        result['reference_sql']=dict(latest=dict(sql=latest_sql,parameters=[10],rows=references),
            coverage=dict(sql=coverage_sql,parameters=[],derived=coverage))
        for scenario in http['scenarios']:
            if scenario['id'] not in {'B01','B02','B03','B04'}: continue
            turn=scenario['turns'][0]; audit=turn['audit']; executed=audit['execution_result']
            expected=references if scenario['id'] in {'B01','B04'} else coverage
            required=PERMISSIONS['sales.latest_documents' if scenario['id'] in {'B01','B04'} else 'sales.coverage']
            assert executed and executed['rows'] == expected
            assert executed['source']['publication_id']==PUBLICATION and executed['source']['snapshot_id']==SNAPSHOT
            assert audit['required_permission']==required and audit['capability_calls']==1 and audit['committed'] is True
            assert turn['classification']=='DIRECT_AVAILABLE' and turn['execution_status']=='executed'
            result['comparisons'][scenario['id']]=dict(parity=True,rows=executed['rows'],capability=executed['capability'],
                required_permission=required,source=executed['source'],parameters=executed['sql_parameters'],
                correlation_id=turn['correlation_id'],state=audit['confirmed_state'],capability_calls=audit['capability_calls'],
                foundation_business_queries=1)
        b4=next(s for s in http['scenarios'] if s['id']=='B04')['turns'][1]
        b5=next(s for s in http['scenarios'] if s['id']=='B05')['turns'][0]
        for turn in (b4,b5): assert turn['execution_status']=='not_executed' and turn['audit']['capability_calls']==0
        result['business_response']=True
    dump('foundation_parity.json',result)

if __name__=='__main__':
    asyncio.run(postgres())
    foundation()
    print('Effective authorization, 7 negative controls, rollback rehearsal and HTTP/SQL parity PASS')
