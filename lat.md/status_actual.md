# Status actual - lat.md

Este tablero resume el estado vigente de la arquitectura viva de Team360 y enlaza las fuentes operativas que conservan evidencia detallada.

Objetivo: `arquitectura-viva`

Última actualización: 2026-08-04.

## Estado vigente

Team360 mantiene una arquitectura funcional separada por fronteras explícitas de runtime, datos, frontend, knowledge y seguridad.

- PostgreSQL 18 es la verdad operacional del estado conversacional.
- Milvus 2.6 es un índice derivado para retrieval y no decide permisos.
- LiteLLM es el gateway de modelos mediante aliases y adapters.
- Vera pública usa Litestar, PostgreSQL, Milvus y LiteLLM sobre el alias `openai_gpt-5.4-nano`.
- El frontend usa Astro 6, Svelte 5, Tailwind CSS 4, DaisyUI 5 y `pnpm`.
- `/t360` resuelve URLs exclusivamente desde `SrvRestAstroLS_v1/astro/src/components/global.js`.
- Playwright + Chromium es el gate E2E reproducible; Browser MCP es diagnóstico exploratorio.
- El Diagnosticador embebible conserva el backend como autoridad de tenant, scope, origin y permisos.

## Cambios recientes

Esta sección conserva únicamente decisiones recientes que siguen afectando el estado vigente; la evidencia diaria vive fuera de LAT.

### Alias LiteLLM GPT-5.4 Nano

El runtime usa un alias alineado con GPT-5.4 Nano y selecciona el protocolo de forma explícita, sin inferirlo desde el nombre del modelo.

- Alias canónico: `openai_gpt-5.4-nano`.
- Upstream: `openai/gpt-5.4-nano`.
- Runtime público: `TEAM360_LITELLM_API_MODE=chat`.
- Responses API queda reservada para labs controlados con override explícito.
- Smoke directo real: contenido no vacío, `finish_reason=stop`, 38 tokens y 1149 ms.
- Validación Vera real: 10/10 escenarios PASS con PostgreSQL, Milvus y LiteLLM.

### Diagnosticador embebible

El componente externo dispone de loader versionado, verificación de integridad, autenticación por cliente y guías de instalación controladas.

- El loader y el entry publican integrity desde un manifest canónico.
- Los módulos cross-origin requieren CORS compatible en `/embed/` y en sus imports `/_astro/*`; HTTP `200` y MIME correcto no prueban ejecución.
- Un `200 / 0 B` puede representar un body bloqueado por CORS, por lo que el gate exige observar la cadena hasta `mount()`.
- Los fixtures E2E verifican loader, entry, cross-origin y montaje real.
- El cliente recibe `clientId`, snippet y requisitos de origin; no recibe secretos ni códigos internos.
- HTML, PHP y WordPress están documentados como superficies de integración.
- `/t360`, `PublicVeraEntry.svelte` y `global.js` conservan sus fronteras existentes.

### Autenticación Console

La fundación de autenticación Console usa PASETO v4.public sin reemplazar el HMAC request-bound del embed.

- PASETO aplica a access tokens de Console y futuras fronteras autenticadas.
- El embed mantiene HMAC-SHA256 ligado a mensaje, sesión y timestamp.
- Las claves privadas permanecen fuera del frontend y del repositorio.
- La autorización efectiva continúa dependiendo de PostgreSQL y del contexto resuelto server-side.

### Normalización para lat 0.11

La arquitectura viva cumple las validaciones de enlaces, índice, resúmenes de sección y referencias de código exigidas por `lat 0.11.0`.

- Se restauraron [[team360-frontend-base]] y [[team360-frontend-ui-policy]] desde sus ADR canónicos.
- El índice raíz incorpora [[status_actual]].
- Este tablero se compactó para eliminar duplicación histórica.
- Las secciones legacy recibieron resúmenes introductorios breves sin cambiar sus reglas.
- `lat check` y `lat check code-refs` finalizan en PASS.

### Política permanente de documentación LAT

La política [[lat-documentation-policy]] centraliza las reglas documentales para reducir prompts futuros y prevenir regresiones de estructura.

- Define reglas de encabezados, enlaces wiki, índice, status y no duplicación.
- AGENTS y el skill Team360 enlazan la fuente canónica sin copiarla completa.
- Los seis gates documentales son obligatorios antes de declarar PASS.

## Políticas canónicas activas

Estas referencias definen las invariantes que deben consultarse antes de cambiar cada frente técnico.

- Orquestación y ownership: [[team360-global-orchestration]].
- Runtime público Vera: [[team360-runtime-operational-policy]].
- PostgreSQL y repositories: [[postgres-driver-policy]].
- Preflight de servicios reales: [[service-preflight-methodology]].
- Arquitectura del Diagnosticador: [[diagnosticador-embeddable-component-architecture]].
- Base frontend: [[team360-frontend-base]].
- UI y package manager: [[team360-frontend-ui-policy]].
- URLs frontend: [[team360-frontend-url-source-of-truth]].
- Browser QA: [[browser-mcp-validation-policy]].
- Playwright MCP: [[playwright-mcp-server-policy]].
- Debugging por causa raíz: [[team360-root-cause-debugging-policy]].
- Documentación LAT y Markdown: [[lat-documentation-policy]].
- Deploy backend: [[team360-backend-rsync-deploy-policy]].
- Deploy frontend: [[team360-frontend-rsync-deploy-policy]].

## Validación vigente

Los gates recientes confirman el cambio de alias y las fronteras principales; no sustituyen el preflight requerido para futuras corridas reales.

| Validación | Resultado vigente |
| --- | --- |
| Backend focalizado LiteLLM/diagnosis | 166 PASS |
| Lab preflight de modelos | 10 PASS |
| Frontend `pnpm check` | PASS, 0 errores |
| Smoke directo LiteLLM GPT-5.4 Nano | PASS, contenido no vacío |
| Conversación productiva Vera | 10/10 escenarios PASS |
| Milvus scope/version | ALIGNED, 183 filas |
| `git diff --check` del cambio de alias | PASS |

## Mantenimiento

Este archivo debe permanecer compacto y describir estado actual, no acumular fases históricas ni duplicar evidencia operativa.

- Registrar evidencia diaria en `SrvRestAstroLS_v1/docs/status_actual.md`.
- Conservar historia congelada en `SrvRestAstroLS_v1/docs/status_historico_hasta_2026-06-28.md` y Git.
- Mantener aquí únicamente invariantes activas, cambios recientes relevantes y enlaces canónicos.
- Actualizar este tablero cuando cambie un documento de `lat.md/`.
- Ejecutar `lat check` y `git diff --check` antes de cerrar cambios LAT.

## Fuentes operativas

Las fuentes siguientes contienen el tablero técnico detallado y las instrucciones de colaboración que complementan esta vista arquitectónica.

- `SrvRestAstroLS_v1/docs/status_actual.md`
- `AGENTS.md`
- `.agents/skills/team360-project/SKILL.md`
- [[team360-knowledge-map]]
