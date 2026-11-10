"""Local arithmetic over accredited results; never query data or trust LLM amounts."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext

from .state_engine import validate
from .capabilities import business_money, business_date, MONTHS
from modules.telchi.datalake.sales_query import MONETARY_OPERATION, MONETARY_PERMISSION, validate_result


def accredited(audit, result_id, owner):
    from modules.telchi.datalake.category_line_amount_query import CAPABILITY
    if (isinstance(audit, dict) and isinstance(audit.get('execution_result'), dict)
            and audit['execution_result'].get('capability') == CAPABILITY):
        return accredited_category(audit, result_id, owner)
    if (not isinstance(audit, dict) or audit.get('owner') != owner
            or audit.get('execution_status') != 'executed'
            or audit.get('business_rbac_verified') is not True
            or audit.get('required_permission') != MONETARY_PERMISSION
            or audit.get('response_prepared', {}).get('classification') != 'DIRECT_AVAILABLE'):
        return None
    try:
        state, result = audit['confirmed_state'], audit['execution_result']
        validate(state)
        if (state['metric'] != 'sales.net_amount' or state['pending'] or state['comparison']
                or state['branches'] or state['sales_channel'] or state.get('entity_mention')
                or state.get('product_search_text') or state.get('semantic_references')
                or result['capability'] != MONETARY_OPERATION + '.v1'):
            return None
        options = dict(date_from=state['period']['start'], date_to_exclusive=state['period']['end_exclusive'], currency='BS')
        validate_result(MONETARY_OPERATION, options, result)
        if result['rows'][0]['invoice_count'] == 0:
            return None  # absence of documents is not accredited zero revenue
        return dict(result_id=result_id, owner=deepcopy(owner), state=deepcopy(state),
                    required_permission=MONETARY_PERMISSION, capability=result['capability'],
                    metric='billed_amount', currency=result['currency'], definition=result['definition'],
                    period=deepcopy(result['period']), source=deepcopy(result['source']),
                    amount=result['rows'][0]['billed_amount'],
                    components={k: result['rows'][0][k] for k in
                                ('billed_amount', 'credit_amount', 'net_amount')},
                    partial=result['source']['updated_at'][:10] < (date.fromisoformat(options['date_to_exclusive'])-timedelta(days=1)).isoformat())
    except (ValueError, KeyError, TypeError, ArithmeticError):
        return None


def accredited_category(audit, result_id, owner):
    from modules.telchi.datalake.category_line_amount_query import CAPABILITY, PERMISSION, validate_result
    from .business_categories import category_code
    try:
        if (audit.get('owner') != owner or audit.get('execution_status') != 'executed'
                or audit.get('business_rbac_verified') is not True
                or audit.get('required_permission') != PERMISSION
                or audit.get('response_prepared', {}).get('classification') != 'DIRECT_AVAILABLE'):
            return None
        state, result = audit['confirmed_state'], audit['execution_result']
        validate(state)
        from .capabilities import SalesCapabilities
        if not SalesCapabilities().availability(state).allowed or not category_code(state):
            return None
        options = dict(category=category_code(state), currency='BS', date_from=state['period']['start'],
            date_to_exclusive=state['period']['end_exclusive'])
        validate_result(options, result)
        if not result['rows'][0]['line_count']:
            return None
        return dict(result_id=result_id, owner=deepcopy(owner), state=deepcopy(state),
            required_permission=PERMISSION, capability=CAPABILITY, metric='category_line_amount',
            currency=result['currency'], definition=result['definition'],
            category=category_code(state), period={k: options[k] for k in ('date_from','date_to_exclusive')},
            coverage=deepcopy(result['coverage']), classification=deepcopy(result['classification']),
            source=deepcopy(result['source']), amount=result['rows'][0]['amount'], partial=True)
    except (KeyError, ValueError, TypeError, ArithmeticError):
        return None


def calculate_components(ref, results, owner):
    """Closed arithmetic over components of ONE validated monetary result.

    No expressions, new queries, cross-result composition or model-supplied values.
    The handler revalidates the original result's permission before disclosure.
    """
    if (not isinstance(ref['target_id'], str) or ref['target_id'] != ref['baseline_id']
            or ref['mode'] not in {'ratio_percent', 'difference'}
            or not isinstance(ref['target_field'], str) or not isinstance(ref['baseline_field'], str)
            or ref['target_field'] == ref['baseline_field']):
        raise ValueError('invalid_component_reference')
    result = {r['result_id']: r for r in results}[ref['target_id']]
    if (result['owner'] != owner or result['capability'] != MONETARY_OPERATION + '.v1'
            or result['required_permission'] != MONETARY_PERMISSION):
        raise ValueError('incompatible_component_result')
    labels = {'billed_amount': 'facturación', 'credit_amount': 'notas de crédito', 'net_amount': 'neto documental'}
    if ref['target_field'] not in labels or ref['baseline_field'] not in labels:
        raise ValueError('unknown_component')
    with localcontext() as ctx:
        ctx.prec = 50
        a, b = (Decimal(result['components'][ref[k]]) for k in ('target_field', 'baseline_field'))
        if not a.is_finite() or not b.is_finite() or (ref['mode'] == 'ratio_percent' and b <= 0):
            raise ValueError('invalid_component_amount')
        difference = a - b
        percent = a / b * 100 if b > 0 else None
    ratio = ref['mode'] == 'ratio_percent'
    record = dict(deepcopy(ref), target=deepcopy(result), baseline=deepcopy(result),
                  difference=str(difference), percent=str(percent) if percent is not None else None,
                  formula='target / baseline * 100' if ratio else 'target - baseline')
    target, base = labels[ref['target_field']], labels[ref['baseline_field']]
    value = business_money(percent) + ' %' if ratio else result['currency'] + ' ' + business_money(difference)
    text = (f'{target.capitalize()} sobre {base}: {value}. ' if ratio else
            f'Diferencia entre {target} y {base}: {value}. ')
    text += (f"Base: {result['currency']} {business_money(b)}. "
             f"Período: {business_date(result['period']['date_from'])} a "
             f"{business_date((date.fromisoformat(result['period']['date_to_exclusive']) - timedelta(days=1)).isoformat())}. "
             f"Reutilizo el resultado anterior autorizado, con información al {business_date(result['source']['updated_at'])}; "
             'no hice una nueva consulta. Cobertura completa no certificada. No equivale a cobros ni saldo pendiente.')
    if result['partial']:
        text += ' Información parcial: no certifica cierre del período.'
    return record, text


def descriptors(results, previous=None):
    # No amounts or row values leave Team360.
    return dict(results=[dict({k: r[k] for k in ('result_id', 'metric', 'currency', 'period', 'partial')},
                             **({'category': r['category']} if 'category' in r else {}),
                             **({'fields': list(r['components'])} if 'components' in r else {})) for r in results],
                previous=previous)


def calculate(proposal, results, owner):
    if (not isinstance(proposal, dict) or set(proposal) != {'intent', 'action', 'comparison', 'clarification'}
            or proposal['intent'] != 'MONETARY_COMPARISON' or proposal['action'] != 'CALCULATE'
            or proposal['clarification'] is not None):
        raise ValueError('invalid_comparison_contract')
    ref = proposal['comparison']
    if isinstance(ref, dict) and set(ref) == {'target_id', 'baseline_id', 'mode', 'target_field', 'baseline_field'}:
        return calculate_components(ref, results, owner)
    if (not isinstance(ref, dict) or set(ref) != {'target_id', 'baseline_id', 'mode'}
            or ref['mode'] not in {'difference', 'percent'}
            or not isinstance(ref['target_id'], str) or not isinstance(ref['baseline_id'], str)
            or ref['target_id'] == ref['baseline_id']):
        raise ValueError('ambiguous_comparison')
    by_id = {r['result_id']: r for r in results}
    target, base = by_id[ref['target_id']], by_id[ref['baseline_id']]
    if any(r['owner'] != owner for r in (target, base)):
        raise ValueError('owner_changed')
    if any(target[k] != base[k] for k in ('metric', 'currency', 'definition', 'capability', 'source')):
        raise ValueError('incompatible_results')
    category_comparison = target['metric'] == 'category_line_amount'
    if category_comparison:
        if (target['category'] == base['category'] or target['period'] != base['period']
                or target['coverage'] != base['coverage']
                or any(target['classification'][k] != base['classification'][k] for k in ('version','sha256','reference'))):
            raise ValueError('incompatible_categories_or_coverage')
    else:
        if target['period'] == base['period']:
            raise ValueError('same_period')
        # Periods must not overlap. Explicit reversed comparisons retain their sign.
        if not (target['period']['date_from'] >= base['period']['date_to_exclusive']
                or base['period']['date_from'] >= target['period']['date_to_exclusive']):
            raise ValueError('overlapping_periods')
    with localcontext() as ctx:
        ctx.prec = 50
        a, b = Decimal(target['amount']), Decimal(base['amount'])
        if not a.is_finite() or not b.is_finite():
            raise ValueError('nonfinite')
        difference = a - b
        if ref['mode'] == 'percent' and b <= 0:
            raise ValueError('invalid_percentage_base')
        percent = difference / b * 100 if b > 0 else None
    record = dict(deepcopy(ref), target=deepcopy(target), baseline=deepcopy(base),
                  difference=str(difference), percent=str(percent) if percent is not None else None,
                  formula='(target - baseline) / baseline * 100' if ref['mode'] == 'percent' else 'target - baseline')
    def label(r):
        start = date.fromisoformat(r['period']['date_from'])
        end = date.fromisoformat(r['period']['date_to_exclusive'])
        if start.day == end.day == 1 and (end-start).days <= 31:
            return f'{MONTHS[start.month-1]} de {start.year}'
        return f"{business_date(start.isoformat())} a {business_date((end-timedelta(days=1)).isoformat())}"
    if category_comparison:
        from .business_categories import CATEGORIES
        winner = target if difference >= 0 else base
        text = ('Las dos categorías registraron el mismo importe.' if difference == 0 else
            f"{CATEGORIES[winner['category']]} registró más importe de líneas comerciales, "
            f"con una diferencia de Bs {business_money(abs(difference))}.")
        if ref['mode'] == 'percent':
            text += (f" Variación de {CATEGORIES[target['category']]} respecto de "
                     f"{CATEGORIES[base['category']]}: {business_money(percent)} %.")
        text += (f" Período: {label(target)}. Cobertura documental observada hasta "
            f"{business_date(target['coverage']['last_date'])}; período completo no certificado. "
            'Comparación de resultados consultados, sin IVA de línea ni descuento de notas de crédito; no es neto ni cobros.')
        return record, text
    value = (business_money(percent) + ' %' if ref['mode'] == 'percent'
             else target['currency'] + ' ' + business_money(difference))
    text = (f"Diferencia: {value}. Facturación registrada de {label(target)} respecto de {label(base)}. "
            f"Base: {base['currency']} {business_money(b)}. ")
    if target['partial'] or base['partial']:
        partials = ' y '.join(label(r) for r in (target, base) if r['partial'])
        text += f'Información parcial en {partials}: no es una caída ni una tendencia mensual definitiva. '
    text += (f"Resultados anteriores con información al {business_date(target['source']['updated_at'])}; "
             'cobertura completa no certificada. No equivale a cobros ni a saldo pendiente.')
    return record, text
