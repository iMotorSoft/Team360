"""Team360 half-contract tests. No Evolution/Meta delivery claim."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest

from modules.messaging.domain.delivery import DeliveryEvent, MessagingSendError
from modules.messaging.domain.egress import OutboundIdentity, validate_egress
from modules.messaging.providers.evolution.config import EvolutionConfig
from modules.messaging.providers.evolution.provider import EvolutionProvider


def identity():
    return OutboundIdentity(*(str(uuid4()) for _ in range(4)), 'isolated-instance')


def evidence(context, **overrides):
    return {**context.wire(), 'acceptance': 'ACCEPTED', 'provider_message_id': 'wamid.fixture',
            'automatic_retry': False, 'durable': True, **overrides}


@pytest.mark.parametrize('key,value', [
    ('version', 2), ('version', True), ('outbound_intent_id', str(uuid4())),
    ('transport_attempt_id', str(uuid4())), ('workspace_id', str(uuid4())),
    ('channel_id', str(uuid4())), ('provider_instance', 'other-instance'),
    ('acceptance', 'DELIVERED'), ('provider_message_id', None),
    ('provider_message_id', 'invented'), ('automatic_retry', True),
    ('durable', False), ('http_status', True), ('http_status', 600),
    ('graph_code', '131030'),
])
def test_reject_invalid_or_mismatched_evidence(key, value):
    context = identity()
    with pytest.raises(ValueError):
        validate_egress(evidence(context, **{key: value}), context)


def test_allowlist_excludes_sensitive_payload():
    context = identity()
    result = validate_egress(evidence(context, body='secret', headers={'token': 'secret'}), context)
    assert 'secret' not in repr(result)


@pytest.mark.parametrize('status', [201, 500])
def test_acceptance_is_not_http_status_or_delivery(status):
    context = identity()
    def wire(request):
        assert json.loads(request.content)['team360_egress'] == context.wire()
        return httpx.Response(status, json={'egress': evidence(context)})
    sender = EvolutionProvider(EvolutionConfig('http://fixture.invalid', context.provider_instance,
                               'synthetic-key'), transport=httpx.MockTransport(wire))
    receipt = sender.send_intent(identity=context, destination='15550000001', text='fixture')
    assert receipt.external_message_id == 'wamid.fixture'
    assert receipt.egress['acceptance'] == 'ACCEPTED'
    assert 'delivery_status' not in receipt.egress


def test_missing_contract_never_falls_back_to_legacy():
    context = identity()
    calls = []
    def wire(request):
        calls.append(request)
        return httpx.Response(201, json={'key': {'id': 'wamid.fixture', 'fromMe': True}})
    sender = EvolutionProvider(EvolutionConfig('http://fixture.invalid', context.provider_instance,
                               'synthetic-key'), transport=httpx.MockTransport(wire))
    with pytest.raises(MessagingSendError) as error:
        sender.send_intent(identity=context, destination='15550000001', text='fixture')
    assert error.value.uncertain and len(calls) == 1


# Only the explicitly named disposable cluster is allowed. No inherited DB env.
SOCKET = Path(__file__).resolve().parents[3] / 'pgsocket'
EXPECTED_LAB = 'dev-promotion-v1'


@pytest.fixture(scope='module')
def isolated_db():
    if os.getenv('TEAM360_DURABLE_ISOLATED_TEST') != '1':
        pytest.skip('explicit disposable PostgreSQL opt-in required')
    import psycopg
    assert SOCKET.parent.name == EXPECTED_LAB
    assert (SOCKET / '.s.PGSQL.5432').exists()
    alias = Path(os.environ['TEAM360_DURABLE_SOCKET_ALIAS'])
    assert alias.is_symlink() and alias.resolve() == SOCKET
    assert str(alias).startswith('/tmp/t360-egress-')
    dsn = f'host={alias} dbname=postgres user=postgres connect_timeout=3'
    with psycopg.connect(dsn, autocommit=True) as conn:
        address, directory, version = conn.execute(
            "SELECT inet_server_addr(), current_setting('data_directory'), version()").fetchone()
        assert address is None and directory == '/var/lib/postgresql/18/docker'
        conn.execute('CREATE DATABASE team360_durable_fixture')
    dsn = f'host={alias} dbname=team360_durable_fixture user=postgres connect_timeout=3'
    backend = Path(__file__).resolve().parents[1]
    with psycopg.connect(dsn, autocommit=True) as conn:
        for migration in ('001_team360_core_schema.sql', '026_team360_messaging_transport_v1.sql'):
            conn.execute((backend / 'db/migrations' / migration).read_text())
    yield dsn
    with psycopg.connect(f'host={alias} dbname=postgres user=postgres', autocommit=True) as conn:
        conn.execute('DROP DATABASE team360_durable_fixture')


async def seed(dsn, tmp_path):
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool
    from modules.db.transaction import transaction
    from modules.messaging.domain.messages import InboundMessage
    from modules.messaging.repository import MessagingRepository
    repo = MessagingRepository()
    async with AsyncConnectionPool(dsn, min_size=1, max_size=2, kwargs={'row_factory': dict_row},
                                   open=False) as pool:
        async with transaction(pool) as conn:
            workspace = 'durable-' + uuid4().hex
            await conn.execute("INSERT INTO core_workspaces(slug,display_name) VALUES (%s,'Isolated fixture')",
                               (workspace,))
            binding = await repo.provision_dev_channel(conn, workspace_slug=workspace,
                        channel_alias='fixture', provider='evolution', instance='isolated-'+uuid4().hex)
            event = InboundMessage('evolution', 'whatsapp', uuid4().hex, '', '15550000001',
                ('fixture-receiver',), '', 'team360 ping 01', datetime.now(timezone.utc),
                {'provider_instance': binding.provider_instance})
            claimed = await repo.claim(conn, binding, event, {})
            outbound = await repo.intent(conn, binding, claimed, event, 'synthetic', {})
            assert await repo.intent(conn, binding, claimed, event, 'synthetic', {}) == outbound
    from dataclasses import asdict
    config = {'dsn': dsn, 'binding': asdict(binding), 'outbound_id': outbound,
              'calls': str(tmp_path / 'calls.jsonl'), 'meta_id': 'wamid.'+uuid4().hex}
    path = tmp_path / 'worker.json'
    path.write_text(json.dumps(config))
    return config, path


def worker(path, mode):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PG', 'TEAM360_', 'META_', 'DATABASE'))}
    env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONDONTWRITEBYTECODE='1')
    return subprocess.Popen([sys.executable, str(Path(__file__).with_name('durable_egress_worker.py')),
                             str(path), mode], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def collect(child):
    try:
        stdout, stderr = child.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        child.kill()  # This function created this exact child; no shared processes.
        child.communicate()
        raise
    return child.returncode, stdout, stderr


async def rows(config):
    import psycopg
    from psycopg.rows import dict_row
    async with await psycopg.AsyncConnection.connect(config['dsn'], row_factory=dict_row) as conn:
        return await (await conn.execute('SELECT * FROM message_events WHERE id=%s',
                                         (config['outbound_id'],))).fetchone()


@pytest.mark.parametrize('mode,exit_code,acceptance,calls', [
    ('accepted', 0, 'ACCEPTED', 1), ('accepted_http500', 0, 'ACCEPTED', 1),
    ('rejected', 0, 'REJECTED', 1), ('unknown', 0, 'UNKNOWN', 1),
    ('no_id', 0, None, 1), ('timeout', 0, None, 1),
    ('before_io', 71, None, 0), ('during_io', 72, None, 1),
    ('after_acceptance', 73, None, 1), ('persist_fail', 1, None, 1),
    ('early_callback', 0, 'ACCEPTED', 1),
])
def test_real_process_restart_never_resends(isolated_db, tmp_path, mode, exit_code, acceptance, calls):
    config, path = asyncio.run(seed(isolated_db, tmp_path))
    code, stdout, stderr = collect(worker(path, mode))
    assert code == exit_code, stderr
    row = asyncio.run(rows(config))
    payload = row['payload_jsonb']
    assert payload['outbound_identity']['outbound_intent_id'] == config['outbound_id']
    if acceptance:
        assert payload['egress']['acceptance'] == acceptance
        assert 'discard_secret' not in repr(payload)
    else:
        assert row['transport_status'] == 'unknown'
    if mode == 'early_callback':
        assert row['transport_status'] == 'delivered'
    before = Path(config['calls']).read_text().splitlines() if Path(config['calls']).exists() else []
    assert len(before) == calls
    # A fresh OS process reconstructs provider, service, repository and pool.
    code, stdout, stderr = collect(worker(path, 'accepted'))
    assert code == 0 and stdout.strip() == 'duplicate', stderr
    after = Path(config['calls']).read_text().splitlines() if Path(config['calls']).exists() else []
    assert before == after
    assert asyncio.run(rows(config))['payload_jsonb'] == payload


def test_two_processes_same_identity_one_execution(isolated_db, tmp_path):
    config, path = asyncio.run(seed(isolated_db, tmp_path))
    children = [worker(path, 'accepted'), worker(path, 'accepted')]
    results = [collect(child) for child in children]
    assert all(code == 0 for code, _, _ in results), results
    assert sorted(stdout.strip() for _, stdout, _ in results) == ['accepted', 'duplicate']
    assert len(Path(config['calls']).read_text().splitlines()) == 1


def test_team360_failure_before_execution_fence_sends_nothing(isolated_db, tmp_path):
    config, path = asyncio.run(seed(isolated_db, tmp_path))
    code, _, stderr = collect(worker(path, 'pre_fence_persist_fail'))
    assert code == 1 and 'DivisionByZero' in stderr
    assert not Path(config['calls']).exists()
    row = asyncio.run(rows(config))
    assert row['payload_jsonb']['initial_result'] == 'dispatch_intent'
    assert 'outbound_identity' not in row['payload_jsonb']


def test_only_explicit_retry_of_confirmed_rejection_allocates_new_attempt(isolated_db, tmp_path):
    import psycopg
    from psycopg.rows import dict_row
    from modules.messaging.repository import ChannelBinding, MessagingRepository
    config, path = asyncio.run(seed(isolated_db, tmp_path))
    assert collect(worker(path, 'rejected'))[0] == 0
    previous = asyncio.run(rows(config))['payload_jsonb']
    async def retry():
        async with await psycopg.AsyncConnection.connect(isolated_db, row_factory=dict_row) as conn:
            repo = MessagingRepository()
            binding = ChannelBinding(**config['binding'])
            assert not await repo.begin_send(conn, binding, config['outbound_id'])
            assert await repo.begin_send(conn, binding, config['outbound_id'], retry=True)
            assert not await repo.begin_send(conn, binding, config['outbound_id'], retry=True)
    asyncio.run(retry())
    current = asyncio.run(rows(config))['payload_jsonb']
    assert current['outbound_identity']['outbound_intent_id'] == config['outbound_id']
    assert current['outbound_identity']['transport_attempt_id'] != previous['outbound_identity']['transport_attempt_id']
    assert current['attempt_history'] == [{'identity': previous['outbound_identity'], 'egress': previous['egress']}]
    assert 'egress' not in current
    # The test reserves, but does not execute, the separately authorized attempt.
    assert len(Path(config['calls']).read_text().splitlines()) == 1


def test_unknown_and_unmappable_callback_remain_unknown_and_orphaned(isolated_db, tmp_path):
    import psycopg
    from psycopg.rows import dict_row
    from modules.messaging.repository import ChannelBinding, MessagingRepository
    config, path = asyncio.run(seed(isolated_db, tmp_path))
    assert collect(worker(path, 'timeout'))[0] == 0
    async def callback():
        async with await psycopg.AsyncConnection.connect(isolated_db, row_factory=dict_row) as conn:
            repo = MessagingRepository()
            binding = ChannelBinding(**config['binding'])
            assert not await repo.begin_send(conn, binding, config['outbound_id'], retry=True)
            await repo.delivery(conn, binding, DeliveryEvent('evolution', binding.provider_instance,
                config['meta_id'], 'delivered', datetime.now(timezone.utc)))
            orphan = await (await conn.execute("SELECT thread_id FROM message_events WHERE "
                "channel_id=%s AND provider_message_id=%s AND event_type='status'",
                (binding.channel_id, config['meta_id']))).fetchone()
            assert orphan['thread_id'] is None
    asyncio.run(callback())
    assert collect(worker(path, 'accepted'))[1].strip() == 'duplicate'
    assert asyncio.run(rows(config))['transport_status'] == 'unknown'


def test_late_orphan_duplicate_callback_scope(isolated_db, tmp_path):
    from dataclasses import replace
    import psycopg
    from psycopg.rows import dict_row
    from modules.messaging.repository import ChannelBinding, MessagingRepository
    config, path = asyncio.run(seed(isolated_db, tmp_path))
    binding = ChannelBinding(**config['binding'])
    repo = MessagingRepository()
    async def callbacks():
        async with await psycopg.AsyncConnection.connect(isolated_db, row_factory=dict_row) as conn:
            event = DeliveryEvent('evolution', binding.provider_instance, config['meta_id'], 'read',
                                  datetime.now(timezone.utc))
            await repo.delivery(conn, binding, event)
            await repo.delivery(conn, binding, event)
            statuses = await (await conn.execute("SELECT * FROM message_events WHERE channel_id=%s "
                "AND event_type='status'", (binding.channel_id,))).fetchall()
            assert len(statuses) == 1 and statuses[0]['thread_id'] is None
            for wrong in (replace(binding, workspace_id=str(uuid4())),
                          replace(binding, channel_id=str(uuid4())),
                          replace(binding, provider_instance='wrong-instance')):
                assert not await repo.begin_send(conn, wrong, config['outbound_id'])
                with pytest.raises(ValueError):
                    await repo.send_identity(conn, wrong, config['outbound_id'])
    asyncio.run(callbacks())
    code, _, stderr = collect(worker(path, 'accepted'))
    assert code == 0, stderr
    assert asyncio.run(rows(config))['transport_status'] == 'read'
    async def late():
        async with await psycopg.AsyncConnection.connect(isolated_db, row_factory=dict_row) as conn:
            await repo.delivery(conn, binding, DeliveryEvent('evolution', binding.provider_instance,
                config['meta_id'], 'sent', datetime.now(timezone.utc)))
            orphan = DeliveryEvent('evolution', binding.provider_instance, 'wamid.unmapped',
                                   'delivered', datetime.now(timezone.utc))
            await repo.delivery(conn, binding, orphan)
            # Unknown exact Meta identity remains orphan; no guessing.
            orphan_row = await (await conn.execute("SELECT thread_id FROM message_events WHERE "
                "channel_id=%s AND provider_message_id='wamid.unmapped'", (binding.channel_id,))).fetchone()
            assert orphan_row['thread_id'] is None
    asyncio.run(late())
    assert asyncio.run(rows(config))['transport_status'] == 'read'
