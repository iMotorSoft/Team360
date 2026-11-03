"""Minimal all-workspace DEV identity inventory to disambiguate name misses."""
import asyncio
import json
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict
from modules.db.settings import get_database_settings
from .probe import ReadOnlyProbeRepository, OUT

async def main():
    dsn=get_database_settings().dsn
    cfg=conninfo_to_dict(dsn)
    if cfg.get('host') not in {'localhost','127.0.0.1','::1'} or cfg.get('dbname')!='team360':
        raise RuntimeError('nonlocal_target_refused')
    conn=await psycopg.AsyncConnection.connect(dsn,connect_timeout=5,application_name='telchi-b3-readonly',
        options='-c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=1000 -c max_parallel_workers_per_gather=0')
    async with conn:
        async with conn.transaction():
            repo=ReadOnlyProbeRepository()
            report={'users':await repo.rows(conn,"""SELECT u.id::text AS user_id,u.display_name,u.status,w.slug,
                lower(coalesce(u.email,'')) LIKE ANY(%s) AS target_name_in_email,
                lower(u.metadata_jsonb::text) LIKE ANY(%s) AS target_name_in_metadata
                FROM core_users u JOIN core_workspaces w ON w.id=u.workspace_id ORDER BY w.slug,u.display_name""",
                (['%mario%','%abraham%'],['%mario%','%abraham%','%presidencia%'])),
                'presidencia_roles':await repo.rows(conn,"""SELECT role_code,display_name,status FROM core_roles
                    WHERE lower(role_code||' '||display_name) LIKE ANY(%s)""", (['%presiden%','%abraham%','%mario%'],)),
                'credential_counts':await repo.rows(conn,'SELECT count(*) AS credentials,count(*) FILTER(WHERE NOT disabled) AS enabled FROM console_password_credentials')}
    for user in report['users']:
        if '@' in (user.get('display_name') or ''):
            user['display_name']='<email-like display name redacted>'
    directory=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/console-auth-window-20261014T134648Z')
    report['documented_auth_directory']={'issuer_config_exists':(directory/'issuer.json').is_file(),
        'token_files_by_filename':sum('token' in p.name.lower() for p in directory.iterdir())}
    # Private identity allowlists are not sessions and cannot prove human ownership.
    report['private_allowlists']=[]
    for name in ['authorized-identities-diagnostic.json','authorized-identities-whatsapp.json']:
        p=directory/name
        if p.is_file():
            value=json.loads(p.read_text())
            report['private_allowlists'].append({'file':name,'top_level_keys':list(value) if isinstance(value,dict) else [],
                'is_console_session':False})
    with (OUT/'identity-inventory.json').open('x') as f: json.dump(report,f,indent=2,default=str)
    print(json.dumps(report,indent=2,default=str))

if __name__=='__main__': asyncio.run(main())
