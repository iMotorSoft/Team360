-- Team360 migration 007 — Core organizations and ingestion ownership.
--
-- Adds the minimal organizational root needed by Knowledge Ingestion so
-- ingestion can resolve:
--   organization -> workspace -> package / assistant_instance
--   -> knowledge_scope -> ingestion_runs
--
-- This migration does NOT:
--   - Recreate core_users (it already exists from migration 001)
--   - Implement auth, login, passwords, OAuth or sessions
--   - Create services, CRM, billing, partner portal or UI
--   - Create KnowledgeMap / KnowledgeNode
--   - Activate ArangoDB, Milvus, embeddings or document/chunk ingestion
--   - Touch automation_diagnosis runtime
--
-- Depends on migrations 001, 002, 003, 004, 005 and 006.

-- ---------------------------------------------------------------------------
-- 1. Evolve core_users without breaking historical rows
-- ---------------------------------------------------------------------------

-- core_users exists since migration 001. Keep existing columns, nullable email,
-- workspace_id and role. Extend status values for organization identity usage.
do $$
begin
    alter table core_users drop constraint if exists chk_core_users_status;
    alter table core_users add constraint chk_core_users_status
        check (status in (
            'invited', 'active', 'inactive', 'testing', 'retired', 'archived'
        ));
end $$;

create unique index if not exists uq_core_users_email_lower_present
    on core_users (lower(email))
    where email is not null;

-- ---------------------------------------------------------------------------
-- 2. Core organizations
-- ---------------------------------------------------------------------------

create table if not exists core_organizations (
    id uuid primary key default gen_random_uuid(),
    organization_code text unique not null,
    display_name text not null,
    primary_type text not null,
    status text not null default 'active',
    parent_organization_id uuid references core_organizations(id) on delete set null,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint chk_core_organizations_primary_type
        check (primary_type in (
            'platform_owner', 'partner', 'client',
            'internal_client', 'demo_client'
        )),
    constraint chk_core_organizations_status
        check (status in ('active', 'inactive', 'archived'))
);

create index if not exists idx_core_organizations_parent
    on core_organizations (parent_organization_id);

create index if not exists idx_core_organizations_primary_type
    on core_organizations (primary_type);

create table if not exists core_organization_roles (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references core_organizations(id) on delete cascade,
    role_code text not null,
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_core_organization_roles_code
        unique (organization_id, role_code),
    constraint chk_core_organization_roles_status
        check (status in ('active', 'inactive', 'archived'))
);

create index if not exists idx_core_organization_roles_org
    on core_organization_roles (organization_id);

create table if not exists core_organization_members (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references core_organizations(id) on delete cascade,
    user_id uuid not null references core_users(id) on delete cascade,
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_core_organization_members_user
        unique (organization_id, user_id),
    constraint chk_core_organization_members_status
        check (status in ('active', 'inactive', 'archived'))
);

create index if not exists idx_core_organization_members_org
    on core_organization_members (organization_id);

create index if not exists idx_core_organization_members_user
    on core_organization_members (user_id);

create table if not exists core_organization_member_roles (
    id uuid primary key default gen_random_uuid(),
    organization_member_id uuid not null references core_organization_members(id) on delete cascade,
    role_code text not null,
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_core_organization_member_roles_code
        unique (organization_member_id, role_code),
    constraint chk_core_organization_member_roles_status
        check (status in ('active', 'inactive', 'archived'))
);

create index if not exists idx_core_organization_member_roles_member
    on core_organization_member_roles (organization_member_id);

-- ---------------------------------------------------------------------------
-- 3. Organization links for workspaces and ingestion runs
-- ---------------------------------------------------------------------------

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'core_workspaces'
          and column_name = 'organization_id'
    ) then
        alter table core_workspaces add column organization_id uuid;
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_core_workspaces_organization'
          and conrelid = 'core_workspaces'::regclass
    ) then
        alter table core_workspaces
            add constraint fk_core_workspaces_organization
            foreign key (organization_id)
            references core_organizations(id)
            on delete set null;
    end if;
end $$;

create index if not exists idx_core_workspaces_organization
    on core_workspaces (organization_id);

do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'knowledge_ingestion_runs'
          and column_name = 'organization_id'
    ) then
        alter table knowledge_ingestion_runs add column organization_id uuid;
    end if;

    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public'
          and table_name = 'knowledge_ingestion_runs'
          and column_name = 'triggered_by_user_id'
    ) then
        alter table knowledge_ingestion_runs add column triggered_by_user_id uuid;
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_kir_organization'
          and conrelid = 'knowledge_ingestion_runs'::regclass
    ) then
        alter table knowledge_ingestion_runs
            add constraint fk_kir_organization
            foreign key (organization_id)
            references core_organizations(id)
            on delete set null;
    end if;

    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_kir_triggered_by_user'
          and conrelid = 'knowledge_ingestion_runs'::regclass
    ) then
        alter table knowledge_ingestion_runs
            add constraint fk_kir_triggered_by_user
            foreign key (triggered_by_user_id)
            references core_users(id)
            on delete set null;
    end if;
end $$;

create index if not exists idx_kir_organization
    on knowledge_ingestion_runs (organization_id);

create index if not exists idx_kir_triggered_by_user
    on knowledge_ingestion_runs (triggered_by_user_id);

-- ---------------------------------------------------------------------------
-- 4. Minimal production seeds
-- ---------------------------------------------------------------------------

do $$
declare
    v_platform_org_id uuid;
    v_live_org_id uuid;
    v_platform_user_id uuid;
    v_live_user_id uuid;
    v_member_id uuid;
    v_role text;
begin
    insert into core_organizations (
        organization_code,
        display_name,
        primary_type,
        status,
        metadata_jsonb,
        updated_at_utc
    ) values (
        'team360_platform',
        'Team360 Platform',
        'platform_owner',
        'active',
        '{"seed": "007_team360_core_organizations_users"}'::jsonb,
        now()
    )
    on conflict (organization_code) do update set
        display_name = excluded.display_name,
        primary_type = excluded.primary_type,
        status = excluded.status,
        metadata_jsonb = core_organizations.metadata_jsonb || excluded.metadata_jsonb,
        updated_at_utc = now()
    returning id into v_platform_org_id;

    insert into core_organizations (
        organization_code,
        display_name,
        primary_type,
        status,
        parent_organization_id,
        metadata_jsonb,
        updated_at_utc
    ) values (
        'team360_live',
        'Team360.live',
        'internal_client',
        'active',
        v_platform_org_id,
        '{"seed": "007_team360_core_organizations_users"}'::jsonb,
        now()
    )
    on conflict (organization_code) do update set
        display_name = excluded.display_name,
        primary_type = excluded.primary_type,
        status = excluded.status,
        parent_organization_id = excluded.parent_organization_id,
        metadata_jsonb = core_organizations.metadata_jsonb || excluded.metadata_jsonb,
        updated_at_utc = now()
    returning id into v_live_org_id;

    foreach v_role in array array[
        'platform_owner', 'platform_admin', 'service_provider', 'technical_operator'
    ]
    loop
        insert into core_organization_roles (
            organization_id,
            role_code,
            status,
            metadata_jsonb,
            updated_at_utc
        ) values (
            v_platform_org_id,
            v_role,
            'active',
            '{"role_scope": "organization_capability"}'::jsonb,
            now()
        )
        on conflict (organization_id, role_code) do update set
            status = excluded.status,
            metadata_jsonb = core_organization_roles.metadata_jsonb || excluded.metadata_jsonb,
            updated_at_utc = now();
    end loop;

    foreach v_role in array array[
        'internal_client', 'demo_client', 'content_owner', 'client'
    ]
    loop
        insert into core_organization_roles (
            organization_id,
            role_code,
            status,
            metadata_jsonb,
            updated_at_utc
        ) values (
            v_live_org_id,
            v_role,
            'active',
            '{"role_scope": "organization_capability"}'::jsonb,
            now()
        )
        on conflict (organization_id, role_code) do update set
            status = excluded.status,
            metadata_jsonb = core_organization_roles.metadata_jsonb || excluded.metadata_jsonb,
            updated_at_utc = now();
    end loop;

    insert into core_users (
        email,
        display_name,
        status,
        metadata_jsonb,
        updated_at_utc
    )
    select
        'mario.rojas@alquimiablue.com',
        'Mario Rojas',
        'active',
        '{"identity_seed": "007_team360_core_organizations_users"}'::jsonb,
        now()
    where not exists (
        select 1 from core_users
        where lower(email) = lower('mario.rojas@alquimiablue.com')
    );

    update core_users
    set
        display_name = 'Mario Rojas',
        status = 'active',
        metadata_jsonb = metadata_jsonb || '{"identity_seed": "007_team360_core_organizations_users"}'::jsonb,
        updated_at_utc = now()
    where lower(email) = lower('mario.rojas@alquimiablue.com');

    select id into v_platform_user_id
    from core_users
    where lower(email) = lower('mario.rojas@alquimiablue.com')
    order by created_at_utc
    limit 1;

    insert into core_users (
        email,
        display_name,
        status,
        metadata_jsonb,
        updated_at_utc
    )
    select
        'mario.rojas.marconi@gmail.com',
        'Mario Rojas Marconi',
        'active',
        '{"identity_seed": "007_team360_core_organizations_users"}'::jsonb,
        now()
    where not exists (
        select 1 from core_users
        where lower(email) = lower('mario.rojas.marconi@gmail.com')
    );

    update core_users
    set
        display_name = 'Mario Rojas Marconi',
        status = 'active',
        metadata_jsonb = metadata_jsonb || '{"identity_seed": "007_team360_core_organizations_users"}'::jsonb,
        updated_at_utc = now()
    where lower(email) = lower('mario.rojas.marconi@gmail.com');

    select id into v_live_user_id
    from core_users
    where lower(email) = lower('mario.rojas.marconi@gmail.com')
    order by created_at_utc
    limit 1;

    insert into core_organization_members (
        organization_id,
        user_id,
        status,
        metadata_jsonb,
        updated_at_utc
    ) values (
        v_platform_org_id,
        v_platform_user_id,
        'active',
        '{"membership_seed": "007_team360_core_organizations_users"}'::jsonb,
        now()
    )
    on conflict (organization_id, user_id) do update set
        status = excluded.status,
        metadata_jsonb = core_organization_members.metadata_jsonb || excluded.metadata_jsonb,
        updated_at_utc = now()
    returning id into v_member_id;

    foreach v_role in array array[
        'organization_owner', 'organization_admin', 'technical_admin'
    ]
    loop
        insert into core_organization_member_roles (
            organization_member_id,
            role_code,
            status,
            metadata_jsonb,
            updated_at_utc
        ) values (
            v_member_id,
            v_role,
            'active',
            '{"role_scope": "organization_member"}'::jsonb,
            now()
        )
        on conflict (organization_member_id, role_code) do update set
            status = excluded.status,
            metadata_jsonb = core_organization_member_roles.metadata_jsonb || excluded.metadata_jsonb,
            updated_at_utc = now();
    end loop;

    insert into core_organization_members (
        organization_id,
        user_id,
        status,
        metadata_jsonb,
        updated_at_utc
    ) values (
        v_live_org_id,
        v_live_user_id,
        'active',
        '{"membership_seed": "007_team360_core_organizations_users"}'::jsonb,
        now()
    )
    on conflict (organization_id, user_id) do update set
        status = excluded.status,
        metadata_jsonb = core_organization_members.metadata_jsonb || excluded.metadata_jsonb,
        updated_at_utc = now()
    returning id into v_member_id;

    foreach v_role in array array[
        'organization_owner', 'organization_admin', 'content_admin'
    ]
    loop
        insert into core_organization_member_roles (
            organization_member_id,
            role_code,
            status,
            metadata_jsonb,
            updated_at_utc
        ) values (
            v_member_id,
            v_role,
            'active',
            '{"role_scope": "organization_member"}'::jsonb,
            now()
        )
        on conflict (organization_member_id, role_code) do update set
            status = excluded.status,
            metadata_jsonb = core_organization_member_roles.metadata_jsonb || excluded.metadata_jsonb,
            updated_at_utc = now();
    end loop;

    update core_workspaces
    set organization_id = v_platform_org_id,
        updated_at_utc = now(),
        metadata_jsonb = metadata_jsonb || '{"organization_code": "team360_platform"}'::jsonb
    where slug = 'team360_platform';

    update core_workspaces
    set organization_id = v_live_org_id,
        updated_at_utc = now(),
        metadata_jsonb = metadata_jsonb || '{"organization_code": "team360_live"}'::jsonb
    where slug = 'team360_public_site';
end $$;
