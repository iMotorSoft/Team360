"""Independent runtime contracts. Fixtures do NOT certify enterprise E2E."""
import asyncio
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import httpx
import pytest

from . import dev_app
from .test_console_http import headers, PAIR


def test_import_does_not_load_central_workers():
    code = '''
import sys
from modules.telchi.dev_app import app
for name in ('ls_iMotorSoft_Srv01', 'ls_iMotorSoft_Srv05', 'modules.module_registry',
             'modules.flow.scheduler', 'modules.messaging.routes'):
    assert name not in sys.modules, name
assert app.on_startup
'''
    subprocess.run([sys.executable, '-c', code], check=True, timeout=20)


@pytest.mark.parametrize('env,profile,enabled', [
    ('production', 'telchiai-only', '1'), ('dev', 'normal', '1'),
    ('dev', 'telchiai-only', '0'), ('', 'telchiai-only', '1'),
])
def test_explicit_dev_required(monkeypatch, env, profile, enabled):
    monkeypatch.setenv('TEAM360_ENV', env)
    monkeypatch.setenv('TEAM360_DEV_PROFILE', profile)
    monkeypatch.setenv('TEAM360_TELCHI_CONSOLE_ENABLED', enabled)
    with pytest.raises(ValueError):
        dev_app.validate_config()


@pytest.mark.parametrize('failure', ['none', 'open', 'runtime', 'dependencies'])
def test_pool_owned_and_closed_on_every_exit(monkeypatch, failure):
    events = []
    class Pool:
        async def wait(self, **kwargs):
            events.append('wait')
    pool = Pool()
    monkeypatch.setattr(dev_app, 'validate_config', lambda: {})
    monkeypatch.setattr(dev_app, 'create_pool', lambda settings: pool)
    async def opened(p):
        assert p is pool
        events.append('open')
        if failure == 'open':
            raise ValueError('PRIVATE DSN')
    async def closed(p):
        assert p is pool
        events.append('close')
    def runtime(config, *, pool):
        if failure == 'runtime':
            raise ValueError('PRIVATE config')
        return SimpleNamespace(service=SimpleNamespace(pool=pool))
    async def dependencies(runtime):
        events.append('dependencies')
        if failure == 'dependencies':
            raise ValueError('PRIVATE key')
        return 'foundation_fixture'
    monkeypatch.setattr(dev_app, 'open_pool', opened)
    monkeypatch.setattr(dev_app, 'close_pool', closed)
    monkeypatch.setattr(dev_app, 'ConsoleHTTPRuntime', runtime)
    monkeypatch.setattr(dev_app, 'validate_dependencies', dependencies)
    async def run():
        app = dev_app.create_app()
        if failure == 'none':
            await dev_app.startup(app)
            assert app.state.telchi_pool is pool
            assert app.state.telchi_publication == 'foundation_fixture'
        else:
            with pytest.raises(RuntimeError, match='startup blocked') as error:
                await dev_app.startup(app)
            assert 'PRIVATE' not in str(error.value)
        await dev_app.shutdown(app)
        await dev_app.shutdown(app)
    asyncio.run(run())
    assert events.count('open') == 1
    assert events.count('close') == 1


def test_accredited_reader_never_accepts_a_different_current(monkeypatch):
    from .console_http import AccreditedReader
    from .datalake.foundation_reader import FoundationReader
    monkeypatch.setattr(FoundationReader, '__init__', lambda self: None)
    monkeypatch.setattr(FoundationReader, 'resolve_on',
        lambda self, conn: SimpleNamespace(foundation_publication_id='foundation_current'))
    assert AccreditedReader('foundation_current').resolve_on(None).foundation_publication_id == 'foundation_current'
    with pytest.raises(ValueError, match='accredited_current_changed'):
        AccreditedReader('foundation_previous').resolve_on(None)


def test_missing_private_configuration_fails_before_pool_creation(monkeypatch):
    monkeypatch.setenv('TEAM360_ENV', 'dev')
    monkeypatch.setenv('TEAM360_DEV_PROFILE', 'telchiai-only')
    monkeypatch.setenv('TEAM360_TELCHI_CONSOLE_ENABLED', '1')
    monkeypatch.delenv('TEAM360_TELCHI_CONSOLE_CONFIG', raising=False)
    monkeypatch.setattr(dev_app, 'create_pool', lambda _: pytest.fail('unexpected pool'))
    with pytest.raises(RuntimeError, match='private configuration'):
        asyncio.run(dev_app.startup(dev_app.create_app()))


def test_provider_preflight_requests_json_explicitly(monkeypatch):
    from contextlib import asynccontextmanager
    from .exploratory_sql.research import LunaSQL

    @asynccontextmanager
    async def context():
        yield conn

    conn = SimpleNamespace(transaction=context)
    pool = SimpleNamespace(connection=context)
    async def permissions(conn, workspace):
        return frozenset()
    runtime = SimpleNamespace(service=SimpleNamespace(pool=pool, workspace='fixture',
        repository=SimpleNamespace(enabled_permissions=permissions),
        reader=SimpleNamespace(get_current_foundation=lambda:
            SimpleNamespace(foundation_publication_id='foundation_fixture'))))

    async def next_value(self, payload, *, timeout):
        # OpenAI json_object rejects input without the literal word json.
        assert 'json' in self.system.lower()
        assert self.max_output_tokens == 1024
        assert timeout == 45
        return {'ok': True}

    monkeypatch.setattr(LunaSQL, 'next', next_value)
    assert asyncio.run(dev_app.validate_dependencies(runtime)) == 'foundation_fixture'


# Test-owned processes with inert lifecycle and an explicitly fake research service.
# The actual Telchi handlers/auth/SSE and Srv05 composition run over TCP.
SERVER = '''
import asyncio, os, socket, uvicorn
from pathlib import Path
from types import SimpleNamespace
if os.environ['TEST_SERVICE'] == 'central':
    from ls_iMotorSoft_Srv05 import create_app
    app = create_app()
else:
    from modules.telchi.dev_app import create_app
    from modules.telchi.test_console_http import Service
    app = create_app()
    service = Service()
    service.keys = {os.environ['TEST_KEY_ID']: os.environ['TEST_PUBLIC_KEY']}
    original_ask = service.ask
    async def ask(value, question, save, *, progress, conversation_id):
        if question == 'fail':
            raise RuntimeError('PRIVATE failure')
        if question == 'wait':
            try:
                progress('waiting')
                await asyncio.sleep(60)
            finally:
                Path(os.environ['TEST_CANCELLED_FILE']).write_text('cancelled')
        return await original_ask(value, question, save, progress=progress,
                                  conversation_id=conversation_id)
    service.ask = ask
    app.state.telchi_console_runtime = SimpleNamespace(service=service, evidence_sink=lambda: lambda _: None)
app.on_startup.clear()
app.on_shutdown.clear()
sock = socket.socket(fileno=int(os.environ['TEST_SOCKET']))
uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False)).run(sockets=[sock])
'''


def start_owned(service, *, marker=''):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(64)
    port = sock.getsockname()[1]
    env = dict(os.environ, TEST_SERVICE=service, TEST_SOCKET=str(sock.fileno()),
        TEST_KEY_ID=PAIR.key_id, TEST_PUBLIC_KEY=PAIR.public_pem,
        TEST_CANCELLED_FILE=str(marker),
        TEAM360_ENV='dev', TEAM360_TELCHI_CONSOLE_ENABLED='1',
        TEAM360_SRV05_EVOLUTION_ENABLED='0', AUTOMATION_DIAGNOSIS_REPOSITORY='memory',
        TEAM360_AI_PROVIDER='mock', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    proc = subprocess.Popen([sys.executable, '-c', SERVER], env=env,
        pass_fds=(sock.fileno(),), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sock.close()
    try:
        url = f'http://127.0.0.1:{port}'
        path = '/health' if service == 'central' else '/api/telchiai/health'
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError('test server exited')
            try:
                if httpx.get(url + path, timeout=.5).status_code == 200:
                    return proc, url
            except httpx.TransportError:
                pass
            time.sleep(.05)
        raise RuntimeError('test server startup timeout')
    except BaseException:
        stop_owned(proc)
        raise


def stop_owned(proc):
    # Popen handle belongs to this test; never discover/kill by name or port.
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_independent_process_restart_preserves_srv05_pid():
    central, central_url = start_owned('central')
    telchi = None
    try:
        pid = central.pid
        telchi, url = start_owned('telchi')
        assert httpx.get(url + '/api/telchiai/session').status_code == 401
        for _ in range(2):
            response = httpx.post(url + '/api/telchiai/ask', headers=headers(),
                json={'question': 'ventas octubre',
                      'conversation_id': '12345678-1234-1234-1234-123456789abc'}, timeout=10)
            assert response.status_code == 200
            assert 'event: result' in response.text
            assert 'PRIVATE' not in response.text
            stop_owned(telchi)
            assert central.poll() is None and central.pid == pid
            assert httpx.get(central_url + '/health').status_code == 200
            assert httpx.get(central_url + '/api/telchiai/session').status_code == 404
            telchi, url = start_owned('telchi')
    finally:
        if telchi is not None:
            stop_owned(telchi)
        stop_owned(central)
    assert central.poll() is not None and telchi.poll() is not None


def test_sse_disconnect_cancels_task_and_allows_retry(tmp_path):
    marker = tmp_path / 'cancelled'
    proc, url = start_owned('telchi', marker=marker)
    body = {'question': 'wait', 'conversation_id': '12345678-1234-1234-1234-123456789abc'}
    try:
        with httpx.stream('POST', url + '/api/telchiai/ask', headers=headers(),
                          json=body, timeout=5) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line == 'event: progress':
                    break
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert marker.read_text() == 'cancelled'
        body['question'] = 'fail'
        failed = httpx.post(url + '/api/telchiai/ask', headers=headers(), json=body)
        assert 'event: error' in failed.text and 'PRIVATE' not in failed.text
        body['question'] = 'retry'
        assert 'event: result' in httpx.post(url + '/api/telchiai/ask',
            headers=headers(), json=body).text
    finally:
        stop_owned(proc)


def test_launcher_refuses_occupied_port_without_reclaiming_it(tmp_path):
    # Copy only the launcher so a developer's local override file is never sourced.
    launcher = Path(__file__).resolve().parents[3] / 'backend-dev.sh'
    isolated = tmp_path / 'backend-dev.sh'
    isolated.write_bytes(launcher.read_bytes())
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        env = dict(os.environ, TEAM360_DEV_PROFILE='telchiai-only', TEAM360_ENV='dev',
            TEAM360_TELCHIAI_PORT=str(port), TEAM360_BACKEND_HOST='127.0.0.1')
        result = subprocess.run(['bash', str(isolated)], env=env, capture_output=True,
                                text=True, timeout=10)
        assert result.returncode != 0
        assert 'occupied; no existing process will be terminated' in result.stdout
        assert listener.getsockname()[1] == port


def test_new_prefix_and_legacy_alias(client):
    # Reuse the HTTP fixture; it has no external dependencies.
    http, _ = client
    assert http.get('/api/telchiai/session', headers=headers()).status_code == 200
    assert http.get('/api/telchi/luna/session', headers=headers()).status_code == 200


# Import explicitly so pytest can supply the shared fixture.
from .test_console_http import client  # noqa: E402,F401
