"""Selected semantic transport is data, never a source or join grant."""
from dataclasses import replace

import pytest

from .authorized_foundation import EffectiveScope, selected_business_knowledge
from .validator import Rejected
from .test_authorized_foundation import setup


def envelope():
    concept = dict(concept_id='horizontal', version=7, workspace_id='dev',
        approval_status='published', semantic_code='telchi.sales.horizontal_channel',
        definition='Venta de calle/DMS; no inferir desde vendedor.',
        source='owner:approved', operational_context={'limitations': ['No historical validity']},
        related_evidence={'entities': [{'entity_key': 'SECRET'}]})
    return dict(scope=dict(user_id='u', organization='o', workspace='dev', permissions=['read']),
        resolution=dict(interpretation_concepts=[concept], context_concepts=[concept]))


def test_selected_definitions_preserve_version_provenance_without_source_evidence():
    scope = EffectiveScope('u', 'o', 'dev', frozenset({'read'}))
    result = selected_business_knowledge(envelope(), scope, 'current-resolved', 42)
    assert len(result['concepts']) == 1
    assert result['concepts'][0]['version'] == 7
    assert result['concepts'][0]['source'] == 'owner:approved'
    assert 'SECRET' not in str(result)
    assert result['publication'] == 'current-resolved'
    assert result['snapshot'] == '42'
    assert 'not Foundation' in result['authority']


@pytest.mark.parametrize('change', [dict(user_id='other'), dict(workspace='other'),
                                    dict(organization='other'), dict(permissions=frozenset())])
def test_scope_change_denies_even_metadata(change):
    scope = replace(EffectiveScope('u', 'o', 'dev', frozenset({'read'})), **change)
    with pytest.raises(Rejected, match='knowledge_scope_mismatch'):
        selected_business_knowledge(envelope(), scope, 'current', 1)


def test_selected_contract_reaches_actual_research_payload(setup, monkeypatch, tmp_path):
    import asyncio
    from .test_console_bridge import service, install_model
    seen, saved = [], []
    install_model(monkeypatch, seen)
    import duckdb
    from .authorized_foundation import SourcePolicy
    with duckdb.connect(str(tmp_path / 'fixture.duckdb'), config={'threads': '1'}) as db:
        db.execute("CREATE TABLE docs AS SELECT 'HORIZONTAL' AS sales_channel_code, 'Horizontal' AS sales_channel_name")
    access = setup.reader.resolve_on(None)
    original = access.relation
    access.relation = lambda component, name: 'telchi.main.docs' if name == 'sales_document' else original(component, name)
    setup.policies.append(SourcePolicy('sales_document', 'existing.sales.read', 'org1', 'w1', None, True))
    svc, _ = service(setup)
    scope = setup.state[0]
    data = envelope()
    data['resolution']['interpretation_concepts'][0]['operational_context']['dimension'] = 'commercial_channel'
    data['scope'] = dict(user_id=scope.user_id, organization=scope.organization,
        workspace=scope.workspace, permissions=sorted(scope.permissions))
    data['resolution']['interpretation_concepts'][0]['workspace_id'] = scope.workspace

    async def resolve():
        return scope

    report = asyncio.run(svc.ask_scope(resolve, 'Investigate a new regional decline', saved.append,
                                      business_knowledge=data))
    assert seen
    assert all(p['business_knowledge']['concepts'][0]['version'] == 7 for p in seen)
    assert all(p['business_knowledge']['publication'] == 'fixture_published' for p in seen)
    assert all('SECRET' not in str(p) for p in seen)
    assert report['business_knowledge']['concepts'][0]['source'] == 'owner:approved'
    assert report['business_knowledge'] == seen[0]['business_knowledge']


def test_projection_receipts_are_selective_and_require_every_full_source(setup):
    from .authorized_foundation import ResearchBinding, SourcePolicy
    from .adaptive_research import discovery_catalog
    scope = setup.state[0]
    receipt = dict(origin='existing_projection', version='1',
        authority='CHECKED_BACKEND_PROJECTION_ONLY',
        sources=['sales_line', 'inventory_balance'], relationship='fixture composite projection')
    sources = tuple(replace(s, projection_contracts=(receipt,)) if s.name == 'sales_line' else s
                    for s in setup.sources)
    policies = [replace(p, permission='existing.sales.read', columns=None) for p in setup.policies]

    def bind(ps, ss=scope):
        return ResearchBinding(resolve_scope=lambda: ss, scope=ss, publication='fixture_published',
            snapshot=7, sources=sources, policies=ps, investigation_id='fixture')

    b = bind(policies)
    try:
        loaded = discovery_catalog(b.context.catalog, {'sales_line'})
        assert 'CHECKED_BACKEND_PROJECTION_ONLY' in str(loaded['tables'])
        assert 'fixture_published' in str(loaded['tables'])
        assert '"snapshot":"7"' in str(loaded['tables'])
        assert 'existing_projection' not in str(discovery_catalog(b.context.catalog, set()))
        # Composite projections MUST NOT accredit individual raw key equalities.
        assert not b.context.catalog.known_relations
    finally:
        b.close()
    for ps in (policies[:1], [policies[0], replace(policies[1], columns=('item_code',))],
               [policies[0], replace(policies[1], whole_dataset=False)],
               [policies[0], replace(policies[1], organization='foreign')],
               [replace(policies[0], columns=('doc_entry',)), policies[1]],
               [policies[0], replace(policies[1], permission='not_granted')]):
        b = bind(ps)
        try:
            assert 'existing_projection' not in str(b.context.catalog)
        finally:
            b.close()


def test_definition_authorization_before_interpreter_and_current_applicability():
    from .authorized_foundation import authorized_business_resolution, SourcePolicy
    scope = EffectiveScope('u', 'o', 'dev', frozenset({'read'}))
    data = envelope()['resolution']
    c = data['interpretation_concepts'][0]
    c['operational_context']['dimension'] = 'commercial_channel'
    policy = SourcePolicy('sales_document', 'read', 'o', 'dev', None, True)
    allowed = authorized_business_resolution(data, scope, [policy])
    concept = allowed['interpretation_concepts'][0]
    assert concept['source_applicability']['sources'] == ['sales_document']
    assert 'SECRET' not in str(allowed)
    for policies in ([], [replace(policy, permission='denied')],
                     [replace(policy, columns=('sales_channel_code',))],
                     [replace(policy, whole_dataset=False)], [replace(policy, organization='foreign')]):
        denied = authorized_business_resolution(data, scope, policies)
        assert not denied['interpretation_concepts'] and 'horizontal' not in str(denied)
    assert not authorized_business_resolution(data, scope, [policy], available_sources={})['interpretation_concepts']
    unrelated = envelope()['resolution']
    assert not authorized_business_resolution(unrelated, scope, [policy])['interpretation_concepts']


def test_unpublished_and_other_workspace_never_reach_luna():
    scope = EffectiveScope('u', 'o', 'dev', frozenset({'read'}))
    data = envelope()
    data['resolution']['interpretation_concepts'][0]['approval_status'] = 'proposed'
    assert selected_business_knowledge(data, scope, 'current', 1) == {}
    data = envelope()
    data['resolution']['interpretation_concepts'][0]['workspace_id'] = 'other'
    with pytest.raises(Rejected):
        selected_business_knowledge(data, scope, 'current', 1)
