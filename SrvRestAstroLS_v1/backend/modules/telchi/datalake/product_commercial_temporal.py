"""Additive temporal usage contract; legacy purpose values remain untouched."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Mapping

from .product_commercial_semantics import dataset_relation
from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb

VERSION = '1.0.0'
CONTRACT = 'temporal_commercial_purpose_v1'
DOMAINS = {'commercial', 'internal'}


def _date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError('date must be an ISO date')
    return date.fromisoformat(value)


def evidence_dates(evidence):
    """Dated positive observations; counts/flags/names are not dated events."""
    if set(evidence) != DOMAINS:
        raise ValueError('both evidence domains are required')
    result = {}
    for domain in DOMAINS:
        values = [_date(v) for v in evidence[domain]]
        if len(values) != len(set(values)):
            raise ValueError('duplicate product/day/domain evidence: fanout')
        result[domain] = sorted(values)
    return result


def historical_usage_profile(evidence):
    dates = evidence_dates(evidence)
    commercial, internal = bool(dates['commercial']), bool(dates['internal'])
    profile = ('MIXED' if commercial and internal else 'COMMERCIAL_EVIDENCE_ONLY' if commercial
               else 'INTERNAL_EVIDENCE_ONLY' if internal else 'UNKNOWN')
    return {'historical_usage_profile': profile, 'historical_usage_profile_version': VERSION,
            'historical_commercial_evidence': commercial, 'historical_internal_use_evidence': internal,
            'commercial_evidence_first_date': str(dates['commercial'][0]) if commercial else None,
            'commercial_evidence_last_date': str(dates['commercial'][-1]) if commercial else None,
            'internal_use_evidence_first_date': str(dates['internal'][0]) if internal else None,
            'internal_use_evidence_last_date': str(dates['internal'][-1]) if internal else None}


def _coverage(item, domain, coverage, start, end):
    """Require explicit proof of whole-domain absence, including interval holes."""
    intervals = []
    for window in coverage.get(domain, []):
        a, b = _date(window['from']), _date(window['to'])
        if a > b:
            raise ValueError('reversed coverage interval')
        scope = window.get('item_scope')
        if scope != 'ALL_PRODUCTS' and (not isinstance(scope, list) or item not in scope):
            continue
        if (window.get('status') == 'COMPLETE' and window.get('proof')
                and window.get('domain_scope') == 'ALL_' + domain.upper() + '_USE_EVENTS'):
            intervals.append((a, b))
    cursor = start
    for a, b in sorted(intervals):
        if b < cursor:
            continue
        if a > cursor:
            break
        if b >= end:
            return 'COMPLETE'
        cursor = b + timedelta(days=1)
    return 'PARTIAL_OR_UNPROVEN'


def commercial_purpose_for_period(ItemCode, period_from, period_to, *, evidence, coverage,
                                  lookback_days=0):
    """Classify observed use within an explicit closed date interval.

    An explicitly requested lookback extends the evaluated interval. The strict
    requested-period result is returned separately and never replaced silently.
    Exclusivity requires proven coverage of the opposite whole usage domain.
    """
    start, end = _date(period_from), _date(period_to)
    if start > end:
        raise ValueError('period_from exceeds period_to')
    if isinstance(lookback_days, bool) or not isinstance(lookback_days, int) or lookback_days < 0:
        raise ValueError('lookback_days must be a nonnegative integer')
    effective_start = start - timedelta(days=lookback_days)
    dates = evidence_dates(evidence)

    def classify(a, b):
        selected = {d: [v for v in dates[d] if a <= v <= b] for d in DOMAINS}
        c, i = bool(selected['commercial']), bool(selected['internal'])
        cc = _coverage(ItemCode, 'commercial', coverage, a, b)
        ic = _coverage(ItemCode, 'internal', coverage, a, b)
        if c and i:
            purpose, reason = 'MIXED', 'BOTH_POSITIVE_USES_WITHIN_EVALUATED_INTERVAL'
        elif c and ic == 'COMPLETE':
            purpose, reason = 'COMMERCIAL_ONLY', 'COMMERCIAL_USE_AND_PROVEN_NO_INTERNAL_USE'
        elif i and cc == 'COMPLETE':
            purpose, reason = 'INTERNAL_ONLY', 'INTERNAL_USE_AND_PROVEN_NO_COMMERCIAL_USE'
        else:
            purpose = 'UNKNOWN'
            reason = ('COMMERCIAL_EVIDENCE_ONLY_INTERNAL_COVERAGE_UNPROVEN' if c else
                      'INTERNAL_EVIDENCE_ONLY_COMMERCIAL_COVERAGE_UNPROVEN' if i else
                      'NO_POSITIVE_USE_WITHIN_EVALUATED_INTERVAL')
        return {'commercial_purpose': purpose, 'reason': reason,
                'commercial_evidence': c, 'internal_use_evidence': i,
                'commercial_evidence_dates': [str(v) for v in selected['commercial']],
                'internal_use_evidence_dates': [str(v) for v in selected['internal']],
                'sales_coverage_status': cc, 'production_coverage_status': ic}

    strict, effective = classify(start, end), classify(effective_start, end)
    return {'ItemCode': ItemCode, 'contract_version': VERSION, **effective,
            'commercial_purpose_without_lookback': strict['commercial_purpose'],
            'requested_period_evidence': strict,
            'historical_usage_profile': historical_usage_profile(evidence)['historical_usage_profile'],
            'provenance': {'period_from': str(start), 'period_to': str(end),
                           'lookback_days': lookback_days, 'evaluation_from': str(effective_start),
                           'evaluation_to': str(end), 'coverage': coverage,
                           'absence_requires_complete_opposite_domain': True}}


def commercial_query_eligible(result):
    """A sale within the requested period is evaluable even with unknown purpose.

    Historical commerce, implicit lookback, intent flags and BOM alone do not
    confer period eligibility. Exclusivity is never required for observed sales.
    """
    return (result['requested_period_evidence']['commercial_evidence'] or
            result['commercial_purpose_without_lookback'] in {'COMMERCIAL_ONLY', 'MIXED'})


class TemporalPurposeReader:
    """Read the explicit sealed component; no CURRENT/latest fallback or scans."""
    def __init__(self, component: Mapping):
        if component.get('stable_contract', {}).get('contracts', {}).get(CONTRACT, {}).get('version') != VERSION:
            raise ValueError('explicit temporal contract unavailable or unsupported')
        self.component = component

    def commercial_purpose_for_period(self, ItemCode, period_from, period_to, *, lookback_days=0):
        relation = dataset_relation(self.component, 'product_purpose')
        with open_safe_duckdb(profile=DuckDBSafetyProfile(threads=2, memory_limit='1GB')) as c:
            rows = c.execute('SELECT temporal_usage_dates,temporal_usage_coverage FROM '+relation+
                             ' WHERE item_code=?', [ItemCode]).fetchall()
        if len(rows) != 1:
            raise ValueError('one temporal evidence row per ItemCode required')
        return commercial_purpose_for_period(ItemCode, period_from, period_to,
                                             evidence=json.loads(rows[0][0]), coverage=json.loads(rows[0][1]),
                                             lookback_days=lookback_days)
