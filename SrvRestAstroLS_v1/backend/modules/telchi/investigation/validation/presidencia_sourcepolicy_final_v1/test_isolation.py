"""Counterexample and existing workspace boundary; fixture identities only."""
from dataclasses import replace

from modules.telchi.investigation.validation.presidencia_sourcepolicy_v1.test_proposal import (
    proposal, bind,
)
from modules.telchi.exploratory_sql.authorized_foundation import EffectiveScope


def exposed(scope, policies, sources):
    binding = bind(scope, policies, sources)
    try:
        return set(binding.projections)
    finally:
        binding.close()


def test_shared_scope_cannot_distinguish_presidencia_from_other_holder():
    policies, sources = proposal()
    president = EffectiveScope('president-fixture', 'fixture-org', 'fixture-workspace',
                               frozenset(p.permission for p in policies))
    other = replace(president, user_id='technical-non-presidencia-fixture')
    assert exposed(president, policies, sources) == exposed(other, policies, sources)
    assert len(exposed(other, policies, sources)) == 70


def test_seller_anchor_would_expand_its_contract_not_acquire_all_twelve():
    policies, sources = proposal()
    seller = EffectiveScope('seller-fixture', 'fixture-org', 'fixture-workspace',
        frozenset({'telchi.sales.commercial_line_amount_by.read.v1'}))
    visible = exposed(seller, policies, sources)
    assert len(visible) == 23
    assert {'ref_users', 'ref_party', 'credit_memo_line'} <= visible
    assert 'ap_invoice' not in visible


def test_existing_workspace_boundary_can_isolate_without_new_permissions():
    policies, sources = proposal()
    dedicated = tuple(replace(p, workspace='presidencia-fixture-workspace') for p in policies)
    president = EffectiveScope('president-fixture', 'fixture-org', 'presidencia-fixture-workspace',
                               frozenset(p.permission for p in policies))
    technical = replace(president, user_id='technical-fixture', workspace='fixture-workspace')
    assert len(exposed(president, dedicated, sources)) == 70
    assert exposed(technical, dedicated, sources) == set()
