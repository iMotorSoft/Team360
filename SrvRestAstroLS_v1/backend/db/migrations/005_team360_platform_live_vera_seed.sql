-- Team360 migration 005 - initial productive seed for Team360 Platform,
-- Team360.live and the commercial Vera diagnosis assistant.
--
-- Depends on migrations 001, 002, 003 and 004.
-- This is a configuration/seed migration only. It does not create schema.
-- No passwords, API keys, provider tokens or secret material are stored here.
--
-- Naming invariant:
--   Vera is a visible commercial name only.
--   Stable technical identifiers remain:
--     assistant_instance_code = team360_sales_diagnosis
--     package_code = pkg_sales_diagnosis
--     knowledge_scope_code = ks_team360_sales_diagnosis

do $$
declare
    v_platform_workspace_id uuid;
    v_site_workspace_id uuid;
    v_platform_admin_user_id uuid;
    v_client_admin_user_id uuid;
    v_platform_role_id uuid;
    v_client_role_id uuid;
    v_platform_profile_id uuid;
    v_client_profile_id uuid;
    v_knowledge_scope_id uuid;
    v_assistant_instance_id uuid;
    v_package_id uuid;
    v_worker record;
    v_worker_definition_id uuid;
    v_package_worker_id uuid;
begin
    -- Platform control context. There is no organizations table yet, so
    -- platform/customer separation is represented with workspace metadata.
    insert into core_workspaces (slug, display_name, timezone, status, metadata_jsonb, updated_at_utc)
    values (
        'team360_platform',
        'Team360 Platform',
        'UTC',
        'active',
        '{
          "workspace_kind": "platform_control",
          "platform_code": "team360_platform",
          "platform_name": "Team360 Platform"
        }'::jsonb,
        now()
    )
    on conflict (slug) do update set
        display_name = excluded.display_name,
        status = excluded.status,
        metadata_jsonb = core_workspaces.metadata_jsonb || excluded.metadata_jsonb,
        updated_at_utc = now()
    returning id into v_platform_workspace_id;

    -- First real customer/public-site workspace for the Team360 direct
    -- sales diagnosis assistant. The slug stays aligned with runtime/tests.
    insert into core_workspaces (slug, display_name, timezone, status, metadata_jsonb, updated_at_utc)
    values (
        'team360_public_site',
        'Team360.live Public Site',
        'UTC',
        'active',
        '{
          "workspace_kind": "customer_public_site",
          "organization_code": "team360_live",
          "organization_name": "Team360.live",
          "organization_type": "direct_client",
          "parent_platform_code": "team360_platform",
          "site_channel": "team360.live",
          "public_channel_code": "team360_live_home"
        }'::jsonb,
        now()
    )
    on conflict (slug) do update set
        display_name = excluded.display_name,
        status = excluded.status,
        metadata_jsonb = core_workspaces.metadata_jsonb || excluded.metadata_jsonb,
        updated_at_utc = now()
    returning id into v_site_workspace_id;

    -- Users are idempotent by email at application/seed level; core_users
    -- does not currently enforce an email unique constraint.
    insert into core_users (workspace_id, email, display_name, role, status, metadata_jsonb, updated_at_utc)
    select
        v_platform_workspace_id,
        'mario.rojas@alquimiablue.com',
        'Mario Rojas',
        'platform_admin',
        'active',
        '{
          "user_kind": "platform_admin",
          "platform_code": "team360_platform"
        }'::jsonb,
        now()
    where not exists (
        select 1 from core_users where lower(email) = lower('mario.rojas@alquimiablue.com')
    );

    update core_users
    set
        workspace_id = v_platform_workspace_id,
        display_name = 'Mario Rojas',
        role = 'platform_admin',
        status = 'active',
        metadata_jsonb = metadata_jsonb || '{
          "user_kind": "platform_admin",
          "platform_code": "team360_platform"
        }'::jsonb,
        updated_at_utc = now()
    where lower(email) = lower('mario.rojas@alquimiablue.com');

    select id into v_platform_admin_user_id
    from core_users
    where lower(email) = lower('mario.rojas@alquimiablue.com')
    order by created_at_utc
    limit 1;

    insert into core_users (workspace_id, email, display_name, role, status, metadata_jsonb, updated_at_utc)
    select
        v_site_workspace_id,
        'mario.rojas.marconi@gmail.com',
        'Mario Rojas Marconi',
        'client_admin',
        'active',
        '{
          "user_kind": "client_admin",
          "organization_code": "team360_live",
          "workspace_slug": "team360_public_site"
        }'::jsonb,
        now()
    where not exists (
        select 1 from core_users where lower(email) = lower('mario.rojas.marconi@gmail.com')
    );

    update core_users
    set
        workspace_id = v_site_workspace_id,
        display_name = 'Mario Rojas Marconi',
        role = 'client_admin',
        status = 'active',
        metadata_jsonb = metadata_jsonb || '{
          "user_kind": "client_admin",
          "organization_code": "team360_live",
          "workspace_slug": "team360_public_site"
        }'::jsonb,
        updated_at_utc = now()
    where lower(email) = lower('mario.rojas.marconi@gmail.com');

    select id into v_client_admin_user_id
    from core_users
    where lower(email) = lower('mario.rojas.marconi@gmail.com')
    order by created_at_utc
    limit 1;

    insert into core_permissions (permission_code, display_name, category)
    values
        ('platform.manage', 'Gestionar plataforma', 'platform'),
        ('organizations.read', 'Ver organizaciones', 'organization'),
        ('organizations.manage', 'Gestionar organizaciones', 'organization'),
        ('workspaces.read', 'Ver workspaces', 'workspace'),
        ('workspaces.switch', 'Cambiar workspace activo', 'workspace'),
        ('services.read', 'Ver servicios', 'service'),
        ('services.manage', 'Gestionar servicios', 'service'),
        ('assistant.configure', 'Configurar assistant instances', 'assistant'),
        ('diagnosis.session.read', 'Ver sesiones de diagnostico', 'diagnosis'),
        ('diagnosis.lead.read', 'Ver leads de diagnostico', 'diagnosis'),
        ('diagnosis.lead.manage', 'Gestionar leads de diagnostico', 'diagnosis')
    on conflict (permission_code) do nothing;

    insert into core_roles (workspace_id, role_code, display_name, description, is_system_role, status, updated_at_utc)
    values (
        null,
        'platform_admin',
        'Platform Admin',
        'Administracion global de Team360 Platform',
        true,
        'active',
        now()
    )
    on conflict (role_code) where workspace_id is null do update set
        display_name = excluded.display_name,
        description = excluded.description,
        is_system_role = excluded.is_system_role,
        status = excluded.status,
        updated_at_utc = now()
    returning id into v_platform_role_id;

    insert into core_roles (workspace_id, role_code, display_name, description, is_system_role, status, updated_at_utc)
    values (
        v_site_workspace_id,
        'client_admin',
        'Client Admin',
        'Administracion cliente para Team360.live',
        true,
        'active',
        now()
    )
    on conflict (workspace_id, role_code) where workspace_id is not null do update set
        display_name = excluded.display_name,
        description = excluded.description,
        is_system_role = excluded.is_system_role,
        status = excluded.status,
        updated_at_utc = now()
    returning id into v_client_role_id;

    insert into core_permission_profiles (workspace_id, profile_code, display_name, description, status, updated_at_utc)
    values (
        null,
        'platform_admin',
        'Platform Admin',
        'Perfil global para administrar Team360 Platform',
        'active',
        now()
    )
    on conflict (profile_code) where workspace_id is null do update set
        display_name = excluded.display_name,
        description = excluded.description,
        status = excluded.status,
        updated_at_utc = now()
    returning id into v_platform_profile_id;

    insert into core_permission_profiles (workspace_id, profile_code, display_name, description, status, updated_at_utc)
    values (
        v_site_workspace_id,
        'client_admin',
        'Client Admin',
        'Perfil cliente para administrar el servicio Vera de Team360.live',
        'active',
        now()
    )
    on conflict (workspace_id, profile_code) where workspace_id is not null do update set
        display_name = excluded.display_name,
        description = excluded.description,
        status = excluded.status,
        updated_at_utc = now()
    returning id into v_client_profile_id;

    insert into core_role_permissions (role_id, permission_id)
    select v_platform_role_id, p.id
    from core_permissions p
    where p.permission_code in (
        'platform.manage',
        'organizations.read',
        'organizations.manage',
        'workspaces.read',
        'workspaces.switch',
        'services.read',
        'services.manage',
        'package.view',
        'package.configure',
        'worker.view',
        'worker.configure',
        'knowledge.view',
        'knowledge.upload',
        'assistant.configure',
        'diagnosis.session.read',
        'diagnosis.lead.read',
        'diagnosis.lead.manage',
        'audit.view',
        'user.manage',
        'role.manage'
    )
    on conflict (role_id, permission_id) do nothing;

    insert into core_role_permissions (role_id, permission_id)
    select v_client_role_id, p.id
    from core_permissions p
    where p.permission_code in (
        'workspaces.read',
        'services.read',
        'knowledge.view',
        'diagnosis.session.read',
        'diagnosis.lead.read',
        'diagnosis.lead.manage',
        'audit.view'
    )
    on conflict (role_id, permission_id) do nothing;

    insert into core_profile_permissions (profile_id, permission_id)
    select v_platform_profile_id, p.id
    from core_permissions p
    where p.permission_code in (
        'platform.manage',
        'organizations.read',
        'organizations.manage',
        'workspaces.read',
        'workspaces.switch',
        'services.read',
        'services.manage',
        'package.view',
        'package.configure',
        'worker.view',
        'worker.configure',
        'knowledge.view',
        'knowledge.upload',
        'assistant.configure',
        'diagnosis.session.read',
        'diagnosis.lead.read',
        'diagnosis.lead.manage',
        'audit.view',
        'user.manage',
        'role.manage'
    )
    on conflict (profile_id, permission_id) do nothing;

    insert into core_profile_permissions (profile_id, permission_id)
    select v_client_profile_id, p.id
    from core_permissions p
    where p.permission_code in (
        'workspaces.read',
        'services.read',
        'knowledge.view',
        'diagnosis.session.read',
        'diagnosis.lead.read',
        'diagnosis.lead.manage',
        'audit.view'
    )
    on conflict (profile_id, permission_id) do nothing;

    insert into core_user_roles (user_id, role_id)
    values
        (v_platform_admin_user_id, v_platform_role_id),
        (v_client_admin_user_id, v_client_role_id)
    on conflict (user_id, role_id) do nothing;

    insert into core_user_profiles (user_id, profile_id, area_id)
    values
        (v_platform_admin_user_id, v_platform_profile_id, null),
        (v_client_admin_user_id, v_client_profile_id, null)
    on conflict do nothing;

    insert into knowledge_scopes (
        workspace_id,
        scope_code,
        name,
        retrieval_mode,
        graph_enabled,
        settings_jsonb,
        status,
        updated_at_utc
    )
    values (
        v_site_workspace_id,
        'ks_team360_sales_diagnosis',
        'Team360 Sales Diagnosis Knowledge',
        'rag',
        false,
        '{
          "organization_code": "team360_live",
          "assistant_instance_code": "team360_sales_diagnosis",
          "package_code": "pkg_sales_diagnosis",
          "visible_offer": "Asistente Inteligente Vera",
          "commercial_name": "Vera",
          "template_code": "team360_sales_automation_diagnosis",
          "site_channel": "team360.live",
          "runtime_targets": {
            "arangodb": "future_source_text_graph",
            "milvus": "future_vector_index",
            "pgvector": "available_fallback_not_primary"
          }
        }'::jsonb,
        'active',
        now()
    )
    on conflict (workspace_id, scope_code) where workspace_id is not null do update set
        name = excluded.name,
        retrieval_mode = excluded.retrieval_mode,
        graph_enabled = excluded.graph_enabled,
        settings_jsonb = knowledge_scopes.settings_jsonb || excluded.settings_jsonb,
        status = excluded.status,
        updated_at_utc = now()
    returning id into v_knowledge_scope_id;

    insert into assistant_instances (
        workspace_id,
        assistant_code,
        assistant_type,
        name,
        status,
        public_config_jsonb,
        default_knowledge_scope_id,
        settings_jsonb,
        updated_at_utc
    )
    values (
        v_site_workspace_id,
        'team360_sales_diagnosis',
        'sales_diagnosis',
        'Asistente Inteligente Vera',
        'active',
        '{
          "display_name": "Vera",
          "commercial_name": "Asistente Inteligente Vera",
          "service_display_name": "Asistente Inteligente Vera",
          "site_channel": "team360.live",
          "public_channel_code": "team360_live_home",
          "default_locale": "es",
          "supported_locales": ["es", "en"]
        }'::jsonb,
        v_knowledge_scope_id,
        '{
          "assistant_instance_code": "team360_sales_diagnosis",
          "package_code": "pkg_sales_diagnosis",
          "knowledge_scope_code": "ks_team360_sales_diagnosis",
          "service_code": "svc_sales_diagnosis",
          "template_code": "team360_sales_automation_diagnosis",
          "display_name": "Vera",
          "commercial_name": "Asistente Inteligente Vera",
          "lead_owner": "Team360",
          "market": "direct"
        }'::jsonb,
        now()
    )
    on conflict (workspace_id, assistant_code) where assistant_code is not null do update set
        assistant_type = excluded.assistant_type,
        name = excluded.name,
        status = excluded.status,
        public_config_jsonb = assistant_instances.public_config_jsonb || excluded.public_config_jsonb,
        default_knowledge_scope_id = excluded.default_knowledge_scope_id,
        settings_jsonb = assistant_instances.settings_jsonb || excluded.settings_jsonb,
        updated_at_utc = now()
    returning id into v_assistant_instance_id;

    insert into automation_packages (
        workspace_id,
        assistant_instance_id,
        package_code,
        package_name,
        plan_code,
        status,
        enabled_features_jsonb,
        settings_jsonb,
        updated_at_utc
    )
    values (
        v_site_workspace_id,
        v_assistant_instance_id,
        'pkg_sales_diagnosis',
        'Asistente Inteligente Vera',
        'starter',
        'active',
        '["diagnosis.basic", "rag.simple", "events.basic"]'::jsonb,
        '{
          "service_code": "svc_sales_diagnosis",
          "service_display_name": "Asistente Inteligente Vera",
          "package_display_name": "Asistente Inteligente Vera",
          "commercial_name": "Vera",
          "assistant_instance_code": "team360_sales_diagnosis",
          "knowledge_scope_code": "ks_team360_sales_diagnosis",
          "lead_owner": "Team360",
          "site_channel": "team360.live"
        }'::jsonb,
        now()
    )
    on conflict (workspace_id, package_code) do update set
        assistant_instance_id = excluded.assistant_instance_id,
        package_name = excluded.package_name,
        status = excluded.status,
        enabled_features_jsonb = excluded.enabled_features_jsonb,
        settings_jsonb = automation_packages.settings_jsonb || excluded.settings_jsonb,
        updated_at_utc = now()
    returning id into v_package_id;

    insert into knowledge_scope_bindings (
        knowledge_scope_id,
        workspace_id,
        binding_type,
        bound_entity_id,
        is_default,
        metadata_jsonb
    )
    values
        (
            v_knowledge_scope_id,
            v_site_workspace_id,
            'workspace',
            v_site_workspace_id,
            true,
            '{"workspace_slug": "team360_public_site"}'::jsonb
        ),
        (
            v_knowledge_scope_id,
            v_site_workspace_id,
            'assistant_instance',
            v_assistant_instance_id,
            true,
            '{"assistant_instance_code": "team360_sales_diagnosis"}'::jsonb
        ),
        (
            v_knowledge_scope_id,
            v_site_workspace_id,
            'automation_package',
            v_package_id,
            true,
            '{"package_code": "pkg_sales_diagnosis"}'::jsonb
        )
    on conflict do nothing;

    for v_worker in
        select *
        from (
            values
                ('pw_team360_guided_intake', 'guided_intake_worker', 'assisted', false),
                ('pw_team360_lead_qualification', 'lead_qualification_worker', 'assisted', false),
                ('pw_team360_knowledge_retrieval', 'knowledge_retrieval_worker', 'read_only', false),
                ('pw_team360_diagnosis_scoring', 'diagnosis_scoring_worker', 'read_only', false),
                ('pw_team360_package_recommendation', 'package_recommendation_worker', 'assisted', false),
                ('pw_team360_proposal_outline', 'proposal_outline_worker', 'assisted', false),
                ('pw_team360_crm_handoff', 'crm_handoff_worker', 'assisted', false),
                ('pw_team360_calendar_handoff', 'calendar_handoff_worker', 'assisted', false),
                ('pw_team360_agui_render', 'agui_render_worker', 'read_only', false)
        ) as workers(package_worker_code, worker_definition_code, mode, requires_human_approval)
    loop
        select id into v_worker_definition_id
        from worker_definitions
        where worker_code = v_worker.worker_definition_code;

        if v_worker_definition_id is null then
            raise exception 'Missing worker_definition seed: %', v_worker.worker_definition_code;
        end if;

        insert into package_workers (
            workspace_id,
            automation_package_id,
            worker_definition_id,
            package_worker_code,
            status,
            mode,
            knowledge_scope_id,
            updated_at_utc
        )
        values (
            v_site_workspace_id,
            v_package_id,
            v_worker_definition_id,
            v_worker.package_worker_code,
            'active',
            v_worker.mode,
            v_knowledge_scope_id,
            now()
        )
        on conflict (automation_package_id, package_worker_code) do update set
            worker_definition_id = excluded.worker_definition_id,
            status = excluded.status,
            mode = excluded.mode,
            knowledge_scope_id = excluded.knowledge_scope_id,
            updated_at_utc = now()
        returning id into v_package_worker_id;

        insert into package_worker_configs (
            package_worker_id,
            config_jsonb,
            allowed_actions_jsonb,
            blocked_actions_jsonb,
            limits_jsonb,
            requires_human_approval,
            updated_at_utc
        )
        values (
            v_package_worker_id,
            jsonb_build_object(
                'assistant_instance_code', 'team360_sales_diagnosis',
                'package_code', 'pkg_sales_diagnosis',
                'knowledge_scope_code', 'ks_team360_sales_diagnosis',
                'commercial_name', 'Vera'
            ),
            '[]'::jsonb,
            '["bypass_mfa", "bypass_2fa", "bypass_hardware_key", "irreversible_financial_write"]'::jsonb,
            '{}'::jsonb,
            v_worker.requires_human_approval,
            now()
        )
        on conflict (package_worker_id) do update set
            config_jsonb = excluded.config_jsonb,
            allowed_actions_jsonb = excluded.allowed_actions_jsonb,
            blocked_actions_jsonb = excluded.blocked_actions_jsonb,
            limits_jsonb = excluded.limits_jsonb,
            requires_human_approval = excluded.requires_human_approval,
            updated_at_utc = now();

        insert into knowledge_scope_bindings (
            knowledge_scope_id,
            workspace_id,
            binding_type,
            bound_entity_id,
            is_default,
            metadata_jsonb
        )
        values (
            v_knowledge_scope_id,
            v_site_workspace_id,
            'package_worker',
            v_package_worker_id,
            false,
            jsonb_build_object(
                'package_worker_code', v_worker.package_worker_code,
                'worker_definition_code', v_worker.worker_definition_code
            )
        )
        on conflict do nothing;
    end loop;

    insert into workspace_plan_subscriptions (workspace_id, plan_id, status, metadata_jsonb, updated_at_utc)
    select
        v_site_workspace_id,
        pp.id,
        'active',
        '{"package_code": "pkg_sales_diagnosis", "commercial_name": "Vera"}'::jsonb,
        now()
    from package_plans pp
    where pp.plan_code = 'starter'
      and not exists (
          select 1
          from workspace_plan_subscriptions existing
          where existing.workspace_id = v_site_workspace_id
            and existing.status = 'active'
      );

    insert into core_events (
        workspace_id,
        event_name,
        entity_type,
        entity_id,
        correlation_id,
        payload_jsonb,
        occurred_at_utc
    )
    select
        v_site_workspace_id,
        'team360.platform_live_vera_seeded',
        'assistant_instance',
        v_assistant_instance_id,
        'seed_005_team360_platform_live_vera',
        '{
          "assistant_instance_code": "team360_sales_diagnosis",
          "package_code": "pkg_sales_diagnosis",
          "knowledge_scope_code": "ks_team360_sales_diagnosis",
          "commercial_name": "Vera"
        }'::jsonb,
        now()
    where not exists (
        select 1
        from core_events
        where workspace_id = v_site_workspace_id
          and event_name = 'team360.platform_live_vera_seeded'
          and correlation_id = 'seed_005_team360_platform_live_vera'
    );
end $$;
