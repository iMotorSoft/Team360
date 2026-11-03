"""Dedicated unprivileged DEV runtime logins; no memberships or administration rights."""
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import quote, urlencode
sys.path.insert(0,str(Path(__file__).parent))
from provision import save, P, SCHEMA
from inspect_consumers import OUT
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from modules.db.settings import get_database_settings


def main():
    os.umask(0o077)
    assert not (P/'runtime-dsns.json').exists()
    base=conninfo_to_dict(get_database_settings().dsn)
    dsns={};proof={}
    for side,db,role in [('team360','team360','t360devv1_runtime'),('evolution','evolution_api','evodevv1_runtime')]:
        password=secrets.token_urlsafe(40)
        with psycopg.connect(make_conninfo(**{**base,'dbname':db}),row_factory=dict_row) as conn:
            schema=SCHEMA[side]
            conn.execute(sql.SQL('SET search_path TO {},public').format(sql.Identifier(schema)))
            existing = conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
            if '--recover-own-logins' in sys.argv:
                # ONLY the two unused logins created by the immediately preceding
                # run, which failed CONNECT before saving any runtime credentials.
                assert existing
                conn.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
            else:
                assert not existing
                conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8').format(sql.Identifier(role),sql.Literal(password)))
            conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(db),sql.Identifier(role)))
            conn.execute(sql.SQL('ALTER ROLE {} IN DATABASE {} SET search_path TO {},public').format(sql.Identifier(role),sql.Identifier(db),sql.Identifier(schema)))
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema),sql.Identifier(role)))
            # One existing DB/instance, read-only legacy catalog for the baseline composition.
            # Runtime cannot write target/inventory scope/revisions/audit or any legacy configuration.
            tables=[r['tablename'] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname=%s AND left(tablename,3)<>'ot_'",(schema,)).fetchall()]
            grants=[('SELECT',tables),('SELECT',['ot_target','ot_revision']),('SELECT,UPDATE',['ot_inventory'])]
            if side=='team360':
                grants += [('SELECT,INSERT',['ot_received_callback']),('INSERT,UPDATE',['message_events','message_threads'])]
            else:
                grants += [('SELECT',['ot_meta_instance']),('SELECT,INSERT,UPDATE',['ot_attempt','ot_callback'])]
            for privileges,names in grants:
                conn.execute(sql.SQL('GRANT {} ON {} TO {}').format(sql.SQL(privileges),sql.SQL(',').join(map(sql.Identifier,names)),sql.Identifier(role)))
            conn.commit()
            conn.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
            assert conn.execute('SELECT count(*) AS n FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)').fetchone()['n']==0
            assert not conn.execute('SELECT has_schema_privilege(current_user,%s,\'CREATE\') AS allowed',(schema,)).fetchone()['allowed']
            for table in ('ot_target','ot_revision','ot_operation'):
                for privilege in ('INSERT','UPDATE','DELETE','TRUNCATE'):
                    assert not conn.execute('SELECT has_table_privilege(current_user,%s,%s) AS allowed',(table,privilege)).fetchone()['allowed']
            assert not conn.execute('SELECT has_table_privilege(current_user,\'ot_inventory\',\'INSERT\') AS allowed').fetchone()['allowed']
            conn.rollback()
        dsns[side]='postgresql://'+quote(role,safe='')+':'+quote(password,safe='')+'@'+base['host']+':'+base.get('port','5432')+'/'+db
        with psycopg.connect(dsns[side],row_factory=dict_row,connect_timeout=3) as conn:
            info=conn.execute('SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
            assert all(info[k] is False for k in info if k!='rolname')
            proof[side]=dict(info)
    save('runtime-dsns.json',dsns)
    # Prisma requires URL syntax; values are private and never printed.
    evo=conninfo_to_dict(dsns['evolution'])
    from dotenv import dotenv_values
    from urllib.parse import urlsplit
    lab = P.parents[2] / 'lab/evolution-api'
    # Preserve the existing container-to-PostgreSQL endpoint, not host localhost.
    old = urlsplit(dotenv_values(lab/'.env')['DATABASE_CONNECTION_URI'])
    uri='postgresql://'+quote(evo['user'],safe='')+':'+quote(evo['password'],safe='')+'@'+old.hostname+':'+str(old.port or 5432)+'/'+evo['dbname']+'?'+urlencode({'schema':'evolution_api','connection_limit':4})
    save('evolution-runtime-dsn.json',{'url':uri})
    (OUT/'runtime-role-proof.json').write_text(json.dumps({'roles':proof,'target_revision_audit_write_privileges':False,
        'legacy_config_write_privileges':False,'business_rbac_modified':False,'memberships':0},indent=2)+'\n')
    print('RUNTIME_ROLE_PREFLIGHT=PASS ADMINISTRATION_WRITES_DENIED=YES')

if __name__=='__main__': main()
