"""Manual, bounded DEV Srv05 + TelchiAI + Evolution session. Never sends a probe.

preflight: read-only DB and Evolution GETs, no listener/webhook/model calls.
start: explicit operator action; private backup before webhook mutation.
restore: explicit recovery after hard interruption; refuses foreign configuration.

The session closes when it is idle for a configurable period or when it
reaches its maximum duration, never while a turn is in flight. The activity
and the reason of the closure are recorded in the private session state.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

import httpx

PRIVATE_ROOT = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi')
MODULE = 'modules.telchi.assistant.whatsapp_dev'
WEBHOOK = '/webhooks/messaging/evolution/whatsapp'
GATES = {'http_auth', 'identity_tenant_isolation', 'business_authorization',
         'durable_idempotency', 'assistant_foundation', 'model_no_fallback'}
DEFAULT_IDLE_TIMEOUT = 900
DEFAULT_MAX_DURATION = 14400
MIN_IDLE_TIMEOUT = 60
MAX_IDLE_TIMEOUT = 3600
MIN_MAX_DURATION = 60
MAX_MAX_DURATION = 86400


def private_file(path):
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to(PRIVATE_ROOT) or path.stat().st_mode & 0o077:
        raise ValueError('private_file_required')
    return path


def read_approval(path):
    approval = json.loads(private_file(path).read_text())
    if (approval.get('environment') != 'dev' or approval.get('tenant_id') != 'telchi'
            or approval.get('access') != 'assistant'
            or approval.get('revoked') is not False
            or 'permission' in approval or 'expires_at' in approval
            or not approval.get('issued_at')
            or approval.get('module_enabled') is not True
            or approval.get('whole_workspace_scope_verified') is not True
            or not approval.get('approved_by') or not approval.get('user_id')
            or not approval.get('workspace_id')):
        raise PermissionError('explicit_pilot_access_required')
    issued = datetime.fromisoformat(approval['issued_at'])
    if issued.tzinfo is None or issued > datetime.now(timezone.utc):
        raise PermissionError('invalid_approval_issue_time')
    sender = approval.get('sender_sha256', '')
    if len(sender) != 64 or any(c not in '0123456789abcdef' for c in sender):
        raise PermissionError('verified_sender_hash_required')
    # Pin the owner's evidence, not just an unsubstantiated enable flag.
    evidence = private_file(approval['business_evidence_file'])
    if hashlib.sha256(evidence.read_bytes()).hexdigest() != approval['business_evidence_sha256']:
        raise PermissionError('business_evidence_changed')
    return approval


DEV_GATE_POLICY = 'change_based_v1'


def configuration_digest():
    """Trusted operator environment only; never ingress fields. Do not expose secrets."""
    from .whatsapp_dev_lifecycle import CONFIG_ENV
    values = {key: os.environ.get(key) for key in sorted(CONFIG_ENV)}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def gate_evidence(approval):
    """Missing/live-unproven gates block activation; doubles never count as real."""
    evidence = json.loads(private_file(approval['gates_file']).read_text())
    if (evidence.get('workspace_id') != approval['workspace_id']
            or evidence.get('user_id') != approval['user_id']
            or evidence.get('instance') != 'team360-meta-dev'
            or evidence.get('approval_sha256') != approval_digest(approval)
            or evidence.get('source_sha256') != source_digest()):
        raise ValueError('gate_scope_mismatch')
    if 'validity_policy' in evidence or 'schema_version' in evidence:
        if (os.getenv('TEAM360_ENV', '').strip().lower() not in {'dev', 'development'}
                or approval.get('environment') != 'dev'
                or evidence.get('environment') != 'dev'
                or evidence.get('schema_version') != 2
                or evidence.get('validity_policy') != DEV_GATE_POLICY
                or 'expires_at' in evidence
                or evidence.get('configuration_sha256') != configuration_digest()):
            raise ValueError('DEV_gate_policy_scope_mismatch')
        issued = datetime.fromisoformat(evidence['issued_at'])
        if issued.tzinfo is None or issued > datetime.now(timezone.utc):
            raise ValueError('invalid_gate_issue_time')
        if set(evidence.get('gates', {})) != GATES:
            raise ValueError('six_gates_required')
        expires = None
    else:
        # Legacy admission is unchanged, including its expiration in production.
        expires = datetime.fromisoformat(evidence['expires_at'])
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise ValueError('gates_expired')
    for name in GATES:
        gate = evidence.get('gates', {}).get(name, {})
        if gate.get('status') != 'PASS' or gate.get('kind') != 'real':
            raise ValueError('real_gate_required')
        artifact = private_file(gate['artifact'])
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != gate['sha256']:
            raise ValueError('gate_artifact_changed')
        if expires is None:
            report = json.loads(artifact.read_text())
            observations = gate.get('observations')
            if (report.get('status') != 'PASS' or not isinstance(observations, list)
                    or not observations or any(
                        report.get('observations', {}).get(item, {}).get('status') != 'PASS'
                        for item in observations)):
                raise ValueError('incomplete_gate_evidence')
    return expires


def approval_digest(approval):
    return hashlib.sha256(json.dumps(approval, sort_keys=True).encode()).hexdigest()


def source_digest():
    """Invalidate gate attestations when their runtime implementation changes."""
    backend = Path(__file__).resolve().parents[3]
    paths = {backend/'ls_iMotorSoft_Srv05.py', backend/'ls_iMotorSoft_Srv01.py',
             backend/'modules/srv05_settings.py'}
    for root in ('telchi/assistant', 'telchi/datalake', 'messaging', 'console', 'db'):
        paths.update((backend/'modules'/root).rglob('*.py'))
        # Contracts and declarative configuration are part of the accreditation.
        for pattern in ('*.md', '*.json', '*.sql'):
            paths.update((backend/'modules'/root).rglob(pattern))
    paths.update((backend/'db/migrations').glob('*.sql'))
    paths.update({backend/'pyproject.toml', backend/'uv.lock'})
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(backend)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def configuration():
    from modules.messaging.settings import MessagingDevSettings
    from modules.srv05_settings import Srv05Settings
    srv = Srv05Settings.from_env()
    settings = MessagingDevSettings.from_env()
    if (not srv.evolution_enabled or settings.dispatch_mode != 'horizontal_v1'
            or settings.workspace_slug != 'telchi_dev' or settings.channel_alias != 'telchi_whatsapp_dev'
            or srv.evolution.instance != 'team360-meta-dev'
            or not settings.authorized_sender.isdigit() or not 7 <= len(settings.authorized_sender) <= 15
            or not srv.recipient or os.getenv('TEAM360_DEV_PROFILE')
            or os.getenv('TEAM360_TELCHI_ASSISTANT_DEV_HTTP') == '1'
            or os.getenv('TEAM360_BUSINESS_SEMANTICS') == '1'):
        raise ValueError('isolated_DEV_configuration_required')
    if urlparse(srv.evolution.base_url).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('local_Evolution_required')
    return srv, settings


async def check_database(approval, settings, evolution):
    import psycopg
    from psycopg.rows import dict_row
    from modules.console.login_cli import local_dsn
    from modules.db.settings import get_database_settings
    from .whatsapp_dev_repository import check_session
    dsn = get_database_settings().dsn
    local_dsn(dsn)
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row, connect_timeout=5,
            options='-c statement_timeout=5000 -c lock_timeout=3000') as conn:
        async with conn.transaction():
            await conn.execute('SET TRANSACTION READ ONLY')
            binding = await check_session(conn, settings, evolution, approval)
            if binding.receiver_context != os.getenv('META_TEAM360_PHONE_NUMBER_ID', '').strip():
                raise PermissionError('receiver_mismatch')
            return binding


async def inspect_exchange(approval_path, inbound_id):
    import uuid
    import psycopg
    from psycopg.rows import dict_row
    from modules.console.login_cli import local_dsn
    from modules.db.settings import get_database_settings
    from .repository import ConversationRepository
    from .whatsapp_dev_repository import check_session
    from .whatsapp_dev_evidence import evaluate
    approval = read_approval(approval_path)
    srv, settings = configuration()
    inbound_id = str(uuid.UUID(inbound_id))
    dsn = get_database_settings().dsn
    local_dsn(dsn)
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row, connect_timeout=5,
            options='-c statement_timeout=5000 -c lock_timeout=3000') as conn:
        async with conn.transaction():
            await conn.execute('SET TRANSACTION READ ONLY')
            binding = await check_session(conn, settings, srv.evolution, approval)
            rows = await ConversationRepository().controlled_transport_evidence(conn, binding, [inbound_id])
            return evaluate(rows, binding, approval, inbound_id)


def client_for(config):
    management_key = (os.environ['TEAM360_EVOLUTION_MANAGEMENT_API_KEY']
                      if os.getenv('TEAM360_TRANSPORT_V1_CONFIG') else config.api_key)
    return httpx.Client(base_url=config.base_url, headers={'apikey': management_key},
                        timeout=10, trust_env=False, follow_redirects=False)


def api(client, method, path, body=None):
    response = client.request(method, path, json=body)
    if response.status_code not in {200, 201}:
        raise RuntimeError('Evolution_request_failed')
    return response.json()


def webhook_body(value):
    """Canonical documented Evolution fields. Refuse unknown configuration loss."""
    value = value or {}
    known = {'id', 'createdAt', 'updatedAt', 'instanceId', 'enabled', 'url', 'events',
             'headers', 'webhookByEvents', 'webhookBase64', 'byEvents', 'base64'}
    if not isinstance(value, dict) or set(value) - known:
        raise ValueError('unrecognized_webhook_configuration')
    return dict(enabled=bool(value.get('enabled')), url=value.get('url') or '',
                events=value.get('events') or [], headers=value.get('headers') or {},
                byEvents=bool(value.get('webhookByEvents', value.get('byEvents', False))),
                base64=bool(value.get('webhookBase64', value.get('base64', False))))


def preflight(approval_path, *, require_gates=True):
    approval = read_approval(approval_path)
    srv, settings = configuration()
    if hashlib.sha256(settings.authorized_sender.encode()).hexdigest() != approval.get('sender_sha256'):
        raise PermissionError('approved_pilot_line_mismatch')
    binding = asyncio.run(check_database(approval, settings, srv.evolution))
    with client_for(srv.evolution) as client:
        if api(client, 'GET', '/instance/connectionState/'+srv.evolution.instance).get('instance', {}).get('state') != 'open':
            raise ValueError('Evolution_not_open')
        previous = webhook_body(api(client, 'GET', '/webhook/find/'+srv.evolution.instance))
        if previous['enabled']:
            raise ValueError('active_webhook_preserved_session_blocked')
        if not previous['url']:
            raise ValueError('restorable_previous_webhook_required')
    if require_gates:
        gate_evidence(approval)
    return approval, srv, settings, binding


def unchanged_approval(path, expected):
    """Fail closed on explicit revocation, deletion, tampering or scope replacement."""
    if read_approval(path) != expected:
        raise PermissionError('pilot_access_changed')


class ActivityMarker:
    """A verifiable, secret-free record of the activity of the owned session.

    Only a timestamp, a counter of turns and the number of turns in flight are
    written: never a message, a phone number, a credential or a business value.
    """

    def __init__(self, path):
        self.path = Path(path) if path else None
        self.lock = threading.Lock()
        self.state = dict(last_activity=None, in_flight=0, turns=0)

    def enter(self):
        with self.lock:
            self.state['in_flight'] += 1
            self.state['turns'] += 1
            self.state['last_activity'] = datetime.now(timezone.utc).isoformat()
            self._write()

    def leave(self):
        with self.lock:
            self.state['in_flight'] = max(0, self.state['in_flight'] - 1)
            self._write()

    def _write(self):
        if self.path is None:
            return
        temporary = self.path.with_name(self.path.name + '.tmp')
        try:
            fd = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(self.state, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            # The activity record is evidence, never a reason to stop a turn.
            pass


def session_close_reason(*, elapsed, idle_elapsed, in_flight, max_duration, idle_timeout,
                         gates_expired=False):
    """Why the owned session closes, or None while it must stay open.

    A turn in flight is never interrupted: the idle timeout only closes a
    session that is genuinely waiting for the operator.
    """
    if elapsed >= max_duration:
        return 'max_duration_reached'
    if gates_expired:
        return 'gate_evidence_expired'
    if idle_timeout and idle_elapsed >= idle_timeout and not in_flight:
        return 'idle_timeout_reached'
    return None


def session_timing(args):
    """The idle timeout and the maximum duration of the owned session.

    The legacy ``--duration`` remains as an alias of the maximum duration.
    """
    idle = getattr(args, 'idle_timeout', None)
    total = getattr(args, 'max_duration', None)
    legacy = getattr(args, 'duration', None)
    if total is None:
        total = legacy if legacy is not None else DEFAULT_MAX_DURATION
    if idle is None:
        idle = min(DEFAULT_IDLE_TIMEOUT, total)
    if type(idle) is not int or not MIN_IDLE_TIMEOUT <= idle <= MAX_IDLE_TIMEOUT:
        raise ValueError('idle_timeout_out_of_range')
    if type(total) is not int or not MIN_MAX_DURATION <= total <= MAX_MAX_DURATION:
        raise ValueError('max_duration_out_of_range')
    if idle > total:
        raise ValueError('idle_timeout_exceeds_max_duration')
    return idle, total


def read_activity(path):
    """The last recorded activity, or None when it cannot be read."""
    try:
        with open(path) as stream:
            value = json.load(stream)
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def session_policy(control_path, idle_timeout, max_duration):
    """Re-read the private control to extend a running session.

    Only the timing keys are read: the environment is never touched and
    nothing is printed.
    """
    if not control_path:
        return idle_timeout, max_duration
    try:
        from .whatsapp_dev_lifecycle import read_json
        config = read_json(Path(control_path))
    except (OSError, ValueError, KeyError):
        return idle_timeout, max_duration
    if not isinstance(config, dict):
        return idle_timeout, max_duration
    idle = config.get('idle_timeout', idle_timeout)
    total = config.get('max_duration', max_duration)
    if type(idle) is not int or not MIN_IDLE_TIMEOUT <= idle <= MAX_IDLE_TIMEOUT:
        idle = idle_timeout
    if type(total) is not int or not MIN_MAX_DURATION <= total <= MAX_MAX_DURATION:
        total = max_duration
    return idle, total


class PilotBoundary:
    """Transport restriction only. Srv05 still resolves identity and business RBAC.

    Authenticate before body decoding; reject other pilot senders before any
    persistence/provider call. Reuse Evolution normalization, not conversation.
    """
    def __init__(self, app, settings, config, recipient, access_check=None, activity=None, health_check=None):
        self.app, self.settings, self.config, self.recipient = app, settings, config, recipient
        self.access_check = access_check
        self.activity = activity
        self.health_check = health_check

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        async def answer(code):
            await send({'type': 'http.response.start', 'status': code, 'headers': [
                (b'x-team360-session', os.getenv('TEAM360_TELCHI_WHATSAPP_NONCE', '').encode())]})
            await send({'type': 'http.response.body', 'body': b''})
        if scope['path'] == '/health' and scope['method'] == 'GET':
            return await answer(200 if self.health_check is None or self.health_check() else 503)
        if scope['path'] != WEBHOOK or scope['method'] != 'POST':
            return await answer(404)
        headers = dict(scope['headers'])
        if not hmac.compare_digest(headers.get(b'x-team360-webhook-token', b''), self.settings.webhook_token.encode()):
            return await answer(401)
        if self.access_check is not None:
            try:
                self.access_check()
            except Exception:
                return await answer(403)
        data = b''
        while True:
            item = await receive()
            if item['type'] == 'http.disconnect':
                return
            data += item.get('body', b'')
            if len(data) > 1_048_576:
                return await answer(413)
            if not item.get('more_body'):
                break
        try:
            from modules.messaging.providers.evolution.mapper import normalize_events
            from modules.messaging.domain.messages import InboundMessage
            events = normalize_events(json.loads(data), instance=self.config.instance,
                recipient=self.recipient, received_at=datetime.now(timezone.utc))
            if any(isinstance(event, InboundMessage) and event.sender != self.settings.authorized_sender for event in events):
                return await answer(403)
        except Exception:
            return await answer(400)
        async def replay():
            return {'type': 'http.request', 'body': data, 'more_body': False}
        if self.activity is not None:
            # A real inbound message is the activity of the session; a turn in
            # flight keeps the session alive.
            self.activity.enter()
            try:
                await self.app(scope, replay, send)
            finally:
                self.activity.leave()
            return
        await self.app(scope, replay, send)


def create_session_app(diagnostics=None, activity=None):
    def stage(value):
        if diagnostics is not None:
            diagnostics.advance(value)
    stage('backend_import')
    from .composition import create_telchi_app
    from .handler import BusinessPolicy
    stage('configuration')
    if len(os.getenv('TEAM360_TELCHI_WHATSAPP_NONCE', '')) != 64:
        raise ValueError('owned_session_launcher_required')
    approval = read_approval(os.environ['TEAM360_TELCHI_WHATSAPP_APPROVAL'])
    srv, settings = configuration()
    stage('gate_validation')
    gate_evidence(approval)
    stage('database_validation')
    asyncio.run(check_database(approval, settings, srv.evolution))
    def access_check():
        unchanged_approval(os.environ['TEAM360_TELCHI_WHATSAPP_APPROVAL'], approval)
        gate_evidence(approval)
    stage('app_composition')
    if os.getenv('TEAM360_TRANSPORT_V1_CONFIG'):
        from .transport_dev import create_app
        return create_app(activity=activity)
    app = create_telchi_app(policy=BusinessPolicy(approval['tenant_id'], approval['workspace_id'],
        None, approval['module_enabled'], approval['whole_workspace_scope_verified'],
        pilot_access_check=access_check, pilot_approval_sha256=approval_digest(approval),
        pilot_user_id=approval['user_id']))
    # Existing HTTP lab precedent: retain PG lifecycle, never start unrelated Flow automation.
    app.on_startup = [h for h in app.on_startup if getattr(h, '__name__', '') != '_start_flow_scheduler']
    app.on_shutdown = [h for h in app.on_shutdown if getattr(h, '__name__', '') != '_stop_flow_scheduler']
    return PilotBoundary(app, settings, srv.evolution, srv.recipient, access_check, activity=activity)


def save_private(path, value):
    with open(path, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())


def restore(client, instance, backup):
    current = webhook_body(api(client, 'GET', '/webhook/find/'+instance))
    if current == backup['previous']:
        return
    if current != backup['temporary']:
        raise RuntimeError('webhook_changed_by_other_owner_manual_reconciliation_required')
    api(client, 'POST', '/webhook/set/'+instance, {'webhook': backup['previous']})
    if webhook_body(api(client, 'GET', '/webhook/find/'+instance)) != backup['previous']:
        raise RuntimeError('webhook_restoration_not_verified')


def container_probe(container, url, settings, instance):
    # No WhatsApp input: ignored connection event + invalid-token request.
    code = """const http=require('http');let b='';process.stdin.on('data',x=>b+=x);process.stdin.on('end',async()=>{const c=JSON.parse(b);for(const token of ['',c.token]){await new Promise((ok,no)=>{const r=http.request(c.url,{method:'POST',headers:{'content-type':'application/json','x-team360-webhook-token':token}},s=>{let d='';s.on('data',v=>d+=v);s.on('end',()=>{if(s.statusCode!==(token?200:401))return no();if(token&&JSON.parse(d).results.ignored!==1)return no();ok()})});r.on('error',no);r.end(JSON.stringify({event:'connection.update',instance:c.instance}))})}});"""
    # Input only via stdin, never argv/logs. Check node syntax in unit tests.
    result = subprocess.run(['podman', 'exec', '-i', container, 'node', '-e', code],
        input=json.dumps(dict(url=url, token=settings.webhook_token, instance=instance)),
        text=True, capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError('container_webhook_auth_or_reachability_failed')


def stop_owned(process):
    if process is None or process.poll() is not None:
        return True
    try:
        process.terminate()
        try:
            process.wait(timeout=320)  # durable DEV turn budget plus Foundation cleanup
        except subprocess.TimeoutExpired:
            # Only the still-live session/group leader created with start_new_session.
            try:
                if process.poll() is None and os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
        return process.poll() is not None
    except (OSError, subprocess.TimeoutExpired):
        return False


def start(args):
    from .whatsapp_dev_lifecycle import owned_session
    from .whatsapp_dev_diagnostics import Diagnostics
    with owned_session(args) as session:
        diagnostics = Diagnostics(session, args.output)
        v1 = bool(os.getenv('TEAM360_TRANSPORT_V1_CONFIG'))
        try:
            if v1:
                from .whatsapp_dev_lifecycle import prepare_v1, reaccredit_v1
                diagnostics.advance('V1_preflight')
                prepare_v1()
                diagnostics.advance('V1_reaccreditation')
                reaccredit_v1(args.approval)
            return _start(args, session, diagnostics)
        except BaseException as exc:
            diagnostics.capture(exc)
            raise
        finally:
            if v1:
                from .whatsapp_dev_lifecycle import evolution_running
                evolution_running(False)


def _start(args, session, diagnostics):
    approval, srv, settings, _ = preflight(args.approval)
    diagnostics.advance('gate_validation')
    gates_expiry = gate_evidence(approval)
    directory = Path(args.output).resolve()
    if not directory.is_relative_to(PRIVATE_ROOT):
        raise ValueError('private_output_required')
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    idle_timeout, max_duration = session_timing(args)
    diagnostics.advance('port_check')
    # Validate an unused explicit IPv4 interface. Do not bind all interfaces.
    if args.host in {'0.0.0.0', '127.0.0.1'}:
        raise ValueError('container_reachable_explicit_host_required')
    socket.inet_aton(args.host)
    with socket.socket() as probe:
        probe.bind((args.host, args.port))
    url = f'http://host.containers.internal:{args.port}{WEBHOOK}'
    temporary = dict(enabled=True, url=url, events=['MESSAGES_UPSERT', 'MESSAGES_UPDATE'],
        headers={'x-team360-webhook-token': settings.webhook_token}, byEvents=False, base64=False)
    process, attempted, backup = None, False, None
    session.publish('STARTING')
    result = dict(status='BLOCKED', webhook_restored=False, backend_stopped=False)
    with client_for(srv.evolution) as client, open(directory/'backend.log', 'x', opener=lambda p, f: os.open(p, f, 0o600)) as log:
        worker = None
        try:
            diagnostics.advance('webhook_backup')
            previous = webhook_body(api(client, 'GET', '/webhook/find/'+srv.evolution.instance))
            if previous['enabled']:
                raise RuntimeError('active_webhook_preserved')
            backup = dict(instance=srv.evolution.instance, previous=previous, temporary=temporary)
            save_private(directory/'webhook-backup.json', backup)
            import secrets
            nonce = secrets.token_hex(32)
            env = dict(os.environ, TEAM360_TELCHI_WHATSAPP_APPROVAL=str(private_file(args.approval)),
                       TEAM360_TELCHI_WHATSAPP_NONCE=nonce)
            backend_argv = [sys.executable, '-m', MODULE, '_serve', '--host', args.host,
                '--port', str(args.port), '--diagnostics', str(directory/'backend-diagnostics.json'),
                '--activity', str(directory/'activity.json')]
            diagnostics.advance('backend_spawn')
            process = subprocess.Popen(backend_argv, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, start_new_session=True)
            from .whatsapp_dev_diagnostics import capture_output
            worker = capture_output(process, log)
            from .whatsapp_dev_lifecycle import wait_backend_identity
            diagnostics.advance('backend_identity')
            backend_identity = wait_backend_identity(process, backend_argv)
            session.publish(backend=backend_identity,
                listener=dict(host=args.host, port=args.port,
                    nonce_sha256=hashlib.sha256(nonce.encode()).hexdigest()))
            diagnostics.advance('backend_readiness')
            with httpx.Client(base_url=f'http://{args.host}:{args.port}', trust_env=False, timeout=2) as local:
                for _ in range(150):
                    if process.poll() is not None:
                        raise RuntimeError('owned_backend_exited')
                    try:
                        health = local.get('/health')
                        if health.status_code == 200 and hmac.compare_digest(health.headers.get('x-team360-session', ''), nonce):
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError('owned_backend_startup_timeout')
            # Reachability and auth gate BEFORE changing the webhook.
            diagnostics.advance('container_probe')
            container_probe(args.container, url, settings, srv.evolution.instance)
            if webhook_body(api(client, 'GET', '/webhook/find/'+srv.evolution.instance)) != previous:
                raise RuntimeError('webhook_changed_during_preflight')
            # Recheck policy/integrity immediately before allowing real ingress.
            diagnostics.advance('policy_recheck')
            if read_approval(args.approval) != approval:
                raise RuntimeError('approval_changed_during_startup')
            gate_evidence(approval)
            diagnostics.advance('webhook_activation')
            session.publish(webhook_attempted=True)
            attempted = True  # A timeout can mean the provider applied the change.
            api(client, 'POST', '/webhook/set/'+srv.evolution.instance, {'webhook': temporary})
            if webhook_body(api(client, 'GET', '/webhook/find/'+srv.evolution.instance)) != temporary:
                raise RuntimeError('temporary_webhook_not_verified')
            diagnostics.advance('ready')
            result['status'] = 'READY_FOR_HUMAN_TEST'
            session.publish('READY', ready_at=datetime.now(timezone.utc).isoformat())
            print('READY_FOR_HUMAN_TEST: operador, enviar UNA pregunta; Ctrl-C para cerrar. No E2E_PASS.', flush=True)
            # The session lives while it is used: it closes when it is idle,
            # when it reaches its maximum duration, or when the operator stops
            # it. A turn in flight is never interrupted.
            started = time.monotonic()
            last_activity = started
            closure_reason = 'operator_stop'
            activity_path = directory/'activity.json'
            while True:
                unchanged_approval(args.approval, approval)
                if process.poll() is not None:
                    raise RuntimeError('owned_backend_exited')
                now_m = time.monotonic()
                idle_timeout, max_duration = session_policy(
                    getattr(args, 'control', None), idle_timeout, max_duration)
                activity = read_activity(activity_path)
                if activity:
                    if activity.get('last_activity'):
                        try:
                            observed = datetime.fromisoformat(activity['last_activity']).timestamp()
                            last_activity = max(last_activity, observed)
                        except (TypeError, ValueError):
                            pass
                in_flight = activity.get('in_flight') if activity else None
                gates_expired = False
                if gates_expiry is not None:  # Legacy manifests retain expiration.
                    gates_expired = (gates_expiry - datetime.now(timezone.utc)).total_seconds() <= 0
                reason = session_close_reason(
                    elapsed=now_m - started, idle_elapsed=now_m - last_activity,
                    in_flight=in_flight, max_duration=max_duration, idle_timeout=idle_timeout,
                    gates_expired=gates_expired)
                if reason:
                    closure_reason = reason
                    break
                time.sleep(.5)
            result['closure_reason'] = closure_reason
            result['session_duration_seconds'] = round(time.monotonic() - started, 3)
            result['last_activity_at'] = datetime.fromtimestamp(
                last_activity, timezone.utc).isoformat()
        finally:
            failure = sys.exc_info()[1]
            if failure is not None:
                try:
                    if worker is not None and process.poll() is not None:
                        worker.join(timeout=1)
                    diagnostics.capture(failure)
                except OSError:
                    pass  # Evidence I/O must never prevent owned-resource cleanup.
            # A second Ctrl-C must not interrupt restoration/owned-process cleanup.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            # State publication must never prevent the existing cleanup.
            try:
                session.publish('STOPPING')
            finally:
                try:
                    # Also verify the unchanged webhook after failures before activation.
                    if backup is not None:
                        restore(client, srv.evolution.instance, backup)
                        result['webhook_restored'] = True
                finally:
                    result['backend_stopped'] = stop_owned(process)
                    if worker is not None:
                        worker.join(timeout=5)
                    # Runtime outcome and cleanup outcome are separate guarantees.
                    # restore() compares every canonical backup field, not only URL
                    # and enabled; stop_owned() waits for the exact child to exit.
                    result['status'] = ('CLOSED' if result['webhook_restored']
                                        and result['backend_stopped'] else 'REVIEW_REQUIRED')
                    result['review_reasons'] = ([] if result['webhook_restored'] else
                                                ['webhook_restoration_not_verified'])
                    if not result['backend_stopped']:
                        result['review_reasons'].append('owned_backend_exit_not_verified')
                    result['runtime_incident'] = type(failure).__name__ if failure else None
                    result['original_error'] = diagnostics.original
                    result['startup_stage'] = diagnostics.stage
                    result['diagnostic_logs'] = session.value.get('diagnostic_logs', {})
                    result.setdefault('closure_reason', 'startup_failure')
                    try:
                        save_private(directory/'closure.json', result)
                    finally:
                        session.publish('STOPPED' if result['status'] == 'CLOSED'
                            else 'REVIEW_REQUIRED',
                            closure=result['status'], review_reasons=result['review_reasons'],
                            runtime_incident=result['runtime_incident'],
                            original_error=result['original_error'],
                            webhook_restored=result['webhook_restored'],
                            backend_stopped=result['backend_stopped'],
                            closure_reason=result['closure_reason'],
                            last_activity_at=result.get('last_activity_at'),
                            closed_at=datetime.now(timezone.utc).isoformat())
                    print('CLOSURE='+result['status'], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('preflight', 'start'):
        p = sub.add_parser(name)
        p.add_argument('--approval', type=Path, required=True)
        if name == 'start':
            p.add_argument('--host', required=True)
            p.add_argument('--port', type=int, default=18181)
            p.add_argument('--idle-timeout', type=int, default=None,
                           help='close the session after this many idle seconds')
            p.add_argument('--max-duration', type=int, default=None,
                           help='maximum total duration of the session in seconds')
            p.add_argument('--duration', type=int, default=None,
                           help='legacy alias of --max-duration')
            p.add_argument('--control', type=Path, default=None,
                           help='private control configuration re-read to extend the session')
            p.add_argument('--container', default='evolution-api')
            p.add_argument('--output', required=True)
    p = sub.add_parser('fingerprint')
    p.add_argument('--approval', type=Path, required=True)
    p = sub.add_parser('inspect')
    p.add_argument('--approval', type=Path, required=True)
    p.add_argument('--inbound-id', required=True)
    p = sub.add_parser('restore')
    p.add_argument('--backup', type=Path, required=True)
    p = sub.add_parser('_serve', help=argparse.SUPPRESS)
    p.add_argument('--host', required=True)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--diagnostics', type=Path, required=True)
    p.add_argument('--activity', type=Path, default=None)
    args = parser.parse_args()
    try:
        if args.command == 'preflight':
            preflight(args.approval)
            print('PREFLIGHT_PASS; session not started; container ingress still NOT_TESTED')
        elif args.command == 'start':
            def interrupted(signum, frame):
                raise KeyboardInterrupt
            signal.signal(signal.SIGTERM, interrupted)
            start(args)
        elif args.command == 'fingerprint':
            print(json.dumps(dict(approval_sha256=approval_digest(read_approval(args.approval)),
                                  source_sha256=source_digest())))
        elif args.command == 'inspect':
            print(json.dumps(asyncio.run(inspect_exchange(args.approval, args.inbound_id)), indent=2))
        elif args.command == 'restore':
            srv, _ = configuration()
            backup = json.loads(private_file(args.backup).read_text())
            if backup['instance'] != srv.evolution.instance:
                raise ValueError('backup_instance_mismatch')
            with client_for(srv.evolution) as client:
                restore(client, srv.evolution.instance, backup)
            print('RESTORATION_VERIFIED')
        else:
            from .whatsapp_dev_diagnostics import serve
            # Build outside uvicorn's running loop; check_database uses asyncio.run.
            activity = ActivityMarker(args.activity) if args.activity else None
            serve(args, lambda diagnostics: create_session_app(diagnostics=diagnostics,
                                                              activity=activity))
    except (Exception, KeyboardInterrupt):
        print('BLOCKED: diagnóstico sanitizado en estado privado de sesión y logs referenciados; revisar cierre.', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
