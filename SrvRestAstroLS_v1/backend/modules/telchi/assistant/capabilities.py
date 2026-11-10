"""Closed sales catalog. Never substitutes documentary quantity for revenue."""
import re
from dataclasses import dataclass
from decimal import Decimal

from .state_engine import SalesState, validate, entity_represented_by_target
from modules.telchi.datalake.invoice_lines_query import query_invoice_lines, validate_result as validate_invoice_lines
from modules.telchi.datalake.sales_query import (
    PERMISSIONS, MONETARY_OPERATION, MONETARY_PERMISSION, query_sales, validate_result,
)

from modules.telchi.datalake.product_sales_query import (
    PERMISSIONS as PRODUCT_PERMISSIONS, query_products, validate_result as validate_product_result,
)
from modules.telchi.datalake.messaging_sales_query import (
    CAPABILITY, PERIOD_FROM, PERIOD_TO_EXCLUSIVE, query_fixed_sales,
)


@dataclass(frozen=True)
class Availability:
    allowed: bool
    reason: str | None = None
    category: str | None = None


class ProductResolutionError(ValueError):
    """A product mention that cannot be resolved to exactly one ItemCode."""

    def __init__(self, candidates, reason='product_resolution_required'):
        super().__init__(reason)
        self.candidates = list(candidates)
        self.reason = reason


class SalesCapabilities:
    def __init__(self, *, query=query_fixed_sales, sales_query=query_sales, product_query=query_products, category_query=None, ranking_query=None, commercial_query=None, timeout_seconds=60):
        from modules.telchi.datalake.category_line_amount_query import query_category_line_amount
        self.category_query = category_query or query_category_line_amount
        from modules.telchi.datalake.product_line_amount_ranking_query import query_product_line_amount_ranking
        self.ranking_query = ranking_query or query_product_line_amount_ranking
        from modules.telchi.datalake.commercial_line_amount_by_query import query_commercial_line_amount_by
        self.commercial_query = commercial_query or query_commercial_line_amount_by
        self.product_query = product_query
        self.sales_query = sales_query
        self.query = query
        self.timeout_seconds = timeout_seconds

    async def invoice_lines(self, options):
        return validate_invoice_lines(options, await query_invoice_lines(options, timeout_seconds=self.timeout_seconds))

    async def invoice_amount(self, options):
        from modules.telchi.datalake.invoice_amount_query import query_invoice_amount, validate_result
        return validate_result(options, await query_invoice_amount(options, timeout_seconds=self.timeout_seconds))

    def availability(self, state: SalesState) -> Availability:
        validate(state)
        if state['pending']:
            return Availability(False, 'Todavía falta resolver una aclaración.', 'CAPABILITY_MISSING')
        metrics = state.get('requested_metrics') or [state['metric']]
        from modules.telchi.datalake.operational_query import OPERATIONS, SNAPSHOT_METRICS
        if state['metric'] in OPERATIONS:
            from .operational import options_for
            try:
                options_for(state)
            except ValueError as exc:
                return Availability(False, 'El alcance requiere un período explícito o un código de producto acreditado, sin filtros no compatibles: ' + str(exc), 'OPERATIONAL_SCOPE_UNAVAILABLE')
            return Availability(True)
        from .business_categories import category_code
        if state['metric'] == 'sales.commercial_line_amount_by':
            return self.commercial_availability(state, metrics)
        if state['metric'] == 'sales.product_line_amount_ranking':
            if (not category_code(state) or category_code(state) == 'UNKNOWN'
                    or metrics != ['sales.product_line_amount_ranking']
                    or state['branches'] or state['sales_channel']
                    or ((state['comparison'] or state.get('ranking_detail')) and not state.get('ranking_target_item_code'))
                    or state.get('temporal_reference') or state.get('product_search_text')
                    or state.get('selected_item_codes') or state.get('product_context')):
                return Availability(False, 'El ranking monetario no está disponible para ese universo o esos filtros.', 'RANKING_UNAVAILABLE')
            if not state['period']:
                return Availability(False, 'El ranking monetario requiere un período concreto.', 'PERIOD_UNRESOLVED')
            return Availability(True)
        if state.get('ranking_target_item_code'):
            return Availability(False, 'El producto objetivo corresponde únicamente al ranking monetario.', 'RANKING_UNAVAILABLE')
        if category_code(state):
            if (category_code(state) == 'UNKNOWN' or metrics != ['sales.net_amount']
                    or state['branches'] or state['sales_channel'] or state['comparison']
                    or state.get('temporal_reference') or state.get('product_search_text')
                    or state.get('selected_item_codes') or state.get('product_context')
                    or state.get('limit', 10) != 10):
                return Availability(False, 'La operación solicitada por categoría no está acreditada.', 'CATEGORY_CAPABILITY_UNAVAILABLE')
            if not state['period']:
                return Availability(False, 'La consulta por categoría requiere un período concreto.', 'PERIOD_UNRESOLVED')
            from modules.telchi.datalake.category_line_amount_query import parameters
            try:
                parameters(dict(category=category_code(state), currency='BS',
                    date_from=state['period']['start'], date_to_exclusive=state['period']['end_exclusive']))
            except ValueError:
                return Availability(False, 'El período por categoría excede el contrato.', 'CATEGORY_CAPABILITY_UNAVAILABLE')
            return Availability(True)
        if state['metric'] in PRODUCT_PERMISSIONS:
            # An explicit ItemCode may arrive as product_target. It is still
            # resolved through products.search before any sales read; the code
            # is never trusted as a catalog existence proof.
            product_reference = state.get('product_search_text') or (
                state.get('product_target') if state['metric'] == 'sales.by_products' else None)
            if (state['branches'] or state['sales_channel'] or state['comparison'] or state.get('temporal_reference')
                    or not product_reference
                    or not set(metrics) <= {'products.search', 'sales.by_products', 'sales.net_amount', 'sales.source_top_items'}):
                return Availability(False, 'La búsqueda de productos necesita texto o un código explícito y no admite esos filtros.', 'CAPABILITY_MISSING')
            return Availability(True)
        if state.get('product_search_text') or state.get('selected_item_codes') or state.get('product_context'):
            return Availability(False, 'La consulta conserva productos seleccionados. Una operación global no puede sustituir sus ventas ni su importe; el neto por producto no está acreditado. Puedo consultar líneas y cantidades documentales por sus códigos.', 'MAPPING_MISSING')
        if 'sales.net_amount' in metrics:
            if not set(metrics) <= {'sales.net_amount', 'sales.source_top_items'}:
                return Availability(False, 'Las operaciones documentales no tienen un contrato conjunto con importes.', 'METRIC_MISSING')
            if state['comparison']:
                return Availability(False, 'Todavía no puedo calcular la diferencia entre períodos en esta conversación. '
                                    'Los importes consultados siguen disponibles; no voy a inventar una comparación.', 'COMPARISON_UNSUPPORTED')
            if state.get('entity_mention') or state['branches'] or state['sales_channel'] not in (None, 'HORIZONTAL'):
                return Availability(False, 'El importe documental no admite filtros de entidad, sucursal, canal ni comparación no acreditados. No es un problema con la fecha elegida.', 'MAPPING_MISSING')
            if state.get('temporal_reference'):
                return Availability(False, 'La cobertura global no acredita todavía un mes monetario por entidad.', 'TEMPORAL_METADATA_MISSING')
            if not state['period']:
                return Availability(False, 'La facturación requiere un período concreto.', 'PERIOD_UNRESOLVED')
            # A single-row aggregate has no rows to limit: `/limit` belongs to the
            # row-producing operation that requested it and is not a parameter of
            # this one. It never makes the aggregate unavailable.
            return Availability(True)
        if state['metric'] in PERMISSIONS:
            if metrics != [state['metric']]:
                return Availability(False, 'Las métricas adicionales no tienen un contrato conjunto aprobado.', 'METRIC_MISSING')
            if (state['period'] or state['branches'] or state['sales_channel'] or state['comparison']
                    or state.get('entity_mention')
                    or (state['metric'] == 'sales.latest_documents' and state.get('temporal_reference'))):
                return Availability(False, 'Esta operación documental no admite esos filtros o métricas.', 'MAPPING_MISSING')
            if state['metric'] == 'sales.coverage' and state.get('limit', 10) != 10:
                return Availability(False, 'Cobertura no admite límite de documentos.', 'CAPABILITY_MISSING')
            return Availability(True)
        if state.get('limit', 10) != 10:
            return Availability(False, 'El límite parametrizado sólo está aprobado para últimas facturas.', 'CAPABILITY_MISSING')
        if state.get('temporal_reference'):
            return Availability(False, 'Entendí la referencia al último mes registrado. No tengo metadata temporal habilitada para determinarlo por entidad y métrica; no voy a inventar un mes.', 'TEMPORAL_METADATA_MISSING')
        if state.get('entity_mention'):
            return Availability(False, 'La entidad mencionada todavía no tiene una resolución ni un filtro comercial aprobado en esta consulta.', 'MAPPING_MISSING')
        if state['metric'] != 'sales.source_top_items':
            return Availability(False, 'Esta consulta todavía no está disponible.', 'CAPABILITY_MISSING')
        if state['branches']:
            return Availability(False, 'El mapping de sucursal para esta consulta todavía no está aprobado.', 'MAPPING_MISSING')
        if state['sales_channel']:
            return Availability(False, 'El filtro de canal no está habilitado en esta consulta.', 'MAPPING_MISSING')
        if state['comparison']:
            return Availability(False, 'La comparación todavía no está disponible para esta métrica.', 'CAPABILITY_MISSING')
        if state['period'] != {'start': PERIOD_FROM, 'end_exclusive': PERIOD_TO_EXCLUSIVE}:
            period = state['period']
            if period is None:
                return Availability(False, 'La solicitud todavía no tiene un período concreto; no se ejecutó ninguna consulta.', 'PERIOD_UNRESOLVED')
            if period and (period['start'] < PERIOD_FROM or period['end_exclusive'] > PERIOD_TO_EXCLUSIVE):
                return Availability(False, 'El período solicitado excede la ventana de la consulta documental fija (01/01–15/09/2026); no certifica la cobertura de todos los datos Foundation.', 'COVERAGE_GAP')
            return Availability(False, 'El período solicitado está dentro de la ventana documental, pero esta capability sólo ejecuta la ventana fija completa (01/01–15/09/2026). Los filtros por mes todavía no están habilitados.', 'PERIOD_PARAMETER_UNSUPPORTED')
        return Availability(True)

    def commercial_availability(self, state, metrics):
        """A business scope is executable only on an accredited plan."""
        from .business_categories import CATEGORIES
        entity = state.get('entity_mention')
        if state.get('comparison') and state.get('group_by') != 'physical_state':
            return Availability(False, 'Esta operación no lleva un período de comparación: la comparación entre '
                                'meses se lee con el desglose por mes del conjunto de períodos.', 'COMPARISON_UNSUPPORTED')
        if (metrics != ['sales.commercial_line_amount_by'] or state['branches']
                or state['sales_channel']
                or state.get('temporal_reference') or state.get('selected_item_codes')
                or state.get('product_context')
                or state.get('semantic_references')):
            return Availability(False, 'Esta operación comercial no admite esos filtros o métricas.', 'MAPPING_MISSING')
        # A named product may arrive as text for a customer drilldown. The service
        # resolves it against the accredited catalog before compiling the plan;
        # it never invents a code and never substitutes a global scope on failure.
        needs_product_resolution = (state.get('group_by') == 'card_code'
            and state.get('product_target') is None
            and bool(state.get('product_search_text')))
        if state.get('product_search_text') and not needs_product_resolution:
            return Availability(False, 'Esta operación comercial no admite esos filtros o métricas.', 'MAPPING_MISSING')
        if (isinstance(entity, dict) and entity.get('text') not in CATEGORIES
                and not entity_represented_by_target(state)):
            return Availability(False, 'La entidad mencionada todavía no tiene un filtro comercial aprobado en esta consulta.', 'MAPPING_MISSING')
        category = state.get('business_category')
        if category is not None and category not in CATEGORIES:
            return Availability(False, 'La categoría solicitada no está acreditada.', 'CATEGORY_CAPABILITY_UNAVAILABLE')
        if not state.get('group_by'):
            return Availability(False, 'Necesito saber si agrupo el importe por producto o por cliente facturado.', 'DIMENSION_NOT_ACCREDITED')
        if state.get('breakdown_by') == 'period' and not state.get('periods'):
            return Availability(False, 'El desglose por mes necesita el conjunto de períodos.', 'PERIOD_SET_UNSUPPORTED')
        if not state.get('period'):
            return Availability(False, 'Esta consulta comercial requiere un período concreto.', 'PERIOD_UNRESOLVED')
        from .business_plan import build, PlanError
        try:
            build(state)
        except PlanError as exc:
            reason = str(exc)
            if reason == 'period_unresolved':
                return Availability(False, 'Esta consulta comercial requiere un período concreto.', 'PERIOD_UNRESOLVED')
            if reason == 'dimension_not_accredited':
                return Availability(False, 'Esa dimensión comercial no está acreditada.', 'DIMENSION_NOT_ACCREDITED')
            if reason == 'period_set_unresolved':
                return Availability(False, 'El desglose por mes necesita el conjunto de períodos.', 'PERIOD_SET_UNSUPPORTED')
            return Availability(False, 'El alcance solicitado excede el contrato comercial acreditado.', 'MAPPING_MISSING')
        return Availability(True)

    def required_permissions(self, state):
        if state.get('analysis_categories'):
            from modules.telchi.datalake.category_line_amount_query import PERMISSION as category_permission
            from modules.telchi.datalake.commercial_line_amount_by_query import PERMISSION as commercial_permission
            return [category_permission, commercial_permission]
        if (state.get('metric') == 'sales.commercial_line_amount_by'
                and state.get('group_by') == 'card_code'
                and state.get('product_target') is None
                and state.get('product_search_text')):
            # Resolving a name is a catalog read under its own permission.
            return [PRODUCT_PERMISSIONS['products.search'], self.required_permission(state)]
        if state['metric'] in PRODUCT_PERMISSIONS:
            return [PRODUCT_PERMISSIONS['products.search']] + (
                [PRODUCT_PERMISSIONS['sales.by_products']] if state['metric'] == 'sales.by_products' else [])
        permission = self.required_permission(state)
        return [permission] if permission else []

    def required_permission(self, state):
        from modules.telchi.datalake.operational_query import PERMISSIONS as OPERATIONAL_PERMISSIONS
        if state['metric'] in OPERATIONAL_PERMISSIONS:
            return OPERATIONAL_PERMISSIONS[state['metric']]
        if state['metric'] == 'sales.commercial_line_amount_by':
            from modules.telchi.datalake.commercial_line_amount_by_query import PERMISSION
            return PERMISSION
        if state['metric'] == 'sales.product_line_amount_ranking':
            from modules.telchi.datalake.product_line_amount_ranking_query import PERMISSION
            return PERMISSION
        from .business_categories import category_code
        if category_code(state):
            from modules.telchi.datalake.category_line_amount_query import PERMISSION
            return PERMISSION
        if state['metric'] in PRODUCT_PERMISSIONS:
            return PRODUCT_PERMISSIONS[state['metric']]
        if 'sales.net_amount' in (state.get('requested_metrics') or [state['metric']]):
            return MONETARY_PERMISSION
        if state['metric'] == 'sales.source_top_items':
            return 'telchi.sales.source_quantity.read.v1'
        return PERMISSIONS.get(state['metric'])

    async def execute(self, state: SalesState) -> dict:
        if not self.availability(state).allowed:
            raise ValueError('capability_not_available')
        from modules.telchi.datalake.operational_query import OPERATIONS, query_operational
        if state['metric'] in OPERATIONS:
            from .operational import options_for
            return await query_operational(state['metric'], options_for(state), timeout_seconds=self.timeout_seconds)
        from .business_categories import category_code
        if state['metric'] == 'sales.commercial_line_amount_by':
            from .business_plan import build
            from modules.telchi.datalake.commercial_line_amount_by_query import validate_result as validate_commercial
            if (state.get('group_by') == 'card_code' and state.get('product_target') is None
                    and state.get('product_search_text')):
                await self.resolve_commercial_product(state)
            options = build(state)
            return validate_commercial(options, await self.commercial_query(options, timeout_seconds=self.timeout_seconds))
        if state['metric'] == 'sales.product_line_amount_ranking':
            from modules.telchi.datalake.product_line_amount_ranking_query import validate_result as validate_ranking
            options = dict(category=category_code(state), currency='BS', date_from=state['period']['start'],
                date_to_exclusive=state['period']['end_exclusive'], limit=state.get('limit', 10))
            if state.get('ranking_target_item_code'):
                from .historical_ranking import execute
                return await execute(state, category_code(state), self.ranking_query, self.timeout_seconds)
            return validate_ranking(options, await self.ranking_query(options, timeout_seconds=self.timeout_seconds))
        if category_code(state):
            from modules.telchi.datalake.category_line_amount_query import validate_result as validate_category
            options = dict(category=category_code(state), currency='BS', date_from=state['period']['start'],
                date_to_exclusive=state['period']['end_exclusive'])
            return validate_category(options, await self.category_query(options, timeout_seconds=self.timeout_seconds))
        if state['metric'] in PRODUCT_PERMISSIONS:
            return await self.execute_products(state)
        if 'sales.net_amount' in (state.get('requested_metrics') or [state['metric']]):
            options = dict(date_from=state['period']['start'],
                           date_to_exclusive=state['period']['end_exclusive'], currency='BS')
            if state['sales_channel']:
                options['sales_channel'] = state['sales_channel']
            result = await self.sales_query(MONETARY_OPERATION, options, timeout_seconds=self.timeout_seconds)
            result = validate_result(MONETARY_OPERATION, options, result)
            result['requested_metrics'] = state.get('requested_metrics') or [state['metric']]
            return result
        if state['metric'] in PERMISSIONS:
            options = {'limit': state.get('limit', 10)} if state['metric'] == 'sales.latest_documents' else {}
            result = await self.sales_query(state['metric'], options, timeout_seconds=self.timeout_seconds)
            return validate_result(state['metric'], options, result)
        result = await self.query(timeout_seconds=self.timeout_seconds)
        # Reject incomplete/mismatched contracts, including units and source.
        if (result.get('capability') != CAPABILITY or result.get('read_only') is not True
                or result.get('sap_accessed') is not False
                or not result.get('foundation_publication_id') or not result.get('foundation_data_as_of')
                or result.get('period_from') != PERIOD_FROM
                or result.get('period_to_exclusive') != PERIOD_TO_EXCLUSIVE
                or not isinstance(result.get('ducklake_snapshot_id'), int)
                or not isinstance(result.get('rows'), list) or len(result['rows']) > 10):
            raise ValueError('invalid_foundation_result')
        for row in result['rows']:
            if not isinstance(row.get('item_code'), str) or not Decimal(row['quantity']).is_finite():
                raise ValueError('invalid_quantity')
        return dict(capability=CAPABILITY, parameters=state, metric='source_document_quantity_by_item',
                    period=state['period'], rows=[dict(item_code=r['item_code'], quantity=r['quantity']) for r in result['rows']],
                    source=dict(publication_id=result['foundation_publication_id'],
                                snapshot_id=result['ducklake_snapshot_id'], updated_at=result['foundation_data_as_of']),
                    coverage='fixed_query_window; historical completeness not certified',
                    units='source_document_units_per_item; not comparable across items',
                    limitations='Invoices only, no cancellation filter or credit subtraction; not net sales or revenue.')

    async def resolve_commercial_product(self, state):
        """Resolve a product mention to exactly one accredited SAP ItemCode.

        Uses the existing products.search capability (its own permission is
        validated by the handler) and the shared normalization. The model never
        provides an ItemCode. Ambiguity is a question, not a guessed filter.
        """
        from modules.telchi.datalake.product_sales_query import normalize
        text = state['product_search_text']
        tokens = [t for t in normalize(text).split() if t not in STOPWORDS]
        if not tokens:
            raise ProductResolutionError([], 'empty_product_mention')
        # The catalog search is a literal containment test over the published
        # label. A real mention carries packaging the label writes differently
        # («soda cáustica x25 kg» vs «SODA CAUSTICA (HIDROXIDO DE SODIO) x 25kg.»),
        # so the whole phrase cannot be the only attempt: search relaxation is
        # progressive, and every attempt still has to name the same product
        # through its significant tokens. Packaging only ranks candidates.
        core = [t for t in tokens if not packaging_token(t)] or tokens
        attempts = []
        for candidate in (text, ' '.join(tokens), ' '.join(core),
                          ' '.join(core[:2]) if len(core) > 2 else None):
            if candidate and normalize(candidate) not in attempts:
                attempts.append(normalize(candidate))
        candidates = []
        for attempt in attempts:
            options = {'text': attempt, 'limit': 20}
            catalog = validate_product_result('products.search', options,
                await self.product_query('products.search', options, timeout_seconds=self.timeout_seconds))
            found = [r for r in catalog['rows'] if all(mention_in_row(t, r) for t in core)]
            if found:
                candidates = found
                break
        if not candidates:
            raise ProductResolutionError([], 'product_not_found')
        sellable = [r for r in candidates if r.get('sell_item') == 'Y'] or candidates
        # The candidate that names the whole mention, packaging included, wins;
        # an equal coverage is real ambiguity and is asked, never guessed.
        coverage = {id(r): sum(mention_in_row(t, r) for t in tokens) for r in sellable}
        best_coverage = max(coverage.values())
        best = [r for r in sellable if coverage[id(r)] == best_coverage]
        if len(best) != 1:
            # A unique sellable item ends the ambiguity; otherwise ask.
            raise ProductResolutionError(best)
        chosen = best[0]
        state['product_target'] = chosen['item_code']
        state['product_search_text'] = None
        state['product_context'] = None
        state['selected_item_codes'] = []
        state['focus'] = dict(state.get('focus') or {},
                             product=chosen['item_code'], product_label=chosen['description'])
        validate(state)
        return dict(item_code=chosen['item_code'], label=chosen['description'],
                    candidates=len(candidates))

    async def execute_products(self, state):
        from copy import deepcopy
        if state.get('product_target') and not state.get('product_search_text'):
            # One canonical path: an explicit code is looked up in the catalog
            # and selected only if it exists there. No synthesized result rows.
            state = deepcopy(state)
            state['product_search_text'] = state['product_target']
            state['product_target'] = None
        options = {'text': state['product_search_text'], 'limit': 20}
        catalog = state.get('product_context')
        if catalog is None:
            catalog = validate_product_result('products.search', options,
                await self.product_query('products.search', options, timeout_seconds=self.timeout_seconds))
        validate_product_result('products.search', catalog['parameters'], catalog)
        candidates = catalog['rows']
        selected = list(state.get('selected_item_codes') or [])
        if not selected and candidates and not catalog['truncated']:
            best = candidates[0]['match_rank']
            relevant = [r['item_code'] for r in candidates if r['match_rank'] == best
                        and (best == 0 or r.get('sell_item') == 'Y')]
            if best < 2 or len(relevant) == 1:
                selected = relevant
        next_state = deepcopy(state)
        next_state.update(product_context=deepcopy(catalog), selected_item_codes=selected)
        validate(next_state)
        if state['metric'] == 'products.search' or not selected:
            result = deepcopy(catalog)
            result['selection_required'] = bool(candidates) and not selected
        else:
            options = dict(namespace='SAP_HANA', item_codes=selected, limit=state.get('limit', 10))
            if state['period']:
                options.update(date_from=state['period']['start'], date_to_exclusive=state['period']['end_exclusive'])
            result = validate_product_result('sales.by_products', options,
                await self.product_query('sales.by_products', options, timeout_seconds=self.timeout_seconds))
            result['products'] = [r for r in candidates if r['item_code'] in selected]
            result['requested_metrics'] = state.get('requested_metrics') or [state['metric']]
        state.update(next_state)  # IDs only originate in a validated real search.
        return result


MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
          'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
STOPWORDS = {'a', 'al', 'de', 'del', 'el', 'en', 'la', 'las', 'le', 'les', 'lo',
             'los', 'por', 'para', 'que', 'se', 'un', 'una', 'x'}
# Quantity/packaging noise of a commercial mention. It never identifies the
# product and the catalog writes it with other spacing, so it is scored instead
# of demanded from the published label.
_PACKAGING = re.compile(
    r'^x?\d+(?:[.,]\d+)?(?:kilos?|kg|gramos?|grs?|gr|mg|ml|cc|litros?|lt|l|'
    r'unidades?|un|u|cm|mm|m)?$'
    r'|^(?:kilos?|kg|gramos?|grs?|gr|mg|ml|cc|litros?|lt|unidades?|un|cm|mm)$')


def packaging_token(token):
    return bool(_PACKAGING.match(token))


def _compact(text):
    """Join a number and its unit so «x 25kg» and «x25 kg» compare equal."""
    return re.sub(r'(?<=[0-9])\s+(?=[a-z])|(?<=[a-z])\s+(?=[0-9])', '', text)


def mention_in_row(token, row):
    """A mention token names this catalog row (description or ItemCode)."""
    from modules.telchi.datalake.product_sales_query import normalize
    description = normalize(str(row.get('description') or ''))
    return (token in description or token in _compact(description)
            or token in normalize(str(row.get('item_code') or '')))


def business_date(value):
    from datetime import date
    try:
        day = date.fromisoformat(value[:10])
        return f'{day.day} de {MONTHS[day.month-1]} de {day.year}'
    except (ValueError, TypeError, IndexError):
        return 'fecha no disponible'


def business_money(value):
    return f'{Decimal(value):,.2f}'.translate(str.maketrans({',': '.', '.': ','}))


def format_result(result, scope=None):
    from modules.telchi.datalake.operational_query import CONTRACT as OPERATIONAL_CONTRACT
    if result.get('contract') == OPERATIONAL_CONTRACT:
        from .operational import format_operational
        return format_operational(result)
    rows = result['rows']
    if result.get('view') == 'historical_position':
        from .historical_ranking import format_historical
        return format_historical(result)
    if result['capability'] == 'sales.commercial_line_amount_by.v1':
        from .commercial_answer import format_commercial
        return format_commercial(result, scope)
    if result['capability'] == 'sales.product_line_amount_ranking.v1':
        from .business_categories import RANKING_LABELS
        from datetime import date, timedelta
        options = result['parameters']
        start, end = date.fromisoformat(options['date_from']), date.fromisoformat(options['date_to_exclusive'])
        period = (f'{MONTHS[start.month-1]} de {start.year}'
                  if start.day == end.day == 1 and (end-start).days <= 31 else
                  f"del {business_date(start.isoformat())} al {business_date((end-timedelta(days=1)).isoformat())}")
        from .historical_ranking import exception_text
        exceptions = result.get('exceptions', [])
        if not rows and exceptions:
            return ('No hay importes compatibles acreditados para este ranking. ' + exception_text(exceptions))
        if not rows:
            return ('No encontré productos con líneas comerciales en ese período y categoría. '
                    'Esto no acredita ventas cero fuera de la cobertura disponible.')
        article = 'Las' if options['category'] == 'RAW_MATERIAL' else 'Los'
        text = f"{article} {len(rows)} {RANKING_LABELS[options['category']]} con mayor importe vendido en {period}\n\n"
        text += '\n'.join(f"{i}. {r['item_code']} · {r['description']} — Bs {business_money(r['amount'])}"
                          for i, r in enumerate(rows, 1))
        if exceptions:
            text += '\n\nRanking parcial entre operaciones verificadas en BS. ' + exception_text(exceptions)
        text += '\n\nImportes sin IVA, antes de notas de crédito.'
        last = result['coverage']['last_date']
        if last:
            text += f" Datos disponibles hasta el {business_date(last)}."
        text += ' Descuentos de línea incluidos; sin ajustes globales. No son precios unitarios ni un cierre mensual completo.'
        return text
    if result['capability'] == 'sales.category_line_amount.v1':
        from .business_categories import CATEGORIES
        row = rows[0]
        options = result['parameters']
        label = CATEGORIES[options['category']].lower()
        from datetime import date, timedelta
        start, end = date.fromisoformat(options['date_from']), date.fromisoformat(options['date_to_exclusive'])
        period = (f'{MONTHS[start.month-1]} de {start.year}'
                  if start.day == end.day == 1 and (end-start).days <= 31 else
                  f"del {business_date(start.isoformat())} al {business_date((end-timedelta(days=1)).isoformat())}")
        if not row['line_count']:
            return (f'No encontré líneas comerciales de {label} {period}. '
                    'Esto no acredita ventas cero: la cobertura completa no está certificada.')
        text = (f"Registramos Bs {business_money(row['amount'])} en importe registrado en líneas comerciales de {label}, {period}. "
                f"Corresponde a {row['product_count']} productos, {row['line_count']} líneas y {row['document_count']} facturas. "
                f"La cobertura documental observada va del {business_date(result['coverage']['first_date'])} "
                f"al {business_date(result['coverage']['last_date'])}; no certifica el período completo. "
                'No incluye IVA de línea ni descuenta notas de crédito. Los descuentos propios ya están reflejados; '
                'no incorpora ajustes globales ni otros componentes de cabecera. Clasificación actual, no histórica.')
        if 'SUPPORTED' in result['classification']['quality_lines']:
            text += ' Incluye clasificación respaldada (SUPPORTED), no toda validada.'
        return text
    if result['capability'] == 'sales.invoice_amount.v1':
        row = rows[0]
        return (f"La factura N.º {result['document']['doc_num']} tiene un total documental de "
                f"{row['currency']} {business_money(row['amount'])}. "
                'Es el importe de la factura, no lo cobrado ni el saldo pendiente. '
                f"Información actualizada al {business_date(result['source']['updated_at'])}.")
    if result['capability'] == 'sales.invoice_lines.v1':
        details = f"Factura N.º {result['document']['doc_num']}\n\nProductos:\n"
        details += ('\n'.join(f"{i}. {r['description'] or 'Descripción no disponible'} ({r['item_code']}) — cantidad documental {r['quantity']}."
                    for i, r in enumerate(rows, 1)) or 'No hay líneas publicadas para esta factura.')
        return (details + '\nLa unidad nativa de cada línea no está publicada; no infiero unidades del nombre. '
                'Las descripciones corresponden al catálogo publicado, no al texto histórico de la factura. '
                f"Información actualizada al {business_date(result['source']['updated_at'])}; puede no reflejar cambios posteriores.")
    if result['capability'] in {'products.search.v1', 'sales.by_products.v1'}:
        if result['capability'] == 'products.search.v1':
            details = '\n'.join(f"{r['item_code']} · {r['description']} · {r['status']} · unidad de catálogo sin etiqueta acreditada" for r in rows)
            if not rows:
                details = 'No se encontraron productos con ese nombre o código en el catálogo SAP consultado.'
            elif result.get('selection_required'):
                details += '\nHay coincidencias amplias: indicá un código o una presentación de esta lista para consultar ventas.'
        else:
            details = 'Presentaciones incluidas:\n' + '\n'.join(f"{r['item_code']} · {r['description']}" for r in result['products'])
            period = result['parameters']
            if result.get('product_summary'):
                details += '\nMovimientos por producto en el período publicado:\n' + '\n'.join(
                    f"{r['item_code']}: {r['line_count']} líneas de facturas activas" +
                    (f" · última fecha {r['last_date'][:10]}" if r['line_count'] else ' · sin movimientos observados en este alcance')
                    for r in result['product_summary'])
            details += '\nLa selección automática usa coincidencias relevantes habilitadas para venta (SellItem=Y), incluidos inactivos para historia; etiquetas e insumos internos requieren selección explícita.'
            details += ('\nLíneas de facturas activas (cantidad documental original, UoM de línea no publicada):\n' +
                ('\n'.join(f"{r['doc_date'][:10]} · OINV {r['doc_entry']} / línea {r['line_num']} · {r['item_code']} · {r['description']} · cantidad {r['quantity']}" for r in rows)
                 or 'Sin líneas observadas para esos IDs y este período publicado; no certifica ventas cero fuera de cobertura.'))
            if period.get('date_from'):
                details += f"\nPeríodo [{period['date_from']}, {period['date_to_exclusive']})."
            details += f"\nHasta {period['limit']} líneas; orden fecha, DocEntry y número de línea descendentes. No son facturas completas ni cantidades físicas agregadas. Excluye anuladas y notas de crédito; no es venta neta."
            details += '\nImporte neto por producto no acreditado: LineTotal no resuelve descuentos/impuestos de cabecera y NC. No reparto DocTotal. No sumo unidades incompatibles.'
        return details + f"\nFoundation {result['source']['publication_id']}, snapshot {result['source']['snapshot_id']}."
    if result['capability'] == MONETARY_OPERATION+'.v1':
        row, period = rows[0], result['period']
        from datetime import date, timedelta
        money = lambda key: business_money(row[key])
        start, end = period['date_from'], period['date_to_exclusive']
        last = (date.fromisoformat(end) - timedelta(days=1)).isoformat()
        channel_label = 'Canal horizontal / DMS (venta de calle). ' if result.get('sales_channel') == 'HORIZONTAL' else ''
        if row['invoice_count'] == 0 and row['credit_count'] == 0:
            return (channel_label + f"No hay documentos publicados en BS entre el {business_date(start)} y el {business_date(last)}. "
                    'No puedo acreditar una facturación de cero ni la cobertura completa del período. '
                    f"Información actualizada al {business_date(result['source']['updated_at'])}.")
        response = (channel_label + f"Facturación registrada: Bs {money('billed_amount')}, "
                    f"del {business_date(start)} al {business_date(last)}. "
                    f"Notas de crédito: Bs {money('credit_amount')}. "
                    f"Neto documental tras notas de crédito: Bs {money('net_amount')}. "
                    'Facturas activas en BS, con impuestos y descuentos; excluye anuladas y otras monedas. '
                    'No equivale a ingreso contable, cobros ni a saldo pendiente; cobertura histórica completa no certificada. ')
        if channel_label:
            response = (f"Venta neta documental del canal horizontal / DMS (venta de calle): Bs {money('net_amount')}. "
                        f"Del {business_date(start)} al {business_date(last)}. "
                        f"Facturado: Bs {money('billed_amount')}; notas de crédito: Bs {money('credit_amount')}. "
                        'Facturas y notas de crédito activas en BS, por fecha documental, con impuestos y descuentos; '
                        'excluye anuladas. No son cobros. Canal según series DMS materializadas. '
                        'No certifica reconciliación completa DMS/origen, créditos entre canales ni devoluciones no registradas. '
                        'Cobertura histórica completa no certificada. ')
        if result['source']['updated_at'][:10] < last:
            response += 'El período solicitado termina después de la actualización disponible: no es un cierre mensual completo. '
        response += f"Información actualizada al {business_date(result['source']['updated_at'])}. "
        source = result['source']
        if source.get('reference_version'):
            if last >= source['sales_cutoff'][:10] or end > source['coverage_end_exclusive']:
                response += 'Período parcial hasta el corte disponible; no es un mes ni un día completo. '
            response += (f"Corte de ventas: {source['sales_cutoff']} (observaciones por consulta, no snapshot transaccional). "
                         f"Cobertura capturada [{source['coverage_start']}, {source['coverage_end_exclusive']}). "
                         f"Foundation: {source['publication_id']}; Reference: {source['reference_version']}; snapshot: {source['snapshot_id']}. ")
        if 'sales.source_top_items' in result.get('requested_metrics', []):
            response += ('Conservo la solicitud de cantidades: el ranking disponible usa la ventana fija '
                         '01/01–15/09/2026, sin excluir anuladas ni descontar NC; '
                         'no tiene un contrato conjunto compatible con este importe. '
                         'No sumo unidades incompatibles ni sustituyo cantidades físicas por el conteo de documentos. ')
        return response.strip()
    if result['capability'] in {'sales.latest_documents.v1', 'sales.coverage.v1'}:
        if result['capability'] == 'sales.coverage.v1':
            row = rows[0]
            details = (f"Último mes con facturas activas registradas por fecha documental: {row['latest_month_with_rows']}. "
                       f"Última fecha: {row['last_date']}. Documentos: {row['documents']}. "
                       'No certifica último mes completo ni cobertura de ventas netas.'
                       if row['documents'] else 'No se observaron facturas activas en esta publicación; no certifica ventas cero.')
        else:
            details = 'Últimas facturas activas por fecha documental (no instante de ingreso):\n' + (
                '\n'.join(f"{i}. Factura N.º {r['doc_num']} · fecha {r['doc_date'][:10]}" for i, r in enumerate(rows, 1))
                or 'Sin filas observadas; no certifica ventas cero.')
            details += '\nOrdenadas de más reciente a más antigua. Excluye anuladas y notas de crédito. No es venta neta.'
            updated_at = result['source'].get('updated_at')
            return details + (f"\nInformación actualizada al {business_date(updated_at)}; puede no reflejar cambios posteriores."
                              if isinstance(updated_at, str) and updated_at else
                              '\nLa fecha de actualización no está disponible; no afirmo que sean datos actuales.')
        return details + f"\nFoundation {result['source']['publication_id']}, snapshot {result['source']['snapshot_id']}."

    details = '\n'.join(f"{r['item_code']}: {r['quantity']}" for r in rows) or 'Sin filas observadas (no certifica ventas cero).'
    return ('Top 10 por cantidad documental, 01/01–15/09/2026:\n' + details +
            '\nUnidades originales por producto, no comparables entre productos. '
            'Sin descontar notas de crédito ni anulaciones; no es facturación ni venta neta. '
            'Cobertura histórica completa no certificada. '
            f"Actualización: {result['source']['updated_at']}. Fuente: Foundation {result['source']['publication_id']}.")
