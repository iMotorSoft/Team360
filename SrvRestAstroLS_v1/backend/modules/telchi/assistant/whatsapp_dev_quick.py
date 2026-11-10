"""One-command DEV orchestration over the canonical WhatsApp lifecycle."""
import argparse
import asyncio
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import time

from . import whatsapp_dev as dev
from . import whatsapp_dev_lifecycle as control
from modules.messaging.providers.evolution import meta_webhook_update as meta

ROOT = Path(__file__).resolve().parents[5]
LAB = ROOT.parent.parent / 'lab/evolution-api'


def script(name, *, env=None):
    result = subprocess.run([str(LAB / name)], cwd=LAB, capture_output=True,
                            text=True, timeout=100, env=env)
    # Do not print script output: logs may contain provider credentials.
    return result.returncode, result.stdout


def cloud_state():
    _, text = script('cloudflare-status.sh')
    for state in ('READY', 'STOPPED', 'DEGRADED', 'REVIEW_REQUIRED'):
        if text.startswith('cloudflare_tunnel=' + state + ' '):
            return state
    return 'REVIEW_REQUIRED'


def litellm_ready():
    try:
        with dev.httpx.Client(trust_env=False, timeout=5) as client:
            return client.get('http://127.0.0.1:4000/health/liveliness').status_code == 200
    except dev.httpx.HTTPError:
        return False


def snapshot(config, meta_env):
    report = dict(POSTGRES='DEGRADED', LITELLM='DEGRADED', EVOLUTION='DEGRADED',
                  CLOUDFLARE='DEGRADED', PUBLIC_URL='UNAVAILABLE', META_CALLBACK='UPDATE_REQUIRED',
                  SIX_GATES='DEGRADED', WHATSAPP_RUNTIME='STOPPED', READY_FOR_DIALOGUE='NO')
    blockers = []
    approval_path = config.get('approval', dev.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json')
    try:
        approval = dev.read_approval(approval_path)
        dev.gate_evidence(approval)
        report['SIX_GATES'] = 'PASS'
    except Exception:
        blockers.append('SIX_GATES_INVALID_OR_APPROVAL_INVALID')
    try:
        # Independent from gate evidence, with real binding/identity/schema validation.
        approval = dev.read_approval(approval_path)
        srv, settings = dev.configuration()
        asyncio.run(dev.check_database(approval, settings, srv.evolution))
        report['POSTGRES'] = 'READY'
    except Exception:
        blockers.append('POSTGRES_OR_IDENTITY_BINDING_CONFIGURATION')
    if litellm_ready():
        report['LITELLM'] = 'READY'
    else:
        blockers.append('LITELLM_UNAVAILABLE_USE_APPROVED_RUNBOOK')
    try:
        _, container = control.adopted_container()
        if container['State']['Running']:
            srv, _ = dev.configuration()
            with dev.client_for(srv.evolution) as client:
                connection = dev.api(client, 'GET', '/instance/connectionState/' + srv.evolution.instance)
            if connection.get('instance', {}).get('state') == 'open':
                report['EVOLUTION'] = 'READY'
        if report['EVOLUTION'] != 'READY':
            blockers.append('EVOLUTION_NOT_READY')
    except Exception:
        blockers.append('EVOLUTION_IDENTITY_OR_API_UNVERIFIED')
    try:
        state = cloud_state()
        if state == 'READY':
            origin = meta.base_url((LAB / 'data/cloudflared.url').read_text().strip())
            report['PUBLIC_URL'] = origin
            updater = meta.Updater(meta_env, meta.Transport())
            row, _ = updater.inventory()  # GET only, including WABA/override/identity checks.
            updater.challenge('http://127.0.0.1:18180', 'LOCAL_CALLBACK')
            updater.challenge(origin, 'PUBLIC_CALLBACK')
            report['CLOUDFLARE'] = 'READY'
            if row['callback_url'] == origin + '/webhook/meta':
                report['META_CALLBACK'] = 'SYNCED'
            else:
                blockers.append('META_UPDATE_REQUIRES_EXPLICIT_AUTHORIZATION')
        else:
            blockers.append('CLOUDFLARE_' + state)
    except Exception:
        blockers.append('CLOUDFLARE_OR_META_READBACK_UNVERIFIED')
    runtime = control.status()
    if runtime['state'] == 'READY':
        report['WHATSAPP_RUNTIME'] = 'RUNNING'
    elif runtime['state'] != 'STOPPED':
        blockers.append('RUNTIME_' + runtime['state'])
    else:
        blockers.append('RUNTIME_STOPPED')
    report['READY_FOR_DIALOGUE'] = 'YES' if not blockers else 'NO'
    report['BLOCKER'] = ','.join(blockers) if blockers else 'NONE'
    return report


def ensure_services():
    # Only restart a verified existing adopted container, never provision/migrate.
    _, container = control.adopted_container()
    if not container['State']['Running']:
        # The approved lab script addresses evolution-api by name: verify same ID.
        named = subprocess.run(['podman', 'container', 'inspect', '--format', '{{.Id}}', 'evolution-api'],
                               capture_output=True, text=True, timeout=15, check=True)
        if named.stdout.strip() != container['Id']:
            raise RuntimeError('approved_script_container_identity_mismatch')
        # start.sh can provision networks/images when missing. Refuse that path:
        # pin the already-installed adopted image and require its network first.
        subprocess.run(['podman', 'network', 'exists', 'evolution-api-net'],
                       capture_output=True, timeout=15, check=True)
        subprocess.run(['podman', 'image', 'exists', container['Image']],
                       capture_output=True, timeout=15, check=True)
        code, _ = script('start.sh', env=dict(os.environ, EVOLUTION_IMAGE=container['Image']))
        if code:
            raise RuntimeError('approved_Evolution_start_failed')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            srv, _ = dev.configuration()
            try:
                with dev.client_for(srv.evolution) as client:
                    state = dev.api(client, 'GET', '/instance/connectionState/' + srv.evolution.instance)
                if state.get('instance', {}).get('state') == 'open':
                    break
            except Exception:
                pass
            time.sleep(.5)
        else:
            raise RuntimeError('Evolution_start_readiness_failed')
    state = cloud_state()
    if state == 'STOPPED':
        code, _ = script('cloudflare-start.sh')
        if code or cloud_state() != 'READY':
            raise RuntimeError('approved_Cloudflare_start_failed')
    elif state != 'READY':
        raise RuntimeError('Cloudflare_requires_review_no_duplicate_started')


@contextmanager
def operation_lock():
    control.directory(control.root())
    fd = os.open(control.root() / 'quick.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private_lock_required')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def operate(command, config, config_path, meta_env):
    if command == 'status':
        return snapshot(config, meta_env)
    with operation_lock():
        if command == 'down':
            result = control.stop()
            report = snapshot(config, meta_env)
            if result['state'] != 'STOPPED':
                report.update(READY_FOR_DIALOGUE='NO', BLOCKER='RUNTIME_STOP_REQUIRES_REVIEW')
            return report
        # Fail cheap, before any infrastructure mutation. Never reaccredit implicitly.
        approval = dev.read_approval(config.get('approval', dev.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
        try:
            dev.gate_evidence(approval)
        except Exception:
            raise RuntimeError('SIX_GATES_DEGRADED') from None
        try:
            srv, settings = dev.configuration()
            asyncio.run(dev.check_database(approval, settings, srv.evolution))
        except Exception:
            raise RuntimeError('POSTGRES_OR_IDENTITY_BINDING_CONFIGURATION') from None
        if not litellm_ready():
            raise RuntimeError('LITELLM_UNAVAILABLE_USE_APPROVED_RUNBOOK')
        # A stale owner record must not cause side effects in shared services.
        runtime = control.status()
        if runtime['state'] not in {'READY', 'STOPPED'}:
            raise RuntimeError('previous_session_requires_review')
        ensure_services()
        report = snapshot(config, meta_env)
        if report['BLOCKER'] not in {'NONE', 'RUNTIME_STOPPED'}:
            return report
        if report['WHATSAPP_RUNTIME'] == 'STOPPED':
            control.launch(config, config_path)
        return snapshot(config, meta_env)


def emit(report):
    for key, value in report.items():
        print(f'{key}={value}')
    if report['META_CALLBACK'] == 'UPDATE_REQUIRED' and report['PUBLIC_URL'] != 'UNAVAILABLE':
        print('AUTHORIZED_META_UPDATE_COMMAND=./meta-webhook-update.sh ' + report['PUBLIC_URL'] + ' --apply')
    print('READINESS_SCOPE=transport_and_runtime_only; reception_and_delivery_NOT_TESTED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['up', 'status', 'down', 'reconcile'])
    parser.add_argument('--config', type=Path, default=dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    parser.add_argument('--session', help='Exact historical session ID; required for explicit recovery')
    args = parser.parse_args()
    # The canonical controller sanitizes its environment. Keep Meta credentials
    # separately in memory solely for the existing read-only updater implementation.
    meta_env = {k: v for k, v in os.environ.items() if k.startswith('META_TEAM360_') or k == 'TEAM360_ENV'}
    try:
        config = control.load_config(args.config)
        if args.command == 'reconcile':
            if not args.session:
                parser.error('reconcile requires --session')
            from .whatsapp_dev_recovery import reconcile
            with operation_lock():
                result = reconcile(args.session)
            print('HISTORICAL_STOPPING=' + result['recovery'])
            return 0
        report = operate(args.command, config, args.config, meta_env)
        emit(report)
        if args.command == 'status':
            return 0 if report['BLOCKER'] in {'NONE', 'RUNTIME_STOPPED'} else 1
        if args.command == 'down':
            return 0 if report['WHATSAPP_RUNTIME'] == 'STOPPED' and not report['BLOCKER'].startswith('RUNTIME_STOP_REQUIRES') else 1
        return 0 if report['READY_FOR_DIALOGUE'] == 'YES' else 1
    except Exception as exc:
        # Provider/DSN exceptions can contain secrets. Expose only known safe codes.
        safe = {'previous_session_requires_review', 'LITELLM_UNAVAILABLE_USE_APPROVED_RUNBOOK',
                'SIX_GATES_DEGRADED', 'POSTGRES_OR_IDENTITY_BINDING_CONFIGURATION',
                'historical_work_requires_reconciliation', 'historical_session_changed',
                'historical_process_present_or_pid_reused', 'historical_state_not_recoverable'}
        code = str(exc) if str(exc) in safe else 'inspect_private_configuration_gates_and_lifecycle'
        if args.command in {'up', 'status', 'down'} and 'config' in locals():
            report = snapshot(config, meta_env)
            report.update(READY_FOR_DIALOGUE='NO', BLOCKER=code)
            emit(report)
        else:
            print('READY_FOR_DIALOGUE=NO\nBLOCKER=' + code)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
