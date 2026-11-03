"""Promoted SQL retains official business semantics and uses Foundation pins."""
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest

from modules.telchi.datalake.messaging_sales_query import execute_fixed_query, SQL_TEMPLATE
import modules.telchi.datalake.foundation_reader as reader


def test_fixed_select_uses_only_pinned_relations_and_static_period(monkeypatch):
    calls = []
    class Connection:
        def execute(self, sql, params=None):
            calls.append((sql, params))
            return self
        def fetchone(self):
            return (True,)
        def fetchall(self):
            return [('L001', 2, Decimal('123.5'), Decimal('11.1'))]
    class Connector:
        @contextmanager
        def session(self, *, read_only):
            assert read_only is True
            yield Connection()
    access = SimpleNamespace(foundation_publication_id='foundation-test', foundation_data_as_of='2026-09-15',
        foundation_resolution_ms=2, ducklake_snapshot_id=42,
        sales=lambda name: f'(SELECT * FROM telchi.atomic."{name}" AT (VERSION => 42))')
    monkeypatch.setattr(reader.FoundationReader, 'resolve_on', lambda self, connection: access)
    result = execute_fixed_query(Connector())
    sql, params = calls[-1]
    assert sql.startswith('SELECT') and sql.count('AT (VERSION => 42)') == 2
    assert params == ['2026-01-01','2026-09-16']
    assert 'ORDER BY quantity DESC,l.item_code LIMIT 10' in sql
    assert 'canceled' not in sql and 'credit_memo' not in sql
    assert result['rows'][0]['quantity'] == '123.5'
    assert result['read_only'] and not result['sap_accessed']
    assert result['sql_finished_ms'] >= result['sql_started_ms']
    assert len(result['result_hash']) == 64
    assert '{documents}' in SQL_TEMPLATE


def test_non_readonly_attachment_fails_before_foundation_or_sales(monkeypatch):
    from modules.telchi.datalake.messaging_sales_query import TelchiQueryError
    class Connection:
        def execute(self, sql):
            assert not sql.startswith('SELECT l.item_code')
            return self
        def fetchone(self):
            return (False,)
    class Connector:
        @contextmanager
        def session(self, *, read_only):
            yield Connection()
    def unexpected(*args):
        pytest.fail('Foundation must not resolve on a writable attachment')
    monkeypatch.setattr(reader.FoundationReader, 'resolve_on', unexpected)
    with pytest.raises(TelchiQueryError, match='datalake_not_read_only'):
        execute_fixed_query(Connector())
