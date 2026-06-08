# Knowledge Ingestion Multi-Scope / Multi-Nivel para Team360

**Fecha:** 2026-06-07
**Objetivo:** Diseñar el modelo de ingesta de conocimiento reusable, multi-scope y multi-nivel para la plataforma Team360.
**Tipo:** Documento técnico de diseño (sin implementación)

---

## 1. Resumen ejecutivo

Team360 necesita un servicio de **Knowledge Ingestion** transversal de plataforma, no un componente específico de un solo asistente, cliente o marca.

Vera es el nombre comercial visible del primer asistente, pero la ingesta debe servir a todos los clientes, proyectos, paquetes y asistentes de Team360, incluyendo futuros partners como Mamá Mía 360 y cualquier cliente enterprise.

El problema central: un cliente puede querer consultar **todo** el conocimiento de su empresa o solo **una parte** jerárquica (área, sector, proceso, tema). Además, el acceso depende del **rol** del usuario (CEO ve todo, un responsable de área ve solo su área).

La solución propuesta extiende el contrato canónico `KnowledgeScope / KnowledgeDocument / KnowledgeChunk / VectorEmbedding` (definido en `lat.md/knowledge-scope-contract.md`) con una capa intermedia de estructura organizacional/conceptual: **KnowledgeMap / KnowledgeNode**.

El patrón general es:

```text
documento → estructura organizacional/conceptual → chunks → embeddings filtrables
```

No se implementa código en este documento. Es un artefacto de diseño para guiar fases posteriores.

---

## 2. Estado actual encontrado

### 2.1 Tablas existentes (PostgreSQL, migraciones 002 + 003 + 004)

| Tabla | Propósito | Limitación |
|---|---|---|
| `knowledge_scopes` | Límite de corpus consultable por scope_code | Plano, sin jerarquía interna |
| `knowledge_scope_bindings` | Binding de scope a entidades (workspace, assistant_instance, etc.) | Solo binding, no estructura interna |
| `knowledge_documents` | Documento fuente dentro de un scope | metadata_jsonb plano, sin nodo jerárquico |
| `knowledge_chunks` | Fragmento semántico de documento | metadata_jsonb plano, sin path organizacional |
| `knowledge_embedding_models` | Catálogo de modelos de embedding | Sin relación con scopes/nodos |
| `knowledge_chunk_embeddings` | Vector embedding por chunk | Filtrable solo por knowledge_scope_id |
| `worker_definitions` | Definiciones de workers del sistema | Sin binding a conocimiento |
| `package_workers` | Workers por paquete | knowledge_scope_id nullable, sin nodo |
| `assistant_instances` | Instancia de asistente | default_knowledge_scope_id, sin policy de acceso |
| `automation_packages` | Paquete de automatización | settings_jsonb plano |

### 2.2 Schemas runtime actuales (`automation_diagnosis/schemas.py`)

- `KnowledgeScope`: id, name, retrieval_mode, workspace_id, assistant_instance_id, automation_package_id, package_worker_id, graph_enabled, metadata
- `KnowledgeDocument`: id, knowledge_scope_id, title, source_path, content, metadata
- `KnowledgeChunk`: id, knowledge_scope_id, document_id, title, content, ordinal, metadata

### 2.3 Retrieval actual (`automation_diagnosis/retrieval.py`)

- Búsqueda por keyword simple (tokenización + scoring TF-like)
- Único filtro: `chunk.knowledge_scope_id == knowledge_scope_id`
- Sin filtro por organización, área, rol, path, nodo

### 2.4 Chunker actual (`automation_diagnosis/chunker.py`)

- Divide por secciones Markdown (headers #, ##, ###)
- Sin awareness de contexto organizacional
- Sin metadata de nodo/área/tópico

### 2.5 Documentos de arquitectura existentes

- `lat.md/knowledge-scope-contract.md`: Define el contrato canónico pero no aborda jerarquía organizacional multi-nivel
- `lat.md/ai-diagnosis-rag-runtime.md`: Define ArangoDB + Milvus + LiteLLM pero no el modelo de ingesta
- `lat.md/knowledge-rag-graphrag.md`: Define niveles de binding pero sin estructura jerárquica
- `lat.md/customer-packaged-assistant-instance.md`: Define paquete por cliente pero no el árbol de conocimiento

---

## 3. Brecha actual

### 3.1 ¿Las tablas actuales permiten representar Empresa → Área → Sector → Proceso → Tema?

**No.** Las tablas actuales son planas:

- `knowledge_documents` se asocia a un solo `knowledge_scope_id`
- `knowledge_chunks` se asocia a un solo `knowledge_document_id`
- No hay concepto de `parent`, `path`, `node_type`, `depth` ni `tree`
- `metadata_jsonb` podría almacenar un path, pero no hay índices, constraints ni queries que lo soporten como estructura consultable
- `core_workspace_areas` existe pero es plana (solo `area_code`, sin parent), diseñada para RBAC no para árbol de conocimiento

### 3.2 ¿Permiten filtrar por CEO / Director / Gerente / Responsable?

**No.** No hay:

- Política de acceso por rol/nodo
- Relación entre `core_user_profiles.area_id` y documentos/chunks
- Tag de visibilidad por nodo
- Filter de retrieval por `permission_tags` o `access_tags`

### 3.3 ¿Qué falta?

1. **Estructura jerárquica navegable**: árbol de nodos con parent, path, depth
2. **Binding documento → nodo**: cada documento sabe en qué nodo organizacional/conceptual vive
3. **Política de acceso por nodo**: qué roles ven qué nodos
4. **Tags de visibilidad y permiso**: para filtrar chunks por nivel de acceso
5. **Retrieval por path**: búsqueda que respete `node_path` y `permission_tags`
6. **Scope types**: más allá de `workspace`, incluir `global`, `package`, `partner`, `organization`, `service`, `assistant_instance`, `session`
7. **Registro de corridas de ingesta**: para auditoría, reprocesamiento y trazabilidad
8. **Política de retrieval por asistente**: qué scopes/nodos puede consultar cada asistente

---

## 4. Modelo conceptual propuesto

### 4.1 Entidades

```text
┌─────────────────────────────────────────────────────────────────┐
│                      KnowledgeScope                             │
│  (boundary: qué corpus es consultable)                          │
└────────────────────────┬────────────────────────────────────────┘
                         │ contains
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      KnowledgeMap                                │
│  (árbol/grafo de organización o taxonomía conceptual)            │
└────────────────────────┬────────────────────────────────────────┘
                         │ composed of
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      KnowledgeNode                               │
│  (nodo individual: Empresa, Área, Sector, Proceso, Tema)         │
│  - parent_node_key                                               │
│  - path (materializado, ej: /finanzas/cobranzas)                 │
│  - depth                                                         │
│  - permission_tags                                               │
│  - visibility                                                    │
└────────────────────────┬────────────────────────────────────────┘
                         │ contains
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      KnowledgeDocument                           │
│  (documento fuente: Markdown, PDF, texto)                        │
│  - node_path (a qué nodo pertenece)                              │
└────────────────────────┬────────────────────────────────────────┘
                         │ split into
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      KnowledgeChunk                              │
│  (fragmento semántico con metadata de contexto)                  │
└────────────────────────┬────────────────────────────────────────┘
                         │ embedded as
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      KnowledgeEmbedding                          │
│  (vector + metadatos de filtrado multi-tenant)                   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Entidades adicionales de operación

| Entidad | Propósito |
|---|---|
| `KnowledgeIngestionRun` | Registro de cada corrida de ingesta (auditoría, reprocesamiento) |
| `KnowledgeAccessPolicy` | Regla: qué rol/perfil puede acceder a qué nodo o tag |
| `KnowledgeRetrievalPolicy` | Regla: qué asistente/scope/path aplica a cada retrieval |

### 4.3 Relaciones

- Un `KnowledgeScope` contiene uno o más `KnowledgeMap`
- Un `KnowledgeMap` es un árbol de `KnowledgeNode` (nodos con parent)
- Un `KnowledgeDocument` pertenece a un `KnowledgeNode` (por `node_path`)
- Un `KnowledgeChunk` hereda el `node_path` y `permission_tags` de su documento
- Un `KnowledgeEmbedding` hereda el `node_path`, `permission_tags` y filtros multi-tenant de su chunk
- `KnowledgeAccessPolicy` asocia `role_code` o `profile_code` a nodos o tags
- `KnowledgeRetrievalPolicy` asocia `assistant_instance` o `package_worker` a scopes y modos de retrieval

---

## 5. Scope levels

Cada `KnowledgeScope` debe declarar su `scope_type`. Los niveles propuestos son:

| Nivel | scope_type | Descripción | Ejemplo |
|---|---|---|---|
| 0 | `global` | Conocimiento de plataforma, visible a todos los asistentes | Políticas globales, términos de servicio, FAQ platform |
| 1 | `package` | Conocimiento de un paquete de automatización | Guías de `pkg_sales_diagnosis`, templates |
| 2 | `partner` | Conocimiento de un partner/distribuidor | Material de Mamá Mía 360 |
| 3 | `organization` | Conocimiento de una organización cliente | Todo el conocimiento de Team360.live |
| 4 | `workspace` | Conocimiento de un workspace específico | `team360_public_site` |
| 5 | `service` | Conocimiento de un servicio comercial | `svc_sales_diagnosis` |
| 6 | `assistant_instance` | Conocimiento de una instancia de asistente | `team360_sales_diagnosis` |
| 7 | `session` | Conocimiento efímero de una sesión | Contexto de diagnóstico en curso |

Regla: un scope de nivel superior puede heredar o incluir scopes de nivel inferior cuando la política de acceso lo permita.

Ejemplo: un scope `organization` puede incluir todos los `workspace` scopes de esa organización.

---

## 6. KnowledgeMap / KnowledgeNode

### 6.1 KnowledgeMap

```text
KnowledgeMap:
  map_key: text (único por scope)
  knowledge_scope_id: uuid (FK a knowledge_scopes)
  name: text
  description: text (opcional)
  map_type: text (organizational | conceptual | functional | taxonomy)
  root_node_key: text (referencia al nodo raíz)
  metadata_jsonb: jsonb
  status: text (active | inactive | drafting)
  created_at_utc: timestamptz
  updated_at_utc: timestamptz
```

### 6.2 KnowledgeNode

```text
KnowledgeNode:
  node_key: text (único dentro del map)
  parent_node_key: text (nullable, referencia a otro KnowledgeNode)
  knowledge_scope_id: uuid (FK a knowledge_scopes)
  knowledge_map_key: text (FK a KnowledgeMap)
  organization_code: text (código de organización, para filtro rápido)
  node_type: text (root | area | sector | process | topic | subtopic)
  name: text
  path: text (materializado, ej: /finanzas/cobranzas/creditos)
  depth: integer (0 para root)
  permission_tags: text[] (ej: {ceo, director_finanzas, gerente_finanzas, responsable_cajas})
  visibility: text (visible | restricted | hidden)
  status: text (active | inactive | archived)
  metadata_jsonb: jsonb (atributos adicionales: budget, kpi, owner, etc.)
  sort_order: integer
  created_at_utc: timestamptz
  updated_at_utc: timestamptz
```

### 6.3 Ejemplo de árbol

```
node_key: "acme_root"
parent: null
path: "/"
depth: 0
permission_tags: {ceo}

node_key: "acme_finanzas"
parent: "acme_root"
path: "/finanzas"
depth: 1
permission_tags: {ceo, director_finanzas}

node_key: "acme_finanzas_cajas"
parent: "acme_finanzas"
path: "/finanzas/cajas"
depth: 2
permission_tags: {ceo, director_finanzas, gerente_finanzas, responsable_cajas}

node_key: "acme_finanzas_cobranzas"
parent: "acme_finanzas"
path: "/finanzas/cobranzas"
depth: 2
permission_tags: {ceo, director_finanzas, gerente_finanzas}

node_key: "acme_finanzas_creditos"
parent: "acme_finanzas"
path: "/finanzas/creditos"
depth: 2
permission_tags: {ceo, director_finanzas, gerente_finanzas}

node_key: "acme_ventas"
parent: "acme_root"
path: "/ventas"
depth: 1
permission_tags: {ceo, director_ventas}
```

### 6.4 Índices recomendados

- Unique index on `(knowledge_scope_id, node_key)`
- Index on `parent_node_key` (para navegar árbol)
- Index on `path` (para búsqueda por prefijo)
- Index on `permission_tags` usando GIN
- Index on `(knowledge_scope_id, organization_code)`

---

## 7. Metadata obligatoria de documentos

Al ingestar un documento, debe incluir la siguiente metadata como mínimo:

```text
knowledge_scope_code: text        # scope al que pertenece
scope_type: text                  # global | package | organization | workspace | service | assistant_instance
organization_code: text           # código de organización dueña
workspace_code: text              # workspace específico (opcional según scope_type)
package_code: text                # paquete relacionado (opcional)
assistant_instance_code: text     # instancia de asistente (opcional)
node_path: text                   # path en el KnowledgeMap (ej: /finanzas/cobranzas)
area_key: text                    # clave del área funcional
topic_key: text                   # clave del tema específico
document_type: text               # policy | guide | procedure | template | faq | reference | report
visibility: text                  # public | internal | restricted | confidential
access_tags: text[]               # tags de acceso (ej: {ceo, director_finanzas})
locale: text                      # es | en | he
version: text                     # versión del documento
status: text                      # draft | active | deprecated | archived
```

Esta metadata debe almacenarse en la columna `metadata_jsonb` de `knowledge_documents` y propagarse a `knowledge_chunks` y `knowledge_chunk_embeddings`.

---

## 8. Retrieval por capas

Un asistente debe buscar conocimiento en orden de especificidad, no globalmente sin filtros.

### 8.1 Cascada de retrieval

```text
1. Session knowledge (scope_type=session)
   → conocimiento efímero de la conversación actual
   → mayor prioridad, menor alcance

2. Assistant instance knowledge (scope_type=assistant_instance)
   → conocimiento específico de la instancia del asistente
   → ej: ks_team360_sales_diagnosis

3. Service knowledge (scope_type=service)
   → conocimiento del servicio comercial contratado
   → ej: svc_sales_diagnosis

4. Workspace knowledge (scope_type=workspace)
   → conocimiento del workspace activo

5. Organization knowledge (scope_type=organization)
   → conocimiento de toda la organización cliente

6. Partner knowledge (scope_type=partner)
   → conocimiento del partner/distribuidor (si aplica)

7. Package knowledge (scope_type=package)
   → conocimiento del paquete de automatización

8. Global knowledge (scope_type=global)
   → conocimiento de plataforma (términos, FAQ, políticas)
   → menor prioridad, mayor alcance
   → solo si el scope global está explícitamente habilitado
```

### 8.2 Filtros obligatorios en cada capa

Cada búsqueda en Milvus (o pgvector) debe incluir:

```text
knowledge_scope_id: filtro obligatorio
organization_code: filtro obligatorio
node_path: filtro por prefijo (si aplica)
access_tags: al menos un tag debe coincidir con los permisos del usuario
visibility: no puede ser 'hidden' si el usuario no tiene permiso explícito
status: solo 'active'
```

### 8.3 Resolución de nodos permitidos

Antes de buscar en el vector index:

1. Resolver el rol del usuario → obtener `permission_tags`
2. Consultar `KnowledgeAccessPolicy` para el rol/scope → obtener nodos permitidos
3. Expandir nodos permitidos a todos sus hijos (herencia hacia abajo)
4. Construir lista de `node_path` con prefijos permitidos
5. Pasar esos prefijos como filtro al retrieval

---

## 9. Ejemplo CEO / Finanzas

### 9.1 CEO pregunta sobre Cobranzas y Créditos

Contexto:
- Usuario: CEO (permission_tags = {ceo})
- Scope: organization (acme_corp)

Flujo:
1. Resolver roles: CEO → tag `ceo`
2. Consultar KnowledgeAccessPolicy: `ceo` → todos los nodos del árbol
3. Buscar en Milvus con filtros:
   - `knowledge_scope_id = ks_acme_corp`
   - `node_path @> /finanzas/cobranzas` OR `node_path @> /finanzas/creditos`
   - `access_tags && {ceo}`
4. Resultados: chunks de Cobranzas y Créditos dentro de Finanzas

### 9.2 Director Finanzas pregunta por el área completa

Contexto:
- Usuario: Director Finanzas (permission_tags = {ceo, director_finanzas})
- Scope: organization (acme_corp)

Flujo:
1. Resolver: `director_finanzas`
2. KnowledgeAccessPolicy: `director_finanzas` → nodos con path que empieza con `/finanzas/`
3. Buscar en Milvus con filtros:
   - `knowledge_scope_id = ks_acme_corp`
   - `node_path @> /finanzas`
   - `access_tags && {director_finanzas}`
4. Resultados: todos los chunks del área Finanzas (Cajas, Cobranzas, Créditos)

### 9.3 Responsable Cajas pregunta algo financiero

Contexto:
- Usuario: Responsable Cajas (permission_tags = {responsable_cajas})
- Scope: organization (acme_corp)
- Query: "¿cómo manejar pagos atrasados?"

Flujo:
1. Resolver: `responsable_cajas`
2. KnowledgeAccessPolicy: `responsable_cajas` → solo nodos con tag que incluye `responsable_cajas`
3. Buscar en Milvus con filtros:
   - `knowledge_scope_id = ks_acme_corp`
   - `node_path @> /finanzas/cajas`
   - `access_tags && {responsable_cajas}`
4. Resultados: solo chunks de Cajas, aunque la pregunta sea financiera
5. Si no hay resultados suficientes, se puede intentar expansión controlada pero limitada

---

## 10. Relación con Milvus / ArangoDB

### 10.1 Principio

```text
KnowledgeMap / KnowledgeNode (ArangoDB o PostgreSQL) → decide profundidad/sector
Milvus → busca solo dentro de filtros resueltos
```

### 10.2 ArangoDB como fuente de grafo/jerarquía

- `KnowledgeMap` y `KnowledgeNode` pueden vivir en ArangoDB como colecciones de grafo
- ArangoDB resuelve: qué nodos puede ver un rol, qué path cubre cada nodo, herencia de permisos
- Cada nodo conoce sus hijos y padres (relaciones de grafo)
- La resolución de `access_tags` y expansión de path se hace contra ArangoDB

### 10.3 Milvus como índice vectorial

- Milvus almacena embeddings con metadata de filtrado
- **Nunca** buscar globalmente sin filtros multi-tenant
- Los filtros se resuelven FIRST en ArangoDB/KnowledgeMap, luego se pasan a Milvus
- Metadata en Milvus por embedding:
  ```text
  knowledge_scope_id (obligatorio)
  organization_code (obligatorio)
  node_path (para filtro por prefijo)
  access_tags (para filtro por permiso)
  visibility
  locale
  document_type
  status
  ```

### 10.4 Protección contra leakage

- No existe una colección Milvus global sin filtros
- No existe una query Milvus sin `knowledge_scope_id`
- No existe una query Milvus sin filtro de `access_tags` (al menos uno debe coincidir)
- El backend MUST re-validar los resultados de Milvus contra ArangoDB/PostgreSQL antes de usarlos como contexto de LLM

---

## 11. Worker de ingesta

### 11.1 Worker genérico: `knowledge_ingestion_worker`

```text
worker_code: knowledge_ingestion_worker
worker_kind: api (o interpreter)
default_mode: read_only
```

### 11.2 Fases del worker

```text
Fase 0: Recibir payload de ingesta
  - document_source (Markdown, PDF, texto plano, URL)
  - metadata obligatoria (ver sección 7)
  - scope destino

Fase 1: Validar metadata
  - Verificar que todos los campos obligatorios existen
  - Verificar que el knowledge_scope_code existe y está activo
  - Verificar que el node_path existe en el KnowledgeMap
  - Verificar que los access_tags son válidos
  - Rechazar si falta información crítica

Fase 2: Convertir a Markdown/texto
  - Si es PDF: extraer texto + estructura
  - Si es HTML: convertir a Markdown
  - Si es texto plano: envolver en Markdown mínimo
  - Si ya es Markdown: validar sintaxis

Fase 3: Generar L0 (metadata + resumen ejecutivo)
  - Extraer título, descripción, palabras clave
  - Generar resumen automático de 1-3 párrafos
  - Este resumen puede servir como chunk de nivel 0

Fase 4: Generar L1 (secciones estructuradas) si aplica
  - Si el documento tiene estructura jerárquica (headers), dividir en secciones L1
  - Cada sección L1 se asocia al nodo correspondiente o al nodo padre

Fase 5: Chunk semántico
  - Dividir el documento en chunks semánticos
  - Preservar contexto: título de sección, path, nodo
  - Asignar node_path a cada chunk
  - Asignar permission_tags a cada chunk (heredados del documento/nodo)
  - Calcular token_count por chunk

Fase 6: Guardar documento y chunks en PostgreSQL
  - Insertar o actualizar KnowledgeDocument
  - Insertar o upsert KnowledgeChunks
  - Registrar en KnowledgeIngestionRun

Fase 7: Generar embeddings
  - Llamar al modelo de embedding configurado en el scope
  - Almacenar vector + metadata en knowledge_chunk_embeddings (pgvector)
  - Si Milvus está activo: también indexar en Milvus con metadata de filtro

Fase 8: Indexar (si aplica para ArangoDB)
  - Crear/actualizar nodo en ArangoDB
  - Indexar documento y chunks en colecciones ArangoDB

Fase 9: Registrar estado/error
  - Actualizar KnowledgeIngestionRun con resultado
  - Si falló: registrar error_code, error_detail, fase donde falló
  - Si ok: registrar stats (documento_id, chunk_count, token_count, duración)
```

### 11.3 KnowledgeIngestionRun

```text
KnowledgeIngestionRun:
  run_id: uuid
  knowledge_scope_id: uuid
  document_source: text (URI o referencia)
  metadata_snapshot: jsonb (copia de la metadata al momento de ingestar)
  status: text (pending | validating | converting | chunking | embedding | indexing | completed | failed)
  phases_jsonb: jsonb (registro por fase: timestamp, duración, resultado)
  chunk_count: integer
  token_count: integer
  error_code: text (nullable)
  error_detail: text (nullable)
  started_at_utc: timestamptz
  completed_at_utc: timestamptz
  created_at_utc: timestamptz
```

---

## 12. Migración mínima posible

Si las tablas actuales no alcanzan para la Fase 1 de implementación, proponemos la siguiente migración mínima futura (NO implementar ahora):

### 12.1 Nuevas tablas

```sql
-- Tabla 1: KnowledgeMap
create table if not exists knowledge_maps (
    id uuid primary key default gen_random_uuid(),
    knowledge_scope_id uuid not null references knowledge_scopes(id) on delete cascade,
    map_key text not null,
    name text not null,
    map_type text not null default 'organizational',
    root_node_key text,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_knowledge_maps_scope_key unique (knowledge_scope_id, map_key)
);

-- Tabla 2: KnowledgeNode
create table if not exists knowledge_nodes (
    id uuid primary key default gen_random_uuid(),
    node_key text not null,
    parent_node_key text,
    knowledge_scope_id uuid not null references knowledge_scopes(id) on delete cascade,
    knowledge_map_id uuid not null references knowledge_maps(id) on delete cascade,
    organization_code text,
    node_type text not null default 'topic',
    name text not null,
    path text not null,
    depth integer not null default 0,
    permission_tags text[] not null default '{}',
    visibility text not null default 'visible',
    status text not null default 'active',
    metadata_jsonb jsonb not null default '{}'::jsonb,
    sort_order integer not null default 0,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_knowledge_nodes_map_key unique (knowledge_map_id, node_key)
);

-- Tabla 3: KnowledgeIngestionRun
create table if not exists knowledge_ingestion_runs (
    id uuid primary key default gen_random_uuid(),
    knowledge_scope_id uuid not null references knowledge_scopes(id) on delete cascade,
    document_source text not null,
    metadata_snapshot jsonb not null default '{}'::jsonb,
    status text not null default 'pending',
    phases_jsonb jsonb not null default '{}'::jsonb,
    chunk_count integer default 0,
    token_count integer default 0,
    error_code text,
    error_detail text,
    started_at_utc timestamptz,
    completed_at_utc timestamptz,
    created_at_utc timestamptz not null default now()
);

-- Tabla 4: KnowledgeAccessPolicy
create table if not exists knowledge_access_policies (
    id uuid primary key default gen_random_uuid(),
    knowledge_scope_id uuid not null references knowledge_scopes(id) on delete cascade,
    role_code text not null,
    permission_tags text[] not null default '{}',
    allowed_node_paths text[] not null default '{}',
    max_depth integer,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now(),
    constraint uq_knowledge_access_policies_role_scope unique (knowledge_scope_id, role_code)
);

-- Tabla 5: KnowledgeRetrievalPolicy
create table if not exists knowledge_retrieval_policies (
    id uuid primary key default gen_random_uuid(),
    knowledge_scope_id uuid not null references knowledge_scopes(id) on delete cascade,
    assistant_instance_code text,
    package_worker_code text,
    retrieval_mode text not null default 'rag',
    scope_levels int[] not null default '{5,6}',
    max_chunks integer not null default 5,
    metadata_jsonb jsonb not null default '{}'::jsonb,
    status text not null default 'active',
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now()
);
```

### 12.2 Modificaciones a tablas existentes

```sql
-- Agregar node_path a knowledge_documents
alter table knowledge_documents add column if not exists node_path text;

-- Agregar node_path y permission_tags a knowledge_chunks
alter table knowledge_chunks add column if not exists node_path text;
alter table knowledge_chunks add column if not exists permission_tags text[] not null default '{}';

-- Agregar permission_tags a knowledge_chunk_embeddings
alter table knowledge_chunk_embeddings add column if not exists permission_tags text[] not null default '{}';
alter table knowledge_chunk_embeddings add column if not exists organization_code text;
```

### 12.3 Índices adicionales

```sql
create index if not exists idx_knowledge_nodes_parent
    on knowledge_nodes (parent_node_key) where parent_node_key is not null;

create index if not exists idx_knowledge_nodes_path
    on knowledge_nodes using gin (path gin_trgm_ops);

create index if not exists idx_knowledge_nodes_permission_tags
    on knowledge_nodes using gin (permission_tags);

create index if not exists idx_knowledge_chunks_node_path
    on knowledge_chunks (node_path);

create index if not exists idx_knowledge_chunks_permission_tags
    on knowledge_chunks using gin (permission_tags);

create index if not exists idx_knowledge_chunk_embeddings_org
    on knowledge_chunk_embeddings (organization_code);

create index if not exists idx_knowledge_chunk_embeddings_permission_tags
    on knowledge_chunk_embeddings using gin (permission_tags);
```

---

## 13. Qué NO hacer todavía

1. **No upload público**: no implementar endpoint de subida de documentos sin autenticación y autorización
2. **No L2 global sin filtros**: no permitir retrieval global sin filtros multi-tenant obligatorios
3. **No Arango/Milvus productivo sin scope cerrado**: no activar ArangoDB o Milvus en producción hasta que el modelo de KnowledgeMap/KnowledgeNode esté implementado y validado
4. **No knowledge cross-customer**: no permitir retrieval entre organizaciones sin política explícita de scope compartido
5. **No usar Vera como código técnico**: ningún identificador técnico debe contener `vera` (política establecida en `lat.md/customer-packaged-assistant-instance.md`)
6. **No crear motor paralelo**: el worker de ingesta debe ser un worker más de Team360, no un servicio separado con su propia infraestructura
7. **No implementar código ni migraciones ahora**: este documento es diseño únicamente

---

## 14. Plan de implementación posterior

### Fase 1: Documento de diseño y validación

- [x] Crear este documento de diseño
- [ ] Revisar con el equipo técnico
- [ ] Validar contra casos de uso reales (Team360.live, Mamá Mía 360, futuros clientes enterprise)

### Fase 2: Metadata y mocks (solo modelos de datos)

- [ ] Extender `knowledge_documents.metadata_jsonb` con campos de metadata (node_path, access_tags, etc.)
- [ ] Extender `knowledge_chunks` con node_path y permission_tags
- [ ] Crear mocks de árbol organizacional para pruebas

### Fase 3: Worker skeleton

- [ ] Crear `knowledge_ingestion_worker` como worker definition en seed
- [ ] Implementar estructura base del worker con las 8 fases como stubs
- [ ] Implementar validación de metadata (Fase 1)
- [ ] Registrar corridas de ingesta (KnowledgeIngestionRun en PostgreSQL)

### Fase 4: Ingesta Markdown/PDF

- [ ] Implementar conversión a Markdown (Fase 2)
- [ ] Implementar chunker semántico con awareness de contexto organizacional (Fase 5)
- [ ] Guardar documento y chunks en PostgreSQL (Fase 6)

### Fase 5: SemanticChunker

- [ ] Implementar chunker con awareness de nodo/path
- [ ] Implementar L0 (resumen ejecutivo) y L1 (secciones)
- [ ] Validar calidad de chunks con golden queries

### Fase 6: PostgreSQL operational records

- [ ] Implementar KnowledgeAccessPolicy para filtrar por rol
- [ ] Implementar KnowledgeRetrievalPolicy por asistente
- [ ] Implementar retrieval con filtros de node_path y permission_tags sobre pgvector

### Fase 7: ArangoDB / Milvus integration

- [ ] Implementar KnowledgeMap/KnowledgeNode en ArangoDB como grafo
- [ ] Implementar resolución de nodos permitidos contra ArangoDB
- [ ] Indexar embeddings en Milvus con metadata de filtro (node_path, permission_tags)
- [ ] Implementar retrieval con filtros resueltos contra Milvus

### Fase 8: Retrieval policy

- [ ] Implementar cascada completa de retrieval por capas
- [ ] Implementar revalidación de resultados contra PostgreSQL/ArangoDB
- [ ] Implementar fallback Arango-only si Milvus no está disponible

### Fase 9: Console admin

- [ ] UI para gestionar KnowledgeMaps y KnowledgeNodes
- [ ] UI para subir documentos con metadata
- [ ] UI para monitorear corridas de ingesta
- [ ] UI para definir KnowledgeAccessPolicy y KnowledgeRetrievalPolicy

---

## 15. Recomendación final

### Orden correcto para avanzar

```text
1. DISEÑO (este documento) → validar con equipo
2. METADATA → extender tablas existentes con node_path y permission_tags
3. WORKER SKELETON → knowledge_ingestion_worker con fases 1-6
4. INGESTA REAL → Markdown/PDF con metadata completa
5. CHUNKER SEMÁNTICO → con awareness de contexto organizacional
6. POSTGRESQL RETRIEVAL → filtrado por path y tags sobre pgvector
7. ARANGO/MILVUS → integración con grafo de nodos e índice vectorial
8. RETRIEVAL POLICY → cascada completa por capas
9. CONSOLE ADMIN → UI de gestión
```

No saltar fases. No implementar Arango/Milvus antes de que el modelo de nodos y políticas esté funcionando en PostgreSQL. No abrir upload público sin access policies.

Mantener los identificadores técnicos estables acordados:

| Rol | Identificador |
|---|---|
| assistant_instance_code | `team360_sales_diagnosis` |
| package_code | `pkg_sales_diagnosis` |
| knowledge_scope_code | `ks_team360_sales_diagnosis` |
| service_code | `svc_sales_diagnosis` |

Vera es solo nombre comercial visible, no identificador técnico.
