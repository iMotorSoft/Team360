"""Owner-approved local DEV registry procedure, private backup and ledger; no grants."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from modules.db.settings import get_database_settings
from .business_close_cli import PRIVATE
from .ranking_repository import RankingRegistrationRepository, AUTHORIZATION, TARGET
from .repository import Conflict


async def run(args):
    if os.getenv('TEAM360_ENV', '').strip().lower() not in {'dev', 'development'}:
        raise Conflict('explicit DEV environment required')
    dsn = get_database_settings().dsn
    parsed = urlparse(dsn)
    if parsed.hostname not in ('localhost', '127.0.0.1') or parsed.port != 5432 or parsed.path != '/team360':
        raise Conflict('only approved local DEV team360 target allowed')
    async with await psycopg.AsyncConnection.connect(dsn, connect_timeout=5, row_factory=dict_row,
            application_name='telchi-ranking-register-owner-dev') as conn:
        await conn.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
        repo = RankingRegistrationRepository()
        await repo.guard(conn)
        if await repo.target(conn) != TARGET:
            raise Conflict('actual DEV database identity differs')
        before = await repo.snapshot(conn)
        if not args.apply:
            return dict(mode='PLAN_ONLY', target=before['target'], identities=before['identities'], effective=before['effective'])
        data = (json.dumps(before, sort_keys=True, default=str, indent=2)+'\n').encode()
        out = PRIVATE / ('ranking-registration-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        out.mkdir(mode=0o700)
        with os.fdopen(os.open(out/'before.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        digest = hashlib.sha256(data).hexdigest()
        result = await repo.activate(conn, authorization=AUTHORIZATION, backup_sha256=digest)
        repeated = await repo.activate(conn, authorization=AUTHORIZATION, backup_sha256=digest)
        if repeated['changed'] or repeated['run_id']:
            raise Conflict('registration not idempotent')
        await conn.commit()
        return dict(mode='APPLIED', backup=str(out/'before.json'), backup_sha256=digest, idempotent=True, **result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    print(json.dumps(asyncio.run(run(parser.parse_args())), indent=2, default=str))


if __name__ == '__main__':
    main()
