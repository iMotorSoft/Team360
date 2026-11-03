"""Pure decimal contracts + audit of persisted live evidence, no external services."""
import csv
import json
from decimal import Decimal as D
from pathlib import Path
import pytest
from modules.telchi.investigation.validation.iva_bolivia_13_v1.reconcile import classification, stats

REPORT = Path(__file__).resolve().parents[7] / 'data/reports/telchi/iva-bolivia-13-v1/verified'


@pytest.mark.parametrize('a,b,expected', [
    ('25','21.75','exact'), ('25','21.749','tolerance'),
    ('25','21.74','tolerance'), ('25','21.760001','exception'),
    ('25','25','exception'), ('0','0','exact'),
    ('33241.04','35392.90','exception'),
])
def test_exact_decimal_boundaries(a,b,expected):
    c,d,e,label = classification(D(a),D(b))
    assert label == expected
    assert c == D(a)-D(b) and d == D(a)*D('.13') and e == c-d


def test_included_tax_is_not_113():
    assert D('21.75')/D('.87') == D('25')
    assert D('21.75')*D('1.13') != D('25')


def test_bands_preserve_every_residual():
    rows = []
    for a,b in [('25','21.75'),('25','21.749'),('25','25'),('33241.04','35392.90')]:
        c,d,e,m = classification(D(a),D(b))
        rows.append(dict(C=c,D=d,E=e,match=m))
    s = stats(rows)
    assert sum(r['documents'] for r in s['bands']) == len(rows)
    assert sum(r['residual'] for r in s['bands']) == s['aggregate_residual']


@pytest.fixture(scope='module')
def evidence():
    return json.loads((REPORT/'reconciliation.json').read_text()), json.loads((REPORT/'diagnostics.json').read_text())


def test_live_source_parity(evidence):
    j,_ = evidence
    assert j['lineage']['ducklake_snapshot_id'] == 1408
    assert j['raw_parity'] == {'matched_raw_line':65163}
    assert j['tax_bridge']['complete_documents'] == 30301
    assert j['sap_write_count'] == 0


def test_live_exclusive_partition(evidence):
    j,d = evidence
    assert sum(v['documents'] for v in d['exclusive_partition'].values()) == 30301
    assert sum(D(v['E']) for v in d['exclusive_partition'].values()) == D(j['summary']['aggregate_residual'])
    assert j['summary']['counts'] == dict(exact=14467,tolerance=12841,exception=2993)
    assert d['exclusive_partition']['3_other_registered_tax_treatment']['documents'] == 890


def test_live_currency_is_independent(evidence):
    _,d = evidence
    for source in d['reused_currency_evidence']:
        assert source['company_currency']['local'] == 'BS'
        assert source['company_currency']['system'] == 'USD'
        assert 'MainCurncy' in source['oadm_sql'][0]
        assert source['source']['schema'] == 'TELCHI'


def test_live_category_not_uniform_tax(evidence):
    j,d = evidence
    r = next(x for x in j['category'] if x['category']=='RAW_MATERIAL')
    assert D(r['amount']) == D('839582.63') and r['lines'] == 526
    assert d['category_by_tax_rate']['0']['lines'] == 9
    assert sum(D(x['amount']) for x in d['category_by_tax_rate'].values()) == D(r['amount'])
    assert D(r['amount'])/D('.87') != D(r['amount'])+D(r['tax'])


def test_document_csv_independent_arithmetic(evidence):
    j,_ = evidence
    rows = list(csv.DictReader((REPORT/'documents.csv').open()))
    assert len({r['doc_entry'] for r in rows}) == len(rows) == 30301
    for r in rows:
        c,d,e,label = classification(D(r['A']),D(r['B']))
        assert (c,d,e,label) == (D(r['C']),D(r['D']),D(r['E']),r['match'])
    assert sum(D(r['C']) for r in rows) == D('842748.21')
    assert sum(D(r['tax_bridge_residual']) for r in rows) == D('-112920.38')


def test_real_example_is_recorded_tax_not_only_ratio(evidence):
    j,_ = evidence
    r, = j['example_260192728']
    assert r['doc_entry'] == '11532517'
    assert D(r['registered_line_tax']) == D('3.25')
    assert r['rates'] == {'13':1}
    assert r['cause'] == 'line_tax_exact'
