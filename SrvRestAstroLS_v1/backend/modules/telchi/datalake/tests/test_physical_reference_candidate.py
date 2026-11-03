"""Physical-only preparation stays additive and never activates a pointer."""
import json
from pathlib import Path

import pytest

from modules.telchi.datalake import reference_update as ru
from modules.telchi.datalake.reference_compatibility import reference_projection
from .test_reference_update import _make_root


def seed(tmp_path):
    root, fixture = _make_root(tmp_path)
    ru.run_reference_update(data_root=root, fixture_dir=fixture, evidence_root=tmp_path / 'seed')
    pointer, ref, cw = ru.active_pointer(root)
    rows = ru.read_parquet_rows(ref / 'products/part-00000.parquet')[2]
    key = next(row['source_native_id'] for row in rows if row['source_system'] == 'SAP_HANA')
    return root, ref, cw, key


def test_prepare_preserves_all_contracts_and_real_noop(tmp_path, monkeypatch):
    root, ref, cw, key = seed(tmp_path)
    monkeypatch.setattr(ru.HanaReadOnlySource, '__init__', lambda *_: pytest.fail('HANA forbidden'))
    pointer = (root / 'manifests/reference_current.json').read_bytes()
    before = ru.digest(ru.version_content(ref, cw))
    observations = [dict(ItemCode=key, U_FormaFarmac='1', observed_at='2026-10-29T12:00:00Z'),
                    dict(ItemCode='NOT_IN_REFERENCE', U_FormaFarmac='4', observed_at='2026-10-29T12:00:00Z')]
    kwargs = dict(previous_reference=ref, previous_crosswalk=cw, observations=observations,
                  candidate_root=tmp_path / 'isolated')
    result = ru.prepare_physical_reference(**kwargs)
    assert result['status'] == 'PREPARED' and result['enriched_rows'] == 1
    assert result['pending_structural_identities'] == ['NOT_IN_REFERENCE']
    reference_projection(ref, Path(result['reference_path']))
    assert ru.prepare_physical_reference(**kwargs) == result
    sealed_bytes = (Path(result['reference_path']) / 'products/part-00000.parquet').read_bytes()
    later = [{**observation, 'observed_at':'2026-10-30T12:00:00Z'} for observation in observations]
    replay = ru.prepare_physical_reference(**{**kwargs, 'observations':later})
    assert replay['reference_version'] == result['reference_version']
    assert (Path(result['reference_path']) / 'products/part-00000.parquet').read_bytes() == sealed_bytes
    repeat = ru.prepare_physical_reference(previous_reference=Path(result['reference_path']),
        previous_crosswalk=Path(result['crosswalk_path']), observations=observations,
        candidate_root=tmp_path / 'repeat')
    assert repeat['status'] == 'NOOP' and repeat['enriched_rows'] == 0
    assert repeat['reference_version'] == result['reference_version']
    assert (root / 'manifests/reference_current.json').read_bytes() == pointer
    assert ru.digest(ru.version_content(ref, cw)) == before


@pytest.mark.parametrize('damage', ['duplicate', 'blank', 'timestamp', 'timezone'])
def test_bad_observation_rejected_before_writes(tmp_path, damage):
    _, ref, cw, key = seed(tmp_path)
    obs = [dict(ItemCode=key, U_FormaFarmac='1', observed_at='2026-10-29T12:00:00Z')]
    if damage == 'duplicate': obs *= 2
    if damage == 'blank': obs[0]['ItemCode'] = ' '
    if damage == 'timestamp': obs[0]['observed_at'] = 'invented'
    if damage == 'timezone': obs[0]['observed_at'] = '2026-10-29T12:00:00'
    with pytest.raises(ValueError):
        ru.prepare_physical_reference(previous_reference=ref, previous_crosswalk=cw,
                                     observations=obs, candidate_root=tmp_path / 'isolated')
    assert not (tmp_path / 'isolated').exists()


def test_shared_and_source_destinations_rejected(tmp_path):
    _, ref, cw, _ = seed(tmp_path)
    for output in (ref, cw, ref.parent, Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/staging/forbidden')):
        with pytest.raises(ValueError, match='isolated'):
            ru.prepare_physical_reference(previous_reference=ref, previous_crosswalk=cw,
                                         observations=[], candidate_root=output)


def test_interrupted_destination_not_repaired_or_activated(tmp_path):
    _, ref, cw, key = seed(tmp_path)
    kwargs = dict(previous_reference=ref, previous_crosswalk=cw,
        observations=[dict(ItemCode=key, U_FormaFarmac='2', observed_at='2026-10-29T12:00:00Z')],
        candidate_root=tmp_path / 'isolated')
    result = ru.prepare_physical_reference(**kwargs)
    path = Path(result['reference_path']) / 'products/part-00000.parquet'
    path.write_bytes(b'interrupted isolated fixture')
    with pytest.raises(RuntimeError, match='immutable version collision'):
        ru.prepare_physical_reference(**kwargs)
    assert path.read_bytes() == b'interrupted isolated fixture'
    assert not (tmp_path / 'isolated/manifests').exists()
