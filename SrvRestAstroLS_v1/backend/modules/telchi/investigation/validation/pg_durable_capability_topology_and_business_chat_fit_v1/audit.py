"""TEAM360_PG_DURABLE_UPSTREAM_CAPABILITY_TOPOLOGY_AND_BUSINESS_CHAT_FIT_V1.

This gate is read-only. It inspects an already downloaded upstream release and
package in /tmp, plus the prior PostgreSQL-18 read-only evidence. It never
installs the package, connects to PostgreSQL, changes configuration, or starts
a worker/workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATE = "TEAM360_PG_DURABLE_UPSTREAM_CAPABILITY_TOPOLOGY_AND_BUSINESS_CHAT_FIT_V1"
REPO_ROOT = Path(__file__).resolve().parents[7]
SOURCE_ROOT = Path("/tmp/team360-pg-durable-audit/src/pg_durable-0.2.8")
PACKAGE_PATH = Path("/tmp/team360-pg-durable-audit/pg-durable-postgresql-18_0.2.8-1_amd64.deb")
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
PRIOR_GATE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_PG_DURABLE_POSTGRES18_GLOBAL_READINESS_AND_ISOLATION_V1")

EXPECTED_PACKAGE_SHA256 = "090028f59b003613b150e61ccd5cdbebe70e69e65361913ad29b1f0b6af9e2bb"
EXPECTED_TARBALL_SHA256 = "3ae6186a4875000520caef2f4fdb568e9b1cbdb272b1a06d127256e890edc3cb"

SOURCE_FILES = {
    "README": "README.md",
    "USER_GUIDE": "USER_GUIDE.md",
    "API": "docs/api-reference.md",
    "HTTP_SECURITY": "docs/http-security.md",
    "MULTI_DATABASE": "docs/multi-database.md",
    "DSL": "src/dsl.rs",
    "LIB": "src/lib.rs",
    "TYPES": "src/types.rs",
    "WORKER": "src/worker.rs",
    "HTTP_ACTIVITY": "src/activities/execute_http.rs",
    "HTTP_PROBLEMS": "docs/http_problems.md",
    "GRAPH": "src/orchestrations/execute_function_graph.rs",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact(value: Any) -> Any:
    """Redact credential-shaped values while preserving assessment metadata keys."""
    if isinstance(value, dict):
        sensitive_keys = {"password", "passwd", "pwd", "api_key", "access_token", "private_key"}
        return {key: "<REDACTED>" if str(key).lower() in sensitive_keys else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(password|token|secret|api.?key)\s*[=:]\s*[^\s,;]+", r"\1=<REDACTED>", value)
        return re.sub(r"(postgres(?:ql)?://[^:/@\s]+:)[^@\s]+(@)", r"\1<REDACTED>\2", value)
    return value


def write_json(name: str, value: Any) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_ROOT / name).write_text(json.dumps(redact(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(name: str, value: str) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_ROOT / name).write_text(redact(value).rstrip() + "\n", encoding="utf-8")


def source_inventory(root: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for name, relative in SOURCE_FILES.items():
        path = root / relative
        files[name] = {"path": str(path), "exists": path.is_file(), "sha256": sha256(path), "relative": relative}
    return {"root": str(root), "files": files}


def source_text(root: Path, key: str) -> str:
    relative = SOURCE_FILES[key]
    path = root / relative
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def evidence_refs(root: Path, checks: dict[str, tuple[str, str]]) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    for check, (key, needle) in checks.items():
        text = source_text(root, key)
        lines = [number for number, line in enumerate(text.splitlines(), 1) if needle.lower() in line.lower()]
        refs[check] = {"source": SOURCE_FILES[key], "needle": needle, "matching_lines": lines[:20], "found": bool(lines)}
    return refs


def evaluate(root: Path = SOURCE_ROOT, package: Path = PACKAGE_PATH) -> dict[str, Any]:
    inv = source_inventory(root)
    package_hash = sha256(package)
    checks = evidence_refs(root, {
        "preload": ("LIB", "shared_preload_libraries"),
        "worker_registration": ("LIB", "register_background_worker"),
        "single_worker_database": ("USER_GUIDE", "only processes functions in **one** database"),
        "database_target_parameter": ("DSL", "database: default!(Option<&str>, \"NULL\")"),
        "cross_database_excluded": ("MULTI_DATABASE", "Cross-database functions"),
        "df_schema": ("LIB", "CREATE TABLE df.instances"),
        "rls": ("LIB", "ALTER TABLE df.instances ENABLE ROW LEVEL SECURITY"),
        "worker_superuser": ("LIB", "must be a superuser to bypass"),
        "no_generic_retry_policy": ("HTTP_PROBLEMS", "there is no `with_retry`"),
        "http_allowlist": ("HTTP_SECURITY", "http-allow-azure-domains"),
        "http_openai_azure": ("HTTP_SECURITY", ".openai.azure.com"),
        "secret_plaintext": ("USER_GUIDE", "df.vars.value"),
        "secret_history": ("USER_GUIDE", "Durable execution history"),
        "no_python": ("README", "arbitrary code"),
        "no_streaming": ("API", "Returns a JSON envelope"),
        "retention": ("USER_GUIDE", "pg_durable.retention_days"),
    })
    package_info = {
        "path": str(package),
        "exists": package.is_file(),
        "sha256": package_hash,
        "sha256_matches_expected": package_hash == EXPECTED_PACKAGE_SHA256,
        "expected_sha256": EXPECTED_PACKAGE_SHA256,
        "package_name": "pg-durable-postgresql-18",
        "package_version": "0.2.8-1",
        "architecture": "amd64",
        "depends": ["postgresql-18", "libssl3", "ca-certificates"],
        "inspection": "STATIC_ONLY; downloaded to /tmp; not installed",
    }
    stable = {
        "version": "0.2.8",
        "release_date": "2026-09-11",
        "release_url": "https://github.com/microsoft/pg_durable/releases/tag/v0.2.8",
        "repository_url": "https://github.com/microsoft/pg_durable",
        "source_scope": "tag v0.2.8 / downloaded source snapshot",
        "stable_only": True,
        "package": package_info,
        "tarball_sha256_observed": EXPECTED_TARBALL_SHA256,
        "official_build_feature": "http-allow-azure-domains",
        "postgres_major": 18,
    }
    topology = {
        "control_plane": {
            "extension_installation": "one approved database only",
            "worker_database": "pg_durable.database GUC; default postgres",
            "metadata_schemas": ["df", "duroxide or _duroxide provider schema"],
            "worker": "in-process PostgreSQL background worker",
            "namespace_api": "NO native project/module/service/environment namespace",
            "queue_api": "NO separate application queue/namespace API; duroxide internal store",
        },
        "database_binding": {
            "same_database_default": True,
            "target_database_parameter": "YES; df.start(database => ...) targets one database on same cluster",
            "one_invocation_spans_multiple_databases": False,
            "extension_installed_in_multiple_databases": False,
            "cross_database_alternative": "dblink/postgres_fdw inside SQL or separate durable functions; not a native graph boundary",
        },
        "isolation": {
            "rls": "YES for df.instances, df.nodes, df.vars",
            "execution_role": "submitted_by LOGIN role for SQL nodes",
            "worker_role": "must be SUPERUSER (source also warns BYPASSRLS; package validation is superuser-oriented)",
            "superuser_instances_default": "off",
            "module_isolation": "NO native boundary; application registry/authorization required",
            "failure_domain": "cluster/postmaster and control database; not module-isolated",
        },
        "resources": {
            "management_connections_default": 6,
            "duroxide_connections_default": 10,
            "user_execution_connections_default": 10,
            "new_transaction_start_connections_default": 2,
            "steady_pool_total_before_application_backends": 26,
            "restart_required_for_connection_gucs": True,
            "connection_budget_note": "per-user execution and backend client connections add to the cluster budget",
        },
        "backup_retention": {
            "terminal_retention_guc": "pg_durable.retention_days; default 30 days",
            "terminal_hard_cap": 10000,
            "logs_outside_database_retention": True,
            "chat_erasure_contract": "NO application-level conversation erasure or tenant retention contract identified",
        },
    }
    retry = {
        "generic_activity_retry_policy": "NO; no with_retry/max_attempts policy on schedule_activity in v0.2.8",
        "http_5xx": "activity returns error; workflow must explicitly model retry",
        "network_timeout": "activity fails; explicit workflow retry/backoff required",
        "available_control": "df.loop/df.sleep and explicit bounded counters can implement an application retry pattern",
        "internal_retries": "bounded graph-admission/transaction-visibility and worker connection retries are runtime internals, not business retry semantics",
        "idempotency": "df.start returns generated instance id; no caller idempotency key; bridge must deduplicate turn/job submission",
    }
    http = {
        "release_build": "restricted",
        "execution_identity": "background worker privileges; no user-specific URL allowlist",
        "allowed": ["HTTPS Azure approved suffixes", "api.github.com"],
        "azure_openai": "allowed only through *.openai.azure.com hostname and released feature policy",
        "generic_internal_litellm": "NO; internal host is not in the released allowlist",
        "direct_external_llm": "NO unless hosted behind an approved Azure endpoint",
        "ssrf": "IP blocklist, bare-IP rejection, DNS-safe resolver and redirects disabled",
        "secrets_in_http": "headers/body are workflow inputs; response/errors/history can retain sensitive values",
    }
    secrets = {
        "df_vars": "plaintext table value, owner-scoped by RLS but not encrypted",
        "start_snapshot": "all owned vars copied into FunctionInput / durable execution history",
        "substituted_values": "may appear in node inputs, SQL text, results, errors, WAL/backups and logs",
        "df_secrets": "NOT IMPLEMENTED in stable; docs/spec only and explicitly marked as future",
        "secret_manager": "NO native secret manager or runtime secret reference contract",
        "decision": "REJECT credentials/API keys/PII-bearing chat payloads as pg_durable vars or inline HTTP config",
    }
    chat_fit = [
        {"capability": "durable asynchronous turn/job state", "status": "PARTIAL_FIT", "reason": "df.start/status/result/signal/await and durable history exist; application state remains external"},
        {"capability": "conversation history and branching context", "status": "BRIDGE_REQUIRED", "reason": "no chat conversation/thread/message model; use Team360 PostgreSQL source of truth"},
        {"capability": "LLM invocation", "status": "BRIDGE_REQUIRED", "reason": "no Python/LLM adapter; released HTTP allowlist does not reach generic Team360 LiteLLM"},
        {"capability": "token streaming/SSE/resume", "status": "NO", "reason": "HTTP activity returns one completed JSON envelope; no client stream or offset protocol"},
        {"capability": "authorization before retrieval", "status": "BRIDGE_REQUIRED", "reason": "RLS is row ownership for df state, not Team360 domain/scope/capability authorization"},
        {"capability": "secret boundary", "status": "NO", "reason": "plaintext vars and durable history; no stable df.secrets"},
        {"capability": "bounded retries", "status": "BRIDGE_REQUIRED", "reason": "explicit workflow loop/backoff and idempotency needed; no generic policy"},
        {"capability": "Python/data-lake orchestration", "status": "NO_NATIVE", "reason": "SQL/HTTP-shaped runtime only; Python remains an application worker/bridge"},
        {"capability": "PII retention/deletion", "status": "INSUFFICIENT", "reason": "global retention and logs/backups are separate sinks; no chat erasure contract"},
    ]
    bridge_contract = {
        "role_of_pg_durable": "optional durable job/turn coordinator; never the chat source of truth",
        "opaque_payload_only": ["turn_id", "job_id", "publication_id", "workflow_type"],
        "conversation_source_of_truth": "Team360 PostgreSQL conversation/message tables with application authorization",
        "llm_execution": "Team360 application adapter/worker using the existing LiteLLM alias; not df.http() directly",
        "secret_execution": "private secret manager/config injected only into the application adapter; no df.vars or durable input",
        "retrieval_boundary": "identity -> capability/domain scope -> semantic plan -> filtered DuckLake/DuckDB query -> result",
        "streaming": "application event table/offset plus SSE or WebSocket; pg_durable status is not a token stream",
        "idempotency": "unique conversation_id + client_turn_id and durable run registry; reconcile uncertain df.start launches",
        "retry": "application-owned bounded retry policy with backoff, classification and idempotent side effects",
        "pii": "prompt, retrieved rows and answer remain outside df history; explicit retention/erasure policy required",
        "interactive_path": "do not put pg_durable in the synchronous token-stream path; use it for asynchronous ingestion/rebuild/long jobs",
    }
    topology_decision = {
        "shared_existing_postgres_cluster": "NOT_RECOMMENDED",
        "dedicated_durable_team360_cluster": "RECOMMENDED_CANDIDATE",
        "recommended_shape": "one dedicated PostgreSQL cluster/instance for Team360 durable runtime; one pg_durable control database; bridge-owned registry keyed by instance_id and publication/turn id",
        "module_namespace": "application-enforced in registry and authorization; not pg_durable-native",
        "telchi_ducklake_catalog": "keep team360_telchi_ducklake separate from pg_durable control database",
        "database_per_module": "DO NOT ASSUME; stable v0.2.8 does not provide multi-installation module isolation",
        "separate_cluster_per_module": "not required initially; consider only for stronger blast-radius/compliance isolation",
        "why": ["preload/restart affects all cluster consumers", "worker requires a superuser", "26 default pool connections before application backends", "no native module namespace", "logs/WAL/backups and global retention cross application boundaries"],
    }
    return {
        "gate": GATE,
        "generated_at": utc_now(),
        "stage": "INVESTIGATION",
        "mode": "READ_ONLY_STATIC_UPSTREAM_AUDIT",
        "source_inventory": inv,
        "source_evidence_refs": checks,
        "stable_release": stable,
        "topology": topology,
        "retry_semantics": retry,
        "http_security": http,
        "secret_boundary": secrets,
        "business_chat_fit": chat_fit,
        "business_chat_bridge_contract": bridge_contract,
        "topology_decision": topology_decision,
        "prior_server_state": {
            "evidence_path": str(PRIOR_GATE),
            "postgres_version": "18.4",
            "pg_durable_installed": "NO",
            "pg_durable_preloaded": "NO",
            "postgres_write_count": 0,
            "config_modified": "NO",
            "restart_performed": "NO",
            "source": "prior read-only gate; no new PostgreSQL connection in this gate",
        },
        "upstream_version_boundary": {
            "stable": "v0.2.8 only",
            "main_or_open_pr": "NOT USED AS STABLE EVIDENCE",
            "multi_database_pr": "PR #386 is open/unpublished and cannot approve DATABASE_PER_MODULE",
            "other_open_work": "PR #397 HTTP body handling is open/unpublished; not a stable capability",
        },
        "mutations": {
            "postgres_modified": "NO",
            "postgres_objects_created": 0,
            "postgres_config_modified": "NO",
            "postgres_restarted": "NO",
            "pg_durable_installed": "NO",
            "pg_durable_extension_created": "NO",
            "workflow_started": "NO",
            "sap_accessed": "NO",
            "sap_write_count": 0,
            "data_files_modified": 0,
        },
    }


def report(result: dict[str, Any]) -> str:
    stable = result["stable_release"]
    topo = result["topology_decision"]
    return f"""# {GATE}

- **Resultado:** `{GATE}_DEGRADED`
- **Etapa:** `INVESTIGATION`
- **Modo:** auditoría read-only estática del release estable `v{stable['version']}`; no se instaló el paquete ni se conectó a PostgreSQL en esta corrida.
- **Versión estable auditada:** `pg_durable v{stable['version']}`, publicada el `{stable['release_date']}`; paquete `pg-durable-postgresql-18_0.2.8-1_amd64.deb`, SHA-256 verificado en `/tmp`.
- **Compatibilidad:** paquete oficial para PostgreSQL 18 / amd64; exige preload y reinicio antes de que el background worker opere, seguido de `CREATE EXTENSION` en su database de control.

## Decisión ejecutiva

`pg_durable` **no debe instalarse en el PostgreSQL compartido actual**. La recomendación es un **cluster/instancia PostgreSQL dedicado para el runtime durable de Team360**, con una database de control de pg_durable y un registro/bridge de aplicación que imponga `project/module/service/environment/workflow` e idempotencia. `team360_telchi_ducklake` permanece separado como catálogo DuckLake. No se adopta `DATABASE_PER_MODULE`: la release estable no ofrece aislamiento nativo por módulo ni soporte aprobado para múltiples instalaciones; PR #386 queda fuera de la evidencia estable.

## Capacidades y límites encontrados

- Worker in-process de PostgreSQL y estado en `df.*` + schema interno `duroxide`/`_duroxide`; no hay namespace/queue API nativo para Team360.
- `df.start(database => ...)` puede dirigir **una invocación a una database del mismo cluster**, pero el workflow no cruza databases. La extensión/worker se liga a una sola database de control.
- RLS separa instancias, nodos y variables por rol; el worker debe ser `SUPERUSER`, y el SQL se conecta como `submitted_by`. Esto es aislamiento de usuario, no de módulo.
- El presupuesto predeterminado es `6` conexiones de management + `10` de duroxide + `10` de ejecución de usuario, antes de conexiones de aplicación; los cambios principales requieren reinicio.
- No existe política genérica `with_retry/max_attempts`; 5xx/timeouts fallan la activity. Los retries de negocio deben modelarse explícitamente con loops, backoff, límites e idempotencia.
- El build publicado restringe HTTP a HTTPS, dominios Azure aprobados y `api.github.com`; un endpoint interno genérico de LiteLLM no puede ser destino directo. Además, `df.http()` ejecuta con privilegios del background worker y no ofrece allowlist por usuario. Tampoco existe runtime Python.

## Secretos, PII y Business Chat

El límite de secretos es **insuficiente**: `df.vars` es plaintext, `df.start()` copia las variables a durable history y valores sustituidos pueden alcanzar inputs, resultados, errores, WAL/backups y logs. `df.secrets` aparece en documentos/spec como futuro, pero no está implementado en v0.2.8. No se deben guardar API keys, tokens ni PII conversacional allí.

Business Chat sólo tiene un **partial fit** como motor durable de jobs/turnos asíncronos. Requiere un bridge Team360 para autenticación/autorización antes de retrieval, conversación y mensajes canónicos, LLM/LiteLLM, secretos, deduplicación, retries, PII/retención y SSE/WebSocket. `df.http()` devuelve un envelope completo, no streaming ni resume de tokens.

| Área | Evaluación |
|---|---|
| Estado durable de job/turno | `PARTIAL_FIT` |
| Conversación/historia | `BRIDGE_REQUIRED` |
| LLM genérico/LiteLLM | `BRIDGE_REQUIRED` |
| SSE/token streaming | `NO` |
| Auth/scope antes de retrieval | `BRIDGE_REQUIRED` |
| Secretos | `NO` |
| Retry/idempotencia de negocio | `BRIDGE_REQUIRED` |
| Python/Data Lake | `NO_NATIVE` |
| PII retention/erasure | `INSUFFICIENT` |

## Gate y próximos pasos

Estado: **NO LISTO PARA INSTALACIÓN**. Antes de cualquier gate mutante se necesita: aprobar cluster dedicado, definir registry/bridge e identidad de módulo, diseñar secret manager y PII policy, fijar límites de conexiones/retención, y validar un smoke aislado con un endpoint autorizado sin secretos reales. La versión candidata queda fijada en `v{stable['version']}`; no se debe sustituir por `main`, PRs o tags flotantes.

PostgreSQL writes: `0`; config modified: `NO`; restart: `NO`; pg_durable installed/created: `NO/NO`; workflows started: `NO`; SAP writes: `0`.
"""


def run(root: Path = SOURCE_ROOT, package: Path = PACKAGE_PATH) -> dict[str, Any]:
    result = evaluate(root, package)
    write_json("release_inventory.json", result["stable_release"])
    write_json("source_inventory.json", result["source_inventory"])
    write_json("source_evidence_refs.json", result["source_evidence_refs"])
    write_json("pg_durable_topology_matrix.json", result["topology"])
    write_json("retry_semantics.json", result["retry_semantics"])
    write_json("http_security_fit.json", result["http_security"])
    write_json("secret_boundary_assessment.json", result["secret_boundary"])
    write_json("business_chat_fit_matrix.json", result["business_chat_fit"])
    write_json("business_chat_bridge_contract.json", result["business_chat_bridge_contract"])
    write_json("topology_decision.json", result["topology_decision"])
    write_json("current_state.json", result)
    summary = {
        "GATE": GATE,
        "RESULT": f"{GATE}_DEGRADED",
        "STAGE": "INVESTIGATION",
        "READ_ONLY": "YES",
        "STABLE_VERSION": "0.2.8",
        "PACKAGE_SHA256_VERIFIED": "YES" if result["stable_release"]["package"]["sha256_matches_expected"] else "NO",
        "PG18_PACKAGE": "YES",
        "NATIVE_MODULE_NAMESPACE": "NO",
        "NATIVE_PYTHON_RUNTIME": "NO",
        "GENERIC_RETRY_POLICY": "NO",
        "HTTP_GENERIC_LITELLM_ENDPOINT": "NO",
        "SECRET_BOUNDARY": "INSUFFICIENT",
        "BUSINESS_CHAT_FIT": "PARTIAL_WITH_BRIDGE_REQUIRED",
        "SHARED_POSTGRES_RECOMMENDATION": "NO",
        "DEDICATED_DURABLE_TEAM360_CLUSTER_RECOMMENDATION": "YES",
        "DATABASE_PER_MODULE": "NOT_APPROVED",
        "PG_DURABLE_INSTALLED_BY_GATE": "NO",
        "POSTGRES_MODIFIED": "NO",
        "POSTGRES_WRITE_COUNT": 0,
        "POSTGRES_RESTARTED": "NO",
        "SAP_ACCESSED": "NO",
        "SAP_WRITE_COUNT": 0,
        "READY_FOR_INSTALLATION": "NO",
        "READY_FOR_BUSINESS_CHAT": "NO_NATIVE; BRIDGE_DESIGN_REQUIRED",
    }
    write_json("summary.json", summary)
    write_text("report.md", report(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--package", type=Path, default=PACKAGE_PATH)
    parser.add_argument("--evidence-root", type=Path, default=None)
    args = parser.parse_args()
    global EVIDENCE_ROOT
    if args.evidence_root is not None:
        EVIDENCE_ROOT = args.evidence_root
    run(args.source_root, args.package)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
