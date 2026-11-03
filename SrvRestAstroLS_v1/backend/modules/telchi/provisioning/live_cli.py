"""Explicit audited local owner bootstrap for the three Telchi DEV identities.

Not a password/login command. Requires owner-only private manifest, a readable
validated backup and exact source hashes. Never issues a Console token.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from modules.db.settings import get_database_settings
from .admin_cli import private_json
from .live_repository import LiveRepository
from .repository import Conflict

AUTHORIZATION = 'TEAM360 — TELCHI DEV REAL PROVISIONING V1'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def validate(manifest):
    if manifest['authorization'] != AUTHORIZATION or manifest['environment'] != 'dev' or manifest['operator_uid'] != os.getuid():
        raise Conflict('explicit local owner DEV authorization required')
    if manifest['target']['database'] != 'team360' or manifest['target']['server_port'] != 5432:
        raise Conflict('only approved team360 target allowed')
    ids = [manifest['platform_workspace_id'], manifest['global_role_id'], *manifest['user_ids'],
           manifest['seed']['workspace_id'], manifest['seed']['organization_id']]
    if len(manifest['user_ids']) != 3 or len(set(ids)) != len(ids):
        raise Conflict('distinct identities/scopes required')
    for ident in ids:
        if str(UUID(ident)) != ident:
            raise Conflict('canonical UUID required')
    if manifest['seed'].get('stage') != 'scaffold' or set(manifest['seed']) != {'workspace_id', 'organization_id', 'stage'}:
        raise Conflict('only fixed scaffold followed by grants allowed')
    backup = Path(manifest['backup']).resolve()
    private = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi').resolve()
    if not backup.is_relative_to(private) or backup.stat().st_uid != os.getuid() or backup.stat().st_mode & 0o077:
        raise Conflict('owner-only backup in PRIVATE_ROOT required')
    if digest(backup) != manifest['backup_sha256'] or not backup.with_suffix('.toc').is_file():
        raise Conflict('backup integrity/TOC validation missing')
    for name in ('repository.py', 'admin_repository.py', 'live_repository.py'):
        if digest(Path(__file__).with_name(name)) != manifest['sources'].get(name):
            raise Conflict('reviewed source checksum changed')
    return manifest


async def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--local-owner-bootstrap', action='store_true')
    parser.add_argument('--sales-activation', action='store_true', help='Existing identities only: approved latest/coverage sales grants')
    parser.add_argument('--rollback-sales-run', default=None, help='Withdraw only assignments created by this sales run')
    parser.add_argument('--monetary-activation', action='store_true', help='Existing identities only: bounded period DocTotal grant')
    parser.add_argument('--product-activation', action='store_true', help='Existing identities only: product search and invoice lines by ItemCode')
    parser.add_argument('--invoice-activation', action='store_true', help='Existing identities only: products of one validated active invoice')
    args = parser.parse_args()
    if sum((args.sales_activation, args.monetary_activation, args.product_activation, args.invoice_activation)) > 1:
        raise Conflict('select one explicit activation scope')
    if args.sales_activation or args.monetary_activation or args.product_activation or args.invoice_activation:
        from .sales_cli import run_sales
        await run_sales(args)
        return
    if args.rollback_sales_run:
        raise Conflict('sales rollback requires --sales-activation')
    manifest = validate(private_json(args.manifest))
    if not args.apply:
        print(json.dumps(dict(mode='PLAN_ONLY', identities=3, migration_application=False,
                              password_activation=False, phone_verification=False)))
        return
    if not args.local_owner_bootstrap:
        raise Conflict('explicit local bootstrap confirmation required')
    dsn = get_database_settings().dsn
    parsed = urlparse(dsn)
    if parsed.hostname not in ('localhost', '127.0.0.1') or parsed.port != 5432 or parsed.path != '/team360':
        raise Conflict('only local approved DEV DSN allowed')
    async with await psycopg.AsyncConnection.connect(dsn, connect_timeout=5, row_factory=dict_row, autocommit=True,
                                                   application_name='telchi-dev-local-owner-bootstrap') as conn:
        async with conn.transaction():
            await conn.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
            result = await LiveRepository().apply(conn, manifest)
    print(json.dumps(result, indent=2, default=str))


def main():
    try:
        asyncio.run(run())
    except Exception:
        print('TELCHI_LOCAL_BOOTSTRAP_REJECTED: transaction aborted; inspect private manifest and schema, no secrets logged.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
