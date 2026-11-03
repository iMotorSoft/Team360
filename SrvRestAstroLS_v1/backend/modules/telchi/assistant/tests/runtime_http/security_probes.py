"""HTTP security probes for the DEV-only Telchi assistant endpoint.

Proves the DEV adapter is fail-closed: token required, payload validated, routes
bounded to health + the dev turn, identity never accepted from the body, sessions
isolated and concurrent turns not cross-contaminated. Negative identity/tenant
cases that require a second authorized identity stay in the fixture test suites.

Usage:
    uv run python -m modules.telchi.assistant.tests.runtime_http.security_probes --output <dir>
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import secrets
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_battery as rb  # noqa: E402

ENDPOINT = '/api/telchi/assistant/dev/turn'


def _status(base_url: str, *, token=None, body=None, path=ENDPOINT, method='POST') -> str:
    command = ['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', '-X', method, base_url + path]
    if token is not None:
        command += ['-H', f'x-team360-dev-token: {token}']
    if body is not None:
        command += ['-H', 'content-type: application/json', '--data-binary', body]
    return subprocess.run(command, capture_output=True, text=True).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_env = rb._load_env_file()
    phone = rb._pilot_phone('team360-meta-dev')
    metadata = rb._binding_metadata('telchi_dev', 'telchi_whatsapp_dev', 'team360-meta-dev')
    receiver = metadata.get('receiver_context', '')
    token = secrets.token_urlsafe(48)
    port = rb._free_port()
    log_path = output_dir / 'security-server.log'
    process, base_url = rb.start_server(base_env, phone, receiver, port, token, log_path)
    results = dict(endpoint=ENDPOINT, transport='curl', checks={})
    try:
        results['checks']['missing_token'] = _status(base_url, body='{"text":"hola"}')
        results['checks']['wrong_token'] = _status(base_url, token='x' * 48, body='{"text":"hola"}')
        results['checks']['invalid_json'] = _status(base_url, token=token, body='{not json')
        results['checks']['missing_text'] = _status(base_url, token=token, body='{"conversation":"s"}')
        results['checks']['forbidden_field_user_id'] = _status(
            base_url, token=token, body='{"text":"hola","user_id":"other"}')
        results['checks']['forbidden_field_phone'] = _status(
            base_url, token=token, body='{"text":"hola","phone":"0000000000"}')
        results['checks']['unknown_route'] = _status(base_url, token=token, path='/api/console/me', method='GET')
        results['checks']['webhook_blocked'] = _status(
            base_url, token=token, path='/webhooks/messaging/evolution/whatsapp', method='POST', body='{}')
        results['checks']['health'] = _status(base_url, path='/health', method='GET')

        # Session isolation: two independent conversations must not share a thread.
        a = rb._curl_turn(base_url, token, 'sec-a', 'dame las ultimas ventas de calenta')
        b = rb._curl_turn(base_url, token, 'sec-b', 'cuanto facturo Calenta?')
        results['session_isolation'] = dict(
            a_conversation=a['response'].get('conversation_id'),
            b_conversation=b['response'].get('conversation_id'),
            distinct=a['response'].get('conversation_id') != b['response'].get('conversation_id'),
            a_entity=(a['response'].get('audit') or {}).get('confirmed_state', {}).get('entity_mention'),
            b_entity=(b['response'].get('audit') or {}).get('confirmed_state', {}).get('entity_mention'))

        # Concurrency: parallel turns on distinct conversations stay independent.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(rb._curl_turn, base_url, token, f'sec-par-{n}',
                                   'cuales son los productos mas vendidos?') for n in range(2)]
            parallel = [f.result() for f in futures]
        results['concurrency'] = dict(
            statuses=[p['response'].get('ok') for p in parallel],
            conversations=[p['response'].get('conversation_id') for p in parallel],
            distinct=parallel[0]['response'].get('conversation_id') != parallel[1]['response'].get('conversation_id'))

        log_text = log_path.read_text(errors='ignore')
        results['checks']['token_absent_from_log'] = token not in log_text
        results['checks']['phone_absent_from_log'] = phone not in log_text
    finally:
        rb.stop_server(process)

    expected = {'missing_token': '401', 'wrong_token': '401', 'invalid_json': '400',
                'missing_text': '400', 'forbidden_field_user_id': '400',
                'forbidden_field_phone': '400', 'unknown_route': '404',
                'webhook_blocked': '404', 'health': '200'}
    results['passed'] = (all(results['checks'].get(k) == v for k, v in expected.items())
                         and results['session_isolation']['distinct']
                         and all(results['concurrency']['statuses'])
                         and results['concurrency']['distinct']
                         and results['checks']['token_absent_from_log']
                         and results['checks']['phone_absent_from_log'])
    (output_dir / 'security_results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps({'passed': results['passed'], 'checks': results['checks'],
                      'session_distinct': results['session_isolation']['distinct'],
                      'concurrency_distinct': results['concurrency']['distinct']}, indent=2))


if __name__ == '__main__':
    main()