"""Private Linux-only lifecycle contract for the bounded TelchiAI DEV launcher.

No infrastructure lifecycle, port-based process discovery, or log parsing.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time

from . import whatsapp_dev as dev


def now():
    return datetime.now(timezone.utc).isoformat()


def directory(path):
    path = Path(path)
    # Do not follow a symlink, including in parent components.
    if path.absolute() != path.resolve() or not path.resolve().is_relative_to(dev.PRIVATE_ROOT.resolve()):
        raise ValueError('private_directory_required')
    path.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('private_directory_required')
    return path


def root():
    return dev.PRIVATE_ROOT / 'whatsapp-dev-control'


def read_json(path):
    path = Path(path)
    if path.absolute() != path.resolve():
        raise ValueError('symlink_refused')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if (not path.resolve().is_relative_to(dev.PRIVATE_ROOT.resolve())
                or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise ValueError('private_file_required')
        return json.load(stream)


def atomic(path, value):
    path = Path(path)
    directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix='.state-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def identity(pid):
    try:
        proc = Path('/proc') / str(int(pid))
        fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return dict(pid=int(pid), start_ticks=fields[19], uid=proc.stat().st_uid,
                    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                    executable=os.readlink(proc / 'exe'),
                    command_sha256=hashlib.sha256((proc / 'cmdline').read_bytes()).hexdigest())
    except (OSError, ValueError, IndexError):
        return None


def wait_backend_identity(process, argv):
    expected = hashlib.sha256(b''.join(os.fsencode(arg) + b'\0' for arg in argv)).hexdigest()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and process.poll() is None:
        value = identity(process.pid)
        if value and value['command_sha256'] == expected:
            return value
        time.sleep(.01)
    raise RuntimeError('owned_backend_exec_identity_unavailable')


def matches(value):
    return bool(value and value.get('uid') == os.getuid() and identity(value['pid']) == value)


def signal_owned(value):
    # Pin the kernel process BEFORE rechecking identity: no PID-reuse signal race.
    if not value or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('verified_pidfd_required')
    fd = os.pidfd_open(value['pid'])
    try:
        if not matches(value):
            raise RuntimeError('process_identity_changed')
        signal.pidfd_send_signal(fd, signal.SIGTERM)
    finally:
        os.close(fd)


class Session:
    def __init__(self, args):
        self.path = root() / 'current.json'
        self.published = False
        self.value = dict(version=1, session_id=secrets.token_hex(16), state='STARTING',
                          launcher=identity(os.getpid()), backend=None, listener=None,
                          backup=str(Path(args.output).resolve() / 'webhook-backup.json'),
                          approval=str(Path(args.approval).resolve()),
                          created_at=now(), webhook_attempted=False,
                          webhook_restored=False, backend_stopped=False)

    def publish(self, state=None, **values):
        self.value.update(values)
        if state:
            self.value['state'] = state
        self.value['updated_at'] = now()
        atomic(self.path, self.value)
        self.published = True
        # Preserve each session's identity/closing evidence across subsequent starts.
        atomic(self.path.parent / (self.value['session_id'] + '.json'), self.value)


@contextmanager
def owned_session(args):
    directory(root())
    fd = os.open(root() / 'owner.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    session = None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private_lock_required')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            prior = read_json(root() / 'current.json')
        except FileNotFoundError:
            prior = None
        if prior and (prior.get('state') != 'STOPPED' or not prior.get('backend_stopped')
                      or not (prior.get('webhook_restored') or prior.get('webhook_untouched'))
                      or matches(prior.get('launcher'))
                      or matches(prior.get('backend'))):
            raise RuntimeError('previous_session_requires_review')
        session = Session(args)
        session.publish()
        yield session
    finally:
        try:
            if session and session.published and session.value['state'] not in {'STOPPED', 'REVIEW_REQUIRED'}:
                if not session.value.get('backend') and not session.value['webhook_attempted']:
                    session.publish('STOPPED', backend_stopped=True, webhook_untouched=True,
                                    closed_at=now())
                else:
                    session.publish('REVIEW_REQUIRED')
        finally:
            os.close(fd)


# Exact capability allowlist, not prefixes. All other inherited variables are
# removed in this controller process before importing application settings.
CONFIG_ENV = frozenset({
    'AUTOMATION_DIAGNOSIS_REPOSITORY', 'TEAM360_ENV', 'TEAM360_TELCHI_DURABLE',
    'TEAM360_TELCHI_FREE_ANALYSIS', 'TEAM360_TELCHI_CONSOLE_CONFIG',
    'TEAM360_SRV05_EVOLUTION_ENABLED', 'TEAM360_SRV05_MESSAGING_PROVIDER',
    'TEAM360_MESSAGING_DEV_ENABLED', 'TEAM360_MESSAGING_DISPATCH_MODE',
    'TEAM360_MESSAGING_WORKSPACE_SLUG', 'TEAM360_MESSAGING_CHANNEL_ALIAS',
    'TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER', 'TEAM360_MESSAGING_WEBHOOK_TOKEN',
    'TEAM360_EVOLUTION_BASE_URL', 'TEAM360_EVOLUTION_INSTANCE',
    'TEAM360_EVOLUTION_API_KEY', 'TEAM360_EVOLUTION_TIMEOUT_SECONDS',
    'META_TEAM360_PHONE_NUMBER_ID', 'TEAM360_DB_URL', 'TEAM360_DB_SCHEMA',
    'OpenAI_Key_JAI_query', 'TEAM360_EVOLUTION_MANAGEMENT_API_KEY',
    'TEAM360_TRANSPORT_V1_CONFIG', 'TEAM360_TRANSPORT_V1_RUNTIME_ROLE',
    'TEAM360_TELCHI_V1_SEND_AUTHORIZED',
})
BASE_ENV = frozenset({'PATH', 'HOME', 'LANG'})


def load_config(path):
    config = read_json(path)
    if stat.S_IMODE(Path(path).stat().st_mode) != 0o600:
        raise ValueError('configuration_mode_0600_required')
    allowed = {'env', 'host', 'port', 'duration', 'container', 'approval',
               'idle_timeout', 'max_duration'}
    if set(config) - allowed or not isinstance(config.get('env'), dict):
        raise ValueError('invalid_private_configuration')
    # JSON data only: never source shell, expand substitutions or accept Python paths.
    for name, value in config['env'].items():
        if name not in CONFIG_ENV or not isinstance(value, str) or '\x00' in value:
            raise ValueError('invalid_environment_entry')
    if config['env'].get('AUTOMATION_DIAGNOSIS_REPOSITORY', 'postgres') != 'postgres':
        raise ValueError('postgres_repository_required')
    for key, low, high in (('idle_timeout', dev.MIN_IDLE_TIMEOUT, dev.MAX_IDLE_TIMEOUT),
                           ('max_duration', dev.MIN_MAX_DURATION, dev.MAX_MAX_DURATION),
                           ('duration', dev.MIN_MAX_DURATION, dev.MAX_MAX_DURATION)):
        value = config.get(key)
        if value is not None and (type(value) is not int or not low <= value <= high):
            raise ValueError('invalid_private_configuration')
    # Validate everything before mutation; never inherit credentials, profiles,
    # proxy/Python injection, libpq options or flags from the caller's terminal.
    environment = dict(PATH='/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8',
                       HOME=pwd.getpwuid(os.getuid()).pw_dir)
    environment.update(config['env'])
    os.environ.clear()
    os.environ.update(environment)
    return config


def adopted_container():
    """Verify the explicit DEV adoption; immutable labels are evidence, not grants."""
    record = read_json(dev.PRIVATE_ROOT / 'evolution-dev-v1/owned-runtime.json')
    receipt = read_json(record['adoption_receipt'])
    cid = record['evolution_container_id']
    def inspect(*args):
        return json.loads(subprocess.check_output(['podman', *args], timeout=15))[0]
    container = inspect('inspect', cid)
    image = inspect('image', 'inspect', container['Image'])
    labels = hashlib.sha256(json.dumps(container['Config']['Labels'], sort_keys=True).encode()).hexdigest()
    if (receipt['operation'] != 'owner_authorized_dev_adoption'
            or receipt['container_id'] != cid or container['Id'] != cid
            or receipt['image_manifest_digest'] != image['Digest']
            or receipt['image_id'] != container['Image'] or receipt['labels_sha256'] != labels):
        raise ValueError('adopted_Evolution_identity_changed')
    return cid, container


def evolution_running(running):
    cid, container = adopted_container()
    if bool(container['State']['Running']) != running:
        subprocess.run(['podman', 'start' if running else 'stop', *([] if running else ['--time', '10']), cid],
                       check=True, capture_output=True, timeout=40)
    if bool(adopted_container()[1]['State']['Running']) != running:
        raise RuntimeError('adopted_Evolution_state_not_verified')


def prepare_v1():
    """Only the adopted container; no recreation, migration, replay or Meta calls."""
    if os.environ.get('TEAM360_TELCHI_DURABLE') != '1':
        raise ValueError('V1_durable_worker_required')
    evolution_running(True)
    srv, _ = dev.configuration()
    with dev.client_for(srv.evolution) as client:
        for attempt in range(100):
            try:
                current = dev.webhook_body(dev.api(client, 'GET', '/webhook/find/' + srv.evolution.instance))
                break
            except (dev.httpx.HTTPError, RuntimeError):
                if attempt == 99:
                    raise
                time.sleep(.3)
        # Close the existing DEV ingress before probes. Preserve all fields and evidence.
        if current['enabled']:
            directory(root())
            dev.save_private(root() / ('prestart-webhook-' + secrets.token_hex(8) + '.json'), current)
            closed = dict(current, enabled=False)
            dev.api(client, 'POST', '/webhook/set/' + srv.evolution.instance, {'webhook': closed})
            if dev.webhook_body(dev.api(client, 'GET', '/webhook/find/' + srv.evolution.instance)) != closed:
                raise RuntimeError('DEV_ingress_closure_not_verified')
    document = read_json(os.environ['TEAM360_TRANSPORT_V1_CONFIG'])
    callback = Path(document['socket'])
    if callback.exists():
        import socket
        connection = socket.socket(socket.AF_UNIX)
        try:
            connection.connect(str(callback))
        except ConnectionRefusedError:
            info = callback.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError('callback_ownership_unverified')
            callback.rename(callback.with_name(callback.name + '.stale-' + secrets.token_hex(8)))
        else:
            raise ValueError('existing_V1_callback_listener_preserved')
        finally:
            connection.close()


def reaccredit_v1(approval):
    try:
        dev.gate_evidence(dev.read_approval(approval))
        return
    except (ValueError, KeyError, FileNotFoundError):
        pass
    backend = Path(__file__).resolve().parents[3]
    runner = backend.parents[1] / 'data/reports/messaging/binding-activation-dev-20261023/reaccredit_v1.py'
    logpath = root() / ('reaccredit-' + secrets.token_hex(8) + '.log')
    with open(logpath, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as log:
        result = subprocess.run([sys.executable, str(runner)], cwd=backend,
            env=dict(os.environ, TEAM360_REACCREDIT_LAUNCHER_PID=str(os.getpid())),
            stdout=log, stderr=subprocess.STDOUT, timeout=600)
    if result.returncode:
        raise RuntimeError('V1_reaccreditation_failed_private_log:' + str(logpath))
    dev.gate_evidence(dev.read_approval(approval))


def inspect_webhook(record):
    if os.getenv('TEAM360_TRANSPORT_V1_CONFIG') and not adopted_container()[1]['State']['Running']:
        return 'INACTIVE', 'STOPPED'
    srv, _ = dev.configuration()
    with dev.client_for(srv.evolution) as client:
        connection = dev.api(client, 'GET', '/instance/connectionState/' + srv.evolution.instance)
        external = 'READY' if connection.get('instance', {}).get('state') == 'open' else 'DEGRADED'
        current = dev.webhook_body(dev.api(client, 'GET', '/webhook/find/' + srv.evolution.instance))
    try:
        backup = read_json(record['backup'])
    except FileNotFoundError:
        # No backup means the launcher has not reached webhook mutation.
        if not record['webhook_attempted'] and record.get('backend') is None:
            return ('INACTIVE' if not current['enabled'] and current['url'] else 'FOREIGN'), external
        raise
    if backup['instance'] != srv.evolution.instance:
        raise ValueError('backup_instance_mismatch')
    return ('INTERNAL' if current == backup['previous'] else
            'SESSION' if current == backup['temporary'] else 'FOREIGN'), external


def listener_owned(record):
    listener = record.get('listener')
    if not listener or not matches(record.get('backend')):
        return False
    with dev.httpx.Client(trust_env=False, timeout=2) as client:
        response = client.get(f"http://{listener['host']}:{listener['port']}/health")
    return (response.status_code == 200 and
            hashlib.sha256(response.headers.get('x-team360-session', '').encode()).hexdigest()
            == listener['nonce_sha256'])


def status():
    try:
        record = read_json(root() / 'current.json')
    except FileNotFoundError:
        return dict(state='STOPPED', backend='ABSENT', webhook='UNKNOWN',
                    evolution='NOT_CHECKED', postgresql='NOT_CHECKED',
                    approval='NOT_CHECKED', gates='NOT_CHECKED')
    state = record['state']
    launcher = matches(record.get('launcher'))
    backend = matches(record.get('backend'))
    report = dict(state=state, session_id=record['session_id'],
                  launcher='OWNED' if launcher else 'ABSENT_OR_CHANGED',
                  backend='OWNED' if backend else 'ABSENT_OR_CHANGED',
                  webhook='UNKNOWN', evolution='UNKNOWN', postgresql='NOT_CHECKED',
                  approval='UNKNOWN', gates='NOT_CHECKED',
                  review_reasons=list(record.get('review_reasons', [])))
    if state not in {'STOPPED', 'REVIEW_REQUIRED'} and not launcher:
        report['state'] = 'REVIEW_REQUIRED'
        report['review_reasons'].append('launcher_ownership_not_demonstrated')
    if record.get('backend') and not backend and (
            state not in {'STOPPED', 'STOPPING'} or identity(record['backend']['pid'])):
        report['state'] = 'REVIEW_REQUIRED'
        report['review_reasons'].append('backend_ownership_not_demonstrated')
    try:
        report['webhook'], report['evolution'] = inspect_webhook(record)
        if report['webhook'] == 'FOREIGN':
            report['state'] = 'REVIEW_REQUIRED'
            report['review_reasons'].append('webhook_differs_from_backup_and_session')
        elif state == 'READY' and report['webhook'] != 'SESSION':
            report['state'] = 'REVIEW_REQUIRED'
            report['review_reasons'].append('active_session_webhook_not_verified')
        elif state == 'STOPPED' and report['webhook'] not in {'INTERNAL', 'INACTIVE'}:
            report['state'] = 'REVIEW_REQUIRED'
            report['review_reasons'].append('webhook_restoration_not_verified')
    except Exception:
        report['state'] = 'REVIEW_REQUIRED'
        report['review_reasons'].append('webhook_readback_or_backup_unavailable')
    try:
        approval = dev.read_approval(record['approval'])
        report['approval'] = 'VALID'
    except Exception:
        report['approval'] = 'INVALID_OR_REVOKED'
    else:
        try:
            dev.gate_evidence(approval)  # Integrity/expiry only; never execute batteries.
            report['gates'] = 'VALID'
        except Exception:
            report['gates'] = 'INVALID_OR_EXPIRED'
        try:
            srv, settings = dev.configuration()
            asyncio.run(dev.check_database(approval, settings, srv.evolution))
            report['postgresql'] = 'READY'
        except Exception:
            report['postgresql'] = 'DEGRADED'
    if state == 'READY' and report['state'] != 'REVIEW_REQUIRED':
        try:
            healthy = listener_owned(record)
        except Exception:
            healthy = False
        if os.getenv('TEAM360_TRANSPORT_V1_CONFIG'):
            report['provider'] = 'BoundEvolutionProvider'
            report['durable_worker'] = 'PASS' if healthy else 'BLOCKED'
        if not backend:
            report['state'] = 'REVIEW_REQUIRED'
        elif (not healthy or report['postgresql'] != 'READY' or report['evolution'] != 'READY'
              or report['approval'] != 'VALID' or report['gates'] != 'VALID'):
            report['state'] = 'DEGRADED'
    if state == 'STOPPED' and (backend or not record.get('backend_stopped')
                               or not (record.get('webhook_restored') or record.get('webhook_untouched'))):
        report['state'] = 'REVIEW_REQUIRED'
        report['review_reasons'].append('persisted_closure_or_backend_exit_not_verified')
    if state == 'REVIEW_REQUIRED' and not report['review_reasons']:
        report['review_reasons'].append('historical_session_requires_explicit_review')
    return report


def stop(timeout=350):
    try:
        record = read_json(root() / 'current.json')
    except FileNotFoundError:
        return status()
    if record['state'] == 'STOPPED':
        return status()
    if (record['state'] == 'REVIEW_REQUIRED' or not matches(record.get('launcher'))
            or (record['state'] != 'STOPPING' and record.get('backend') and not matches(record['backend']))):
        return dict(state='REVIEW_REQUIRED', reason='ownership_not_demonstrated')
    if record['state'] != 'STOPPING':
        signal_owned(record['launcher'])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        latest = read_json(root() / 'current.json')
        if latest['session_id'] != record['session_id']:
            return dict(state='REVIEW_REQUIRED', reason='session_changed')
        if not matches(record['launcher']):
            break
        time.sleep(.2)
    report = status()
    if matches(record['launcher']) or matches(record.get('backend')):
        report['state'] = 'REVIEW_REQUIRED'
    return report


def launch(config, control_path=None):
    if not config.get('host'):
        raise ValueError('explicit_authorized_launch_host_required')
    directory(root())
    # The launcher owns the lock/record. The controller never claims a PID itself.
    output = dev.PRIVATE_ROOT / ('whatsapp-dev-session-' + secrets.token_hex(16))
    args = [sys.executable, '-m', dev.MODULE, 'start', '--approval',
            str(config.get('approval', dev.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json')),
            '--host', config['host'], '--port', str(config.get('port', 18181)),
            '--idle-timeout', str(config.get('idle_timeout', dev.DEFAULT_IDLE_TIMEOUT)),
            '--max-duration', str(config.get('max_duration',
                                             config.get('duration', dev.DEFAULT_MAX_DURATION))),
            '--control', str(control_path), '--container',
            config.get('container', 'evolution-api'), '--output', str(output)]
    logpath = root() / (output.name + '.log')
    with open(logpath, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as log:
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
    # A bounded startup wait; the session continues independently of this terminal.
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            record = read_json(root() / 'current.json')
            if record.get('launcher') and record['launcher']['pid'] == child.pid:
                if record['state'] == 'READY' and matches(record['launcher']):
                    return status()
                if record['state'] in {'STOPPED', 'REVIEW_REQUIRED'}:
                    return startup_failure(record, logpath)
        except FileNotFoundError:
            pass
        if child.poll() is not None:
            try:
                record = read_json(root() / 'current.json')
                if record.get('launcher', {}).get('pid') == child.pid:
                    return startup_failure(record, logpath)
            except FileNotFoundError:
                pass
            return dict(state='REVIEW_REQUIRED', reason='start_refused_or_failed',
                        launcher_log=str(logpath))
        time.sleep(.2)
    return dict(state='STARTING', reason='read_status_before_retry')


def startup_failure(record, logpath):
    original = record.get('original_error')
    return dict(state=record['state'],
                reason=original['category'] if original else 'start_closed_before_ready',
                original_error=original, startup_stage=record.get('startup_stage'),
                backend_stage=record.get('backend_stage'),
                diagnostic_logs=record.get('diagnostic_logs', {}), launcher_log=str(logpath))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'status', 'stop'])
    parser.add_argument('--config', type=Path, default=dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.command == 'start' and status()['state'] == 'READY':
            print(json.dumps(status(), sort_keys=True))
            return 0
        result = (launch(config, args.config) if args.command == 'start'
                  else stop() if args.command == 'stop' else status())
        print(json.dumps(result, sort_keys=True))
        successful = {'READY', 'STARTING'} if args.command == 'start' else {'READY', 'STOPPED', 'STARTING', 'STOPPING'}
        return 0 if result['state'] in successful else 1
    except Exception:
        print(json.dumps(dict(state='REVIEW_REQUIRED', reason='inspect_private_configuration_and_evidence')))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
