"""Offline replay/versioning of the Material Supply sales-dependent datasets.

Uses only stored BOM, original stock, original purchasing/consumption evidence
and pinned Reference. No HANA, new inventory coverage, or source refresh. A
failed original-output replay is a hard gate, never a reason to change gold.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import os

from . import sales_incremental as inc
from .material_supply_derivation import (split_bom_raw_materials, build_parent_index,
                                        build_equivalent_demand, build_supply_status)
from .material_supply_fact_capture import _dataset_parquet_files
from .material_supply_purchasing_lineage import FACT_CAPTURE_ROOT
from .raw import write_raw
from modules.telchi.runtime.config import DuckDBSafetyProfile


def normalized(value):
    """Numeric representation and set ordering only; no monetary tolerance."""
    if isinstance(value,(date,datetime)):
        return value.isoformat()
    if isinstance(value,dict):
        return {k:normalized(v) for k,v in sorted(value.items())}
    if isinstance(value,list):
        result=[normalized(v) for v in value]
        return sorted(result,key=lambda v:inc.digest(v))
    if isinstance(value,(float,int,Decimal)) and not isinstance(value,bool):
        return str(Decimal(str(value)).normalize())
    return value


def rows(con,sql,params=None):
    cur=con.execute(sql,params or [])
    names=[c[0] for c in cur.description]
    return [dict(zip(names,r)) for r in cur.fetchall()]


def replay(con,access,destination,*,start,end):
    """Prove original output first, then rebuild only materially affected files."""
    destination=destination.resolve()
    old=access.manifest['components']['material_supply']
    datasets=old['datasets']
    provenance={}
    def persisted(dataset):
        metadata=datasets[dataset]
        for path,sha in zip(metadata['file_references'],metadata['file_hashes']):
            if inc.file_hash(Path(path))!=sha:
                raise ValueError('sealed Material Supply hash mismatch')
        return rows(con,'SELECT * FROM read_parquet(?)',[metadata['file_references']])
    bom={}
    for dataset in ('bom_header','bom_line'):
        files=_dataset_parquet_files(FACT_CAPTURE_ROOT,dataset)
        if not files or len(files)>100 or sum(p.stat().st_size for p in files)>32*1024*1024:
            raise RuntimeError('BOM_REPLAY_SOURCE_UNAVAILABLE_OR_OVER_BUDGET')
        provenance[dataset]={str(p):inc.file_hash(p) for p in files}
        bom[dataset]=rows(con,'SELECT * FROM read_parquet(?)',[[str(p) for p in files]])
    headers={str(h['Code']):float(h.get('Qauntity') or 0) for h in bom['bom_header']}
    if len(headers)!=len(bom['bom_header']):
        raise ValueError('ambiguous BOM capture versions')
    edges=split_bom_raw_materials(bom['bom_line'],headers)
    parents=build_parent_index(edges)
    raw_materials=sorted({e['child'] for e in edges}-{e['parent'] for e in edges})
    quantities={}
    for prefix in ('old','full'):
        quantities[prefix]={}
        for domain,doc,line in [('sales','sales_document','sales_line'),('credit_memo','credit_memo_document','credit_memo_line')]:
            quantities[prefix][domain]={str(item):float(q or 0) for item,q in con.execute(f'''SELECT l.item_code,sum(try_cast(l.quantity AS DOUBLE))
FROM {prefix}_{line} l JOIN {prefix}_{doc} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
WHERE d.doc_date>=? AND d.doc_date<? GROUP BY l.item_code''',[start,(date.fromisoformat(end)+timedelta(days=1)).isoformat()]).fetchall() if item}
    demand={prefix:build_equivalent_demand(raw_materials=raw_materials,parents=parents,
        sales_by_item=q['sales'],credit_by_item=q['credit_memo'],window_start=date.fromisoformat(start),window_end=date.fromisoformat(end))
        for prefix,q in quantities.items()}
    original_demand=persisted('material_equivalent_demand')
    original_status=persisted('material_supply_status')
    actual=persisted('material_actual_consumption')
    pipeline=persisted('open_purchase_pipeline')
    profiles=persisted('material_lead_time_profile')
    demand_before_matches=normalized(demand['old'])==normalized(original_demand)
    # Do not use new Reference attributes, warehouse roles or inventories.
    # Their exact immutable versions are the existing Foundation component.
    products={str(r['item_code']):dict(canonical_name=r['canonical_name'],inventory_uom=r['inventory_uom_id'],active=r['active'],status=r['status'])
        for r in rows(con,"SELECT item_code,canonical_name,inventory_uom_id,active,status FROM read_parquet(?) WHERE source_system='SAP_HANA'",[str(access.reference('products'))]) if r['item_code']}
    warehouses={str(r[0]) for r in con.execute("SELECT code FROM read_parquet(?) WHERE source_system='SAP_HANA'",[str(access.reference('warehouses'))]).fetchall()}-{'SAA-T2','SAA-T3'}
    old_by_item={str(r['ItemCode']):r for r in original_status}
    if not old_by_item:
        raise ValueError('empty Material Supply status')
    items={item:dict(products.get(item,{}),warehouse='SAA-M1',material_class='RAW_MATERIAL' if r.get('is_raw_material') else str(r.get('material_class') or 'OTHER')) for item,r in old_by_item.items()}
    evidence_fields=('saavedra_relevance','saavedra_relevance_basis','saavedra_relevance_confidence',
        'item_activity_status','saa_m1_history','recent_saa_m1_movement','recent_saa_consumption',
        'saa_production_link','saa_active_bom','open_po_to_saa')
    relevance={item:{k:r.get(k) for k in evidence_fields} for item,r in old_by_item.items()}
    source_times={r['source_as_of'] for r in original_status}
    if len(source_times)!=1:
        raise ValueError('ambiguous stock/derivation cutoff')
    source_as_of=next(iter(source_times))
    if hasattr(source_as_of,'isoformat'):
        source_as_of=source_as_of.isoformat()
    ids=sorted(items)
    stock=rows(con,f'''SELECT item_code,whs_code,try_cast(on_hand AS DOUBLE) AS on_hand,
try_cast(is_commited AS DOUBLE) AS is_commited,try_cast(on_order AS DOUBLE) AS on_order
FROM {access.oitw()} WHERE item_code IN ({','.join('?' for _ in ids)})''',ids)
    status={prefix:build_supply_status(stock_rows=stock,items=items,
        actual_consumption={r['item_code']:float(r.get('actual_consumption_qty') or 0) for r in actual},
        equivalent_demand={r['item_code']:r['commercial_daily_equivalent_basis_qty'] for r in values},
        open_pipeline=pipeline,lead_profiles=profiles,source_as_of=source_as_of,window_days=90,
        saavedra_evidence=relevance,valid_warehouses=warehouses) for prefix,values in demand.items()}
    status_before_matches=normalized(status['old'])==normalized(original_status)
    proof=dict(status='REPLAY_PASS' if demand_before_matches and status_before_matches else 'REPLAY_BLOCKED',
               old_demand_replay_matches=demand_before_matches,old_status_replay_matches=status_before_matches,
               before_demand_sha256=inc.digest(normalized(original_demand)),
               replay_demand_sha256=inc.digest(normalized(demand['old'])),
               after_demand_sha256=inc.digest(normalized(demand['full'])),
               before_status_sha256=inc.digest(normalized(original_status)),
               replay_status_sha256=inc.digest(normalized(status['old'])),
               after_status_sha256=inc.digest(normalized(status['full'])),
               bom_provenance=provenance,stock_component=access.manifest['components']['oitw']['publication_id'],
               stock_source_as_of=source_as_of,demand_window=[start,end],
               refresh_of_stock_production_purchasing=False,datasets_replaced=[],new_component=None)
    if proof['status']!='REPLAY_PASS':
        return proof
    manifests={name:dict(metadata) for name,metadata in datasets.items()}
    for name,new_rows,old_rows in [('material_equivalent_demand',demand['full'],original_demand),('material_supply_status',status['full'],original_status)]:
        if normalized(new_rows)==normalized(old_rows):
            continue
        manifest=write_raw(root=destination/'material_supply',segment_id=name,extraction_id='sales-facts-revalidation-v1',rows=new_rows,
            metadata=dict(source_as_of=source_as_of,source_system='TELCHI_DATA_LAKE_DERIVATION',
                          prior_component=old['publication_id'],prior_foundation=access.foundation_publication_id,
                          dependency_proof_sha256=inc.digest(proof)),profile=DuckDBSafetyProfile(threads=1,memory_limit='256MB',temp_directory=destination/'material_replay_temp'))
        for file in Path(manifest['path']).parent.iterdir():
            with file.open('rb') as stream: os.fsync(stream.fileno())
        directory=Path(manifest['path']).parent
        while True:
            inc.sync_dir(directory)
            if directory==destination:
                break
            directory=directory.parent
        manifests[name]={k:manifest.get(k) for k in ('manifest_path','file_references','file_hashes','row_count')}
        proof['datasets_replaced'].append(name)
    if proof['datasets_replaced']:
        stable=dict(datasets=manifests,original_component=old['publication_id'],proof=deepcopy(proof))
        fingerprint=inc.digest(stable)
        proof['new_component']=dict(name='material_supply',publication_id='material_supply_'+fingerprint[:24],
            source_as_of=old.get('source_as_of'),row_count=sum(m['row_count'] for m in manifests.values()),
            content_identity=fingerprint,keyset_fingerprint=None,datasets=manifests,
            sales_revalidation_contract=stable)
    return proof
