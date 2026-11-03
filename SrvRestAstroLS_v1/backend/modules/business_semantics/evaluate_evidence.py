"""Evaluate business evidence, not merely HTTP status. No external services."""
import argparse
import json
from decimal import Decimal
from pathlib import Path


def evaluate(root):
    pg=json.loads((root/'postgres_embedding_evidence.json').read_text())
    http=json.loads((root/'http_final/http_results.json').read_text())
    fixed=json.loads((root/'http_coverage_fix/http_results.json').read_text())
    turns={t['case']:t for t in http['turns']}
    turns['R04']=next(t for t in fixed['turns'] if t['case']=='R04')
    checks={}
    for n,code in enumerate(['telchi.sales.pharmacy_branches','telchi.sales.menona_customers',
                            'telchi.procurement.import_recommendations','telchi.receivables.outstanding',
                            'telchi.sales.lost_opportunities'],1):
        t=turns[f'S{n:02}'];a=t['audit'];concepts=a['business_semantics']['concepts']
        checks[f'S{n:02}']=bool(t['http_status']==200 and a['committed'] is True and a['capability_calls']==0
                                and concepts[0]['semantic_code']==code and a['confirmed_state'].get('semantic_references'))
    checks['S06']=('candidato' in turns['S06']['text'] and 'pérdida' in turns['S06']['text']
                   and turns['S06']['audit']['capability_calls']==0)
    for case in ['R01','R02']:
        expected=('8761459.22','209380.03','8552079.19') if case=='R01' else ('10033501.02','270007.35','9763493.67')
        a=turns[case]['audit'];result=a['execution_result'];row=result['rows'][0]
        checks[case]=bool(a['committed'] is True and a['capability_calls']==1 and result['grain']=='document_header'
                         and [Decimal(row[k]) for k in ['billed_amount','credit_amount','net_amount']]==[Decimal(v) for v in expected])
    for case,metric in [('R03','sales.latest_documents'),('R04','sales.coverage'),('R05','sales.source_top_items'),
                        ('S07_LATEST','sales.by_products'),('S07_SEARCH','products.search'),('S07_FROM_SEARCH','sales.by_products')]:
        a=turns[case]['audit']
        checks[case]=bool(a['committed'] is True and a['capability_calls']==1 and a['confirmed_state']['metric']==metric
                         and a['execution_result']['source']['publication_id']=='foundation_afd08d9eca6a725be53cdc3f9d5709c9')
    checks['KNOWN_FOLLOWUP']=turns['KNOWN_PERIOD']['audit']['capability_calls']==0 and turns['KNOWN_NEW_QUERY']['audit']['capability_calls']==1
    checks['S08']=not turns['S08']['audit']['business_semantics']['interpretation_concepts'] and turns['S08']['audit']['capability_calls']==0
    for case in ['NEW_CONVERSATION','AFTER_RESTART']:
        a=turns[case]['audit'];checks[case]=a['business_semantics']['status']=='resolved' and a['capability_calls']==0
    for case in ['A01','A02','A03','A04','A05','A06']:
        checks[case]=turns[case]['audit']['capability_calls']==0 and turns[case]['audit']['committed'] is True
    checks['A06_BOTH_CHANNELS']=len(turns['A06']['audit']['business_semantics']['concepts'])==2
    checks['OFFLINE_EXACT']=pg['offline_exact']['status']=='resolved' and pg['offline_exact']['timings']['embedding_ms']==0
    checks['OFFLINE_TEXT']=bool(pg['offline_text']['concepts']) and pg['offline_text']['degraded']=='embedding_unavailable'
    checks['SQL_VECTOR_DEGRADATION']=pg['turn_transaction_survives_vector_SQL_failure'] and pg['simulated_vector_SQL_failure']['degraded']=='vector_search_unavailable'
    checks['PROPOSALS_EXCLUDED']=pg['published_catalog_count']==9 and sum(c['status']=='proposed' for c in pg['administrative_catalog'])==2
    checks['VERSIONING']=pg['versioning']['versions']==[1,2] and pg['versioning']['embedding_count']==2 and pg['published_definition_mutation_denied']
    checks['SCOPE_FILTERS']=pg['cross_tenant_catalog_count']==0 and pg['scope_mismatch_denied'] and pg['non_admin_write_denied']
    checks['CLEANUP']=http['own_processes_left_running']==0 and fixed['own_processes_left_running']==0
    report={'checks':checks,'all_evaluated_checks_pass':all(checks.values()),
            'second_authorized_user_HTTP':'BLOCKED: only one identity has existing commercial access',
            'authenticated_administration_CLI':'NOT_TESTED: no trusted issuer/token fixture provided',
            'vector_calibration':'Provisional measured DEV sample; never auto-confirms vector candidates',
            'global_gate':'PARTIAL'}
    (root/'validation_results.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return all(checks.values())


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    if not evaluate(p.parse_args().root):
        raise SystemExit(1)


if __name__=='__main__':
    main()
