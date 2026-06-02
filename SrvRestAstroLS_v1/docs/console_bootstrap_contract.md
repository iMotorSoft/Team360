# ConsoleBootstrap Contract

Fecha: 2026-06-02

Estado: diseno de contrato. No implementa endpoint, repositories, DB ni migraciones.

## 1. Objetivo del contrato

`ConsoleBootstrap` es el DTO que la API backend sirve como carga inicial de Team360 Console.

Objetivos:

- **Carga inicial unica:** el frontend recibe todo lo que necesita para pintar el App Shell, la navegacion, el sidebar, las capacidades y el estado contextual en una sola respuesta.
- **Vista filtrada y segura:** el backend decide que datos son visibles segun usuario autenticado, workspace solicitado, membresias, permisos y tipo de organizacion. El frontend no reconstruye reglas criticas de autorizacion.
- **Read-only:** este contrato nunca expone mutaciones, secretos ni configuracion interna de workers o credenciales.
- **Tipado compartido:** la forma del contrato se documenta como JSON y se refleja en tipos Python (TypedDicts) para uso interno, sin Pydantic como requisito.

## 2. Endpoint futuro propuesto

**Recomendacion:** `GET /api/workspaces/{workspace_id}/console/bootstrap`

```
GET /api/workspaces/{workspace_id}/console/bootstrap
```

Razon:

- El workspace es la unidad de contexto de Console: navegacion, servicios, permisos y tareas se resuelven dentro de un workspace.
- REST semantico: el recurso es el workspace, y `console/bootstrap` es una subresource que devuelve su contexto operativo.
- Permite validar ownership del workspace en el path antes de ejecutar la consulta compuesta.
- El frontend ya usa `workspace_id` en todas las rutas (`/w/:workspaceId`).
- Mas facil de cachear por workspace.
- Evita query params largos y mezcla de responsabilidades.

Alternativa descartada:
- `GET /api/console/bootstrap?workspace_id=...` -- menos RESTful, no comunica claramente que el recurso principal es el workspace.

Headers requeridos:
- `Authorization: Bearer <session_token>`
- `Accept: application/json`

Respuesta esperada:
- `200 OK` con body `ConsoleBootstrap`
- `401 Unauthorized`
- `403 Forbidden` -- workspace no autorizado
- `404 Not Found` -- workspace inexistente

## 3. DTO JSON completo de ejemplo

```json
{
  "workspace": {
    "workspace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "workspace_code": "ws-carmel-retail",
    "display_name": "Carmel Retail",
    "workspace_type": "client",
    "status": "active"
  },
  "current_user": {
    "user_id": "user-uuid-0001",
    "display_name": "Israel Sajar",
    "email": "israel@example.com",
    "user_type": "internal",
    "area_id": null,
    "roles": [
      {
        "role_id": "role-uuid-team360-admin",
        "role_code": "team360_admin",
        "display_name": "Team360 Admin"
      }
    ],
    "permission_profiles": [
      {
        "profile_id": "profile-uuid-full-access",
        "profile_code": "full_access",
        "display_name": "Acceso Completo"
      }
    ]
  },
  "effective_permissions": [
    "dashboard.view",
    "task.view",
    "task.assign",
    "task.approve",
    "package.view",
    "worker.view",
    "knowledge.view",
    "audit.view",
    "user.manage"
  ],
  "capabilities": [
    "can_view_dashboard",
    "can_view_services",
    "can_view_tasks",
    "can_view_workers",
    "can_view_runs",
    "can_view_reports",
    "can_view_alerts",
    "can_manage_users",
    "can_switch_workspace",
    "can_view_knowledge"
  ],
  "entitlements": {
    "plan_code": "premium_erp",
    "plan_display_name": "Premium ERP",
    "features": [
      "diagnosis.basic",
      "dashboard.basic",
      "dashboard.by_area",
      "rag.simple",
      "graphrag.enabled",
      "approval.basic",
      "approval.multi_level",
      "events.basic",
      "audit.advanced",
      "workers.internal",
      "workers.external",
      "package_worker.config",
      "erp.read_only",
      "erp.assisted",
      "erp.write_approval",
      "marketplace.ops",
      "crm.integration"
    ]
  },
  "navigation": [
    {
      "group": "Plataforma",
      "items": [
        { "id": "dashboard", "label": "Dashboard", "route": "/w/a1b2.../dashboard", "icon": "home" },
        { "id": "services", "label": "Servicios", "route": "/w/a1b2.../services", "icon": "package" }
      ]
    },
    {
      "group": "Operacion",
      "items": [
        { "id": "tasks", "label": "Tareas", "route": "/w/a1b2.../tasks", "icon": "checklist" },
        { "id": "alerts", "label": "Alertas", "route": "/w/a1b2.../alerts", "icon": "bell" },
        { "id": "reports", "label": "Reportes", "route": "/w/a1b2.../reports", "icon": "chart" }
      ]
    },
    {
      "group": "Tecnico",
      "visibility_level": "internal",
      "items": [
        { "id": "workers", "label": "Workers", "route": "/w/a1b2.../workers", "icon": "cpu" },
        { "id": "runs", "label": "Ejecuciones", "route": "/w/a1b2.../runs", "icon": "activity" }
      ]
    }
  ],
  "services": [
    {
      "service_id": "svc-uuid-carmel-leads",
      "package_id": "pkg-uuid-carmel-continuity",
      "package_code": "continuity_comercial",
      "package_name": "Continuidad Comercial",
      "display_name": "Seguimiento de leads y WhatsApp",
      "status": "active",
      "health": "healthy",
      "plan_code": "operational",
      "category": "sales_operations",
      "summary": "Ordena consultas comerciales y pendientes de seguimiento para el equipo de ventas.",
      "client_summary": "Ayuda a sostener el seguimiento comercial y reducir oportunidades sin respuesta.",
      "task_summary": {
        "pending": 3,
        "waiting_approval": 1,
        "failed": 0,
        "completed_today": 12,
        "blocked_by_policy": 0
      },
      "has_knowledge": true,
      "has_workers_visible": true,
      "visibility_level": "client"
    }
  ],
  "tasks_summary": {
    "pending": 8,
    "waiting_approval": 2,
    "failed": 1,
    "completed_today": 24,
    "blocked_by_policy": 0
  },
  "alerts": [
    {
      "alert_id": "alert-uuid-001",
      "severity": "warning",
      "message": "Dos borradores de respuesta pendientes de aprobacion.",
      "target": "svc-netzaj-questions",
      "created_at_utc": "2026-06-02T10:30:00Z",
      "status": "open"
    }
  ],
  "workspace_context": {
    "active_area": null,
    "available_areas": [
      { "area_id": "area-uuid-ventas", "area_code": "ventas", "display_name": "Ventas" },
      { "area_id": "area-uuid-soporte", "area_code": "soporte", "display_name": "Soporte" }
    ],
    "selected_package": null
  },
  "organization_context": {
    "organization_id": "org-uuid-carmel-retail",
    "organization_code": "carmel-retail",
    "display_name": "Carmel Retail",
    "organization_type": "client",
    "parent_organization_id": null,
    "status": "active",
    "access_mode": "own",
    "delegated_by_organization_id": null
  },
  "debug": {
    "source": "backend",
    "permissions_evaluated": 9,
    "hidden_items_count": 2,
    "feature_flags": {
      "agui_enabled": false,
      "rtl_preview": true,
      "organization_switcher": false,
      "workspace_switcher": true
    }
  }
}
```

## 4. Mapeo DB a DTO

### workspace

| Campo DTO | Fuente DB |
|---|---|
| workspace_id | `core_workspaces.id` |
| workspace_code | `core_workspaces.workspace_code` o `slug` |
| display_name | `core_workspaces.display_name` |
| workspace_type | derivado: `core_workspaces.type` o segun migracion futura de organizaciones |
| status | `core_workspaces.status` |

### current_user

| Campo DTO | Fuente DB |
|---|---|
| user_id | `core_users.id` |
| display_name | `core_users.display_name` |
| email | `core_users.email` |
| user_type | `core_users.user_type` (segun schema 001) |
| area_id | `core_user_profiles.area_id` (join) |
| roles | `core_roles` via `core_user_roles` |
| permission_profiles | `core_permission_profiles` via `core_user_profiles` |

### effective_permissions

Derivado de la union de:
- `core_role_permissions.permission_id` -> `core_permissions.permission_code` via `core_user_roles`
- `core_profile_permissions.permission_id` -> `core_permissions.permission_code` via `core_user_profiles`

### capabilities

Capacidades UX derivadas desde `effective_permissions` + `entitlements` + tipo de organizacion.

Tabla de derivacion recomendada:

| Capability UX | Permiso requerido | Feature requerida | Nota |
|---|---|---|---|
| can_view_dashboard | dashboard.view | dashboard.basic | |
| can_view_services | package.view | — | |
| can_view_tasks | task.view | — | |
| can_view_workers | worker.view | workers.internal o workers.external | |
| can_view_runs | task.view | — | workers + runs |
| can_view_reports | — | dashboard.basic | reportes |
| can_view_alerts | — | events.basic | |
| can_manage_users | user.manage | — | |
| can_switch_workspace | — | — | si tiene > 1 workspace accesible |
| can_view_knowledge | knowledge.view | rag.simple | |

### entitlements

| Campo DTO | Fuente DB |
|---|---|
| plan_code | `package_plans.plan_code` via `workspace_plan_subscriptions` + `package_plans` |
| plan_display_name | `package_plans.display_name` |
| features | `package_features.feature_code` via `package_plan_features` + `package_plans` |

### services (automation_packages)

| Campo DTO | Fuente DB |
|---|---|
| service_id | `automation_packages.id` |
| package_id | `automation_packages.id` (mismo) |
| package_code | `automation_packages.package_code` |
| package_name | `automation_packages.package_name` |
| display_name | `automation_packages.package_name` o name para UX |
| status | `automation_packages.status` |
| health | derivado: segun estado de workers, `task_runs` recientes, alertas activas |
| plan_code | `automation_packages.plan_code` |
| category | derivado del paquete o `automation_packages.settings_jsonb` |
| summary | descripcion corta del paquete |
| client_summary | descripcion visible al cliente (puede ser subset de summary) |
| task_summary | agregacion desde `task_runs` filtrada por `automation_package_id` |
| has_knowledge | existe `knowledge_scope_bindings` vinculado a este paquete |
| has_workers_visible | existe `package_workers` activo bajo este paquete |
| visibility_level | `client` / `partner` / `internal` — segun features, plan y audiencia |

### tasks_summary

Agregacion de `task_runs` para el workspace activo:

| Campo | Filtro |
|---|---|
| pending | `status = 'pending'` |
| waiting_approval | `approval_status = 'pending'` |
| failed | `status = 'failed'` |
| completed_today | `status = 'completed'` AND `updated_at_utc >= today` |
| blocked_by_policy | `status = 'blocked'` o modo `blocked` segun `package_worker_configs` |

### alerts

Proyeccion inicial desde `core_events`:

| Campo DTO | Fuente DB |
|---|---|
| alert_id | `core_events.id` |
| severity | `core_events.severity` o level |
| message | `core_events.message` o description |
| target | `core_events.resource_type` + `resource_id` |
| created_at_utc | `core_events.created_at_utc` |
| status | `core_events.status` |

### workspace_context

Derivado de `core_workspace_areas` (areas) y contexto de sesion.

### organization_context

| Campo DTO | Fuente DB |
|---|---|
| organization_id | pendiente de migracion futura de organizaciones |
| organization_code | pendiente de migracion futura |
| display_name | pendiente de migracion futura |
| organization_type | pendiente de migracion futura |
| parent_organization_id | pendiente de migracion futura |
| status | pendiente de migracion futura |
| access_mode | `own` o `delegated` — derivado de membresia |
| delegated_by_organization_id | si access_mode es delegated |

**Nota:** `organization_context` depende de la migracion futura de organizaciones jerarquicas mencionada en `ux_console_backend_alignment.md`. Hasta entonces, se puede derivar parcialmente desde `core_workspaces.organization_id` si se agrega una tabla `organizations` en migracion 004.

### debug

Solo incluido para perfiles internos (`user_type = 'internal'` o permiso `audit.view`):

| Campo | Fuente |
|---|---|
| source | `"backend"` fijo |
| permissions_evaluated | count de `effective_permissions` |
| hidden_items_count | items de navigation, services o alerts filtrados |
| feature_flags | flags de UI derivados desde `entitlements` y perfil |

## 5. Seguridad

### Reglas obligatorias

1. **No devolver `secret_ref`** de `credential_references` bajo ninguna circunstancia.
2. **No devolver credenciales**, tokens, API keys ni passwords.
3. **No devolver payloads internos** de `package_worker_configs.config_jsonb`.
4. **No devolver workers tecnicos a cliente final** salvo permiso explicito `worker.view`.
5. **Filtrado en backend:** el backend decide visibilidad. El frontend recibe una vista ya filtrada. Ocultar en frontend es solo refuerzo visual, no control de acceso.
6. **Validacion de workspace:** el endpoint debe verificar que el usuario autenticado tenga membresia activa en el workspace solicitado.

### Visibilidad por audiencia

| Audiencia | Ve | No ve |
|---|---|---|
| Team360 internal | todo segun permisos | secretos |
| Team360 operator | servicios asignados, workers permitidos, runs, tareas, alertas | configuracion critica fuera de scope, credenciales |
| Partner admin | organizacion propia + subarbol, servicios, resultados, tareas | clientes laterales, workers internos, credenciales |
| Client admin | solo workspace propio, servicios contratados, resultados, tareas, soporte | workers, logs, payloads, credenciales |

### Debug

- La seccion `debug` solo se incluye si `user_type = 'internal'` o el permiso `audit.view` esta activo.
- `hidden_items_count` expresa cuantos items se filtraron en navigation, services o alerts.

## 6. TypedDicts Python (uso interno, sin Pydantic)

Los tipos internos se definen en `backend/modules/console/types.py` usando `TypedDict` y `dataclass` de la stdlib.

No importan Pydantic.
No requieren dependencias externas.
Son la fuente de verdad del contrato para repositories y servicios.

## 7. Repositories futuros (diseno)

Sin implementar. Nombres y responsabilidades:

| Repository | Responsabilidad | Metodos clave |
|---|---|---|
| `WorkspaceConsoleRepository` | Datos del workspace activo | `get_by_id(conn, workspace_id) -> WorkspaceDTO` |
| `PermissionConsoleRepository` | Roles, perfiles y permisos del usuario en el workspace | `get_effective_permissions(conn, user_id, workspace_id) -> list[str]` |
| `PackageConsoleRepository` | Paquetes activos del workspace con features y workers | `get_services(conn, workspace_id, user_id) -> list[ServiceDTO]` |
| `TaskConsoleRepository` | Resumen de tareas y alertas del workspace | `get_tasks_summary(conn, workspace_id) -> TasksSummary` / `get_alerts(conn, workspace_id) -> list[AlertDTO]` |
| `NavigationBuilder` | Construye arbol de navegacion desde capacidades | `build(capabilities, workspace_id, organization_type) -> list[NavGroup]` |
| `ConsoleBootstrapService` | Orquesta los 5 repos y construye el DTO completo | `get_bootstrap(conn, user_id, workspace_id) -> ConsoleBootstrap` |

No crear aun. Se implementaran en Fase C.

## 8. Fases

### Fase A — Contrato y tipos (esta fase)

- Documentar `console_bootstrap_contract.md`.
- Crear `backend/modules/console/types.py` con TypedDicts.
- Actualizar mocks frontend para alinearse al contrato (opcional aqui).
- Validar que los tipos compilan con `py_compile`.
- No implementar endpoint, repositories, DB ni migraciones.

### Fase B — Modulo db psycopg async base

- Crear `backend/modules/db/pool.py`, `settings.py`, `transaction.py`, `errors.py`.
- Sin repositories aun. Solo infraestructura de conexion.
- Validar conexion real contra `team360`.

### Fase C — Repositories read-only

- Implementar `WorkspaceConsoleRepository`, `PermissionConsoleRepository`, `PackageConsoleRepository`, `TaskConsoleRepository`.
- Cada repository retorna TypedDicts o dataclasses.
- Sin endpoint. Se prueban con script de integracion.

### Fase D — Endpoint Litestar read-only

- Implementar `GET /api/workspaces/{workspace_id}/console/bootstrap`.
- `ConsoleBootstrapService` orquesta los repos.
- Evaluar Pydantic para el contrato HTTP si se necesita OpenAPI automatico.
- Validar autenticacion y autorizacion.

### Fase E — Conectar Console frontend

- Reemplazar `getMockBootstrap()` por fetch a `/api/workspaces/{workspace_id}/console/bootstrap`.
- Eliminar `?profile=` de las URLs de desarrollo.
- Agregar estados loading, error, empty, forbidden.

### Fase F — Permisos reales y navegacion dinamica

- Reemplazar `deriveNavigation()` mock por datos del backend.
- Sincronizar catalogo de permisos DB con capacidades UX.
- Agregar migracion de organizaciones jerarquicas y membresias.

## 9. Que queda fuera (explicitamente)

| Aspecto | Excluido hasta |
|---|---|
| Escritura (POST/PUT/DELETE) | Fase posterior |
| Gestion de usuarios | Fase posterior |
| Configuracion de workers | Fase posterior |
| Edicion de knowledge | Fase posterior |
| Exposicion de credenciales | Siempre |
| AG-UI / SSE | Fase posterior |
| LangGraph checkpoints | Fase posterior |
| Organizaciones jerarquicas | Migracion 004 futura |
| Membresias multi-workspace | Migracion 004 futura |
| Servicios como entidad separada | Migracion 004 futura |
| Pydantic como requisito | Solo endpoint HTTP si se justifica |
