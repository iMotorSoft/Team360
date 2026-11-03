"""Evolution adapter unit and HTTP boundary tests; synthetic identifiers only."""
from datetime import datetime, timezone
import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from litestar import Litestar
from litestar.testing import TestClient

from modules.messaging.domain.delivery import DeliveryEvent, MessagingSendError
from modules.messaging.domain.whatsapp import WhatsAppMessageSenderPort
from modules.messaging.providers.evolution.config import EvolutionConfig, EvolutionConfigurationError
from modules.messaging.providers.evolution.mapper import normalize_events
from modules.messaging.providers.evolution.provider import EvolutionProvider
from modules.messaging.service import fixed_response, MessagingService
from modules.messaging.settings import MessagingDevSettings
from modules.messaging.webhooks.evolution_whatsapp import EvolutionWhatsAppWebhookController
from modules.messaging.repository import ChannelBinding
from modules.messaging.benchmark import report, stats
import modules.messaging.service as service_module
import modules.messaging.webhooks.evolution_whatsapp as webhook

NOW = datetime.now(timezone.utc)
INSTANCE = 'test-instance'
SENDER = '15550000001'
TOKEN = 'synthetic-webhook-token-0000000000000000'


def payload(text='team360 ping 01', message_id='synthetic-inbound'):
    return {'event': 'messages.upsert', 'instance': INSTANCE, 'apikey': 'discard-this-secret',
            'data': {'key': {'id': message_id, 'remoteJid': SENDER+'@s.whatsapp.net', 'fromMe': False},
                     'message': {'conversation': text}, 'messageTimestamp': 1700000000}}


def normalize(value):
    return normalize_events(value, instance=INSTANCE, recipient='synthetic-recipient', received_at=NOW)


@pytest.fixture
def dev_env(monkeypatch):
    values = {'TEAM360_ENV': 'development', 'TEAM360_MESSAGING_DEV_ENABLED': '1',
              'TEAM360_EVOLUTION_BASE_URL': 'http://127.0.0.1:9', 'TEAM360_EVOLUTION_INSTANCE': INSTANCE,
              'TEAM360_EVOLUTION_API_KEY': 'synthetic-key', 'TEAM360_MESSAGING_WORKSPACE_SLUG': 'test-workspace',
              'TEAM360_MESSAGING_CHANNEL_ALIAS': 'test-channel',
              'TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER': SENDER, 'TEAM360_MESSAGING_WEBHOOK_TOKEN': TOKEN}
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_normalized_text_identity_and_no_raw_payload():
    message, = normalize(payload())
    assert (message.provider, message.channel, message.sender, message.external_message_id,
            message.text_body, message.recipients) == (
                'evolution', 'whatsapp', SENDER, 'synthetic-inbound', 'team360 ping 01', ('synthetic-recipient',))
    assert message.received_at == NOW
    assert message.metadata['provider_instance'] == INSTANCE
    assert len(message.metadata['raw_event_reference']) == 64
    assert 'apikey' not in message.metadata
    assert 'discard-this-secret' not in repr(message)


def test_extended_text_and_batch():
    value = payload()
    value['data']['message'] = {'extendedTextMessage': {'text': 'team360 ping 02'}}
    value['data'] = [value['data'], None, 4]
    assert normalize(value)[0].text_body == 'team360 ping 02'


@pytest.mark.parametrize('value', [None, [], {}, {'event':'connection.update', 'instance':INSTANCE},
                                 {'event':'messages.upsert', 'instance':INSTANCE, 'data':None}])
def test_incomplete_or_irrelevant_payload(value):
    assert normalize(value) == ()


@pytest.mark.parametrize('change', ['instance','self','id','sender','group','text','media','long','key'])
def test_ignore_wrong_instance_nontext_self_and_bad_identity(change):
    value = payload()
    if change == 'instance': value['instance'] = 'another-instance'
    if change == 'self': value['data']['key']['fromMe'] = True
    if change == 'id': value['data']['key'].pop('id')
    if change == 'sender': value['data']['key']['remoteJid'] = 'bad'
    if change == 'group': value['data']['key']['remoteJid'] = '15550000001@g.us'
    if change == 'text': value['data']['message']['conversation'] = ''
    if change == 'media': value['data']['message'] = {'imageMessage': {'caption':'team360 ping 01'}}
    if change == 'long': value['data']['message']['conversation'] = 'x'*4097
    if change == 'key': value['data']['key'] = None
    assert normalize(value) == ()


@pytest.mark.parametrize('status,expected', [('SENT','sent'),('DELIVERED','delivered'),('READ','read'),
                                            ('FAILED','failed'),('DELIVERY_ACK','delivered')])
def test_meta_status_uses_key_id_even_when_from_me_false(status, expected):
    event, = normalize({'event':'messages.update','instance':INSTANCE,
                       'data':{'keyId':'synthetic-outbound','messageId':'prisma-not-provider-id',
                               'fromMe':False,'status':status}})
    assert event == DeliveryEvent('evolution',INSTANCE,'synthetic-outbound',expected,NOW)


@pytest.mark.parametrize('record', [{}, {'keyId':'x','status':'PENDING'}, {'status':'READ'}, 4])
def test_bad_status_ignored(record):
    assert normalize({'event':'messages.update','instance':INSTANCE,'data':record}) == ()


@pytest.mark.parametrize('number', range(1,21))
def test_exact_fixed_responder(number):
    assert fixed_response(f'team360 ping {number:02}') == f'TEAM360 PONG {number:02}'


@pytest.mark.parametrize('text', ['team360 ping 00','team360 ping 21','TEAM360 ping 01',
                                 'team360 ping 1','team360 ping 01\n',' team360 ping 01'])
def test_no_other_routing(text):
    assert fixed_response(text) is None


def test_sender_port_and_outbound_wire_format():
    def handler(request):
        assert request.url.path == '/message/sendText/test-instance'
        assert request.headers['apikey'] == 'synthetic-key'
        assert request.content == b'{"number":"15550000001","text":"TEAM360 PONG 01"}'
        return httpx.Response(201, json={'key':{'id':'synthetic-outbound','fromMe':True,
                                              'remoteJid':SENDER+'@s.whatsapp.net'}})
    provider = EvolutionProvider(EvolutionConfig('http://test',INSTANCE,'synthetic-key'),
                                 transport=httpx.MockTransport(handler))
    assert isinstance(provider, WhatsAppMessageSenderPort)
    assert provider.send_text(destination=SENDER,text='TEAM360 PONG 01').external_message_id == 'synthetic-outbound'
    assert 'synthetic-key' not in repr(provider._config)


@pytest.mark.parametrize('kind,code,uncertain', [('500','provider_http_error',True),
    ('401','provider_http_error',False),('timeout','provider_timeout',True),
    ('offline','provider_unavailable',False),('invalid','provider_invalid_response',True),
    ('badkey','provider_invalid_response',True),('wrongrecipient','provider_invalid_response',True)])
def test_provider_errors_sanitized(kind, code, uncertain):
    def handler(request):
        if kind == 'timeout': raise httpx.ReadTimeout('secret-should-not-leak',request=request)
        if kind == 'offline': raise httpx.ConnectError('secret-should-not-leak',request=request)
        if kind.isdigit(): return httpx.Response(int(kind),text='secret-should-not-leak')
        if kind == 'invalid': return httpx.Response(201,text='not-json-secret')
        if kind == 'badkey': return httpx.Response(201,json={'key':None})
        return httpx.Response(201,json={'key':{'id':'x','fromMe':True,'remoteJid':'wrong'}})
    provider = EvolutionProvider(EvolutionConfig('http://test',INSTANCE,'synthetic-key'),
                                 transport=httpx.MockTransport(handler))
    with pytest.raises(MessagingSendError) as exc:
        provider.send_text(destination=SENDER,text='TEAM360 PONG 01')
    assert str(exc.value) == code
    assert exc.value.uncertain is uncertain


def test_dev_config_and_missing_key_fail_closed(dev_env,monkeypatch):
    assert MessagingDevSettings.from_env().authorized_sender == SENDER
    assert '15550000001' not in repr(MessagingDevSettings.from_env())
    monkeypatch.delenv('TEAM360_EVOLUTION_API_KEY')
    with pytest.raises(EvolutionConfigurationError): EvolutionConfig.from_env()
    for environment in ('production', 'staging', '', 'unknown'):
        monkeypatch.setenv('TEAM360_ENV', environment)
        with pytest.raises(ValueError):
            MessagingDevSettings.from_env()
    monkeypatch.delenv('TEAM360_ENV')
    with pytest.raises(ValueError):
        MessagingDevSettings.from_env()


def test_webhook_auth_json_filter_and_disabled(dev_env,monkeypatch):
    app = Litestar(route_handlers=[EvolutionWhatsAppWebhookController])
    path = '/webhooks/messaging/evolution/whatsapp'
    with TestClient(app) as client:
        assert client.post(path,json=payload()).status_code == 401
        headers={'x-team360-webhook-token':TOKEN}
        assert client.post(path,content=b'bad',headers=headers).status_code == 400
        assert client.post(path,json={},headers=headers).json()['results'] == {'ignored':1}
        monkeypatch.setenv('TEAM360_MESSAGING_DEV_ENABLED','0')
        assert client.post(path,json=payload(),headers=headers).status_code == 503


def test_webhook_normalizes_before_service(dev_env,monkeypatch):
    seen=[]
    class Service:
        async def process(self,event,**timings):
            seen.append(event)
            assert timings['t1_ms'] >= timings['t0_ms']
            return 'accepted'
    async def build(*args): return Service()
    monkeypatch.setattr(webhook,'build_service',build)
    with TestClient(Litestar(route_handlers=[EvolutionWhatsAppWebhookController])) as client:
        result=client.post('/webhooks/messaging/evolution/whatsapp',json=payload(),
                           headers={'x-team360-webhook-token':TOKEN})
    assert result.json()['results']=={'accepted':1}
    assert seen[0].sender==SENDER and not isinstance(seen[0],dict)


# @lat: [[team360-platform#Team360 Platform#WhatsApp transport boundary#Adapter unit specifications]]
def test_unit_idempotency_and_authorization(monkeypatch):
    seen=set()
    sends=[]
    class Repository:
        async def claim(self, conn, binding, message, timings):
            if message.external_message_id in seen: return None
            seen.add(message.external_message_id)
            return {'id':'inbound','thread_id':'thread'}
        async def intent(self,*args): return 'outbound'
        async def begin_send(self,*args,**kwargs): return True
        async def lock_receipt(self,*args): pass
        async def finish(self,*args,**kwargs): assert kwargs['receipt'].external_message_id=='sent'
    class Sender:
        def send_text(self,**kwargs):
            from modules.messaging.domain.messages import OutboundMessageReceipt
            sends.append(kwargs)
            return OutboundMessageReceipt('sent',SENDER)
    @asynccontextmanager
    async def tx(pool): yield object()
    monkeypatch.setattr(service_module,'transaction',tx)
    async def exercise():
        service=MessagingService(pool=object(),repository=Repository(),
            binding=ChannelBinding('workspace','channel','provider',INSTANCE),
            sender=Sender(),authorized_sender=SENDER)
        event=normalize(payload())[0]
        assert await service.process(event,t0_ms=1,t1_ms=2)=='accepted'
        assert await service.process(event,t0_ms=1,t1_ms=2)=='duplicate'
        other=payload(message_id='unauthorized')
        other['data']['key']['remoteJid']='15550000002@s.whatsapp.net'
        assert await service.process(normalize(other)[0],t0_ms=1,t1_ms=2)=='unauthorized'
    asyncio.run(exercise())
    assert len(seen)==1 and len(sends)==1


def test_latency_statistics_and_missing_measurements():
    values=stats([1,2,3,4])
    assert values['p50']==2.5 and values['p95']==pytest.approx(3.85)
    assert stats([])=={'n':0}
    result=report([],NOW)
    assert all(metric=={'n':0} for metric in result['metrics'].values())
    assert result['complete_20_sequential_pairs'] is False
