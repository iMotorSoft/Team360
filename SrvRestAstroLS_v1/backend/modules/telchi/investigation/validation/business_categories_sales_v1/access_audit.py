"""Bounded local DEV Console read-only audit; no identity impersonation."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row

from modules.db.settings import get_database_settings
from .access_repository import AccessInventoryRepository


async def run(output):
    for key, value in dotenv_values('../.env.backend-dev.local').items():
        if value is not None:
            os.environ[key] = value
    dsn = get_database_settings().dsn
    target = urlparse(dsn)
    if target.hostname not in {'localhost', '127.0.0.1'} or target.path != '/team360':
        raise ValueError('unexpected_DEV_target')
    async with await psycopg.AsyncConnection.connect(
        dsn, connect_timeout=5, row_factory=dict_row,
        options='-c default_transaction_read_only=on -c statement_timeout=5000',
        application_name='telchi-category-readonly-inventory',
    ) as conn:
        evidence = await AccessInventoryRepository().inspect(conn)
    evidence.update(observed_at=datetime.now(timezone.utc).isoformat(), database_writes=0,
                    limitation='Resolver inventory only; no live authentication, revocation or session claim')
    evidence['source_hashes'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__), Path(__file__).with_name('access_repository.py'))}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(evidence, stream, indent=2, default=str)
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))
