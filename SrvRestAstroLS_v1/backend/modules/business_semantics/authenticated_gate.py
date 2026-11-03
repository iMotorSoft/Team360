"""Operator-run DEV ceremony: existing login CLI followed immediately by rollback-only gates.

Manifest: {"identities": [{"slot": "user-a|user-b|tenant-b|admin", "email": "...",
"workspace": "...", "user_id": "existing UUID", "workspace_id": "existing UUID"}]}.
Default full gate requires four distinct subjects. Explicit diagnostic-three omits user-b,
compares reader/admin catalogs and finishes PARTIAL (exit 2), never full coverage PASS.
No enrollment unless --enroll-authorized is explicitly passed in full mode by the operator.
Passwords remain in login_cli's TTY; tokens stay in new private files, never in reports.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import psycopg
from psycopg.rows import dict_row

from modules.console.login_cli import read_config, checked_target, issuer_settings, private_path
from modules.console.login_service import ConsoleLoginService
from modules.console.auth import ConsoleAuthError
from .repository import BusinessConceptRepository, rows
from .resolver import BusinessConceptResolver
from .service import BusinessConceptAdministration

SLOTS = {'user-a', 'user-b', 'tenant-b', 'admin'}


def load_manifest(path, mode='full'):
    if mode not in {'full', 'diagnostic-three'}:
        raise ValueError('unknown_ceremony_mode')
    identities = json.loads(path.read_text())['identities']
    slots = SLOTS if mode == 'full' else SLOTS - {'user-b'}
    if len(identities) != len(slots) or {i['slot'] for i in identities} != slots:
        raise ValueError('four_explicit_identity_slots_required' if mode == 'full'
                         else 'three_explicit_identity_slots_required')
    if len({i['user_id'] for i in identities}) != len(slots):
        raise ValueError('distinct_authorized_identities_required')
    telchi = {i['workspace_id'] for i in identities if i['slot'] != 'tenant-b'}
    other = next(i for i in identities if i['slot'] == 'tenant-b')
    if len(telchi) != 1 or other['workspace_id'] in telchi:
        raise ValueError('separate_workspace_required')
    for i in identities:
        uuid.UUID(i['user_id']); uuid.UUID(i['workspace_id'])
        if not i['email'] or not i['workspace']:
            raise ValueError('explicit_login_identifiers_required')
    return sorted(identities, key=lambda i: ['user-a', 'user-b', 'tenant-b', 'admin'].index(i['slot']))


async def validate(cfg, identity, token_path, identities):
    repo = BusinessConceptRepository()
    service = ConsoleLoginService(issuer_settings(cfg))
    token = private_path(token_path, existing=True).read_text().strip()
    async with await psycopg.AsyncConnection.connect(cfg['runtime_dsn'], row_factory=dict_row,
            connect_timeout=5, options='-c statement_timeout=10000 -c lock_timeout=3000') as conn:
        async with conn.transaction(force_rollback=True):
            await checked_target(conn, cfg['target'], runtime=True)
            principal = await service.verify_session(conn, token, workspace_id=identity['workspace_id'])
            if principal.user_id != identity['user_id']:
                raise PermissionError('authenticated_subject_differs_from_authorized_manifest')
            scope = await repo.scope(conn, identity['workspace_id'])
            expected_code = 'telchi' if identity['slot'] != 'tenant-b' else None
            if (expected_code and scope['organization_code'] != expected_code) or (not expected_code and scope['organization_code'] == 'telchi'):
                raise PermissionError('expected_tenant_mismatch')
            await repo.authorize(conn, scope['organization_id'], identity['workspace_id'], principal.user_id)
            catalog = await repo.catalog(conn, scope['organization_id'], identity['workspace_id'], 'telchi')
            checks = {'password_session': True, 'active_identity': True}
            if identity['slot'] != 'tenant-b':
                if not catalog:
                    raise AssertionError('published_telchi_catalog_required')
                resolved = await BusinessConceptResolver().resolve(conn, organization_id=scope['organization_id'],
                    workspace_id=identity['workspace_id'], module='telchi', actor_id=principal.user_id,
                    text=catalog[0]['semantic_code'])
                assert resolved['status'] == 'resolved'
                checks['published_exact_retrieval'] = True
            foreign = next(i for i in identities if (i['slot'] == 'tenant-b') != (identity['slot'] == 'tenant-b'))
            foreign_scope = await repo.scope(conn, foreign['workspace_id'])
            if foreign_scope['organization_id'] == scope['organization_id']:
                raise AssertionError('different_organization_required')
            try:
                await service.verify_session(conn, token, workspace_id=foreign['workspace_id'])
            except (PermissionError, ConsoleAuthError):
                checks['foreign_session_rejected'] = True
            else:
                raise AssertionError('foreign_session_accepted')
            try:
                await BusinessConceptResolver().resolve(conn, organization_id=foreign_scope['organization_id'],
                    workspace_id=foreign['workspace_id'], module='telchi', actor_id=principal.user_id,
                    text='telchi.farmacia')
            except PermissionError:
                checks['foreign_retrieval_denied'] = True
            else:
                raise AssertionError('foreign_retrieval_accepted')
            admin = BusinessConceptAdministration()
            for action in ('list', 'propose', 'publish', 'alias', 'retire', 'history', 'embed'):
                try:
                    await admin.execute(conn, actor_id=principal.user_id, workspace_id=foreign['workspace_id'],
                        module='telchi', action=action, payload={})
                except PermissionError:
                    checks['foreign_'+action+'_denied'] = True
                else:
                    raise AssertionError('foreign_administration_accepted')
            if identity['slot'] == 'admin':
                # Fully synthetic semantic definition; transaction always rolls back.
                item = dict(code='dev.ceremony.'+uuid.uuid4().hex, name='Synthetic ceremony probe',
                    definition='Synthetic validation only; not a commercial fact.', type='validation',
                    context={'synthetic': True}, source='DEV ceremony', reason='rollback-only validation', aliases=[])
                created = await admin.execute(conn, actor_id=principal.user_id, workspace_id=identity['workspace_id'],
                    module='telchi', action='propose', payload=item)
                for action, payload in [('list', {}), ('history', created),
                                        ('alias', dict(created, alias='Synthetic ceremony alias')),
                                        ('publish', created), ('retire', created)]:
                    await admin.execute(conn, actor_id=principal.user_id, workspace_id=identity['workspace_id'],
                        module='telchi', action=action, payload=payload)
                    checks['admin_'+action] = True
                checks['admin_propose'] = True
                # Immutable published aliases must fail in a savepoint, not poison the gate.
                try:
                    async with conn.transaction():
                        await admin.execute(conn, actor_id=principal.user_id, workspace_id=identity['workspace_id'],
                            module='telchi', action='alias', payload=dict(created, alias='Forbidden published alias'))
                except psycopg.Error as exc:
                    if exc.sqlstate != 'P0001':
                        raise
                    checks['published_alias_mutation_denied'] = True
                else:
                    raise AssertionError('published_alias_changed')
            elif identity['slot'] != 'tenant-b':
                for action in ('list', 'propose', 'publish', 'alias', 'retire', 'history', 'embed'):
                    try:
                        await admin.execute(conn, actor_id=principal.user_id, workspace_id=identity['workspace_id'],
                            module='telchi', action=action, payload={})
                    except PermissionError:
                        checks['nonadmin_'+action+'_denied'] = True
                    else:
                        raise AssertionError('nonadmin_administration_accepted')
            return dict(slot=identity['slot'], subject_hash=hashlib.sha256(principal.user_id.encode()).hexdigest(),
                catalog_fingerprint=hashlib.sha256(json.dumps(sorted((c['concept_id'], c['version']) for c in catalog)).encode()).hexdigest(),
                checks=checks, rollback_only=True, status='PASS')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--auth-config', required=True, type=Path)
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--mode', choices=('full', 'diagnostic-three'), default='full',
                   help='diagnostic-three omits user-b and can only finish PARTIAL (exit 2)')
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--enroll-authorized', action='store_true')
    args = p.parse_args()
    results = []
    try:
        if os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
            raise PermissionError('explicit_DEV_required')
        cfg = read_config(args.auth_config)
        if args.mode == 'diagnostic-three' and args.enroll_authorized:
            raise PermissionError('diagnostic_mode_forbids_enrollment')
        identities = load_manifest(private_path(args.manifest, existing=True), args.mode)
        if args.output.exists():
            raise FileExistsError('new_report_path_required')
        # Cheap checks before any human login; no scrypt/password operations.
        async def preflight():
            async with await psycopg.AsyncConnection.connect(cfg['runtime_dsn'], row_factory=dict_row, connect_timeout=5) as conn:
                await checked_target(conn, cfg['target'], runtime=True)
                for i in identities:
                    actor = await service_actor(conn, i)
                    if not actor:
                        raise PermissionError('manifest_identity_not_active')
                    repo = BusinessConceptRepository()
                    scope = await repo.scope(conn, i['workspace_id'])
                    if (scope['organization_code'] == 'telchi') != (i['slot'] != 'tenant-b'):
                        raise PermissionError('manifest_tenant_mismatch')
                    try:
                        await repo.authorize(conn, scope['organization_id'], i['workspace_id'], i['user_id'], admin=True)
                    except PermissionError:
                        if i['slot'] == 'admin':
                            raise
                    else:
                        if i['slot'] in {'user-a', 'user-b'}:
                            raise PermissionError('nonadmin_test_identity_required')
        asyncio.run(preflight())
        if args.prepare_only:
            print('CEREMONY_READY: manifest and restricted DEV target checked; no login or enrollment')
            return
        if not sys.stdin.isatty():
            raise PermissionError('interactive_terminal_required')
        for identity in identities:
            base = [sys.executable, '-m', 'modules.console.login_cli']
            if args.enroll_authorized:
                print('Authorized enrollment: '+identity['slot'], flush=True)
                subprocess.run(base+['set-password', '--config', str(args.auth_config), '--user-id', identity['user_id'],
                    '--workspace-id', identity['workspace_id'], '--apply', '--local-owner-enrollment'], check=True)
            token = args.auth_config.parent / ('ceremony-'+identity['slot']+'-'+uuid.uuid4().hex+'.paseto')
            print('Login and immediate validation: '+identity['slot'], flush=True)
            try:
                subprocess.run(base+['login', '--config', str(args.auth_config), '--workspace', identity['workspace'],
                    '--email', identity['email'], '--token-output', str(token)], check=True)
                result = asyncio.run(validate(cfg, identity, token, identities))
                if identity['slot'] != 'tenant-b':
                    with token.open() as session_input:
                        listed = subprocess.run([sys.executable, '-m', 'modules.business_semantics.cli', 'list',
                            '--workspace', identity['workspace'], '--auth-config', str(args.auth_config)],
                            stdin=session_input, capture_output=True, timeout=20)
                    if listed.returncode != (0 if identity['slot'] == 'admin' else 1):
                        raise AssertionError('existing_cli_list_unexpected_result')
                    result['checks']['existing_cli_list_expected_RBAC'] = True
                results.append(result)
                print(identity['slot']+': PASS', flush=True)
            finally:
                # Only the token file exclusively created by this invocation.
                if token.exists():
                    token.unlink()
        by_slot = {r['slot']: r for r in results}
        a = by_slot['user-a']
        b = by_slot['user-b' if args.mode == 'full' else 'admin']
        if a['subject_hash'] == b['subject_hash'] or a['catalog_fingerprint'] != b['catalog_fingerprint']:
            raise AssertionError('multiuser_catalog_mismatch')
        status = 'PASS' if args.mode == 'full' else 'PARTIAL'
    except Exception as exc:
        status = 'FAIL'
        results.append({'status': 'FAIL', 'error_class': type(exc).__name__})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(dict(status=status, mode=args.mode, identities=results,
            missing_coverage=['second_nonadmin_telchi_reader', 'two_nonadmin_catalog_equivalence']
                if args.mode == 'diagnostic-three' else [],
            scope='CLI_DB_RBAC_not_HTTP_or_WhatsApp_E2E'), stream, indent=2)
    print('AUTHENTICATED_GATE='+status)
    if status != 'PASS':
        raise SystemExit(2 if status == 'PARTIAL' else 1)


async def service_actor(conn, identity):
    from modules.console.login_repository import ConsoleLoginRepository
    # Verify manifest email/slug too; never infer identity from free-form text.
    actors = await rows(conn, '''SELECT u.id FROM core_users u JOIN core_workspaces w ON w.id=u.workspace_id
        WHERE u.id=%s AND w.id=%s AND lower(u.email)=lower(%s) AND w.slug=%s''',
        (identity['user_id'], identity['workspace_id'], identity['email'], identity['workspace']))
    return actors and await ConsoleLoginRepository().actor(conn, identity['user_id'], identity['workspace_id'])


if __name__ == '__main__':
    main()
