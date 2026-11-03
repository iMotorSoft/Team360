"""Launcher profile isolation; real closed sockets, and opt-in PostgreSQL/HTTP."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
import pytest

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.repository import MessagingRepository

BACKEND = Path(__file__).resolve().parents[1]
LAUNCHER = BACKEND.parent / 'backend-dev.sh'
TOKEN = 'synthetic-webhook-token-0000000000000000'
FORBIDDEN = ('modules.flow', 'modules.telchi', 'modules.ai', 'modules.module_registry',
             'routes', 'pymilvus', 'litellm', 'openai', 'langchain', 'langgraph')


@pytest.fixture
def launcher(tmp_path):
    # Same launcher bytes, isolated from the operator's private local overrides.
    script = tmp_path / 'backend-dev.sh'
    script.write_bytes(LAUNCHER.read_bytes())
    (tmp_path / 'backend').symlink_to(BACKEND, target_is_directory=True)
    return script


def test_normal_default_retains_real_preflights(launcher):
    env = dict(os.environ)
    env.pop('TEAM360_DEV_PROFILE', None)
    env.update(TEAM360_POSTGRES_HOST='127.0.0.1', TEAM360_POSTGRES_PORT='1',
               TEAM360_MILVUS_HOST='127.0.0.1', TEAM360_MILVUS_PORT='1',
               TEAM360_LITELLM_BASE_URL='http://127.0.0.1:1')
    result = subprocess.run(['bash', str(launcher)], env=env, capture_output=True, text=True, timeout=15)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert 'PostgreSQL (127.0.0.1:1)' in output
    assert 'Milvus (127.0.0.1:1)' in output
    assert 'LiteLLM TCP (127.0.0.1:1)' in output
    assert 'required production-like services are unavailable' in output
    assert 'messaging-only preflight' not in output
    source = LAUNCHER.read_text()
    assert '_preflight_litellm_http || PREFLIGHT_FAILED=1' in source
    assert 'LiteLLM authenticated preflight' in source


def test_profile_refuses_production_unknown_and_occupied_port(launcher):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen()
        env = dict(os.environ, TEAM360_DEV_PROFILE='messaging-only', TEAM360_ENV='development',
                   TEAM360_BACKEND_PORT=str(listener.getsockname()[1]))
        result = subprocess.run(['bash', str(launcher)], env=env, capture_output=True, text=True, timeout=10)
        assert 'is occupied' in result.stdout and result.returncode != 0
        assert listener.fileno() != -1  # launcher never kills an existing owner
        env['TEAM360_ENV'] = 'production'
        result = subprocess.run(['bash', str(launcher)], env=env, capture_output=True, text=True, timeout=10)
        assert 'restricted to DEV' in result.stdout
        env['TEAM360_DEV_PROFILE'] = 'typo'
        result = subprocess.run(['bash', str(launcher)], env=env, capture_output=True, text=True, timeout=10)
        assert 'unknown TEAM360_DEV_PROFILE' in result.stdout


def test_bootstrap_import_is_lazy_and_isolated():
    code = f"""
import sys
from modules.messaging.dev_app import app
from modules.db.pool import get_pool
from modules.db.errors import DatabasePoolNotInitializedError
assert not any(n == p or n.startswith(p+'.') for n in sys.modules for p in {FORBIDDEN!r})
assert {{r.path for r in app.routes}} == {{'/health','/webhooks/messaging/evolution/whatsapp'}}
try:
    get_pool()
except DatabasePoolNotInitializedError:
    pass
else:
    raise AssertionError('pool opened at import')
print('isolated import OK')
"""
    env = dict(os.environ, PYTHONPATH=str(BACKEND))
    result = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert 'isolated import OK' in result.stdout


@pytest.mark.skipif(os.getenv('TEAM360_MESSAGING_POSTGRES_TEST') != '1', reason='requires PostgreSQL migration 026')
# @lat: [[team360-platform#Team360 Platform#WhatsApp transport boundary#Messaging-only DEV bootstrap tests]]
def test_launcher_starts_without_milvus_and_webhook_persists(launcher):
    suffix = uuid4().hex
    workspace = 'profile-test-' + suffix
    instance = 'profile-' + suffix
    repository = MessagingRepository()

    async def setup():
        pool = create_pool(get_database_settings(min_size=1,max_size=1))
        await open_pool(pool)
        try:
            async with transaction(pool) as conn:
                await conn.execute("INSERT INTO core_workspaces(slug,display_name) VALUES (%s,'Profile test')", (workspace,))
                return await repository.provision_dev_channel(conn, workspace_slug=workspace,
                    channel_alias='profile-test', provider='evolution', instance=instance)
        finally:
            await close_pool(pool)
    binding = asyncio.run(setup())
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        port = probe.getsockname()[1]
    env = dict(os.environ, TEAM360_DEV_PROFILE='messaging-only', TEAM360_ENV='development',
        TEAM360_BACKEND_HOST='127.0.0.1', TEAM360_BACKEND_PORT=str(port),
        TEAM360_MESSAGING_DEV_ENABLED='1', TEAM360_MESSAGING_WORKSPACE_SLUG=workspace,
        TEAM360_MESSAGING_CHANNEL_ALIAS='profile-test', TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER='15550000001',
        TEAM360_MESSAGING_WEBHOOK_TOKEN=TOKEN, TEAM360_EVOLUTION_INSTANCE=instance,
        TEAM360_EVOLUTION_BASE_URL='http://127.0.0.1:1', TEAM360_EVOLUTION_API_KEY='synthetic-key',
        TEAM360_MILVUS_HOST='127.0.0.1', TEAM360_MILVUS_PORT='1',
        TEAM360_LITELLM_BASE_URL='http://127.0.0.1:1', PYTHONPATH=str(BACKEND))
    process = None
    try:
        # Verify startup too, not merely the import path: no forbidden modules.
        code = f"""
import asyncio, sys
from modules.messaging.dev_app import app, startup, shutdown
async def check():
    await startup(app)
    assert not any(n == p or n.startswith(p+'.') for n in sys.modules for p in {FORBIDDEN!r})
    await shutdown(app)
asyncio.run(check())
print('isolated startup OK')
"""
        check = subprocess.run([sys.executable,'-c',code],cwd=BACKEND,env=env,capture_output=True,text=True,timeout=20)
        assert check.returncode == 0, check.stderr
        process = subprocess.Popen(['bash',str(launcher)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=2) as client:
            deadline = time.monotonic()+20
            while time.monotonic()<deadline:
                assert process.poll() is None, 'launcher exited before health'
                try:
                    response = client.get('/health')
                    if response.status_code == 200: break
                except httpx.HTTPError: pass
                time.sleep(.1)
            else: raise AssertionError('backend did not become ready')
            assert response.json() == {'status':'ok','profile':'messaging-only','postgres':'ok'}
            assert client.post('/api/diagnosis/start',json={}).status_code == 404
            assert client.get('/schema/openapi.json').status_code == 404
            payload = {'event':'messages.upsert','instance':instance,'data':{
                'key':{'id':'profile-inbound-'+suffix,'remoteJid':'15550000001@s.whatsapp.net','fromMe':False},
                'message':{'conversation':'hello profile'}}}
            headers={'x-team360-webhook-token':TOKEN}
            path='/webhooks/messaging/evolution/whatsapp'
            assert client.post(path,json=payload).status_code == 401
            assert client.post(path,json=payload,headers=headers).json()['results'] == {'received':1}
            assert client.post(path,json=payload,headers=headers).json()['results'] == {'duplicate':1}
        process.terminate(); output,_=process.communicate(timeout=10)
        assert 'messaging-only preflight' in output
        assert 'production-like services' not in output
        async def verify_and_cleanup():
            pool=create_pool(get_database_settings(min_size=1,max_size=1)); await open_pool(pool)
            try:
                async with transaction(pool) as conn:
                    rows=await repository.evidence(conn,binding)
                    assert len(rows)==1 and rows[0]['direction']=='inbound'
            finally: await close_pool(pool)
        asyncio.run(verify_and_cleanup())
    finally:
        if process is not None and process.poll() is None:
            process.terminate(); process.communicate(timeout=10)
        async def cleanup():
            pool=create_pool(get_database_settings(min_size=1,max_size=1)); await open_pool(pool)
            try:
                async with transaction(pool) as conn:
                    for table in ['message_events','message_threads','communication_channels']:
                        await conn.execute(f'DELETE FROM {table} WHERE workspace_id=%s',(binding.workspace_id,))
                    await conn.execute('DELETE FROM core_workspaces WHERE id=%s',(binding.workspace_id,))
            finally: await close_pool(pool)
        asyncio.run(cleanup())
