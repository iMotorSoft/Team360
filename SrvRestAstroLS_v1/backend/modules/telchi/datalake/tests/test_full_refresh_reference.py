"""Captured-master integration, real local receipts/Parquet, zero HANA calls."""
from copy import deepcopy
from pathlib import Path
import shutil

import pytest

from modules.telchi.datalake import full_refresh_reference as integration
from modules.telchi.datalake import sales_reference_release as release
from modules.telchi.datalake import sales_incremental as inc
from modules.telchi.datalake import reference_update as ref
from modules.telchi.datalake.full_refresh_capture import CaptureSession, DomainBudget
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.foundation_publication import ComponentReference, FoundationPublication, FoundationReaderError
from modules.telchi.runtime.config import DuckDBSafetyProfile
from .test_full_refresh_capture import Source, Guard


class MasterSource(Source):
    def query_read_only(self, name, sql, params=()):
        if 'clock' in name:
            return super().query_read_only(name, sql, params)
        return [dict(rows=len(self.rows))]


@pytest.fixture
def captured(tmp_path, monkeypatch):
    monkeypatch.setattr(inc, 'DATA_ROOT', tmp_path)
    old = tmp_path/'reference/_versions/old'
    cw = tmp_path/'crosswalk/_versions/old'
    root = tmp_path/'raw/sap/full-data-lake-refresh-capture-v1/unit'
    for entity, cfg in ((e, ref.ENTITY_CONFIG[e]) for e in integration.ENTITIES):
        cols = ['source_system', 'source_native_id', cfg['canonical'],
                'name' if entity == 'customer' else 'canonical_name']
        if entity == 'product':
            cols += list(ref.PHYSICAL_FIELDS)
        row = dict(source_system='SAP_HANA', source_native_id='old_'+entity,
                   **{cfg['canonical']: 'canonical_'+entity, cols[3]: 'Preserved'})
        ref.write_parquet(old/cfg['ref']/'part-00000.parquet', cols, ['VARCHAR']*len(cols), [row])
        cc = ['source_system', 'source_native_id', 'canonical_id']
        ref.write_parquet(cw/cfg['crosswalk']/'part-00000.parquet', cc, ['VARCHAR']*3,
            [dict(source_system='SAP_HANA', source_native_id='old_'+entity, canonical_id='canonical_'+entity)])
        if entity == 'supplier':
            continue  # OCRD below contains both role observations.
        table, key, fields = release.FIELDS[entity]
        obs = dict.fromkeys(fields)
        obs.update({key: 'new_'+entity, 'ItemName': 'Accredited', 'CardName': 'Accredited',
                    'CardType': 'C', 'U_FormaFarmac': '1'})
        budget = DomainBudget(10, 120, 100)
        source_rows = [obs]
        if entity == 'customer':
            source_rows.append({**obs, 'CardCode':'new_supplier', 'CardType':'S'})
        source = MasterSource(budget, rows=source_rows)
        session = CaptureSession(root/'reference', source, budget, guard=Guard(),
            profile=DuckDBSafetyProfile(temp_directory=tmp_path/'temp', threads=2))
        sql = getattr(ref, table+'_SQL').strip() + ' ORDER BY "'+key+'"'
        session.capture(table.lower(), sql, keys=[key], semantic_scope={'kind':'CURRENT_MASTER_SNAPSHOT'})
    inc.seal(root/'cycle-plan.json', {'contract':'full-data-lake-refresh-capture-v1'})
    observations, _ = integration.missing_observations(old, root)
    result = release.prepare(old, cw, observations, tmp_path/'prepared')
    new = tmp_path/'reference/_versions'/result['reference_version']
    newcw = tmp_path/'crosswalk/_versions'/result['reference_version']
    shutil.copytree(result['reference_path'], new)
    shutil.copytree(result['crosswalk_path'], newcw)
    catalog = {n: ComponentReference(n, 'old' if n=='reference' else n+'_id')
               for n in ('reference', 'sales', 'credit_memo', 'oinm', 'oitw')}
    base = FoundationPublication('base', 'unit', reference_version='old', components=catalog,
        status='CURRENT', manifest={'foundation_publication_id':'base', 'base_snapshot_id':84,
        'facts_base_snapshot_id':1408, 'permissions':{'role':'unchanged'},
        'components': {n:v.as_dict() for n,v in catalog.items()}})
    class Store:
        def get(self, identity):
            return base if identity == 'base' else None
    return base, Store(), old, new, root


def test_captured_append_validates_and_preserves_old_physical(captured):
    base, store, old, new, root = captured
    candidate = integration.make_candidate(base, new, root)
    validate_manifest(store, candidate)
    assert candidate.manifest['reference_compatibility']['new_identities'] == {'customer':1,'product':1,'supplier':1}
    assert candidate.manifest['facts_base_snapshot_id'] == 1408
    assert candidate.manifest['base_snapshot_id'] == 84
    assert candidate.components['sales'] == base.components['sales']
    assert candidate.manifest['reference_compatibility'] == release.append_proof(old, new, root)
    rows = ref.read_parquet_rows(new/'products/part-00000.parquet')[2]
    assert next(r for r in rows if r['source_native_id']=='new_product')['physical_state'] == 'LIQUID'
    assert next(r for r in rows if r['source_native_id']=='old_product')['physical_state'] is None


@pytest.mark.parametrize('mutation', ['permissions','snapshot','component','proof','adapter','schema','identity','old_attribute','bytes','receipt'])
def test_captured_append_fail_closed(captured, mutation):
    base, store, old, new, root = captured
    candidate = integration.make_candidate(base, new, root)
    m = candidate.manifest
    if mutation == 'permissions': m['permissions']['role'] = 'elevated'
    if mutation == 'snapshot': m['facts_base_snapshot_id'] = 1500
    if mutation == 'component': m['components']['oinm']['publication_id'] = 'wrong'
    if mutation == 'proof': m['reference_compatibility']['capture_receipts'][0]['receipt_sha256'] = '0'*64
    if mutation == 'adapter': m['reference_compatibility_adapter'] = 'AUTO_SCHEMA_MATCH'
    if mutation in {'schema','identity','old_attribute'}:
        path = new/'products/part-00000.parquet'
        cols, types, rows = ref.read_parquet_rows(path)
        if mutation == 'schema': cols.append('extra'); types.append('VARCHAR')
        if mutation == 'identity': rows.append(deepcopy(rows[0]))
        if mutation == 'old_attribute': rows[0]['canonical_name'] = 'altered'
        path.unlink(); ref.write_parquet(path, cols, types, rows)
    if mutation == 'bytes':
        page = inc.read_json(root/'reference/oitm/complete.json')['pages'][0]
        Path(page['path']).write_bytes(b'corrupt')
    if mutation == 'receipt': (root/'reference/oitm/complete.json').unlink()
    with pytest.raises((FoundationReaderError, ValueError, RuntimeError, FileNotFoundError)):
        validate_manifest(store, candidate)
