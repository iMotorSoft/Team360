"""Opt-in DEV semantics connection; never changes Team360's shared pool."""
from contextlib import asynccontextmanager
import os

import psycopg
from psycopg.rows import dict_row

from modules.console.login_cli import read_config, checked_target


class RestrictedSemanticsConnection:
    def __init__(self, config_path):
        if os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
            raise PermissionError('explicit_DEV_required')
        cfg = read_config(config_path)
        self._dsn, self._target = cfg['runtime_dsn'], cfg['target']

    @asynccontextmanager
    async def __call__(self):
        if os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
            raise PermissionError('explicit_DEV_required')
        async with await psycopg.AsyncConnection.connect(self._dsn, row_factory=dict_row,
                connect_timeout=5, options='-c statement_timeout=10000 -c lock_timeout=3000') as conn:
            async with conn.transaction():
                await checked_target(conn, self._target, runtime=True)
                yield conn
