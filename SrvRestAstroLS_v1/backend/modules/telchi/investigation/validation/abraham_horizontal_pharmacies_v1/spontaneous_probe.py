"""One original question through the existing DEV HTTP harness; no assistant changes."""
import asyncio
import json
import os
from pathlib import Path
import secrets
from datetime import datetime, timezone

from modules.telchi.assistant.tests.runtime_http import run_battery as harness
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY

QUESTION = '¿Cuántos clientes tenemos en horizontal, principalmente las farmacias, y cuánto se les vende por mes?'


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'question': QUESTION, 'timestamp': datetime.now(timezone.utc).isoformat(),
              'assistant_modified': False, 'whatsapp_sent': False,
              'scope': 'existing DEV HTTP adapter, approved pilot binding; new conversation',
              'preflight': {}, 'own_processes_left_running': 0}
    process = None
    try:
        base = harness._load_env_file()
        # Same configuration file and environment as the existing HTTP harness.
        for key, value in base.items():
            os.environ[key] = value
        import globalVar
        import psycopg
        with psycopg.connect(globalVar.get_team360_db_url_psql(), connect_timeout=5) as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            report['preflight']['postgres'] = conn.execute('SELECT 1').fetchone()[0] == 1
        # Isolated minimal provider probe; never enters the tested conversation.
        luna = LunaInterpreter()
        asyncio.run(luna.interpret(text='¿Cuánto vendimos?', state=EMPTY,
                                  history=[], turn_id='isolated-provider-preflight'))
        report['preflight']['model'] = luna.last_metadata
        report['preflight']['fallback'] = False
        report['preflight']['milvus_litellm'] = 'not used by this direct OpenAI assistant'
        instance = base.get('TEAM360_EVOLUTION_INSTANCE', 'team360-meta-dev')
        phone = harness._pilot_phone(instance)
        metadata = harness._binding_metadata('telchi_dev', 'telchi_whatsapp_dev', instance)
        token = secrets.token_urlsafe(48)
        process, url = harness.start_server(base, phone, metadata.get('receiver_context', ''),
                                            harness._free_port(), token, output / 'dev-server.log')
        report['server_pid'] = process.pid
        report['turn'] = harness._curl_turn(url, token, 'abraham-' + secrets.token_hex(8), QUESTION)
    except BaseException as exc:
        report['blocked'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if process is not None:
            harness.stop_server(process)
            report['server_reaped'] = process.poll() is not None
            report['own_processes_left_running'] = int(process.poll() is None)
        (output / 'spontaneous.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
