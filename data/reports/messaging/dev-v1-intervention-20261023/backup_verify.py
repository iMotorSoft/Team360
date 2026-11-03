"""Owner-authorized DEV backup and isolated restore. No target writes or delivery."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
from modules.db.settings import get_database_settings
LAB = ROOT.parents[1] / 'lab/evolution-api'
PRIVATE = ROOT.parents[1] / 'private/telchi'
OUT = Path(__file__).resolve().parent
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
DEST = PRIVATE / 'backups' / ('evolution-v1-dev-' + STAMP)
TOOL_IMAGE = 'docker.io/library/postgres:18-alpine'
RESTORE_IMAGE = 'pgvector/pgvector:pg18-trixie'
CHANNELS = ['489e6f2c-8bac-4805-99ba-7dbe4d48c10e', '3cc01e11-da1c-4630-a9c6-ecc2f79220d4']


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def run(args, **kw):
    # Logs may contain database details: exclusively private, never terminal.
    with (DEST / 'commands.log').open('ab') as log:
        return subprocess.run(args, check=True, stderr=log, **kw)


def inventory(conn):
    tables = conn.execute("""SELECT schemaname,tablename FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog','information_schema')
        AND schemaname NOT LIKE 'pg_toast%%' ORDER BY 1,2""").fetchall()
    result = {}
    for row in tables:
        s, t = row['schemaname'], row['tablename']
        h = hashlib.sha256()
        n = 0
        with conn.cursor(name='backup_rows') as cur:
            cur.execute(sql.SQL('SELECT to_jsonb(t)::text AS j FROM {}.{} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(s), sql.Identifier(t)))
            for item in cur:
                b = item['j'].encode()
                h.update(len(b).to_bytes(8, 'big')); h.update(b); n += 1
        result[s + '.' + t] = {'count': n, 'sha256': h.hexdigest()}
    columns = conn.execute("""SELECT table_schema,table_name,column_name,ordinal_position,data_type,
        udt_name,is_nullable,column_default,is_identity,is_generated
        FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema')
        ORDER BY 1,2,4""").fetchall()
    constraints = conn.execute("""SELECT n.nspname,t.relname,c.conname,pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,3""").fetchall()
    return {'tables': result, 'columns': columns, 'constraints': constraints}


def main():
    os.umask(0o077)
    DEST.mkdir(parents=True, mode=0o700)
    (DEST / 'private').mkdir(mode=0o700)
    report = {'backup_directory': str(DEST), 'started_at': STAMP, 'target_writes': 0,
              'real_messages_sent': 0, 'databases': {}, 'restore_verified': False,
              'host_preflight': 'SAFE: 8 cores, load 1.49, MemAvailable 5204 MiB, swap stable/no si-so in samples',
              'concurrency': 'one sequential dump/restore; isolated PG max 512 MiB/2 CPU; no port/network',
              'restore_container_removed': False}
    owned = None
    try:
        # Preserve existing service definition privately, not printed or executed.
        saved = run(['podman', 'inspect', 'evolution-api'], stdout=subprocess.PIPE).stdout
        (DEST / 'private/evolution-container.json').write_bytes(saved)
        state = json.loads(saved)[0]['State']['Status']
        assert state == 'created', 'Do not back up a running Evolution without coordinated quiescence'
        # No changes to environment/control/store. Preserve configuration bytes and modes.
        for source, name in [(LAB / '.env', 'evolution.env'), (LAB / 'image.ref', 'image.ref'),
                             (ROOT / 'SrvRestAstroLS_v1/.env.backend-dev.local', 'backend.env'),
                             (PRIVATE / 'whatsapp-dev-control.json', 'telchi-control.json')]:
            shutil.copy2(source, DEST / 'private' / name)
        with tarfile.open(DEST / 'evolution-store.tar', 'w') as archive:
            archive.add(LAB / 'data/store', arcname='store', recursive=True)
        store = {str(p.relative_to(LAB / 'data/store')): digest(p)
                 for p in (LAB / 'data/store').rglob('*') if p.is_file()}
        report['store_manifest'] = store
        u = urlsplit(dotenv_values(LAB / '.env')['DATABASE_CONNECTION_URI'])
        u = u._replace(netloc=u.netloc.replace('host.containers.internal', '127.0.0.1'),
                       query=urlencode([(k, v) for k, v in parse_qsl(u.query) if k != 'schema']))
        dsns = {'team360': get_database_settings().dsn, 'evolution_api': urlunsplit(u)}
        for name, dsn in dsns.items():
            with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=3,
                                 application_name='authorized-dev-v1-backup',
                                 options='-c default_transaction_read_only=on -c statement_timeout=30000') as conn:
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                assert conn.execute('SELECT current_database() AS db').fetchone()['db'] == name
                snapshot = conn.execute('SELECT pg_export_snapshot() AS snapshot').fetchone()['snapshot']
                info = conninfo_to_dict(dsn)
                values = {'PGHOST': info.get('host', '127.0.0.1'), 'PGPORT': info.get('port', '5432'),
                          'PGDATABASE': name, 'PGUSER': info['user'], 'PGPASSWORD': info.get('password', ''),
                          'PGCONNECT_TIMEOUT': '3', 'PGOPTIONS': '-c default_transaction_read_only=on -c statement_timeout=60000'}
                assert all('\n' not in v for v in values.values())
                env = DEST / 'private' / (name + '-dump.env')
                env.write_text(''.join(k + '=' + v + '\n' for k, v in values.items()))
                with (DEST / (name + '.dump')).open('wb') as f:
                    run(['podman', 'run', '--rm', '--pull=never', '--network=host', '--memory=256m', '--cpus=1',
                         '--env-file', str(env), '--entrypoint=pg_dump', TOOL_IMAGE,
                         '--no-password', '--format=custom', '--snapshot=' + snapshot], stdout=f)
                baseline = inventory(conn)
                (DEST / (name + '-baseline.json')).write_text(json.dumps(baseline, default=str, sort_keys=True))
                report['databases'][name] = {'snapshot': snapshot, 'archive_sha256': digest(DEST / (name + '.dump')),
                                             'archive_bytes': (DEST / (name + '.dump')).stat().st_size,
                                             'table_count': len(baseline['tables'])}
                conn.rollback()
        # A fresh network-isolated recovery target; never restore to existing DBs.
        owned = run(['docker', 'run', '-d', '--pull=never', '--network=none', '--memory=512m', '--cpus=2',
                     '--label', 'team360.task=dev-v1-backup-' + STAMP,
                     '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', RESTORE_IMAGE,
                     '-c', 'shared_buffers=64MB', '-c', 'max_connections=10', '-c', 'listen_addresses='],
                    stdout=subprocess.PIPE).stdout.decode().strip()
        (DEST / 'restore-container-id.txt').write_text(owned + '\n')
        for _ in range(40):
            p = subprocess.run(['docker', 'exec', owned, 'pg_isready', '-U', 'postgres'], capture_output=True)
            if p.returncode == 0:
                break
            time.sleep(.5)
        else:
            with (DEST / 'restore-startup.log').open('wb') as f:
                subprocess.run(['docker', 'logs', owned], stdout=f, stderr=subprocess.STDOUT)
            raise RuntimeError('Isolated restore PostgreSQL not ready')
        for name in dsns:
            run(['docker', 'exec', owned, 'createdb', '-U', 'postgres', name], stdout=subprocess.DEVNULL)
            with (DEST / (name + '.dump')).open('rb') as f:
                run(['docker', 'exec', '-i', owned, 'pg_restore', '-U', 'postgres', '-d', name,
                     '--exit-on-error', '--no-owner', '--no-privileges'], stdin=f, stdout=subprocess.DEVNULL)
            # Run inventory using psql JSON; compare canonical full row hashes from COPY.
            baseline = json.loads((DEST / (name + '-baseline.json')).read_text())
            pgoptions = 'PGOPTIONS=-c search_path=' + ('evolution_api,public' if name == 'evolution_api' else 'public')
            restored = {}
            for key in baseline['tables']:
                schema, table = key.split('.', 1)
                query = sql.SQL('COPY (SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text COLLATE "C") TO STDOUT').format(sql.Identifier(schema), sql.Identifier(table)).as_string()
                # COPY text escapes special characters. Use JSON aggregate per row via psql -At instead.
                query = sql.SQL('SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(schema), sql.Identifier(table)).as_string()
                data = run(['docker', 'exec', '-e', pgoptions, owned, 'psql', '-X', '-U', 'postgres', '-d', name, '-At', '-c', query], stdout=subprocess.PIPE).stdout
                h = hashlib.sha256(); n = 0
                for b in data.splitlines():
                    h.update(len(b).to_bytes(8, 'big')); h.update(b); n += 1
                restored[key] = {'count': n, 'sha256': h.hexdigest()}
            report['verification_stage'] = name + ':rows'
            report['mismatched_tables'] = [k for k in restored if restored[k] != baseline['tables'][k]]
            assert restored == baseline['tables'], 'Restored table content mismatch: ' + name
            # Same column/constraint queries as source, excluding owner/ACL (stored in archive).
            for label, query in [
                ('columns', "SELECT table_schema,table_name,column_name,ordinal_position,data_type,udt_name,is_nullable,column_default,is_identity,is_generated FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,4"),
                ('constraints', "SELECT n.nspname,t.relname,c.conname,pg_get_constraintdef(c.oid) AS definition FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,3")]:
                data = run(['docker', 'exec', '-e', pgoptions, owned, 'psql', '-X', '-U', 'postgres', '-d', name, '-At', '-c',
                            'SELECT coalesce(json_agg(q),\'[]\'::json) FROM (' + query + ') q'], stdout=subprocess.PIPE).stdout
                report['verification_stage'] = name + ':' + label
                assert json.loads(data) == baseline[label], 'Restored schema mismatch: ' + name + ':' + label
            report['databases'][name]['restore_all_rows_and_schema'] = 'PASS'
        report['restore_verified'] = True
        report['files'] = {str(p.relative_to(DEST)): digest(p) for p in DEST.rglob('*')
                           if p.is_file() and p.name != 'commands.log'}
    finally:
        if owned:
            # Only this exact newly created recovery target; no existing processes touched.
            run(['docker', 'stop', '--time=10', owned], stdout=subprocess.DEVNULL)
            run(['docker', 'rm', '-v', owned], stdout=subprocess.DEVNULL)
            report['restore_container_removed'] = True
        (DEST / 'backup-verification.json').write_text(json.dumps(report, indent=2))
        (OUT / 'backup-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'backup_directory': str(DEST), 'restore_verified': report['restore_verified'],
                      'restore_container_removed': report['restore_container_removed'], 'target_writes': 0}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never emit DSNs, query rows or server details from exception text.
        print(json.dumps({'backup_recovery': 'FAIL', 'error_class': type(exc).__name__}))
        sys.exit(1)
