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
- `feature/console-backend-core`: producto funcional vivo; backend, Console, UX real conectada/productiva, diagnosis assistant, LiteLLM, PostgreSQL, runtime y orquestación global viva.
- `feature/console-backend-core` también puede contener labs cuando validan backend runtime, assistant productivo, UX conectada o experiencia final de consola.
- `ux/team360-console-design-handoff`: referencia visual congelada / diseño base.
- `feature/knowledge-ingestion-service`: knowledge ingestion / RAG / labs de knowledge; embeddings, chunking, scanner, retrieval, package behavior, golden answers, pruebas RAG/asistente como efecto del knowledge package y decision notes técnicas de esa línea.
- `feature/knowledge-ingestion-service` no es para desarrollo funcional productivo del runtime, backend o Console.
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
6. Cuando el usuario escriba `contexto componentes`, leer `lat.md/diagnosticador-embeddable-component-architecture.md` antes de analizar o modificar componentes, paquetes, estilos, interaction blocks, adapters, tests E2E o estructura frontend del Diagnosticador embebible.
7. Para conectividad frontend/backend de `/t360`, `SrvRestAstroLS_v1/astro/src/components/global.js` es la unica fuente de verdad: en desarrollo local y Browser MCP debe usarse `IS_REST_PRO=false` con `URL_REST_DEV=http://localhost:7050`; no corregir rutas tocando `astro.config.mjs`, API clients, componentes Svelte ni URLs hardcodeadas salvo instruccion explicita.
8. Para validaciones de navegador, Playwright + Chromium es el gate E2E oficial; Browser MCP / `opencode-browser` es exploratorio y de diagnostico visual, no reemplaza Playwright para cerrar fases, regresiones o produccion. Ver `lat.md/browser-mcp-validation-policy.md`.
9. Para validaciones visuales y reproduccion interactiva con Playwright MCP Server, leer primero `lat.md/playwright-mcp-server-policy.md`.
10. Para tests locales de paginas/componentes/E2E reales, leer `lat.md/browser-mcp-validation-policy.md`: levantar/bajar backend y Astro solo con `SrvRestAstroLS_v1/backend-dev.sh` y `SrvRestAstroLS_v1/astro-dev.sh`; Playwright debe automatizar navegador con `PLAYWRIGHT_SKIP_WEBSERVER=1`, no levantar su `webServer` automatico ni usar proxy/puertos paralelos salvo justificacion explicita.
11. Para validaciones Browser MCP / `opencode-browser`, seguir `lat.md/browser-mcp-validation-policy.md`: antes de navegar deben responder backend `127.0.0.1:7050` y Astro `127.0.0.1:3050`; el agente puede bajar/subir esos dos servidores locales si hace falta; si Browser MCP falla, detener la prueba y avisar, sin reemplazarla por terminal, `curl`, Playwright, HTML o lectura de codigo salvo autorizacion explicita.
12. Para despliegue frontend Astro de `team360.live` por `rsync`, seguir `lat.md/team360-frontend-rsync-deploy-policy.md`: verificar `IS_REST_PRO=true`, build limpio, fix en source y `dist`, backup remoto, dry-run revisado, rsync real, assets local=produccion y Playwright productivo antes de declarar PASS.
13. Para despliegue backend de Team360 por `rsync`, seguir `lat.md/team360-backend-rsync-deploy-policy.md`: validar rama/HEAD, tests backend, exclusiones `.env*`/`.venv`, backup remoto, dry-run revisado, rsync real, preservar sensibles, no reiniciar automaticamente, esperar reinicio manual en `tmux`, health y smoke modelo real sin fallback antes de aprobar.
14. Para diagramas tecnicos, seguir `lat.md/team360-mermaid-diagram-policy.md`: Mermaid es la fuente canonica versionable; renders SVG/PNG/Excalidraw son derivados opcionales; no hay instalacion global obligatoria ni se adopta el skill gstack `/diagram` completo.
15. Para bugs no triviales, especialmente cuando la prueba manual falla aunque los tests pasen, seguir `lat.md/team360-root-cause-debugging-policy.md`: reproducir, nombrar hipotesis de causa raiz, confirmar evidencia, aplicar fix minimo y agregar regresion backend/Playwright cuando corresponda.
16. Para QA browser dirigido con DeepSeek V4 Flash en OpenCode + `opencode-browser`, seguir `lat.md/deepseek-v4-flash-opencode-browser.md`: usar `browsermcp_*`, snapshots antes/despues, fase browser atomica, no reemplazar navegador con terminal y detenerse tras la evidencia pedida.
17. Mantener compatibilidad con ejecución tipo:
   - `python -m modules.messaging.providers.mercadolibre.probes.smoke_login`
   - `python -m modules.messaging.providers.mercadolibre.probes.smoke_inbox`
18. No hacer scraping complejo en fases de smoke/probe.
19. Si la validación requiere intervención humana, dejarlo explícito.
20. No instalar dependencias ni ejecutar comandos destructivos salvo pedido explícito.
21. Respetar la estrategia de environment parity del backend con Vertice360, más extras necesarios como Playwright.
22. Antes de crear acceso DB runtime, usar `psycopg 3 async` directo como estándar (ver `lat.md/postgres-driver-policy.md`).
23. No introducir SQLAlchemy/SQLModel/asyncpg como dependencia base sin decisión explícita documentada en `lat.md/postgres-driver-policy.md`.
24. Mantener SQL en repositories; no escribir SQL en endpoints ni rutas.
25. No mezclar pools de conexión: Team360 usa `psycopg_pool.AsyncConnectionPool` para `public.*`; LangGraph PostgresSaver usa su pool interno para `langgraph.*`.
26. Antes de desarrollo, test, smoke, benchmark o prueba que dependa de servicios reales, ejecutar preflight obligatorio (ver `lat.md/service-preflight-methodology.md`):
   - PostgreSQL activo.
   - Milvus activo y collection correcta.
   - LiteLLM activo.
   - `.bashrc` / env vars accesibles.
   - `globalVar.py` importable cuando aplique backend config.
   - Modelo registrado en LiteLLM.
   - Llamada real minima al modelo validando auth, credito/provider, endpoint y ausencia de fallback silencioso.
   - Si el preflight falla, no aceptar el benchmark ni interpretar resultados como calidad del modulo.

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
