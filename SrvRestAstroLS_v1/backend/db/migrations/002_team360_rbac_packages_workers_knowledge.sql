-- Team360 migration 002 — RBAC, packages, workers, knowledge.
-- BORRADOR CORREGIDO v3 — No aplicar sobre team360 sin validacion con GPT-5.5.
-- v3: knowledge_scope_bindings CHECK fuerte + nuevos indices unicos parciales + filtro schema en DO blocks.
-- Depende de migration 001 aplicada.
-- Consistent with 001: gen_random_uuid, timestamptz _utc, jsonb, check constraints.
--
-- Correcciones aplicadas respecto a v1:
--   - core_roles: workspace_id nullable, is_system_role, partial unique indexes
--   - core_permission_profiles: partial unique indexes for nullable workspace_id
--   - core_user_profiles: area_id + partial unique for distinct areas
--   - automation_packages: package_code scoped to workspace, FK to package_plans
--   - approval_status: removed 'bypassed', uses safe values only
--   - knowledge_scope_bindings: new table, binding moved from knowledge_scopes
--   - assistant_instances: no FK to knowledge_scopes (circular avoided)
--   - package_workers: added package_worker_code
--   - workspace_plan_subscriptions: partial unique for active only, ended_at_utc
--   - credential_references: metadata_jsonb must not contain secrets
--   - worker_definitions seeds: aligned with lat.md naming

-- ---------------------------------------------------------------------------
-- 1. RBAC minimo
-- ---------------------------------------------------------------------------

create table if not exists core_workspace_areas (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    area_code text not null,
    display_name text not null,
    description text,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_core_workspace_areas_code
        unique (workspace_id, area_code),
    constraint chk_core_workspace_areas_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists core_permissions (
    id uuid primary key default gen_random_uuid(),
    permission_code text not null unique,
    display_name text not null,
    description text,
    category text,
    created_at_utc timestamptz not null default now()
);

create table if not exists core_roles (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references core_workspaces(id) on delete cascade,
    role_code text not null,
    display_name text not null,
    description text,
    is_system_role boolean not null default false,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_core_roles_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create unique index if not exists uq_core_roles_global
    on core_roles (role_code)
    where workspace_id is null;

create unique index if not exists uq_core_roles_workspace
    on core_roles (workspace_id, role_code)
    where workspace_id is not null;

create table if not exists core_role_permissions (
    id uuid primary key default gen_random_uuid(),
    role_id uuid not null references core_roles(id) on delete cascade,
    permission_id uuid not null references core_permissions(id) on delete cascade,
    created_at_utc timestamptz not null default now(),
    constraint uq_core_role_permissions
        unique (role_id, permission_id)
);

create table if not exists core_permission_profiles (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references core_workspaces(id) on delete cascade,
    profile_code text not null,
    display_name text not null,
    description text,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_core_permission_profiles_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create unique index if not exists uq_core_permission_profiles_global
    on core_permission_profiles (profile_code)
    where workspace_id is null;

create unique index if not exists uq_core_permission_profiles_workspace
    on core_permission_profiles (workspace_id, profile_code)
    where workspace_id is not null;

create table if not exists core_profile_permissions (
    id uuid primary key default gen_random_uuid(),
    profile_id uuid not null references core_permission_profiles(id) on delete cascade,
    permission_id uuid not null references core_permissions(id) on delete cascade,
    created_at_utc timestamptz not null default now(),
    constraint uq_core_profile_permissions
        unique (profile_id, permission_id)
);

create table if not exists core_user_roles (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references core_users(id) on delete cascade,
    role_id uuid not null references core_roles(id) on delete cascade,
    created_at_utc timestamptz not null default now(),
    constraint uq_core_user_roles
        unique (user_id, role_id)
);

create table if not exists core_user_profiles (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references core_users(id) on delete cascade,
    profile_id uuid not null references core_permission_profiles(id) on delete cascade,
    area_id uuid references core_workspace_areas(id) on delete set null,
    created_at_utc timestamptz not null default now()
);

-- Allow same profile in different areas; prevent duplicates for the same (user, profile, area).
create unique index if not exists uq_core_user_profiles_nonnull_area
    on core_user_profiles (user_id, profile_id, area_id)
    where area_id is not null;

create unique index if not exists uq_core_user_profiles_null_area
    on core_user_profiles (user_id, profile_id)
    where area_id is null;

-- ---------------------------------------------------------------------------
-- 2. Planes, features y limites
-- ---------------------------------------------------------------------------

create table if not exists package_plans (
    id uuid primary key default gen_random_uuid(),
    plan_code text not null unique,
    display_name text not null,
    description text,
    sort_order integer not null default 0,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_package_plans_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists package_features (
    id uuid primary key default gen_random_uuid(),
    feature_code text not null unique,
    display_name text not null,
    description text,
    category text,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    constraint chk_package_features_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists package_plan_features (
    id uuid primary key default gen_random_uuid(),
    plan_id uuid not null references package_plans(id) on delete cascade,
    feature_id uuid not null references package_features(id) on delete cascade,
    max_value integer,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    constraint uq_package_plan_features
        unique (plan_id, feature_id)
);

create table if not exists workspace_plan_subscriptions (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    plan_id uuid not null references package_plans(id) on delete restrict,
    status text not null default 'active',
    started_at_utc timestamptz not null default now(),
    ended_at_utc timestamptz,
    expires_at_utc timestamptz,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_workspace_plan_subscriptions_status
        check (status in ('active', 'inactive', 'testing', 'retired', 'expired', 'cancelled'))
);

-- Only one active subscription per workspace at a time; history allowed via status.
create unique index if not exists uq_workspace_plan_subscriptions_active
    on workspace_plan_subscriptions (workspace_id)
    where status = 'active';

-- ---------------------------------------------------------------------------
-- 3. Assistant instances
-- ---------------------------------------------------------------------------

create table if not exists assistant_instances (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    assistant_type text not null,
    name text not null,
    status text not null default 'testing',
    embed_config_jsonb jsonb not null default '{}'::jsonb,
    public_config_jsonb jsonb not null default '{}'::jsonb,
    default_knowledge_scope_id uuid,
    settings_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_assistant_instances_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

-- Note: default_knowledge_scope_id has NO FK to knowledge_scopes to avoid
-- circular dependency. The default scope is resolved via knowledge_scope_bindings
-- with is_default = true for the assistant_instance. See knowledge_scope_bindings below.

-- ---------------------------------------------------------------------------
-- 4. Automation packages
-- ---------------------------------------------------------------------------

create table if not exists automation_packages (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    assistant_instance_id uuid references assistant_instances(id) on delete set null,
    package_code text not null,
    package_name text not null,
    plan_code text not null references package_plans(plan_code),
    status text not null default 'testing',
    enabled_features_jsonb jsonb not null default '[]'::jsonb,
    limits_jsonb jsonb not null default '{}'::jsonb,
    settings_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_automation_packages_workspace_code
        unique (workspace_id, package_code),
    constraint chk_automation_packages_status
        check (status in ('active', 'inactive', 'testing', 'retired', 'paused'))
);

-- ---------------------------------------------------------------------------
-- 5. Workers
-- ---------------------------------------------------------------------------

create table if not exists worker_definitions (
    id uuid primary key default gen_random_uuid(),
    worker_code text not null unique,
    display_name text not null,
    description text,
    worker_kind text not null,
    default_mode text not null default 'read_only',
    capabilities_jsonb jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_worker_definitions_kind
        check (worker_kind in ('browser', 'api', 'desktop', 'interpreter', 'classifier', 'approval', 'notification', 'other')),
    constraint chk_worker_definitions_default_mode
        check (default_mode in ('read_only', 'assisted', 'approval_required', 'execution', 'blocked')),
    constraint chk_worker_definitions_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create table if not exists package_workers (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    automation_package_id uuid not null references automation_packages(id) on delete cascade,
    worker_definition_id uuid not null references worker_definitions(id) on delete restrict,
    package_worker_code text not null,
    status text not null default 'testing',
    mode text not null default 'read_only',
    knowledge_scope_id uuid,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_package_workers_code
        unique (automation_package_id, package_worker_code),
    constraint chk_package_workers_status
        check (status in ('active', 'inactive', 'testing', 'retired', 'paused', 'error')),
    constraint chk_package_workers_mode
        check (mode in ('read_only', 'assisted', 'approval_required', 'execution', 'blocked'))
);

create table if not exists package_worker_configs (
    id uuid primary key default gen_random_uuid(),
    package_worker_id uuid not null unique references package_workers(id) on delete cascade,
    config_jsonb jsonb not null default '{}'::jsonb,
    allowed_actions_jsonb jsonb not null default '[]'::jsonb,
    blocked_actions_jsonb jsonb not null default '[]'::jsonb,
    limits_jsonb jsonb not null default '{}'::jsonb,
    requires_human_approval boolean not null default false,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 6. Credenciales genericas
-- ---------------------------------------------------------------------------
-- WARNING: metadata_jsonb must NOT contain passwords, tokens, API keys
-- or any secret material. Only secret_ref references external storage.
-- Use audit_team360_schema.py to detect suspicious keys in metadata_jsonb.

create table if not exists credential_references (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references core_workspaces(id) on delete cascade,
    automation_package_id uuid references automation_packages(id) on delete cascade,
    package_worker_id uuid references package_workers(id) on delete cascade,
    credential_type text not null,
    provider_code text,
    secret_ref text not null,
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_credential_references_status
        check (status in ('active', 'inactive', 'testing', 'retired', 'rotated'))
);

-- ---------------------------------------------------------------------------
-- 7. Knowledge scopes
-- ---------------------------------------------------------------------------

create table if not exists knowledge_scopes (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references core_workspaces(id) on delete cascade,
    scope_code text not null,
    name text not null,
    retrieval_mode text not null default 'none',
    graph_enabled boolean not null default false,
    settings_jsonb jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_knowledge_scopes_retrieval_mode
        check (retrieval_mode in ('none', 'rag', 'graphrag', 'hybrid')),
    constraint chk_knowledge_scopes_status
        check (status in ('active', 'inactive', 'testing', 'retired'))
);

create unique index if not exists uq_knowledge_scopes_global
    on knowledge_scopes (scope_code)
    where workspace_id is null;

create unique index if not exists uq_knowledge_scopes_workspace
    on knowledge_scopes (workspace_id, scope_code)
    where workspace_id is not null;

-- ---------------------------------------------------------------------------
-- 8. Knowledge scope bindings
-- ---------------------------------------------------------------------------
-- Replaces the old binding_type/binding_id columns on knowledge_scopes.
-- A knowledge scope can be bound to multiple entities.
-- Each binding type has a FK-like constraint at application level.

create table if not exists knowledge_scope_bindings (
    id uuid primary key default gen_random_uuid(),
    knowledge_scope_id uuid not null references knowledge_scopes(id) on delete cascade,
    workspace_id uuid references core_workspaces(id) on delete cascade,
    binding_type text not null,
    bound_entity_id uuid,
    is_default boolean not null default false,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    -- Strong convention: validates nullability rules per binding_type
    --   internal           -> workspace_id IS NULL, bound_entity_id IS NULL
    --   workspace          -> workspace_id NOT NULL, bound_entity_id NOT NULL, bound_entity_id = workspace_id
    --   assistant_instance / automation_package / package_worker
    --                     -> workspace_id NOT NULL, bound_entity_id NOT NULL
    constraint chk_ksb_convention
        check (
            (
                binding_type = 'internal'
                and workspace_id is null
                and bound_entity_id is null
            )
            or
            (
                binding_type = 'workspace'
                and workspace_id is not null
                and bound_entity_id is not null
                and bound_entity_id = workspace_id
            )
            or
            (
                binding_type in ('assistant_instance', 'automation_package', 'package_worker')
                and workspace_id is not null
                and bound_entity_id is not null
            )
        )
);

create index if not exists idx_ksb_knowledge_scope
    on knowledge_scope_bindings (knowledge_scope_id);

create index if not exists idx_ksb_workspace
    on knowledge_scope_bindings (workspace_id);

create index if not exists idx_ksb_binding
    on knowledge_scope_bindings (binding_type, bound_entity_id);

-- Only one default for internal bindings (internal is global, no workspace_id)
create unique index if not exists uq_ksb_default_internal
    on knowledge_scope_bindings (binding_type)
    where binding_type = 'internal' and is_default = true;

-- Only one default per workspace (bound_entity_id = workspace_id enforced by CHECK)
create unique index if not exists uq_ksb_default_workspace
    on knowledge_scope_bindings (workspace_id)
    where binding_type = 'workspace' and is_default = true;

-- Only one default per entity type+id (assistant_instance, automation_package, package_worker)
create unique index if not exists uq_ksb_default_per_entity
    on knowledge_scope_bindings (binding_type, bound_entity_id)
    where binding_type in ('assistant_instance', 'automation_package', 'package_worker')
    and is_default = true;

-- ---------------------------------------------------------------------------
-- 9. Knowledge documents and chunks
-- ---------------------------------------------------------------------------

create table if not exists knowledge_documents (
    id uuid primary key default gen_random_uuid(),
    knowledge_scope_id uuid not null references knowledge_scopes(id) on delete cascade,
    source_type text not null,
    source_uri text,
    title text not null,
    content_hash text not null,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_knowledge_documents_status
        check (status in ('active', 'inactive', 'testing', 'retired', 'archived'))
);

create table if not exists knowledge_chunks (
    id uuid primary key default gen_random_uuid(),
    knowledge_document_id uuid not null references knowledge_documents(id) on delete cascade,
    chunk_index integer not null,
    title text,
    content text not null,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    token_count integer,
    embedding_status text not null default 'pending',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_knowledge_chunks_index
        unique (knowledge_document_id, chunk_index),
    constraint chk_knowledge_chunks_embedding_status
        check (embedding_status in ('pending', 'processing', 'completed', 'failed'))
);

-- ---------------------------------------------------------------------------
-- 10. ALTER TABLE — FK diferidas (solo package_workers -> knowledge_scopes)
-- ---------------------------------------------------------------------------

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_package_workers_knowledge_scope'
          and conrelid = 'package_workers'::regclass
    ) then
        alter table package_workers
            add constraint fk_package_workers_knowledge_scope
            foreign key (knowledge_scope_id)
            references knowledge_scopes(id)
            on delete set null;
    end if;
end $$;

-- ---------------------------------------------------------------------------
-- 11. ALTER TABLE — Extension de task_runs
-- ---------------------------------------------------------------------------

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'task_runs' and column_name = 'automation_package_id'
    ) then
        alter table task_runs add column automation_package_id uuid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'task_runs' and column_name = 'package_worker_id'
    ) then
        alter table task_runs add column package_worker_id uuid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'task_runs' and column_name = 'area_id'
    ) then
        alter table task_runs add column area_id uuid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'task_runs' and column_name = 'assigned_user_id'
    ) then
        alter table task_runs add column assigned_user_id uuid;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'task_runs' and column_name = 'required_permission'
    ) then
        alter table task_runs add column required_permission text;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'task_runs' and column_name = 'approval_status'
    ) then
        alter table task_runs add column approval_status text;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_task_runs_approval_status'
          and conrelid = 'task_runs'::regclass
    ) then
        alter table task_runs
            add constraint chk_task_runs_approval_status
            check (approval_status is null or approval_status in (
                'not_required', 'pending', 'approved', 'rejected', 'expired', 'cancelled'
            ));
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_task_runs_automation_package'
          and conrelid = 'task_runs'::regclass
    ) then
        alter table task_runs
            add constraint fk_task_runs_automation_package
            foreign key (automation_package_id)
            references automation_packages(id)
            on delete set null;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_task_runs_package_worker'
          and conrelid = 'task_runs'::regclass
    ) then
        alter table task_runs
            add constraint fk_task_runs_package_worker
            foreign key (package_worker_id)
            references package_workers(id)
            on delete set null;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_task_runs_area'
          and conrelid = 'task_runs'::regclass
    ) then
        alter table task_runs
            add constraint fk_task_runs_area
            foreign key (area_id)
            references core_workspace_areas(id)
            on delete set null;
    end if;
end $$;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_task_runs_assigned_user'
          and conrelid = 'task_runs'::regclass
    ) then
        alter table task_runs
            add constraint fk_task_runs_assigned_user
            foreign key (assigned_user_id)
            references core_users(id)
            on delete set null;
    end if;
end $$;

-- ---------------------------------------------------------------------------
-- 12. Seeds — Catalogos del sistema (idempotentes)
-- ---------------------------------------------------------------------------

-- Permisos iniciales
insert into core_permissions (permission_code, display_name, category) values
    ('dashboard.view', 'Ver dashboard', 'dashboard'),
    ('task.view', 'Ver tareas', 'task'),
    ('task.assign', 'Asignar tareas', 'task'),
    ('task.execute', 'Ejecutar tareas', 'task'),
    ('task.approve', 'Aprobar tareas', 'task'),
    ('task.reject', 'Rechazar tareas', 'task'),
    ('task.comment', 'Comentar tareas', 'task'),
    ('package.view', 'Ver paquetes', 'package'),
    ('package.configure', 'Configurar paquetes', 'package'),
    ('package.pause', 'Pausar paquetes', 'package'),
    ('worker.view', 'Ver workers', 'worker'),
    ('worker.configure', 'Configurar workers', 'worker'),
    ('worker.execute', 'Ejecutar workers', 'worker'),
    ('knowledge.view', 'Ver conocimiento', 'knowledge'),
    ('knowledge.upload', 'Subir documentos', 'knowledge'),
    ('credential.view_ref', 'Ver referencias de credenciales', 'credential'),
    ('credential.manage_ref', 'Gestionar referencias de credenciales', 'credential'),
    ('audit.view', 'Ver auditoria', 'audit'),
    ('user.manage', 'Gestionar usuarios', 'user'),
    ('role.manage', 'Gestionar roles', 'user')
on conflict (permission_code) do nothing;

-- Planes
insert into package_plans (plan_code, display_name, sort_order, description) values
    ('starter', 'Starter', 1, 'Plan inicial para diagnosticos y dashboard basico'),
    ('operational', 'Operational', 2, 'Plan operativo con workers internos y RAG simple'),
    ('premium_erp', 'Premium ERP', 3, 'Plan premium con integracion ERP y GraphRAG'),
    ('enterprise_custom', 'Enterprise Custom', 4, 'Plan enterprise con configuracion personalizada')
on conflict (plan_code) do nothing;

-- Features
insert into package_features (feature_code, display_name, category) values
    ('diagnosis.basic', 'Diagnostico basico', 'diagnosis'),
    ('dashboard.basic', 'Dashboard basico', 'dashboard'),
    ('dashboard.by_area', 'Dashboard por area', 'dashboard'),
    ('rag.simple', 'RAG simple', 'knowledge'),
    ('graphrag.enabled', 'GraphRAG habilitado', 'knowledge'),
    ('approval.basic', 'Aprobacion basica', 'approval'),
    ('approval.multi_level', 'Aprobacion multi-nivel', 'approval'),
    ('events.basic', 'Eventos basicos', 'events'),
    ('audit.advanced', 'Auditoria avanzada', 'audit'),
    ('workers.internal', 'Workers internos', 'workers'),
    ('workers.external', 'Workers externos', 'workers'),
    ('package_worker.config', 'Configuracion de workers', 'workers'),
    ('erp.read_only', 'ERP solo lectura', 'erp'),
    ('erp.assisted', 'ERP asistido', 'erp'),
    ('erp.write_approval', 'ERP escritura con aprobacion', 'erp'),
    ('marketplace.ops', 'Operaciones marketplace', 'marketplace'),
    ('crm.integration', 'Integracion CRM', 'crm')
on conflict (feature_code) do nothing;

-- Asignacion de features a planes (refs cruzadas con seeds anteriores)
do $$
declare
    v_starter_id uuid;
    v_operational_id uuid;
    v_premium_id uuid;
    v_enterprise_id uuid;
    v_feature record;
begin
    select id into v_starter_id from package_plans where plan_code = 'starter';
    select id into v_operational_id from package_plans where plan_code = 'operational';
    select id into v_premium_id from package_plans where plan_code = 'premium_erp';
    select id into v_enterprise_id from package_plans where plan_code = 'enterprise_custom';

    -- Starter: features basicas
    for v_feature in
        select pf.id from package_features pf where pf.feature_code in (
            'diagnosis.basic', 'dashboard.basic', 'events.basic', 'rag.simple'
        )
    loop
        insert into package_plan_features (plan_id, feature_id)
        values (v_starter_id, v_feature.id)
        on conflict (plan_id, feature_id) do nothing;
    end loop;

    -- Operational: starter + workers internos + approval basico
    for v_feature in
        select pf.id from package_features pf where pf.feature_code in (
            'diagnosis.basic', 'dashboard.basic', 'dashboard.by_area',
            'rag.simple', 'approval.basic', 'events.basic', 'audit.advanced',
            'workers.internal', 'package_worker.config',
            'marketplace.ops', 'crm.integration'
        )
    loop
        insert into package_plan_features (plan_id, feature_id)
        values (v_operational_id, v_feature.id)
        on conflict (plan_id, feature_id) do nothing;
    end loop;

    -- Premium ERP: todo
    for v_feature in
        select pf.id from package_features pf where pf.feature_code in (
            'diagnosis.basic', 'dashboard.basic', 'dashboard.by_area',
            'rag.simple', 'graphrag.enabled',
            'approval.basic', 'approval.multi_level',
            'events.basic', 'audit.advanced',
            'workers.internal', 'workers.external', 'package_worker.config',
            'erp.read_only', 'erp.assisted', 'erp.write_approval',
            'marketplace.ops', 'crm.integration'
        )
    loop
        insert into package_plan_features (plan_id, feature_id)
        values (v_premium_id, v_feature.id)
        on conflict (plan_id, feature_id) do nothing;
    end loop;

    -- Enterprise: todas las features
    for v_feature in
        select pf.id from package_features pf
    loop
        insert into package_plan_features (plan_id, feature_id)
        values (v_enterprise_id, v_feature.id)
        on conflict (plan_id, feature_id) do nothing;
    end loop;
end $$;

-- Worker definitions base (aligned with lat.md naming)
insert into worker_definitions (worker_code, display_name, description, worker_kind, default_mode) values
    ('diagnosis_ai_interpreter', 'Diagnosis AI Interpreter', 'Worker que interpreta diagnosticos de automatizacion via IA', 'interpreter', 'assisted'),
    ('workflow_classifier', 'Workflow Classifier', 'Worker que clasifica flujos de trabajo', 'classifier', 'read_only'),
    ('approval_worker', 'Approval Worker', 'Worker que gestiona flujos de aprobacion', 'approval', 'approval_required'),
    ('sap_b1_desktop_worker', 'SAP B1 Desktop Worker', 'Worker de automatizacion desktop para SAP Business One', 'desktop', 'assisted'),
    ('meli_browser_worker', 'Mercado Libre Browser Worker', 'Worker de browser para operaciones en Mercado Libre', 'browser', 'assisted'),
    ('document_ocr_worker', 'Document OCR Worker', 'Worker de reconocimiento optico de documentos', 'api', 'read_only'),
    ('rag_retriever_worker', 'RAG Retriever Worker', 'Worker que recupera fragmentos de conocimiento para contexto', 'api', 'read_only'),
    ('notification_worker', 'Notification Worker', 'Worker que envia notificaciones multicanal', 'notification', 'execution')
on conflict (worker_code) do nothing;

-- ---------------------------------------------------------------------------
-- 13. Indices
-- ---------------------------------------------------------------------------

-- RBAC
create index if not exists idx_core_workspace_areas_workspace
    on core_workspace_areas (workspace_id);

create index if not exists idx_core_roles_workspace
    on core_roles (workspace_id);

create index if not exists idx_core_role_permissions_role
    on core_role_permissions (role_id);

create index if not exists idx_core_role_permissions_permission
    on core_role_permissions (permission_id);

create index if not exists idx_core_permission_profiles_workspace
    on core_permission_profiles (workspace_id);

create index if not exists idx_core_profile_permissions_profile
    on core_profile_permissions (profile_id);

create index if not exists idx_core_profile_permissions_permission
    on core_profile_permissions (permission_id);

create index if not exists idx_core_user_roles_user
    on core_user_roles (user_id);

create index if not exists idx_core_user_roles_role
    on core_user_roles (role_id);

create index if not exists idx_core_user_profiles_user
    on core_user_profiles (user_id);

create index if not exists idx_core_user_profiles_profile
    on core_user_profiles (profile_id);

create index if not exists idx_core_user_profiles_area
    on core_user_profiles (area_id)
    where area_id is not null;

-- Plans
create index if not exists idx_package_plan_features_plan
    on package_plan_features (plan_id);

create index if not exists idx_package_plan_features_feature
    on package_plan_features (feature_id);

create index if not exists idx_workspace_plan_subscriptions_workspace
    on workspace_plan_subscriptions (workspace_id);

create index if not exists idx_workspace_plan_subscriptions_plan
    on workspace_plan_subscriptions (plan_id);

create index if not exists idx_workspace_plan_subscriptions_status
    on workspace_plan_subscriptions (status);

-- Assistant instances
create index if not exists idx_assistant_instances_workspace
    on assistant_instances (workspace_id);

create index if not exists idx_assistant_instances_default_knowledge_scope
    on assistant_instances (default_knowledge_scope_id);

-- Automation packages
create index if not exists idx_automation_packages_workspace
    on automation_packages (workspace_id);

create index if not exists idx_automation_packages_assistant_instance
    on automation_packages (assistant_instance_id);

create index if not exists idx_automation_packages_plan_code
    on automation_packages (plan_code);

-- Workers
create index if not exists idx_worker_definitions_kind
    on worker_definitions (worker_kind);

create index if not exists idx_package_workers_workspace
    on package_workers (workspace_id);

create index if not exists idx_package_workers_package
    on package_workers (automation_package_id);

create index if not exists idx_package_workers_definition
    on package_workers (worker_definition_id);

create index if not exists idx_package_workers_knowledge_scope
    on package_workers (knowledge_scope_id)
    where knowledge_scope_id is not null;

create index if not exists idx_package_workers_mode
    on package_workers (mode);

-- Credential references
create index if not exists idx_credential_references_workspace
    on credential_references (workspace_id);

create index if not exists idx_credential_references_package
    on credential_references (automation_package_id)
    where automation_package_id is not null;

create index if not exists idx_credential_references_worker
    on credential_references (package_worker_id)
    where package_worker_id is not null;

create index if not exists idx_credential_references_type
    on credential_references (credential_type);

-- Knowledge
create index if not exists idx_knowledge_scopes_workspace
    on knowledge_scopes (workspace_id);

create index if not exists idx_knowledge_scopes_retrieval_mode
    on knowledge_scopes (retrieval_mode);

create index if not exists idx_knowledge_documents_scope
    on knowledge_documents (knowledge_scope_id);

create index if not exists idx_knowledge_documents_content_hash
    on knowledge_documents (content_hash);

create index if not exists idx_knowledge_chunks_document
    on knowledge_chunks (knowledge_document_id, chunk_index);

create index if not exists idx_knowledge_chunks_embedding_status
    on knowledge_chunks (embedding_status);

-- task_runs nuevos indices
create index if not exists idx_task_runs_automation_package
    on task_runs (automation_package_id)
    where automation_package_id is not null;

create index if not exists idx_task_runs_package_worker
    on task_runs (package_worker_id)
    where package_worker_id is not null;

create index if not exists idx_task_runs_area
    on task_runs (area_id)
    where area_id is not null;

create index if not exists idx_task_runs_assigned_user
    on task_runs (assigned_user_id)
    where assigned_user_id is not null;

create index if not exists idx_task_runs_approval_status
    on task_runs (approval_status)
    where approval_status is not null;
