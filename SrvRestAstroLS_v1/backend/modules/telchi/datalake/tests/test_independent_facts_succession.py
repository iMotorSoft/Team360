from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from modules.telchi.datalake import independent_facts_succession as facts
from modules.telchi.datalake import full_refresh_capture as cap
from modules.telchi.datalake import sales_incremental as inc
from modules.telchi.datalake.create_initial import transform
from modules.telchi.datalake.foundation_publication import ComponentReference, FoundationPublication, FoundationReaderError
from modules.telchi.datalake.sales_facts_transition import NAMES, uses_sealed_sales
from modules.telchi.datalake.sales_foundation_promotion import load_candidate
from modules.telchi.datalake.tests.test_full_refresh_capture import Guard
from modules.telchi.runtime.config import DuckDBSafetyProfile


class StockSource:
    def __init__(self, budget):
        self.limits, self.query_log = budget.transport(), []
        self.clock = '2026-11-01T12:00:00'
        self.rows = [dict(ItemCode='A', WhsCode='01', OnHand='12.25', IsCommited='2', OnOrder='3'),
                     dict(ItemCode='Ñ"B', WhsCode='01', OnHand='4', IsCommited='0', OnOrder='1')]

    def query_read_only(self, name, sql, params=()):
        self.query_log.append(dict(query_id=name))
        if 'clock' in name:
            return [dict(utc=self.clock, source_local='2026-11-01T08:00:00', source_date='2026-11-01')]
        return [dict(rows=len(self.rows), **{'sum_'+f:str(sum(Decimal(r[f]) for r in self.rows))
                                            for f in ('OnHand','IsCommited','OnOrder')})]

    def stream_read_only(self, *args, **kwargs):
        yield self.rows


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(inc, 'DATA_ROOT', tmp_path)
    directory = tmp_path/'raw/sap'/cap.CONTRACT/'cycle/inventory'
    budget = cap.DomainBudget(10, 120, 100)
    source = StockSource(budget)
    session = cap.CaptureSession(directory, source, budget, guard=Guard(),
        profile=DuckDBSafetyProfile(temp_directory=tmp_path/'temp'))
    result = session.capture('stock', facts.STOCK_SQL, keys=['ItemCode','WhsCode'],
        sums=['OnHand','IsCommited','OnOrder'], semantic_scope=dict(kind='CURRENT_STOCK_STATEMENT_SNAPSHOT',history_rebuilt=False))
    reference = tmp_path/'reference/_versions/ref'
    with duckdb.connect() as con:
        for dataset, query in [('products', '''SELECT 'SAP_HANA' AS source_system, unnest(['A','Ñ"B']) AS item_code, 'UNIT' AS inventory_uom_id'''),
                               ('warehouses', "SELECT 'SAP_HANA' AS source_system,'01' AS code")]:
            path = reference/dataset/'part-00000.parquet'
            path.parent.mkdir(parents=True)
            con.execute('COPY ('+query+') TO '+facts.literal(path)+' (FORMAT PARQUET)')
    catalog = {n:ComponentReference(n, n+'_old',source_as_of='2026-09-24T00:00:00+00:00')
               for n in ('reference','sales','credit_memo','oinm','oitw')}
    catalog['reference'] = ComponentReference('reference','ref',source_as_of='2026-09-24T00:00:00+00:00')
    components = {n:catalog[n].as_dict() if n in catalog else dict(name=n,publication_id=n+'_old',source_as_of='2026-09-24T00:00:00+00:00') for n in NAMES}
    base = FoundationPublication('foundation_base','base',reference_version='ref',components=catalog,
        manifest=dict(foundation_publication_id='foundation_base',components=components,base_snapshot_id=1322,
                      facts_base_snapshot_id=1408, permission='UNCHANGED',sales_facts_revalidation={'sealed':'unchanged'}))
    candidate = facts.make_candidate(base, directory/'stock', tmp_path/'staging/cycle')
    previous = tmp_path/'previous.parquet'
    with duckdb.connect() as con:
        con.execute('COPY (SELECT * FROM read_parquet(?) WHERE item_code=?) TO '+facts.literal(previous)+' (FORMAT PARQUET)',
                    [candidate.manifest['components']['oitw']['independent_facts_contract']['dataset']['path'],'A'])
    monkeypatch.setattr(facts, 'previous_relation', lambda base:'read_parquet('+facts.literal(previous)+')')
    class Store:
        @contextmanager
        def connection_factory(self):
            with duckdb.connect() as con:
                yield con
    return base, candidate, Store(), source, result, previous


def validate(prepared):
    base, candidate, store, *_ = prepared
    return facts.validate_transition(store,candidate,base,base.manifest['components'])


def resign(candidate):
    stable = facts.stock_contract(candidate.manifest)
    sha = inc.digest(stable)
    ref = ComponentReference('oitw','oitw_'+sha[:24],content_identity=sha,
        source_as_of=stable['evidence']['observation_start'],row_count=stable['dataset']['row_count'])
    candidate.components['oitw'] = ref
    candidate.manifest['components']['oitw'] = dict(ref.as_dict(),independent_facts_contract=stable)
    candidate.foundation_publication_id = 'foundation_'+inc.digest(dict(
        base=candidate.previous_foundation_publication_id, components=candidate.manifest['components'],
        proof=candidate.manifest['independent_facts_succession']))[:32]
    candidate.manifest['foundation_publication_id'] = candidate.foundation_publication_id


def test_full_stock_successor_retains_all_other_components(prepared):
    base, candidate, _, source, result, _ = prepared
    assert validate(prepared) == candidate.manifest['components']
    assert uses_sealed_sales(candidate.manifest)
    stable = facts.stock_contract(candidate.manifest)
    path = stable['dataset']['path']
    with duckdb.connect() as con:
        rows = con.execute('SELECT * FROM read_parquet(?) ORDER BY item_code',[path]).fetchall()
        names = [r[0] for r in con.description]
    canonical = transform('inventory',source.rows,dict(source_as_of=stable['evidence']['observation_start'],
        extraction_id=result['plan_sha256'], reference_version='ref',
        reference_manifest_hash=str(inc.DATA_ROOT/'reference/_versions/ref'))).tables['inventory_balance']
    assert [dict(zip(names,r)) for r in rows] == canonical
    assert len(source.query_log) == 4  # Validation never calls source.
    for name in NAMES-{'oitw'}:
        assert candidate.manifest['components'][name] == base.manifest['components'][name]
    assert load_candidate(Path(path).parent/'foundation-candidate.json').as_row() == candidate.as_row()
    assert stable['evidence']['historical_stock_available'] is False


@pytest.mark.parametrize('field,value', [('permission','ELEVATED'),('base_snapshot_id',1323),
    ('facts_base_snapshot_id',1492),('sales_facts_revalidation',{}),('sales_coverage',[])])
def test_reject_inherited_semantic_permission_snapshot_changes(prepared, field, value):
    prepared[1].manifest[field] = value
    with pytest.raises(FoundationReaderError, match='inherited business'):
        validate(prepared)


@pytest.mark.parametrize('name', sorted(NAMES-{'oitw'}))
def test_reject_unaffected_component_change(prepared,name):
    prepared[1].manifest['components'][name]['publication_id'] += '_changed'
    with pytest.raises(FoundationReaderError):
        validate(prepared)


def test_reject_corrupt_hash(prepared):
    stable = facts.stock_contract(prepared[1].manifest)
    Path(stable['dataset']['path']).write_bytes(b'corrupt')
    with pytest.raises(FoundationReaderError, match='physical hash'):
        validate(prepared)


@pytest.mark.parametrize('mode,match', [('quantity','source quantity|source replay'),
    ('same_total','source replay'),('atomic_identity','source replay'),('metadata','source replay'),
    ('duplicate','duplicate'),('schema','schema incompatible')])
def test_reject_self_attested_dataset_even_with_recomputed_hash(prepared, mode, match):
    candidate = prepared[1]
    stable = facts.stock_contract(candidate.manifest)
    path = Path(stable['dataset']['path'])
    with duckdb.connect() as con:
        con.execute('CREATE TABLE altered AS SELECT * FROM read_parquet(?)',[str(path)])
        if mode == 'quantity':
            con.execute("UPDATE altered SET on_hand='99' WHERE item_code='A'")
        elif mode == 'same_total':
            con.execute("UPDATE altered SET on_hand=CASE WHEN item_code='A' THEN '13.25' ELSE '3' END")
        elif mode == 'atomic_identity':
            con.execute("UPDATE altered SET atomic_id='forged_identity' WHERE item_code='A'")
        elif mode == 'metadata':
            con.execute("UPDATE altered SET raw_extraction_id='forged_lineage'")
        elif mode == 'duplicate':
            con.execute('INSERT INTO altered SELECT * FROM altered LIMIT 1')
        else:
            con.execute('ALTER TABLE altered DROP COLUMN source_table')
        con.execute('COPY altered TO '+facts.literal(path)+' (FORMAT PARQUET)')
    stable['dataset']['sha256'] = inc.file_hash(path)
    resign(candidate)
    with pytest.raises(FoundationReaderError, match=match):
        validate(prepared)


def test_reject_capture_checkpoint_corruption(prepared):
    stable = facts.stock_contract(prepared[1].manifest)
    path = Path(stable['evidence']['capture_directory'])/'checkpoint-00000.json'
    path.write_text('{}')
    with pytest.raises(ValueError,match='CHECKPOINT_CONFLICT'):
        validate(prepared)


def test_reject_loss_of_historical_identity(prepared):
    previous = prepared[-1]
    with duckdb.connect() as con:
        con.execute('CREATE TABLE changed AS SELECT * FROM read_parquet(?)',[str(previous)])
        con.execute("UPDATE changed SET atomic_id='different_historical_identity'")
        con.execute('COPY changed TO '+facts.literal(previous)+' (FORMAT PARQUET)')
    with pytest.raises(FoundationReaderError,match='loss of historical position'):
        validate(prepared)


def test_reject_unresolved_reference(prepared):
    path = inc.DATA_ROOT/'reference/_versions/ref/products/part-00000.parquet'
    with duckdb.connect() as con:
        con.execute("COPY (SELECT 'SAP_HANA' AS source_system,'A' AS item_code) TO "+facts.literal(path)+' (FORMAT PARQUET)')
    with pytest.raises(FoundationReaderError,match='unresolved Reference'):
        validate(prepared)


def test_reject_observation_regression(prepared):
    base = prepared[0]
    base.manifest['components']['oitw']['source_as_of'] = '2026-11-02T00:00:00+00:00'
    candidate = prepared[1]
    candidate.manifest['independent_facts_succession']['base_manifest_sha256'] = inc.digest(base.manifest)
    facts.stock_contract(candidate.manifest)['base_manifest_sha256'] = inc.digest(base.manifest)
    resign(candidate)
    with pytest.raises(FoundationReaderError,match='observation did not advance'):
        validate(prepared)


def test_successive_stock_observation_and_reader(prepared, monkeypatch):
    from types import SimpleNamespace
    from modules.telchi.datalake.foundation_reader import FoundationAccess
    base, first, store, *_ = prepared
    directory = inc.DATA_ROOT/'raw/sap'/cap.CONTRACT/'next-cycle/inventory'
    budget = cap.DomainBudget(10,120,100)
    source = StockSource(budget)
    source.clock = '2026-11-02T12:00:00'
    source.rows[0]['OnHand'] = '7.5'
    session = cap.CaptureSession(directory,source,budget,guard=Guard())
    session.capture('stock',facts.STOCK_SQL,keys=['ItemCode','WhsCode'],sums=['OnHand','IsCommited','OnOrder'],
        semantic_scope=dict(kind='CURRENT_STOCK_STATEMENT_SNAPSHOT',history_rebuilt=False))
    second = facts.make_candidate(first,directory/'stock',inc.DATA_ROOT/'staging/next-cycle')
    monkeypatch.setattr(facts,'previous_relation',lambda base:facts.relation(base.manifest))
    facts.validate_transition(store,second,first,first.manifest['components'])
    assert second.foundation_publication_id != first.foundation_publication_id
    access = FoundationAccess(SimpleNamespace(reference_version='ref'),1408,0,
        inc.DATA_ROOT/'reference/_versions/ref',second.manifest,1322)
    with duckdb.connect() as con:
        result = con.execute('SELECT item_code,inventory_uom_id,on_hand_qty,available_qty,stock_as_of FROM '+access.stock_availability()+' ORDER BY item_code').fetchall()
        reader = facts.verify_reader(con,access)
        assert reader['rows'] == 2 and reader['unknown_inventory_uom_rows'] == 0
    assert result[0] == ('A','UNIT',Decimal('7.5'),Decimal('5.5'),'2026-11-02T12:00:00+00:00')
    assert 'AT (VERSION => 1408)' in access.oinm()


@pytest.mark.parametrize('change', ['kind','sales_proof','ancestry'])
def test_stock_dispatch_cannot_bypass_canonical_validation(prepared,change):
    manifest = deepcopy(prepared[1].manifest)
    if change == 'kind':
        manifest['candidate_kind'] = 'FOUNDATION_BASE_V1'
    elif change == 'sales_proof':
        manifest.pop('sales_facts_revalidation')
    else:
        manifest.pop('independent_facts_succession')
    with pytest.raises(FoundationReaderError,match='validated succession ancestry'):
        facts.relation(manifest)


def test_no_overwrite_candidate_or_capture(prepared):
    base, candidate, _, _, _, _ = prepared
    stable = facts.stock_contract(candidate.manifest)
    with pytest.raises(FileExistsError):
        facts.make_candidate(base,stable['evidence']['capture_directory'],Path(stable['dataset']['path']).parent)
