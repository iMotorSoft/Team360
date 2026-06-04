# Knowledge Scope Contract

Team360 uses a stable knowledge contract derived from the proven JudaismoEnVivo RAG pattern.

This document defines the conceptual entities for Team360 knowledge runtime. It does not implement ArangoDB, Milvus, pgvector or any driver.

Related decisions: [[knowledge-rag-graphrag]], [[ai-diagnosis-rag-runtime]], [[customer-packaged-assistant-instance]], [[postgres-ai-persistence]] and [[security-hitl-mfa]].

## JudaismoEnVivo Mapping

The JudaismoEnVivo baseline uses:

```text
Catalog -> MD -> Chunk -> Milvus vector
```

Team360 maps this to:

```text
KnowledgeScope -> KnowledgeDocument -> KnowledgeChunk -> VectorEmbedding
```

Equivalence:

| JudaismoEnVivo | Team360 | Meaning |
| --- | --- | --- |
| `Catalog` | `KnowledgeScope` | queryable corpus boundary |
| `Catalog._key` / `catalog_key` | `knowledge_scope_id` | required retrieval filter |
| `MD` | `KnowledgeDocument` | source text/document block |
| `MD._key` / `md_key` | `document_id` | source document identifier |
| `Chunk` | `KnowledgeChunk` | retrievable semantic unit |
| `Chunk._key` / `chunk_key` | `chunk_id` | chunk identifier |
| Milvus row | `VectorEmbedding` | derived vector index row |

## Core Rule

```text
PostgreSQL owns operational truth.
ArangoDB owns knowledge text and graph.
Milvus owns derived vector search.
pgvector remains laboratory/fallback.
```

ArangoDB and Milvus must never become the commercial source of truth for customers, packages, workers, permissions, diagnosis sessions, final leads, billing or audit.

## Entities

### KnowledgeScope

`KnowledgeScope` is the queryable boundary for a corpus.

It binds knowledge to one or more of:

- organization;
- workspace;
- assistant instance;
- automation package;
- package worker;
- public/partner sales channel.

Required fields:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
retrieval_mode
status
version
locale_policy
```

`knowledge_scope_id` is the Team360 equivalent of JudaismoEnVivo `catalog_key`.

No retrieval query can run without a resolved `knowledge_scope_id`.

### KnowledgeDocument

`KnowledgeDocument` is the source text/document unit.

In the first RAG runtime, ArangoDB is the recommended source for `KnowledgeDocument` because it can hold both document text and graph relationships.

Required fields:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
document_id
document_type
source_kind
source_uri
title
language
version
status
markdown_text
metadata
created_at_utc
updated_at_utc
```

`markdown_text` is the Team360 equivalent of JudaismoEnVivo `MD.markdown_text`.

### KnowledgeChunk

`KnowledgeChunk` is the semantic retrieval unit derived from a `KnowledgeDocument`.

Team360 should persist `chunk_text`.

JudaismoEnVivo proved that tracing `chunk_key -> md_key -> catalog_key` works, but it also showed a weakness: if chunk text is not persisted, the runtime may need to retrieve larger Markdown blocks than necessary. Team360 should keep `chunk_text` to improve evidence precision, debugging, grounding, prompt size control and auditability.

Required fields:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
document_id
chunk_id
chunk_index
chunk_text
source_kind
language
version
status
metadata
created_at_utc
updated_at_utc
```

### VectorEmbedding

`VectorEmbedding` is a derived search row, not truth.

Milvus is the initial vector search runtime for diagnosis and sales knowledge. A vector row must be rebuildable from ArangoDB source documents/chunks and Team360 metadata.

Required metadata:

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

The embedding vector itself belongs to the vector index. The source text belongs to ArangoDB.

## Mandatory Multi-Tenant Filters

Every knowledge retrieval must filter by:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
status
version or active_version
```

When available, retrieval should also filter by:

```text
source_kind
language
document_type
package_worker_id
market
site_channel
```

Cross-customer retrieval is forbidden unless a future explicit global/shared scope is created with a documented access policy.

## ArangoDB Boundary

ArangoDB is the first knowledge text and graph runtime for:

- `KnowledgeScope` graph bindings;
- `KnowledgeDocument` source text;
- `KnowledgeChunk` source chunks;
- relationships between processes, pains, risks, systems, packages and workers;
- fallback retrieval when Milvus is unavailable.

Default collection strategy:

```text
shared domain collections
  + mandatory tenant/scope fields
  + logical graph per knowledge_scope or assistant_instance
```

Do not create one physical collection per customer by default. Physical isolation is reserved for enterprise/compliance, high volume, legal isolation, performance proof or dedicated deployment contract.

## Milvus Boundary

Milvus is the first vector search runtime.

It stores:

- vector embeddings;
- retrieval metadata;
- references to `knowledge_scope_id`, `document_id` and `chunk_id`.

It does not store:

- commercial truth;
- final diagnosis records;
- permissions;
- billing state;
- authoritative source text.

Milvus results must be revalidated against ArangoDB/PostgreSQL scope metadata before being used as LLM context.

## pgvector Boundary

pgvector is already available in PostgreSQL, but it is not the primary RAG runtime for the first diagnosis release.

Allowed use:

- laboratory comparisons;
- small internal scopes;
- fallback experiments;
- PostgreSQL-only deployment research;
- future consolidation if metrics justify it.

Do not migrate the ArangoDB knowledge runtime to PostgreSQL/JSONB/pgvector now.

## Arango-Only Fallback

Team360 should define a fallback retrieval path that uses ArangoDB only when Milvus is unavailable or degraded.

Fallback behavior:

```text
resolve KnowledgeScope
filter ArangoDB by tenant/scope/status/version
retrieve KnowledgeChunk or KnowledgeDocument text
rank with deterministic rules or simple lexical scoring
send bounded context to LiteLLM
mark response metadata as arango_only_fallback
```

The fallback should prefer reduced recall over cross-scope leakage.

## Milvus 2.6 Rule

Milvus 2.6 has evidence as a parallel compatibility path from JudaismoEnVivo labs.

For Team360:

```text
Milvus 2.6 is a validation target, not an automatic migration.
```

Before adopting it, validate:

- client/server compatibility;
- metadata filter behavior;
- index parity;
- restore/backup behavior;
- vector non-zero integrity;
- latency and recall against golden questions;
- behavior with Team360 multi-tenant filters.

## Non-Goals

This contract does not:

- implement ArangoDB drivers;
- implement Milvus drivers;
- create migrations;
- change runtime retrieval;
- replace PostgreSQL;
- migrate ArangoDB knowledge to PostgreSQL;
- make pgvector the primary runtime.

## Decision

Team360 formalizes:

```text
KnowledgeScope / KnowledgeDocument / KnowledgeChunk / VectorEmbedding
```

as the canonical knowledge contract for the diagnosis/sales assistant.

The first implementation should follow the JudaismoEnVivo lesson:

```text
scope first, text/grafo in ArangoDB, vectors in Milvus, model calls through LiteLLM, truth in PostgreSQL.
```
