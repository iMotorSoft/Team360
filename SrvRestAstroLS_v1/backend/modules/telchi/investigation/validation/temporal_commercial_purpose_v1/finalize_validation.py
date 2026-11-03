"""Seal verified validation state; never promote or change CURRENT."""
import json
from datetime import datetime, timezone
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.product_commercial_semantics import COMPONENT, dataset_relation, row_digest
from modules.telchi.datalake.product_commercial_temporal import TemporalPurposeReader, commercial_query_eligible, CONTRACT
from modules.telchi.datalake.raw import file_hash
from .run_gate import OUTPUT, PREVIOUS, INPUT, EXPECTED, START, END, ROOT, records, save


def main():
    # Call only after focalized pytest, all LAT gates and diff review succeed.
    report=json.loads((OUTPUT/'report.json').read_text())
    assert report['TEST_FAILURES']==0 and report['LAT_CHECK']=='PASS' and report['GIT_DIFF_CHECK']=='PASS'
    co=DuckLakeConnector();store=FoundationPublicationStore(co.session)
    assert store.current_pointer()==EXPECTED
    prior=store.get(INPUT);candidate=store.get(report['OUTPUT_CANDIDATE'])
    assert prior.status=='VALIDATING' and candidate.status in {'VALIDATING','READY_TO_COMMIT'}
    old=validate_manifest(store,prior)[COMPONENT]
    components=validate_manifest(store,candidate);component=components[COMPONENT]
    assert component['datasets']['product_sales_uom']==old['datasets']['product_sales_uom']
    with co.session(read_only=True) as c:
        c.execute('SET threads=2');c.execute("SET memory_limit='1GB'")
        previous=records(c,'SELECT * FROM '+dataset_relation(old,'product_purpose'))
        current=records(c,'SELECT * FROM '+dataset_relation(component,'product_purpose'))
        assert row_digest(current)==component['datasets']['product_purpose']['logical_hash']
        original_fields=list(previous[0])
        assert row_digest([{k:r[k] for k in original_fields} for r in current])==old['datasets']['product_purpose']['logical_hash']
    pmap={r['item_code']:r for r in current}
    reader=TemporalPurposeReader(component)
    cases=json.loads((OUTPUT/'mixed_24_reclassification.json').read_text())
    assert len(cases)==24
    for case in cases:
        assert reader.commercial_purpose_for_period(case['ItemCode'],START,END)==case['period_2026']
        assert reader.commercial_purpose_for_period(case['ItemCode'],START,END,lookback_days=365)==case['explicit_365_day_lookback']
    gold=json.loads((OUTPUT/'gold_cases.json').read_text())
    for item,case in gold.items():
        assert reader.commercial_purpose_for_period(item,START,END)==case['period']
        case['SellItem']=pmap[item]['sap_sell_item']
    for item in ['L00759','L00761']:
        assert gold[item]['SellItem']=='N' and gold[item]['legacy_purpose']=='INTERNAL_ONLY'
        assert not commercial_query_eligible(gold[item]['period'])
    save('gold_cases',gold)
    old_report=json.loads((PREVIOUS/'report.json').read_text())
    assert report['SOURCE_GAPS_REQUIRING_NEW_INGESTION']==old_report['SOURCE_GAPS_REQUIRING_NEW_INGESTION']==422
    assert report['TRUE_BUSINESS_UNKNOWN']==old_report['TRUE_BUSINESS_UNKNOWN']==384
    provenance=component['stable_contract']['source_provenance'][CONTRACT]
    assert provenance['evidence_sha256']==file_hash(OUTPUT/'dated_evidence.json')
    assert provenance['previous_report_sha256']==file_hash(PREVIOUS/'report.json')
    lock='temporal-purpose-final-validation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    store.acquire_run_lock(lock,owner='temporal_commercial_purpose_v1')
    try:
        assert store.current_pointer()==EXPECTED and store.get(candidate.foundation_publication_id).status==candidate.status
        store.update_components(candidate.foundation_publication_id,{},validation_status='PASS_TEMPORAL_PURPOSE_WITH_DECLARED_SOURCE_GAPS')
        store.set_status(candidate.foundation_publication_id,'READY_TO_COMMIT',validated_at=datetime.now(timezone.utc).isoformat())
        assert store.current_pointer()==EXPECTED
        assert validate_manifest(store,store.get(candidate.foundation_publication_id))==components
    finally:
        store.release_run_lock(lock)
    report.update(CANDIDATE_STATE=store.get(candidate.foundation_publication_id).status,PROMOTION_ELIGIBLE='YES',
        FINAL_PINNED_VERIFICATION='PASS',code_sha256={str(p.relative_to(ROOT)):file_hash(p) for p in [
            ROOT/'SrvRestAstroLS_v1/backend/modules/telchi/datalake/product_commercial_temporal.py',
            ROOT/'SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/temporal_commercial_purpose_v1/run_gate.py']})
    save('report',report)
    save('source_gap_validation_assessment',{'GATE':'TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_SOURCE_GAP_VALIDATION_V1_PASS',
        'CURRENT_FOUNDATION':EXPECTED,'INPUT_CANDIDATE':INPUT,'OUTPUT_CANDIDATE':candidate.foundation_publication_id,
        'semantics_blocker_closed':True,'source_gap_counts_unchanged':True,'SOURCE_GAPS_REQUIRING_NEW_INGESTION':422,
        'TRUE_BUSINESS_UNKNOWN':384,'validation_evidence':str(OUTPUT/'report.json'),
        'scope':'Superseding validation assessment only; previous sealed reports and input candidate untouched',
        'PROMOTION_EXECUTED':'NO','REQUIRES_SEPARATE_PROMOTION_GATE':True})
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
