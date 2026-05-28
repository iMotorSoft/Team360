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

## Knowledge Scope

Scope inicial:

```text
ks_team360_automation_diagnosis
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
7 passed
```

## Limitaciones

- Persistencia in-memory.
- Eventos in-memory.
- Sin GraphRAG real todavia.
- Sin embeddings ni pgvector en runtime.
- Rutas no montadas en app Litestar productiva.
- Frontend Astro/Svelte pendiente.
- Sin workers externos.
- Sin secretos planos.

## Proximos Pasos

1. Montar rutas en Litestar.
2. Agregar persistencia Postgres para sesiones, respuestas, resultados, eventos y knowledge.
3. Registrar uso LLM en `llm_usage_logs` cuando la DB este activa.
4. Agregar UI demo aislada en Astro/Svelte.
5. Migrar retrieval simple a embeddings/pgvector si corresponde.
6. Agregar GraphRAG en paquetes premium donde las relaciones aporten valor.
7. Convertir workers internos en `package_worker` ejecutables por cola/proceso externo cuando haya necesidad.
