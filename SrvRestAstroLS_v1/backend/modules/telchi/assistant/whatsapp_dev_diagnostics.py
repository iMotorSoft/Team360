"""DEV-only, local structured diagnostics. Free-form text is NEVER persisted.

Descriptions are an allowlist, not regex-based secret removal. Exception frames
contain code coordinates only (no source lines, locals, arguments or payloads).
"""
from __future__ import annotations

import errno
import json
import logging
import re
from pathlib import Path
import threading


def incident(exc, stage, depth=0):
    category = 'startup_error'
    if isinstance(exc, ImportError):
        category = 'import_error'
    elif isinstance(exc, OSError) and exc.errno == errno.EADDRINUSE:
        category = 'port_conflict'
    elif isinstance(exc, TimeoutError) or str(exc) == 'owned_backend_startup_timeout':
        category = 'timeout'
    elif str(exc) in {'owned_backend_exited', 'owned_backend_exec_identity_unavailable'}:
        category = 'premature_exit'
    elif stage == 'asgi_lifespan':
        category = 'lifespan_failure'
    elif stage in {'configuration', 'preflight', 'gate_validation'}:
        category = 'configuration_failure'
    # Names/paths supplied by third-party exceptions are untrusted too. Only
    # coordinates relative to installed source, without arbitrary filenames.
    frames = []
    tb = exc.__traceback__
    while tb:
        code = tb.tb_frame.f_code
        module = tb.tb_frame.f_globals.get('__name__', '')
        frames.append({'line': tb.tb_lineno,
                       'module': module if all(part.isidentifier() for part in module.split('.')) else '<module>',
                       'function': code.co_name if code.co_name.isidentifier() else '<code>'})
        tb = tb.tb_next
    kind = type(exc).__name__
    # Retain only explicitly reviewed diagnostic codes; arbitrary exception
    # messages can be SQL, customer text or provider responses, so omit them.
    codes = {'owned_backend_exited', 'owned_backend_startup_timeout',
             'owned_backend_exec_identity_unavailable', 'isolated_DEV_configuration_required',
             'gate_scope_mismatch', 'DEV_gate_policy_scope_mismatch', 'gates_expired',
             'gate_artifact_changed', 'six_gates_required', 'real_gate_required',
             'active_webhook_preserved', 'approval_changed_during_startup',
             'container_webhook_auth_or_reachability_failed', 'Evolution_request_failed',
             'webhook_changed_during_preflight', 'temporary_webhook_not_verified'}
    description = str(exc) if str(exc) in codes else category
    cause = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return dict(category=category, stage=stage,
                exception_type=kind if kind.isidentifier() else 'Exception',
                description=description, errno=getattr(exc, 'errno', None)
                if isinstance(exc, OSError) else None, frames=frames,
                cause=incident(cause, stage, depth+1) if cause and depth < 3 else None)


def write_record(path, value):
    # Atomic private files; caller's session directory is validated separately.
    from .whatsapp_dev_lifecycle import atomic
    atomic(path, value)


class Diagnostics:
    def __init__(self, session, output):
        self.session = session
        self.output = Path(output)
        self.stage = 'preflight'
        self.original = None
        self.advance('preflight')

    def advance(self, stage):
        self.stage = stage
        self.session.publish(startup_stage=stage, diagnostic_logs={
            'backend': str(self.output / 'backend.log'),
            'backend_diagnostics': str(self.output / 'backend-diagnostics.json'),
            'closure': str(self.output / 'closure.json')})

    def capture(self, exc):
        if self.original is not None:
            return
        # Child structured evidence is more specific than the parent's exit error.
        from .whatsapp_dev_lifecycle import read_json
        try:
            child = read_json(self.output / 'backend-diagnostics.json')
        except (OSError, ValueError):
            child = {}
        self.original = child.get('original_error')
        if self.original is None:
            try:
                # This file contains only our structured allowlisted events.
                with (self.output / 'backend.log').open() as stream:
                    for line in stream:
                        event = json.loads(line)
                        if event.get('exception_type') in {'ImportError', 'ModuleNotFoundError'}:
                            self.original = dict(category='import_error', stage='backend_import',
                                exception_type=event['exception_type'], description='import_error',
                                evidence='backend_output_signature', frames=[])
                            break
            except (OSError, ValueError):
                pass
        self.original = self.original or incident(exc, self.stage)
        self.session.publish(original_error=self.original, backend_stage=child.get('stage'))


class ChildDiagnostics:
    def __init__(self, path):
        self.path = Path(path)
        self.stage = 'backend_import'
        self.original = None
        self.advance(self.stage)

    def advance(self, stage):
        self.stage = stage
        self.save()

    def save(self):
        write_record(self.path, dict(stage=self.stage, original_error=self.original))

    def capture(self, exc):
        if self.original is None:
            self.original = incident(exc, self.stage)
            self.save()

    def event(self, category):
        if self.original is None:
            # A protocol failure/log line is evidence, not a Python exception.
            self.original = dict(category=category, stage=self.stage,
                                 exception_type=None, description=category,
                                 evidence='asgi_or_uvicorn_error', frames=[])
            self.save()


class LifespanDiagnostics:
    def __init__(self, app, diagnostics):
        self.app, self.diagnostics = app, diagnostics

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'lifespan':
            return await self.app(scope, receive, send)
        self.diagnostics.advance('asgi_lifespan')
        async def observed(message):
            if message['type'] == 'lifespan.startup.failed':
                # ASGI failure strings may contain arbitrary application data.
                self.diagnostics.event('lifespan_failure')
            elif message['type'] == 'lifespan.startup.complete':
                self.diagnostics.advance('backend_listening')
            await send(message)
        try:
            return await self.app(scope, receive, observed)
        except BaseException as exc:
            self.diagnostics.capture(exc)
            raise


class SafeErrorHandler(logging.Handler):
    def __init__(self, diagnostics):
        super().__init__(logging.ERROR)
        self.diagnostics = diagnostics

    def emit(self, record):
        if record.exc_info and record.exc_info[1]:
            self.diagnostics.capture(record.exc_info[1])
        else:
            # Uvicorn may log a bind error without exc_info.
            text = record.getMessage()
            if 'address already in use' in text.lower() or '10048' in text:
                self.diagnostics.capture(OSError(errno.EADDRINUSE, 'port_conflict'))
            else:
                self.diagnostics.event('lifespan_failure' if self.diagnostics.stage == 'asgi_lifespan'
                                       else 'uvicorn_error')


def capture_output(process, log):
    """Drain only our child's pipe. Never write untrusted output to disk."""
    pipe = getattr(process, 'stdout', None)
    if pipe is None:
        return None
    def drain():
        try:
            # Bounded reads, even if a library prints a huge payload without LF.
            while chunk := pipe.read(4096):
                text = chunk.decode('utf-8', errors='replace').lower()
                category = ('port_conflict' if 'address already in use' in text else
                            'import_error' if 'modulenotfounderror' in text or 'importerror' in text else
                            'lifespan_failure' if 'application startup failed' in text else
                            'backend_output_redacted')
                match = re.search(r'(?m)^(ModuleNotFoundError|ImportError):',
                                  chunk.decode('utf-8', errors='replace'))
                log.write(json.dumps({'event': category,
                                      'exception_type': match.group(1) if match else None}) + '\n')
                log.flush()
        finally:
            pipe.close()
    worker = threading.Thread(target=drain, name='telchiai-dev-log', daemon=True)
    worker.start()
    return worker


def serve(args, factory):
    diagnostics = ChildDiagnostics(args.diagnostics)
    handler = SafeErrorHandler(diagnostics)
    # No default formatter can print raw exception text or ASGI failure messages.
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.ERROR)
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.ERROR)
    try:
        import uvicorn
        diagnostics.advance('configuration')
        app = factory(diagnostics)
        diagnostics.advance('uvicorn_start')
        uvicorn.run(LifespanDiagnostics(app, diagnostics), host=args.host,
                    port=args.port, workers=1, access_log=False,
                    log_level='error', log_config=None, lifespan='on')
        if diagnostics.stage != 'backend_listening' and diagnostics.original is None:
            diagnostics.capture(RuntimeError('owned_backend_exited'))
    except BaseException as exc:
        diagnostics.capture(exc)
        raise
