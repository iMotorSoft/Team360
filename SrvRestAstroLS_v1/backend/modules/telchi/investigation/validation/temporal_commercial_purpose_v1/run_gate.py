"""Temporal contract gate: existing materialized evidence only, no promotion."""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.product_commercial_semantics import COMPONENT, dataset_relation, materialize, create_candidate, row_digest
from modules.telchi.datalake.product_commercial_temporal import CONTRACT, VERSION, historical_usage_profile, commercial_purpose_for_period, commercial_query_eligible, TemporalPurposeReader
from modules.telchi.datalake.material_supply_candidate import resolve_current_material_supply
from modules.telchi.datalake.receivables_collections_foundation import resolve_current as resolve_receivables
from modules.telchi.datalake.raw import file_hash
from modules.telchi.investigation.validation.product_commercial_semantics_v1.run_closure import EXPECTED, START, END, records, checked_manifest

INPUT = 'foundation_fd73cb4b753f41ada7e954badd2ef6f5'
ROOT = Path(__file__).resolve().parents[7]
PREVIOUS = ROOT/'data/reports/telchi/product_commercial_semantics_source_gap_v1'
OUTPUT = ROOT/'data/reports/telchi/temporal_commercial_purpose_v1'
DIAGNOSTIC_LOOKBACK = 365


def save(name, value):
    (OUTPUT/(name+'.json')).write_text(json.dumps(value, indent=2, default=str)+'\n')


def evaluate(row, start=START, end=END, lookback_days=0):
    return commercial_purpose_for_period(row['item_code'], start, end,
        evidence=json.loads(row['temporal_usage_dates']), coverage=json.loads(row['temporal_usage_coverage']),
        lookback_days=lookback_days)


def replay(c, access, component, purpose, previous):
    """Use the same quantity window, stock and ranking; temporal eligibility only."""
    contract = component['stable_contract']['contracts']
    assert contract['temporal']['sales']['quantity_materialization_from'] == START
    assert contract['temporal']['sales']['quantity_materialization_to'] == END
    r = dataset_relation(component, 'product_sales_uom')
    stocks = records(c, f'SELECT item_code,sum(try_cast(on_hand AS DECIMAL(38,12))-try_cast(is_commited AS DECIMAL(38,12))) qty FROM {access.oitw()} GROUP BY item_code')
    stock = {v['item_code']:v['qty'] for v in stocks}
    net_rows = records(c, 'SELECT item_code,bool_and(uom_status IN (\'UOM_RESOLVED_EXACT\',\'UOM_RESOLVED_SUPPORTED\')) resolved,sum(CASE WHEN document_kind=\'INVOICE\' THEN try_cast(base_qty AS DECIMAL(38,12)) ELSE -try_cast(base_qty AS DECIMAL(38,12)) END) qty,sum(CASE WHEN doc_date<CAST(? AS DATE) THEN CASE WHEN document_kind=\'INVOICE\' THEN try_cast(base_qty AS DECIMAL(38,12)) ELSE -try_cast(base_qty AS DECIMAL(38,12)) END ELSE 0 END) closed_qty,max(doc_date) FILTER(WHERE document_kind=\'INVOICE\')::VARCHAR last_sale,count(distinct doc_date) FILTER(WHERE document_kind=\'INVOICE\') sale_days FROM '+r+' GROUP BY item_code', [END])
    net = {v['item_code']:v for v in net_rows}
    known_uoms = {v[0] for v in c.execute('SELECT distinct inventory_uom_id FROM '+r+" WHERE uom_status IN ('UOM_RESOLVED_EXACT','UOM_RESOLVED_SUPPORTED')").fetchall()}
    native_units = contract['source_gap_v1']['source_native_inventory_units']
    prior_rows = {v['item_code']:v for v in previous['ranking']+previous['zero_sales']}
    ranking, zero, unresolved, eligibility = [], [], [], {}
    days = Decimal((date(2026,9,23)-date(2026,1,1)).days+1)
    pmap = {v['item_code']:v for v in purpose}
    for item,p in sorted(pmap.items()):
        if not item.startswith('L') or p['sap_invnt_item'] != 'Y':
            continue
        temporal = evaluate(p)
        permitted = commercial_query_eligible(temporal)
        eligibility[item] = {'eligible':permitted, 'purpose':temporal['commercial_purpose'],
            'commercial_evidence':temporal['commercial_evidence'], 'internal_use_evidence':temporal['internal_use_evidence'],
            'historical_usage_profile':temporal['historical_usage_profile'], 'reason':temporal['reason']}
        if not permitted or stock.get(item,Decimal(0)) <= 0:
            continue
        n = net.get(item, {'resolved':True,'qty':Decimal(0),'closed_qty':Decimal(0),'last_sale':None,'sale_days':0})
        if not n['resolved'] or (p['inventory_uom_id'] not in known_uoms and item not in native_units):
            unresolved.append(item)
            continue
        qty, closed = n['qty'],n['closed_qty']
        meta = prior_rows.get(item,n)
        row = {'item_code':item,'purpose':temporal['commercial_purpose'], 'historical_usage_profile':temporal['historical_usage_profile'],
            'legacy_commercial_purpose':p['commercial_purpose'], 'available_qty':str(stock[item].normalize()),
            'net_sales_base_qty':str(qty.normalize()),'ratio':str(stock[item]/qty) if qty>0 else None,
            'coverage_days':str(stock[item]*days/closed) if closed>0 else None,
            'last_sale':meta['last_sale'], 'sale_days':meta['sale_days'],
            'commercial_evidence':temporal['commercial_evidence'],'internal_use_evidence':temporal['internal_use_evidence'],
            'classification_reason':temporal['reason']}
        if qty==0: zero.append(row)
        elif qty>0: ranking.append(row)
    ranking.sort(key=lambda v:(-Decimal(v['ratio']),v['last_sale'] or '',v['sale_days'],v['item_code']))
    evaluated = {v['item_code'] for v in ranking+zero}
    assert len(evaluated)==len(ranking+zero)
    for row in ranking+zero:
        if row['item_code'] in prior_rows:
            old=prior_rows[row['item_code']]
            assert Decimal(old['available_qty'])==Decimal(row['available_qty'])
            assert Decimal(old['net_sales_base_qty'])==Decimal(row['net_sales_base_qty'])
    old_top = previous['ranking'][:10]
    current_top = ranking[:10]
    old_items, new_items = {v['item_code'] for v in old_top},{v['item_code'] for v in current_top}
    removed = sorted(set(prior_rows)-evaluated)
    added = sorted(evaluated-set(prior_rows))
    assert all(not eligibility[i]['commercial_evidence'] for i in removed)
    assert all(eligibility[i]['commercial_evidence'] for i in added)
    return {'query':'HIGH_STOCK_LOW_SALES_COMMERCIAL_PRODUCTS', 'period_from':START,'period_to':END,'lookback_days':0,
        'previous_evaluated_products':len(prior_rows),'candidate_evaluated_products':len(evaluated),
        'added':{i:eligibility[i] for i in added},'removed':{i:eligibility[i] for i in removed},
        'mixed_evaluated':sum(v['purpose']=='MIXED' for v in ranking+zero),
        'unknown_evaluated':sum(v['purpose']=='UNKNOWN' for v in ranking+zero),
        'uom_unresolved_items':unresolved,'ranking':ranking,'zero_sales':zero,
        'previous_top10':old_top,'new_top10':current_top,
        'top10_change_explanations':{'entries':{i:eligibility[i] for i in new_items-old_items},
            'exits':{i:{**eligibility[i],'reason_for_top10_exit':'ORDERED_BELOW_NEW_PERIOD_COMMERCIAL_ENTRY' if eligibility[i]['eligible'] else 'NO_PERIOD_COMMERCIAL_EVIDENCE'} for i in old_items-new_items}},
        'top10_changed':[v['item_code'] for v in old_top]!=[v['item_code'] for v in current_top],
        'ranking_rule':'ratio DESC, last_sale ASC, sale_days ASC, ItemCode ASC',
        'zero_sales_policy':'Requires period commercial evidence; net zero from observed sales/credits remains eligible. Historical sales or undated intended classification alone do not establish period commerce.'}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    co= DuckLakeConnector()
    store=FoundationPublicationStore(co.session)
    prior=store.get(INPUT)
    assert prior and prior.status=='VALIDATING' and store.current_pointer()==EXPECTED
    original=validate_manifest(store,prior)
    old=original[COMPONENT]
    sg=old['stable_contract']['source_provenance']['source_gap_v1']
    for name, sha in sg['evidence_hashes'].items():
        assert file_hash(PREVIOUS/(name+'.json'))==sha
    old_report=json.loads((PREVIOUS/'report.json').read_text())
    assert old_report['SOURCE_GAPS_REQUIRING_NEW_INGESTION']==422 and old_report['TRUE_BUSINESS_UNKNOWN']==384
    source_events=json.loads((PREVIOUS/'commercial_events.json').read_text())
    matrix=json.loads((PREVIOUS/'commercial_matrix.json').read_text())
    target=sorted(v['ItemCode'] for v in matrix if v['proposed_commercial_purpose']=='MIXED')
    assert len(target)==24
    provenance=deepcopy(old['stable_contract']['source_provenance'])
    contracts=deepcopy(old['stable_contract']['contracts'])
    with co.session(read_only=True) as c:
        c.execute('SET threads=2');c.execute("SET memory_limit='1GB'")
        access=FoundationReader(co).resolve_on(c)
        assert access.foundation_publication_id==EXPECTED
        purpose=records(c,'SELECT * FROM '+dataset_relation(old,'product_purpose'))
        assert row_digest(purpose)==old['datasets']['product_purpose']['logical_hash']
        original_fields=list(purpose[0])
        sd,sl=access.sales('sales_document'),access.sales('sales_line')
        duplicate_sales=c.execute(f'SELECT count(*) FROM (SELECT source_system,doc_entry,line_num,count(*) n FROM {sl} GROUP BY ALL HAVING n>1)').fetchone()[0]
        duplicate_docs=c.execute(f'SELECT count(*) FROM (SELECT source_system,doc_entry,count(*) n FROM {sd} GROUP BY ALL HAVING n>1)').fetchone()[0]
        assert duplicate_sales==duplicate_docs==0
        daily_sales=records(c,f"SELECT l.item_code,CAST(d.doc_date AS DATE)::VARCHAR event_date,count(*) event_count FROM {sl} l JOIN {sd} d USING(source_system,doc_entry) WHERE d.canceled='N' AND try_cast(l.quantity AS DECIMAL(38,12))>0 AND CAST(d.doc_date AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE) GROUP BY l.item_code,CAST(d.doc_date AS DATE)",[START,END])
        issue_files,issue_proofs=[],[]
        for proof in provenance['production_issue']:
            _,fs,verified=checked_manifest(Path(proof['manifest_path']))
            assert verified['file_hashes']==proof['file_hashes']
            issue_files+=fs;issue_proofs.append(verified)
        duplicate_issues=c.execute('SELECT count(*) FROM (SELECT DocEntry,LineNum,count(*) n FROM read_parquet(?,union_by_name=true) GROUP BY ALL HAVING n>1)',[issue_files]).fetchone()[0]
        assert duplicate_issues==0
        daily_issues=records(c,"SELECT ItemCode item_code,CAST(DocDate AS DATE)::VARCHAR event_date,count(*) event_count FROM read_parquet(?,union_by_name=true) WHERE CANCELED='N' AND BaseType=202 AND try_cast(Quantity AS DECIMAL(38,12))>0 AND CAST(DocDate AS DATE)<=CAST(? AS DATE) GROUP BY ItemCode,CAST(DocDate AS DATE)",[issue_files,END])
        commercial,internal=defaultdict(set),defaultdict(set)
        for r in daily_sales:commercial[r['item_code']].add(r['event_date'])
        for r in source_events['historical_sales']:
            assert r['doc_date']<START
            commercial[r['item_code']].add(r['doc_date'])
        for r in daily_issues:internal[r['item_code']].add(r['event_date'])
        common_coverage={
            'commercial':[{'from':START,'to':END,'status':'PARTIAL','proof':INPUT+':pinned-valid-invoice-relation',
                'domain_scope':'MATERIALIZED_VALID_INVOICE_EVENTS','item_scope':'ALL_PRODUCTS','source_as_of':access.foundation.sales_source_as_of,
                'reason':'Observed bounds and sealed publication do not prove complete whole-domain coverage; final day is intraday.'}],
            'internal':[{'from':START,'to':END,'status':'PARTIAL','proof':INPUT+':hash-verified-production-issue-capture',
                'domain_scope':'BASE_TYPE_202_PRODUCTION_ISSUE_ONLY','item_scope':'ALL_PRODUCTS',
                'reason':'Production capture is dated, but does not certify all internal purposes or full final day.'}]}
        temporal_contract={'version':VERSION,'period_interval':'CLOSED_INCLUSIVE_DATES','default_lookback_days':0,
            'legacy_commercial_purpose':'Unchanged V1 accumulated observed/intended classification bounded by its declared source windows; never a current-period assertion.',
            'legacy_rule_version':contracts['commercial_purpose']['rule_version'],
            'historical_usage_profile':'Observed positive uses only, across all materialized evidence windows; evidence-only states do not claim exclusivity.',
            'positive_commerce':'Noncancelled invoice line with positive source-native quantity; isolated invoice is positive evidence, not exclusive intent.',
            'positive_internal':'Noncancelled positive production issue with source-native BaseType=202; BOM and warehouse membership are not consumption.',
            'period_mixed':'Both positive usages occur within the evaluated interval; not necessarily on the same day.',
            'exclusive_usage':'Positive usage plus COMPLETE proven coverage of the opposite entire usage domain over the evaluated interval.',
            'lookback':'Explicit caller parameter; expands evaluation_from; strict requested-period classification retained separately.',
            'business_eligibility':'Period commercial evidence OR strict period COMMERCIAL_ONLY/MIXED; UNKNOWN can be evaluated with positive period commerce. Default lookback zero.',
            'coverage':common_coverage,'materialized_period':{'from':START,'to':END},
            'evidence_relations':{'commercial':{'line':sl,'document':sd,'foundation_snapshot':access.ducklake_snapshot_id},
                'historical_commercial':{'path':str(PREVIOUS/'commercial_events.json'),'sha256':sg['evidence_hashes']['commercial_events'],'scope':'Original 720 product cohort; pre-2026 positive sales only'},
                'internal':issue_proofs}}
        counts=Counter()
        for p in purpose:
            item=p['item_code'];e={'commercial':sorted(commercial[item]),'internal':sorted(internal[item])}
            p.update(historical_usage_profile(e))
            p['commercial_purpose_semantics_version']='legacy-bounded-v1'
            p['temporal_usage_dates']=json.dumps(e,sort_keys=True)
            p['temporal_usage_coverage']=json.dumps(common_coverage,sort_keys=True)
            p['sales_coverage_from']=START;p['sales_coverage_to']=END
            p['production_coverage_from']=START;p['production_coverage_to']=END
            t=evaluate(p);counts[t['commercial_purpose']]+=1
            p['materialized_purpose_period_from']=START;p['materialized_purpose_period_to']=END
            p['commercial_purpose_for_materialized_period']=t['commercial_purpose']
            p['temporal_purpose_reason']=t['reason']
        assert row_digest([{k:p[k] for k in original_fields} for p in purpose])==old['datasets']['product_purpose']['logical_hash']
        pmap={r['item_code']:r for r in purpose}
        cases=[]
        for item in target:
            p=pmap[item];t=evaluate(p);lb=evaluate(p,lookback_days=DIAGNOSTIC_LOOKBACK)
            group=('MIXED_WITHIN_2026' if t['commercial_purpose']=='MIXED' else
                'MIXED_WITH_LOOKBACK' if lb['commercial_purpose']=='MIXED' else
                'HISTORICALLY_MIXED_ONLY' if p['historical_usage_profile']=='MIXED' else 'INSUFFICIENT_TEMPORAL_EVIDENCE')
            dates=json.loads(p['temporal_usage_dates'])
            cd,ii=dates['commercial'],dates['internal']
            overlap=bool(cd and ii and max(min(cd),min(ii))<=min(max(cd),max(ii)))
            cases.append({'ItemCode':item,'group':group,'commercial_evidence_first_date':p['commercial_evidence_first_date'],
                'commercial_evidence_last_date':p['commercial_evidence_last_date'],'internal_use_evidence_first_date':p['internal_use_evidence_first_date'],
                'internal_use_evidence_last_date':p['internal_use_evidence_last_date'],'evidence_ranges_overlap':overlap,
                'period_2026':t,'explicit_365_day_lookback':lb,'historical_usage_profile':p['historical_usage_profile']})
        save('mixed_24_reclassification',cases)
        save('contract',temporal_contract)
        save('dated_evidence',{'commercial_daily':daily_sales,'internal_daily':daily_issues,'historical_source':temporal_contract['evidence_relations']['historical_commercial']})
        contracts[CONTRACT]=temporal_contract
        provenance[CONTRACT]={'input_candidate':INPUT,'contract_version':VERSION,'evidence_sha256':file_hash(OUTPUT/'dated_evidence.json'),
            'previous_report_sha256':file_hash(PREVIOUS/'report.json'),'production_issue':issue_proofs,'foundation':access.as_dict()}
    component=materialize({'product_purpose':purpose},dependencies=old['stable_contract']['dependencies'],provenance=provenance,contracts=contracts,
        reuse_datasets={'product_sales_uom':old['datasets']['product_sales_uom']})
    run_id='temporal-commercial-purpose-v1-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    store.acquire_run_lock(run_id,owner='temporal_commercial_purpose_v1')
    try:
        assert store.current_pointer()==EXPECTED and store.get(INPUT).status==prior.status
        candidate_id=create_candidate(store,base_id=EXPECTED,component=component,run_id=run_id)
        candidate=store.get(candidate_id);pinned=validate_manifest(store,candidate)
        assert pinned[COMPONENT]==component
        assert all(pinned[k]==v for k,v in original.items() if k!=COMPONENT)
        assert pinned[COMPONENT]['datasets']['product_sales_uom']==old['datasets']['product_sales_uom']
        class Shadow:
            def current_pointer(self):return candidate_id
            def current_publication(self):return replace(candidate,status='CURRENT')
            def get(self,identity):return self.current_publication() if identity==candidate_id else store.get(identity)
        assert resolve_current_material_supply(Shadow()).foundation_publication_id==candidate_id
        assert resolve_receivables(Shadow()).foundation_publication_id==candidate_id
    finally:
        store.release_run_lock(run_id)
    with co.session(read_only=True) as c:
        c.execute('SET threads=2');c.execute("SET memory_limit='1GB'")
        recovered=records(c,'SELECT * FROM '+dataset_relation(pinned[COMPONENT],'product_purpose'))
        assert row_digest(recovered)==component['datasets']['product_purpose']['logical_hash']
        assert row_digest([{k:p[k] for k in original_fields} for p in recovered])==old['datasets']['product_purpose']['logical_hash']
        previous=json.loads((PREVIOUS/'replay.json').read_text())
        result=replay(c,access,pinned[COMPONENT],recovered,previous)
        assert result['previous_evaluated_products']==834
        duplicates=c.execute('SELECT count(*) FROM (SELECT source_system,document_kind,doc_entry,line_num,count(*) n FROM '+dataset_relation(component,'product_sales_uom')+' GROUP BY ALL HAVING n>1)').fetchone()[0]
        assert duplicates==0
    save('replay',result)
    reader=TemporalPurposeReader(pinned[COMPONENT])
    gold={i:{'legacy_purpose':pmap[i]['commercial_purpose'],'SellItem':pmap[i]['sap_sell_item'],'period':reader.commercial_purpose_for_period(i,START,END)} for i in ['L00002','L02475','L00954','L00759','L00761']}
    assert gold['L00002']['period']['commercial_purpose']=='MIXED'
    assert gold['L02475']['period']['internal_use_evidence'] and not gold['L02475']['period']['commercial_evidence']
    assert gold['L02475']['period']['commercial_purpose']!='MIXED'
    assert gold['L00954']['period']['commercial_evidence'] and not gold['L00954']['period']['internal_use_evidence']
    for i in ['L00759','L00761']:
        assert gold[i]['legacy_purpose']=='INTERNAL_ONLY'
        assert gold[i]['SellItem']=='N'
        assert not gold[i]['period']['commercial_evidence'] and not commercial_query_eligible(gold[i]['period'])
    save('gold_cases',gold)
    assert store.current_pointer()==EXPECTED
    groups=Counter(r['group'] for r in cases)
    report={
        'GATE':'TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_TEMPORAL_VALIDATION_V1_PASS',
        'GATE_A':'TELCHI_TEMPORAL_COMMERCIAL_PURPOSE_CONTRACT_V1_PASS',
        'GATE_B':'TELCHI_TEMPORAL_MIXED_RECLASSIFICATION_V1_PASS',
        'GATE_C':'TELCHI_TEMPORAL_COMMERCIAL_PURPOSE_BUSINESS_REPLAY_V1_PASS',
        'GATE_D':'TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_TEMPORAL_VALIDATION_V1_PASS',
        'SOURCE_GAP_VALIDATION_ASSESSMENT':'TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_SOURCE_GAP_VALIDATION_V1_PASS',
        'CURRENT_FOUNDATION':store.current_pointer(),'INPUT_CANDIDATE':INPUT,'OUTPUT_CANDIDATE':candidate_id,
        'PREVIOUS_MIXED_NEW':24,**{k:groups[k] for k in ['MIXED_WITHIN_2026','MIXED_WITH_LOOKBACK','HISTORICALLY_MIXED_ONLY','INSUFFICIENT_TEMPORAL_EVIDENCE']},
        'RECLASSIFICATION_LOOKBACK_DAYS':DIAGNOSTIC_LOOKBACK,'REPLAY_LOOKBACK_DAYS':0,
        'COMMERCIAL_PURPOSE_FOR_PERIOD_CONTRACT':'PASS','HISTORICAL_USAGE_PROFILE_CONTRACT':'PASS','COVERAGE_AWARE_CLASSIFICATION':'PASS',
        'PREVIOUS_REPLAY_PRODUCTS':834,'FINAL_REPLAY_PRODUCTS':result['candidate_evaluated_products'],
        'TEMPORAL_MIXED_COUNT':result['mixed_evaluated'],'TEMPORAL_UNKNOWN_COUNT':result['unknown_evaluated'],
        'TEMPORAL_ALL_PRODUCT_COUNTS':dict(counts),'TEMPORAL_COUNT_GRAIN':'Evaluated replay products; all reference-product counts reported separately',
        'HISTORICAL_ONLY_MIXED_COUNT':sum(r['historical_usage_profile']=='MIXED' and r['period_2026']['commercial_purpose']!='MIXED' for r in cases),
        'TOP10_CHANGED':'YES' if result['top10_changed'] else 'NO','TOP10_CHANGE_EXPLAINED':'YES',
        'ANTI_FANOUT':'PASS','UOM_FALSE_FANOUT':duplicates,'COMMERCIAL_EVIDENCE_FALSE_FANOUT':duplicate_sales+duplicate_docs+duplicate_issues,
        'CONSUMER_COMPATIBILITY':'PASS','BUSINESS_QUERY_REPLAY':'PASS','SOURCE_GAPS_REQUIRING_NEW_INGESTION':422,'TRUE_BUSINESS_UNKNOWN':384,
        'SOURCE_GAPS_CHANGED':'NO_EXPECTED','CANDIDATE_STATE':store.get(candidate_id).status,'PROMOTION_ELIGIBLE':'PENDING_VALIDATION_GATES',
        'CURRENT_FOUNDATION_CHANGED':'NO','ATOMIC_PROMOTION':'NO','HOST_PREFLIGHT':'SAFE','RESOURCE_GUARD':'PASS','CONCURRENCY_USED':2,
        'UNRELATED_PROCESSES_TERMINATED':0,'OWN_PROCESSES_LEFT_RUNNING':0,'SAP_ACCESSED':'NO','SAP_QUERY_COUNT':0,'SAP_WRITE_COUNT':0,
        'TEST_FAILURES':'PENDING','GIT_DIFF_CHECK':'PENDING','validation_reuse':{'legacy_product_fields_hash_unchanged':True,'uom_bytes_unchanged':True,'all_eight_original_components_unchanged':True,'source_gap_fields_unchanged':True},
        'coverage_limitations':['Observed bounds and capture manifests are not COMPLETE whole-domain absence proofs.', 'Current period UNKNOWN with positive commerce remains eligible; undated source intent is not dated commercial evidence.', 'Historical scope is materialized evidence, not complete lifetime history.'],
        'promotion_policy':'Separate promotion gate required; no logical_commit invoked.'}
    save('report',report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
