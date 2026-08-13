"""Read-only SAP HANA 2 smoke for Telchi over the validated strongSwan VPN.

The password is loaded only from the private external ``hana.env`` file.
This script never writes to HANA and never prints connection strings or secrets.
"""

from __future__ import annotations

import importlib.metadata
import ipaddress
import shlex
import socket
import sys
from pathlib import Path
from typing import Any


HANA_HOST = "192.168.20.20"
HANA_PORT = 30015
HANA_SCHEMA = "TELCHI"
HANA_USER = "insiding_hana"
PRIVATE_ENV_FILE = Path(
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/"
    "telchi/access/sap/hana.env"
)

CORE_TABLES = (
    "OINV",
    "INV1",
    "ORIN",
    "RIN1",
    "OINM",
    "OITM",
    "OITW",
    "OITT",
    "ITT1",
    "OCRD",
    "OSLP",
    "OWHS",
)
OPTIONAL_TABLES = (
    "OITB",
    "OITG",
    "OCQG",
    "OACT",
    "OUSR",
    "OPLN",
    "OMRC",
    "ODLN",
    "DLN1",
    "OHEM",
    "OUBR",
)
HISTORICAL_UDTS = ("@OBJ_VENTAS_C", "@OBJ_VENTAS_L")


class SmokeBlocked(RuntimeError):
    """Expected external/configuration blocker with a stable public code."""


def emit(label: str, result: str) -> None:
    print(f"{label:<28} {result}")


def load_private_config(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise SmokeBlocked("TELCHI_SAP_HANA_PASSWORD_REQUIRED")
    if path.stat().st_mode & 0o077:
        raise SmokeBlocked("TELCHI_SAP_HANA_ENV_PERMISSIONS")

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, encoded_value = line.partition("=")
        if not separator:
            raise SmokeBlocked("TELCHI_SAP_HANA_ENV_INVALID")
        try:
            parsed = shlex.split(encoded_value, posix=True)
        except ValueError as exc:
            raise SmokeBlocked("TELCHI_SAP_HANA_ENV_INVALID") from exc
        if len(parsed) != 1:
            raise SmokeBlocked("TELCHI_SAP_HANA_ENV_INVALID")
        values[key] = parsed[0]

    expected = {
        "TELCHI_SAP_HANA_HOST": HANA_HOST,
        "TELCHI_SAP_HANA_PORT": str(HANA_PORT),
        "TELCHI_SAP_HANA_SCHEMA": HANA_SCHEMA,
        "TELCHI_SAP_HANA_USER": HANA_USER,
    }
    for key, expected_value in expected.items():
        if values.get(key) != expected_value:
            raise SmokeBlocked(f"{key}_INVALID")
    if not values.get("TELCHI_SAP_HANA_PASSWORD"):
        raise SmokeBlocked("TELCHI_SAP_HANA_PASSWORD_REQUIRED")
    if set(values) != {*expected, "TELCHI_SAP_HANA_PASSWORD"}:
        raise SmokeBlocked("TELCHI_SAP_HANA_ENV_INVALID")
    return values


def tcp_preflight() -> None:
    try:
        with socket.create_connection((HANA_HOST, HANA_PORT), timeout=5):
            pass
    except OSError as exc:
        raise SmokeBlocked("TELCHI_SAP_HANA_TCP_UNREACHABLE") from exc


def fetch_scalar(cursor: Any, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
    cursor.execute(sql, parameters)
    row = cursor.fetchone()
    return None if row is None else row[0]


def catalog_names(cursor: Any, names: tuple[str, ...]) -> set[str]:
    placeholders = ",".join("?" for _ in names)
    cursor.execute(
        "SELECT TABLE_NAME FROM SYS.TABLES "
        f"WHERE SCHEMA_NAME = ? AND TABLE_NAME IN ({placeholders})",
        (HANA_SCHEMA, *names),
    )
    found = {str(row[0]) for row in cursor.fetchall()}
    cursor.execute(
        "SELECT VIEW_NAME FROM SYS.VIEWS "
        f"WHERE SCHEMA_NAME = ? AND VIEW_NAME IN ({placeholders})",
        (HANA_SCHEMA, *names),
    )
    found.update(str(row[0]) for row in cursor.fetchall())
    return found


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def validate_read_access(cursor: Any, table_names: tuple[str, ...]) -> None:
    schema = quote_identifier(HANA_SCHEMA)
    for table_name in table_names:
        table = quote_identifier(table_name)
        cursor.execute(f"SELECT TOP 1 1 FROM {schema}.{table}")
        cursor.fetchone()


def run_smoke() -> None:
    emit("SAP HANA HOST", HANA_HOST)
    emit("SAP HANA PORT", str(HANA_PORT))
    emit("SAP HANA USER", HANA_USER)
    emit("SAP HANA SCHEMA", HANA_SCHEMA)

    try:
        config = load_private_config(PRIVATE_ENV_FILE)
    except SmokeBlocked:
        emit("SAP HANA PASSWORD", "MISSING")
        raise
    emit("SAP HANA PASSWORD", "LOADED")

    tcp_preflight()
    emit("VPN/TCP PREFLIGHT", "PASS")

    try:
        from hdbcli import dbapi
    except ImportError as exc:
        emit("HANA DRIVER", "FAIL")
        raise SmokeBlocked("HDBCLI_REQUIRED") from exc
    emit("HANA DRIVER", f"PASS ({importlib.metadata.version('hdbcli')})")

    password = config.pop("TELCHI_SAP_HANA_PASSWORD")
    connection = None
    cursor = None
    try:
        connection = dbapi.connect(
            address=HANA_HOST,
            port=HANA_PORT,
            user=HANA_USER,
            password=password,
        )
        password = ""
        connection.setautocommit(False)
        emit("HANA AUTH", "PASS")
        emit("HANA CONNECTION", "PASS")

        cursor = connection.cursor()
        current_user = fetch_scalar(cursor, "SELECT CURRENT_USER FROM DUMMY")
        if str(current_user).casefold() != HANA_USER.casefold():
            raise SmokeBlocked("HANA_AUTH_IDENTITY_MISMATCH")

        version = fetch_scalar(cursor, "SELECT VERSION FROM SYS.M_DATABASE")
        if not version:
            raise SmokeBlocked("HANA_VERSION_UNAVAILABLE")
        emit("HANA VERSION", f"PASS ({version})")

        schema_count = fetch_scalar(
            cursor,
            "SELECT COUNT(*) FROM SYS.SCHEMAS WHERE SCHEMA_NAME = ?",
            (HANA_SCHEMA,),
        )
        if int(schema_count or 0) != 1:
            raise SmokeBlocked("HANA_SCHEMA_NOT_FOUND")
        emit("HANA SCHEMA TELCHI", "PASS")

        present_core = catalog_names(cursor, CORE_TABLES)
        missing_core = tuple(name for name in CORE_TABLES if name not in present_core)
        if missing_core:
            emit("SAP B1 CORE TABLES", f"FAIL (missing {','.join(missing_core)})")
            raise SmokeBlocked("SAP_B1_CORE_TABLES_MISSING")
        validate_read_access(cursor, CORE_TABLES)
        emit("HANA READ ACCESS", "PASS")
        emit("SAP B1 CORE TABLES", f"PASS ({len(present_core)}/{len(CORE_TABLES)})")

        present_optional = catalog_names(cursor, OPTIONAL_TABLES)
        emit(
            "SAP B1 OPTIONAL TABLES",
            f"OBSERVED ({len(present_optional)}/{len(OPTIONAL_TABLES)})",
        )

        present_udts = catalog_names(cursor, HISTORICAL_UDTS)
        if present_udts:
            validate_read_access(cursor, tuple(sorted(present_udts)))
        missing_udts = tuple(name for name in HISTORICAL_UDTS if name not in present_udts)
        if missing_udts:
            emit("HISTORICAL UDT", f"PARTIAL (missing {','.join(missing_udts)})")
        else:
            emit("HISTORICAL UDT", "PASS (2/2)")
    except SmokeBlocked:
        raise
    except Exception as exc:
        error_name = type(exc).__name__.upper()
        if connection is None:
            emit("HANA AUTH", "FAIL")
            raise SmokeBlocked(f"HANA_AUTH_FAILED_{error_name}") from exc
        raise SmokeBlocked(f"HANA_READ_FAILED_{error_name}") from exc
    finally:
        password = ""
        config.clear()
        if cursor is not None:
            cursor.close()
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()
        emit("HANA CLEAN CLOSE", "PASS" if connection is not None else "NOT_OPENED")


def main() -> int:
    try:
        run_smoke()
    except SmokeBlocked as exc:
        print("TEAM360_TELCHI_SAP_HANA_SMOKE_BLOCKED")
        print(f"BLOCKER: {exc}")
        return 2
    print("TEAM360_TELCHI_SAP_HANA_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
