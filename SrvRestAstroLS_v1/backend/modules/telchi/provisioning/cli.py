"""Legacy offline seed plan only. Execution moved to authenticated admin_cli."""
import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from .repository import Seed, Conflict

REQUIRED = ('dev_isolation', 'no_production_impact', 'human_identities', 'business_permission',
            'backup_restore', 'explicit_application', 'organization_admin_membership')


def approved(manifest):
    seed = Seed(**manifest['seed'])
    seed.validate()
    for key in REQUIRED:
        # Opaque reference to human evidence, NOT a magical runtime environment flag.
        if not isinstance(manifest.get('approvals', {}).get(key), str) or not manifest['approvals'][key].strip():
            raise Conflict('approval missing: ' + key)
    target = manifest['target']
    if not all(target.get(k) for k in ('database', 'system_identifier', 'server_address', 'server_port')):
        raise Conflict('pinned target missing')
    return seed


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback-run')
    args = parser.parse_args()
    if args.apply or args.rollback_run:
        raise Conflict('legacy unauthenticated execution disabled; use admin_cli with authenticated actor. Rollback requires authorized service transaction')
    manifest = json.loads(args.manifest.read_text())
    seed = Seed(**manifest['seed'])
    seed.validate()
    print(json.dumps(dict(mode='PLAN_ONLY_NO_CONNECTION', seed=asdict(seed), required_approvals=REQUIRED), indent=2))


if __name__ == '__main__':
    asyncio.run(main())
