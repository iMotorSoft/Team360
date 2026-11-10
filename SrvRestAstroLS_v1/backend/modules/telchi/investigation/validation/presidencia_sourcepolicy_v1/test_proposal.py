"""Small offline checks against the unchanged SourcePolicy binding contract."""
import csv
from dataclasses import replace
from pathlib import Path

import pytest

from modules.telchi.exploratory_sql.authorized_foundation import (
    DiscoveredSource, EffectiveScope, ResearchBinding, SourcePolicy,
)
from modules.telchi.exploratory_sql.contracts import Column

ROOT = Path(__file__).resolve().parents[7]


def proposal():
    with (ROOT / 'data/reports/telchi/presidencia-sourcepolicy-v1/matrix.csv').open() as f:
        rows = list(csv.DictReader(f))
    policies = tuple(SourcePolicy(r['dataset'], r['existing_permission'], 'fixture-org',
                                 'fixture-workspace', None, True) for r in rows)
    sources = tuple(DiscoveredSource(r['dataset'], '(SELECT 1 AS id)',
                                    (Column('id', 'INTEGER', False),),
                                    (r['limitations'],)) for r in rows)
    return policies, sources


def bind(scope, policies, sources):
    return ResearchBinding(resolve_scope=lambda: scope, scope=scope,
        publication='fixture-only-not-current', snapshot=1, sources=sources,
        policies=policies, investigation_id='offline-proposal')


def test_seventy_sources_twelve_existing_anchors_no_ambiguity():
    policies, sources = proposal()
    assert len(policies) == len({p.source for p in policies}) == 70
    assert len({p.permission for p in policies}) == 12
    scope = EffectiveScope('fixture-user', 'fixture-org', 'fixture-workspace',
                           frozenset(p.permission for p in policies))
    binding = bind(scope, policies, sources)
    try:
        assert set(binding.projections) == {p.source for p in policies}
    finally:
        binding.close()


@pytest.mark.parametrize('change', [
    {'permissions': frozenset()}, {'organization': 'other-org'},
    {'workspace': 'other-workspace'},
    {'permissions': frozenset({'telchi.full_access'})},
])
def test_no_implicit_scope_or_full_access_literal(change):
    policies, sources = proposal()
    scope = EffectiveScope('fixture-user', 'fixture-org', 'fixture-workspace',
                           frozenset(p.permission for p in policies))
    binding = bind(replace(scope, **change), policies, sources)
    try:
        assert not binding.projections
    finally:
        binding.close()


def test_single_anchor_only_exposes_its_explicit_dataset_contracts():
    policies, sources = proposal()
    permission = 'telchi.purchasing.ordered_amount.read.v1'
    scope = EffectiveScope('fixture-user', 'fixture-org', 'fixture-workspace',
                           frozenset({permission}))
    binding = bind(scope, policies, sources)
    try:
        assert set(binding.projections) == {p.source for p in policies if p.permission == permission}
        assert 'sales_document' not in binding.projections
        assert 'ref_users' not in binding.projections
    finally:
        binding.close()


def test_duplicate_dataset_policies_remain_rejected():
    policies, sources = proposal()
    scope = EffectiveScope('fixture-user', 'fixture-org', 'fixture-workspace',
                           frozenset(p.permission for p in policies))
    with pytest.raises(ValueError, match='ambiguous_source_policy'):
        bind(scope, policies + (policies[0],), sources)
