# Knowledge RAG GraphRAG

Team360 needs flexible knowledge scopes. Do not choose globally between RAG and GraphRAG for the whole platform.

The retrieval decision belongs to each `knowledge_scope`.

```text
knowledge_scope.retrieval_mode = none | rag | graphrag | hybrid
```

## Binding Levels

A knowledge scope can bind to:

- workspace;
- assistant_instance;
- automation_package;
- package_worker.

## Phase 1 Model

Minimum model:

```text
knowledge_scope
knowledge_document
knowledge_chunk
```

Phase 1 can use simple RAG or basic retrieval over documents/chunks.

## Future Graph Model

Prepare for:

```text
knowledge_entity
knowledge_relation
knowledge_graph
```

GraphRAG should be activated only when relationships add real value.

## Retrieval Criteria

Use RAG simple for:

- first implementation;
- speed;
- low cost;
- easy debugging;
- policy and documentation lookup;
- small internal knowledge scopes.

Use GraphRAG for premium or complex packages where entity relationships matter:

- SAP B1 / ERP;
- administrative processes across departments;
- customers, orders, invoices, payments and accounts receivable;
- inventory, purchases, suppliers and margins;
- action audit trails;
- multi-worker dependencies;
- workflows with related entities.

## Principle

RAG provides context.

GraphRAG provides relationships when the domain justifies it.

LiteLLM interprets and drafts.

Scoring/classifier decides.

Team360 governs and audits.
