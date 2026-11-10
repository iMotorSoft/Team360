"""Explicit, audited administrative closure; never replay or declare runtime success."""
import asyncio
import fcntl
import hashlib
import os
from pathlib import Path
import socket
import stat

from . import whatsapp_dev as dev
from . import whatsapp_dev_lifecycle as control


async def inventory(record):
    import psycopg
    from psycopg.rows import dict_row
    from modules.db.settings import get_database_settings
    from modules.console.login_cli import local_dsn
    from .whatsapp_dev_repository import check_session, recovery_inventory
    srv, settings = dev.configuration()
    dsn = get_database_settings().dsn
    local_dsn(dsn)
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row,
            connect_timeout=5, options='-c statement_timeout=5000 -c lock_timeout=3000') as conn:
        async with conn.transaction():
            await conn.execute('SET TRANSACTION READ ONLY')
            binding = await check_session(conn, settings, srv.evolution,
                                          dev.read_approval(record['approval']))
            return await recovery_inventory(conn, binding, record['created_at'])


def verify_absent(record):
    for name in ('launcher', 'backend'):
        value = record.get(name)
        # A reused PID is ambiguous, not permission to signal or close.
        if value and control.identity(value['pid']) is not None:
            raise RuntimeError('historical_process_present_or_pid_reused')
    listener = record.get('listener')
    if listener:
        with socket.socket() as probe:
            probe.bind((listener['host'], listener['port']))


def reconcile(session_id):
    """Caller explicitly authorizes restore of this exact historical session."""
    control.directory(control.root())
    fd = os.open(control.root() / 'owner.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private_lock_required')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = control.root() / 'current.json'
        record = control.read_json(path)
        if record['session_id'] != session_id:
            raise RuntimeError('historical_session_changed')
        if record['state'] == 'STOPPED' and record.get('administrative_recovery'):
            return dict(state='STOPPED', session_id=session_id, recovery='ALREADY_RECONCILED')
        if record['state'] not in {'STOPPING', 'REVIEW_REQUIRED', 'READY'}:
            raise RuntimeError('historical_state_not_recoverable')
        # READY is recoverable only with the original process/listener evidence.
        # A missing identity is not proof of death; live OR reused PIDs and a
        # bound listener remain fenced by verify_absent under the lifecycle lock.
        if record['state'] == 'READY' and not all(
                record.get(key) for key in ('launcher', 'backend', 'listener')):
            raise RuntimeError('ready_orphan_evidence_required')
        verify_absent(record)
        counts = asyncio.run(inventory(record))
        if any(counts[key] for key in ('durable_pending', 'resumable_outbound',
                                      'session_uncertain_outbound', 'session_running_inbound')):
            raise RuntimeError('historical_work_requires_reconciliation')
        audit = control.directory(control.root() / ('recovery-' + session_id))
        # Exact originals retained before any remote/local mutation. On interruption,
        # resume only if originals are still identical; never overwrite evidence.
        for source in (path, control.root() / (session_id + '.json'), Path(record['backup'])):
            control.read_json(source)
            target = audit / source.name
            raw = source.read_bytes()
            if target.exists():
                if target.read_bytes() != raw:
                    raise RuntimeError('recovery_original_changed')
            else:
                with open(target, 'xb', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
        evidence = dict(operation='administrative_closure_not_runtime_success',
                        session_id=session_id, at=control.now(), uid=os.getuid(),
                        original_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        inventory=counts, database_writes=0, messages_sent=0,
                        transition=dict(from_state=record['state'], to_state='STOPPED'),
                        processes_absent=True, listener_free=True)
        control.atomic(audit / 'review.json', evidence)
        srv, _ = dev.configuration()
        backup = control.read_json(record['backup'])
        if backup['instance'] != srv.evolution.instance:
            raise RuntimeError('backup_instance_mismatch')
        with dev.client_for(srv.evolution) as client:
            # Existing fail-closed restore checks ALL canonical fields, then readback.
            dev.restore(client, srv.evolution.instance, backup)
        verify_absent(record)
        if control.read_json(path) != record:
            raise RuntimeError('historical_session_changed')
        evidence.update(webhook_restored=True, backend_stopped=True, verified_at=control.now())
        control.atomic(audit / 'verified.json', evidence)
        closed = dict(record, state='STOPPED', webhook_restored=True, backend_stopped=True,
                      closure='ADMINISTRATIVE_RECOVERY', closure_reason='orphaned_session_reconciled',
                      administrative_recovery=str(audit / 'verified.json'),
                      closed_at=control.now(), updated_at=control.now())
        # Session first, current last: current is the launch admission authority.
        control.atomic(control.root() / (session_id + '.json'), closed)
        control.atomic(path, closed)
        return dict(state='STOPPED', session_id=session_id, recovery='RECONCILED', inventory=counts)
    finally:
        os.close(fd)
