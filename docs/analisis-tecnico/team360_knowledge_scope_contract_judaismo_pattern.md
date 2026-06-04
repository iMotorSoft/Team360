# Team360 Knowledge Scope Contract basado en JudaismoEnVivo

Fecha: 2026-06-04

## Objetivo

Formalizar el contrato tecnico de conocimiento para Team360 antes de implementar drivers ArangoDB/Milvus.

El aprendizaje reutilizado viene del patron probado de JudaismoEnVivo:

```text
Catalog -> MD -> Chunk -> Milvus vector
```

Team360 lo adapta como:

```text
KnowledgeScope -> KnowledgeDocument -> KnowledgeChunk -> VectorEmbedding
```

Este documento es analisis tecnico no-runtime. La decision estable queda en `lat.md/knowledge-scope-contract.md`.

## Baseline JudaismoEnVivo

JudaismoEnVivo valida un flujo RAG con:

- ArangoDB como fuente de Catalog, Markdown y relaciones;
- Milvus como indice vectorial derivado;
- OpenAI embeddings sobre chunks;
- busqueda filtrada por `catalog_key`;
- recuperacion de Markdown desde ArangoDB;
- respuesta LLM sobre contexto acotado.

El punto mas importante no es la tecnologia aislada, sino el contrato:

```text
catalog_key limita el corpus antes de recuperar contexto.
md_key y chunk_key dan trazabilidad.
Milvus no es fuente de verdad.
```

## Equivalencia para Team360

| JudaismoEnVivo | Team360 | Nota |
| --- | --- | --- |
| `Catalog` | `KnowledgeScope` | corpus consultable |
| `catalog_key` | `knowledge_scope_id` | filtro obligatorio |
| `MD` | `KnowledgeDocument` | fuente textual |
| `md_key` | `document_id` | identificador de documento |
| `Chunk` | `KnowledgeChunk` | unidad semantica |
| `chunk_key` | `chunk_id` | identificador de chunk |
| Milvus row | `VectorEmbedding` | indice derivado |

Para Team360, `knowledge_scope_id` no alcanza solo. Debe viajar junto con:

```text
organization_id
workspace_id
assistant_instance_id
status
version
```

## Filtros obligatorios multi-tenant

Toda consulta RAG/GraphRAG debe resolver scope antes de buscar.

Filtro minimo:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
status
version o active_version
```

Filtros recomendados:

```text
source_kind
language
document_type
package_worker_id
market
site_channel
```

No debe existir retrieval cross-customer salvo que en el futuro se cree un scope global/shared explicito con politica de acceso documentada.

## ArangoDB como fuente textual/grafo

ArangoDB debe ser la fuente inicial de:

- documentos de conocimiento;
- chunks con texto;
- relaciones entre procesos, dolores, riesgos, sistemas, paquetes y workers;
- playbooks y fragmentos de diagnostico;
- fallback sin Milvus.

Modelo recomendado:

```text
shared domain collections
  + tenant/scope fields obligatorios
  + grafo logico por knowledge_scope o assistant_instance
```

No se recomienda una coleccion fisica por cliente como default. El aislamiento fisico queda para enterprise, compliance, volumen alto, performance demostrada o contrato dedicado.

## Milvus como indice derivado

Milvus debe indexar embeddings y metadata minima:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
document_id
chunk_id
source_kind
language
embedding_model
embedding_dimension
content_hash
version
status
```

Milvus no debe guardar verdad comercial ni ser autoridad del texto. Sus resultados deben volver a resolverse contra ArangoDB/PostgreSQL antes de armar contexto para LiteLLM.

## chunk_text recomendado

JudaismoEnVivo valida la trazabilidad `catalog_key -> md_key -> chunk_key`, pero expone una deuda: si el texto exacto del chunk no se persiste, el runtime tiende a recuperar bloques Markdown mas grandes.

Team360 deberia persistir `chunk_text` en `KnowledgeChunk`.

Beneficios:

- evidencia mas precisa;
- prompts mas chicos;
- mejor auditoria;
- debugging de retrieval;
- menor riesgo de mezclar contexto;
- posibilidad de mostrar fuentes/chunks en AG-UI.

## Fallback Arango-only

Team360 debe admitir un modo degradado cuando Milvus no este disponible.

Flujo:

```text
resolver KnowledgeScope
filtrar ArangoDB por tenant/scope/status/version
recuperar KnowledgeChunk o KnowledgeDocument
rankear por reglas deterministicas o lexical simple
limitar contexto
llamar LiteLLM con metadata arango_only_fallback
```

El fallback debe preferir menor recall antes que riesgo de fuga cross-scope.

## PostgreSQL y pgvector

PostgreSQL sigue siendo la fuente de verdad de:

- organizaciones;
- workspaces;
- permisos;
- paquetes;
- assistant instances;
- package workers;
- sesiones;
- diagnosticos finales;
- leads;
- eventos;
- auditoria;
- costos y billing.

pgvector esta disponible como capacidad instalada, pero no debe reemplazar el stack ArangoDB/Milvus en la primera salida.

Usos razonables de pgvector:

- laboratorio;
- fallback experimental;
- scopes chicos;
- deployment PostgreSQL-only futuro;
- comparativas de costo/latencia/recall.

No conviene migrar ArangoDB a PostgreSQL/JSONB/pgvector ahora.

## Milvus 2.6

JudaismoEnVivo tiene evidencia de compatibilidad en laboratorio con Milvus 2.6.

Para Team360, esa evidencia habilita prueba paralela, no migracion automatica.

Antes de adoptar Milvus 2.6 validar:

- compatibilidad cliente/servidor;
- filtros por metadata multi-tenant;
- indices y metricas;
- backup/restore;
- vectores no-cero;
- latencia;
- recall contra golden questions;
- paridad con filtros Team360.

## No implementar todavia

Este paso no debe:

- crear drivers ArangoDB;
- crear drivers Milvus;
- tocar API;
- tocar runtime;
- crear migraciones;
- reemplazar Postgres;
- mover pgvector a runtime principal;
- migrar conocimiento ArangoDB a Postgres.

## Decision recomendada

Formalizar el contrato ahora y diferir implementacion.

Secuencia recomendada:

1. Documentar contrato estable en `lat.md`.
2. Mantener `automation_diagnosis` actual funcionando con memory/postgres.
3. Disenar adapter de conocimiento contra el contrato, no contra un proveedor.
4. Crear corpus demo de diagnostico/ventas.
5. Implementar primero ArangoDB source-of-truth textual/grafo.
6. Implementar Milvus como indice derivado.
7. Medir fallback Arango-only.
8. Comparar Milvus 2.6 y pgvector en laboratorio, sin bloquear la demo.
