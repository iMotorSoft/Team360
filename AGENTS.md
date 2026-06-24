# Team360 - Instrucciones Para Agentes

Trabajar siempre desde la raiz del proyecto:

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`

Antes de cambios relevantes, leer:

- `.agents/skills/team360-project/SKILL.md`
- `SrvRestAstroLS_v1/docs/status_actual.md`
- `lat.md/lat.md` cuando el cambio afecte arquitectura, dominio, IA, workers, knowledge, seguridad, paquetes o reglas transversales.

Al iniciar cualquier sesion de agente de codigo, seguir el protocolo obligatorio declarado en `.agents/skills/team360-project/SKILL.md`: leer reglas, verificar rama, verificar worktree y revisar `lat.md/team360-global-orchestration.md` si existe antes de modificar archivos.

Convencion operativa de ramas:

- `main`: estado estable validado.
- `feature/console-backend-core`: producto funcional vivo; backend, Console, UX real conectada/productiva, diagnosis assistant, LiteLLM, PostgreSQL, runtime y orquestacion global viva. Tambien puede contener labs cuando validan backend runtime, assistant productivo, UX conectada o experiencia final de consola.
- `feature/knowledge-ingestion-service`: knowledge ingestion / RAG / labs de knowledge; embeddings, chunking, scanner, retrieval, package behavior, golden answers, pruebas RAG/asistente como efecto del knowledge package y decision notes tecnicas de esa linea. No usar para desarrollo funcional productivo del runtime, backend o Console.
- `docs/knowledge-documents-foundation`: contenido y documentacion knowledge, estandares, paquetes, manuales, authoring, metadata y contenido curado.
- `ux/team360-console-design-handoff`: rama de diseno visual, frontend mock y handoff UX antes de integrar.
- Cuando una instruccion de trabajo mencione `desarrollo`, `dev` o `backend`, interpretar que la rama destino es `feature/console-backend-core`.
- `Objetivo: desarrollo` dentro de `SrvRestAstroLS_v1/docs/status_actual.md` describe el tipo de bitacora tecnica; para trabajo Git corresponde usar `feature/console-backend-core`.
- No crear ramas funcionales nuevas salvo necesidad puntual explicita.
- No crear una rama local llamada `desarrollo`.

Separacion documental:

- Comercial / negocio / producto / reportes no tecnicos: `docs/` y `data/reports/`
- Tecnico / codigo / backend / Astro / migraciones / runtime: `SrvRestAstroLS_v1/docs/`

Estructura documental vigente:

- `lat.md/`: arquitectura viva, invariantes estables, reglas de dominio y referencias anclables desde codigo.
- `docs/README.md`: indice raiz de documentacion no tecnica de runtime.
- `docs/negocio/`: contexto comercial, tesis de negocio, analisis de clientes, mercados y oportunidades.
- `docs/estrategia/`: decisiones de producto/plataforma, continuidad, inventarios y estrategia tecnico-negocio.
- `docs/analisis-tecnico/`: analisis tecnico no operativo, factibilidad y automatizacion que no pertenece al runtime.
- `docs/templates/`: plantillas documentales reutilizables.
- `data/reports/README.md`: indice de reportes y evidencias generadas.
- `data/reports/mercadolibre/netzaj-racing/`: relevamientos publicos, playbook e intents derivados del seller NETZAJ RACING.
- `data/reports/snapshots/`: snapshots historicos de estado del repo o de tareas puntuales.
- `SrvRestAstroLS_v1/docs/`: documentacion tecnica de desarrollo, backend, Astro, runtime, migraciones y estado tecnico.

Regla de ubicacion:

- Un documento narrativo de negocio/producto/estrategia va en `docs/`.
- Una evidencia generada, muestra, reporte exportable o snapshot va en `data/reports/`.
- Una nota tecnica ligada a codigo, backend, Astro, migraciones, runtime o validacion de desarrollo va en `SrvRestAstroLS_v1/docs/`.
- Un invariante estable de arquitectura, dominio, IA, workers, paquetes, knowledge o seguridad va en `lat.md/`.
- No duplicar el mismo contenido entre `lat.md/`, `docs/`, `data/reports/` y `SrvRestAstroLS_v1/docs/`; mover o enlazar, segun corresponda.

## Laboratorio tecnico

El proyecto puede usar `SrvRestAstroLS_v1/lab/` para experimentos tecnicos reproducibles y aislados de produccion.

Reglas principales:

- no modificar configuracion productiva desde `lab/`;
- cada experimento debe tener su propia carpeta y README;
- guardar resultados auditables en JSON/Markdown y, si aporta claridad, HTML;
- ejecutar comandos desde la raiz del proyecto;
- preferir `uv run` cuando corresponda;
- si un experimento se adopta, migrarlo luego a codigo productivo, tests o documentacion formal.

Ver detalles en `SrvRestAstroLS_v1/lab/README.md`.

Convencion para `lat.md`:

- `lat.md/lat.md` es el indice raiz de arquitectura viva.
- `lat.md/` guarda reglas estables e invariantes de Team360, no bitacoras diarias, evidencias ni status de implementacion.
- Usar documentos `kebab-case.md` por concepto, por ejemplo `multi-package-workers.md` o `knowledge-rag-graphrag.md`.
- Usar referencias `[[concepto]]` entre documentos y comentarios `# @lat: [[concepto#Seccion]]` en codigo solo cuando una funcion, clase o modulo implemente una regla no trivial.
- No llenar el codigo de anchors triviales; anclar cerca del punto decisivo donde se aplica la regla.
- Al crear o modificar documentos dentro de `lat.md/`, actualizar `lat.md/status_actual.md`.
- `SrvRestAstroLS_v1/docs/status_actual.md` sigue siendo la bitacora tecnica principal de desarrollo; `lat.md/` no reemplaza esa bitacora.

Convencion para `status_actual.md`:

- `SrvRestAstroLS_v1/docs/status_actual.md`
- Objetivo actual: `desarrollo`

Convencion para status locales por directorio documental:

- Todo directorio documental activo debe tener su propio `status_actual.md`.
- Ese archivo describe el ultimo estado y la ultima accion relevante dentro de ese directorio, no el estado global del proyecto.
- Al crear, mover, eliminar o reorganizar documentos dentro de un directorio, actualizar el `status_actual.md` de ese directorio.
- Si el cambio afecta a una subcarpeta y tambien al indice del padre, actualizar ambos status cuando corresponda.
- `SrvRestAstroLS_v1/docs/status_actual.md` sigue siendo la bitacora tecnica principal de desarrollo.
- Los status locales de `docs/` y `data/reports/` no deben mezclar decisiones tecnicas de runtime con material comercial o reportes.
- Carpetas auxiliares vacias que solo contienen `.gitkeep` no requieren `status_actual.md` hasta tener contenido documental real.

Que significa `desarrollo`:

- bitacora tecnica del estado de implementacion
- decisiones tecnicas y cambios realizados
- validaciones ejecutadas
- pendientes recomendados
- notas operativas o de seguridad relevantes para ingenieria

No interpretar ese documento como material comercial, de ventas, marketing o presentacion ejecutiva.

Si en el futuro se crean estados para otros objetivos, deben declararse de forma explicita.

Ejemplos posibles:

- `comercial`
- `producto`
- `operaciones`

Reglas rapidas:

- No mezclar criterios tecnicos con criterios comerciales.
- No inventar estructuras nuevas fuera del patron actual del repo.
- No tocar `team360_orquestador` salvo que el objetivo lo pida.
- No mezclar browser lab de Mercado Libre con AG-UI o frontend salvo que el objetivo lo pida.
- Preferir cambios chicos, claros y reversibles.
- Para conectividad frontend/backend de `/t360`, `SrvRestAstroLS_v1/astro/src/components/global.js` es la unica fuente de verdad: en desarrollo local y Browser MCP debe usarse `IS_REST_PRO=false` con `URL_REST_DEV=http://localhost:7050`; no corregir rutas tocando `astro.config.mjs`, API clients, componentes Svelte ni URLs hardcodeadas salvo instruccion explicita.
- Para validaciones de navegador, Playwright + Chromium es el gate E2E oficial; Browser MCP / `opencode-browser` es exploratorio y de diagnostico visual, no reemplaza Playwright para cerrar fases, regresiones o produccion. Ver `lat.md/browser-mcp-validation-policy.md`.
- Para validaciones Browser MCP / `opencode-browser`, usar `lat.md/browser-mcp-validation-policy.md`: antes de navegar deben responder backend `127.0.0.1:7050` y Astro `127.0.0.1:3050`; el agente puede bajar/subir esos dos servidores locales si hace falta; si Browser MCP falla, detener la prueba y avisar, sin reemplazarla por terminal, `curl`, Playwright, HTML o lectura de codigo salvo autorizacion explicita.
- Para despliegue frontend Astro de `team360.live` por `rsync`, seguir `lat.md/team360-frontend-rsync-deploy-policy.md`: verificar `IS_REST_PRO=true`, build limpio, fix en source y `dist`, backup remoto, dry-run revisado, rsync real, assets local=produccion y Playwright productivo antes de declarar PASS.
- Para despliegue backend de Team360 por `rsync`, seguir `lat.md/team360-backend-rsync-deploy-policy.md`: validar rama/HEAD, tests backend, exclusiones `.env*`/`.venv`, backup remoto, dry-run revisado, rsync real, preservar sensibles, no reiniciar automaticamente, esperar reinicio manual en `tmux`, health y smoke modelo real sin fallback antes de aprobar.
- Para QA browser dirigido con DeepSeek V4 Flash en OpenCode + `opencode-browser`, usar `lat.md/deepseek-v4-flash-opencode-browser.md`: fase browser atomica, herramientas `browsermcp_*`, snapshots antes/despues, no reemplazar navegador con terminal, evidencia explicita y detencion obligatoria.
- Antes de desarrollo, test, smoke, benchmark o prueba con servicios reales, ejecutar preflight obligatorio: PostgreSQL activo, Milvus activo y collection correcta, LiteLLM activo, `.bashrc`/env vars accesibles, `globalVar.py` importable cuando aplique, modelo registrado en LiteLLM y llamada real minima al modelo validando auth/credito/provider/endpoint/sin fallback silencioso. Si falla, no aceptar benchmark ni interpretar resultados como calidad del modulo. Ver `lat.md/service-preflight-methodology.md`.
- Actualizar `SrvRestAstroLS_v1/docs/status_actual.md` al cerrar tareas tecnicas importantes.
- Para Team360, la politica DB runtime se define en `lat.md/postgres-driver-policy.md`.

Formato recomendado para `status_actual.md`:

- `Objetivo: ...`
- `Ultima actualizacion: YYYY-MM-DD`
- `## Estado general`
- `## Acciones realizadas`
- entradas por fecha con titulo corto, por ejemplo: `### 2026-05-13 - Integracion inicial de ...`
- dentro de cada entrada: que se cambio, que no se toco, validacion, riesgos o notas si aplica
- `## Validacion`
- `## Pendientes recomendados`
- `## Notas de seguridad`
- Plantilla base disponible en: `docs/templates/status_actual_template.md`
