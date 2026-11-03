"""Second explicitly authorized sales block. Capture only; no publication API.

Reuses V1 projection, transport, immutable journal, transform and validation.
Business-date backfill is separate from the unfinished change reconciliation.
Each response is fsynced before another SELECT. A failed/uncertain request is
never retried. Recovery is offline only; a new live block requires new consent.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import fcntl
import time

from . import sales_incremental as inc
from .source import HanaReadOnlySource, HanaTransportLimits
from .sql import assert_read_only_select

CONTRACT = "sales-controlled-block-v1.0.0"
BUDGET = dict(max_selects=8, header_documents=10, line_rows=250,
              statement_seconds=5, operation_seconds=30, persistence_seconds=10,
              pause_seconds=10, total_seconds=360, closure_reserve_seconds=40,
              concurrency=1, retries=0)


def header_fields(domain):
    return [part.strip() for part in inc.projection(domain).split(",") if part.strip().startswith('H.')]


def header_query(domain, excluded):
    header, lines = inc.DOMAINS[domain]
    exclusion = (' AND H."DocEntry" NOT IN (' + ','.join('?' for _ in excluded) + ')') if excluded else ''
    # Correlated counts are bounded to the selected headers, NOT global counts.
    sql = f'''SELECT TOP 10 {', '.join(header_fields(domain))},
(SELECT COUNT(*) FROM "TELCHI"."{lines}" C WHERE C."DocEntry"=H."DocEntry") AS "ExpectedLines"
FROM "TELCHI"."{header}" H WHERE H."DocDate">=? AND H."DocDate"<?
AND H."DocEntry">?{exclusion} ORDER BY H."DocEntry"'''
    return assert_read_only_select(sql)


def line_query(domain, entries):
    if not 1 <= len(entries) <= 10:
        raise ValueError("invalid bounded document set")
    header, lines = inc.DOMAINS[domain]
    return assert_read_only_select(f'''SELECT TOP 250 {inc.projection(domain)}
FROM "TELCHI"."{header}" H JOIN "TELCHI"."{lines}" L ON L."DocEntry"=H."DocEntry"
WHERE H."DocEntry" IN ({','.join('?' for _ in entries)})
AND (H."DocEntry">? OR (H."DocEntry"=? AND L."LineNum">?))
ORDER BY H."DocEntry",L."LineNum"''')


def validate_unit(domain, headers, rows):
    ids = [int(h['DocEntry']) for h in headers]
    if len(ids) != len(set(ids)) or len(ids) > 10 or ids != sorted(ids):
        raise ValueError("invalid header page")
    counts = Counter(int(r['DocEntry']) for r in rows)
    if counts != {int(h['DocEntry']): int(h['ExpectedLines']) for h in headers}:
        raise ValueError("incomplete or changed document lines")
    expected = {int(h['DocEntry']): {k:v for k,v in h.items() if k != 'ExpectedLines'} for h in headers}
    for row in rows:
        if any(row.get(k) != v for k,v in expected[int(row['DocEntry'])].items()):
            raise ValueError("header changed during pagination")
    return inc.validate_rows(domain, rows, limit=10)


def recover(root):
    """Validate every query and complete unit. Never submit a source request."""
    p = inc.read_json(root / 'plan.json')
    if p['contract'] != CONTRACT or p['budget'] != BUDGET:
        raise ValueError('unaccredited controlled block')
    units = []
    verified = {}
    for intent_path in sorted(root.glob('q*.intent.json')):
        key = intent_path.name.split('.')[0]
        intent = inc.read_json(intent_path)
        receipt_path, response_path = root/f'{key}.receipt.json', root/f'{key}.response.json'
        if not receipt_path.exists():
            raise RuntimeError('UNCERTAIN_REQUEST_NO_AUTOMATIC_RETRY')
        receipt = inc.read_json(receipt_path)
        if (intent['plan_sha256'] != inc.digest(p) or receipt['intent_sha256'] != inc.file_hash(intent_path)
                or receipt['response_sha256'] != inc.file_hash(response_path)):
            raise ValueError('query hash mismatch')
        response = inc.read_json(response_path)
        bound = 10 if intent['kind'] == 'headers' else 250
        if len(response) > bound or receipt['rows'] != len(response):
            raise ValueError('query row count mismatch')
        verified[response_path.name] = intent
    for commit_path in sorted(root.glob('unit*.commit.json')):
        commit = inc.read_json(commit_path)
        if commit['plan_sha256'] != inc.digest(p):
            raise ValueError('unit plan mismatch')
        for name, kind in [(commit['headers'], 'headers'), *((n, 'lines') for n in commit['pages'])]:
            if name not in verified or verified[name]['domain'] != commit['domain'] or verified[name]['kind'] != kind:
                raise ValueError('unit query binding mismatch')
        headers = inc.read_json(root / commit['headers'])
        rows = [r for name in commit['pages'] for r in inc.read_json(root/name)]
        metrics = validate_unit(commit['domain'], headers, rows)
        if metrics != commit['metrics'] or inc.digest(rows) != commit['rows_sha256']:
            raise ValueError('unit integrity mismatch')
        units.append(commit)
    return units


@contextmanager
def extraction_lock(parent):
    with (parent / '.sales-controlled-extraction.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def make_plan(pilot_root, base):
    with inc.locked(pilot_root):
        prior = inc.read_json(pilot_root/'plan.json')
        inc.recover(pilot_root, prior)
        excluded = {d: sorted({int(r['DocEntry']) for r in inc.read_json(pilot_root/f'{d}.source.json')}) for d in inc.DOMAINS}
    return dict(contract=CONTRACT, created_at=inc.now(), source='SAP_B1_HANA/TELCHI',
                business_from='2026-10-01', business_to_exclusive='2026-10-02',
                selection='BUSINESS_DATE_BACKFILL_KEYSET_EXCLUDING_VERIFIED_PILOT',
                excluded=excluded, pilot_plan_sha256=inc.digest(prior),
                pilot_commits={d:inc.file_hash(pilot_root/f'{d}.commit.json') for d in inc.DOMAINS},
                budget=BUDGET, limits=asdict(HanaTransportLimits(max_rows=250)), base=base,
                authorization='USER_SECOND_BLOCK_ONLY_NO_THIRD_BLOCK', publication='FORBIDDEN')


def run(root: Path, p: dict, source: HanaReadOnlySource, *, sleep=time.sleep, clock=time.monotonic):
    if (p['contract'] != CONTRACT or p['budget'] != BUDGET
            or source.limits != HanaTransportLimits(max_rows=250) or source.query_log):
        raise ValueError('unaccredited source/budget')
    # Existing directories cannot consume this one-shot authorization again.
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    inc.sync_dir(root.parent)
    inc.seal(root/'plan.json', p)
    started = clock()
    state = dict(status='PARTIAL', queries=[], units=[], started_at=inc.now(), reason=None)
    cursors = {d:-1 for d in inc.DOMAINS}
    exhausted = {d:False for d in inc.DOMAINS}

    def request(domain, sql, params, kind):
        n = len(source.query_log)
        if n >= 8 or clock()-started + 30 + 10 + 40 + (10 if n else 0) >= 360:
            raise RuntimeError('BLOCK_BUDGET_STOP')
        if n:
            sleep(10)
        key = f'q{n+1:02}'
        inc.seal(root/f'{key}.intent.json', dict(plan_sha256=inc.digest(p), domain=domain,
                 kind=kind, sql=sql, params=params, at=inc.now()))
        rows = source.query_read_only(f'block2_{domain}_{kind}', sql, tuple(params))
        persist = clock()
        inc.seal(root/f'{key}.response.json', rows)
        # Receipt is written before latency checks so safe responses survive stop.
        inc.seal(root/f'{key}.receipt.json', dict(intent_sha256=inc.file_hash(root/f'{key}.intent.json'),
                 response_sha256=inc.file_hash(root/f'{key}.response.json'), rows=len(rows),
                 audit=source.query_log[-1], persistence_seconds=clock()-persist))
        if clock()-persist > 10:
            raise RuntimeError('PERSISTENCE_BUDGET_STOP')
        if source.query_log[-1]['duration_ms'] > 5000:
            raise RuntimeError('ABNORMAL_LATENCY_STOP')
        if len(rows) > (10 if kind == 'headers' else 250):
            raise ValueError('row limit exceeded')
        return rows, f'{key}.response.json'

    try:
        # Balanced deterministic order. Invoices first; at most two pages/domain.
        for unit, domain in enumerate(('sales','credit_memo','sales','credit_memo'), 1):
            if exhausted[domain] or len(source.query_log) >= 7:
                continue
            excluded = p['excluded'][domain]
            headers, header_path = request(domain, header_query(domain, excluded),
                [p['business_from'],p['business_to_exclusive'],cursors[domain],*excluded], 'headers')
            if any(int(h['ExpectedLines']) <= 0 for h in headers):
                raise ValueError('document without lines')
            entries = [int(h['DocEntry']) for h in headers]
            rows, pages = [], []
            last_entry, last_line = -1, -1
            expected = sum(int(h['ExpectedLines']) for h in headers)
            while len(rows) < expected:
                page, name = request(domain, line_query(domain, entries),
                                     [*entries,last_entry,last_entry,last_line], 'lines')
                if not page or any((int(r['DocEntry']),int(r['LineNum'])) <= (last_entry,last_line) for r in page):
                    raise ValueError('nonadvancing line cursor')
                keys = [(int(r['DocEntry']),int(r['LineNum'])) for r in page]
                if keys != sorted(set(keys)):
                    raise ValueError('unordered or duplicate lines')
                rows.extend(page); pages.append(name)
                last_entry, last_line = keys[-1]
            unit_persistence_started = clock()
            metrics = validate_unit(domain, headers, rows)
            if rows:
                candidate = inc.transform_capture(domain, rows, dict(extraction_id=root.name,source_as_of=inc.now()))
                validation = inc.validate_candidate(candidate, 2500)
                if validation['status'] != 'PASS':
                    raise ValueError('transform validation failed')
                reconciliation = inc.reconcile_candidate(candidate, candidate.source_rows)
            else:
                validation, reconciliation = {}, {}
            commit = dict(plan_sha256=inc.digest(p),domain=domain,headers=header_path,pages=pages,
                          metrics=metrics,rows_sha256=inc.digest(rows),validation=validation,
                          reconciliation=reconciliation,window_exhausted=len(headers)<10,
                          committed_at=inc.now())
            inc.seal(root/f'unit{unit:02}.commit.json',commit)
            state['units'] = recover(root)
            if clock()-unit_persistence_started > 10:
                raise RuntimeError('PERSISTENCE_BUDGET_STOP')
            cursors[domain] = metrics['last_cursor']
            exhausted[domain] = commit['window_exhausted']
        state['reason'] = 'AUTHORIZED_SECOND_BLOCK_FINISHED_NO_THIRD_BLOCK'
    except BaseException as exc:
        state['reason'] = type(exc).__name__
        state['error_code'] = str(exc) if str(exc).endswith('_STOP') else 'REVIEW_DURABLE_JOURNAL'
    finally:
        state.update(queries=source.query_log,finished_at=inc.now(),elapsed_seconds=clock()-started)
        inc.seal(root/'session.json',state)
    return state


def watermark(root):
    """A limited durable backfill frontier, explicitly NOT complete-source CDC."""
    units = recover(root)
    p = inc.read_json(root/'plan.json')
    return dict(contract='sales-watermark-v1.0.0', source=p['source'],
                contract_version=CONTRACT, date_or_cursor={d:max((u['metrics']['last_cursor'] for u in units if u['domain']==d),default=-1) for d in inc.DOMAINS},
                last_document_identity={d:dict(header_table=inc.DOMAINS[d][0],doc_entry=max((u['metrics']['last_cursor'] for u in units if u['domain']==d),default=-1)) for d in inc.DOMAINS},
                coverage=dict(business_from=p['business_from'],business_to_exclusive=p['business_to_exclusive'],
                              status='PARTIAL_BACKFILL_ONLY',october_complete=False),
                checkpoint_state='VERIFIED_COMMITTED_UNITS_ONLY',
                evidence={f.name:inc.file_hash(f) for f in sorted(root.glob('unit*.commit.json'))},
                change_watermark=None, change_indicator='UpdateDate_COARSE_DATE_OBSERVED_IN_PILOT',
                gaps=inc.GAPS, reconciliation_window=dict(days=7,status='PROPOSED_NOT_COMPLETE_CDC',
                    required='Full bounded September/October backfill plus recurring whole-document overlap; reset cursors each cycle. Periodic older-history reconciliation needed for changes beyond overlap.'),
                backfill_frontier_is_not_change_watermark=True,
                source_update_time_or_log_instance='NOT_PROBED_NO_RELIABILITY_CLAIM',
                publication='NOT_PUBLISHED')
