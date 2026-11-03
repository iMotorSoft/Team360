"""IN-selection contract and durable response ledger; transport lives separately.

Uses the existing capture's directory lock and fsync primitives, not its keyset
checkpoint. Callers must hold destination_lock for every ledger operation.
"""
from copy import deepcopy
import json
import os
from pathlib import Path

from ..controlled_physical_capture_v1.capture import PRIVATE, digest, save, sha, sync_directory
from ..operational_products_offline_v1.analyze import selective_query

CONTROLS = dict(max_items_per_select=25, max_queries_per_block=5,
    active_connections=1, parallelism=0, automatic_retries=0,
    query_pause_seconds=10, block_pause_seconds=30, hana_latency_seconds=1.5,
    durable_persistence_seconds=10, cooperative_timeout=True,
    closure_and_recovery_reserve_required=True, verify_cursor_connection_closed=True,
    interprocess_exclusion=True)


def plan_for(keys):
    if any(not isinstance(k, str) or not k.strip() for k in keys):
        raise ValueError('invalid_itemcode')
    if keys != sorted(set(keys)):
        raise ValueError('keys_must_be_sorted_unique')
    batches = []
    for i in range(0, len(keys), 25):
        sql, params = selective_query(keys[i:i+25])
        batches.append(dict(index=len(batches), block=len(batches)//5,
                            sql=sql, parameters=params))
    plan = dict(version='selective-offline-v2', source='SAP_HANA.TELCHI.OITM',
        item_codes=keys, batches=batches, controls=CONTROLS.copy(),
        status='OFFLINE_CONTRACT_ONLY_NO_HANA_RUNNER',
        missing_policy='Terminal NOT_RETURNED after completed fetch; not proof of deletion. No automatic retry.',
        execution_gate='New explicit HANA authorization AND transport pacing/timeout/closure integration gate required.')
    return dict(plan, plan_sha256=sha(plan))


def validate_plan(plan):
    if plan != plan_for(plan['item_codes']):
        raise RuntimeError('plan_mismatch')


def response_batch(plan, index, rows, *, observed_at, fetch_complete):
    validate_plan(plan)
    return _response_batch(plan, index, rows, observed_at=observed_at,
                           fetch_complete=fetch_complete)


def _response_batch(plan, index, rows, *, observed_at, fetch_complete):
    """Internal row validation; caller has already validated the whole plan."""
    if type(index) is not int or not 0 <= index < len(plan['batches']):
        raise RuntimeError('invalid_batch_index')
    if fetch_complete is not True or not observed_at:
        raise RuntimeError('incomplete_fetch_or_missing_observation')
    requested = plan['batches'][index]['parameters']
    if not isinstance(rows, list) or any(not isinstance(r, dict) or
            set(r) != {'ItemCode', 'U_FormaFarmac'} for r in rows):
        raise RuntimeError('incompatible_response')
    keys = [r['ItemCode'] for r in rows]
    if any(not isinstance(k, str) or not k.strip() for k in keys):
        raise RuntimeError('invalid_response_key')
    if len(set(keys)) != len(keys) or keys != sorted(keys) or not set(keys) <= set(requested):
        raise RuntimeError('duplicate_unordered_or_unexpected_response')
    return dict(plan_sha256=plan['plan_sha256'], index=index, requested=requested,
        rows=rows, not_returned=sorted(set(requested)-set(keys)),
        observed_at=observed_at, fetch_complete=True)


def validate_destination(root):
    if root.is_symlink() or root.resolve().parent != PRIVATE.resolve():
        raise RuntimeError('destination_must_be_new_private_isolated_directory')


def initialize(root, plan):
    validate_destination(root)
    validate_plan(plan)
    if any(root.iterdir()):
        raise RuntimeError('destination_not_empty')
    save(root/'plan.json', plan)
    save(root/'checkpoint.json', dict(version='selective-offline-v2',
        plan_sha256=plan['plan_sha256'], batches=[]))


def read_state(root, plan, cp=None):
    validate_destination(root)
    validate_plan(plan)
    if json.loads((root/'plan.json').read_text()) != plan:
        raise RuntimeError('destination_plan_mismatch')
    if cp is None:
        cp = json.loads((root/'checkpoint.json').read_text())
    if (cp.get('version') != 'selective-offline-v2' or
            cp.get('plan_sha256') != plan['plan_sha256'] or
            len(cp['batches']) > len(plan['batches'])):
        raise RuntimeError('incompatible_checkpoint')
    for i, entry in enumerate(cp['batches']):
        if entry['file'] != f'selective-{i:06d}.json':
            raise RuntimeError('incompatible_batch_path')
        path = root/entry['file']
        if path.is_symlink() or digest(path) != entry['sha256']:
            raise RuntimeError('batch_hash_mismatch')
        b = json.loads(path.read_text())
        expected = _response_batch(plan, i, b['rows'], observed_at=b['observed_at'],
                                  fetch_complete=b['fetch_complete'])
        if b != expected:
            raise RuntimeError('batch_contract_mismatch')
    return cp


def archive_temporary(root, path):
    """Preserve interrupted bytes; never discard evidence or use it as a checkpoint."""
    archive = root/'interrupted'
    archive.mkdir(mode=0o700, exist_ok=True)
    target = archive/f'{len(list(archive.iterdir())):06d}-{path.name}'
    if target.exists():
        raise RuntimeError('archive_conflict')
    os.replace(path, target)
    sync_directory(archive)
    sync_directory(root)


def validated_journal(root, plan, cp, j):
    b, candidate = j['batch'], j['checkpoint']
    expected = _response_batch(plan, b['index'], b['rows'],
        observed_at=b['observed_at'], fetch_complete=b['fetch_complete'])
    entry = dict(file=f"selective-{b['index']:06d}.json", sha256=sha(b))
    if (b != expected or candidate.get('version') != cp['version'] or
            candidate.get('plan_sha256') != plan['plan_sha256'] or
            len(candidate['batches']) != b['index']+1 or
            candidate['batches'][-1] != entry):
        raise RuntimeError('incompatible_journal')
    if digest(root/'checkpoint.json') == j['base_sha256']:
        if candidate['batches'][:-1] != cp['batches']:
            raise RuntimeError('incompatible_journal_prefix')
    elif candidate != cp:
        raise RuntimeError('journal_checkpoint_conflict')
    return j


def recover(root, plan):
    """A complete journal (including a validated tmp) recovers without SAP."""
    if any(p.is_symlink() for p in root.rglob('*')):
        raise RuntimeError('symlinks_not_supported')
    cp = read_state(root, plan)
    journal = root/'pending.json'
    tmp = root/'pending.json.tmp'
    if not journal.exists() and tmp.exists():
        # A full payload can be re-fsynced and adopted; partial JSON stays blocked.
        try:
            j = validated_journal(root, plan, cp, json.loads(tmp.read_text()))
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError('unresolved_temporary_file') from exc
        with tmp.open('rb') as f:
            os.fsync(f.fileno())
        os.replace(tmp, journal)
        sync_directory(root)
    if journal.exists():
        j = validated_journal(root, plan, cp, json.loads(journal.read_text()))
        # The verified journal is authoritative, not partial local writes.
        for interrupted in root.glob('*.tmp'):
            archive_temporary(root, interrupted)
        candidate = j['checkpoint']
        b = j['batch']
        entry = candidate['batches'][-1]
        if digest(root/'checkpoint.json') == j['base_sha256']:
            path = root/entry['file']
            if path.exists():
                if digest(path) != entry['sha256']:
                    raise RuntimeError('journal_batch_conflict')
            else:
                save(path, b)
            read_state(root, plan, candidate)
            save(root/'checkpoint.json', candidate)
        elif cp != candidate:
            raise RuntimeError('journal_checkpoint_conflict')
        read_state(root, plan)
        journal.unlink()
        sync_directory(root)
    cp = read_state(root, plan)
    if {p.name for p in root.glob('selective-*.json')} != {e['file'] for e in cp['batches']}:
        raise RuntimeError('untracked_selective_batch')
    intent = root/'request.json'
    if intent.exists():
        request = json.loads(intent.read_text())
        index = request['index']
        if (request.get('plan_sha256') != plan['plan_sha256'] or type(index) is not int or
                not 0 <= index < len(plan['batches']) or
                request.get('requested') != plan['batches'][index]['parameters'] or
                not request.get('reserved_at') or index > len(cp['batches'])):
            raise RuntimeError('invalid_request_intent')
        if index < len(cp['batches']):
            intent.unlink()
            sync_directory(root)
        # Otherwise uncertain query outcome: preserve intent; never reserve/retry.
    # A .tmp is never evidence of an executed query. Require explicit offline review.
    if list(root.glob('*.tmp')):
        raise RuntimeError('unresolved_temporary_file')
    return cp


def acknowledge_uncertain(root, plan, *, reason):
    """Explicit OFFLINE operator decision, under lock; never called by the runner.

    May cause a physical repeat on a later authorized run. Confirmed batches
    remain untouched. Partial writes and request intent are archived, not deleted.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise RuntimeError('review_reason_required')
    cp = read_state(root, plan)
    if (root/'pending.json').exists():
        raise RuntimeError('recover_journal_first')
    tmp = root/'pending.json.tmp'
    if tmp.exists():
        try:
            value = json.loads(tmp.read_text())
        except (ValueError, UnicodeError):
            pass
        else:
            validated_journal(root, plan, cp, value)
            raise RuntimeError('recover_complete_journal_first')
    if any(p.is_symlink() for p in root.rglob('*')):
        raise RuntimeError('symlinks_not_supported')
    if {p.name for p in root.glob('selective-*.json')} != {e['file'] for e in cp['batches']}:
        raise RuntimeError('untracked_selective_batch')
    if (root/'review.json').exists():
        archive_temporary(root, root/'review.json')
    save(root/'review.json', dict(plan_sha256=plan['plan_sha256'],
        next_batch=len(cp['batches']), reason=reason, physical_repeat_possible=True))
    for path in list(root.glob('*.tmp')) + ([root/'request.json'] if (root/'request.json').exists() else []):
        archive_temporary(root, path)
    return recover(root, plan)


def reserve_request(root, plan, index, *, reserved_at):
    """Durable pre-query intent. Uncertain outcomes block future automatic queries."""
    cp = recover(root, plan)
    if (root/'request.json').exists():
        raise RuntimeError('uncertain_request_manual_review_no_retry')
    if type(index) is not int or index != len(cp['batches']) or not 0 <= index < len(plan['batches']) or not reserved_at:
        raise RuntimeError('invalid_request_reservation')
    request = dict(plan_sha256=plan['plan_sha256'], index=index,
        requested=plan['batches'][index]['parameters'], reserved_at=reserved_at)
    save(root/'request.json', request)
    if json.loads((root/'request.json').read_text()) != request:
        raise RuntimeError('request_readback_mismatch')
    return request


def commit_response(root, plan, index, rows, *, observed_at, fetch_complete):
    cp = recover(root, plan)
    b = response_batch(plan, index, rows, observed_at=observed_at, fetch_complete=fetch_complete)
    if index < len(cp['batches']):
        if json.loads((root/cp['batches'][index]['file']).read_text()) != b:
            raise RuntimeError('committed_response_conflict')
        return cp
    if index != len(cp['batches']):
        raise RuntimeError('nonsequential_batch')
    if not (root/'request.json').exists():
        raise RuntimeError('durable_request_intent_required')
    candidate = deepcopy(cp)
    candidate['batches'].append(dict(file=f'selective-{index:06d}.json', sha256=sha(b)))
    save(root/'pending.json', dict(base_sha256=digest(root/'checkpoint.json'),
        checkpoint=candidate, batch=b))
    return recover(root, plan)


def query_slot_allowed(plan, completed, *, elapsed_query_pause, elapsed_block_pause,
                       remaining_seconds, closure_reserve_seconds, has_unresolved_request=False):
    """Pure future scheduler predicate; does NOT execute or sleep."""
    validate_plan(plan)
    if has_unresolved_request or not 0 <= completed < len(plan['batches']) or closure_reserve_seconds <= 0:
        return False
    if completed and elapsed_query_pause < 10:
        return False
    if completed and completed % 5 == 0 and elapsed_block_pause < 30:
        return False
    return remaining_seconds >= 1.5 + 10 + closure_reserve_seconds
