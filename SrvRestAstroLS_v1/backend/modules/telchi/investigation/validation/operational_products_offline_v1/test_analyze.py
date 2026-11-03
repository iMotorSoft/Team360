"""Offline rule and artifact regression; never opens the operational catalog."""
import json
from pathlib import Path

import duckdb
import pytest

from .analyze import production_rule, selective_query, digest


def test_selective_boundaries_and_parameterization():
    keys = ["A' OR 1=1 --", 'B']
    sql, params = selective_query(keys)
    assert keys[0] not in sql and params == keys and sql.count('?') == 2
    assert ' > ?' not in sql
    for bad in [[], ['A']*2, ['B','A'], [''], [str(i).zfill(2) for i in range(26)]]:
        with pytest.raises(ValueError):
            selective_query(bad)
    assert selective_query([str(i).zfill(2) for i in range(25)])[0].count('?') == 25


def test_production_requires_effective_documentary_link():
    with duckdb.connect() as c:
        c.execute('SET threads=1')
        c.execute('CREATE TABLE o(DocEntry INTEGER, Type VARCHAR, Status VARCHAR)')
        c.execute("INSERT INTO o VALUES (1,'S','R'),(2,'D','L'),(3,'S','C')")
        c.execute('CREATE TABLE i(ItemCode VARCHAR,CANCELED VARCHAR,BaseType INTEGER,Quantity VARCHAR,BaseEntry INTEGER)')
        cases = [('ok','N',202,'1',1),('generic','N',-1,'1',1),('orphan','N',202,'1',99),
            ('canceled','Y',202,'1',1),('reversal','C',202,'1',1),('zero','N',202,'0',1),
            ('negative','N',202,'-1',1),('unknown_qty','N',202,None,1),
            ('disassembly','N',202,'1',2),('canceled_order','N',202,'1',3)]
        c.executemany('INSERT INTO i VALUES (?,?,?,?,?)',cases)
        got = c.execute('SELECT i.ItemCode FROM i LEFT JOIN o ON i.BaseEntry=o.DocEntry WHERE '+production_rule()).fetchall()
        assert got == [('ok',)]
        # An open OWOR without a posted issue is not projected into the universe.
        c.execute("INSERT INTO o VALUES (4,'S','R')")
        assert c.execute('SELECT count(*) FROM i LEFT JOIN o ON i.BaseEntry=o.DocEntry WHERE '+production_rule()).fetchone()[0] == 1


def test_report_reconciles_evidence_and_exact_pending_set():
    root = Path(__file__).resolve().parents[7]/'data/reports/telchi/operational-products-offline-20261029-v2'
    if not root.exists():
        pytest.fail(f'Missing real offline evidence: {root}')
    r = json.loads((root/'report.json').read_text())
    products = json.loads((root/'products.json').read_text())
    plan = json.loads((root/'selective_plan.json').read_text())
    keys = [p['ItemCode'] for p in products]
    assert keys == sorted(set(keys))
    assert plan['item_codes'] == [p['ItemCode'] for p in products if not p['captured']]
    assert [k for b in plan['batches'] for k in b['parameters']] == plan['item_codes']
    assert all(1 <= len(b['parameters']) <= 25 for b in plan['batches'])
    counts = r['counts']
    assert counts['total'] == len(keys) == counts['covered']+counts['pending']
    assert counts['total'] == counts['sales_including_returns']+counts['production_effective_observed']-counts['both']
    assert counts['covered'] == sum(x['products'] for x in r['classification'])
    assert counts['explicit_physical']+counts['without_explicit_physical'] == len(keys)
    with duckdb.connect() as c:
        c.execute('SET threads=2')
        path = str(root/'evidence.parquet')
        assert c.execute('SELECT count(DISTINCT item_code) FROM read_parquet(?)',[path]).fetchone()[0] == len(keys)
        n, distinct = c.execute('SELECT count(*),count(DISTINCT(event_kind,doc_entry,line_num)) FROM read_parquet(?)',[path]).fetchone()
        assert n == distinct
        ref = Path(r['inventory']['foundation']['reference_path'])
        crosswalk = ref.parents[2]/'crosswalk/_versions'/ref.name/'product_crosswalk/part-00000.parquet'
        reference = c.execute("SELECT source_native_id,canonical_product_id FROM read_parquet(?) WHERE source_system='SAP_HANA'",[str(ref/'products/part-00000.parquet')]).fetchall()
        cw = c.execute("SELECT source_native_id,canonical_id FROM read_parquet(?) WHERE source_system='SAP_HANA'",[str(crosswalk)]).fetchall()
        assert len(cw) == len(dict(cw))
        assert dict(reference) == dict(cw)
        assert counts['operational_missing_reference'] == len(set(keys)-dict(reference).keys())
    assert digest(root/'evidence.parquet') == r['evidence_sha256']
    assert r['safety']['hana_queries'] == 0
    hashes = json.loads((root/'artifact_hashes.json').read_text())
    assert all(digest(root/name) == expected for name,expected in hashes.items())
