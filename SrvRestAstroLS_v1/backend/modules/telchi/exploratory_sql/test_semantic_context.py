"""Binding-local semantic context cannot widen authorization or imply facts."""
from dataclasses import replace

import duckdb
import pytest

from .authorized_foundation import (DiscoveredSource, EffectiveScope, SourcePolicy,
                                    describe_authorized_dimensions)
from .contracts import Column


@pytest.mark.parametrize('mode', ['approved', 'no_permission', 'other_tenant', 'partial_rows', 'partial_columns', 'large'])
def test_vocabularies_are_bounded_and_fully_authorized(mode):
    source = DiscoveredSource('sales_document', 'docs',
        (Column('sales_channel_code', 'VARCHAR'), Column('sales_channel_name', 'VARCHAR')),
        ('Unaccredited calendar coverage.',))
    scope = EffectiveScope('user', 'Telchi', 'dev', frozenset({'read'}))
    policy = SourcePolicy('sales_document', 'read', 'Telchi', 'dev', whole_dataset=True)
    if mode == 'no_permission':
        scope = replace(scope, permissions=frozenset())
    elif mode == 'other_tenant':
        policy = replace(policy, organization='other')
    elif mode == 'partial_rows':
        policy = replace(policy, whole_dataset=False)
    elif mode == 'partial_columns':
        policy = replace(policy, columns=('sales_channel_code',))
    with duckdb.connect() as db:
        db.execute('CREATE TABLE docs(sales_channel_code VARCHAR, sales_channel_name VARCHAR)')
        rows = [(str(i), 'label') for i in range(31)] if mode == 'large' else [('HORIZONTAL', 'HORIZONTAL'), (None, None)]
        db.executemany('INSERT INTO docs VALUES (?,?)', rows)
        result, = describe_authorized_dimensions(db, (source,), (policy,), scope)
    if mode == 'approved':
        assert result.limitations[0] == source.limitations[0]
        assert 'HORIZONTAL' in result.limitations[1]
        assert '"complete":true' in result.limitations[1]
        assert 'NOT sales amounts' in result.limitations[2]
    else:
        assert result == source
