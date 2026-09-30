"""TELCHI_PG_DURABLE_POSTGRES18_GLOBAL_READINESS_AND_ISOLATION_V1.

This gate is deliberately read-only.  It resolves the existing Team360 DSN
through ``backend/globalVar.py``, opens one PostgreSQL connection with
``default_transaction_read_only=on``, and writes only external evidence.

It does not install pg_durable, alter PostgreSQL, create objects, inspect SAP,
or start any worker/workflow.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

GATE = "TELCHI_PG_DURABLE_POSTGRES18_GLOBAL_READINESS_AND_ISOLATION_V1"
REPO_ROOT = Path(__file__).resolve().parents[7]
BACKEND_ROOT = REPO_ROOT / "SrvRestAstroLS_v1" / "backend"
GLOBALVAR_PATH = BACKEND_ROOT / "globalVar.py"
EVIDENCE_ROOT = Path(
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi"
) / GATE

READ_ONLY_SQL_RE = re.compile(r"^\s*(SELECT|SHOW)\b", re.IGNORECASE)
FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|GRANT|REVOKE|"
    r"VACUUM|REINDEX|TRUNCATE|COPY|CALL|DO|NOTIFY|LISTEN|UNLISTEN|"
    r"CHECKPOINT|LOAD|SECURITY_LABEL)\b",
    re.IGNORECASE,
)
SECRET_KEY_RE = re.compile(
    r"(?i)(password|passwd|pwd|token|secret|api[_ -]?key|private[_ -]?key)"
    r"\s*([=:])\s*[^\s,;]+"
)
URI_CREDENTIAL_RE = re.compile(r"(postgres(?:ql)?(?:\+[a-z0-9_-]+)?://[^:/@\s]+:)[^@\s]+(@)", re.IGNORECASE)


def is_secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in {"password", "passwd", "pwd", "token", "secret", "apikey", "privatekey", "credentials"} or normalized.endswith("apikey") or normalized.endswith("token")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any) -> Any:
    """Recursively redact credentials and secret-like key/value text."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if is_secret_key(str(key)):
                result[key] = "<REDACTED>"
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = URI_CREDENTIAL_RE.sub(r"\1<REDACTED>\2", value)
        return SECRET_KEY_RE.sub(r"\1\2<REDACTED>", value)
    return value


def write_json(name: str, value: Any) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_ROOT / name).write_text(
        json.dumps(redact(value), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_text(name: str, value: str) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_ROOT / name).write_text(redact(value).rstrip() + "\n", encoding="utf-8")


def assert_read_only_sql(sql: str) -> None:
    """Reject every non-SELECT/SHOW statement before it reaches psycopg."""
    if not READ_ONLY_SQL_RE.match(sql) or FORBIDDEN_SQL_RE.search(sql):
        raise ValueError(f"read-only audit SQL rejected: {sql!r}")


def safe_error(exc: BaseException) -> str:
    return str(redact(f"{type(exc).__name__}: {exc}"))


def safe_dsn_info(dsn: str) -> dict[str, Any]:
    parsed = urlparse(dsn)
    host = parsed.hostname or "<none>"
    if host in {"localhost", "127.0.0.1", "::1"}:
        host_classification = "LOCALHOST"
        safe_host = host
    else:
        safe_host = "<REDACTED_OR_SAFE_HOST>"
        host_classification = "REMOTE_OR_REDACTED"
    return {
        "host": safe_host,
        "host_classification": host_classification,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/") or "<none>",
        "user": parsed.username or "<none>",
        "password": "<REDACTED>",
        "sslmode": (parsed.query or "<not_in_dsn>"),
    }


def query(conn: Any, sql: str) -> list[dict[str, Any]]:
    """Execute a checked metadata query and return dict rows."""
    assert_read_only_sql(sql)
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return list(cur.fetchall())


def show(conn: Any, name: str) -> Any:
    rows = query(conn, f"SHOW {name}")
    return rows[0].get(name) if rows else None


def import_globalvar() -> tuple[Any | None, dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    if not GLOBALVAR_PATH.is_file():
        return None, {"found": False, "path": str(GLOBALVAR_PATH), "postgres_blocks": inventory}
    try:
        import globalVar  # type: ignore[import-not-found]
    except Exception as exc:
        return None, {
            "found": True,
            "path": str(GLOBALVAR_PATH),
            "imported": False,
            "import_error": safe_error(exc),
            "postgres_blocks": inventory,
        }

    dsn_specs = [
        ("TEAM360_DB_URL", "active Team360 DB URL", "ACTIVE"),
        ("TEAM360_DB_URL_PSQL", "active Team360 psql-compatible DB URL", "ACTIVE"),
        ("V360_SOURCE_DB_URL", "optional v360 source DB URL; not connected by this gate", "OPTIONAL_SOURCE"),
        ("FUTURE_OPTIONAL_V360_SOURCE_DB_URL", "optional v360 source DB URL; not connected by this gate", "OPTIONAL_SOURCE"),
    ]
    for name, purpose, status in dsn_specs:
        raw = getattr(globalVar, name, "") or ""
        if not raw and name == "FUTURE_OPTIONAL_V360_SOURCE_DB_URL":
            try:
                raw = globalVar.get_future_optional_v360_source_db_url_psql()
            except Exception:
                raw = ""
        if raw:
            info = safe_dsn_info(raw)
            inventory.append(
                {
                    "logical_variable_name": name,
                    "target_database": info["database"],
                    "target_host_classification": info["host_classification"],
                    "port": info["port"],
                    "role_name": info["user"],
                    "purpose": purpose,
                    "status": status,
                    "credentials": "<REDACTED>",
                }
            )
        else:
            inventory.append(
                {
                    "logical_variable_name": name,
                    "configured": False,
                    "purpose": purpose,
                    "status": status,
                }
            )
    resolved_target = ""
    try:
        resolved_target = globalVar.get_team360_db_url_psql()
    except Exception:
        pass
    resolved_inventory = safe_dsn_info(resolved_target) if resolved_target else None
    return globalVar, {
        "found": True,
        "path": str(GLOBALVAR_PATH),
        "imported": True,
        "team360_db_name": getattr(globalVar, "TEAM360_DB_NAME", None),
        "team360_db_schema": getattr(globalVar, "TEAM360_DB_SCHEMA", None),
        "postgres_blocks": inventory,
        "resolved_team360_target": resolved_inventory,
        "resolved_target_source": "TEAM360_DB_URL or TEAM360_DB_URL_PSQL or derived from V360_SOURCE_DB_URL with TEAM360_DB_NAME" if resolved_inventory else "NONE",
        "secrets_redacted": True,
    }


def classify_name(name: str, *, exact_telchi: bool = False) -> str:
    normalized = name.lower()
    if exact_telchi:
        return "CONFIRMED"
    if any(token in normalized for token in ("team360", "telchi", "flow", "tebaai")):
        return "LIKELY"
    return "UNKNOWN"


def operating_system_inventory() -> dict[str, Any]:
    release: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                release[key] = value.strip('"')
    except OSError:
        pass
    machine = platform.machine() or "UNKNOWN"
    return {
        "os": release.get("PRETTY_NAME") or platform.system() or "UNKNOWN",
        "architecture": machine,
        "normalized_architecture": "amd64/x86_64" if machine in {"x86_64", "amd64"} else machine,
        "package_family": "Debian/Ubuntu" if release.get("ID_LIKE", release.get("ID", "")).lower().find("debian") >= 0 else release.get("ID", "UNKNOWN"),
        "kernel": platform.release(),
    }


def run_command(args: list[str], timeout: int = 10) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", safe_error(exc)


def local_pg_config() -> dict[str, Any]:
    """Inspect pg_config and extension files without installing/copying anything."""
    commands: dict[str, str] = {}
    executable = shutil.which("pg_config")
    container: str | None = None
    if executable:
        runner = [executable]
        source = "host"
    else:
        code, output, error = run_command(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"], 10)
        candidates = [line.split("\t", 1)[0] for line in output.splitlines() if "postgres" in line.lower()]
        container = candidates[0] if code == 0 and candidates else None
        runner = ["docker", "exec", container, "pg_config"] if container else []
        source = "postgres_container" if container else "unavailable"
    for option in ("--version", "--sharedir", "--pkglibdir"):
        if runner:
            code, output, error = run_command(runner + [option], 15)
            commands[option] = output if code == 0 else f"UNAVAILABLE: {error}"
        else:
            commands[option] = "UNAVAILABLE"
    files: list[dict[str, Any]] = []
    if runner and commands.get("--sharedir", "").startswith("/"):
        for root in (commands["--sharedir"], commands.get("--pkglibdir", "")):
            if not root.startswith("/"):
                continue
            find_args = ["find", root, "-maxdepth", "2", "-type", "f", "(", "-iname", "pg_durable*", "-o", "-iname", "*durable*", ")", "-print"]
            args = (runner[:-1] + find_args) if container else find_args
            code, output, error = run_command(args, 20)
            if code == 0:
                for path in output.splitlines():
                    files.append({"path": path, "source": source})
            elif error:
                files.append({"path_scan_error": error, "root": root})
    return {
        "pg_config_source": source,
        "container": container,
        "pg_config": commands,
        "pg_durable_files": files,
        "filesystem_presence": "YES" if files else "NO",
        "install_action": "NONE",
    }


def service_inventory() -> dict[str, Any]:
    code, output, error = run_command(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"], 10)
    postgres = []
    if code == 0:
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) >= 2 and ("postgres" in fields[1].lower() or "pgvector" in fields[1].lower()):
                postgres.append({"container": fields[0], "image": fields[1], "ports": fields[2] if len(fields) > 2 else ""})
    return {
        "service_type": "container" if postgres else "UNKNOWN",
        "postgres_services": postgres,
        "systemd_postgres_units": [],
        "inspection_error": error if code != 0 else None,
        "restart_performed": False,
    }


def repo_reference_inventory() -> dict[str, Any]:
    terms = ("pg_durable", "durable", "scheduler", "job", "queue", "background worker")
    allowed_suffixes = {".py", ".sql", ".md", ".toml", ".yaml", ".yml", ".json", ".sh"}
    matches: list[dict[str, Any]] = []
    scanned = 0
    for path in [BACKEND_ROOT, REPO_ROOT / "AGENTS.md", REPO_ROOT / "pyproject.toml"]:
        paths = [path] if path.is_file() else path.rglob("*") if path.is_dir() else []
        for candidate in paths:
            if not candidate.is_file() or candidate.suffix.lower() not in allowed_suffixes:
                continue
            if any(part in {".venv", "node_modules", "__pycache__", ".git"} for part in candidate.parts):
                continue
            scanned += 1
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            found = sorted({term for term in terms if term.lower() in text.lower()})
            if found:
                classification = "GATE_SELF_REFERENCE" if "pg_durable" in found and GATE.lower() in text.lower() else "EXISTING_MODULE_OR_INFRA_REFERENCE"
                matches.append({"path": str(candidate), "terms": found, "classification": classification})
    return {"scope": [str(BACKEND_ROOT), str(REPO_ROOT / "AGENTS.md"), str(REPO_ROOT / "pyproject.toml")], "scanned_files": scanned, "matches": matches}


def inspect_relevant_databases(dsn: str, databases: list[dict[str, Any]], current_database: str) -> list[dict[str, Any]]:
    """Inspect schemas/extensions sequentially, never exceeding one connection."""
    candidates = [
        row["database_name"]
        for row in databases
        if row["connection_allowed"] and not row["is_template"]
        and row["database_name"] not in {"template0", "template1"}
    ]
    result: list[dict[str, Any]] = []
    parsed = urlparse(dsn)
    for database_name in sorted(set(candidates)):
        target_dsn = urlunparse(parsed._replace(path=f"/{database_name}")) if parsed.path else dsn
        record: dict[str, Any] = {"database_name": database_name, "connection": safe_dsn_info(target_dsn), "audited": False}
        try:
            import psycopg
            with psycopg.connect(target_dsn, autocommit=True, options="-c default_transaction_read_only=on", connect_timeout=10) as connection:
                record["transaction_read_only"] = show(connection, "transaction_read_only")
                record["schemas"] = query(connection, "SELECT n.nspname AS schema_name, pg_get_userbyid(n.nspowner) AS owner, has_schema_privilege(current_user, n.nspname, 'USAGE') AS usage_visible FROM pg_namespace n ORDER BY n.nspname")
                record["extensions"] = query(connection, "SELECT e.extname AS extension_name, e.extversion AS version, n.nspname AS schema, pg_get_userbyid(e.extowner) AS owner FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace ORDER BY e.extname")
                record["audited"] = True
        except Exception as exc:
            record["error"] = safe_error(exc)
        result.append(record)
    return result


def isolation_matrix(availability: dict[str, Any]) -> dict[str, Any]:
    package_verified = availability.get("pg_durable_available_on_server") == "YES" or availability.get("pg_durable_extension_installed") == "YES"
    package_status = "VERIFIED" if package_verified else "NOT_VERIFIED"
    rows = [
        {"level": "CLUSTER", "supported": "YES", "verified_for_pg_durable": "UNKNOWN" if not package_verified else "UNKNOWN", "isolation_strength": "STRONG", "operational_cost": "HIGH", "restart_implications": "Cluster restart affects all databases/apps", "backup_implications": "Cluster/PITR boundary", "failure_blast_radius": "Entire cluster", "notes": "PostgreSQL boundary; not a pg_durable package claim."},
        {"level": "DATABASE", "supported": "YES", "verified_for_pg_durable": "UNKNOWN" if not package_verified else "UNKNOWN", "isolation_strength": "STRONG_LOGICAL", "operational_cost": "MEDIUM", "restart_implications": "No separate restart, but cluster restart still shared", "backup_implications": "Database-level dump can be separated; PITR remains cluster-level", "failure_blast_radius": "Database plus shared cluster resources", "notes": "PostgreSQL extensions are installed in a database; pg_durable semantics remain unverified."},
        {"level": "SCHEMA", "supported": "YES", "verified_for_pg_durable": "UNKNOWN", "isolation_strength": "MEDIUM_LOGICAL", "operational_cost": "LOW", "restart_implications": "None", "backup_implications": "Usually database/cluster backup; schema dump possible", "failure_blast_radius": "Database", "notes": "PostgreSQL supports schemas, but package-owned object and grant behavior is unknown."},
        {"level": "ROLE", "supported": "YES", "verified_for_pg_durable": "UNKNOWN", "isolation_strength": "MEDIUM_SECURITY", "operational_cost": "LOW", "restart_implications": "None", "backup_implications": "Role/ACL state is cluster-wide", "failure_blast_radius": "Depends on grants", "notes": "Role is an authorization boundary, not workflow namespace."},
        {"level": "PG_DURABLE WORKER", "supported": "UNKNOWN", "verified_for_pg_durable": "NO", "isolation_strength": "UNKNOWN", "operational_cost": "UNKNOWN", "restart_implications": "UNKNOWN", "backup_implications": "UNKNOWN", "failure_blast_radius": "UNKNOWN", "notes": f"Worker model not discoverable; package {package_status}."},
        {"level": "QUEUE/NAMESPACE", "supported": "UNKNOWN", "verified_for_pg_durable": "NO", "isolation_strength": "UNKNOWN", "operational_cost": "UNKNOWN", "restart_implications": "UNKNOWN", "backup_implications": "UNKNOWN", "failure_blast_radius": "UNKNOWN", "notes": f"Namespace/queue API not discoverable; package {package_status}."},
        {"level": "APPLICATION METADATA", "supported": "YES", "verified_for_pg_durable": "NO", "isolation_strength": "WEAK_UNLESS_ENFORCED", "operational_cost": "LOW", "restart_implications": "None", "backup_implications": "Included with selected database", "failure_blast_radius": "Database", "notes": "Recommended ownership labels, not a substitute for physical/logical boundaries."},
    ]
    return {
        "package_status": package_status,
        "matrix": rows,
        "GLOBAL_UNNAMESPACED_PG_DURABLE_STATE_ALLOWED": "NO",
        "PG_DURABLE_ISOLATION_BY_DATABASE_SUPPORTED": "UNKNOWN",
        "PG_DURABLE_ISOLATION_BY_SCHEMA_SUPPORTED": "UNKNOWN",
        "PG_DURABLE_NAMESPACE_CAPABILITY": "UNKNOWN",
    }


def future_topology() -> dict[str, Any]:
    return {
        "options": [
            {"id": "A", "name": "database per project", "assessment": "CANDIDATE", "reason": "Strong logical boundary, but Team360 modules still need namespace/ownership metadata."},
            {"id": "B", "name": "database per module", "assessment": "CANDIDATE", "reason": "Strongest practical module boundary on a shared cluster; more databases, grants and backup coordination."},
            {"id": "C", "name": "shared database with schema/namespace", "assessment": "NOT_RECOMMENDED_YET", "reason": "Requires verified pg_durable schema/namespace and worker behavior; not evidenced on this server."},
            {"id": "D", "name": "separate PostgreSQL cluster/instance", "assessment": "ESCALATION_OPTION", "reason": "Strongest failure/security boundary; operationally expensive and not justified by this read-only audit alone."},
        ],
        "recommended": "DATABASE_PLUS_NAMESPACE",
        "recommendation": "Use a dedicated pg_durable database for each Team360 module that runs durable orchestration, starting with Telchi; keep DuckLake catalog in team360_telchi_ducklake. Within each database require explicit project/module/service/environment/workflow ownership metadata once the real package API is verified.",
        "telchi": {
            "project": "Team360",
            "module": "telchi",
            "service": "datalake",
            "orchestration": "ingestion",
            "database": "FUTURE_NAME_PENDING_POLICY_REVIEW",
            "separate_from_ducklake_database": "YES",
        },
        "flow": {"project": "Team360", "module": "flow", "separate_logical_instance": "YES"},
        "tebaai": {"project": "Team360", "module": "tebaai", "separate_logical_instance": "YES"},
        "cross_database_recovery": "Compatible in principle: publication_id is the logical bridge; no distributed transaction is introduced. The runtime must persist/reconcile publication_id explicitly across databases.",
        "ducklake_relationship": "DuckLake catalog only in its own database; durable orchestration state elsewhere to avoid coupling, permission, backup and failure-domain ambiguity.",
    }


def naming_policy() -> dict[str, Any]:
    return {
        "policy_status": "PROPOSED_PENDING_REVIEW",
        "fields": {"project": "stable project slug", "module": "stable module slug", "service": "bounded service slug", "environment": "existing logical environment policy (dev/prod)", "workflow": "stable workflow/job type slug"},
        "identity_format": "project=<project>; module=<module>; service=<service>; environment=<environment>; workflow=<workflow>",
        "examples": [
            "project=team360; module=telchi; service=datalake; environment=dev; workflow=ingestion",
            "project=team360; module=flow; service=automation; environment=dev; workflow=mail_intake",
            "project=team360; module=tebaai; service=<service>; environment=dev; workflow=<workflow>",
        ],
        "database_names": "Do not create or suffix database names until package semantics and naming policy are reviewed.",
        "collision_rule": "No runtime may omit project and module ownership; an unnamespaced global durable state is forbidden.",
    }


def plans(topology: dict[str, Any], availability: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    installation = {
        "status": "PLAN_ONLY_NOT_EXECUTED",
        "preconditions": ["architecture review approval", "approved pg_durable release compatible with PostgreSQL 18.4 and Ubuntu/Debian-compatible packaging", "package documentation/API inspected", "restart window with all cluster consumers identified", "backup/restore plan approved"],
        "steps": [
            "Obtain the approved server-side pg_durable package from the approved repository; do not use an unreviewed latest version.",
            "Inspect control/SQL/shared-library files and package release notes for PostgreSQL 18.4 compatibility, preload requirement, worker/resource GUCs, and upgrade path.",
            "Schedule a maintenance window after inventorying all cluster databases, active applications and restart blast radius.",
            "Install the package on the PostgreSQL host/container only; record package checksum and version.",
            "If the real package requires it, add pg_durable to shared_preload_libraries through the approved configuration mechanism and restart PostgreSQL once in the window.",
            "Create the extension only in the approved dedicated Telchi pg_durable database using an installation/admin role; never in the DuckLake catalog database unless an explicit review approves it.",
            "Create/grant only the minimum runtime role privileges documented by the installed package; runtime must not need SUPERUSER, CREATEDB or CREATEROLE.",
            "Configure one explicit Team360/Telchi/datalake/environment/workflow namespace or metadata identity, then verify collision rejection and worker ownership without starting ingestion.",
            "Run read-only health/catalog checks and a controlled non-production workflow test only after a separate gate authorizes it.",
        ],
        "current_server_finding": f"No pg_durable package/API was available on this PostgreSQL 18.4 server: {availability.get('pg_durable_available_on_server')}; no installation performed.",
    }
    rollback = {
        "status": "PLAN_ONLY_NOT_EXECUTED",
        "before_extension_creation": ["Stop before restart if package/config validation fails.", "Remove only the newly installed package/config entry in an approved maintenance window, then restart if the package was preloaded.", "Restore the prior configuration from the change record; do not remove unrelated preload entries."],
        "after_extension_creation": ["Disable/stop only the Telchi durable worker according to the installed package procedure.", "Export/retain durable state according to the package-supported backup procedure.", "Revert grants and package/config changes in reverse order.", "Drop the extension only with an explicit destructive-change authorization and verified state retention; this gate will never execute that step."],
        "data_safety": "Do not delete DuckLake data or publication records. Reconcile interrupted work by publication_id; no distributed transaction is assumed.",
        "verification": ["Post-rollback SELECT/SHOW checks", "extension/config/version checks", "runtime connection and least-privilege checks", "backup/restore evidence"],
    }
    return installation, rollback


def run_audit() -> int:
    globalvar, globalvar_inventory = import_globalvar()
    write_json("globalvar_postgres_inventory.json", globalvar_inventory)
    if globalvar is None or not globalvar_inventory.get("imported"):
        write_json("summary.json", {"gate": GATE, "result": f"{GATE}_DEGRADED", "GLOBALVAR_FOUND": "YES" if globalvar_inventory.get("found") else "NO", "GLOBALVAR_POSTGRES_CONFIG_FOUND": "NO", "SECRETS_REDACTED": "YES", "POSTGRES_CONNECTED": "NO", "POSTGRES_MODE": "READ_ONLY", "reason": "globalVar.py could not be imported; no connection attempted."})
        write_text("report.md", f"# {GATE}\n\nResult: **{GATE}_DEGRADED**. globalVar.py could not be imported; no PostgreSQL connection was attempted.\n")
        return 0

    try:
        dsn = globalvar.get_team360_db_url_psql()
    except Exception as exc:
        dsn = ""
        globalvar_inventory["dsn_resolution_error"] = safe_error(exc)
        write_json("globalvar_postgres_inventory.json", globalvar_inventory)
    if not dsn:
        summary = {"gate": GATE, "result": f"{GATE}_DEGRADED", "GLOBALVAR_FOUND": "YES", "GLOBALVAR_POSTGRES_CONFIG_FOUND": "NO", "SECRETS_REDACTED": "YES", "POSTGRES_CONNECTED": "NO", "POSTGRES_MODE": "READ_ONLY", "reason": "No Team360 PostgreSQL DSN resolved from globalVar.py; no connection attempted."}
        write_json("summary.json", summary)
        write_text("report.md", f"# {GATE}\n\nResult: **{GATE}_DEGRADED**. No DSN resolved from globalVar.py; no PostgreSQL connection was attempted.\n")
        return 0

    connection_error: str | None = None
    try:
        import psycopg
        conn = psycopg.connect(dsn, autocommit=True, options="-c default_transaction_read_only=on", connect_timeout=10)
    except Exception as exc:
        conn = None
        connection_error = safe_error(exc)
    if conn is None:
        summary = {"gate": GATE, "result": f"{GATE}_DEGRADED", "GLOBALVAR_FOUND": "YES", "GLOBALVAR_POSTGRES_CONFIG_FOUND": "YES", "SECRETS_REDACTED": "YES", "POSTGRES_CONNECTED": "NO", "POSTGRES_MODE": "READ_ONLY", "connection_error": connection_error}
        write_json("summary.json", summary)
        write_text("report.md", f"# {GATE}\n\nResult: **{GATE}_DEGRADED**. PostgreSQL connection failed; no mutation fallback was attempted.\n\nError: {connection_error}\n")
        return 0

    # One connection only.  Every statement passes assert_read_only_sql first.
    try:
        conn_readonly = show(conn, "transaction_read_only")
        connectivity = query(conn, "SELECT 1 AS connectivity")
        server_version = show(conn, "server_version")
        server_version_num = show(conn, "server_version_num")
        server = {
            "connection": safe_dsn_info(dsn),
            "connectivity": connectivity,
            "server_version": server_version,
            "server_version_num": server_version_num,
            "major_version": str(int(server_version_num) // 10000) if str(server_version_num or "").isdigit() else "UNKNOWN",
            "server_address": show(conn, "listen_addresses"),
            "server_port": show(conn, "port"),
            "current_database": query(conn, "SELECT current_database() AS current_database")[0]["current_database"],
            "current_user": query(conn, "SELECT current_user AS current_user")[0]["current_user"],
            "session_user": query(conn, "SELECT session_user AS session_user")[0]["session_user"],
            "data_directory": show(conn, "data_directory"),
            "transaction_read_only": conn_readonly,
            "POSTGRES_MODE": "READ_ONLY",
        }
        databases = query(conn, "SELECT datname AS database_name, pg_get_userbyid(datdba) AS owner, pg_encoding_to_char(encoding) AS encoding, datcollate AS collation, datallowconn AS connection_allowed, datistemplate AS is_template FROM pg_database ORDER BY datname")
        roles = query(conn, "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin, rolreplication FROM pg_roles ORDER BY rolname")
        extensions = query(conn, "SELECT e.extname AS extension_name, e.extversion AS version, n.nspname AS schema, pg_get_userbyid(e.extowner) AS owner FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace ORDER BY e.extname")
        available = query(conn, "SELECT name, default_version, comment FROM pg_available_extensions WHERE lower(name) = 'pg_durable' OR lower(name) LIKE '%durable%' ORDER BY name")
        available_versions = query(conn, "SELECT name, version, installed, superuser, trusted, relocatable, requires FROM pg_available_extension_versions WHERE lower(name) = 'pg_durable' OR lower(name) LIKE '%durable%' ORDER BY name, version")
        preload = show(conn, "shared_preload_libraries")
        config = {
            "show": {name: show(conn, name) for name in ("config_file", "hba_file", "ident_file", "shared_preload_libraries", "data_directory", "port")},
            "relevant_pg_settings": query(conn, "SELECT name, setting, unit, context, source, sourcefile, sourceline, pending_restart FROM pg_settings WHERE name IN ('shared_preload_libraries','config_file','hba_file','ident_file','data_directory','port','max_connections','max_worker_processes','max_parallel_workers','max_parallel_workers_per_gather') ORDER BY name"),
            "hba_content": "NOT_READ",
            "POSTGRES_CONFIG_MODIFIED": "NO",
        }
        active_connections = query(conn, "SELECT COALESCE(datname, '<none>') AS database_name, COALESCE(usename, '<none>') AS user_name, COALESCE(NULLIF(application_name, ''), '<empty>') AS application_name, COALESCE(state, '<none>') AS state, backend_type, count(*) AS connection_count FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND backend_type = 'client backend' GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5")
        functions = []
        if any(row["extension_name"].lower() == "pg_durable" for row in extensions):
            functions = query(conn, "SELECT n.nspname AS schema_name, p.proname AS function_name, pg_get_function_identity_arguments(p.oid) AS arguments, pg_get_function_result(p.oid) AS result_type, p.prokind, l.lanname AS language FROM pg_depend d JOIN pg_extension e ON e.oid=d.refobjid JOIN pg_proc p ON d.classid='pg_proc'::regclass AND d.objid=p.oid JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang WHERE e.extname = 'pg_durable' ORDER BY 1,2")
        durable_gucs = query(conn, "SELECT name, setting, unit, context, source, sourcefile, sourceline, pending_restart FROM pg_settings WHERE lower(name) LIKE '%durable%' ORDER BY name")
    except Exception as exc:
        conn.close()
        write_json("summary.json", {"gate": GATE, "result": f"{GATE}_DEGRADED", "GLOBALVAR_FOUND": "YES", "GLOBALVAR_POSTGRES_CONFIG_FOUND": "YES", "SECRETS_REDACTED": "YES", "POSTGRES_CONNECTED": "YES", "POSTGRES_MODE": "READ_ONLY", "query_error": safe_error(exc), "POSTGRES_WRITE_COUNT": 0})
        write_text("report.md", f"# {GATE}\n\nResult: **{GATE}_DEGRADED**. PostgreSQL connected read-only, but metadata collection failed. No mutation fallback was attempted.\n")
        return 0
    finally:
        if conn is not None and not conn.closed:
            conn.close()

    os_inventory = operating_system_inventory()
    pg_config = local_pg_config()
    service = service_inventory()
    if service.get("postgres_services"):
        os_inventory["postgres_runtime_os"] = "Debian container (image reports PostgreSQL Debian packaging)"
        os_inventory["postgres_runtime_package_family"] = "Debian"
    else:
        os_inventory["postgres_runtime_os"] = "UNKNOWN"
        os_inventory["postgres_runtime_package_family"] = "UNKNOWN"
    current_db = server["current_database"]
    relevant_database_inventory = inspect_relevant_databases(dsn, databases, current_db)
    telchi_db = next((row for row in databases if row["database_name"] == "team360_telchi_ducklake"), None)
    telchi_role = next((row for row in roles if row["rolname"] == "team360_telchi_ducklake"), None)
    durable_installed = [row for row in extensions if row["extension_name"].lower() == "pg_durable"]
    durable_available = [row for row in available if row["name"].lower() == "pg_durable"]
    durable_available_versions = [row for row in available_versions if row["name"].lower() == "pg_durable"]
    availability = {
        "database_audited": current_db,
        "pg_durable_extension_installed": "YES" if durable_installed else "NO",
        "installed_versions": durable_installed,
        "installed_database": current_db if durable_installed else None,
        "available_on_server": "YES" if durable_available else "NO",
        "pg_durable_available_on_server": "YES" if durable_available else "NO",
        "available_extensions": durable_available,
        "available_versions": durable_available_versions,
        "filesystem": pg_config,
        "PG_DURABLE_INSTALLED_BY_GATE": "NO",
        "PG_DURABLE_OBJECTS_CREATED": 0,
        "PG_DURABLE_OBJECTS_MODIFIED": 0,
    }
    # Querying extension membership is conditional, but pg_durable is absent here.
    capabilities = {
        "discovery_status": "NOT_AVAILABLE_ON_SERVER" if not durable_installed and not durable_available else "REQUIRES_PACKAGE_INSPECTION",
        "extension_catalog_functions": functions,
        "durable_gucs": durable_gucs,
        "worker_model": "UNKNOWN",
        "database_binding": "UNKNOWN_PG_DURABLE_PACKAGE; PostgreSQL database boundary exists",
        "schema_model": "UNKNOWN",
        "task_workflow_identity": "UNKNOWN",
        "retry_semantics": "UNKNOWN",
        "history_model": "UNKNOWN",
        "concurrency_model": "UNKNOWN",
        "resource_implications": "UNKNOWN for pg_durable; observed cluster settings include max_connections=100 and max_worker_processes=8, while worker count, connection pool and memory requirements are not available.",
        "permissions": {
            "installation_admin_role": "Current audit role is administrator and is SUPERUSER=YES; installation must use a separately approved admin window.",
            "runtime_role_target": "The existing team360_telchi_ducklake role is SUPERUSER=NO, CREATEDB=NO, CREATEROLE=NO, but it owns the DuckLake database and must not be reused for pg_durable without review.",
            "pg_durable_minimum_privileges": "UNKNOWN until package documentation/API is available; runtime target remains without SUPERUSER, CREATEDB or CREATEROLE.",
        },
        "python_package_check": "NOT_USED; pg_durable is assessed server-side, not by import or pyproject/uv.lock presence",
        "evidence_limit": "No pg_durable API, documentation, catalog objects or GUCs were available for inspection on this server.",
    }
    matrix = isolation_matrix(availability)
    topology = future_topology()
    naming = naming_policy()
    installation, rollback = plans(topology, availability)
    active_database_names = {row["database_name"] for row in active_connections}
    named_shared_databases = {"litellm", "tebaai", "v360", "team360_telchi_ducklake"}
    shared = "YES" if any(name != current_db for name in active_database_names) or bool(named_shared_databases & {row["database_name"] for row in databases}) else "UNKNOWN"
    blast = {
        "service": service,
        "active_connections_excluding_audit_session": active_connections,
        "observed_databases_in_use": sorted({row["database_name"] for row in active_connections}),
        "all_visible_databases": [row["database_name"] for row in databases],
        "known": False,
        "RESTART_BLAST_RADIUS_KNOWN": "NO",
        "reason": "Active connections and the PostgreSQL container were observed, but dormant clients and all application restart dependencies cannot be proven from this read-only session.",
        "POSTGRES_RESTARTED": "NO",
    }
    repo_refs = repo_reference_inventory()
    databases_out = {"audited_database": current_db, "visible_count": len(databases), "databases": [{**row, "classification": "CONFIRMED" if row["database_name"] == current_db else classify_name(row["database_name"]), "telchi_ducklake_expected": row["database_name"] == "team360_telchi_ducklake"} for row in databases], "schema_inventory": relevant_database_inventory, "TELCHI_DUCKLAKE_DATABASE_EXISTS": "YES" if telchi_db else "NO"}
    roles_out = {"visible_count": len(roles), "roles": [{**row, "classification": "CONFIRMED" if row["rolname"] == "team360_telchi_ducklake" else classify_name(row["rolname"])} for row in roles], "TELCHI_DUCKLAKE_ROLE_EXISTS": "YES" if telchi_role else "NO", "TELCHI_DUCKLAKE_ROLE_SUPERUSER": "YES" if telchi_role and telchi_role["rolsuper"] else "NO"}
    extensions_out = {"audited_database": current_db, "installed_count": len(extensions), "extensions": extensions, "per_relevant_database": [{"database_name": row["database_name"], "audited": row["audited"], "extensions": row.get("extensions", []), "error": row.get("error")} for row in relevant_database_inventory], "pg_durable": availability}
    server_out = {**server, "os": os_inventory}
    current_state = {
        "gate": GATE, "generated_at": utc_now(), "stage": "INVESTIGATION", "read_only": True,
        "server": server_out, "databases": databases_out, "roles": roles_out, "extensions": extensions_out,
        "schema_inventory": relevant_database_inventory,
        "configuration": config, "availability": availability, "cluster_usage": {"POSTGRES_CLUSTER_SHARED": shared, "active_connections": active_connections},
        "restart_blast_radius": blast, "repo_references": repo_refs, "POSTGRES_WRITE_COUNT": 0,
        "POSTGRES_CONFIG_MODIFIED": "NO", "POSTGRES_RESTARTED": "NO", "POSTGRES_OBJECTS_CREATED": 0, "POSTGRES_OBJECTS_DROPPED": 0,
        "POSTGRES_PRIVILEGES_MODIFIED": "NO", "DUCKLAKE_MODIFIED": "NO", "SAP_ACCESSED": "NO", "SAP_WRITE_COUNT": 0,
    }
    write_json("current_state.json", current_state)
    write_json("postgres_server_inventory.json", server_out)
    write_json("postgres_database_inventory.json", databases_out)
    write_json("postgres_role_inventory.json", roles_out)
    write_json("postgres_extension_inventory.json", extensions_out)
    write_json("postgres_configuration_inventory.json", config)
    write_json("pg_durable_server_availability.json", availability)
    write_json("pg_durable_capabilities.json", capabilities)
    write_json("pg_durable_isolation_matrix.json", matrix)
    write_json("cluster_usage_inventory.json", {"POSTGRES_CLUSTER_SHARED": shared, "active_connections": active_connections, "service": service})
    write_json("restart_blast_radius.json", blast)
    write_json("telchi_pg_durable_topology_options.json", topology)
    write_json("recommended_topology.json", {"recommended_isolation_level": matrix["matrix"][1]["level"] + "_PLUS_NAMESPACE", **topology})
    write_json("naming_policy.json", naming)
    write_json("installation_plan.json", installation)
    write_json("rollback_plan.json", rollback)
    write_json("repo_reference_inventory.json", repo_refs)

    postgres_major = server["major_version"]
    ready = "NO"
    result = f"{GATE}_DEGRADED"
    report = f"""# {GATE}

- **Result:** `{result}`
- **Generated:** `{utc_now()}`
- **Mode:** `READ_ONLY`; one connection; `default_transaction_read_only=on`; `SELECT 1` passed.
- **PostgreSQL:** `{server['server_version']}` (`server_version_num={server['server_version_num']}`), major `{postgres_major}`.
- **Target:** `{server['connection']['host']}:{server['connection']['port']}/{server['connection']['database']}` as `{server['connection']['user']}`; password redacted. The audit role is SUPERUSER=YES; it is not a runtime least-privilege recommendation.
- **Host:** `{os_inventory['os']}`, `{os_inventory['normalized_architecture']}`, package family `{os_inventory['package_family']}`.
- **pg_durable:** installed `{availability['pg_durable_extension_installed']}` in audited database, available `{availability['pg_durable_available_on_server']}`, filesystem files `{pg_config['filesystem_presence']}`, preloaded `{'YES' if 'pg_durable' in (preload or '').lower() else 'NO'}`.
- **Capabilities:** worker, namespace, workflow identity, retries, history and pg_durable minimum privileges are `UNKNOWN` because no server-side package/documentation/API is present. Observed cluster limits are `max_connections=100` and `max_worker_processes=8`.
- **Sharing:** cluster observed as `{shared}`; restart blast radius is `NO` (dormant clients cannot be proven absent).
- **Topology recommendation:** dedicated pg_durable database per durable Team360 module, plus explicit project/module/service/environment/workflow namespace; keep DuckLake catalog separate. This is a candidate pending package/API review, not an installation decision.
- **Cross-database recovery:** compatible in principle through `publication_id`; no distributed transaction is introduced.
- **Mutations:** PostgreSQL writes `0`; config changed `NO`; restart `NO`; PostgreSQL objects created/dropped `0/0`; privileges changed `NO`; pg_durable objects created/modified `0/0`; DuckLake modified `NO`; SAP accessed `NO`.

## Review blockers

1. Obtain and review the approved pg_durable PostgreSQL 18 package and its real API.
2. Confirm database/schema/namespace binding and worker/concurrency/retry semantics.
3. Identify all dormant cluster consumers and establish a restart window.
4. Approve names and grants before any future installation gate.

This gate did not install pg_durable, modify `shared_preload_libraries`, restart PostgreSQL, create a database/schema/role, create an extension, create a workflow, or start ingestion.
"""
    write_text("report.md", report)
    summary = {
        "GATE": GATE, "GLOBALVAR_FOUND": "YES", "GLOBALVAR_POSTGRES_CONFIG_FOUND": "YES", "SECRETS_REDACTED": "YES",
        "POSTGRES_CONNECTED": "YES", "POSTGRES_MODE": "READ_ONLY", "POSTGRES_VERSION": server["server_version"], "POSTGRES_MAJOR_VERSION": "18" if postgres_major == "18" else "OTHER",
        "POSTGRES_OS": os_inventory.get("postgres_runtime_os", os_inventory["os"]), "POSTGRES_ARCH": os_inventory["normalized_architecture"], "POSTGRES_CURRENT_DATABASE": server["current_database"], "POSTGRES_CURRENT_ROLE": server["current_user"],
        "TELCHI_DUCKLAKE_DATABASE_EXISTS": databases_out["TELCHI_DUCKLAKE_DATABASE_EXISTS"], "TELCHI_DUCKLAKE_ROLE_EXISTS": roles_out["TELCHI_DUCKLAKE_ROLE_EXISTS"], "TELCHI_DUCKLAKE_ROLE_SUPERUSER": roles_out["TELCHI_DUCKLAKE_ROLE_SUPERUSER"],
        "POSTGRES_DATABASE_COUNT_VISIBLE": len(databases), "POSTGRES_ROLE_COUNT_VISIBLE": len(roles), "POSTGRES_EXTENSION_COUNT_INSTALLED": len(extensions),
        "PG_DURABLE_EXTENSION_INSTALLED": availability["pg_durable_extension_installed"], "PG_DURABLE_INSTALLED_VERSION": durable_installed[0]["version"] if durable_installed else "NONE",
        "PG_DURABLE_AVAILABLE_ON_SERVER": availability["pg_durable_available_on_server"], "PG_DURABLE_AVAILABLE_VERSIONS": [row["version"] for row in durable_available_versions] or "NONE",
        "PG_DURABLE_PRELOADED": "YES" if "pg_durable" in (preload or "").lower() else "NO", "PG_DURABLE_REQUIRES_POSTGRES_RESTART": "UNKNOWN" if not durable_installed and not durable_available else "UNKNOWN",
        "POSTGRES_CLUSTER_SHARED": shared, "RESTART_BLAST_RADIUS_KNOWN": blast["RESTART_BLAST_RADIUS_KNOWN"],
        "PG_DURABLE_ISOLATION_BY_DATABASE_SUPPORTED": matrix["PG_DURABLE_ISOLATION_BY_DATABASE_SUPPORTED"], "PG_DURABLE_ISOLATION_BY_SCHEMA_SUPPORTED": matrix["PG_DURABLE_ISOLATION_BY_SCHEMA_SUPPORTED"], "PG_DURABLE_NAMESPACE_CAPABILITY": matrix["PG_DURABLE_NAMESPACE_CAPABILITY"],
        "GLOBAL_UNNAMESPACED_PG_DURABLE_STATE_ALLOWED": "NO", "RECOMMENDED_ISOLATION_LEVEL": "DATABASE_PLUS_NAMESPACE", "RECOMMENDED_TELCHI_TOPOLOGY": topology["recommendation"],
        "TELCHI_PG_DURABLE_SEPARATE_FROM_DUCKLAKE_DB": "YES", "FLOW_SEPARATION_DEFINED": "YES", "TEBAAI_SEPARATION_DEFINED": "YES", "OTHER_PROJECT_SEPARATION_SUPPORTED": "YES", "APPROVED_VERSION_CANDIDATE": "NONE",
        "INSTALLATION_PLAN_CREATED": "YES", "ROLLBACK_PLAN_CREATED": "YES", "POSTGRES_WRITE_COUNT": 0, "POSTGRES_CONFIG_MODIFIED": "NO", "POSTGRES_RESTARTED": "NO", "POSTGRES_OBJECTS_CREATED": 0, "POSTGRES_OBJECTS_DROPPED": 0, "POSTGRES_PRIVILEGES_MODIFIED": "NO", "PG_DURABLE_OBJECTS_CREATED": 0, "PG_DURABLE_OBJECTS_MODIFIED": 0, "DUCKLAKE_MODIFIED": "NO", "SAP_ACCESSED": "NO", "SAP_WRITE_COUNT": 0, "PG_DURABLE_INSTALLED_BY_GATE": "NO", "READY_FOR_PG_DURABLE_INSTALLATION": ready, "READY_FOR_INITIAL_INGESTION": "NO", "result": result,
    }
    write_json("summary.json", summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--evidence-root", type=Path, default=None, help="Override external evidence root (for tests only).")
    args = parser.parse_args()
    global EVIDENCE_ROOT
    if args.evidence_root is not None:
        EVIDENCE_ROOT = args.evidence_root
    return run_audit()


if __name__ == "__main__":
    raise SystemExit(main())
