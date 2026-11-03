"""Deterministic business answer for the commercial breakdown family.

No model, no invented value, no lost period. The answer states the accredited
result first, then the exact gaps, the risk they carry and the next useful
step. Every figure comes from the accredited result.

The answer is written for a conversation channel: the main result, its share
of the accredited scope, the material warnings and an offer to continue. A
long list is never dumped in full, and a figure, a name or a warning is never
altered or cut in half.
"""
from decimal import Decimal

from .business_scope import period_label, fiscal_control_accounts


def _money(value):
    from .capabilities import business_money
    return business_money(value)


def _count(value):
    return f'{value:,}'.translate(str.maketrans({',': '.', '.': ','}))


def _percent(part, whole):
    from decimal import localcontext
    with localcontext() as ctx:
        ctx.prec = 20
        value = part / whole * 100
    return f'{value.quantize(Decimal("0.01")):,}'.translate(str.maketrans({',': '.', '.': ','})) + ' %'


def _date(value):
    if not value:
        return None
    from .capabilities import business_date
    return business_date(str(value)[:10])


def _periods(options):
    periods = options.get('periods')
    if periods:
        return [dict(p) for p in periods]
    return [dict(start=options['date_from'], end_exclusive=options['date_to_exclusive'])]


def _published(result):
    focus = result.get('focus') or {}
    return focus.get('item_label'), focus.get('customer_label')


def _title(options, result, when):
    filters = options.get('filters') or {}
    group_by = options['group_by']
    item_label, customer_label = _published(result)
    product = filters.get('item_code')
    customer = filters.get('card_code')
    category = filters.get('category')
    from .business_categories import CATEGORIES
    if group_by == 'card_code' and customer:
        subject = f'{customer_label} ({customer})' if customer_label else customer
        title = f'Compras de {subject}'
        if product:
            title += f' — {product} · {item_label}' if item_label else f' — {product}'
    elif group_by == 'card_code':
        title = 'Cliente facturado en SAP con mayor importe'
        if product:
            title += f' — {product} · {item_label}' if item_label else f' — {product}'
        elif category:
            title += f' — {CATEGORIES[category].lower()}'
    elif customer:
        subject = f'{customer_label} ({customer})' if customer_label else customer
        title = f'Productos que compró {subject}'
        if product:
            title += f' — {product} · {item_label}' if item_label else f' — {product}'
        elif category:
            title += f' — {CATEGORIES[category].lower()}'
    else:
        title = 'Productos con mayor importe vendido'
        if product:
            title += f' — {product} · {item_label}' if item_label else f' — {product}'
        elif category:
            title += f' — {CATEGORIES[category].lower()}'
    return f'{title} — {when}'


def _row_headline(row, group_by, focus):
    """The main result: who or what, and how much. No period, no variation."""
    if group_by == 'card_code':
        head = f"{row['label']} ({row['key']})"
    else:
        head = f"{row['key']} · {row['label']}"
    if focus and focus.get('key') == row['key'] and focus.get('kind') == ('card_code' if group_by == 'card_code' else 'sap_product'):
        head += ' (en foco)'
    return f'{head} — Bs {_money(row["amount"])}'


def _row_periods(row):
    """Every period of the main result, read one by one. No period is lost."""
    parts = row.get('periods') or []
    if not parts:
        return []
    lines = [f"{period_label([p['period']])}: Bs {_money(p['amount'])}." for p in parts]
    if len(parts) >= 2:
        # The variation between the first and the last period, from the same
        # accredited figures: it is what a "what changed" question asks for.
        first, last = parts[0], parts[-1]
        delta = Decimal(last['amount']) - Decimal(first['amount'])
        share = ''
        if Decimal(first['amount']) > 0:
            share = f' ({_percent(abs(delta), Decimal(first["amount"]))})'
        lines.append(f'Entre {period_label([first["period"]])} y {period_label([last["period"]])} '
                     f'{"subió" if delta >= 0 else "bajó"} Bs {_money(abs(delta))}{share}.')
    return lines


def _row_text(row, group_by, focus):
    """One group with its period reading and its variation, when published."""
    text = _row_headline(row, group_by, focus)
    parts = row.get('periods') or []
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        text += ' · ' + ' · '.join(f'{period_label([p["period"]])}: Bs {_money(p["amount"])}' for p in parts)
        delta = Decimal(last['amount']) - Decimal(first['amount'])
        share = ''
        if Decimal(first['amount']) > 0:
            share = f' ({_percent(abs(delta), Decimal(first["amount"]))})'
        text += (f' · entre {period_label([first["period"]])} y {period_label([last["period"]])} '
                 f'{"subió" if delta >= 0 else "bajó"} Bs {_money(abs(delta))}{share}')
    return text


def _share_sentence(main, total, universe, filters, group_by):
    """The participation of the main result over the accredited scope.

    A scope filtered by a billed customer is weighed against the same scope
    without that customer filter: the universe is read with the same measure
    and the same guards, never with another definition.
    """
    if filters.get('card_code') and universe and Decimal(universe['amount']) > 0:
        return (f'Peso de este cliente en el mismo alcance sin filtrar por cliente: '
                f'{_percent(Decimal(total["amount"]), Decimal(universe["amount"]))} '
                f'de los Bs {_money(universe["amount"])} registrados.')
    whole = Decimal(total['amount'])
    if whole <= 0:
        return None
    if filters.get('item_code'):
        subject = f'las ventas acreditadas del producto {filters["item_code"]}'
    elif group_by == 'card_code':
        subject = 'el total acreditado de clientes facturados del alcance'
    else:
        subject = 'el total acreditado de productos del alcance'
    return f'Participación en {subject}: {_percent(Decimal(main["amount"]), whole)}.'


def _rest_sentence(rows, total, group_by):
    """What the main result does not cover, in accredited figures."""
    counted = total.get('customer_count') if group_by == 'card_code' else total.get('product_count')
    if not counted or counted <= 1:
        return None
    whole = Decimal(total['amount'])
    rest = whole - Decimal(rows[0]['amount'])
    if rest <= 0:
        return None
    unit = 'cuentas facturadas' if group_by == 'card_code' else 'productos'
    return (f'El resto del alcance son {counted - 1} {unit} por Bs {_money(rest)} '
            f'({_percent(rest, whole)}).')


def _warnings(result, rows, group_by, filters):
    warnings = []
    if group_by == 'card_code' or filters.get('card_code'):
        warnings.append('«Cliente facturado en SAP» es la cuenta que recibe las líneas de factura (CardCode). '
                        'No es el comprador final ni un cliente comercial validado: la taxonomía de cliente comercial '
                        'no está acreditada en la publicación vigente, así que no puedo afirmar cuál es el cliente '
                        'comercial final.')
        control = fiscal_control_accounts(rows)
        if control:
            amount = sum((Decimal(row['amount']) for row in control), Decimal(0))
            warnings.append(f'De las {len(rows)} cuentas de mayor importe del alcance, {len(control)} son cuentas de control '
                            f'tributario de SAP (nombre publicado «CONTROL TRIBUTARIO»), con Bs {_money(amount)} en total. '
                            'No son clientes comerciales; no las depuré porque no hay una taxonomía acreditada que las distinga.')
    if result.get('unnamed_accounts'):
        warnings.append(f"{result['unnamed_accounts']} de las cuentas del universo no tienen nombre publicado; "
                        'se las identifica por su código.')
    if result.get('exceptions'):
        warnings.append(f"Se excluyeron {len(result['exceptions'])} operaciones con moneda no acreditada para esta "
                        'medida BS. El importe y el orden pueden cambiar; no las convertí ni las sumé.')
    warnings.append('Importe registrado en líneas comerciales en BS, sin IVA de línea, antes de notas de crédito y sin '
                    'ajustes globales: no es facturación documental neta ni monto cobrado.')
    coverage = result.get('coverage') or {}
    if coverage.get('first_date') and coverage.get('last_date'):
        warnings.append(f'Cobertura documental observada del {_date(coverage["first_date"])} al '
                        f'{_date(coverage["last_date"])}; no certifica el cierre completo del período.')
    if filters.get('category'):
        warnings.append('Clasificación de producto actual, no histórica.')
    if result.get('accreditation') == 'partial':
        warnings.append('Resultado parcial: algunas operaciones quedaron fuera y requieren auditoría.')
    return warnings


def _continuation(rows, group_by):
    """The next useful step: continue the same scope, without losing it."""
    unit = 'cliente facturado' if group_by == 'card_code' else 'producto'
    if len(rows) <= 1:
        return (f'Este alcance tiene un solo {unit}. '
                'Podés pedirme otro período o el detalle de otro cliente o producto.')
    return (f'Pedime «el segundo» o el número del {unit} que quieras ver y te muestro ese detalle, '
            'sin repetir la consulta.')


def format_physical(result):
    """Business first, with all unclassified money and source binding visible."""
    from modules.telchi.datalake.physical_sales_dimension import EXPLICIT
    physical = result['physical_classification']
    total = Decimal(result['total']['amount'])
    explicit = Decimal(physical['classified_amount'])
    amounts = {r['key']: Decimal(r['amount']) for r in result['full_breakdown']}
    unclassified = sum((a for k,a in amounts.items() if k not in EXPLICIT | {'MEDICINE','NOT_APPLICABLE'}), Decimal(0))
    rows = [('Líquidos', amounts.get('LIQUID', Decimal(0))),
            ('Sólidos', amounts.get('SOLID', Decimal(0))),
            ('Semisólidos', amounts.get('SEMISOLID', Decimal(0))),
            ('Sin clasificación explícita (0, ausente o desconocida)', unclassified),
            ('Medicamento (4; no es estado físico)', amounts.get('MEDICINE', Decimal(0))),
            ('No corresponde (5)', amounts.get('NOT_APPLICABLE', Decimal(0)))]
    text = 'Importe registrado en líneas comerciales — ' + period_label(_periods(result['parameters'])) + ':\n'
    for label, amount in rows:
        share = _percent(amount,total) if total else 'porcentaje no definido'
        text += f'\n• {label}: Bs {_money(amount)} ({share} del total).'
    text += f'\n\nTotal de líneas acreditadas: Bs {_money(total)} (BS).'
    if explicit:
        text += ' Dentro del importe con estado físico explícito: ' + ', '.join(
            label + ' ' + _percent(amount,explicit) for label,amount in rows[:3]) + '.'
    coverage = physical['coverage_percent']
    text += (f'\nCobertura física: {(_money(coverage["amount"]) + " %") if coverage["amount"] is not None else "no definida"} del importe, '
             f'{physical["classified_line_count"]}/{physical["line_count"]} líneas y '
             f'{physical["classified_product_count"]}/{physical["product_count"]} productos. '
             f'{physical["product_count"]-physical["classified_product_count"]} productos vendidos sin estado físico explícito. '
             f'Sin estado físico explícito, incluidos códigos 4/5: Bs {_money(physical["without_explicit_amount"])}.')
    observed = [r['observed_from'] for r in physical['audit'] if r.get('observed_from')]
    observed += [r['observed_to'] for r in physical['audit'] if r.get('observed_to')]
    text += '\nObservación física: ' + (' a '.join((_date(min(observed)),_date(max(observed)))) if observed else 'no disponible') + '. '
    text += physical['observation_warning']
    coverage = result['coverage']
    text += '\nVentas observadas: ' + str(_date(coverage['first_date'])) + ' a ' + str(_date(coverage['last_date'])) + '; no acredita cierre mensual.'
    text += '\nMétrica: suma de importes de líneas de facturas activas, descuentos propios incluidos, sin IVA de línea y antes de NC y ajustes de cabecera.'
    reconciliation = result.get('document_reconciliation')
    if reconciliation:
        text += (f'\nCabeceras: Bs {_money(reconciliation["invoice_amount"])}; '
                 f'diferencia no asignada con líneas: Bs {_money(reconciliation["header_minus_classified_line_universe"])}; '
                 f'NC documentales separadas: Bs {_money(reconciliation["credit_note_amount"])}. '
                 'No se distribuyen cabeceras ni se atribuye todo el residuo a impuestos.')
    if result.get('exceptions'):
        text += f'\nAdvertencia: {len(result["exceptions"])} líneas con moneda no acreditada excluidas; detalle preservado en auditoría. Sus importes no se convierten ni se tratan como cero.'
    options = result['parameters']
    focus = options.get('physical_focus')
    if options.get('breakdown_by') == 'products':
        ranking = [r for r in physical['products'] if not focus or r['key'] == focus]
        ranking.sort(key=lambda r: r['item_code'])
        ranking.sort(key=lambda r: Decimal(r['amount']), reverse=True)
        limit = options.get('detail_limit', 10)
        text += '\n\nProductos con mayor importe' + (f' ({focus})' if focus else '') + ': '
        text += '; '.join(f'{r["item_code"]}: Bs {_money(r["amount"])}' for r in ranking[:limit]) + '.'
        if len(ranking) > limit:
            text += f' Se muestran {limit} de {len(ranking)} productos; ranking íntegro conservado en auditoría.'
    elif options.get('breakdown_by') == 'day':
        daily = [r for r in physical['daily'] if not focus or r['key'] == focus]
        dates = sorted({r['date'] for r in daily})
        shown = dates[:7]
        text += '\n\nEvolución diaria (BS): '
        for day in shown:
            values = [r for r in daily if r['date'] == day]
            text += '\n' + day[:10] + ': ' + '; '.join(r['key'] + ' ' + _money(r['amount']) for r in values) + '.'
        if len(dates) > len(shown):
            text += f'\nSe muestran {len(shown)} de {len(dates)} días; la serie completa está conservada en auditoría.'
    elif options.get('breakdown_by') == 'period':
        from modules.telchi.datalake.physical_sales_dimension import LABELS
        text += '\n\nComparación por ventanas exactas (BS):'
        for reading in result['period_breakdown']:
            period = reading['period']
            text += '\n' + period_label([period]) + ': ' + '; '.join(
                LABELS[r['key']] + ' ' + _money(r['amount']) for r in reading['rows']) + '.'
    source = result['source']
    if source.get('sales_cutoff'):
        text += (f'\nCorte de ventas: {source["sales_cutoff"]}; observaciones por consulta, no snapshot transaccional. '
                 'No es ingreso contable.')
    text += (f'\nFoundation: {source["publication_id"]}; snapshot: {source["snapshot_id"]}; '
             f'Reference: {physical["reference"]}.')
    return text


def format_commercial(result, scope=None):
    if result['parameters']['group_by'] == 'physical_state':
        return format_physical(result)
    options = result['parameters']
    rows = result['rows']
    total = result['total']
    group_by = options['group_by']
    filters = options.get('filters') or {}
    when = period_label(_periods(options))
    title = _title(options, result, when)

    if not rows:
        return (f'{title}.\n\nNo encontré líneas comerciales en ese alcance y período. '
                'Esto no acredita ventas cero fuera de la cobertura disponible.')

    excluded = (scope or {}).get('excluded_product')
    if excluded:
        offset = (scope or {}).get('product_offset', 0)
        additional = [row for row in rows if row['key'] != excluded][offset:offset + 5]
        text = title + f' — excluyendo {excluded}.\n\n'
        if additional:
            text += '\n'.join(_row_headline(row, group_by, None) + '.' for row in additional)
        else:
            text += 'No encontré otros productos en los resultados acreditados de este alcance.'
        text += '\n\n' + ' '.join(_warnings(result, rows, group_by, filters))
        return text + '\n\nPuedo continuar con más productos del mismo cliente y período.'

    focus = None
    if scope and scope.get('focus'):
        published = scope['focus']
        key = published.get('customer') if group_by == 'card_code' else published.get('product')
        if key:
            focus = dict(key=key, kind='card_code' if group_by == 'card_code' else 'sap_product')
    main = rows[0]
    # BUSINESS ANSWER FIRST: the main result, its periods, its share, the
    # material warnings and the next step. The rest of the list is offered,
    # never dumped.
    text = title + '\n\n' + _row_headline(main, group_by, focus) + '.'
    periods = _row_periods(main)
    if periods:
        text += '\n' + '\n'.join(periods)
    share = _share_sentence(main, total, result.get('universe_total'), filters, group_by)
    if share:
        text += '\n' + share
    rest = _rest_sentence(rows, total, group_by)
    if rest:
        text += '\n' + rest
    warnings = _warnings(result, rows, group_by, filters)
    if warnings:
        text += '\n\n' + ' '.join(warnings)
    text += '\n\n' + _continuation(rows, group_by)
    return text
