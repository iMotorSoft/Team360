"""Explicit recovery diagnostics for a source that advanced during a cursor.

Does not promote a failed segment to complete and never publishes. Proves the
captured native-key prefix separately, retaining the original failure and the
fact that the entire business-date window is not closed at a global cutoff.
"""
from pathlib import Path
from decimal import Decimal
import re

from . import sales_incremental as durable
from .raw import digest, file_hash
from modules.telchi.runtime.config import open_safe_duckdb


def reconcile_prefix(session, directory, *, native_field):
    directory = Path(directory)
    if not re.fullmatch(r'[A-Z]\."[A-Za-z_][A-Za-z0-9_]*"', native_field):
        raise ValueError('EXPLICIT_SOURCE_KEY_REQUIRED')
    with durable.locked(directory):
        intent = durable.read_json(directory/'intent.json')
        failure = durable.read_json(directory/'failure.json')
        if failure.get('code') != 'SOURCE_CONTROL_CHANGED_OR_CAPTURE_MISMATCH':
            raise ValueError('NOT_A_SOURCE_ADVANCE_RECONCILIATION')
        checkpoints = [durable.read_json(p) for p in sorted(directory.glob('checkpoint-*.json'))]
        if not checkpoints:
            raise ValueError('NO_REUSABLE_ROWS')
        files = []
        for page in checkpoints:
            manifest = durable.read_json(Path(page['manifest_path']))
            unsigned = dict(manifest)
            unsigned.pop('manifest_hash')
            if digest(unsigned) != page['manifest_hash'] or manifest['manifest_hash'] != page['manifest_hash']:
                raise ValueError('MANIFEST_CHANGED')
            if file_hash(Path(page['path'])) != page['sha256']:
                raise ValueError('RAW_BYTES_CHANGED')
            files.append(page['path'])
        plan = intent['plan']
        if digest(plan) != intent['plan_sha256']:
            raise ValueError('PLAN_CHANGED')
        first_key = plan['keys'][0]
        sums = plan['sums']
        sql = plan['sql']
        # Only the known single SELECT builders with one WHERE are eligible.
        if sql.upper().count('WHERE') != 1 or 'UNION' in sql.upper():
            raise ValueError('SIMPLE_NATIVE_KEY_QUERY_REQUIRED')
        body = re.split(r'\s+ORDER BY\s+', sql, flags=re.I)[0]
        db = open_safe_duckdb(profile=session.profile)
        try:
            columns = ['COUNT(*)', f'MAX("{first_key}")'] + [f'SUM(CAST("{s}" AS DECIMAL(38,12)))' for s in sums]
            observed = db.execute('SELECT ' + ','.join(columns) + ' FROM read_parquet(?, union_by_name=true)', [files]).fetchone()
        finally:
            db.close()
        total, upper, *totals = observed
        if total != failure['captured_rows'] or total != sum(p['rows'] for p in checkpoints):
            raise ValueError('CAPTURE_ROWS_CHANGED')
        bounded_body = body + ' AND ' + native_field + ' <= ?'
        control_sql = 'SELECT COUNT(*) AS "rows"' + ''.join(f',SUM(Q."{s}") AS "sum_{s}"' for s in sums) + ' FROM (' + bounded_body + ') Q'
        control = session.query(directory.name+'_prefix_revalidation', control_sql, tuple(plan['params'])+(upper,))[0]
        if int(control['rows']) != total or any(Decimal(str(control['sum_'+s] or 0)) != (value or Decimal(0)) for s,value in zip(sums, totals)):
            raise ValueError('FROZEN_PREFIX_CHANGED')
        result = dict(status='FROZEN_PREFIX_RECONCILED_NOT_PUBLISHED', row_count=total, upper_native_key=upper,
            first_key=first_key, source_control=control, sql=control_sql, params=plan['params']+[upper],
            checkpoint_hashes=[durable.file_hash(p) for p in sorted(directory.glob('checkpoint-*.json'))],
            original_intent_sha256=durable.file_hash(directory/'intent.json'),
            original_failure_sha256=durable.file_hash(directory/'failure.json'),
            captured_observation_start=intent['source_before'], reconciled_at=durable.now(),
            coverage_complete=False, published=False, recaptured_rows=0,
            limitation='Only this observed native-key prefix; not all later documents/events in the business window')
        durable.seal(directory/'prefix-reconciliation.json', result)
        return result
