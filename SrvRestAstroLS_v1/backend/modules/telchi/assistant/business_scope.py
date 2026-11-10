"""Business scope: what the conversation is about, in business terms.

The scope is explicit, small and reusable: category, product, billed customer,
metric, dimension, measure, currency, periods and the accreditation of the
result. It is what a later turn recovers, so a follow-up never has to repeat
a product, a customer or a month.
"""
from copy import deepcopy
from datetime import date, timedelta

from .state_engine import scope_window

MEASURE = 'commercial_active_invoice_line_amount_excluding_line_tax_v1'
UNIVERSE = 'active_bs_invoice_lines'
CUSTOMER_TYPE = 'sap_billed'
FISCAL_CONTROL_NAME = 'CONTROL TRIBUTARIO'
MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
          'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')


def month_label(period):
    start = date.fromisoformat(period['start'])
    end = date.fromisoformat(period['end_exclusive'])
    if start.day == 1 and end.day == 1 and (end - start).days <= 31:
        return f'{MONTHS[start.month - 1]} de {start.year}'
    return f'del {start.isoformat()} al {(end - timedelta(days=1)).isoformat()}'


def period_label(periods, single=None):
    """Name every period in scope. A set of periods is never one month."""
    if not periods:
        return month_label(single) if single else None
    if len(periods) == 1:
        return month_label(periods[0])
    labels = [month_label(p) for p in periods]
    if all(label.endswith(tuple(f'de {y}' for y in range(2000, 2100))) for label in labels):
        years = {label.rsplit(' de ', 1)[1] for label in labels}
        if len(years) == 1:
            months = ' y '.join(label.rsplit(' de ', 1)[0] for label in labels)
            return f'{months} de {years.pop()}'
    return ', '.join(labels)


def scope(state):
    """The business scope carried by the state. Never contains business values."""
    window = scope_window(state)
    periods = [dict(p) for p in (state.get('periods') or [])]
    if state.get('period_mode') == 'union' and periods:
        window = state.get('period')
    focus = state.get('focus') or {}
    return dict(
        excluded_product=state.get('excluded_product'),
        excluded_products=state.get('excluded_products'),
        product_offset=state.get('product_offset', 0),
        category=state.get('business_category'),
        product=state.get('product_target'),
        customer=state.get('customer_target'),
        focus=dict(focus),
        customer_label=focus.get('customer_label'),
        customer_type=focus.get('customer_type'),
        metric=state.get('metric'),
        dimension=state.get('group_by'),
        breakdown=state.get('breakdown_by'),
        ranking_by=state.get('ranking_by'),
        period_mode=state.get('period_mode'),
        periods=periods or ([dict(window)] if window else []),
        period=dict(window) if window else None,
        comparison=dict(state['comparison']) if state.get('comparison') else None,
        currency='BS',
    )


def result_scope(state, result):
    """The scope of an executed result, with its accreditation and measure."""
    base = scope(state)
    plan = result.get('plan') or {}
    base = dict(base, measure=plan.get('measure') or result.get('definition'),
                dimension=plan.get('group_by') or base.get('dimension'),
                dataset=plan.get('dataset'),
                universe=UNIVERSE,
                accreditation=result.get('accreditation', 'verified'))
    if result.get('view') == 'historical_position':
        base['periods'] = [dict(o['period']) for o in result.get('periods', [])]
        base['period_mode'] = 'compare' if len(base['periods']) > 1 else 'single'
        base['product'] = result.get('target_item_code') or base.get('product')
    return base


def project(state, result):
    """Project the executed scope into the state. Service owned, never model authored.

    The focus is what the conversation is about: the product and the billed
    customer the last answer certified. It survives a change of filter, so a
    later turn can recover it without the user repeating it.
    """
    from .state_engine import attach_scope
    focus = dict(state.get('focus') or {})
    if result.get('capability') == 'sales.commercial_line_amount_by.v1':
        parameters = result.get('parameters') or {}
        filters = parameters.get('filters') or {}
        published = result.get('focus') or {}
        if filters.get('item_code'):
            focus['product'] = filters['item_code']
            if published.get('item_label'):
                focus['product_label'] = published['item_label']
        if filters.get('card_code'):
            focus['customer'] = filters['card_code']
            if published.get('customer_label'):
                focus['customer_label'] = published['customer_label']
            focus['customer_type'] = CUSTOMER_TYPE
        rows = result.get('rows') or []
        if parameters.get('group_by') == 'card_code' and rows:
            focus['customer'] = rows[0].get('key')
            focus['customer_label'] = rows[0].get('label')
            focus['customer_type'] = CUSTOMER_TYPE
        elif parameters.get('group_by') == 'sap_product' and rows:
            focus['product'] = rows[0].get('key')
            focus['product_label'] = rows[0].get('label')
    elif result.get('view') == 'historical_position':
        if result.get('target_item_code'):
            focus['product'] = result['target_item_code']
            for outcome in result.get('periods') or []:
                if outcome.get('target'):
                    focus['product_label'] = outcome['target'].get('description')
                    break
    if focus:
        attach_scope(state, {'focus': focus})
    return state


def fiscal_control_accounts(rows):
    """Published master names that are SAP fiscal control accounts.

    This is a disclosure, not a classification: the commercial customer
    taxonomy is not accredited, so these accounts are shown and quantified
    instead of being silently removed from the universe.
    """
    matched = [row for row in rows
               if str(row.get('label', '')).strip().upper() == FISCAL_CONTROL_NAME]
    return matched
