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
# A recovered population keeps every authorized record so continuation can page
# it locally. Its size is already bounded by the 5000-row execution cap, so the
# durable view gets a population ceiling instead of the single-page one: this is
# a presentation bound, not a new query, row or resource budget.
MAX_POPULATION_BYTES = 512 * 1024


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
    if result.get('capability') == COMMERCIAL_BREAKDOWN and (
            state.get('excluded_product') or state.get('excluded_products')):
        # Ordinals must refer to the products actually shown, not to the reference
        # product(s) retained in the accredited full query.
        offset = state.get('product_offset', 0)
        excluded = set(filter(None, [state.get('excluded_product')]))
        excluded.update(state.get('excluded_products') or [])
        rows = [r for r in rows if r.get('key') not in excluded][offset:offset + 5]
        if not rows:
            return None
    label, fields = adapter
    if any(not isinstance(r, dict) or not set(fields) <= set(r)
           or any(type(r[f]) not in (str, int, float, type(None)) for f in fields) for r in rows):
        return None
    page_size = (5 if result.get('capability') == COMMERCIAL_BREAKDOWN
                 and state.get('customer_target') and not state.get('ranking_by') else 10)
    return dict(next_ordinal=min(page_size, len(rows)) + 1,
                document=deepcopy(result.get('document')),
                document_reference=deepcopy(audit.get('document_reference')),
                result_id=result_id, conversation_id=conversation_id, owner=deepcopy(owner),
                capability=result['capability'], label=label, fields=fields,
                rows=[{f: r[f] for f in fields} for r in rows], source=deepcopy(source),
                state=deepcopy(audit['confirmed_state']), required_permission=audit['required_permission'])


def research_presentation(saved, owner, conversation_id):
    """Adapt the single executed list cited by the answer, never catalog probes.

    Full investigative evidence stays private. PG retains all executed records;
    only a bounded unambiguous list is exposed to the selection interpreter.
    """
    full = saved.get('full_result') or {}
    cited = {v['claim']['result_id'] for v in full.get('claim_verifications', [])
             if v.get('match') is True and v.get('claim', {}).get('kind') == 'executed_cell'}
    # Coverage/COUNT singleton queries are not competing lists. Keep the one
    # cited grouped entity list even when its answer also cites coverage cells.
    manifests = [m for m in full.get('evidence_manifests', []) if m['result_id'] in cited]
    if len(manifests) > 1:
        manifests = [m for m in manifests if m.get('group_expressions')]
    if len(manifests) > 1:
        # Discovery lists do not compete with the final account list. Never
        # guess between two answer lists of the same grain.
        accounts = [m for m in manifests if any('card_code' in g for g in m['group_expressions'])]
        if len(accounts) == 1:
            manifests = accounts
    if len(manifests) != 1:
        return None
    manifest = manifests[0]
    results = [r for r in full.get('results', []) if r['query_id'] == manifest['query_id']]
    if len(results) != 1:
        return None
    result = results[0]
    # A page-sized prefix is not the population. When the controller recovered
    # the whole grouped population with its existing keyset pages, the durable
    # records are that complete population, exactly once and in order.
    recovery = (full.get('population_recovery') or {}).get(manifest['result_id']) or {}
    pages = (full.get('population_pages') or {}).get(manifest['result_id']) or []
    if recovery and recovery.get('complete') is not True:
        return None  # Known-unrecovered tail: never present a prefix as the result.
    complete = recovery.get('complete') is True and bool(pages)
    if (result.get('status') != 'COMPLETED' or (not complete and result.get('truncated') is not False)
            or not 0 < len(result.get('rows') or []) <= 5000):
        return None
    columns = {c['alias']: c for c in manifest['columns']}
    names = [c['name'] for c in result['schema']]
    if not set(names) <= set(columns) or any(len(row) != len(names) for row in result['rows']):
        return None
    rows = [dict(zip(names, row)) for row in result['rows']]
    if complete:
        seen = {tuple(row.values()) for row in rows}
        for page in pages:
            if (page.get('status') != 'COMPLETED'
                    or [c.get('name') for c in page.get('schema') or ()] != names
                    or any(len(row) != len(names) for row in page.get('rows') or ())):
                return None
            for row in page['rows']:
                record = dict(zip(names, row))
                if tuple(record.values()) in seen:
                    continue
                seen.add(tuple(record.values()))
                rows.append(record)
        if len(rows) != recovery.get('recovered_records'):
            return None  # Durable records must equal the recovered accounting.
    if not 0 < len(rows) <= 5000:
        return None
    delivered = set(full.get('presentation_pages', {}).get(manifest['result_id'], []))
    # Product rows intentionally not selected by the answer may be hidden
    # presentation references. A local page must never resurrect them. Keep
    # their original full population in PG, not in the referencable product list.
    if (not complete and any('item_code' in g for g in manifest.get('group_expressions', []))
            and not any('card_code' in g for g in manifest.get('group_expressions', []))):
        selected_ids = {v['claim'].get('row_id') for v in full.get('claim_verifications', [])
                        if v.get('match') is True and v.get('claim', {}).get('result_id') == manifest['result_id']}
        row_ids = manifest.get('row_ids', [])
        kept = [(i, row) for i, row in enumerate(rows, 1)
                if i <= len(row_ids) and row_ids[i-1] in selected_ids]
        delivered = {new for new, (old, _) in enumerate(kept, 1) if old in delivered}
        rows = [row for _, row in kept]
    if not rows or len(json.dumps(rows).encode()) > (MAX_POPULATION_BYTES if complete else MAX_BYTES):
        return None
    next_ordinal = next((i for i in range(1, len(rows) + 1) if i not in delivered), len(rows) + 1)
    return dict(next_ordinal=next_ordinal,
                result_id=saved['result_id'], owner=deepcopy(owner),
                conversation_id=conversation_id, capability='research.executed_result',
                label='registro', fields={n: n for n in names}, rows=rows,
                schema=deepcopy(result['schema']), source=dict(
                    publication_id=manifest['publication'], snapshot_id=manifest['snapshot']),
                research_receipt=deepcopy(saved['receipt']), required_permission=None,
                question=full.get('question'), manifest=deepcopy(manifest), state={})


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
                   entity_label=result['label'], historical=True,
                   next_ordinal=result.get('next_ordinal'))
    try:
        from . import business_scope
        scope = business_scope.result_scope(result.get('state') or {},
                                            {'capability': result.get('capability'),
                                             'definition': None, 'accreditation': 'verified'})
    except (ValueError, TypeError, KeyError):
        scope = {}
    context['scope'] = scope
    if result['capability'] == 'research.executed_result':
        context.update(next_ordinal=result.get('next_ordinal', 1),
                       rows=deepcopy(result['rows'][:50]), rows_complete=len(result['rows']) <= 50,
                       schema=deepcopy(result['schema']),
                       question=result['question'], evidence=deepcopy(result['manifest']))
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
            or proposal['action'] not in {'SELECT_RESULT', 'PAGE_RESULT'} or proposal['clarification'] is not None):
        raise ValueError('invalid_reference_contract')
    ref = proposal['result_reference']
    if (not isinstance(ref, dict) or set(ref) != {'result_id', 'ordinal', 'field'}
            or result is None or result['owner'] != owner
            or result['conversation_id'] != conversation_id or ref['result_id'] != result['result_id']):
        raise ValueError('result_unavailable')
    if proposal['action'] == 'PAGE_RESULT':
        if ref['field'] is not None:
            raise ValueError('invalid_page_field')
        start = ref['ordinal']
        if type(start) is not int or not 1 <= start <= len(result['rows']):
            raise ValueError('ordinal_unavailable')
        texts = []
        end = start - 1
        for position in range(start, min(start + 4, len(result['rows'])) + 1):
            _, text = resolve(dict(proposal, action='SELECT_RESULT',
                result_reference=dict(ref, ordinal=position)), result, None, owner, conversation_id)
            line = f'{position}. {text}'
            if len('\n'.join(texts + [line])) > 3400:
                break
            texts.append(line)
            end = position
        if not texts:
            return None, 'Ese registro no cabe completo en una página. Pedí un campo específico; no avancé la selección.'
        return end, ('\n'.join(texts) + f'\nMostrados {start}–{end} de {len(result["rows"])} registros conservados. '
                     + ('Podés pedir los siguientes.' if end < len(result['rows']) else 'Fin del resultado conservado; no certifica cobertura fuera de él.'))
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
    if result['capability'] == 'research.executed_result':
        from .capabilities import business_money
        types = {c['name']: c['sql_type'] for c in result['schema']}
        columns = {c['alias']: c for c in result['manifest']['columns']}
        # Currency is an executed filter, never a model-supplied denomination.
        bs = 'currency COMPARE_EQUAL "BS"' in result['manifest'].get('filter_expression', '')
        def display(key, value):
            monetary = (columns[key].get('currency') == 'BS' or
                        (bs and 'sales_line.line_total' in columns[key].get('source_fields', [])))
            if value is not None and types[key].startswith('DECIMAL') and monetary:
                return 'Bs ' + business_money(value)
            return str(value)
        text = ' · '.join(f'{result["fields"][k]}: {display(k, v)}' for k, v in row.items()
                          if v is not None and (field is None or k == field))
        text += '. Según el resultado conservado; líneas publicadas, no facturación neta ni cobros.'
        return ordinal, text
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
