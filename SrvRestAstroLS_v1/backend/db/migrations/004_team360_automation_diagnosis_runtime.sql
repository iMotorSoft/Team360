-- Team360 migration 004 — automation diagnosis runtime persistence.
-- Adds persistent DB writes for sales/diagnosis assistant package installations.
-- Depends on migrations 001, 002 and 003.
-- No provider credentials or secrets are stored here.

-- ---------------------------------------------------------------------------
-- 1. Assistant instance stable code
-- ---------------------------------------------------------------------------

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'assistant_instances'
          and column_name = 'assistant_code'
    ) then
        alter table assistant_instances add column assistant_code text;
    end if;
end $$;

create unique index if not exists uq_assistant_instances_workspace_code
    on assistant_instances (workspace_id, assistant_code)
    where assistant_code is not null;

-- ---------------------------------------------------------------------------
-- 2. Automation diagnosis sessions
-- ---------------------------------------------------------------------------

create table if not exists automation_diagnosis_sessions (
    id uuid primary key default gen_random_uuid(),
    public_session_id text not null unique,
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    assistant_instance_id uuid references assistant_instances(id) on delete set null,
    automation_package_id uuid references automation_packages(id) on delete set null,
    knowledge_scope_id uuid references knowledge_scopes(id) on delete set null,
    organization_code text not null,
    workspace_slug text not null,
    assistant_instance_code text not null,
    automation_package_code text not null,
    knowledge_scope_code text not null,
    source_url text,
    site_channel text not null,
    lead_owner text not null,
    locale text not null default 'es',
    market text,
    status text not null default 'active',
    correlation_id text not null,
    visitor_jsonb jsonb not null default '{}'::jsonb,
    package_worker_codes_jsonb jsonb not null default '[]'::jsonb,
    cost_attribution_jsonb jsonb not null default '{}'::jsonb,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    result_jsonb jsonb,
    contact_jsonb jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_automation_diagnosis_sessions_status
        check (status in ('active', 'classified', 'contact_captured', 'finalized', 'abandoned', 'error')),
    constraint chk_automation_diagnosis_sessions_locale
        check (locale in ('es', 'en', 'he'))
);

create index if not exists idx_ads_workspace_created
    on automation_diagnosis_sessions (workspace_id, created_at_utc desc);

create index if not exists idx_ads_assistant_created
    on automation_diagnosis_sessions (assistant_instance_id, created_at_utc desc);

create index if not exists idx_ads_knowledge_scope
    on automation_diagnosis_sessions (knowledge_scope_id);

create index if not exists idx_ads_correlation
    on automation_diagnosis_sessions (correlation_id);

-- ---------------------------------------------------------------------------
-- 3. Automation diagnosis answers
-- ---------------------------------------------------------------------------

create table if not exists automation_diagnosis_answers (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references automation_diagnosis_sessions(id) on delete cascade,
    step_id text not null,
    selected_jsonb jsonb not null default '[]'::jsonb,
    free_text text not null default '',
    normalized_text text not null default '',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_automation_diagnosis_answers_step
        unique (session_id, step_id)
);

create index if not exists idx_ada_session
    on automation_diagnosis_answers (session_id);

-- ---------------------------------------------------------------------------
-- 4. Automation diagnosis leads
-- ---------------------------------------------------------------------------

create table if not exists automation_diagnosis_leads (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null unique references automation_diagnosis_sessions(id) on delete cascade,
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    assistant_instance_id uuid references assistant_instances(id) on delete set null,
    automation_package_id uuid references automation_packages(id) on delete set null,
    knowledge_scope_id uuid references knowledge_scopes(id) on delete set null,
    lead_type text not null default 'automation_opportunity',
    lead_owner text not null,
    site_channel text not null,
    locale text not null default 'es',
    status text not null default 'new',
    classification text,
    automation_mode text,
    recommended_package_type text,
    score_total integer,
    next_step text,
    internal_card_jsonb jsonb not null default '{}'::jsonb,
    contact_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_automation_diagnosis_leads_status
        check (status in ('new', 'qualified', 'consulting_required', 'not_recommended', 'contacted', 'closed', 'discarded')),
    constraint chk_automation_diagnosis_leads_classification
        check (classification is null or classification in ('standard_package', 'operational_automation', 'consulting_required', 'not_recommended')),
    constraint chk_automation_diagnosis_leads_automation_mode
        check (automation_mode is null or automation_mode in ('read_only', 'assisted', 'approval_required', 'execution', 'blocked'))
);

create index if not exists idx_adl_workspace_created
    on automation_diagnosis_leads (workspace_id, created_at_utc desc);

create index if not exists idx_adl_owner_status
    on automation_diagnosis_leads (lead_owner, status, created_at_utc desc);

create index if not exists idx_adl_assistant_created
    on automation_diagnosis_leads (assistant_instance_id, created_at_utc desc);

-- Supports idempotent application-level bindings for package installations.
create unique index if not exists uq_ksb_binding_scope_entity
    on knowledge_scope_bindings (knowledge_scope_id, binding_type, bound_entity_id)
    where bound_entity_id is not null;

-- ---------------------------------------------------------------------------
-- 5. Worker definition seeds for sales diagnosis package workers
-- ---------------------------------------------------------------------------

insert into worker_definitions (worker_code, display_name, description, worker_kind, default_mode)
values
    ('guided_intake_worker', 'Guided intake worker', 'Collects structured sales diagnosis answers', 'interpreter', 'assisted'),
    ('lead_qualification_worker', 'Lead qualification worker', 'Qualifies commercial fit and next step', 'classifier', 'assisted'),
    ('knowledge_retrieval_worker', 'Knowledge retrieval worker', 'Retrieves scoped sales and automation context', 'interpreter', 'read_only'),
    ('diagnosis_scoring_worker', 'Diagnosis scoring worker', 'Scores viability, risk and package fit', 'classifier', 'read_only'),
    ('package_recommendation_worker', 'Package recommendation worker', 'Recommends Team360 package or consulting path', 'classifier', 'assisted'),
    ('proposal_outline_worker', 'Proposal outline worker', 'Drafts structured proposal outline', 'interpreter', 'assisted'),
    ('crm_handoff_worker', 'CRM handoff worker', 'Prepares lead card for sales follow-up', 'notification', 'assisted'),
    ('calendar_handoff_worker', 'Calendar handoff worker', 'Suggests discovery meeting handoff', 'notification', 'assisted'),
    ('agui_render_worker', 'AG-UI render worker', 'Renders validated semantic diagnosis output', 'interpreter', 'read_only')
on conflict (worker_code) do update set
    display_name = excluded.display_name,
    description = excluded.description,
    worker_kind = excluded.worker_kind,
    default_mode = excluded.default_mode,
    updated_at_utc = now();
