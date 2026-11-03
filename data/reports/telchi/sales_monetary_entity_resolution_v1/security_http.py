"""Same DEV endpoint/handler with explicit denial and invalid-proposal fixtures.

No RBAC rows are withdrawn from the pilot. Missing permission is a harness
fixture; real negative PostgreSQL identities are verified separately.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent
BACKEND = OUT.parents[3] / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))


def serve():
    import uvicorn
    from modules.telchi.assistant.dev_runtime_http import create_dev_app
    from modules.telchi.assistant.handler import BusinessAuthorization
    from modules.telchi.datalake.sales_query import MONETARY_PERMISSION
    app = create_dev_app()
    handler = app.app.state.messaging_handlers['telchi'].handler
    class DeniedMonetary(BusinessAuthorization):
        async def allowed(self, context, conn=None, *, required_permission=None):
            if required_permission == MONETARY_PERMISSION:
                return False
            return await super().allowed(context, conn, required_permission=required_permission)
    class InterpreterFixture:
        async def interpret(self, *, text, **kwargs):
            fields = {'/metric': 'sales.coverage'}
            if text == 'MONETARY_DENIAL_FIXTURE':
                fields = {'/metric': 'sales.net_amount', '/period':
                    {'start': '2026-05-01', 'end_exclusive': '2026-06-01'}}
            if text == 'REJECT_FIXTURE':
                fields = {'/unknown': 'EXECUTE'}
            return dict(intent='NEW_QUERY', action='EXECUTE',
                        state_delta=dict(set=fields, unset=[]), clarification=None)
    handler.authorization = DeniedMonetary(handler.authorization.policy)
    handler.interpreter = InterpreterFixture()
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ['TEAM360_TELCHI_ASSISTANT_DEV_HTTP_PORT']),
                workers=1, access_log=False, log_level='warning')


def main():
    from modules.telchi.assistant.tests.runtime_http import run_battery as battery
    base = battery._load_env_file()
    os.environ.update(base)
    phone = battery._pilot_phone('team360-meta-dev')
    binding = battery._binding_metadata('telchi_dev', 'telchi_whatsapp_dev', 'team360-meta-dev')
    token, port = secrets.token_urlsafe(48), battery._free_port()
    env = battery._server_env(token, phone, port, base, binding['receiver_context'])
    base_url = f'http://127.0.0.1:{port}'
    conversation = 'security-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    evidence = dict(fixture=True, endpoint='/api/telchi/assistant/dev/turn', cases={})
    with (OUT/'security-server.log').open('w') as log:
        process = subprocess.Popen([str(BACKEND/'.venv/bin/python'), str(Path(__file__).resolve()), '--serve'],
                                   cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            battery._wait_health(base_url, process)
            denial = battery._curl_turn(base_url, token, conversation+'-denied', 'MONETARY_DENIAL_FIXTURE')
            assert denial['response']['classification'] == 'DENIED'
            assert denial['response']['audit']['capability_calls'] == 0
            seed = battery._curl_turn(base_url, token, conversation+'-reject', 'SEED_COVERAGE')
            assert seed['response']['classification'] == 'DIRECT_AVAILABLE'
            rejected = battery._curl_turn(base_url, token, conversation+'-reject', 'REJECT_FIXTURE')
            audit = rejected['response']['audit']
            assert audit['committed'] is False and audit['capability_calls'] == 0
            assert audit['confirmed_state'] == seed['response']['audit']['confirmed_state']
            evidence['cases'] = dict(M08=denial, M09=rejected)
        finally:
            battery.stop_server(process)
            evidence['own_server_reaped'] = process.poll() is not None
    (OUT/'security_http_results.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print('M08 denial fixture / M09 real engine rejection through HTTP: verified')


if __name__ == '__main__':
    serve() if '--serve' in sys.argv else main()
