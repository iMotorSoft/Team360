"""Resume verification of existing immutable DEV archives; no fresh dump or target writes."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import backup_verify as b

report = json.loads((b.OUT / 'backup-verification.json').read_text())
b.DEST = Path(report['backup_directory'])
owned = None
try:
    for name, entry in report['databases'].items():
        assert b.digest(b.DEST / (name + '.dump')) == entry['archive_sha256']
    owned = b.run(['docker', 'run', '-d', '--pull=never', '--network=none', '--memory=512m', '--cpus=2',
                   '--label', 'team360.task=dev-v1-restore-verification', '--tmpfs', '/var/lib/postgresql:rw,size=268435456',
                   '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', b.RESTORE_IMAGE,
                   '-c', 'shared_buffers=32MB', '-c', 'max_connections=10', '-c', 'listen_addresses=',
                   '-c', 'fsync=off', '-c', 'full_page_writes=off', '-c', 'synchronous_commit=off'],
                  stdout=subprocess.PIPE).stdout.decode().strip()
    (b.DEST / 'resume-restore-container-id.txt').write_text(owned + '\n')
    for _ in range(120):
        if subprocess.run(['docker', 'exec', owned, 'pg_isready', '-U', 'postgres'], capture_output=True).returncode == 0:
            break
        time.sleep(.5)
    else:
        raise RuntimeError('Isolated recovery PostgreSQL not ready')
    for name, entry in report['databases'].items():
        b.run(['docker', 'exec', owned, 'createdb', '-U', 'postgres', name], stdout=subprocess.DEVNULL)
        with (b.DEST / (name + '.dump')).open('rb') as f:
            b.run(['docker', 'exec', '-i', owned, 'pg_restore', '-U', 'postgres', '-d', name,
                   '--exit-on-error', '--no-owner', '--no-privileges'], stdin=f, stdout=subprocess.DEVNULL)
        baseline = json.loads((b.DEST / (name + '-baseline.json')).read_text())
        opts = 'PGOPTIONS=-c search_path=' + ('evolution_api,public' if name == 'evolution_api' else 'public')
        def query(text):
            return b.run(['docker', 'exec', '-e', opts, owned, 'psql', '-X', '-U', 'postgres', '-d', name, '-At', '-F', '\t', '-c', text], stdout=subprocess.PIPE).stdout
        hashes = {key: hashlib.sha256() for key in baseline['tables']}
        counts = {key: 0 for key in baseline['tables']}
        selects = []
        for key in baseline['tables']:
            schema, table = key.split('.', 1)
            selects.append(b.sql.SQL('SELECT {} AS k,to_jsonb(t)::text AS j FROM {}.{} t').format(b.sql.Literal(key), b.sql.Identifier(schema), b.sql.Identifier(table)))
        text = b.sql.SQL('SELECT k,j FROM ({}) all_rows ORDER BY k COLLATE "C",j COLLATE "C"').format(b.sql.SQL(' UNION ALL ').join(selects)).as_string()
        for line in query(text).splitlines():
            key, row = line.split(b'\t', 1)
            key = key.decode()
            hashes[key].update(len(row).to_bytes(8, 'big')); hashes[key].update(row); counts[key] += 1
        restored = {key: {'count': counts[key], 'sha256': hashes[key].hexdigest()} for key in hashes}
        assert restored == baseline['tables'], 'Full data mismatch'
        entry['all_restored_table_rows'] = 'PASS'
        for label, text in [
            ('columns', "SELECT table_schema,table_name,column_name,ordinal_position,data_type,udt_name,is_nullable,column_default,is_identity,is_generated FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,4"),
            ('constraints', "SELECT n.nspname,t.relname,c.conname,pg_get_constraintdef(c.oid) AS definition FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,3")]:
            actual = json.loads(query("SELECT coalesce(json_agg(q),'[]'::json) FROM (" + text + ') q'))
            expected = baseline[label]
            if label == 'columns':
                # pg_dump correctly omits dropped-column attnum holes. Compare live
                # column order (dense rank per table), not historical physical attnums.
                def logical_order(columns):
                    positions = {}
                    result = []
                    for column in columns:
                        key = (column['table_schema'], column['table_name'])
                        positions[key] = positions.get(key, 0) + 1
                        result.append(dict(column, ordinal_position=positions[key]))
                    return result
                actual, expected = logical_order(actual), logical_order(expected)
                entry['schema_column_order_comparison'] = 'live order; dropped-column attnum holes normalized'
            if actual != expected:
                # Diagnostic kept PRIVATE; do not emit default values or row contents.
                (b.DEST / (name + '-' + label + '-restored.json')).write_text(json.dumps(actual, indent=2))
                diffs = []
                for a, e in zip(actual, expected):
                    if a != e:
                        diffs.append({'object': [a.get('table_schema'), a.get('table_name'), a.get('column_name')],
                                      'fields': [k for k in a if a.get(k) != e.get(k)]})
                print(json.dumps({'schema_comparison': label, 'actual_count': len(actual), 'expected_count': len(expected), 'differing_fields': diffs[:10]}))
                raise AssertionError('Restored schema differs: ' + name + ':' + label)
        entry['restore_all_rows_and_schema'] = 'PASS'
    report['restore_verified'] = True
    report['verification_stage'] = 'COMPLETE'
finally:
    if owned:
        with (b.DEST / 'resume-restore-startup.log').open('wb') as f:
            subprocess.run(['docker', 'logs', owned], stdout=f, stderr=subprocess.STDOUT)
        b.run(['docker', 'stop', '--time=10', owned], stdout=subprocess.DEVNULL)
        b.run(['docker', 'rm', '-v', owned], stdout=subprocess.DEVNULL)
    report['restore_container_removed'] = True
    (b.DEST / 'backup-verification.json').write_text(json.dumps(report, indent=2))
    (b.OUT / 'backup-verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'backup_directory': str(b.DEST), 'restore_verified': report['restore_verified'], 'own_recovery_container_removed': True}))
