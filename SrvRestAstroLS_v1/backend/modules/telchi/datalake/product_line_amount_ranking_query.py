"""Product-grain commercial amounts; read-only, accredited category universe only."""
import asyncio
from decimal import Decimal, localcontext
import hashlib
import json
import sys

from . import category_line_amount_query as category
from .messaging_sales_query import TelchiQueryError

METRIC = 'sales.product_line_amount_ranking'
CAPABILITY = METRIC + '.v1'
PERMISSION = 'telchi.sales.product_line_amount_ranking.read.v1'
PLAN = dict(operation='ranking', group_by='sap_product', measure=category.DEFINITION,
            order_by=[['amount', 'desc'], ['item_code', 'asc']])
SAFE_ERRORS = category.SAFE_ERRORS | {'ranking_catalog_integrity_failed', 'ranking_reconciliation_failed'}


class RankingError(TelchiQueryError):
    def __init__(self, reason, evidence):
        super().__init__(reason)
        self.evidence = evidence


def parameters(options):
    if (not isinstance(options, dict) or set(options) != {'category', 'date_from', 'date_to_exclusive', 'currency', 'limit'}
            or type(options['limit']) is not int or not 1 <= options['limit'] <= 50):
        raise ValueError('invalid_ranking_parameters')
    return category.parameters({k: v for k, v in options.items() if k != 'limit'})


def reconcile(full, total):
    # Decimal context must retain the DECIMAL(38,6) source precision.
    with localcontext() as ctx:
        ctx.prec = 50
        amount = sum((Decimal(r['amount']) for r in full), Decimal(0))
        difference = amount - Decimal(total['amount'])
    evidence = dict(product_amount= str(amount), category_amount=total['amount'], difference=str(difference),
                    tolerance='0', product_count=len(full), line_count=sum(r['line_count'] for r in full))
    if difference != 0 or len(full) != total['product_count'] or evidence['line_count'] != total['line_count']:
        raise RankingError('ranking_reconciliation_failed', dict(evidence, full_breakdown=full, category_total=total))
    return evidence


def aggregate(con, documents, lines, crosswalk, catalog, options, *, exceptions=None):
    base = parameters(options)
    # Same key, currency, lineage and classification guards as the accredited total.
    total, coverage, qualities = category.aggregate(con, documents, lines, crosswalk, base, exceptions=exceptions)
    if con.execute(f'''SELECT COUNT(*) FROM (SELECT item_code FROM {catalog}
        WHERE source_system='SAP_HANA' GROUP BY item_code HAVING COUNT(*)<>1 OR item_code IS NULL)''').fetchone()[0]:
        raise TelchiQueryError('ranking_catalog_integrity_failed')
    grouped = con.execute(f'''SELECT l.item_code,SUM(CAST(l.line_total AS DECIMAL(38,6))) amount,
        COUNT(*) line_count,COUNT(DISTINCT d.doc_entry) document_count
        FROM {documents} d JOIN {lines} l ON d.doc_entry=l.doc_entry AND d.source_system=l.source_system
        JOIN {crosswalk} x ON x."ItemCode"=l.item_code
        WHERE d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND d.canceled='N'
        AND l.source_table='INV1' AND d.doc_date>=? AND d.doc_date<? AND x.product_business_type=?
        AND d.currency='BS' AND l.currency='BS'
        GROUP BY l.item_code''', [options['date_from'], options['date_to_exclusive'], options['category']]).fetchall()
    names = dict(con.execute(f'''SELECT item_code,coalesce(sap_item_name,product_name,canonical_name)
        FROM {catalog} WHERE source_system='SAP_HANA' ''').fetchall())
    full = []
    for code, amount, line_count, document_count in grouped:
        if not isinstance(names.get(code), str) or not names[code].strip():
            raise TelchiQueryError('ranking_catalog_integrity_failed')
        full.append(dict(item_code=code, description=names[code], amount=str(amount),
                         line_count=line_count, document_count=document_count))
    # Stable secondary ordering, without unary Decimal rounding under default context.
    full.sort(key=lambda r: r['item_code'])
    full.sort(key=lambda r: Decimal(r['amount']), reverse=True)
    reconciliation = reconcile(full, total)
    reconciliation['breakdown_sha256'] = hashlib.sha256(json.dumps(full, sort_keys=True).encode()).hexdigest()
    return full, total, coverage, qualities, reconciliation


def validate_result(options, result, *, _admitted=None):
    from .sales_succession import admitted_source
    _admitted = _admitted or admitted_source(result)
    base = parameters(options)
    category.validate_result(base, dict(result, capability=category.CAPABILITY, parameters=base,
                                       rows=[result['category_total']]), _admitted=_admitted)
    full = result['full_breakdown']
    exceptions = result.get('exceptions', [])
    if (not isinstance(exceptions, list) or result.get('accreditation', 'verified') != ('partial' if exceptions else 'verified')
            or any(not isinstance(e, dict) or e.get('excluded') is not True
                or e.get('reason') != 'currency_not_accredited' or e.get('audit_required') is not True
                or e.get('impact') != 'amount_and_position_may_change'
                or not all(isinstance(e.get(k), str) for k in ('doc_entry','line_num','item_code','original_line_total'))
                or (e.get('header_currency') == e.get('line_currency') == 'BS') for e in exceptions)):
        raise ValueError('invalid_ranking_exceptions')
    if (result.get('capability') != CAPABILITY or result.get('parameters') != options
            or result.get('plan') != PLAN or not isinstance(full, list)
            or result['rows'] != full[:options['limit']]):
        raise ValueError('invalid_ranking_result')
    codes = set()
    for row in full:
        if (not isinstance(row.get('item_code'), str) or not row['item_code'] or row['item_code'] in codes
                or not isinstance(row.get('description'), str) or not row['description'].strip()
                or not isinstance(row.get('amount'), str) or not Decimal(row['amount']).is_finite()
                or any(type(row.get(k)) is not int or row[k] < 1 for k in ('line_count', 'document_count'))
                or row['document_count'] > row['line_count']):
            raise ValueError('invalid_ranking_row')
        codes.add(row['item_code'])
    ordered = sorted(full, key=lambda r: r['item_code'])
    ordered.sort(key=lambda r: Decimal(r['amount']), reverse=True)
    expected = reconcile(full, result['category_total'])
    expected['breakdown_sha256'] = hashlib.sha256(json.dumps(full, sort_keys=True).encode()).hexdigest()
    if full != ordered or result['reconciliation'] != expected:
        raise ValueError('invalid_ranking_reconciliation')
    return result


def execute_query(options, connector=None):
    parameters(options)
    from .ducklake import DATA_ROOT, DuckLakeConnector
    from .foundation_reader import FoundationReader
    connector = connector or DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        if con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() != (True,):
            raise TelchiQueryError('datalake_not_read_only')
        access = FoundationReader(connector).resolve_on(con)
        from .sales_succession import admit, source_metadata
        admit(access, con, category_legacy=True)
        path = DATA_ROOT / 'crosswalk/_versions' / access.foundation.reference_version / 'product_business_type/part-00000.parquet'
        if (getattr(access, 'read_binding', None) is None
                and hashlib.sha256(path.read_bytes()).hexdigest() != category.CROSSWALK_SHA256):
            raise TelchiQueryError('category_classification_changed')
        relation = lambda p: "read_parquet('" + str(p).replace("'", "''") + "')"
        exceptions = []
        full, total, coverage, qualities, reconciliation = aggregate(con, access.sales('sales_document'),
            access.sales('sales_line'), relation(path), relation(access.reference('products')), options, exceptions=exceptions)
        # Audit independently classified external anomalies, never call them
        # exclusions from the requested ranking or let them change its amounts.
        external = con.execute(f'''SELECT d.doc_entry,l.line_num,l.item_code,x.product_business_type,
            d.currency,l.currency,l.line_total,json_extract_string(to_json(d),'$.doc_num') FROM {access.sales('sales_document')} d
            JOIN {access.sales('sales_line')} l ON d.doc_entry=l.doc_entry AND d.source_system=l.source_system
            JOIN {relation(path)} x ON x."ItemCode"=l.item_code
            WHERE d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND l.source_table='INV1'
            AND d.canceled='N' AND d.doc_date>=? AND d.doc_date<? AND x.product_business_type<>?
            AND (d.currency IS DISTINCT FROM 'BS' OR l.currency IS DISTINCT FROM 'BS')
            ORDER BY d.doc_entry,l.line_num''', [options['date_from'], options['date_to_exclusive'], options['category']]).fetchall()
        external = [dict(doc_entry=d,doc_num=num,line_num=n,item_code=i,category=c,header_currency=h,line_currency=l,
            original_line_total=str(a),participates_in_ranking=False,audit_required=True) for d,n,i,c,h,l,a,num in external]
        result = dict(capability=CAPABILITY, parameters=options, plan=PLAN, definition=category.DEFINITION,
            external_currency_anomalies=external,
            currency='BS', rows=full[:options['limit']], full_breakdown=full, category_total=total,
            exceptions=exceptions, accreditation='partial' if exceptions else 'verified',
            reconciliation=reconciliation, coverage=coverage, classification=dict(version=category.CLASSIFICATION_VERSION,
                sha256=category.CROSSWALK_SHA256, reference=access.foundation.reference_version, quality_lines=qualities),
            source=source_metadata(access), limitations=category.LIMITATIONS, read_only=True, sap_accessed=False)
    return validate_result(options, result, _admitted=result['source'])


_LOCK = asyncio.Lock()


async def query_product_line_amount_ranking(options, *, timeout_seconds=30):
    parameters(options)
    if _LOCK.locked():
        raise TelchiQueryError('datalake_busy')
    async with _LOCK:
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', __name__, json.dumps(options),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout_seconds)
            payload = json.loads(output)
            if process.returncode:
                reason = payload.get('error')
                raise RankingError(reason if reason in SAFE_ERRORS else 'ranking_worker_error', payload.get('evidence'))
            from .sales_succession import mark_result
            return mark_result(validate_result(options, payload['result']))
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


if __name__ == '__main__':
    try:
        print(json.dumps({'result': execute_query(json.loads(sys.argv[1]))}))
    except Exception as exc:
        print(json.dumps(dict(error=str(exc) if str(exc) in SAFE_ERRORS else 'ranking_unavailable',
                              evidence=getattr(exc, 'evidence', None))))
        sys.exit(1)
