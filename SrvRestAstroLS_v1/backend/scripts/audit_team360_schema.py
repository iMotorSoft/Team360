"""Audit script for Team360 PostgreSQL schema.

Compares the live database `team360` against expected tables, columns,
indexes, constraints and seeds from migrations 001, 002 v3, 003 and 004.

Also checks:
  - No 'bypassed' in approval_status check constraints
  - No suspicious keys in credential_references.metadata_jsonb
  - Cross-workspace consistency (basic)
  - Partial unique indexes existence and KSB semantic predicates via pg_index
  - knowledge_scope_bindings convention (nulabilidad, defaults)
  - pgvector extension and knowledge embedding persistence
  - automation diagnosis runtime persistence from migration 004
  - Seed presence for catalogs

Read-only. Never modifies the database.
Run: python -m backend.scripts.audit_team360_schema
"""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import urlsplit, urlunsplit
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Helper: normalize PostgreSQL predicate for tolerant semantic checks
# ---------------------------------------------------------------------------
def normalize_predicate(predicate: str | None) -> str:
    """Normalize PostgreSQL predicate text without depending on exact formatting."""
    if not predicate:
        return ""

    normalized = str(predicate).lower()
    normalized = re.sub(r"::[a-z_][a-z0-9_]*(?:\[\])?", "", normalized)
    normalized = normalized.replace('"', "")
    normalized = re.sub(r"^\s*where\s+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\(\s+", "(", normalized)
    normalized = re.sub(r"\s+\)", ")", normalized)
    return normalized.strip()


def predicate_has_is_default_true(predicate: str) -> bool:
    if re.search(r"\bis_default\s*=\s*true\b", predicate):
        return True
    if re.search(r"\bis_default\s+is\s+true\b", predicate):
        return True
    return bool(re.search(r"\bis_default\b", predicate)) and not re.search(
        r"\bis_default\s*(=|is)\s*false\b", predicate
    )


def predicate_binding_types(predicate: str) -> set[str]:
    known_types = {
        "internal",
        "workspace",
        "assistant_instance",
        "automation_package",
        "package_worker",
    }
    return set(re.findall(r"'([^']+)'", predicate)) & known_types


def predicate_matches_ksb_rule(index_name: str, predicate: str | None) -> bool:
    expected_types = KSB_DEFAULT_INDEX_RULES[index_name]
    normalized = normalize_predicate(predicate)
    if not predicate_has_is_default_true(normalized):
        return False

    return predicate_binding_types(normalized) == expected_types


# ---------------------------------------------------------------------------
# Expected schema definitions
# ---------------------------------------------------------------------------

MIGRATION_001_TABLES: dict[str, list[str]] = {
    "core_workspaces": [
        "id", "slug", "display_name", "timezone", "status",
        "metadata_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "core_users": [
        "id", "workspace_id", "email", "display_name", "role",
        "status", "metadata_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "core_events": [
        "id", "workspace_id", "actor_user_id", "event_name",
        "entity_type", "entity_id", "correlation_id", "payload_jsonb",
        "occurred_at_utc", "created_at_utc",
    ],
    "communication_providers": [
        "id", "code", "display_name", "provider_kind", "status",
        "capabilities_jsonb", "metadata_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "provider_credentials": [
        "id", "workspace_id", "provider_id", "credential_scope",
        "environment", "secret_ref", "public_config_jsonb", "status",
        "rotated_at_utc", "created_at_utc", "updated_at_utc",
    ],
    "communication_channels": [
        "id", "workspace_id", "provider_id", "channel_type",
        "channel_alias", "department", "display_name", "status",
        "current_whatsapp_number_id", "default_for_department",
        "metadata_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "whatsapp_numbers": [
        "id", "workspace_id", "provider_id", "channel_id",
        "credential_id", "phone_e164", "phone_display",
        "provider_phone_number_id", "provider_business_id",
        "phone_number_status", "verification_status",
        "activated_at_utc", "retired_at_utc", "replaced_by_number_id",
        "metadata_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "webhook_bindings": [
        "id", "workspace_id", "provider_id", "channel_id",
        "whatsapp_number_id", "webhook_url", "verify_token_ref",
        "signing_secret_ref", "provider_external_id", "status",
        "last_verified_at_utc", "metadata_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "channel_routing_rules": [
        "id", "workspace_id", "channel_id", "rule_type",
        "match_value", "priority", "status", "active_from_utc",
        "active_to_utc", "metadata_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "local_runners": [
        "id", "workspace_id", "runner_name", "runner_key_hash",
        "install_fingerprint", "status", "capabilities_jsonb",
        "version", "last_seen_at_utc", "created_at_utc", "updated_at_utc",
    ],
    "scheduled_tasks": [
        "id", "workspace_id", "task_key", "display_name",
        "schedule_kind", "schedule_expression", "timezone", "status",
        "target_channel_id", "required_runner_capability",
        "payload_jsonb", "next_run_at_utc", "last_run_at_utc",
        "created_at_utc", "updated_at_utc",
    ],
    "task_runs": [
        "id", "workspace_id", "scheduled_task_id", "runner_id",
        "workflow_run_id", "status", "lease_id", "lease_expires_at_utc",
        "idempotency_key", "attempt", "max_attempts",
        "scheduled_for_utc", "started_at_utc", "completed_at_utc",
        "failed_at_utc", "timeout_at_utc", "correlation_id",
        "input_jsonb", "result_jsonb", "error_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "runner_heartbeats": [
        "id", "workspace_id", "runner_id", "status",
        "observed_at_utc", "metrics_jsonb", "created_at_utc",
    ],
    "message_threads": [
        "id", "workspace_id", "channel_id", "current_whatsapp_number_id",
        "contact_identity", "subject", "current_status",
        "previous_thread_id", "last_message_at_utc", "metadata_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "message_events": [
        "id", "workspace_id", "thread_id", "channel_id",
        "whatsapp_number_id", "provider_id", "task_run_id",
        "provider_message_id", "direction", "event_type", "status",
        "contact_identity", "payload_jsonb", "occurred_at_utc",
        "correlation_id", "created_at_utc",
    ],
    "whatsapp_number_migration_history": [
        "id", "workspace_id", "channel_id", "old_whatsapp_number_id",
        "new_whatsapp_number_id", "migration_policy_jsonb",
        "migrated_by_user_id", "status", "started_at_utc",
        "completed_at_utc", "notes", "created_at_utc", "updated_at_utc",
    ],
    "llm_providers": [
        "id", "code", "display_name", "base_url", "auth_type",
        "status", "capabilities_jsonb", "metadata_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "llm_credentials": [
        "id", "workspace_id", "provider_id", "credential_scope",
        "environment", "secret_ref", "status", "created_by_user_id",
        "rotated_at_utc", "metadata_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "llm_model_profiles": [
        "id", "provider_id", "model_id", "display_name",
        "model_capabilities", "context_window",
        "input_cost_per_million", "output_cost_per_million",
        "currency", "latency_class", "status", "metadata_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "llm_fallback_policy": [
        "id", "workspace_id", "name", "ordered_model_profile_ids",
        "fallback_on_error_codes", "max_attempts", "cooldown_seconds",
        "status", "metadata_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "workspace_llm_settings": [
        "id", "workspace_id", "default_model_profile_id",
        "fallback_policy_id", "key_scope_preference",
        "monthly_budget_limit", "daily_budget_limit",
        "safety_policy_jsonb", "data_retention_policy", "status",
        "created_at_utc", "updated_at_utc",
    ],
    "automation_llm_policy": [
        "id", "workspace_id", "automation_key",
        "primary_model_profile_id", "fallback_policy_id",
        "credential_scope_preference", "max_tokens", "temperature",
        "timeout_ms", "retry_policy_jsonb", "status",
        "created_at_utc", "updated_at_utc",
    ],
    "llm_cost_estimates": [
        "id", "provider_id", "model_id", "currency",
        "input_cost_per_million", "output_cost_per_million",
        "effective_from_utc", "effective_to_utc", "created_at_utc",
    ],
    "llm_usage_logs": [
        "id", "workspace_id", "automation_key", "task_run_id",
        "workflow_run_id", "provider_id", "model_profile_id",
        "credential_scope", "prompt_tokens", "completion_tokens",
        "total_tokens", "estimated_cost", "currency", "latency_ms",
        "status", "error_code", "correlation_id", "metadata_jsonb",
        "created_at_utc",
    ],
}

MIGRATION_002_TABLES: dict[str, list[str]] = {
    "core_workspace_areas": [
        "id", "workspace_id", "area_code", "display_name",
        "description", "status", "created_at_utc", "updated_at_utc",
    ],
    "core_permissions": [
        "id", "permission_code", "display_name", "description",
        "category", "created_at_utc",
    ],
    "core_roles": [
        "id", "workspace_id", "role_code", "display_name",
        "description", "is_system_role", "status",
        "created_at_utc", "updated_at_utc",
    ],
    "core_role_permissions": [
        "id", "role_id", "permission_id", "created_at_utc",
    ],
    "core_permission_profiles": [
        "id", "workspace_id", "profile_code", "display_name",
        "description", "status", "created_at_utc", "updated_at_utc",
    ],
    "core_profile_permissions": [
        "id", "profile_id", "permission_id", "created_at_utc",
    ],
    "core_user_roles": [
        "id", "user_id", "role_id", "created_at_utc",
    ],
    "core_user_profiles": [
        "id", "user_id", "profile_id", "area_id", "created_at_utc",
    ],
    "package_plans": [
        "id", "plan_code", "display_name", "description",
        "sort_order", "status", "created_at_utc", "updated_at_utc",
    ],
    "package_features": [
        "id", "feature_code", "display_name", "description",
        "category", "status", "created_at_utc",
    ],
    "package_plan_features": [
        "id", "plan_id", "feature_id", "max_value",
        "metadata_jsonb", "created_at_utc",
    ],
    "workspace_plan_subscriptions": [
        "id", "workspace_id", "plan_id", "status",
        "started_at_utc", "ended_at_utc", "expires_at_utc",
        "metadata_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "assistant_instances": [
        "id", "workspace_id", "assistant_code", "assistant_type", "name", "status",
        "embed_config_jsonb", "public_config_jsonb",
        "default_knowledge_scope_id", "settings_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "automation_packages": [
        "id", "workspace_id", "assistant_instance_id",
        "package_code", "package_name", "plan_code", "status",
        "enabled_features_jsonb", "limits_jsonb", "settings_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "worker_definitions": [
        "id", "worker_code", "display_name", "description",
        "worker_kind", "default_mode", "capabilities_jsonb",
        "status", "created_at_utc", "updated_at_utc",
    ],
    "package_workers": [
        "id", "workspace_id", "automation_package_id",
        "worker_definition_id", "package_worker_code", "status",
        "mode", "knowledge_scope_id",
        "created_at_utc", "updated_at_utc",
    ],
    "package_worker_configs": [
        "id", "package_worker_id", "config_jsonb",
        "allowed_actions_jsonb", "blocked_actions_jsonb",
        "limits_jsonb", "requires_human_approval",
        "created_at_utc", "updated_at_utc",
    ],
    "credential_references": [
        "id", "workspace_id", "automation_package_id",
        "package_worker_id", "credential_type", "provider_code",
        "secret_ref", "status", "metadata_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "knowledge_scopes": [
        "id", "workspace_id", "scope_code", "name",
        "retrieval_mode", "graph_enabled", "settings_jsonb",
        "status", "created_at_utc", "updated_at_utc",
    ],
    "knowledge_scope_bindings": [
        "id", "knowledge_scope_id", "workspace_id", "binding_type",
        "bound_entity_id", "is_default", "metadata_jsonb",
        "created_at_utc",
    ],
    "knowledge_documents": [
        "id", "knowledge_scope_id", "source_type", "source_uri",
        "title", "content_hash", "metadata_jsonb", "status",
        "created_at_utc", "updated_at_utc",
    ],
    "knowledge_chunks": [
        "id", "knowledge_document_id", "chunk_index", "title",
        "content", "metadata_jsonb", "token_count",
        "embedding_status", "created_at_utc", "updated_at_utc",
    ],
}

MIGRATION_003_TABLES: dict[str, list[str]] = {
    "knowledge_embedding_models": [
        "embedding_model_id", "provider_code", "model_code", "model_alias",
        "dimension", "distance_metric", "status", "metadata_jsonb",
        "created_at_utc", "updated_at_utc",
    ],
    "knowledge_chunk_embeddings": [
        "chunk_embedding_id", "knowledge_chunk_id", "knowledge_scope_id",
        "embedding_model_id", "embedding", "embedding_status",
        "content_hash", "metadata_jsonb", "embedded_at_utc",
        "created_at_utc", "updated_at_utc",
    ],
}

MIGRATION_006_TABLES: dict[str, list[str]] = {
    "knowledge_ingestion_runs": [
        "id", "knowledge_scope_id", "workspace_id", "document_source",
        "metadata_snapshot", "status", "phases_jsonb", "chunk_count",
        "token_count", "error_code", "error_detail",
        "started_at_utc", "completed_at_utc", "created_at_utc",
    ],
}

# Extended columns from migration 006 (added to existing 002 tables)
MIGRATION_006_EXTENDED_COLUMNS: dict[str, list[str]] = {
    "knowledge_documents": ["node_path"],
    "knowledge_chunks": ["node_path", "permission_tags"],
}

MIGRATION_004_TABLES: dict[str, list[str]] = {
    "automation_diagnosis_sessions": [
        "id", "public_session_id", "workspace_id", "assistant_instance_id",
        "automation_package_id", "knowledge_scope_id", "organization_code",
        "workspace_slug", "assistant_instance_code", "automation_package_code",
        "knowledge_scope_code", "source_url", "site_channel", "lead_owner",
        "locale", "market", "status", "correlation_id", "visitor_jsonb",
        "package_worker_codes_jsonb", "cost_attribution_jsonb", "metadata_jsonb",
        "result_jsonb", "contact_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "automation_diagnosis_answers": [
        "id", "session_id", "step_id", "selected_jsonb", "free_text",
        "normalized_text", "metadata_jsonb", "created_at_utc", "updated_at_utc",
    ],
    "automation_diagnosis_leads": [
        "id", "session_id", "workspace_id", "assistant_instance_id",
        "automation_package_id", "knowledge_scope_id", "lead_type", "lead_owner",
        "site_channel", "locale", "status", "classification", "automation_mode",
        "recommended_package_type", "score_total", "next_step", "internal_card_jsonb",
        "contact_jsonb", "created_at_utc", "updated_at_utc",
    ],
}

MIGRATION_003_VIEWS: dict[str, list[str]] = {
    "knowledge_ready_chunks": [
        "knowledge_scope_id", "knowledge_document_id", "knowledge_chunk_id",
        "chunk_index", "title", "content", "embedding_model_id",
        "model_alias", "embedding_status", "embedded_at_utc",
    ],
}

TASK_RUNS_NEW_COLUMNS = [
    "automation_package_id",
    "package_worker_id",
    "area_id",
    "assigned_user_id",
    "required_permission",
    "approval_status",
]

APPROVAL_STATUS_ALLOWED = {
    "not_required", "pending", "approved", "rejected", "expired", "cancelled",
}

# Index names that must exist (key partial unique indexes from 002)
REQUIRED_UNIQUE_INDEXES: list[dict[str, str]] = [
    {"name": "uq_core_roles_global", "table": "core_roles", "reason": "unique role_code global"},
    {"name": "uq_core_roles_workspace", "table": "core_roles", "reason": "unique role_code per workspace"},
    {"name": "uq_core_permission_profiles_global", "table": "core_permission_profiles", "reason": "unique profile_code global"},
    {"name": "uq_core_permission_profiles_workspace", "table": "core_permission_profiles", "reason": "unique profile_code per workspace"},
    {"name": "uq_core_user_profiles_nonnull_area", "table": "core_user_profiles", "reason": "unique profile per area"},
    {"name": "uq_core_user_profiles_null_area", "table": "core_user_profiles", "reason": "unique profile without area"},
    {"name": "uq_workspace_plan_subscriptions_active", "table": "workspace_plan_subscriptions", "reason": "single active subscription per workspace"},
    {"name": "uq_knowledge_scopes_global", "table": "knowledge_scopes", "reason": "unique scope_code global"},
    {"name": "uq_knowledge_scopes_workspace", "table": "knowledge_scopes", "reason": "unique scope_code per workspace"},
    {"name": "uq_ksb_default_internal", "table": "knowledge_scope_bindings", "reason": "single default internal"},
    {"name": "uq_ksb_default_workspace", "table": "knowledge_scope_bindings", "reason": "single default per workspace"},
    {"name": "uq_ksb_default_per_entity", "table": "knowledge_scope_bindings", "reason": "single default per entity"},
    {"name": "uq_assistant_instances_workspace_code", "table": "assistant_instances", "reason": "unique assistant_code per workspace"},
    {"name": "uq_ksb_binding_scope_entity", "table": "knowledge_scope_bindings", "reason": "idempotent knowledge scope binding per entity"},
]


KSB_DEFAULT_INDEX_RULES: dict[str, set[str]] = {
    "uq_ksb_default_internal": {"internal"},
    "uq_ksb_default_workspace": {"workspace"},
    "uq_ksb_default_per_entity": {
        "assistant_instance",
        "automation_package",
        "package_worker",
    },
}

REQUIRED_SEEDS: list[tuple[str, str, str]] = [
    ("core_permissions", "permission_code", "dashboard.view"),
    ("package_plans", "plan_code", "starter"),
    ("package_features", "feature_code", "diagnosis.basic"),
    ("worker_definitions", "worker_code", "diagnosis_ai_interpreter"),
    ("worker_definitions", "worker_code", "rag_retriever_worker"),
    ("knowledge_embedding_models", "model_alias", "default_1536"),
    ("worker_definitions", "worker_code", "guided_intake_worker"),
    ("worker_definitions", "worker_code", "lead_qualification_worker"),
    ("worker_definitions", "worker_code", "knowledge_retrieval_worker"),
    ("worker_definitions", "worker_code", "diagnosis_scoring_worker"),
    ("worker_definitions", "worker_code", "package_recommendation_worker"),
    ("worker_definitions", "worker_code", "proposal_outline_worker"),
    ("worker_definitions", "worker_code", "crm_handoff_worker"),
    ("worker_definitions", "worker_code", "calendar_handoff_worker"),
    ("worker_definitions", "worker_code", "agui_render_worker"),
    ("worker_definitions", "worker_code", "knowledge_ingestion_worker"),
]

REQUIRED_003_CONSTRAINTS = {
    "knowledge_embedding_models": {
        "chk_kem_dimension",
        "chk_kem_distance_metric",
        "chk_kem_status",
        "uq_kem_provider_model_dimension",
        "uq_kem_model_alias",
    },
    "knowledge_chunk_embeddings": {
        "chk_kce_embedding_status",
        "chk_kce_ready_requires_embedding",
        "uq_kce_chunk_model",
    },
}

REQUIRED_003_INDEXES = {
    "idx_kce_knowledge_scope",
    "idx_kce_knowledge_chunk",
    "idx_kce_embedding_model",
    "idx_kce_embedding_status",
    "idx_kce_ready_scope_model",
    "idx_kce_embedding_hnsw_cosine",
}

KCE_ALLOWED_STATUSES = {"pending", "ready", "failed", "stale"}

SUSPICIOUS_METADATA_KEYS = [
    "password", "passwd", "token", "api_key", "apikey", "secret", "private_key", "credential",
]
SUSPICIOUS_METADATA_PATTERN = "|".join(re.escape(k) for k in SUSPICIOUS_METADATA_KEYS)


# ---------------------------------------------------------------------------
# Audit logic
# ---------------------------------------------------------------------------


@dataclass
class AuditResult:
    passed: int = 0
    failed: int = 0
    warnings: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


def audit_schema(cursor: Any, result: AuditResult) -> None:
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    db_tables = {row[0] for row in cursor.fetchall()}

    all_expected: dict[str, list[str]] = {}
    all_expected.update(MIGRATION_001_TABLES)
    all_expected.update(MIGRATION_002_TABLES)
    all_expected.update(MIGRATION_003_TABLES)
    all_expected.update(MIGRATION_004_TABLES)
    all_expected.update(MIGRATION_006_TABLES)

    result.details.append(f"Tablas en DB: {len(db_tables)}")
    result.details.append(f"Tablas esperadas (001+002+003+004+006): {len(all_expected)}")

    for table_name, expected_cols in sorted(all_expected.items()):
        if table_name not in db_tables:
            result.failed += 1
            result.details.append(f"  FALTA tabla: {table_name}")
            continue

        cursor.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        db_cols = {row[0] for row in cursor.fetchall()}

        missing = [c for c in expected_cols if c not in db_cols]
        if missing:
            result.failed += 1
            result.details.append(
                f"  FALTAN columnas en {table_name}: {', '.join(missing)}"
            )
        else:
            result.passed += 1

    # Check migration 006 extended columns on existing tables
    for table_name, expected_cols in MIGRATION_006_EXTENDED_COLUMNS.items():
        if table_name not in db_tables:
            continue
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        )
        existing_cols = {row[0] for row in cursor.fetchall()}
        present = [c for c in expected_cols if c in existing_cols]
        missing = [c for c in expected_cols if c not in existing_cols]
        if present:
            result.details.append(
                f"  {table_name}: columnas 006 presentes: {', '.join(present)}"
            )
        if missing:
            result.details.append(
                f"  {table_name}: columnas 006 FALTAN: {', '.join(missing)}"
            )

    # Check task_runs extensions
    if "task_runs" in db_tables:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'task_runs'
            """
        )
        tr_cols = {row[0] for row in cursor.fetchall()}
        present = [c for c in TASK_RUNS_NEW_COLUMNS if c in tr_cols]
        missing = [c for c in TASK_RUNS_NEW_COLUMNS if c not in tr_cols]
        if present:
            result.details.append(
                f"  task_runs: columnas 002 presentes: {', '.join(present)}"
            )
        if missing:
            result.details.append(
                f"  task_runs: columnas 002 FALTAN: {', '.join(missing)}"
            )


def audit_views(cursor: Any, result: AuditResult) -> None:
    """Verify expected migration 003 views and their public columns."""
    for view_name, expected_cols in sorted(MIGRATION_003_VIEWS.items()):
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (view_name,),
        )
        db_cols = [row[0] for row in cursor.fetchall()]
        if not db_cols:
            result.failed += 1
            result.details.append(f"  FALTA view: {view_name}")
            continue

        missing = [c for c in expected_cols if c not in set(db_cols)]
        if missing:
            result.failed += 1
            result.details.append(
                f"  FALTAN columnas en view {view_name}: {', '.join(missing)}"
            )
        else:
            result.passed += 1
            result.details.append(f"  view {view_name}: OK")


def audit_vector_extension(cursor: Any, result: AuditResult) -> None:
    """Verify pgvector is installed in team360."""
    cursor.execute(
        """
        SELECT default_version, installed_version
        FROM pg_available_extensions
        WHERE name = 'vector'
        """
    )
    row = cursor.fetchone()
    if not row:
        result.failed += 1
        result.details.append("  Extension vector: no disponible en el servidor")
        return

    default_version, installed_version = row
    if not installed_version:
        result.failed += 1
        result.details.append(
            f"  Extension vector: disponible {default_version}, no instalada"
        )
        return

    result.passed += 1
    result.details.append(
        f"  Extension vector: OK instalada {installed_version} "
        f"(default disponible {default_version})"
    )


def audit_check_constraints(cursor: Any, result: AuditResult) -> None:
    """Verify approval_status check constraint does NOT contain 'bypassed'."""
    cursor.execute(
        """
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE contype = 'c'
          AND conname = 'chk_task_runs_approval_status'
        """
    )
    row = cursor.fetchone()
    if not row:
        result.warnings.append(
            "chk_task_runs_approval_status: constraint not found"
        )
        return

    constraint_def = row[1]
    if "bypassed" in constraint_def.lower():
        result.failed += 1
        result.details.append(
            "ERROR: chk_task_runs_approval_status contiene 'bypassed' (inseguro)"
        )
    else:
        # Verify all allowed values are present
        for val in APPROVAL_STATUS_ALLOWED:
            if val not in constraint_def.lower():
                result.warnings.append(
                    f"chk_task_runs_approval_status: falta valor '{val}'"
                )
        result.passed += 1
        result.details.append(
            f"chk_task_runs_approval_status: OK (sin bypassed)"
        )


def audit_partial_unique_indexes(cursor: Any, result: AuditResult) -> None:
    """Verify key indexes exist, are unique/partial, and KSB predicates match semantically."""
    cursor.execute(
        """
        SELECT
            index_class.relname AS index_name,
            table_class.relname AS table_name,
            pg_index.indisunique,
            pg_index.indpred IS NOT NULL AS is_partial,
            pg_get_indexdef(pg_index.indexrelid) AS index_def,
            pg_get_expr(pg_index.indpred, pg_index.indrelid) AS predicate
        FROM pg_index
        JOIN pg_class index_class ON index_class.oid = pg_index.indexrelid
        JOIN pg_class table_class ON table_class.oid = pg_index.indrelid
        JOIN pg_namespace table_ns ON table_ns.oid = table_class.relnamespace
        WHERE table_ns.nspname = 'public'
        """
    )
    existing = {
        row[0]: {
            "table": row[1],
            "is_unique": bool(row[2]),
            "is_partial": bool(row[3]),
            "index_def": row[4],
            "predicate": row[5],
        }
        for row in cursor.fetchall()
    }

    for spec in REQUIRED_UNIQUE_INDEXES:
        name = spec["name"]
        if name not in existing:
            result.failed += 1
            result.details.append(f"  FALTA index {name}: {spec['reason']}")
            continue

        index_info = existing[name]
        if index_info["table"] != spec["table"]:
            result.failed += 1
            result.details.append(
                f"  ERROR index {name}: existe sobre "
                f"{index_info['table']}, esperado {spec['table']}"
            )
            continue

        if not index_info["is_unique"]:
            result.failed += 1
            result.details.append(f"  ERROR index {name}: no es UNIQUE")
            continue

        if not index_info["is_partial"]:
            result.failed += 1
            result.details.append(f"  ERROR index {name}: no es parcial")
            continue

        if name in KSB_DEFAULT_INDEX_RULES and not predicate_matches_ksb_rule(
            name,
            index_info["predicate"],
        ):
            result.failed += 1
            result.details.append(
                f"  ERROR index {name}: predicate KSB no coincide semanticamente. "
                f"Predicate: {index_info['predicate']!r}"
            )
            continue

        result.passed += 1
        if name in KSB_DEFAULT_INDEX_RULES:
            result.details.append(
                f"  index {name}: OK UNIQUE parcial, predicate semantico "
                f"({spec['reason']})"
            )
        else:
            result.details.append(f"  index {name}: OK UNIQUE parcial ({spec['reason']})")


def audit_fks(cursor: Any, result: AuditResult) -> None:
    """Verify key FKs exist."""
    expected_fks = [
        "fk_task_runs_automation_package",
        "fk_task_runs_package_worker",
        "fk_task_runs_area",
        "fk_task_runs_assigned_user",
        "fk_package_workers_knowledge_scope",
    ]
    cursor.execute(
        "SELECT conname FROM pg_constraint WHERE contype = 'f'"
    )
    existing = {row[0] for row in cursor.fetchall()}

    for fk in expected_fks:
        if fk in existing:
            result.passed += 1
        else:
            result.warnings.append(f"FK {fk}: no encontrada")

    result.details.append(
        f"  FKs esperadas encontradas: "
        f"{sum(1 for f in expected_fks if f in existing)}/{len(expected_fks)}"
    )


def audit_seeds(cursor: Any, result: AuditResult) -> None:
    for table, code_col, code in REQUIRED_SEEDS:
        cursor.execute(
            f"SELECT count(*) FROM {table} WHERE {code_col} = %s",
            (code,),
        )
        count = cursor.fetchone()[0]
        if count > 0:
            result.passed += 1
            result.details.append(f"  Seed {table}.{code}: OK ({count})")
        else:
            result.failed += 1
            result.details.append(f"  FALTA seed {table}.{code}")


def audit_secrets_in_jsonb(cursor: Any, result: AuditResult) -> None:
    """Check for suspicious keys in credential_references metadata_jsonb.

    Uses a regex scan of the raw text. This is a heuristic, not a guarantee.
    """
    cursor.execute(
        """
        SELECT count(*) FROM credential_references
        WHERE metadata_jsonb::text ~* %s
        """,
        (SUSPICIOUS_METADATA_PATTERN,),
    )
    count = cursor.fetchone()[0]
    if count and int(count) > 0:
        result.warnings.append(
            f"credential_references.metadata_jsonb: {count} filas con claves "
            f"sospechosas ({'/'.join(SUSPICIOUS_METADATA_KEYS)})"
        )
    else:
        result.details.append(
            f"credential_references.metadata_jsonb: {count} filas con claves "
            f"sospechosas ({'/'.join(SUSPICIOUS_METADATA_KEYS)})"
        )


def audit_multi_tenant_consistency(cursor: Any, result: AuditResult) -> None:
    """Basic cross-workspace consistency check.

    Checks that package_workers.workspace_id matches automation_packages.workspace_id
    for existing rows (if data exists).
    """
    cursor.execute("SELECT count(*) FROM package_workers")
    pw_count = int(cursor.fetchone()[0])
    if pw_count == 0:
        result.details.append("multi-tenant: package_workers vacia, no se verifica consistencia")
        return

    cursor.execute("SELECT count(*) FROM automation_packages")
    ap_count = int(cursor.fetchone()[0])
    if ap_count == 0:
        result.details.append("multi-tenant: automation_packages vacia, no se verifica consistencia")
        return

    cursor.execute("""
        SELECT count(*) FROM package_workers pw
        JOIN automation_packages ap ON pw.automation_package_id = ap.id
        WHERE pw.workspace_id != ap.workspace_id
    """)
    mismatch = int(cursor.fetchone()[0])
    if mismatch > 0:
        result.warnings.append(
            f"multi-tenant: {mismatch} package_workers con workspace_id "
            f"distinto al de su automation_package"
        )
    else:
        result.details.append("multi-tenant: no se detectaron cruces de workspace_id")


def audit_knowledge_scope_bindings(cursor: Any, result: AuditResult) -> None:
    """Validate knowledge_scope_bindings against the strong convention.

    Checks:
    1. chk_ksb_convention CHECK constraint exists
    2. No ambiguous defaults (multiple is_default=true with NULL bound_entity_id)
    3. No internal bindings with bound_entity_id NOT NULL
    4. No non-internal bindings with bound_entity_id NULL
    5. All workspace bindings have bound_entity_id = workspace_id
    """
    cursor.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'knowledge_scope_bindings'
    """)
    if cursor.fetchone()[0] == 0:
        result.details.append(
            "knowledge_scope_bindings: table does not exist, skipping validation"
        )
        return

    # 1. CHECK constraint exists
    cursor.execute("""
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_ksb_convention'
          AND conrelid = 'knowledge_scope_bindings'::regclass
    """)
    if cursor.fetchone():
        result.passed += 1
        result.details.append("  chk_ksb_convention: CHECK constraint OK")
    else:
        result.failed += 1
        result.details.append("  FALTA chk_ksb_convention CHECK constraint")

    # 2. Ambiguous defaults (multiple is_default=true with NULL bound_entity_id)
    cursor.execute("""
        SELECT count(*) FROM (
            SELECT binding_type, count(*)
            FROM knowledge_scope_bindings
            WHERE is_default = true
              AND binding_type IN ('assistant_instance', 'automation_package', 'package_worker', 'workspace')
              AND bound_entity_id IS NULL
            GROUP BY binding_type
            HAVING count(*) > 1
        ) t
    """)
    count = int(cursor.fetchone()[0])
    if count > 0:
        result.failed += 1
        result.details.append(
            f"  ERROR: {count} binding types tienen defaults ambiguos "
            "(multiples is_default=true con bound_entity_id NULL)"
        )
    else:
        result.passed += 1
        result.details.append("  No ambiguous defaults: OK")

    # 3. Internal bindings with bound_entity_id NOT NULL
    cursor.execute("""
        SELECT count(*) FROM knowledge_scope_bindings
        WHERE binding_type = 'internal' AND bound_entity_id IS NOT NULL
    """)
    count = int(cursor.fetchone()[0])
    if count > 0:
        result.failed += 1
        result.details.append(
            f"  ERROR: {count} internal bindings tienen bound_entity_id NOT NULL"
        )
    else:
        result.passed += 1
        result.details.append("  No internal bindings with bound_entity_id NOT NULL: OK")

    # 4. Non-internal bindings with bound_entity_id NULL
    cursor.execute("""
        SELECT count(*) FROM knowledge_scope_bindings
        WHERE binding_type IN ('workspace', 'assistant_instance', 'automation_package', 'package_worker')
          AND bound_entity_id IS NULL
    """)
    count = int(cursor.fetchone()[0])
    if count > 0:
        result.failed += 1
        result.details.append(
            f"  ERROR: {count} non-internal bindings tienen bound_entity_id NULL"
        )
    else:
        result.passed += 1
        result.details.append("  No non-internal bindings with bound_entity_id NULL: OK")

    # 5. Workspace bindings where bound_entity_id != workspace_id
    cursor.execute("""
        SELECT count(*) FROM knowledge_scope_bindings
        WHERE binding_type = 'workspace'
          AND (bound_entity_id IS NULL OR workspace_id IS NULL OR bound_entity_id != workspace_id)
    """)
    count = int(cursor.fetchone()[0])
    if count > 0:
        result.failed += 1
        result.details.append(
            f"  ERROR: {count} workspace bindings tienen bound_entity_id != workspace_id"
        )
    else:
        result.passed += 1
        result.details.append(
            "  All workspace bindings have bound_entity_id = workspace_id: OK"
        )


def audit_knowledge_embeddings(cursor: Any, result: AuditResult) -> None:
    """Validate pgvector-backed knowledge embedding persistence from migration 003."""
    cursor.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'knowledge_chunk_embeddings'
    """)
    if cursor.fetchone()[0] == 0:
        result.details.append(
            "knowledge_chunk_embeddings: table does not exist, skipping validation"
        )
        return

    for table_name, expected_constraints in sorted(REQUIRED_003_CONSTRAINTS.items()):
        cursor.execute(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = %s::regclass
            """,
            (table_name,),
        )
        existing = {row[0] for row in cursor.fetchall()}
        missing = sorted(expected_constraints - existing)
        if missing:
            result.failed += 1
            result.details.append(
                f"  FALTAN constraints en {table_name}: {', '.join(missing)}"
            )
        else:
            result.passed += 1
            result.details.append(f"  constraints {table_name}: OK")

    cursor.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'knowledge_chunk_embeddings'
        """
    )
    indexes = {row[0]: row[1] for row in cursor.fetchall()}
    missing_indexes = sorted(REQUIRED_003_INDEXES - set(indexes))
    if missing_indexes:
        result.failed += 1
        result.details.append(
            f"  FALTAN indexes knowledge_chunk_embeddings: {', '.join(missing_indexes)}"
        )
    else:
        result.passed += 1
        result.details.append("  indexes knowledge_chunk_embeddings: OK")

    hnsw_def = indexes.get("idx_kce_embedding_hnsw_cosine", "").lower()
    if hnsw_def and "using hnsw" in hnsw_def and "vector_cosine_ops" in hnsw_def:
        result.passed += 1
        result.details.append("  idx_kce_embedding_hnsw_cosine: OK HNSW cosine")
    else:
        result.failed += 1
        result.details.append("  ERROR idx_kce_embedding_hnsw_cosine: no es HNSW cosine")

    cursor.execute(
        """
        SELECT provider_code, model_code, dimension, distance_metric, status
        FROM knowledge_embedding_models
        WHERE model_alias = 'default_1536'
        """
    )
    seed = cursor.fetchone()
    if seed == ("openai", "text-embedding-3-small", 1536, "cosine", "active"):
        result.passed += 1
        result.details.append("  Seed knowledge_embedding_models.default_1536: OK")
    else:
        result.failed += 1
        result.details.append("  FALTA o difiere seed knowledge_embedding_models.default_1536")

    cursor.execute("""
        SELECT count(*) FROM knowledge_chunk_embeddings
        WHERE embedding_status = 'ready' AND embedding IS NULL
    """)
    ready_null = int(cursor.fetchone()[0])
    if ready_null > 0:
        result.failed += 1
        result.details.append(
            f"  ERROR: {ready_null} embeddings ready tienen embedding NULL"
        )
    else:
        result.passed += 1
        result.details.append("  No ready embeddings with NULL vector: OK")

    cursor.execute(
        """
        SELECT count(*) FROM knowledge_chunk_embeddings
        WHERE embedding_status <> ALL(%s)
        """,
        (list(KCE_ALLOWED_STATUSES),),
    )
    invalid_status = int(cursor.fetchone()[0])
    if invalid_status > 0:
        result.failed += 1
        result.details.append(
            f"  ERROR: {invalid_status} embeddings con status invalido"
        )
    else:
        result.passed += 1
        result.details.append("  No invalid embedding_status values: OK")

    cursor.execute("""
        SELECT count(*) FROM (
            SELECT knowledge_chunk_id, embedding_model_id, count(*)
            FROM knowledge_chunk_embeddings
            GROUP BY knowledge_chunk_id, embedding_model_id
            HAVING count(*) > 1
        ) duplicates
    """)
    duplicates = int(cursor.fetchone()[0])
    if duplicates > 0:
        result.failed += 1
        result.details.append(
            f"  ERROR: {duplicates} duplicados knowledge_chunk_id + embedding_model_id"
        )
    else:
        result.passed += 1
        result.details.append("  No duplicate chunk/model embeddings: OK")

    cursor.execute("""
        SELECT count(*)
        FROM knowledge_chunk_embeddings kce
        JOIN knowledge_chunks kc ON kc.id = kce.knowledge_chunk_id
        JOIN knowledge_documents kd ON kd.id = kc.knowledge_document_id
        WHERE kce.knowledge_scope_id <> kd.knowledge_scope_id
    """)
    mismatches = int(cursor.fetchone()[0])
    if mismatches > 0:
        result.failed += 1
        result.details.append(
            f"  ERROR: {mismatches} embeddings con knowledge_scope_id inconsistente"
        )
    else:
        result.passed += 1
        result.details.append("  knowledge_scope_id consistency for embeddings: OK")


def audit_row_counts(cursor: Any, result: AuditResult) -> None:
    cursor.execute("""
        SELECT relname, reltuples::bigint
        FROM pg_class
        WHERE relkind = 'r'
          AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
        ORDER BY relname
    """)
    rows = cursor.fetchall()
    non_empty = [(t, int(c)) for t, c in rows if c and int(c) > 0]
    if non_empty:
        result.details.append("Tablas con datos (~estimado pg_class):")
        for t, c in non_empty:
            result.details.append(f"  {t}: ~{c} rows")
    else:
        result.details.append("Todas las tablas: 0 filas (o recien creadas).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def resolve_db_url() -> str:
    db_url = os.environ.get("TEAM360_DB_URL_PSQL")
    if not db_url:
        db_url = os.environ.get("TEAM360_DB_URL")
    if db_url:
        return db_url

    # Local development fallback: reuse the PostgreSQL server DSN documented
    # for v360, but force the database name to Team360 without printing secrets.
    source_url = os.environ.get("DB_PG_V360_URL")
    if source_url:
        parts = urlsplit(source_url)
        scheme = "postgresql" if parts.scheme.startswith("postgresql") else parts.scheme
        return urlunsplit((scheme, parts.netloc, "/team360", parts.query, parts.fragment))

    print(
        "ERROR: Define TEAM360_DB_URL_PSQL, TEAM360_DB_URL o DB_PG_V360_URL en el entorno.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    db_url = resolve_db_url()

    try:
        import psycopg  # type: ignore[import-untyped]
    except ImportError:
        print(
            "ERROR: psycopg no instalado. pip install psycopg[binary]",
            file=sys.stderr,
        )
        sys.exit(1)

    result = AuditResult()

    print("Conectando a DB...")
    conn = psycopg.connect(db_url)
    conn.autocommit = True

    try:
        with conn.cursor() as cursor:
            print("\n=== 1. Tablas y columnas ===\n")
            audit_schema(cursor, result)

            print("\n=== 2. Views 003 ===\n")
            audit_views(cursor, result)

            print("\n=== 3. Extension vector ===\n")
            audit_vector_extension(cursor, result)

            print("\n=== 4. Check constraints (approval_status) ===\n")
            audit_check_constraints(cursor, result)

            print("\n=== 5. Indices unicos parciales ===\n")
            audit_partial_unique_indexes(cursor, result)

            print("\n=== 6. Foreign keys ===\n")
            audit_fks(cursor, result)

            print("\n=== 7. Seeds ===\n")
            audit_seeds(cursor, result)

            print("\n=== 8. Secretos en metadata_jsonb ===\n")
            audit_secrets_in_jsonb(cursor, result)

            print("\n=== 9. Knowledge scope bindings convention ===\n")
            audit_knowledge_scope_bindings(cursor, result)

            print("\n=== 10. Multi-tenant consistency ===\n")
            audit_multi_tenant_consistency(cursor, result)

            print("\n=== 11. Knowledge embeddings 003 ===\n")
            audit_knowledge_embeddings(cursor, result)

            print("\n=== 12. Extensiones columnas 006 ===\n")
            # Checked inside audit_schema via MIGRATION_006_EXTENDED_COLUMNS

            print("\n=== 13. Conteo de filas ===\n")
            audit_row_counts(cursor, result)
    finally:
        conn.close()

    print("\n" + "=" * 50)
    print("RESUMEN")
    print("=" * 50)
    print(f"  Checks pasados: {result.passed}")
    print(f"  Checks fallidos: {result.failed}")
    if result.warnings:
        print(f"  Advertencias: {len(result.warnings)}")
        for w in result.warnings:
            print(f"    - {w}")
    print()

    for d in result.details:
        print(f"  {d}")

    if result.failed > 0:
        print("\nCONCLUSION: Auditoria fallida. Revisar pendientes.")
        sys.exit(1)
    else:
        print("\nCONCLUSION: Schema OK (verificacion estructural).")

    print("Audit completed for current database state.")


if __name__ == "__main__":
    main()
