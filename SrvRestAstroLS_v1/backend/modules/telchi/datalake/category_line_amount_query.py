"""Accredited BS commercial line amounts. No header allocation or tax conversion."""
import asyncio
from datetime import date
from decimal import Decimal
import hashlib
import json
import sys

from .messaging_sales_query import TelchiQueryError

CAPABILITY = 'sales.category_line_amount.v1'
PERMISSION = 'telchi.sales.category_line_amount.read.v1'
DEFINITION = 'commercial_active_invoice_line_amount_excluding_line_tax_v1'
# Historical accreditation root: successors require canonical compatibility
# proof (sales_succession), never an implicit latest fallback.
PUBLICATION = 'foundation_afd08d9eca6a725be53cdc3f9d5709c9'
SNAPSHOT = 1408
CROSSWALK_SHA256 = '7fcfef912cc8ef46868e03b56f90b61da13c08e951c453abc0483690edc36e10'
CLASSIFICATION_VERSION = 'v2_product_business_type_f9c1130d852ccb61'
SAFE_ERRORS = {'category_currency_not_accredited', 'category_classification_provisional',
    'category_unaccredited_rows_or_lineage', 'category_key_integrity_failed',
    'category_accreditation_binding_changed', 'category_classification_changed'}
LIMITATIONS = ['Sin IVA de línea; descuentos propios ya reflejados en el importe.',
    'No descuenta notas de crédito ni incorpora ajustes globales u otros componentes de cabecera.',
    'Clasificación actual, no histórica. Cobertura completa del período no certificada.',
    'No es facturación documental neta ni monto cobrado. Las diferencias con cabeceras no son íntegramente IVA.']


def parameters(options):
    from ..assistant.business_categories import CATEGORIES
    if (not isinstance(options, dict) or set(options) != {'category', 'date_from', 'date_to_exclusive', 'currency'}
            or options['category'] not in CATEGORIES or options['category'] == 'UNKNOWN'
            or options['currency'] != 'BS'):
        raise ValueError('unaccredited_category_or_currency')
    start, end = (date.fromisoformat(options[k]) for k in ('date_from', 'date_to_exclusive'))
    if not 0 < (end-start).days <= 366:
        raise ValueError('invalid_category_period')
    return options


def scoped_source(con, documents, lines, crosswalk, base, *, item_code=None, card_code=None,
                  project_card_code=False):
    """Guard the commercial invoice-line universe and return (cte, args).

    Same relations, keys, currency and lineage guards as the accredited
    category total. Optional filters narrow the universe; they never relax a
    guard and never filter a row out silently: the membership and integrity
    checks run over the whole guarded universe, exactly as before.
    """
    d = f"(SELECT * FROM {documents} WHERE source_system='SAP_B1_HANA' AND source_table='OINV')"
    l = f"(SELECT * FROM {lines} WHERE source_system='SAP_B1_HANA' AND source_table='INV1')"
    guards = con.execute(f'''SELECT
      (SELECT COUNT(*) FROM (SELECT doc_entry FROM {d} GROUP BY ALL HAVING COUNT(*)<>1)),
      (SELECT COUNT(*) FROM (SELECT doc_entry,line_num FROM {l} GROUP BY ALL HAVING COUNT(*)<>1)),
      (SELECT COUNT(*) FROM {d} WHERE doc_entry IS NULL OR canceled IS NULL OR canceled NOT IN ('N','Y','C')),
      (SELECT COUNT(*) FROM {l} WHERE doc_entry IS NULL OR line_num IS NULL),
      (SELECT COUNT(*) FROM {l} l WHERE NOT EXISTS(SELECT 1 FROM {d} d WHERE d.doc_entry=l.doc_entry)),
      (SELECT COUNT(*) FROM (SELECT "ItemCode" FROM {crosswalk} GROUP BY ALL HAVING COUNT(*)<>1)),
      (SELECT COUNT(*) FROM {crosswalk} WHERE "ItemCode" IS NULL)''').fetchone()
    if any(guards):
        raise TelchiQueryError('category_key_integrity_failed')
    window = "canceled='N' AND doc_date>=? AND doc_date<?"
    args = [base['date_from'], base['date_to_exclusive']]
    if card_code is not None:
        window += " AND card_code=?"
        args.append(card_code)
    if base.get('periods'):
        window += ' AND (' + ' OR '.join('(doc_date>=? AND doc_date<?)' for _ in base['periods']) + ')'
        for period in base['periods']:
            args.extend([period['start'], period['end_exclusive']])
    joined_where = ''
    if item_code is not None:
        joined_where = ' WHERE l.item_code=?'
        args.append(item_code)
    projection = ('d.doc_entry,d.doc_date,d.currency doc_currency,'
        + ('d.card_code card_code,' if project_card_code else '')
        + "json_extract_string(to_json(d),'$.doc_num') doc_num,"
        + "d.raw_extraction_id de,d.source_as_of da,l.*,x.product_business_type category,x.status quality")
    cte = f'''WITH d AS (SELECT * FROM {d} WHERE {window}),
      joined AS (SELECT {projection}
        FROM d LEFT JOIN {l} l ON d.doc_entry=l.doc_entry
        LEFT JOIN {crosswalk} x ON x."ItemCode"=l.item_code{joined_where})'''
    return cte, args


def bs_only_cte(cte):
    """The same guarded universe restricted to amounts actually denominated in BS."""
    return (cte.replace('joined AS (', 'unfiltered AS (')
            + ", joined AS (SELECT * FROM unfiltered WHERE doc_currency='BS' AND currency='BS')")


def scoped_aggregate(con, documents, lines, crosswalk, base, *, category=None, item_code=None,
                     card_code=None, exceptions=None, require_category=True, source=None):
    """Accredited BS commercial line amount over a filtered universe.

    The measure, the currency guard, the lineage guard and the classification
    gate are the ones already accredited for the category total. A category is a
    filter, never a silent row filter: unclassified or provisional rows fail
    the operation instead of shrinking the total.
    """
    cte, args = source if source is not None else scoped_source(
        con, documents, lines, crosswalk, base, item_code=item_code, card_code=card_code)
    integrity = ('line_num IS NULL OR de IS NULL OR da IS NULL'
                 ' OR de IS DISTINCT FROM raw_extraction_id OR da IS DISTINCT FROM source_as_of'
                 ' OR TRY_CAST(line_total AS DECIMAL(38,6)) IS NULL'
                 ' OR NOT isfinite(TRY_CAST(line_total AS DOUBLE))')
    if require_category:
        integrity = 'category IS NULL OR quality IS NULL OR ' + integrity
    bad = con.execute(cte+f''' SELECT COUNT(*) FROM joined WHERE {integrity}''', args).fetchone()[0]
    if bad:
        raise TelchiQueryError('category_unaccredited_rows_or_lineage')
    scope = ' WHERE category=?' if category is not None else ''
    scope_args = args + ([category] if category is not None else [])
    qualities = {}
    if require_category:
        qualities = dict(con.execute(cte+''' SELECT quality,COUNT(*) FROM joined
          WHERE category=? GROUP BY quality''', scope_args).fetchall())
        if set(qualities)-{'VALIDATED', 'SUPPORTED'}:
            raise TelchiQueryError('category_classification_provisional')
    # Establish membership and integrity BEFORE monetary exclusions. Unknown
    # membership/lineage is not silently filtered into an apparently complete total.
    incompatible = con.execute(cte+''' SELECT doc_entry,line_num,item_code,doc_currency,currency,line_total,doc_num
      FROM joined WHERE ''' + ('category=? AND ' if category is not None else '') +
      '''(doc_currency IS DISTINCT FROM 'BS' OR currency IS DISTINCT FROM 'BS')
      ORDER BY doc_entry,line_num''', scope_args).fetchall()
    if incompatible:
        if exceptions is None:
            raise TelchiQueryError('category_currency_not_accredited')
        exceptions.extend(dict(doc_entry=d, doc_num=num, line_num=n, item_code=i, header_currency=h,
            line_currency=c, original_line_total=str(a), excluded=True,
            reason='currency_not_accredited', impact='amount_and_position_may_change',
            audit_required=True) for d,n,i,h,c,a,num in incompatible)
        # Only compatible amounts contribute. No conversion or assumed denomination
        # of LineTotal from a price currency (not necessarily the amount currency).
        cte = bs_only_cte(cte)
        if require_category:
            qualities = dict(con.execute(cte+''' SELECT quality,COUNT(*) FROM joined
              WHERE category=? GROUP BY quality''', scope_args).fetchall())
    row = con.execute(cte+''' SELECT COALESCE(SUM(CAST(line_total AS DECIMAL(38,6))),0),
      COUNT(DISTINCT item_code),COUNT(*),COUNT(DISTINCT doc_entry),MIN(doc_date),MAX(doc_date)
      FROM joined''' + scope, scope_args).fetchone()
    # Effective observed coverage of the documentary source, not a month-close claim.
    coverage = con.execute(cte+''' SELECT MIN(doc_date),MAX(doc_date) FROM d''', args).fetchone()
    return dict(amount=str(row[0]), product_count=row[1], line_count=row[2], document_count=row[3],
        first_date=row[4], last_date=row[5]), dict(first_date=coverage[0], last_date=coverage[1],
        complete=False), qualities


def aggregate(con, documents, lines, crosswalk, options, *, exceptions=None):
    """Accredited total of one business category. Historical contract, unchanged."""
    parameters(options)
    return scoped_aggregate(con, documents, lines, crosswalk, options,
        category=options['category'], exceptions=exceptions)


def validate_result(options, result, *, _admitted=None):
    from .sales_succession import accepts_result, admitted_source
    _admitted = _admitted or admitted_source(result)
    parameters(options)
    if (result.get('capability') != CAPABILITY or result.get('parameters') != options
            or result.get('definition') != DEFINITION or result.get('currency') != 'BS'
            or result.get('read_only') is not True or result.get('sap_accessed') is not False
            or not accepts_result(result.get('source', {}), {(PUBLICATION, SNAPSHOT)}, _admitted=_admitted)
            or not result['source'].get('updated_at')
            or result.get('classification', {}).get('sha256') != CROSSWALK_SHA256
            or result['classification'].get('version') != CLASSIFICATION_VERSION
            or not isinstance(result.get('rows'), list) or len(result['rows']) != 1
            or result.get('limitations') != LIMITATIONS or result.get('coverage', {}).get('complete') is not False):
        raise ValueError('invalid_category_amount_result')
    row = result['rows'][0]
    if (not isinstance(row['amount'], str) or not Decimal(row['amount']).is_finite()
            or any(type(row[k]) is not int or row[k] < 0 for k in ('product_count','line_count','document_count'))
            or row['product_count'] > row['line_count'] or row['document_count'] > row['line_count']
            or sum(result['classification']['quality_lines'].values()) != row['line_count']
            or set(result['classification']['quality_lines'])-{'VALIDATED','SUPPORTED'}):
        raise ValueError('invalid_category_amount')
    for bounds in (row, result['coverage']):
        first, last = bounds['first_date'], bounds['last_date']
        if (first is None) != (last is None):
            raise ValueError('invalid_category_coverage')
        if first is not None and not options['date_from'] <= first[:10] <= last[:10] < options['date_to_exclusive']:
            raise ValueError('invalid_category_coverage')
    if (row['line_count'] == 0 and (Decimal(row['amount']) != 0 or row['first_date'] is not None)
            or row['line_count'] > 0 and row['first_date'] is None):
        raise ValueError('invalid_category_empty_result')
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
                and hashlib.sha256(path.read_bytes()).hexdigest() != CROSSWALK_SHA256):
            raise TelchiQueryError('category_classification_changed')
        x = "read_parquet('" + str(path).replace("'", "''") + "')"
        row, coverage, qualities = aggregate(con, access.sales('sales_document'), access.sales('sales_line'), x, options)
        result = dict(capability=CAPABILITY, parameters=options, definition=DEFINITION, currency='BS',
            rows=[row], coverage=coverage, classification=dict(version=CLASSIFICATION_VERSION,
                sha256=CROSSWALK_SHA256, reference=access.foundation.reference_version, quality_lines=qualities),
            source=source_metadata(access), limitations=LIMITATIONS,
            read_only=True, sap_accessed=False)
    return validate_result(options, result, _admitted=result['source'])


_LOCK = asyncio.Lock()


async def query_category_line_amount(options, *, timeout_seconds=30):
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
                raise TelchiQueryError(reason if reason in SAFE_ERRORS else 'category_amount_worker_error')
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
        reason = str(exc)
        print(json.dumps({'error': reason if reason in SAFE_ERRORS else 'category_line_amount_unavailable'}))
        sys.exit(1)
