"""Tiny local fixtures, NOT evidence of a real Foundation read or Luna run."""
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import duckdb
import pytest

from . import foundation as f
from .contracts import Decision, ExploratoryQueryProposal
from .direct_readonly import DirectReadonlyExecutor
from .validator import validate


def proposal(sql='SELECT sum(line_total) AS amount FROM sales_line', sources=('sales_line',)):
    return ExploratoryQueryProposal(sql, 'control', 'local test', sources, 'total', 'amount')


@pytest.fixture
def reader(tmp_path, monkeypatch):
    path = tmp_path / 'fixture.duckdb'
    with duckdb.connect(str(path)) as db:
        db.execute('CREATE TABLE docs(source_system VARCHAR, source_table VARCHAR, canceled VARCHAR, doc_entry VARCHAR, doc_num VARCHAR, doc_date VARCHAR, currency VARCHAR, slp_code VARCHAR, series VARCHAR, sales_channel_code VARCHAR, sales_channel_semantic_status VARCHAR, raw_extraction_id VARCHAR)')
        db.execute("INSERT INTO docs VALUES ('SAP_B1_HANA','OINV','N','1','10','2026-08-05','BS','7','9',NULL,'UNKNOWN','r1'), ('SAP_B1_HANA','OINV','N','2','20','2026-07-01','BS','8','9','SALON','CONFIRMED','r1'), ('OTHER_CLIENT','OINV','N','3','30','2026-08-05','BS','8','9',NULL,'UNKNOWN','r1')")
        db.execute("ALTER TABLE docs ADD COLUMN source_as_of VARCHAR DEFAULT '2026-09-01'")
        db.execute('CREATE TABLE lines(source_system VARCHAR, source_table VARCHAR, doc_entry VARCHAR, line_num VARCHAR, item_code VARCHAR, currency VARCHAR, line_total VARCHAR, raw_extraction_id VARCHAR)')
        db.execute("INSERT INTO lines VALUES ('SAP_B1_HANA','INV1','1','0','L02822','BS','12.34','r1'), ('SAP_B1_HANA','INV1','1','1','OTHER_SKU','BS','999','r1'), ('SAP_B1_HANA','INV1','2','0','L02822','BS','100','r1'), ('OTHER_CLIENT','INV1','3','0','L02822','BS','900','r1')")
        db.execute("ALTER TABLE lines ADD COLUMN source_as_of VARCHAR DEFAULT '2026-09-01'")
    opened = []
    @contextmanager
    def session(*, read_only):
        assert read_only is True
        opened.append(True)
        with duckdb.connect() as db:
            db.execute(f"ATTACH '{path}' AS telchi (READ_ONLY)")
            yield db
    access = SimpleNamespace(foundation_publication_id=f.PUBLICATION, ducklake_snapshot_id=int(f.SNAPSHOT),
                             sales=lambda table: 'telchi.main.' + ('docs' if table == 'sales_document' else 'lines'))
    result = SimpleNamespace(connector=SimpleNamespace(session=session), resolve_on=lambda db: access,
                             access=access, opened=opened)
    monkeypatch.setattr(f, 'host_read_preflight', lambda: dict(safe=True))
    return result


def test_binding_fixture_only(reader):
    context = f.local_context('fixture')
    with f.FoundationReadonlyExecutor(context, reader=reader) as executor:
        decision, result = executor.execute(proposal(), context)
    assert decision.decision == Decision.ALLOW, result
    assert result.status == 'COMPLETED', result
    assert str(result.rows[0][0]) == '12.340000'
    assert result.source == f.CATALOG.dataset
    assert (result.publication, result.snapshot) == (f.PUBLICATION, f.SNAPSHOT)


@pytest.mark.parametrize('change', ['publication', 'snapshot'])
def test_changed_binding_never_runs_model_sql(reader, change):
    setattr(reader.access, 'foundation_publication_id' if change == 'publication' else 'ducklake_snapshot_id', 'changed')
    context = f.local_context('fixture')
    with f.FoundationReadonlyExecutor(context, reader=reader) as executor:
        decision, result = executor.execute(proposal(), context)
    assert decision.decision != Decision.ALLOW
    assert result.status == 'NOT_EXECUTED' and not result.rows


@pytest.mark.parametrize('sql', ["SELECT * FROM read_parquet('/etc/passwd')", 'DELETE FROM sales_line',
                               'SELECT doc_entry FROM telchi.atomic.sales_document',
                               'SELECT line_total FROM sales_line; SELECT 1',
                               'SELECT * FROM duckdb_tables()', 'SELECT amount FROM invoices'])
def test_denied_before_open(reader, sql):
    context = f.local_context('fixture')
    with f.FoundationReadonlyExecutor(context, reader=reader) as executor:
        decision, result = executor.execute(proposal(sql), context)
    assert decision.decision != Decision.ALLOW
    assert not reader.opened and result.status == 'NOT_EXECUTED'


@pytest.mark.parametrize('changes', [dict(permissions=frozenset({'FULL_ACCESS'})),
    dict(organization='OTHER_CLIENT'), dict(snapshot='latest'), dict(identity='external-user'),
    dict(workspace='other'), dict(environment='production')])
def test_authority_is_scoped(reader, changes):
    context = f.local_context('fixture')
    altered = replace(context, **changes)
    with f.FoundationReadonlyExecutor(context, reader=reader) as executor:
        decision, result = executor.execute(proposal(), altered)
    assert decision.decision == Decision.DENY
    assert not reader.opened


def test_pressure_blocks_before_reader(reader, monkeypatch):
    monkeypatch.setattr(f, 'host_read_preflight', lambda: dict(safe=False))
    context = f.local_context('fixture')
    with f.FoundationReadonlyExecutor(context, reader=reader) as executor:
        decision, result = executor.execute(proposal(), context)
    assert decision.decision == Decision.RESOURCE_BLOCKED
    assert result.limitations == ('BLOCKED_HOST',) and not reader.opened


def test_independent_control_fixture_only(reader):
    from .foundation_verifier import control_proposals, verify_control
    context = f.local_context('fixture')
    with f.FoundationReadonlyExecutor(context, reader=reader) as executor:
        results = [executor.execute(p, context)[1] for p in control_proposals()]
    check = verify_control(context, results)
    assert check['state'] == 'VERIFIED_WITH_LIMITATIONS', check
    assert check['total'] == '12.340000' and check['null_channel_lines'] == 1
    assert check['document_count'] == 1
    assert verify_control(context, [replace(results[0], truncated=True), *results[1:]])['state'] == 'BLOCKED'
    assert verify_control(context, [replace(results[0], rows=((500,),)), *results[1:]])['state'] == 'BLOCKED'
    duplicated = replace(results[2], rows=results[2].rows * 2, returned_count=2)
    assert verify_control(context, [*results[:2], duplicated])['reason'] == 'duplicate_or_null_documentary_key'


@pytest.mark.parametrize('field,value,reason', [
    ('currency', 'USD', 'population_period_or_currency_mismatch'),
    ('raw_extraction_id', 'different', 'header_line_lineage_mismatch'),
    ('line_total', None, 'invalid_line_amount'),
    ('doc_entry', 'missing', 'orphan_line'),
])
def test_independent_control_rejects_bad_reference(reader, field, value, reason):
    from .foundation_verifier import control_proposals, verify_control
    context = f.local_context('fixture')
    with f.FoundationReadonlyExecutor(context, reader=reader) as executor:
        results = [executor.execute(p, context)[1] for p in control_proposals()]
    position = [c.name for c in f.CATALOG.tables[1].columns].index(field)
    row = list(results[2].rows[0])
    row[position] = value
    results[2] = replace(results[2], rows=(tuple(row),))
    assert verify_control(context, results)['reason'] == reason


def test_readwrite_catalog_is_rejected(reader):
    original = reader.connector.session
    @contextmanager
    def session(*, read_only):
        with original(read_only=read_only) as db:
            db.execute('DETACH telchi')
            db.execute("ATTACH ':memory:' AS telchi")
            yield db
    reader.connector.session = session
    context = f.local_context('fixture')
    with f.FoundationReadonlyExecutor(context, reader=reader) as executor:
        decision, result = executor.execute(proposal(), context)
    assert decision.decision != Decision.ALLOW and result.status == 'NOT_EXECUTED'


def test_no_fixture_authority_reused():
    context = f.local_context('fixture')
    with pytest.raises(ValueError, match='synthetic_context_required'):
        DirectReadonlyExecutor(context)


def test_joins_do_not_raise_resource_budget():
    context = f.local_context('fixture')
    decision, query = validate(proposal('SELECT sum(l.line_total) AS amount FROM sales_line l JOIN sales_document d ON l.doc_entry=d.doc_entry', ('sales_line', 'sales_document')), context)
    assert query is None and decision.decision != Decision.ALLOW
