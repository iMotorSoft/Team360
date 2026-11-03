"""DEV exception boundaries; synthetic local fixtures only."""
from dataclasses import replace

import pytest

from .contracts import Budget, Decision
from .foundation import local_context
from .foundation_dev import DevBudget, DevExecutor, check_claim
from .foundation_verifier import control_proposals, verify_control
from .test_foundation import reader, proposal


def test_budget_is_separate_and_bounded():
    assert Budget().query_seconds == 2
    assert DevBudget().query_seconds == 120
    assert DevBudget().threads == 1
    assert DevBudget().process_memory_bytes == 512 * 1024**2
    assert DevBudget().intersect(Budget()).query_seconds == 2
    for change in [dict(threads=2), dict(query_seconds=121), dict(result_rows=5001),
                   dict(process_memory_bytes=1024**3), dict(queries=13)]:
        with pytest.raises(ValueError):
            DevBudget(**change)


def test_explicit_exception_required():
    with pytest.raises(ValueError):
        DevExecutor(local_context('test'))


def test_io_only_exception_retains_guards(reader, monkeypatch):
    from . import foundation_dev as dev
    monkeypatch.setattr(dev, 'host_read_preflight', lambda: dict(safe=False, io_wait_fraction=.8))
    context = replace(local_context('test'), effective_budget=DevBudget())
    with DevExecutor(context, authorized=True) as executor:
        executor.reader = reader
        p = replace(proposal(), requested_budget=DevBudget())
        decision, result = executor.execute(p, context)
        assert decision.decision == Decision.ALLOW and result.status == 'COMPLETED'
        decision, result = executor.execute(proposal('DELETE FROM sales_line'), context)
        assert decision.decision != Decision.ALLOW
        executor.cancel.set()
        decision, result = executor.execute(p, context)
        assert decision.decision == Decision.RESOURCE_BLOCKED
    assert not executor.monitor.is_alive()


def test_reference_accepts_only_budget_variation(reader):
    context = replace(local_context('test'), effective_budget=DevBudget())
    references = tuple(replace(p, requested_budget=DevBudget()) for p in control_proposals())
    with DevExecutor(context, authorized=True) as executor:
        executor.reader = reader
        results = [executor.execute(p, context)[1] for p in references]
    assert verify_control(context, results, reference_proposals=references)['state'] == 'VERIFIED_WITH_LIMITATIONS'
    bad = (replace(references[0], sql='SELECT count(*) AS amount FROM sales_line'), *references[1:])
    assert verify_control(context, results, reference_proposals=bad)['reason'] == 'reference_proposal_mismatch'
    assert verify_control(context, results)['state'] == 'BLOCKED'


def test_supported_channel_never_becomes_confirmed(reader):
    context = local_context('test')
    from .foundation import FoundationReadonlyExecutor
    with FoundationReadonlyExecutor(context, reader=reader) as executor:
        results = [executor.execute(p, context)[1] for p in control_proposals()]
    names = [c.name for c in results[1].schema]
    row = list(results[1].rows[0])
    row[names.index('sales_channel_code')] = 'SALON'
    row[names.index('sales_channel_semantic_status')] = 'SUPPORTED'
    results[1] = replace(results[1], rows=(tuple(row),))
    assert verify_control(context, results)['state'] == 'BLOCKED'
    check = verify_control(context, results, allow_supported_channel=True)
    assert check['total'] == '12.340000' and check['supported_channel_lines'] == 1
    assert any('NOT CONFIRMED' in text for text in check['limitations'])
    row[names.index('sales_channel_semantic_status')] = 'UNKNOWN'
    results[1] = replace(results[1], rows=(tuple(row),))
    assert verify_control(context, results, allow_supported_channel=True)['state'] == 'BLOCKED'


def test_claims_fail_closed():
    ref = dict(total='12.340000', breakdowns=dict(product=[dict(key='L02822', amount='12.34')]))
    assert check_claim(dict(metric='reference_sku_line_total_bs', value='12.34'), ref)['state'] == 'REFERENCE_MATCH'
    assert check_claim(dict(metric='sku:L02822', value='12.34'), ref)['state'] == 'REFERENCE_MATCH'
    for value in ['NaN', 'Infinity', '13', None]:
        assert check_claim(dict(metric='reference_sku_line_total_bs', value=value), ref)['state'] == 'REJECTED'
    assert check_claim(dict(metric='billing', value='12.34'), ref)['state'] == 'UNVERIFIED'
