# Status actual - Team360

Objetivo: `desarrollo`

Ultima actualizacion: 2026-06-28 (Fases 3 a 5 y reorganizacion documental publicadas)

Este documento es un tablero del estado vigente. La bitacora detallada previa, incluidas las fases actuales aun sin commit, se conserva en `status_historico_hasta_2026-06-28.md` y en Git.

## Directorio y rama

- raiz: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`
- rama funcional actual: `feature/console-backend-core`
- las Fases 3 a 5 del Diagnosticador embebible quedaron confirmadas en `cdd1b1b` y publicadas en `origin/feature/console-backend-core`

## Estado general

- Team360 mantiene frontend Astro 6 + Svelte 5 y backend Litestar.
- PostgreSQL 18 es la verdad operacional del estado conversacional.
- Milvus 2.6 es el indice vectorial derivado para retrieval.
- LiteLLM es el gateway de modelos mediante aliases y adapters.
- El runtime publico de Vera usa `/t360 -> Litestar -> PostgreSQL -> Milvus -> LiteLLM`.
- Las migraciones `001` a `004` y la Fase 1 de `automation_diagnosis` fueron validadas anteriormente.
- La politica DB vigente exige `psycopg 3 async`, pools separados y SQL dentro de repositories.

Referencias canonicas:

- `lat.md/team360-runtime-operational-policy.md`
- `lat.md/postgres-driver-policy.md`
- `lat.md/service-preflight-methodology.md`
- `lat.md/diagnosticador-embeddable-component-architecture.md`

## Trabajo actual - Diagnosticador embebible

Estado: Fases 1 a 5 implementadas; Fases 3 a 5 confirmadas en `cdd1b1b`.

Implementado:

- `DiagnosticadorCore.svelte` extrae el nucleo conversacional de Vera.
- La configuracion de sesion e identidad vive en modulos reutilizables.
- `/t360-diagnosticador-lab` monta el Core fuera de `/t360` con session storage aislado.
- `apiBaseUrl` es configurable en `DiagnosticadorCore` y en `sendPublicTurn`.
- `publicDiagnosisContext` es configurable; el lab envia el contexto explicito y Vera conserva el comportamiento por defecto.
- Vera mantiene compatibilidad hacia atras mediante `API_BASE_URL` de `global.js`.
- No se creo iframe, Web Component, package npm ni workspace adicional.

Archivos confirmados por `cdd1b1b`:

- modificados: `publicDiagnosis.ts`, `DiagnosticadorCore.svelte`, `config/defaults.ts`, `config/types.ts`;
- nuevos: `DiagnosticadorEmbedLab.svelte`, `t360-diagnosticador-lab.astro`, `diagnosticador-embed-lab.spec.ts`;
- `lat.md/status_actual.md` quedo incluido en el mismo commit funcional.

## Ultima validacion disponible

Validacion estatica del bloque actual:

- `pnpm check`: 0 errores, 0 warnings, 3 hints preexistentes;
- `pnpm build`: 140 paginas, sin errores;
- `git diff --check`: PASS.

Playwright con servidores externos y `PLAYWRIGHT_SKIP_WEBSERVER=1`:

- `diagnosticador-embed-lab.spec.ts`: 1/1 PASS;
- `public-vera.spec.ts`: 12/12 PASS, 2 skips preexistentes;
- `public-vera-new-conversation.spec.ts`: 1/1 PASS;
- total focalizado: 14/14 PASS;
- sesion del lab y sesion de Vera aisladas;
- la request del lab uso la URL explicita y el contexto publico esperados.

Limites de esta validacion:

- PostgreSQL, Milvus y LiteLLM no fueron operados durante el ultimo bloque;
- no se ejecuto un preflight productivo completo;
- el bloque funcional y la reorganizacion documental fueron confirmados y publicados;
- los resultados anteriores deben volver a ejecutarse si cambia codigo funcional.

## Calidad documental y operativa

- `AGENTS.md` es ahora la fuente operativa canonica compartida por Codex, OpenCode y Crush.
- la reorganizacion de `AGENTS.md`, status compacto e historial quedo confirmada en `8c51dca` y publicada.
- `.opencode-rules` queda como legado no cargado por la configuracion efectiva de OpenCode; debe retirarse o migrarse en una tarea posterior.
- `lat check` tiene una deuda preexistente de 129 errores: 110 secciones sin leading paragraph, 10 summaries extensos, 6 links rotos y 3 errores adicionales de indice.
- `lat search` requiere configurar `LAT_LLM_KEY`, `LAT_LLM_KEY_FILE` o `LAT_LLM_KEY_HELPER`; mientras tanto se usa `lat locate`.
- No existe CI ni task runner raiz; las validaciones siguen dependiendo de ejecucion local.

## Pendientes prioritarios

1. Revisar y cerrar el bloque actual del Diagnosticador embebible sin mezclar otros cambios.
2. Ejecutar nuevamente los tests focalizados antes del commit.
3. Corregir `lat check` hasta cero errores.
4. Reducir o retirar reglas duplicadas en `.agents/skills/team360-project/SKILL.md` y `.opencode-rules`.
5. Crear comandos canonicos y CI para backend, frontend, LAT y E2E.
6. Corregir evidencia hardcodeada, I/O sincronico dentro de handlers async y posibles fallbacks silenciosos del runtime.
7. Evaluar Milvus frente a pgvector con metricas reales y hacer que LiteLLM registre tokens, coste, latencia y provider efectivo.

## Notas de seguridad

- No guardar secretos en el repositorio ni imprimirlos en comandos o documentacion.
- Las credenciales expuestas previamente deben rotarse.
- Evitar exportar todas las credenciales globalmente desde `~/.bashrc`; preferir carga acotada al proyecto o un gestor de secretos.

## Historial

- historial tecnico completo hasta esta reorganizacion: `status_historico_hasta_2026-06-28.md`;
- arquitectura viva e invariantes: `lat.md/lat.md`;
- orquestacion transversal: `lat.md/team360-global-orchestration.md`;
- Git conserva la evolucion exacta de cada cambio confirmado.
