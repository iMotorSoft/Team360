"""Source+uv listeners and rollback smoke in memory/mock, no external services.

Both listeners use memory: no DB pool exists, hence Flow cannot read real
settings or execute delivery. Evolution ON is covered separately by fixtures.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import urlopen, Request

BACKEND = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, AUTOMATION_DIAGNOSIS_REPOSITORY='memory', TEAM360_AI_PROVIDER='mock',
               TEAM360_SRV05_EVOLUTION_ENABLED='0', TEAM360_DIAGNOSIS_STATE_PROVIDER='memory',
               TEAM360_DB_URL='', TEAM360_DB_URL_PSQL='', DB_PG_V360_URL='')
    processes, results = [], {}
    try:
        with ExitStack() as stack:
            for target in ('ls_iMotorSoft_Srv01:app', 'ls_iMotorSoft_Srv05:app'):
                listener = stack.enter_context(socket.socket())
                listener.bind(('127.0.0.1', 0)); listener.listen()
                port = listener.getsockname()[1]
                log = (args.output / (target.split(':')[0] + '.log')).open('w+b')
                command = ['uv', 'run', '--locked', 'uvicorn', target, '--host', '127.0.0.1',
                           '--port', str(port), '--fd', str(listener.fileno()), '--no-access-log']
                process = subprocess.Popen(command, cwd=BACKEND, env=env, pass_fds=(listener.fileno(),),
                                           stdout=log, stderr=log, start_new_session=True)
                processes.append((process, log, target))
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None: raise RuntimeError('Source startup failed')
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                            health = json.load(response)
                        break
                    except OSError:
                        if time.monotonic() > deadline: raise RuntimeError('Readiness timeout')
                        time.sleep(.1)
                with urlopen(f'http://127.0.0.1:{port}/schema/openapi.json', timeout=3) as response:
                    schema = json.load(response)
                try:
                    urlopen(Request(f'http://127.0.0.1:{port}/webhooks/messaging/evolution/whatsapp',
                                    data=b'{}', headers={'Content-Type': 'application/json'}), timeout=3)
                except HTTPError as error:
                    assert error.code == 404
                else:
                    raise AssertionError('Evolution leaked into disabled composition')
                results[target] = {'health': health, 'operations': sum(len(v) for v in schema['paths'].values()),
                                   'evolution': 404, 'pid': process.pid, 'command': command}
                (args.output / (target.split(':')[0] + '-openapi.json')).write_text(json.dumps(schema, indent=2)+'\n')
            assert all(p.poll() is None for p, _, _ in processes)
            results['simultaneous'] = 'PASS memory/mock, neither has a DB pool/delivery destination'
            results['rollback'] = 'PASS Srv01 source listener and legacy schema remain usable'
    finally:
        # Only our own process groups; never touch an existing listener/service.
        for process, log, target in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
            log.seek(0)
            text = log.read().decode(errors='replace')
            log.close()
            results.setdefault(target, {})['returncode'] = process.returncode
            results[target]['cleanup'] = process.poll() is not None
            results[target]['shutdown_complete'] = 'Application shutdown complete' in text
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                results[target]['process_group_empty'] = True
            else:
                results[target]['process_group_empty'] = False
        (args.output / 'report.json').write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(results, indent=2))
    assert all(results[target]['shutdown_complete'] and results[target]['process_group_empty']
               for _, _, target in processes), 'Source runtime cleanup incomplete'


if __name__ == '__main__': main()
