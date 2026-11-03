"""Bounded references to structured, previously formatted results, not query filters.

Only approved presentation fields and explicitly requested document identity are
referencable. Values never enter the interpreter context. Order is persisted.
"""
from copy import deepcopy
import json

from .state_engine import validate
from modules.telchi.datalake.invoice_lines_query import CAPABILITY as INVOICE_LINES, PERMISSION as INVOICE_PERMISSION, validate_result as validate_lines

# Presentation adapters, not capabilities or grants. New list types opt in here.
# Multi-list reports (e.g. sales.by_products: products, summary AND lines) are
# deliberately not referencable until each displayed list has its own identity.
PRESENTATIONS = {
    'sales.product_line_amount_ranking.v1': ('producto', {'item_code': 'código', 'description': 'descripción', 'amount': 'importe acumulado vendido (BS, sin IVA, antes de notas de crédito)'}),
    'sales.latest_documents.v1': ('factura', {'doc_date': 'fecha', 'doc_entry': 'DocEntry', 'doc_num': 'número de factura'}),
    INVOICE_LINES: ('producto', {'item_code': 'código', 'description': 'descripción de catálogo', 'quantity': 'cantidad documental', 'unit': 'unidad'}),
    'products.search.v1': ('producto', {'item_code': 'código', 'description': 'descripción', 'status': 'estado'}),
    'telchi.sales_top_items.source_quantity.20260101_20260915.v1': ('producto', {'item_code': 'código', 'quantity': 'cantidad documental'}),
}
# The commercial breakdown presents one dimension at a time; the label follows it.
COMMERCIAL_BREAKDOWN = 'sales.commercial_line_amount_by.v1'
COMMERCIAL_FIELDS = {'key': 'código', 'label': 'nombre', 'amount': 'importe acumulado (BS, sin IVA de línea, antes de notas de crédito)'}
MAX_BYTES = 65536


def presentation(audit, result_id, owner, conversation_id):
    """Accept only successful business-authorized executions from this owner."""
    if not isinstance(audit, dict):
        return None
    result = audit.get('execution_result')
    if (audit.get('owner') != owner or audit.get('execution_status') != 'executed'
            or audit.get('business_rbac_verified') is not True
            or audit.get('response_prepared', {}).get('classification') != 'DIRECT_AVAILABLE'
            or not audit.get('required_permission') or not isinstance(result, dict)
            or len(json.dumps(result).encode()) > MAX_BYTES):
        return None
    # A partial list cannot become an unqualified ordinal/amount on a follow-up.
    # Its full exceptions remain in the execution audit, not this single-list adapter.
    if result.get('exceptions') or result.get('view') == 'historical_position':
        return None
    state = audit.get('confirmed_state')
    try:
        validate(state)
    except (ValueError, TypeError, KeyError):
        return None
    expected = ('telchi.sales_top_items.source_quantity.20260101_20260915.v1'
                if state['metric'] == 'sales.source_top_items' else f"{state['metric']}.v1")
    if result.get('capability') == INVOICE_LINES:
        try:
            validate_lines(result['parameters'], result)
        except (ValueError, TypeError, KeyError):
            return None
        if audit['required_permission'] != INVOICE_PERMISSION or not audit.get('document_reference'):
            return None
    elif result.get('capability') != expected:
        return None
    adapter = PRESENTATIONS.get(result.get('capability'))
    if result.get('capability') == COMMERCIAL_BREAKDOWN:
        group_by = (result.get('parameters') or {}).get('group_by')
        adapter = (('cliente facturado' if group_by == 'card_code' else 'producto'), dict(COMMERCIAL_FIELDS))
    source, rows = result.get('source'), result.get('rows')
    if (not adapter or not isinstance(source, dict) or not source.get('publication_id')
            or type(source.get('snapshot_id')) is not int or not isinstance(source.get('updated_at'), str)
            or not source['updated_at']
            or not isinstance(rows, list) or not 0 < len(rows) <= 50):
        return None
    if result.get('capability') == COMMERCIAL_BREAKDOWN and state.get('excluded_product'):
        # Ordinals must refer to the five additional products actually shown,
        # not to the reference product retained in the accredited full query.
        offset = state.get('product_offset', 0)
        rows = [r for r in rows if r.get('key') != state['excluded_product']][offset:offset + 5]
        if not rows:
            return None
    label, fields = adapter
    if any(not isinstance(r, dict) or not set(fields) <= set(r)
           or any(type(r[f]) not in (str, int, float, type(None)) for f in fields) for r in rows):
        return None
    return dict(document=deepcopy(result.get('document')),
                document_reference=deepcopy(audit.get('document_reference')),
                result_id=result_id, conversation_id=conversation_id, owner=deepcopy(owner),
                capability=result['capability'], label=label, fields=fields,
                rows=[{f: r[f] for f in fields} for r in rows], source=deepcopy(source),
                state=deepcopy(audit['confirmed_state']), required_permission=audit['required_permission'])


def document_selection(proposal, result, selected_ordinal, owner, conversation_id):
    """Document IDs come from an authorized presented row, never the interpreter."""
    if (not isinstance(proposal, dict) or set(proposal) != {'intent', 'action', 'result_reference', 'clarification'}
            or proposal['intent'] != 'DOCUMENT_REFERENCE' or proposal['action'] not in {'READ_LINES', 'SELECT_DOCUMENT'}
            or proposal['clarification'] is not None or result is None
            or result['capability'] != 'sales.latest_documents.v1'):
        raise ValueError('invalid_document_contract')
    ref = proposal['result_reference']
    if (not isinstance(ref, dict) or set(ref) != {'result_id', 'ordinal', 'field'}
            or ref['field'] not in {None, 'doc_num', 'doc_date', 'client', 'amount'}
            or (proposal['action'] == 'READ_LINES' and ref['field'] is not None)):
        raise ValueError('invalid_document_field')
    query = dict(proposal, intent='RESULT_REFERENCE', action='SELECT_RESULT',
                 result_reference=dict(ref, field=None))
    ordinal, _ = resolve(query, result, selected_ordinal, owner, conversation_id)
    row = result['rows'][ordinal - 1]
    options = dict(source_system='SAP_B1_HANA', document_type='OINV',
                   doc_entry=row['doc_entry'], doc_num=row['doc_num'], doc_date=row['doc_date'],
                   publication_id=result['source']['publication_id'], snapshot_id=result['source']['snapshot_id'])
    return ordinal, options


def interpreter_context(result, selected_ordinal=None):
    """The presented result and the business scope it certifies.

    The scope is what lets a later turn recover the category, the product, the
    customer, the periods and the measure of a previous answer without the
    user repeating any of them.
    """
    if result is None:
        return None
    context = dict(result_id=result['result_id'], row_count=len(result['rows']),
                   fields=result['fields'], selected_ordinal=selected_ordinal,
                   entity_label=result['label'], historical=True)
    try:
        from . import business_scope
        scope = business_scope.result_scope(result.get('state') or {},
                                            {'capability': result.get('capability'),
                                             'definition': None, 'accreditation': 'verified'})
    except (ValueError, TypeError, KeyError):
        scope = {}
    context['scope'] = scope
    return context


def resolve(proposal, result, selected_ordinal, owner, conversation_id):
    """Validate the whole independent contract; no repair, query patch or LLM values."""
    if not isinstance(proposal, dict) or proposal.get('intent') != 'RESULT_REFERENCE':
        raise ValueError('invalid_reference_contract')
    if proposal.get('action') == 'ASK':
        if (set(proposal) != {'intent', 'action', 'result_reference', 'clarification'}
                or proposal['result_reference'] is not None
                or not isinstance(proposal['clarification'], dict)
                or set(proposal['clarification']) != {'question'}
                or not isinstance(proposal['clarification']['question'], str)
                or not 0 < len(proposal['clarification']['question']) <= 300):
            raise ValueError('invalid_reference_clarification')
        # Fixed safe question: never echo model-generated business values.
        return None, '¿A qué lista o elemento de los resultados anteriores te referís?'
    if (set(proposal) != {'intent', 'action', 'result_reference', 'clarification'}
            or proposal['action'] != 'SELECT_RESULT' or proposal['clarification'] is not None):
        raise ValueError('invalid_reference_contract')
    ref = proposal['result_reference']
    if (not isinstance(ref, dict) or set(ref) != {'result_id', 'ordinal', 'field'}
            or result is None or result['owner'] != owner
            or result['conversation_id'] != conversation_id or ref['result_id'] != result['result_id']):
        raise ValueError('result_unavailable')
    ordinal = selected_ordinal if ref['ordinal'] is None else ref['ordinal']
    if ordinal is None and len(result['rows']) == 1:
        ordinal = 1  # A singleton is unambiguous, not an arbitrary selection.
    if type(ordinal) is not int or not 1 <= ordinal <= len(result['rows']):
        raise ValueError('ordinal_unavailable')
    field = ref['field']
    if field is not None and (not isinstance(field, str) or field not in result['fields']):
        raise ValueError('field_unavailable')
    row = result['rows'][ordinal - 1]
    if field is not None and row[field] is None:
        if result['capability'] == INVOICE_LINES and field in {'unit', 'description'}:
            text = (f"Factura N.º {result['document']['doc_num']}, producto {ordinal}: "
                    f"{result['fields'][field]} no disponible en la publicación conservada. "
                    f"Datos al {result['source']['updated_at']}.")
            return ordinal, text
        raise ValueError('field_unavailable')
    # Deterministic wording; data is taken verbatim, including document identifiers.
    if field == 'doc_num' and result['label'] == 'factura':
        ordinals = {1: 'primera', 2: 'segunda', 3: 'tercera', 4: 'cuarta', 5: 'quinta'}
        position = ordinals.get(ordinal, f'en posición {ordinal}')
        text = f"La {position} factura es la N.º {row[field]}."
    elif field == 'amount' and result['capability'] == 'sales.product_line_amount_ranking.v1':
        from .capabilities import business_money
        text = (f"{row['item_code']} · {row['description']}: Bs {business_money(row['amount'])} de importe acumulado vendido. "
                'Sin IVA, antes de notas de crédito; no es precio unitario ni cierre mensual completo.')
    elif field is not None:
        text = f"{result['fields'][field].capitalize()} del elemento {ordinal}: {row[field]}."
    else:
        text = f"{result['label'].capitalize()} {ordinal}: " + ' · '.join(
            f"{result['fields'][f]}: {value}" for f, value in row.items()
            if value is not None and f not in {'doc_entry', 'line_num'}) + '.'
        if result['label'] == 'factura':
            text += ' Sólo dispongo de estos datos de cabecera, no de la factura completa.'
    if result['capability'] == INVOICE_LINES:
        text = f"Factura N.º {result['document']['doc_num']}. " + text
        text += ' La unidad nativa de la línea no está publicada; no infiero una unidad del nombre del producto.'
    # No TTL invented: this is always the prior publication, not a fresh read.
    text += f" Según el resultado anterior (datos al {result['source']['updated_at']})."
    return ordinal, text
