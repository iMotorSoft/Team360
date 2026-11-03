"""Historical projection of the existing full ranking, never a product filter."""
from decimal import Decimal

from modules.telchi.datalake.product_line_amount_ranking_query import CAPABILITY, validate_result


async def execute(state, category, query, timeout_seconds):
    periods = [state['period']]
    if state['comparison']:
        periods.append(state['comparison'])
    outcomes = []
    for period in periods:
        options = dict(category=category, currency='BS', date_from=period['start'],
            date_to_exclusive=period['end_exclusive'], limit=state.get('limit', 10))
        try:
            result = validate_result(options, await query(options, timeout_seconds=timeout_seconds))
            full = result['full_breakdown']
            target = next((dict(row, position=i+1) for i, row in enumerate(full)
                           if row['item_code'] == state['ranking_target_item_code']), None)
            outcomes.append(dict(period=period, status=result.get('accreditation', 'verified'),
                target=target, comparable_products=len(full), result=result))
        except Exception as exc:
            # One period cannot erase the other. No fabricated zero or position.
            from modules.telchi.datalake.product_line_amount_ranking_query import SAFE_ERRORS
            reason = str(exc) if str(exc) in SAFE_ERRORS else 'ranking_unavailable'
            outcomes.append(dict(period=period, status='unresolved', reason=reason,
                audit_required=True, evidence=getattr(exc, 'evidence', None)))
    return dict(capability=CAPABILITY, view='historical_position',
        category=category, target_item_code=state['ranking_target_item_code'], detail=state.get('ranking_detail'),
        periods=outcomes, rows=[], answer_policy='ANSWER_FIRST_WITH_EXCEPTIONS')


def exception_text(exceptions):
    from .capabilities import business_money
    text = []
    for e in exceptions:
        document = f"factura N.º {e['doc_num']}" if e.get('doc_num') else 'documento de venta sin número publicado'
        # Currency of LineTotal is NOT inferred from price/line currency.
        text.append(f"Se excluyó {document}, producto {e['item_code']}: cabecera {e.get('header_currency') or 'sin moneda'}, "
            f"línea {e.get('line_currency') or 'sin moneda'}, LineTotal original {business_money(e['original_line_total'])} "
            '(denominación monetaria pendiente de acreditar).')
    if exceptions:
        text.append('El importe y la posición definitivos pueden cambiar. Estas operaciones requieren auditoría; no se convirtieron ni sumaron.')
    return ' '.join(text)


def format_historical(result):
    from .capabilities import MONTHS, business_money
    from datetime import date
    lines, warnings = [], []
    for outcome in result['periods']:
        start = date.fromisoformat(outcome['period']['start'])
        end = date.fromisoformat(outcome['period']['end_exclusive'])
        label = (f'{MONTHS[start.month-1].capitalize()} {start.year}'
                 if start.day == end.day == 1 and (end-start).days <= 31
                 else f"{start.isoformat()} hasta {end.isoformat()} (fin exclusivo)")
        if outcome['status'] == 'unresolved':
            reasons = {
                'category_key_integrity_failed': 'no pude verificar la unicidad o las relaciones documentales',
                'category_unaccredited_rows_or_lineage': 'hay líneas sin clasificación o procedencia acreditada',
                'category_classification_provisional': 'hay clasificación provisional',
                'ranking_catalog_integrity_failed': 'no pude verificar el catálogo de productos',
                'ranking_reconciliation_failed': 'el desglose no concilia con el total de categoría',
            }
            warnings.append(f"{label}: {reasons.get(outcome['reason'], 'no se obtuvo un cálculo verificable')}. "
                'Requiere investigar las líneas y su procedencia; no asigno una cifra ni una posición.')
            continue
        row = outcome['target']
        partial = outcome['status'] == 'partial'
        if row:
            lines.append(f"{label}: puesto {row['position']} entre {outcome['comparable_products']} productos"
                + (' en las operaciones verificadas en BS (ranking parcial)' if partial else '')
                + f", con Bs {business_money(row['amount'])}.")
        else:
            lines.append(f"{label}: no aparece entre los {outcome['comparable_products']} productos con operaciones verificadas. "
                'No se asigna puesto ni se acredita venta cero.')
        details = exception_text(outcome['result'].get('exceptions', []))
        if details:
            warnings.append(f'{label}: {details}')
    title = next((o['target']['description'] for o in result['periods'] if o.get('target')), None)
    text = result['target_item_code'] + (f' — {title}' if title else '') + '\n\n'
    text += '\n'.join(lines + warnings)
    verified = [o for o in result['periods'] if o['status'] == 'verified' and o.get('target')]
    if len(verified) == 2:
        verified.sort(key=lambda o: o['period']['start'])
        delta = Decimal(verified[1]['target']['amount']) - Decimal(verified[0]['target']['amount'])
        text += f'\nDiferencia de importe entre ambos períodos: Bs {business_money(delta)}.'
    if result.get('detail') == 'exceptions':
        if all(o['status']=='verified' for o in result['periods']):
            text += '\nNo se excluyeron operaciones de estos rankings por incompatibilidad monetaria.'
        external = [e for o in result['periods'] if 'result' in o
                    for e in o['result'].get('external_currency_anomalies', [])]
        for e in external:
            document = f"factura N.º {e['doc_num']}" if e.get('doc_num') else 'documento de venta'
            text += (f"\nSe detectó {document}, producto {e['item_code']}, con cabecera {e['header_currency']} "
                f"y línea {e['line_currency']}, fuera de la categoría consultada. "
                'No interviene ni fue excluido de estos rankings; la diferencia de monedas queda en auditoría. '
                'Bloquear el ranking por ese registro ajeno sería un problema de procesamiento.')
    return text + ('\n\nProductos de la categoría solicitada, por importe vendido sin IVA de línea, antes de notas de crédito '
        'y ajustes globales. Clasificación actual; los datos disponibles no certifican el cierre completo de los períodos.')
