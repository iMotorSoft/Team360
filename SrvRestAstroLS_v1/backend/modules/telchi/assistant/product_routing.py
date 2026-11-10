"""Deterministic routing for «a quién le vendimos <producto>».

The existing commercial breakdown (``sales.commercial_line_amount_by`` with
``group_by=card_code``) is the accredited operation for product -> billed
customer. This module only translates a question into that existing plan. It
never creates a capability, never invents an ItemCode and never widens the
period or the scope.

A product mentioned in a previous result is resolved from that presented list
(values stay in the backend). Otherwise the mention is carried as text and the
service resolves it against the accredited catalog under its own permission.
"""
import re
import unicodedata

# Sales verb directed at the buyer of a product. «vendidos» covers the typo of
# the audited turn; the contract is semantic, not a phrase catalogue.
_CUSTOMER_QUESTION = re.compile(
    r'\b(?:a\s+quien(?:es)?|a\s+que\s+clientes?|que\s+clientes?|quien(?:es)?)\b'
    r'.{0,60}\b(?:vendimos|vendio|vendieron|vendidos|compro|compraron)\b'
    r'|\b(?:a\s+quien(?:es)?|que\s+clientes?)\b.{0,30}\bse\s+la\s+vend\w*')
# A customer -> products question is a different plan; never convert it.
_CUSTOMER_AS_SUBJECT = re.compile(
    r'\b(?:que|otros?|cuales?)\s+productos?\b.{0,40}\b(?:compro|compraron|compra)\b'
    r'|\bcuanto\s+(?:compro|compro|compra|compraron)\b')
_UNION = re.compile(r'\b(?:ambos|esos|estos|los dos)\s+meses\b|\bentre\s+(?:ambos|esos|los dos)\s+meses\b')
_ITEM_CODE = re.compile(r'\b([A-Za-z]\d{3,9})\b')
_LIMIT = re.compile(r'\b(?:los|las|top)\s+(\d{1,2})\b')
_STOPWORDS = {'a', 'al', 'de', 'del', 'el', 'en', 'la', 'las', 'le', 'les', 'lo',
              'los', 'por', 'para', 'que', 'se', 'un', 'una', 'x'}


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                   if unicodedata.category(c) != 'Mn')


def tokens(text):
    return [t for t in normalized(text).split() if t not in _STOPWORDS]


def _presented_match(mention, result):
    """Match a mention against the rows of an already authorized presentation."""
    if not isinstance(result, dict) or not isinstance(result.get('rows'), list):
        return []
    wanted = tokens(mention)
    if not wanted:
        return []
    found = []
    for row in result['rows']:
        label = normalized(str(row.get('label') or row.get('description') or ''))
        key = normalized(str(row.get('key') or row.get('item_code') or ''))
        if all(token in label or token in key for token in wanted):
            found.append(row)
    return found


def request_contract(proposal, text, before, reference_result=None):
    """Rewrite only an explicit product -> customer question into its plan.

    Raw interpreter output stays in the audit; the State Engine still validates
    the whole delta atomically. No product code, period or grant is synthesized.
    """
    if not isinstance(proposal, dict) or not isinstance(proposal.get('state_delta'), dict):
        return proposal
    q = normalized(text)
    if not _CUSTOMER_QUESTION.search(q) or _CUSTOMER_AS_SUBJECT.search(q):
        return proposal
    delta = proposal['state_delta']
    sets = {'/' + k.strip().lstrip('/'): v for k, v in (delta.get('set') or {}).items()}
    unsets = ['/' + k.strip().lstrip('/') for k in (delta.get('unset') or [])]
    focus = before.get('focus') or {}
    mention = sets.get('/product_search_text') or before.get('product_search_text')
    code = sets.get('/product_target') or before.get('product_target')
    if not code:
        explicit = _ITEM_CODE.search(text)
        if explicit:
            code = explicit.group(1)
    if not mention and not code and not focus.get('product'):
        return proposal

    product_target, product_search_text = code, None
    if not product_target:
        if mention:
            matches = _presented_match(mention, reference_result)
            if len(matches) == 1:
                product_target = matches[0].get('key') or matches[0].get('item_code')
            else:
                product_search_text = mention
        elif focus.get('product'):
            product_target = focus['product']

    period = sets.get('/period') or before.get('period')
    periods = sets.get('/periods') or before.get('periods')
    period_mode = sets.get('/period_mode') or before.get('period_mode')
    # An exclusion («pero no en septiembre») is a set difference over two periods.
    # The accredited single-period breakdown cannot compute it, so the baseline
    # must stay in the state: dropping it here would execute a plausible but
    # different question. Availability names the real gap and the free analysis
    # path, not this contract, owns the answer.
    comparison = sets.get('/comparison') if '/comparison' in sets else None
    if _UNION.search(q):
        known = sorted([p for p in (before.get('period'), before.get('comparison'),
                                    sets.get('/period'), sets.get('/comparison')) if p],
                       key=lambda p: p['start'])
        unique = {p['start']: p for p in known}
        ordered = [unique[k] for k in sorted(unique)]
        if len(ordered) == 2 and ordered[0]['end_exclusive'] == ordered[1]['start']:
            periods = ordered
            period_mode = 'union'
            period = {'start': ordered[0]['start'], 'end_exclusive': ordered[1]['end_exclusive']}
            comparison = None
    limit = sets.get('/limit')
    if type(limit) is not int or not 1 <= limit <= 50:
        found = _LIMIT.search(q)
        limit = int(found.group(1)) if found and 1 <= int(found.group(1)) <= 50 else 10

    sets.update({
        '/schema_version': 2,
        '/metric': 'sales.commercial_line_amount_by',
        '/requested_metrics': ['sales.commercial_line_amount_by'],
        '/group_by': 'card_code',
        '/product_target': product_target,
        '/product_search_text': product_search_text,
        '/customer_target': None,
        '/ranking_by': None,
        '/ranking_target_item_code': None,
        '/ranking_detail': None,
        '/breakdown_by': None,
        '/period': period,
        '/periods': periods,
        '/period_mode': period_mode,
        '/comparison': comparison,
        '/analysis_categories': None,
        '/physical_focus': None,
        '/entity_mention': None,
        '/temporal_reference': None,
        '/limit': limit,
    })
    # Never keep a stale operation flag that the State Engine would reject.
    for key in ('/pending', '/product_context'):
        unsets = [p for p in unsets if p != key]
    unsets = [p for p in unsets if p not in sets]
    corrected = dict(proposal)
    corrected['state_delta'] = {'set': sets, 'unset': unsets}
    corrected['intent'] = 'REFINE' if any(before.get(k) for k in (
        'metric', 'period', 'product_target', 'product_search_text', 'focus')) else 'NEW_QUERY'
    if period is not None or periods:
        corrected['action'] = 'EXECUTE'
        corrected['clarification'] = None
    else:
        corrected['intent'] = 'NEW_QUERY'
        corrected['action'] = 'ASK'
        corrected['clarification'] = {
            'slot': 'period',
            'question': '¿Para qué período querés los clientes facturados de ese producto?'}
    return corrected
