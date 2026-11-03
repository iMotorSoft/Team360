"""Read-only precheck and unique recoverable owner-only backup; no PG writes."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parents[3] / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
from dotenv import dotenv_values
for key, value in dotenv_values(BACKEND.parent / '.env.backend-dev.local').items():
    if value is not None: os.environ[key] = value
from modules.telchi.provisioning.sales_repository import SalesActivationRepository, AUTHORIZATION
from modules.telchi.provisioning.live_cli import digest
from modules.db.settings import get_database_settings
import psycopg
from psycopg.rows import dict_row


async def main():
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn, row_factory=dict_row,
            options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
        snapshot = await SalesActivationRepository().snapshot(conn)
        version = await (await conn.execute('SHOW server_version')).fetchone()
    private = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/backups') / ('sales-rbac-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    private.mkdir(mode=0o700)
    backup = private / 'before.json'
    with backup.open('x') as f: json.dump(snapshot, f, indent=2, default=str)
    backup.chmod(0o600)
    assert json.loads(backup.read_text()) == snapshot
    manifest = dict(authorization=AUTHORIZATION, environment='dev', operator_uid=os.getuid(),
        target=snapshot['target'], backup=str(backup), backup_sha256=digest(backup), sources={})
    for name in ('sales_repository.py', 'sales_cli.py', 'live_cli.py', 'admin_repository.py', 'repository.py', 'admin_service.py'):
        manifest['sources'][name] = digest(BACKEND / 'modules/telchi/provisioning' / name)
    path = private / 'manifest.json'
    with path.open('x') as f: json.dump(manifest, f, indent=2)
    path.chmod(0o600)
    (ROOT / 'precheck.json').write_text(json.dumps(dict(version=version, target=snapshot['target'],
        identities=snapshot['identities'], effective_before=snapshot['effective'], backup=str(backup),
        backup_sha256=manifest['backup_sha256'], backup_roundtrip=True, manifest=str(path),
        existing_counts={k:len(v) for k,v in snapshot['records'].items()}), indent=2))
    print(path)

if __name__ == '__main__': asyncio.run(main())
