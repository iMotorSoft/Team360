"""Explicit local DEV closeout. Never starts servers, issues tokens or sends messages."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from modules.db.settings import get_database_settings
from .business_close_repository import BusinessCloseRepository, AUTHORIZATION
from .repository import Conflict

PRIVATE = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi')


async def run(args):
    if os.getenv('TEAM360_ENV', '').strip().lower() not in {'dev','development'}:
        raise Conflict('explicit DEV environment required')
    dsn = get_database_settings().dsn
    parsed = urlparse(dsn)
    if parsed.hostname not in ('localhost','127.0.0.1') or parsed.port != 5432 or parsed.path != '/team360':
        raise Conflict('only local approved DEV team360 target allowed')
    async with await psycopg.AsyncConnection.connect(dsn, connect_timeout=5, row_factory=dict_row,
            application_name='telchi-business-close-owner-dev') as conn:
        await conn.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
        repo = BusinessCloseRepository()
        await repo.guard(conn)
        installed = (await (await conn.execute("SELECT to_regclass('public.core_module_full_access_grants') AS present")).fetchone())['present']
        if not installed:
            if not args.apply_schema or not args.apply:
                return dict(mode='PLAN_ONLY', schema_required='031_team360_scoped_full_access.sql', pilot_assignments=1)
            migration = Path(__file__).resolve().parents[3] / 'db/migrations/031_team360_scoped_full_access.sql'
            await conn.execute(migration.read_text())
        if not args.apply:
            return dict(mode='PLAN_ONLY', identity_scope_verified=bool(await repo.identities(conn)), revoke=args.revoke)
        snapshot = await repo.snapshot(conn)
        data = (json.dumps(snapshot, sort_keys=True, default=str, indent=2)+'\n').encode()
        directory = PRIVATE / ('business-close-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        directory.mkdir(mode=0o700)
        with os.fdopen(os.open(directory/'before.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        kwargs = dict(authorization=AUTHORIZATION, backup_sha256=hashlib.sha256(data).hexdigest())
        result = await (repo.revoke(conn, **kwargs) if args.revoke else repo.activate(conn, **kwargs))
        await conn.commit()
        return dict(mode='APPLIED', backup=str(directory/'before.json'), **result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--apply-schema', action='store_true', help='Install only migration 031, local DEV')
    parser.add_argument('--revoke', action='store_true', help='Revoke only this pilot module FULL_ACCESS; retain normal grants')
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2, default=str))


if __name__ == '__main__':
    main()
