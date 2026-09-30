"""Idempotent DEV-only provisioning for the isolated Telchi DuckLake catalog.

This is intentionally separate from runtime. It uses an administrator DSN
provided by the shell (normally ``DB_PG_V360_URL``) only to create the
module-local database and role. The runtime role is never a superuser.
"""
from __future__ import annotations

import argparse
import os
import secrets
import stat
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

from .runtime import CATALOG_DATABASE, DEFAULT_PRIVATE_CONFIG, RUNTIME_ROLE


def _normalize_dsn(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"postgresql+psycopg", "postgres"}:
        return urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return value


def _private_password(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("TELCHI_DUCKLAKE_PG_PASSWORD="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def provision(*, check_only: bool = False) -> dict[str, object]:
    admin_dsn = os.environ.get("TELCHI_DUCKLAKE_ADMIN_DSN", "").strip() or os.environ.get("DB_PG_V360_URL", "").strip()
    if not admin_dsn:
        raise RuntimeError("TELCHI_DUCKLAKE_ADMIN_DSN or DB_PG_V360_URL is required for provisioning")
    private_path = Path(os.environ.get("TEAM360_TELCHI_DUCKLAKE_PRIVATE_CONFIG", str(DEFAULT_PRIVATE_CONFIG))).expanduser()
    password = _private_password(private_path) or secrets.token_urlsafe(32)
    if check_only:
        return {"admin_configured": True, "database": CATALOG_DATABASE, "role": RUNTIME_ROLE, "private_config_exists": private_path.is_file()}

    with psycopg.connect(_normalize_dsn(admin_dsn), autocommit=True) as connection:
        role_exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (RUNTIME_ROLE,)).fetchone() is not None
        if not role_exists:
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}").format(
                    sql.Identifier(RUNTIME_ROLE), sql.Literal(password)
                )
            )
        database_exists = connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (CATALOG_DATABASE,)).fetchone() is not None
        if not database_exists:
            connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(CATALOG_DATABASE), sql.Identifier(RUNTIME_ROLE)))
        role = connection.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolcanlogin FROM pg_roles WHERE rolname=%s", (RUNTIME_ROLE,)
        ).fetchone()
        database = connection.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", (CATALOG_DATABASE,)).fetchone()

    private_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not private_path.exists():
        private_path.write_text(
            "TELCHI_DUCKLAKE_PG_HOST=localhost\n"
            "TELCHI_DUCKLAKE_PG_PORT=5432\n"
            f"TELCHI_DUCKLAKE_PG_DATABASE={CATALOG_DATABASE}\n"
            f"TELCHI_DUCKLAKE_PG_USER={RUNTIME_ROLE}\n"
            f"TELCHI_DUCKLAKE_PG_PASSWORD={password}\n",
            encoding="utf-8",
        )
        private_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return {
        "admin_configured": True,
        "database": CATALOG_DATABASE,
        "role": RUNTIME_ROLE,
        "role_flags": role,
        "database_owner": database[0] if database else None,
        "private_config_exists": private_path.is_file(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="inspect provisioning prerequisites without changes")
    args = parser.parse_args()
    print(provision(check_only=args.check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
