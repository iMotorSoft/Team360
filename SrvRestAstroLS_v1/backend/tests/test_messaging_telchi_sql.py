"""Deterministic SQL gate tests; no phone/transport credentials or LLM."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from modules.messaging.telchi_sql import ERROR_TEXT, TelchiSqlAdapter, format_sales, is_telchi_trigger
from modules.messaging.service import MessagingService, epoch_ms
from modules.messaging.repository import ChannelBinding
from modules.messaging.providers.evolution.mapper import normalize_events
from modules.telchi.datalake.messaging_sales_query import TelchiQueryError, query_fixed_sales
import modules.messaging.service as service_module


@pytest.mark.parametrize('text', ['hola', ' Hola ', 'HOLA', '\nhola\t'])
def test_exact_trigger(text):
    assert is_telchi_trigger(text)


@pytest.mark.parametrize('text', ['', 'hola!', 'hola ventas', 'holá', 'team360 ping 01'])
def test_not_trigger(text):
    assert not is_telchi_trigger(text)


def test_formatter_source_quantity_and_empty():
    text = format_sales({'rows': [{'item_code': 'L001', 'quantity': '51436.1200000000'}]*10})
    assert '51.436,12' in text and '5. L001' in text and '6. L001' not in text
    assert 'JSON' not in text and 'no netea' in text
    assert 'Sin resultados' in format_sales({'rows': []})


@pytest.mark.parametrize('code', ['datalake_timeout', 'datalake_connection_error', 'datalake_query_error'])
def test_sanitized_error(code):
    async def query(**kwargs):
        raise TelchiQueryError(code)
    text, audit = asyncio.run(TelchiSqlAdapter(query).execute())
    assert text == ERROR_TEXT and audit == {'status': 'failed', 'error_code': code}


def test_unexpected_error_no_details():
    async def query(**kwargs):
        raise RuntimeError('password=SECRET SQL SELECT')
    text, audit = asyncio.run(TelchiSqlAdapter(query).execute())
    assert 'SECRET' not in str((text, audit))


def test_overlap_rejected_without_second_worker_or_queue(monkeypatch):
    import modules.telchi.datalake.messaging_sales_query as module
    async def exercise():
        started, finish = asyncio.Event(), asyncio.Event()
        calls = []
        async def worker(**kwargs):
            calls.append(1)
            started.set()
            await finish.wait()
            return {'rows': []}
        monkeypatch.setattr(module, '_query_in_worker', worker)
        first = asyncio.create_task(module.query_fixed_sales())
        await started.wait()
        with pytest.raises(TelchiQueryError, match='datalake_busy'):
            await module.query_fixed_sales()
        assert len(calls)==1
        finish.set()
        await first
        assert not module._QUERY_LOCK.locked()
    asyncio.run(exercise())


def test_worker_timeout_and_cancellation_reap_exact_child(monkeypatch):
    import modules.telchi.datalake.messaging_sales_query as module
    class Process:
        returncode = None
        killed = False
        async def communicate(self):
            await asyncio.sleep(20)
        def kill(self):
            self.killed = True
        async def wait(self):
            self.returncode = -9
    async def exercise(cancel):
        child = Process()
        async def create(*args, **kwargs):
            return child
        monkeypatch.setattr(module.asyncio, 'create_subprocess_exec', create)
        task = asyncio.create_task(query_fixed_sales(timeout_seconds=.01))
        if cancel:
            await asyncio.sleep(.001)
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TelchiQueryError):
            await task
        assert child.killed and child.returncode == -9
    asyncio.run(exercise(False))
    asyncio.run(exercise(True))


def test_audit_lock_order_matches_claim():
    from modules.messaging.repository import MessagingRepository
    statements = []
    class Connection:
        async def execute(self, sql, params):
            statements.append(sql)
    asyncio.run(MessagingRepository().record_sql_gate(Connection(), ChannelBinding('w','c','p','i'),
        {'id':'message','thread_id':'thread'}, {'tenant':'telchi'}))
    assert 'UPDATE message_threads' in statements[0]
    assert 'UPDATE message_events' in statements[1]


def test_settings_mapping_opt_in_and_fail_closed(monkeypatch):
    from modules.messaging.settings import MessagingDevSettings
    values = {'TEAM360_ENV':'development','TEAM360_MESSAGING_DEV_ENABLED':'1',
              'TEAM360_MESSAGING_WORKSPACE_SLUG':'test','TEAM360_MESSAGING_CHANNEL_ALIAS':'test',
              'TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER':'15550000001',
              'TEAM360_MESSAGING_WEBHOOK_TOKEN':'synthetic-token-000000000000000000000'}
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('TEAM360_MESSAGING_DEV_SQL_TENANT', raising=False)
    assert MessagingDevSettings.from_env().telchi_tenant is None
    monkeypatch.setenv('TEAM360_MESSAGING_DEV_SQL_TENANT','telchi')
    assert MessagingDevSettings.from_env().telchi_tenant == 'telchi'
    monkeypatch.setenv('TEAM360_MESSAGING_DEV_SQL_TENANT','other')
    with pytest.raises(ValueError):
        MessagingDevSettings.from_env()
    monkeypatch.setenv('TEAM360_MESSAGING_DEV_SQL_TENANT','telchi')
    monkeypatch.setenv('TEAM360_ENV','production')
    with pytest.raises(ValueError):
        MessagingDevSettings.from_env()


def test_service_authorization_idempotency_audit_and_new_id(monkeypatch):
    @asynccontextmanager
    async def transaction(pool):
        yield object()
    monkeypatch.setattr(service_module, 'transaction', transaction)
    class Repository:
        seen = set()
        audits = []
        intents = []
        async def claim(self, conn, binding, event, timings):
            if event.external_message_id in self.seen:
                return None
            self.seen.add(event.external_message_id)
            return {'id': event.external_message_id, 'thread_id': 'thread'}
        async def record_sql_gate(self, conn, binding, claimed, audit):
            import copy
            self.audits.append(copy.deepcopy(audit))
        async def intent(self, conn, binding, claimed, event, reply, timings):
            self.intents.append(reply)
            return 'outbound'
        async def lock_receipt(self, *args): pass
        async def finish(self, *args, **kwargs): pass
    class Sender:
        calls = []
        def send_text(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(external_message_id='outbound-id')
    async def exercise():
        calls = []
        async def query(**kwargs):
            calls.append(1)
            return {'rows': [{'item_code':'L001', 'quantity':'123'}],
                    'sql_started_ms':epoch_ms(), 'sql_finished_ms':epoch_ms()}
        repo, sender = Repository(), Sender()
        svc = MessagingService(pool=None, repository=repo, binding=ChannelBinding('w','c','p','test'),
            sender=sender, authorized_sender='15550000001', tenant='telchi', telchi_capability=TelchiSqlAdapter(query))
        def event(id, text='hola', sender='15550000001'):
            return normalize_events({'event':'messages.upsert', 'instance':'test',
                'data':{'key':{'id':id,'remoteJid':sender+'@s.whatsapp.net','fromMe':False},
                        'message':{'conversation':text}}}, instance='test', recipient='test',
                received_at=datetime.now(timezone.utc))[0]
        async def send(value):
            return await svc.process(value,t0_ms=epoch_ms(),t1_ms=epoch_ms())
        assert await send(event('bad',sender='15550000002')) == 'unauthorized'
        assert not calls and not repo.seen
        assert await send(event('other',text='hola!')) == 'received'
        assert not calls
        outcomes = await asyncio.gather(send(event('in-1',' HOLA ')), send(event('in-1',' HOLA ')))
        assert sorted(outcomes) == ['accepted','duplicate']
        assert len(calls) == len(sender.calls) == 1
        assert repo.audits[0]['status'] == 'started'
        assert repo.audits[-1]['tenant'] == 'telchi'
        assert await send(event('in-2')) == 'accepted'
        assert len(calls) == len(sender.calls) == 2
        svc.tenant = None
        assert await send(event('no-mapping')) == 'received'
        assert len(calls) == 2
    asyncio.run(exercise())
