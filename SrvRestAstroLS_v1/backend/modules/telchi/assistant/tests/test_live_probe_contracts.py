"""Synthetic evidence contracts only; not live HTTP/auth/WhatsApp results."""
from copy import deepcopy
import pytest

from modules.telchi.assistant.tests.runtime_http.authenticated_semantics_probe import check_response
from modules.telchi.assistant.tests.runtime_http.whatsapp_delivery_probe import evaluate


def test_http_200_without_effective_connection_is_not_proof():
    with pytest.raises(AssertionError, match='connection_not_proven'):
        check_response(200, {'classification': 'NEEDS_CLARIFICATION'}, 'scope')
    assert check_response(401, {}, 'deny')['status'] == 'PASS'
    with pytest.raises(AssertionError):
        check_response(200, {}, 'deny')


def test_http_probe_requires_no_execution_and_actual_role_audit():
    audit = dict(business_semantics=dict(connection=dict(role='team360_business_semantics_dev_runtime',
        rolsuper=False, rolbypassrls=False), semantic_guard={'requires_clarification': True}),
        decision='ASK', capability_calls=0, execution_status='not_executed')
    body = dict(audit=audit, classification='NEEDS_CLARIFICATION', correlation_id='unit-id', conversation_id='unit-thread')
    assert check_response(200, body, 'scope')['status'] == 'PASS'
    audit['capability_calls'] = 1
    with pytest.raises(AssertionError):
        check_response(200, body, 'scope')


def evidence():
    rows, cases, duplicates = [], [], {}
    for n, kind in enumerate(('ASK', 'BLOCK', 'EXECUTE')):
        iid = 'unit-inbound-'+str(n)
        classification = {'ASK': 'NEEDS_CLARIFICATION', 'BLOCK': 'ERROR', 'EXECUTE': 'DIRECT_AVAILABLE'}[kind]
        calls = int(kind == 'EXECUTE')
        cases.append(dict(kind=kind, inbound_id=iid))
        duplicates[iid] = {'results': {'duplicate': 1}}
        rows += [dict(id=iid, thread_id='unit-thread', direction='inbound', event_type='message',
            payload_jsonb=dict(metadata={'raw_event_reference': 'synthetic-hash'},
                dispatch_result=dict(classification=classification, correlation_id=iid, text='unit-response'),
                telchi_assistant_v1=dict(capability_calls=calls, execution_status='executed' if calls else 'not_executed',
                    response_prepared=dict(text='unit-response')))),
            dict(id='unit-outbound-'+str(n), thread_id='unit-thread', direction='outbound', event_type='message',
                 correlation_id=iid, provider_message_id='unit-provider-'+str(n), transport_status='delivered',
                 payload_jsonb=dict(text='unit-response')),
            dict(id='unit-status-'+str(n), direction='outbound', event_type='status', correlation_id=iid,
                 provider_message_id='unit-provider-'+str(n), transport_status='delivered',
                 payload_jsonb=dict(t_callback_ms=1234))]
    return rows, cases, duplicates


def test_delivery_observation_does_not_self_declare_E2E():
    result = evaluate(*evidence())
    assert result['status'] == 'DELIVERY_OBSERVED'
    assert result['E2E'].startswith('NOT_DECLARED')
    assert len(result['exchanges']) == 3


@pytest.mark.parametrize('fault', ['acceptance_only', 'missing_callback', 'duplicate_send', 'wrong_correlation',
                                  'changed_text', 'HTTP_adapter', 'missing_replay', 'double_execution'])
def test_reject_incomplete_delivery_or_idempotence_evidence(fault):
    rows, cases, duplicates = evidence()
    if fault == 'acceptance_only': rows[1]['transport_status'] = 'sent'
    if fault == 'missing_callback': rows.pop(2)
    if fault == 'duplicate_send': rows.append(deepcopy(rows[1]))
    if fault == 'wrong_correlation': rows[1]['correlation_id'] = 'other'
    if fault == 'changed_text': rows[1]['payload_jsonb']['text'] = 'different'
    if fault == 'HTTP_adapter': rows[0]['payload_jsonb']['dev_adapter'] = {'synthetic': True}
    if fault == 'missing_replay': duplicates[cases[0]['inbound_id']] = {'results': {'accepted': 1}}
    if fault == 'double_execution': rows[6]['payload_jsonb']['telchi_assistant_v1']['capability_calls'] = 2
    with pytest.raises(AssertionError):
        evaluate(rows, cases, duplicates)
