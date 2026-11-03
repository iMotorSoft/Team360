"""DEV-only bilateral provisioning, explicitly authorized by sole owner Mario.

All keys/credentials/DSNs stay in owner-controlled PRIVATE_ROOT. No Meta call.
No public callback, business grants, messages or historical event mutation.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).parent))
from inspect_consumers import ROOT, PRIVATE, OUT, CHANNELS
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
from modules.db.settings import get_database_settings
from modules.messaging.administration.bindings import BindingAdministration
from modules.messaging.administration.repository import Repository
from modules.messaging.administration.contract import canonical, confirmation, signature
from modules.messaging.transport_profile import credential_verifier

P = PRIVATE/'evolution-dev-v1'
SCHEMA = {'team360':'public','evolution':'evolution_api'}

def save(name,value):
    data=canonical(value)
    fd=os.open(P/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    assert not (P/'trust.json').exists(), 'Never replace an existing trust root implicitly'
    assert P.stat().st_mode & 0o777 == 0o700
    base=conninfo_to_dict(get_database_settings().dsn)
    dsns={s:make_conninfo(**{**base,'dbname':d}) for s,d in [('team360','team360'),('evolution','evolution_api')]}
    connections={s:psycopg.connect(dsn,row_factory=dict_row,connect_timeout=3,
        options='-c statement_timeout=5000 -c lock_timeout=3000') for s,dsn in dsns.items()}
    try:
        t,e=connections['team360'],connections['evolution']
        for side,conn in connections.items():
            conn.execute(sql.SQL('SET search_path TO {},public').format(sql.Identifier(SCHEMA[side])))
            for table in ('ot_target','ot_inventory','ot_revision','ot_operation'):
                assert conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(sql.Identifier(table))).fetchone()['n']==0
        BindingAdministration().require_exclusive(t,'team360-meta-dev',CHANNELS[1])
        channel=t.execute('''SELECT c.id::text,c.workspace_id::text,c.provider_id::text,w.organization_id::text,
            c.metadata_jsonb AS metadata FROM communication_channels c JOIN core_workspaces w ON w.id=c.workspace_id
            WHERE c.id=%s''',(CHANNELS[1],)).fetchone()
        instance=e.execute('''SELECT id,name,integration,number,"businessId" FROM "Instance" WHERE id=%s''',
            ('0234646c-458c-4808-a6ea-a0d264cc999b',)).fetchone()
        assert instance['name']=='team360-meta-dev' and instance['integration']=='WHATSAPP-BUSINESS'
        assert instance['number']==os.environ['META_TEAM360_PHONE_NUMBER_ID']
        assert instance['businessId']==os.environ['META_TEAM360_WABA_ID']
        assert e.execute('SELECT count(*) AS n FROM "Instance" WHERE number=%s',(instance['number'],)).fetchone()['n']==1
        m=channel['metadata']
        assert m['environment']=='dev' and m['module']=='telchi' and m['tenant_id']=='telchi'
        scope=dict(binding_id=str(uuid4()),environment='dev',workspace_id=channel['workspace_id'],channel_id=channel['id'],
            provider_id=channel['provider_id'],instance_id=instance['id'],instance_name=instance['name'],
            organization_id=channel['organization_id'],tenant_id=m['tenant_id'],module=m['module'],receiver_context=m['receiver_context'])
        keys={s:Ed25519PrivateKey.generate() for s in ('mario','team360','evolution')}
        b64=lambda v:base64.b64encode(v).decode()
        targets={s:dict(id=str(uuid4()),epoch=str(uuid4()),public_key=b64(keys[s].public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)))
            for s in ('team360','evolution')}
        now=int(time.time())
        trust=dict(version=1,laboratory_only=False,profile='dev',administration_mode='single_owner_dev',owner_id='mario',targets=targets,
            actors={'mario':dict(enabled=True,public_key=b64(keys['mario'].public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)),
                identity_ref='owner-Mario-explicit-DEV-V1-authorization-20261023',key_custody='owner',not_before=now-60,not_after=now+365*86400,
                grants=[dict(capability='administer',action=a,scope=scope) for a in ('prepare','activate','revoke')])})
        secret='t360devv1_'+secrets.token_urlsafe(32)
        verifier=credential_verifier(secret,'dev')
        # Owner custody: local 0700 owner directory, 0600 exclusive files, never exported into Git/logs.
        for name,key in keys.items(): save(name+'-key.json',{'key':b64(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))})
        pin=save('trust.json',trust)
        save('credential.json',{'credential':secret,'credential_hash':verifier})
        save('scope.json',scope)
        for side,conn in connections.items():
            for s,target in targets.items():
                conn.execute('INSERT INTO ot_target(side,target_id,epoch) VALUES (%s,%s,%s)',(s,target['id'],target['epoch']))
                conn.execute('INSERT INTO ot_inventory(side,binding_id,scope) VALUES (%s,%s,%s)',(s,scope['binding_id'],Jsonb(scope)))
            role='t360devv1_provisioner' if side=='team360' else 'evodevv1_provisioner'
            assert not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
            conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS').format(sql.Identifier(role)))
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(SCHEMA[side]),sql.Identifier(role)))
            for priv,tables in [('SELECT',['ot_target']),('SELECT,UPDATE',['ot_inventory']),('SELECT,INSERT,UPDATE',['ot_revision']),('SELECT,INSERT',['ot_operation'])]:
                conn.execute(sql.SQL('GRANT {} ON {} TO {}').format(sql.SQL(priv),sql.SQL(',').join(map(sql.Identifier,tables)),sql.Identifier(role)))
            conn.commit()
        # Exact same signed operations and activation ID on both databases.
        def envelope(action,receipts=None):
            n=int(time.time())
            m=dict(version=1,administration_mode='single_owner_dev',owner='mario',operation_id=str(uuid4()),nonce=str(uuid4()),
                issued_at=n-1,expires_at=n+600,action=action,scope=scope,revision=1,credential_hash=verifier,
                targets={s:{k:v[k] for k in ('id','epoch')} for s,v in targets.items()},preparations=receipts or {})
            m['confirmation']=confirmation(m)
            return dict(manifest=m,owner_signature=signature(keys['mario'],'team360.offline.single_owner_dev.v1',m))
        receipts={}
        prepare=envelope('prepare');save('prepare.json',prepare)
        for side,conn in connections.items():
            role='t360devv1_provisioner' if side=='team360' else 'evodevv1_provisioner'
            conn.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
            receipts[side]=Repository().apply(conn,prepare,trust,side,keys[side],environment='dev')['receipt']
            conn.commit()
        activation=envelope('activate',receipts);save('activate.json',activation)
        for side,conn in connections.items():
            role='t360devv1_provisioner' if side=='team360' else 'evodevv1_provisioner'
            conn.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
            receipt=Repository().apply(conn,activation,trust,side,keys[side],environment='dev')
            conn.commit();save(side+'-activation-receipt.json',receipt)
        save('team360.json',dict(version=1,scope=scope,revision=1,trust=trust,
            signer=b64(keys['team360'].private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())),
            socket=str(P/'callback.sock'),admission_open=False))
        save('evolution.json',dict(laboratory_only=False,trust=trust,signing_key=b64(keys['evolution'].private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())),
            app={'id':os.environ['META_TEAM360_APP_ID'],'secret':os.environ['META_TEAM360_APP_SECRET']},callback_socket=str(P/'callback.sock'),admission_open=False))
        e.execute('INSERT INTO ot_meta_instance(instance_id,app_id,phone_number_id,waba_id) VALUES (%s,%s,%s,%s)',
            (instance['id'],os.environ['META_TEAM360_APP_ID'],instance['number'],instance['businessId']));e.commit()
        result=dict(single_owner='mario',administration_mode='single_owner_dev',trust_sha256=pin,
            binding_id=scope['binding_id'],revision=1,admission_open=False,private_custody='owner-local-0700/0600',
            bilateral={s:conn.execute('SELECT side,revision,state,activation_id::text FROM ot_revision WHERE side=%s',(s,)).fetchone()
                for s,conn in connections.items()},real_messages_sent=0,meta_calls=0)
        assert result['bilateral']['team360']['activation_id']==result['bilateral']['evolution']['activation_id']
        (OUT/'provisioning.json').write_text(json.dumps(result,indent=2)+'\n')
        print('SINGLE_OWNER_DEV=PASS V1_CREDENTIALS=PASS BILATERAL_REVISION=ACTIVE ADMISSION=CLOSED')
    finally:
        for conn in connections.values(): conn.close()

if __name__=='__main__': main()
