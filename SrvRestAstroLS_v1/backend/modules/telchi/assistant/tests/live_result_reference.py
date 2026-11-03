"""Opt-in focused real Luna Medium probe. No business values sent to OpenAI.

Synthetic accredited rows and identity/RBAC; no Foundation, HTTP runtime or WhatsApp.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from modules.telchi.assistant.luna import LunaInterpreter, MODEL
from modules.telchi.assistant import result_references as refs
from modules.telchi.assistant.state_engine import EMPTY
from .test_result_references import document_result, PERMISSION


async def probe():
    luna = LunaInterpreter()
    state = dict(EMPTY, metric='sales.latest_documents', limit=3)
    owner = ['dev', 'telchi', 'fixture-workspace', 'fixture-channel', 'fixture-user']
    view = refs.presentation(dict(owner=owner, execution_status='executed', business_rbac_verified=True,
        required_permission=PERMISSION, confirmed_state=state, execution_result=document_result(),
        response_prepared={'classification': 'DIRECT_AVAILABLE'}), 'fixture-three', owner, 'fixture-conversation')
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(), model=MODEL, reasoning='medium',
        provider='OpenAI direct', fallback=False, rows='synthetic', auth='fixture', foundation_calls=0,
        whatsapp_sent=0, turns=[])
    args = dict(state=state, history={'fixture-five': dict(state, limit=5), 'fixture-three': state},
                enterprise_context=dict(source='authenticated_team360_workspace', tenant_id='telchi',
                    workspace_id='fixture-workspace', own_company={'name': 'Telchi', 'aliases': []}))
    try:
        preflight = await luna.interpret(text='Mostrame las últimas tres facturas de venta de Telchi.',
            turn_id='preflight', **args)
        report['preflight'] = dict(metadata=luna.last_metadata, proposal=preflight,
            status='PASS' if luna.last_metadata else 'BLOCKED')
        selected = None
        for text in ['¿Cuál es el número de factura de la segunda de esas tres?', '¿Cuál es su número?',
                     '¿Y la primera?', 'Mostrame solamente esa factura']:
            proposal = await luna.interpret(text=text, turn_id=f'probe-{len(report["turns"])}',
                result_context=refs.interpreter_context(view, selected), **args)
            selected, response = refs.resolve(proposal, view, selected, owner, 'fixture-conversation')
            report['turns'].append(dict(user_message=text, proposal=proposal,
                selected_ordinal=selected, response=response, metadata=luna.last_metadata))
        report['REAL_LUNA_ORDINAL'] = ('PASS' if report['turns'][0]['selected_ordinal'] == 2
            and report['turns'][0]['proposal']['result_reference']['field'] == 'doc_num'
            and '260192727' in report['turns'][0]['response'] else 'FAIL')
    except Exception as exc:
        report['REAL_LUNA_ORDINAL'] = 'FAIL' if luna.last_metadata else 'BLOCKED'
        report['error'] = type(exc).__name__
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = Path(args.output)
    if path.exists():
        raise SystemExit('Refusing to overwrite evidence')
    report = asyncio.run(probe())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'REAL_LUNA_ORDINAL': report['REAL_LUNA_ORDINAL'], 'turns': len(report['turns'])}))


if __name__ == '__main__':
    main()
