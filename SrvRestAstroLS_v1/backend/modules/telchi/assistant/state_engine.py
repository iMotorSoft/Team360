"""Sales-only adaptation of LlmFit's atomic delta/pending contract.

No natural-language rules, experimental imports or execution authority. A
validated request is not an executed query; capability availability is separate.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import re
from typing import TypedDict, Literal, NotRequired
from modules.telchi.datalake.operational_query import OPERATIONS, SNAPSHOT_METRICS


class Period(TypedDict):
    start: str
    end_exclusive: str


class SalesState(TypedDict):
    metric: Literal['sales.net_amount', 'sales.source_top_items', 'sales.latest_documents', 'sales.coverage', 'sales.product_line_amount_ranking'] | None
    period: Period | None
    branches: list[str]
    sales_channel: Literal['HORIZONTAL', 'SALON'] | None
    comparison: Period | None
    reference: str | None
    pending: dict | None
    limit: NotRequired[int]
    ranking_target_item_code: NotRequired[str | None]
    ranking_detail: NotRequired[Literal['exceptions'] | None]
    schema_version: NotRequired[Literal[2]]
    requested_metrics: NotRequired[list[str]]  # ordered: first metric is /metric
    entity_mention: NotRequired[dict | None]  # unresolved, never a guessed filter
    temporal_reference: NotRequired[Literal['latest_available_month'] | None]


EMPTY: SalesState = dict(metric=None, period=None, branches=[], sales_channel=None,
             comparison=None, reference=None, pending=None)
# Optional, versioned conversational extension. Legacy persisted states remain valid.
INTENT_V2 = dict(schema_version=2, requested_metrics=[], entity_mention=None,
                 temporal_reference=None)
QUERY_FIELDS = {'limit': 10, 'ranking_target_item_code': None, 'ranking_detail': None}
PRODUCT_FIELDS = dict(product_search_text=None, product_context=None, selected_item_codes=[])
SEMANTIC_FIELDS = {'semantic_references': []}  # Application-owned references, not LLM-editable paths.
# Business scope (V3): explicit commercial entities, dimension and period set.
# LLM-settable through the closed vocabulary; never free-form commercial filters.
SCOPE_FIELDS = {
    'analysis_categories': None,  # closed category-share request, including explicit unaccredited labels
    'excluded_product': None,   # presentation exclusion, never a product filter
    'product_offset': 0,        # bounded presentation page within the retained ranking
    'business_category': None,   # canonical product_business_type code
    'product_target': None,      # SAP ItemCode in focus, transferable across metrics
    'customer_target': None,     # SAP CardCode in focus (billed customer)
    'physical_focus': None,      # presentation focus, never a monetary exclusion
    'group_by': None,            # 'sap_product' | 'card_code' | 'physical_state'
    'breakdown_by': None,        # 'period': read each period of the set separately
    'periods': None,             # list[Period]: the set of periods read together
    'period_mode': None,         # 'single' | 'union' | 'compare'
}
# Service-owned projection of the executed scope. Never written by the model.
OWNED_SCOPE_FIELDS = {'focus': None, 'customer_type': None}
METRICS = {'sales.net_amount', 'sales.source_top_items', 'sales.latest_documents', 'sales.coverage',
           'products.search', 'sales.by_products', 'sales.product_line_amount_ranking',
           'sales.commercial_line_amount_by'} | set(OPERATIONS)
# A row limit belongs to the operation that asked for it. These are the
# analytical families: a limit used for a ranking never contaminates a later
# product or customer query, and a limit of one family never reaches another.
LIMIT_FAMILIES = {
    'sales.product_line_amount_ranking': 'ranking',
    'sales.commercial_line_amount_by': 'commercial',
    'sales.latest_documents': 'documents',
    'products.search': 'catalog',
    'sales.by_products': 'products',
    'sales.net_amount': 'aggregate',
    'sales.coverage': 'aggregate',
    'sales.source_top_items': 'aggregate',
}


def limit_family(metric):
    """The analytical family a row limit belongs to."""
    return LIMIT_FAMILIES.get(metric, 'aggregate')


def scope_limit(base, after, delta):
    """Keep a row limit inside the operation that requested it.

    A limit inherited from another family is dropped and the corresponding
    default of the new operation applies. An explicit quantity requested by
    the user is always respected.
    """
    if '/limit' in (delta.get('set') or {}):
        return after
    if base.get('metric') == after.get('metric'):
        return after
    if limit_family(base.get('metric')) == limit_family(after.get('metric')):
        return after
    if 'limit' in after and after.get('limit') != DEFAULTS['limit']:
        after = dict(after, limit=DEFAULTS['limit'])
    return after
# Metrics whose scope is a product or a business category: a commercial entity
# mention is not a filter they can honour.
PRODUCT_SCOPED_METRICS = {'sales.product_line_amount_ranking', 'sales.commercial_line_amount_by'}
DEFAULTS = EMPTY | INTENT_V2 | QUERY_FIELDS | PRODUCT_FIELDS | SCOPE_FIELDS
GROUP_BY_VALUES = {'sap_product', 'card_code', 'physical_state'}
PERIOD_MODES = {'single', 'union', 'compare'}
ITEM_CODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,49}')
CARD_CODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,19}')
INTENTS = {'NEW_QUERY', 'REFINE', 'COMPARE', 'REFERENCE', 'CORRECT', 'ANSWER_CLARIFICATION', 'EXPLAIN'}
ACTIONS = {'ASK', 'EXECUTE', 'DIRECT_UNAVAILABLE', 'ANALYSIS_UNAVAILABLE'}


def state_hash(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def patch(state, delta):
    if not isinstance(delta, dict) or set(delta) != {'set', 'unset'}:
        raise ValueError('invalid_delta')
    sets, unsets = delta['set'], delta['unset']
    if not isinstance(sets, dict) or not isinstance(unsets, list):
        raise ValueError('invalid_delta')
    paths = list(sets) + unsets
    if any(not isinstance(p, str) for p in paths):
        raise ValueError('invalid_paths')
    # LlmFit atomic_paths: serialization-only prefix normalization, no guessing.
    normalize = lambda p: '/' + p.strip().lstrip('/')
    canonical = [normalize(p) for p in paths]
    if len(canonical) != len(set(canonical)):
        raise ValueError('conflicting_paths')
    sets = {normalize(p): value for p, value in sets.items()}
    unsets = [normalize(p) for p in unsets]
    paths = canonical
    if not set(paths) <= {'/' + k for k in (EMPTY | INTENT_V2 | QUERY_FIELDS | PRODUCT_FIELDS | SCOPE_FIELDS)
                          if k not in {'pending', 'product_context'}}:
        raise ValueError('unknown_path')
    after = deepcopy(state)
    if any(p[1:] in INTENT_V2 or p[1:] in PRODUCT_FIELDS for p in paths):
        after = dict(deepcopy(INTENT_V2 | PRODUCT_FIELDS), **after)
    if ('/product_search_text' in sets and sets['/product_search_text'] is not None
            and sets['/product_search_text'] != state.get('product_search_text')):
        # A refined label with an explicit selection does not invalidate real IDs.
        # Validation below still rejects IDs absent from the previous search.
        if not (sets.get('/selected_item_codes') and state.get('product_context')):
            after['product_context'], after['selected_item_codes'] = None, []
    for p in paths:
        key = p[1:]
        after[key] = deepcopy(sets[p] if p in sets else DEFAULTS[key])
    # Resolve the entire atomic delta first: clearing a search abandons its
    # candidates only when no selection remains. Retained IDs still require
    # the trusted context and are validated below (never silently discarded).
    if ('/product_search_text' in paths and after['product_search_text'] is None
            and after.get('selected_item_codes') == []):
        after['product_context'] = None
    # The engine, not the model, owns the period window of a period set. A union
    # of contiguous periods is read as one window; the set itself is preserved so
    # a later turn can still name the individual periods.
    mode = effective_period_mode(after)
    if mode == 'union' and not after.get('periods'):
        # The union of the two periods already in context. Deterministic, and
        # only when the model asked for a union of contiguous periods.
        known = sorted([p for p in (after.get('comparison'), after.get('period')) if p],
                       key=lambda p: p['start'])
        if len(known) == 2 and known[0]['end_exclusive'] == known[1]['start']:
            after['periods'] = known
    if mode == 'union':
        merged = merge_periods(after.get('periods'))
        if merged is None:
            raise ValueError('invalid_period_set')
        after['period'] = merged
        # In a union the two periods are read together: the comparison slot of
        # a previous question has no meaning and would name a false baseline.
        after['comparison'] = None
    elif mode == 'single':
        after.pop('periods', None)
    # A product- or category-scoped operation cannot honour a commercial entity
    # filter. Reject the transition instead of persisting a mention that silently
    # replaces the category or the product in focus.
    if after.get('metric') in PRODUCT_SCOPED_METRICS:
        from .business_categories import CATEGORIES
        entity = after.get('entity_mention')
        if isinstance(entity, dict) and entity.get('text') not in CATEGORIES:
            raise ValueError('entity_not_supported_by_metric')
    validate(after)
    # Recover previously persisted abandoned searches too, not only explicit
    # removals in this delta. Validate provenance first; never repair malformed
    # context or discard selected IDs, active searches or documentary pointers.
    from .business_categories import category_code
    context = after.get('product_context')
    if (after.get('metric') == 'sales.net_amount'
            and after.get('requested_metrics') == ['sales.net_amount']
            and category_code(after) is not None
            and after.get('product_search_text') is None
            and after.get('selected_item_codes') == []
            and context is not None and context.get('capability') == 'products.search.v1'):
        after['product_context'] = None
    return after


def interval(value):
    if not isinstance(value, dict) or set(value) != {'start', 'end_exclusive'}:
        raise ValueError('invalid_period')
    start, end = date.fromisoformat(value['start']), date.fromisoformat(value['end_exclusive'])
    if not start < end or (end - start).days > 366:
        raise ValueError('invalid_period')


def effective_period_mode(state):
    """How the periods in scope are read together.

    An explicit mode wins. A declared set of periods is a union. A comparison
    is a comparison. A single period is a single period: never a union.
    """
    mode = state.get('period_mode')
    if mode:
        return mode
    if state.get('periods'):
        return 'union'
    return 'compare' if state.get('comparison') else 'single'


def merge_periods(periods):
    """Merge a contiguous, ordered set of periods into one window.

    Only adjacent periods merge. Gaps or overlaps are not a union: they would
    silently drop or double count days.
    """
    if not isinstance(periods, list) or len(periods) < 2:
        return None
    ordered = []
    for value in periods:
        interval(value)
        ordered.append((date.fromisoformat(value['start']), date.fromisoformat(value['end_exclusive'])))
    for previous, current in zip(ordered, ordered[1:]):
        if previous[1] != current[0]:
            return None
    if (ordered[-1][1] - ordered[0][0]).days > 366:
        return None
    return {'start': ordered[0][0].isoformat(), 'end_exclusive': ordered[-1][1].isoformat()}


def scope_window(state):
    """The window a commercial scope is read over. Never collapses a period set."""
    if state.get('period_mode') == 'union' and state.get('periods'):
        merged = merge_periods(state['periods'])
        if merged is not None:
            return merged
    return state.get('period')


def attach_scope(state, scope):
    """Service-owned projection of an executed scope. Never model authored."""
    for key in OWNED_SCOPE_FIELDS:
        if key in scope:
            state[key] = deepcopy(scope[key])
    if state.get('pending'):
        state['pending']['base_state_hash'] = state_hash(dict(state, pending=None))
    validate(state)
    return state


def validate_scope(state):
    """Business scope must be explicit, closed and internally consistent."""
    import re
    from .business_categories import CATEGORIES
    categories = state.get('analysis_categories')
    if categories is not None:
        if (not isinstance(categories, list) or not 1 <= len(categories) <= 6
                or any(not isinstance(c, str) or c not in set(CATEGORIES) | {'MEDICATIONS'} for c in categories)
                or len(set(categories)) != len(categories)):
            raise ValueError('invalid_analysis_categories')
        if (state.get('metric') != 'sales.net_amount' or state.get('customer_target')
                or state.get('product_target') or state.get('business_category')
                or state.get('entity_mention') or state.get('periods') or state.get('comparison')):
            raise ValueError('inconsistent_category_analysis')
    offset = state.get('product_offset', 0)
    if type(offset) is not int or not 0 <= offset <= 45 or (offset and not state.get('excluded_product')):
        raise ValueError('invalid_product_offset')
    excluded = state.get('excluded_product')
    if excluded is not None and (not isinstance(excluded, str) or ITEM_CODE.fullmatch(excluded) is None
            or state.get('metric') != 'sales.commercial_line_amount_by'
            or state.get('group_by') != 'sap_product' or not state.get('customer_target')
            or state.get('product_target')):
        raise ValueError('invalid_product_exclusion')
    category = state.get('business_category')
    if category is not None and category not in CATEGORIES:
        raise ValueError('invalid_business_category')
    product = state.get('product_target')
    if product is not None and (not isinstance(product, str)
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,49}', product) is None):
        raise ValueError('invalid_product_target')
    customer = state.get('customer_target')
    if customer is not None and (not isinstance(customer, str)
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,19}', customer) is None):
        raise ValueError('invalid_customer_target')
    if state.get('group_by') is not None and state['group_by'] not in GROUP_BY_VALUES:
        raise ValueError('invalid_group_by')
    if state.get('physical_focus') not in {None, 'LIQUID', 'SOLID', 'SEMISOLID', 'UNCLASSIFIED',
                                           'MISSING', 'MEDICINE', 'NOT_APPLICABLE', 'UNKNOWN', 'IDENTITY_MISSING'}:
        raise ValueError('invalid_physical_focus')
    if state.get('physical_focus') is not None and state.get('group_by') != 'physical_state':
        raise ValueError('physical_focus_requires_dimension')
    if state.get('breakdown_by') not in {None, 'period', 'day', 'products'}:
        raise ValueError('invalid_breakdown_by')
    if state.get('breakdown_by') in {'day', 'products'} and state.get('group_by') != 'physical_state':
        raise ValueError('physical_breakdown_requires_dimension')
    if state.get('breakdown_by') == 'period' and state.get('periods') is None:
        raise ValueError('breakdown_requires_period_set')
    if state.get('customer_type') not in {None, 'sap_billed'}:
        raise ValueError('invalid_customer_type')
    label = state.get('customer_label')
    if label is not None and (not isinstance(label, str) or not 0 < len(label) <= 120):
        raise ValueError('invalid_customer_label')
    focus = state.get('focus')
    if focus is not None:
        if (not isinstance(focus, dict)
                or set(focus) - {'product', 'product_label', 'customer', 'customer_label', 'customer_type'}
                or any(not isinstance(v, str) or not v or len(v) > 120 for v in focus.values())):
            raise ValueError('invalid_focus')
        if focus.get('customer') is not None and CARD_CODE.fullmatch(focus['customer']) is None:
            raise ValueError('invalid_focus')
        if focus.get('product') is not None and ITEM_CODE.fullmatch(focus['product']) is None:
            raise ValueError('invalid_focus')
    mode = state.get('period_mode')
    if mode is not None and mode not in PERIOD_MODES:
        raise ValueError('invalid_period_mode')
    mode = effective_period_mode(state)
    periods = state.get('periods')
    if periods is not None:
        if not isinstance(periods, list) or not 2 <= len(periods) <= 6:
            raise ValueError('invalid_period_set')
        for value in periods:
            interval(value)
    if mode == 'union':
        merged = merge_periods(periods)
        if merged is None:
            raise ValueError('invalid_period_set')
        if state.get('period') is not None and state['period'] != merged:
            # A union is never one of its months: the window is the whole set.
            raise ValueError('inconsistent_period_set')
    elif mode == 'compare':
        if state.get('comparison') is None:
            raise ValueError('comparison_required')
        if periods is not None:
            raise ValueError('invalid_period_set')
    elif mode == 'single' and periods is not None:
        raise ValueError('invalid_period_set')
    if mode == 'compare' and state.get('comparison') is None:
        raise ValueError('comparison_required')
    entity = state.get('entity_mention')
    if (isinstance(entity, dict) and entity.get('text') in CATEGORIES
            and category is not None and entity['text'] != category):
        raise ValueError('incompatible_business_category')


def validate(state):
    if (not isinstance(state, dict) or not set(EMPTY) <= set(state)
            or not set(state) <= set(EMPTY | INTENT_V2 | QUERY_FIELDS | PRODUCT_FIELDS | SEMANTIC_FIELDS
                                     | SCOPE_FIELDS | OWNED_SCOPE_FIELDS)):
        raise ValueError('invalid_state')
    if state.get('ranking_detail') not in (None, 'exceptions'):
        raise ValueError('invalid_ranking_detail')
    target = state.get('ranking_target_item_code')
    if target is not None:
        import re
        if not isinstance(target, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,49}', target) is None:
            raise ValueError('invalid_ranking_target')
    if 'limit' in state and (type(state['limit']) is not int or not 1 <= state['limit'] <= 50):
        raise ValueError('invalid_sales_limit')
    if 'semantic_references' in state:
        refs = state['semantic_references']
        from uuid import UUID
        if not isinstance(refs, list) or len(refs) > 5:
            raise ValueError('invalid_semantic_references')
        for ref in refs:
            if (not isinstance(ref, dict) or set(ref) != {'concept_id', 'version'}
                    or not isinstance(ref['concept_id'], str)
                    or str(UUID(ref['concept_id'])) != ref['concept_id']
                    or type(ref['version']) is not int or ref['version'] < 1):
                raise ValueError('invalid_semantic_reference')
    if set(state) - set(EMPTY | QUERY_FIELDS | SEMANTIC_FIELDS | SCOPE_FIELDS | OWNED_SCOPE_FIELDS):
        if not set(INTENT_V2) <= set(state) or type(state['schema_version']) is not int or state['schema_version'] != 2:
            raise ValueError('invalid_intent_version')
        metrics = state['requested_metrics']
        if (not isinstance(metrics, list) or len(metrics) > 2
                or any(not isinstance(m, str) or m not in METRICS for m in metrics)
                or len(metrics) != len(set(metrics))
                or (metrics and state['metric'] != metrics[0])):
            raise ValueError('invalid_requested_metrics')
        entity = state['entity_mention']
        if entity is not None and (not isinstance(entity, dict) or set(entity) != {'text', 'type'}
                or not isinstance(entity['text'], str) or not 0 < len(entity['text']) <= 120
                or entity['type'] is not None):
            raise ValueError('unresolved_entity_required')
        if state['temporal_reference'] not in {None, 'latest_available_month'}:
            raise ValueError('invalid_temporal_reference')
        if state['temporal_reference'] is not None and state['period'] is not None:
            raise ValueError('unresolved_period_conflict')
    if set(state) & set(SCOPE_FIELDS | OWNED_SCOPE_FIELDS):
        validate_scope(state)
    if any(k in state for k in PRODUCT_FIELDS):
        text, context, selected = (state.get(k) for k in PRODUCT_FIELDS)
        if text is not None and (not isinstance(text, str) or not 0 < len(text) <= 120):
            raise ValueError('invalid_product_search_text')
        if not isinstance(selected, list) or len(selected) > 20 or len(selected) != len(set(selected)):
            raise ValueError('invalid_product_selection')
        available_codes = set()
        if context is not None:
            from modules.telchi.datalake.product_sales_query import validate_result
            if context.get('parameters', {}).get('limit') != 20:
                raise ValueError('invalid_product_context_limit')
            validate_result('products.search', context['parameters'], context)
            available_codes = {r['item_code'] for r in context['rows']}
        if any(not isinstance(c, str) or c not in available_codes for c in selected):
            raise ValueError('item_code_not_from_search')
    if state['metric'] is not None and state['metric'] not in METRICS:
        raise ValueError('unknown_metric')
    for key in ('period', 'comparison'):
        if state[key] is not None:
            interval(state[key])
    branches = state['branches']
    if (not isinstance(branches, list) or len(branches) > 10
            or any(not isinstance(b, str) or not b or len(b) > 80 for b in branches)
            or len(branches) != len(set(branches))):
        raise ValueError('invalid_branches')
    if state['sales_channel'] not in {None, 'HORIZONTAL', 'SALON'}:
        raise ValueError('invalid_channel')
    if state['reference'] is not None and not isinstance(state['reference'], str):
        raise ValueError('invalid_reference')


def attach_semantic_references(state, references):
    """Only after committed=True. Keep pending hash coherent; references grant no execution."""
    state['semantic_references'] = deepcopy(references)
    if state.get('pending'):
        state['pending']['base_state_hash'] = state_hash(dict(state, pending=None))
    validate(state)


def process(before, proposal, history, turn_id):
    """Rejection retains raw action deliberately; downstream MUST check commit."""
    try:
        validate(before)
        if not isinstance(proposal, dict) or set(proposal) != {'intent', 'action', 'state_delta', 'clarification'}:
            raise ValueError('invalid_envelope')
        intent, action = proposal['intent'], proposal['action']
        if intent not in INTENTS or action not in ACTIONS:
            raise ValueError('invalid_enum')
        base = deepcopy(before)
        if intent == 'NEW_QUERY':
            base.pop('limit', None)
            base.pop('ranking_target_item_code', None)
            base.pop('ranking_detail', None)
        delta = deepcopy(proposal['state_delta'])
        # A new query already discards application-owned product context. Accept
        # its explicit removal only here; never allow model-supplied context/IDs.
        if intent == 'NEW_QUERY' and isinstance(delta.get('unset'), list):
            if delta['unset'].count('/product_context') > 1:
                raise ValueError('conflicting_paths')
            delta['unset'] = [p for p in delta['unset'] if p != '/product_context']
        sets = delta.get('set', {})
        if intent == 'NEW_QUERY' and (before.get('schema_version') == 2 or sets.get('/schema_version') == 2):
            # V2 NEW_QUERY is independent; missing slots cannot inherit a prior plan.
            base = deepcopy(EMPTY | INTENT_V2 | PRODUCT_FIELDS)
        if action == 'ASK':
            spec = proposal['clarification']
            if (not isinstance(spec, dict) or set(spec) != {'slot', 'question'}
                    or spec['slot'] not in {'metric', 'period', 'branches', 'comparison', 'reference'}
                    or not isinstance(spec['question'], str) or not 0 < len(spec['question']) <= 300):
                raise ValueError('invalid_clarification')
            # A follow-up ASK must retain the known slots from the previous ASK.
            # CORRECT also supersedes a pending clarification: the user corrected
            # the intention instead of literally answering the question.
            if before['pending'] and intent in {'ANSWER_CLARIFICATION', 'CORRECT'}:
                pending = before['pending']
                if pending['base_state_hash'] != state_hash(dict(before, pending=None)):
                    raise ValueError('stale_pending')
                base = deepcopy(pending['proposed'])
            known = patch(dict(base, pending=None), delta)
            slot = spec['slot']
            if ((slot == 'metric' and known.get('requested_metrics'))
                    or (known.get('schema_version') == 2 and slot == 'period'
                        and (known['period'] is not None or known.get('temporal_reference')))):
                raise ValueError('clarification_already_answered')
            # Known proposal stays pending, never modifies the active request.
            after = deepcopy(before)
            after['pending'] = dict(spec=deepcopy(spec), proposed=known,
                                    base_state_hash=state_hash(dict(before, pending=None)), source_turn_id=turn_id)
        else:
            if proposal['clarification'] is not None:
                raise ValueError('unexpected_clarification')
            if before['pending'] and intent in {'ANSWER_CLARIFICATION', 'CORRECT'}:
                pending = before['pending']
                if pending['base_state_hash'] != state_hash(dict(before, pending=None)):
                    raise ValueError('stale_pending')
                base = deepcopy(pending['proposed'])
            elif before['pending'] and intent == 'NEW_QUERY':
                base['pending'] = None
            elif before['pending'] and action == 'EXECUTE':
                raise ValueError('unresolved_pending')
            after = patch(base, delta)
            after = scope_limit(base, after, delta)
            if intent in {'ANSWER_CLARIFICATION', 'CORRECT'}:
                after['pending'] = None
            ref = after['reference']
            if ref is not None:
                if ref not in history:
                    raise ValueError('unavailable_reference')
                if intent == 'REFERENCE':
                    restored = deepcopy(history[ref])
                    restored['reference'] = ref
                    after = patch(restored, delta)
            if action == 'EXECUTE' and intent == 'EXPLAIN':
                raise ValueError('explanation_is_not_execution')
            if action == 'EXECUTE' and (after['metric'] is None or after['pending']
                    or (after['period'] is None and after['metric'] not in ({'sales.latest_documents', 'sales.coverage', 'products.search', 'sales.by_products'} | SNAPSHOT_METRICS))):
                raise ValueError('not_ready')
        validate(after)
        return dict(output=deepcopy(proposal), state_after=after, committed=True, contract_error=None)
    except (ValueError, TypeError, KeyError, AttributeError):
        return dict(output=deepcopy(proposal), state_after=deepcopy(before), committed=False,
                    contract_error='CONTRACT_ERROR_NO_COMMIT')
