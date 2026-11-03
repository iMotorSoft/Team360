"""Offline startup failures: synthetic children/apps only; no horizontal services."""
import errno
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant import whatsapp_dev_diagnostics as diag
from modules.telchi.assistant import whatsapp_dev_lifecycle as control

SECRET = 'fixture-only-sensitive-92342'


@pytest.mark.parametrize('exc,stage,category', [
    (ImportError(SECRET), 'configuration', 'import_error'),
    (RuntimeError(SECRET), 'asgi_lifespan', 'lifespan_failure'),
    (OSError(errno.EADDRINUSE, SECRET), 'port_check', 'port_conflict'),
    (TimeoutError(SECRET), 'backend_readiness', 'timeout'),
    (RuntimeError('owned_backend_exited'), 'backend_readiness', 'premature_exit'),
    (ValueError(SECRET), 'configuration', 'configuration_failure'),
])
def test_sanitized_original(exc, stage, category):
    try:
        raise exc
    except Exception as caught:
        value = diag.incident(caught, stage)
    assert value['category'] == category
    assert value['exception_type'] == type(exc).__name__
    assert value['frames'] and value['stage'] == stage
    assert SECRET not in json.dumps(value)


@pytest.mark.parametrize('failure', ['import', 'lifespan', 'port', 'timeout', 'exit', 'success'])
def test_start_closure_and_original(tmp_path, monkeypatch, failure):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    approval = tmp_path/'approval.json'
    dev.save_private(approval, {})
    settings = SimpleNamespace(webhook_token=SECRET)
    srv = SimpleNamespace(evolution=SimpleNamespace(instance='offline'))
    monkeypatch.setattr(dev, 'preflight', lambda _: ({}, srv, settings, None))
    monkeypatch.setattr(dev, 'gate_evidence', lambda _: None)
    monkeypatch.setattr(dev, 'read_approval', lambda _: {})
    monkeypatch.setattr(dev.signal, 'signal', lambda *a: None)
    def sleep(seconds):
        if failure == 'success' and seconds == .5:
            raise KeyboardInterrupt  # operator closes after READY
    monkeypatch.setattr(dev.time, 'sleep', sleep)
    args = SimpleNamespace(approval=approval, output=str(tmp_path/'session'),
                           duration=60, host='192.0.2.1', port=18181, container='offline')
    previous = dev.webhook_body(dict(url='http://offline.invalid/previous'))
    state = [previous]
    posts = []
    def api(client, method, path, body=None):
        if method == 'POST':
            posts.append(body)
            state[0] = body['webhook']
        return state[0]
    monkeypatch.setattr(dev, 'api', api)
    class Client:
        def __init__(self, *a, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def get(self, path):
            return SimpleNamespace(status_code=503 if failure == 'timeout' else 200,
                                   headers={'x-team360-session': 'n'*64})
    monkeypatch.setattr(dev, 'client_for', lambda _: Client())
    monkeypatch.setattr(dev.httpx, 'Client', Client)
    class Socket(Client):
        def bind(self, address):
            if failure == 'port':
                raise OSError(errno.EADDRINUSE, SECRET)
    monkeypatch.setattr(dev.socket, 'socket', Socket)
    import secrets
    monkeypatch.setattr(secrets, 'token_hex', lambda _: 'n'*64)
    children = []
    class Child:
        pid = os.getpid()
        stopped = False
        def poll(self):
            return 1 if failure in {'import', 'lifespan', 'exit'} or self.stopped else None
        def terminate(self):
            self.stopped = True
        def wait(self, timeout):
            assert self.stopped
    def popen(*a, **kw):
        child = Child()
        children.append(child)
        if failure in {'import', 'lifespan'}:
            recorder = diag.ChildDiagnostics(Path(args.output)/'backend-diagnostics.json')
            recorder.advance('backend_import' if failure == 'import' else 'asgi_lifespan')
            recorder.capture(ImportError(SECRET) if failure == 'import' else ValueError(SECRET))
        return child
    monkeypatch.setattr(dev.subprocess, 'Popen', popen)
    monkeypatch.setattr(control, 'wait_backend_identity', lambda *a: control.identity(os.getpid()))
    def probe(*a):
        if failure == 'success':
            return
        pytest.fail('failed backend must never reach container probe')
    monkeypatch.setattr(dev, 'container_probe', probe)
    expected = OSError if failure == 'port' else KeyboardInterrupt if failure == 'success' else RuntimeError
    with pytest.raises(expected):
        dev.start(args)
    record = control.read_json(control.root()/'current.json')
    assert record['state'] == 'STOPPED'
    assert record['backend_stopped']
    assert record.get('webhook_restored') or record.get('webhook_untouched')
    assert len(posts) == (2 if failure == 'success' else 0)
    assert state[0] == previous
    if failure == 'success':
        assert record['ready_at'] and record['startup_stage'] == 'ready'
    assert all(c.poll() is not None for c in children)
    assert SECRET not in json.dumps(record)
    assert record['startup_stage']
    assert record['diagnostic_logs']['backend'].endswith('backend.log')
    if failure != 'success':
        category = {'import': 'import_error', 'lifespan': 'lifespan_failure',
                    'port': 'port_conflict', 'timeout': 'timeout', 'exit': 'premature_exit'}[failure]
        assert record['original_error']['category'] == category
    if failure != 'port':
        closure = control.read_json(Path(args.output)/'closure.json')
        assert closure['original_error'] == record['original_error']
        assert closure['status'] == 'CLOSED'


@pytest.mark.parametrize('mode', ['import', 'lifespan_exception', 'lifespan_failed', 'port', 'success'])
def test_real_uvicorn_child_offline(tmp_path, mode):
    """Real owned subprocess + Uvicorn; no Team360 runtime or provider imported."""
    tmp_path.chmod(0o700)
    output = tmp_path/'backend-diagnostics.json'
    # This test owns the reservation; nobody else's process is signalled.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
        if mode == 'port':
            reservation.listen()
        else:
            reservation.close()
        code = '''
import os
from pathlib import Path
from types import SimpleNamespace
from modules.telchi.assistant import whatsapp_dev as dev
from modules.telchi.assistant.whatsapp_dev_diagnostics import serve
root, mode, port = __import__('sys').argv[1:]
dev.PRIVATE_ROOT = Path(root)
async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        await receive()
        if mode == 'lifespan_exception':
            raise ValueError('password=fixture-only-sensitive-92342')
        if mode == 'lifespan_failed':
            await send({'type':'lifespan.startup.failed', 'message':'Authorization: fixture-only-sensitive-92342'})
            return
        await send({'type':'lifespan.startup.complete'})
        await receive()
        await send({'type':'lifespan.shutdown.complete'})
def factory(diagnostics):
    if mode == 'import':
        raise ModuleNotFoundError('postgresql://user:fixture-only-sensitive-92342@localhost/db')
    return app
serve(SimpleNamespace(diagnostics=Path(root)/'backend-diagnostics.json', host='127.0.0.1', port=int(port)), factory)
'''
        process = subprocess.Popen([sys.executable, '-c', code, str(tmp_path), mode, str(port)],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        logpath = tmp_path/'backend.log'
        try:
            with open(logpath, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as log:
                worker = diag.capture_output(process, log)
                import time
                deadline = time.monotonic()+10
                if mode == 'success':
                    while time.monotonic() < deadline:
                        if output.exists() and json.loads(output.read_text())['stage'] == 'backend_listening':
                            break
                        time.sleep(.02)
                    else:
                        pytest.fail('synthetic app never started')
                    assert process.poll() is None
                    process.terminate()
                process.wait(timeout=10)
                worker.join(timeout=5)
                assert not worker.is_alive()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        record = json.loads(output.read_text())
        if mode == 'success':
            assert record['original_error'] is None
        else:
            expected = 'import_error' if mode == 'import' else 'port_conflict' if mode == 'port' else 'lifespan_failure'
            assert record['original_error']['category'] == expected
            if mode == 'lifespan_exception':
                assert record['original_error']['exception_type'] == 'ValueError'
        assert SECRET not in output.read_text()+logpath.read_text()
        assert output.stat().st_mode & 0o077 == 0
        assert logpath.stat().st_mode & 0o077 == 0
        assert process.poll() is not None
        if mode == 'port':
            assert reservation.fileno() != -1  # foreign-to-launcher listener preserved


def test_error_log_and_cleanup_preserve_first(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    recorder = diag.ChildDiagnostics(tmp_path/'backend-diagnostics.json')
    recorder.advance('asgi_lifespan')
    handler = diag.SafeErrorHandler(recorder)
    try:
        raise LookupError(SECRET)
    except LookupError:
        record = logging.LogRecord('uvicorn.error', logging.ERROR, __file__, 1,
                                   'Authorization: '+SECRET, (), sys.exc_info())
        handler.emit(record)
    recorder.advance('shutdown')
    recorder.capture(RuntimeError('cleanup '+SECRET))
    result = json.loads(recorder.path.read_text())
    assert result['original_error']['exception_type'] == 'LookupError'
    assert result['original_error']['stage'] == 'asgi_lifespan'
    assert SECRET not in recorder.path.read_text()


def test_preinstrumentation_import_error_is_recoverable(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(dev, 'PRIVATE_ROOT', tmp_path)
    class Session:
        def publish(self, **values):
            self.value.update(values)
        value = {}
    session = Session()
    recorder = diag.Diagnostics(session, tmp_path)
    child = subprocess.Popen([sys.executable, '-c',
                              "raise ModuleNotFoundError('password="+SECRET+"')"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with (tmp_path/'backend.log').open('w') as log:
        worker = diag.capture_output(child, log)
        child.wait(timeout=5)
        worker.join(timeout=5)
    recorder.capture(RuntimeError('owned_backend_exited'))
    assert recorder.original['exception_type'] == 'ModuleNotFoundError'
    assert recorder.original['category'] == 'import_error'
    assert SECRET not in json.dumps(session.value)
    assert SECRET not in (tmp_path/'backend.log').read_text()


def test_raw_child_output_is_never_saved(tmp_path):
    child = subprocess.Popen([sys.executable, '-c',
                              f"import sys; print({SECRET!r}); sys.stderr.write('Authorization: '+{SECRET!r})"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with (tmp_path/'redacted.log').open('w') as log:
        worker = diag.capture_output(child, log)
        child.wait(timeout=5)
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert SECRET not in (tmp_path/'redacted.log').read_text()
    assert 'backend_output_redacted' in (tmp_path/'redacted.log').read_text()
