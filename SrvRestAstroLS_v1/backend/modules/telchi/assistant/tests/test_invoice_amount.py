from copy import deepcopy
from dataclasses import replace
import pytest
from modules.telchi.datalake.invoice_amount_query import CAPABILITY, PERMISSION
from .test_assistant import run, event, proposal
from .test_invoice_continuity import prepare, document
from .test_result_references import select


@pytest.mark.parametrize('authorized', [True, False])
@run
async def test_amount_requires_own_permission_and_preserves_document(monkeypatch, authorized):
    h, db, llm, calls, checks, c, line_calls = prepare(monkeypatch, [
        proposal({'/metric':'sales.latest_documents'}, intent='NEW_QUERY'),
        select(1, result_id='turn-1'), document(),
        document('SELECT_DOCUMENT', field='amount'), document('SELECT_DOCUMENT', field='doc_num')])
    if authorized:
        c = replace(c, sender_identity=replace(c.sender_identity, permissions=c.sender_identity.permissions | {PERMISSION}))
    amount_calls = []
    async def amount(opts):
        amount_calls.append(opts)
        return dict(capability=CAPABILITY, parameters=opts,
            document={k: opts[k] for k in ('source_system','document_type','doc_entry','doc_num','doc_date')},
            source=dict(publication_id=opts['publication_id'],snapshot_id=opts['snapshot_id'],updated_at='2026-09-28'),
            rows=[dict(amount='25.00',currency='BS')], read_only=True,sap_accessed=False)
    h.capabilities.invoice_amount = amount
    for n in range(1, 5):
        response = await h.handle(event(), replace(c, correlation_id=f'turn-{n}'))
    if authorized:
        assert response.classification == 'DIRECT_AVAILABLE'
        assert 'BS 25,00' in response.text
        assert all(internal not in response.text for internal in ('DocEntry','OINV','snapshot','Foundation','sales.invoice'))
        audit = db.events['turn-4']['telchi_assistant_v1']
        assert audit['execution_result']['capability'] == CAPABILITY
        assert audit['required_permission'] == PERMISSION
        assert len(amount_calls) == 1 and amount_calls[0]['doc_entry'] == '900'
        # A cached amount cannot survive revocation.
        denied_context = replace(c, sender_identity=replace(c.sender_identity,permissions=c.sender_identity.permissions-{PERMISSION}))
        assert (await h.handle(event(),replace(denied_context,correlation_id='turn-4'))).classification == 'DENIED'
    else:
        assert response.classification == 'DENIED' and not amount_calls
    response = await h.handle(event(),replace(c,correlation_id='turn-5'))
    assert response.classification == 'DIRECT_AVAILABLE' and '260192728' in response.text
    assert len(calls) == len(line_calls) == 1
