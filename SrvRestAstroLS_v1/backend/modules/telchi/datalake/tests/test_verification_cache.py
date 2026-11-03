from pathlib import Path
import pytest

from modules.telchi.datalake.verification_cache import verification_scope, verified_projection
from modules.telchi.datalake import reference_update as ref


def test_same_bytes_reused_only_within_one_verification(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    a.write_bytes(b'first'); b.write_bytes(b'first')
    calls = []
    def project(path):
        return verified_projection(path, 'v1', lambda: calls.append(path) or path.read_bytes())
    @verification_scope
    def run():
        assert project(a) == project(b) == b'first'
        assert len(calls) % 2 == 1
        b.write_bytes(b'other')  # same size; no path/mtime assumption
        assert project(b) == b'other'
    run()
    b.write_bytes(b'first')
    run()
    assert calls == [a, b, a, b]
    assert project(a) == b'first'  # outside a scope, no cached authority
    assert len(calls) == 5


def test_changed_bytes_during_projection_rejected_and_scope_discarded(tmp_path):
    path = tmp_path/'file'; path.write_text('old')
    @verification_scope
    def run():
        def build():
            path.write_text('new')
            return 'untrusted'
        return verified_projection(path, 'v1', build)
    with pytest.raises(ValueError, match='BYTES_CHANGED'):
        run()
    assert verified_projection(path, 'v1', lambda: 'fresh') == 'fresh'


def test_version_content_and_fingerprint_are_identical_with_reuse(tmp_path, monkeypatch):
    for family in ('ref', 'cw'):
        ref.write_parquet(tmp_path/family/'entity/part.parquet', ['id','value','_ingested_at'],
                          ['VARCHAR']*3, [dict(id='A',value='ñ',_ingested_at='volatile')])
    roots = tmp_path/'ref', tmp_path/'cw'
    expected = ref.version_content(*roots)
    original = ref.read_parquet_rows
    calls = []
    def read(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(ref, 'read_parquet_rows', read)
    @verification_scope
    def run():
        first = ref.version_content(*roots)
        second = ref.version_content(*roots)
        assert first == second == expected
        assert ref.digest(first) == ref.digest(expected)
        assert ref.version_fingerprint(*roots) == ref.digest(expected)
    run()
    assert len(calls) == 2  # content and streaming JSON are distinct verified projections
    run()
    assert len(calls) == 4


def test_contract_version_change_never_reuses_projection(tmp_path):
    path = tmp_path/'input'
    path.write_bytes(b'unchanged')
    @verification_scope
    def run():
        assert verified_projection(path, 'contract-v1', lambda: 'v1') == 'v1'
        assert verified_projection(path, 'contract-v2', lambda: 'v2') == 'v2'
    run()


def test_streaming_fingerprint_keeps_exact_json_and_multiset(tmp_path):
    rows = [dict(id='a', value='\\"\\n😀', physical_classification_observed_at='t1'),
            dict(id='b', value=None, physical_classification_observed_at='t2'),
            dict(id='b', value=None, physical_classification_observed_at='t2')]
    root = tmp_path/'ref'
    ref.write_parquet(root/'entity/part.parquet', list(rows[0]), ['VARCHAR']*3, rows)
    assert ref.version_fingerprint(root, tmp_path/'empty') == ref.digest(ref.version_content(root, tmp_path/'empty'))
