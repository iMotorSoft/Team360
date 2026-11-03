"""Operational extension of the existing catalog/state/response contracts."""
from modules.telchi.datalake.operational_query import OPERATIONS, SNAPSHOT_METRICS, parameters


def unsupported_followup(text, state):
    """Fence the demonstrated supplier-ranking substitution, not a new query engine.

    The ten registered operations expose purchase totals, not supplier grouping.
    Never silently execute that total as an answer to a requested supplier list.
    """
    import re
    import unicodedata
    normalized = ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                         if unicodedata.category(c) != 'Mn')
    if ((state.get('metric') or '').startswith('purchasing.')
            and re.search(r'\bproveedores?\b', normalized)
            and re.search(r'\b(principales|ranking|top|mayores)\b|por proveedor', normalized)):
        period = state.get('period')
        scope = (f" Conservo el período [{period['start']}, {period['end_exclusive']})."
                 if period else '')
        return ('La operación disponible acredita el total de compras, pero no un ranking por proveedor.'
                + scope + ' No recalculé el total como sustituto ni inventé los cinco proveedores. '
                'Podés continuar con las operaciones disponibles o iniciar una nueva consulta.')
    return None


def options_for(state):
    metric = state['metric']
    if (state.get('pending') or (state.get('requested_metrics') or [metric]) != [metric]
            or any(state.get(k) for k in ('branches','sales_channel','comparison','temporal_reference',
                'entity_mention','product_search_text','selected_item_codes','product_context',
                'business_category','customer_target','group_by','breakdown_by','periods',
                'analysis_categories','ranking_target_item_code','semantic_references'))):
        raise ValueError('unsupported_operational_scope')
    options = {'limit':state.get('limit',10)}
    if state.get('product_target'):
        options['item_code'] = state['product_target']
    if state.get('period'):
        options.update(date_from=state['period']['start'],date_to_exclusive=state['period']['end_exclusive'])
    return parameters(metric,options)


def format_operational(result):
    from .capabilities import business_money
    metric, rows = result['metric'], result['rows']
    lines = [result['label'] + ':']
    if (metric in {'production.consumption', 'material_supply.consumption'}
            and 'included_issue_lines' in result.get('controls', {})):
        count = result['controls']['included_issue_lines']
        label = 'líneas elegibles de consumo de materiales' if metric.startswith('material_supply.') else 'líneas de consumo de producción'
        lines.append(f"{count:,} {label}.".replace(',', '.'))
    if result.get('summary'):
        s = result['summary']
        lines.append(f"Total acreditado BS {business_money(s['amount'])} · {s['documents']} documentos de esta etapa.")
    if not rows:
        lines += ['No encontré filas acreditadas para este alcance; no significa cero empresarial.']
    for r in rows:
        if 'amount' in r:
            count = r.get('documents', r.get('payments'))
            state = ' · estado '+r['document_status'] if 'document_status' in r else ''
            lines.append(f"BS {business_money(r['amount'])} · {count} documentos/pagos{state}")
        elif metric == 'inventory.stock_by_warehouse':
            lines.append(f"{r['item_code']} · depósito {r['warehouse']}: existencia {r['on_hand_qty']}, comprometido {r['committed_qty']}, disponible {r['available_qty']} · unidad {r['unit'] or 'desconocida'} · corte {r['stock_as_of']}")
        elif 'quantity' in r:
            lines.append(f"{r.get('item_code',r.get('component'))}: {r['quantity']} · unidad {r.get('unit') or 'desconocida'} · código UoM {r.get('uom_code') or 'no disponible'} · factor nativo {r.get('native_factor') or 'no disponible'}")
        elif metric == 'production.orders':
            lines.append(f"Orden {r['production_order']} · {r['item_code']} · estado {r['native_status']} · planificado {r['planned_quantity']}")
        else:
            lines.append(f"Pago {r['payment_number']} · cliente {r['customer_code']} · fecha {str(r['payment_date'])[:10]} · estado cancelado {r['cancelled']}")
    coverage = result['coverage']
    if coverage.get('requested_period'):
        p = coverage['requested_period']
        lines.append(f"Período solicitado [{p['date_from']}, {p['date_to_exclusive']}); cobertura observada [{coverage['declared_start']}, {coverage['declared_end_exclusive']}). No certifica histórico completo.")
        if coverage.get('requested_outside_capture'):
            lines.append('Período parcialmente fuera de captura: resultado parcial, no cierre del período completo.')
    if coverage.get('observation_started_at'):
        lines.append(f"Observación fuente: {coverage['observation_started_at']} a {coverage['observation_finished_at']}.")
    if result.get('controls'):
        lines.append('Controles: '+', '.join(f'{k}={v}' for k,v in result['controls'].items()))
    if result['omitted_rows']:
        lines.append(f"Mostradas {len(rows)} de {result['total_rows']} filas; {result['omitted_rows']} omitidas del mensaje. No es un ranking global entre unidades.")
    lines += result['limitations']
    # A publication's global update is NOT the observation date of every domain.
    lines.append('Foundation '+result['source']['publication_id']+'; cortes propios por dominio, no actualización global de métricas legacy.')
    return '\n'.join(lines)
