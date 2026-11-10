"""DEV pilot authorization contracts; no external services or operational writes."""
from dataclasses import replace

import pytest

from modules.telchi.exploratory_sql.authorized_foundation import EffectiveScope
from modules.telchi.investigation.validation.presidencia_sourcepolicy_v1.test_proposal import bind, proposal
from modules.telchi.investigation.validation.devfull_free_pilot_v1.prepare import ORG, WORKSPACE


def pilot():
    policies, sources = proposal()
    policies = tuple(replace(p, organization=ORG, workspace=WORKSPACE) for p in policies)
    scope = EffectiveScope('fixture-devfull', ORG, WORKSPACE, frozenset(p.permission for p in policies))
    return scope, policies, sources


@pytest.mark.parametrize('change,count', [
    ({}, 70), ({'user_id': 'fixture-admin', 'permissions': frozenset()}, 0),
    ({'workspace': 'other-workspace'}, 0), ({'organization': 'other-organization'}, 0),
    ({'permissions': frozenset({'telchi.full_access'})}, 0),
])
def test_exact_dev_scope_and_explicit_policy(change, count):
    scope, policies, sources = pilot()
    binding = bind(replace(scope, **change), policies, sources)
    try:
        assert len(binding.projections) == count
    finally:
        binding.close()


def test_no_policy_means_no_access_even_with_all_effective_permissions():
    scope, _, sources = pilot()
    binding = bind(scope, (), sources)
    try:
        assert not binding.projections
    finally:
        binding.close()


def test_future_partial_holder_would_gain_access_and_requires_reaccreditation():
    scope, policies, sources = pilot()
    permission = 'telchi.sales.commercial_line_amount_by.read.v1'
    binding = bind(replace(scope, user_id='fixture-future-user', permissions=frozenset({permission})), policies, sources)
    try:
        assert len(binding.projections) == 23
    finally:
        binding.close()
