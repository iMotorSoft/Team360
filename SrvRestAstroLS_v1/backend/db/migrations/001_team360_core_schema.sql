-- Team360 core schema proposal.
-- Development-first migration for PostgreSQL.
-- No real provider credentials or secrets are stored here.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Core
-- ---------------------------------------------------------------------------

create table if not exists core_workspaces (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    display_name text not null,
    timezone text not null default 'UTC',
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_core_workspaces_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists core_users (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references core_workspaces(id) on delete set null,
    email text,
    display_name text,
    role text not null default 'member',
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_core_users_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists core_events (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references core_workspaces(id) on delete set null,
    actor_user_id uuid references core_users(id) on delete set null,
    event_name text not null,
    entity_type text,
    entity_id uuid,
    correlation_id text,
    payload_jsonb jsonb not null default '{}'::jsonb,
    occurred_at_utc timestamptz not null default now(),
    created_at_utc timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Communication / WhatsApp
-- ---------------------------------------------------------------------------

create table if not exists communication_providers (
    id uuid primary key default gen_random_uuid(),
    code text not null unique,
    display_name text not null,
    provider_kind text not null default 'whatsapp',
    status text not null default 'active',
    capabilities_jsonb jsonb not null default '{}'::jsonb,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_communication_providers_status
        check (status in ('active', 'inactive', 'testing', 'retired')),
    constraint chk_communication_providers_kind
        check (provider_kind in ('whatsapp', 'marketplace', 'email', 'sms', 'other'))
);

create table if not exists provider_credentials (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references core_workspaces(id) on delete cascade,
    provider_id uuid not null references communication_providers(id) on delete restrict,
    credential_scope text not null,
    environment text not null,
    secret_ref text,
    public_config_jsonb jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    rotated_at_utc timestamptz,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_provider_credentials_scope
        check (credential_scope in ('platform', 'workspace', 'channel')),
    constraint chk_provider_credentials_environment
        check (environment in ('dev', 'stg', 'pro')),
    constraint chk_provider_credentials_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists communication_channels (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    provider_id uuid references communication_providers(id) on delete restrict,
    channel_type text not null default 'whatsapp',
    channel_alias text not null,
    department text,
    display_name text not null,
    status text not null default 'testing',
    current_whatsapp_number_id uuid,
    default_for_department boolean not null default false,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_communication_channels_alias
        unique (workspace_id, channel_alias),
    constraint chk_communication_channels_type
        check (channel_type in ('whatsapp', 'marketplace', 'email', 'sms', 'other')),
    constraint chk_communication_channels_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists whatsapp_numbers (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    provider_id uuid not null references communication_providers(id) on delete restrict,
    channel_id uuid references communication_channels(id) on delete set null,
    credential_id uuid references provider_credentials(id) on delete set null,
    phone_e164 text not null,
    phone_display text,
    provider_phone_number_id text,
    provider_business_id text,
    phone_number_status text not null default 'testing',
    verification_status text not null default 'pending',
    activated_at_utc timestamptz,
    retired_at_utc timestamptz,
    replaced_by_number_id uuid references whatsapp_numbers(id) on delete set null,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_whatsapp_numbers_phone_status
        check (phone_number_status in ('active', 'inactive', 'testing', 'retired', 'paused', 'failed', 'provisioning')),
    constraint chk_whatsapp_numbers_verification_status
        check (verification_status in ('pending', 'verified', 'failed', 'expired'))
);

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_communication_channels_current_whatsapp_number'
    ) then
        alter table communication_channels
            add constraint fk_communication_channels_current_whatsapp_number
            foreign key (current_whatsapp_number_id)
            references whatsapp_numbers(id)
            on delete set null;
    end if;
end $$;

create table if not exists webhook_bindings (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    provider_id uuid not null references communication_providers(id) on delete restrict,
    channel_id uuid references communication_channels(id) on delete set null,
    whatsapp_number_id uuid references whatsapp_numbers(id) on delete set null,
    webhook_url text not null,
    verify_token_ref text,
    signing_secret_ref text,
    provider_external_id text,
    status text not null default 'testing',
    last_verified_at_utc timestamptz,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_webhook_bindings_status
        check (status in ('active', 'inactive', 'testing', 'retired', 'failed'))
);

create table if not exists channel_routing_rules (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    channel_id uuid not null references communication_channels(id) on delete cascade,
    rule_type text not null,
    match_value text,
    priority integer not null default 100,
    status text not null default 'active',
    active_from_utc timestamptz,
    active_to_utc timestamptz,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_channel_routing_rules_type
        check (rule_type in ('provider_number', 'department', 'keyword', 'default', 'automation')),
    constraint chk_channel_routing_rules_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

-- ---------------------------------------------------------------------------
-- Tasks / local runners
-- ---------------------------------------------------------------------------

create table if not exists local_runners (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    runner_name text not null,
    runner_key_hash text,
    install_fingerprint text,
    status text not null default 'testing',
    capabilities_jsonb jsonb not null default '{}'::jsonb,
    version text,
    last_seen_at_utc timestamptz,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_local_runners_workspace_name
        unique (workspace_id, runner_name),
    constraint chk_local_runners_status
        check (status in ('active', 'inactive', 'testing', 'retired', 'blocked'))
);

create table if not exists scheduled_tasks (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    task_key text not null,
    display_name text not null,
    schedule_kind text not null default 'cron',
    schedule_expression text not null,
    timezone text not null default 'UTC',
    status text not null default 'active',
    target_channel_id uuid references communication_channels(id) on delete set null,
    required_runner_capability text,
    payload_jsonb jsonb not null default '{}'::jsonb,
    next_run_at_utc timestamptz,
    last_run_at_utc timestamptz,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_scheduled_tasks_workspace_key
        unique (workspace_id, task_key),
    constraint chk_scheduled_tasks_kind
        check (schedule_kind in ('cron', 'interval', 'manual')),
    constraint chk_scheduled_tasks_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists task_runs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    scheduled_task_id uuid references scheduled_tasks(id) on delete set null,
    runner_id uuid references local_runners(id) on delete set null,
    workflow_run_id uuid,
    status text not null default 'pending',
    lease_id uuid,
    lease_expires_at_utc timestamptz,
    idempotency_key text,
    attempt integer not null default 1,
    max_attempts integer not null default 1,
    scheduled_for_utc timestamptz,
    started_at_utc timestamptz,
    completed_at_utc timestamptz,
    failed_at_utc timestamptz,
    timeout_at_utc timestamptz,
    correlation_id text,
    input_jsonb jsonb not null default '{}'::jsonb,
    result_jsonb jsonb not null default '{}'::jsonb,
    error_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_task_runs_status
        check (status in ('pending', 'running', 'completed', 'failed', 'expired', 'cancelled')),
    constraint chk_task_runs_attempts
        check (attempt >= 1 and max_attempts >= 1)
);

create table if not exists runner_heartbeats (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    runner_id uuid not null references local_runners(id) on delete cascade,
    status text not null default 'active',
    observed_at_utc timestamptz not null default now(),
    metrics_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    constraint chk_runner_heartbeats_status
        check (status in ('active', 'inactive', 'testing', 'retired', 'error'))
);

-- ---------------------------------------------------------------------------
-- Conversations / message events
-- ---------------------------------------------------------------------------

create table if not exists message_threads (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    channel_id uuid not null references communication_channels(id) on delete restrict,
    current_whatsapp_number_id uuid references whatsapp_numbers(id) on delete set null,
    contact_identity text not null,
    subject text,
    current_status text not null default 'active',
    previous_thread_id uuid references message_threads(id) on delete set null,
    last_message_at_utc timestamptz,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_message_threads_status
        check (current_status in ('active', 'inactive', 'testing', 'retired', 'closed'))
);

create table if not exists message_events (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    thread_id uuid references message_threads(id) on delete set null,
    channel_id uuid references communication_channels(id) on delete set null,
    whatsapp_number_id uuid references whatsapp_numbers(id) on delete set null,
    provider_id uuid references communication_providers(id) on delete set null,
    task_run_id uuid references task_runs(id) on delete set null,
    provider_message_id text,
    direction text not null,
    event_type text not null default 'message',
    status text not null default 'completed',
    contact_identity text,
    payload_jsonb jsonb not null default '{}'::jsonb,
    occurred_at_utc timestamptz not null default now(),
    correlation_id text,
    created_at_utc timestamptz not null default now(),
    constraint chk_message_events_direction
        check (direction in ('inbound', 'outbound')),
    constraint chk_message_events_status
        check (status in ('pending', 'running', 'completed', 'failed', 'expired', 'cancelled')),
    constraint chk_message_events_type
        check (event_type in ('message', 'status', 'error', 'system'))
);

create table if not exists whatsapp_number_migration_history (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    channel_id uuid not null references communication_channels(id) on delete cascade,
    old_whatsapp_number_id uuid not null references whatsapp_numbers(id) on delete restrict,
    new_whatsapp_number_id uuid not null references whatsapp_numbers(id) on delete restrict,
    migration_policy_jsonb jsonb not null default '{}'::jsonb,
    migrated_by_user_id uuid references core_users(id) on delete set null,
    status text not null default 'pending',
    started_at_utc timestamptz,
    completed_at_utc timestamptz,
    notes text,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_whatsapp_number_migration_status
        check (status in ('pending', 'running', 'completed', 'failed', 'expired', 'cancelled'))
);

-- ---------------------------------------------------------------------------
-- LLM
-- ---------------------------------------------------------------------------

create table if not exists llm_providers (
    id uuid primary key default gen_random_uuid(),
    code text not null unique,
    display_name text not null,
    base_url text,
    auth_type text not null default 'bearer',
    status text not null default 'active',
    capabilities_jsonb jsonb not null default '{}'::jsonb,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_llm_providers_status
        check (status in ('active', 'inactive', 'testing', 'retired')),
    constraint chk_llm_providers_auth_type
        check (auth_type in ('bearer', 'api_key', 'none'))
);

create table if not exists llm_credentials (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references core_workspaces(id) on delete cascade,
    provider_id uuid not null references llm_providers(id) on delete restrict,
    credential_scope text not null,
    environment text not null,
    secret_ref text,
    status text not null default 'active',
    created_by_user_id uuid references core_users(id) on delete set null,
    rotated_at_utc timestamptz,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_llm_credentials_scope
        check (credential_scope in ('platform', 'workspace')),
    constraint chk_llm_credentials_environment
        check (environment in ('dev', 'stg', 'pro')),
    constraint chk_llm_credentials_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists llm_model_profiles (
    id uuid primary key default gen_random_uuid(),
    provider_id uuid not null references llm_providers(id) on delete restrict,
    model_id text not null,
    display_name text not null,
    model_capabilities jsonb not null default '{}'::jsonb,
    context_window integer,
    input_cost_per_million numeric(12, 6),
    output_cost_per_million numeric(12, 6),
    currency text not null default 'USD',
    latency_class text,
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_llm_model_profiles_provider_model
        unique (provider_id, model_id),
    constraint chk_llm_model_profiles_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists llm_fallback_policy (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references core_workspaces(id) on delete cascade,
    name text not null,
    ordered_model_profile_ids uuid[] not null default array[]::uuid[],
    fallback_on_error_codes text[] not null default array[]::text[],
    max_attempts integer not null default 1,
    cooldown_seconds integer not null default 0,
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_llm_fallback_policy_status
        check (status in ('active', 'inactive', 'testing', 'retired')),
    constraint chk_llm_fallback_policy_attempts
        check (max_attempts >= 1 and cooldown_seconds >= 0)
);

create table if not exists workspace_llm_settings (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null unique references core_workspaces(id) on delete cascade,
    default_model_profile_id uuid references llm_model_profiles(id) on delete set null,
    fallback_policy_id uuid references llm_fallback_policy(id) on delete set null,
    key_scope_preference text not null default 'platform_first',
    monthly_budget_limit numeric(12, 4),
    daily_budget_limit numeric(12, 4),
    safety_policy_jsonb jsonb not null default '{}'::jsonb,
    data_retention_policy text,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_workspace_llm_settings_key_scope
        check (key_scope_preference in ('platform_first', 'workspace_first', 'platform_only', 'workspace_only')),
    constraint chk_workspace_llm_settings_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists automation_llm_policy (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    automation_key text not null,
    primary_model_profile_id uuid references llm_model_profiles(id) on delete set null,
    fallback_policy_id uuid references llm_fallback_policy(id) on delete set null,
    credential_scope_preference text not null default 'platform_first',
    max_tokens integer,
    temperature numeric(4, 3),
    timeout_ms integer,
    retry_policy_jsonb jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_automation_llm_policy_workspace_key
        unique (workspace_id, automation_key),
    constraint chk_automation_llm_policy_scope
        check (credential_scope_preference in ('platform_first', 'workspace_first', 'platform_only', 'workspace_only')),
    constraint chk_automation_llm_policy_status
        check (status in ('active', 'inactive', 'testing', 'retired')),
    constraint chk_automation_llm_policy_temperature
        check (temperature is null or (temperature >= 0 and temperature <= 2))
);

create table if not exists llm_cost_estimates (
    id uuid primary key default gen_random_uuid(),
    provider_id uuid not null references llm_providers(id) on delete cascade,
    model_id text not null,
    currency text not null default 'USD',
    input_cost_per_million numeric(12, 6),
    output_cost_per_million numeric(12, 6),
    effective_from_utc timestamptz not null default now(),
    effective_to_utc timestamptz,
    created_at_utc timestamptz not null default now()
);

create table if not exists llm_usage_logs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    automation_key text,
    task_run_id uuid references task_runs(id) on delete set null,
    workflow_run_id uuid,
    provider_id uuid references llm_providers(id) on delete set null,
    model_profile_id uuid references llm_model_profiles(id) on delete set null,
    credential_scope text,
    prompt_tokens integer,
    completion_tokens integer,
    total_tokens integer,
    estimated_cost numeric(12, 6),
    currency text not null default 'USD',
    latency_ms integer,
    status text not null default 'completed',
    error_code text,
    correlation_id text,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    constraint chk_llm_usage_logs_scope
        check (credential_scope is null or credential_scope in ('platform', 'workspace')),
    constraint chk_llm_usage_logs_status
        check (status in ('pending', 'running', 'completed', 'failed', 'expired', 'cancelled')),
    constraint chk_llm_usage_logs_tokens
        check (
            (prompt_tokens is null or prompt_tokens >= 0)
            and (completion_tokens is null or completion_tokens >= 0)
            and (total_tokens is null or total_tokens >= 0)
        )
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

create index if not exists idx_core_users_workspace
    on core_users (workspace_id);

create index if not exists idx_core_events_workspace
    on core_events (workspace_id);

create index if not exists idx_core_events_correlation
    on core_events (correlation_id);

create index if not exists idx_core_events_occurred_at
    on core_events (occurred_at_utc desc);

create index if not exists idx_communication_providers_created_at
    on communication_providers (created_at_utc desc);

create index if not exists idx_provider_credentials_workspace
    on provider_credentials (workspace_id);

create index if not exists idx_provider_credentials_provider
    on provider_credentials (provider_id);

create index if not exists idx_communication_channels_workspace
    on communication_channels (workspace_id);

create index if not exists idx_communication_channels_provider
    on communication_channels (provider_id);

create index if not exists idx_whatsapp_numbers_workspace
    on whatsapp_numbers (workspace_id);

create index if not exists idx_whatsapp_numbers_channel
    on whatsapp_numbers (channel_id);

create index if not exists idx_whatsapp_numbers_provider_phone
    on whatsapp_numbers (provider_id, provider_phone_number_id);

create unique index if not exists uq_whatsapp_numbers_active_phone_per_workspace
    on whatsapp_numbers (workspace_id, phone_e164)
    where phone_number_status in ('active', 'testing', 'paused');

create index if not exists idx_webhook_bindings_workspace
    on webhook_bindings (workspace_id);

create index if not exists idx_webhook_bindings_number
    on webhook_bindings (whatsapp_number_id);

create index if not exists idx_channel_routing_rules_workspace
    on channel_routing_rules (workspace_id);

create index if not exists idx_local_runners_workspace
    on local_runners (workspace_id);

create index if not exists idx_local_runners_last_seen
    on local_runners (last_seen_at_utc desc);

create index if not exists idx_scheduled_tasks_workspace
    on scheduled_tasks (workspace_id);

create index if not exists idx_scheduled_tasks_next_run
    on scheduled_tasks (next_run_at_utc);

create index if not exists idx_task_runs_workspace
    on task_runs (workspace_id);

create index if not exists idx_task_runs_runner
    on task_runs (runner_id);

create index if not exists idx_task_runs_status
    on task_runs (status);

create index if not exists idx_task_runs_correlation
    on task_runs (correlation_id);

create index if not exists idx_task_runs_created_at
    on task_runs (created_at_utc desc);

create unique index if not exists uq_task_runs_idempotency_key
    on task_runs (workspace_id, idempotency_key)
    where idempotency_key is not null;

create index if not exists idx_runner_heartbeats_runner
    on runner_heartbeats (runner_id, observed_at_utc desc);

create index if not exists idx_runner_heartbeats_workspace
    on runner_heartbeats (workspace_id);

create index if not exists idx_message_threads_workspace
    on message_threads (workspace_id);

create index if not exists idx_message_threads_channel
    on message_threads (channel_id);

create index if not exists idx_message_threads_contact
    on message_threads (workspace_id, contact_identity);

create index if not exists idx_message_threads_created_at
    on message_threads (created_at_utc desc);

create index if not exists idx_message_events_workspace
    on message_events (workspace_id);

create index if not exists idx_message_events_thread
    on message_events (thread_id, occurred_at_utc);

create index if not exists idx_message_events_channel
    on message_events (channel_id);

create index if not exists idx_message_events_provider_message
    on message_events (provider_message_id);

create index if not exists idx_message_events_task_run
    on message_events (task_run_id);

create index if not exists idx_message_events_correlation
    on message_events (correlation_id);

create index if not exists idx_message_events_occurred_at
    on message_events (occurred_at_utc desc);

create index if not exists idx_whatsapp_number_migration_workspace
    on whatsapp_number_migration_history (workspace_id);

create index if not exists idx_whatsapp_number_migration_channel
    on whatsapp_number_migration_history (channel_id);

create index if not exists idx_llm_credentials_workspace
    on llm_credentials (workspace_id);

create index if not exists idx_llm_credentials_provider
    on llm_credentials (provider_id);

create index if not exists idx_llm_model_profiles_provider
    on llm_model_profiles (provider_id);

create index if not exists idx_workspace_llm_settings_workspace
    on workspace_llm_settings (workspace_id);

create index if not exists idx_automation_llm_policy_workspace
    on automation_llm_policy (workspace_id);

create index if not exists idx_llm_usage_logs_workspace
    on llm_usage_logs (workspace_id);

create index if not exists idx_llm_usage_logs_task_run
    on llm_usage_logs (task_run_id);

create index if not exists idx_llm_usage_logs_correlation
    on llm_usage_logs (correlation_id);

create index if not exists idx_llm_usage_logs_created_at
    on llm_usage_logs (created_at_utc desc);

create index if not exists idx_llm_cost_estimates_provider_model
    on llm_cost_estimates (provider_id, model_id, effective_from_utc desc);
