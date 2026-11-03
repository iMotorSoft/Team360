"""Exact append-only multiset comparison without redundant row fingerprints."""
from datetime import datetime, timezone
from decimal import Decimal

from modules.telchi.datalake.sales_reference_release import _projected_rows


def test_typed_equivalence_and_order():
    columns = ['name', 'amount', 'at', 'flag', 'missing']
    types = ['VARCHAR', 'DECIMAL(38,6)', 'TIMESTAMP WITH TIME ZONE', 'BOOLEAN', 'VARCHAR']
    left = [dict(name='á', amount=Decimal('1.000'), at=datetime(2026, 9, 1, tzinfo=timezone.utc), flag=True)]
    right = [dict(name='á', amount='1', at='2026-08-31T20:00:00-04:00', flag='true', missing=None)]
    assert _projected_rows(left, columns, types) == _projected_rows(right, columns, types)
    assert _projected_rows(left * 2, columns, types) != _projected_rows(right, columns, types)
    assert _projected_rows(left + right, columns, types) == _projected_rows(right + left, columns, types)


def test_every_value_and_null_remain_material():
    columns, types = ['a', 'b'], ['VARCHAR', 'VARCHAR']
    original = _projected_rows([{'a': '1', 'b': None}], columns, types)
    for changed in ({'a': '1', 'b': ''}, {'a': '2', 'b': None}, {'a': None, 'b': '1'}):
        assert original != _projected_rows([changed], columns, types)


def test_equivalent_to_legacy_projection_for_typed_rows():
    from modules.telchi.datalake.reference_update import digest, _normal
    columns = ['name', 'amount', 'at', 'flag']
    types = ['VARCHAR', 'DECIMAL(38,6)', 'TIMESTAMP WITH TIME ZONE', 'BOOLEAN']
    def legacy(rows):
        def typed(value, typ):
            value = _normal(value)
            if value is None:
                return None
            if typ.startswith(('DECIMAL', 'DOUBLE', 'FLOAT')):
                return str(Decimal(value).normalize())
            if typ.startswith('TIMESTAMP'):
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return (parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed).isoformat()
            return value
        return sorted(digest({k: typed(row.get(k), typ) for k, typ in zip(columns, types)}) for row in rows)
    variants = [
        dict(name='á', amount='1.00', at='2026-09-01T00:00:00Z', flag=True),
        dict(name='á', amount=Decimal('1'), at='2026-08-31T20:00:00-04:00', flag='true'),
        dict(name='', amount=None, at=None, flag=False),
        dict(name=None, amount='-0.000', at='2026-09-01', flag=None),
    ]
    samples = [[], *[[row] for row in variants], variants, variants * 2, variants[::-1]]
    for left in samples:
        for right in samples:
            assert ((_projected_rows(left, columns, types) == _projected_rows(right, columns, types))
                    == (legacy(left) == legacy(right)))


def test_comparison_does_not_compute_row_digest(monkeypatch):
    from modules.telchi.datalake import sales_reference_release as release
    def forbidden(*args):
        raise AssertionError('per-row JSON hashing reintroduced')
    monkeypatch.setattr(release, 'digest', forbidden)
    assert _projected_rows([{'a': 'x'}], ['a'], ['VARCHAR'])
