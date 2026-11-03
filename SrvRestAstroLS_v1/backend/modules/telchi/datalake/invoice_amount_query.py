"""One active invoice's published header total. No line reconstruction or tax inference."""
import asyncio
from decimal import Decimal
import json
import sys

from .invoice_lines_query import parameters
from .messaging_sales_query import TelchiQueryError

CAPABILITY = 'sales.invoice_amount.v1'
PERMISSION = 'telchi.sales.invoice_amount.read.v1'


def validate_result(options, result):
    parameters(options)
    if (result.get('capability') != CAPABILITY or result.get('parameters') != options
            or result.get('read_only') is not True or result.get('sap_accessed') is not False
            or result.get('source', {}).get('publication_id') != options['publication_id']
            or result.get('source', {}).get('snapshot_id') != options['snapshot_id']
            or not isinstance(result.get('source', {}).get('updated_at'), str)
            or not result['source']['updated_at']
            or result.get('document') != {k: options[k] for k in ('source_system', 'document_type', 'doc_entry', 'doc_num', 'doc_date')}
            or not isinstance(result.get('rows'), list) or len(result['rows']) != 1):
        raise ValueError('invalid_invoice_amount_result')
    row = result['rows'][0]
    if (set(row) != {'amount', 'currency'} or not isinstance(row['amount'], str)
            or not Decimal(row['amount']).is_finite()
            or not isinstance(row['currency'], str) or not row['currency'].strip()):
        raise ValueError('invalid_invoice_amount')
    return result


def execute_query(options, connector=None):
    parameters(options)
    from .ducklake import DuckLakeConnector
    from .foundation_reader import FoundationReader
    connector = connector or DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        if con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() != (True,):
            raise TelchiQueryError('datalake_not_read_only')
        access = FoundationReader(connector).resolve_on(con)
        if (access.foundation_publication_id, access.ducklake_snapshot_id) != (options['publication_id'], options['snapshot_id']):
            raise TelchiQueryError('invoice_publication_changed')
        docs = access.sales('sales_document')
        headers = con.execute(f'''SELECT doc_num,doc_date,canceled,doc_total,currency,raw_extraction_id,source_as_of
            FROM {docs} WHERE source_system=? AND doc_entry=? AND source_table='OINV' ''',
            [options['source_system'], options['doc_entry']]).fetchall()
        if len(headers) != 1 or headers[0][:3] != (options['doc_num'], options['doc_date'], 'N'):
            raise TelchiQueryError('invoice_missing_changed_or_canceled')
        _, _, _, total, currency, extraction, as_of = headers[0]
        if total is None or not currency or not extraction or not as_of:
            raise TelchiQueryError('invoice_amount_or_lineage_missing')
        result = dict(capability=CAPABILITY, parameters=options,
            document={k: options[k] for k in ('source_system', 'document_type', 'doc_entry', 'doc_num', 'doc_date')},
            rows=[dict(amount=str(total), currency=currency)], read_only=True, sap_accessed=False,
            source=dict(publication_id=access.foundation_publication_id, snapshot_id=access.ducklake_snapshot_id,
                        updated_at=access.foundation_data_as_of),
            amount_source='OINV.DocTotal', source_as_of=as_of, raw_extraction_id=extraction,
            limitations='Published active invoice header total in its native currency. Not collections or outstanding balance. No inferred tax breakdown or line reconstruction.')
    return validate_result(options, result)


_LOCK = asyncio.Lock()


async def query_invoice_amount(options, *, timeout_seconds=30):
    parameters(options)
    if _LOCK.locked():
        raise TelchiQueryError('datalake_busy')
    async with _LOCK:
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', __name__, json.dumps(options),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout_seconds)
            if process.returncode:
                raise TelchiQueryError('invoice_amount_worker_error')
            return validate_result(options, json.loads(output)['result'])
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


if __name__ == '__main__':
    try:
        print(json.dumps({'result': execute_query(json.loads(sys.argv[1]))}))
    except Exception:
        print(json.dumps({'error': 'invoice_amount_unavailable'}))
        sys.exit(1)
