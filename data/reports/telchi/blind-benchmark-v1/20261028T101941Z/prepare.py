"""Technical preparation only. No business question, no investigator code edits."""
import asyncio
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
BACKEND = ROOT / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
os.umask(0o077)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')

def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return 'NOT_INSTALLED'

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True)

from modules.telchi.exploratory_sql.ask import SYSTEM
from modules.telchi.exploratory_sql.ask_sources import CATALOG, AskExecutor, context_for_run
from modules.telchi.exploratory_sql.foundation import host_read_preflight
from modules.telchi.exploratory_sql.research import LunaSQL, code_digest
from modules.telchi.assistant.luna import MODEL, CREDENTIAL_ENV
from modules.telchi.exploratory_sql import CONTRACT_VERSION

save('configuration.json', dict(branch=git('branch', '--show-current').strip(), head=git('rev-parse', 'HEAD').strip(),
    platform=platform.platform(), python=sys.version, uid=os.getuid(), model=MODEL, reasoning='medium',
    endpoint='https://api.openai.com/v1/responses', fallback=False, store=False,
    credential_variable=CREDENTIAL_ENV, credential_present=bool(os.getenv(CREDENTIAL_ENV)),
    credential_project='Not independently established from key; owner-authorized DEV variable, never copied',
    contract_version=CONTRACT_VERSION, catalog=asdict(CATALOG), budget=asdict(context_for_run().effective_budget),
    system_sha256=hashlib.sha256(SYSTEM.encode()).hexdigest(), exploratory_code_digest=code_digest(),
    dependencies={p: package_version(p) for p in ('duckdb','sqlglot','httpx','psycopg','pytest')},
    pi={k: os.getenv(k) for k in ('PI_PROVIDER','PI_MODEL','PI_REASONING_LEVEL','PI_SESSION_ID')},
    host=host_read_preflight()))
(OUT / 'worktree-status.txt').write_text(git('status', '--short', '--untracked-files=all'))

# Startup only: no input question is sent. EOF ends cleanly and closes the lock.
started=time.monotonic()
startup=subprocess.run([sys.executable, '-m', 'modules.telchi.exploratory_sql.ask',
    '--authorize-dev-io-exception'], input='', text=True, capture_output=True, cwd=BACKEND,
    env={**os.environ, 'TEAM360_ENV':'development'}, timeout=30)
(OUT / 'startup.txt').write_text(startup.stdout + startup.stderr)
save('startup.json', dict(returncode=startup.returncode, elapsed_seconds=time.monotonic()-started, business_question_sent=False))

# A synthetic readiness request with no enterprise input or data.
async def probe():
    model=LunaSQL(system='Return exactly a JSON object {"ready":true}.', max_output_tokens=4096)
    try:
        result=await model.next({'purpose':'authorized DEV model preflight'}, timeout=45)
        save('model-preflight.json', dict(ready=result=={'ready':True}, result=result, calls=model.calls, enterprise_data_sent=False))
    except RuntimeError as exc:
        save('model-preflight.json', dict(ready=False, reason=str(exc), calls=model.calls, enterprise_data_sent=False))
asyncio.run(probe())

# Resolve catalog, manifests and schemas only. No commercial analysis or totals.
from modules.telchi.datalake.foundation_reader import FoundationReader
reader=FoundationReader()
ctx=context_for_run()
try:
    with AskExecutor(ctx, authorized=True) as executor:
        executor.reader=reader
        with executor._open_connection(ctx.effective_budget) as db:
            executor._prepare_connection(db, ctx)
            access=reader.resolve_on(db)
            schemas={t.name: db.execute(f'DESCRIBE SELECT * FROM {t.name}').fetchall() for t in CATALOG.tables}
            refs={}
            for dataset in ('products','salespersons'):
                path=access.reference(dataset)
                refs[dataset]=dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            save('foundation-binding.json', dict(ready=True, readonly=db.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone()[0],
                binding=access.as_dict(), manifest=access.manifest, schemas=schemas, reference_files=refs,
                snapshot_1408_present=bool(db.execute("SELECT snapshot_id FROM ducklake_snapshots('telchi') WHERE snapshot_id=1408").fetchall()),
                period='All published active OINV/INV1 rows; no imposed date window; calendar completeness NOT certified',
                business_queries_executed=0, additional_foundation_components_authorized=False))
except Exception as exc:
    # Never record exception text which might contain connection secrets.
    save('foundation-binding.json', dict(ready=False, error_type=type(exc).__name__, business_queries_executed=0))
