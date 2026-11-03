"""Operational channels, unlike historical rows, participate in exclusivity."""
from unittest.mock import Mock
import pytest
from modules.messaging.administration.bindings import BindingAdministration
from modules.messaging.administration.contract import Denied


def test_operational_selection_uses_runtime_status_boundary():
    conn = Mock()
    BindingAdministration().operative(conn, 'instance')
    query, args = conn.execute.call_args.args
    assert "c.status IN ('active','testing')" in query
    assert "w.status IN ('active','testing')" in query
    assert "p.status IN ('active','testing')" in query
    assert "dev_only'='true'" in query
    assert args == ('instance',)


@pytest.mark.parametrize('rows,allowed', [([], False), ([{'id':'telchi'}], True),
    ([{'id':'legacy'}], False), ([{'id':'telchi'}, {'id':'legacy'}], False)])
def test_exclusivity_counts_only_operational_query_results(rows, allowed):
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = rows
    if allowed:
        assert BindingAdministration().require_exclusive(conn,'instance','telchi') == rows[0]
    else:
        with pytest.raises(Denied, match='operative_binding_not_exclusive'):
            BindingAdministration().require_exclusive(conn,'instance','telchi')


def test_absence_evidence_required_before_any_write():
    conn = Mock()
    with pytest.raises(Denied, match='consumer_absence_evidence_required'):
        BindingAdministration().deactivate_historical(conn, channel_id='x',workspace_slug='w',alias='a',
            instance='i',expected_status='testing',expected_events=164,evidence_ref='')
    conn.execute.assert_not_called()
