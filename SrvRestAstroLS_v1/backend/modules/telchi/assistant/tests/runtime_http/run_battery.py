"""Reproducible HTTP battery for the real Telchi assistant on Srv05 DEV.

Drives the DEV-only assistant endpoint (``modules.telchi.assistant.dev_runtime_http``)
with ``curl`` so every turn is an actual HTTP request against the real pipeline
(MessageDispatcher -> TelchiHandler -> State Engine -> capabilities -> Foundation)
persisted in PostgreSQL. By default it starts and reaps its own server.

Usage:
    uv run python -m modules.telchi.assistant.tests.runtime_http.run_battery \
        --output ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/runtime_http

    # or against an already running DEV server:
    ... --base-url http://127.0.0.1:7090 --token "$TEAM360_TELCHI_ASSISTANT_DEV_HTTP_TOKEN"

No credential, token or phone is embedded in this file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[5]
ENV_FILE = BACKEND.parent / '.env.backend-dev.local'

SCENARIOS = [
    dict(id='incident_20261011', conversation='incident-20261011', turns=[
        'dame las ultimas ventas de calenta',
        'las dos',
        'primero dame el importe de las ventas del mes',
        'ultimo mes registrado',
        'mayo 2026',
        'todo mayo de 2026',
    ]),
    dict(id='C01_multimetric', conversation='c01', turns=[
        'dame las ultimas ventas de calenta', 'las dos cosas']),
    dict(id='C02_priority', conversation='c02', turns=[
        'dame las ultimas ventas de calenta', 'las dos', 'primero la plata']),
    dict(id='C03_dynamic_period', conversation='c03', turns=[
        'dame las ultimas ventas de calenta', 'las dos', 'primero dame el importe',
        'el ultimo mes que tengas']),
    dict(id='C04_full_period', conversation='c04', turns=[
        'dame las ultimas ventas de calenta', 'las dos', 'primero dame el importe',
        'mayo entero']),
    dict(id='C05_monetary_missing', conversation='c05', turns=[
        'cuanto facturo Calenta?']),
    dict(id='C06_documentary', conversation='c06', turns=[
        'cuales son los productos mas vendidos?']),
    dict(id='C07_temporal_continuity', conversation='c07', turns=[
        'dame las ultimas ventas de calenta', 'las dos', 'mayo 2026', 'y el mes anterior?']),
    dict(id='C08_change_priority', conversation='c08', turns=[
        'dame las ultimas ventas de calenta', 'las dos', 'primero dame el importe',
        'ahora quiero cantidades']),
    dict(id='C09_diagnosis', conversation='c09', turns=[
        'por que bajaron las ventas?']),
    dict(id='C10_entity_period', conversation='c10', turns=[
        'mostrame ventas de Calenta en mayo']),
    dict(id='foundation_positive', conversation='foundation-positive', turns=[
        'Nueva consulta: top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros']),
]

# Opt-in selection only: preserve the previous default 12 scenarios / 32 turns.
ACTIVATION_SCENARIOS = [
    dict(id='TQ01', conversation='tq01', turns=['Dame las últimas 10 ventas registradas']),
    dict(id='TQ02', conversation='tq02', turns=['Ventas de mayo de 2026']),
    dict(id='TQ03', conversation='tq03', turns=['¿Cuál es el último mes con ventas registradas?']),
    dict(id='TQ04', conversation='tq04', turns=['Dame las últimas ventas de Calenta']),
    dict(id='TQ05', conversation='tq05', turns=['Quiero importes y cantidades']),
    dict(id='TQ06', conversation='tq06', turns=['Ventas de mayo de 2026', '¿Y el mes anterior?']),
    dict(id='TQ07', conversation='tq07', turns=['¿Cuáles fueron los productos más vendidos?']),
    dict(id='TQ08', conversation='tq08', turns=['Dame el importe neto por producto de mayo de 2026']),
    dict(id='TQ09', conversation='tq09', turns=['Mostrá la cobertura de facturas activas por fecha documental']),
    dict(id='TQ11', conversation='tq11', turns=['Sumá en una sola cantidad física las ventas de todos los productos de mayo de 2026']),
    dict(id='TQ12', conversation='tq12', turns=['Dame las últimas ventas de Calenta Forte y Calenta como una sola marca']),
]

# Sales RBAC/business activation: opt-in; default regression remains unchanged.
ACTIVATION_SCENARIOS += [
    dict(id='B01', conversation='b01', turns=['Dame las últimas 10 facturas de venta registradas']),
    dict(id='B02', conversation='b02', turns=['¿Cuál es la última fecha de ventas registrada?']),
    dict(id='B03', conversation='b03', turns=['¿Cuál es el último mes con ventas registradas?']),
    dict(id='B04', conversation='b04', turns=['Dame las últimas 10 facturas', '¿Y las anteriores?']),
    dict(id='B05', conversation='b05', turns=['¿Cuánto facturamos neto en mayo de 2026?']),
    dict(id='B06', conversation='b06', turns=['¿Cuáles son los productos más vendidos?',
        'Nueva consulta: top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros']),
]

# Monetary increment is opt-in; previous default scenarios stay unchanged.
ACTIVATION_SCENARIOS += [
    dict(id='M01', conversation='m01', turns=['Ventas de mayo de 2026']),
    dict(id='M02', conversation='m02', turns=['Ventas de junio de 2026']),
    dict(id='M03', conversation='m03', turns=['¿Cuál es el último mes con ventas?']),
    dict(id='M04', conversation='m04', turns=['Dame las últimas ventas de Calenta']),
    dict(id='M05', conversation='m05', turns=['Ventas de mayo de 2026', 'Quiero importe y cantidades']),
    dict(id='M06', conversation='m06', turns=['Ventas de junio de 2026', '¿Y el mes anterior?']),
    dict(id='M07', conversation='m07', turns=['¿Cuáles son los productos más vendidos?',
        'Top 10 por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros']),
    dict(id='M10', conversation='m10', turns=['Dame el importe neto por producto de mayo de 2026']),
    dict(id='M11', conversation='m11', turns=['Dame las últimas ventas de Calenta y Calenta Forte como una sola marca']),
]

# Product increment is opt-in; the previous default battery is preserved.
ACTIVATION_SCENARIOS += [
    dict(id='P01', conversation='p01', turns=['Buscá Calenta']),
    dict(id='P02', conversation='p02', turns=['Dame las últimas ventas de Calenta', 'Mostrame todas las presentaciones']),
    dict(id='P04', conversation='p04', turns=['Dame las últimas ventas de Calenta', '¿Y solamente una presentación?', 'Solamente Calenta Forte de 250 g']),
    dict(id='P05', conversation='p05', turns=['¿Cuánto vendimos de Calenta en mayo de 2026?']),
    dict(id='P06', conversation='p06', turns=['Últimas ventas de Calenta', 'Dame importes y cantidades', '¿Y las ventas de mayo de 2026?']),
    dict(id='P07', conversation='p07', turns=['Buscá el producto por código L02822']),
    dict(id='P08', conversation='p08', turns=['Buscá el producto inexistente XYZ_NO_EXISTE_903718']),
    dict(id='P09', conversation='p09', turns=['Buscá productos con nombre pomada']),
    dict(id='P10', conversation='p10', turns=['Últimas ventas del producto L02822']),
    dict(id='P11', conversation='p11', turns=['Ventas de mayo 2026', 'Ventas de junio 2026', '¿Y el mes anterior?']),
    dict(id='P12', conversation='p12', turns=['¿Cuál es el último mes registrado con ventas?']),
    dict(id='P16', conversation='p16', turns=['Últimas ventas de Calenta', 'Sumá todas las cantidades físicas de las presentaciones de Calenta y Calenta por kg']),
    dict(id='P17', conversation='p17', turns=['Últimas ventas del producto L03650']),
]

# Conversational business scenario (Presidencia). Opt-in; the default battery is unchanged.
ACTIVATION_SCENARIOS += [
    dict(id='BIZ01', conversation='biz01', turns=[
        '¿Cuánto facturamos en septiembre?',
        '¿Y cuánto corresponde a productos terminados de laboratorio?',
        '¿Cuáles fueron los cinco productos con mayor importe vendido?',
        '¿En qué puesto estuvo L03281 en julio y agosto?',
        '¿A qué cliente le vendimos más ese producto entre ambos meses?',
        '¿Cuánto compró ese cliente en julio y cuánto en agosto?',
        '¿Qué otros productos nos compró durante esos meses?',
        '¿Qué porcentaje representa ese cliente sobre las ventas de L03281?',
        '¿Qué otros clientes importantes compraron ese producto?',
        '¿Qué cambió entre julio y agosto?',
    ]),
]

FORBIDDEN_FIELDS = {'user_id', 'tenant', 'tenant_id', 'workspace', 'workspace_id',
                    'permissions', 'permission', 'phone', 'sender'}


def _load_env_file() -> dict:
    values = {}
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            values[key.strip()] = value.strip()
    return values


def _pilot_phone(instance: str) -> str:
    import globalVar
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(globalVar.get_team360_db_url_psql(), row_factory=dict_row) as conn:
        row = conn.execute("""
            SELECT sender_identity FROM messaging_phone_bindings
            WHERE environment='dev' AND provider='evolution' AND tenant_id='telchi'
              AND verification_status='verified' AND revoked_at_utc IS NULL
            ORDER BY verified_at_utc LIMIT 1
            """).fetchone()
        if not row:
            raise SystemExit('No verified Telchi pilot phone binding found')
        return str(row['sender_identity'])


def _binding_metadata(workspace_slug: str, channel_alias: str, instance: str) -> dict:
    import globalVar
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(globalVar.get_team360_db_url_psql(), row_factory=dict_row) as conn:
        row = conn.execute("""
            SELECT c.metadata_jsonb FROM communication_channels c
            JOIN core_workspaces w ON w.id=c.workspace_id
            WHERE w.slug=%s AND c.channel_alias=%s
              AND c.metadata_jsonb->>'provider_instance'=%s
            """, (workspace_slug, channel_alias, instance)).fetchone()
        if not row:
            raise SystemExit('Telchi DEV channel binding missing')
        return dict(row['metadata_jsonb'])


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _server_env(token: str, phone: str, port: int, base: dict, receiver: str) -> dict:
    env = os.environ.copy()
    env.update(base)
    env.update({
        'TEAM360_ENV': 'dev',
        'TEAM360_SRV05_EVOLUTION_ENABLED': '1',
        'TEAM360_MESSAGING_DEV_ENABLED': '1',
        'TEAM360_MESSAGING_DISPATCH_MODE': 'horizontal_v1',
        'TEAM360_MESSAGING_DEV_SQL_TENANT': '',
        'TEAM360_MESSAGING_WORKSPACE_SLUG': 'telchi_dev',
        'TEAM360_MESSAGING_CHANNEL_ALIAS': 'telchi_whatsapp_dev',
        'AUTOMATION_DIAGNOSIS_REPOSITORY': 'postgres',
        'TEAM360_TELCHI_ASSISTANT_DEV_HTTP': '1',
        'TEAM360_TELCHI_ASSISTANT_DEV_HTTP_TOKEN': token,
        'TEAM360_TELCHI_ASSISTANT_DEV_PHONE': phone,
        'TEAM360_TELCHI_ASSISTANT_DEV_HTTP_PORT': str(port),
        'TEAM360_TELCHI_ASSISTANT_DEV_HTTP_HOST': '127.0.0.1',
        'META_TEAM360_PHONE_NUMBER_ID': receiver,
        'OMP_NUM_THREADS': '2',
        'OPENBLAS_NUM_THREADS': '2',
    })
    return env


def start_server(base_env: dict, phone: str, receiver: str, port: int, token: str,
                 log_path: Path) -> tuple:
    """Start the DEV assistant server on loopback and wait for health."""
    env = _server_env(token, phone, port, base_env, receiver)
    log = log_path.open('w')
    process = subprocess.Popen([str(BACKEND / '.venv/bin/python'), '-m',
                                'modules.telchi.assistant.dev_runtime_http'],
                               cwd=str(BACKEND), env=env, stdout=log, stderr=subprocess.STDOUT)
    base_url = f'http://127.0.0.1:{port}'
    try:
        _wait_health(base_url, process)
    except BaseException:
        stop_server(process)
        raise
    finally:
        log.close()
    return process, base_url


def stop_server(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _wait_health(base_url: str, proc: subprocess.Popen, deadline: float = 90) -> None:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise SystemExit('DEV server exited before health')
        result = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}',
                                 f'{base_url}/health'], capture_output=True, text=True)
        if result.stdout.strip() == '200':
            return
        time.sleep(0.3)
    raise SystemExit('DEV server health deadline exceeded')


def _curl_turn(base_url: str, token: str, conversation: str, text: str, timeout: int = 180) -> dict:
    payload = json.dumps({'text': text, 'conversation': conversation}, ensure_ascii=False)
    command = [
        'curl', '-sS', '-X', 'POST', f'{base_url}/api/telchi/assistant/dev/turn',
        '-H', 'content-type: application/json',
        '-H', f'x-team360-dev-token: {token}',
        '-H', 'accept: application/json',
        '--max-time', str(timeout),
        '--write-out', '\\n%{http_code}',
        '--data-binary', payload,
    ]
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True)
    elapsed_ms = (time.monotonic() - started) * 1000
    body, _, status = result.stdout.rpartition('\n')
    if not body:
        body, status = status, ''
    try:
        parsed = json.loads(body.strip()) if body.strip() else {}
    except json.JSONDecodeError:
        parsed = {'raw': body[:2000]}
    recorded = [('x-team360-dev-token: <redacted>' if c.startswith('x-team360-dev-token:')
                 else ('<redacted>' if c == token else c)) for c in command if c != payload]
    recorded += ['{"text": <censored>, "conversation": "%s"}' % conversation]
    return dict(curl=recorded, http_status=status.strip() or result.returncode,
                elapsed_ms=round(elapsed_ms, 2), response=parsed)


def _summary(turn: dict) -> dict:
    response = turn['response']
    audit = response.get('audit') or {}
    state = audit.get('confirmed_state') or {}
    effective = state.get('pending', {}).get('proposed') if state.get('pending') else state
    return dict(http_ok=bool(response.get('ok')),
                classification=response.get('classification'),
                committed=audit.get('committed'),
                decision=audit.get('decision'),
                execution_status=audit.get('execution_status'),
                bmd_category=(audit.get('bmd') or {}).get('category'),
                metrics=(effective or {}).get('requested_metrics'),
                metric=(effective or {}).get('metric'),
                entity=((effective or {}).get('entity_mention') or {}).get('text'),
                temporal_reference=(effective or {}).get('temporal_reference'),
                period=(effective or {}).get('period'),
                response_text=response.get('text'))


def run_battery(base_url: str, token: str, only: list[str] | None = None,
                timeout: int = 180) -> dict:
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    selected = [s for s in (SCENARIOS + ACTIVATION_SCENARIOS if only else SCENARIOS)
                if not only or s['id'] in only]
    if only and set(only) - {s['id'] for s in selected}:
        raise ValueError('unknown_runtime_scenario')
    evidence = dict(run_id=run_id, base_url=base_url, endpoint='/api/telchi/assistant/dev/turn',
                    transport='curl', pipeline='MessageDispatcher -> TelchiHandler -> StateEngine -> capabilities',
                    whatsapp_e2e=False, scenarios=[])
    for scenario in selected:
        # Unique per run so each gate execution starts from a clean durable thread
        # while still reusing one conversation key across the scenario's turns.
        conversation = f"{scenario['conversation']}:{run_id}"
        record = dict(id=scenario['id'], conversation=conversation, turns=[])
        for turn in scenario['turns']:
            result = _curl_turn(base_url, token, conversation, turn, timeout=timeout)
            summary = _summary(result)
            summary.update(user_text=turn, elapsed_ms=result['elapsed_ms'],
                           http_status=result['http_status'], curl=result['curl'],
                           conversation_id=result['response'].get('conversation_id'),
                           correlation_id=result['response'].get('correlation_id'),
                           audit=result['response'].get('audit'))
            record['turns'].append(summary)
        evidence['scenarios'].append(record)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--base-url', default=None)
    parser.add_argument('--token', default=None)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--only', default='', help='comma-separated scenario ids to run')
    args = parser.parse_args()
    only = [s for s in args.only.split(',') if s] or None
    if not shutil.which('curl'):
        raise SystemExit('curl is required')

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.base_url:
        if not args.token:
            raise SystemExit('--token required with --base-url')
        evidence = run_battery(args.base_url, args.token, only=only, timeout=args.timeout)
    else:
        base_env = _load_env_file()
        instance = 'team360-meta-dev'
        phone = _pilot_phone(instance)
        metadata = _binding_metadata('telchi_dev', 'telchi_whatsapp_dev', instance)
        receiver = metadata.get('receiver_context', '')
        token = secrets.token_urlsafe(48)
        port = _free_port()
        base_url = f'http://127.0.0.1:{port}'
        log_path = output_dir / 'dev-server.log'
        process, base_url = start_server(base_env, phone, receiver, port, token, log_path)
        try:
            evidence = run_battery(base_url, token, only=only, timeout=args.timeout)
        finally:
            stop_server(process)
        evidence['server'] = dict(pid_reaped=True, log=str(log_path))

    (output_dir / 'runtime_http_results.json').write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
    if any(s['id'] == 'BIZ01' for s in evidence['scenarios']):
        from .biz01_evaluator import evaluate
        report = evaluate(output_dir / 'runtime_http_results.json')
        (output_dir / 'biz01_evaluation.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + '\n')
        evidence['biz01'] = {k: report[k] for k in
                             ('turns_total', 'turns_correct', 'conversation_pass', 'unjustified_unavailability',
                              'context_loss', 'monetary_reconciliation', 'authorization')}
        (output_dir / 'runtime_http_results.json').write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
    turns = sum(len(s['turns']) for s in evidence['scenarios'])
    fails = sum(1 for s in evidence['scenarios'] for t in s['turns'] if not t['http_ok'])
    print(json.dumps({'run_id': evidence['run_id'], 'scenarios': len(evidence['scenarios']),
                      'turns': turns, 'http_failures': fails, 'biz01': evidence.get('biz01')}))


if __name__ == '__main__':
    main()