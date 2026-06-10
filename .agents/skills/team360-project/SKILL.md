---
name: team360-project
description: Reglas y flujo de trabajo para desarrollar Team360 con Codex CLI, incluyendo team360_orquestador, AG-UI y laboratorio aislado de Mercado Libre.
---

# Team360

## Propósito
Team360 es una solución multicanal conversacional.
El núcleo del sistema es `team360_orquestador`.
AG-UI / SSE es parte estructural.
Providers iniciales:
- Gupshup
- Mercado Libre

Mercado Libre arranca con laboratorio aislado de browser automation.

## Ubicación del skill
Usar esta copia del skill dentro del repo:
`.agents/skills/team360-project/SKILL.md`

## Raíz del proyecto
Asumir como raíz el directorio actual del repositorio Team360.

## Protocolo obligatorio al iniciar una sesión de agente

Al comenzar cualquier sesión de Codex CLI, OpenCode u otro agente de código, antes de modificar archivos, el agente debe ubicarse en el contexto del proyecto.

Pasos obligatorios:

1. Leer este skill:

   `.agents/skills/team360-project/SKILL.md`

2. Leer `AGENTS.md` si existe.

3. Leer `lat.md/team360-global-orchestration.md` si existe.

4. Verificar rama actual:

   ```bash
   git branch --show-current
   ```

5. Verificar estado del worktree:

   ```bash
   git status
   ```

6. No cambiar de rama si el worktree no está limpio.

7. No modificar archivos si hay cambios o archivos untracked no esperados.

8. No hacer commit, push, merge, rebase, reset, clean ni borrar ramas salvo pedido explícito del usuario.

9. Confirmar que la tarea corresponde a la rama actual según el mapa de ramas Team360.

10. Si la rama no corresponde, detenerse y explicar qué rama debería usarse.

11. Si hay dudas sobre ownership de un cambio, revisar `lat.md/team360-global-orchestration.md`.

Regla central:

> Antes de ejecutar, ubicarse. Antes de modificar, verificar rama y estado.

### Mapa rápido de ramas

- `main`: producción / snapshot estable.
- `feature/console-backend-core`: backend, console, UX real productiva, diagnosis assistant, LiteLLM, PostgreSQL, `lab/` y orquestación global viva.
- `ux/team360-console-design-handoff`: referencia visual congelada / diseño base.
- `feature/knowledge-ingestion-service`: ingestion service, embeddings, chunking, scanner, retrieval, package behavior, golden answers y labs de ingesta.
- `docs/knowledge-documents-foundation`: documentación knowledge, estándares, paquetes, manuales, authoring, metadata y contenido curado.

## Atajos de workflow de ramas
Interpretar frases claras del usuario como atajos de contexto de rama:

Cuando una instruccion mencione `desarrollo`, usar `feature/console-backend-core`. No crear una rama local llamada `desarrollo`. El valor `Objetivo: desarrollo` de `SrvRestAstroLS_v1/docs/status_actual.md` identifica el tipo de bitacora tecnica y no modifica esta convencion Git.

- Diseño / UX / `design` / `ux`:
  - Rama destino: `ux/team360-console-design-handoff`
  - Usar para diseño visual, copy, responsive, revisión de pantallas, mock UX y handoff.
  - No incorporar backend real, DB, auth real ni integración AG-UI funcional.
- Desarrollo / `dev` / `backend`:
  - Rama destino: `feature/console-backend-core`
  - Usar para backend real, bootstrap de consola, auth, permisos, DB, migraciones controladas, APIs, AG-UI e integración real frontend/backend.
- Producción / `main` / `stable` / rama estable:
  - Rama destino: `main`
  - Usar como base estable e integrable.
  - En este contexto, "producción" significa contexto de rama; no implica deploy real.

Frases equivalentes incluyen `trabajamos con ...`, `vamos a ...` y `pasemos a ...`.

### Protocolo seguro para cambiar de rama
1. Ejecutar `git status --short` y `git branch --show-current`.
2. Si hay cualquier cambio pendiente (`M`, `A`, `D`, `??`, `UU` u otro), detenerse. Reportar rama actual, cambios pendientes, rama destino solicitada y recomendación. No ejecutar checkout.
3. Si el worktree está limpio y la rama destino existe localmente, ejecutar `git checkout <rama>`.
4. Si la rama no existe localmente, verificar `git branch -r`. Si existe `origin/<rama>`, crear tracking branch con `git checkout -t origin/<rama>`.
5. Si la rama tampoco existe en `origin`, detenerse y pedir instrucción.

No hacer automáticamente `stash`, `reset`, `commit`, `merge`, `rebase`, force checkout, force push, creación o borrado de ramas. No propagar cambios entre diseño, desarrollo y `main` sin instrucción explícita.

## Estructura relevante
- `lat.md/lat.md`
- `lat.md/`
- `SrvRestAstroLS_v1/backend/modules/team360_orquestador/`
- `SrvRestAstroLS_v1/backend/modules/agui_stream/`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/browser/`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/probes/`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/runtime/`
- `SrvRestAstroLS_v1/astro/src/lib/team360_orquestador/`
- `SrvRestAstroLS_v1/astro/src/components/demo/team360-orquestador/`
- `SrvRestAstroLS_v1/astro/src/pages/demo/team360-orquestador/`

## Convenciones para lat.md
`lat.md/` es la capa de arquitectura viva de Team360. Usarla para reglas estables, invariantes de dominio y decisiones transversales que deben sobrevivir a una tarea puntual.

Leer `lat.md/lat.md` antes de cambios que afecten:
- arquitectura general o limites de modulos
- IA, LiteLLM, providers o scoring
- workers, `package_worker`, paquetes o automatizaciones
- knowledge, RAG, GraphRAG o scopes
- seguridad, MFA, HITL, credenciales o acciones bloqueadas
- contratos que puedan quedar anclados desde codigo

Reglas de uso:
1. Crear documentos por concepto estable con nombre `kebab-case.md`.
2. Usar referencias tipo `[[concepto]]` entre documentos.
3. Usar anchors de codigo tipo `# @lat: [[concepto#Seccion]]` solo cerca de clases, funciones o decisiones donde se implementa una regla no trivial.
4. No anclar cada linea ni comentarios obvios.
5. No usar `lat.md/` para bitacoras diarias, evidencias, snapshots, instrucciones efimeras o estado de implementacion.
6. Al crear o modificar documentos de `lat.md/`, actualizar `lat.md/status_actual.md`.
7. Mantener `SrvRestAstroLS_v1/docs/status_actual.md` como bitacora tecnica principal; `lat.md/` solo registra invariantes y conceptos estables.

## Reglas de trabajo
1. No inventar una estructura nueva fuera del patrón actual.
2. No copiar módulos de Vertice360 fuera del alcance ya definido.
3. No tocar `team360_orquestador` salvo que el objetivo lo pida.
4. No mezclar probes/browser con AG-UI, rutas o frontend salvo que el objetivo lo pida.
5. Preferir cambios chicos, claros y reversibles.
6. Mantener compatibilidad con ejecución tipo:
   - `python -m modules.messaging.providers.mercadolibre.probes.smoke_login`
   - `python -m modules.messaging.providers.mercadolibre.probes.smoke_inbox`
7. No hacer scraping complejo en fases de smoke/probe.
8. Si la validación requiere intervención humana, dejarlo explícito.
9. No instalar dependencias ni ejecutar comandos destructivos salvo pedido explícito.
10. Respetar la estrategia de environment parity del backend con Vertice360, más extras necesarios como Playwright.
11. Antes de crear acceso DB runtime, usar `psycopg 3 async` directo como estándar (ver `lat.md/postgres-driver-policy.md`).
12. No introducir SQLAlchemy/SQLModel/asyncpg como dependencia base sin decisión explícita documentada en `lat.md/postgres-driver-policy.md`.
13. Mantener SQL en repositories; no escribir SQL en endpoints ni rutas.
14. No mezclar pools de conexión: Team360 usa `psycopg_pool.AsyncConnectionPool` para `public.*`; LangGraph PostgresSaver usa su pool interno para `langgraph.*`.

## Convenciones para Mercado Libre browser lab
- `browser/` contiene helpers reutilizables
- `probes/` contiene scripts ejecutables aislados
- `runtime/` contiene perfiles, screenshots y storage state
- `selectors.py` debe ser conservador y ajustable
- `smoke_*` primero validan acceso, luego lectura, después interacción

## Convenciones para resultados
Al terminar una tarea:
1. resumir archivos modificados
2. explicar diff o cambios principales
3. indicar cómo validar manualmente
4. listar supuestos y heurísticas

## Qué priorizar
- primero laboratorio Mercado Libre funcional
- luego normalización mínima
- luego integración gradual con `team360_orquestador`
- luego AG-UI/SSE/UI

## Regla de acceso a datos: Pydantic no es obligatorio

Pydantic no es obligatorio en repositories ni en el core de dominio.

- Repositories devuelven `dict`, `dataclass`, `TypedDict` o DTO explícitos.
- Pydantic solo se usa en bordes HTTP/API cuando aporte validación, serialización JSON, OpenAPI o protección de campos sensibles.
- Pydantic no es fuente de verdad del dominio.
- Pydantic no debe duplicar el schema SQL como si fuera ORM.
- Para contratos internos simples, preferir `dataclass` o `TypedDict`.
- Para ConsoleBootstrap, documentar JSON/TypedDict primero; Pydantic se evalúa cuando exista endpoint real.

Ver sección `Pydantic Boundary` en `lat.md/postgres-driver-policy.md`.

## Qué evitar
- mezclar demasiado pronto dominio y provider
- sobreautomatizar antes de tener smoke tests sólidos
- introducir complejidad innecesaria
- refactors grandes fuera del objetivo puntual
