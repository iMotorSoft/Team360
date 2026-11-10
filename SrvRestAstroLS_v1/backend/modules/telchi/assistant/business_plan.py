"""The closed business plan Team360 compiles into a commercial query.

The interpreter never names a table, a column, a dataset or an expression. It
selects a business dimension and closed filters in the conversational state;
this module turns that scope into an explicit plan, validates it against the
closed vocabulary and hands it to the accredited reader.
"""
from modules.telchi.datalake.commercial_line_amount_by_query import (
    CAPABILITY, DATASET, GROUP_BY, MEASURE, ORDER_BY, QUANTITY_ORDER_BY,
    parameters as commercial_parameters,
)

DATASETS = {
    DATASET: dict(capability=CAPABILITY, measure=MEASURE, group_by=GROUP_BY,
                  filters=('category', 'item_code', 'card_code'), breakdown=('period', 'day', 'products'),
                  order_by=ORDER_BY, currency='BS'),
}


class PlanError(ValueError):
    """The requested scope has no accredited plan."""


def build(state):
    """Compile the validated business scope into an explicit plan.

    The plan is deterministic: the same scope always produces the same plan,
    and the reader validates it again before touching Foundation.
    """
    from .state_engine import scope_window
    dataset = DATASETS.get(DATASET)
    if dataset is None:
        raise PlanError('unknown_dataset')
    window = scope_window(state)
    if not window:
        raise PlanError('period_unresolved')
    group_by = state.get('group_by')
    if group_by not in dataset['group_by']:
        raise PlanError('dimension_not_accredited')
    breakdown = state.get('breakdown_by')
    periods = [dict(p) for p in (state.get('periods') or [])]
    if breakdown == 'period' and len(periods) < 2:
        raise PlanError('period_set_unresolved')
    if breakdown != 'period' and state.get('period_mode') != 'union':
        # Only a union declares a set; a single period or a comparison does not.
        periods = None
    if group_by == 'physical_state' and state.get('comparison'):
        periods = sorted([dict(state['comparison']), dict(state['period'])], key=lambda p: p['start'])
        breakdown = 'period'
        window = dict(start=periods[0]['start'], end_exclusive=periods[-1]['end_exclusive'])
    plan = dict(
        dataset=DATASET,
        filters=dict(category=state.get('business_category'),
                     item_code=state.get('product_target'),
                     card_code=state.get('customer_target')),
        date_from=window['start'],
        date_to_exclusive=window['end_exclusive'],
        group_by=group_by,
        breakdown_by=breakdown,
        periods=periods,
        # A product ranking may be ordered by documentary quantity. The amount
        # stays the measure; the order criterion is closed, never free form.
        order_by=[list(order) for order in (
            QUANTITY_ORDER_BY if state.get('ranking_by') == 'quantity' else dataset['order_by'])],
        measure=dataset['measure'],
        limit=max(9, state.get('limit', 10)) if group_by == 'physical_state' else state.get('limit', 10),
        currency=dataset['currency'],
    )
    if group_by == 'physical_state' and state.get('physical_focus') is not None:
        plan['physical_focus'] = state['physical_focus']
    if group_by == 'physical_state' and breakdown == 'products':
        plan['detail_limit'] = state.get('limit', 10)
    try:
        commercial_parameters(plan)
    except ValueError as exc:
        raise PlanError(str(exc)) from None
    return plan


def describe(plan):
    """A human readable description of a plan. No business values."""
    filters = plan.get('filters') or {}
    return dict(dataset=plan.get('dataset'), group_by=plan.get('group_by'),
                measure=plan.get('measure'), currency=plan.get('currency'),
                breakdown=plan.get('breakdown_by'),
                filters={k: v for k, v in filters.items() if v is not None},
                period=dict(start=plan.get('date_from'), end_exclusive=plan.get('date_to_exclusive')))
