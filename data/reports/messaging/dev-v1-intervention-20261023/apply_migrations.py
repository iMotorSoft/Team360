"""Execute ONLY the owner's three hash-approved additive DEV migrations."""
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

import backup_verify as b


def main():
    os.umask(0o077)
    proof = json.loads((b.OUT / 'backup-verification.json').read_text())
    assert proof['restore_verified'] and proof['restore_container_removed']
    private = Path(proof['backup_directory'])
    packet = json.loads((b.LAB / 'data/dev-operational-v1/closed-review-packet.json').read_text())
    for migration in packet['migrations']:
        assert hashlib.sha256(Path(migration['path']).read_bytes()).hexdigest() == migration['sha256']
    for name, entry in proof['databases'].items():
        assert b.digest(private / (name + '.dump')) == entry['archive_sha256']
    result = {'authorization': 'owner DEV V1 intervention; no messages or Meta/webhook changes',
              'backup_restore_verified': True, 'migrations': [], 'history_preserved': False,
              'real_messages_sent': 0, 'admission': 'CLOSED / no operational V1 revision or credential created'}
    # Existing authorized admin connection, same local cluster; never log conninfo.
    base = conninfo_to_dict(b.get_database_settings().dsn)
    for db, schema, role, migrations in [
        ('team360', 'public', 't360devv1_ddl', packet['migrations'][:1]),
        ('evolution_api', 'evolution_api', 'evodevv1_ddl', packet['migrations'][1:])]:
        dsn = make_conninfo(**{**base, 'dbname': db})
        with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=3,
                             application_name='authorized-dev-v1-migration',
                             options='-c statement_timeout=15000 -c lock_timeout=2000') as conn:
            identity = conn.execute('SELECT current_database() AS db,host(inet_server_addr()) AS server,inet_server_port() AS port').fetchone()
            assert identity == {'db': db, 'server': '172.18.0.2', 'port': 5432}, 'Unexpected target'
            conn.execute(sql.SQL('SET LOCAL search_path TO {},public').format(sql.Identifier(schema)))
            assert not conn.execute("SELECT 1 FROM pg_tables WHERE schemaname=%s AND left(tablename,3)='ot_'", (schema,)).fetchone(), 'Already installed: do not blindly replay'
            before = b.inventory(conn)
            (private / (db + '-premigration.json')).write_text(json.dumps(before, default=str, sort_keys=True))
            assert not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone(), 'Do not adopt preexisting DDL identity'
            conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS').format(sql.Identifier(role)))
            conn.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA {} TO {}').format(sql.Identifier(schema), sql.Identifier(role)))
            for migration in migrations:
                content = Path(migration['path']).read_text()
                conn.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
                conn.execute(content, prepare=False)
                conn.execute('RESET ROLE')
                if db == 'evolution_api':
                    migration_name = Path(migration['path']).parent.name
                    assert not conn.execute(sql.SQL('SELECT 1 FROM {}._prisma_migrations WHERE migration_name=%s').format(sql.Identifier(schema)), (migration_name,)).fetchone()
                    # Explicit migration bookkeeping; no Prisma deploy/generate or other SQL file.
                    conn.execute(sql.SQL('''INSERT INTO {}._prisma_migrations
                        (id,checksum,finished_at,migration_name,logs,rolled_back_at,started_at,applied_steps_count)
                        VALUES (%s,%s,clock_timestamp(),%s,NULL,NULL,clock_timestamp(),1)''').format(sql.Identifier(schema)),
                        (str(uuid4()), migration['sha256'], migration_name))
                result['migrations'].append({'database': db, 'schema': schema, 'path': migration['path'],
                                             'sha256': migration['sha256'], 'ddl_owner': role, 'status': 'TRANSACTION_PENDING'})
            conn.execute(sql.SQL('REVOKE CREATE ON SCHEMA {} FROM {}').format(sql.Identifier(schema), sql.Identifier(role)))
            after = b.inventory(conn)
            for table, entry in before['tables'].items():
                if table.endswith('._prisma_migrations'):
                    # Old ledger rows must remain identical; only the 2 authorized entries added.
                    import collections
                    old = conn.execute(sql.SQL('SELECT count(*) AS n FROM {}._prisma_migrations WHERE migration_name NOT IN (%s,%s)').format(sql.Identifier(schema)),
                                       tuple(Path(x['path']).parent.name for x in migrations)).fetchone()['n']
                    assert old == entry['count']
                    # Entire historic migration ledger serialized separately for exact comparison below.
                    h = hashlib.sha256()
                    rows = conn.execute(sql.SQL('SELECT to_jsonb(t)::text AS j FROM {}._prisma_migrations t WHERE migration_name NOT IN (%s,%s) ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(schema)),
                                        tuple(Path(x['path']).parent.name for x in migrations)).fetchall()
                    for row in rows:
                        data = row['j'].encode();h.update(len(data).to_bytes(8,'big'));h.update(data)
                    assert h.hexdigest() == entry['sha256']
                else:
                    assert after['tables'][table] == entry, 'Historical table changed: ' + table
            conn.commit()
            for entry in result['migrations']:
                if entry['database'] == db:
                    entry['status'] = 'APPLIED'
            (b.OUT / 'migration-result.json').write_text(json.dumps(result, indent=2))
    result['history_preserved'] = True
    result['completed_at'] = datetime.now(timezone.utc).isoformat()
    (b.OUT / 'migration-result.json').write_text(json.dumps(result, indent=2))
    (private / 'migration-result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({'three_migrations': 'PASS', 'history_preserved': True, 'real_messages_sent': 0}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'migration_execution': 'STOPPED', 'error_class': type(exc).__name__,
                          'instruction': 'Inspect committed migration-result.json before any retry; never replay blindly'}))
        sys.exit(1)
