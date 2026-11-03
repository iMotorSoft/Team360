"""Commercial line amount by SAP product or by billed SAP customer.

Read-only, one accredited measure, one grouping dimension per operation. The
measure, the currency guard, the lineage guard and the reconciliation tolerance
are the ones already accredited for the category total; this reader only adds a
closed grouping dimension and closed filters. The model never names a table,
a column or an expression: it selects a plan and Team360 compiles it here.
"""
import asyncio
import subprocess
from decimal import Decimal, localcontext
import hashlib
import json
import re
import sys

from . import category_line_amount_query as category
from .messaging_sales_query import TelchiQueryError

METRIC = 'sales.commercial_line_amount_by'
CAPABILITY = METRIC + '.v1'
PERMISSION = 'telchi.sales.commercial_line_amount_by.read.v1'
DATASET = 'commercial_line_amount'
MEASURE = category.DEFINITION
GROUP_BY = ('sap_product', 'card_code', 'physical_state')
# Exact reviewed releases only; no implicit CURRENT/latest accreditation.
PHYSICAL_PUBLICATION = 'foundation_881005a5a694a25dc806233dcb3838ac'
PHYSICAL_REFERENCE = 'v2_04de6eed3805f591777012c7'
PHYSICAL_PRODUCTS_SHA256 = '6f0bc2335ebb351485109017c17ef2fea4931d53c8f34a3d0f4780d10f505d9a'
PHYSICAL_CROSSWALK_SHA256 = 'b458903333c6c78de83128a64a72bdfe70efa859bc7f9f9c3be1a3a639dabace'
ACCREDITED_BINDINGS = {(category.PUBLICATION, category.SNAPSHOT),
    ('foundation_38680850adc058b1bb11887632b7b681', 1408), (PHYSICAL_PUBLICATION, 1408)}
ORDER_BY = [['amount', 'desc'], ['key', 'asc']]
PLAN = dict(dataset=DATASET, group_by=None, measure=MEASURE, order_by=ORDER_BY, breakdown=None)
FILTERS = ('category', 'item_code', 'card_code')
SAFE_ERRORS = category.SAFE_ERRORS | {'commercial_catalog_integrity_failed',
                                      'commercial_reconciliation_failed',
                                      'commercial_universe_unchanged'}
LIMITATIONS = ['Sin IVA de línea; descuentos propios ya reflejados en el importe.',
    'No descuenta notas de crédito ni incorpora ajustes globales u otros componentes de cabecera.',
    'Clasificación actual, no histórica. Cobertura completa del período no certificada.',
    'No es facturación documental neta ni monto cobrado. Las diferencias con cabeceras no son íntegramente IVA.',
    '«Cliente» significa la cuenta facturada en SAP (CardCode) que recibe las líneas; '
    'no es el comprador final ni un cliente comercial validado por taxonomía.',
    'Un importe de un producto es el de sus líneas: no incluye los demás productos de la misma factura.']
ITEM_CODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,49}')
CARD_CODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,19}')


class CommercialAmountError(TelchiQueryError):
    def __init__(self, reason, evidence=None):
        super().__init__(reason)
        self.evidence = evidence


def parameters(options):
    """Fail closed on anything outside the closed plan vocabulary."""
    from datetime import date
    from ..assistant.business_categories import CATEGORIES
    if not isinstance(options, dict):
        raise ValueError('invalid_commercial_plan')
    if set(options) - {'physical_focus', 'detail_limit'} != {'dataset', 'filters', 'date_from', 'date_to_exclusive', 'group_by',
                        'breakdown_by', 'periods', 'measure', 'order_by', 'limit', 'currency'}:
        raise ValueError('invalid_commercial_plan')
    if 'detail_limit' in options and (options['group_by'] != 'physical_state'
            or options['breakdown_by'] != 'products' or type(options['detail_limit']) is not int
            or not 1 <= options['detail_limit'] <= 50):
        raise ValueError('invalid_physical_detail_limit')
    if options['dataset'] != DATASET or options['measure'] != MEASURE:
        raise ValueError('invalid_commercial_plan')
    if options['order_by'] != ORDER_BY or options['currency'] != 'BS':
        raise ValueError('invalid_commercial_plan')
    if options['group_by'] not in GROUP_BY:
        raise ValueError('invalid_commercial_group_by')
    if 'physical_focus' in options:
        from .physical_sales_dimension import LABELS
        if options['group_by'] != 'physical_state' or options['physical_focus'] not in LABELS:
            raise ValueError('invalid_physical_focus')
    if type(options['limit']) is not int or not 1 <= options['limit'] <= 50:
        raise ValueError('invalid_commercial_limit')
    if options['group_by'] == 'physical_state' and options['limit'] < 9:
        raise ValueError('physical_categories_must_not_be_truncated')
    filters = options['filters']
    if not isinstance(filters, dict) or set(filters) != set(FILTERS):
        raise ValueError('invalid_commercial_filters')
    category_code = filters['category']
    if category_code is not None and (category_code not in CATEGORIES or category_code == 'UNKNOWN'):
        raise ValueError('unaccredited_category_or_currency')
    if filters['item_code'] is not None and (
            not isinstance(filters['item_code'], str) or not ITEM_CODE.fullmatch(filters['item_code'])):
        raise ValueError('invalid_commercial_filter')
    if filters['card_code'] is not None and (
            not isinstance(filters['card_code'], str) or not CARD_CODE.fullmatch(filters['card_code'])):
        raise ValueError('invalid_commercial_filter')
    start, end = (date.fromisoformat(options[k]) for k in ('date_from', 'date_to_exclusive'))
    if not 0 < (end - start).days <= 366:
        raise ValueError('invalid_commercial_period')
    if options['breakdown_by'] not in ({None, 'period', 'day', 'products'}
                                      if options['group_by'] == 'physical_state' else {None, 'period'}):
        raise ValueError('invalid_commercial_breakdown')
    periods = options['periods']
    if options['breakdown_by'] == 'period' and not periods:
        raise ValueError('invalid_commercial_breakdown')
    if periods is not None:
        # A declared set of periods is contiguous and covers the whole window.
        if not isinstance(periods, list) or not 2 <= len(periods) <= 6:
            raise ValueError('invalid_commercial_breakdown')
        previous_end = None
        for value in periods:
            if (not isinstance(value, dict) or set(value) != {'start', 'end_exclusive'}):
                raise ValueError('invalid_commercial_breakdown')
            p_start, p_end = (date.fromisoformat(value[k]) for k in ('start', 'end_exclusive'))
            if not p_start < p_end or (p_end - p_start).days > 366:
                raise ValueError('invalid_commercial_breakdown')
            if previous_end is not None and (previous_end > p_start or
                    (options['group_by'] != 'physical_state' and previous_end != p_start)):
                raise ValueError('invalid_commercial_breakdown')
            previous_end = p_end
        if periods[0]['start'] != options['date_from'] or periods[-1]['end_exclusive'] != options['date_to_exclusive']:
            raise ValueError('invalid_commercial_breakdown')
    return options


def plan_of(options):
    plan = dict(PLAN)
    plan['group_by'] = options['group_by']
    plan['breakdown'] = (None if options['breakdown_by'] is None else dict(by=options['breakdown_by']))
    if options['breakdown_by'] == 'period':
        plan['breakdown']['periods'] = [dict(p) for p in options['periods']]
    if options.get('physical_focus'):
        plan['physical_focus'] = options['physical_focus']
    if 'detail_limit' in options:
        plan['detail_limit'] = options['detail_limit']
    return plan


def reconcile(rows, total, group_by):
    """Tolerance zero: the breakdown must be the total, not a sample of it."""
    with localcontext() as ctx:
        ctx.prec = 50
        amount = sum((Decimal(r['amount']) for r in rows), Decimal(0))
        difference = amount - Decimal(total['amount'])
        lines = sum(r['line_count'] for r in rows)
        documents = sum(r['document_count'] for r in rows)
    evidence = dict(measure=MEASURE, breakdown_amount=str(amount), universe_amount=total['amount'],
                    difference=str(difference), tolerance='0', group_count=len(rows),
                    line_count=lines, universe_line_count=total['line_count'],
                    document_count=documents, universe_document_count=total['document_count'],
                    group_by=group_by)
    if difference != 0 or lines != total['line_count']:
        raise CommercialAmountError('commercial_reconciliation_failed', evidence)
    # A billed customer partitions the documents of the universe; a product does not.
    if group_by == 'card_code' and documents != total['document_count']:
        raise CommercialAmountError('commercial_reconciliation_failed', evidence)
    if group_by == 'sap_product' and len(rows) != total['product_count']:
        raise CommercialAmountError('commercial_reconciliation_failed', evidence)
    evidence['breakdown_sha256'] = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return evidence


def _grouped(con, cte, args, options, window):
    """Group the guarded universe by the requested dimension."""
    scope = ''
    scope_args = list(args)
    if options['filters']['category'] is not None:
        scope = ' WHERE category=?'
        scope_args = list(args) + [options['filters']['category']]
    key = {'sap_product': 'item_code', 'card_code': 'card_code',
           'physical_state': 'physical_key'}[options['group_by']]
    rows = con.execute(cte + f''' SELECT {key} group_key,
        SUM(CAST(line_total AS DECIMAL(38,6))) amount, COUNT(*) line_count,
        COUNT(DISTINCT doc_entry) document_count
        FROM joined{scope} GROUP BY {key} ORDER BY 2 DESC, 1 ASC''', scope_args).fetchall()
    return [dict(key=r[0], amount=str(r[1]), line_count=r[2], document_count=r[3]) for r in rows]


def _labels(con, access, group_by, keys):
    """Published master names. Never inferred from a document or a line."""
    if not keys:
        return {}, 0
    if group_by == 'physical_state':
        from .physical_sales_dimension import LABELS
        return {key: LABELS[key] for key in keys}, 0
    if group_by == 'sap_product':
        catalog = access.reference('products')
        relation = f"read_parquet('{str(catalog).replace(chr(39), chr(39) * 2)}')"
        found = dict(con.execute(f'''SELECT item_code,coalesce(sap_item_name,product_name,canonical_name)
            FROM {relation} WHERE source_system='SAP_HANA' ''').fetchall())
        missing = [k for k in keys if not isinstance(found.get(k), str) or not found[k].strip()]
        if missing:
            raise CommercialAmountError('commercial_catalog_integrity_failed',
                                        dict(missing=missing[:20], missing_count=len(missing)))
        return {k: found[k] for k in keys}, 0
    catalog = access.reference('customers')
    relation = f"read_parquet('{str(catalog).replace(chr(39), chr(39) * 2)}')"
    found = dict(con.execute(f'''SELECT code,name FROM {relation}
        WHERE source_system='SAP_HANA' ''').fetchall())
    labels, unnamed = {}, 0
    for key in keys:
        name = found.get(key)
        if isinstance(name, str) and name.strip():
            labels[key] = name
        else:
            labels[key] = key
            unnamed += 1
    return labels, unnamed


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
        physical = options['group_by'] == 'physical_state'
        physical_binding = admit(access, con, physical=physical, category_legacy=True)
        path = DATA_ROOT / 'crosswalk/_versions' / access.foundation.reference_version / 'product_business_type/part-00000.parquet'
        if hashlib.sha256(path.read_bytes()).hexdigest() != category.CROSSWALK_SHA256:
            raise TelchiQueryError('category_classification_changed')
        relation = f"read_parquet('{str(path).replace(chr(39), chr(39) * 2)}')"
        filters = options['filters']
        base = dict(date_from=options['date_from'], date_to_exclusive=options['date_to_exclusive'])
        if physical and options['breakdown_by'] == 'period':
            base['periods'] = options['periods']
        exceptions = []
        cte, args = category.scoped_source(con, access.sales('sales_document'), access.sales('sales_line'),
            relation, base, item_code=filters['item_code'], card_code=filters['card_code'],
            project_card_code=True)
        total, coverage, qualities = category.scoped_aggregate(con, access.sales('sales_document'),
            access.sales('sales_line'), relation, base, category=filters['category'],
            item_code=filters['item_code'], card_code=filters['card_code'], exceptions=exceptions,
            require_category=filters['category'] is not None, source=(cte, args))
        if exceptions:
            # The total and the breakdown must exclude exactly the same rows.
            cte = category.bs_only_cte(cte)
        physical_result = None
        if physical:
            from .physical_sales_dimension import enrich, profile
            products = "read_parquet('" + str(access.reference('products')).replace("'", "''") + "')"
            crosswalk_path = DATA_ROOT / 'crosswalk/_versions' / access.foundation.reference_version / 'product_crosswalk/part-00000.parquet'
            crosswalk = "read_parquet('" + str(crosswalk_path).replace("'", "''") + "')"
            if (hashlib.sha256(access.reference('products').read_bytes()).hexdigest() != physical_binding['products_sha256']
                    or hashlib.sha256(crosswalk_path.read_bytes()).hexdigest() != physical_binding['crosswalk_sha256']):
                raise TelchiQueryError('physical_classification_changed')
            cte, args = enrich(con, cte, args, products, crosswalk)
            physical_result = profile(con, cte, args, category=filters['category'])
            physical_result.update(reference=access.foundation.reference_version,
                products_sha256=hashlib.sha256(access.reference('products').read_bytes()).hexdigest(),
                crosswalk_sha256=hashlib.sha256(crosswalk_path.read_bytes()).hexdigest())
        grouped = _grouped(con, cte, args, options, (options['date_from'], options['date_to_exclusive']))
        # The universe of the same scope without the customer filter. It is the
        # denominator of a participation and is computed with the same measure
        # and the same guards, never with another definition.
        universe_total = None
        if filters['card_code'] is not None:
            u_cte, u_args = category.scoped_source(con, access.sales('sales_document'),
                access.sales('sales_line'), relation, base, item_code=filters['item_code'],
                project_card_code=True)
            u_total, _, _ = category.scoped_aggregate(con, access.sales('sales_document'),
                access.sales('sales_line'), relation, base, category=filters['category'],
                item_code=filters['item_code'], exceptions=[], require_category=filters['category'] is not None)
            universe_total = u_total
        # A period breakdown reads each period independently and then joins them
        # on the group key. The union total above stays the reconciliation base.
        period_rows = []
        if options['breakdown_by'] == 'period':
            for value in options['periods']:
                period_base = dict(date_from=value['start'], date_to_exclusive=value['end_exclusive'])
                p_cte, p_args = category.scoped_source(con, access.sales('sales_document'),
                    access.sales('sales_line'), relation, period_base,
                    item_code=filters['item_code'], card_code=filters['card_code'],
                    project_card_code=True)
                p_exceptions = []
                p_total, _, _ = category.scoped_aggregate(con, access.sales('sales_document'),
                    access.sales('sales_line'), relation, period_base, category=filters['category'],
                    item_code=filters['item_code'], card_code=filters['card_code'],
                    require_category=filters['category'] is not None, source=(p_cte, p_args), exceptions=p_exceptions)
                if p_exceptions:
                    p_cte = category.bs_only_cte(p_cte)
                if physical:
                    p_cte, p_args = enrich(con, p_cte, p_args, products, crosswalk)
                p_grouped = _grouped(con, p_cte, p_args, options, (value['start'], value['end_exclusive']))
                with localcontext() as ctx:
                    ctx.prec = 50
                    p_sum = sum((Decimal(r['amount']) for r in p_grouped), Decimal(0))
                if p_sum != Decimal(p_total['amount']):
                    raise CommercialAmountError('commercial_reconciliation_failed',
                                                dict(period=value, breakdown_amount=str(p_sum),
                                                     universe_amount=p_total['amount'], difference='0', tolerance='0'))
                period_rows.append(dict(period=dict(value), rows=p_grouped, total=p_total))
        merged = _merge(grouped, period_rows)
        labels, unnamed = _labels(con, access, options['group_by'], [r['key'] for r in merged])
        for row in merged:
            row['label'] = labels.get(row['key'], row['key'])
        focus = {}
        if filters['item_code']:
            product_labels, _ = _labels(con, access, 'sap_product', [filters['item_code']])
            focus['item_code'] = filters['item_code']
            focus['item_label'] = product_labels[filters['item_code']]
        if filters['card_code']:
            customer_labels, _ = _labels(con, access, 'card_code', [filters['card_code']])
            focus['card_code'] = filters['card_code']
            focus['customer_label'] = customer_labels[filters['card_code']]
        merged.sort(key=lambda r: r['key'])
        merged.sort(key=lambda r: Decimal(r['amount']), reverse=True)
        reconciliation = reconcile(merged, total, options['group_by'])
        customer_count = con.execute(cte + ''' SELECT COUNT(DISTINCT card_code) FROM joined''',
                                     args).fetchone()[0]
        result = dict(capability=CAPABILITY, parameters=options, plan=plan_of(options),
            definition=MEASURE, currency='BS', rows=merged[:options['limit']],
            full_breakdown=merged, total=dict(total, customer_count=customer_count),
            universe_total=universe_total,
            period_breakdown=period_rows, exceptions=exceptions,
            accreditation='partial' if exceptions else 'verified',
            reconciliation=reconciliation, coverage=coverage,
            classification=(None if filters['category'] is None else dict(
                version=category.CLASSIFICATION_VERSION, sha256=category.CROSSWALK_SHA256,
                reference=access.foundation.reference_version, quality_lines=qualities)),
            source=source_metadata(access),
            limitations=LIMITATIONS, read_only=True, sap_accessed=False,
            unnamed_accounts=unnamed, focus=focus)
        if physical_result is not None:
            result['physical_classification'] = physical_result
            if all(v is None for v in filters.values()) and not base.get('periods'):
                doc_amounts = []
                for relation in (access.sales('sales_document'), access.credit_memo('credit_memo_document')):
                    doc_amounts.append(str(con.execute(f'''SELECT coalesce(sum(CAST(doc_total AS DECIMAL(38,6))),0)
                        FROM {relation} WHERE source_system='SAP_B1_HANA' AND canceled='N'
                        AND currency='BS' AND doc_date>=? AND doc_date<?''',
                        [options['date_from'], options['date_to_exclusive']]).fetchone()[0]))
                result['document_reconciliation'] = dict(invoice_amount=doc_amounts[0],
                    credit_note_amount=doc_amounts[1],
                    header_minus_classified_line_universe=str(Decimal(doc_amounts[0])-Decimal(total['amount'])),
                    credit_notes_subtracted=False, residual_allocated=False,
                    warning='Residuo no asignable: impuestos, descuentos de cabecera y otros ajustes no desagregados; '
                            'incluye cualquier exclusión monetaria declarada. NC documentales separadas, no por estado físico.')
    return validate_result(options, result, _admitted=result['source'], _physical_binding=physical_binding)


def _merge(grouped, period_rows):
    """Join the period readings on the group key. One row per group."""
    if not period_rows:
        return [dict(row) for row in grouped]
    merged = {}
    for reading in period_rows:
        for row in reading['rows']:
            entry = merged.setdefault(row['key'], dict(key=row['key'], amount='0', line_count=0,
                document_count=0, periods=[]))
            entry['periods'].append(dict(period=dict(reading['period']), amount=row['amount'],
                line_count=row['line_count'], document_count=row['document_count']))
    with localcontext() as ctx:
        ctx.prec = 50
        for entry in merged.values():
            entry['amount'] = str(sum((Decimal(p['amount']) for p in entry['periods']), Decimal(0)))
            entry['line_count'] = sum(p['line_count'] for p in entry['periods'])
            entry['document_count'] = sum(p['document_count'] for p in entry['periods'])
    return [merged[k] for k in sorted(merged)]


def validate_result(options, result, *, _admitted=None, _physical_binding=None):
    from .sales_succession import accepts_result, result_binding, admitted_source
    _admitted = _admitted or admitted_source(result)
    if _admitted is not None and _physical_binding is None:
        _physical_binding = getattr(result, 'physical_binding', None)
    parameters(options)
    if (options['group_by'] == 'physical_state' and _admitted is None
            and (result.get('source', {}).get('publication_id'), result.get('source', {}).get('snapshot_id')) not in ACCREDITED_BINDINGS):
        _physical_binding = result_binding(result.get('source', {}), physical=True)
        _admitted = result['source']
    rows = result.get('rows')
    full = result.get('full_breakdown')
    exceptions = result.get('exceptions', [])
    if (result.get('capability') != CAPABILITY or result.get('parameters') != options
            or result.get('plan') != plan_of(options) or result.get('definition') != MEASURE
            or result.get('currency') != 'BS' or result.get('read_only') is not True
            or result.get('sap_accessed') is not False
            or not accepts_result(result.get('source', {}), ACCREDITED_BINDINGS,
                                  physical=options['group_by'] == 'physical_state', _admitted=_admitted)
            or not result['source'].get('updated_at')
            or result.get('limitations') != LIMITATIONS
            or result.get('coverage', {}).get('complete') is not False
            or not isinstance(full, list) or not isinstance(rows, list)
            or rows != full[:options['limit']]
            or result.get('accreditation', 'verified') != ('partial' if exceptions else 'verified')):
        raise ValueError('invalid_commercial_result')
    if any(not isinstance(e, dict) or e.get('excluded') is not True
            or e.get('reason') != 'currency_not_accredited' or e.get('audit_required') is not True
            or e.get('impact') != 'amount_and_position_may_change'
            or not all(isinstance(e.get(k), str) for k in ('doc_entry', 'line_num', 'item_code', 'original_line_total'))
            or (e.get('header_currency') == e.get('line_currency') == 'BS') for e in exceptions):
        raise ValueError('invalid_commercial_exceptions')
    keys = set()
    for row in full:
        if (not isinstance(row.get('key'), str) or not row['key'] or row['key'] in keys
                or not isinstance(row.get('label'), str) or not row['label'].strip()
                or not isinstance(row.get('amount'), str) or not Decimal(row['amount']).is_finite()
                or any(type(row.get(k)) is not int or row[k] < 1 for k in ('line_count', 'document_count'))
                or row['document_count'] > row['line_count']):
            raise ValueError('invalid_commercial_row')
        keys.add(row['key'])
    ordered = sorted(full, key=lambda r: r['key'])
    ordered.sort(key=lambda r: Decimal(r['amount']), reverse=True)
    if full != ordered:
        raise ValueError('invalid_commercial_order')
    expected = reconcile(full, result['total'], options['group_by'])
    if result.get('reconciliation') != expected:
        raise ValueError('invalid_commercial_reconciliation')
    if options['group_by'] == 'physical_state':
        from .physical_sales_dimension import LABELS, EXPLICIT, OBSERVATION_WARNING, validate_profile
        physical = result.get('physical_classification', {})
        audit = physical.get('audit', [])
        binding = (dict(reference=PHYSICAL_REFERENCE, products_sha256=PHYSICAL_PRODUCTS_SHA256,
                        crosswalk_sha256=PHYSICAL_CROSSWALK_SHA256)
                   if result['source']['publication_id'] == PHYSICAL_PUBLICATION
                   else (_physical_binding or result_binding(result['source'], physical=True)))
        if (physical.get('reference') != binding['reference']
                or physical.get('observation_warning') != OBSERVATION_WARNING
                or physical.get('products_sha256') != binding['products_sha256']
                or physical.get('crosswalk_sha256') != binding['crosswalk_sha256']
                or any(r['key'] not in LABELS or r['label'] != LABELS[r['key']] for r in full)
                or sum(Decimal(r['amount']) for r in audit) != Decimal(result['total']['amount'])
                or sum(r['line_count'] for r in audit) != result['total']['line_count']
                or Decimal(physical.get('classified_amount', 'NaN')) != sum(
                    (Decimal(r['amount']) for r in full if r['key'] in EXPLICIT), Decimal(0))
                or Decimal(physical.get('without_explicit_amount', 'NaN')) != sum(
                    (Decimal(r['amount']) for r in full if r['key'] not in EXPLICIT), Decimal(0))):
            raise ValueError('invalid_physical_breakdown')
        validate_profile(physical, full, result['total'])
        documents = result.get('document_reconciliation')
        if documents is not None and (
                documents.get('credit_notes_subtracted') is not False or documents.get('residual_allocated') is not False
                or not Decimal(documents['invoice_amount']).is_finite()
                or not Decimal(documents['credit_note_amount']).is_finite()
                or Decimal(documents['header_minus_classified_line_universe']) !=
                    Decimal(documents['invoice_amount'])-Decimal(result['total']['amount'])):
            raise ValueError('invalid_physical_document_reconciliation')
    universe = result.get('universe_total')
    if universe is not None:
        if (not isinstance(universe, dict) or not isinstance(universe.get('amount'), str)
                or not Decimal(universe['amount']).is_finite()
                or any(type(universe.get(k)) is not int or universe[k] < 0
                       for k in ('product_count', 'line_count', 'document_count'))):
            raise ValueError('invalid_commercial_universe')
    return result


_LOCK = asyncio.Lock()


async def query_commercial_line_amount_by(options, *, timeout_seconds=60):
    parameters(options)
    if _LOCK.locked():
        raise TelchiQueryError('datalake_busy')
    async with _LOCK:
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', __name__, json.dumps(options),
            stdout=asyncio.subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout_seconds)
            payload = json.loads(output)
            if process.returncode:
                reason = payload.get('error')
                raise CommercialAmountError(reason if reason in SAFE_ERRORS else 'commercial_amount_worker_error',
                                            payload.get('evidence'))
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
        print(json.dumps(dict(error=str(exc) if str(exc) in SAFE_ERRORS else 'commercial_amount_unavailable',
                              evidence=getattr(exc, 'evidence', None))))
        sys.exit(1)
