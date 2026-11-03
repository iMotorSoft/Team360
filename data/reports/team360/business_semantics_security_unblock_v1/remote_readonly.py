"""Stream over SSH to existing production venv Python; no remote files created.
Inspect only an existing Team360 process environment, never print credentials.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone

report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'writes': 0, 'processes': [], 'errors': []}
backend = Path('/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend')
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        cmd = (proc / 'cmdline').read_bytes()
        entrypoints = [v for v in ('ls_iMotorSoft_Srv01', 'ls_iMotorSoft_Srv05') if v.encode() in cmd]
        if not entrypoints or (proc / 'cwd').resolve() != backend:
            continue
        item = {'pid': int(proc.name), 'entrypoints': entrypoints, 'cwd': str(backend)}
        report['processes'].append(item)
        env = dict(v.decode().split('=', 1) for v in (proc / 'environ').read_bytes().split(b'\0') if b'=' in v)
        item['environment_label'] = env.get('TEAM360_ENV')
        item['configuration_presence'] = {k: bool(env.get(k)) for k in ('TEAM360_DB_URL','TEAM360_DB_URL_PSQL','DB_PG_V360_URL')}
        # Use the running process's inherited env with the deployed pure resolver.
        os.environ.clear()
        os.environ.update(env)
        import sys
        sys.path.insert(0, str(backend))
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row
        from modules.db.settings import get_database_settings
        dsn = get_database_settings().dsn
        p = conninfo_to_dict(dsn)
        item['resolved_target'] = {k: p.get(k) for k in ('host','port','dbname','user')}
        with psycopg.connect(dsn,connect_timeout=5,row_factory=dict_row,
                options='-c default_transaction_read_only=on -c statement_timeout=5000',
                application_name='bs-production-boundary-readonly') as conn:
            item['server'] = conn.execute("SELECT current_database() AS database,current_user AS role,inet_server_addr()::text AS address,inet_server_port() AS port,current_setting('server_version') AS version,current_setting('transaction_read_only') AS read_only,(pg_control_system()).system_identifier::text AS system_identifier").fetchone()
            conn.rollback()
    except (FileNotFoundError, PermissionError):
        continue
    except Exception as exc:
        report['errors'].append(type(exc).__name__)
if not report['processes']:
    report['errors'].append('NO_READABLE_TEAM360_PROCESS_IN_CANONICAL_CWD')
print(json.dumps(report, indent=2, default=str))
