# Status actual - lat.md

Objetivo: `arquitectura-viva`

Ultima actualizacion: 2026-05-31

## Estado general

`lat.md/` contiene definiciones de alto nivel, reglas de negocio, decisiones de arquitectura e invariantes para Team360.

Esta capa sigue el patron usado en JudaismoenVivo: indice raiz `lat.md/lat.md`, documentos por concepto y referencias `[[...]]` que pueden anclarse desde codigo con comentarios `@lat`. Las reglas de uso quedaron declaradas en `AGENTS.md` y en `.agents/skills/team360-project/SKILL.md`.

## Acciones realizadas

### 2026-06-01 - Atajos seguros de workflow de ramas

- Se agrego al skill de Team360 una regla para interpretar diseño / UX, desarrollo / dev / backend y producción / main como atajos de rama.
- Se fijo el protocolo seguro: verificar rama y worktree antes del checkout, detenerse ante cualquier cambio pendiente y no hacer stash, reset, commit, merge, rebase ni force push automáticamente.
- Se aclaro que producción significa contexto de rama `main`, no deploy real.

### 2026-05-31 - Politica estable frontend pnpm y wrappers UI

- Se agrego referencia `[[team360-frontend-ui-policy]]` en `lat.md/lat.md`.
- Se fijo pnpm como package manager frontend obligatorio.
- Se fijo Tailwind CSS 4 + DaisyUI 5 CSS-first como stack UI inicial obligatorio.
- Se fijo que las pantallas de negocio consumen wrappers Team360 y no clases DaisyUI dispersas.
- La especificacion completa queda en `docs/frontend/` y ADR-005.

### 2026-05-31 - Correccion frontend base DaisyUI 5 + Tailwind 4

- Se corrigio la referencia estable `[[team360-frontend-base]]`.
- DaisyUI 5 queda confirmado como compatible con Tailwind 4 mediante integracion CSS-first.
- Se mantiene como invariante no reutilizar configuracion legacy ni tema `vertice360`.
- La documentacion completa y fuentes oficiales quedan en `docs/frontend/`.

### 2026-05-31 - App Shell reutilizable de Team360 Console

- Se amplio `console-multi-organization.md` con el invariante de App Shell.
- Se fijo un unico shell reutilizable y layouts compartidos, sin consolas separadas por rol.
- Se agrego la regla de no renderizar datos privados antes de validar sesion y contexto, y descartar estado obsoleto al cambiar workspace.
- Se enlazaron la guia UX de layouts y `ADR-003`.

### 2026-05-31 - Navegacion contextual de Team360 Console

- Se amplio `console-multi-organization.md` con el invariante de navegacion contextual.
- Se fijo un unico App Shell adaptable con navegacion derivada desde tipo de organizacion, permisos efectivos, workspace activo, servicios, modulos y scope permitido.
- Se enlazaron la guia UX `docs/ux/team360-console-navigation-model.md` y `ADR-002`.
- No se duplico la especificacion UX completa dentro de `lat.md/`.

### 2026-05-31 - Team360 Console multi-organizacion

- Se agrego `console-multi-organization.md` como regla estable de arquitectura viva.
- Se separaron `team360.live` como sitio comercial publico y `console.team360.live` como Team360 Console privada.
- Se definieron jerarquia de organizaciones, diferencia entre `organization` y `workspace`, alcance delegado de partners e invariante de autorizacion.
- Se registro a `Mamá Mía 360` como primera instancia configurable de `partner` para Israel, sin hardcodear reglas de producto.
- Se actualizo `lat.md/lat.md` con referencia `[[console-multi-organization]]`.

### 2026-05-29 - Driver policy psycopg 3 async

- Se agrego `postgres-driver-policy.md` como decision estable de arquitectura viva.
- Documenta que `psycopg 3 async` es el driver runtime estandar de Team360.
- Prohibe SQLAlchemy/SQLModel/asyncpg como base del core; permite excepciones solo si hay metrica concreta.
- Define patron de repositories, unit-of-work, pool, y estructura de modulos `backend/modules/db/`.
- Relacion con pgvector, LangGraph PostgresSaver y schema migrations explicitas.
- Se actualizo `lat.md/lat.md` con referencia `[[postgres-driver-policy]]`.

### 2026-05-29 - Materializacion de pgvector en fase 003

- Se actualizo `postgres-ai-persistence.md` para reflejar que la fase `003_team360_pgvector_knowledge_embeddings.sql` ya materializa pgvector sobre `team360`.
- Se mantuvo la separacion arquitectonica: embeddings en tabla propia, Team360 core como fuente de verdad y LangGraph PostgresSaver reservado para fase 004.
- No se convirtio `lat.md/` en bitacora operativa; el detalle de aplicacion y auditoria queda en `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-05-29 - Decision Postgres AI persistence

- Se agrego `postgres-ai-persistence.md` como decision estable de arquitectura viva.
- Se documento PostgreSQL 18 como nucleo transaccional unico de Team360.
- Se separo explicitamente el modelo core Team360 de futuras capas pgvector y LangGraph PostgresSaver.
- Se fijo que LangGraph checkpoints no reemplazan `task_runs` ni `core_events`.
- Se documento la precaucion de no depender de `pg_checkpointer` sin verificar disponibilidad real.
- Se actualizo `lat.md/lat.md` con la referencia `[[postgres-ai-persistence]]`.

### 2026-05-28 - Reglas operativas de lat.md para agentes

- Se agrego en `AGENTS.md` la regla obligatoria para leer `lat.md/lat.md` ante cambios de arquitectura, dominio, IA, workers, knowledge, seguridad, paquetes o reglas transversales.
- Se agrego en `.agents/skills/team360-project/SKILL.md` el procedimiento de uso de `lat.md/`: documentos `kebab-case.md`, referencias `[[...]]`, anchors `@lat`, limites de uso y actualizacion de status local.
- Se explicito que `lat.md/` no reemplaza la bitacora tecnica `SrvRestAstroLS_v1/docs/status_actual.md`.

### 2026-05-28 - Base lat.md general de Team360

- Se creo `lat.md/lat.md` como indice raiz.
- Se agregaron documentos para:
  - plataforma Team360;
  - multi-paquete / multi-worker;
  - knowledge RAG / GraphRAG;
  - LiteLLM;
  - seguridad HITL / MFA;
  - automation diagnosis.

## Validacion

- No se movio documentacion tecnica viva desde `SrvRestAstroLS_v1/docs/`.
- `lat.md/` queda como capa de invariantes y conceptos estables anclables desde codigo.

### 2026-05-31 - Base frontend Team360 desde Vertice360

- Se agrego referencia `[[team360-frontend-base]]` en `lat.md/lat.md`.
- La documentacion completa de la base frontend queda en `docs/frontend/` y `docs/adr/ADR-004/`.
- No se implemento codigo, rutas, componentes ni migraciones.

## Pendientes recomendados

- Agregar nuevos documentos lat.md solo para conceptos estables de plataforma.
- Evitar duplicar bitacoras tecnicas: el estado de implementacion sigue en `SrvRestAstroLS_v1/docs/status_actual.md`.
