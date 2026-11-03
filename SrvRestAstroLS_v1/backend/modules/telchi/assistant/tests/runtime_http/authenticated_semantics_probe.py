"""Real HTTP probe using existing private Console sessions; no login or server startup.

Requires an operator-started existing DEV adapter, its private gate token and a
fresh login_cli session whose subject owns the approved pilot phone binding.
Never sends WhatsApp, issues tokens, activates accounts or queries Foundation.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid

import httpx

from modules.console.login_cli import private_path


def check_response(status, body, expectation):
    if expectation == 'deny':
        if status in {401, 403}:
            return dict(status='PASS', scope='HTTP_auth_denied_before_handler')
        if status == 200 and body.get('classification') == 'DENIED' and not body.get('audit'):
            return dict(status='PASS', scope='HTTP_business_permission_denied')
        raise AssertionError('expected_auth_or_RBAC_denial')
    if status != 200:
        raise AssertionError('authorized_HTTP_request_not_accepted')
    audit = body.get('audit') or {}
    identity = audit.get('business_semantics', {}).get('connection', {})
    if identity != dict(role='team360_business_semantics_dev_runtime', rolsuper=False, rolbypassrls=False):
        raise AssertionError('effective_retrieval_connection_not_proven')
    if (body.get('classification') != 'NEEDS_CLARIFICATION' or audit.get('decision') != 'ASK'
            or audit.get('capability_calls') != 0 or audit.get('execution_status') != 'not_executed'
            or not audit.get('business_semantics', {}).get('semantic_guard', {}).get('requires_clarification')):
        raise AssertionError('semantic_guard_not_enforced_without_business_execution')
    if not body.get('correlation_id') or not body.get('conversation_id'):
        raise AssertionError('missing_correlation')
    return dict(status='PASS', scope='real_authenticated_HTTP_to_restricted_semantics_not_WhatsApp',
        effective_connection=identity, correlation_id=body['correlation_id'], conversation_id=body['conversation_id'],
        classification=body['classification'], capability_calls=0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', default='http://127.0.0.1:7090')
    p.add_argument('--session-file', required=True, type=Path)
    p.add_argument('--dev-token-file', required=True, type=Path)
    p.add_argument('--expect', choices=['scope', 'deny'], required=True)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    try:
        url = urlsplit(args.base_url)
        if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'} or url.username
                or url.password or url.query or url.fragment or url.path not in {'', '/'}):
            raise PermissionError('loopback_base_required')
        if args.output.exists():
            raise FileExistsError('new_report_path_required')
        token = private_path(args.session_file, existing=True).read_text().strip()
        dev_token = private_path(args.dev_token_file, existing=True).read_text().strip()
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=30) as client:
            response = client.post(args.base_url.rstrip('/')+'/api/telchi/assistant/dev/turn',
                headers={'Authorization': 'Bearer '+token, 'x-team360-dev-token': dev_token},
                json={'text': 'Deudas con proveedores', 'conversation': 'scope-probe-'+uuid.uuid4().hex})
        report = check_response(response.status_code, response.json(), args.expect)
    except Exception as exc:
        report = dict(status='NOT_PROVEN', error_class=type(exc).__name__)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
    print('AUTHENTICATED_HTTP='+report['status'])
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
