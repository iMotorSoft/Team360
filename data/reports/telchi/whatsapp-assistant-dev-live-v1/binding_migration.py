"""Authorized DEV-only administrative 027 application with backup and rollback rehearsal."""
import asyncio, hashlib, json, os, subprocess
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
ROOT=Path(__file__).resolve().parent
EXPECTED='9ff78e59b5276e0158a774aaef70162770bc907fbe71cf81159a73ec036f1694'
async def main():
    for k,v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None: os.environ[k]=v
    from modules.db.settings import get_database_settings
    from modules.messaging.identity import PhoneIdentityRepository
    dsn=get_database_settings().dsn;p=urlparse(dsn)
    assert p.hostname in ('localhost','127.0.0.1') and p.port==5432 and p.path=='/team360'
    source=Path('db/migrations/027_team360_messaging_phone_bindings.sql').read_bytes()
    assert hashlib.sha256(source).hexdigest()==EXPECTED
    text=source.decode(); assert text.count('BEGIN;')==2 and text.count('COMMIT;')==2
    # Remove only active wrapper; rollback comment remains inert. Caller owns atomic transaction.
    body=text.replace('\nBEGIN;\n','\n',1).replace('\nCOMMIT;\n','\n',1)
    result={'timestamp':datetime.now(timezone.utc).isoformat(),'checksum':EXPECTED,'target':'localhost:5432/team360'}
    async with await psycopg.AsyncConnection.connect(dsn,autocommit=True,row_factory=dict_row,application_name='telchi-dev-migration-027') as c:
        assert (await (await c.execute('SHOW server_version_num')).fetchone())['server_version_num'].startswith('18')
        existing=await (await c.execute("SELECT to_regclass('messaging_phone_bindings') AS t,to_regprocedure('messaging_phone_binding_audit()') AS f")).fetchone()
        assert existing=={'t':None,'f':None},'existing objects require separate review'
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/backups')/('binding-027-'+stamp)
        backup.mkdir(mode=0o700)
        path=backup/'team360.dump'
        with path.open('xb') as f:
            os.chmod(path,0o600)
            subprocess.run(['docker','exec','imotorsoft-postgres','pg_dump','-U','administrator','-d','team360','-Fc'],stdout=f,stderr=subprocess.DEVNULL,check=True,timeout=90)
        with path.open('rb') as f, (backup/'team360.toc').open('x') as toc:
            os.chmod(backup/'team360.toc',0o600)
            subprocess.run(['docker','exec','-i','imotorsoft-postgres','pg_restore','--list'],stdin=f,stdout=toc,stderr=subprocess.DEVNULL,check=True,timeout=30)
        with path.open('rb') as f:
            subprocess.run(['docker','exec','-i','imotorsoft-postgres','pg_restore','--file=/dev/null'],stdin=f,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=30)
        result['backup']={'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'toc_sql_extraction':'PASS','restore_rehearsal':'NOT_EXECUTED'}
        async def validate():
            await PhoneIdentityRepository().validate_schema(c)
            constraints=await (await c.execute("SELECT conname,contype,convalidated,pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conrelid='messaging_phone_bindings'::regclass ORDER BY conname")).fetchall()
            assert sum(x['contype']=='f' for x in constraints)==4
            assert sum(x['contype']=='u' for x in constraints)==1 and all(x['convalidated'] for x in constraints)
            triggers=await (await c.execute("SELECT tgname,tgenabled,pg_get_triggerdef(oid) AS definition FROM pg_trigger WHERE tgrelid='messaging_phone_bindings'::regclass AND NOT tgisinternal")).fetchall()
            assert len(triggers)==1 and triggers[0]['tgenabled']=='O'
            indexes=await (await c.execute("SELECT indexname,indexdef FROM pg_indexes WHERE tablename='messaging_phone_bindings'")).fetchall()
            return {'constraints':constraints,'triggers':triggers,'indexes':indexes}
        async with c.transaction(force_rollback=True):
            await c.execute("SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='10s'")
            await c.execute(body)
            result['rehearsal']=await validate()
        assert (await (await c.execute("SELECT to_regclass('messaging_phone_bindings') AS t")).fetchone())['t'] is None
        result['transactional_rollback']='PASS'
        async with c.transaction():
            await c.execute("SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='10s'")
            await c.execute(body)
            result['applied_schema']=await validate()
            await c.execute("INSERT INTO core_events(event_name,entity_type,payload_jsonb) VALUES ('telchi.dev.migration_027.applied','migration',%s)",(Jsonb({'sha256':EXPECTED,'authorization':'TELCHI WHATSAPP DEV BINDING & LIVE V1','backup_sha256':result['backup']['sha256']}),))
        await PhoneIdentityRepository().validate_schema(c)
        result['applied']='PASS';result['completed_at']=datetime.now(timezone.utc).isoformat()
    (ROOT/'binding-migration.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rehearsal','applied_schema')},indent=2))
if __name__=='__main__': asyncio.run(main())
