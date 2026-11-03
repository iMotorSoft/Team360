"""Exactly one real Luna call, recorded authenticated DEV scope; no DB/transport/data query.

Run from backend with --output <new JSON path>. Uses the approved pilot's existing
RBAC evidence, NOT a fresh login or certification of current effective permissions.
"""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

from dotenv import dotenv_values
from modules.messaging.handlers import ChannelContext, MessageContext, SenderIdentity
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy
from modules.telchi.assistant.luna import CREDENTIAL_ENV, LunaInterpreter

QUESTION = 'Mostrame las últimas 5 facturas de venta de Telchi.'


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Exclusive create: never overwrite existing gate/evidence manifests.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        root = Path(__file__).resolve().parents[6]
        source = root / 'data/reports/telchi/sales_rbac_business_runtime_v1/effective_and_security.json'
        recorded = json.loads(source.read_text())
        pilot = recorded['identities']['pilot']
        workspace = recorded['identities']['workspace']['id']
        permission = 'telchi.sales.latest_documents.read.v1'
        assert pilot['workspace_id'] == workspace
        assert permission in recorded['effective'] and recorded['positive_authorization'][permission] is True
        base_permission = 'telchi.sales.source_quantity.read.v1'
        channel = ChannelContext('offline-no-transport', 'offline', 'offline', 'offline',
                                 'telchi', workspace, 'telchi')
        identity = SenderIdentity(pilot['id'], 'telchi', workspace,
                                  permissions=frozenset(recorded['effective']))
        context = MessageContext(channel, identity, '', 'offline', 'enterprise-context-single', frozenset())
        auth = BusinessAuthorization(BusinessPolicy('telchi', workspace, base_permission, True, True))
        assert await auth.allowed(context, required_permission=permission)
        trusted = auth.enterprise_context(context)
        assert trusted is not None
        # Load only the required credential, never log the secret or unrelated env.
        if not os.getenv(CREDENTIAL_ENV):
            key = dotenv_values(root / 'SrvRestAstroLS_v1/.env.backend-dev.local').get(CREDENTIAL_ENV)
            if key:
                os.environ[CREDENTIAL_ENV] = key
        interpreter = LunaInterpreter()
        before = dict(deepcopy(engine.EMPTY), metric='sales.net_amount',
                      period={'start': '2026-05-01', 'end_exclusive': '2026-06-01'})
        evidence = dict(question=QUESTION, enterprise_context=trusted,
                        identity_source=str(source.relative_to(root)),
                        identity_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                        authorization='Recorded PG-effective evidence; no fresh DB/auth resolution',
                        foundation_calls=0, whatsapp_sent=0, real_interpreter_calls=1)
        start = perf_counter()
        try:
            raw = await interpreter.interpret(text=QUESTION, state=before, history={},
                turn_id=context.correlation_id, enterprise_context=trusted)
            processed = engine.process(before, raw, {}, context.correlation_id)
            state = processed['state_after']
            catalog = SalesCapabilities()
            available = catalog.availability(state)
            checks = dict(committed=processed['committed'] is True,
                intent=raw.get('intent') == 'NEW_QUERY', action=raw.get('action') == 'EXECUTE',
                metric=state.get('metric') == 'sales.latest_documents', limit=state.get('limit') == 5,
                no_extra_metrics=state.get('requested_metrics') in (None, ['sales.latest_documents']),
                no_filters_or_period=not any(state.get(k) for k in ('entity_mention', 'period', 'branches',
                    'sales_channel', 'comparison', 'temporal_reference', 'product_search_text', 'selected_item_codes')),
                capability_available=available.allowed,
                permission=catalog.required_permission(state) == permission)
            evidence.update(raw_proposal=raw, state_engine=processed,
                availability=vars(available), required_permission=catalog.required_permission(state),
                metadata=interpreter.last_metadata, checks=checks,
                status='INTERPRETER_PASS' if all(checks.values()) else 'FUNCTIONAL_FAILURE')
        except Exception as exc:
            evidence.update(status='BLOCKED', exception_class=type(exc).__name__)
        evidence['elapsed_seconds'] = round(perf_counter() - start, 3)
        output.write(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
        print(json.dumps(evidence, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
