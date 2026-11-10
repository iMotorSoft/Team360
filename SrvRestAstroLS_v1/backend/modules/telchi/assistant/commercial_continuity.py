"""Deterministic scope transitions and useful partial category-share answers.

Uses existing closed capabilities, never SQL, authorization or category inference.
Unknown business labels remain unknown. A share request is not a comparison of
header totals against line amounts.
"""
from copy import deepcopy
import re
import unicodedata

from .state_engine import DEFAULTS

LABELS = {'LAB_FINISHED_PRODUCT': 'Productos terminados de laboratorio',
          'RAW_MATERIAL': 'Materias primas', 'MEDICATIONS': 'Medicamentos',
          'FRACTIONATED_PRODUCT': 'Fraccionados'}
# «Other things/products» is a semantic family, not one literal phrase. It keeps
# the discussed product as a presentation reference instead of a hidden filter.
_OTHER_THINGS = re.compile(
    r'\botr[oa]s?\s+(?:productos?|cosas?|articulos?|items?)\b'
    r'|\bque\s+mas\s+(?:compro|compraron|compra|compras)\b')
_PURCHASE = re.compile(r'\b(?:compro|compraron|compra|compras|adquirio|adquirieron)\b')


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                   if unicodedata.category(c) != 'Mn')


def _reference_product_codes(result):
    """Item codes the cited result was explicitly filtered by, when published."""
    expression = ((result or {}).get('manifest') or {}).get('filter_expression') or ''
    codes = []
    for code in re.findall(r'item_code\s+COMPARE_EQUAL\s+"([^"]+)"', expression):
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,49}', code) and code not in codes:
            codes.append(code)
    return codes if len(codes) <= 20 else []


def _mention_matches_customer(mention, customer, before, reference_result):
    """The mention names the resolved account, not a different unresolved entity."""
    if not isinstance(mention, dict):
        return True
    text = normalized(str(mention.get('text') or ''))
    if not text:
        return True
    if re.fullmatch(r'(?:(?:cuenta|sap|cliente)\s+)*' + re.escape(normalized(customer)), text):
        return True  # The already resolved account code is identity, not a new name.
    label = normalized(((before.get('focus') or {}).get('customer_label') or ''))
    if label and text in label:
        return True
    for row in (reference_result or {}).get('rows') or []:
        code = row.get('card_code') or row.get('key')
        name = normalized(str(row.get('customer_name') or row.get('label') or ''))
        if code == customer and name and text in name:
            return True
    return False


def request_contract(proposal, text, before, reference_result=None):
    """REFINE vs CHANGE_DIMENSION vs NEW_ANALYSIS, before atomic validation.

    Only explicit commercial language triggers these corrections. No code or
    account is synthesized. Model proposals and corrected contracts are audited
    separately by the caller; the State Engine still owns commitment.
    """
    if not isinstance(proposal, dict) or not isinstance(proposal.get('state_delta'), dict):
        return proposal
    q = normalized(text)
    delta = proposal['state_delta']
    sets = {'/' + k.strip().lstrip('/'): v for k, v in delta.get('set', {}).items()}
    unsets = ['/' + k.strip().lstrip('/') for k in delta.get('unset', [])]
    p = deepcopy(proposal)
    p['state_delta'] = dict(set=sets, unset=unsets)

    def put(**values):
        for k, v in values.items():
            path = '/' + k
            sets[path] = deepcopy(v)
            if path in unsets:
                unsets.remove(path)

    if (before.get('excluded_product') or before.get('excluded_products')) and re.fullmatch(r'[¿?¡!.,\s]*(?:y )?(?:mostrame mas|muestrame mas|mas|otros cinco|los siguientes|continua)[¿?¡!.,\s]*', q):
        return dict(intent='REFINE', action='EXECUTE', clarification=None,
                    state_delta={'set': {'/product_offset': min(before.get('product_offset', 0) + 5, 45),
                                         '/limit': 50}, 'unset': []})

    # A new operation must not inherit presentation/analysis instructions.
    if proposal.get('intent') == 'NEW_QUERY' and not _OTHER_THINGS.search(q):
        if before.get('excluded_product'):
            put(excluded_product=None, product_offset=0)
        if before.get('excluded_products'):
            put(excluded_products=None, product_offset=0)
    if proposal.get('intent') == 'REFINE' and not re.search(r'quita.*exclusion|sin exclusion|inclui.*(?:primero|oculto)', q):
        for key in ('excluded_product', 'excluded_products'):
            if before.get(key) and (key_path := '/' + key) in set(sets) | set(unsets):
                put(**{key: before[key]})
    if (before.get('analysis_categories') and proposal.get('intent') != 'EXPLAIN'
            and not re.search(r'porcent|procent|participacion', q)):
        put(analysis_categories=None)

    # A requested purchase list is not a top-one summary. Recover the existing
    # bounded result budget; presentation independently chooses a short page.
    if (_PURCHASE.search(q) and re.search(r'que productos|lista.*productos', q)
            and not re.search(r'mayor|principales|top|primeros|mas vendidos|\d+ productos', q)
            and (sets.get('/customer_target') or before.get('customer_target'))
            and (sets.get('/group_by') or before.get('group_by')) == 'sap_product'
            and not _OTHER_THINGS.search(q)):
        put(limit=50)

    # Hiding a ranking row is presentation, independent of customer filtering.
    if (re.search(r'no (?:muestres|mostres)|oculta|exclui', q)
            and re.search(r'primero|primer producto', q)
            and reference_result and reference_result.get('rows')
            and before.get('group_by') == 'sap_product'):
        code = reference_result['rows'][0].get('key') or reference_result['rows'][0].get('item_code')
        if code:
            put(excluded_product=code, excluded_products=None, product_offset=0,
                limit=50, ranking_by=None)
            p.update(intent='REFINE', action='EXECUTE', clarification=None)
            return p

    if _OTHER_THINGS.search(q) and _PURCHASE.search(q):
        focus = before.get('focus') or {}
        customer = sets.get('/customer_target') or before.get('customer_target') or focus.get('customer')
        product = before.get('product_target')
        if not product and focus.get('product'):
            label = normalized(focus.get('product_label') or '')
            search = normalized(before.get('product_search_text') or '')
            # If an unresolved product search is the active reference and it does
            # not name the focused code, excluding that code would hide a
            # different product. Keep the new investigation without exclusion.
            if not search or (label and search in label):
                product = focus['product']
        reference_codes = [] if product else _reference_product_codes(reference_result)
        if not customer or (not product and not reference_codes):
            return p
        from .business_categories import CATEGORIES
        mention = sets.get('/entity_mention')
        if (isinstance(mention, dict) and mention.get('text') not in CATEGORIES
                and not _mention_matches_customer(mention, customer, before, reference_result)):
            return p  # Do not replace an unresolved new customer with the old account.
        # Category must be explicitly requested again; a reference product is
        # not evidence that every other purchase belongs to its category.
        category = None
        if re.search(r'laboratorio|terminados|misma categoria', q):
            category = before.get('business_category')
        if re.search(r'materias? primas?', q):
            category = 'RAW_MATERIAL'
        elif re.search(r'fraccionados?', q):
            category = 'FRACTIONATED_PRODUCT'
        excluded = [product] if product else reference_codes
        put(metric='sales.commercial_line_amount_by', requested_metrics=['sales.commercial_line_amount_by'],
            schema_version=2, customer_target=customer, product_target=None,
            excluded_product=product, excluded_products=None if product else reference_codes,
            product_offset=0, analysis_categories=None, group_by='sap_product',
            business_category=category, entity_mention=None, breakdown_by=None,
            ranking_target_item_code=None, ranking_detail=None, comparison=None,
            limit=min(5 + len(excluded), 50))
        if before.get('periods') and re.search(r'esos meses|estos meses|mismos meses', q):
            put(period=before['period'], periods=before['periods'], period_mode='union')
        p.update(intent='REFINE', action='EXECUTE', clarification=None)
        return p

    share = bool(re.search(r'porcent|procent|participacion', q))
    categories = []
    for pattern, code in [(r'productos? terminados?', 'LAB_FINISHED_PRODUCT'),
                          (r'materias? primas?', 'RAW_MATERIAL'),
                          (r'medicamentos?', 'MEDICATIONS'),
                          (r'fraccionados?', 'FRACTIONATED_PRODUCT')]:
        if re.search(pattern, q):
            categories.append(code)
    # A percentage scoped to a customer/product is not a global composition.
    from .business_categories import CATEGORIES
    mention = sets.get('/entity_mention')
    category_label = (isinstance(mention, dict) and re.fullmatch(
        r'productos? terminados?(?: de laboratorio)?|materias? primas?|medicamentos?|fraccionados?',
        normalized(mention.get('text', ''))))
    unresolved_entity = isinstance(mention, dict) and mention.get('text') not in CATEGORIES and not category_label
    customer_name = normalized((before.get('focus') or {}).get('customer_label', '')).split()
    named_customer = bool(customer_name and len(customer_name[0]) >= 3
                          and re.search(r'\b' + re.escape(customer_name[0]) + r'\b', q))
    scoped = unresolved_entity or named_customer or re.search(r'cliente|\b[A-Za-z]\d{4,}\b', text, re.I)
    global_request = bool(re.search(r'venta[s]? (total|global)|total de (la[s]? )?venta|composicion|ventas? de (enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)', q))
    if (share and categories and not scoped
            and (global_request or before.get('analysis_categories') or not before.get('customer_target'))):
        period = sets.get('/period') or before.get('period')
        # Keep the period of the percentage analysis in a short follow-up.
        if before.get('analysis_categories') and not re.search(r'enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|20\d{2}', q):
            period = before.get('period')
        if not period:
            return p
        # Do not erase explicitly requested unsupported branch/channel filters.
        if (sets.get('/branches') or sets.get('/sales_channel')
                or (not global_request and (before.get('branches') or before.get('sales_channel')))):
            return p
        values = deepcopy(DEFAULTS)
        values.update(schema_version=2, metric='sales.net_amount', requested_metrics=['sales.net_amount'],
                      period=period, analysis_categories=categories)
        p = dict(intent='NEW_QUERY', action='EXECUTE',
                 state_delta={'set': {'/' + k: v for k, v in values.items() if k not in {'pending', 'product_context'}}, 'unset': []},
                 clarification=None)
    return p


def component_states(state):
    """Closed reusable category primitive; no fabricated classification."""
    from .business_categories import CATEGORIES
    for code in state['analysis_categories']:
        if code in CATEGORIES and code != 'UNKNOWN':
            part = deepcopy(state)
            part.update(analysis_categories=None, business_category=code,
                        entity_mention=None, limit=10)
            yield code, part


def denominator_accredited(state, denominator):
    """Accredit the global base independently of any category numerator."""
    from decimal import Decimal, InvalidOperation
    try:
        if not denominator or denominator.get('exceptions') or denominator.get('accreditation') != 'verified':
            return False
        options = denominator['parameters']
        whole = Decimal(denominator['total']['amount'])
        return (not any(options['filters'].values())
                and options['date_from'] == state['period']['start']
                and options['date_to_exclusive'] == state['period']['end_exclusive']
                and denominator['currency'] == 'BS'
                and Decimal(denominator.get('reconciliation', {}).get('difference', 'NaN')) == 0
                and whole.is_finite() and whole > 0)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return False


def shares(state, components, denominator):
    """Decimal only, same pinned source/period/measure, no excluded currencies.

    Category and global readers share scoped_source/scoped_aggregate and the
    immutable classification hash. No header amount participates. Reconciliation
    is validated by the existing global capability before this composition.
    """
    from decimal import Decimal, localcontext
    if not denominator_accredited(state, denominator):
        return {}
    options = denominator['parameters']
    whole = Decimal(denominator['total']['amount'])
    values = {}
    for code, component in components.items():
        result = component.get('result')
        if not result or result.get('exceptions') or component.get('status') == 'partial':
            continue
        p = result['parameters']
        if (result['source'] != denominator['source'] or result['definition'] != denominator['definition']
                or result['currency'] != denominator['currency'] or result['coverage'] != denominator['coverage']
                or p['date_from'] != options['date_from'] or p['date_to_exclusive'] != options['date_to_exclusive']
                or p['category'] != code):
            continue
        amount = Decimal(result['rows'][0]['amount'])
        if not amount.is_finite() or not 0 <= amount <= whole or result['rows'][0]['line_count'] == 0:
            continue
        with localcontext() as ctx:
            ctx.prec = 50
            values[code] = str((amount / whole * 100).quantize(Decimal('0.01')))
    return values


def format_category_analysis(state, components, denominator=None, percentages=None):
    from .capabilities import business_money, business_date
    from .business_scope import period_label
    percentages = percentages or {}
    lines = [f'Composición de ventas globales — {period_label([state["period"]])}.']
    for code in state['analysis_categories']:
        component = components.get(code)
        if component and component.get('result'):
            result = component['result']
            row = result.get('total') or result['rows'][0]
            share = f' — {business_money(percentages[code])} %' if code in percentages else ' — porcentaje no acreditado'
            if not row['line_count']:
                lines.append(f'{LABELS.get(code, code)}: sin líneas observadas; no acredita ventas cero ni una participación.')
            else:
                lines.append(f'{LABELS.get(code, code)}: Bs {business_money(row["amount"])}{share}.')
                supported = (result.get('classification') or {}).get('quality_lines', {}).get('SUPPORTED', 0)
                if supported:
                    unit = 'línea' if supported == 1 else 'líneas'
                    lines.append(f'Incluye {supported} {unit} con clasificación respaldada (SUPPORTED), no toda validada.')
                if result.get('exceptions'):
                    lines.append(f'Resultado parcial: operaciones excluidas por moneda no acreditada: {len(result["exceptions"])}. No las convertí. El importe puede cambiar; no calculé su participación.')
        elif code == 'MEDICATIONS':
            lines.append('Medicamentos: clasificación no acreditada; no los equiparo con productos terminados. Todavía no puedo determinar su porcentaje: falta identificar qué importe de estas ventas corresponde a medicamentos.')
        else:
            lines.append(f'{LABELS.get(code, code)}: no pude acreditar el importe; los demás resultados siguen disponibles.')
    if denominator_accredited(state, denominator):
        lines.append(f'Base: Bs {business_money(denominator["total"]["amount"])} de líneas comerciales activas BS del mismo período, sin filtros de cliente o producto. No es facturación documental con impuestos.')
    else:
        lines.append('Porcentaje no calculado: falta acreditar un total global de líneas con el mismo universo monetario, moneda y exclusiones. La facturación documental con impuestos no es ese denominador.')
    coverages = { (r['result']['coverage'].get('first_date'), r['result']['coverage'].get('last_date'))
                  for r in components.values() if r.get('result') }
    for first, last in sorted(coverages, key=str):
        if first and last:
            lines.append(f'Cobertura observada: {business_date(first[:10])} al {business_date(last[:10])}; no certifica cierre completo.')
    lines.append('Importes sin IVA de línea, antes de notas de crédito y ajustes globales. Clasificación actual, no histórica.')
    if len(state['analysis_categories']) > 1:
        lines.append('No sumo las categorías como una partición: medicamentos puede superponerse con otras categorías y no tiene identificación acreditada.')
    lines.append('Puedo ampliar los importes acreditados por producto.')
    return '\n\n'.join(lines)
