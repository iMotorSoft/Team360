# Automation Diagnosis - Fase 1

## Objetivo

Implementar el primer modulo aislado del Asistente de Diagnostico de Automatizacion.

El asistente no es un chatbot abierto. Es una experiencia guiada que releva un proceso candidato a automatizacion, usa conocimiento interno de Team360, interpreta texto libre con IA, clasifica con reglas deterministicas y genera una respuesta visible mas una ficha interna.

## Principios

- Team360 gobierna, decide y audita.
- LiteLLM interpreta y redacta.
- RAG aporta contexto.
- Scoring y classifier deciden.
- Workers ejecutan capacidades autorizadas.
- El cliente interactua siempre con Team360, nunca con workers directos.

## Alcance implementado

Modulo:

```text
backend/modules/automation_diagnosis/
```

Incluye flujo guiado, adapter LiteLLM/mock/noop, knowledge scope interno, carga de Markdown, chunking, retrieval simple, scoring y classifier deterministico, respuesta visible, ficha interna, eventos in-memory, repositorio in-memory, funciones de ruta y tests.

Tambien incluye un contrato in-memory de `assistant_instance` para tratar a `team360_sales_diagnosis` como primera instalacion cliente real del paquete de venta y diagnostico, no como demo interna.

## Instalacion cliente Team360 directo

La salida directa de Team360 se modela como paquete instalado para el propio Team360 como cliente:

```text
organization_id: org_team360
workspace_id: team360_public_site
automation_package_id: pkg_sales_diagnosis
assistant_instance_id: team360_sales_diagnosis
knowledge_scope_id: ks_team360_sales_diagnosis
site_channel: team360.live
lead_owner: Team360
locale default: es
```

Workers internos vinculados por package worker:

```text
guided_intake_worker
lead_qualification_worker
knowledge_retrieval_worker
diagnosis_scoring_worker
package_recommendation_worker
proposal_outline_worker
crm_handoff_worker
calendar_handoff_worker
agui_render_worker
```

La resolucion de sesion rechaza overrides de `workspace_id`, `automation_package_id` o `knowledge_scope_id` que no coincidan con la configuracion del `assistant_instance`, para evitar retrieval o auditoria cruzada entre scopes.

## Knowledge Scope

Scopes iniciales:

```text
ks_team360_sales_diagnosis
ks_team360_automation_diagnosis  # compatibilidad de fixtures/lab interno
```

Modo:

```text
retrieval_mode = rag
```

Modelo minimo:

```text
knowledge_scope
knowledge_document
knowledge_chunk
```

Preparado para futuro:

```text
knowledge_entity
knowledge_relation
knowledge_graph
```

Documentos fixture:

```text
fixtures/knowledge/criteria_automation.md
fixtures/knowledge/security_limits_mfa.md
fixtures/knowledge/sap_b1_automation.md
fixtures/knowledge/browser_desktop_automation.md
fixtures/knowledge/commercial_packages.md
```

## LiteLLM

Variables previstas:

```bash
export TEAM360_AI_PROVIDER="litellm"
export TEAM360_LITELLM_BASE_URL="http://localhost:4000/v1"
export TEAM360_LITELLM_API_KEY="..."
export TEAM360_AUTOMATION_DIAGNOSIS_TEXT_MODEL="automation_diagnosis_text"
```

Fallback local:

- `TEAM360_AI_PROVIDER=mock`
- `TEAM360_AI_PROVIDER=none`

## ArangoDB y Milvus preparados

Fase 1 no conecta todavia ArangoDB ni Milvus reales, pero la configuracion de `team360_sales_diagnosis` ya declara:

- colecciones ArangoDB compartidas por dominio (`diagnosis_vertices`, `diagnosis_edges`, `diagnosis_documents`, `diagnosis_playbooks`);
- `physical_collection_per_customer = false` como default;
- filtros obligatorios por `organization_id`, `workspace_id`, `assistant_instance_id` y `knowledge_scope_id`;
- coleccion Milvus `team360_diagnosis_chunks` con `knowledge_scope_id` como particion/filtro principal.

PostgreSQL sigue siendo la fuente de verdad para sesiones, resultados, leads, eventos, costos y auditoria cuando se implemente persistencia real.

## Contrato Conceptual Multi-paquete

Fase 1 no implementa workers externos ni colas, pero deja los nombres preparados:

```text
workspace
assistant_instance
automation_package
worker_definition
package_worker
package_worker_config
credential_reference
knowledge_scope
```

Regla:

```text
Cliente -> Team360 -> automation_package -> package_worker -> worker interno/externo
```

Nunca:

```text
Cliente -> worker directo
```

## Clasificaciones

El classifier devuelve una de:

```text
standard_package
operational_automation
consulting_required
not_recommended
```

Tambien produce paquete recomendado, workers sugeridos, config requerida de `package_worker`, referencias de credenciales, scope de conocimiento, modo operativo, riesgos, acciones bloqueadas y si requiere aprobacion humana.

## Persistencia PostgreSQL

Fase 1 ya tiene repository async de escritura:

```text
backend/modules/automation_diagnosis/postgres_repository.py
```

Operaciones principales:

- `upsert_package_installation()`: instala/actualiza `team360_sales_diagnosis` como paquete cliente real en PostgreSQL;
- `persist_session_snapshot()`: persiste sesion, respuestas, lead y eventos en `core_events`;
- todo SQL queda dentro del repository y recibe una `AsyncConnection` externa.

Migracion aplicada:

```text
004_team360_automation_diagnosis_runtime.sql
```

Smoke real sobre `team360`:

```text
package_workers=9
sessions=1
answers=10
leads=1
events=16
```

## Rutas Preparadas

Archivo:

```text
backend/routes/automation_diagnosis.py
```

Funciones:

- `start_session(payload)`
- `get_session(session_id)`
- `save_answer(session_id, payload)`
- `classify(session_id)`
- `capture_contact(session_id, payload)`
- `finalize(session_id)`
- `debug(session_id)`
- `search_knowledge(payload)`

El backend Team360 todavia no tiene app Litestar productiva activa, por eso esta fase deja funciones de ruta listas sin decorar.

## Pruebas

Tests:

```text
backend/tests/test_automation_diagnosis.py
```

Comando:

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest tests/test_automation_diagnosis.py
```

Resultado observado:

```text
11 passed
```

## Limitaciones

- Persistencia runtime PostgreSQL disponible via repository async; el servicio actual mantiene cache in-memory para la sesion activa.
- Eventos in-memory en el servicio actual, persistibles a `core_events` via snapshot.
- Contrato `assistant_instance` in-memory; repository PostgreSQL ya puede instalarlo/persistirlo, pero el servicio sync actual todavia no lo lee desde DB al iniciar.
- Sin GraphRAG real todavia.
- Sin embeddings ni pgvector en runtime.
- Rutas no montadas en app Litestar productiva.
- Frontend Astro/Svelte pendiente.
- Sin workers externos.
- Sin secretos planos.

## Proximos Pasos

1. Diseñar migracion/repositories para persistir `assistant_instance`, package workers, sesiones, respuestas, resultados, eventos y knowledge en PostgreSQL.
2. Montar rutas en Litestar.
3. Registrar uso LLM en `llm_usage_logs` cuando la DB este activa.
4. Agregar UI demo aislada en Astro/Svelte.
5. Migrar retrieval simple a embeddings/pgvector si corresponde.
6. Agregar GraphRAG en paquetes premium donde las relaciones aporten valor.
7. Convertir workers internos en `package_worker` ejecutables por cola/proceso externo cuando haya necesidad.
