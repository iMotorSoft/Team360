"""Bounded invoice facts and historical document amounts from CURRENT.

Knowledge: historical inventory F08/F09 and sales_exact_document. Authorization
belongs to the handler; these operations require distinct commercial grants.
"""
import asyncio
import json
import signal
import sys
from datetime import date, datetime
from time import perf_counter

from .messaging_sales_query import TelchiQueryError
from .query_profile import Trace, enabled as profile_enabled, span

PUBLICATION = 'foundation_38680850adc058b1bb11887632b7b681'
SNAPSHOT = 1408
# Reviewed physical-only successor retains the exact sales and NC contracts.
PHYSICAL_SUCCESSOR_PUBLICATION = 'foundation_881005a5a694a25dc806233dcb3838ac'
MONETARY_PERMISSION = 'telchi.sales.period_billed_amount.read.v1'
MONETARY_OPERATION = 'sales.period_billed_amount'
PERMISSIONS = {
    'sales.latest_documents': 'telchi.sales.latest_documents.read.v1',
    'sales.coverage': 'telchi.sales.coverage.read.v1',
}
SQL = {
    MONETARY_OPERATION: '''WITH invoices AS (
SELECT COUNT(*) documents,COUNT(DISTINCT doc_entry) unique_documents,COUNT(doc_total) amount_documents,
COALESCE(SUM(CAST(doc_total AS DECIMAL(38,6))),0) amount
FROM {documents} WHERE source_system=? AND canceled=? AND currency=? AND doc_date>=? AND doc_date<? {channel_filter}
), credits AS (
SELECT COUNT(*) documents,COUNT(DISTINCT doc_entry) unique_documents,COUNT(doc_total) amount_documents,
COALESCE(SUM(CAST(doc_total AS DECIMAL(38,6))),0) amount
FROM {credits} WHERE source_system=? AND canceled=? AND currency=? AND doc_date>=? AND doc_date<? {channel_filter}
)
SELECT i.documents invoice_count,i.unique_documents unique_invoices,i.amount billed_amount,
c.documents credit_count,c.unique_documents unique_credits,c.amount credit_amount,
i.amount-c.amount net_amount,i.amount_documents invoice_amount_count,c.amount_documents credit_amount_count
FROM invoices i CROSS JOIN credits c''',
    'sales.latest_documents': '''SELECT source_system,doc_entry,doc_num,doc_date,canceled
FROM {documents}
WHERE source_system=? AND canceled=? AND doc_date IS NOT NULL
ORDER BY doc_date DESC,CAST(doc_entry AS BIGINT) DESC,doc_entry DESC LIMIT ?''',
    'sales.coverage': '''SELECT MIN(doc_date) AS first_date,MAX(doc_date) AS last_date,COUNT(*) AS documents
FROM {documents} WHERE source_system=? AND canceled=? AND doc_date IS NOT NULL''',
}


def parameters(operation, options):
    if operation not in SQL or not isinstance(options, dict):
        raise ValueError('unsupported_sales_operation')
    if operation == MONETARY_OPERATION:
        if (set(options) - {'date_from', 'date_to_exclusive', 'currency', 'sales_channel'}
                or not {'date_from', 'date_to_exclusive', 'currency'} <= set(options)
                or options['currency'] != 'BS'
                or ('sales_channel' in options and options['sales_channel'] != 'HORIZONTAL')):
            raise ValueError('unsupported_monetary_parameters')
        start, end = (date.fromisoformat(options[k]) for k in ('date_from', 'date_to_exclusive'))
        if (start.isoformat() != options['date_from'] or end.isoformat() != options['date_to_exclusive']
                or not 0 < (end-start).days <= 366):
            raise ValueError('invalid_monetary_period')
        return (['SAP_B1_HANA', 'N', 'BS', start.isoformat(), end.isoformat()]
                + ([options['sales_channel']] if 'sales_channel' in options else [])) * 2
    if set(options) - ({'limit'} if operation == 'sales.latest_documents' else set()):
        raise ValueError('unsupported_sales_parameters')
    values = ['SAP_B1_HANA', 'N']
    if operation == 'sales.latest_documents':
        limit = options.get('limit', 10)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('invalid_sales_limit')
        values.append(limit)
    return values


def execute_query(operation, options, connector=None):
    values = parameters(operation, options)
    from .ducklake import DuckLakeConnector
    from .foundation_reader import FoundationReader
    connector = connector or DuckLakeConnector()
    with connector.session(read_only=True) as connection:
        connection.execute('SET threads=2')
        connection.execute("SET memory_limit='512MB'")
        connection.execute("SET max_temp_directory_size='0B'")
        readonly = connection.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone()
        if readonly is None or readonly[0] is not True:
            raise TelchiQueryError('datalake_not_read_only')
        access = FoundationReader(connector).resolve_on(connection)
        from .sales_succession import admit, source_metadata
        admit(access, connection)
        channel = options.get('sales_channel')
        documents, credits = access.sales('sales_document'), access.credit_memo('credit_memo_document')
        if channel:
            # Do not silently omit tagged rows whose semantic status is missing or degraded.
            for relation in (documents, credits):
                invalid = connection.execute(f'''SELECT COUNT(*) FROM {relation}
                    WHERE source_system=? AND canceled=? AND currency=? AND doc_date>=? AND doc_date<?
                    AND sales_channel_code=? AND sales_channel_semantic_status IS DISTINCT FROM 'CONFIRMED' ''',
                    values[:6]).fetchone()[0]
                if invalid:
                    raise TelchiQueryError('sales_channel_not_confirmed')
        sql = SQL[operation].format(documents=documents, credits=credits,
            channel_filter='AND sales_channel_code=?' if channel else '')
        started = perf_counter()
        with span('sales_sql_execution'):
            cursor = connection.execute(sql, values)
        with span('sales_fetch'):
            names = [c[0] for c in cursor.description]
            rows = [dict(zip(names, row)) for row in cursor.fetchall()]
        elapsed = (perf_counter() - started) * 1000
    # Dates are source strings/timestamps; no periods derived from today's clock.
    with span('sales_serialization'):
        rows = json.loads(json.dumps(rows, default=str))
    if operation == MONETARY_OPERATION:
        row = rows[0]
        if (row['invoice_count'] != row['unique_invoices'] or row['credit_count'] != row['unique_credits']
                or row['invoice_count'] != row['invoice_amount_count'] or row['credit_count'] != row['credit_amount_count']):
            raise TelchiQueryError('duplicate_monetary_documents')
        return dict(capability=operation+'.v1', rows=rows, period=dict(options), currency='BS',
                    definition='SALES_VALID_GROSS=active OINV DocTotal; SALES_NET=SALES_VALID_GROSS-active ORIN DocTotal',
                    source=source_metadata(access),
                    read_only=True, sap_accessed=False, sql=sql, sql_parameters=values,
                    sql_duration_ms=elapsed, grain='document_header',
                    limitations='DocDate; active N; BS only; DocTotal retains source taxes/discounts. Not cash collections. Historical completeness and separate tax/discount reconciliation not certified.',
                    **(dict(sales_channel=channel, channel_semantic_status='CONFIRMED',
                        channel_basis='materialized DMS numbering series; not customer or salesperson type',
                        channel_limitations='DMS/U_ORIGIN census reconciliation, cross-channel credit attribution and unposted DMS returns completeness not certified.') if channel else {}))
    if operation == 'sales.coverage':
        rows[0]['latest_month_with_rows'] = rows[0]['last_date'][:7] if rows[0]['last_date'] else None
        rows[0]['complete_month_certified'] = False
    return dict(capability=operation + '.v1', rows=rows,
                source=source_metadata(access),
                read_only=True, sap_accessed=False, sql=sql, sql_parameters=values,
                sql_duration_ms=elapsed, grain='invoice_header', document_type='OINV',
                limitations='Active invoices (N), by DocDate, not entry timestamp; excludes credit memos. Not net sales. Completeness not certified.')


def validate_result(operation, options, result):
    from .sales_succession import accepts_result, admitted_source
    values = parameters(operation, options)
    if (result.get('capability') != operation + '.v1' or result.get('read_only') is not True
            or result.get('sap_accessed') is not False
            or not accepts_result(result.get('source', {}), {(PUBLICATION, SNAPSHOT), (PHYSICAL_SUCCESSOR_PUBLICATION, SNAPSHOT)},
                                  _admitted=admitted_source(result))
            or result.get('sql_parameters') != values or not isinstance(result.get('rows'), list)):
        raise ValueError('invalid_sales_result')
    rows = result['rows']
    if operation == MONETARY_OPERATION:
        from decimal import Decimal
        if (len(rows) != 1 or result.get('period') != options or result.get('currency') != 'BS'
                or result.get('grain') != 'document_header'):
            raise ValueError('invalid_monetary_result')
        if options.get('sales_channel'):
            if (result.get('sales_channel') != options['sales_channel']
                    or result.get('channel_semantic_status') != 'CONFIRMED'
                    or not result.get('channel_basis') or not result.get('channel_limitations')):
                raise ValueError('invalid_monetary_channel')
        elif result.get('sales_channel') is not None:
            raise ValueError('unexpected_monetary_channel')
        updated = result.get('source', {}).get('updated_at')
        if not isinstance(updated, str) or not updated:
            raise ValueError('monetary_update_date_missing')
        datetime.fromisoformat(updated)
        row = rows[0]
        for key in ('invoice_count', 'credit_count', 'unique_invoices', 'unique_credits', 'invoice_amount_count', 'credit_amount_count'):
            if type(row.get(key)) is not int or row[key] < 0:
                raise ValueError('invalid_monetary_count')
        amounts = [Decimal(row[k]) for k in ('billed_amount', 'credit_amount', 'net_amount')]
        if (any(not a.is_finite() for a in amounts) or amounts[0]-amounts[1] != amounts[2]
                or row['invoice_count'] != row['unique_invoices'] or row['credit_count'] != row['unique_credits']
                or row['invoice_count'] != row['invoice_amount_count'] or row['credit_count'] != row['credit_amount_count']):
            raise ValueError('invalid_monetary_integrity')
    elif operation == 'sales.coverage':
        if len(rows) != 1 or type(rows[0].get('documents')) is not int or rows[0]['documents'] < 0:
            raise ValueError('invalid_sales_coverage')
        row = rows[0]
        first, last = row.get('first_date'), row.get('last_date')
        if row.get('complete_month_certified') is not False:
            raise ValueError('uncertified_sales_completeness')
        if row['documents'] == 0:
            if any(row.get(k) is not None for k in ('first_date', 'last_date', 'latest_month_with_rows')):
                raise ValueError('invalid_empty_coverage')
        elif (not isinstance(first, str) or not isinstance(last, str)
              or date.fromisoformat(first[:10]) > date.fromisoformat(last[:10])
              or row.get('latest_month_with_rows') != last[:7]):
            raise ValueError('invalid_sales_coverage_dates')
    else:
        if len(rows) > values[-1]:
            raise ValueError('sales_limit_exceeded')
        keys = []
        for row in rows:
            if (row.get('source_system') != 'SAP_B1_HANA' or row.get('canceled') != 'N'
                    or not isinstance(row.get('doc_entry'), str) or not row['doc_entry'].isdigit()
                    or not isinstance(row.get('doc_num'), str)):
                raise ValueError('invalid_sales_document')
            timestamp = datetime.fromisoformat(row['doc_date'])
            keys.append((timestamp, int(row['doc_entry']), row['doc_entry']))
        if len(keys) != len(set(keys)) or keys != sorted(keys, reverse=True):
            raise ValueError('invalid_sales_order')
    return result


_LOCK = asyncio.Lock()


async def query_sales(operation, options, *, timeout_seconds=60):
    parameters(operation, options)  # reject before spawning or touching Foundation
    if _LOCK.locked():
        raise TelchiQueryError('datalake_busy')
    async with _LOCK:
        started = perf_counter()
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', __name__, operation, json.dumps(options),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            remaining = max(0.001, timeout_seconds - (perf_counter() - started))
            stdout, _ = await asyncio.wait_for(process.communicate(), remaining)
            if process.returncode:
                raise TelchiQueryError('sales_worker_error')
            envelope = json.loads(stdout)
            if 'result' not in envelope:
                raise TelchiQueryError('sales_query_unavailable')
            result = validate_result(operation, options, envelope['result'])
            if profile_enabled():
                result['worker_lifecycle'] = dict(timeout_seconds=timeout_seconds,
                    deadline_monotonic=started + timeout_seconds,
                    elapsed_ms=(perf_counter()-started)*1000,
                    response_bytes=len(stdout), returned_rows=len(result['rows']),
                    canceled=False, worker_reaped=process.returncode is not None)
            from .sales_succession import mark_result
            return mark_result(result)
        finally:
            if process.returncode is None:
                process.terminate()  # Python validation unwinds its connection context.
                try:
                    await asyncio.wait_for(process.wait(), 2)
                except asyncio.TimeoutError:
                    # Native calls may not service Python signals promptly.
                    process.kill()
                    await process.wait()


def _cancel_worker(signum, frame):
    raise InterruptedError('sales_worker_canceled')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _cancel_worker)
    try:
        if profile_enabled():
            trace = Trace()
            with trace.activate():
                result = execute_query(sys.argv[1], json.loads(sys.argv[2]))
            result['query_profile'] = trace.export()
            print(json.dumps({'result': result}))
        else:
            print(json.dumps({'result': execute_query(sys.argv[1], json.loads(sys.argv[2]))}))
    except Exception:
        print(json.dumps({'error': 'sales_query_unavailable'}))
