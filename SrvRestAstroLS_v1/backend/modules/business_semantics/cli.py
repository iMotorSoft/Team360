"""DEV administration, Console PASETO from stdin. No token generation or grants."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict
from modules.console.auth import verify_console_access_token
from modules.security.paseto_tokens import paseto_console_settings_from_env
from modules.db.settings import get_database_settings
from .repository import rows
from .service import BusinessConceptAdministration
from .embeddings import EmbeddingConfiguration,LiteLLMEmbeddingAdapter
from .telchi_seed import seed


async def run():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['migrate','seed','propose','alias','publish','retire','history','embed','list'])
    p.add_argument('--migration', choices=['028_team360_business_semantics_v1.sql','029_team360_business_semantics_relations_v1.sql'],
                   default='028_team360_business_semantics_v1.sql')
    p.add_argument('--workspace',default='telchi_dev')
    p.add_argument('--module',default='telchi')
    p.add_argument('--payload',type=Path)
    p.add_argument('--foundation-evidence',type=Path,help='Optional inspected CURRENT evidence for addendum relations')
    p.add_argument('--historical-proposals',action='store_true',help='Seed documented candidates without publication')
    p.add_argument('--apply',action='store_true')
    p.add_argument('--auth-config',type=Path,help='Private Console password issuer/runtime configuration; no global pool change')
    p.add_argument('--local-owner-bootstrap',action='store_true',help='Explicit approved OS-owner seed/migration only, never chat or impersonation')
    p.add_argument('--actor-id',help='Existing administrator, only for approved local-owner seed')
    args=p.parse_args()
    if os.getenv('TEAM360_ENV') not in {'dev','development'}:
        raise ValueError('explicit_DEV_required')
    if args.action not in {'list','history'} and not args.apply:
        raise ValueError('explicit_apply_required')
    if args.local_owner_bootstrap and args.action not in {'migrate','seed'}:
        raise PermissionError('bootstrap_only_seed_or_migration')
    if args.action!='migrate' and not args.local_owner_bootstrap and not args.auth_config:
        raise PermissionError('password_issuer_configuration_required')
    actor=None
    login_service=None
    auth_config=None
    if args.auth_config:
        if args.local_owner_bootstrap or args.action=='migrate':
            raise PermissionError('password_runtime_not_bootstrap')
        from modules.console.login_cli import read_config,issuer_settings
        from modules.console.login_service import ConsoleLoginService
        auth_config=read_config(args.auth_config)
        login_service=ConsoleLoginService(issuer_settings(auth_config))
    if args.action!='migrate' and not args.local_owner_bootstrap:
        settings=issuer_settings(auth_config) if auth_config else paseto_console_settings_from_env()
        if not settings.enabled or not settings.public_key_pem:
            raise PermissionError('trusted_Console_issuer_required')
        session_token=sys.stdin.readline().strip()
        principal=verify_console_access_token(session_token,
            public_keys_by_id={settings.key_id:settings.public_key_pem},issuer=settings.issuer,leeway_seconds=0)
        if principal.subject!='user:'+principal.user_id:
            raise PermissionError('authenticated_user_required')
        actor=principal.user_id
    elif args.action=='seed':
        actor=args.actor_id
        if not actor:
            raise PermissionError('explicit_existing_seed_approver_required')
    if args.action=='migrate' and not args.local_owner_bootstrap:
        raise PermissionError('migration_requires_explicit_owner_window')
    dsn = auth_config['runtime_dsn'] if auth_config else get_database_settings().dsn
    client_target = conninfo_to_dict(dsn)
    if client_target.get('host') not in {'localhost', '127.0.0.1', '::1'}:
        raise PermissionError('explicit_local_client_target_required')
    async with await psycopg.AsyncConnection.connect(dsn,row_factory=dict_row,connect_timeout=5) as conn:
        async with conn.transaction():
            target=(await rows(conn,"SELECT current_database() AS db,inet_server_addr()::text AS address,current_setting('server_version_num') AS version,(pg_control_system()).system_identifier::text AS system_identifier"))[0]
            if (target['db']!='team360' or not target['version'].startswith('18')
                    or target['system_identifier'] != (auth_config['target']['system_identifier'] if auth_config else os.getenv('TEAM360_SEMANTICS_DEV_SYSTEM_IDENTIFIER'))):
                raise PermissionError('approved_local_PG18_DEV_target_required')
            await conn.execute("SET LOCAL lock_timeout='3s'")
            await conn.execute("SET LOCAL statement_timeout='10s'")
            if args.action=='migrate':
                path=Path(__file__).resolve().parents[2]/'db/migrations'/args.migration
                await conn.execute(path.read_text())
                print(json.dumps({'migration':path.name,'target':target,'applied':True}));return
            w=(await rows(conn,'SELECT id::text FROM core_workspaces WHERE slug=%s',(args.workspace,)))[0]
            if login_service:
                from modules.console.login_cli import checked_target
                await checked_target(conn,auth_config['target'],runtime=True)
                principal=await login_service.verify_session(conn,session_token,workspace_id=w['id'])
                actor=principal.user_id
            adapter=None
            if args.action=='embed':
                adapter=LiteLLMEmbeddingAdapter(EmbeddingConfiguration.from_env())
            admin=BusinessConceptAdministration(embeddings=adapter)
            if args.action=='seed':
                result=await seed(conn,admin,actor_id=actor,workspace_id=w['id'])
                if args.foundation_evidence:
                    from .addendum_seed import seed_relations
                    relations=await seed_relations(conn,admin,actor_id=actor,workspace_id=w['id'],
                        foundation_evidence=json.loads(args.foundation_evidence.read_text()))
                    result={'concepts':result,'relations':relations}
                if args.historical_proposals:
                    from .historical_proposals import seed_proposals
                    proposals=await seed_proposals(conn,admin,actor_id=actor,workspace_id=w['id'])
                    result={'seed':result,'historical':proposals}
            else:
                payload=json.loads(args.payload.read_text()) if args.payload else {}
                result=await admin.execute(conn,actor_id=actor,workspace_id=w['id'],module=args.module,action=args.action,payload=payload)
        print(json.dumps(result,default=str,ensure_ascii=False,indent=2))


def main():
    try:
        asyncio.run(run())
    except Exception as exc:
        print('BUSINESS_SEMANTICS_REJECTED: '+type(exc).__name__,file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':
    main()
