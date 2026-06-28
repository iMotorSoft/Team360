# Team360 - Instrucciones para agentes

Este archivo es la fuente operativa canonica para Codex, OpenCode, Crush y otros agentes que trabajen en Team360. Las politicas extensas se cargan solo cuando la tarea las necesita.

## Inicio obligatorio

1. Trabajar desde `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`.
2. Ejecutar `git branch --show-current` y `git status --short`.
3. Leer `SrvRestAstroLS_v1/docs/status_actual.md` para conocer el estado vigente.
4. Identificar el frente y consultar solo las referencias de la tabla siguiente.
5. No cambiar de rama ni pisar cambios existentes. Si hay archivos modificados, preservar ownership y editar solo paths compatibles con la tarea.
6. Un solo agente puede escribir sobre un worktree. Otros agentes deben trabajar en modo read-only o en otro worktree.

No hacer commit, push, merge, rebase, reset, clean, stash, checkout forzado ni borrar ramas salvo pedido explicito del usuario.

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

- `SrvRestAstroLS_v1/docs/status_actual.md`: tablero tecnico vigente y compacto.
- `SrvRestAstroLS_v1/docs/status_historico_hasta_2026-06-28.md`: bitacora tecnica historica congelada.
- `lat.md/`: invariantes, contratos y decisiones estables; no usar para evidencia diaria.
- `docs/`: producto, negocio, estrategia y analisis no operativo.
- `data/reports/`: resultados, snapshots y evidencia generada.

No duplicar contenido: enlazar a la fuente canonica.

## Cierre

Reportar siempre:

- rama y objetivo;
- archivos modificados;
- validaciones ejecutadas y resultado;
- impacto transversal;
- riesgos, supuestos y proximo paso.
