"""Shared READ-ONLY HANA connection (project convention).

Never writes. Never hardcodes credentials — reads access/sap/hana.env.
"""
from __future__ import annotations

import shlex
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT, SECRET_ROOT

from hdbcli import dbapi

TELCHI_ROOT = INVESTIGATION_ROOT
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"


def load_hana_config() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in HANA_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if not separator:
            continue
        parsed = shlex.split(raw_value, posix=True)
        if parsed:
            values[key] = parsed[0]
    return values


def connect() -> tuple[dbapi.Connection, dbapi.Cursor]:
    """Create a READ-ONLY HANA connection."""
    cfg = load_hana_config()
    host = cfg.get("TELCHI_SAP_HANA_HOST", "127.0.0.1")
    port = int(cfg.get("TELCHI_SAP_HANA_PORT", "30015"))
    user = cfg.get("TELCHI_SAP_HANA_USER", "")
    password = cfg.get("TELCHI_SAP_HANA_PASSWORD", "")
    schema = cfg.get("TELCHI_SAP_HANA_SCHEMA", "TELCHI")
    conn = dbapi.connect(
        address=host, port=port, user=user, password=password,
        currentSchema=schema, encrypt="false",
    )
    cursor = conn.cursor()
    return conn, cursor


def table_columns(schema: str, table: str) -> list[str]:
    """Confirmed physical columns for a HANA table (READ ONLY).

    Catalog (SYS.TABLE_COLUMNS) is unreliable for some tables under the
    insiding_hana grant; fall back to a zero-row describe (SELECT * ... LIMIT 0)
    which is still READ ONLY and CONFIRMED.
    """
    conn, cur = connect()
    try:
        cur.execute(
            'SELECT "COLUMN_NAME" FROM "SYS"."TABLE_COLUMNS" '
            'WHERE "SCHEMA_NAME" = ? AND "TABLE_NAME" = ? ORDER BY "POSITION"',
            (schema, table),
        )
        cols = [row[0] for row in cur.fetchall()]
        if cols:
            return cols
        # fallback: describe via LIMIT 0
        cur.execute(f'SELECT * FROM "{schema}"."{table}" LIMIT 0')
        return [col[0] for col in cur.description]
    finally:
        cur.close()
        conn.close()