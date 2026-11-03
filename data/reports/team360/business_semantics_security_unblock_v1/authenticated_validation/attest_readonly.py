"""Read-only metadata attestation. Run from backend; no app, login, seed or pool startup."""
import asyncio
import hashlib
import importlib.util
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import dotenv_values
from modules.db.settings import get_database_settings
from modules.console.login_cli import read_config, checked_target

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
AUTH = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/console-auth-window-20261014T134648Z/issuer.json')
spec = importlib.util.spec_from_file_location('previous_probe', OUT.parent / 'probe_readonly.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
QUERIES = {k: old.QUERIES[k] for k in ('server', 'role', 'membership', 'direct_role_grants', 'extensions', 'tables', 'policies', 'sessions')}
QUERIES.update({
    'credentials_aggregate': 'SELECT count(*) AS enrolled,count(*) FILTER (WHERE NOT disabled) AS enabled FROM console_password_credentials',
    'login_attempts_aggregate': 'SELECT count(*) AS tracked_accounts FROM console_login_attempts',
    'semantic_aggregate': 'SELECT status,count(*) AS n FROM business_concepts GROUP BY status ORDER BY status',
    'embeddings_aggregate': 'SELECT model_alias,model_revision,dimension,count(*) AS n FROM business_concept_embeddings GROUP BY 1,2,3 ORDER BY 1,2,3',
    'iam_table_privileges': "SELECT c.relname,pg_get_userbyid(c.relowner) AS owner,has_table_privilege(current_user,c.oid,'SELECT') AS can_select,has_table_privilege(current_user,c.oid,'INSERT') AS can_insert,has_table_privilege(current_user,c.oid,'UPDATE') AS can_update,has_table_privilege(current_user,c.oid,'DELETE') AS can_delete FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('console_password_credentials','console_login_attempts','core_events') ORDER BY 1",
})

async def probe(dsn, *, expected=None):
    result = {'target': old.target(dsn), 'queries': {}, 'errors': {}}
    try:
        async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row, connect_timeout=5,
                options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000',
                application_name='bs-authenticated-validation-readonly') as conn:
            if expected:
                await checked_target(conn, expected, runtime=True)
                result['dedicated_role_guard'] = 'PASS'
            for name, sql in QUERIES.items():
                try:
                    async with conn.transaction():
                        result['queries'][name] = await (await conn.execute(sql)).fetchall()
                except Exception as exc:
                    result['errors'][name] = type(exc).__name__
            await conn.rollback()
    except Exception as exc:
        result['errors']['connection_or_guard'] = type(exc).__name__
    return result

async def main():
    original = dict(os.environ)
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'database_writes': 0,
              'queries': QUERIES, 'contexts': {}}
    for name, override in [('inherited_shell', None), ('backend_dev_launcher_override', Path('../.env.backend-dev.local'))]:
        os.environ.clear()
        os.environ.update(original)
        if override:
            if not override.is_file():
                report['contexts'][name] = {'override_present': False}
                continue
            os.environ.update({k: v for k, v in dotenv_values(override).items() if v is not None})
        report['contexts'][name] = {'source': old.source(),
            'embedding_configuration_presence': {k: bool(os.getenv(k)) for k in (
                'TEAM360_SEMANTICS_EMBEDDING_ALIAS', 'TEAM360_SEMANTICS_EMBEDDING_REVISION',
                'TEAM360_SEMANTICS_EMBEDDING_DIMENSION', 'TEAM360_SEMANTICS_VECTOR_CALIBRATION',
                'TEAM360_SEMANTICS_VECTOR_MINIMUM_SCORE', 'TEAM360_SEMANTICS_VECTOR_MINIMUM_MARGIN')},
            **await probe(get_database_settings().dsn)}
    os.environ.clear()
    os.environ.update(original)
    try:
        cfg = read_config(AUTH)
        report['contexts']['authenticated_cli_config'] = {'source': 'private issuer.json runtime_dsn',
            'pin': cfg['target'], **await probe(cfg['runtime_dsn'], expected=cfg['target'])}
        # Inspect names/count only, never read or emit session token contents.
        report['private_session_file_count'] = len(list(AUTH.parent.glob('*.paseto')))
    except Exception as exc:
        report['contexts']['authenticated_cli_config'] = {'error': type(exc).__name__}
    (OUT / 'environment_probe.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    corpus_path = OUT.parent.parent / 'business_semantics_operational_closure_v1/SEMANTIC_DATASET.json'
    data = json.loads(corpus_path.read_text())
    corpus = {'sha256': hashlib.sha256(corpus_path.read_bytes()).hexdigest(), 'splits': {},
              'overlap': sorted(set(r['query'] for r in data['calibration']) & set(r['query'] for r in data['validation_holdout'])),
              'pgvector_executed_this_run': False, 'thresholds_modified': False, 'holdout_tuned': False}
    for split in ('calibration', 'validation_holdout'):
        cases = data[split]
        corpus['splits'][split] = {'total': len(cases), 'unique_queries': len(set(r['query'] for r in cases)),
            'intent_labels': dict(Counter(r.get('intent', 'NO_INTENT_LABEL') for r in cases)),
            'constraint_labels': dict(Counter(r.get('constraint', 'NO_CONSTRAINT_LABEL') for r in cases))}
    (OUT / 'corpus_audit.json').write_text(json.dumps(corpus, indent=2) + '\n')
    previous = json.loads((OUT.parent / 'auth_window/integrity.json').read_text())
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in previous['source_sha256']}
    (OUT / 'auth_baseline_integrity.json').write_text(json.dumps({'source_sha256': hashes,
        'changed_from_auth_window': [p for p, h in hashes.items() if h != previous['source_sha256'][p]]}, indent=2) + '\n')
    print('Read-only attestation and corpus/integrity audit written; no secrets emitted.')

if __name__ == '__main__':
    asyncio.run(main())
