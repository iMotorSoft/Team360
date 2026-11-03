"""Administrative rules reusable by a future UI; no transport or credentials."""
import re
from uuid import UUID

from .admin_repository import AdminRepository, ROLE
from .repository import Conflict, Seed, PERMISSION


def keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise Conflict('manifest fields missing or unknown')


def ident(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise Conflict('canonical UUID required')


def validate(manifest):
    keys(manifest, ('version', 'environment', 'actor_id', 'workspace_id', 'command'), ('seed', 'operations'))
    if manifest['version'] != 1 or manifest['environment'] != 'dev':
        raise Conflict('only V1 DEV manifests supported')
    ident(manifest['actor_id'])
    ident(manifest['workspace_id'])
    if manifest['command'] == 'bootstrap-client':
        if 'operations' in manifest:
            raise Conflict('bootstrap cannot contain delegated operations')
        keys(manifest.get('seed'), ('workspace_id', 'organization_id', 'stage'), ('admin_id', 'pilot_id'))
        seed = Seed(**manifest['seed'])
        seed.validate()
        if seed.workspace_id != manifest['workspace_id']:
            raise Conflict('workspace mismatch')
    elif manifest['command'] == 'manage-client':
        if 'seed' in manifest or not isinstance(manifest.get('operations'), list) or not 1 <= len(manifest['operations']) <= 50:
            raise Conflict('one to fifty operations required')
        for op in manifest['operations']:
            if not isinstance(op, dict):
                raise Conflict('operation must be an object')
            action = op.get('action')
            if action == 'inspect':
                keys(op, ('action',))
                continue
            extra = {'grant': ('role', 'permissions', 'modules'), 'grant-sales': ('permissions', 'modules'), 'revoke-access': (),
                     'bind-phone': ('sender_identity', 'verification_ref', 'consent_verified'),
                     'revoke-phone': ('binding_id',)}
            if action not in extra:
                raise Conflict('unsupported operation; enrollment and module installation unavailable')
            keys(op, ('action', 'user_id', *extra[action]))
            ident(op['user_id'])
            if action == 'grant' and (op['role'] != ROLE or op['permissions'] != [PERMISSION] or op['modules'] != ['telchi']):
                raise Conflict('grant outside approved commercial catalog')
            if action == 'grant-sales':
                from .sales_repository import PERMISSIONS
                if op['permissions'] != list(PERMISSIONS.values()) or op['modules'] != ['telchi']:
                    raise Conflict('grant outside approved sales catalog')
            if action == 'bind-phone' and (not isinstance(op['sender_identity'], str) or not re.fullmatch(r'[1-9][0-9]{6,14}', op['sender_identity']) or op['consent_verified'] is not True or not isinstance(op['verification_ref'], str) or not op['verification_ref'].strip()):
                raise Conflict('normalized phone and independent consent/possession evidence required')
            if action == 'revoke-phone':
                ident(op['binding_id'])
    else:
        raise Conflict('unsupported command')
    return manifest


class AdminService:
    def __init__(self, repository=None):
        self.repository = repository or AdminRepository()

    async def execute(self, conn, manifest, principal, *, dry_run=True):
        validate(manifest)
        if principal.user_id != manifest['actor_id'] or principal.subject != 'user:' + principal.user_id:
            raise Conflict('authenticated actor mismatch')
        # SERIALIZABLE is set by caller; no caller-selected identities accepted.
        repo = self.repository
        actor, workspace = manifest['actor_id'], manifest['workspace_id']
        if not dry_run:
            await repo.guard(conn)
        if manifest['command'] == 'bootstrap-client':
            await repo.global_actor(conn, actor)
            seed = Seed(**manifest['seed'])
            if dry_run:
                if seed.stage == 'grants':
                    for user in set((seed.admin_id, seed.pilot_id)):
                        await repo.user(conn, workspace, user, lock=False)
                return dict(mode='READ_ONLY_PLAN', command=manifest['command'], stage=seed.stage,
                            limits=repo.limits(), conflicts_checked='actor/identity only; seed conflicts checked on apply')
            return await repo.bootstrap(conn, actor, seed)
        if dry_run:
            # Do not use SELECT FOR UPDATE in read-only transactions.
            await repo.delegated_actor(conn, actor, workspace, lock=False)
            for op in manifest['operations']:
                if op['action'] != 'inspect':
                    await repo.user(conn, workspace, op['user_id'], lock=False)
            return dict(mode='READ_ONLY_PLAN', operations=[op['action'] for op in manifest['operations']],
                        conflicts_checked='actor/catalog/identity; binding and grant conflicts checked on apply')
        return [await repo.manage(conn, actor, workspace, op) for op in manifest['operations']]
