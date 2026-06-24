# Status actual - lat.md

Objetivo: `arquitectura-viva`

Ultima actualizacion: 2026-06-24 (Politica root cause)

## Estado general

`lat.md/` contiene definiciones de alto nivel, reglas de negocio, decisiones de arquitectura e invariantes para Team360.

Esta capa sigue el patron usado en JudaismoenVivo: indice raiz `lat.md/lat.md`, documentos por concepto y referencias `[[...]]` que pueden anclarse desde codigo con comentarios `@lat`. Las reglas de uso quedaron declaradas en `AGENTS.md` y en `.agents/skills/team360-project/SKILL.md`.

## Acciones realizadas

### 2026-06-24 - Politica root cause para bugs manuales

- Se agrego `team360-root-cause-debugging-policy.md` como invariante operativo
  para investigar bugs no triviales de Team360.
- La politica adapta el concepto util de gstack `/investigate`: no corregir sin
  causa raiz verificable, reproducir el sintoma, formular una hipotesis
  explicita, confirmar evidencia, aplicar fix minimo y convertir el caso en
  regresion backend/Playwright cuando corresponda.
- Se documento su uso obligatorio para bugs que aparecen en prueba manual
  aunque los tests pasen, diferencias local/produccion, interaction blocks,
  touch mobile, requests duplicados, persistencia, fallback de modelo y deploys.
- Se fijo la regla de tres hipotesis: si tres hipotesis verificadas fallan, se
  detiene el parcheo y se reporta posible problema de arquitectura, contrato,
  estado persistido o entorno.
- Se enlazo desde `lat.md/lat.md`, `AGENTS.md` y
  `.agents/skills/team360-project/SKILL.md`.
- No se instalo gstack, no se adopto su skill completo y no se modifico codigo
  productivo, frontend, backend, DB, Milvus, LiteLLM ni servicios.

### 2026-06-24 - Politica Mermaid para diagramas

- Se agrego `team360-mermaid-diagram-policy.md` como invariante documental para
  diagramas tecnicos de Team360.
- Se definio Mermaid como fuente canonica versionable en Git, embebida en
  Markdown o en archivos `.mmd` cuando el diagrama sea largo o reutilizable.
- Se establecio que SVG, PNG, PDF y Excalidraw son artefactos derivados
  opcionales, no fuente de verdad tecnica.
- Se dejo explicito que Team360 no requiere instalacion global de Mermaid y que
  cualquier render automatico futuro debe versionarse localmente en el proyecto.
- Se tomo de gstack `/diagram` solo el concepto de fuente textual revisable y
  renders derivados, sin adoptar su skill completo, telemetry, estado global,
  hooks, routing, browse daemon ni commits automaticos.
- Se actualizaron `lat.md/lat.md`, `AGENTS.md` y
  `.agents/skills/team360-project/SKILL.md`.

### 2026-06-24 - Politica rsync para deploy backend

- Se agrego `team360-backend-rsync-deploy-policy.md` como invariante operativo
  para publicar el backend de Team360 por `rsync`.
- La politica fija el flujo canonico: validar rama/HEAD, distinguir HEAD vs
  worktree, comparar con origin, ejecutar tests backend, validar SSH/destino,
  preservar `.env*` y `.venv`, crear backup remoto, revisar dry-run con
  `--delete`, ejecutar rsync real y verificar archivos remotos.
- Se establecio que el procedimiento no reinicia automaticamente el backend ni
  toca `tmux`, `systemctl`, Nginx, frontend, PostgreSQL, Milvus ni LiteLLM; el
  reinicio productivo queda como paso manual posterior en `tmux`.
- Se documento que la aprobacion requiere health remoto/interno, smoke con
  modelo real y `fallback_used=false`, smoke conversacional, 0 errores 5xx,
  0 requests duplicados y Playwright productivo.
- Se actualizaron `lat.md/lat.md`, `AGENTS.md`,
  `.agents/skills/team360-project/SKILL.md` y
  `team360-runtime-operational-policy.md` para enlazar la politica.
- No se ejecuto deploy ni se modifico produccion, backend runtime, frontend,
  DB, Milvus, LiteLLM, Nginx ni tmux.

### 2026-06-24 - Politica rsync para deploy frontend Astro

- Se agrego `team360-frontend-rsync-deploy-policy.md` como invariante
  operativo para publicar el frontend Astro de `team360.live` por `rsync`.
- La politica fija el flujo canonico: build productivo, validacion local,
  backup remoto, dry-run, rsync real, verificacion de assets servidos y smoke
  productivo.
- Se documento el destino remoto oficial, la obligacion de conservar la barra
  final en `.../astro/dist/`, el uso obligatorio de `--delete`, la revision del
  dry-run y la condicion `dist local = dist remoto = assets servidos por
  team360.live`.
- Se establecio que un rsync exitoso no prueba el despliegue: el cierre requiere
  `IS_REST_PRO=true`, `pnpm check`, build limpio, fix presente en source y
  `dist`, backup, metadata intacta, Playwright productivo, smoke UX y 0 errores
  criticos.
- Se actualizaron `lat.md/lat.md`, `AGENTS.md`,
  `.agents/skills/team360-project/SKILL.md` y la nota historica
  `SrvRestAstroLS_v1/docs/team360_live_frontend_deploy_20260618.md`.
- No se ejecuto deploy ni se modifico produccion, backend, DB, Milvus, LiteLLM
  ni Nginx.

### 2026-06-24 - Politica de validacion de navegador

- Se amplio `browser-mcp-validation-policy.md` para convertirlo en la politica
  unica de validacion de navegador de Team360.
- Se fijo Playwright + Chromium como gate E2E oficial para regresiones, flujos
  completos, interaction blocks, validaciones productivas y cierres de fase.
- Se reclasifico Browser MCP / `opencode-browser` como herramienta exploratoria
  y de diagnostico visual: ayuda a descubrir, reproducir e inspeccionar, pero
  no reemplaza Playwright como evidencia de PASS reproducible.
- Se documentaron launchers oficiales (`backend-dev.sh`, `astro-dev.sh`),
  configuracion local con `IS_REST_PRO=false`, variables estandar de
  Playwright, reglas para produccion, build productivo, pruebas moviles tactiles
  y evidencia minima ante PASS/fallo.
- Se actualizo el indice `lat.md/lat.md`, la guia
  `deepseek-v4-flash-opencode-browser.md`, `AGENTS.md` y el skill propio
  `.agents/skills/team360-project/SKILL.md` para que los agentes carguen la
  nueva jerarquia: Playwright demuestra, Browser MCP explora.
- No se modifico codigo productivo, frontend, backend, DB, Milvus, LiteLLM ni
  configuracion de servicios.

### 2026-06-22 - Refuerzo de `global.js` como control de conectividad

- Se reforzo `team360-frontend-url-source-of-truth.md` para aclarar que
  `global.js` es el unico punto de control de conectividad frontend/backend.
- Para desarrollo local, Browser MCP, Playwright real de `/t360` y validacion
  contra backend `7050`, `IS_REST_PRO` debe estar en `false` y `URL_REST_DEV`
  debe apuntar a `http://localhost:7050`.
- Se dejo explicitado que `IS_REST_PRO=true` con `URL_REST_PRO=""` usa rutas
  relativas `/api` y solo es valido si existe proxy/reverse proxy documentado.
- Se agrego la regla de no corregir conectividad de `/t360` tocando
  `astro.config.mjs`, API clients, componentes Svelte ni URLs hardcodeadas salvo
  instruccion explicita.

### 2026-06-22 - Politica general de Browser MCP

- Se agrego `browser-mcp-validation-policy.md` como regla operativa estable
  para validaciones Browser MCP / `opencode-browser` sobre Team360.
- Se fijo como precondicion que backend Litestar responda en `127.0.0.1:7050`
  y Astro en `127.0.0.1:3050` antes de iniciar la fase browser.
- Se autorizo bajar y volver a levantar solo los procesos locales de backend y
  Astro cuando sea necesario para validar contra el estado correcto; no aplica a
  PostgreSQL, Milvus ni LiteLLM salvo pedido explicito.
- Se documento que cualquier falla de Browser MCP obliga a detener la prueba,
  reportar el paso/error/estado de servidores y no reemplazar la validacion con
  terminal, `curl`, Playwright, HTML o lectura de codigo sin autorizacion.
- Se agrego la referencia `[[browser-mcp-validation-policy]]` al indice
  `lat.md/lat.md`.

### 2026-06-20 - Comando canonico de arranque productivo backend Vera

- Se actualizo `team360-runtime-operational-policy.md` con la linea canonica
  actual para levantar el backend productivo remoto de Vera:
  `uv run uvicorn ls_iMotorSoft_Srv01:app --host 127.0.0.1 --port 7050`.
- Se documento que `TEAM360_BACKEND_DEBUG` no debe definirse en produccion y
  que Litestar debe quedar con `debug=False` por defecto.
- Se aclaro la diferencia entre variables efectivas y marcadores operativos:
  `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres` es el switch real de estado
  persistido; `TEAM360_EMBEDDING_VERSION` es la variable efectiva para version
  de embeddings Milvus; `TEAM360_PUBLIC_*` documenta contexto publico esperado.
- Se dejo explicitado que `/api/env` y `/api/config` son rutas de scanner
  externas y deben responder `404 Not Found` controlado, sin crear endpoints
  sensibles ni tracebacks por debug.

### 2026-06-18 - Politica Responses API para GPT-5.4 Nano

- Se aclaro en `team360-runtime-operational-policy.md` que la ruta publica
  validada de Vera sigue usando Chat Completions sin `reasoning_effort`.
- Se documento la excepcion para labs, compatibilidad o evaluaciones controladas
  con Responses API: cuando el upstream efectivo es `openai/gpt-5.4-nano`, el
  valor operativo de `reasoning.effort` debe ser `low`.
- Se dejo explicitado que `minimal` no debe usarse para ese upstream y que esta
  excepcion no cambia la configuracion principal de `/t360`.

### 2026-06-18 - Guia DeepSeek V4 Flash + opencode-browser para agentes

- Se agrego `deepseek-v4-flash-opencode-browser.md` como invariante operativo
  transversal para agentes.
- Se clasifico el uso validado de DeepSeek V4 Flash con OpenCode +
  `opencode-browser`: browser QA dirigido, smoke tests, validacion
  frontend/backend acotada, prompts atomicos, snapshots y punto de detencion.
- Se documento que `browsermcp_*` debe usarse como herramienta obligatoria
  durante la fase browser y que terminal, `curl`, HTML directo o Playwright no
  reemplazan la validacion real de UI.
- Se agregaron plantillas de prompt para navegacion minima, inspeccion de UI,
  interaccion basica, envio de mensaje, validacion frontend/backend y smoke
  repetible sobre `http://127.0.0.1:3050/t360`.
- Se enlazo el documento desde `lat.md/lat.md` y desde
  `model-selection-routing.md`.
- Se actualizaron `AGENTS.md` y `.agents/skills/team360-project/SKILL.md` para
  que la guia quede visible en el protocolo de agentes.
- No se modifico codigo productivo, runtime, frontend, backend, DB, Milvus ni
  LiteLLM.

### 2026-06-17 - Politica operativa runtime publico Vera

- Se agrego `team360-runtime-operational-policy.md` como invariante estable para
  la experiencia publica `/t360` y el endpoint `POST /api/diagnosis/turn`.
- Se documento el flujo validado: Astro/Svelte -> Litestar -> PostgreSQL 18 ->
  Milvus 2.6 -> LiteLLM -> `openai_gpt-5-nano` -> `openai/gpt-5.4-nano`.
- Se fijaron puertos operativos, variables de entorno conceptuales, coleccion
  Milvus `team360_sales_diagnosis_knowledge_v1`, modo LiteLLM
  `chat`, endpoint base `http://localhost:4000/v1` y regla de no usar OpenAI
  directo como ruta principal.
- Se documento que `global.js` es fuente efectiva de `/t360` y que el proxy
  Astro hacia `8000` es una inconsistencia conocida pendiente de unificacion.
- Se reforzaron las reglas de secretos: no imprimir DSN con password, master
  keys ni claves upstream; usar `postgresql://administrator:***@localhost:5432/team360`
  como representacion sanitizada.
- Se actualizo `lat.md/lat.md` con la referencia
  `[[team360-runtime-operational-policy]]`.

### 2026-06-16 - Frontend URL source of truth invariant

- Se agrego `team360-frontend-url-source-of-truth.md` como invariante de arquitectura frontend.
- Se fijaron 5 reglas:
  1. `global.js` es la unica fuente de verdad para endpoints REST, URLs de site y SSE.
  2. No hardcodear URLs fuera de `global.js`.
  3. Toggle dev/pro exclusivo via `IS_REST_PRO` en `global.js`.
  4. API clients en `src/lib/` deben importar desde `global.js`.
  5. `global.d.ts` debe sincronizarse con `global.js`.
- Se auditaron `src/lib/` y `src/components/` (33 archivos limpios, 3 corregidos):
  - `src/lib/api/diagnosis.ts`: migrado a `API_BASE_URL` desde global.js.
  - `MarketingFooter.astro` y `MarketingHeader.astro`: migrados a `CONSOLE_SITE_URL` desde global.js.
- Validacion: `pnpm check` = 0 errors, 0 warnings, 0 hints.
- Se actualizo `lat.md/lat.md` con referencia `[[team360-frontend-url-source-of-truth]]`.

### 2026-06-14 - Modelo T360 Pack, Task, Flow, Integrate y Diagnostico

- Se agrego `team360-pack-task-diagnosis-model.md` como invariante conceptual y comercial transversal.
- Se definieron T360 Pack, T360 Task, T360 Pack Flow, T360 Pack Integrate y modos de ejecucion Scheduled, On-Demand y Event-Driven.
- Se fijo que el Diagnostico Team360 debe diagnosticar la operacion real del cliente y traducirla en una arquitectura posible de solucion, aunque todavia no exista el Pack o Task exacta.
- Se documento la clasificacion de resultado: disponible hoy, configurable/armable, requiere desarrollo y no conviene vender todavia.
- Se reforzo la regla: automatizable no significa vendible hoy.
- Se actualizo `lat.md/lat.md` con la referencia `[[team360-pack-task-diagnosis-model]]`.
- Se actualizo `team360-global-orchestration.md` para enlazar el modelo desde decisiones globales de producto.
- No se implemento codigo, no se tocaron migraciones, runtime, frontend ni `knowledge/`.

### 2026-06-12 - Metodologia obligatoria de preflight de servicios

- Se agrego `service-preflight-methodology.md` como invariante estable para
  desarrollo, tests, smokes, benchmarks y pruebas con servicios reales.
- Se fijo la regla central: no aceptar benchmarks ni conclusiones de calidad si
  el preflight falla.
- El checklist obligatorio cubre PostgreSQL, Milvus, collection correcta,
  LiteLLM, `.bashrc`/env vars, `globalVar.py`, alias registrado en LiteLLM y
  llamada real minima al modelo para validar auth/credito/provider/endpoint.
- Se actualizo `lat.md/lat.md` con la referencia
  `[[service-preflight-methodology]]`.
- No se implemento codigo runtime ni migraciones.

### 2026-06-10 - Ajuste de ownership por rama

- Se refinó `team360-global-orchestration.md` para evitar ambigüedad entre producto funcional vivo, labs de knowledge/RAG, documentación editorial y handoff visual.
- `feature/console-backend-core` queda descrita como desarrollo funcional principal/producto funcional vivo; los labs solo aplican allí cuando validan backend runtime, assistant productivo, UX conectada o experiencia final de consola.
- `feature/knowledge-ingestion-service` queda descrita como knowledge ingestion / RAG / labs de knowledge, incluyendo pruebas RAG/asistente como efecto del knowledge package y decision notes técnicas de esa línea.
- Se actualizó el mapa rápido de ramas en `.agents/skills/team360-project/SKILL.md` y la convención operativa en `AGENTS.md`.
- No se modificó código productivo, frontend, backend runtime ni labs.

### 2026-06-10 - Orquestación global entre ramas y frentes

- Se creo `team360-global-orchestration.md` como documento transversal de arquitectura viva.
- Se documento el mapa actual de ramas (`main`, `feature/console-backend-core`, `ux/team360-console-design-handoff`, `feature/knowledge-ingestion-service`, `docs/knowledge-documents-foundation`) y sus responsabilidades.
- Se fijo la regla operativa: trabajar separado, decidir globalmente.
- Se agregaron reglas para coordinar UX real vs handoff visual, knowledge ingestion vs documentacion editorial, ownership de `lab/` por hipotesis validada y cierre de trabajo por rama.
- Se registraron decisiones globales de producto: `pkg_sales_diagnosis` evolutivo, Team360.live como primer contexto de validacion, Vera como marca visible, diagnosis mas amplio que ventas y capacidades futuras no vendibles como listas.
- Se actualizo `lat.md/lat.md` con la referencia `[[team360-global-orchestration]]`.
- No se modifico codigo productivo, migraciones, runtime, frontend ni documentos knowledge editoriales.

### 2026-06-07 - Diseno tecnico Knowledge Ingestion multi-scope / multi-nivel

- Se creo `SrvRestAstroLS_v1/docs/knowledge_ingestion_multiscope_design_20260607.md` como documento de diseno tecnico.
- El diseno referencia y extiende los invariantes existentes en `[[knowledge-scope-contract]]` y `[[ai-diagnosis-rag-runtime]]`.
- Se propusieron nuevas entidades conceptuales (KnowledgeMap, KnowledgeNode, KnowledgeAccessPolicy, KnowledgeRetrievalPolicy) que complementan el contrato canonico sin reemplazarlo.
- Se documentaron 8 niveles de scope y cascada de retrieval por capas.
- El documento es de diseno solamente; no crea nuevos invariantes en `lat.md/` ni modifica contratos existentes.
- No se implemento codigo, no se tocaron DBs ni migraciones.

### 2026-06-07 - Fase 1 Knowledge Ingestion Platform Service

- Se implemento la Fase 1 minima del servicio de ingesta, basada en el diseno tecnico.
- Migracion 006: `knowledge_ingestion_runs`, `node_path` en `knowledge_documents`, `node_path` + `permission_tags` en `knowledge_chunks`, seed de `knowledge_ingestion_worker`.
- Modulo backend `modules/knowledge_ingestion/` con schemas, repository y worker skeleton.
- 20 tests de validacion de metadata de ingesta.
- No se agregaron columnas a `knowledge_chunk_embeddings` (difiere a Fase 2).
- No se tocaron invariantes de arquitectura ni contratos existentes en `lat.md/`.

### 2026-06-07 - Fase 1.1 Hardening de Knowledge Ingestion Platform Service

- Revision sistematica de migracion 006, schemas, repository, worker y tests.
- Migration 006: se agrego `updated_at_utc`, status `running` al CHECK, manejo de `started_at_utc`.
- Schemas: validacion de node_path, area_key, topic_key, access_tags depth, source_type. Se removieron constantes no usadas (RETRIEVAL_MODES, NODE_TYPES).
- Repository: error handling explicito, started_at_utc en transicion a running, updated_at_utc en todos los updates.
- Worker: pending→running en lugar de pending→validating. Metodo `advance_phase()` stub con validacion de orden.
- Tests: 8 nuevos. Total: 30 tests. 110/110 suite completa.

### 2026-06-07 - Politica de seleccion de modelos y ruteo (gpt-5-nano, DeepSeek, Gemini)

- Se agrego `model-selection-routing.md` como invariante de arquitectura viva.
- Se documento la jerarquia de tiers (nano/mini/medium/large) con costos y distribucion objetivo 95/4/1.
- Se fijo `gpt-5-nano` como modelo economico para OpenAI directo (USD 0.05/0.40) y `google/gemini-2.5-flash-lite` como alternativa para OpenRouter.
- Se fijo DeepSeek V4 Flash como orquestador textual, no como lector de capturas.
- Se documentaron reglas de ruteo por tipo de automatizacion: SAP B1 (UI Automation > OCR > vision > humano), browser automation (Playwright > datos estructurados > modelo barato), diagnosis assistant (LiteLLM aliases).
- Se documento que los modelos deben configurarse mediante aliases LiteLLM, no hardcodearse como slugs.
- Se actualizo `lat.md/lat.md` con referencia `[[model-selection-routing]]`.
- Fuentes: `docs/analisis-tecnico/analisis_tecnico_browser_automation_modelos_ai_2026-05-08.md`, `docs/analisis-tecnico/sap_b1_modelos_vision_costos_automatizacion.md`, `docs/analisis-tecnico/team360_ai_diagnostico_stack_arango_milvus_litellm.md` y `lat.md/ai-diagnosis-rag-runtime.md`.
- No se implemento codigo, no se tocaron DBs, migraciones ni runtime.

### 2026-06-07 - Contrato publico /api/diagnosis/* wrapper backend

- Se creo `SrvRestAstroLS_v1/backend/routes/diagnosis.py` como wrapper sobre `automation_diagnosis`, compartiendo la misma instancia de servicio.
- Endpoints: `POST /api/diagnosis/start`, `POST /api/diagnosis/message`, `GET /api/diagnosis/session/{id}`.
- Stubs 501 para `submit-checklist` y `lead` (no implementados).
- No se creo motor paralelo, no se cambio scoring, service.py ni guided_flow.
- `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis` y `svc_sales_diagnosis` se mantienen como identificadores estables.

### 2026-06-07 - Entrada publica de Vera en Home Team360

- La Home publica incorpora una primera entrada de texto libre para `Vera` como marca visible del asistente Team360.
- La implementacion reutiliza el backend existente `automation_diagnosis` mediante un adapter frontend minimo; no crea motor paralelo ni contrato definitivo `/api/diagnosis/*`.
- Se mantiene la frontera tecnica/comercial: `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis` y `svc_sales_diagnosis` siguen siendo identificadores estables.
- El flujo publico todavia no implementa conversacion completa, captura de lead, resultado final ni L2/RAG ArangoDB/Milvus.
- El mailto queda como fallback controlado si el backend no esta disponible.

### 2026-06-07 - Representacion Console de Team360.live y Vera

- Se valido y ajusto la Console mock para representar Team360.live como cliente real y el servicio `Asistente Inteligente Vera` como servicio comercial visible.
- La navegacion mock habilita `diagnosis` para el admin cliente de Team360.live, manteniendo el flujo actual de `automation_diagnosis`.
- Los codigos tecnicos estables se mantienen como `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis` y `svc_sales_diagnosis`; `Vera` queda como marca visible.
- El detalle de servicio deja explicito que la home publica y L2/RAG ArangoDB/Milvus no estan activos todavia.
- No se modificaron invariantes de arquitectura, motor conversacional, migraciones ni contrato `/api/diagnosis/*`.

### 2026-06-07 - Materializacion inicial de configuracion productiva Team360.live / Vera

- Se avanzo desde documentacion hacia configuracion inicial mediante seed SQL y mocks, manteniendo los invariantes de arquitectura viva.
- La configuracion productiva inicial conserva `team360_sales_diagnosis`, `pkg_sales_diagnosis` y `ks_team360_sales_diagnosis` como identificadores tecnicos estables.
- `Vera` se materializa solo como nombre comercial visible en metadata/display fields, Console label y package/service visible.
- Se mantiene `automation_diagnosis` como motor base; no se creo motor paralelo ni contrato `/api/diagnosis/*`.
- No se implemento home publica, L2/RAG ArangoDB/Milvus ni nuevas tablas de organizaciones/servicios.

### 2026-06-07 - Vera como marca comercial, no identificador tecnico

- Se actualizo `customer-packaged-assistant-instance.md` con el invariante de naming comercial/tecnico.
- Se fijo que `Vera` es nombre visible configurable y no debe usarse como identificador core de assistant instance, paquete, knowledge scope, workers, rutas, tests, migrations ni integraciones.
- Se mantienen como identificadores tecnicos estables `team360_sales_diagnosis`, `pkg_sales_diagnosis` y `ks_team360_sales_diagnosis`.
- Se agrego una nota en `automation-diagnosis.md` para aclarar que los commercial entry points son assistant instance codes tecnicos.
- La regla busca evitar migraciones, rewrites de tests, cambios de integracion o reescritura de sesiones/leads historicos ante un rebranding.
- No se implemento runtime, no se tocaron DBs, migraciones, frontend ni seeds.

### 2026-06-04 - Contrato canonico KnowledgeScope / Document / Chunk / VectorEmbedding

- Se agrego `knowledge-scope-contract.md`.
- Se formalizo el mapeo del patron probado de JudaismoEnVivo `Catalog -> MD -> Chunk -> Milvus vector` hacia Team360 `KnowledgeScope -> KnowledgeDocument -> KnowledgeChunk -> VectorEmbedding`.
- Se fijo que `knowledge_scope_id` es el equivalente de `catalog_key`, pero siempre con filtros multi-tenant obligatorios por organizacion, workspace, assistant instance, status y version.
- Se documento ArangoDB como fuente textual/grafo y Milvus como indice vectorial derivado, no fuente de verdad comercial.
- Se recomendo persistir `chunk_text` en Team360 para mejorar precision, auditoria, fuentes y control de contexto.
- Se documento fallback Arango-only y se aclaro que Milvus 2.6 es objetivo de validacion paralela, no migracion automatica.
- Se reforzo que pgvector queda como laboratorio/fallback y que no se debe migrar ArangoDB a PostgreSQL/JSONB/pgvector ahora.
- Se actualizaron `lat.md/lat.md`, `knowledge-rag-graphrag.md`, `ai-diagnosis-rag-runtime.md` y `customer-packaged-assistant-instance.md`.
- No se implemento runtime, drivers ArangoDB/Milvus, migraciones ni cambios de API.

### 2026-06-04 - Persistencia PostgreSQL 004 para automation diagnosis runtime

- Se actualizo `postgres-ai-persistence.md` para reflejar que `004_team360_automation_diagnosis_runtime.sql` fue aplicada sobre `team360`.
- Se aclaro que la migracion 004 persiste sesiones, respuestas, leads y soporte de package installation para el asistente de venta/diagnostico.
- LangGraph PostgresSaver queda reservado para una migracion futura separada, ahora referida como `005_team360_langgraph_checkpointing.sql`.
- PostgreSQL sigue siendo verdad operacional; ArangoDB/Milvus siguen como runtime RAG/knowledge inicial, no como fuente de verdad comercial.

### 2026-06-04 - Team360 como primera instalacion cliente del paquete venta/diagnostico

- Se agrego `customer-packaged-assistant-instance.md`.
- Se fijo que `team360_sales_diagnosis` no es demo interna ni caso hardcodeado: es la primera instalacion cliente del paquete de venta y diagnostico para el workspace publico de Team360.
- Se documento la forma canonica: organizacion/workspace, `automation_package`, `assistant_instance`, `package_workers`, `knowledge_scope`, lead owner, costos, eventos y auditoria.
- Se documento la frontera ArangoDB/Milvus: colecciones compartidas por dominio con filtros obligatorios por organizacion, workspace, assistant instance y knowledge scope; no una coleccion fisica por cliente como default.
- Se reservaron colecciones/base fisicamente aisladas para enterprise, compliance, volumen alto o contrato dedicado.
- Se actualizo `lat.md/lat.md`, `automation-diagnosis.md` y `ai-diagnosis-rag-runtime.md`.
- No se implemento codigo, no se tocaron DBs ni migraciones.

### 2026-06-04 - Runtime RAG inicial para diagnostico: ArangoDB + Milvus + LiteLLM

- Se agrego `ai-diagnosis-rag-runtime.md`.
- Se documento como decision estable que el primer servicio de asistente inteligente de venta y diagnostico de automatizacion debe acelerar salida reutilizando el patron probado en JudaismoenVivo: ArangoDB + Milvus + LiteLLM.
- Se documento el alcance comercial inicial: asistente `team360_sales_diagnosis` para venta directa Team360 y asistente `mamamia360_sales_diagnosis` para Mamá Mía 360 como distribuidor regional en Israel, con soporte español, ingles y hebreo.
- Se fijo que ambos asistentes comparten motor tecnico y difieren por configuracion de organizacion, workspace, canal, marca, mercado, locale, paquetes, knowledge scope, lead owner y atribucion de costos.
- Se fijo que PostgreSQL 18 sigue siendo la fuente de verdad transaccional para organizaciones, workspaces, permisos, paquetes, workers, diagnosticos, eventos, auditoria, costos y billing.
- Se aclaro que `003_team360_pgvector_knowledge_embeddings.sql` deja pgvector disponible, pero no como RAG principal de la primera salida.
- Se actualizo `console-multi-organization.md` y `automation-diagnosis.md` con la frontera de canal directo / partner.
- Se actualizo `knowledge-rag-graphrag.md` con la frontera del runtime inicial.
- Se actualizo `postgres-ai-persistence.md` para alinear pgvector como capacidad instalada/futura y no como runtime RAG primario inicial.
- Se actualizo `lat.md/lat.md` con la nueva referencia `[[ai-diagnosis-rag-runtime]]`.
- No se implemento codigo, no se tocaron DBs ni migraciones.

### 2026-06-02 - Pydantic Boundary: Pydantic no es obligatorio en repositorios ni dominio

- Se agrego la seccion `Pydantic Boundary` en `lat.md/postgres-driver-policy.md` que define:
  - Pydantic solo en bordes HTTP/API (validacion, serializacion, OpenAPI, proteccion de campos).
  - Repositorios devuelven `dict`, `dataclass`, `TypedDict` o DTO explicitos; nunca Pydantic como capa de dominio.
  - Pydantic no es fuente de verdad del dominio ni debe duplicar schema SQL.
  - ConsoleBootstrap: primero JSON/TypedDict; Pydantic se evalua cuando exista endpoint real.
  - Contratos internos simples usan `dataclass` o `TypedDict`.
- Se actualizo el resumen de Decision (linea `Repos:`) y Summary table.
- Se reemplazo el ejemplo de repositorio de Pydantic a `dataclass`.
- Se agrego la regla en `.agents/skills/team360-project/SKILL.md`: no asumir Pydantic en repositorios ni core de dominio.
- No se toco DB, migraciones, codigo runtime, v360, litellm ni temp1.txt.

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
