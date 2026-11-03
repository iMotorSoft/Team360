"""Observe Srv05 coexistence. No infrastructure administration or runtime repairs.

Run from backend: uv run python scripts/validate_team360_full_stack.py
Exit 0 = full PASS, 1 = structural failure, 2 = operational degradation.
Workers are fresh interpreters, bounded and sequential; no secrets in reports.
Default is read-only. --safe-operational explicitly allows isolated DEV state
writes/cleanup and synthetic responses, with a disabled-automation test fixture.
It never certifies unmodified enabled automation or promotion.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import AsyncExitStack, contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import traceback
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parents[1]
PUBLIC_ENV = {
    'AUTOMATION_DIAGNOSIS_REPOSITORY': 'postgres',
    'TEAM360_DIAGNOSIS_STATE_PROVIDER': 'postgres',
    'TEAM360_AI_PROVIDER': 'litellm',
    'TEAM360_LITELLM_BASE_URL': 'http://127.0.0.1:4000',
    'TEAM360_LITELLM_MODEL_ALIAS': 'openai_gpt-5.4-nano',
    'TEAM360_LITELLM_API_MODE': 'chat',
    'TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER': 'milvus',
    'TEAM360_MILVUS_HOST': '127.0.0.1', 'TEAM360_MILVUS_PORT': '19530',
    'TEAM360_MILVUS_COLLECTION': 'team360_sales_diagnosis_knowledge_v1',
    'TEAM360_EMBEDDING_VERSION': 'team360-openai-small-1536-v1',
}
TEST_GROUPS = {
    'Srv05': ['test_srv05_compatibility', 'test_srv05_architecture', 'test_srv05_runtime', 'test_srv05_launchers', 'test_srv05_evolution_isolation'],
    'Core': ['test_module_registry', 'test_db_module'],
    'Flow': ['test_flow_routes', 'test_flow_configuration_routes', 'test_flow_scheduler', 'test_flow_director_authorization', 'test_flow_access_mode', 'test_flow_configuration_service', 'test_flow_service', 'test_flow_lamuni_demo'],
    'Diagnosis': ['test_diagnosis_public_router', 'test_embed_clients_contract', 'test_knowledge_scope_resolver', 'test_sales_diagnosis_active_context', 'test_sales_diagnosis_milvus_provider', 'test_sales_diagnosis_runtime_contracts', 'test_sales_diagnosis_runtime_route', 'test_sales_diagnosis_runtime_dev_route', 'test_sales_diagnosis_feasibility_scope', 'test_sales_diagnosis_post_close'],
    'Console': ['test_console_auth', 'test_console_bootstrap_service', 'test_console_me_route', 'test_console_repositories_sql_safety', 'test_paseto_tokens'],
    'Messaging': ['test_messaging_evolution', 'test_messaging_gupshup_client', 'test_messaging_gupshup_config', 'test_messaging_gupshup_mapper', 'test_messaging_gupshup_sender', 'test_messaging_gupshup_webhook', 'test_messaging_whatsapp_idempotency', 'test_messaging_whatsapp_ports', 'test_messaging_meta_config', 'test_messaging_benchmark'],
    'Harness': ['test_team360_full_gate'],
}


def owner(module):
    if module.startswith('modules.flow'):
        return 'Flow'
    if module.startswith('modules.messaging'):
        return 'Messaging'
    if module.startswith('routes.console'):
        return 'Console'
    if module.startswith('routes.'):
        return 'Diagnosis'
    return 'Core'


def canonical(path):
    return re.sub(r'\{([^}:]+):[^}]+\}', r'{\1}', path)


def assert_unique(rows):
    counts = Counter((re.sub(r'\{[^}]+\}', '{}', r['path']), r['method']) for r in rows)
    assert not [key for key, n in counts.items() if n > 1], 'Duplicate path/method claims'


def inventory(app):
    rows = []
    for route in app.routes:
        for method, (handler, _) in getattr(route, 'route_handler_map', {}).items():
            if method == 'OPTIONS' or handler.fn.__module__.startswith('litestar'):
                continue
            module = handler.fn.__module__
            rows.append({'path': route.path, 'method': method, 'owner': owner(module),
                         'handler': f'{module}.{handler.fn.__qualname__}'})
    return sorted(rows, key=lambda r: (r['path'], r['method']))


def check_schema(schema, rows):
    operations = [(path, method.upper(), op) for path, item in schema['paths'].items()
                  for method, op in item.items() if method in {'get', 'post', 'patch', 'delete', 'put', 'head'}]
    ids = [op['operationId'] for _, _, op in operations]
    assert len(ids) == len(set(ids)), 'Duplicate OpenAPI operation IDs'
    assert {(canonical(r['path']), r['method']) for r in rows} == {(p, m) for p, m, _ in operations}
    def visit(value):
        if isinstance(value, dict):
            ref = value.get('$ref', '')
            if ref.startswith('#/'):
                target = schema
                for part in ref[2:].split('/'):
                    target = target[part.replace('~1', '/').replace('~0', '~')]
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(schema)


def structural():
    def forbidden(*args, **kwargs):
        raise AssertionError('Structural construction attempted network/process I/O')
    import socket
    from litestar import Litestar, Controller
    with patch.object(socket.socket, 'connect', forbidden), patch.object(subprocess, 'Popen', forbidden):
        import ls_iMotorSoft_Srv05 as srv
        import ls_iMotorSoft_Srv01 as legacy
        assert srv.app is not legacy.app
        assert inventory(srv.app) == inventory(legacy.app), 'Disabled extensions changed legacy base'
        captured = []
        def construct(**kwargs):
            captured.extend(kwargs['route_handlers'])
            return Litestar(**kwargs)
        with patch.object(legacy, 'Litestar', construct):
            fresh = srv.create_app()
        rows = inventory(srv.app)
        assert rows == inventory(fresh), 'Factory routing is not deterministic'
        # Inspect constructor inputs before Litestar can collapse/overwrite claims.
        claims = []
        for entry in captured:
            handlers = entry(owner=srv.app).get_route_handlers() if isinstance(entry, type) and issubclass(entry, Controller) else [entry]
            prefix = entry.path if isinstance(entry, type) and issubclass(entry, Controller) else ''
            for handler in handlers:
                for path in handler.paths:
                    for method in handler.http_methods:
                        claims.append({'path': '/' + (prefix + '/' + path).strip('/').replace('//', '/'), 'method': method,
                                       'handler': f'{handler.fn.__module__}.{handler.fn.__qualname__}'})
        assert_unique(claims)
        assert {(canonical(r['path']), r['method'], r['handler']) for r in rows} == {(canonical(r['path']), r['method'], r['handler']) for r in claims}, 'Handler lost or overwritten'
        check_schema(srv.app.openapi_schema.to_schema(), rows)
        assert [h.__name__ for h in srv.app.on_startup] == ['_open_db_pool', '_start_flow_scheduler']
        assert [h.__name__ for h in srv.app.on_shutdown] == ['_stop_flow_scheduler', '_close_db_pool']
        from modules.module_registry import get_module_route_handlers
        registry = get_module_route_handlers()
        assert len(registry) == len({id(h) for h in registry})
    return {'status': 'PASS', 'routes': rows, 'schema': srv.app.openapi_schema.to_schema(),
            'modules': {'Flow': 'MOUNTED', 'Diagnosis': 'MOUNTED', 'Console': 'MOUNTED',
                        'Messaging/Gupshup': 'MOUNTED', 'Messaging/Evolution': 'NOT_MOUNTED (Srv05 opt-in OFF)',
                        'Diagnosis product adapter': 'REGISTERED_BUT_DISABLED (default)',
                        'Diagnosis dev adapter': 'DEV_ONLY (physically mounted)', 'Telchi': 'NOT_IN_GLOBAL_SERVER'},
            'lifecycle_hooks': 'pool → scheduler; scheduler → pool'}


async def operational(result=None):
    from modules.db.settings import get_database_settings
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row
    from team360_full_gate_repository import inspect_database
    result = result if result is not None else {}
    result.update({'status': 'DEGRADED', 'services': {}, 'checks': {}, 'not_tested': [
        'Diagnosis conversational turn/persistence (no writes)', 'browser E2E', 'frontend build/static',
        'Gupshup outbound', 'Evolution send/delivery (no test binding enabled)',
        'Telchi (no global routes)', 'Flow automatic cycle (no external writes)']})
    services, checks = result['services'], result['checks']
    database = None
    try:
        async with await AsyncConnection.connect(get_database_settings().dsn, connect_timeout=5,
                options='-c default_transaction_read_only=on -c statement_timeout=5000', row_factory=dict_row) as conn:
            database = await inspect_database(conn)
        services['PostgreSQL'] = {'status': 'READY', **database}
    except Exception as exc:
        services['PostgreSQL'] = {'status': 'NOT_READY', 'error_class': type(exc).__name__}
    # Import the actual public configuration only after the database preflight.
    import ls_iMotorSoft_Srv05 as srv
    from modules.db.pool import get_pool, open_pool, close_pool
    from modules.flow.scheduler import get_scheduler
    import httpx
    from litestar.testing import AsyncTestClient
    pool = get_pool()
    if database:
        async with AsyncExitStack() as stack:
            if not database['automation_enabled']:
                client = await stack.enter_async_context(AsyncTestClient(srv.app))
                checks['Lifecycle'] = {'status': 'PASS', 'mode': 'real ASGI lifespan, read-only DB'}
                assert get_scheduler() is not None
                assert len([t for t in asyncio.all_tasks() if t.get_name() == 'flow-scheduler']) == 1
            else:
                # Do not start a live mail scheduler against enabled real automation.
                # Manual pool here is only a resource for read-only probes, not app startup.
                await open_pool(pool)
                stack.push_async_callback(close_pool, pool)
                client = await stack.enter_async_context(httpx.AsyncClient(transport=httpx.ASGITransport(app=srv.app), base_url='http://gate'))
                checks['Lifecycle'] = {'status': 'NOT_TESTED', 'reason': 'real Flow automation enabled; starting scheduler could send mail', 'mode': 'HTTP probes without lifespan; manually opened read-only probe pool'}
            await pool.wait(timeout=5)
            async with pool.connection() as conn:
                await inspect_database(conn)  # Prove the actual runtime pool is read-only too.
            from modules.flow.access_mode import flow_access_mode, DEFAULT_ADMIN_MODE
            access_mode = flow_access_mode()
            checks['Flow access policy'] = {'mode': access_mode, 'warning': 'default_admin includes Directorio; README/global status claiming unconditional PASETO differ from runtime' if access_mode == DEFAULT_ADMIN_MODE else None}
            from modules.sales_diagnosis_runtime.knowledge_scope_resolver import PostgresKnowledgeScopeResolver
            from modules.sales_diagnosis_runtime.contracts import KnowledgeScopeContext
            from modules.embed_clients.repository import PostgresEmbedClientRepository
            context = KnowledgeScopeContext(organization_code='team360_live', workspace_code='team360_public_site', package_code='pkg_sales_diagnosis', knowledge_scope_code='ks_team360_sales_diagnosis')
            resolver = PostgresKnowledgeScopeResolver(pool=pool)
            scope = await resolver.resolve_scope_id(context)
            wrong_scope = await resolver.resolve_scope_id(replace(context, organization_code='full_gate_wrong_tenant'))
            checks['Diagnosis context'] = {'status': 'PASS' if scope and wrong_scope is None else 'NOT_READY', 'public_scope': scope, 'wrong_tenant_denied': wrong_scope is None}
            embed = await PostgresEmbedClientRepository(pool).load('mamamia360')
            previous_probe_binding = await PostgresEmbedClientRepository(pool).load('mamamia360_embed')
            embed_scope = None
            if embed and embed.is_active:
                embed_context = KnowledgeScopeContext(organization_code=embed.organization_code, workspace_code=embed.workspace_code, package_code=embed.package_code, knowledge_scope_code=embed.knowledge_scope_code)
                embed_scope = await resolver.resolve_scope_id(embed_context)
            checks['Mamamia360 binding'] = {'status': 'PASS' if embed_scope else 'NOT_READY', 'client_id': 'mamamia360', 'previous_probe_id_present': previous_probe_binding is not None, 'client_present': embed is not None, 'active': bool(embed and embed.is_active), 'scope': embed_scope, 'reason': 'local DEV database only; no production binding altered'}
            probes = [('GET', '/health', None, {200}), ('GET', '/api/health', None, {200}),
                      ('GET', '/api/team360-flow/configuration', None, {200}),
                      ('GET', '/api/team360-flow/operational-settings', None, {200}),
                      ('GET', '/api/console/me', None, {401}),
                      ('GET', '/api/team360-flow/executive?page_size=1', None, {200} if access_mode == DEFAULT_ADMIN_MODE else {401}),
                      ('POST', '/api/diagnosis/turn', {'message': 'gate', 'organization_code': 'forbidden-tenant'}, {403}),
                      ('POST', '/webhooks/messaging/evolution/whatsapp', {}, {404}),
                      ('POST', '/webhooks/messaging/gupshup/whatsapp', {}, {401, 503})]
            checks['HTTP'] = []
            for method, path, body, expected in probes:
                response = await client.request(method, path, **({'json': body} if body is not None else {}))
                checks['HTTP'].append({'path': path, 'status_code': response.status_code, 'status': 'PASS' if response.status_code in expected else 'FAIL'})
            checks['HTTP aggregate'] = 'PASS' if all(p['status'] == 'PASS' for p in checks['HTTP']) else 'FAIL'
        assert pool.closed and get_scheduler() is None
        checks['Cleanup'] = {'status': 'PASS', 'pool_closed': True, 'scheduler_remaining': False}
    try:
        from pymilvus import MilvusClient
        client = MilvusClient(uri=os.environ.get('TEAM360_MILVUS_URI') or 'http://' + os.environ['TEAM360_MILVUS_HOST'] + ':' + os.environ['TEAM360_MILVUS_PORT'], token=os.environ.get('TEAM360_MILVUS_TOKEN', ''), timeout=5)
        try:
            collection = os.environ['TEAM360_MILVUS_COLLECTION']
            description = client.describe_collection(collection, timeout=5)
            fields = {f['name']: f for f in description['fields']}
            assert int(fields['embedding']['params']['dim']) == 1536
            assert 'knowledge_scope_id' in fields and 'embedding_version' in fields
            scopes = {checks.get('Diagnosis context', {}).get('public_scope'), checks.get('Mamamia360 binding', {}).get('scope')} - {None}
            assert scopes, 'No resolved scope for collection probe'
            for scope in scopes:
                matches = client.query(collection, filter=f'knowledge_scope_id == "{scope}" and embedding_version == "{os.environ["TEAM360_EMBEDDING_VERSION"]}"', output_fields=['knowledge_scope_id'], limit=1, timeout=5)
                assert matches and matches[0]['knowledge_scope_id'] == scope
            services['Milvus'] = {'status': 'READY', 'collection': collection, 'scopes_with_version_verified': len(scopes), 'dimension': 1536}
            # Consume the real public embedding adapter; search an already-loaded collection.
            # No collection.load(), writes, ingestion or synthetic/zero vectors.
            from routes.diagnosis import _PublicLiteLLMEmbeddingProvider
            vector = await asyncio.to_thread(_PublicLiteLLMEmbeddingProvider().embed_query, 'Automatizar consultas de ventas con aprobación humana')
            assert len(vector) == 1536 and any(vector)
            scope = checks['Diagnosis context']['public_scope']
            hits = client.search(collection, data=[vector], anns_field='embedding', filter=f'knowledge_scope_id == "{scope}" and embedding_version == "{os.environ["TEAM360_EMBEDDING_VERSION"]}"', search_params={'metric_type': 'COSINE'}, output_fields=['knowledge_scope_id'], limit=1, timeout=5)
            assert hits and hits[0] and all(h['entity']['knowledge_scope_id'] == scope for h in hits[0])
            checks['Diagnosis embedding/search'] = {'status': 'PASS', 'dimension': len(vector), 'results': len(hits[0]), 'scope_verified': True}
        finally:
            client.close()
    except Exception as exc:
        if services.get('Milvus', {}).get('status') == 'READY':
            checks['Diagnosis embedding/search'] = {'status': 'NOT_READY', 'error_class': type(exc).__name__}
        else:
            services['Milvus'] = {'status': 'NOT_READY', 'error_class': type(exc).__name__}
    try:
        from modules.automation_diagnosis.litellm_client import LiteLLMClient
        llm = LiteLLMClient(timeout_seconds=15)
        async with httpx.AsyncClient(timeout=5) as http:
            models = await http.get(llm.base_url + '/models', headers={'Authorization': 'Bearer ' + llm.api_key})
            models.raise_for_status()
            assert os.environ['TEAM360_LITELLM_MODEL_ALIAS'] in {m['id'] for m in models.json()['data']}
        response = await asyncio.to_thread(llm.chat_completion, os.environ['TEAM360_LITELLM_MODEL_ALIAS'], [{'role': 'user', 'content': 'Respond only with OK.'}], temperature=0, max_tokens=8, correlation_id='team360-full-gate')
        assert response.content.strip() and 'gpt-5.4-nano' in response.model
        services['LiteLLM'] = {'status': 'READY', 'alias': os.environ['TEAM360_LITELLM_MODEL_ALIAS'], 'observed_model': response.model, 'latency_ms': response.latency_ms, 'fallback': 'no client fallback; proxy internal routing NOT_TESTED'}
    except Exception as exc:
        services['LiteLLM'] = {'status': 'NOT_READY', 'error_class': type(exc).__name__}
    services['Evolution'] = {'status': 'OPTIONAL' if os.environ.get('TEAM360_MESSAGING_DEV_ENABLED') == '1' else 'NOT_REQUIRED', 'reason': 'DEV consumer conditional; Flow/Diagnosis do not consume it', 'health': 'NOT_TESTED'}
    services['Gmail'] = {'status': 'CONDITIONAL', 'probe': 'NOT_TESTED', 'reason': 'no delegated test account selected; no mail sent/read'}
    services['Gupshup'] = {'status': 'CONDITIONAL', 'probe': 'NOT_TESTED', 'reason': 'no outbound traffic authorized'}
    result['not_tested'].append('LiteLLM proxy internal fallback audit')
    if checks.get('Diagnosis embedding/search', {}).get('status') != 'PASS':
        result['not_tested'].append('Real embedding/vector search unsuccessful or unavailable')
    # Full PASS requires all guarantees, not just dependency health.
    return result


@contextmanager
def safe_scheduler_fixture(evidence):
    """Real settings read, explicit test-only disabled projection; no DB mutation."""
    from modules.flow.scheduler import FlowScheduler
    original = FlowScheduler._read_settings

    async def disabled(self):
        settings = await original(self)
        evidence['reads'] = evidence.get('reads', 0) + 1
        evidence['database_automation_enabled'] = settings.get('automation_enabled')
        return {**settings, 'automation_enabled': False, 'scheduler_interval_seconds': 1}

    async def forbidden_cycle(*args, **kwargs):
        evidence['forbidden_cycle_attempts'] = evidence.get('forbidden_cycle_attempts', 0) + 1
        raise AssertionError('Automatic delivery forbidden in gate fixture')

    with patch.object(FlowScheduler, '_read_settings', disabled), patch.object(FlowScheduler, '_execute_cycle', forbidden_cycle):
        yield


@contextmanager
def local_connections_only(evidence):
    """Deny Python socket egress except the three existing local dependencies."""
    import socket
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def allowed(address):
        return (isinstance(address, tuple) and address[0] in {'127.0.0.1', 'localhost', '::1'}
                and address[1] in {5432, 4000, 19530}) or isinstance(address, str) and address.startswith('/var/run/postgresql/')

    def guarded(self, address):
        if not allowed(address):
            evidence['blocked_connections'] = evidence.get('blocked_connections', 0) + 1
            raise OSError('Gate forbids non-dependency connections')
        return original(self, address)

    def guarded_ex(self, address):
        if not allowed(address):
            evidence['blocked_connections'] = evidence.get('blocked_connections', 0) + 1
            raise OSError('Gate forbids non-dependency connections')
        return original_ex(self, address)

    with patch.object(socket.socket, 'connect', guarded), patch.object(socket.socket, 'connect_ex', guarded_ex):
        yield


async def controlled_operational(result):
    """Opt-in fixture, not unmodified live automation and not production certification."""
    import base64
    import time
    from uuid import uuid4
    from urllib.parse import urlparse
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from modules.db.settings import get_database_settings
    from modules.db.pool import get_pool, create_pool, set_pool
    from modules.flow.scheduler import get_scheduler, start_scheduler
    from modules.security.paseto_tokens import PasetoKeyPair
    from modules.sales_diagnosis_runtime.state_repository import SyncPostgresConversationStateRepository
    from modules.automation_diagnosis.litellm_client import LiteLLMClient
    from team360_full_gate_repository import cleanup_test_sessions
    from litestar.testing import AsyncTestClient
    import ls_iMotorSoft_Srv05 as srv
    from routes import diagnosis

    checks = result['checks']
    phase = checks['Controlled operational'] = {'status': 'DEGRADED', 'fixture': 'scheduler disabled projection over real PG reads', 'scheduler': {'forbidden_cycle_attempts': 0}, 'egress': {'blocked_connections': 0}, 'conversation': [], 'llm_calls': []}
    if any(result['services'].get(s, {}).get('status') != 'READY' for s in ('PostgreSQL', 'Milvus', 'LiteLLM')):
        phase['reason'] = 'Dependency preflight incomplete'
        return
    dsn = get_database_settings().dsn
    identity = conninfo_to_dict(dsn)
    # libpq/grpc do not use Python sockets: validate their configured endpoints too.
    assert identity.get('dbname') == 'team360'
    assert identity.get('host', '') in {'localhost', '127.0.0.1', '::1', ''}
    assert identity.get('port', '5432') == '5432'
    assert os.environ['TEAM360_MILVUS_HOST'] in {'localhost', '127.0.0.1'}
    assert not os.environ.get('TEAM360_MILVUS_URI')
    assert urlparse(os.environ['TEAM360_LITELLM_BASE_URL']).hostname in {'localhost', '127.0.0.1'}
    assert urlparse(os.environ['TEAM360_LITELLM_BASE_URL']).port == 4000
    writable_dsn = make_conninfo(dsn, options='-c default_transaction_read_only=off -c statement_timeout=5000')
    sessions = ['full_gate_' + uuid4().hex for _ in range(2)]
    state = SyncPostgresConversationStateRepository(writable_dsn)
    original_chat = LiteLLMClient.chat_completion

    def observed_chat(self, *args, **kwargs):
        response = original_chat(self, *args, **kwargs)
        phase['llm_calls'].append({'model': response.model, 'provider': 'litellm', 'latency_ms': response.latency_ms, 'nonempty': bool(response.content.strip())})
        return response

    assert get_pool().closed
    pool = create_pool(get_database_settings())
    set_pool(pool)
    # A closed psycopg pool cannot reopen. Fresh test pool, never two live pools.
    phase['pool_fixture'] = 'fresh standard pool after prior read-only probe pool closed'
    try:
        with safe_scheduler_fixture(phase['scheduler']), local_connections_only(phase['egress']), patch.object(diagnosis, '_public_scope_resolver', None), patch.object(diagnosis, '_public_embed_client_repo', None):
            async with AsyncTestClient(srv.app) as client:
                await pool.wait(timeout=5)
                deadline = time.monotonic() + 5
                while phase['scheduler'].get('reads', 0) < 2 and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)
                assert phase['scheduler'].get('reads', 0) >= 2, 'Scheduler never reread real DB'
                assert get_scheduler() is not None and get_scheduler().is_running
                task = get_scheduler()._task
                await start_scheduler()
                assert get_scheduler()._task is task
                async def scheduler_task_count():
                    return len([t for t in asyncio.all_tasks() if t.get_name() == 'flow-scheduler'])
                # Litestar's AsyncTestClient runs lifespan in its own portal loop.
                count = client.blocking_portal.call(scheduler_task_count)
                assert count == 1 and not task.done()
                phase['scheduler_tasks_in_lifespan_loop'] = count
                phase['startup'] = 'PASS'
                phase['double_initialization'] = 'ABSENT'
                from team360_full_gate_repository import inspect_database
                async with pool.connection() as conn:
                    phase['pool_read_only'] = (await inspect_database(conn))['read_only']
                # Reuse official unit fixtures, while mounting the real HTTP handlers.
                sys.path.insert(0, str(BACKEND / 'tests'))
                from test_console_bootstrap_service import _service
                from routes import console_bootstrap
                pair = PasetoKeyPair.generate('full-gate-fixture')
                key_env = {'TEAM360_PASETO_ENABLED': 'true', 'TEAM360_PASETO_KEY_ID': pair.key_id,
                           'TEAM360_PASETO_PRIVATE_KEY_B64': base64.b64encode(pair.private_pem.encode()).decode(),
                           'TEAM360_PASETO_PUBLIC_KEY_B64': base64.b64encode(pair.public_pem.encode()).decode()}
                with patch.dict(os.environ, key_env), patch.object(console_bootstrap, '_SERVICE', _service(permissions=['package.view'], features=['events.basic'])):
                    bootstrap = await client.post('/api/console/bootstrap', json={'workspace_id': 'workspace-1', 'user_id': 'user-1'})
                    assert bootstrap.status_code == 201
                    payload = bootstrap.json()
                    assert payload['services'] and payload['effective_permissions'] == ['package.view']
                    token = payload['access_token']
                    assert token.startswith('v4.public.')
                    me = await client.get('/api/console/me', headers={'Authorization': 'Bearer ' + token})
                    assert me.status_code == 200 and me.json()['user_id'] == 'user-1'
                    invalid = await client.get('/api/console/me', headers={'Authorization': 'Bearer ' + token[:-5] + 'xxxxx'})
                    assert invalid.status_code == 401
                    assert (await client.get('/api/console/me')).status_code == 401
                    assert 'can_view_workers' not in payload['capabilities']
                    phase['Console fixture'] = {'status': 'PASS', 'bootstrap': 201, 'valid_token': 200, 'tampered_token': 401, 'missing_token': 401, 'permissions': payload['effective_permissions'], 'workspace': 'workspace-1', 'entitlements': payload['entitlements'], 'worker_access': 'DENIED by bootstrap capability', 'scope': 'official repository fakes + fresh Ed25519 keys; NOT real DB identity/RBAC'}
                # Only existing DEV clients; no seed, origin or tenant modification.
                from modules.embed_clients.repository import PostgresEmbedClientRepository
                mamamia = await PostgresEmbedClientRepository(pool).load('mamamia360')
                if mamamia and mamamia.is_active:
                    mamamia_origin = 'https://www.mamamia360.com'
                    mamamia_body = {'client_id': 'mamamia360', 'session_id': sessions[1], 'message': 'Sonda de autorización sin conversación.'}
                    allowed = await client.post('/api/diagnosis/embed/auth', json=mamamia_body, headers={'Origin': mamamia_origin})
                    denied = await client.post('/api/diagnosis/embed/auth', json=mamamia_body, headers={'Origin': 'https://full-gate-denied.invalid'})
                    assert allowed.status_code == 200 and denied.status_code == 403
                    unsigned = await client.post('/api/diagnosis/turn', json={**mamamia_body, 'timestamp': allowed.json()['timestamp']}, headers={'Origin': mamamia_origin})
                    assert unsigned.status_code == 403
                    phase['Mamamia authorization'] = {'status': 'PASS', 'client_id': 'mamamia360', 'allow_origin': allowed.status_code, 'deny_origin': denied.status_code, 'unsigned_turn': unsigned.status_code,
                                                     'context': {key: getattr(mamamia, key) for key in ('assistant_instance_code', 'organization_code', 'workspace_code', 'package_code', 'knowledge_scope_code')},
                                                     'distributor_model': 'embed binding to canonical public context, not independent customer DB', 'scope_cross_tenant': result['checks']['Diagnosis context']['wrong_tenant_denied']}
                embed = mamamia
                origin = 'https://www.mamamia360.com'
                if embed and embed.is_active and origin in embed.allowed_origins:
                    auth_body = {'client_id': 'mamamia360', 'session_id': sessions[1], 'message': 'Prueba técnica aislada: diagnóstico sin ejecutar acciones.'}
                    auth = await client.post('/api/diagnosis/embed/auth', json=auth_body, headers={'Origin': origin})
                    assert auth.status_code == 200
                    signed = auth.json()
                    assert not {'hmac_secret', 'organization_code', 'workspace_code', 'knowledge_scope_code'} & signed.keys()
                    bad_origin = await client.post('/api/diagnosis/embed/auth', json=auth_body, headers={'Origin': 'https://full-gate-denied.invalid'})
                    assert bad_origin.status_code == 403
                    altered = await client.post('/api/diagnosis/turn', json={**auth_body, 'message': 'changed', 'timestamp': signed['timestamp']}, headers={'Origin': origin, 'X-T360-Signature': signed['signature']})
                    assert altered.status_code == 403
                    phase['Embed auth'] = {'status': 'PASS', 'client_id': 'mamamia360', 'allow': 200, 'deny_origin': 403, 'request_bound_tamper': 403, 'context_fields_not_leaked': True}
                else:
                    phase['Embed auth'] = {'status': 'NOT_TESTED', 'reason': 'Canonical mamamia360 inactive, absent or allowed origin unavailable'}
                    signed = None
                # Real state repository and runtime, isolated session IDs; no corpus writes.
                assert all(state.load(sid) is None for sid in sessions)
                with patch.object(diagnosis, '_public_turn_state', state), patch.object(LiteLLMClient, 'chat_completion', observed_chat):
                    prompts = [
                        'Caso sintético de prueba. Tenemos una tienda y queremos automatizar consultas de stock y precios recibidas por email. Stock en sistema y precios en planilla. Son 20 consultas diarias y una persona aprueba toda respuesta. No ejecutes acciones.',
                        'El objetivo es reducir trabajo manual en consultas de ventas. Usamos email y Excel. La aprobación humana es obligatoria. Con estos datos cerrá un diagnóstico de factibilidad; no envíes comunicaciones ni pidas credenciales.',
                        'Dame ahora el diagnóstico final de factibilidad y un próximo paso concreto, sin implementar ni enviar nada.',
                    ]
                    for message in prompts:
                        started = time.monotonic()
                        response = await client.post('/api/diagnosis/turn', json={'session_id': sessions[0], 'message': message})
                        entry = {'http_status': response.status_code, 'latency_ms': round((time.monotonic() - started) * 1000)}
                        phase['conversation'].append(entry)
                        assert response.status_code == 201
                        body = response.json()
                        persisted = state.load(sessions[0])
                        assert body['response_text'].strip() and persisted
                        assert persisted.turn_count == len(phase['conversation']) == body['turn_count']
                        assert all(c.knowledge_scope_id == checks['Diagnosis context']['public_scope'] for c in persisted.last_sources)
                        generation = (body.get('turn_decision') or {}).get('generation', {})
                        assert generation.get('status') == 'success' and not generation.get('fallback_used') and not generation.get('provider_fallback_used')
                        memory = persisted.semantic_memory
                        entry['post_close_state'] = {key: memory.get(key) for key in ('human_approval', 'diagnosis_status')}
                        if persisted.turn_count >= 2:
                            assert memory.get('human_approval') == 'required'
                            assert memory.get('diagnosis_status') == 'completed'
                        if persisted.turn_count == 3:
                            assert body['turn_decision']['action'] == 'diagnose'
                            assert body.get('diagnosis')
                            assert '?' not in body['response_text'] and '¿' not in body['response_text']
                            phase['Diagnosis post-close'] = {'status': 'PASS', 'action': 'diagnose', 'reload': True, 'human_approval': 'required', 'diagnosis_status': 'completed', 'implicit_reopen': False, 'approval_event_created': False}
                        entry.update(response=body['response_text'], turn_count=persisted.turn_count, decision=body.get('turn_decision'), diagnosis_present=bool(body.get('diagnosis')), persisted=True, scope=persisted.knowledge_scope_code,
                                     retrieval=[{'chunk_id': c.chunk_id, 'scope': c.knowledge_scope_id, 'score': c.score} for c in persisted.last_sources])
                    phase['Diagnosis conversation'] = {'status': 'PASS' if any(e['diagnosis_present'] for e in phase['conversation']) and any(e['retrieval'] for e in phase['conversation']) and phase['llm_calls'] else 'DEGRADED', 'sessions': sessions[:1], 'state_provider': 'postgres', 'retrieval_provider': 'milvus', 'generation_provider': 'litellm', 'proxy_upstream_fallback_audit': 'NOT_TESTED'}
                    if signed:
                        response = await client.post('/api/diagnosis/turn', json={**auth_body, 'timestamp': signed['timestamp'], 'workspace_code': 'full-gate-wrong-tenant'}, headers={'Origin': origin, 'X-T360-Signature': signed['signature']})
                        assert response.status_code == 201
                        persisted = state.load(sessions[1])
                        assert persisted and persisted.knowledge_scope_code == embed.knowledge_scope_code and persisted.package_code == embed.package_code
                        phase['Embed conversation'] = {'status': 'PASS', 'http_status': 201, 'persisted': True, 'scope': persisted.knowledge_scope_code, 'package': persisted.package_code, 'body_context_override_ignored': True, 'browser_assets': 'NOT_TESTED'}
    except Exception as exc:
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        phase['error_class'] = type(exc).__name__
        phase['failed_at'] = f'{Path(frame.filename).name}:{frame.lineno}'
    finally:
        phase['cleanup'] = await cleanup_test_sessions(writable_dsn, sessions)
        phase['shutdown'] = 'PASS' if pool.closed and get_scheduler() is None else 'FAIL'
        phase['remaining_scheduler_tasks'] = len([t for t in asyncio.all_tasks() if t.get_name() == 'flow-scheduler'])
    if phase.get('startup') == 'PASS' and phase.get('shutdown') == 'PASS':
        phase['lifecycle_status'] = 'PASS_CONTROLLED_FIXTURE'
    # No escalation to Full PASS: live automation, browser and DB-backed Console remain untested.
    if phase.get('Diagnosis conversation', {}).get('status') == 'PASS':
        result['not_tested'] = [n for n in result['not_tested'] if not n.startswith('Diagnosis conversational')]
    result['not_tested'].extend(['Unmodified DB-enabled Flow automatic startup/delivery', 'Console real DB identity/permission boundary', 'Embed browser loader/manifest/assets'])


def run_child(command, env, timeout):
    # Each child owns a new session: timeout cleanup includes only its descendants.
    process = subprocess.Popen(command, cwd=BACKEND, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        completed.pid = process.pid
        return completed
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        # Child test suites must not leave listeners/workers in their own session.
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError('Own child session still has processes after cleanup')


def host_preflight():
    memory = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    load = os.getloadavg()[0]
    available_mb = memory['MemAvailable'] // 1024
    # Combined sustained CPU/memory risk; never consume all cores, all suites sequential.
    safe = available_mb >= 1024 and not (available_mb < 2048 and load > (os.cpu_count() or 1))
    return {'status': 'SAFE' if safe else 'RESOURCE_BLOCKED', 'load_1m': load,
            'available_mb': available_mb, 'swap_used_mb': (memory['SwapTotal'] - memory['SwapFree']) // 1024,
            'concurrency': 1, 'unrelated_processes_terminated': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=['structural', 'operational'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--safe-operational', action='store_true', help='Explicit controlled lifespan and isolated DEV conversation writes with scoped cleanup')
    args = parser.parse_args()
    if args.worker:
        result = {}
        try:
            result = structural() if args.worker == 'structural' else asyncio.run(operational(result))
            if args.worker == 'operational' and args.safe_operational:
                asyncio.run(controlled_operational(result))
        except Exception as exc:
            frame = traceback.extract_tb(exc.__traceback__)[-1]
            result.update(status='FAIL' if args.worker == 'structural' else 'DEGRADED', error_class=type(exc).__name__, failed_at=f'{Path(frame.filename).name}:{frame.lineno}')
        print('FULL_GATE_JSON=' + json.dumps(result, default=str))
        return 0
    output = args.output or ROOT / 'data/reports/team360-full-gate' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True, exist_ok=False)
    host = host_preflight()
    if host['status'] == 'RESOURCE_BLOCKED':
        (output / 'report.json').write_text(json.dumps({'host': host, 'full_gate': 'BLOCKED'}, indent=2) + '\n')
        print('TEAM360_FULL_GATE_BLOCKED: RESOURCE_BLOCKED')
        return 3
    env = dict(os.environ, AUTOMATION_DIAGNOSIS_REPOSITORY='memory', TEAM360_AI_PROVIDER='mock',
               TEAM360_SRV05_EVOLUTION_ENABLED='0')
    # Unit suites cannot inherit external opt-in switches from an operator shell.
    for key in list(env):
        if key.endswith(('_POSTGRES_TEST', '_INTEGRATION_TEST')):
            env.pop(key)
    report = {'host': host, 'entrypoint': 'ls_iMotorSoft_Srv05:app', 'timestamp': datetime.now(timezone.utc).isoformat(), 'tests': {}, 'processes': [], 'frontend': 'NOT_TESTED', 'browser': 'NOT_TESTED'}
    for mode in ('structural', 'operational'):
        worker_env = dict(env)
        if mode == 'operational':
            worker_env.update({key: os.environ.get(key) or value for key, value in PUBLIC_ENV.items()})
            worker_env['PGOPTIONS'] = '-c default_transaction_read_only=on -c statement_timeout=5000'
        try:
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', mode]
            if mode == 'operational' and args.safe_operational:
                command.append('--safe-operational')
            child = run_child(command, worker_env, 240 if args.safe_operational else 90)
            report['processes'].append({'pid': child.pid, 'kind': mode, 'returncode': child.returncode, 'session_cleanup_verified': True})
            payloads = [line[15:] for line in child.stdout.splitlines() if line.startswith('FULL_GATE_JSON=')]
            report[mode] = json.loads(payloads[-1]) if payloads else {'status': 'FAIL' if mode == 'structural' else 'DEGRADED', 'error_class': 'WorkerExited', 'returncode': child.returncode}
        except subprocess.TimeoutExpired:
            report[mode] = {'status': 'FAIL' if mode == 'structural' else 'DEGRADED', 'error_class': 'TimeoutExpired'}
    for group, names in TEST_GROUPS.items():
        if host_preflight()['status'] == 'RESOURCE_BLOCKED':
            report['tests'][group] = {'status': 'RESOURCE_BLOCKED'}
            continue
        command = [sys.executable, '-m', 'pytest', '-q', '--tb=no', '-p', 'no:cacheprovider', *[f'tests/{n}.py' for n in names]]
        try:
            child = run_child(command, env, 180)
            report['processes'].append({'pid': child.pid, 'kind': 'pytest ' + group, 'returncode': child.returncode, 'session_cleanup_verified': True})
            # Only test node IDs/counts, never assertion bodies or provider logs.
            lines = [line for line in child.stdout.splitlines() if re.match(r'^(FAILED tests/|=|\d+ passed|\d+ failed)', line)]
            report['tests'][group] = {'status': 'PASS' if child.returncode == 0 else 'FAIL', 'command': command[1:], 'summary': lines[-15:], 'returncode': child.returncode}
        except subprocess.TimeoutExpired:
            report['tests'][group] = {'status': 'FAIL', 'error_class': 'TimeoutExpired'}
    structural_pass = report['structural']['status'] == 'PASS' and all(t['status'] == 'PASS' for t in report['tests'].values())
    report['structural_gate'] = 'PASS' if structural_pass else 'FAIL'
    report['operational_gate'] = report['operational']['status']
    report['full_gate'] = ('PASS' if report['operational_gate'] == 'PASS' else 'DEGRADED') if structural_pass else 'BLOCKED'
    if 'schema' in report['structural']:
        (output / 'openapi.json').write_text(json.dumps(report['structural'].pop('schema'), indent=2) + '\n')
        (output / 'routes.json').write_text(json.dumps(report['structural']['routes'], indent=2) + '\n')
    (output / 'report.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    print('TEAM360 FULL GATE')
    print('Structural Gate       ' + report['structural_gate'])
    print('Operational Gate      ' + report['operational_gate'])
    for name, item in report['operational'].get('services', {}).items():
        print(f'{name:22}{item["status"]}')
    for group, item in report['tests'].items():
        print(f'{group + " tests":22}{item["status"]}')
    print('Detail: ' + str(output / 'report.json'))
    print('TEAM360_FULL_GATE_' + report['full_gate'])
    return (0 if report['full_gate'] == 'PASS' else 2) if structural_pass else 1


if __name__ == '__main__':
    raise SystemExit(main())
