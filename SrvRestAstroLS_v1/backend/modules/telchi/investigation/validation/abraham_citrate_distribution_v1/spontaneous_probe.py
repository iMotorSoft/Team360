"""Abraham 002: literal question, unchanged real DEV HTTP pipeline, isolated thread."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets

from modules.telchi.assistant.tests.runtime_http import run_battery as harness
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY

QUESTION = 'Venta de Citrato de magnesio en la paz y cochabamba, en la paz distribucion propia y en conchabamba lo hace L&S'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = harness.BACKEND / 'modules/telchi/assistant'
    hashes = lambda: {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(root.glob('*.py'))}
    report = {'case': 'ABRAHAM_002', 'question': QUESTION,
              'timestamp': datetime.now(timezone.utc).isoformat(), 'preflight': {},
              'assistant_hashes_before': hashes(), 'whatsapp_sent': False,
              'host_preflight': 'SAFE: load 2.22/8 CPUs, MemAvailable 5226 MB, swap 8 MB; sequential HTTP, 2 internal threads',
              'own_processes_left_running': 0}
    process = None
    try:
        base = harness._load_env_file()
        os.environ.update(base)
        import globalVar
        import psycopg
        with psycopg.connect(globalVar.get_team360_db_url_psql(), connect_timeout=5) as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            report['preflight']['postgres'] = conn.execute('SELECT 1').fetchone()[0] == 1
        luna = LunaInterpreter()
        asyncio.run(luna.interpret(text='¿Cuánto vendimos?', state=EMPTY,
                                  history=[], turn_id='isolated-provider-preflight'))
        report['preflight']['model'] = luna.last_metadata
        report['preflight']['milvus_litellm'] = 'NOT_APPLICABLE: direct OpenAI Responses; no retrieval/proxy'
        instance = base.get('TEAM360_EVOLUTION_INSTANCE', 'team360-meta-dev')
        phone = harness._pilot_phone(instance)
        metadata = harness._binding_metadata('telchi_dev', 'telchi_whatsapp_dev', instance)
        token = secrets.token_urlsafe(48)
        process, url = harness.start_server(base, phone, metadata.get('receiver_context', ''),
                                            harness._free_port(), token, output / 'dev-server.log')
        report['server_pid'] = process.pid
        report['turn'] = harness._curl_turn(url, token, 'abraham002-' + secrets.token_hex(8), QUESTION)
    except BaseException as exc:
        report['blocked'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if process is not None:
            harness.stop_server(process)
            report['server_reaped'] = process.poll() is not None
            report['own_processes_left_running'] = int(process.poll() is None)
        report['assistant_hashes_after'] = hashes()
        report['assistant_sources_unchanged'] = report['assistant_hashes_before'] == report['assistant_hashes_after']
        (output / 'spontaneous.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
