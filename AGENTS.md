# Team360 - Instrucciones para agentes

Este archivo es la fuente operativa canonica para Codex, OpenCode, Crush y otros agentes que trabajen en Team360. Las politicas extensas se cargan solo cuando la tarea las necesita.

## Inicio obligatorio

Comenzar por rama, worktree y [estado técnico GLOBAL](SrvRestAstroLS_v1/docs/status_actual.md); cargar después solo el contexto necesario.

1. Trabajar desde `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`.
2. Ejecutar `git branch --show-current` y `git status --short`.
3. Leer `SrvRestAstroLS_v1/docs/status_actual.md` para conocer el estado vigente.
4. Identificar el frente y consultar solo las referencias de la tabla siguiente.
5. No cambiar de rama ni pisar cambios existentes. Si hay archivos modificados, preservar ownership y editar solo paths compatibles con la tarea.
6. Varios agentes pueden escribir en el mismo worktree solo sobre scopes `MODULE_LOCAL` explicitamente asignados y disjuntos.

No hacer commit, push, merge, rebase, reset, clean, stash, checkout forzado ni borrar ramas salvo pedido explicito del usuario y una ventana Git exclusiva.

## Shared development host

La máquina comparte backend, frontend, PostgreSQL, browsers, IDE, agentes, otros proyectos y procesos de usuario. Esta política aplica aunque el prompt no mencione recursos.

- `USE AVAILABLE CAPACITY, DO NOT DESTABILIZE THE HOST`; prioridad: `CORRECTNESS > HOST STABILITY > SPEED`.
- Antes de workloads pesados, inspeccionar sin modificar el host: load, CPU aproximada, memoria disponible, swap y procesos pesados relevantes.
- Evaluar señales conjuntamente y su evolución; un pico breve o un único umbral no decide por sí solo. Evitar presión sostenida, swap creciente, agotamiento de RAM y degradación de servicios.
- Usar concurrencia moderada si hay capacidad; reducirla con carga, ejecutar focalizado/secuencial en host ocupado y no iniciar trabajo intensivo si es inseguro. No imponer single-thread universal.
- No consumir todos los cores por defecto; no usar `pytest -n auto`, pools ilimitados ni suites grandes simultáneas; contar también threads internos y procesos hijos.
- Checks baratos primero, tests focalizados y evidencia válida reutilizada; escalar carga progresivamente solo cuando agregue una garantía necesaria.
- NO terminar procesos que la ejecución actual no haya creado: prohibidos `killall`, `pkill` genérico y matar backend/frontend, PostgreSQL, browsers, IDE u otros agentes existentes; no reiniciar servicios para liberar recursos.
- Ante presión, no iniciar nuevas tareas pesadas, reducir concurrencia, preservar estado y detener únicamente workers propios atribuibles con seguridad; reportar `RESOURCE_BLOCKED` / `BLOCKED_HOST`, nunca forzar un PASS.
- Al terminar, comprobar y cerrar procesos propios, incluidos hijos, browsers y servidores temporales; ante atribución dudosa, dejarlos intactos.
- Distinguir `FUNCTIONAL_FAILURE` (fallo lógico demostrado), `RESOURCE_BLOCKED` (no es seguro ejecutar) y `ENVIRONMENTAL_ABORT` (interrupción ambiental sin defecto demostrado); no cambiar código para ocultar problemas ambientales.
- Guard proporcional: consultas pequeñas normales, contexto rápido para un test local y guard explícito para suites grandes, browsers, scans, benchmarks y gates largos. Telchi detalla operación y promociones en `SrvRestAstroLS_v1/backend/modules/telchi/CONTEXT.md`.

## Ownership y concurrencia

La politica detallada y fuente humana canonica es `lat.md/team360-global-orchestration.md`; estas son las reglas operativas inmediatas.

- `MODULE_LOCAL`: el agente puede editar solo el scope existente que le fue asignado, incluidos sus tests y documentacion propios.
- `SHARED`: antes de editar, identificar consumidores, informar el impacto y obtener asignacion o autorizacion cuando pueda afectarlos.
- `GLOBAL`: todos pueden leer; un solo writer GLOBAL simultáneo, con ventana explícita y alcance delimitado. Antes de editar, informar path, motivo, impacto y módulo solicitante y coordinar ownership. Los agentes locales pueden continuar si no alteran condiciones GLOBAL.
- Una ventana GLOBAL documental no autoriza código, infraestructura, Git ni producción. Procesos `pi`, `opencode` u otros activos no prueban ownership. Con autorización de reconciliación, inspeccionar el diff preexistente y preservarlo; nunca exigir limpiar el worktree para comenzar.
- `PRODUCTION_PROTECTED`: detenerse y obtener autorizacion explicita; exige regresion especifica y no permite ampliar el scope. Actualmente cubre solo Diagnosticador/Vera y el componente/embed productivo.
- Los cambios dentro del scope asignado a otro agente son `EXPECTED CONCURRENT CHANGES`: preservarlos y no revertirlos, borrarlos, formatearlos, modificarlos ni incluirlos en Git.
- Un cambio fuera de los scopes concurrentes declarados que no pueda explicarse obliga a detenerse e informar.
- Edicion concurrente `MODULE_LOCAL` esta permitida; `git add`, commit, checkout/switch, merge, rebase, reset, stash, clean y operaciones equivalentes requieren exclusividad y ningun otro agente escritor activo.
- Tambien requieren ventana exclusiva los formatters globales, lockfiles, regeneraciones masivas y scripts o regresiones que alteren artefactos compartidos.

## Ramas

| Rama | Responsabilidad |
| --- | --- |
| `main` | Snapshot estable; no desarrollar directamente salvo hotfix explicito. |
| `feature/console-backend-core` | Backend, Console, UX conectada, diagnosis assistant, LiteLLM, PostgreSQL y runtime productivo. |
| `feature/knowledge-ingestion-service` | Ingestion, embeddings, chunking, retrieval, RAG y labs de knowledge. |
| `docs/knowledge-documents-foundation` | Contenido, metadata, authoring y documentacion knowledge. |
| `ux/team360-console-design-handoff` | Referencia visual y handoff UX, sin backend real. |

`desarrollo`, `dev` y `backend` corresponden a `feature/console-backend-core`. No crear una rama llamada `desarrollo`.

## Contexto por tarea

| Tarea | Referencia obligatoria |
| --- | --- |
| Orquestacion, ownership o decisiones transversales | `lat.md/team360-global-orchestration.md` |
| Arquitectura o conceptos estables | `lat.md/lat.md` y el documento enlazado relevante |
| PostgreSQL, repositories o pools | `lat.md/postgres-driver-policy.md` |
| Servicios reales, smokes o benchmarks | `lat.md/service-preflight-methodology.md` |
| Runtime publico Vera | `lat.md/team360-runtime-operational-policy.md` |
| Componentes del Diagnosticador | `lat.md/diagnosticador-embeddable-component-architecture.md` |
| Browser QA o E2E | `lat.md/browser-mcp-validation-policy.md` |
| Playwright MCP | `lat.md/playwright-mcp-server-policy.md` |
| OpenCode + DeepSeek browser | `lat.md/deepseek-v4-flash-opencode-browser.md` |
| Bugs no triviales | `lat.md/team360-root-cause-debugging-policy.md` |
| Deploy frontend/backend | politica `team360-*-rsync-deploy-policy.md` correspondiente |
| Diagramas | `lat.md/team360-mermaid-diagram-policy.md` |

## TELCHI CONTEXT

Esta regla aplica a cualquier agente que consuma `AGENTS.md`; la autoridad detallada permanece únicamente en el contexto canónico Telchi.

Para toda tarea Telchi, antes de elegir directorios, ejecutar scripts, crear archivos o tomar decisiones arquitectónicas, leer `SrvRestAstroLS_v1/backend/modules/telchi/CONTEXT.md`. Resolver en orden `ENTITY=TELCHI → DOMAIN → STAGE → SOURCES / OUTPUTS / POLICIES` y solo entonces elegir roots, ejecutar o escribir.

- `INVESTIGATION_BY_DEFAULT=YES`: si Telchi está confirmado y Development o Production no son explícitos, usar `STAGE=INVESTIGATION`.
- Una intención explícita de construir capacidad usa `STAGE=DEVELOPMENT` bajo el módulo Telchi y fuera de `investigation/`; una promoción explícita usa `STAGE=PRODUCTION` y requiere su gate.
- SAP/HANA es una source Telchi, no una stage. En conversación Telchi activa, atajos como “SAP ventas”, “HANA compras”, “revisar deudas” o “probar producción” heredan Telchi; fuera de ese contexto, SAP/HANA por sí solos no implican Telchi.
- Data Lake es infraestructura/output, no development root. `DATA_ROOT` es `DATA ONLY` y nunca `DEVELOPMENT_ROOT`.
- Los secretos permanecen fuera de Git en `PRIVATE_ROOT`.

No duplicar aquí la arquitectura Telchi detallada; `CONTEXT.md` es la autoridad.

El skill `.agents/skills/team360-project/SKILL.md` conserva workflows detallados. No cargarlo junto con todas las politicas por defecto; usarlo cuando la tarea requiera su flujo especifico.

## Limites de implementacion

- Hacer cambios pequenos, reversibles y limitados al objetivo.
- No tocar `team360_orquestador`, AG-UI, providers, frontend o knowledge si la tarea no los incluye.
- No crear motores paralelos cuando existe una implementacion equivalente.
- No reescribir migraciones aplicadas.
- No guardar secretos, tokens, passwords ni API keys en codigo, tests o documentacion.
- PostgreSQL es la verdad operacional; Milvus es un indice derivado y nunca decide permisos.
- Usar `psycopg 3 async` y `psycopg_pool.AsyncConnectionPool`; mantener SQL en repositories.
- No introducir SQLAlchemy, SQLModel o asyncpg como base sin una decision LAT explicita.
- LiteLLM se consume mediante adapters y aliases; no hardcodear providers ni ocultar fallos con fallback silencioso.
- Para `/t360`, `SrvRestAstroLS_v1/astro/src/components/global.js` es la unica fuente de verdad de URLs.
- Browser MCP es diagnostico exploratorio; Playwright + Chromium es el gate E2E reproducible.
- Autoridad operativa: la instruccion directa del responsable del proyecto autoriza la operacion dentro de su alcance y permisos efectivos. Ningun agente agrega aprobaciones, jerarquias administrativas ni bloqueos nuevos sin decision explicita; la trazabilidad se registra automaticamente, sin tramite adicional. Ver [team360-operational-authority-policy](lat.md/team360-operational-authority-policy.md).

## Validacion

Ejecutar siempre:

- `git diff --check`;
- tests focalizados del modulo afectado;
- revision del diff final.

Segun el cambio:

- backend: `cd SrvRestAstroLS_v1/backend && uv run pytest <paths>`;
- frontend: `cd SrvRestAstroLS_v1/astro && pnpm check`;
- paginas, configuracion o build: agregar `pnpm build`;
- E2E real: levantar servicios solo con `backend-dev.sh` y `astro-dev.sh`, luego usar `PLAYWRIGHT_SKIP_WEBSERVER=1`;
- servicios reales: ejecutar primero el preflight y comprobar provider/modelo real, auth, credito y ausencia de fallback silencioso;
- cambios en `lat.md/`: actualizar `lat.md/status_actual.md` y ejecutar `lat check`.

No declarar PASS solo por HTTP 200, por Browser MCP o por una entrada previa del status. Informar comandos, resultados y limitaciones observadas.

## Documentacion

Jerarquía: AGENTS (trabajo/ownership) → [estado GLOBAL](SrvRestAstroLS_v1/docs/status_actual.md) → [LAT](lat.md/lat.md) y autoridades locales → contratos, runbooks y evidencia.

- `SrvRestAstroLS_v1/docs/status_actual.md`: único estado técnico GLOBAL vigente y compacto. El nombre canónico de estados nuevos es `status_actual.md`, en minúsculas.
- `lat.md/status_actual.md`: mantenimiento de arquitectura LAT, no otro estado técnico GLOBAL.
- Estado local: usar el `status_actual.md` o autoridad existente enlazado desde el tablero GLOBAL; Telchi conserva `CONTEXT.md` para arquitectura, roots y etapas.
- `SrvRestAstroLS_v1/docs/status_historico_hasta_2026-06-28.md`: bitacora tecnica historica congelada.
- `lat.md/`: invariantes, contratos y decisiones estables; no usar para evidencia diaria.
- `docs/`: producto, negocio, estrategia y analisis no operativo.
- `data/reports/`: resultados, snapshots y evidencia generada.

No duplicar contenido: enlazar a la fuente canonica.

## Política LAT / Markdown

La documentación del proyecto debe seguir la política permanente definida en `lat.md/lat-documentation-policy.md`.

Antes de cerrar una tarea que crea o modifica documentación Markdown, ejecutar:

```bash
lat check md
lat check index
lat check sections
lat check code-refs
lat check
git diff --check
```

Si cualquier gate falla, no declarar PASS.

## Cierre

Reportar siempre:

- rama y objetivo;
- archivos modificados;
- validaciones ejecutadas y resultado;
- impacto transversal;
- riesgos, supuestos y proximo paso.
