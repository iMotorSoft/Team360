# Team360 Console - Alineacion UX, backend y PostgreSQL

Fecha: 2026-06-01

Estado: analisis tecnico previo a integracion. No implementa backend, DB ni migraciones.

## Resumen ejecutivo

Team360 ya tiene dos bases compatibles pero todavia desacopladas:

- una UX navegable de `team360.live` y Team360 Console con Astro/Svelte, App Shell, perfiles mock, workspaces, servicios y profundidad tecnica progresiva;
- una DB PostgreSQL viva con workspaces, RBAC, paquetes, `package_workers`, configuraciones, referencias de credenciales, knowledge scopes, runs, eventos, telemetria LLM y pgvector.

La integracion no debe conectar componentes Svelte directamente a tablas ni convertir cada mock en una tabla nueva. El siguiente paso correcto es definir un contrato backend `ConsoleBootstrap` autorizado y read-only, servido por repositories con `psycopg 3 async`.

La UX usa dos conceptos que el schema aplicado todavia no modela por completo:

- `organization`: jerarquia Team360 -> partner -> cliente y alcance delegado;
- `service`: prestacion visible al cliente, distinta del paquete comercial y de los workers tecnicos.

Esas brechas requieren una migracion futura explicita y auditable. No corresponde modificar silenciosamente las migraciones `001`, `002` o `003`.

## 1. Estado actual UX

### 1.1 Separacion de dominios

La estrategia vigente separa:

```text
team360.live
  -> sitio publico comercial

console.team360.live
  -> plataforma privada operativa
```

La home publica vive en `astro/src/pages/index.astro`. Explica valor, casos de uso, metodo y contacto sin exponer workers, credenciales ni detalle interno.

Team360 Console usa layouts separados:

- `PublicMarketingLayout.astro` para la home;
- `MockAccessLayout.astro` para `/login` y `/select-workspace`;
- `ConsoleAppLayout.astro` para rutas privadas mock.

### 1.2 Console implementada

El frontend actual ya materializa:

- un unico `AppShell.svelte`;
- sidebar y topbar contextuales;
- `WorkspaceSwitcher`;
- selector de perfil mock;
- breadcrumbs;
- banner de contexto propio o delegado;
- centro de notificaciones;
- dashboards adaptados;
- listados y detalle de servicios;
- reportes, alertas, tareas, equipo y settings;
- vistas tecnicas resumidas de workers y runs;
- i18n inicial `es`, `en`, `he` y direccion `ltr` / `rtl`.

Las rutas existentes son:

```text
/
/login
/select-workspace
/w/[workspaceId]
/w/[workspaceId]/organizations
/w/[workspaceId]/partners
/w/[workspaceId]/clients
/w/[workspaceId]/workspaces
/w/[workspaceId]/services
/w/[workspaceId]/services/[serviceId]
/w/[workspaceId]/client-services
/w/[workspaceId]/results
/w/[workspaceId]/reports
/w/[workspaceId]/alerts
/w/[workspaceId]/tasks
/w/[workspaceId]/team
/w/[workspaceId]/support
/w/[workspaceId]/settings
/w/[workspaceId]/workers
/w/[workspaceId]/runs
```

### 1.3 Bootstrap mock actual

`astro/src/lib/mock/bootstrap.ts` construye un `ConsoleBootstrap` con:

- usuario actual;
- membresia conceptual;
- organizacion y workspace activos;
- organizaciones y workspaces accesibles;
- permisos efectivos;
- modulos habilitados;
- servicios contratados;
- arbol autorizado;
- notificaciones;
- profundidad tecnica;
- capacidad AG-UI deshabilitada.

`astro/src/lib/navigation/derive.ts` filtra la navegacion por audiencia, modulos, permisos, tipo de organizacion, workspace y servicios contratados.

Este shape es una base util para el contrato backend. No debe conservar sus fuentes mock ni el parametro de URL `?profile=` cuando exista auth real.

### 1.4 Limites actuales

- Las rutas Console son estaticas y accesibles sin auth real.
- No existe fetch a backend para bootstrap ni pantallas.
- No existe validacion productiva de permisos o scope.
- Ocultar workers/runs es solo una guarda visual.
- `AGUI_BASE_URL` esta reservado, pero no existe transporte AG-UI/SSE funcional.
- `routes/team360.py` y `routes/agui.py` siguen siendo placeholders.
- La rama `ux/team360-console-design-handoff` contiene ajustes visuales posteriores aun no integrados a `feature/console-backend-core`, incluyendo smoke de diseno y mejoras del acceso para cambiar workspace.

## 2. Modelo backend disponible

### 2.1 Migracion 001 - Core

La migracion `001_team360_core_schema.sql` aporta:

- `core_workspaces`, `core_users`, `core_events`;
- providers, canales, numeros y webhooks;
- runners, tareas programadas, `task_runs`, heartbeats;
- threads y eventos de mensajeria;
- catalogo, configuracion y telemetria LLM;
- `llm_usage_logs`.

### 2.2 Migracion 002 - RBAC, paquetes, workers y knowledge

La migracion `002_team360_rbac_packages_workers_knowledge.sql` agrega:

- areas, roles, permisos, perfiles y asignaciones;
- planes, features y suscripciones por workspace;
- `assistant_instances`;
- `automation_packages`;
- `worker_definitions`;
- `package_workers`;
- `package_worker_configs`;
- `credential_references`;
- `knowledge_scopes`, bindings, documentos y chunks;
- extension de `task_runs` con paquete, `package_worker`, area, usuario asignado, permiso requerido y estado de aprobacion.

El centro operativo es `package_worker`: una capacidad concreta dentro de un paquete y workspace. `worker_definition` es catalogo tecnico reutilizable.

### 2.3 Migracion 003 - pgvector

La migracion `003_team360_pgvector_knowledge_embeddings.sql` agrega:

- extension `vector`;
- `knowledge_embedding_models`;
- `knowledge_chunk_embeddings`;
- indice HNSW cosine;
- vista `knowledge_ready_chunks`.

La fase vigente soporta RAG simple. GraphRAG sigue siendo futuro y se decide por `knowledge_scope`.

### 2.4 Brechas del schema aplicado

El modelo actual no representa por completo:

- organizaciones jerarquicas;
- parent-child de partners y clientes;
- membresias de usuario multi-workspace;
- scope delegado por organizacion o subarbol;
- servicios visibles al cliente como entidad separada;
- reportes persistidos;
- alertas con lifecycle y acknowledgement propios.

`core_users.workspace_id` permite un workspace principal, pero no sustituye una tabla de membresias multi-workspace.

## 3. Mapeo UX <-> DB

| UX / Console | Fuente DB disponible | Alineacion recomendada |
| --- | --- | --- |
| Usuario autenticado | `core_users` | Agregar capa de identidad/sesion sin guardar secretos en frontend. |
| Selector de workspace | `core_workspaces` | Resolver lista mediante membresias autorizadas. El schema necesita membresia multi-workspace futura. |
| Organizacion activa y acceso delegado | No existe entidad completa | Agregar migracion futura de organizaciones, jerarquia y membresias/scope delegado. |
| Servicios contratados | `automation_packages`, planes, features | No igualar `service` a `automation_package`. Crear proyeccion de API y luego entidad visible estable. |
| Detalle de servicio | paquete, assistant, features, `package_workers`, `task_runs`, eventos | Devolver DTO sanitizado segun audiencia. El cliente recibe resultados y proximos pasos, no topologia tecnica. |
| Workers | `package_workers` + `worker_definitions` + configs | Visible solo para operacion autorizada. El recurso principal es `package_worker`, no el worker global. |
| Runs | `task_runs`, `core_events`, `package_worker_id`, `automation_package_id` | Exponer resumen operativo. Payloads, errores sensibles y correlaciones profundas quedan restringidos. |
| Tareas y aprobaciones | `task_runs`, `assigned_user_id`, `approval_status`, `required_permission` | Usar read model. Separar tareas humanas si el lifecycle futuro excede `task_runs`. |
| Reportes y resultados | No existe entidad dedicada | Empezar con proyecciones read-only; persistir reportes solo cuando se defina lifecycle y descarga. |
| Alertas | `core_events`, estado de runs | Crear proyeccion inicial. Agregar entidad propia si se necesita acknowledgement, asignacion o SLA. |
| Equipo, roles y permisos | `core_users`, roles, profiles, permissions, areas | Completar alcance multi-workspace y organizacion antes de habilitar gestion real. |
| Integraciones | providers, canales, assistant settings, package settings, configs, `credential_references` | Exponer estado seguro. Nunca devolver secretos ni referencias sensibles a perfiles no autorizados. |
| Knowledge | scopes, bindings, documents, chunks, embeddings | Mantener interno al inicio; habilitar vistas acotadas solo con `knowledge.view`. |
| Consumo IA | `llm_usage_logs` | Reservar para observabilidad Team360 y reportes agregados autorizados. |

### 3.1 Vocabulario de permisos

El mock frontend usa permisos UX como:

```text
services.read
workers.read
runs.read
reports.read
alerts.read
tasks.read
```

La DB semilla usa permisos core como:

```text
package.view
worker.view
task.view
dashboard.view
audit.view
```

Antes de implementar auth se debe fijar un catalogo canonico. La recomendacion es que PostgreSQL sea fuente de verdad y que el backend derive capacidades UX estables para el bootstrap. Evitar duplicar logica de permisos en Svelte.

### 3.2 DTO inicial recomendado

El primer endpoint privado debe devolver un DTO equivalente al mock:

```text
ConsoleBootstrap
  current_user
  active_context
  accessible_workspaces
  allowed_organization_scope
  effective_permissions
  ui_capabilities
  enabled_modules
  contracted_services
  notification_summary
```

El backend debe calcularlo despues de validar sesion, workspace solicitado, membresia, permisos y ownership del recurso.

## 4. Recomendacion de rutas Console

### 4.1 Mantener rutas UX estables

Conservar como nucleo:

```text
/login
/select-workspace
/w/:workspaceId
/w/:workspaceId/services
/w/:workspaceId/services/:serviceId
/w/:workspaceId/results
/w/:workspaceId/reports
/w/:workspaceId/alerts
/w/:workspaceId/tasks
/w/:workspaceId/team
/w/:workspaceId/support
/w/:workspaceId/settings
```

Mantener con visibilidad restringida:

```text
/w/:workspaceId/organizations
/w/:workspaceId/partners
/w/:workspaceId/clients
/w/:workspaceId/workspaces
/w/:workspaceId/workers
/w/:workspaceId/runs
```

Agregar progresivamente para Team360 autorizado:

```text
/w/:workspaceId/packages
/w/:workspaceId/packages/:packageId
/w/:workspaceId/workers/:packageWorkerId
/w/:workspaceId/runs/:runId
/w/:workspaceId/knowledge
/w/:workspaceId/audit
```

Los IDs de rutas deben ser opacos y el backend debe validar scope en cada request. Conocer una URL no concede acceso.

### 4.2 API read-only inicial

Primer corte sugerido:

```text
GET /api/console/bootstrap?workspace_id=:workspaceId
GET /api/console/workspaces
GET /api/console/workspaces/:workspaceId/services
GET /api/console/workspaces/:workspaceId/services/:serviceId
GET /api/console/workspaces/:workspaceId/tasks
GET /api/console/workspaces/:workspaceId/alerts
GET /api/console/workspaces/:workspaceId/reports
```

Solo para perfiles tecnicos autorizados:

```text
GET /api/console/workspaces/:workspaceId/workers
GET /api/console/workspaces/:workspaceId/runs
GET /api/console/workspaces/:workspaceId/runs/:runId
```

Todos los queries SQL deben vivir en repositories y usar `psycopg 3 async` directo.

## 5. Separacion publico / privado

`team360.live` y `console.team360.live` deben compartir marca y sistema visual, pero no bootstrap ni autorizacion.

Reglas:

- La home publica no consulta datos operativos privados.
- Console valida sesion y contexto antes de renderizar datos.
- `/login` deja de ser mock cuando exista identidad real.
- `/select-workspace` lista solo contextos autorizados por backend.
- El selector productivo no incluye perfiles mock ni `?profile=`.
- Cambiar workspace invalida estado UI obsoleto y vuelve a solicitar bootstrap.
- AG-UI/SSE muestra estado derivado; PostgreSQL conserva la verdad operativa.

## 6. Reglas de visibilidad

Toda request privada debe resolver:

```text
authenticated_user_id
organization_id
workspace_id
granted_permissions
allowed_organization_scope
resource_ownership
```

La UI puede ocultar o resumir, pero el backend siempre autoriza.

| Audiencia | Puede ver | No debe ver |
| --- | --- | --- |
| Team360 admin autorizado | red, workspaces, paquetes, servicios, `package_workers`, runs, auditoria segun permiso | secretos planos |
| Operador Team360 autorizado | servicios asignados, salud resumida, workers y runs permitidos, alertas, tareas | configuracion critica fuera de scope |
| Partner | organizacion propia, descendientes autorizados, servicios, resultados, reportes, tareas | clientes laterales, workers internos, credenciales |
| Cliente | workspace propio, servicios contratados, resultados, reportes, alertas, aprobaciones y soporte | workers, logs internos, payloads tecnicos, credenciales |

Reglas adicionales:

- El cliente nunca habla directo con workers.
- El detalle cliente de historial se deriva de runs y eventos sanitizados.
- `credential_references.secret_ref` no se envia como dato de UI general.
- La configuracion de `package_worker` solo se expone de forma parcial y autorizada.
- Knowledge y telemetria LLM empiezan como vistas internas.

## 7. Fases recomendadas

### Fase 0 - Contratos y vocabulario

- Congelar DTO `ConsoleBootstrap`.
- Definir catalogo canonico de permisos DB -> capacidades UX.
- Definir `service` como prestacion visible separada de package y worker.
- Integrar conscientemente los cambios visuales pendientes de la rama UX.

### Fase 1 - Bootstrap read-only workspace-centric

- Crear pool DB y repositories con `psycopg 3 async`.
- Implementar sesion minima y resolucion de workspace autorizado.
- Implementar `/api/console/bootstrap`.
- Conectar home privada, selector de workspace y servicios read-only.
- Mantener fuera el scope delegado complejo hasta modelarlo.

### Fase 2 - Migracion futura explicita

- Agregar organizaciones y jerarquia.
- Agregar membresias usuario-organizacion-workspace.
- Agregar scope delegado auditable.
- Agregar entidad o proyeccion persistida de servicios visibles.
- Evaluar lifecycle propio para alertas y reportes.

No modificar retroactivamente `001`, `002` o `003`.

### Fase 3 - Sustitucion gradual del mock

- Reemplazar fixtures por API por pantalla.
- Eliminar selector de perfil mock.
- Mantener feature flags para desarrollo visual.
- Aplicar guards backend y estados `loading`, `empty`, `error`, `permission denied`.

### Fase 4 - Operacion tecnica y HITL

- Conectar workers desde `package_workers`.
- Conectar runs desde `task_runs` y eventos.
- Exponer aprobaciones con `approval_status`.
- Registrar acciones sensibles en `core_events`.

### Fase 5 - Knowledge y realtime

- Incorporar retrieval RAG simple por scope.
- Exponer estado de ingesta solo a perfiles autorizados.
- Agregar AG-UI/SSE para mostrar cambios de estado.
- Mantener GraphRAG como evolucion por paquete, no como requisito global.

## 8. Riesgos

| Riesgo | Consecuencia | Mitigacion |
| --- | --- | --- |
| Tratar organization y workspace como sinonimos | Scope delegado incorrecto y filtraciones laterales | Migracion explicita y autorizacion por contexto completo. |
| Tratar service y package como la misma entidad | UX acoplada a internals y contratos inestables | DTO de servicio visible y entidad futura separada. |
| Usar permisos mock como autoridad | Inconsistencia entre UI y DB | PostgreSQL como fuente de verdad y capacidades UX derivadas por backend. |
| Confiar en ocultamiento frontend | Acceso directo por URL a recursos privados | Guard backend en cada endpoint y validacion de ownership. |
| Exponer workers, payloads o credenciales | Filtracion de detalles operativos o secretos | DTOs sanitizados y permisos atomicos. |
| Conectar Svelte directo a SQL | Acoplamiento, SQL disperso y seguridad debil | API + services + repositories con `psycopg 3 async`. |
| Reusar `core_events` como alerta completa sin lifecycle | ACK, SLA y asignacion ambiguos | Read model inicial; entidad propia si aparece necesidad real. |
| Mantener rutas estaticas al pasar a datos reales | Contextos obsoletos o enumerables | Rutas dinamicas privadas y bootstrap validado. |
| Mezclar AG-UI con fuente de verdad | Estado efimero inconsistente | Postgres registra verdad; SSE solo comunica cambios. |
| Integrar ramas UX y backend sin revision | Perder smoke o cambios visuales recientes | Integracion explicita con diff y validacion frontend posterior. |

## Decisiones para la proxima implementacion

- No tocar migraciones existentes para adaptar mocks.
- No ejecutar DB desde componentes frontend.
- No crear endpoints que devuelvan tablas crudas.
- No exponer workers a clientes.
- No introducir SQLAlchemy o SQLModel como core.
- Implementar primero bootstrap read-only y repositories.
- Diseñar luego una migracion nueva para las brechas de organizacion, membresias y servicios.

## Referencias

- `lat.md/team360-platform.md`
- `lat.md/console-multi-organization.md`
- `lat.md/multi-package-workers.md`
- `lat.md/knowledge-rag-graphrag.md`
- `lat.md/postgres-driver-policy.md`
- `docs/ux/team360-domains-and-console-strategy.md`
- `docs/ux/team360-console-navigation-model.md`
- `docs/ux/team360-console-app-shell-and-layout-system.md`
- `SrvRestAstroLS_v1/docs/postgresql_002_rbac_packages_workers_knowledge_design.md`
- `SrvRestAstroLS_v1/docs/postgresql_003_pgvector_knowledge_embeddings_design.md`
