from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import json

import duckdb
import pytest

from modules.telchi.datalake import sales_incremental as inc, sales_material_revalidation as r
from modules.telchi.datalake.raw import write_raw
from modules.telchi.runtime.config import DuckDBSafetyProfile
from modules.telchi.datalake.material_supply_derivation import build_equivalent_demand,build_supply_status


@pytest.mark.parametrize('changed,corrupt',[(False,False),(True,False),(True,True)])
def test_exact_replay_and_selective_versioning(tmp_path,monkeypatch,changed,corrupt):
    profile=DuckDBSafetyProfile(threads=1,memory_limit='128MB',temp_directory=tmp_path/'tmp')
    def persist(name,records):
        m=write_raw(root=tmp_path/'input',segment_id=name,extraction_id='v1',rows=records,metadata={},profile=profile)
        return {k:m[k] for k in ('manifest_path','file_references','file_hashes','row_count')}
    bom_header=persist('bom_header',[dict(Code='P',Qauntity=1)])
    bom_line=persist('bom_line',[dict(Father='P',Code='R',Quantity=2)])
    monkeypatch.setattr(r,'_dataset_parquet_files',lambda root,dataset:[Path((bom_header if dataset=='bom_header' else bom_line)['file_references'][0])])
    start,end='2026-06-26','2026-09-24'
    demand=build_equivalent_demand(raw_materials=['R'],parents={'R':[('P',2)]},sales_by_item={'P':10},credit_by_item={},window_start=date.fromisoformat(start),window_end=date.fromisoformat(end))
    stock=[dict(item_code='R',whs_code='SAA-M1',on_hand=10,is_commited=0,on_order=0)]
    items={'R':dict(canonical_name='Material R',inventory_uom='kg',warehouse='SAA-M1',material_class='RAW_MATERIAL')}
    pipeline=[dict(item_code='R',procurement_origin='LOCAL',open_qty_source=0,supplier='S')]
    profiles=[dict(item_code='R',supplier='S',procurement_origin='LOCAL',lead_time_basis='ITEM+SUPPLIER+ORIGIN',p50_days=1,sample_count=1,confidence='HIGH')]
    actual=[dict(item_code='R',actual_consumption_qty=0)]
    status=build_supply_status(stock_rows=stock,items=items,actual_consumption={'R':0},equivalent_demand={'R':20},open_pipeline=pipeline,lead_profiles=profiles,source_as_of='2026-09-24',window_days=90,saavedra_evidence={'R':{}},valid_warehouses={'SAA-M1'})
    if corrupt: status[0]['current_stock']=999
    datasets={name:persist(name,values) for name,values in [('material_equivalent_demand',demand),('material_supply_status',status),('material_actual_consumption',actual),('open_purchase_pipeline',pipeline),('material_lead_time_profile',profiles)]}
    products=persist('products',[dict(item_code='R',canonical_name='Material R',inventory_uom_id='kg',active=True,status='ACTIVE',source_system='SAP_HANA')])
    warehouses=persist('warehouses',[dict(code='SAA-M1',source_system='SAP_HANA')])
    con=duckdb.connect()
    try:
        con.execute('SET threads=1')
        con.execute('CREATE TABLE stock(item_code VARCHAR,whs_code VARCHAR,on_hand DOUBLE,is_commited DOUBLE,on_order DOUBLE)')
        con.execute("INSERT INTO stock VALUES ('R','SAA-M1',10,0,0)")
        for prefix in ('old','full'):
            for domain in ('sales','credit_memo'):
                doc='sales_document' if domain=='sales' else 'credit_memo_document'
                line='sales_line' if domain=='sales' else 'credit_memo_line'
                con.execute(f'CREATE TABLE {prefix}_{doc}(source_system VARCHAR,doc_entry VARCHAR,doc_date VARCHAR)')
                con.execute(f'CREATE TABLE {prefix}_{line}(source_system VARCHAR,doc_entry VARCHAR,item_code VARCHAR,quantity VARCHAR)')
                if domain=='sales':
                    q=20 if changed and prefix=='full' else 10
                    con.execute(f"INSERT INTO {prefix}_{doc} VALUES ('SAP','1','2026-09-01')")
                    con.execute(f"INSERT INTO {prefix}_{line} VALUES ('SAP','1','P','{q}')")
        refs={'products':products,'warehouses':warehouses}
        access=SimpleNamespace(manifest={'components':{'material_supply':dict(publication_id='material_old',source_as_of='2026-09-24',datasets=datasets),'oitw':dict(publication_id='stock_old')}},foundation_publication_id='foundation_old',oitw=lambda:'stock',reference=lambda name:Path(refs[name]['file_references'][0]))
        out=tmp_path/'output';out.mkdir()
        proof=r.replay(con,access,out,start=start,end=end)
        if corrupt:
            assert proof['status']=='REPLAY_BLOCKED' and not proof['new_component']
            assert not list(out.glob('material_supply/*'))
        elif changed:
            assert proof['status']=='REPLAY_PASS'
            assert set(proof['datasets_replaced'])=={'material_equivalent_demand','material_supply_status'}
            component=proof['new_component']
            stable=component['sales_revalidation_contract']
            assert component['publication_id']=='material_supply_'+inc.digest(stable)[:24]
            for name in ['material_actual_consumption','open_purchase_pipeline','material_lead_time_profile']:
                assert component['datasets'][name]==datasets[name]
            assert proof['stock_component']=='stock_old' and not proof['refresh_of_stock_production_purchasing']
            json.dumps(proof)  # no cyclic proof/component references
        else:
            assert proof['status']=='REPLAY_PASS' and not proof['datasets_replaced'] and not proof['new_component']
    finally: con.close()
