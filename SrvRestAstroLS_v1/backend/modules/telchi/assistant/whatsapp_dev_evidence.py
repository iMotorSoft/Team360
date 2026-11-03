"""Read-only reduction of one real WhatsApp exchange; never declares E2E_PASS."""
import hashlib
import json


def evaluate(rows, binding, approval, inbound_id):
    if len(rows) >= 100:
        raise ValueError('evidence_limit_reached')
    inbound = [r for r in rows if r['id'] == inbound_id and r['direction'] == 'inbound' and r['event_type'] == 'message']
    if len(inbound) != 1:
        raise ValueError('one_inbound_required')
    source = inbound[0]
    payload = source['payload_jsonb']
    if payload.get('dev_adapter') or not payload.get('metadata', {}).get('raw_event_reference'):
        raise ValueError('real_Evolution_ingress_required')
    audit = payload.get('telchi_assistant_v1', {})
    expected_owner = ['dev', 'telchi', approval['workspace_id'], binding.channel_id, approval['user_id']]
    if audit.get('owner') != expected_owner:
        raise ValueError('authorized_TelchiHandler_audit_required')
    if (audit.get('execution_status') != 'executed' or audit.get('capability_calls') != 1
            or not audit.get('required_permission')):
        raise ValueError('authorized_capability_execution_required')
    result = audit.get('execution_result') or {}
    source_info = result.get('source') or {}
    from modules.telchi.datalake.sales_query import PERMISSIONS, MONETARY_OPERATION, MONETARY_PERMISSION
    from modules.telchi.datalake.product_sales_query import PERMISSIONS as PRODUCT_PERMISSIONS
    contracts = {operation+'.v1': permission for operation, permission in (PERMISSIONS | PRODUCT_PERMISSIONS).items()}
    contracts[MONETARY_OPERATION+'.v1'] = MONETARY_PERMISSION
    from modules.telchi.datalake.invoice_lines_query import CAPABILITY as LINES, PERMISSION as LINES_PERMISSION
    from modules.telchi.datalake.invoice_amount_query import CAPABILITY as AMOUNT, PERMISSION as AMOUNT_PERMISSION
    contracts.update({LINES: LINES_PERMISSION, AMOUNT: AMOUNT_PERMISSION})
    contracts['telchi.sales_top_items.source_quantity.20260101_20260915.v1'] = 'telchi.sales.source_quantity.read.v1'
    if contracts.get(result.get('capability')) != audit['required_permission']:
        raise ValueError('capability_permission_contract_mismatch')
    if approval.get('access') == 'assistant':
        from .whatsapp_dev import approval_digest
        if (audit.get('pilot_approval_sha256') != approval_digest(approval)
                or audit.get('business_rbac_verified') is not True):
            raise ValueError('pilot_and_business_authorization_audit_required')
    if (not source_info.get('publication_id') or source_info.get('snapshot_id') is None
            or not source_info.get('updated_at')):
        raise ValueError('Foundation_capability_lineage_required')
    dispatch = payload.get('dispatch_result', {})
    if dispatch.get('classification') != 'DIRECT_AVAILABLE' or dispatch.get('correlation_id') != inbound_id:
        raise ValueError('correlated_business_response_required')
    outbound = [r for r in rows if r['direction'] == 'outbound' and r['event_type'] == 'message' and r['correlation_id'] == inbound_id]
    if len(outbound) != 1:
        raise ValueError('exactly_one_logical_outbound_required')
    reply = outbound[0]
    text = audit.get('response_prepared', {}).get('text')
    if (not text or text != dispatch.get('text') or text != reply['payload_jsonb'].get('text')
            or reply['thread_id'] != source['thread_id']):
        raise ValueError('prepared_dispatch_sent_response_mismatch')
    callbacks = {r['transport_status'] for r in rows if r['event_type'] == 'status'
        and r['correlation_id'] == inbound_id and r['provider_message_id'] == reply['provider_message_id']}
    return dict(status='EXCHANGE_OBSERVED_REVIEW_REQUIRED', E2E='NOT_DECLARED',
        correlation_sha256=hashlib.sha256(inbound_id.encode()).hexdigest(),
        handler='TelchiHandler', identity_scope_match=True, required_permission=audit['required_permission'],
        capability=result['capability'], capability_calls=1, execution_status='executed', logical_outbound_count=1,
        foundation_publication_sha256=hashlib.sha256(source_info['publication_id'].encode()).hexdigest(),
        provider_accepted=bool(reply['provider_message_id']),
        delivered_callback='delivered' in callbacks, read_callback='read' in callbacks,
        response_sha256=hashlib.sha256(text.encode()).hexdigest(),
        result_sha256=hashlib.sha256(json.dumps(audit.get('execution_result'), sort_keys=True).encode()).hexdigest(),
        limits='Device observation, duplicate/retry evidence and independent business-result review required.')
