"""Generic discovery and typed temporal execution-to-answer regressions."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime
from types import SimpleNamespace

import duckdb
import pytest

from .adaptive_research import discovery_catalog, bounded_payload
from .authorized_foundation import (EffectiveScope, SourcePolicy, ResearchBinding,
    DiscoveredSource, AuthorizedFoundationExecutor)
from .ask_verifier import AskRegistry
from .contracts import Column, ExploratoryQueryProposal
from .validator import validate


def test_source_index_exposes_alternatives_without_authority():
    scope = EffectiveScope('u', 'o', 'w', frozenset({'read'}))
    sources = tuple(DiscoveredSource(name, name, tuple(Column(c, 'VARCHAR') for c in cols), ())
        for name, cols in [('old_fact', ('key', 'line', 'amount')),
                           ('new_fact', ('key', 'name', 'day', 'amount')),
                           ('secret', ('private',))])
    binding = ResearchBinding(resolve_scope=lambda: scope, scope=scope, publication='p', snapshot=1,
        sources=sources, policies=tuple(SourcePolicy(s.name, 'read', 'o', 'w',
            ('key', 'name', 'day') if s.name == 'new_fact' else None, True) for s in sources[:2]),
        investigation_id='test')
    try:
        wire = discovery_catalog(binding.context.catalog, {'old_fact'})
        index = {t['name']: t for t in wire['source_index']}
        assert set(index) == {'old_fact', 'new_fact'}
        assert [wire['source_column_dictionary'][i] for i in index['new_fact']['columns']] == ['key', 'name', 'day']
        assert index['old_fact']['permission'] == index['new_fact']['permission']
        assert [t['name'] for t in wire['tables']] == ['old_fact']
        assert 'proves no rows' in wire['discovery_protocol']
        assert bounded_payload(dict(catalog=wire, observations=[]))['catalog'] == wire
    finally:
        binding.close()


@pytest.mark.parametrize('typ,expected', [('DATE', '2024-02-29'), ('TIMESTAMP', '2024-02-29T13:14:15.123456')])
@pytest.mark.parametrize('conditional', [False, True])
def test_temporal_sql_cells_survive_verifier_and_render(tmp_path, monkeypatch, typ, expected, conditional):
    from . import foundation
    monkeypatch.setattr(foundation, 'host_read_preflight', lambda: {'safe': True})
    path = tmp_path / 'source.duckdb'
    with duckdb.connect(str(path), config={'threads': '1'}) as db:
        db.execute(f'CREATE TABLE events(day {typ})')
        db.execute("INSERT INTO events VALUES ('2024-02-29 13:14:15.123456'), (NULL)")
    @contextmanager
    def session(*, read_only):
        assert read_only
        with duckdb.connect(':memory:', config={'threads': '1'}) as db:
            db.execute(f"ATTACH '{path}' AS telchi (READ_ONLY)")
            yield db
    access = SimpleNamespace(foundation_publication_id='p', ducklake_snapshot_id=1)
    reader = SimpleNamespace(connector=SimpleNamespace(session=session), resolve_on=lambda db: access)
    scope = EffectiveScope('u', 'o', 'w', frozenset({'read'}))
    binding = ResearchBinding(resolve_scope=lambda: scope, scope=scope, publication='p', snapshot=1,
        sources=(DiscoveredSource('events', 'telchi.main.events', (Column('day', typ),), ()),),
        policies=(SourcePolicy('events', 'read', 'o', 'w', None, True),), investigation_id='test')
    registry = AskRegistry(binding.context, executor_factory=lambda context, **kwargs:
        AuthorizedFoundationExecutor(context, reader=reader))
    try:
        field = "CASE WHEN day >= '2024-02-01' THEN day ELSE NULL END" if conditional else 'day'
        p = ExploratoryQueryProposal(f'SELECT min({field}) AS first_day FROM events',
            'test', 'test', ('events',), 'aggregate', 'observed')
        _, query = validate(p, binding.context)
        with AuthorizedFoundationExecutor(binding.context, reader=reader) as executor:
            _, result = executor.execute(p, binding.context)
        assert result.status == 'COMPLETED'
        assert type(result.rows[0][0]) is (date if typ == 'DATE' else datetime)
        manifest = registry.register(query, result, result.rows)
        claim = dict(kind='executed_cell', result_id=manifest['result_id'],
            row_id=manifest['row_ids'][0], column_id=manifest['columns'][0]['column_id'])
        checked = registry.verify(claim)
        assert checked['match'], checked
        assert checked['value'] == expected
        evidence = checked['evidence'][0]
        assert (evidence['sql_type'], evidence['source'], evidence['publication'], evidence['snapshot']) == (typ, 'events', 'p', '1')
        assert evidence['temporal_scope'] == ('published_rows', 'not_complete_calendar')
        assert expected in registry.render([checked])
        assert not registry.verify(claim | {'value': '1999-01-01'})['match']
        assert not registry.verify(claim | {'column_id': 'made_up'})['match']
        # A string/incorrect runtime type must not become a typed date by looking ISO-like.
        entry = registry.entries[manifest['result_id']]
        registry.entries[manifest['result_id']] = (*entry[:3], ((expected,),), *entry[4:])
        assert not registry.verify(claim)['match']
        registry.entries[manifest['result_id']] = entry
        registry.entries[manifest['result_id']] = (entry[0], entry[1], replace(entry[2], truncated=True), *entry[3:])
        assert not registry.verify(claim)['match']
    finally:
        registry.close()
        binding.close()
