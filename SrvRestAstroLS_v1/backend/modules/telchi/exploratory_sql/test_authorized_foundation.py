"""Phase B: small sequential fixtures, no enterprise grants or real Foundation."""
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import duckdb
import pytest

from .authorized_foundation import (EffectiveScope, SourcePolicy, ResearchBinding,
    DiscoveredSource, AuthorizedFoundationExecutor, discover, console_scope)
from .contracts import Column, ExploratoryQueryProposal, Decision
from .validator import authorize, validate, Rejected


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = tmp_path / 'fixture.duckdb'
    with duckdb.connect(str(path), config={'threads': '1'}) as db:
        db.execute('CREATE TABLE sales_line(doc_entry VARCHAR, amount INTEGER, private_note VARCHAR)')
        db.execute("INSERT INTO sales_line VALUES ('1',10,'secret'),('2',20,'secret')")
        db.execute('CREATE TABLE inventory_balance(item_code VARCHAR, quantity INTEGER)')
        db.execute("INSERT INTO inventory_balance VALUES ('a',3),('b',4)")
    @contextmanager
    def session(read_only=True):
        assert read_only
        with duckdb.connect(':memory:', config={'threads': '1'}) as db:
            db.execute(f"ATTACH '{path}' AS telchi (READ_ONLY)")
            yield db
    class Access:
        foundation_publication_id = 'fixture_published'
        ducklake_snapshot_id = 7
        manifest = {'components': {'sales': {}, 'oitw': {}, 'unreadable': {'datasets': {'future_data': {}}}}}
        def relation(self, component, name):
            from ..datalake.foundation_reader import FoundationReaderError
            if name not in {'sales_line', 'inventory_balance'}:
                raise FoundationReaderError('not published by fixture')
            return f'telchi.main.{name}'
    access = Access()
    reader = SimpleNamespace(connector=SimpleNamespace(session=session), resolve_on=lambda db: access)
    with session() as db:
        sources, gaps = discover(db, access)
    state = [EffectiveScope('u1', 'org1', 'w1', frozenset({'existing.sales.read'}))]
    policies = [SourcePolicy('sales_line', 'existing.sales.read', 'org1', 'w1', ('doc_entry', 'amount'), True),
                SourcePolicy('inventory_balance', 'existing.inventory.read', 'org1', 'w1', None, True)]
    def bind(scope=None, policies_=None):
        return ResearchBinding(resolve_scope=lambda: state[0], scope=scope or state[0],
            publication='fixture_published', snapshot=7, sources=sources,
            policies=policies if policies_ is None else policies_, investigation_id='fixture')
    from . import foundation
    monkeypatch.setattr(foundation, 'host_read_preflight', lambda: {'safe': True})
    yield SimpleNamespace(reader=reader, sources=sources, gaps=gaps, state=state, bind=bind, policies=policies)


def proposal(sql, sources=('sales_line',)):
    return ExploratoryQueryProposal(sql, 'fixture', 'fixture', sources, 'aggregate', 'observed')


def test_manifest_sealed_extension_discovery(tmp_path, monkeypatch):
    import hashlib
    from ..datalake import ducklake
    from ..datalake.foundation_reader import FoundationReaderError
    monkeypatch.setattr(ducklake, 'DATA_ROOT', tmp_path)
    path = tmp_path / 'sealed.parquet'
    with duckdb.connect(':memory:', config={'threads': '1'}) as db:
        db.execute("COPY (SELECT 7 AS business_value, 'sku' AS ItemCode) TO ? (FORMAT PARQUET)", [str(path)])
        entry = {'file_references': [str(path)],
                 'file_hashes': [hashlib.sha256(path.read_bytes()).hexdigest()]}
        def unsupported(*_):
            raise FoundationReaderError('not an Atomic contract')
        access = SimpleNamespace(manifest={'components': {'extension': {
            'datasets': {'new_dataset': entry}}}}, relation=unsupported)
        sources, gaps = discover(db, access)
        assert not gaps and sources[0].name == 'new_dataset'
        assert 'item_code' in {c.name for c in sources[0].columns}
        assert db.execute('SELECT item_code FROM ' + sources[0].relation).fetchone() == ('sku',)
        assert db.execute('SELECT business_value FROM ' + sources[0].relation).fetchone() == (7,)
        entry['file_hashes'] = ['0' * 64]
        sources, gaps = discover(db, access)
        assert not sources and 'unsupported_reader_contract' in gaps[0]
        entry['file_references'] = [str(tmp_path.parent / 'outside.parquet')]
        assert not discover(db, access)[0]
        entry['file_references'] = [str(path)]
        entry['file_hashes'] = []
        assert not discover(db, access)[0]


def test_dynamic_schemas_and_new_columns(setup):
    assert {s.name for s in setup.sources} == {'sales_line', 'inventory_balance'}
    assert [c.name for c in setup.sources[0].columns]  # real DESCRIBE, not a hand-maintained projection
    assert any('future_data:unsupported_reader_contract' in gap for gap in setup.gaps)
    b = setup.bind()
    assert [t.name for t in b.context.catalog.tables] == ['sales_line']
    assert {c.name for c in b.context.catalog.tables[0].columns} == {'doc_entry', 'amount'}
    assert 'telchi.main' not in str(b.context.catalog)
    # A previously unknown reference dataset/column needs no investigator code change.
    new = DiscoveredSource('ref_new_business_entity', 'trusted_relation',
                           (Column('new_identifier', 'VARCHAR'),), ('Unaccredited semantics',))
    fresh = ResearchBinding(resolve_scope=lambda: setup.state[0], scope=setup.state[0],
        publication='fixture_published', snapshot=7, sources=(new,),
        policies=(SourcePolicy(new.name, 'existing.sales.read', 'org1', 'w1', None, True),), investigation_id='new')
    assert fresh.context.catalog.tables[0].columns[0].name == 'new_identifier'
    b.close(); fresh.close()


@pytest.mark.parametrize('sql,sources', [
    ('SELECT sum(quantity) AS total FROM inventory_balance', ('inventory_balance',)),
    ('WITH x AS (SELECT private_note AS note FROM sales_line) SELECT note AS note FROM x', ('sales_line',)),
    ('SELECT count(*) AS total FROM (SELECT private_note AS note FROM sales_line) AS x', ('sales_line',)),
    ('SELECT private_note AS note FROM sales_line', ('sales_line',)),
    ('SELECT count(*) AS total FROM telchi.main.sales_line', ('sales_line',)),
    ("SELECT count(*) AS total FROM read_parquet('/etc/passwd')", ('sales_line',)),
    ('DELETE FROM sales_line', ('sales_line',)),
    ('SELECT a.doc_entry AS doc FROM sales_line a JOIN inventory_balance b ON a.doc_entry=b.item_code', ('sales_line','inventory_balance')),
])
def test_denials_in_compositions(setup, sql, sources):
    b = setup.bind()
    decision, query = validate(proposal(sql, sources), b.context)
    assert decision.decision != Decision.ALLOW and query is None
    b.close()


def test_readonly_query_and_authorized_cte(setup):
    b = setup.bind()
    with AuthorizedFoundationExecutor(b.context, reader=setup.reader) as executor:
        for sql in ('SELECT sum(amount) AS total FROM sales_line',
                    'WITH x AS (SELECT amount AS amount FROM sales_line) SELECT sum(amount) AS total FROM x'):
            decision, result = executor.execute(proposal(sql), b.context)
            assert decision.decision == Decision.ALLOW, decision
            assert result.status == 'COMPLETED', result
            assert result.rows == ((30,),)
    b.close()


def test_new_reference_dataset_discovered_without_catalog_entry(tmp_path):
    from .validator import canonical
    root = tmp_path / 'immutable_reference_version'
    dataset = root / 'previously_unknown_domain'
    dataset.mkdir(parents=True)
    path = dataset / 'part-00000.parquet'
    with duckdb.connect(':memory:', config={'threads': '1'}) as db:
        db.execute(f"COPY (SELECT 'business-id' AS novel_identifier, 42 AS new_measure) TO '{path}' (FORMAT PARQUET)")
        access = SimpleNamespace(manifest={'components': {'reference': {}}}, reference_path=root,
                                 reference=lambda name: root / name / 'part-00000.parquet')
        sources, gaps = discover(db, access)
    assert gaps == ()
    assert sources[0].name == 'ref_previously_unknown_domain'
    assert {c.name for c in sources[0].columns} == {'novel_identifier', 'new_measure'}
    scope = EffectiveScope('u', 'org', 'w', frozenset({'existing.read'}))
    b = ResearchBinding(resolve_scope=lambda: scope, scope=scope, publication='p', snapshot=1,
        sources=sources, policies=[SourcePolicy(sources[0].name, 'existing.read', 'org', 'w', None, True)],
        investigation_id='dynamic')
    assert 'novel_identifier' in canonical(b.context.catalog)
    assert str(root) not in canonical(b.context.catalog)
    b.close()


def test_bounded_derived_join_without_raising_budget(setup):
    from .contracts import CandidateRelation
    b = setup.bind()
    sql = '''WITH a AS (SELECT doc_entry AS doc_entry,amount AS amount FROM sales_line LIMIT 2),
                  z AS (SELECT doc_entry AS doc_entry FROM sales_line LIMIT 2)
             SELECT sum(a.amount) AS total FROM a JOIN z ON a.doc_entry=z.doc_entry'''
    p = replace(proposal(sql), candidate_relations=(
        CandidateRelation('sales_line', 'doc_entry', 'sales_line', 'doc_entry', 'fixture key candidate'),))
    with AuthorizedFoundationExecutor(b.context, reader=setup.reader) as executor:
        decision, result = executor.execute(p, b.context)
        assert decision.decision == Decision.ALLOW and result.rows == ((30,),)
    assert b.context.effective_budget.max_join_pairs == 10000
    assert validate(replace(p, sql=sql.replace(' LIMIT 2', '')), b.context)[0].reason == 'join_pair_budget'
    # A forbidden column in a bounded branch remains forbidden.
    denied = replace(p, sql=sql.replace('amount AS amount', 'private_note AS amount'))
    assert validate(denied, b.context)[1] is None
    b.close()


def test_partial_row_scopes_withheld(setup):
    b = setup.bind(policies_=[SourcePolicy('sales_line', 'existing.sales.read', 'org1', 'w1', None, False)])
    assert b.context.catalog.tables == ()
    assert validate(proposal('SELECT count(*) AS total FROM sales_line'), b.context)[1] is None
    b.close()


def test_revocation_execution_evidence_resume(setup):
    b = setup.bind()
    p = proposal('SELECT sum(amount) AS total FROM sales_line')
    with AuthorizedFoundationExecutor(b.context, reader=setup.reader) as executor:
        _, result = executor.execute(p, b.context)
        assert b.present(result, b.context).rows == ((30,),)
        setup.state[0] = replace(setup.state[0], permissions=frozenset())
        decision, result = executor.execute(p, b.context)
        assert decision.decision == Decision.DENY and result.rows == ()
        with pytest.raises(Rejected):
            b.present('old protected result', b.context)
        with pytest.raises(Rejected):
            authorize(b.context)
    b.close()


@pytest.mark.parametrize('field,value', [('user_id','u2'), ('organization','org2'), ('workspace','w2'), ('active',False)])
def test_live_identity_and_tenant_changes(setup, field, value):
    b = setup.bind()
    setup.state[0] = replace(setup.state[0], **{field: value})
    with pytest.raises(Rejected):
        authorize(b.context)
    b.close()


def test_copied_context_or_cross_owner_evidence_not_authority(setup):
    b = setup.bind()
    with pytest.raises(Rejected):
        authorize(replace(b.context))
    with pytest.raises(Rejected):
        b.present('protected', replace(b.context, identity='other'))
    b.close()
    with pytest.raises(Rejected):
        authorize(b.context)
    with pytest.raises(Rejected):
        b.present('closed protected evidence', b.context)


def test_second_workspace_cannot_reuse_source_policy(setup):
    setup.state[0] = replace(setup.state[0], organization='org2', workspace='w2')
    b = setup.bind()
    assert b.context.catalog.tables == ()
    b.close()


def test_broad_fixture_shared_scope_not_technical_privilege(setup):
    setup.state[0] = replace(setup.state[0], permissions=frozenset({'existing.sales.read', 'existing.inventory.read'}))
    owner = setup.bind()
    setup.state[0] = replace(setup.state[0], user_id='second_executive_fixture')
    second = setup.bind()
    assert owner.context.catalog == second.context.catalog
    assert second.context.permissions == frozenset({'existing.sales.read', 'existing.inventory.read'})
    assert len(second.context.catalog.tables) == 2
    owner.close(); second.close()


def test_resource_block_preserves_authorized_publication(setup, monkeypatch):
    from . import foundation
    b = setup.bind()
    monkeypatch.setattr(foundation, 'host_read_preflight', lambda: {'safe': False})
    with AuthorizedFoundationExecutor(b.context, reader=setup.reader) as executor:
        decision, result = executor.execute(proposal('SELECT sum(amount) AS total FROM sales_line'), b.context)
        assert decision.decision == Decision.RESOURCE_BLOCKED
        assert (result.publication, result.snapshot) == ('fixture_published', '7')
        assert not result.rows
    b.close()


def test_pinned_snapshot_change_blocks_execution(setup):
    b = setup.bind()
    setup.reader.resolve_on = lambda db: SimpleNamespace(foundation_publication_id='new', ducklake_snapshot_id=8)
    with AuthorizedFoundationExecutor(b.context, reader=setup.reader) as executor:
        decision, result = executor.execute(proposal('SELECT sum(amount) AS total FROM sales_line'), b.context)
        assert decision.decision != Decision.ALLOW and not result.rows
    b.close()


def test_authorization_backend_failure_is_denial_not_stale_access(setup):
    b = setup.bind()
    def unavailable():
        raise RuntimeError('sensitive backend diagnostic')
    b.resolve_scope = unavailable
    with pytest.raises(Rejected, match='authorization_unavailable'):
        b.present('old evidence', b.context)
    assert validate(proposal('SELECT sum(amount) AS total FROM sales_line'), b.context)[0].decision == Decision.DENY
    b.close()


def test_full_access_string_does_not_expand_scope(setup):
    setup.state[0] = replace(setup.state[0], permissions=frozenset({'FULL_ACCESS'}))
    b = setup.bind()
    assert not b.context.catalog.tables
    b.close()


def test_session_revocation_during_model_call_scrubs_presentation(setup, monkeypatch):
    import asyncio
    from . import adaptive_research as runner
    from .ask import Session
    class Probe:
        calls = []
        async def next(self, *args, **kwargs):
            return {'ready': True}
    class Model:
        calls = []
        async def next(self, payload, **kwargs):
            setup.state[0] = replace(setup.state[0], permissions=frozenset())
            return {'action': 'clarify', 'question': 'protected model content'}
    monkeypatch.setattr(runner, 'LunaSQL', lambda **kwargs: Probe())
    b = setup.bind()
    session = Session(authorized_binding=b, progress=lambda event: None)
    session.history = [{'role': 'assistant', 'content': 'protected previous observation'}]
    def executor_factory(ctx, **kwargs):
        return AuthorizedFoundationExecutor(ctx, reader=setup.reader, **kwargs)
    report = asyncio.run(session.ask('fixture question', lambda report: None,
        luna=Model(), executor_factory=executor_factory))
    assert report['status'] == 'BLOCKED'
    assert report['business_answer'] == '' and not session.history
    assert 'protected' not in str(report)
    b.close()


def test_console_resolver_reused_without_role_expansion():
    import asyncio
    asyncio.run(console_resolver_contract())


async def console_resolver_contract():
    calls = []
    class Repository:
        async def list_effective_permissions(self, conn, workspace, user):
            calls.append((workspace, user))
            return ['telchi.existing.read']
    async def validate_identity(*args):
        return True
    scope = await console_scope(None, SimpleNamespace(user_id='u'), organization='org',
        workspace='w', validate_identity=validate_identity, repository=Repository())
    assert calls == [('w','u')]
    assert scope.permissions == frozenset({'telchi.existing.read'})
    async def denied(*args):
        return False
    with pytest.raises(Rejected):
        await console_scope(None, SimpleNamespace(user_id='u'), organization='other',
            workspace='w', validate_identity=denied, repository=Repository())
    assert len(calls) == 1
