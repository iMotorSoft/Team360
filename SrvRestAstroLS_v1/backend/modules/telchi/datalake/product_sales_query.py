"""DEV product lookup and invoice lines by natural SAP ItemCode, CURRENT 1408.

SAP_HANA (Reference OITM) and SAP_B1_HANA (Atomic INV1) are producer labels
for the TELCHI SAP company, not interchangeable namespaces for other sources.
No canonical IDs, aliases, names or legacy namespaces participate in sales joins.
Amounts and physical line UoM are deliberately not exposed as approved metrics.
"""
import asyncio
from datetime import date
from decimal import Decimal
import json
import sys
import unicodedata

from .messaging_sales_query import TelchiQueryError
from .sales_succession import ROOT_SNAPSHOT, SALES_ROOT

# Historical accreditation root, never the pin of the current publication. A
# successor is admitted only through the canonical commercial ancestry; an
# exact match against this value is accepted for replaying sealed results.
PUBLICATION = SALES_ROOT
SNAPSHOT = ROOT_SNAPSHOT
PERMISSIONS = {'products.search': 'telchi.products.search.read.v1',
               'sales.by_products': 'telchi.sales.by_products.read.v1'}
SAFE_ERRORS = {'product_binding_changed', 'product_result_binding_mismatch',
               'duplicate_catalog_item_code', 'item_code_absent_from_catalog',
               'duplicate_product_documents', 'duplicate_product_lines',
               'orphan_product_lines', 'datalake_not_read_only',
               'product_worker_error', 'product_query_unavailable'}
MAX_PRODUCTS = 20


def normalize(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                           if not unicodedata.combining(c)).split())


def parameters(operation, options):
    if not isinstance(options, dict) or operation not in PERMISSIONS:
        raise ValueError('invalid_product_operation')
    limit = options.get('limit', 10)
    if type(limit) is not int or not 1 <= limit <= (MAX_PRODUCTS if operation == 'products.search' else 50):
        raise ValueError('invalid_product_limit')
    if operation == 'products.search':
        if set(options) - {'text', 'limit'} or not isinstance(options.get('text'), str):
            raise ValueError('invalid_search')
        text = normalize(options['text'])
        if not 1 <= len(text) <= 120 or len(options['text']) > 240 or any(ord(c) < 32 for c in options['text']):
            raise ValueError('invalid_search_text')
        return [text, text, text, limit + 1]
    if set(options) - {'item_codes', 'namespace', 'date_from', 'date_to_exclusive', 'limit'}:
        raise ValueError('invalid_product_sales_parameters')
    codes = options.get('item_codes')
    if (options.get('namespace') != 'SAP_HANA' or not isinstance(codes, list)
            or not 1 <= len(codes) <= MAX_PRODUCTS or any(not isinstance(c, str) or not 1 <= len(c) <= 80 for c in codes)
            or len(codes) != len(set(codes))):
        raise ValueError('invalid_item_codes')
    start, end = options.get('date_from'), options.get('date_to_exclusive')
    if (start is None) != (end is None):
        raise ValueError('incomplete_product_period')
    if start is not None:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        if s.isoformat() != start or e.isoformat() != end or not 0 < (e-s).days <= 366:
            raise ValueError('invalid_product_period')
    return [codes, start, end, limit]


# Parameters are values, not LIKE patterns; %/_ in a message remain literal.
SEARCH_SQL = """WITH catalog AS (
SELECT source_system AS namespace,item_code,canonical_product_id,
coalesce(sap_item_name,product_name,canonical_name) AS description,
sales_uom_id AS catalog_sales_uom_id,inventory_uom_id AS catalog_inventory_uom_id,
active,status,sap_sell_item AS sell_item,
lower(regexp_replace(strip_accents(coalesce(sap_item_name,product_name,canonical_name)), '\\s+', ' ', 'g')) AS search_name
FROM read_parquet(?) WHERE source_system='SAP_HANA'
), ranked AS (
SELECT *,CASE WHEN lower(item_code)=? THEN 0
WHEN contains(' ' || search_name || ' ', ' ' || ? || ' ') THEN 1 ELSE 2 END AS match_rank
FROM catalog WHERE contains(search_name,?) OR contains(lower(item_code),?)
) SELECT * EXCLUDE(search_name) FROM ranked ORDER BY match_rank,item_code LIMIT ?"""
SALES_SQL = """SELECT d.doc_date,'OINV' AS document_type,l.source_system,d.doc_entry,d.doc_num,
l.line_num,l.item_code,l.quantity,p.description,p.catalog_sales_uom_id
FROM {lines} l JOIN {documents} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
JOIN (SELECT item_code,coalesce(sap_item_name,product_name,canonical_name) AS description,
sales_uom_id AS catalog_sales_uom_id FROM read_parquet(?) WHERE source_system='SAP_HANA') p
ON p.item_code=l.item_code
WHERE l.source_system='SAP_B1_HANA' AND l.source_table='INV1' AND d.source_table='OINV'
AND d.canceled='N' AND l.item_code IN (SELECT unnest(?)) AND d.doc_date IS NOT NULL
AND (? IS NULL OR d.doc_date>=?) AND (? IS NULL OR d.doc_date<?)
ORDER BY d.doc_date DESC,CAST(d.doc_entry AS BIGINT) DESC,CAST(l.line_num AS BIGINT) DESC,l.item_code LIMIT ?"""


def execute_query(operation, options, connector=None):
    values = parameters(operation, options)
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
        # CURRENT is admissible only through the canonical commercial succession.
        # A hash equality would reject every accredited successor; a missing or
        # unprovable accreditation fails closed before any read.
        from .sales_succession import admit, source_metadata
        admit(access, con)
        source = source_metadata(access)
        path = str(access.reference('products'))
        if con.execute("SELECT item_code FROM read_parquet(?) WHERE source_system='SAP_HANA' GROUP BY item_code HAVING count(*)<>1 LIMIT 1", [path]).fetchone():
            raise TelchiQueryError('duplicate_catalog_item_code')
        summary = []
        if operation == 'products.search':
            text, _, _, limit = values
            sql, bound = SEARCH_SQL, [path, text, text, text, text, limit]
        else:
            codes, start, end, limit = values
            found = con.execute("SELECT item_code FROM read_parquet(?) WHERE source_system='SAP_HANA' AND item_code IN (SELECT unnest(?))", [path, codes]).fetchall()
            if {r[0] for r in found} != set(codes):
                raise TelchiQueryError('item_code_absent_from_catalog')
            lines, documents = access.sales('sales_line'), access.sales('sales_document')
            if con.execute(f"SELECT source_system,doc_entry FROM {documents} GROUP BY ALL HAVING count(*)<>1 LIMIT 1").fetchone():
                raise TelchiQueryError('duplicate_product_documents')
            if con.execute(f"SELECT source_system,doc_entry,line_num FROM {lines} WHERE item_code IN (SELECT unnest(?)) GROUP BY ALL HAVING count(*)<>1 LIMIT 1", [codes]).fetchone():
                raise TelchiQueryError('duplicate_product_lines')
            if con.execute(f"SELECT l.doc_entry FROM {lines} l LEFT JOIN {documents} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry WHERE l.source_system='SAP_B1_HANA' AND l.item_code IN (SELECT unnest(?)) AND d.doc_entry IS NULL LIMIT 1", [codes]).fetchone():
                raise TelchiQueryError('orphan_product_lines')
            summary_rows = con.execute(f"SELECT l.item_code,count(*),min(d.doc_date),max(d.doc_date) FROM {lines} l JOIN {documents} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry WHERE l.source_system='SAP_B1_HANA' AND l.source_table='INV1' AND d.source_table='OINV' AND d.canceled='N' AND l.item_code IN (SELECT unnest(?)) AND d.doc_date IS NOT NULL AND (? IS NULL OR d.doc_date>=?) AND (? IS NULL OR d.doc_date<?) GROUP BY l.item_code", [codes,start,start,end,end]).fetchall()
            by_code = {r[0]: r[1:] for r in summary_rows}
            summary = [dict(item_code=code, line_count=by_code.get(code,(0,None,None))[0],
                first_date=by_code.get(code,(0,None,None))[1], last_date=by_code.get(code,(0,None,None))[2]) for code in codes]
            sql = SALES_SQL.format(lines=lines, documents=documents)
            bound = [path, codes, start, start, end, end, limit]
        cur = con.execute(sql, bound)
        rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    rows = json.loads(json.dumps(rows, default=str))
    truncated = operation == 'products.search' and len(rows) > options.get('limit', 10)
    if truncated:
        rows = rows[:options.get('limit', 10)]
    result = dict(capability=operation+'.v1', parameters=options, rows=rows,
                  source=source,
                  read_only=True, sap_accessed=False, sql=sql, sql_parameters=bound,
                  product_summary=summary, truncated=truncated, grain='catalog_product' if operation == 'products.search' else 'invoice_line',
                  limitations='Active OINV only; no credit subtraction. Quantity is source documentary quantity per line; physical line UoM/factor not published. Catalog UoM is metadata, not line UoM. No physical totals or approved line amounts. Empty results do not certify zero sales outside this publication.')
    return validate_result(operation, options, result)


def validate_result(operation, options, result, *, accredit=True):
    parameters(operation, options)
    from .sales_succession import accepts_result, admitted_source
    source = result.get('source', {})
    if (result.get('capability') != operation+'.v1' or result.get('parameters') != options
            or result.get('read_only') is not True or result.get('sap_accessed') is not False
            or not isinstance(source.get('publication_id'), str)
            or type(source.get('snapshot_id')) is not int
            or not isinstance(result.get('rows'), list) or len(result['rows']) > options.get('limit', 10)
            or type(result.get('truncated')) is not bool):
        raise ValueError('invalid_product_result')
    # Execution already proved the canonical admission. Persisted context is
    # validated structurally without catalog I/O: it is application-owned and
    # was admitted when it was produced.
    if accredit and not accepts_result(source, {(PUBLICATION, SNAPSHOT)},
                                       _admitted=admitted_source(result)):
        raise ValueError('invalid_product_result')
    summary = result.get('product_summary')
    if operation == 'sales.by_products' and summary is not None:
        if not isinstance(summary, list) or [r.get('item_code') for r in summary] != options['item_codes']:
            raise ValueError('invalid_product_summary')
        for row in summary:
            if type(row.get('line_count')) is not int or row['line_count'] < 0:
                raise ValueError('invalid_product_line_count')
            if row['line_count'] == 0:
                if row.get('first_date') is not None or row.get('last_date') is not None:
                    raise ValueError('invalid_empty_product_summary')
            elif date.fromisoformat(row['first_date'][:10]) > date.fromisoformat(row['last_date'][:10]):
                raise ValueError('invalid_product_summary_dates')
            if sum(r.get('item_code') == row['item_code'] for r in result['rows']) > row['line_count']:
                raise ValueError('invalid_product_summary_count')
    keys = []
    for row in result['rows']:
        if not isinstance(row.get('item_code'), str) or not isinstance(row.get('description'), str):
            raise ValueError('invalid_product_row')
        if operation == 'products.search':
            if row.get('namespace') != 'SAP_HANA' or row.get('match_rank') not in (0, 1, 2):
                raise ValueError('invalid_product_namespace')
            keys.append((row['match_rank'], row['item_code']))
        else:
            if (row['item_code'] not in options['item_codes'] or row.get('source_system') != 'SAP_B1_HANA'
                    or row.get('document_type') != 'OINV' or not Decimal(row['quantity']).is_finite()):
                raise ValueError('invalid_product_sales_row')
            day = date.fromisoformat(row['doc_date'][:10])
            if options.get('date_from') and not options['date_from'] <= day.isoformat() < options['date_to_exclusive']:
                raise ValueError('invalid_product_sales_date')
            keys.append((row['doc_date'], int(row['doc_entry']), int(row['line_num']), row['item_code']))
    if len(keys) != len(set(keys)) or keys != sorted(keys, reverse=operation == 'sales.by_products'):
        raise ValueError('invalid_product_order')
    return result


_LOCK = asyncio.Lock()


async def query_products(operation, options, *, timeout_seconds=30):
    parameters(operation, options)
    if _LOCK.locked():
        raise TelchiQueryError('datalake_busy')
    async with _LOCK:
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', __name__, operation, json.dumps(options),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout_seconds)
            payload = json.loads(output)
            if process.returncode:
                # Preserve the real, allowlisted cause instead of hiding it behind
                # an opaque worker error. Unknown failures stay generic.
                reason = payload.get('error')
                raise TelchiQueryError(reason if reason in SAFE_ERRORS else 'product_worker_error')
            from .sales_succession import mark_result
            return mark_result(validate_result(operation, options, payload['result']))
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


def publication_compatibility(connector=None):
    """Read-only proof that CURRENT is admissible for both product operations.

    Run before enabling a runtime or promoting a publication. It resolves the
    same CURRENT and the same canonical admission used by the capability, and
    proves that the catalog and sales relations are readable. It never runs a
    business query, replays ancestry or writes anything.
    """
    from .ducklake import DuckLakeConnector
    from .foundation_reader import FoundationReader
    connector = connector or DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=1')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        if con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() != (True,):
            raise TelchiQueryError('datalake_not_read_only')
        access = FoundationReader(connector).resolve_on(con)
        from .sales_succession import admit, source_metadata
        admit(access, con)
        catalog = str(access.reference('products'))
        con.execute("SELECT item_code FROM read_parquet(?) WHERE source_system='SAP_HANA' LIMIT 1", [catalog]).fetchone()
        con.execute(f"SELECT doc_entry FROM {access.sales('sales_document')} LIMIT 1").fetchone()
        con.execute(f"SELECT doc_entry FROM {access.sales('sales_line')} LIMIT 1").fetchone()
        return dict(compatible=True, operations=sorted(PERMISSIONS),
                    source=source_metadata(access), reference=access.foundation.reference_version,
                    check='canonical_commercial_admission; read-only relations resolved')


if __name__ == '__main__':
    try:
        if len(sys.argv) == 2 and sys.argv[1] == '--compatibility':
            print(json.dumps(dict(compatibility=publication_compatibility())))
        else:
            print(json.dumps({'result': execute_query(sys.argv[1], json.loads(sys.argv[2]))}))
    except TelchiQueryError as exc:
        print(json.dumps({'error': str(exc) if str(exc) in SAFE_ERRORS else 'product_query_unavailable'}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'product_query_unavailable'}))
        sys.exit(1)
