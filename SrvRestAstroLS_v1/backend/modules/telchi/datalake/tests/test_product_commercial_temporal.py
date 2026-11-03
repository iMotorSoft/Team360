"""Coverage, period boundaries and compatibility regression for usage contract."""
import json
from pathlib import Path

import pytest

from modules.telchi.datalake.product_commercial_temporal import (
    commercial_purpose_for_period, commercial_query_eligible, historical_usage_profile,
    TemporalPurposeReader,
)


def coverage(domain, start='2026-01-01', end='2026-09-24', status='COMPLETE', scope='ALL_PRODUCTS'):
    return {'from':start,'to':end,'status':status,'proof':'verified-source-coverage',
            'domain_scope':'ALL_'+domain.upper()+'_USE_EVENTS','item_scope':scope}


def classify(commercial=(), internal=(), cov=None, lookback=0):
    return commercial_purpose_for_period('A','2026-01-01','2026-09-24',
        evidence={'commercial':list(commercial),'internal':list(internal)},
        coverage=cov or {},lookback_days=lookback)


def test_same_period_mixed_does_not_require_same_day_or_complete_absence_coverage():
    result=classify(['2026-01-01'],['2026-09-24'])
    assert result['commercial_purpose']=='MIXED'
    assert result['sales_coverage_status']=='PARTIAL_OR_UNPROVEN'


def test_history_is_not_mixed_for_current_period():
    result=classify(['2023-03-01'],['2026-08-01'])
    assert result['historical_usage_profile']=='MIXED'
    assert result['commercial_purpose']=='UNKNOWN'
    assert not result['commercial_evidence'] and result['internal_use_evidence']
    assert not commercial_query_eligible(result)


def test_only_commerce_with_partial_internal_coverage_is_unknown_but_evaluable():
    result=classify(['2026-04-01'],[], {'internal':[coverage('internal',status='PARTIAL')]})
    assert result['commercial_purpose']=='UNKNOWN'
    assert commercial_query_eligible(result)


def test_full_internal_domain_coverage_allows_commercial_only():
    result=classify(['2026-04-01'],[], {'internal':[coverage('internal')]})
    assert result['commercial_purpose']=='COMMERCIAL_ONLY'


def test_full_commercial_domain_coverage_allows_internal_only():
    result=classify([],['2026-04-01'], {'commercial':[coverage('commercial')]})
    assert result['commercial_purpose']=='INTERNAL_ONLY'
    assert not commercial_query_eligible(result)


def test_internal_positive_partial_commerce_is_unknown():
    result=classify([],['2026-04-01'])
    assert result['commercial_purpose']=='UNKNOWN'


def test_full_coverage_without_any_events_preserves_unknown():
    assert classify(cov={d:[coverage(d)] for d in ['commercial','internal']})['commercial_purpose']=='UNKNOWN'


def test_lookback_is_explicit_and_strict_period_result_survives():
    result=classify(['2025-12-31'],['2026-02-01'],lookback=365)
    assert result['commercial_purpose']=='MIXED'
    assert result['commercial_purpose_without_lookback']=='UNKNOWN'
    assert result['provenance']['evaluation_from']=='2025-01-01'
    assert result['provenance']['lookback_days']==365
    assert not commercial_query_eligible(result)


def test_lookback_boundary_is_inclusive_and_not_universal():
    assert classify(['2024-12-31'],['2026-03-01'],lookback=365)['commercial_purpose']=='UNKNOWN'
    assert classify(['2025-01-01'],['2026-03-01'],lookback=365)['commercial_purpose']=='MIXED'
    assert classify(['2025-01-01'],['2026-03-01'])['commercial_purpose']=='UNKNOWN'


def test_disjoint_coverage_windows_do_not_hide_holes():
    windows=[coverage('internal',end='2026-03-31'),coverage('internal',start='2026-05-01')]
    assert classify(['2026-04-01'],cov={'internal':windows})['commercial_purpose']=='UNKNOWN'


def test_adjacent_complete_intervals_cover_whole_period():
    windows=[coverage('internal',end='2026-03-31'),coverage('internal',start='2026-04-01')]
    assert classify(['2026-04-01'],cov={'internal':windows})['commercial_purpose']=='COMMERCIAL_ONLY'


def test_coverage_proof_and_whole_domain_scope_are_required():
    window=coverage('internal');window['proof']=None
    assert classify(['2026-04-01'],cov={'internal':[window]})['commercial_purpose']=='UNKNOWN'
    window=coverage('internal');window['domain_scope']='PRODUCTION_ISSUES_ONLY'
    assert classify(['2026-04-01'],cov={'internal':[window]})['commercial_purpose']=='UNKNOWN'


def test_coverage_is_scoped_to_item_and_period():
    assert classify(['2026-04-01'],cov={'internal':[coverage('internal',scope=['B'])]})['commercial_purpose']=='UNKNOWN'
    assert classify(['2026-04-01'],cov={'internal':[coverage('internal',end='2026-09-23')]})['commercial_purpose']=='UNKNOWN'


def test_historical_evidence_only_does_not_claim_exclusivity():
    result=historical_usage_profile({'commercial':['2023-01-01'],'internal':[]})
    assert result['historical_usage_profile']=='COMMERCIAL_EVIDENCE_ONLY'
    assert result['commercial_evidence_first_date']==result['commercial_evidence_last_date']=='2023-01-01'
    assert result['internal_use_evidence_first_date'] is None


@pytest.mark.parametrize('lookback', [-1,True,0.5,'365'])
def test_invalid_lookback_rejected(lookback):
    with pytest.raises(ValueError):classify(lookback=lookback)


def test_invalid_or_duplicate_evidence_fails_closed():
    with pytest.raises(ValueError,match='fanout'):
        classify(['2026-01-01','2026-01-01'])
    with pytest.raises(ValueError):classify(['not-a-date'])
    with pytest.raises(ValueError):
        commercial_purpose_for_period('A','2026-02-01','2026-01-01',evidence={'commercial':[],'internal':[]},coverage={})


def test_reader_requires_explicit_contract_and_has_no_fallback():
    with pytest.raises(ValueError,match='contract'):
        TemporalPurposeReader({'stable_contract':{'contracts':{}}})


def test_real_reclassification_gold_and_replay_when_materialized():
    root=Path(__file__).resolve().parents[6]/'data/reports/telchi/temporal_commercial_purpose_v1'
    if not (root/'report.json').exists():pytest.skip('real gate not yet materialized')
    report=json.loads((root/'report.json').read_text())
    cases=json.loads((root/'mixed_24_reclassification.json').read_text())
    gold=json.loads((root/'gold_cases.json').read_text())
    replay=json.loads((root/'replay.json').read_text())
    assert len(cases)==len({r['ItemCode'] for r in cases})==24
    assert sum(report[k] for k in ['MIXED_WITHIN_2026','MIXED_WITH_LOOKBACK','HISTORICALLY_MIXED_ONLY','INSUFFICIENT_TEMPORAL_EVIDENCE'])==24
    assert all(not r['period_2026']['commercial_evidence'] for r in cases)
    assert gold['L00002']['period']['commercial_purpose']=='MIXED'
    assert gold['L02475']['period']['internal_use_evidence'] and gold['L02475']['period']['commercial_purpose']!='MIXED'
    assert gold['L00954']['period']['commercial_evidence'] and not gold['L00954']['period']['internal_use_evidence']
    for item in ['L00759','L00761']:
        assert gold[item]['legacy_purpose']=='INTERNAL_ONLY'
        assert not gold[item]['period']['commercial_evidence']
        assert not commercial_query_eligible(gold[item]['period'])
    assert report['FINAL_REPLAY_PRODUCTS']==834+len(replay['added'])-len(replay['removed'])
    assert all(r['commercial_evidence'] for r in replay['ranking']+replay['zero_sales'])
    assert report['SOURCE_GAPS_REQUIRING_NEW_INGESTION']==422 and report['TRUE_BUSINESS_UNKNOWN']==384
    assert report['ANTI_FANOUT']==report['CONSUMER_COMPATIBILITY']=='PASS'
