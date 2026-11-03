import pytest

from modules.telchi.datalake.sales_sealed_revalidation import demand_projection,validate_physical_files
from modules.telchi.datalake.raw import file_hash


def test_demand_uses_real_dependency_window_not_new_publication_id():
    docs=[dict(doc_entry='1',doc_date='2026-09-01',doc_status='O'),dict(doc_entry='2',doc_date='2026-10-01')]
    lines=[dict(doc_entry='1',item_code='P',quantity='2'),dict(doc_entry='2',item_code='P',quantity='999')]
    before=demand_projection(docs,lines,'2026-06-26','2026-09-24')
    assert before=={'P':'2'}
    assert before==demand_projection([dict(d,doc_status='C') for d in docs],lines,'2026-06-26','2026-09-24')
    lines[0]['quantity']='3'
    assert before!=demand_projection(docs,lines,'2026-06-26','2026-09-24')
    docs[0]['doc_date']='2026-10-01'
    assert demand_projection(docs,lines,'2026-06-26','2026-09-24')=={}


def test_physical_hash_revalidation_never_rewrites_fingerprints(tmp_path):
    file=tmp_path/'sealed'; file.write_bytes(b'real bytes')
    metadata=dict(file_references=[str(file)],file_hashes=[file_hash(file)])
    components={name:dict(datasets={'data':metadata.copy()}) for name in ('material_supply','purchasing')}
    assert validate_physical_files(components)[str(file)]['actual_sha256']==file_hash(file)
    with pytest.raises(RuntimeError,match='RESOURCE_BLOCKED'):
        validate_physical_files(components,max_bytes=1)
    file.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='hash mismatch'):
        validate_physical_files(components)
