"""Bounded sales continuity recovery. No publication, scheduling or SAP writes.

A cycle scans frozen daily business windows, replacing whole documents. This
also detects line-only edits in those windows without trusting UpdateDate as
CDC. Older-history edits and remote snapshot isolation remain explicit gaps.
The CLI authorization is restricted to September--October 29, 2026. Subsequent
cycles can reuse the engine but need their own bounded operational entitlement.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import signal
import time
import uuid

from . import sales_incremental as inc
from .sales_controlled_block import extraction_lock, header_fields
from .source import HanaReadOnlySource, HanaTransportLimits, _canonical, hana_config
from .sql import assert_read_only_select
from modules.telchi.runtime.resource_guard import ResourceGuard

CONTRACT = 'sales-continuity-recovery-v1.0.0'
BUDGET = dict(total_seconds=14400, max_selects=12000, max_window_selects=512,
              header_documents=100, line_rows=250, response_bytes=2097152,
              statement_seconds=5, operation_seconds=30, persistence_seconds=10,
              closure_reserve_seconds=120, concurrency=1, retries=0,
              normal_pause_seconds=0.1, degraded_pause_seconds=2,
              sustained_latency_ms=4000, sustained_samples=5)
LIMITS = HanaTransportLimits(max_rows=250)


class ByteCursor:
    """Enforce cumulative serialized payload bound during driver fetch."""
    def __init__(self, cursor):
        self.cursor, self.bytes = cursor, 0

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def fetchmany(self, size):
        batch = self.cursor.fetchmany(size)
        self.bytes += sum(len(json.dumps([_canonical(v) for v in row], ensure_ascii=True).encode()) for row in batch)
        if self.bytes > BUDGET['response_bytes']:
            raise RuntimeError('RESPONSE_BYTE_BUDGET_STOP')
        return batch


class SalesSource(HanaReadOnlySource):
    def __init__(self):
        super().__init__(limits=LIMITS)

    def _connect(self):
        connection, cursor = super()._connect()
        return connection, ByteCursor(cursor)


def windows(start=date(2026, 9, 1), end=date(2026, 10, 30)):
    if start < date(2026, 9, 1) or end > date(2026, 10, 30) or start >= end:
        raise ValueError('outside authorized scope')
    result = []
    while start < end:
        for domain in inc.DOMAINS:
            missing_from = date(2026, 9, 25 if domain == 'sales' else 24)
            result.append(dict(id=f'{start.isoformat()}_{domain}', domain=domain,
                               start=start.isoformat(), end=(start+timedelta(days=1)).isoformat(),
                               mode='BACKFILL' if start >= missing_from else 'OVERLAP_RECONCILIATION'))
        start += timedelta(days=1)
    return result


def make_plan(prior_evidence):
    return dict(contract=CONTRACT, created_at=inc.now(), budget=BUDGET, limits=asdict(LIMITS),
                source='SAP_B1_HANA/TELCHI', windows=windows(), prior_evidence=prior_evidence,
                authorization='USER_SALES_CONTINUITY_RECOVERY_V1_SEP_THROUGH_20261029',
                publication='NOT_AUTHORIZED', global_change_watermark=None,
                gaps=inc.GAPS, strategy='DAILY_COMPLETE_DOCUMENT_RECONCILIATION_NOT_CDC',
                budget_derivation='Prior 5s/30s transport and 10s persistence retained; pilots ~0.9s/query. '
                '118 daily source windows, <=512 SELECT/window, <=12000 globally and 4h wall. '
                'Header batch <=100, rows <=250 (accredited transport cap); 2MiB fetch payload. '
                'Stop at first effective bound; budgets are not additive or automatically renewable.')


def validate_plan(p):
    if (p['contract'] != CONTRACT or p['budget'] != BUDGET or p['limits'] != asdict(LIMITS)
            or p['windows'] != windows() or p['source'] != 'SAP_B1_HANA/TELCHI'
            or p['authorization'] != 'USER_SALES_CONTINUITY_RECOVERY_V1_SEP_THROUGH_20261029'):
        raise ValueError('unaccredited plan')


def header_sql(domain):
    header, lines = inc.DOMAINS[domain]
    return assert_read_only_select(f'''SELECT TOP 100 {', '.join(header_fields(domain))},
(SELECT COUNT(*) FROM "TELCHI"."{lines}" C WHERE C."DocEntry"=H."DocEntry") AS "ExpectedLines"
FROM "TELCHI"."{header}" H WHERE H."DocDate">=? AND H."DocDate"<?
AND H."DocEntry">? ORDER BY H."DocEntry"''')


def line_sql(domain, entries):
    if not 1 <= len(entries) <= BUDGET['header_documents']:
        raise ValueError('invalid bounded keyset')
    header, lines = inc.DOMAINS[domain]
    return assert_read_only_select(f'''SELECT TOP 250 {inc.projection(domain)}
FROM "TELCHI"."{header}" H JOIN "TELCHI"."{lines}" L ON L."DocEntry"=H."DocEntry"
WHERE H."DocEntry" IN ({','.join('?' for _ in entries)})
AND (H."DocEntry">? OR (H."DocEntry"=? AND L."LineNum">?))
ORDER BY H."DocEntry",L."LineNum"''')


def validate_unit(window, after, headers, rows):
    ids = [int(h['DocEntry']) for h in headers]
    if ids != sorted(set(ids)) or any(i <= after for i in ids) or len(ids) > 100:
        raise ValueError('invalid header order/cursor')
    if any(not window['start'] <= str(h['DocDate'])[:10] < window['end'] or int(h['ExpectedLines']) <= 0 for h in headers):
        raise ValueError('invalid business window or document without lines')
    expected = {int(h['DocEntry']): int(h['ExpectedLines']) for h in headers}
    if Counter(int(r['DocEntry']) for r in rows) != expected:
        raise ValueError('incomplete document lines')
    heads = {int(h['DocEntry']): {k:v for k,v in h.items() if k != 'ExpectedLines'} for h in headers}
    keys = [(int(r['DocEntry']), int(r['LineNum'])) for r in rows]
    if keys != sorted(set(keys)):
        raise ValueError('unordered duplicate lines')
    for row in rows:
        if any(row.get(k) != v for k,v in heads[int(row['DocEntry'])].items()):
            raise ValueError('header changed during extraction')
    return inc.validate_rows(window['domain'], rows, limit=100, after=after)


def recover(root):
    """Hash-verify the journal without HANA. In-flight receipts are replayable."""
    p = inc.read_json(root/'plan.json')
    validate_plan(p)
    receipts, commits = {}, []
    for path in sorted(root.glob('q*.intent.json')):
        key = path.name.split('.')[0]
        intent = inc.read_json(path)
        if intent['plan_sha256'] != inc.digest(p):
            raise ValueError('intent plan binding')
        if not (root/f'{key}.receipt.json').exists():
            raise RuntimeError('UNCERTAIN_REQUEST_NO_AUTOMATIC_RETRY')
        receipt = inc.read_json(root/f'{key}.receipt.json')
        response = root/f'{key}.response.json'
        if (receipt['intent_sha256'] != inc.file_hash(path) or receipt['response_sha256'] != inc.file_hash(response)):
            raise ValueError('query hash mismatch')
        rows = inc.read_json(response)
        bound = 100 if intent['request']['kind'] == 'headers' else 250
        if len(rows) > bound or len(rows) != receipt['rows']:
            raise ValueError('query count mismatch')
        signature = inc.digest(intent['request'])
        if signature in receipts:
            raise ValueError('duplicate physical query')
        receipts[signature] = (key, intent, receipt)
    by_key = {r[0]:r for r in receipts.values()}
    frontiers = {w['id']:-1 for w in p['windows']}
    finished = set()
    for path in sorted(root.glob('u*.commit.json')):
        commit = inc.read_json(path)
        w = next((w for w in p['windows'] if w['id'] == commit['window']), None)
        if w is None or w['id'] in finished or commit['after'] != frontiers[w['id']] or commit['plan_sha256'] != inc.digest(p):
            raise ValueError('unit checkpoint binding')
        hkey = commit['headers']
        hreq = by_key[hkey][1]['request']
        if hreq != dict(window=w['id'], kind='headers', sql=header_sql(w['domain']), params=[w['start'],w['end'],commit['after']]):
            raise ValueError('header request binding')
        headers = inc.read_json(root/f'{hkey}.response.json')
        entries = [int(h['DocEntry']) for h in headers]
        rows, last = [], (-1,-1)
        for key in commit['pages']:
            req = by_key[key][1]['request']
            if req != dict(window=w['id'],kind='lines',sql=line_sql(w['domain'],entries),params=[*entries,last[0],last[0],last[1]]):
                raise ValueError('line request binding')
            page = inc.read_json(root/f'{key}.response.json')
            keys = [(int(r['DocEntry']),int(r['LineNum'])) for r in page]
            if not keys or keys != sorted(set(keys)) or keys[0] <= last:
                raise ValueError('line cursor regression')
            rows.extend(page)
            last = keys[-1]
        metrics = validate_unit(w,commit['after'],headers,rows)
        if commit['metrics'] != metrics or commit['rows_sha256'] != inc.digest(rows) or commit['exhausted'] != (len(headers)<100):
            raise ValueError('unit integrity')
        frontiers[w['id']] = metrics['last_cursor']
        if commit['exhausted']:
            finished.add(w['id'])
        commits.append(commit)
    return p, receipts, commits, frontiers, finished


def run(root, p, source, *, sleep=time.sleep, clock=time.monotonic, guard=None):
    validate_plan(p)
    if source.limits != LIMITS or source.query_log:
        raise ValueError('unexpected source limits')
    guard = guard or ResourceGuard(temp_directory=root.parent.resolve())
    if not root.exists():
        root.mkdir(mode=0o700)
        inc.sync_dir(root.parent)
        inc.seal(root/'plan.json',p)
    with inc.locked(root):
        saved, receipts, commits, cursors, finished = recover(root)
        if saved != p:
            raise ValueError('immutable plan mismatch')
        started, stopped = clock(), []
        handlers = {s:signal.signal(s,lambda signum, frame: stopped.append(signum)) for s in (signal.SIGINT,signal.SIGTERM)}
        counts = Counter(r[1]['request']['window'] for r in receipts.values())
        latencies = [r[2]['audit']['duration_ms'] for r in receipts.values()]
        last_audit = latencies[-5:]
        state = dict(status='PARTIAL',started_at=inc.now(),reason=None)
        def budget():
            wall = (datetime.now(timezone.utc)-datetime.fromisoformat(p['created_at'])).total_seconds()
            if stopped:
                raise RuntimeError('STOP_REQUESTED')
            if wall + 30 + 10 + 120 >= BUDGET['total_seconds']:
                raise RuntimeError('GLOBAL_TIME_BUDGET_STOP')
        def request(w, kind, sql, params):
            req = dict(window=w['id'],kind=kind,sql=sql,params=params)
            signature = inc.digest(req)
            if signature in receipts:
                key = receipts[signature][0]
                return inc.read_json(root/f'{key}.response.json'), key
            budget()
            if len(receipts) >= BUDGET['max_selects'] or counts[w['id']] >= BUDGET['max_window_selects']:
                raise RuntimeError('SELECT_BUDGET_STOP')
            assessment = guard.assess()
            if not assessment.allowed:
                raise RuntimeError('RESOURCE_BLOCKED')
            if len(last_audit) >= 5 and min(last_audit[-5:]) >= 4000:
                raise RuntimeError('SUSTAINED_HANA_DEGRADATION_STOP')
            if receipts:
                sleep(2 if assessment.warnings or (last_audit and last_audit[-1] >= 2000) else .1)
            budget()
            key = f'q{len(receipts)+1:06}'
            intent = dict(plan_sha256=inc.digest(p),request=req,at=inc.now())
            inc.seal(root/f'{key}.intent.json',intent)
            rows = source.query_read_only(f'continuity_{w["domain"]}_{kind}',sql,tuple(params))
            persistence = clock()
            inc.seal(root/f'{key}.response.json',rows)
            receipt = dict(intent_sha256=inc.file_hash(root/f'{key}.intent.json'),
                           response_sha256=inc.file_hash(root/f'{key}.response.json'),rows=len(rows),
                           audit=source.query_log[-1],persistence_seconds=clock()-persistence)
            inc.seal(root/f'{key}.receipt.json',receipt)
            receipts[signature] = (key,intent,receipt)
            counts[w['id']] += 1
            last_audit.append(receipt['audit']['duration_ms']); del last_audit[:-5]
            if clock()-persistence > 10:
                raise RuntimeError('PERSISTENCE_BUDGET_STOP')
            if not receipt['audit']['cursor_closed'] or not receipt['audit']['connection_closed']:
                raise RuntimeError('RESOURCE_CLOSURE_STOP')
            return rows,key
        try:
            for w in p['windows']:
                if w['id'] in finished:
                    continue
                while w['id'] not in finished:
                    after = cursors[w['id']]
                    headers,hkey = request(w,'headers',header_sql(w['domain']),[w['start'],w['end'],after])
                    entries = [int(h['DocEntry']) for h in headers]
                    rows, pages, last = [], [], (-1,-1)
                    expected = sum(int(h['ExpectedLines']) for h in headers)
                    if any(int(h['ExpectedLines']) <= 0 for h in headers):
                        raise ValueError('document without lines')
                    while len(rows) < expected:
                        page,key = request(w,'lines',line_sql(w['domain'],entries),[*entries,last[0],last[0],last[1]])
                        keys = [(int(r['DocEntry']),int(r['LineNum'])) for r in page]
                        if not keys or keys != sorted(set(keys)) or keys[0] <= last:
                            raise ValueError('nonadvancing line cursor')
                        rows.extend(page); pages.append(key); last = keys[-1]
                    persist = clock()
                    metrics = validate_unit(w,after,headers,rows)
                    validation, reconciliation = {}, {}
                    if rows:
                        candidate = inc.transform_capture(w['domain'],rows,dict(extraction_id=root.name,source_as_of=inc.now()))
                        validation = inc.validate_candidate(candidate,max(2500,len(rows)))
                        if validation['status'] != 'PASS':
                            raise ValueError('transform validation failed')
                        reconciliation = inc.reconcile_candidate(candidate,candidate.source_rows)
                    commit = dict(plan_sha256=inc.digest(p),window=w['id'],domain=w['domain'],after=after,
                                  headers=hkey,pages=pages,metrics=metrics,rows_sha256=inc.digest(rows),
                                  exhausted=len(headers)<100,validation=validation,reconciliation=reconciliation,
                                  committed_at=inc.now(),persistence_seconds=clock()-persist)
                    inc.seal(root/f'u{len(commits)+1:06}.commit.json',commit)
                    commits.append(commit)
                    cursors[w['id']] = metrics['last_cursor']
                    if commit['exhausted']:
                        finished.add(w['id'])
                        print(json.dumps(dict(window=w['id'],complete=True,units=len(commits),selects=len(receipts))),flush=True)
                    if clock()-persist > 10:
                        raise RuntimeError('PERSISTENCE_BUDGET_STOP')
            state.update(status='CAPTURED_PASS',reason='ALL_AUTHORIZED_WINDOWS_COMPLETE')
        except BaseException as exc:
            state.update(reason=type(exc).__name__,code=str(exc) if isinstance(exc,RuntimeError) else 'INTEGRITY_REVIEW_REQUIRED')
        finally:
            for s,h in handlers.items():
                signal.signal(s,h)
            state.update(finished_at=inc.now(),elapsed_seconds=clock()-started,queries_this_session=source.query_log,
                         total_selects=len(receipts),completed_windows=sorted(finished),units=len(commits),
                         metrics={d:{k:sum(c['metrics'][k] for c in commits if c['domain']==d) for k in ('documents','lines','cancellations')} for d in inc.DOMAINS},
                         incomplete_windows=[w['id'] for w in p['windows'] if w['id'] not in finished],
                         global_change_watermark=None,publication='NOT_ATTEMPTED')
            inc.seal(root/f'session-{uuid.uuid4().hex}.json',state)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['run','recover'])
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--authorize-hana',action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    allowed = (inc.DATA_ROOT/'raw'/'sap'/CONTRACT).resolve()
    if root.parent != allowed:
        parser.error('destination must be contract-owned DATA_ROOT child')
    if args.action == 'recover':
        with inc.locked(root):
            p,receipts,commits,cursors,finished = recover(root)
        print(json.dumps(dict(selects=len(receipts),units=len(commits),completed_windows=sorted(finished))))
        return 0
    if not args.authorize_hana:
        parser.error('explicit HANA authorization required')
    from . import sales_controlled_block as block
    pilot = inc.DATA_ROOT/'raw/sap'/inc.CONTRACT/'sales-pilot-20261029-v1'
    second = inc.DATA_ROOT/'raw/sap'/block.CONTRACT/'sales-second-block-20261029-v1'
    allowed.mkdir(parents=True,exist_ok=True)
    # Same shared extraction lock as the accredited second block, not a parallel namespace.
    with extraction_lock(second.parent):
        with inc.locked(pilot):
            inc.recover(pilot,inc.read_json(pilot/'plan.json'))
        block.recover(second)
        p = inc.read_json(root/'plan.json') if root.exists() else make_plan({
            'pilot_plan':inc.file_hash(pilot/'plan.json'), 'second_plan':inc.file_hash(second/'plan.json'),
            'second_units':{f.name:inc.file_hash(f) for f in second.glob('unit*.commit.json')}})
        assert hana_config()['schema'] == 'TELCHI'
        state = run(root,p,SalesSource())
    print(json.dumps(state,default=str),flush=True)
    return 0 if state['status'] == 'CAPTURED_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
