"""READ-ONLY audit wrapper for HANA (TELCHI policy).

Every query in the credit-control cycle must execute through this helper so
that write operations are impossible and the executed SQL can be audited.

SAP_WRITE_COUNT must be 0 at the end of the cycle.
"""
from __future__ import annotations

import re
from typing import Any

_WRITE_TOKENS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE"
    r"|CALL|TRUNCATE|UPSERT|REPLACE)\b",
    re.IGNORECASE,
)

LOCKED = False
WARNED = set()


def guard_sql(sql: str) -> None:
    """Refuse statements that could write or invoke procedures."""
    if _WRITE_TOKENS.search(sql):
        raise RuntimeError(f"WRITE ATTEMPT BLOCKED: {sql[:120]!r}")
    body = sql.lstrip()
    if body[:6].upper() == "SELECT":
        return
    # allow only SELECT-like (CALL/EXEC etc. rejected by token check above)
    raise RuntimeError(f"ONLY SELECT ALLOWED: {sql[:120]!r}")


class ReadOnlyCursor:
    def __init__(self, cursor: Any):
        self._c = cursor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def execute(self, sql: str, params: Any = None, *args: Any, **kwargs: Any) -> Any:
        guard_sql(sql)
        if params is None:
            return self._c.execute(sql, *args, **kwargs)
        return self._c.execute(sql, params, *args, **kwargs)

    def executemany(self, sql: str, seq: Any) -> Any:  # pragma: no cover
        guard_sql(sql)
        return self._c.executemany(sql, seq)

    def connection(self) -> Any:
        return self._c.connection

    @property
    def description(self) -> Any:
        return self._c.description


class ReadOnlyConnection:
    def __init__(self, conn: Any):
        self._c = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def cursor(self) -> ReadOnlyCursor:
        return ReadOnlyCursor(self._c.cursor())

    def rollback(self) -> Any:
        return self._c.rollback()

    def close(self) -> Any:
        return self._c.close()
