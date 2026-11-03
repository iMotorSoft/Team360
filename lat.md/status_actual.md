# Status actual - lat.md

Registro compacto de mantenimiento LAT, no otro estado técnico GLOBAL. El único tablero vigente es [SrvRestAstroLS_v1/docs/status_actual.md](../SrvRestAstroLS_v1/docs/status_actual.md), con navegación a autoridades locales.

Objetivo: `arquitectura-viva`

Última actualización: 2026-10-06 (normalización documental; fronteras Evolution y seguridad compartida preservadas).

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
- La orquestación global define `MODULE_LOCAL`, `SHARED`, `GLOBAL` y el overlay `PRODUCTION_PROTECTED`, con edición local concurrente y ventanas exclusivas para Git y cambios transversales.
- El module registry backend está implementado y monta Flow una sola vez desde `ROUTE_HANDLERS` en `routes.py`; la afirmación histórica de export vacío ya no describe el módulo vigente.
- El coordinador Python y su inventario JSON continúan pendientes.

## Cambios recientes

Esta sección conserva únicamente decisiones recientes que siguen afectando el estado vigente; la evidencia diaria vive fuera de LAT.

### Autoridad operativa

[[team360-operational-authority-policy]] fija que la instrucción directa del owner autoriza la operación y que ningún agente agrega aprobaciones, jerarquías administrativas ni bloqueos nuevos sin decisión explícita.

- Origen: un agente convirtió `authorized_by` en condición para publicar la Foundation de ventas de Telchi; el requisito no tenía decisión del owner y detuvo la promoción ya autorizada.
- Corrección: se retiró el carácter bloqueante, se conservó la auditoría automática del journal y se mantuvieron CAS, hashes, locks, recuperación y rollback. [[team360-global-orchestration]] conserva las reglas de ownership.

### Jerarquía documental y GLOBAL

[[lat-documentation-policy]] fija un solo estado técnico GLOBAL; [[team360-global-orchestration]] define lectura abierta y un writer GLOBAL coordinado, sin locks complejos.

- AGENTS define trabajo y ownership; LAT conserva invariantes; el tablero técnico enlaza autoridades locales y estas enlazan contratos/reportes.
- Una ventana documental no autoriza código, infraestructura, Git ni producción. Los agentes locales pueden continuar sin alterar condiciones GLOBAL; procesos activos no prueban ownership.
- Estados nuevos usan `status_actual.md` en minúsculas; Telchi conserva CONTEXT como autoridad de arquitectura, roots y etapas.
- El cuerpo íntegro del tablero anterior, incluidos cambios preexistentes, se conserva en el [histórico de normalización](../SrvRestAstroLS_v1/docs/status_historico_hasta_normalizacion_2026-10-06.md). Cierres/reportes existentes no se reescriben.
- Srv05: `full` es inventario registrado, no Full Team360 Gate. Compatibilidad/modelado estático no implican lifecycle selectivo, preflight operacional ni migración productiva; consultar el tablero técnico para estado y evidencia.

### Frontera Evolution / Team360 Messaging

[[team360-platform#Team360 Platform#WhatsApp transport boundary]] fija la separación entre transporte WhatsApp y autoridad conversacional de Team360.

- Adapter Team360 y latencia fija: PASS con veinte pares WhatsApp reales, delivery/read, deduplicación y recuperación; conversación en tablas core, transporte Evolution sin inteligencia.
- El bloque Meta de `globalVar.py` consume exclusivamente `META_TEAM360_*`, sin fallback a otros proyectos; tests aislados cubren coexistencia, ausencias y configuración legacy-only.
- Gates `TEAM360_MESSAGING_EVOLUTION_ADAPTER_V1` y `TEAM360_MESSAGING_FIXED_RESPONSE_LATENCY_V1`: PASS. [[team360-platform#Team360 Platform#WhatsApp transport boundary#Messaging-only DEV bootstrap]] evita dependencias ajenas sin alterar normal; runtime temporal cerrado, evidencia y benchmark separados en status técnico.
- [[team360-platform#Team360 Platform#WhatsApp transport boundary#Fixed response conversation ownership]] define idempotencia persistida y ausencia de reintentos automáticos en resultados inciertos.
- La medición observable de veinte respuestas es GOOD; el gate formal del benchmark sigue PENDING por desgloses ausentes y un intento fuera de orden ignorado.
- Detalles y evidencia en [status técnico canónico](../SrvRestAstroLS_v1/docs/status_actual.md) y [Messaging README](../SrvRestAstroLS_v1/backend/modules/messaging/README.md), sin duplicar el reporte aquí.

### Ownership modular y concurrencia

La política [[team360-global-orchestration]] es la fuente humana canónica para ownership por paths, coordinación entre agentes y alta inicial de módulos en el registry.

- Varios agentes pueden editar scopes `MODULE_LOCAL` asignados y disjuntos.
- `SHARED` requiere coordinación; `GLOBAL` y Git requieren ventana exclusiva.
- Solo Diagnosticador/Vera y el embed productivo están hoy declarados `PRODUCTION_PROTECTED`.
- Ownership por paths no reemplaza ownership por ramas; Knowledge conserva su política actual.

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

## Referencia de validación del cambio de alias

Esta tabla conserva resultados fechados del cierre del alias, no disponibilidad actual ni evidencia de esta normalización. El estado técnico y los límites vigentes se consultan en el tablero GLOBAL.

| Validación | Resultado de aquel cierre |
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

- Registrar en el tablero GLOBAL solo estado vigente + decisión + límite + enlace; evidencia diaria en reports/fases propios.
- Conservar historia congelada en los históricos enlazados desde el tablero técnico y en Git.
- Mantener aquí únicamente invariantes activas, cambios recientes relevantes y enlaces canónicos.
- Actualizar este tablero cuando cambie un documento de `lat.md/`.
- Ejecutar `lat check` y `git diff --check` antes de cerrar cambios LAT.

## Fuentes operativas

Las fuentes siguientes contienen el tablero técnico detallado y las instrucciones de colaboración que complementan esta vista arquitectónica.

- [Estado técnico GLOBAL y autoridades locales](../SrvRestAstroLS_v1/docs/status_actual.md).
- [AGENTS](../AGENTS.md).
- [Skill Team360](../.agents/skills/team360-project/SKILL.md).
- [[team360-knowledge-map]]
