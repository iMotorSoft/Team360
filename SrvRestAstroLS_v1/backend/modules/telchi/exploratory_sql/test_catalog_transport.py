"""Full-source transport regressions, independent of private Foundation data."""
import asyncio
import copy
from dataclasses import asdict, replace
import threading
from types import SimpleNamespace

import pytest

from .adaptive_research import bounded_payload, discovery_catalog
from .adaptive_sources import CATALOG, context_for_run
from .contracts import Column, LogicalTable
from .validator import canonical


def catalog_payload(count=70, unique=False):
    return dict(observations=[], catalog=dict(tables=[dict(
        name=f'published_{n}', grain=['document', 'line'],
        columns=[dict(name=f'published_column_{n if unique else 0}_{c}',
                      sql_type='VARCHAR', nullable=False) for c in range(24)],
        semantic_constraints=['Schema discovery is not business accreditation.'])
        for n in range(count)]))


def test_all_70_sources_and_columns_survive_lossless_dictionary_transport():
    payload = catalog_payload()
    original = copy.deepcopy(payload)
    compact = bounded_payload(payload)
    assert len(canonical(compact).encode()) <= 32768
    catalog = compact['catalog']
    assert len(catalog['tables']) == 70
    assert 'column_dictionary' in catalog
    for expected, actual in zip(payload['catalog']['tables'], catalog['tables']):
        restored = [catalog['column_dictionary'][i] for i in actual['columns']]
        assert actual['name'] == expected['name']
        assert actual['grain'] == expected['grain']
        assert [(name, catalog['column_type_dictionary'][kind]) for name, kind in restored] == [
            (c['name'], c['sql_type']) for c in expected['columns']]
        assert [catalog['semantic_constraint_dictionary'][i] for i in actual['semantic_constraints']] == expected['semantic_constraints']
    assert payload == original


def test_future_uncompressible_publication_fails_before_model_not_silently_truncated():
    with pytest.raises(RuntimeError, match='observation_byte_budget'):
        bounded_payload(catalog_payload(count=150, unique=True))


def test_progressive_index_covers_every_source_and_preserves_exact_selected_schema():
    tables = tuple(LogicalTable(f'domain_{n}', (Column('exact_column', 'VARCHAR', True),),
                               'permission', ('exact_column',), 100) for n in range(70))
    catalog = replace(CATALOG, tables=tables)
    initial = discovery_catalog(catalog, set())
    assert len(initial['source_index']) == 70 and initial['tables'] == []
    for table in tables:
        loaded = discovery_catalog(catalog, {table.name})
        assert loaded['tables'] == [asdict(table)]
        assert len(canonical(bounded_payload(dict(catalog=loaded, observations=[]))).encode()) <= 32768
    crossed = discovery_catalog(catalog, {'domain_0', 'domain_69'})
    assert {t['name'] for t in crossed['tables']} == {'domain_0', 'domain_69'}
    assert len(catalog.tables) == 70  # transport does not mutate authorization


def test_discovery_controller_replaces_schemas_without_sql_or_extra_model_router(monkeypatch):
    from . import adaptive_research as runner
    tables = tuple(LogicalTable(t['name'], tuple(Column(c['name'], c['sql_type']) for c in t['columns']),
                               'permission', tuple(t['grain']), 100, tuple(t['semantic_constraints']))
                   for t in catalog_payload(unique=True)['catalog']['tables'])
    context = replace(context_for_run(), catalog=replace(CATALOG, tables=tables))
    authorizations = []
    monkeypatch.setattr(runner, 'authorize', lambda ctx: authorizations.append(ctx))

    class Probe:
        calls = []
        def __init__(self, **kwargs): pass
        async def next(self, *args, **kwargs): return {'ready': True}

    seen = []
    class Model:
        calls = []
        async def next(self, payload, **kwargs):
            seen.append(payload)
            if len(seen) == 1:
                return dict(action='discover', requested_sources=['not_authorized'])
            if len(seen) == 2:
                return dict(action='discover', requested_sources=['published_0', 'published_69'])
            if len(seen) == 3:
                return dict(action='discover', requested_sources=['published_35'])
            return dict(action='clarify', question='¿Qué período desea?')

    class Executor:
        def __init__(self, *args, **kwargs): self.cancel = threading.Event()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args, **kwargs): pytest.fail('Metadata discovery must not execute SQL')

    monkeypatch.setattr(runner, 'LunaSQL', Probe)
    report = {}
    registry = SimpleNamespace(entries={}, audit=[], close=lambda: None)
    asyncio.run(runner.run(report, lambda _: None, luna=Model(), context=context,
                          executor_factory=Executor, registry_factory=lambda _: registry))
    assert report['status'] == 'NEEDS_CLARIFICATION'
    assert len(seen) == 4 and not report['turns']
    assert report['catalog_discoveries'] == [['published_0', 'published_69'], ['published_35']]
    assert seen[0]['catalog']['tables'] == []
    assert {t['name'] for t in seen[2]['catalog']['tables']} == {'published_0', 'published_69'}
    assert {t['name'] for t in seen[3]['catalog']['tables']} == {'published_35'}
    assert all(len(p['catalog']['source_index']) == 70 for p in seen)
    assert all(len(canonical(p).encode()) <= 32768 for p in seen)
    assert len(authorizations) >= 4  # discovery never caches authority


def test_new_cross_domain_source_remains_accessible():
    compact = bounded_payload(catalog_payload(count=71))
    assert {t['name'] for t in compact['catalog']['tables']} == {f'published_{n}' for n in range(71)}
