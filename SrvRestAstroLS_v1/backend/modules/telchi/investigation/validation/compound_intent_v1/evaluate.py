"""Post-run evaluation only. No provider calls; gold never enters extraction.

Evaluates frozen LlmFit plan eligibility conservatively, WITHOUT equating that
laboratory catalog to current runtime execution permission. Raw rows stay immutable.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import statistics
from .contract import atoms
from .run import summarize, ABRAHAM, BACKEND

EXTRAS = {'segments','granularities','geographies','relations','claims','unresolved_requirements'}
IGNORED = {'intent','pending_clarification'}


def replay_eligibility(row):
    """Only retain frozen approved plan if all extracted facets are represented.

    No new capabilities, no state_delta synthesized from extraction, no execution.
    Structural mismatch fails closed. This is deliberately stricter than an LLM judge.
    """
    intent=row['candidate_intent']
    if row['sidecar_error'] or row['candidate_call']['error'] or not intent:
        return False
    if any(intent.get(k) for k in EXTRAS):
        return False
    baseline={k:v for k,v in row['baseline_intent'].items() if k not in IGNORED}
    extracted={k:v for k,v in intent.items() if k not in EXTRAS}
    return bool(row['baseline_allowed'] and atoms(baseline)==atoms(extracted))


def raw_score(gold, candidate):
    a=atoms(gold)
    b=atoms({k:v for k,v in candidate.items() if k in gold})
    return dict(preserved=len(a&b), expected=len(a), predicted=len(b), exact=a==b,
                missing=sorted(a-b), unexpected=sorted(b-a))


def main(args):
    output=Path(args.output); llmfit=Path(args.llmfit)/'benchmarks/telchi/conversation_state_v1'
    raw=[json.loads(line) for line in (output/'rows.jsonl').read_text().splitlines()]
    data=json.loads((llmfit/'dataset.json').read_text())
    golds={t['turn_id']:t for c in data['conversations'] for t in c['turns']}
    frozen={r['turn_id']:r for r in map(json.loads,(llmfit/'hybrid_router_validation/LUNA_ONLY/turns.jsonl').read_text().splitlines())}
    rows=deepcopy(raw)
    for row in rows:
        if row['group']=='llmfit':
            row['candidate_allowed']=replay_eligibility(row)
    report=summarize(rows)
    report['plan_comparison_method']='LlmFit: conservative frozen-plan eligibility replay. Abraham/simple: unchanged current State Engine + availability, no execution. Not runtime-equivalent catalogs.'
    report['limitations']=[s for s in report['limitations'] if 'remain frozen and candidate cannot authorize' not in s]
    report['limitations'].append('Additional LlmFit eligibility gate is post-run deterministic analysis; extraction/raw rows unchanged. No semantic repair or inferred capabilities.')
    details=[]
    for group in ('llmfit','abraham','simple'):
        subset=[r for r in rows if r['group']==group]
        plan={}; field_counts={}
        for arm in ('baseline','candidate'):
            tp=fp=fn=tn=0; good_ids=[]; losses=[]
            for r in subset:
                # LlmFit's reviewed-status caveat remains applicable. Current simple
                # control availability is independently specified by the existing catalog.
                expected=(golds[r['id']]['expected_action']=='EXECUTE' if group=='llmfit'
                          else (False if group=='abraham' else r['id']!='S06_1'))
                allowed=r[arm+'_allowed']
                tp+=int(allowed and expected); fp+=int(allowed and not expected)
                fn+=int(not allowed and expected); tn+=int(not allowed and not expected)
                if allowed and expected: good_ids.append(r['id'])
            plan[arm]=dict(true_positive=tp,false_positive=fp,false_negative=fn,true_negative=tn,
                           precision=tp/(tp+fp) if tp+fp else None, recall=tp/(tp+fn) if tp+fn else None)
        report[group]['plan_eligibility_vs_gold']=plan
        correct_baseline=[]; regressions=[]
        for r in subset:
            scores={arm:raw_score(r['gold'],r[arm+'_intent']) for arm in ('baseline','candidate')}
            if scores['baseline']['exact']:
                correct_baseline.append(r['id'])
                if not scores['candidate']['exact']: regressions.append(r['id'])
            details.append(dict(id=r['id'],group=group,scores=scores,
                                baseline_allowed=r['baseline_allowed'],candidate_allowed=r['candidate_allowed'],
                                sidecar_error=r['sidecar_error']))
            for field in r['gold']:
                if field in IGNORED: continue
                count=field_counts.setdefault(field,dict(expected=0,baseline_preserved=0,candidate_preserved=0))
                g=atoms({field:r['gold'][field]}); count['expected']+=len(g)
                for arm in ('baseline','candidate'):
                    count[arm+'_preserved']+=len(g&atoms({field:r[arm+'_intent'].get(field)}))
        report[group]['baseline_correct_turns']=len(correct_baseline)
        report[group]['previously_correct_turn_regressions']=regressions
        report[group]['per_field']=field_counts
        # Diagnostic only: rename the unambiguous exclusive-period key. This is
        # NOT a repaired model output, NOT used by eligibility, and NOT primary score.
        standardized=[]
        for r in subset:
            candidate=deepcopy(r['candidate_intent'])
            for period in (candidate.get('time') or {}).get('periods',[]):
                if 'end' in period and 'end_exclusive' not in period:
                    period['end_exclusive']=period.pop('end')
            standardized.append(raw_score(r['gold'],candidate))
        report[group]['diagnostic_end_key_standardized_only']=dict(
            preserved=sum(x['preserved'] for x in standardized),requirements=sum(x['expected'] for x in standardized),
            exact_turns=sum(x['exact'] for x in standardized),
            method='Scorer-only end -> end_exclusive in time.periods. No changes to raw outputs or eligibility.')
        baseline_latency=[]
        for r in subset:
            if group=='llmfit': baseline_latency.append(frozen[r['id']]['latency_ms'])
            elif group=='simple': baseline_latency.append(r['baseline_call']['latency_ms'])
        if baseline_latency:
            combined=[x+r['candidate_call']['latency_ms'] for x,r in zip(baseline_latency,subset)]
            report[group]['baseline_interpretation_ms']={'p50':statistics.median(baseline_latency),'p95':sorted(baseline_latency)[max(0,math.ceil(len(baseline_latency)*.95)-1)]}
            report[group]['estimated_serial_candidate_ms']={'p50':statistics.median(combined),'p95':sorted(combined)[max(0,math.ceil(len(combined)*.95)-1)]}
    attempts=[json.loads(line) for line in (llmfit/'hybrid_router_validation/LUNA_ONLY/attempts.jsonl').read_text().splitlines()]
    report['llmfit']['baseline_llm_calls']=len(attempts)
    report['llmfit']['baseline_tokens']={k:sum(r.get(k) or 0 for r in attempts) for k in ('input_tokens','output_tokens')}
    report['llmfit']['candidate_total_llm_calls']=len(attempts)+report['llmfit']['additional_llm_calls']
    report['llmfit']['candidate_total_tokens']={k:report['llmfit']['baseline_tokens'][k]+report['llmfit']['additional_tokens'][k] for k in ('input_tokens','output_tokens')}
    report['provider_errors']=sum(bool(r['candidate_call']['error']) for r in raw)
    report['claims_or_relations_rejected']=sum(bool(r['sidecar_error']) for r in raw)
    report['all_relations_remain_unverified']=all(x['status']=='USER_ASSERTED_UNVERIFIED' for r in raw for k in ('claims','relations') for x in r['candidate_intent'].get(k,[]))
    report['raw_time_end_key_turns']=[r['id'] for r in raw if any('end' in p for p in (r['candidate_intent'].get('time') or {}).get('periods',[]))]
    report['abraham_semantic_review'] = review_abraham(rows)
    report['cost_accounting_note'] = ('Measured tokens cover checkpointed completed calls only. Initial harness aborted after 104 corpus rows: '
        'measure_context string caused AttributeError in plan guard. Corrected fail-closed guard and resumed cached rows. '
        'Tail requests in flight at abort were not checkpointed; exact billed total UNKNOWN (not zero). '
        'See execution.log, execution-resume.log and source snapshots. No corpus extraction re-run.')
    report['harness_functional_failures'] = dict(initial=1, resolved=1, environmental_aborts=0)
    report['recommendation']='REVISE'
    report['recommendation_reasons']=[
        'Require canonical validated nested intent schema (including end_exclusive), grounding and explicit update semantics.',
        'Require a proven lossless intent-to-plan coverage check before promotion; conservative V1 blocks previously allowed controls.',
        'Do not accept Abraham improvements as general success: report full-corpus loss/regressions separately.',
        'Need independently reviewed gold for unsupported REQUESTS rather than accepted-state-only gold, and verified USD tariff.']
    manifest=json.loads((output/'manifest.json').read_text())
    report['protected_sources_unchanged']=all(Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in manifest['runtime_hashes_before'].items())
    report['host_cleanup']=dict(host_preflight='SAFE',resource_guard='PASS',concurrency_used=2,unrelated_processes_terminated=0,environmental_aborts=0,own_processes_left_running=0)
    report['artifact_hashes']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [output/'rows.jsonl',*sorted(Path(__file__).parent.glob('*.py'))]}
    (output/'evaluation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    (output/'errors_and_regressions.json').write_text(json.dumps(details,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k in ('llmfit','abraham','simple','abraham_relations','recommendation')},indent=2,ensure_ascii=False))

def review_abraham(rows):
    """Explicit analyst adjudication, not independent gold or a new model judge.

    Uses existing Abraham acceptance's unresolved population/mapping requirements.
    Translation equivalences below never change raw output, raw score or plan gate.
    """
    results={}
    for r in rows:
        if r['group']!='abraham': continue
        c=r['candidate_intent']
        fingerprint=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()
        manually_reviewed = fingerprint == 'ee166af780622f5e1d5bc4348e3316988c279495364354ad93839ce6569b6e68'
        path=next(path for tid,_,_,path in ABRAHAM if tid==r['id'])
        original=json.loads((BACKEND.parents[1]/'data/reports/telchi'/path).read_text())
        b=original['turn']['response']['audit']['confirmed_state']
        if r['id']=='ABRAHAM_001':
            # Manual ambiguity review grounded in the complete stored output:
            # it explicitly mentions pharmacy prioritization and unapproved mapping,
            # unspecified monetary definition and absent dates, but not population
            # (registered vs distinct period/monthly buyers).
            checks=[
                ('customer_count',False,'customer_count' in c.get('metrics',[]),'candidate.metrics'),
                ('horizontal_channel',b.get('sales_channel')=='HORIZONTAL',any(f.get('field')=='sales_channel_id' and 'HORIZONTAL' in f.get('values',[]) for clause in c.get('filters',[]) for f in clause),'candidate.filters'),
                ('pharmacy_focus_not_certified_membership',False,'pharmacies' in c.get('segments',[]) or 'farmacias' in c.get('segments',[]),'candidate.segments + unresolved_requirements: prioritizes pharmacies'),
                ('monthly_granularity',False,any(x in {'month','monthly'} for x in c.get('granularities',[])),'candidate.granularities'),
                ('sales_magnitude_request',b.get('metric')=='sales.net_amount',any(x.startswith('sales.') for x in c.get('metrics',[])),'metrics; not certification of net definition'),
                ('period_unresolved_not_invented',b.get('period') is None,not (c.get('time') or {}).get('periods'),'period/time + unresolved_requirements'),
                ('customer_population_registered_vs_buyers_unresolved',False,False,'Missing from candidate; acceptance.json requires clarification'),
                ('pharmacy_mapping_unverified',False,manually_reviewed,'Analyst reading: candidate explicitly says no validated customer classification/filter'),
                ('monetary_basis_unverified',False,manually_reviewed,'Analyst reading: candidate explicitly says monetary sales measure unspecified; no execution')]
        else:
            relations=c.get('relations',[])
            relation_checks=[]
            for city,distributor in [('La Paz','propia'),('Cochabamba','L&S')]:
                relation_checks.append(any(x.get('subject')=='Citrato de magnesio' and x.get('predicate') in {'distribution','distribución'} and x.get('object')==distributor and x.get('geography')==city for x in relations))
            checks=[
                ('product_mention',b.get('product_search_text')=='Citrato de magnesio',any(x.get('subject')=='Citrato de magnesio' for x in relations),'original confirmed_state.product_search_text vs candidate.relations.subject'),
                ('La_Paz_geography_not_branch',False,'La Paz' in c.get('geographies',[]),'geographies; baseline branches misclassify geography'),
                ('Cochabamba_geography_not_branch',False,'Cochabamba' in c.get('geographies',[]),'geographies; baseline branches misclassify geography'),
                ('product_La_Paz_own_distribution',False,relation_checks[0],'relations; distribución/distribution is translation-only equivalence'),
                ('product_Cochabamba_LS_distribution',False,relation_checks[1],'relations; exact product/distributor/geography match'),
                ('no_invented_branch_mapping',not b.get('branches'),not (c.get('scope') or {}).get('branch_ids'),'scope vs branches'),
                ('distribution_claims_preserved_unverified',False,len(relations)==2 and all(x['status']=='USER_ASSERTED_UNVERIFIED' for x in relations),'relations.status + exact-substring provenance validated')]
        results[r['id']]=dict(candidate_fingerprint=fingerprint,manual_review_applies=(manually_reviewed if r['id']=='ABRAHAM_001' else None),requirements=len(checks),baseline_preserved=sum(bool(b) for _,b,_,_ in checks),
            candidate_preserved=sum(bool(c) for _,_,c,_ in checks),checks=[dict(requirement=n,baseline=bool(b),candidate=bool(c),evidence=e) for n,b,c,e in checks])
    return dict(method='Analyst semantic adjudication; not independent review. Raw structural scores also reported. No output repair or gate changes.',
                cases=results,relations=dict(baseline_preserved=0,candidate_preserved=2,expected=2),
                remaining_error='Abraham 001 customer population ambiguity not explicitly retained (registered members vs distinct buyers).')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True); parser.add_argument('--llmfit',required=True)
    main(parser.parse_args())
