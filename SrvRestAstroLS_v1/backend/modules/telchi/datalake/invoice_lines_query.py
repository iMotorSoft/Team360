"""Read one validated OINV in its original Foundation publication, never latest.

Producer create_initial._sales_candidate binds SAP_B1_HANA/OINV to INV1.
Reference OITM supplies a catalog description, not the historic invoice wording
or physical line UoM. Neither amounts nor conversions are in this contract.
"""
import asyncio
from decimal import Decimal
import json
import sys

from .sales_query import PUBLICATION, SNAPSHOT
from .messaging_sales_query import TelchiQueryError

CAPABILITY = 'sales.invoice_lines.v1'
PERMISSION = 'telchi.sales.invoice_lines.read.v1'


def parameters(options):
    if (not isinstance(options, dict) or set(options) != {
            'source_system', 'document_type', 'doc_entry', 'doc_num', 'doc_date',
            'publication_id', 'snapshot_id'}
            or options['source_system'] != 'SAP_B1_HANA' or options['document_type'] != 'OINV'
            or options['publication_id'] != PUBLICATION or options['snapshot_id'] != SNAPSHOT
            or any(not isinstance(options[k], str) or not options[k] or len(options[k]) > 80
                   for k in ('doc_entry', 'doc_num', 'doc_date'))
            or not options['doc_entry'].isascii() or not options['doc_entry'].isdigit()):
        raise ValueError('invalid_invoice_reference')
    return options


def validate_result(options, result):
    parameters(options)
    if (result.get('capability') != CAPABILITY or result.get('parameters') != options
            or result.get('read_only') is not True or result.get('sap_accessed') is not False
            or result.get('source', {}).get('publication_id') != options['publication_id']
            or result.get('source', {}).get('snapshot_id') != options['snapshot_id']
            or not isinstance(result.get('source', {}).get('updated_at'), str)
            or not result['source']['updated_at'] or not isinstance(result.get('rows'), list)
            or result.get('document') != {k: options[k] for k in ('source_system', 'document_type', 'doc_entry', 'doc_num', 'doc_date')}):
        raise ValueError('invalid_invoice_result')
    order = []
    for row in result['rows']:
        if (not isinstance(row, dict) or set(row) != {'line_num', 'item_code', 'description', 'quantity', 'unit', 'description_source', 'source_as_of'}
                or type(row['line_num']) is not int or row['line_num'] < 0
                or not isinstance(row['item_code'], str) or not row['item_code']
                or (row['description'] is not None and not isinstance(row['description'], str))
                or row['unit'] is not None or row['description_source'] != 'Foundation reference.products SAP_HANA'
                or not isinstance(row['source_as_of'], str) or not row['source_as_of']
                or not isinstance(row['quantity'], str) or not Decimal(row['quantity']).is_finite()):
            raise ValueError('invalid_invoice_line')
        order.append(row['line_num'])
    if order != sorted(set(order)):
        raise ValueError('invalid_invoice_line_order')
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
        docs, lines = access.sales('sales_document'), access.sales('sales_line')
        key = [options['source_system'], options['doc_entry']]
        headers = con.execute(f"SELECT doc_num,doc_date,canceled,raw_extraction_id,source_as_of FROM {docs} WHERE source_system=? AND doc_entry=? AND source_table='OINV'", key).fetchall()
        if len(headers) != 1 or headers[0][:3] != (options['doc_num'], options['doc_date'], 'N'):
            raise TelchiQueryError('invoice_missing_changed_or_canceled')
        extraction, as_of = headers[0][3:]
        if not extraction or not as_of:
            raise TelchiQueryError('invoice_lineage_missing')
        cur = con.execute(f"SELECT line_num,item_code,quantity,source_as_of,raw_extraction_id FROM {lines} WHERE source_system=? AND doc_entry=? AND source_table='INV1'", key)
        raw = cur.fetchall()
        if any(r[3:] != (as_of, extraction) for r in raw):
            raise TelchiQueryError('invoice_lineage_mismatch')
        codes = list({r[1] for r in raw})
        catalog = con.execute("SELECT item_code,coalesce(sap_item_name,product_name,canonical_name) FROM read_parquet(?) WHERE source_system='SAP_HANA' AND item_code IN (SELECT unnest(?))", [str(access.reference('products')), codes]).fetchall() if codes else []
        if len(catalog) != len({r[0] for r in catalog}):
            raise TelchiQueryError('ambiguous_invoice_product')
        descriptions = dict(catalog)
        rows = [dict(line_num=int(r[0]), item_code=r[1], quantity=r[2], source_as_of=r[3],
                     description=descriptions.get(r[1]), unit=None,
                     description_source='Foundation reference.products SAP_HANA') for r in raw]
        rows.sort(key=lambda r: r['line_num'])
        result = dict(capability=CAPABILITY, parameters=options,
            document={k: options[k] for k in ('source_system', 'document_type', 'doc_entry', 'doc_num', 'doc_date')},
            rows=rows, read_only=True, sap_accessed=False,
            source=dict(publication_id=access.foundation_publication_id, snapshot_id=access.ducklake_snapshot_id,
                        updated_at=access.foundation_data_as_of),
            limitations='Active OINV only, INV1 in original order. Catalog description, not historical invoice wording. Native line UoM is not published. Documentary quantities only, no conversions, totals or amounts.')
    return validate_result(options, result)


_LOCK = asyncio.Lock()


async def query_invoice_lines(options, *, timeout_seconds=30):
    parameters(options)
    if _LOCK.locked():
        raise TelchiQueryError('datalake_busy')
    async with _LOCK:
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', __name__, json.dumps(options),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout_seconds)
            if process.returncode:
                raise TelchiQueryError('invoice_worker_error')
            return validate_result(options, json.loads(output)['result'])
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


if __name__ == '__main__':
    try:
        print(json.dumps({'result': execute_query(json.loads(sys.argv[1]))}))
    except Exception:
        print(json.dumps({'error': 'invoice_query_unavailable'}))
        sys.exit(1)
