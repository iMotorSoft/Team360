"""Explicit EMPTY disposable PostgreSQL only. Refuses known DEV/PROD clusters.

Fixtures are synthetic; passing this does not prove human authenticated sessions.
"""
import asyncio
import os
import json
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
import pytest

from modules.console.auth import ConsoleAuthError
from modules.console.login_admin_repository import ConsoleLoginAdminRepository, RUNTIME_ROLE
from modules.console.login_cli import checked_target
from modules.console.login_repository import ConsoleLoginRepository
from modules.console.login_service import ConsoleLoginService
from modules.security.paseto_tokens import PasetoKeyPair, PasetoConsoleSettings
from modules.business_semantics.service import BusinessConceptAdministration

PROTECTED = {'7630993354699489317','7559180602161319971'}


def test_disposable_password_sessions_privileges_and_business_admin(tmp_path):
    dsn = os.getenv('CONSOLE_AUTH_DISPOSABLE_TEST_DSN')
    if not dsn:
        pytest.skip('explicit disposable DSN required')

    async def run():
        async with await psycopg.AsyncConnection.connect(dsn,connect_timeout=5,row_factory=dict_row) as admin:
            repo=ConsoleLoginRepository()
            target=await repo.target(admin)
            assert target['system_identifier'] not in PROTECTED
            assert target['database']=='team360'
            # Never drop schemas, truncate or clean data on any existing destination.
            empty=await (await admin.execute("SELECT to_regclass('public.core_users') AS existing")).fetchone()
            assert empty['existing'] is None, 'only fresh disposable container accepted'
            await admin.execute('''
                CREATE TABLE core_organizations(id uuid PRIMARY KEY,status text,organization_code text);
                CREATE TABLE core_workspaces(id uuid PRIMARY KEY,organization_id uuid REFERENCES core_organizations(id),slug text,status text);
                CREATE TABLE core_users(id uuid PRIMARY KEY,workspace_id uuid REFERENCES core_workspaces(id),email text,status text);
                CREATE TABLE core_organization_members(id uuid PRIMARY KEY,organization_id uuid,user_id uuid,status text);
                CREATE TABLE core_organization_member_roles(organization_member_id uuid,role_code text,status text);
                CREATE TABLE core_events(id uuid DEFAULT gen_random_uuid(),workspace_id uuid,actor_user_id uuid,event_name text,entity_type text,payload_jsonb jsonb);
            ''')
            migrations=Path(__file__).resolve().parents[1]/'db/migrations'
            for name in ('028_team360_business_semantics_v1.sql','029_team360_business_semantics_relations_v1.sql'):
                await admin.execute((migrations/name).read_text())
            await ConsoleLoginAdminRepository().prepare(admin,role_password='disposable-runtime-password')
            org_a,org_b,w_a,w_b,admin_a,user_a,user_b=[str(uuid4()) for _ in range(7)]
            for org,code,ws,slug in ((org_a,'a',w_a,'telchi_fixture'),(org_b,'b',w_b,'other_fixture')):
                await admin.execute('INSERT INTO core_organizations VALUES(%s,%s,%s)',(org,'active',code))
                await admin.execute('INSERT INTO core_workspaces VALUES(%s,%s,%s,%s)',(ws,org,slug,'testing'))
            for uid,ws,email in ((admin_a,w_a,'admin@example.test'),(user_a,w_a,'reader@example.test'),(user_b,w_b,'other@example.test')):
                await admin.execute('INSERT INTO core_users VALUES(%s,%s,%s,%s)',(uid,ws,email,'active'))
            for org,uid in ((org_a,admin_a),(org_b,user_b)):
                membership=str(uuid4())
                await admin.execute('INSERT INTO core_organization_members VALUES(%s,%s,%s,%s)',(membership,org,uid,'active'))
                await admin.execute('INSERT INTO core_organization_member_roles VALUES(%s,%s,%s)',(membership,'organization_admin','active'))
            pair=PasetoKeyPair.generate('pg-fixture')
            cfg=PasetoConsoleSettings(enabled=True,issuer='fixture',key_id=pair.key_id,private_key_pem=pair.private_pem,public_key_pem=pair.public_pem,ttl_seconds=300)
            service=ConsoleLoginService(cfg)
            for uid,ws in ((admin_a,w_a),(user_a,w_a),(user_b,w_b)):
                await service.enroll(admin,user_id=uid,workspace_id=ws,password='synthetic fixture password')
            await admin.commit()
            p=conninfo_to_dict(dsn)
            runtime=make_conninfo(host=p['host'],port=p['port'],dbname='team360',user=RUNTIME_ROLE,password='disposable-runtime-password')
            async with await psycopg.AsyncConnection.connect(runtime,connect_timeout=5,row_factory=dict_row) as conn:
                await checked_target(conn,target,runtime=True)
                row=await repo.runtime_role(conn)
                assert not row['rolsuper'] and not row['rolbypassrls']
                # DDL and credential enrollment are unavailable to the runtime role.
                for query in ('CREATE TABLE forbidden(id integer)',"UPDATE console_password_credentials SET disabled=true"):
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        async with conn.transaction():await conn.execute(query)
                await conn.commit()
                tokens={}
                for uid,ws,slug,email in ((admin_a,w_a,'telchi_fixture','admin@example.test'),(user_a,w_a,'telchi_fixture','reader@example.test'),(user_b,w_b,'other_fixture','other@example.test')):
                    async with conn.transaction():
                        token=await service.login(conn,workspace_slug=slug,email=email,password='synthetic fixture password')
                        assert token
                        principal=await service.verify_session(conn,token,workspace_id=ws)
                        assert principal.user_id==uid
                        tokens[uid]=token
                with pytest.raises(ConsoleAuthError):
                    async with conn.transaction():await service.verify_session(conn,tokens[user_b],workspace_id=w_a)
                business=BusinessConceptAdministration()
                spec={'code':'fixture.concept','name':'Fixture concept','definition':'Synthetic definition','type':'fixture',
                      'context':{},'source':'test','reason':'isolated test','aliases':['fixture alias']}
                async with conn.transaction():
                    principal=await service.verify_session(conn,tokens[admin_a],workspace_id=w_a)
                    concept=await business.execute(conn,actor_id=principal.user_id,workspace_id=w_a,module='telchi',action='propose',payload=spec)
                    await business.execute(conn,actor_id=principal.user_id,workspace_id=w_a,module='telchi',action='publish',payload=concept)
                    assert len(await business.execute(conn,actor_id=principal.user_id,workspace_id=w_a,module='telchi',action='history',payload=concept))==1
                # Real CLI transport, same synthetic password-authenticated principal/role.
                from modules.console.login_cli import write_private
                tmp_path.chmod(0o700)
                config=write_private(tmp_path/'issuer.json',json.dumps(dict(version=1,environment='dev',target=target,
                    runtime_dsn=runtime,issuer=cfg.issuer,key_id=cfg.key_id,private_key_pem=cfg.private_key_pem,
                    public_key_pem=cfg.public_key_pem,ttl_seconds=cfg.ttl_seconds)))
                child=await asyncio.create_subprocess_exec(sys.executable,'-m','modules.business_semantics.cli','list',
                    '--workspace','telchi_fixture','--auth-config',str(config),
                    env={**os.environ,'TEAM360_ENV':'dev'},stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                try:
                    output,error=await asyncio.wait_for(child.communicate((tokens[admin_a]+'\n').encode()),15)
                finally:
                    if child.returncode is None:
                        child.terminate()
                        await child.wait()
                assert child.returncode==0, error.decode()
                assert json.loads(output)[0]['semantic_code']=='fixture.concept'
                for uid,ws in ((user_a,w_a),(user_b,w_b)):
                    with pytest.raises(PermissionError):
                        async with conn.transaction():await business.execute(conn,actor_id=uid,workspace_id=ws,module='telchi',action='history',payload=concept)
                # Failures persist across fresh transactions and across client connections.
                for _ in range(5):
                    async with conn.transaction():assert await service.login(conn,workspace_slug='telchi_fixture',email='reader@example.test',password='incorrect') is None
                async with conn.transaction():assert await service.login(conn,workspace_slug='telchi_fixture',email='reader@example.test',password='synthetic fixture password') is None
                async with await psycopg.AsyncConnection.connect(runtime,row_factory=dict_row) as fresh:
                    async with fresh.transaction():
                        assert await service.login(fresh,workspace_slug='telchi_fixture',email='reader@example.test',password='synthetic fixture password') is None
                await admin.execute("UPDATE core_users SET status='disabled' WHERE id=%s",(user_b,))
                await admin.commit()
                with pytest.raises(ConsoleAuthError):
                    async with conn.transaction():await service.verify_session(conn,tokens[user_b],workspace_id=w_b)
                await service.enroll(admin,user_id=admin_a,workspace_id=w_a,password='new synthetic fixture password')
                await admin.commit()
                with pytest.raises(ConsoleAuthError):
                    async with conn.transaction():await service.verify_session(conn,tokens[admin_a],workspace_id=w_a)
            # Actual audit does not contain hashes, passwords or signed tokens.
            events=await (await admin.execute('SELECT actor_user_id::text,event_name,payload_jsonb FROM core_events')).fetchall()
            assert any(e['actor_user_id']==admin_a and e['event_name']=='business_semantics.publish' for e in events)
            assert all(e['actor_user_id'] is None and e['payload_jsonb']['method']=='local_owner_enrollment'
                       for e in events if e['event_name']=='console.auth.enroll')
            assert all('password_hash' not in str(e['payload_jsonb']) and 'synthetic fixture password' not in str(e['payload_jsonb']) for e in events)
            # Re-prepare fails closed; never changes an existing role's password or grants.
            with pytest.raises(PermissionError):
                async with admin.transaction():await ConsoleLoginAdminRepository().prepare(admin,role_password='replacement')
    asyncio.run(run())
