from copy import deepcopy
from .evaluate import raw_score, replay_eligibility
from .test_contract import simple_intent


def row():
    intent=simple_intent()
    return dict(candidate_intent=intent, baseline_intent={k:v for k,v in intent.items() if k not in {'segments','granularities','geographies','relations','claims','unresolved_requirements'}},
                baseline_allowed=True,sidecar_error=None,candidate_call={'error':None})


def test_raw_score_does_not_credit_keyword_mentions():
    assert raw_score({'metrics':['customer_count']},{'metrics':['sales.net_amount'], 'claims':[{'text':'customer_count'}]})['preserved']==0


def test_raw_score_counts_regression():
    result=raw_score({'metrics':['a','b']},{'metrics':['a']})
    assert result['preserved']==1 and result['expected']==2 and not result['exact']


def test_replay_can_only_retain_existing_eligibility():
    r=row(); assert replay_eligibility(r)
    r['baseline_allowed']=False; assert not replay_eligibility(r)


def test_replay_blocks_new_unsupported_requirements():
    r=row(); r['candidate_intent']['geographies']=['La Paz']
    assert not replay_eligibility(r)


def test_replay_never_repairs_malformed_period():
    r=row(); period=r['candidate_intent']['time']['periods'][0]
    # Baseline was shared by construction in row(); detach before mutation.
    r['baseline_intent']=deepcopy(r['baseline_intent'])
    period['end']=period.pop('end_exclusive')
    assert not replay_eligibility(r)


def test_replay_provider_failure_blocks_even_on_old_valid_intent():
    r=row(); r['candidate_call']['error']='provider_unavailable'
    assert not replay_eligibility(r)
