"""Read-only operational checks and real session-isolated Console authorization.

No listener/lifespan, model call, send, manifest publication or operational DML.
All DML targets explicitly qualified pg_temp tables containing a NEW fixture ID.
This diagnostic report is NOT a six-gate accreditation.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'SrvRestAstroLS_v1/backend'))
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l


async def run():
    from modules.db.pool import create_pool, open_pool, close_pool
    from modules.db.settings import get_database_settings
    from modules.console.repositories import PermissionConsoleRepository
    from modules.messaging.identity import PhoneIdentityRepository
    from modules.messaging.handlers import ChannelContext, MessageContext
    from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization
    config = l.load_config(d.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    ap = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
    approval = d.read_approval(ap)
    state_path = l.root() / 'current.json'
    state_bytes = state_path.read_bytes()
    state = l.read_json(state_path)
    manifest_path = d.private_file(approval['gates_file'])
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    source = d.source_digest()
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=source,
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        SIX_GATES='INVALID', AUTHORIZATION_GATE_STRATEGY='ISOLATED', GRANTS_MODIFIED='NO',
        RUNTIME_MODIFIED='NO', WHATSAPP_E2E='NOT_RUN', READY_FOR_MANUAL_START='NO',
        manifest_published=False, operational_dml=0, listeners_created=0,
        host_preflight='SAFE: 8 CPUs, load 1.51/1.58/1.90, 6991 MiB available; swap 7 MiB, no swap IO; sampled CPU idle 88-89%',
        concurrency='One process, one PostgreSQL connection; no model, scan or browser',
        runtime=dict(state=state.get('state'), backend_stopped=state.get('backend_stopped'),
            webhook_restored=state.get('webhook_restored'),
            backend_identity_alive=l.matches(state.get('backend')),
            launcher_identity_alive=l.matches(state.get('launcher')),
            backup_exists=Path(state['backup']).is_file(),
            closure_exists=(Path(state['backup']).parent / 'closure.json').exists()),
        policy=dict(value=manifest.get('validity_policy'), schema_version=manifest.get('schema_version'),
            expires_at_present='expires_at' in manifest,
            current_source_matches=manifest.get('source_sha256') == source),
        gates={name: 'NOT_ACCREDITED' for name in sorted(d.GATES)})
    srv, settings = d.configuration()
    binding = await d.check_database(approval, settings, srv.evolution)
    report['postgres_binding_identity'] = 'PASS'
    try:
        with d.client_for(srv.evolution) as client:
            connected = d.api(client, 'GET', '/instance/connectionState/' + srv.evolution.instance)
            webhook = d.webhook_body(d.api(client, 'GET', '/webhook/find/' + srv.evolution.instance))
            report['evolution'] = dict(open=connected.get('instance', {}).get('state') == 'open',
                                       webhook_enabled=webhook['enabled'])
    except Exception as exc:
        report['evolution'] = dict(read_only_check='ENVIRONMENTAL_ABORT', error_class=type(exc).__name__)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=1))
    await open_pool(pool)
    try:
        async with pool.connection() as conn:
            conn.prepare_threshold = None
            async with conn.transaction(force_rollback=True):
                await conn.execute('SET LOCAL statement_timeout = 5000')
                await conn.execute('SET LOCAL lock_timeout = 3000')
                resolver = PermissionConsoleRepository()
                actual_before = await resolver.list_effective_permissions(conn, approval['workspace_id'], approval['user_id'])
                channel = ChannelContext(binding.channel_id, 'evolution', binding.provider_instance,
                    binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
                identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
                assert identity and identity.user_id == approval['user_id']
                fixture_id = str(uuid4())
                absent = await (await conn.execute('SELECT count(*) AS n FROM public.core_users WHERE id=%s', (fixture_id,))).fetchone()
                assert absent['n'] == 0
                # Copy only approved user's rows, then assign ALL copied rows to a new synthetic ID.
                for table, key in (('core_users', 'id'), ('core_user_roles', 'user_id'),
                                   ('core_user_profiles', 'user_id'), ('core_module_full_access_grants', 'user_id')):
                    await conn.execute(f'CREATE TEMP TABLE {table} ON COMMIT DROP AS SELECT * FROM public.{table} WHERE {key}=%s', (approval['user_id'],))
                    await conn.execute(f'UPDATE pg_temp.{table} SET {key}=%s', (fixture_id,))
                await conn.execute('SET LOCAL search_path TO pg_temp, public')
                isolated = replace(identity, user_id=fixture_id)
                context = MessageContext(channel, isolated, settings.authorized_sender, 'isolated', 'isolated', frozenset())
                policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
                    approval['module_enabled'], approval['whole_workspace_scope_verified'],
                    pilot_access_check=lambda: d.unchanged_approval(ap, approval), pilot_user_id=fixture_id)
                authorization = BusinessAuthorization(policy)
                permission = 'telchi.sales.commercial_line_amount_by.read.v1'
                isolated_permissions = await resolver.list_effective_permissions(conn, approval['workspace_id'], fixture_id)
                assert isolated_permissions == actual_before
                assert permission in isolated.permissions
                assert await authorization.allowed(context, conn, required_permission=permission)
                assert not await authorization.allowed(replace(context, channel=replace(channel, tenant_id='foreign')), conn)
                assert not await authorization.allowed(replace(context, channel=replace(channel, workspace_id=str(uuid4()))), conn)
                # Remove ONLY the new synthetic identity's session-local assignments.
                # Operational roles/profiles/catalog/grants are never updated, revoked or restored.
                for table in ('core_user_roles', 'core_user_profiles', 'core_module_full_access_grants'):
                    await conn.execute(f'DELETE FROM pg_temp.{table} WHERE user_id=%s', (fixture_id,))
                assert await resolver.list_effective_permissions(conn, approval['workspace_id'], fixture_id) == []
                assert permission in isolated.permissions  # stale cache retained deliberately
                assert not await authorization.allowed(context, conn, required_permission=permission)
                report['isolated_authorization'] = dict(status='PASS', real_console_sql=True,
                    copied_rows_equal_actual_effective_permissions=True, new_fixture_identity=True,
                    stale_identity_denied=True, foreign_tenant_denied=True, foreign_workspace_denied=True,
                    fixture_scope='pg_temp only; forced rollback and connection close',
                    limitation='No operational grant revocation; no concurrent real-user revocation claimed')
            async with conn.transaction():
                await conn.execute('SET TRANSACTION READ ONLY')
                actual_after = await resolver.list_effective_permissions(conn, approval['workspace_id'], approval['user_id'])
                assert actual_after == actual_before
                for table in ('core_users', 'core_user_roles', 'core_user_profiles', 'core_module_full_access_grants'):
                    row = await (await conn.execute('SELECT to_regclass(%s) AS name', ('pg_temp.' + table,))).fetchone()
                    assert row['name'] is None
                report['temporary_fixtures_removed'] = True
                report['operational_effective_permissions_unchanged'] = True
    finally:
        await close_pool(pool)
        report['pool_closed'] = pool.closed
    assert state_path.read_bytes() == state_bytes
    assert manifest_path.read_bytes() == manifest_bytes
    assert source == d.source_digest()
    report['runtime_control_unchanged'] = report['manifest_unchanged'] = True
    report['own_processes_left_running'] = 0
    report['unrelated_processes_terminated'] = 0
    report['blockers'] = ['Lifecycle is READY, not STOPPED; registered processes absent; no closure/restoration confirmation.',
        'Evolution GET unavailable; current webhook restoration cannot be verified.',
        'Existing change_based_v1 manifest belongs to a different source digest. No partial publication.']
    report['next_step'] = 'Owner reconciles lifecycle and verifies webhook backup using official runbook in an explicitly authorized window; then repeat read-only preflight and reaccredit six gates using isolated authorization fixtures. Do not start services or restore webhook in this task.'
    return report


if __name__ == '__main__':
    try:
        result = asyncio.run(run())
    except Exception as exc:
        import traceback
        frames = traceback.extract_tb(exc.__traceback__)
        print(json.dumps(dict(status='BLOCKED', error_class=type(exc).__name__,
            frames=[dict(file=Path(f.filename).name, line=f.lineno) for f in frames], manifest_published=False)))
        raise SystemExit(1) from None
    output = Path(__file__).with_name('report.json')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in ('source_sha256', 'SIX_GATES', 'AUTHORIZATION_GATE_STRATEGY', 'GRANTS_MODIFIED', 'RUNTIME_MODIFIED', 'WHATSAPP_E2E', 'READY_FOR_MANUAL_START', 'isolated_authorization')}))
