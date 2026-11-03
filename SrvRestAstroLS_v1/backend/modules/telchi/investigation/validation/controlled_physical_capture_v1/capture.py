"""Bounded OITM investigation capture; explicit resume, no retry or publication."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import time
import uuid

from .persistence import LOCAL_PERSISTENCE_SECONDS, PersistenceBlocked, preflight as destination_preflight, verify_probe

PRIVATE = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi')
CONSISTENCY = 'MULTI_SESSION_INTERVAL_SCAN_NOT_TRANSACTIONAL_SNAPSHOT'


def query(size, following=False):
    if type(size) is not int or not 1 <= size <= 100:
        raise RuntimeError('invalid_batch_size')
    predicate = ' WHERE "ItemCode" > ?' if following else ''
    return f'SELECT TOP {size} "ItemCode", "U_FormaFarmac" FROM "TELCHI"."OITM"{predicate} ORDER BY "ItemCode"'


# Legacy SQL fingerprints remain accepted for the preserved 100-row prefix.
FIRST, NEXT = query(100), query(100, True)


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n').encode()


def sha(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def save(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('wb') as f:
        data = encoded(value)
        if f.write(data) != len(data):
            raise OSError('short_capture_write')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    sync_directory(path.parent)


def sync_directory(root):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def destination_lock(root):
    # Directory inode lock: no lockfile deletion/recreation race, no source writes.
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('capture_already_running') from None
        yield
    finally:
        os.close(fd)


def validate(rows, last, seen, limit=100):
    if not isinstance(rows, list) or len(rows) > limit:
        raise RuntimeError('oversized_batch')
    if any(not isinstance(r, dict) or set(r) != {'ItemCode', 'U_FormaFarmac'} for r in rows):
        raise RuntimeError('incompatible_columns')
    keys = [r['ItemCode'] for r in rows]
    if any(not isinstance(k, str) or not k.strip() for k in keys):
        raise RuntimeError('invalid_key')
    if len(set(keys)) != len(keys) or any(k in seen for k in keys):
        raise RuntimeError('duplicate_key')
    chain = ([last] if last is not None else []) + keys
    if any(a >= b for a, b in zip(chain, chain[1:])):
        raise RuntimeError('non_increasing_key')
    return keys


def read_checkpoint(root, cp=None):
    try:
        cp = json.loads((root / 'checkpoint.json').read_text()) if cp is None else cp
        if cp.get('version', 1) not in (1, 2) or (cp.get('version') == 2 and cp.get('source') != 'SAP_HANA.TELCHI.OITM'):
            raise RuntimeError('incompatible_checkpoint')
        rows, seen, last = [], set(), None
        for number, entry in enumerate(cp['batches'], 1):
            if entry['file'] != f'batch-{number:04d}.json':
                raise RuntimeError('incompatible_batch_path')
            p = root / entry['file']
            if p.is_symlink() or digest(p) != entry['sha256']:
                raise RuntimeError('checkpoint_hash_mismatch')
            batch = json.loads(p.read_text())
            limit = entry.get('batch_size', 100)
            if type(limit) is not int or not 1 <= limit <= (25 if 'session_id' in entry else 100):
                raise RuntimeError('incompatible_batch_size')
            expected_sql = query(limit, last is not None)
            if entry['query_sha256'] != hashlib.sha256(expected_sql.encode()).hexdigest():
                raise RuntimeError('incompatible_query')
            if not batch.get('observed_at'):
                raise RuntimeError('missing_observation_date')
            if 'session_id' in entry and batch.get('session_id') != entry['session_id']:
                raise RuntimeError('incompatible_session')
            keys = validate(batch['rows'], last, seen, limit)
            if len(keys) != entry['rows']:
                raise RuntimeError('checkpoint_row_mismatch')
            rows.extend(batch['rows'])
            seen.update(keys)
            if keys:
                last = keys[-1]
        if cp['last_key'] != last or cp['rows'] != len(rows):
            raise RuntimeError('checkpoint_state_mismatch')
        return cp, rows, seen, last
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, OSError) as exc:
        raise RuntimeError('corrupt_checkpoint') from exc


def recover(root):
    _, rows, seen, last = read_checkpoint(root)
    return rows, seen, last


def recover_pending(root):
    """Under destination lock only. A durable batch is adopted without querying SAP."""
    # Validate the committed base even when a recoverable journal is present.
    # A journal must not silently repair or hide a corrupted checkpoint.
    read_checkpoint(root)
    pending = root / 'pending.json'
    if pending.exists():
        try:
            journal = json.loads(pending.read_text())
            current = digest(root / 'checkpoint.json')
            candidate = journal['checkpoint']
            old = json.loads((root / 'checkpoint.json').read_text())
            if current == journal['base_sha256']:
                if candidate['batches'][:-1] != old['batches']:
                    raise RuntimeError('incompatible_pending_prefix')
                entry = candidate['batches'][-1]
                size, count = entry['batch_size'], entry['rows']
                if (candidate.get('version') != 2 or candidate.get('source') != 'SAP_HANA.TELCHI.OITM' or
                    type(size) is not int or not 1 <= size <= 25 or
                    type(count) is not int or not 0 <= count <= size or
                    candidate['rows'] != old['rows'] + count or
                    not isinstance(entry['sha256'], str) or len(entry['sha256']) != 64 or
                    any(c not in '0123456789abcdef' for c in entry['sha256']) or
                    not entry['session_id'] or
                    entry['query_sha256'] != hashlib.sha256(query(size, old['last_key'] is not None).encode()).hexdigest()):
                    raise RuntimeError('incompatible_pending_metadata')
                key = candidate['last_key']
                if ((not count and key != old['last_key']) or
                    (count and (not isinstance(key, str) or not key.strip() or
                                (old['last_key'] is not None and key <= old['last_key'])))):
                    raise RuntimeError('incompatible_pending_key')
                if entry['file'] != f"batch-{len(old['batches']) + 1:04d}.json":
                    raise RuntimeError('incompatible_pending_path')
                if (root / entry['file']).exists():
                    read_checkpoint(root, candidate)
                    save(root / 'checkpoint.json', candidate)
                # No durable batch: unconfirmed rows may be queried again, never fabricated.
            elif current == sha(candidate):
                read_checkpoint(root, candidate)
            else:
                raise RuntimeError('incompatible_pending_checkpoint')
            pending.unlink()
            sync_directory(root)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError, OSError) as exc:
            raise RuntimeError('corrupt_pending') from exc
    cp, rows, seen, last = read_checkpoint(root)
    if {p.name for p in root.glob('batch-*.json')} != {e['file'] for e in cp['batches']}:
        raise RuntimeError('untracked_batch')
    return cp, rows, seen, last


def recover_isolated(source, target):
    """Offline recovery; originals remain byte-identical, including interrupted tmp files."""
    source, target = Path(source).resolve(), Path(target).resolve()
    if target.parent != PRIVATE.resolve() or source == target:
        raise RuntimeError('destination_must_be_private_isolated_directory')
    with destination_lock(source):
        read_checkpoint(source)
        before = file_inventory(source)
        target.mkdir(mode=0o700, exist_ok=False)
        with destination_lock(target):
            for name in before:
                path = target / name
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(source / name, path)
                with path.open('rb') as copied:
                    os.fsync(copied.fileno())
                sync_directory(path.parent)
            if before != file_inventory(source) or before != file_inventory(target):
                raise RuntimeError('copy_hash_mismatch')
            pending = target / 'pending.json'
            adopted_tmp = False
            if pending.exists():
                journal = json.loads(pending.read_text())
                candidate = journal['checkpoint']
                entry = candidate['batches'][-1]
                expected = f"batch-{len(read_checkpoint(target)[0]['batches']) + 1:04d}.json"
                if entry['file'] != expected:
                    raise RuntimeError('incompatible_pending_path')
                final = target / expected
                tmp = final.with_suffix('.json.tmp')
                if not final.exists() and tmp.exists():
                    if (digest(target / 'checkpoint.json') != journal['base_sha256'] or
                            digest(tmp) != entry['sha256']):
                        raise RuntimeError('pending_tmp_hash_mismatch')
                    os.replace(tmp, final)
                    sync_directory(target)
                    read_checkpoint(target, candidate)
                    adopted_tmp = True
            cp, rows, seen, last = recover_pending(target)
            after = file_inventory(target)
            recover_pending(target)
            if after != file_inventory(target) or before != file_inventory(source):
                raise RuntimeError('non_idempotent_recovery_or_source_changed')
            evidence = dict(source=str(source), destination=str(target), source_inventory=before,
                rows=cp['rows'], unique_rows=len(seen), last_key=last,
                checkpoint_sha256=digest(target / 'checkpoint.json'), adopted_tmp=adopted_tmp,
                pending=False, idempotent=True, sap_queries=0, recovered_at=utc())
            save(target / 'recovery.json', evidence)
            return evidence


def file_inventory(root):
    paths = list(root.rglob('*'))
    if any(p.is_symlink() for p in paths):
        raise RuntimeError('symlinks_not_supported')
    return {str(p.relative_to(root)): digest(p) for p in paths if p.is_file()}


def connect_hana():
    # Imported only after local integrity checks, never by offline tests/recover.
    from hdbcli import dbapi
    from modules.telchi.datalake.source import hana_config
    from modules.telchi.datalake.sql import assert_read_only_select
    for sql in (query(25), query(25, True)):
        assert_read_only_select(sql)
    config = hana_config()
    if config['schema'] != 'TELCHI' or 'qmark' not in dbapi.paramstyle:
        raise RuntimeError('incompatible_hana_configuration')
    conn = dbapi.connect(address=config['host'], port=int(config['port']),
        user=config['user'], password=config['password'], currentSchema=config['schema'],
        encrypt='false', connectTimeout=3000, communicationTimeout=3000)
    try:
        conn.setautocommit(True)
        if not conn.getautocommit():
            raise RuntimeError('autocommit_not_enabled')
        return conn
    except BaseException:
        conn.close()
        raise


def controls(batch_size, max_queries, pause_seconds, latency_seconds):
    if (type(batch_size) is not int or not 1 <= batch_size <= 25 or
        type(max_queries) is not int or not 1 <= max_queries <= 5 or
        not math.isfinite(pause_seconds) or pause_seconds < 10 or
        not math.isfinite(latency_seconds) or not 0 < latency_seconds <= 1.5):
        raise RuntimeError('unsafe_controls')


def run(root, *, resume=False, resume_from=None, batch_size=25, max_queries=5,
        pause_seconds=10, latency_seconds=1.5, connect_factory=None,
        sleep=time.sleep, clock=time.perf_counter, budget=None):
    controls(batch_size, max_queries, pause_seconds, latency_seconds)
    os.umask(0o077)
    root = root.resolve()
    if root.parent != PRIVATE.resolve():
        raise RuntimeError('destination_must_be_private_isolated_directory')
    if resume_from is not None and not resume:
        raise RuntimeError('resume_required')
    # Read-only target assessment precedes mkdir, copy, recovery and SAP import.
    persistence_evidence = destination_preflight(root if root.exists() else root.parent)
    if not resume or resume_from is not None:
        root.mkdir(mode=0o700, exist_ok=False)
    with destination_lock(root):
        if resume_from is not None:
            source = Path(resume_from).resolve()
            if source == root:
                raise RuntimeError('source_equals_destination')
            with destination_lock(source):
                cp, _, _, _ = read_checkpoint(source)
                if (source / 'pending.json').exists():
                    raise RuntimeError('source_has_pending_commit')
                inventory = file_inventory(source)
                inherited_origin = json.loads((source / 'origin.json').read_text()) if (source / 'origin.json').exists() else None
                for name in inventory:
                    (root / name).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    shutil.copyfile(source / name, root / name)
                    with (root / name).open('rb') as copied:
                        os.fsync(copied.fileno())
                    sync_directory((root / name).parent)
                if inventory != file_inventory(source):
                    raise RuntimeError('source_changed_during_copy')
                if any(digest(root / name) != value for name, value in inventory.items()):
                    raise RuntimeError('copy_hash_mismatch')
                save(root / 'origin.json', dict(source=str(source), copied_at=utc(),
                    files=inventory, inherited_origin=inherited_origin,
                    rows=cp['rows'], consistency=CONSISTENCY))
        elif not resume:
            save(root / 'checkpoint.json', dict(version=2, source='SAP_HANA.TELCHI.OITM',
                                               last_key=None, rows=0, batches=[]))
        had_pending = (root / 'pending.json').exists()
        cp, _, seen, last = recover_pending(root)
        if cp['batches'] and cp['batches'][-1]['rows'] < cp['batches'][-1].get('batch_size', 100):
            raise RuntimeError('capture_already_complete')
        # Copy/recovery can take time; re-assess the actual prepared destination.
        persistence_evidence = destination_preflight(root)
        persistence_evidence['probe'] = verify_probe(root, save, digest, sync_directory)
        session_id = uuid.uuid4().hex
        sessions = root / 'sessions'
        sessions.mkdir(mode=0o700, exist_ok=True)
        state = dict(session_id=session_id, started_at=utc(), status='PARTIAL',
            base_checkpoint_sha256=digest(root / 'checkpoint.json'), initial_rows=len(seen),
            recovered_pending_commit=had_pending,
            connection_attempts=0, queries=0, batches=0, rows=len(seen),
            cursor_opened=0, cursor_closed=0, connection_closed=False, eof=False,
            durations_ms=[], persistence=persistence_evidence, persistence_ms=[],
            consistency=CONSISTENCY, retries=0, concurrency=1,
            batch_size=batch_size, max_queries=max_queries, pause_seconds=pause_seconds,
            latency_seconds=latency_seconds, persistence_seconds=LOCAL_PERSISTENCE_SECONDS)
        session_path = sessions / f'{session_id}.json'
        save(session_path, state)
        connection = None
        try:
            if budget is not None and not budget.can_start_query():
                state['stop_reason'] = budget.reason()
                return state
            state['connection_attempts'] = 1
            connection = (connect_factory or connect_hana)()
            for number in range(max_queries):
                if budget is not None and not budget.can_start_query(pause_seconds if number else 0):
                    state['stop_reason'] = budget.reason()
                    break
                if number:
                    sleep(pause_seconds)
                    destination_preflight(root)
                if budget is not None and not budget.can_start_query():
                    state['stop_reason'] = budget.reason()
                    break
                cursor = connection.cursor()
                state['cursor_opened'] += 1
                try:
                    cursor.setquerytimeout(3)
                    sql, params = query(batch_size, last is not None), (() if last is None else (last,))
                    query_start = clock()
                    state['queries'] += 1
                    cursor.execute(sql, params)
                    raw = cursor.fetchall()
                    elapsed = (clock() - query_start) * 1000
                    state['durations_ms'].append(elapsed)
                    if [x[0] for x in cursor.description] != ['ItemCode', 'U_FormaFarmac']:
                        raise RuntimeError('unexpected_columns')
                    if any(len(row) != 2 for row in raw):
                        raise RuntimeError('unexpected_row_width')
                    rows = [dict(zip(('ItemCode', 'U_FormaFarmac'), row)) for row in raw]
                finally:
                    cursor.close()
                    state['cursor_closed'] += 1
                keys = validate(rows, last, seen, batch_size)
                filename = f"batch-{len(cp['batches']) + 1:04d}.json"
                if (root / filename).exists():
                    raise RuntimeError('batch_would_be_overwritten')
                batch = dict(session_id=session_id, observed_at=utc(), duration_ms=elapsed, rows=rows)
                entry = dict(file=filename, sha256=sha(batch), rows=len(rows), duration_ms=elapsed,
                    query_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                    session_id=session_id, batch_size=batch_size)
                candidate = dict(cp, version=2, source='SAP_HANA.TELCHI.OITM',
                    batches=cp['batches'] + [entry], rows=len(seen) + len(keys),
                    last_key=keys[-1] if keys else last)
                persist_start = time.monotonic()
                save(root / 'pending.json', dict(base_sha256=digest(root / 'checkpoint.json'), checkpoint=candidate))
                save(root / filename, batch)
                save(root / 'checkpoint.json', candidate)
                (root / 'pending.json').unlink()
                sync_directory(root)
                # Verify durable protocol output before allowing another query.
                read_checkpoint(root)
                persisted_ms = (time.monotonic() - persist_start) * 1000
                state['persistence_ms'].append(persisted_ms)
                cp = candidate
                seen.update(keys)
                last = cp['last_key']
                state.update(batches=state['batches'] + 1, rows=len(seen))
                save(session_path, state)
                if persisted_ms > LOCAL_PERSISTENCE_SECONDS * 1000:
                    raise PersistenceBlocked('destination_commit_latency_exceeded')
                if elapsed > latency_seconds * 1000:
                    state['stop_reason'] = 'latency_threshold_exceeded'
                    break
                if len(rows) < batch_size:
                    state.update(eof=True, status='CAPTURE_COMPLETE', stop_reason='eof')
                    break
            else:
                state['stop_reason'] = 'query_budget_exhausted'
        except BaseException as exc:
            # Never expose driver text, credentials, endpoints or item keys.
            state['stop_reason'] = type(exc).__name__
            if isinstance(exc, PersistenceBlocked):
                state['persistence_block'] = str(exc)
        finally:
            if connection is not None:
                try:
                    connection.close()
                    state['connection_closed'] = True
                except BaseException as exc:
                    state.update(close_error=type(exc).__name__, status='PARTIAL')
            state.update(finished_at=utc(), final_checkpoint_sha256=digest(root / 'checkpoint.json'))
            save(session_path, state)
        print(json.dumps(state), flush=True)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--resume-from', type=Path, help='Copy validated prefix to a NEW destination; source stays untouched')
    parser.add_argument('--batch-size', type=int, default=25)
    parser.add_argument('--max-queries', type=int, default=5)
    parser.add_argument('--pause-seconds', type=float, default=10)
    parser.add_argument('--latency-seconds', type=float, default=1.5)
    args = parser.parse_args()
    state = run(args.destination, resume=args.resume, resume_from=args.resume_from,
        batch_size=args.batch_size, max_queries=args.max_queries,
        pause_seconds=args.pause_seconds, latency_seconds=args.latency_seconds)
    return 0 if state.get('stop_reason') in ('eof', 'query_budget_exhausted') else 1


if __name__ == '__main__':
    raise SystemExit(main())
