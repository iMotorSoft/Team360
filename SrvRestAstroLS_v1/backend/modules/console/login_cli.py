"""Explicit DEV Console password ceremony; secrets only via TTY/private files.

prepare: reviewed additive schema + dedicated role + persistent issuer, no users/passwords.
set-password: existing active user only, hidden input twice; OS-owner enrollment audit.
login: hidden password, output token to a NEW owner-only private file, never stdout.
"""
import argparse
import asyncio
import getpass
import json
import os
from pathlib import Path
import secrets
import stat
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from modules.console.login_admin_repository import ConsoleLoginAdminRepository, RUNTIME_ROLE
from modules.console.login_repository import ConsoleLoginRepository
from modules.console.login_service import ConsoleLoginService
from modules.db.settings import get_database_settings
from modules.security.environment import is_explicit_development_environment
from modules.security.paseto_tokens import PasetoConsoleSettings, PasetoKeyPair

ROOT = Path(__file__).resolve().parents[4]


def private_path(path, *, existing=False):
    path = Path(path).expanduser().absolute()
    if path.resolve().is_relative_to(ROOT):
        raise PermissionError('private_path_outside_repository_required')
    if path.is_symlink():
        raise PermissionError('symlink_rejected')
    parent = path.parent
    if not parent.is_dir() or parent.stat().st_uid != os.getuid() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise PermissionError('owner_only_private_directory_required')
    if existing:
        s = path.stat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
            raise PermissionError('owner_only_regular_file_required')
    return path


def write_private(path, text):
    path = private_path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd,'w') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    return path


def read_config(path):
    path = private_path(path,existing=True)
    cfg = json.loads(path.read_text())
    expected = {'version','environment','target','runtime_dsn','issuer','key_id','private_key_pem','public_key_pem','ttl_seconds'}
    if set(cfg) != expected or cfg['version'] != 1 or cfg['environment'] != 'dev':
        raise PermissionError('invalid_private_issuer_configuration')
    if set(cfg['target']) != {'database','system_identifier'} or not cfg['target']['system_identifier']:
        raise PermissionError('explicit_database_pin_required')
    local_dsn(cfg['runtime_dsn'])
    return cfg


def issuer_settings(cfg):
    return PasetoConsoleSettings(enabled=True,issuer=cfg['issuer'],key_id=cfg['key_id'],
        private_key_pem=cfg['private_key_pem'],public_key_pem=cfg['public_key_pem'],ttl_seconds=cfg['ttl_seconds'])


def local_dsn(dsn):
    target = conninfo_to_dict(dsn)
    if target.get('host') not in {'localhost','127.0.0.1','::1'} or target.get('dbname') != 'team360':
        raise PermissionError('explicit_local_team360_target_required')
    return target


async def checked_target(conn, expected, *, runtime=False):
    repo = ConsoleLoginRepository()
    if await repo.target(conn) != expected:
        raise PermissionError('database_pin_mismatch')
    if runtime:
        row = await repo.runtime_role(conn)
        if row['name'] != RUNTIME_ROLE or any(row[k] for k in ('rolsuper','rolbypassrls','rolcreaterole','rolcreatedb','owns_public_tables','member_of_privileged_roles')):
            raise PermissionError('unprivileged_runtime_role_required')


async def prepare(args):
    if not args.apply or not args.expected_system_id or not args.backup:
        raise PermissionError('explicit_apply_pin_backup_required')
    private_path(args.config)
    if args.config.exists():
        raise PermissionError('config_exists_refusing_overwrite')
    backup = private_path(args.backup,existing=True)
    with backup.open('rb') as stream:
        if stream.read(5) != b'PGDMP':
            raise PermissionError('postgres_custom_backup_required')
    dsn = get_database_settings().dsn
    params = local_dsn(dsn)
    target = {'database':'team360','system_identifier':args.expected_system_id}
    pair = PasetoKeyPair.generate('console-password-dev-v1')  # Explicit prepare, never login fallback.
    password = secrets.token_urlsafe(48)
    runtime_dsn = make_conninfo(host=params['host'],port=params.get('port','5432'),dbname='team360',user=RUNTIME_ROLE,password=password)
    cfg = dict(version=1,environment='dev',target=target,runtime_dsn=runtime_dsn,
               issuer='team360-console-password-dev-v1',key_id=pair.key_id,
               private_key_pem=pair.private_pem,public_key_pem=pair.public_pem,ttl_seconds=900)
    created = None
    try:
        async with await psycopg.AsyncConnection.connect(dsn,connect_timeout=5,row_factory=dict_row,
                options='-c statement_timeout=10000 -c lock_timeout=3000') as conn:
            async with conn.transaction():
                await checked_target(conn,target)
                await ConsoleLoginAdminRepository().prepare(conn,role_password=password)
                created = write_private(args.config,json.dumps(cfg,indent=2)+'\n')
    except BaseException:
        if created is not None:
            created.unlink()  # Only the file just exclusively created by this execution.
        raise
    print('DEV issuer/schema/runtime role prepared; no user password activated.')


async def ceremony(args):
    cfg = read_config(args.config)
    service = ConsoleLoginService(issuer_settings(cfg))
    if not sys.stdin.isatty():
        raise PermissionError('interactive_terminal_required')
    if args.command == 'set-password':
        if not args.apply or not args.local_owner_enrollment:
            raise PermissionError('explicit_local_owner_enrollment_required')
        dsn = get_database_settings().dsn
        local_dsn(dsn)
        password = getpass.getpass('New password (minimum 12 characters): ')
        confirmation = getpass.getpass('Repeat password: ')
        if password != confirmation:
            raise ValueError('password_confirmation_mismatch')
    else:
        # Fail before authentication/audit if token output is not a new safe private path.
        private_path(args.token_output)
        if args.token_output.exists():
            raise PermissionError('token_output_exists')
        dsn = cfg['runtime_dsn']
        password = getpass.getpass('Password: ')
    token = None
    async with await psycopg.AsyncConnection.connect(dsn,connect_timeout=5,row_factory=dict_row,
            options='-c statement_timeout=10000 -c lock_timeout=3000') as conn:
        async with conn.transaction():
            await checked_target(conn,cfg['target'],runtime=args.command=='login')
            if args.command == 'set-password':
                await service.enroll(conn,user_id=args.user_id,workspace_id=args.workspace_id,password=password)
            else:
                token = await service.login(conn,workspace_slug=args.workspace,email=args.email,password=password)
                # Normal return commits failure counters. Do not raise inside the transaction.
    if args.command == 'login':
        if token is None:
            raise PermissionError('authentication_failed')
        write_private(args.token_output,token+'\n')
        print('Authenticated Console token written to private file; expires in 900 seconds.')
    else:
        print('Password activated for existing DEV user; no session issued.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    for command in ('prepare','set-password','login'):
        p = sub.add_parser(command)
        p.add_argument('--config',required=True,type=Path)
        if command=='prepare':
            p.add_argument('--expected-system-id',required=True)
            p.add_argument('--backup',required=True,type=Path)
            p.add_argument('--apply',action='store_true')
        elif command=='set-password':
            p.add_argument('--user-id',required=True)
            p.add_argument('--workspace-id',required=True)
            p.add_argument('--apply',action='store_true')
            p.add_argument('--local-owner-enrollment',action='store_true')
        else:
            p.add_argument('--workspace',required=True)
            p.add_argument('--email',required=True)
            p.add_argument('--token-output',required=True,type=Path)
    args = parser.parse_args()
    try:
        if not is_explicit_development_environment():
            raise PermissionError('explicit_dev_required')
        asyncio.run(prepare(args) if args.command=='prepare' else ceremony(args))
    except Exception:
        # Never emit DB error details, configuration, credentials or supplied passwords.
        print('CONSOLE_AUTH_REJECTED: inspect target, authorization or credentials privately.',file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
