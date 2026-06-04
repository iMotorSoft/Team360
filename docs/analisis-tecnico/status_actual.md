# Status actual - docs/analisis-tecnico

Objetivo: `analisis-tecnico-no-runtime`

Ultima actualizacion: 2026-06-04

## Estado general

`docs/analisis-tecnico/` contiene analisis tecnico de producto, automatizacion o factibilidad que no pertenece directamente al runtime de desarrollo.

## Acciones realizadas

### 2026-06-04 - Contrato KnowledgeScope basado en JudaismoEnVivo

- Se agrego `team360_knowledge_scope_contract_judaismo_pattern.md`.
- Se formalizo la equivalencia JudaismoEnVivo `Catalog/MD/Chunk` hacia Team360 `KnowledgeScope/KnowledgeDocument/KnowledgeChunk/VectorEmbedding`.
- Se documento que `knowledge_scope_id` es el equivalente conceptual de `catalog_key`, pero en Team360 debe viajar con filtros obligatorios multi-tenant: organizacion, workspace, assistant instance, scope, status y version.
- Se fijo ArangoDB como fuente textual/grafo para knowledge y Milvus como indice vectorial derivado.
- Se documento que `chunk_text` debe persistirse en Team360 para mejorar evidencia, auditoria, grounding y control de prompt.
- Se documento fallback Arango-only y se aclaro que Milvus 2.6 es prueba paralela, no migracion automatica.
- Se reforzo que pgvector queda como laboratorio/fallback y que no conviene migrar ArangoDB a PostgreSQL/JSONB/pgvector ahora.
- No se implemento codigo, no se tocaron runtime, API, DBs, migraciones, ArangoDB ni Milvus.

### 2026-06-04 - Stack AI diagnostico con ArangoDB, Milvus y LiteLLM

- Se agrego `team360_ai_diagnostico_stack_arango_milvus_litellm.md`.
- Se documento la factibilidad de acelerar el asistente inteligente de venta y diagnostico de automatizacion replicando el patron probado en JudaismoenVivo: ArangoDB + Milvus + LiteLLM.
- Se agrego el alcance comercial inicial: Team360 directo y Mamá Mía 360 como distribuidor regional en Israel, con asistentes configurables y soporte español, ingles y hebreo.
- Se aclaro que ambos canales deben compartir motor tecnico y diferir por configuracion comercial, knowledge scope, lead owner y atribucion de costos.
- Se documento que Team360 directo debe modelarse como primera instalacion cliente del paquete de venta/diagnostico, no como demo interna.
- Se agrego decision inicial de scoping para ArangoDB/Milvus: colecciones compartidas por dominio con filtros obligatorios por organizacion, workspace, assistant instance y knowledge scope; aislamiento fisico solo por necesidad explicita.
- Se fijo PostgreSQL 18 como core transaccional y auditoria, sin usar pgvector como RAG principal de la primera salida.
- Se documento ArangoDB como knowledge graph/document runtime para procesos, dolores, automatizaciones, riesgos, paquetes y workers.
- Se documento Milvus como runtime vectorial inicial para retrieval semantico, casos similares y playbooks.
- Se documento LiteLLM como gateway AI para aliases, costos, budgets, metadata y ruteo de modelos.
- Se aclaro que AG-UI/SSE debe renderizar estructuras semanticas validadas, no HTML generado directamente por el modelo.
- No se implemento codigo, no se tocaron DBs, migraciones, backend, Astro ni configuracion de LiteLLM.

### 2026-05-15 - Analisis de modelos visuales economicos para SAP B1

- Se agrego `sap_b1_modelos_vision_costos_automatizacion.md`.
- El documento complementa la factibilidad SAP B1 existente con:
  - comparacion entre `gpt-5-nano` y `Gemini 2.5 Flash-Lite`;
  - criterio para usar Microsoft UI Automation como fuente primaria;
  - uso de OCR local y modelos visuales como fallback;
  - modelos relevantes disponibles en OpenRouter;
  - politica recomendada de ruteo y benchmark minimo.
- Decision preliminar registrada:
  - `gpt-5-nano` como opcion visual economica si se usa OpenAI directo;
  - `google/gemini-2.5-flash-lite` como opcion visual economica si se centraliza en OpenRouter;
  - DeepSeek V4 Flash como orquestador textual, no como lector de capturas.
- No se toco runtime, backend, Astro, `team360_orquestador`, AG-UI ni laboratorio browser.

### 2026-05-13 - Reubicacion de factibilidad SAP Business One

- Se movio `sap_b1_desktop_automation_factibilidad.md` desde `SrvRestAstroLS_v1/docs/` a este directorio.
- Motivo:
  - es un documento de factibilidad tecnica y comercial interna;
  - no es documentacion de runtime, backend, Astro, migraciones ni implementacion productiva;
  - corresponde a `docs/analisis-tecnico/` por la convencion documental vigente.
- El documento conserva la ampliacion local con secciones de licenciamiento, checklist, costos, monitoreo y rollback.
- Documentos actuales:
  - `analisis_tecnico_browser_automation_modelos_ai_2026-05-08.md`
  - `sap_b1_desktop_automation_factibilidad.md`
  - `sap_b1_modelos_vision_costos_automatizacion.md`

### 2026-05-13 - Separacion de analisis tecnico no operativo

- Se movio a este directorio el analisis tecnico de browser automation y modelos AI.
- Documentos actuales:
  - `analisis_tecnico_browser_automation_modelos_ai_2026-05-08.md`
- Se agrego `README.md` como indice local.
- Se agrego este `status_actual.md` para registrar el ultimo estado del directorio.

## Validacion

- Se agrego el nuevo documento al indice local `docs/analisis-tecnico/README.md`.
- Se agrego `team360_ai_diagnostico_stack_arango_milvus_litellm.md` al indice local.
- Se agrego `team360_knowledge_scope_contract_judaismo_pattern.md` al indice local.
- Se verifico que `sap_b1_desktop_automation_factibilidad.md` existe en `docs/analisis-tecnico/`.
- Se mantuvo separado de `SrvRestAstroLS_v1/docs/`, que queda para desarrollo, backend, Astro, runtime y migraciones.

## Pendientes recomendados

- Usar este directorio para factibilidad tecnica no ligada todavia a implementacion concreta.
- Si un analisis pasa a decisiones de desarrollo, reflejarlo tambien en `SrvRestAstroLS_v1/docs/status_actual.md`.
