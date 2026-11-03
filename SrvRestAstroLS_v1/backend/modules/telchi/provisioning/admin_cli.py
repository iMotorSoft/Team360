"""Telchi DEV administrative commands. Reads existing Console PASETO from stdin.

No token issuing, implicit DEV keys, credentials, schema installation or bypass.
Operational use requires separately approved destination and authenticated issuer.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import stat
import sys

import psycopg
from psycopg.rows import dict_row

from modules.console.auth import verify_console_access_token
from modules.security.paseto_tokens import paseto_console_settings_from_env
from .admin_repository import AdminRepository
from .admin_service import AdminService, validate, keys
from .repository import Conflict


def private_json(path):
    path = path.resolve()
    root = Path(__file__).resolve().parents[5]
    if path.is_relative_to(root) or path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise Conflict('private files must be owner-only and outside repository')
    return json.loads(path.read_text())


async def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('bootstrap-client', 'manage-client'))
    parser.add_argument('--manifest', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    manifest = validate(private_json(args.manifest))
    if manifest['command'] != args.command:
        raise Conflict('command mismatch')
    # Operator trust configuration is NOT read from the client manifest.
    path = os.environ.get('TELCHI_ADMIN_TRUST_CONFIG')
    if not path:
        raise Conflict('separate private operator trust configuration required')
    trust = private_json(Path(path))
    keys(trust, ('environment', 'target', 'approvals'))
    keys(trust['target'], ('database', 'system_identifier', 'server_address', 'server_port'))
    keys(trust['approvals'], ('dev_isolation', 'explicit_application', 'backup_restore', 'authenticated_issuer'))
    if trust['environment'] != 'dev' or any(not isinstance(v, str) or not v.strip() for v in trust['approvals'].values()):
        raise Conflict('DEV isolation/application/restore/authenticated issuer evidence required')
    settings = paseto_console_settings_from_env()
    if not settings.enabled or not settings.public_key_pem:
        raise Conflict('explicit trusted Console public key required; no generated DEV keys')
    token = sys.stdin.readline().strip()
    principal = verify_console_access_token(token, public_keys_by_id={settings.key_id: settings.public_key_pem}, issuer=settings.issuer, leeway_seconds=0)
    del token
    dsn = os.environ.get('TELCHI_PROVISIONING_DSN')
    if not dsn:
        raise Conflict('explicit private DSN required; no global fallback')
    async with await psycopg.AsyncConnection.connect(dsn, connect_timeout=5, row_factory=dict_row, autocommit=True) as conn:
        async with conn.transaction():
            # Read-only enforced by PostgreSQL, not simulated writes + rollback.
            await conn.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE' + ('' if args.apply else ' READ ONLY'))
            if await AdminRepository().target(conn) != trust['target']:
                raise Conflict('actual target differs from separately approved DEV target')
            result = await AdminService().execute(conn, manifest, principal, dry_run=not args.apply)
    print(json.dumps(result, indent=2, default=str))


def main():
    try:
        asyncio.run(run())
    except Exception:
        # Database error details may contain PII, DSNs or proof references.
        print('TELCHI_ADMIN_ERROR: rejected or interrupted. Review private configuration, authorization and audit before retry.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
