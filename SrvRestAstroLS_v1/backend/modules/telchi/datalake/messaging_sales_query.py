"""Promoted fixed sales_top_items read for the DEV Messaging SQL gate.

Semantics/SQL: datalake_direct_business_query_validation_v1/query_registry,
EXACT evidence, cutoff 2026-09-15. Only relations change to Foundation pins.
No investigation imports, SAP, user parameters, publication or mutation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time

from .query_profile import Trace, enabled, measured, span

CAPABILITY = 'telchi.sales_top_items.source_quantity.20260101_20260915.v1'
PERIOD_FROM = '2026-01-01'
PERIOD_TO_EXCLUSIVE = '2026-09-16'
SQL_TEMPLATE = ('SELECT l.item_code,COUNT(*) AS lines,'
    'COALESCE(SUM(CAST(l.quantity AS DECIMAL(38,10))),0) AS quantity,'
    'COALESCE(SUM(CAST(l.line_total AS DECIMAL(38,10))),0) AS line_total '
    'FROM {documents} h JOIN {lines} l ON l.doc_entry=h.doc_entry '
    'WHERE h."doc_date" >= ? AND h."doc_date" < ? '
    'GROUP BY l.item_code ORDER BY quantity DESC,l.item_code LIMIT 10')
QUERY_HASH = hashlib.sha256((SQL_TEMPLATE + PERIOD_FROM + PERIOD_TO_EXCLUSIVE).encode()).hexdigest()


class TelchiQueryError(Exception):
    """Code only; never expose driver/SQL/connection exception text."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def execute_fixed_query(connector=None):
    with span('capability_imports'):
        from .ducklake import DuckLakeConnector
        from .foundation_reader import FoundationReader

    connector = connector or measured('connector_configuration', DuckLakeConnector)
    with connector.session(read_only=True) as connection:
        # Small fixed budget in this task-owned connection, not server settings.
        with span('query_budget_setup'):
            connection.execute("SET threads=2")
            connection.execute("SET memory_limit='512MB'")
            connection.execute("SET max_temp_directory_size='0B'")
        # Verify the effective attachment, not merely a requested flag.
        with span('read_only_verification'):
            attached = connection.execute(
                "SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'"
            ).fetchone()
        if attached is None or attached[0] is not True:
            raise TelchiQueryError('datalake_not_read_only')
        access = measured('foundation_resolution', FoundationReader(connector).resolve_on, connection)
        with span('query_preparation'):
            sql = SQL_TEMPLATE.format(documents=access.sales('sales_document'), lines=access.sales('sales_line'))
        t2 = time.time_ns() / 1_000_000
        started = time.perf_counter()
        cursor = measured('duckdb_sql_execute', connection.execute, sql, [PERIOD_FROM, PERIOD_TO_EXCLUSIVE])
        rows = measured('fetch', cursor.fetchall)
        elapsed = (time.perf_counter() - started) * 1000
        t3 = time.time_ns() / 1_000_000
        with span('materialization'):
            records = [{'item_code': row[0], 'lines': int(row[1]),
                        'quantity': str(row[2]), 'line_total': str(row[3])} for row in rows]
    with span('result_hash'):
        result_hash = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
    return {'capability': CAPABILITY, 'query_hash': QUERY_HASH,
            'executed_sql_hash': hashlib.sha256(sql.encode()).hexdigest(),
            'period_from': PERIOD_FROM, 'period_to_exclusive': PERIOD_TO_EXCLUSIVE,
            'foundation_publication_id': access.foundation_publication_id,
            'ducklake_snapshot_id': access.ducklake_snapshot_id,
            'foundation_data_as_of': access.foundation_data_as_of,
            'read_only': True, 'sap_accessed': False,
            'sql_started_ms': t2, 'sql_finished_ms': t3, 'sql_duration_ms': elapsed,
            'foundation_resolution_ms': access.foundation_resolution_ms,
            'row_count': len(records), 'result_hash': result_hash, 'rows': records}


_QUERY_LOCK = asyncio.Lock()


async def query_fixed_sales(*, timeout_seconds=30):
    """One gate worker per runtime; reject overlap rather than creating a queue."""
    if _QUERY_LOCK.locked():
        raise TelchiQueryError('datalake_busy')
    async with _QUERY_LOCK:
        return await _query_in_worker(timeout_seconds=timeout_seconds)


async def _query_in_worker(*, timeout_seconds):
    """A bounded own worker: cancellation/timeout reaps it; SQL cannot outlive reply.

    This is a per-call execution boundary, not a queue, broker or daemon. DuckLake
    uses process-global PGPASSWORD; isolation also prevents concurrent callers
    racing the existing connector's environment restoration.
    """
    profile_start = time.perf_counter_ns()
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-m', __name__, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    spawn_end = time.perf_counter_ns()
    try:
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout_seconds)
        except asyncio.TimeoutError:
            raise TelchiQueryError('datalake_timeout') from None
        if process.returncode:
            raise TelchiQueryError('datalake_worker_error')
        try:
            envelope = json.loads(stdout)
            if 'error' in envelope:
                raise TelchiQueryError(envelope['error'])
            result = envelope['result']
            if enabled() and 'profile' in result:
                end = time.perf_counter_ns()
                result['profile']['parent'] = {
                    'spawn_ms': (spawn_end-profile_start)/1e6,
                    'worker_entry_ms': (envelope['worker_entry_ns']-profile_start)/1e6,
                    'total_ms': (end-profile_start)/1e6,
                    'ipc_exit_decode_residual_ms': (end-profile_start)/1e6
                        - (envelope['worker_entry_ns']-profile_start)/1e6
                        - result['profile']['total_ms'],
                    'ipc': 'stdout JSON, communicate waits for exit',
                    'worker_pid': process.pid}
            return result
        except (ValueError, KeyError):
            raise TelchiQueryError('datalake_invalid_result') from None
    finally:
        if process.returncode is None:
            process.kill()  # exact child created above, never an existing process
            await process.wait()


def _worker():
    try:
        entry = time.perf_counter_ns()
        if enabled():
            trace = Trace()
            with trace.activate():
                result = execute_fixed_query()
            result['profile'] = trace.export()
            print(json.dumps({'result': result, 'worker_entry_ns': entry}))
        else:
            result = execute_fixed_query()
            print(json.dumps({'result': result}))
    except Exception as exc:
        # Inspect only exception class, never stringify exceptions/DSNs/SQL.
        import duckdb
        code = (exc.code if isinstance(exc, TelchiQueryError) else
                'datalake_connection_error' if isinstance(exc, (ConnectionError, OSError, duckdb.IOException))
                else 'datalake_query_error')
        print(json.dumps({'error': code}))


if __name__ == '__main__':
    _worker()
