"""Compact semantic vocabulary, NOT a product classifier or monetary capability.

Codes/labels transcribed from the immutable Foundation reference taxonomy.
Luna selects a business meaning; only the existing crosswalk classifies items.
The V2 unresolved entity slot carries the canonical category code (type=None).
No membership, counts, amounts or permissions are inferred here.
"""
from copy import deepcopy

CLASSIFICATION_VERSION = 'v2_product_business_type_f9c1130d852ccb61'
TAXONOMY_SHA256 = '47869a144029baf4862dbb0da0aa47d2dceda53cee810cd8acf7a145d95ecede'
CATEGORIES = {
    'RAW_MATERIAL': 'Materia prima',
    'LAB_FINISHED_PRODUCT': 'Producto terminado de laboratorio',
    'FRACTIONATED_PRODUCT': 'Producto fraccionado',
    'PACKAGING': 'Envase, etiqueta o material de acondicionamiento',
    'OTHER_INPUT': 'Otro insumo',
    'SEMI_FINISHED': 'Producto semielaborado',
    'TRADED_PRODUCT': 'Producto comercial de reventa',
    'SERVICE': 'Servicio',
    'OTHER': 'Otro',
    'UNKNOWN': 'Clasificación desconocida',
}


RANKING_LABELS = dict(zip(CATEGORIES, ('materias primas', 'productos terminados', 'productos fraccionados',
    'envases, etiquetas o materiales de acondicionamiento', 'otros insumos', 'productos semielaborados',
    'productos comerciales de reventa', 'servicios', 'productos de otra categoría', 'productos sin clasificación')))


def interpreter_context():
    return dict(dimension='product_business_type', classification_version=CLASSIFICATION_VERSION,
                accredited_coverage=dict(year=2026, months='2026-01..2026-09',
                    note='Año acreditado por la cobertura Foundation; no es el del reloj.'),
                taxonomy_sha256=TAXONOMY_SHA256, categories=deepcopy(CATEGORIES),
                category_sales_capability='sales.category_line_amount.v1',
                production_consumption_capability='production.consumption',
                monetary_ranking=dict(metric='sales.product_line_amount_ranking', operation='ranking',
                    group_by='sap_product', measure='commercial_active_invoice_line_amount_excluding_line_tax_v1',
                    order_by=[['amount', 'desc'], ['item_code', 'asc']], limit='1..50', currency='BS', category_required=True),
                commercial_breakdown=dict(metric='sales.commercial_line_amount_by', operation='breakdown',
                    group_by=['sap_product', 'card_code'],
                    measure='commercial_active_invoice_line_amount_excluding_line_tax_v1',
                    order_by=[['amount', 'desc'], ['key', 'asc']], limit='1..50', currency='BS',
                    filters=['category', 'item_code', 'card_code'], breakdown=['period'],
                    customer_definition='cuenta facturada en SAP (CardCode) que recibe las líneas; '
                        'no es el comprador final ni un cliente comercial validado'),
                membership_source='existing classified product crosswalk; never product name matching',
                limitations='Classification is current, not historical. BS-only line amount; no line tax, credit notes or header adjustments. UNKNOWN/provisional blocked.')


def category_code(state):
    """The accredited business category of a scope.

    The dedicated slot wins. A legacy state that carried the category in the
    generic entity mention is still honoured, but only while no dedicated
    category is set: the two can never disagree.
    """
    dedicated = state.get('business_category')
    if dedicated in CATEGORIES:
        return dedicated
    entity = state.get('entity_mention')
    code = entity.get('text') if isinstance(entity, dict) else None
    return code if code in CATEGORIES else None


def unavailable_text(state, reason_category=None):
    if state.get('metric') == 'sales.commercial_line_amount_by':
        # The commercial breakdown is not a category operation: its gap has its
        # own vocabulary and its own next step.
        return None
    code = category_code(state)
    if code is None:
        return None
    label = CATEGORIES[code].lower()
    metrics = state.get('requested_metrics') or [state.get('metric')]
    if state.get('metric') == 'sales.product_line_amount_ranking':
        understood = f'Entiendo que querés un ranking de productos por importe acumulado vendido de {label}'
        limitation = 'No tengo disponible ese ranking monetario para el alcance solicitado.'
    elif 'sales.net_amount' in metrics:
        understood = f'Entiendo que querés saber el importe de ventas de {label}'
        limitation = 'No puedo consultar el total de esa categoría con los parámetros solicitados.'
    elif state.get('metric') is None:
        understood = f'Entiendo la consulta sobre {label}'
        limitation = 'Todavía no tengo disponible esa operación; no la sustituyo por ventas ni por una búsqueda de productos.'
    else:
        understood = f'Entiendo la consulta de ventas de {label}'
        limitation = 'Todavía no tengo disponible esa operación de ventas por categoría.'
    if reason_category == 'PERIOD_UNRESOLVED':
        limitation = 'Necesito un período concreto para esta consulta.'
    elif reason_category == 'COVERAGE_GAP':
        limitation = 'El período solicitado excede la cobertura disponible para esta operación.'
    period = state.get('period')
    if period:
        from datetime import date, timedelta
        from .capabilities import business_date
        last = (date.fromisoformat(period['end_exclusive']) - timedelta(days=1)).isoformat()
        understood += f" del {business_date(period['start'])} al {business_date(last)}"
    return understood + '. ' + limitation


def scope_period_text(state):
    """Every period in scope, named. A comparison and a union are both kept."""
    from .business_scope import period_label
    periods = [dict(p) for p in (state.get('periods') or [])]
    comparison = state.get('comparison')
    if periods:
        label = period_label(periods)
        if comparison:
            label += ' (comparado con ' + period_label([dict(comparison)]) + ')'
        return label
    if comparison:
        return period_label([dict(state['period'])] if state.get('period') else []) + \
            ' comparado con ' + period_label([dict(comparison)])
    return period_label([dict(state['period'])]) if state.get('period') else None
