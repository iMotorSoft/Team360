"""Canonical incremental admission, not another publication allowlist."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from modules.telchi.datalake import sales_incremental as inc, sales_refresh_cycle as cycle
from modules.telchi.datalake import sales_succession as succession
from modules.telchi.datalake import category_line_amount_query as category
from modules.telchi.datalake import commercial_line_amount_by_query as commercial
from modules.telchi.datalake import ducklake
from modules.telchi.datalake.sales_facts_transition import make_candidate
from .test_receivables_collections_foundation import store
from .test_sales_facts_transition import built
from .test_sales_refresh_cycle import future
from .test_sales_continuity import Guard
from .test_sales_controlled_block import source


@pytest.fixture
def successor(tmp_path, store, built, future, monkeypatch):
    base, plan = future
    root = tmp_path/'raw/sap'/cycle.CONTRACT/'successor'
    root.parent.mkdir(parents=True, exist_ok=True)
    s, _ = source([[]]*6)
    cycle.capture(root, plan, s, sleep=lambda _:None, guard=Guard())
    report = inc.read_json(tmp_path/'reconciliation.json')
    report.update(base_publication=base.foundation_publication_id, incremental_plan=plan,
                  capture_plan_sha256=inc.file_hash(root/'plan.json'))
    path = tmp_path/'successor-report.json'
    inc.seal(path, report)
    candidate = make_candidate(base, path, root)
    monkeypatch.setattr(succession, 'SALES_ROOT', base.foundation_publication_id)
    monkeypatch.setattr(succession, 'PHYSICAL_ROOT', base.foundation_publication_id)
    monkeypatch.setattr(succession, 'ROOT_SNAPSHOT', 90)
    monkeypatch.setattr(ducklake, 'DATA_ROOT', tmp_path)
    for family, dataset, module, constant in [
        ('crosswalk', 'product_business_type', category, 'CROSSWALK_SHA256'),
        ('crosswalk', 'product_crosswalk', commercial, 'PHYSICAL_CROSSWALK_SHA256'),
        ('reference', 'products', commercial, 'PHYSICAL_PRODUCTS_SHA256')]:
        file = tmp_path/family/'_versions'/base.reference_version/dataset/'part-00000.parquet'
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b'sealed fixture '+dataset.encode())
        monkeypatch.setattr(module, constant, inc.file_hash(file))
    return base, candidate


@pytest.mark.parametrize('physical', [False, True])
def test_canonical_successor_not_id_substitution(store, successor, physical):
    base, candidate = successor
    assert candidate.foundation_publication_id != base.foundation_publication_id
    assert succession.validate_successor(store, candidate, 90, physical=physical) is candidate
    assert candidate.manifest['components']['purchasing'] == base.manifest['components']['purchasing']
    assert candidate.manifest['components']['material_supply'] == base.manifest['components']['material_supply']


@pytest.mark.parametrize('mutation', [
    'schema', 'metric', 'permissions', 'classification', 'category', 'dependency',
    'duplicate_component', 'manifest', 'fingerprint', 'lineage', 'coverage',
    'watermark', 'material', 'snapshot', 'file_hash', 'report_hash'])
def test_incompatible_successor_fails_closed(store, successor, mutation):
    _, candidate = successor
    p = deepcopy(candidate)
    m = p.manifest
    if mutation == 'schema':
        m['components']['sales']['facts_contract']['datasets']['sales_document']['schema'].append(['unreviewed', 'VARCHAR'])
    elif mutation == 'metric': m['metric_definition'] = 'accounting_revenue'
    elif mutation == 'permissions': m['permissions'] = ['all']
    elif mutation == 'classification': m['product_business_classification'] = {}
    elif mutation == 'category':
        path = ducklake.DATA_ROOT/'crosswalk/_versions'/p.reference_version/'product_business_type/part-00000.parquet'
        path.write_bytes(b'unaccredited')
    elif mutation == 'dependency': del m['components']['purchasing']
    elif mutation == 'duplicate_component': m['components']['oinm']['publication_id'] = m['components']['oitw']['publication_id']
    elif mutation == 'manifest': m['foundation_publication_id'] = 'other'
    elif mutation == 'fingerprint': m['components']['sales']['content_identity'] = '0'*64
    elif mutation == 'lineage': m['base_foundation_publication_id'] = 'missing'
    elif mutation == 'coverage': m['sales_coverage'].pop()
    elif mutation == 'watermark': m['sales_facts_revalidation']['incremental_plan']['published_end'] = '2026-10-29'
    elif mutation == 'material': m['sales_facts_revalidation']['material_supply']['proofs']['sales']['after_sha256'] = '0'*64
    elif mutation == 'snapshot': m['facts_base_snapshot_id'] += 1
    elif mutation == 'file_hash':
        path = Path(m['components']['sales']['facts_contract']['datasets']['sales_document']['path'])
        path.write_bytes(b'corrupt')
    elif mutation == 'report_hash': Path(m['sales_facts_revalidation']['report_path']).write_bytes(b'{}')
    with pytest.raises(Exception): succession.validate_successor(store, p, 90)
    assert store.current_pointer() != p.foundation_publication_id


def test_root_snapshot_and_physical_accreditation_not_implicit(store, successor):
    base, candidate = successor
    with pytest.raises(Exception, match='snapshot'):
        succession.validate_successor(store, candidate, 91)
    path = ducklake.DATA_ROOT/'reference/_versions'/base.reference_version/'products/part-00000.parquet'
    path.write_bytes(b'physical lost')
    with pytest.raises(Exception, match='physical accreditation root'):
        succession.validate_successor(store, candidate, 90, physical=True)


def test_process_local_admission_never_survives_json_or_source_mutation():
    result = dict(source=dict(publication_id='fixture', snapshot_id=90))
    marked = succession.mark_result(result)
    assert succession.admitted_source(marked) == result['source']
    assert succession.admitted_source(json.loads(json.dumps(marked))) is None
    marked['source'] = dict(marked['source'], snapshot_id=91)
    assert succession.admitted_source(marked) is None


def test_worker_cannot_self_accredit(monkeypatch):
    calls = []
    def reject(source, **kwargs):
        calls.append(source)
        raise ValueError('no canonical publication')
    monkeypatch.setattr(succession, 'result_binding', reject)
    fake = dict(publication_id='foundation_'+'a'*32, snapshot_id=1408,
                updated_at='2026-11-01', succession='PASS')
    assert not succession.accepts_result(fake, set())
    assert len(calls) == 1
    assert not succession.accepts_result(dict(publication_id='latest'), set())
    assert len(calls) == 1
