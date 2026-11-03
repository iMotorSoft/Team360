"""Harness regressions: fail closed, route collisions and OpenAPI contracts."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('full_gate', Path(__file__).resolve().parents[1] / 'scripts/validate_team360_full_stack.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_duplicate_claim_is_rejected_before_router_overwrite():
    with pytest.raises(AssertionError):
        gate.assert_unique([{'path': '/same', 'method': 'GET'}] * 2)


def test_different_methods_can_coexist():
    gate.assert_unique([{'path': '/same', 'method': 'GET'}, {'path': '/same', 'method': 'POST'}])


def test_typed_path_normalization():
    assert gate.canonical('/item/{id:str}') == '/item/{id}'


def test_parameter_names_cannot_hide_collision():
    with pytest.raises(AssertionError):
        gate.assert_unique([{'path': '/item/{id:str}', 'method': 'GET'}, {'path': '/item/{other:int}', 'method': 'GET'}])


def test_openapi_coverage_mismatch_fails():
    with pytest.raises(AssertionError):
        gate.check_schema({'paths': {}}, [{'path': '/health', 'method': 'GET'}])


def test_openapi_broken_reference_fails():
    with pytest.raises(KeyError):
        gate.check_schema({'paths': {'/health': {'get': {'operationId': 'h', '$ref': '#/missing'}}}}, [{'path': '/health', 'method': 'GET'}])


def test_openapi_duplicate_operation_id_fails():
    with pytest.raises(AssertionError):
        gate.check_schema({'paths': {'/health': {'get': {'operationId': 'h'}, 'post': {'operationId': 'h'}}}}, [{'path': '/health', 'method': 'GET'}, {'path': '/health', 'method': 'POST'}])


def test_no_global_profile_is_used_as_inventory():
    assert 'resolve_runtime_profile' not in Path(gate.__file__).read_text()
    assert gate.owner('modules.messaging.webhooks.evolution_whatsapp') == 'Messaging'
    assert gate.owner('routes.console_me') == 'Console'


def test_scheduler_fixture_reads_real_settings_and_restores(monkeypatch):
    import asyncio
    from modules.flow.scheduler import FlowScheduler
    calls = []

    async def original(self):
        calls.append(True)
        return {'automation_enabled': True, 'scheduler_interval_seconds': 15, 'mail_intake_enabled': True}

    monkeypatch.setattr(FlowScheduler, '_read_settings', original)
    evidence = {}
    scheduler = FlowScheduler()
    with gate.safe_scheduler_fixture(evidence):
        result = asyncio.run(scheduler._read_settings())
        assert result['automation_enabled'] is False
        assert result['mail_intake_enabled'] is True
        with pytest.raises(AssertionError):
            asyncio.run(scheduler._execute_cycle(result))
    assert FlowScheduler._read_settings is original
    assert calls == [True] and evidence['database_automation_enabled'] is True
    assert evidence['forbidden_cycle_attempts'] == 1


def test_socket_guard_denies_delivery_ports_without_connecting():
    import socket
    evidence = {}
    with gate.local_connections_only(evidence), socket.socket() as sock:
        for destination in [('gmail.googleapis.com', 443), ('127.0.0.1', 18180), ('127.0.0.1', 7050)]:
            with pytest.raises(OSError, match='Gate forbids'):
                sock.connect(destination)
        with pytest.raises(OSError, match='Gate forbids'):
            sock.connect_ex(('external.invalid', 443))
    assert evidence['blocked_connections'] == 4


def test_scoped_cleanup_rejects_non_fixture_ids(monkeypatch):
    import asyncio
    monkeypatch.syspath_prepend(str(Path(gate.__file__).parent))
    from team360_full_gate_repository import cleanup_test_sessions
    for sessions in ([], ['production-session'], ['full_gate_%']):
        with pytest.raises(AssertionError):
            asyncio.run(cleanup_test_sessions('unused', sessions))
