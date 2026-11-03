"""Regressions of the WhatsApp reliability and UX correction of 21/10/2026.

The real incident of session ``c716012d8a10876a1cd8e617b5076bd4`` proved that
the business answer can be correct and still never reach the user:

* a correct answer of 5.523 characters was rejected by Meta (limit 4.096);
* a transient transport failure was reported as "I did not understand you";
* a ranking limit of 50 was inherited by a later customer query;
* the DEV session closed on a fixed duration during an active investigation.

These tests never call a model, never touch Foundation and never send a
message. They pin the deterministic behaviour of each correction.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from modules.messaging.delivery_guard import META_TEXT_LIMIT, guard_outbound
from modules.messaging.domain.delivery import MessagingSendError
from modules.messaging.providers.evolution.provider import EvolutionProvider
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.commercial_answer import format_commercial
from modules.telchi.assistant.handler import (BusinessAuthorization, BusinessPolicy, TelchiHandler,
                                              technical_failure_text)
from modules.telchi.assistant.luna import LunaError, LunaInterpreter
from modules.telchi.assistant.whatsapp_dev import (ActivityMarker, read_activity, session_close_reason,
                                                   session_timing)

from .test_assistant import MemoryStore, context, event, proposal

JULY = dict(start='2026-07-01', end_exclusive='2026-08-01')
AUGUST = dict(start='2026-08-01', end_exclusive='2026-09-01')
WINDOW = dict(start='2026-07-01', end_exclusive='2026-09-01')


# ------------------------------------------------------------------ fixtures

def long_answer(rows=50):
    """An answer shaped like the one Meta rejected: a title, many rows, caveats."""
    text = 'Cliente facturado en SAP con mayor importe — L03281 · MINOXITEL 5% LOCION - HOMRE x 100 mL. — julio y agosto de 2026\n\n'
    text += '\n'.join(
        f'C{i:06d} · CLIENTE COMERCIAL DE PRUEBA {i} S.A. — Bs 1.234,56 · julio de 2026: Bs 617,28 · '
        f'agosto de 2026: Bs 617,28 · entre julio de 2026 y agosto de 2026 subió Bs 0,00 (0,00 %)'
        for i in range(rows))
    text += ('\n\n«Cliente facturado en SAP» es la cuenta que recibe las líneas de factura (CardCode). '
             'No es el comprador final ni un cliente comercial validado: la taxonomía de cliente comercial '
             'no está acreditada en la publicación vigente. '
             'Importe registrado en líneas comerciales en BS, sin IVA de línea, antes de notas de crédito: '
             'no es facturación documental neta ni monto cobrado. '
             'Cobertura documental observada del 1 de julio de 2026 al 31 de agosto de 2026; '
             'no certifica el cierre completo del período.')
    return text


def commercial_result(rows=5):
    """The accredited result of the real turn: FARMACORP over L03281."""
    result_rows = [dict(key='C000061', label='FARMACORP S.A.', amount='115044.440000',
                        periods=[dict(period=dict(JULY), amount='72383.990000'),
                                 dict(period=dict(AUGUST), amount='42660.450000')])]
    for index in range(1, rows):
        result_rows.append(dict(key=f'CG{index:03d}', label='CONTROL TRIBUTARIO',
                                 amount=f'{70000 - index}.000000', periods=[]))
    return dict(capability='sales.commercial_line_amount_by.v1',
                parameters=dict(group_by='card_code', filters=dict(category='LAB_FINISHED_PRODUCT',
                                item_code='L03281', card_code=None), date_from=WINDOW['start'],
                                date_to_exclusive=WINDOW['end_exclusive'], periods=[dict(JULY), dict(AUGUST)],
                                breakdown_by='period', measure='m', order_by=[['amount', 'desc']],
                                limit=rows, currency='BS', dataset='commercial_line_amount'),
                rows=result_rows,
                total=dict(amount='586227.060000', line_count=2014, document_count=2012,
                           customer_count=468, product_count=1, first_date='2026-07-01',
                           last_date='2026-08-31'),
                universe_total=None, exceptions=[], accreditation='verified',
                coverage=dict(first_date='2026-07-01', last_date='2026-08-31'), focus={})


# ------------------------------------------------- P0: the delivery guard

def test_a_long_answer_never_reaches_the_provider_over_its_limit():
    text = long_answer()
    assert len(text) > META_TEXT_LIMIT
    decision = guard_outbound(text)
    assert decision.applied is True
    assert len(decision.text) <= META_TEXT_LIMIT
    assert decision.full_text == text  # the accredited answer is kept whole


def test_the_guard_keeps_the_main_result_and_the_material_warnings():
    decision = guard_outbound(long_answer())
    assert 'Cliente facturado en SAP con mayor importe' in decision.text
    assert 'no es facturación documental neta ni monto cobrado' in decision.text
    assert 'no certifica el cierre completo del período' in decision.text


def test_the_guard_never_splits_a_line_and_never_alters_a_figure():
    original = long_answer()
    decision = guard_outbound(original)
    original_lines = original.split('\n')
    for line in decision.text.split('\n'):
        assert line in original_lines or line.startswith('(Mostré')
    for figure in ('1.234,56', 'C000061', 'FARMACORP'):
        if figure in original:
            assert figure in decision.text


def test_the_guard_states_what_it_omitted():
    decision = guard_outbound(long_answer())
    assert 'auditoría de la sesión' in decision.text
    assert decision.omitted_lines > 0
    assert decision.reason == 'provider_text_limit'
    assert decision.audit()['accredited_length'] == len(decision.full_text)


def test_a_short_answer_is_delivered_untouched():
    text = 'FARMACORP S.A. — Bs 115.044,44.'
    decision = guard_outbound(text)
    assert decision.applied is False and decision.text == text


def test_a_fifty_row_ranking_is_still_a_deliverable_message():
    """Case C: a list of 50 results must never become an invalid message."""
    from modules.telchi.assistant.capabilities import format_result
    rows = [dict(item_code=f'L{index:05d}', description=f'PRODUCTO DE PRUEBA {index} x 100 mL',
                 amount=f'{100000 - index * 137}.450000') for index in range(50)]
    result = dict(capability='sales.product_line_amount_ranking.v1',
                  parameters=dict(category='LAB_FINISHED_PRODUCT', currency='BS',
                                  date_from='2026-07-01', date_to_exclusive='2026-09-01', limit=50),
                  rows=rows, coverage=dict(last_date='2026-08-31'))
    text = format_result(result)
    decision = guard_outbound(text)
    assert len(decision.text) <= META_TEXT_LIMIT
    assert 'L00000' in decision.text  # the main result survives
    if decision.applied:
        assert 'auditoría de la sesión' in decision.text


# ------------------------------- P0: the provider rejection is a failure

def provider_config():
    from modules.messaging.providers.evolution.config import EvolutionConfig
    return EvolutionConfig(base_url='http://evolution.invalid', instance='team360-meta-dev',
                           api_key='fixture-key', timeout=5)


def test_an_explicit_rejection_in_a_2xx_answer_is_a_confirmed_failure():
    def respond(request):
        return httpx.Response(200, json={'status': 'error', 'message': 'Text message too long'})
    provider = EvolutionProvider(provider_config(), transport=httpx.MockTransport(respond))
    with pytest.raises(MessagingSendError) as failure:
        provider.send_text(destination='123456789', text='hola')
    assert failure.value.code == 'provider_text_too_long'
    assert failure.value.uncertain is False


def test_a_rejected_message_is_never_reported_as_uncertain():
    def respond(request):
        return httpx.Response(200, json={'key': {'id': 'x', 'fromMe': True,
                                                'remoteJid': '123456789@s.whatsapp.net'},
                                         'status': 'error'})
    provider = EvolutionProvider(provider_config(), transport=httpx.MockTransport(respond))
    with pytest.raises(MessagingSendError) as failure:
        provider.send_text(destination='123456789', text='hola')
    assert failure.value.code == 'provider_message_rejected'
    assert failure.value.uncertain is False


def test_a_body_longer_than_the_limit_is_refused_before_any_call():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={})
    provider = EvolutionProvider(provider_config(), transport=httpx.MockTransport(respond))
    with pytest.raises(MessagingSendError) as failure:
        provider.send_text(destination='123456789', text='x' * (META_TEXT_LIMIT + 1))
    assert failure.value.code == 'provider_text_too_long'
    assert failure.value.uncertain is False
    assert not calls


def test_a_timeout_stays_the_only_uncertain_outcome():
    def respond(request):
        raise httpx.ReadTimeout('timeout', request=request)
    provider = EvolutionProvider(provider_config(), transport=httpx.MockTransport(respond))
    with pytest.raises(MessagingSendError) as failure:
        provider.send_text(destination='123456789', text='hola')
    assert failure.value.uncertain is True


def test_a_rejected_send_is_never_replayed_and_never_duplicated(monkeypatch):
    """Case E: a confirmed rejection is visible, and the turn is not replayed."""
    from contextlib import asynccontextmanager
    from modules.messaging.handlers import ChannelContext, MessageDispatcher, MessageResult
    from modules.messaging.handlers import HandlerRegistration
    from modules.messaging.repository import ChannelBinding
    from modules.messaging.service import MessagingService

    @asynccontextmanager
    async def tx(pool):
        yield object()
    monkeypatch.setattr('modules.messaging.service.transaction', tx)

    class Store:
        def __init__(self):
            self.claims, self.intents, self.finished = {}, {}, []
        async def claim(self, conn, binding, event, timings):
            if event.external_message_id in self.claims:
                return None
            self.claims[event.external_message_id] = {'id': event.external_message_id, 'thread_id': 'conversation'}
            return self.claims[event.external_message_id]
        async def complete_dispatch(self, conn, binding, claimed, result):
            pass
        async def intent(self, conn, binding, claimed, event, text, timings):
            self.intents[claimed['id']] = dict(id=claimed['id'], text=text)
            return claimed['id']
        async def begin_send(self, conn, binding, outbound_id, retry=False):
            return outbound_id not in self.intents or not self.intents[outbound_id].get('sent')
        async def recoverable_intent(self, conn, binding, event):
            return self.intents.get(event.external_message_id)
        async def lock_receipt(self, *args):
            pass
        async def finish(self, conn, outbound_id, *, receipt=None, error=None, timings):
            self.finished.append((outbound_id, error))

    class Handler:
        async def handle(self, message, context):
            return MessageResult('respuesta de negocio', context.correlation_id, 'DIRECT_AVAILABLE')

    channel = ChannelContext('channel', 'evolution', 'instance', 'receiver', 'telchi', 'workspace', 'telchi')
    dispatcher = MessageDispatcher(channels=(channel,),
                                   handlers={'telchi': HandlerRegistration(Handler())},
                                   identities=SimpleNamespace(resolve=lambda channel, phone: None))
    sends = []
    def send(**kwargs):
        sends.append(kwargs)
        raise MessagingSendError('provider_message_rejected')
    binding = ChannelBinding('workspace', 'channel', 'provider', 'instance', 'dev', 'telchi', 'tenant', 'receiver')
    store = Store()
    service = MessagingService(pool=object(), repository=store, binding=binding,
                                sender=SimpleNamespace(send_text=send), authorized_sender='',
                                dispatcher=dispatcher)
    event = SimpleNamespace(provider='evolution', channel='whatsapp', external_message_id='m1',
                            sender='123456789', recipients=('receiver',), text_body='hola',
                            metadata={'provider_instance': 'instance'})
    assert asyncio.run(service.process(event, t0_ms=0, t1_ms=1)) == 'send_failed'
    assert len(sends) == 1  # a confirmed rejection is never replayed automatically
    outbound_id, error = store.finished[-1]
    assert error.code == 'provider_message_rejected' and error.uncertain is False


# ----------------------------------------- P0: Luna technical error audit

def luna_transport(status=500):
    def respond(request):
        return httpx.Response(status, headers={'Location': 'https://example.invalid/'})
    return httpx.MockTransport(respond)


def test_a_transient_failure_is_retried_once_and_audited(monkeypatch):
    monkeypatch.setenv('OpenAI_Key_JAI_query', 'fixture-key')
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(500)
    interpreter = LunaInterpreter(transport=httpx.MockTransport(respond), retry_backoff_seconds=0)
    with pytest.raises(LunaError) as failure:
        asyncio.run(interpreter.interpret(text='consulta', state={}, history={}, turn_id='t'))
    assert len(calls) == 2  # the same request, once more, and never more
    assert failure.value.code == 'provider_server_error'
    assert failure.value.status == 500
    assert failure.value.attempts == 2
    audit = interpreter.last_failure
    assert audit == dict(code='provider_server_error', kind='technical', status=500,
                         retryable=True, duration_ms=audit['duration_ms'], attempts=2)


def test_a_permanent_failure_is_never_retried(monkeypatch):
    monkeypatch.setenv('OpenAI_Key_JAI_query', 'fixture-key')
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(401)
    interpreter = LunaInterpreter(transport=httpx.MockTransport(respond), retry_backoff_seconds=0)
    with pytest.raises(LunaError) as failure:
        asyncio.run(interpreter.interpret(text='consulta', state={}, history={}, turn_id='t'))
    assert len(calls) == 1
    assert failure.value.code == 'provider_client_error' and failure.value.status == 401


def test_a_credential_problem_is_a_configuration_failure(monkeypatch):
    monkeypatch.delenv('OpenAI_Key_JAI_query', raising=False)
    interpreter = LunaInterpreter(transport=luna_transport())
    with pytest.raises(LunaError) as failure:
        asyncio.run(interpreter.interpret(text='consulta', state={}, history={}, turn_id='t'))
    assert failure.value.code == 'credential_unavailable'
    assert failure.value.kind == 'configuration'


def test_a_technical_failure_is_never_reported_as_a_comprehension_failure():
    failure = LunaError('transport_timeout', kind='technical', retryable=True, attempts=2)
    text = technical_failure_text(failure)
    assert 'falla técnica' in text
    assert 'No pude interpretar' not in text
    assert 'No se ejecutó ninguna consulta' in text


def test_the_handler_reports_a_technical_failure_and_executes_nothing(monkeypatch):
    class Failing:
        async def interpret(self, **kwargs):
            raise LunaError('transport_timeout', kind='technical', retryable=True, attempts=2)
    calls = []
    async def query(**kwargs):
        calls.append(kwargs)
        raise AssertionError('a capability must not run after an interpretation failure')
    auth = BusinessAuthorization(BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True))
    handler = TelchiHandler(store=MemoryStore(), authorization=auth, interpreter=Failing(),
                            capabilities=SimpleNamespace(execute=query, availability=lambda state: None))
    result = asyncio.run(handler.handle(event('me das la facturacion de septiembre 2026'), context()))
    assert result.classification == 'ERROR'
    assert 'falla técnica' in result.text
    assert 'No pude interpretar' not in result.text
    audit = list(handler.store.audits.values())[-1]
    assert audit['luna_failure']['code'] == 'transport_timeout'
    assert audit['decision'] == 'LUNA_TECHNICAL_FAILURE'
    assert audit['execution_status'] == 'not_executed'
    assert not calls


# ------------------------------------- P1: informal language is understood

def test_the_interpreter_contract_accepts_informal_phrasing():
    from modules.telchi.assistant.luna import SYSTEM
    assert 'no requieren signos, acentos ni sintaxis rígida' in SYSTEM
    assert 'Preguntas naturales equivalentes' in SYSTEM


@pytest.mark.skipif(not __import__('os').environ.get('TEAM360_LIVE_LUNA'),
                    reason='live interpreter probe; set TEAM360_LIVE_LUNA=1 to run it')
def test_the_live_interpreter_understands_an_informal_request():
    """A live probe of the contract, never a WhatsApp message and never Foundation."""
    interpreter = LunaInterpreter()
    value = asyncio.run(interpreter.interpret(
        text='me das la facturacion de septiembre 2026', state=engine.EMPTY, history={}, turn_id='t'))
    fields = value['state_delta']['set']
    assert fields['/metric'] == 'sales.net_amount'
    assert fields['/period'] == {'start': '2026-09-01', 'end_exclusive': '2026-10-01'}


# ------------------------------------------- P2: the limit stays in its family

def ranking_state(limit=50):
    state = dict(engine.EMPTY | engine.INTENT_V2)
    state.update(metric='sales.product_line_amount_ranking',
                 requested_metrics=['sales.product_line_amount_ranking'],
                 business_category='LAB_FINISHED_PRODUCT', limit=limit, period=dict(AUGUST))
    return state


def test_a_ranking_limit_never_contaminates_a_later_customer_query():
    before = ranking_state(50)
    out = engine.process(before, proposal({
        '/metric': 'sales.commercial_line_amount_by',
        '/requested_metrics': ['sales.commercial_line_amount_by'],
        '/group_by': 'card_code'}), {}, 'turn')
    assert out['committed'] is True
    assert out['state_after'].get('limit', 10) == 10


def test_an_explicit_quantity_requested_by_the_user_is_respected():
    before = ranking_state(50)
    out = engine.process(before, proposal({
        '/metric': 'sales.commercial_line_amount_by',
        '/requested_metrics': ['sales.commercial_line_amount_by'],
        '/group_by': 'card_code', '/limit': 20}), {}, 'turn')
    assert out['committed'] is True
    assert out['state_after']['limit'] == 20


def test_a_limit_of_the_same_family_survives_a_refinement():
    before = ranking_state(50)
    out = engine.process(before, proposal({'/limit': 5}), {}, 'turn')
    assert out['committed'] is True
    assert out['state_after']['limit'] == 5


# ------------------------------------------- P2: the business answer comes first

def test_the_commercial_answer_leads_with_the_main_result_and_its_share():
    text = format_commercial(commercial_result())
    assert text.startswith('Cliente facturado en SAP con mayor importe')
    assert 'FARMACORP S.A. (C000061)' in text
    assert 'Bs 115.044,44' in text
    assert 'julio de 2026: Bs 72.383,99' in text
    assert 'agosto de 2026: Bs 42.660,45' in text
    assert '19,62 %' in text
    assert '35,7' not in text
    assert len(text) <= 1500


def test_the_commercial_answer_never_dumps_a_long_list():
    text = format_commercial(commercial_result(rows=50))
    assert text.count('CONTROL TRIBUTARIO') <= 1
    assert len(text) <= 1500
    assert 'Pedime' in text  # the next step is offered, not dumped


def test_the_answer_keeps_the_accredited_scope_and_its_warnings():
    text = format_commercial(commercial_result())
    assert 'no está acreditada en la publicación vigente' in text
    assert 'no es facturación documental neta ni monto cobrado' in text
    assert 'no certifica el cierre completo del período' in text
    assert 'Clasificación de producto actual, no histórica' in text


# ------------------------------------------------- Fase 4: session continuity

def test_the_session_timing_is_configurable_and_bounded():
    from types import SimpleNamespace as NS
    idle, total = session_timing(NS(idle_timeout=900, max_duration=14400, duration=None))
    assert (idle, total) == (900, 14400)
    idle, total = session_timing(NS(idle_timeout=None, max_duration=None, duration=600))
    assert total == 600 and idle <= 600
    with pytest.raises(ValueError):
        session_timing(NS(idle_timeout=10, max_duration=14400, duration=None))
    with pytest.raises(ValueError):
        session_timing(NS(idle_timeout=900, max_duration=300, duration=None))


def test_an_idle_session_closes_but_a_turn_in_flight_is_never_interrupted():
    assert session_close_reason(elapsed=100, idle_elapsed=1000, in_flight=0,
                                max_duration=14400, idle_timeout=900) == 'idle_timeout_reached'
    assert session_close_reason(elapsed=100, idle_elapsed=1000, in_flight=1,
                                max_duration=14400, idle_timeout=900) is None
    assert session_close_reason(elapsed=14400, idle_elapsed=1, in_flight=1,
                                max_duration=14400, idle_timeout=900) == 'max_duration_reached'


def test_the_activity_record_is_verifiable_and_secret_free(tmp_path):
    path = tmp_path/'activity.json'
    marker = ActivityMarker(path)
    marker.enter()
    assert marker.state['in_flight'] == 1 and marker.state['turns'] == 1
    marker.leave()
    recorded = read_activity(path)
    assert recorded['in_flight'] == 0 and recorded['turns'] == 1
    assert recorded['last_activity']
    assert set(recorded) == {'last_activity', 'in_flight', 'turns'}
